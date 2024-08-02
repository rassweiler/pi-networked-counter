#! /usr/bin/env python3

import os
import sys
import sqlite3
from csv import writer
from datetime import datetime, timedelta
from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt, QThreadPool,pyqtSlot, QTimer
from gpiozero import DistanceSensor
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget
from MainWindow import Ui_MainWindow
from Product import Product
from Worker import WorkerSignals, SensorWorker
from Count import Count

class ObjectCounter(QMainWindow, Ui_MainWindow):
    def __init__(self, parent = None):
        super().__init__(parent)
        self.setupUi(self)

        #Create table structures
        self.connection = sqlite3.connect('/home/tech/pi-networked-counter/database.db',detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
        self.cursor = self.connection.cursor()
        self.cursor.execute('PRAGMA foreign_keys = ON')
        self.cursor.execute('CREATE TABLE IF NOT EXISTS settings(setting_id TEXT PRIMARY KEY UNIQUE, title TEXT, value TEXT);')
        self.cursor.execute('CREATE TABLE IF NOT EXISTS products(product_id INTEGER PRIMARY KEY UNIQUE, title TEXT, target_count INTEGER, product_weight REAL);')
        self.cursor.execute('CREATE TABLE IF NOT EXISTS counts(countdatetime INTEGEGER PRIMARY KEY UNIQUE, machine TEXT NOT NULL, reject INTEGER NOT NULL, product_id INTEGER NOT NULL, FOREIGN KEY(product_id) REFERENCES products (product_id) ON DELETE CASCADE);')
        result = self.cursor.execute('SELECT EXISTS (SELECT 1 FROM settings);').fetchone()
        if not result[0]:
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('is_reject_enabled', 'Rejects Enabled', "True"))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('trigger_point', 'Trigger Point', "20.0"))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('machine_name', 'Machine Name', "sample_machine"))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('export_backend', 'Export Backend', "0"))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('export_frequency', 'Export Frequency', "10"))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('export_target_folder', 'Export Target Folder', ""))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('export_sharepoint_site', 'Sharepoint Site', ""))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('export_sharepoint_username', 'Sharepoint Username', ""))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('export_sharepoint_password', 'Sharepoint Password', ""))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('tech_password', 'Tech Password', "230167"))
            self.connection.commit()

        result = self.cursor.execute('SELECT * FROM settings WHERE setting_id="is_reject_enabled"').fetchone()
        if result:
            self.is_reject_enabled: bool = result[2] == "True"
            self.labelOutfeedDebug.setEnabled(self.is_reject_enabled)
        else:
             self.is_reject_enabled: bool = False
        result = self.cursor.execute('SELECT * FROM settings WHERE setting_id="trigger_point"').fetchone()
        if result:
            self.trigger_point: float = float(result[2])
        else:
            self.trigger_point: float = 20.0
        result = self.cursor.execute('SELECT * FROM settings WHERE setting_id="machine_name"').fetchone()
        if result:
            self.machine_name: str = result[2]
        else:
            self.machine_name: str = "SampleMachine"
        result = self.cursor.execute('SELECT * FROM settings WHERE setting_id="export_backend"').fetchone()
        if result:
            self.export_backend: int = int(result[2])
        else:
            self.export_backend: int = 0
        result = self.cursor.execute('SELECT * FROM settings WHERE setting_id="export_frequency"').fetchone()
        if result:
            self.export_frequency: int = int(result[2])
        else:
            self.export_frequency: int = 10
        result = self.cursor.execute('SELECT * FROM settings WHERE setting_id="export_target_folder"').fetchone()
        if result:
            self.export_target_folder: str = result[2]
        else:
            self.export_target_folder: str = ""
        result = self.cursor.execute('SELECT * FROM settings WHERE setting_id="export_sharepoint_site"').fetchone()
        if result:
            self.export_sharepoint_site: str = result[2]
        else:
            self.export_sharepoint_site: str = ""
        result = self.cursor.execute('SELECT * FROM settings WHERE setting_id="export_sharepoint_username"').fetchone()
        if result:
            self.export_sharepoint_username: str = result[2]
        else:
            self.export_sharepoint_username: str = ""
        result = self.cursor.execute('SELECT * FROM settings WHERE setting_id="export_sharepoint_password"').fetchone()
        if result:
            self.export_sharepoint_password: str = result[2]
        else:
            self.export_sharepoint_password: str = ""
        result = self.cursor.execute('SELECT * FROM settings WHERE setting_id="tech_password"').fetchone()
        if result:
            self.tech_password: str = result[2]
        else:
            self.tech_password: str = "230167"
        result = self.cursor.execute('SELECT * FROM settings WHERE setting_id="ops_password"').fetchone()
        if result:
            self.ops_password: str = result[2]
        else:
            self.ops_password: str = "111111"
        self.infeed_sensor: DistanceSensor = DistanceSensor(echo=27, trigger=17)
        self.infeed_result: float = -1.0
        self.outfeed_sensor: DistanceSensor = DistanceSensor(echo=24, trigger=23)
        self.outfeed_result: float = -1.0
        self.infeed_detected: bool = False
        self.outfeed_detected: bool = False
        self.current_good: int = 0
        self.current_reject: int = 0
        self.all_products: list = []
        self.loaded_product: Product = None
        self.selected_product: Product = None
        self.last_count: Count = None
        self.quality_percent: float = 0
        self.is_logged_in: bool = False
        self.is_fullscreen: bool = True
        self.is_runing_exports: bool = False

        self.set_ui()
        self.get_all_products()

        #Setup sensor threads
        self.threadpool = QThreadPool()
        self.signalInfeed = WorkerSignals()
        self.signalOutfeed = WorkerSignals()
        self.signalInfeed.result.connect(self.process_infeed)
        self.signalOutfeed.result.connect(self.process_outfeed)
        self.setup_threads()
        if self.export_backend > 0:
            self.export_data()

    def set_ui(self):
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.showFullScreen()
        self.buttonExit.clicked.connect(self.quit_app)
        self.productList.itemSelectionChanged.connect(self.product_list_selection_changed)
        self.buttonLoadProduct.clicked.connect(self.load_product)
        self.buttonResetCount.clicked.connect(self.reset_counts)
        self.buttonSaveProduct.clicked.connect(self.update_product)
        self.buttonSaveNewProduct.clicked.connect(self.create_product)
        self.buttonDeleteProduct.clicked.connect(self.delete_product)
        self.comboBoxExportBackend.currentIndexChanged.connect(self.export_backend_changed)
        self.spinBoxExportFrequency.valueChanged.connect(self.export_frequency_changed)
        self.lineEditTargetFolder.textChanged.connect(self.export_target_folder_changed)
        self.lineEditSharepointSite.textChanged.connect(self.export_sharepoint_site_changed)
        self.lineEditSharepointUser.textChanged.connect(self.export_sharepoint_username_changed)
        self.lineEditSharepointPassword.textChanged.connect(self.export_sharepoint_password_changed)
        self.lineEditMachineName.textChanged.connect(self.machine_name_changed)
        self.buttonLogin.released.connect(self.login_attempt)
        self.buttonToggleFullscreen.released.connect(self.toggle_fullscreen)
        if self.is_reject_enabled:
            self.frameRejects.setVisible(True)
            self.frameQualityPercent.setVisible(True)
            self.checkBoxEnableRejects.setChecked(2)
            self.labelGoodText.setVisible(True)
        else:
            self.frameRejects.setVisible(False)
            self.frameQualityPercent.setVisible(False)
            self.checkBoxEnableRejects.setChecked(0)
            self.labelGoodText.setVisible(False)
        self.lineEditMachineName.setText(self.machine_name)
        self.checkBoxEnableRejects.stateChanged.connect(self.reject_setting_changed)
        self.doubleSpinBoxTriggerPoint.setValue(self.trigger_point)
        self.doubleSpinBoxTriggerPoint.valueChanged.connect(self.trigger_point_changed)
        self.frameCountTarget.setVisible(False)
        self.comboBoxExportBackend.setCurrentIndex(self.export_backend)
        self.spinBoxExportFrequency.setValue(self.export_frequency)
        self.lineEditTargetFolder.setText(self.export_target_folder)
        self.lineEditSharepointSite.setText(self.export_sharepoint_site)
        self.lineEditSharepointUser.setText(self.export_sharepoint_username)
        self.lineEditSharepointPassword.setText(self.export_sharepoint_password)
        self.export_backend_changed(self.export_backend)
        self.login_attempt()

    def setup_threads(self):
        worker_infeed = SensorWorker(sensor=self.infeed_sensor, signals=self.signalInfeed)
        self.threadpool.start(worker_infeed)
        if self.is_reject_enabled:
            worker_outfeed = SensorWorker(sensor=self.outfeed_sensor, signals=self.signalOutfeed)
            self.threadpool.start(worker_outfeed)
        QTimer.singleShot(150, self.setup_threads)

    def export_data(self):
        result = self.cursor.execute("SELECT * FROM counts WHERE countdatetime >= ?",(datetime.now() - timedelta(minutes=self.export_frequency),))
        #rows = result.fetchall()
        if result:
            if self.export_backend == 1:
                if self.export_target_folder != "":
                    with open(self.export_target_folder + "Counts_" + str(datetime.now()) + '.csv', 'w', newline='') as f:
                        w = writer(f)
                        w.writerow(["Date Time", "Machine", "Reject", "Product ID"])
                        w.writerows(result)
                    f.close()
        result = self.cursor.execute("SELECT * FROM products")
        if result:
            if self.export_backend == 1:
                if self.export_target_folder != "":
                    with open(self.export_target_folder + "Products_" + str(datetime.now()) + '.csv', 'w', newline='') as f:
                        w = writer(f)
                        w.writerow(["ID", "Title", "Target Count", "Product Weight"])
                        w.writerows(result)
                    f.close()
        if self.export_backend > 0:
            self.is_runing_exports = True
            QTimer.singleShot(1000 * 60 * self.export_frequency, self.export_data)
        else:
            self.is_runing_exports = False

    @pyqtSlot(float)
    def process_infeed(self, distance):
        if distance == self.infeed_result:
            return
        self.infeed_result = distance
        self.labelInfeedDebug.setText(str(distance))
        if self.loaded_product:
            if distance <= self.trigger_point:
                if not self.infeed_detected:
                    self.infeed_detected = True
                    if not self.is_reject_enabled:
                        self.count_good(time=datetime.now())
                        self.update_counts()
                        self.last_count = None
                        return
                    else:
                        if self.last_count:
                            self.count_reject(time=datetime.now(), count=self.last_count)
                            self.update_counts()
                            self.last_count = Count(self.loaded_product.product_id, datetime.now())
                        else:
                            self.last_count = Count(self.loaded_product.product_id, datetime.now())
            else:
                self.infeed_detected = False

    @pyqtSlot(float)
    def process_outfeed(self, distance):
        if distance == self.outfeed_result:
            return
        self.outfeed_result = distance
        self.labelOutfeedDebug.setText(str(distance))
        if self.loaded_product:
            if distance <= self.trigger_point:
                if not self.outfeed_detected:
                    self.outfeed_detected = True
                    if self.is_reject_enabled and self.last_count:
                        self.count_good(time=datetime.now(), count=self.last_count)
                        self.update_counts()
                        self.last_count = None
            else:
                self.outfeed_detected = False

    def count_good(self, time: datetime, count: Count = None):
        if count:
            self.cursor.execute('INSERT INTO counts VALUES (?,?,?,?);', (count.date,self.machine_name,0,count.product_id))
        else:
            self.cursor.execute('INSERT INTO counts VALUES (?,?,?,?);', (time,self.machine_name,0,self.loaded_product.product_id))
        self.connection.commit()
        self.current_good += 1

    def count_reject(self, time: datetime, count: Count = None):
        if count:
            self.cursor.execute('INSERT INTO counts VALUES (?,?,?,?);', (count.date,self.machine_name,1,count.product_id))
        else:
            self.cursor.execute('INSERT INTO counts VALUES (?,?,?,?);', (time,self.machine_name,1,self.loaded_product.product_id))
        self.connection.commit()
        self.current_reject += 1

    def get_all_products(self):
        self.all_products.clear()
        self.cursor.execute('SELECT * FROM products')
        products = self.cursor.fetchall()
        for product in products:
            self.all_products.append(Product(product[0],product[1],product[2],product[3]))
        self.update_product_list()

    def update_product_list(self):
        self.productList.clear()
        for product in self.all_products:
            self.productList.addItem(product.name)

    def product_list_selection_changed(self):
        item = self.productList.selectedItems()
        
        if item:
            for product in self.all_products:
                if product.name == item[0].text():
                    self.selected_product = product
                    break
            self.productName.setText(self.selected_product.name)
            self.productTargetCount.setText(str(self.selected_product.count))
            self.productWeight.setText(str(self.selected_product.weight))
        else:
            self.productName.setText("")
            self.productTargetCount.setText("")
            self.productWeight.setText("")

    def update_product(self):
        if self.selected_product:
            self.selected_product.name = self.productName.text()
            self.selected_product.count = int(self.productTargetCount.text())
            self.selected_product.weight = float(self.productWeight.text())
            self.cursor.execute('UPDATE products SET title = ?, target_count = ?, product_weight = ? WHERE product_id = ?', (self.selected_product.name, self.selected_product.count, self.selected_product.weight, self.selected_product.product_id))
            self.connection.commit()
            self.update_product_list()

    def create_product(self):
        if self.productName.text() and self.productTargetCount.text() and self.productWeight.text():
            self.cursor.execute('INSERT INTO products(title, target_count, product_weight) VALUES(?, ?, ?)', (self.productName.text(), int(self.productTargetCount.text()), float(self.productWeight.text())))
            self.connection.commit()
            self.get_all_products()
            self.update_product_list()

    def delete_product(self):
        if self.selected_product and len(self.all_products) > 1:
            self.cursor.execute('DELETE FROM products WHERE product_id = ?', (str(self.selected_product.product_id)))
            self.connection.commit()
            self.selected_product = None
            self.product_list_selection_changed()
            self.get_all_products()
            self.update_product_list()

    def load_product(self):
        if self.selected_product:
            self.loaded_product = self.selected_product
            self.labelCurrentProduct.setText(self.loaded_product.name)
            self.reset_counts()
            if self.loaded_product.count > 0 and not self.is_reject_enabled:
                self.frameCountTarget.setVisible(True)
            else:
                self.frameCountTarget.setVisible(False)
            self.labelCountTarget.setText(str(self.loaded_product.count))

    def reset_counts(self):
        if self.last_count:
            self.count_reject(time=datetime.now(), count=self.last_count)
            self.update_counts()
            self.last_count = None
        self.current_good = 0
        self.current_reject = 0
        pallette = self.tab.palette()
        pallette.setColor(self.tab.backgroundRole(), QColor(239,239,239))
        self.tab.setPalette(pallette)
        self.update_counts()

    def update_counts(self):
        self.labelGood.setText(str(self.current_good))
        self.labelRejects.setText(str(self.current_reject))
        if self.current_good + self.current_reject > 0:
            self.quality_percent = float(self.current_good / (self.current_good + self.current_reject)) * 100
        else:
            self.quality_percent = 0
        self.labelQualityPercent.setText(str(round(self.quality_percent, 2)))
        if self.loaded_product.count > 0 and not self.is_reject_enabled:
            if self.current_good == self.loaded_product.count:
                pallette = self.tab.palette()
                pallette.setColor(self.tab.backgroundRole(), QColor(100,250,100))
                self.tab.setPalette(pallette)
            elif self.current_good > self.loaded_product.count:
                pallette = self.tab.palette()
                pallette.setColor(self.tab.backgroundRole(), QColor(250,100,100))
                self.tab.setPalette(pallette)

    def machine_name_changed(self, name: str):
        if name != self.machine_name:
            self.machine_name = name
            self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "machine_name"', (str(self.machine_name),))
            self.connection.commit()

    def reject_setting_changed(self, state):
        value: bool = state == Qt.CheckState.Checked.value
        if value != self.is_reject_enabled:
            self.is_reject_enabled = value
            self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "is_reject_enabled"', (str(self.is_reject_enabled),))
            self.connection.commit()
            self.labelOutfeedDebug.setEnabled(value)
            self.frameRejects.setVisible(value)
            self.frameQualityPercent.setVisible(value)
        if not value:
            self.outfeed_result = -1
            if self.loaded_product and self.loaded_product.count > 0:
                self.frameCountTarget.setVisible(True)
            self.labelGoodText.setVisible(False)
        else:
            self.frameCountTarget.setVisible(False)
            self.labelGoodText.setVisible(True)
    
    def trigger_point_changed(self, value):
        if value != self.trigger_point:
            self.trigger_point = value
            self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "trigger_point"', (str(self.trigger_point),))
            self.connection.commit()

    def export_backend_changed(self, index: int):
        self.export_backend = index
        self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "export_backend"', (str(self.export_backend),))
        self.connection.commit()
        if index == 0:
            self.labelExportFrequency.setVisible(False)
            self.spinBoxExportFrequency.setVisible(False)
            self.labelFolder.setVisible(False)
            self.labelSharepointUser.setVisible(False)
            self.labelSharepointSite.setVisible(False)
            self.labelSharepointPassword.setVisible(False)
            self.lineEditSharepointSite.setVisible(False)
            self.lineEditSharepointUser.setVisible(False)
            self.lineEditSharepointPassword.setVisible(False)
            self.lineEditTargetFolder.setVisible(False)
        elif index == 1:
            self.labelExportFrequency.setVisible(True)
            self.spinBoxExportFrequency.setVisible(True)
            self.labelFolder.setVisible(True)
            self.lineEditTargetFolder.setVisible(True)
            self.labelSharepointUser.setVisible(False)
            self.labelSharepointSite.setVisible(False)
            self.labelSharepointPassword.setVisible(False)
            self.lineEditSharepointSite.setVisible(False)
            self.lineEditSharepointUser.setVisible(False)
            self.lineEditSharepointPassword.setVisible(False)
            if not self.is_runing_exports:
                self.export_data()
        elif index == 2:
            self.labelExportFrequency.setVisible(True)
            self.spinBoxExportFrequency.setVisible(True)
            self.labelFolder.setVisible(False)
            self.labelSharepointUser.setVisible(True)
            self.labelSharepointSite.setVisible(True)
            self.labelSharepointPassword.setVisible(True)
            self.lineEditSharepointSite.setVisible(True)
            self.lineEditSharepointUser.setVisible(True)
            self.lineEditSharepointPassword.setVisible(True)
            self.lineEditTargetFolder.setVisible(False)
            if not self.is_runing_exports:
                self.export_data()
        else:
            self.labelExportFrequency.setVisible(False)
            self.spinBoxExportFrequency.setVisible(False)
            self.labelFolder.setVisible(False)
            self.labelSharepointUser.setVisible(False)
            self.labelSharepointSite.setVisible(False)
            self.labelSharepointPassword.setVisible(False)
            self.lineEditSharepointSite.setVisible(False)
            self.lineEditSharepointUser.setVisible(False)
            self.lineEditSharepointPassword.setVisible(False)
            self.lineEditTargetFolder.setVisible(False)

    def export_frequency_changed(self, frequency: int):
        if frequency != self.export_frequency:
            self.export_frequency = frequency
            self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "export_frequency"', (str(self.export_frequency),))
            self.connection.commit()

    def export_target_folder_changed(self, target: str):
        if target != self.export_target_folder:
            self.export_target_folder = target
            self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "export_target_folder"', (str(self.export_target_folder),))
            self.connection.commit()

    def export_sharepoint_site_changed(self, target: str):
        if target != self.export_sharepoint_site:
            self.export_sharepoint_site = target
            self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "export_sharepoint_site"', (str(self.export_sharepoint_site),))
            self.connection.commit()

    def export_sharepoint_username_changed(self, target: str):
        if target != self.export_sharepoint_username:
            self.export_sharepoint_username = target
            self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "export_sharepoint_username"', (str(self.export_sharepoint_username),))
            self.connection.commit()

    def export_sharepoint_password_changed(self, target: str):
        if target != self.export_sharepoint_password:
            self.export_sharepoint_password = target
            self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "export_sharepoint_password"', (str(self.export_sharepoint_password),))
            self.connection.commit()

    def on_toggle_fullscreen(self):
        pass

    def login_attempt(self):
        if self.lineEditLogin.text() == self.tech_password:
            self.tabSettings.setEnabled(True)
            self.buttonExit.setEnabled(True)
            self.frameProductControl.setEnabled(True)
            self.buttonLogin.setText("Logout")
        elif self.lineEditLogin.text() == self.ops_password:
            self.frameProductControl.setEnabled(True)
            self.buttonLogin.setText("Logout")
        else:
            self.tabSettings.setEnabled(False)
            self.buttonExit.setEnabled(False)
            self.frameProductControl.setEnabled(False)
            self.buttonLogin.setText("Login")
        self.lineEditLogin.setText("")

    def toggle_fullscreen(self):
        self.is_fullscreen = not self.is_fullscreen
        if self.is_fullscreen:
            self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
            self.showFullScreen()
        else:
            self.setWindowFlags(Qt.WindowType.WindowCloseButtonHint)
            self.showMaximized()
        

    def quit_app(self):
        self.connection.close()
        QApplication.quit()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ObjectCounter()
    sys.exit(app.exec())

    