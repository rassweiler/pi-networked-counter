#! /usr/bin/env python3

import sys
import sqlite3
import logging
import tomllib
from enum import Enum
from csv import writer
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtCore import Qt, QTimer
from gpiozero import DigitalInputDevice, LED
from PyQt6.QtWidgets import QApplication, QMainWindow
from MainWindow import Ui_MainWindow
from pathlib import Path
from Product import Product
from Count import Count
from SharepointExport import SharepointExport

class ExportBackend(Enum):
    NONE = 0
    FOLDER = 1
    SHAREPOINT = 2

class OperationMode(Enum):
    COUNT = 0
    TARGET = 1
    REJECT = 2
    PACE = 3
    DOUBLE = 4

class OperationState(Enum):
    NORMAL = 0
    WARNING = 1
    FAULT = 2

class ObjectCounter(QMainWindow, Ui_MainWindow): # pyright: ignore[reportUntypedBaseClass]
    def __init__(self, parent = None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.root_dir = Path(__file__).parent
        Path('./logs/').mkdir(parents=True, exist_ok=True)
        logging.basicConfig(filename='./logs/.counter_debug_' + datetime.now().strftime('%Y-%m-%d_%H-%M') + '.log', level=logging.DEBUG)
        self.logger.info('Started Program')
        self.setupUi(self) # pyright: ignore[reportUnknownMemberType]

        self.current_good: int = 0
        self.current_reject: int = 0
        self.all_products: list[Product] = []
        self.loaded_product: Product | None = None
        self.selected_product: Product | None = None
        self.last_count_1: Count | None = None
        self.last_count_2: Count | None = None
        self.count_list_1: list[Count] = []
        self.count_list_2: list[Count] = []
        self.quality_percent: float = 0
        self.current_ppm_1: float = 0
        self.current_ppm_2: float = 0
        self.current_ppm_delta_1: float = 0
        self.current_ppm_delta_2: float = 0
        self.is_logged_in: bool = False
        self.is_fullscreen: bool = True
        self.is_runing_exports_01: bool = False
        self.is_runing_exports_02: bool = False
        self.export_01_timer: QTimer = QTimer()
        self.export_02_timer: QTimer = QTimer()
        self.is_export_setup: bool = False
        self.sharepoint_export: SharepointExport | None = None
        self.current_operation_state: int = OperationState.FAULT.value

        self.operation_mode: int = 0
        self.is_reject_enabled: bool = False
        self.bounce_time: float = 0.1
        self.infeed_pin: int = 17
        self.outfeed_pin: int = 23
        self.stack_pin_green: int = 27
        self.stack_pin_yellow: int = 22
        self.stack_pin_red: int = 24
        self.machine_name: str = "SampleMachine"
        self.export_backend: int = 0
        self.is_export_folder_01_enabled: bool = False
        self.is_export_folder_02_enabled: bool = False
        self.is_export_single_file_enabled: bool = False
        self.export_folder_01_path: str = ""
        self.export_folder_02_path: str = ""
        self.export_folder_01_frequency: int = 1
        self.export_folder_02_frequency: int = 1
        self.export_folder_01_period: int = 1
        self.export_folder_02_period: int = 1
        self.is_export_sharepoint_01_enabled: bool = False
        self.is_export_sharepoint_02_enabled: bool = False
        self.export_sharepoint_01_frequency: int = 1
        self.export_sharepoint_02_frequency: int = 1
        self.export_sharepoint_01_period: int = 1
        self.export_sharepoint_02_period: int = 1
        self.export_sharepoint_01_site_id: str = ""
        self.export_sharepoint_02_site_id: str = ""
        self.export_sharepoint_01_list_id: str = ""
        self.export_sharepoint_02_list_id: str = ""
        self.export_sharepoint_01_path: str = ""
        self.export_sharepoint_02_path: str = ""
        self.tech_password: str = "230167"
        self.ops_password: str = "111111"
        self.is_stack_light_enabled: bool = False

        #Create table structures
        self.logger.info('Setting up tables...')
        self.connection = sqlite3.connect('/home/tech/pi-networked-counter/database.db',detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES, check_same_thread=False)
        self.cursor = self.connection.cursor()
        self.cursor.execute('PRAGMA foreign_keys = ON')
        self.cursor.execute('CREATE TABLE IF NOT EXISTS settings(setting_id TEXT PRIMARY KEY UNIQUE, title TEXT, value TEXT);')
        self.cursor.execute('CREATE TABLE IF NOT EXISTS products(product_id INTEGER PRIMARY KEY UNIQUE, title TEXT, target_count INTEGER, target_pace INTEGER, product_weight REAL);')
        self.cursor.execute('CREATE TABLE IF NOT EXISTS counts(count_id INTEGER PRIMARY KEY, countdatetime INTEGER UNIQUE NOT NULL, machine TEXT NOT NULL, reject INTEGER NOT NULL, product_id INTEGER NOT NULL, FOREIGN KEY(product_id) REFERENCES products (product_id) ON DELETE CASCADE);')
        result = self.cursor.execute('SELECT EXISTS (SELECT 1 FROM settings);').fetchone()
        if not result[0]:
            self.logger.info('Settings not found, creating defaults')
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('operation_mode', 'Operation Mode', "0"))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('bounce_time', 'Bounce Time (s)', "0.1"))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('infeed_pin', 'Infeed Pin', "17"))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('outfeed_pin', 'Outfeed Pin', "23"))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('stack_pin_green', 'Stack Green', "27"))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('stack_pin_yellow', 'Stack Yellow', "22"))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('stack_pin_red', 'Stack Red', "24"))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('machine_name', 'Machine Name', "sample_machine"))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('export_backend', 'Export Backend', "0"))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('is_export_folder_01_enabled', 'Export Folder 01 Enabled', "False"))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('is_export_folder_02_enabled', 'Export Folder 02 Enabled', "False"))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('is_export_single_file_enabled', 'Export Single File Enabled', "False"))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('export_folder_01_path', 'Export Folder 01 Path', ""))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('export_folder_02_path', 'Export Folder 02 Path', ""))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('export_folder_01_frequency', 'Export Folder 01 Frequency', "1"))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('export_folder_02_frequency', 'Export Folder 02 Frequency', "1"))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('export_folder_01_period', 'Export Folder 01 Period', "1"))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('export_folder_02_period', 'Export Folder 02 Period', "1"))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('is_export_sharepoint_01_enabled', 'Export Sharepoint 01 Enabled', "False"))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('is_export_sharepoint_02_enabled', 'Export Sharepoint 02 Enabled', "False"))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('export_sharepoint_01_frequency', 'Export Sharepoint 01 Frequency', "1"))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('export_sharepoint_02_frequency', 'Export Sharepoint 02 Frequency', "1"))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('export_sharepoint_01_period', 'Export Sharepoint 01 Period', "1"))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('export_sharepoint_02_period', 'Export Sharepoint 02 Period', "1"))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('export_sharepoint_01_site_id', 'Export Sharepoint 01 Site ID', ""))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('export_sharepoint_02_site_id', 'Export Sharepoint 02 Site ID', ""))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('export_sharepoint_01_list_id', 'Export Sharepoint 01 List ID', ""))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('export_sharepoint_02_list_id', 'Export Sharepoint 02 List ID', ""))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('export_sharepoint_01_path', 'Export Sharepoint 01 Path', ""))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('export_sharepoint_02_path', 'Export Sharepoint 02 Path', ""))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('tech_password', 'Tech Password', "230167"))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('ops_password', 'Ops Password', "111111"))
            self.cursor.execute('INSERT INTO settings VALUES (?,?,?);', ('is_stack_light_enabled', 'Stack Light Enabled', "False"))
            self.connection.commit()

        result: list[Any] = self.cursor.execute('SELECT * FROM settings').fetchall()
        if result:
            for setting in result:
                match setting[0]:
                    case 'operation_mode':
                        self.operation_mode = int(setting[2])
                    case 'bounce_time':
                        self.bounce_time = float(setting[2])
                    case 'infeed_pin':
                        self.infeed_pin = int(setting[2])
                    case 'outfeed_pin':
                        self.outfeed_pin = int(setting[2])
                    case 'stack_pin_green':
                        self.stack_pin_green = int(setting[2])
                    case 'stack_pin_yellow':
                        self.stack_pin_yellow = int(setting[2])
                    case 'stack_pin_red':
                        self.stack_pin_red = int(setting[2])
                    case 'machine_name':
                        self.machine_name = str(setting[2])
                    case 'export_backend':
                        self.export_backend = int(setting[2])
                    case 'is_export_folder_01_enabled':
                        self.is_export_folder_01_enabled = setting[2] == 'True'
                    case 'is_export_folder_02_enabled':
                        self.is_export_folder_02_enabled = setting[2] == 'True'
                    case 'is_export_single_file_enabled':
                        self.is_export_single_file_enabled = setting[2] == 'True'
                    case 'export_folder_01_path':
                        self.export_folder_01_path = str(setting[2])
                    case 'export_folder_02_path':
                        self.export_folder_02_path = str(setting[2])
                    case 'export_folder_01_frequency':
                        self.export_folder_01_frequency = int(setting[2])
                    case 'export_folder_02_frequency':
                        self.export_folder_02_frequency = int(setting[2])
                    case 'export_folder_01_period':
                        self.export_folder_01_period = int(setting[2])
                    case 'export_folder_02_period':
                        self.export_folder_02_period = int(setting[2])
                    case 'is_export_sharepoint_01_enabled':
                        self.is_export_sharepoint_01_enabled = setting[2] == 'True'
                    case 'is_export_sharepoint_02_enabled':
                        self.is_export_sharepoint_02_enabled = setting[2] == 'True'
                    case 'export_sharepoint_01_path':
                        self.export_sharepoint_01_path = str(setting[2])
                    case 'export_sharepoint_02_path':
                        self.export_sharepoint_02_path = str(setting[2])
                    case 'export_sharepoint_01_frequency':
                        self.export_sharepoint_01_frequency = int(setting[2])
                    case 'export_sharepoint_02_frequency':
                        self.export_sharepoint_02_frequency = int(setting[2])
                    case 'export_sharepoint_01_period':
                        self.export_sharepoint_01_period = int(setting[2])
                    case 'export_sharepoint_02_period':
                        self.export_sharepoint_02_period = int(setting[2])
                    case 'export_sharepoint_01_site_id':
                        self.export_sharepoint_01_site_id = str(setting[2])
                    case 'export_sharepoint_02_site_id':
                        self.export_sharepoint_02_site_id = str(setting[2])
                    case 'export_sharepoint_01_list_id':
                        self.export_sharepoint_01_list_id = str(setting[2])
                    case 'export_sharepoint_02_list_id':
                        self.export_sharepoint_02_list_id = str(setting[2])
                    case 'tech_password':
                        self.tech_password = str(setting[2])
                    case 'ops_password':
                        self.ops_password = str(setting[2])
                    case 'is_stack_light_enabled':
                        self.is_stack_light_enabled = setting[2] == 'True'
                    case _:
                        pass

        self.setup_sensors()
        #self.setup_export()
        self.set_ui()
        self.get_all_products()
        
    def setup_sensors(self):
        self.logger.info('Setting up sensors...')
        self.infeed_sensor: DigitalInputDevice = DigitalInputDevice(pin=self.infeed_pin, pull_up=True, bounce_time=self.bounce_time)
        self.outfeed_sensor: DigitalInputDevice = DigitalInputDevice(pin=self.outfeed_pin, pull_up=True, bounce_time=self.bounce_time)
        self.infeed_sensor.when_activated = self.sensor_activated
        self.outfeed_sensor.when_activated = self.sensor_activated
        self.infeed_sensor.when_deactivated = self.sensor_deactivated
        self.outfeed_sensor.when_deactivated = self.sensor_deactivated
        self.stack_output_green = LED(pin=self.stack_pin_green, initial_value=False)
        self.stack_output_yellow = LED(pin=self.stack_pin_yellow, initial_value=False)
        self.stack_output_red = LED(pin=self.stack_pin_red, initial_value=False)

    def setup_export(self):
        self.logger.info('Setting up exports...')
        self.is_export_setup = False
        if self.export_backend == ExportBackend.NONE.value:
            pass
        elif self.export_backend == ExportBackend.FOLDER.value:
            if not self.is_export_folder_01_enabled and not self.is_export_folder_02_enabled:
                return
            if self.is_export_folder_01_enabled and self.export_folder_01_path == "":
                return
            if self.is_export_folder_02_enabled and self.export_folder_02_path == "":
                return
            self.is_export_setup = True
        elif self.export_backend == ExportBackend.SHAREPOINT.value:
            if not self.is_export_sharepoint_01_enabled and not self.is_export_sharepoint_02_enabled:
                return
            if self.is_export_sharepoint_01_enabled and self.export_sharepoint_01_path == "":
                return
            if self.is_export_sharepoint_02_enabled and self.export_sharepoint_02_path == "":
                return
            if self.is_export_sharepoint_01_enabled and self.export_sharepoint_01_site_id == "":
                return
            if self.is_export_sharepoint_02_enabled and self.export_sharepoint_02_site_id == "":
                return
            if self.is_export_sharepoint_01_enabled and self.export_sharepoint_01_list_id == "":
                return
            if self.is_export_sharepoint_02_enabled and self.export_sharepoint_02_list_id == "":
                return
            #try:
            #    self.sharepoint_export.update_token()
            #except:
            #    return
            self.sharepoint_export = SharepointExport()
            self.is_export_setup = True
        
    def set_ui(self):
        self.logger.info('Setting up ui...')
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.showFullScreen()
        self.buttonExit.clicked.connect(self.quit_app)
        self.productList.itemSelectionChanged.connect(self.product_list_selection_changed)
        self.buttonLoadProduct.clicked.connect(self.load_product)
        self.buttonResetCount.clicked.connect(self.reset_counts)
        self.buttonSaveProduct.clicked.connect(self.update_product)
        self.buttonSaveNewProduct.clicked.connect(self.create_product)
        self.buttonDeleteProduct.clicked.connect(self.delete_product)
        self.spinBoxInfeedPin.valueChanged.connect(self.infeed_pin_changed)
        self.spinBoxOutfeedPin.valueChanged.connect(self.outfeed_pin_changed)
        self.doubleSpinBoxBounceTime.valueChanged.connect(self.bounce_time_changed)
        self.pushButtonTriggerGoodCount.clicked.connect(self.testing_trigger_good_count)
        self.pushButtonTriggerRejectCount.clicked.connect(self.testing_trigger_reject_count)
        #Stacklight
        self.checkBoxEnableStackLight.stateChanged.connect(self.enable_stack_light_changed)
        self.spinBoxStackLightGreenOutput.valueChanged.connect(self.stack_light_pin_green_changed)
        self.spinBoxStackLightYellowOutput.valueChanged.connect(self.stack_light_pin_yellow_changed)
        self.spinBoxStackLightRedOutput.valueChanged.connect(self.stack_light_pin_red_changed)
        self.comboBoxOperationMode.currentIndexChanged.connect(self.operation_mode_changed)
        self.lineEditMachineName.textChanged.connect(self.machine_name_changed)
        self.lineEditLogin.returnPressed.connect(self.login_attempt)
        self.buttonLogin.released.connect(self.login_attempt)
        self.buttonToggleFullscreen.released.connect(self.toggle_fullscreen)
        #Exports
        self.comboBoxExportBackend.currentIndexChanged.connect(self.export_backend_changed)
        self.checkBoxFolderExport01.stateChanged.connect(self.folder_export_01_changed)
        self.checkBoxFolderExport02.stateChanged.connect(self.folder_export_02_changed)
        self.checkBoxSingleFileMode.stateChanged.connect(self.single_file_mode_changed)
        self.checkBoxSharepointExport01.stateChanged.connect(self.sharepoint_export_01_changed)
        self.checkBoxSharepointExport02.stateChanged.connect(self.sharepoint_export_02_changed)
        self.spinBoxFolderExport01Frequency.valueChanged.connect(self.folder_frequency_01_changed)
        self.spinBoxFolderExport02Frequency.valueChanged.connect(self.folder_frequency_02_changed)
        self.spinBoxSharepointExport01Frequency.valueChanged.connect(self.sharepoint_frequency_01_changed)
        self.spinBoxSharepointExport02Frequency.valueChanged.connect(self.sharepoint_frequency_02_changed)
        self.spinBoxFolderExport01Period.valueChanged.connect(self.folder_period_01_changed)
        self.spinBoxFolderExport02Period.valueChanged.connect(self.folder_period_02_changed)
        self.spinBoxSharepointExport01Period.valueChanged.connect(self.sharepoint_period_01_changed)
        self.spinBoxSharepointExport02Period.valueChanged.connect(self.sharepoint_period_02_changed)
        self.lineEditFolderExport01Path.textChanged.connect(self.folder_path_01_changed)
        self.lineEditFolderExport02Path.textChanged.connect(self.folder_path_02_changed)
        self.lineEditSharepointExport01Path.textChanged.connect(self.sharepoint_path_01_changed)
        self.lineEditSharepointExport02Path.textChanged.connect(self.sharepoint_path_02_changed)
        self.lineEditSharepointExport01SiteID.textChanged.connect(self.sharepoint_site_id_01_changed)
        self.lineEditSharepointExport02SiteID.textChanged.connect(self.sharepoint_site_id_02_changed)
        self.lineEditSharepointExport01ListID.textChanged.connect(self.sharepoint_list_id_01_changed)
        self.lineEditSharepointExport02ListID.textChanged.connect(self.sharepoint_list_id_02_changed)
        self.export_01_timer.timeout.connect(self.export_data_01)
        self.export_02_timer.timeout.connect(self.export_data_02)
        self.pushButtonClearCounDatabase.released.connect(self.clear_count_database)

        #Set Initial
        self.lineEditMachineName.setText(self.machine_name)
        self.frameCountTarget.setVisible(False)
        self.spinBoxInfeedPin.setValue(self.infeed_pin)
        self.spinBoxOutfeedPin.setValue(self.outfeed_pin)
        self.doubleSpinBoxBounceTime.setValue(self.bounce_time)
        #Stacklight
        self.frameStackLight.setVisible(self.is_stack_light_enabled)
        self.checkBoxEnableStackLight.setChecked(self.is_stack_light_enabled)
        self.spinBoxStackLightGreenOutput.setValue(self.stack_pin_green)
        self.spinBoxStackLightYellowOutput.setValue(self.stack_pin_yellow)
        self.spinBoxStackLightRedOutput.setValue(self.stack_pin_red)
        self.comboBoxOperationMode.setCurrentIndex(self.operation_mode)
        #Exports
        self.checkBoxFolderExport01.setChecked(self.is_export_folder_01_enabled)
        self.checkBoxFolderExport02.setChecked(self.is_export_folder_02_enabled)
        self.checkBoxSingleFileMode.setChecked(self.is_export_single_file_enabled)
        self.checkBoxSharepointExport01.setChecked(self.is_export_sharepoint_01_enabled)
        self.checkBoxSharepointExport02.setChecked(self.is_export_sharepoint_02_enabled)
        self.spinBoxFolderExport01Frequency.setValue(self.export_folder_01_frequency)
        self.spinBoxFolderExport02Frequency.setValue(self.export_folder_02_frequency)
        self.spinBoxSharepointExport01Frequency.setValue(self.export_sharepoint_01_frequency)
        self.spinBoxSharepointExport02Frequency.setValue(self.export_sharepoint_02_frequency)
        self.spinBoxFolderExport01Period.setValue(self.export_folder_01_period)
        self.spinBoxFolderExport02Period.setValue(self.export_folder_02_period)
        self.spinBoxSharepointExport01Period.setValue(self.export_sharepoint_01_period)
        self.spinBoxSharepointExport02Period.setValue(self.export_sharepoint_02_period)
        self.lineEditFolderExport01Path.setText(self.export_folder_01_path)
        self.lineEditFolderExport02Path.setText(self.export_folder_02_path)
        self.lineEditSharepointExport01Path.setText(self.export_sharepoint_01_path)
        self.lineEditSharepointExport02Path.setText(self.export_sharepoint_02_path)
        self.lineEditSharepointExport01SiteID.setText(self.export_sharepoint_01_site_id)
        self.lineEditSharepointExport02SiteID.setText(self.export_sharepoint_02_site_id)
        self.lineEditSharepointExport01ListID.setText(self.export_sharepoint_01_list_id)
        self.lineEditSharepointExport02ListID.setText(self.export_sharepoint_02_list_id)
        self.comboBoxExportBackend.setCurrentIndex(self.export_backend)

        self.export_backend_changed(self.export_backend)
        self.operation_mode_changed(self.operation_mode)
        self.update_stack_light()
        self.login_attempt()

    def export_data_01(self):
        self.logger.info('Running export 1...')
        if self.export_backend == ExportBackend.NONE.value:
            self.is_runing_exports_01 = False
            self.is_runing_exports_02 = False
        elif self.export_backend == ExportBackend.FOLDER.value:
            if not self.is_export_setup:
                return
            if self.is_export_folder_01_enabled:
                Path(self.export_folder_01_path).mkdir(parents=True, exist_ok=True)
                result = self.cursor.execute("SELECT * FROM counts WHERE countdatetime >= ?",(datetime.now() - timedelta(minutes=self.export_folder_01_period),))
                if result:
                    filepath: str
                    if self.is_export_single_file_enabled:
                        filepath = Path(self.export_folder_01_path + "/Counts_" + self.machine_name + '.csv').as_posix()
                    else:
                        filepath = Path(self.export_folder_01_path + "/Counts_" + self.machine_name + '_' + datetime.now().strftime('%Y-%m-%d_%H-%M') + '.csv').as_posix()
                    with open(filepath, 'w', newline='') as f:
                        w = writer(f)
                        w.writerow(["ID", "Date Time", "Machine", "Reject", "Product ID"])
                        w.writerows(result)
                    f.close()
                result = self.cursor.execute("SELECT * FROM products")
                if result:
                    filepath: str
                    if self.is_export_single_file_enabled:
                        filepath = Path(self.export_folder_01_path + "/Products_" + self.machine_name + '.csv').as_posix()
                    else:
                        filepath = Path(self.export_folder_01_path + "/Products_" + self.machine_name + '_' + datetime.now().strftime('%Y-%m-%d_%H-%M') + '.csv').as_posix()
                    with open(filepath, 'w', newline='') as f:
                        w = writer(f)
                        w.writerow(["ID", "Title", "Target Count", "Target Pace", "Product Weight"])
                        w.writerows(result)
                    f.close()
            self.is_runing_exports_01 = True
        elif self.export_backend == ExportBackend.SHAREPOINT.value:
            if not self.is_export_setup:
                return
            if self.is_export_sharepoint_01_enabled:
                result = self.cursor.execute("SELECT * FROM counts WHERE countdatetime >= ?",(datetime.now() - timedelta(minutes=self.export_sharepoint_01_period),))
                if result:
                    file_name: str = "Counts_" + self.machine_name + '.csv'
                    file_path: str = "/tmp/"
                    with open(file_path + file_name, 'w', newline='') as f:
                        w = writer(f)
                        w.writerow(["ID", "Date Time", "Machine", "Reject", "Product ID"])
                        w.writerows(result)
                    f.close()
                    try:
                        if not self.sharepoint_export:
                            raise
                        self.sharepoint_export.upload_file(file_path, file_name, self.export_sharepoint_01_site_id, self.export_sharepoint_01_list_id, self.export_sharepoint_01_path)
                    except:
                        self.logger.exception('Unable to upload count file')
                result = self.cursor.execute("SELECT * FROM products")
                if result:
                    file_name: str = "Products_" + self.machine_name + '.csv'
                    file_path: str = "/tmp/"
                    with open(file_path + file_name, 'w', newline='') as f:
                        w = writer(f)
                        w.writerow(["ID", "Title", "Target Count", "Target Pace", "Product Weight"])
                        w.writerows(result)
                    f.close()
                    try:
                        if not self.sharepoint_export:
                            raise
                        self.sharepoint_export.upload_file(file_path, file_name, self.export_sharepoint_01_site_id, self.export_sharepoint_01_list_id, self.export_sharepoint_01_path)
                    except:
                        self.logger.exception('Unable to upload product file')
            self.is_runing_exports_01 = True

    def export_data_02(self):
        self.logger.info('Running export 2...')
        if self.export_backend == ExportBackend.NONE.value:
            self.is_runing_exports_01 = False
            self.is_runing_exports_02 = False
        elif self.export_backend == ExportBackend.FOLDER.value:
            if not self.is_export_setup:
                return
            if self.is_export_folder_02_enabled:
                Path(self.export_folder_02_path).mkdir(parents=True, exist_ok=True)
                result = self.cursor.execute("SELECT * FROM counts WHERE countdatetime >= ?",(datetime.now() - timedelta(minutes=self.export_folder_02_period),))
                if result:
                    filepath: str
                    if self.is_export_single_file_enabled:
                        filepath = Path(self.export_folder_02_path + "/Counts_" + self.machine_name + '.csv').as_posix()
                    else:
                        filepath = Path(self.export_folder_02_path + "/Counts_" + self.machine_name + '_' + datetime.now().strftime('%Y-%m-%d_%H-%M') + '.csv').as_posix()
                    with open(filepath, 'w', newline='') as f:
                        w = writer(f)
                        w.writerow(["ID", "Date Time", "Machine", "Reject", "Product ID"])
                        w.writerows(result)
                    f.close()
                result = self.cursor.execute("SELECT * FROM products")
                if result:
                    filepath: str
                    if self.is_export_single_file_enabled:
                        filepath = Path(self.export_folder_02_path + "/Products_" + self.machine_name + '.csv').as_posix()
                    else:
                        filepath = Path(self.export_folder_02_path + "/Products_" + self.machine_name + '_' + datetime.now().strftime('%Y-%m-%d_%H-%M') + '.csv').as_posix()
                    with open(filepath, 'w', newline='') as f:
                        w = writer(f)
                        w.writerow(["ID", "Title", "Target Count", "Target Pace", "Product Weight"])
                        w.writerows(result)
                    f.close()
            self.is_runing_exports_02 = True
        elif self.export_backend == ExportBackend.SHAREPOINT.value:
            if not self.is_export_setup:
                return
            if self.is_export_sharepoint_01_enabled:
                result = self.cursor.execute("SELECT * FROM counts WHERE countdatetime >= ?",(datetime.now() - timedelta(minutes=self.export_sharepoint_02_period),))
                if result:
                    file_name: str = "Counts_" + self.machine_name + '.csv'
                    file_path: str = "/tmp/"
                    with open(file_path + file_name, 'w', newline='') as f:
                        w = writer(f)
                        w.writerow(["ID", "Date Time", "Machine", "Reject", "Product ID"])
                        w.writerows(result)
                    f.close()
                    try:
                        self.sharepoint_export.upload_file(file_path, file_name, self.export_sharepoint_02_site_id, self.export_sharepoint_02_list_id, self.export_sharepoint_02_path)
                    except:
                        self.logger.exception('Unable to upload count file')
                result = self.cursor.execute("SELECT * FROM products")
                if result:
                    file_name: str = "Products_" + self.machine_name + '.csv'
                    file_path: str = "/tmp/"
                    with open(file_path + file_name, 'w', newline='') as f:
                        w = writer(f)
                        w.writerow(["ID", "Title", "Target Count", "Target Pace", "Product Weight"])
                        w.writerows(result)
                    f.close()
                    try:
                        self.sharepoint_export.upload_file(file_path, file_name, self.export_sharepoint_02_site_id, self.export_sharepoint_02_list_id, self.export_sharepoint_02_path)
                    except:
                        self.logger.exception('Unable to upload product file')
            self.is_runing_exports_02 = True

    def sensor_activated(self, sensor: DigitalInputDevice):
        if sensor is self.infeed_sensor:
            self.labelInfeedDebug.setText("1")
            self.labelIOInfeedInput.setPixmap(QPixmap('GreenCircle.png'))
            if not self.loaded_product:
                return
            if not self.operation_mode == OperationMode.REJECT.value:
                self.count_good(time=datetime.now())
                self.update_counts()
                self.last_count_1 = None
                return
            else:
                if self.last_count_1:
                    self.count_reject(time=datetime.now(), count=self.last_count_1)
                    self.update_counts()
                    self.last_count_1 = Count(self.loaded_product.product_id, datetime.now())
                else:
                    self.last_count_1 = Count(self.loaded_product.product_id, datetime.now())
            
        elif sensor is self.outfeed_sensor:
            self.labelOutfeedDebug.setText("1")
            self.labelIOOutfeedInput.setPixmap(QPixmap('GreenCircle.png'))
            if not self.loaded_product:
                return
            if not self.operation_mode == OperationMode.REJECT.value:
                return
            if not self.last_count_1:
                return
            self.count_good(time=datetime.now(), count=self.last_count_1)
            self.update_counts()
            self.last_count_1 = None

    def sensor_deactivated(self, sensor: DigitalInputDevice):
        if sensor is self.infeed_sensor:
            self.labelInfeedDebug.setText("0")
            self.labelIOInfeedInput.setPixmap(QPixmap('RedCircle.png'))
            
        elif sensor is self.outfeed_sensor:
            self.labelOutfeedDebug.setText("0")
            self.labelIOOutfeedInput.setPixmap(QPixmap('RedCircle.png'))

    def count_good(self, time: datetime, count: Count = None):
        try:
            self.logger.info('Counting good product...')
            if not count:
                count = Count(self.loaded_product.product_id, time)
            self.cursor.execute('INSERT INTO counts (count_id, countdatetime, machine, reject, product_id) VALUES (NULL,?,?,?,?);', (count.date,self.machine_name,0,count.product_id))
            self.connection.commit()
            self.current_good += 1
            self.add_count_to_ppm_stack(count)
        except:
            self.logger.exception('Unable to count good product')

    def count_reject(self, time: datetime, count: Count = None):
        try:
            self.logger.info('Counting reject product...')
            if count:
                self.cursor.execute('INSERT INTO counts (count_id, countdatetime, machine, reject, product_id) VALUES (NULL,?,?,?,?);', (count.date,self.machine_name,1,count.product_id))
            else:
                self.cursor.execute('INSERT INTO counts (count_id, countdatetime, machine, reject, product_id) VALUES (NULL,?,?,?,?);', (time,self.machine_name,1,self.loaded_product.product_id))
            self.connection.commit()
            self.current_reject += 1
        except:
            self.logger.exception('Unable to count reject product')

    def get_all_products(self):
        self.all_products.clear()
        self.cursor.execute('SELECT * FROM products')
        products = self.cursor.fetchall()
        for product in products:
            self.all_products.append(Product(product_id=product[0],name=product[1],count=product[2],pace=product[3],weight=product[4]))
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
            self.productTargetCount.setText(str(self.selected_product.target_count))
            self.lineEditPace.setText(str(self.selected_product.target_pace))
            self.productWeight.setText(str(self.selected_product.weight))
        else:
            self.productName.setText("")
            self.productTargetCount.setText("")
            self.lineEditPace.setText("")
            self.productWeight.setText("")

    def update_product(self):
        if self.selected_product:
            self.selected_product.name = self.productName.text()
            self.selected_product.target_count = int(self.productTargetCount.text()) or 0
            self.selected_product.target_pace = int(self.lineEditPace.text()) or 0
            self.selected_product.weight = float(self.productWeight.text()) or 0
            self.cursor.execute('UPDATE products SET title = ?, target_count = ?, target_pace = ?, product_weight = ? WHERE product_id = ?', (self.selected_product.name, self.selected_product.target_count, self.selected_product.target_pace, self.selected_product.weight, self.selected_product.product_id))
            self.connection.commit()
            self.update_product_list()

    def create_product(self):
        if not self.productName.text():
            return
        if not self.productTargetCount.text():
            return
        if not self.lineEditPace.text():
            return
        if not self.productWeight.text():
            return
        self.cursor.execute('INSERT INTO products(title, target_count, target_pace, product_weight) VALUES(?, ?, ?, ?)', (self.productName.text(), int(self.productTargetCount.text()), int(self.lineEditPace.text()), float(self.productWeight.text())))
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
            if self.loaded_product.target_count > 0:
                self.labelCountTarget.setText(str(self.loaded_product.target_count))
            else:
                self.labelCountTarget.setText("*N/A*") 
            if self.loaded_product.target_pace > 0:
                self.labelTargetPPM.setText(str(self.loaded_product.target_pace))
            else:
               self.labelTargetPPM.setText("*N/A*") 

    def reset_counts(self):
        if self.last_count_1:
            self.count_reject(time=datetime.now(), count=self.last_count_1)
            self.update_counts()
            self.last_count_1 = None
        self.current_good = 0
        self.current_reject = 0
        self.current_ppm_offset = 0 #TODO: Not used?
        self.current_ppm_1 = 0
        self.current_ppm_2 = 0
        self.reset_ppm_list()
        pallette = self.tab.palette()
        pallette.setColor(self.tab.backgroundRole(), QColor(239,239,239))
        self.tab.setPalette(pallette)
        self.update_counts()

    def update_counts(self, sensor=None):
        self.labelGood.setText(str(self.current_good))
        self.labelPaceCount.setText(str(self.current_good))
        self.labelRejects.setText(str(self.current_reject))
        self.labelCurrentPPM.setText(str(round(self.current_ppm_1)))
        self.labelPPMDelta.setText(str(round(self.current_ppm_delta_1)))
        if self.current_ppm_delta_1 >= 0:
            self.labelPPMDirection.setText('+')
            pallette = self.framePPMDelta.palette()
            pallette.setColor(self.framePPMDelta.backgroundRole(), QColor(100,250,100))
            self.framePPMDelta.setPalette(pallette)
        else:
            self.labelPPMDirection.setText('')
            pallette = self.framePPMDelta.palette()
            pallette.setColor(self.framePPMDelta.backgroundRole(), QColor(250,100,100))
            self.framePPMDelta.setPalette(pallette)
        if self.current_good + self.current_reject > 0:
            self.quality_percent = float(self.current_good / (self.current_good + self.current_reject)) * 100
        else:
            self.quality_percent = 0
        self.labelQualityPercent.setText(str(round(self.quality_percent, 2)))
        if self.loaded_product and self.loaded_product.target_count > 0 and self.operation_mode == OperationMode.TARGET.value:
            if self.current_good == self.loaded_product.target_count:
                pallette = self.tab.palette()
                pallette.setColor(self.tab.backgroundRole(), QColor(100,250,100))
                self.tab.setPalette(pallette)
                self.current_operation_state = OperationState.NORMAL.value
            elif self.current_good > self.loaded_product.target_count:
                pallette = self.tab.palette()
                pallette.setColor(self.tab.backgroundRole(), QColor(250,100,100))
                self.tab.setPalette(pallette)
                self.current_operation_state = OperationState.FAULT.value
            else:
                self.current_operation_state = OperationState.WARNING.value
        if not self.loaded_product:
            self.current_operation_state = OperationState.FAULT.value
        else:
            if self.operation_mode == OperationMode.PACE.value:
                if self.current_ppm_delta_1 >= 0:
                    self.current_operation_state = OperationState.NORMAL.value
                else:
                    self.current_operation_state = OperationState.WARNING.value
            if self.operation_mode == OperationMode.REJECT.value:
                if self.quality_percent >= 70:
                    self.current_operation_state = OperationState.NORMAL.value
                else:
                    self.current_operation_state = OperationState.WARNING.value

        self.update_stack_light()

    def machine_name_changed(self, name: str):
        if name != self.machine_name:
            self.machine_name = name
            self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "machine_name"', (str(self.machine_name),))
            self.connection.commit()
        
    def infeed_pin_changed(self, value):
        if value != self.infeed_pin:
            self.infeed_pin = value
            self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "infeed_pin"', (str(self.infeed_pin),))
            self.connection.commit()

    def outfeed_pin_changed(self, value):
        if value != self.outfeed_pin:
            self.outfeed_pin = value
            self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "outfeed_pin"', (str(self.outfeed_pin),))
            self.connection.commit()
    
    def bounce_time_changed(self, value):
        if value != self.bounce_time:
            self.bounce_time = value
            self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "bounce_time"', (str(self.bounce_time),))
            self.connection.commit()

    def export_backend_changed(self, index: int):
        if self.export_backend != index:
            self.export_backend = index
            self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "export_backend"', (str(self.export_backend),))
            self.connection.commit()
        match index:
            case ExportBackend.NONE.value:
                self.frameFolder.setVisible(False)
                self.frameSharepoint.setVisible(False)
                if self.export_01_timer.isActive():
                    self.export_01_timer.stop()
                if self.export_02_timer.isActive():
                    self.export_02_timer.stop()
            case ExportBackend.FOLDER.value:
                self.frameFolder.setVisible(True)
                self.frameFolderExport01.setVisible(self.is_export_folder_01_enabled)
                self.frameFolderExport02.setVisible(self.is_export_folder_02_enabled)
                self.frameSharepoint.setVisible(False)
                if self.is_export_folder_01_enabled:
                    self.export_01_timer.start(1000 * 60 * self.export_folder_01_frequency)
                else:
                    self.export_01_timer.stop()
                if self.is_export_folder_02_enabled:
                    self.export_02_timer.start(1000 * 60 * self.export_folder_02_frequency)
                else:
                    self.export_02_timer.stop()
            case ExportBackend.SHAREPOINT.value:
                self.frameFolder.setVisible(False)
                self.frameSharepointExport01.setVisible(self.is_export_sharepoint_01_enabled)
                self.frameSharepointExport02.setVisible(self.is_export_sharepoint_02_enabled)
                self.frameSharepoint.setVisible(True)
                if self.is_export_sharepoint_01_enabled:
                    self.export_01_timer.start(1000 * 60 * self.export_sharepoint_01_frequency)
                else:
                    self.export_01_timer.stop()
                if self.is_export_sharepoint_02_enabled:
                    self.export_02_timer.start(1000 * 60 * self.export_sharepoint_02_frequency)
                else:
                    self.export_02_timer.stop()
        self.setup_export()

    def folder_export_01_changed(self, status: int):
        self.is_export_folder_01_enabled = bool(status == 2)
        self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "is_export_folder_01_enabled"', (str(self.is_export_folder_01_enabled),))
        self.connection.commit()
        #self.export_backend_changed(self.export_backend)

    def folder_export_02_changed(self, status: int):
        self.is_export_folder_02_enabled = bool(status == 2)
        self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "is_export_folder_02_enabled"', (str(self.is_export_folder_02_enabled),))
        self.connection.commit()
        #self.export_backend_changed(self.export_backend)

    def single_file_mode_changed(self, status: int):
        self.is_export_single_file_enabled = bool(status == 2)
        self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "is_export_single_file_enabled"', (str(self.is_export_single_file_enabled),))
        self.connection.commit()
        #self.export_backend_changed(self.export_backend)

    def sharepoint_export_01_changed(self, status: int):
        self.is_export_sharepoint_01_enabled = bool(status == 2)
        self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "is_export_sharepoint_01_enabled"', (str(self.is_export_sharepoint_01_enabled),))
        self.connection.commit()
        #self.export_backend_changed(self.export_backend)

    def sharepoint_export_02_changed(self, status: int):
        self.is_export_sharepoint_02_enabled = bool(status == 2)
        self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "is_export_sharepoint_02_enabled"', (str(self.is_export_sharepoint_02_enabled),))
        self.connection.commit()
        #self.export_backend_changed(self.export_backend)

    def folder_frequency_01_changed(self, value):
        self.export_folder_01_frequency = value
        self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "export_folder_01_frequency"', (str(value),))
        self.connection.commit()

    def folder_frequency_02_changed(self, value):
        self.export_folder_02_frequency = value
        self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "export_folder_02_frequency"', (str(value),))
        self.connection.commit()

    def sharepoint_frequency_01_changed(self, value):
        self.export_sharepoint_01_frequency = value
        self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "export_sharepoint_01_frequency"', (str(value),))
        self.connection.commit()

    def sharepoint_frequency_02_changed(self, value):
        self.export_sharepoint_02_frequency = value
        self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "export_sharepoint_02_frequency"', (str(value),))
        self.connection.commit()

    def folder_period_01_changed(self, value):
        self.export_folder_01_period = value
        self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "export_folder_01_period"', (str(value),))
        self.connection.commit()

    def folder_period_02_changed(self, value):
        self.export_folder_02_period = value
        self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "export_folder_02_period"', (str(value),))
        self.connection.commit()

    def sharepoint_period_01_changed(self, value):
        self.export_sharepoint_01_period = value
        self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "export_sharepoint_01_period"', (str(value),))
        self.connection.commit()

    def sharepoint_period_02_changed(self, value):
        self.export_sharepoint_02_period = value
        self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "export_sharepoint_02_period"', (str(value),))
        self.connection.commit()

    def folder_path_01_changed(self, value):
        self.export_folder_01_path = value
        self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "export_folder_01_path"', (str(value),))
        self.connection.commit()

    def folder_path_02_changed(self, value):
        self.export_folder_02_path = value
        self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "export_folder_02_path"', (str(value),))
        self.connection.commit()

    def sharepoint_path_01_changed(self, value):
        self.export_sharepoint_01_path = value
        self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "export_sharepoint_01_path"', (str(value),))
        self.connection.commit()

    def sharepoint_path_02_changed(self, value):
        self.export_sharepoint_02_path = value
        self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "export_sharepoint_02_path"', (str(value),))
        self.connection.commit()

    def sharepoint_site_id_01_changed(self, value):
        self.export_sharepoint_01_site_id = value
        self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "export_sharepoint_01_site_id"', (str(value),))
        self.connection.commit()

    def sharepoint_site_id_02_changed(self, value):
        self.export_sharepoint_02_site_id = value
        self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "export_sharepoint_02_site_id"', (str(value),))
        self.connection.commit()
    
    def sharepoint_list_id_01_changed(self, value):
        self.export_sharepoint_01_list_id = value
        self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "export_sharepoint_01_list_id"', (str(value),))
        self.connection.commit()

    def sharepoint_list_id_02_changed(self, value):
        self.export_sharepoint_02_list_id = value
        self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "export_sharepoint_02_list_id"', (str(value),))
        self.connection.commit()

    def login_attempt(self):
        if self.lineEditLogin.text() == self.tech_password:
            self.tabSettings.setEnabled(True)
            self.buttonExit.setEnabled(True)
            self.buttonDeleteProduct.setEnabled(True)
            self.frameProductControl.setEnabled(True)
            self.buttonLogin.setText("Logout")
        elif self.lineEditLogin.text() == self.ops_password:
            self.frameProductControl.setEnabled(True)
            self.buttonDeleteProduct.setEnabled(True)
            self.buttonLogin.setText("Logout")
        else:
            self.tabSettings.setEnabled(False)
            self.buttonExit.setEnabled(False)
            self.buttonDeleteProduct.setEnabled(False)
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

    def operation_mode_changed(self, index: int):
        self.operation_mode = index
        self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "operation_mode"', (str(self.operation_mode),))
        self.connection.commit()
        match self.operation_mode:
            case OperationMode.COUNT.value:
                self.frameCountTarget.setVisible(False)
                self.framePPM.setVisible(False)
                self.frameRejects.setVisible(False)
                self.labelOutfeedDebug.setEnabled(False)
                self.labelOutfeedDebug_2.setEnabled(False)
                self.frameRejects.setVisible(False)
                self.frameQualityPercent.setVisible(False)
                self.frameCountTarget.setVisible(False)
                self.labelGoodText.setVisible(False)
                self.frameCount.setVisible(True)
                #self.frameDouble.setVisible(False)
            case OperationMode.REJECT.value:
                self.frameCountTarget.setVisible(False)
                self.framePPM.setVisible(False)
                self.frameRejects.setVisible(True)
                self.labelOutfeedDebug.setEnabled(True)
                self.labelOutfeedDebug_2.setEnabled(True)
                self.frameRejects.setVisible(True)
                self.frameQualityPercent.setVisible(True)
                self.frameCountTarget.setVisible(False)
                self.labelGoodText.setVisible(True)
                self.frameCount.setVisible(True)
                #self.frameDouble.setVisible(False)
            case OperationMode.TARGET.value:
                self.frameCountTarget.setVisible(True)
                self.framePPM.setVisible(False)
                self.frameRejects.setVisible(False)
                self.labelOutfeedDebug.setEnabled(False)
                self.labelOutfeedDebug_2.setEnabled(False)
                self.frameRejects.setVisible(False)
                self.frameQualityPercent.setVisible(False)
                self.frameCountTarget.setVisible(True)
                self.labelGoodText.setVisible(False)
                self.frameCount.setVisible(True)
                #self.frameDouble.setVisible(False)
            case OperationMode.PACE.value:
                self.frameCountTarget.setVisible(False)
                self.framePPM.setVisible(True)
                self.frameRejects.setVisible(False)
                self.labelOutfeedDebug.setEnabled(False)
                self.labelOutfeedDebug_2.setEnabled(False)
                self.frameRejects.setVisible(False)
                self.frameQualityPercent.setVisible(False)
                self.frameCountTarget.setVisible(False)
                self.labelGoodText.setVisible(False)
                self.frameCount.setVisible(False)
                #self.frameDouble.setVisible(False)
            case OperationMode.DOUBLE.value:
                self.frameCountTarget.setVisible(False)
                self.framePPM.setVisible(False)
                self.frameRejects.setVisible(False)
                self.labelOutfeedDebug.setEnabled(False)
                self.labelOutfeedDebug_2.setEnabled(False)
                self.frameRejects.setVisible(False)
                self.frameQualityPercent.setVisible(False)
                self.frameCountTarget.setVisible(False)
                self.labelGoodText.setVisible(False)
                self.frameCount.setVisible(False)
                #self.frameDouble.setVisible(True) #TODO: Implement in UI
    
    def add_count_to_ppm_stack_1(self, count: Count):
        self.count_list_1.append(count)
        if len(self.count_list_1) > 10:
            self.count_list_1.pop(0)
        self.calculate_ppm_1()

    def add_count_to_ppm_stack_2(self, count: Count):
        self.count_list_2.append(count)
        if len(self.count_list_2) > 10:
            self.count_list_2.pop(0)
        self.calculate_ppm_2()

    def reset_ppm_list(self):
        self.count_list_1.clear()
        self.current_ppm_1 = 0
        self.current_ppm_delta_1 = 0
        self.count_list_2.clear()
        self.current_ppm_2 = 0
        self.current_ppm_delta_2 = 0

    def calculate_ppm_1(self):
        if len(self.count_list_1) <= 1:
            return
        start: datetime = self.count_list_1[0].date
        stop: datetime = self.count_list_1[-1].date
        difference = (stop - start).total_seconds()
        minutes = difference / 60
        self.current_ppm_1 = len(self.count_list_1) / minutes
        self.current_ppm_delta_1 = self.current_ppm_1 - self.loaded_product.target_pace

    def calculate_ppm_2(self):
        if len(self.count_list_2) <= 1:
            return
        start: datetime = self.count_list_2[0].date
        stop: datetime = self.count_list_2[-1].date
        difference = (stop - start).total_seconds()
        minutes = difference / 60
        self.current_ppm_2 = len(self.count_list_2) / minutes
        self.current_ppm_delta_2 = self.current_ppm_2 - self.loaded_product.target_pace

    def clear_count_database(self):
        self.cursor.execute('DELETE FROM counts')
        self.connection.commit()

    def enable_stack_light_changed(self, status: int):
        self.is_stack_light_enabled = bool(status == 2)
        print(self.is_stack_light_enabled)
        self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "is_stack_light_enabled"', (str(self.is_stack_light_enabled),))
        self.connection.commit()
        self.frameStackLight.setVisible(self.is_stack_light_enabled)

    def stack_light_pin_green_changed(self, value):
        self.stack_pin_green = value
        self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "stack_pin_green"', (str(value),))
        self.connection.commit()

    def stack_light_pin_yellow_changed(self, value):
        self.stack_pin_yellow = value
        self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "stack_pin_yellow"', (str(value),))
        self.connection.commit()

    def stack_light_pin_red_changed(self, value):
        self.stack_pin_red = value
        self.cursor.execute('UPDATE settings SET value = ? WHERE setting_id = "stack_pin_red"', (str(value),))
        self.connection.commit()

    def update_stack_light(self):
        if not self.is_stack_light_enabled:
            self.stack_output_green.off()
            self.stack_output_yellow.off()
            self.stack_output_red.off()
            self.labelGreenOutput.setText("0")
            self.labelYellowOutput.setText("0")
            self.labelRedOutput.setText("0")
            self.labelIOStackRed.setPixmap(QPixmap('RedCircle.png'))
            self.labelIOStackYellow.setPixmap(QPixmap('RedCircle.png'))
            self.labelIOStackGreen.setPixmap(QPixmap('RedCircle.png'))
            return
        match self.current_operation_state:
            case OperationState.NORMAL.value:
                self.stack_output_green.on()
                self.stack_output_yellow.off()
                self.stack_output_red.off()
                self.labelGreenOutput.setText("1")
                self.labelYellowOutput.setText("0")
                self.labelRedOutput.setText("0")
                self.labelIOStackRed.setPixmap(QPixmap('RedCircle.png'))
                self.labelIOStackYellow.setPixmap(QPixmap('RedCircle.png'))
                self.labelIOStackGreen.setPixmap(QPixmap('GreenCircle.png'))
            case OperationState.WARNING.value:
                self.stack_output_green.off()
                self.stack_output_yellow.on()
                self.stack_output_red.off()
                self.labelGreenOutput.setText("0")
                self.labelYellowOutput.setText("1")
                self.labelRedOutput.setText("0")
                self.labelIOStackRed.setPixmap(QPixmap('RedCircle.png'))
                self.labelIOStackYellow.setPixmap(QPixmap('GreenCircle.png'))
                self.labelIOStackGreen.setPixmap(QPixmap('RedCircle.png'))
            case OperationState.FAULT.value:
                self.stack_output_green.off()
                self.stack_output_yellow.off()
                self.stack_output_red.on()
                self.labelGreenOutput.setText("0")
                self.labelYellowOutput.setText("0")
                self.labelRedOutput.setText("1")
                self.labelIOStackRed.setPixmap(QPixmap('GreenCircle.png'))
                self.labelIOStackYellow.setPixmap(QPixmap('RedCircle.png'))
                self.labelIOStackGreen.setPixmap(QPixmap('RedCircle.png'))

    def testing_trigger_good_count(self) -> None:
        if not self.loaded_product:
            return
        self.count_good(datetime.now())
        self.update_counts()

    def testing_trigger_reject_count(self) -> None:
        if not self.loaded_product:
            return
        self.count_reject(datetime.now())
        self.update_counts()

    def quit_app(self):
        if self.export_01_timer.isActive():
            self.export_01_timer.stop()
        if self.export_02_timer.isActive():
            self.export_02_timer.stop()
        self.connection.close()
        QApplication.quit()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ObjectCounter()
    sys.exit(app.exec())

    