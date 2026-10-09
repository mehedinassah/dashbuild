from django.db import models


class Sale(models.Model):
    number = models.CharField(max_length=200, unique=True)
    date = models.DateField(null=True, blank=True)
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        ordering = ["number"]

    def __str__(self):
        return str(self.number)
