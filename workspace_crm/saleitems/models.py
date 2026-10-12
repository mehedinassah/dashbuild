from django.db import models


class SaleItem(models.Model):
    description = models.CharField(max_length=200)
    sale = models.ForeignKey("sales.Sale", on_delete=models.PROTECT)
    product = models.ForeignKey("products.Product", on_delete=models.PROTECT)
    quantity = models.IntegerField(default=0)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        ordering = ["description"]

    def __str__(self):
        return str(self.description)

    def line_total(self):
            return self.unit_price * self.quantity
