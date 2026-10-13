"""Business logic functions."""
from products.services import reduce_stock


def confirm_sale(sale):
    # Check if all items in the sale are available
    for item in sale.saleitem_set.all():
        product = item.product
        if item.quantity > product.stock:
            raise ValueError(f"Insufficient stock for {product.name}")

    # If all items are available, reduce stock for each item
    for item in sale.saleitem_set.all():
        reduce_stock(item.product, item.quantity)
