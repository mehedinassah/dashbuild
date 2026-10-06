from django.apps import AppConfig


class ProductConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "products"
    verbose_name = "Products"
    crud_module = True
