from django.test import TestCase
from decimal import Decimal
import datetime
from sales.models import Sale, Payment
from customers.models import Customer

class TestSaleAmountPaid(TestCase):
    def test_amount_paid_with_payments(self):
        sale = Sale.objects.create(number="S001", date=datetime.date(2023, 10, 5), customer=Customer.objects.create(name="John Doe"), total=Decimal("100.00"), confirmed=True)
        payment1 = Payment.objects.create(sale=sale, amount=Decimal("50.00"), paid_on=datetime.date(2023, 10, 6))
        payment2 = Payment.objects.create(sale=sale, amount=Decimal("30.00"), paid_on=datetime.date(2023, 10, 7))
        self.assertEqual(sale.amount_paid(), Decimal("80.00"))

    def test_amount_paid_no_payments(self):
        sale = Sale.objects.create(number="S002", date=datetime.date(2023, 10, 5), customer=Customer.objects.create(name="Jane Smith"), total=Decimal("0.00"), confirmed=True)
        self.assertEqual(sale.amount_paid(), Decimal("0.00"))

    def test_amount_paid_with_one_payment(self):
        sale = Sale.objects.create(number="S003", date=datetime.date(2023, 10, 5), customer=Customer.objects.create(name="Alice Johnson"), total=Decimal("200.00"), confirmed=True)
        payment = Payment.objects.create(sale=sale, amount=Decimal("100.00"), paid_on=datetime.date(2023, 10, 8))
        self.assertEqual(sale.amount_paid(), Decimal("100.00"))
