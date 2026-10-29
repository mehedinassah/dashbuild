from django.test import TestCase
from decimal import Decimal
from customers.models import Customer
from sales.models import Sale
from sales.services import customer_outstanding
import datetime

class TestCustomerOutstanding(TestCase):
    def test_customer_with_no_confirmed_sales_returns_zero(self):
        customer = Customer.objects.create(name="Test Customer")
        result = customer_outstanding(customer)
        self.assertEqual(result, Decimal("0.00"))

    def test_customer_with_one_confirmed_sale_returns_balance_due(self):
        customer = Customer.objects.create(name="Test Customer")
        sale = Sale.objects.create(
            number="S123",
            date=datetime.date(2023, 10, 5),
            customer=customer,
            total=Decimal("100.00"),
            confirmed=True
        )
        # Assuming balance_due is calculated correctly based on payments and total
        # For this test, we assume no payments have been made yet
        result = customer_outstanding(customer)
        self.assertEqual(result, Decimal("100.00"))

    def test_customer_with_one_unconfirmed_sale_does_not_count_it(self):
        customer = Customer.objects.create(name="Test Customer")
        sale = Sale.objects.create(
            number="S456",
            date=datetime.date(2023, 10, 7),
            customer=customer,
            total=Decimal("50.00"),
            confirmed=False
        )
        result = customer_outstanding(customer)
        self.assertEqual(result, Decimal("0.00"))

    def test_customer_with_multiple_confirmed_sales_returns_total_balance_due(self):
        customer = Customer.objects.create(name="Test Customer")
        sale1 = Sale.objects.create(
            number="S789",
            date=datetime.date(2023, 10, 6),
            customer=customer,
            total=Decimal("75.00"),
            confirmed=True
        )
        sale2 = Sale.objects.create(
            number="S012",
            date=datetime.date(2023, 10, 8),
            customer=customer,
            total=Decimal("25.00"),
            confirmed=True
        )
        result = customer_outstanding(customer)
        self.assertEqual(result, Decimal("100.00"))
