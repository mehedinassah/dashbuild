"""Business logic functions."""


def reduce_stock(product, quantity):
    if quantity < 0:
        raise ValueError("Quantity cannot be negative")
    if product.stock < quantity:
        raise ValueError(f"Not enough stock: {product.stock} available, {quantity} requested")
    product.stock -= quantity
    product.save()


def low_stock_products(threshold=5):
    from products.models import Product
    products = Product.objects.filter(stock__lt=threshold).order_by('stock', 'name')
    return list(products)
