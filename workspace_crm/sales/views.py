from django.db.models import ProtectedError, Q
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from .models import Sale
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST
from sales.services import confirm_sale
from sales.services import cancel_sale

FIELDS = ["number", "date", "customer", "total"]
SEARCH_FIELDS = ["number"]


class SaleListView(ListView):
    model = Sale
    template_name = "sales/list.html"
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


class SaleCreateView(CreateView):
    model = Sale
    fields = FIELDS
    template_name = "sales/form.html"
    success_url = reverse_lazy("sales:list")


class SaleUpdateView(UpdateView):
    model = Sale
    fields = FIELDS
    template_name = "sales/form.html"
    success_url = reverse_lazy("sales:list")


class SaleDeleteView(DeleteView):
    model = Sale
    template_name = "sales/confirm_delete.html"
    success_url = reverse_lazy("sales:list")

    def form_valid(self, form):
        try:
            return super().form_valid(form)
        except ProtectedError:
            context = self.get_context_data(object=self.object, protected=True)
            return self.render_to_response(context)


@require_POST
def confirm_sale_view(request, pk):
    sale = get_object_or_404(Sale, pk=pk)

    try:
        confirm_sale(sale)
        messages.success(request, 'Sale confirmed.')
    except ValueError as e:
        messages.error(request, str(e))

    return redirect('sales:list')


@require_POST
def cancel_sale_view(request, pk):
    sale = get_object_or_404(Sale, pk=pk)
    try:
        cancel_sale(sale)
        messages.success(request, 'Sale cancelled.')
    except ValueError as e:
        messages.error(request, str(e))
    return redirect('sales:list')
