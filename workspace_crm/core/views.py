from django.shortcuts import render

from .modules import crud_modules


def dashboard(request):
    return render(request, "core/dashboard.html", {"cards": crud_modules(counts=True)})
