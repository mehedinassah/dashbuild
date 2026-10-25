from django.test import TestCase
from decimal import Decimal
import datetime
from sales.models import Sale
from saleitems.models import SaleItem
from products.models import Product
from customers.models import Customer
from sales.services import confirm_sale

class TestConfirmSale(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(name="Alice", email="alice@example.com", phone="1234567890")
        self.product = Product.objects.create(name="Laptop", sku="LAP-001", price=Decimal("1000.00"), stock=5)
        self.sale = Sale.objects.create(number="S-001", date=datetime.date(2023, 10, 5), customer=self.customer, total=Decimal("0.00"), confirmed=False)
        
        # Create sale items
        self.sale_item_1 = SaleItem.objects.create(description="Laptop purchase", sale=self.sale, product=self.product, quantity=2, unit_price=Decimal("1000.00"))
        self.sale_item_2 = SaleItem.objects.create(description="Extra laptop", sale=self.sale, product=self.product, quantity=3, unit_price=Decimal("1000.00"))

    def test_confirm_sale_sets_confirmed_and_calculates_total(self):
        # Confirm the sale
        confirm_sale(self.sale)

        # Refresh from DB to ensure changes are saved
        self.sale.refresh_from_db()

        # Check if confirmed is True
        self.assertTrue(self.sale.confirmed)

        # Calculate expected total (sum of line totals)
        expected_total = Decimal("5000.00")
        self.assertEqual(self.sale.total, expected_total)

    def test_confirm_sale_does_not_change_if_already_confirmed(self):
        # Confirm the sale first
        confirm_sale(self.sale)
        
        # Refresh from DB to ensure changes are saved
        self.sale.refresh_from_db()

        # Try confirming again (should not change anything)
        with self.assertRaises(ValueError):
            confirm_sale(self.sale)

        # Check that confirmed is still True and total remains the same
        self.assertTrue(self.sale.confirmed)
        self.assertEqual(self.sale.total, Decimal("5000.00"))

    def test_confirm_sale_does_not_change_if_insufficient_stock(self):
        # Reduce stock to 2 (insufficient for sale_item_2's quantity of 3)
        self.product.stock = 2
        self.product.save()

        # Try confirming the sale (should raise ValueError)
        with self.assertRaises(ValueError):
            confirm_sale(self.sale)

        # Check that confirmed is still False and total remains unchanged
        self.assertFalse(self.sale.confirmed)
        self.assertEqual(self.sale.total, Decimal("0.00"))

    def test_confirm_sale_does_not_change_if_stock_is_exactly_sufficient(self):
        # Set stock to exactly 5 (equal to the sum of quantities in sale items)
        self.product.stock = 5
        self.product.save()

        # Confirm the sale
        confirm_sale(self.sale)

        # Refresh from DB to ensure changes are saved
        self.sale.refresh_from_db()

        # Check if confirmed is True and total is calculated correctly
        self.assertTrue(self.sale.confirmed)
        expected_total = Decimal("5000.00")
        self.assertEqual(self.sale.total, expected_total)

    def test_confirm_sale_does_not_change_if_stock_is_one_more_than_needed(self):
        # Set stock to 6 (one more than needed)
        self.product.stock = 6
        self.product.save()

        # Confirm the sale
        confirm_sale(self.sale)

        # Refresh from DB to ensure changes are saved
        self.sale.refresh_from_db()

        # Check if confirmed is True and total is calculated correctly
        self.assertTrue(self.sale.confirmed)
        expected_total = Decimal("5000.00")
        self.assertEqual(self.sale.total, expected_total)
