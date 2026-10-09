from django.db.models import ProtectedError, Q
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from .models import Sale

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
