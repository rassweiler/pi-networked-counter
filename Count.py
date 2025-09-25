#! /usr/bin/env python3

from dataclasses import dataclass
from datetime import datetime

@dataclass
class Count(object):
    product_id: int
    date: datetime = datetime.now()
    sensor: int = 0

if __name__ == '__main__':
    exit(0)

