from django.apps import AppConfig


class SaleItemConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "saleitems"
    verbose_name = "Saleitems"
    crud_module = True
    icon = "📦"
