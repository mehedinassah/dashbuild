from django.db import models


class Product(models.Model):
    name = models.CharField(max_length=200)
    sku = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    stock = models.IntegerField(default=0)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return str(self.name)

    def in_stock(self):
        return self.stock > 0
