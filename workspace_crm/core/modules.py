from django.apps import apps
from django.urls import NoReverseMatch, reverse


def crud_modules(counts=False, recent=0, path=""):
    """Every app that sets crud_module = True, for the menu and the dashboard."""
    items = []
    for cfg in apps.get_app_configs():
        if not getattr(cfg, "crud_module", False):
            continue
        try:
            url = reverse(getattr(cfg, "list_url", cfg.label + ":list"))
        except NoReverseMatch:
            continue
        item = {
            "title": cfg.verbose_name,
            "url": url,
            "icon": getattr(cfg, "icon", "▦"),
            "active": bool(path) and path.startswith(url),
        }
        if counts or recent:
            model = next(iter(cfg.get_models()), None)
            if model is None:
                item["count"] = 0
            else:
                queryset = model.objects.all()
                item["count"] = queryset.count()
                if recent:
                    item["recent"] = [str(o) for o in queryset.order_by("-pk")[:recent]]
        items.append(item)
    return items
