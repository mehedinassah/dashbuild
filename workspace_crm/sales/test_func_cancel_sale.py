from django.test import TestCase
from decimal import Decimal
from sales.models import Sale
from saleitems.models import SaleItem
from products.models import Product
from customers.models import Customer
from sales.services import cancel_sale

class TestCancelSale(TestCase):
    def test_cancel_confirmed_sale(self):
        # Create a customer
        customer = Customer.objects.create(name="Alice", email="alice@example.com", phone="123456789")

        # Create a product with some stock
        product = Product.objects.create(name="Laptop", sku="LAP001", price=Decimal("1000.00"), stock=10)

        # Create a sale
        sale = Sale.objects.create(number="S001", date="2023-10-05", customer=customer, total=Decimal("1000.00"), confirmed=True)

        # Create a sale item with quantity and unit price
        sale_item = SaleItem.objects.create(description="Laptop purchase", sale=sale, product=product, quantity=2, unit_price=Decimal("1000.00"))

        # Confirm the sale (this is already done in setup)
        
        # Call cancel_sale on the confirmed sale
        cancel_sale(sale)

        # Refresh from DB to get updated values
        sale.refresh_from_db()
        product.refresh_from_db()

        # Check if the sale is no longer confirmed
        self.assertFalse(sale.confirmed)

        # Check if the product's stock has been increased by the quantity sold
        self.assertEqual(product.stock, 12)

    def test_cancel_unconfirmed_sale_raises_error(self):
        # Create a customer
        customer = Customer.objects.create(name="Bob", email="bob@example.com", phone="987654321")

        # Create a product with some stock
        product = Product.objects.create(name="Phone", sku="PHO001", price=Decimal("500.00"), stock=5)

        # Create a sale that is not confirmed
        sale = Sale.objects.create(number="S002", date="2023-10-06", customer=customer, total=Decimal("500.00"), confirmed=False)

        # Create a sale item with quantity and unit price
        sale_item = SaleItem.objects.create(description="Phone purchase", sale=sale, product=product, quantity=1, unit_price=Decimal("500.00"))

        # Attempt to cancel an unconfirmed sale (should raise ValueError)
        with self.assertRaises(ValueError):
            cancel_sale(sale)

        # Check that the sale remains unconfirmed and product stock is unchanged
        sale.refresh_from_db()
        product.refresh_from_db()

        self.assertFalse(sale.confirmed)
        self.assertEqual(product.stock, 5)

    def test_cancel_confirmed_sale_with_multiple_items(self):
        # Create a customer
        customer = Customer.objects.create(name="Charlie", email="charlie@example.com", phone="123456789")

        # Create two products with some stock
        product1 = Product.objects.create(name="Tablet", sku="TAB001", price=Decimal("300.00"), stock=15)
        product2 = Product.objects.create(name="Mouse", sku="MOU001", price=Decimal("20.00"), stock=20)

        # Create a sale
        sale = Sale.objects.create(number="S003", date="2023-10-07", customer=customer, total=Decimal("940.00"), confirmed=True)

        # Create two sale items with quantities and unit prices
        sale_item1 = SaleItem.objects.create(description="Tablet purchase", sale=sale, product=product1, quantity=2, unit_price=Decimal("300.00"))
        sale_item2 = SaleItem.objects.create(description="Mouse purchase", sale=sale, product=product2, quantity=5, unit_price=Decimal("20.00"))

        # Call cancel_sale on the confirmed sale
        cancel_sale(sale)

        # Refresh from DB to get updated values
        sale.refresh_from_db()
        product1.refresh_from_db()
        product2.refresh_from_db()

        # Check if the sale is no longer confirmed
        self.assertFalse(sale.confirmed)

        # Check if both products' stock has been increased by their respective quantities sold
        self.assertEqual(product1.stock, 17)
        self.assertEqual(product2.stock, 25)

    def test_cancel_confirmed_sale_with_zero_stock(self):
        # Create a customer
        customer = Customer.objects.create(name="David", email="david@example.com", phone="987654321")

        # Create a product with zero stock
        product = Product.objects.create(name="Monitor", sku="MON001", price=Decimal("200.00"), stock=0)

        # Create a sale
        sale = Sale.objects.create(number="S004", date="2023-10-08", customer=customer, total=Decimal("200.00"), confirmed=True)

        # Create a sale item with quantity and unit price
        sale_item = SaleItem.objects.create(description="Monitor purchase", sale=sale, product=product, quantity=3, unit_price=Decimal("200.00"))

        # Call cancel_sale on the confirmed sale
        cancel_sale(sale)

        # Refresh from DB to get updated values
        sale.refresh_from_db()
        product.refresh_from_db()

        # Check if the sale is no longer confirmed
        self.assertFalse(sale.confirmed)

        # Check if the product's stock has been increased by the quantity sold (even though it was zero before)
        self.assertEqual(product.stock, 3)
