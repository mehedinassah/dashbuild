from django.db.models import Q
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from .models import Product

FIELDS = ["name", "sku", "price", "stock"]
SEARCH_FIELDS = ["name", "sku"]


class ProductListView(ListView):
    model = Product
    template_name = "products/list.html"
    context_object_name = "items"

    def get_queryset(self):
        queryset = super().get_queryset()
        q = self.request.GET.get("q", "").strip()
        if q:
            condition = Q()
            for field in SEARCH_FIELDS:
                condition |= Q(**{field + "__icontains": q})
            queryset = queryset.filter(condition)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["q"] = self.request.GET.get("q", "").strip()
        return context


class ProductCreateView(CreateView):
    model = Product
    fields = FIELDS
    template_name = "products/form.html"
    success_url = reverse_lazy("products:list")


class ProductUpdateView(UpdateView):
    model = Product
    fields = FIELDS
    template_name = "products/form.html"
    success_url = reverse_lazy("products:list")


class ProductDeleteView(DeleteView):
    model = Product
    template_name = "products/confirm_delete.html"
    success_url = reverse_lazy("products:list")
