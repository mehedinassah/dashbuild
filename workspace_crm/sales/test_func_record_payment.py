from django.test import TestCase
from decimal import Decimal
import datetime
from sales.models import Sale, Payment
from customers.models import Customer
from products.models import Product
from saleitems.models import SaleItem
from sales.services import record_payment

class TestRecordPayment(TestCase):
    def test_record_payment_with_confirmed_sale_and_positive_amount(self):
        customer = Customer.objects.create(name="John Doe", email="john@example.com", phone="123456789")
        sale = Sale.objects.create(number="S001", date=datetime.date(2023, 10, 5), customer=customer, confirmed=True)
        product = Product.objects.create(name="Laptop", sku="LP001", price=Decimal("1000.00"), stock=10)
        sale_item = SaleItem.objects.create(description="Laptop purchase", sale=sale, product=product, quantity=2, unit_price=Decimal("1000.00"))

        payment = record_payment(sale, Decimal("500.00"))
        payment.refresh_from_db()
        self.assertEqual(payment.amount, Decimal("500.00"))
        self.assertEqual(Payment.objects.count(), 1)

    def test_record_payment_with_unconfirmed_sale(self):
        customer = Customer.objects.create(name="Jane Doe", email="jane@example.com", phone="987654321")
        sale = Sale.objects.create(number="S002", date=datetime.date(2023, 10, 6), customer=customer, confirmed=False)

        with self.assertRaises(ValueError) as context:
            record_payment(sale, Decimal("200.00"))
        self.assertEqual(str(context.exception), "Sale is not confirmed")
        self.assertEqual(Payment.objects.count(), 0)

    def test_record_payment_with_zero_amount(self):
        customer = Customer.objects.create(name="Alice", email="alice@example.com", phone="1122334455")
        sale = Sale.objects.create(number="S003", date=datetime.date(2023, 10, 7), customer=customer, confirmed=True)

        with self.assertRaises(ValueError) as context:
            record_payment(sale, Decimal("0.00"))
        self.assertEqual(str(context.exception), "Amount must be positive")
        self.assertEqual(Payment.objects.count(), 0)

    def test_record_payment_with_negative_amount(self):
        customer = Customer.objects.create(name="Bob", email="bob@example.com", phone="5544332211")
        sale = Sale.objects.create(number="S004", date=datetime.date(2023, 10, 8), customer=customer, confirmed=True)

        with self.assertRaises(ValueError) as context:
            record_payment(sale, Decimal("-100.00"))
        self.assertEqual(str(context.exception), "Amount must be positive")
        self.assertEqual(Payment.objects.count(), 0)
