from django.test import TestCase
from decimal import Decimal
from sales.models import Sale
from saleitems.models import SaleItem
from products.models import Product
from customers.models import Customer
from sales.services import confirm_sale

class TestConfirmSale(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(name="Alice", email="alice@example.com", phone="123456789")
        self.product1 = Product.objects.create(name="Laptop", sku="SKU001", price=Decimal("1000.00"), stock=5)
        self.product2 = Product.objects.create(name="Mouse", sku="SKU002", price=Decimal("20.00"), stock=3)
        
        self.sale = Sale.objects.create(number="S001", date="2023-10-05", customer=self.customer, total=Decimal("0.00"))
        
        self.item1 = SaleItem.objects.create(description="Laptop purchase", sale=self.sale, product=self.product1, quantity=2, unit_price=Decimal("1000.00"))
        self.item2 = SaleItem.objects.create(description="Mouse purchase", sale=self.sale, product=self.product2, quantity=3, unit_price=Decimal("20.00"))

    def test_confirm_sale_with_available_stock(self):
        # Test case where all items have available stock
        confirm_sale(self.sale)
        
        self.product1.refresh_from_db()
        self.assertEqual(self.product1.stock, 3)  # 5 - 2 = 3
        
        self.product2.refresh_from_db()
        self.assertEqual(self.product2.stock, 0)  # 3 - 3 = 0

    def test_confirm_sale_with_insufficient_stock(self):
        # Test case where one item has insufficient stock
        self.item1.quantity = 6  # More than available stock (5)
        self.item1.save()
        
        with self.assertRaises(ValueError):
            confirm_sale(self.sale)
        
        # Ensure no changes are made to product stocks
        self.product1.refresh_from_db()
        self.assertEqual(self.product1.stock, 5)  # No change
        
        self.product2.refresh_from_db()
        self.assertEqual(self.product2.stock, 3)  # No change

    def test_confirm_sale_with_zero_stock(self):
        # Test case where one item has exactly zero stock (boundary)
        self.product1.stock = 0
        self.product1.save()
        
        self.item1.quantity = 0  # Exactly matches available stock (0)
        self.item1.save()
        
        confirm_sale(self.sale)
        
        self.product1.refresh_from_db()
        self.assertEqual(self.product1.stock, 0)  # 0 - 0 = 0
        
        self.product2.refresh_from_db()
        self.assertEqual(self.product2.stock, 0)  # 3 - 3 = 0

    def test_confirm_sale_with_negative_stock(self):
        # Test case where one item has negative stock (invalid)
        self.item1.quantity = -1  # Negative quantity (should not be allowed)
        self.item1.save()
        
        with self.assertRaises(ValueError):
            confirm_sale(self.sale)
        
        # Ensure no changes are made to product stocks
        self.product1.refresh_from_db()
        self.assertEqual(self.product1.stock, 5)  # No change
        
        self.product2.refresh_from_db()
        self.assertEqual(self.product2.stock, 3)  # No change
