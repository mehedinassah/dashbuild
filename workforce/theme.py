"""Look of the shared 'core' app. Edit this file, then run: ./wf make restyle"""

MODULES_PY = '''from django.apps import apps
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
'''

VIEWS_PY = '''from django.shortcuts import render

from .modules import crud_modules


def dashboard(request):
    cards = crud_modules(counts=True, recent=5, path=request.path)
    total = sum(card.get("count", 0) for card in cards)
    return render(request, "core/dashboard.html", {"cards": cards, "total": total})
'''

TAGS_PY = '''from django import template

from core.modules import crud_modules

register = template.Library()


@register.inclusion_tag("core/menu.html", takes_context=True)
def crud_menu(context):
    request = context.get("request")
    path = request.path if request else ""
    return {"items": crud_modules(path=path)}
'''

MENU_HTML = '''{% for item in items %}<a href="{{ item.url }}"{% if item.active %} class="active"{% endif %}><span class="ico">{{ item.icon }}</span>{{ item.title }}</a>
{% endfor %}'''

DASHBOARD_HTML = '''{% extends "core/base.html" %}
{% block title %}Dashboard{% endblock %}
{% block content %}
<div class="head">
  <h1>Dashboard</h1>
  <span class="muted">{{ total }} records across {{ cards|length }} modules</span>
</div>
<div class="cards">
  {% for card in cards %}
  <a class="card" href="{{ card.url }}">
    <span class="ico big">{{ card.icon }}</span>
    <span class="num">{{ card.count }}</span>
    <span class="label">{{ card.title }}</span>
  </a>
  {% empty %}
  <p>No modules yet. Create one with: ./wf make crud Product name:str price:decimal</p>
  {% endfor %}
</div>
<div class="grid2">
  {% for card in cards %}
  <section class="panel wide">
    <h2>{{ card.icon }} Recent {{ card.title }}</h2>
    {% if card.recent %}
    <ul class="recent">{% for r in card.recent %}<li>{{ r }}</li>{% endfor %}</ul>
    {% else %}
    <p class="muted">Nothing yet.</p>
    {% endif %}
    <a class="more" href="{{ card.url }}">View all →</a>
  </section>
  {% endfor %}
</div>
{% endblock %}
'''

