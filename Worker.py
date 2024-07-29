from PyQt6 import QtCore

class WorkerSignals(QtCore.QObject):
    result = QtCore.pyqtSignal(float)

class SensorWorker(QtCore.QRunnable):
    def __init__(self, sensor, signals):
        super(SensorWorker, self).__init__()
        self.sensor = sensor
        self.signals = signals

    def run(self):
        value = self.sensor.distance * 100
        self.signals.result.emit(float(value))
    
if __name__ == '__main__':
    exit(0)