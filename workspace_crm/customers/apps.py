from django.apps import AppConfig


class CustomersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "customers"
    verbose_name = "Customers"
    crud_module = True
    icon = "👥"
    list_url = "customer_list"
