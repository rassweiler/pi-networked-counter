from datetime import datetime

class Count(object):
    def __init__(self, product_id: int, date_time: datetime = datetime.now()):
        self.date: datetime = date_time
        self.product_id: float = product_id

if __name__ == '__main__':
    exit(0)

