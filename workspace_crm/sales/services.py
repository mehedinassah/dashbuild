"""Business logic functions."""
from products.services import reduce_stock


def confirm_sale(sale):
    # Check if sale is already confirmed
    if sale.confirmed:
        raise ValueError("Sale is already confirmed")

    # Check if all items in the sale are available
    for item in sale.saleitem_set.all():
        product = item.product
        if item.quantity > product.stock:
            raise ValueError(f"Insufficient stock for {product.name}")

    # If all items are available, reduce stock for each item
    for item in sale.saleitem_set.all():
        reduce_stock(item.product, item.quantity)

    # Set confirmed to True and save the sale
    sale.confirmed = True
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
