from django.test import TestCase
from decimal import Decimal
from products.models import Product
from products.services import low_stock_products

class TestLowStockProducts(TestCase):
    def test_normal_case(self):
        # Create products with various stock levels
        product1 = Product.objects.create(name="Product 1", sku="SKU001", price=Decimal("10.00"), stock=3)
        product2 = Product.objects.create(name="Product 2", sku="SKU002", price=Decimal("20.00"), stock=4)
        product3 = Product.objects.create(name="Product 3", sku="SKU003", price=Decimal("30.00"), stock=5)
        product4 = Product.objects.create(name="Product 4", sku="SKU004", price=Decimal("40.00"), stock=6)

        # Call the function with threshold 5
        result = low_stock_products(5)

        # Check that only products with stock < 5 are included
        self.assertEqual(result, [product1, product2])

    def test_zero_stock(self):
        # Create a product with zero stock
        product = Product.objects.create(name="Zero Stock", sku="SKU005", price=Decimal("50.00"), stock=0)

        # Call the function with threshold 1
        result = low_stock_products(1)

        # Check that the product is included
        self.assertEqual(result, [product])

    def test_threshold_5_default(self):
        # Create products with various stock levels
        product1 = Product.objects.create(name="Product 1", sku="SKU006", price=Decimal("10.00"), stock=4)
        product2 = Product.objects.create(name="Product 2", sku="SKU007", price=Decimal("20.00"), stock=5)
        product3 = Product.objects.create(name="Product 3", sku="SKU008", price=Decimal("30.00"), stock=6)

        # Call the function without specifying threshold (default is 5)
        result = low_stock_products()

        # Check that only products with stock < 5 are included
        self.assertEqual(result, [product1])

    def test_boundary_case(self):
        # Create products at and around the threshold of 5
        product1 = Product.objects.create(name="Below Threshold", sku="SKU009", price=Decimal("10.00"), stock=4)
        product2 = Product.objects.create(name="At Threshold", sku="SKU010", price=Decimal("20.00"), stock=5)
        product3 = Product.objects.create(name="Above Threshold", sku="SKU011", price=Decimal("30.00"), stock=6)

        # Call the function with threshold 5
        result = low_stock_products(5)

        # Check that only products below the threshold are included
        self.assertEqual(result, [product1])
