from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from sales.models import Sale, Payment
from customers.models import Customer
from products.models import Product
from saleitems.models import SaleItem
from decimal import Decimal
import datetime

class RecordPaymentViewTests(TestCase):
    def setUp(self):
        # Create a customer
        self.customer = Customer.objects.create(name="John Doe", email="john@example.com", phone="1234567890")
        
        # Create a product
        self.product = Product.objects.create(name="Test Product", sku="TEST123", price=Decimal("10.00"), stock=10)
        
        # Create a sale
        self.sale = Sale.objects.create(
            number="S001",
            date=datetime.date(2023, 10, 5),
            customer=self.customer,
            confirmed=True
        )
        
        # Create a sale item for the sale
        self.sale_item = SaleItem.objects.create(
            description="Test Item",
            sale=self.sale,
            product=self.product,
            quantity=2,
            unit_price=Decimal("10.00")
        )
        
    def shown(self, response):
        return [(m.level_tag, str(m)) for m in get_messages(response.wsgi_request)]

    def test_valid_amount_payment_recorded(self):
        url = reverse('sales:record_payment_view', args=[self.sale.pk])
        data = {'amount': '50.00'}
        response = self.client.post(url, data)
        
        self.assertRedirects(response, reverse('sales:list'))
        self.assertEqual(self.shown(response), [('success', "Payment recorded.")])
        
        # Refresh the sale from the database to check if payment was recorded
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.amount_paid(), Decimal("50.00"))
        
        # Check that a Payment object was created
        payment = Payment.objects.get(sale=self.sale)
        self.assertEqual(payment.amount, Decimal("50.00"))
        self.assertEqual(payment.paid_on, datetime.date.today())

    def test_invalid_amount_shows_error(self):
        url = reverse('sales:record_payment_view', args=[self.sale.pk])
        data = {'amount': 'abc'}
        response = self.client.post(url, data)
        
        self.assertRedirects(response, reverse('sales:list'))
        self.assertEqual([level for level, text in self.shown(response)], ["error"])
        
        # Check that no payment was recorded
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.amount_paid(), Decimal("0.00"))
        self.assertFalse(Payment.objects.filter(sale=self.sale).exists())

    def test_unconfirmed_sale_shows_error(self):
        # Create an unconfirmed sale
        unconfirmed_sale = Sale.objects.create(
            number="S002",
            date=datetime.date(2023, 10, 5),
            customer=self.customer,
            confirmed=False
        )
        
        url = reverse('sales:record_payment_view', args=[unconfirmed_sale.pk])
        data = {'amount': '50.00'}
        response = self.client.post(url, data)
        
        self.assertRedirects(response, reverse('sales:list'))
        self.assertEqual([level for level, text in self.shown(response)], ["error"])
        
        # Check that no payment was recorded
        unconfirmed_sale.refresh_from_db()
        self.assertEqual(unconfirmed_sale.amount_paid(), Decimal("0.00"))
        self.assertFalse(Payment.objects.filter(sale=unconfirmed_sale).exists())

    def test_zero_amount_shows_error(self):
        url = reverse('sales:record_payment_view', args=[self.sale.pk])
        data = {'amount': '0.00'}
        response = self.client.post(url, data)
        
        self.assertRedirects(response, reverse('sales:list'))
        self.assertEqual([level for level, text in self.shown(response)], ["error"])
        
        # Check that no payment was recorded
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.amount_paid(), Decimal("0.00"))
        self.assertFalse(Payment.objects.filter(sale=self.sale).exists())

    def test_get_request_returns_405(self):
        url = reverse('sales:record_payment_view', args=[self.sale.pk])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 405)