BASE_HTML = '''{% load core_tags %}<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}My CRM{% endblock %}</title>
  <style>
    :root{--bg:#f5f7fb;--surface:#ffffff;--side:#111827;--side-hover:#1f2937;--accent:#6366f1;--accent2:#8b5cf6;--text:#111827;--muted:#6b7280;--line:#e5e7eb;--danger:#dc2626;--shadow:0 1px 2px rgba(16,24,40,.06),0 4px 14px rgba(16,24,40,.06)}
    @media (prefers-color-scheme:dark){:root{--bg:#0b1020;--surface:#141a2e;--side:#0a0f1e;--side-hover:#1a2140;--text:#e5e7eb;--muted:#9ca3af;--line:#232b45;--shadow:0 1px 2px rgba(0,0,0,.4)}}
    *{box-sizing:border-box}
    body{margin:0;display:flex;min-height:100vh;background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;line-height:1.5}
    .side{width:240px;flex-shrink:0;background:var(--side);padding:1.4rem .8rem;position:sticky;top:0;height:100vh;display:flex;flex-direction:column;gap:.15rem}
    .brand{font-weight:800;font-size:1.3rem;padding:.2rem .8rem 1.2rem;letter-spacing:-.01em}
    .brand span{background:linear-gradient(135deg,#818cf8,#c084fc);-webkit-background-clip:text;background-clip:text;color:transparent}
    .side a{display:flex;align-items:center;gap:.7rem;color:#9ca3af;padding:.6rem .8rem;border-radius:8px;text-decoration:none;font-weight:500}
    .side a:hover{background:var(--side-hover);color:#fff}
    .side a.active{background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff}
    .spacer{flex:1}
    .ico{width:1.5rem;text-align:center}
    .main{flex:1;padding:2rem 2.5rem;min-width:0}
    .head{display:flex;align-items:baseline;gap:1rem;margin-bottom:1.5rem;flex-wrap:wrap}
    h1{margin:0 0 1.2rem;font-size:1.7rem;letter-spacing:-.02em}
    .head h1{margin:0}
    h2{margin:0 0 .8rem;font-size:1.05rem}
    .muted{color:var(--muted)}
    .toolbar{display:flex;gap:.5rem;align-items:center;margin-bottom:1.2rem;flex-wrap:wrap}
    input[type=text],input[type=number],input[type=email],input[type=date],textarea,select{padding:.55rem .75rem;border:1px solid var(--line);border-radius:8px;font:inherit;background:var(--surface);color:var(--text)}
    input:focus,textarea:focus,select:focus{outline:2px solid var(--accent);outline-offset:1px}
    button,.btn{display:inline-block;background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff;border:0;border-radius:8px;padding:.55rem 1.1rem;font:inherit;font-weight:600;cursor:pointer;text-decoration:none}
    button:hover,.btn:hover{filter:brightness(1.08)}
    .btn.secondary{background:var(--line);color:var(--text)}
    .btn.danger{background:var(--danger)}
    table{width:100%;border-collapse:separate;border-spacing:0;background:var(--surface);border-radius:12px;overflow:hidden;box-shadow:var(--shadow)}
    th,td{padding:.8rem 1rem;text-align:left;border-bottom:1px solid var(--line)}
    th{font-size:.72rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
    tbody tr:hover{background:rgba(99,102,241,.07)}
    tr:last-child td{border-bottom:0}
    td.actions{white-space:nowrap;text-align:right}
    td a{color:var(--accent);text-decoration:none;font-weight:600;margin-left:.9rem}
    td a.danger-link{color:var(--danger)}
    .panel{background:var(--surface);padding:1.5rem;border-radius:12px;box-shadow:var(--shadow);max-width:560px}
    .panel.wide{max-width:none}
    .panel p{margin:0 0 .9rem}
    .panel label{display:block;font-weight:600;margin-bottom:.25rem}
    .panel input[type=text],.panel input[type=number],.panel input[type=email],.panel input[type=date],.panel textarea,.panel select{width:100%}
    .errorlist{color:var(--danger);list-style:none;padding:0;margin:0 0 .4rem}
    .cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:1rem;margin-bottom:1.5rem}
    .card{display:block;position:relative;background:var(--surface);padding:1.3rem;border-radius:14px;color:inherit;text-decoration:none;box-shadow:var(--shadow);transition:transform .15s,box-shadow .15s}
    .card:hover{transform:translateY(-2px);box-shadow:0 8px 24px rgba(99,102,241,.2)}
    .card .big{position:absolute;right:1rem;top:1rem;font-size:1.6rem}
    .card .num{display:block;font-size:2.2rem;font-weight:800;color:var(--accent);line-height:1.1}
    .card .label{color:var(--muted)}
    .grid2{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:1rem}
    .recent{list-style:none;margin:0 0 .8rem;padding:0}
    .recent li{padding:.45rem 0;border-bottom:1px solid var(--line)}
    .recent li:last-child{border-bottom:0}
    .more{color:var(--accent);text-decoration:none;font-weight:600}
    @media (max-width:760px){body{flex-direction:column}.side{width:100%;height:auto;position:static;flex-direction:row;flex-wrap:wrap}.main{padding:1.2rem}}
  </style>
</head>
<body>
  <aside class="side">
    <div class="brand"><span>My CRM</span></div>
    <a href="{% url 'core:dashboard' %}"{% if request.path == '/' %} class="active"{% endif %}><span class="ico">🏠</span>Dashboard</a>
    {% crud_menu %}
    <div class="spacer"></div>
    <a href="/admin/"><span class="ico">⚙️</span>Admin</a>
  </aside>
  <main class="main">
    {% block content %}{% endblock %}
  </main>
</body>
</html>
'''

CORE_OVERRIDES = {
    "modules.py": MODULES_PY,
    "views.py": VIEWS_PY,
    "templatetags/core_tags.py": TAGS_PY,
    "templates/core/menu.html": MENU_HTML,
    "templates/core/dashboard.html": DASHBOARD_HTML,
    "templates/core/base.html": BASE_HTML,
}
