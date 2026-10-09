from django.urls import path

from . import views

app_name = "saleitems"

urlpatterns = [
    path("", views.SaleItemListView.as_view(), name="list"),
    path("new/", views.SaleItemCreateView.as_view(), name="create"),
    path("<int:pk>/edit/", views.SaleItemUpdateView.as_view(), name="update"),
    path("<int:pk>/delete/", views.SaleItemDeleteView.as_view(), name="delete"),
]
