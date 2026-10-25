from django.test import TestCase
from decimal import Decimal
from sales.services import sales_by_month
from customers.models import Customer
from sales.models import Sale
import datetime

class TestSalesByMonth(TestCase):
    def setUp(self):
        # Create a customer
        self.customer = Customer.objects.create(name="Test Customer", email="test@example.com", phone="1234567890")

        # Create confirmed sales in different months
        self.sale_oct_2023 = Sale.objects.create(
            number="S123",
            date=datetime.date(2023, 10, 5),
            customer=self.customer,
            total=Decimal("100.00"),
            confirmed=True
        )
        self.sale_nov_2023 = Sale.objects.create(
            number="S456",
            date=datetime.date(2023, 11, 10),
            customer=self.customer,
            total=Decimal("200.00"),
            confirmed=True
        )
        self.sale_oct_2023_unconfirmed = Sale.objects.create(
            number="S789",
            date=datetime.date(2023, 10, 15),
            customer=self.customer,
            total=Decimal("50.00"),
            confirmed=False
        )
        self.sale_dec_2023 = Sale.objects.create(
            number="S101",
            date=datetime.date(2023, 12, 20),
            customer=self.customer,
            total=Decimal("300.00"),
            confirmed=True
        )

    def test_sales_by_month_normal_case(self):
        # Test with confirmed sales in October and November 2023
        result = sales_by_month()
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], ("2023-10", Decimal("100.00")))
        self.assertEqual(result[1], ("2023-11", Decimal("200.00")))
        self.assertEqual(result[2], ("2023-12", Decimal("300.00")))

    def test_sales_by_month_empty_case(self):
        # Test when there are no confirmed sales
        Sale.objects.all().delete()
        result = sales_by_month()
        self.assertEqual(result, [])

    def test_sales_by_month_boundary_confirmed(self):
        # Test with a sale that is confirmed and one that is not
        result = sales_by_month()
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], ("2023-10", Decimal("100.00")))
        self.assertEqual(result[1], ("2023-11", Decimal("200.00")))
        self.assertEqual(result[2], ("2023-12", Decimal("300.00")))

    def test_sales_by_month_confirmed_only(self):
        # Test that only confirmed sales are counted
        result = sales_by_month()
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], ("2023-10", Decimal("100.00")))
        self.assertEqual(result[1], ("2023-11", Decimal("200.00")))
        self.assertEqual(result[2], ("2023-12", Decimal("300.00")))
