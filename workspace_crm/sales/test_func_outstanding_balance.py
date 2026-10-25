from django.test import TestCase
from decimal import Decimal
import datetime
from sales.services import outstanding_balance
from sales.models import Sale, Payment
from customers.models import Customer
from products.models import Product
from saleitems.models import SaleItem

class TestOutstandingBalance(TestCase):
    def test_no_confirmed_sales(self):
        # No confirmed sales should return 0.00
        result = outstanding_balance()
        self.assertEqual(result, Decimal('0.00'))

    def test_one_confirmed_sale_with_payment(self):
        # Create a customer
        customer = Customer.objects.create(name="John Doe", email="john@example.com", phone="123456789")

        # Create a product
        product = Product.objects.create(name="Laptop", sku="LAP001", price=Decimal("1000.00"), stock=10)

        # Create a sale with confirmed=True
        sale = Sale.objects.create(number="S001", date=datetime.date(2023, 10, 5), customer=customer, total=Decimal("1000.00"), confirmed=True)

        # Create a sale item for the sale
        sale_item = SaleItem.objects.create(description="Laptop purchase", sale=sale, product=product, quantity=1, unit_price=Decimal("1000.00"))

        # Create a payment for the sale
        Payment.objects.create(sale=sale, amount=Decimal("500.00"), paid_on=datetime.date(2023, 10, 6))

        # Calculate outstanding balance
        result = outstanding_balance()
        self.assertEqual(result, Decimal("500.00"))

    def test_one_confirmed_sale_no_payment(self):
        # Create a customer
        customer = Customer.objects.create(name="Jane Doe", email="jane@example.com", phone="987654321")

        # Create a product
        product = Product.objects.create(name="Phone", sku="PHO001", price=Decimal("500.00"), stock=5)

        # Create a sale with confirmed=True
        sale = Sale.objects.create(number="S002", date=datetime.date(2023, 10, 7), customer=customer, total=Decimal("500.00"), confirmed=True)

        # Create a sale item for the sale
        sale_item = SaleItem.objects.create(description="Phone purchase", sale=sale, product=product, quantity=1, unit_price=Decimal("500.00"))

        # Calculate outstanding balance
        result = outstanding_balance()
        self.assertEqual(result, Decimal("500.00"))

    def test_multiple_confirmed_sales(self):
        # Create customer 1
        customer1 = Customer.objects.create(name="Alice", email="alice@example.com", phone="123456789")

        # Create product 1
        product1 = Product.objects.create(name="Tablet", sku="TAB001", price=Decimal("300.00"), stock=2)

        # Create sale 1 with confirmed=True
        sale1 = Sale.objects.create(number="S003", date=datetime.date(2023, 10, 8), customer=customer1, total=Decimal("300.00"), confirmed=True)

        # Create a sale item for sale 1
        sale_item1 = SaleItem.objects.create(description="Tablet purchase", sale=sale1, product=product1, quantity=1, unit_price=Decimal("300.00"))

        # Create customer 2
        customer2 = Customer.objects.create(name="Bob", email="bob@example.com", phone="987654321")

        # Create product 2
        product2 = Product.objects.create(name="Monitor", sku="MON001", price=Decimal("200.00"), stock=3)

        # Create sale 2 with confirmed=True
        sale2 = Sale.objects.create(number="S004", date=datetime.date(2023, 10, 9), customer=customer2, total=Decimal("200.00"), confirmed=True)

        # Create a sale item for sale 2
        sale_item2 = SaleItem.objects.create(description="Monitor purchase", sale=sale2, product=product2, quantity=1, unit_price=Decimal("200.00"))

        # Calculate outstanding balance
        result = outstanding_balance()
        self.assertEqual(result, Decimal("500.00"))
