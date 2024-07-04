#! /usr/bin/env python3

import os
import sys
import sqlite3
import datetime
from PyQt6.QtCore import Qt
from gpiozero import DistanceSensor
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget
from MainWindow import Ui_MainWindow
from Product import Product

SENSOR_INFEED = DistanceSensor(echo=27, trigger=17)
SENSOR_OUTFEED = DistanceSensor(echo=24, trigger=23)

class ObjectCounter(QMainWindow, Ui_MainWindow):
    def __init__(self, parent = None, enable_rejects: bool = True):
        super().__init__(parent)
        self.setupUi(self)
        self.set_ui()
        self.enable_rejects: bool = enable_rejects
        self.infeed_detected: bool = False
        self.outfeed_detected: bool = False
        self.connection = sqlite3.connect('/home/tech/pi-networked-counter/database.db',detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
        self.cursor = self.connection.cursor()
        self.cursor.execute('PRAGMA foreign_keys = ON')
        self.current_good: int = 0
        self.current_reject: int = 0
        self.all_products: list = []
        self.loaded_product: Product = None
        self.selected_product: Product = None
        #Create for table structure
        self.cursor.execute('CREATE TABLE IF NOT EXISTS settings(setting_id TEXT PRIMARY KEY UNIQUE, title TEXT, target_count INTEGER);')
        self.cursor.execute('CREATE TABLE IF NOT EXISTS products(product_id INTEGER PRIMARY KEY UNIQUE, title TEXT, target_count INTEGER, product_weight REAL);')
        self.cursor.execute('CREATE TABLE IF NOT EXISTS counts(countdatetime INTEGEGER PRIMARY KEY UNIQUE, reject INTEGER NOT NULL, product_id INTEGER NOT NULL, FOREIGN KEY(product_id) REFERENCES products (product_id));')
        self.get_all_products()

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

    def count_good(self):
        self.cursor.execute('INSERT INTO counts VALUES (?,?,?);', (datetime.datetime.now(),0,self.loaded_product.product_id))
        self.connection.commit()

    def count_reject(self):
        self.cursor.execute('INSERT INTO counts VALUES (?,?,?);', (datetime.datetime.now(),1,self.loaded_product.product_id))
        self.connection.commit()

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

    def reset_counts(self):
        self.current_good = 0
        self.current_reject = 0
        self.update_counts()

    def update_counts(self):
        self.labelGood.setText(str(self.current_good))
        self.labelRejects.setText(str(self.current_reject))

    def quit_app(self):
        self.connection.close()
        quit(0)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ObjectCounter()
    sys.exit(app.exec())