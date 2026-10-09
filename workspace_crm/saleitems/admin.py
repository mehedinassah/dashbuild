from django.contrib import admin

from .models import SaleItem


@admin.register(SaleItem)
class SaleItemAdmin(admin.ModelAdmin):
    list_display = ("description", "sale", "product", "quantity", "unit_price",)
    search_fields = ("description",)
