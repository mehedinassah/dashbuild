from django.test import TestCase
from decimal import Decimal
import datetime
from sales.services import total_revenue
from sales.models import Sale
from customers.models import Customer

class TestTotalRevenue(TestCase):
    def test_no_confirmed_sales(self):
        # No confirmed sales should return 0.00
        result = total_revenue()
        self.assertEqual(result, Decimal("0.00"))

    def test_one_confirmed_sale(self):
        # Create a customer
        customer = Customer.objects.create(name="Alice", email="alice@example.com", phone="1234567890")
        
        # Create a confirmed sale with total 100.00
        sale = Sale.objects.create(number="S001", date=datetime.date(2023, 10, 5), customer=customer, total=Decimal("100.00"), confirmed=True)
        
        # Check the result
        result = total_revenue()
        self.assertEqual(result, Decimal("100.00"))

    def test_multiple_confirmed_sales(self):
        # Create a customer
        customer = Customer.objects.create(name="Bob", email="bob@example.com", phone="0987654321")
        
        # Create two confirmed sales with totals 100.00 and 200.00
        sale1 = Sale.objects.create(number="S002", date=datetime.date(2023, 10, 5), customer=customer, total=Decimal("100.00"), confirmed=True)
        sale2 = Sale.objects.create(number="S003", date=datetime.date(2023, 10, 6), customer=customer, total=Decimal("200.00"), confirmed=True)
        
        # Check the result
        result = total_revenue()
        self.assertEqual(result, Decimal("300.00"))

    def test_unconfirmed_sales_not_counted(self):
        # Create a customer
        customer = Customer.objects.create(name="Charlie", email="charlie@example.com", phone="1234567890")
        
        # Create an unconfirmed sale with total 150.00
        sale = Sale.objects.create(number="S004", date=datetime.date(2023, 10, 7), customer=customer, total=Decimal("150.00"), confirmed=False)
        
        # Check the result
        result = total_revenue()
        self.assertEqual(result, Decimal("0.00"))
