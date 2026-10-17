from django.contrib import admin

from .models import Sale


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ("number", "date", "customer", "total",)
    search_fields = ("number",)

from .models import Payment  # noqa: E402
admin.site.register(Payment)
