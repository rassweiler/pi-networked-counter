# pi-networked-counter
Network attached counter using Pi5, python, pyqt5, and sqlite

![Assembly](./Docs/Assembly_01.png)
![Assembly Opened](./Docs/Assembly_02.png)

## Setup (Pi 5+)

- clone repository:
```
git clone https://github.com/rassweiler/pi-networked-counter.git && cd pi-networked-counter
```

- Setup python environment:
```
python3 -m venv venv

source venv/bin/activate

pip3 install gpiod pyqt6 sqlite3 gpiozero
```