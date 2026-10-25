"""Business logic functions."""
from products.services import reduce_stock
from sales.models import Sale
from decimal import Decimal
from sales.models import Payment
import datetime
from django.db.models.functions import TruncMonth
from django.db.models import Sum


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


def total_revenue():
    confirmed_sales = Sale.objects.filter(confirmed=True)
    return sum(sale.total for sale in confirmed_sales)


def outstanding_balance():
    from sales.models import Sale
    confirmed_sales = Sale.objects.filter(confirmed=True)
    total_outstanding = Decimal('0.00')
    for sale in confirmed_sales:
        total_outstanding += sale.balance_due()
    return total_outstanding


def sales_by_month():
    # Get all confirmed sales
    confirmed_sales = Sale.objects.filter(confirmed=True)

    if not confirmed_sales.exists():
        return []

    # Group by month and sum the totals
    monthly_totals = (confirmed_sales
                      .annotate(month=TruncMonth('date'))
                      .values('month')
                      .annotate(total=Sum('total'))
                      .order_by('month'))

    # Format the result as a list of tuples
    result = [
        (str(entry['month']).split('-')[0] + '-' + str(entry['month']).split('-')[1], Decimal(str(entry['total']))) 
        for entry in monthly_totals
    ]

    return result


def top_customers(limit=5):
    from sales.models import Sale
    from customers.models import Customer

    # Get all confirmed sales
    confirmed_sales = Sale.objects.filter(confirmed=True)

    # Group sales by customer and sum the totals
    customer_totals = {}
    for sale in confirmed_sales:
        customer = sale.customer
        if customer not in customer_totals:
            customer_totals[customer] = Decimal('0.00')
        customer_totals[customer] += sale.total

    # Sort customers by total spent in descending order
    sorted_customers = sorted(customer_totals.items(), key=lambda x: x[1], reverse=True)

    # Return the top 'limit' customers as a list of (customer, total) tuples
    return sorted_customers[:limit]
