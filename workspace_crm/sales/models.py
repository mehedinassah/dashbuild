from django.db import models
import decimal
from decimal import Decimal


class Sale(models.Model):
    number = models.CharField(max_length=200, unique=True)
    date = models.DateField(null=True, blank=True)
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    confirmed = models.BooleanField(default=False)

    class Meta:
        ordering = ["number"]

    def __str__(self):
        return str(self.number)

    def calculate_total(self):
        total = decimal.Decimal("0.00")
        for item in self.saleitem_set.all():
            total += item.line_total()
        self.total = total
        return total

    def amount_paid(self):
        total = Decimal('0.00')
        for payment in self.payment_set.all():
            total += payment.amount
        return total


class Payment(models.Model):
    sale = models.ForeignKey('sales.Sale', on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_on = models.DateField(auto_now_add=True)

    def __str__(self):
        return f"Payment {self.pk}"
