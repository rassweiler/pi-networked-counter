#! /usr/bin/env python3

import os
import sys
import sqlite3
import datetime
from PyQt6.QtCore import Qt, QThreadPool,pyqtSlot, QTimer
from gpiozero import DistanceSensor
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget
from MainWindow import Ui_MainWindow
from Product import Product
from Worker import WorkerSignals, SensorWorker

class ObjectCounter(QMainWindow, Ui_MainWindow):
    def __init__(self, parent = None):
        super().__init__(parent)
        self.setupUi(self)

        #Create table structures
        self.connection = sqlite3.connect('/home/tech/pi-networked-counter/database.db',detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
        self.cursor = self.connection.cursor()
        self.cursor.execute('PRAGMA foreign_keys = ON')
        self.cursor.execute('CREATE TABLE IF NOT EXISTS settings(setting_id TEXT PRIMARY KEY UNIQUE, title TEXT, value REAL);')
        self.cursor.execute('CREATE TABLE IF NOT EXISTS products(product_id INTEGER PRIMARY KEY UNIQUE, title TEXT, target_count INTEGER, product_weight REAL);')
        self.cursor.execute('CREATE TABLE IF NOT EXISTS counts(countdatetime INTEGEGER PRIMARY KEY UNIQUE, reject INTEGER NOT NULL, product_id INTEGER NOT NULL, FOREIGN KEY(product_id) REFERENCES products (product_id));')
        result = self.cursor.execute('SELECT EXISTS (SELECT 1 FROM settings);').fetchone()
        if not result[0]:
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('is_reject_enabled', 'Rejects Enabled', 1.0))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('trigger_point', 'Trigger Point', 20.0))
            self.connection.commit()

        result = self.cursor.execute('SELECT * FROM settings WHERE setting_id="is_reject_enabled"').fetchone()
        if result:
            self.is_reject_enabled: bool = bool(result[2])
            self.labelOutfeedDebug.setEnabled(self.is_reject_enabled)
        else:
             self.is_reject_enabled: bool = False
        result = self.cursor.execute('SELECT * FROM settings WHERE setting_id="trigger_point"').fetchone()
        if result:
            self.trigger_point: float = float(result[2])
        else:
            self.trigger_point: float = 20.0
        self.infeed_sensor: DistanceSensor = DistanceSensor(echo=27, trigger=17)
        self.infeed_result: float = -1.0
        self.outfeed_sensor: DistanceSensor = DistanceSensor(echo=24, trigger=23)
        self.outfeed_result: float = -1.0
        self.infeed_detected: bool = False
        self.infeed_time: datetime.datetime = None
        self.outfeed_detected: bool = False
        self.current_good: int = 0
        self.current_reject: int = 0
        self.all_products: list = []
        self.loaded_product: Product = None
        self.selected_product: Product = None

        self.set_ui()
        self.get_all_products()

        #Setup sensor threads
        self.threadpool = QThreadPool()
        self.signalInfeed = WorkerSignals()
        self.signalOutfeed = WorkerSignals()
        self.signalInfeed.result.connect(self.process_infeed)
        self.signalOutfeed.result.connect(self.process_outfeed)
        self.setup_threads()

    def set_ui(self):
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.showFullScreen()
        self.exitButton.clicked.connect(self.quit_app)
        self.productList.itemSelectionChanged.connect(self.product_list_selection_changed)
        self.buttonLoadProduct.clicked.connect(self.load_product)
        self.buttonResetCount.clicked.connect(self.reset_counts)
        self.buttonSaveProduct.clicked.connect(self.update_product)
        self.buttonSaveNewProduct.clicked.connect(self.create_product)
        self.buttonDeleteProduct.clicked.connect(self.delete_product)
        if self.is_reject_enabled:
            self.checkBoxEnableRejects.setChecked(2)
        else:
            self.checkBoxEnableRejects.setChecked(0)
        self.checkBoxEnableRejects.checkStateChanged.connect(self.reject_setting_changed)

    def setup_threads(self):
        worker_infeed = SensorWorker(sensor=self.infeed_sensor, signals=self.signalInfeed)
        self.threadpool.start(worker_infeed)
        if self.is_reject_enabled:
            worker_outfeed = SensorWorker(sensor=self.outfeed_sensor, signals=self.signalOutfeed)
            self.threadpool.start(worker_outfeed)
        QTimer.singleShot(500, self.setup_threads)

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
                        self.count_good(time=datetime.datetime.now())
                        self.update_counts()
                        return
                    self.infeed_time = datetime.datetime.now()
            else:
                self.infeed_detected = False

    @pyqtSlot(float)
    def process_outfeed(self, distance):
        if distance == self.outfeed_result:
            return
        self.outfeed_result = distance
        self.labelOutfeedDebug.setText(str(distance))
        if self.loaded_product:
            pass

    def count_good(self, time: datetime.datetime):
        self.cursor.execute('INSERT INTO counts VALUES (?,?,?);', (time,0,self.loaded_product.product_id))
        self.connection.commit()
        self.current_good += 1

    def count_reject(self, time: datetime.datetime):
        self.cursor.execute('INSERT INTO counts VALUES (?,?,?);', (time,1,self.loaded_product.product_id))
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
        if self.selected_product:
            self.cursor.execute('DELETE FROM products WHERE product_id = ?', (str(self.selected_product.product_id)))
            self.connection.commit()
            self.selected_product = None
            self.product_list_selection_changed(None)
            self.get_all_products()
            self.update_product_list()

    def load_product(self):
        if self.selected_product:
            self.loaded_product = self.selected_product
            self.labelCurrentProduct.setText(self.loaded_product.name)
            self.current_good = 0
            self.current_reject = 0

    def reset_counts(self):
        self.current_good = 0
        self.current_reject = 0
        self.update_counts()

    def update_counts(self):
        self.labelGood.setText(str(self.current_good))
        self.labelRejects.setText(str(self.current_reject))

    def reject_setting_changed(self, state):
        value: bool = state == Qt.CheckState.Checked
        if value != self.is_reject_enabled:
            self.is_reject_enabled = value
            self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "is_reject_enabled"', (float(self.is_reject_enabled),))
            self.connection.commit()
            self.labelOutfeedDebug.setEnabled(value)
        if not value:
            self.outfeed_result = -1

    def quit_app(self):
        self.connection.close()
        quit(0)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ObjectCounter()
    sys.exit(app.exec())