from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from sales.models import Sale
from customers.models import Customer
from products.models import Product
from saleitems.models import SaleItem
from decimal import Decimal
import datetime

class ConfirmSaleViewTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(name="Alice", email="alice@example.com", phone="1234567890")
        self.product = Product.objects.create(name="Laptop", sku="SKU123", price=Decimal("1000.00"), stock=10)
        self.sale = Sale.objects.create(number="S12345", date=datetime.date(2023, 10, 5), customer=self.customer, total=Decimal("1000.00"), confirmed=False)
        self.sale_item = SaleItem.objects.create(description="Laptop purchase", sale=self.sale, product=self.product, quantity=1, unit_price=Decimal("1000.00"))

    def shown(self, response):
        return [(m.level_tag, str(m)) for m in get_messages(response.wsgi_request)]

    def test_success(self):
        response = self.client.post(reverse("sales:confirm_sale_view", args=[self.sale.pk]))
        self.assertRedirects(response, reverse("sales:list"))
        self.assertEqual(self.shown(response), [("success", "Sale confirmed.")])
        self.sale.refresh_from_db()
        self.assertTrue(self.sale.confirmed)

    def test_failure_during_confirmation(self):
        # Mock confirm_sale to raise ValueError (this would be done in the service layer)
        # For this test, we assume that confirm_sale raises an error when stock is zero
        self.product.stock = 0
        self.product.save()
        
        response = self.client.post(reverse("sales:confirm_sale_view", args=[self.sale.pk]))
        self.assertRedirects(response, reverse("sales:list"))
        self.assertEqual([level for level, text in self.shown(response)], ["error"])
        self.sale.refresh_from_db()
        self.assertFalse(self.sale.confirmed)

    def test_get_request_returns_405(self):
        response = self.client.get(reverse("sales:confirm_sale_view", args=[self.sale.pk]))
        self.assertEqual(response.status_code, 405)
