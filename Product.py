#! /usr/bin/env python3

from dataclasses import dataclass

@dataclass
class Product(object):
    product_id: int = 0
    name: str = ""
    target_count: int = 0
    target_pace: int = 0
    weight: float = 0.0
    
if __name__ == '__main__':
    exit(0)