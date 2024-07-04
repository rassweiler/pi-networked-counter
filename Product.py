
class Product(object):
    def __init__(self, product_id: int = 0, name: str = "", count: int = 0, weight: float = 0.0):
        self.product_id: int = product_id
        self.name: str = name
        self.weight: float = weight
        self.count: int = count
    
if __name__ == '__main__':
    exit(0)