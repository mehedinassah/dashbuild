from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('customers/', include('customers.urls')),
    path('products/', include('products.urls')),
    path('', include('core.urls')),
    path('sales/', include('sales.urls')),
    path('saleitems/', include('saleitems.urls')),
]
