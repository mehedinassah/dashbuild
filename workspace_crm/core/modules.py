from django.apps import apps
from django.urls import NoReverseMatch, reverse


def crud_modules(counts=False):
    """Every app that sets crud_module = True, for the menu and the dashboard."""
    items = []
    for cfg in apps.get_app_configs():
        if not getattr(cfg, "crud_module", False):
            continue
        try:
            url = reverse(getattr(cfg, "list_url", cfg.label + ":list"))
        except NoReverseMatch:
            continue
        item = {"title": cfg.verbose_name, "url": url}
        if counts:
            model = next(iter(cfg.get_models()), None)
            item["count"] = model.objects.count() if model else 0
        items.append(item)
    return items
