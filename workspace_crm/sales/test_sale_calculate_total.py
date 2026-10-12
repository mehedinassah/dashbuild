from django.test import TestCase
from sales.models import Sale
from customers.models import Customer
from products.models import Product
from saleitems.models import SaleItem
import decimal

class TestCalculateTotal(TestCase):
    def test_sale_with_no_items_has_total_zero(self):
        sale = Sale.objects.create(number="S001", date="2023-04-05", customer=Customer.objects.create(name="John Doe"))
        self.assertEqual(sale.calculate_total(), decimal.Decimal("0.00"))

    def test_sale_with_one_item(self):
        product = Product.objects.create(name="Laptop", sku="LAP123", price=decimal.Decimal("1000.00"), stock=10)
        sale = Sale.objects.create(number="S002", date="2023-04-05", customer=Customer.objects.create(name="Jane Smith"))
        sale_item = SaleItem.objects.create(description="Laptop purchase", sale=sale, product=product, quantity=2, unit_price=decimal.Decimal("1000.00"))
        self.assertEqual(sale.calculate_total(), decimal.Decimal("2000.00"))

    def test_sale_with_multiple_items(self):
        product1 = Product.objects.create(name="Laptop", sku="LAP123", price=decimal.Decimal("1000.00"), stock=10)
        product2 = Product.objects.create(name="Mouse", sku="MSE456", price=decimal.Decimal("50.00"), stock=50)
        sale = Sale.objects.create(number="S003", date="2023-04-05", customer=Customer.objects.create(name="Alice Johnson"))
        sale_item1 = SaleItem.objects.create(description="Laptop purchase", sale=sale, product=product1, quantity=1, unit_price=decimal.Decimal("1000.00"))
        sale_item2 = SaleItem.objects.create(description="Mouse purchase", sale=sale, product=product2, quantity=3, unit_price=decimal.Decimal("50.00"))
        self.assertEqual(sale.calculate_total(), decimal.Decimal("1150.00"))
