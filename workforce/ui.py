"""Look and feel for generated modules, plus the shared 'core' app (layout, menu, dashboard)."""

APPS = '''from django.apps import AppConfig


class @MODEL@Config(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "@APP@"
    verbose_name = "@TITLE@"
    crud_module = True
'''

BASE = '''{% extends "core/base.html" %}
{% block title %}@TITLE@{% endblock %}
'''

LIST = '''{% extends "@APP@/base.html" %}
{% block content %}
<h1>@TITLE@</h1>
<form method="get" class="toolbar">
  <input type="text" name="q" value="{{ q }}" placeholder="Search">
  <button type="submit" class="btn secondary">Search</button>
  <a class="btn" href="{% url "@APP@:create" %}">+ Add new</a>
</form>
<table>
  <thead><tr>@HEADERS@<th></th></tr></thead>
  <tbody>
  {% for item in items %}
    <tr>@CELLS@<td class="actions"><a href="{% url "@APP@:update" item.pk %}">Edit</a> <a class="danger-link" href="{% url "@APP@:delete" item.pk %}">Delete</a></td></tr>
  {% empty %}
    <tr><td colspan="@COLSPAN@">Nothing here yet.</td></tr>
  {% endfor %}
  </tbody>
</table>
{% endblock %}
'''

FORM = '''{% extends "@APP@/base.html" %}
{% block content %}
<h1>{% if object %}Edit{% else %}New{% endif %} @MODEL@</h1>
<form method="post" class="panel">
  {% csrf_token %}
  {{ form.as_p }}
  <button type="submit" class="btn">Save</button>
  <a class="btn secondary" href="{% url "@APP@:list" %}">Cancel</a>
</form>
{% endblock %}
'''

CONFIRM = '''{% extends "@APP@/base.html" %}
{% block content %}
<h1>Delete @MODEL@</h1>
<form method="post" class="panel">
  {% csrf_token %}
  <p>Delete "{{ object }}"? This cannot be undone.</p>
  <button type="submit" class="btn danger">Yes, delete</button>
  <a class="btn secondary" href="{% url "@APP@:list" %}">Cancel</a>
</form>
{% endblock %}
'''

