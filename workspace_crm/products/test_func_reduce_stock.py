from django.test import TestCase
from decimal import Decimal
from products.models import Product
from products.services import reduce_stock

class TestReduceStock(TestCase):
    def test_reduce_stock_normal_case(self):
        product = Product.objects.create(name="Test Product", sku="TEST123", price=Decimal("10.00"), stock=10)
        reduce_stock(product, 5)
        product.refresh_from_db()
        self.assertEqual(product.stock, 5)

    def test_reduce_stock_zero_quantity(self):
        product = Product.objects.create(name="Test Product", sku="TEST123", price=Decimal("10.00"), stock=10)
        reduce_stock(product, 0)
        product.refresh_from_db()
        self.assertEqual(product.stock, 10)

    def test_reduce_stock_exactly_equal_to_stock(self):
        product = Product.objects.create(name="Test Product", sku="TEST123", price=Decimal("10.00"), stock=10)
        reduce_stock(product, 10)
        product.refresh_from_db()
        self.assertEqual(product.stock, 0)

    def test_reduce_stock_quantity_greater_than_stock(self):
        product = Product.objects.create(name="Test Product", sku="TEST123", price=Decimal("10.00"), stock=10)
        with self.assertRaises(ValueError):
            reduce_stock(product, 15)
        product.refresh_from_db()
        self.assertEqual(product.stock, 10)

    def test_reduce_stock_boundary_case(self):
        product = Product.objects.create(name="Test Product", sku="TEST123", price=Decimal("10.00"), stock=1)
        reduce_stock(product, 1)
        product.refresh_from_db()
        self.assertEqual(product.stock, 0)

    def test_reduce_stock_boundary_case_plus_one(self):
        product = Product.objects.create(name="Test Product", sku="TEST123", price=Decimal("10.00"), stock=1)
        with self.assertRaises(ValueError):
            reduce_stock(product, 2)
        product.refresh_from_db()
        self.assertEqual(product.stock, 1)
