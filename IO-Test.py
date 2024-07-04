#! /usr/bin/env python3
import time
from gpiozero import DistanceSensor

SENSOR_INFEED = DistanceSensor(echo=27, trigger=17)
SENSOR_OUTFEED = DistanceSensor(echo=24, trigger=23)

while True:
    print('Infeed distance: ', SENSOR_INFEED.distance * 100)
    print('Outfeed distance: ', SENSOR_OUTFEED.distance * 100)
    time.sleep(1)
