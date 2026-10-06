from django.shortcuts import render

from .models import Customer


def customer_list(request):
    q = request.GET.get('q', '').strip()
    customers = Customer.objects.order_by('name')
    if q:
        customers = customers.filter(name__icontains=q)
    return render(request, 'customers/customer_list.html', {'customers': customers, 'q': q})
