#!/bin/bash

cd /home/tech/pi-networked-counter

source venv/bin/activate

pyuic6 form.ui -o MainWindow.py