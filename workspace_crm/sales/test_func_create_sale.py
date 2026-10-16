from django.test import TestCase
from sales.services import create_sale
from customers.models import Customer
from sales.models import Sale
import datetime
from decimal import Decimal

class TestCreateSale(TestCase):
    def test_create_sale_with_active_customer(self):
        customer = Customer.objects.create(name="John Doe", email="john@example.com", phone="1234567890", notes="Test customer", is_active=True)
        sale = create_sale(customer, "SALE001", datetime.date(2023, 10, 5))
        self.assertEqual(sale.number, "SALE001")
        self.assertEqual(sale.date, datetime.date(2023, 10, 5))
        self.assertEqual(sale.customer, customer)
        self.assertEqual(sale.total, Decimal("0.00"))

    def test_create_sale_with_inactive_customer_raises_error(self):
        customer = Customer.objects.create(name="Jane Doe", email="jane@example.com", phone="0987654321", notes="Test customer", is_active=False)
        with self.assertRaises(ValueError):
            create_sale(customer, "SALE002", datetime.date(2023, 10, 5))

    def test_create_sale_does_not_create_sale_for_inactive_customer(self):
        customer = Customer.objects.create(name="Jane Doe", email="jane@example.com", phone="0987654321", notes="Test customer", is_active=False)
        with self.assertRaises(ValueError):
            create_sale(customer, "SALE003", datetime.date(2023, 10, 5))
        self.assertEqual(Sale.objects.count(), 0)

    def test_create_sale_with_different_number_and_date(self):
        customer = Customer.objects.create(name="Alice Smith", email="alice@example.com", phone="1122334455", notes="Test customer", is_active=True)
        sale = create_sale(customer, "SALE004", datetime.date(2023, 10, 6))
        self.assertEqual(sale.number, "SALE004")
        self.assertEqual(sale.date, datetime.date(2023, 10, 6))
        self.assertEqual(sale.customer, customer)
        self.assertEqual(sale.total, Decimal("0.00"))
