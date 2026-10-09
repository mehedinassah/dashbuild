from django.shortcuts import render

from .modules import crud_modules


def dashboard(request):
    cards = crud_modules(counts=True, recent=5, path=request.path)
    total = sum(card.get("count", 0) for card in cards)
    return render(request, "core/dashboard.html", {"cards": cards, "total": total})
