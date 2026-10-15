from django.db import models
class Customer(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    notes = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

    def total_spent(self):
        return sum(sale.total for sale in self.sale_set.all())
