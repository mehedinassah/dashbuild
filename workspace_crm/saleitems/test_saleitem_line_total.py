from django.test import TestCase
from decimal import Decimal
from sales.models import Sale
from customers.models import Customer
from products.models import Product
from saleitems.models import SaleItem

class TestSaleItemLineTotal(TestCase):
    def test_normal_case(self):
        # Create a customer
        customer = Customer.objects.create(name="John Doe", email="john@example.com", phone="123456789")
        
        # Create a product
        product = Product.objects.create(name="Laptop", sku="LAP001", price=Decimal("1000.00"), stock=10)
        
        # Create a sale
        sale = Sale.objects.create(number="S001", date="2023-10-05", customer=customer, total=Decimal("0.00"))
        
        # Create a sale item with unit_price and quantity
        sale_item = SaleItem.objects.create(
            description="Laptop purchase",
            sale=sale,
            product=product,
            quantity=2,
            unit_price=Decimal("950.00")
        )
        
        # Test line_total method
        self.assertEqual(sale_item.line_total(), Decimal("1900.00"))

    def test_zero_quantity(self):
        # Create a customer
        customer = Customer.objects.create(name="Jane Doe", email="jane@example.com", phone="987654321")
        
        # Create a product
        product = Product.objects.create(name="Tablet", sku="TAB001", price=Decimal("500.00"), stock=5)
        
        # Create a sale
        sale = Sale.objects.create(number="S002", date="2023-10-06", customer=customer, total=Decimal("0.00"))
        
        # Create a sale item with quantity 0
        sale_item = SaleItem.objects.create(
            description="Tablet purchase",
            sale=sale,
            product=product,
            quantity=0,
            unit_price=Decimal("450.00")
        )
        
        # Test line_total method
        self.assertEqual(sale_item.line_total(), Decimal("0.00"))

    def test_boundary_case(self):
        # Create a customer
        customer = Customer.objects.create(name="Alice", email="alice@example.com", phone="123456789")
        
        # Create a product
        product = Product.objects.create(name="Phone", sku="PHO001", price=Decimal("300.00"), stock=2)
        
        # Create a sale
        sale = Sale.objects.create(number="S003", date="2023-10-07", customer=customer, total=Decimal("0.00"))
        
        # Create a sale item with quantity 1 and unit_price 250.00
        sale_item_1 = SaleItem.objects.create(
            description="Phone purchase",
            sale=sale,
            product=product,
            quantity=1,
            unit_price=Decimal("250.00")
        )
        
        # Test line_total method for quantity 1
        self.assertEqual(sale_item_1.line_total(), Decimal("250.00"))
        
        # Create a sale item with quantity 2 and unit_price 250.00
        sale_item_2 = SaleItem.objects.create(
            description="Phone purchase",
            sale=sale,
            product=product,
            quantity=2,
            unit_price=Decimal("250.00")
        )
        
        # Test line_total method for quantity 2
        self.assertEqual(sale_item_2.line_total(), Decimal("500.00"))
