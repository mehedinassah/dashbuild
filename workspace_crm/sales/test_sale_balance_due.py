from django.test import TestCase
from decimal import Decimal
import datetime
from sales.models import Sale, Payment
from customers.models import Customer
from products.models import Product
from saleitems.models import SaleItem

class TestSaleBalanceDue(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(name="John Doe", email="john@example.com", phone="1234567890")
        self.product = Product.objects.create(name="Laptop", sku="LAP-001", price=Decimal("1000.00"), stock=10)
        
        # Create a sale
        self.sale = Sale.objects.create(number="SAL-001", date=datetime.date(2023, 10, 5), customer=self.customer, total=Decimal("2000.00"))
        
        # Add sale items
        self.sale_item = SaleItem.objects.create(
            description="Laptop purchase",
            sale=self.sale,
            product=self.product,
            quantity=2,
            unit_price=Decimal("1000.00")
        )
        
        # Create a payment
        self.payment = Payment.objects.create(sale=self.sale, amount=Decimal("500.00"), paid_on=datetime.date(2023, 10, 6))

    def test_balance_due_with_partial_payment(self):
        balance = self.sale.balance_due()
        self.assertEqual(balance, Decimal("1500.00"))

    def test_balance_due_with_full_payment(self):
        # Create a payment that covers the total amount
        full_payment = Payment.objects.create(sale=self.sale, amount=Decimal("2000.00"), paid_on=datetime.date(2023, 10, 6))
        balance = self.sale.balance_due()
        self.assertEqual(balance, Decimal("0.00"))

    def test_balance_due_with_no_payments(self):
        # Remove the existing payment
        self.payment.delete()
        balance = self.sale.balance_due()
        self.assertEqual(balance, Decimal("2000.00"))

    def test_balance_due_never_negative(self):
        # Create a payment that exceeds the total amount
        over_payment = Payment.objects.create(sale=self.sale, amount=Decimal("3000.00"), paid_on=datetime.date(2023, 10, 6))
        balance = self.sale.balance_due()
        self.assertEqual(balance, Decimal("0.00"))