CORE_FILES = {
    "__init__.py": "",
    "templatetags/__init__.py": "",
    "apps.py": '''from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
''',
    "modules.py": '''from django.apps import apps
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
''',
    "views.py": '''from django.shortcuts import render

from .modules import crud_modules


def dashboard(request):
    return render(request, "core/dashboard.html", {"cards": crud_modules(counts=True)})
''',
    "urls.py": '''from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
]
''',
    "templatetags/core_tags.py": '''from django import template

from core.modules import crud_modules

register = template.Library()


@register.inclusion_tag("core/menu.html")
def crud_menu():
    return {"items": crud_modules()}
''',
    "templates/core/menu.html": '''{% for item in items %}<a href="{{ item.url }}">{{ item.title }}</a>
{% endfor %}''',
    "templates/core/dashboard.html": '''{% extends "core/base.html" %}
{% block title %}Dashboard{% endblock %}
{% block content %}
<h1>Dashboard</h1>
<div class="cards">
  {% for card in cards %}
  <a class="card" href="{{ card.url }}">
    <span class="num">{{ card.count }}</span>
    <span class="label">{{ card.title }}</span>
  </a>
  {% empty %}
  <p>No modules yet. Create one with: ./wf make crud Product name:str price:decimal</p>
  {% endfor %}
</div>
{% endblock %}
''',
    "tests.py": '''from django.apps import apps
from django.test import TestCase


class DashboardTests(TestCase):
    def test_dashboard_loads(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dashboard")

    def test_every_module_is_listed(self):
        response = self.client.get("/")
        for cfg in apps.get_app_configs():
            if getattr(cfg, "crud_module", False):
                self.assertContains(response, cfg.verbose_name)
''',
    "templates/core/base.html": '''{% load core_tags %}<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}CRM{% endblock %}</title>
  <style>
    :root { --bg:#f4f6fb; --side:#1f2937; --accent:#4f46e5; --text:#1f2937; --muted:#6b7280; --line:#e5e7eb; }
    * { box-sizing: border-box; }
    body { margin:0; display:flex; min-height:100vh; background:var(--bg); color:var(--text);
           font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
    .side { width:220px; flex-shrink:0; background:var(--side); padding:1.2rem 0; }
    .brand { color:#fff; font-weight:700; font-size:1.2rem; padding:0 1.2rem 1rem; }
    .side a { display:block; color:#cbd5e1; padding:.6rem 1.2rem; text-decoration:none; }
    .side a:hover { background:#374151; color:#fff; }
    .main { flex:1; padding:2rem; max-width:1100px; }
    h1 { margin:0 0 1.2rem; font-size:1.6rem; }
    .toolbar { display:flex; gap:.5rem; align-items:center; margin-bottom:1rem; flex-wrap:wrap; }
    input[type=text], input[type=number], input[type=email], input[type=date], textarea, select {
      padding:.5rem .7rem; border:1px solid var(--line); border-radius:6px; font:inherit; background:#fff; }
    button, .btn { display:inline-block; background:var(--accent); color:#fff; border:0; border-radius:6px;
                   padding:.5rem 1rem; font:inherit; cursor:pointer; text-decoration:none; }
    .btn.secondary { background:#e5e7eb; color:var(--text); }
    .btn.danger { background:#dc2626; }
    table { width:100%; border-collapse:collapse; background:#fff; border-radius:8px; overflow:hidden;
            box-shadow:0 1px 3px rgba(0,0,0,.08); }
    th, td { padding:.7rem 1rem; text-align:left; border-bottom:1px solid var(--line); }
    th { background:#f9fafb; font-size:.78rem; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); }
    tr:last-child td { border-bottom:0; }
    td a { color:var(--accent); text-decoration:none; margin-right:.6rem; }
    td a.danger-link { color:#dc2626; }
    .panel { background:#fff; padding:1.5rem; border-radius:8px; box-shadow:0 1px 3px rgba(0,0,0,.08); max-width:560px; }
    .panel p { margin:0 0 .9rem; }
    .panel label { display:block; font-weight:600; margin-bottom:.25rem; }
    .panel input[type=text], .panel input[type=number], .panel input[type=email], .panel input[type=date], .panel textarea { width:100%; }
    .cards { display:grid; grid-template-columns:repeat(auto-fill, minmax(180px, 1fr)); gap:1rem; }
    .card { display:block; background:#fff; padding:1.2rem; border-radius:10px; color:inherit;
            text-decoration:none; box-shadow:0 1px 3px rgba(0,0,0,.08); }
    .card:hover { box-shadow:0 4px 12px rgba(0,0,0,.12); }
    .card .num { display:block; font-size:2rem; font-weight:700; color:var(--accent); }
    .card .label { color:var(--muted); }
    @media (max-width:700px) { body { flex-direction:column; } .side { width:100%; } }
  </style>
</head>
<body>
  <aside class="side">
    <div class="brand">My CRM</div>
    <a href="{% url 'core:dashboard' %}">Dashboard</a>
    {% crud_menu %}
    <a href="/admin/">Admin</a>
  </aside>
  <main class="main">
    {% block content %}{% endblock %}
  </main>
</body>
</html>
''',
}


# Newer look: new projects get it automatically, existing ones via ./wf make restyle
from .theme import CORE_OVERRIDES  # noqa: E402

CORE_FILES.update(CORE_OVERRIDES)
APPS = APPS.replace("    crud_module = True\n", '    crud_module = True\n    icon = "📦"\n')


CONFIRM = CONFIRM.replace(
    '<p>Delete "{{ object }}"? This cannot be undone.</p>',
    '<p>Delete "{{ object }}"? This cannot be undone.</p>\n'
    '  {% if protected %}<p class="errorlist">Cannot delete: other records still use this one.</p>{% endif %}')
