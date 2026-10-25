"""Business logic functions."""
from products.services import reduce_stock
from sales.models import Sale
from decimal import Decimal
from sales.models import Payment
import datetime


def confirm_sale(sale):
    # Check if sale is already confirmed
    if sale.confirmed:
        raise ValueError("Sale is already confirmed")

    # Check if all items in the sale are available
    for item in sale.saleitem_set.all():
        product = item.product
        if item.quantity > product.stock:
            raise ValueError(f"Insufficient stock for {product.name}")

    # Calculate the total before any changes
    calculated_total = sale.calculate_total()

    # If all items are available, reduce stock for each item
    for item in sale.saleitem_set.all():
        reduce_stock(item.product, item.quantity)

    # Set confirmed to True and save the sale
    sale.confirmed = True
    sale.total = calculated_total
    sale.save()


def cancel_sale(sale):
    if not sale.confirmed:
        raise ValueError("Sale is not confirmed.")

    # Retrieve all items in the sale
    sale_items = sale.saleitem_set.all()

    # Add each item's quantity back to its product's stock
    for item in sale_items:
        product = item.product
        product.stock += item.quantity
        product.save()

    # Set the sale as unconfirmed
    sale.confirmed = False
    sale.save()


def create_sale(customer, number, date):
    if not customer.is_active:
        raise ValueError("Customer is not active")
    sale = Sale.objects.create(number=number, date=date, customer=customer, total=Decimal('0.00'))
    return sale


def record_payment(sale, amount):
    if not sale.confirmed:
        raise ValueError('Sale is not confirmed')
    if amount <= Decimal('0'):
        raise ValueError('Amount must be positive')
    payment = Payment.objects.create(sale=sale, amount=amount, paid_on=datetime.date.today())
    return payment
