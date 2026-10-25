from django.test import TestCase
from decimal import Decimal
import datetime
from customers.models import Customer
from sales.models import Sale
from sales.services import top_customers

class TestTopCustomers(TestCase):
    def test_top_customers_with_multiple_customers(self):
        # Create confirmed sales for customer 1
        customer1 = Customer.objects.create(name="Customer 1", email="customer1@example.com")
        sale1 = Sale.objects.create(number="S001", date=datetime.date(2023, 10, 5), customer=customer1, total=Decimal("100.00"), confirmed=True)
        sale2 = Sale.objects.create(number="S002", date=datetime.date(2023, 10, 6), customer=customer1, total=Decimal("200.00"), confirmed=True)

        # Create confirmed sales for customer 2
        customer2 = Customer.objects.create(name="Customer 2", email="customer2@example.com")
        sale3 = Sale.objects.create(number="S003", date=datetime.date(2023, 10, 7), customer=customer2, total=Decimal("150.00"), confirmed=True)

        # Create unconfirmed sales for customer 3 (should not be included)
        customer3 = Customer.objects.create(name="Customer 3", email="customer3@example.com")
        sale4 = Sale.objects.create(number="S004", date=datetime.date(2023, 10, 8), customer=customer3, total=Decimal("50.00"), confirmed=False)

        # Get top customers with limit 2
        result = top_customers(limit=2)

        # Check the results
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0][0], customer1)
        self.assertEqual(result[0][1], Decimal("300.00"))
        self.assertEqual(result[1][0], customer2)
        self.assertEqual(result[1][1], Decimal("150.00"))

    def test_top_customers_with_no_confirmed_sales(self):
        # Create a customer with no confirmed sales
        customer = Customer.objects.create(name="Customer 4", email="customer4@example.com")

        # Get top customers (should return an empty list)
        result = top_customers(limit=1)

        # Check the results
        self.assertEqual(len(result), 0)

    def test_top_customers_with_one_customer(self):
        # Create confirmed sales for customer 5
        customer = Customer.objects.create(name="Customer 5", email="customer5@example.com")
        sale = Sale.objects.create(number="S005", date=datetime.date(2023, 10, 9), customer=customer, total=Decimal("75.00"), confirmed=True)

        # Get top customers with limit 1
        result = top_customers(limit=1)

        # Check the results
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], customer)
        self.assertEqual(result[0][1], Decimal("75.00"))

    def test_top_customers_with_multiple_confirmed_sales(self):
        # Create confirmed sales for customer 6
        customer = Customer.objects.create(name="Customer 6", email="customer6@example.com")
        sale1 = Sale.objects.create(number="S006", date=datetime.date(2023, 10, 10), customer=customer, total=Decimal("50.00"), confirmed=True)
        sale2 = Sale.objects.create(number="S007", date=datetime.date(2023, 10, 11), customer=customer, total=Decimal("50.00"), confirmed=True)

        # Get top customers with limit 1
        result = top_customers(limit=1)

        # Check the results
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], customer)
        self.assertEqual(result[0][1], Decimal("100.00"))
