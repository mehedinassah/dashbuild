from django.test import TestCase
from decimal import Decimal
from products.models import Product

class TestProductInStock(TestCase):
    def test_in_stock_returns_true_when_stock_greater_than_zero(self):
        product = Product.objects.create(name="Test Product", sku="TEST123", price=Decimal("10.00"), stock=5)
        self.assertTrue(product.in_stock())

    def test_in_stock_returns_false_when_stock_is_zero(self):
        product = Product.objects.create(name="Test Product", sku="TEST456", price=Decimal("20.00"), stock=0)
        self.assertFalse(product.in_stock())

    def test_in_stock_returns_false_when_stock_is_negative(self):
        product = Product.objects.create(name="Test Product", sku="TEST789", price=Decimal("30.00"), stock=-2)
        self.assertFalse(product.in_stock())

    def test_in_stock_returns_true_for_positive_stock_boundary(self):
        product = Product.objects.create(name="Test Product", sku="TEST012", price=Decimal("40.00"), stock=1)
        self.assertTrue(product.in_stock())
