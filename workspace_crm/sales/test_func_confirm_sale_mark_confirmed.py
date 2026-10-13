from django.test import TestCase
from decimal import Decimal
from sales.models import Sale
from products.models import Product
from customers.models import Customer
from saleitems.models import SaleItem
from sales.services import confirm_sale

class TestConfirmSale(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(name="John Doe", email="john@example.com", phone="123456789")
        self.product = Product.objects.create(name="Test Product", sku="SKU123", price=Decimal("10.00"), stock=5)
        
        # Create a sale
        self.sale = Sale.objects.create(number="S12345", date="2023-04-05", customer=self.customer, total=Decimal("0.00"))
        
        # Create a sale item
        self.sale_item = SaleItem.objects.create(description="Test Item", sale=self.sale, product=self.product, quantity=2, unit_price=Decimal("10.00"))

    def test_confirm_sale_sets_confirmed_to_true_and_saves_the_sale(self):
        # Act
        confirm_sale(self.sale)
        
        # Refresh the sale from the database
        self.sale.refresh_from_db()
        
        # Assert
        self.assertTrue(self.sale.confirmed)
        
    def test_confirm_sale_raises_value_error_if_already_confirmed(self):
        # Arrange
        self.sale.confirmed = True
        self.sale.save()
        
        # Act / Assert
        with self.assertRaises(ValueError):
            confirm_sale(self.sale)
        
        # Refresh the sale from the database to ensure no changes were made
        self.sale.refresh_from_db()
        self.assertTrue(self.sale.confirmed)  # Should still be True

    def test_confirm_sale_does_not_lower_stock_twice_if_confirmed_already(self):
        # Arrange
        self.product.stock = 5
        self.product.save()
        
        # Confirm the sale once
        confirm_sale(self.sale)
        
        # Refresh product stock after first confirmation
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 3)  # Stock should be reduced by 2
        
        # Act / Assert: Try to confirm again (should raise ValueError and not change stock)
        with self.assertRaises(ValueError):
            confirm_sale(self.sale)
        
        # Refresh product stock after second confirmation attempt
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 3)  # Stock should remain at 3
