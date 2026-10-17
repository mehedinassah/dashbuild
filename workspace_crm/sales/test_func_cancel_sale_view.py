from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from sales.models import Sale
from customers.models import Customer
from products.models import Product
from saleitems.models import SaleItem
import datetime
from decimal import Decimal

class CancelSaleViewTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(name="John Doe", email="john@example.com", phone="1234567890", notes="Test customer", is_active=True)
        self.product = Product.objects.create(name="Test Product", sku="TESTSKU001", price=Decimal("10.00"), stock=100)
        self.sale = Sale.objects.create(number="S001", date=datetime.date(2023, 10, 5), customer=self.customer, total=Decimal("0.00"), confirmed=True)
        self.sale_item = SaleItem.objects.create(description="Test Item", sale=self.sale, product=self.product, quantity=2, unit_price=Decimal("10.00"))

    def shown(self, response):
        return [(m.level_tag, str(m)) for m in get_messages(response.wsgi_request)]

    def test_cancel_sale_success(self):
        response = self.client.post(reverse('sales:cancel_sale_view', args=[self.sale.pk]))
        self.assertRedirects(response, reverse('sales:list'))
        self.assertEqual(self.shown(response), [('success', 'Sale cancelled.')])
        self.sale.refresh_from_db()
        self.assertFalse(self.sale.confirmed)

    def test_cancel_sale_error(self):
        # Create a scenario where cancel_sale raises ValueError (e.g., sale is not confirmed)
        self.sale.confirmed = False
        self.sale.save()
        response = self.client.post(reverse('sales:cancel_sale_view', args=[self.sale.pk]))
        self.assertRedirects(response, reverse('sales:list'))
        self.assertEqual([level for level, text in self.shown(response)], ["error"])
        self.sale.refresh_from_db()
        self.assertFalse(self.sale.confirmed)  # Assuming the error does not change confirmed status

    def test_get_cancel_sale_view_returns_405(self):
        response = self.client.get(reverse('sales:cancel_sale_view', args=[self.sale.pk]))
        self.assertEqual(response.status_code, 405)
