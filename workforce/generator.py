"""Deterministic CRUD module generator for the Django project. No AI involved.

Usage: ./wf make crud Product name:str price:decimal stock:int
Field types: str, text, int, decimal, bool, date, email. The first field must be str.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

FIELD_TYPES = {
    "str": "models.CharField(max_length=200)",
    "text": "models.TextField(blank=True)",
    "int": "models.IntegerField(default=0)",
    "decimal": "models.DecimalField(max_digits=10, decimal_places=2, default=0)",
    "bool": "models.BooleanField(default=False)",
    "date": "models.DateField(null=True, blank=True)",
    "email": "models.EmailField()",
}
PY_SAMPLE = {"str": '"Sample"', "text": '"Some text"', "int": "5", "decimal": '"9.99"',
             "bool": "True", "date": '"2026-01-15"', "email": '"sample@example.com"'}
POST_SAMPLE = {"str": "Sample", "text": "Some text", "int": "5", "decimal": "9.99",
               "bool": "on", "date": "2026-01-15", "email": "sample@example.com"}
RESERVED = {"id", "pk", "objects"}


def plural(word):
    if word.endswith("y") and len(word) > 1 and word[-2] not in "aeiou":
        return word[:-1] + "ies"
    if word.endswith(("s", "x", "ch", "sh")):
        return word + "es"
    return word + "s"


def parse_fields(specs):
    fields = []
    for spec in specs:
        name, _, kind = spec.partition(":")
        kind = kind or "str"
        if not re.fullmatch(r"[a-z][a-z0-9_]*", name) or name in RESERVED:
            raise SystemExit(f"Bad field name {name!r}: use lowercase letters, digits and underscores.")
        if kind not in FIELD_TYPES:
            raise SystemExit(f"Bad type {kind!r} for {name}. Types: {', '.join(FIELD_TYPES)}")
        if any(name == n for n, _ in fields):
            raise SystemExit(f"Duplicate field: {name}")
        fields.append((name, kind))
    if not fields:
        raise SystemExit("Give at least one field, for example name:str")
    if fields[0][1] != "str":
        raise SystemExit("The first field must be a str field: it is the display name and the main search field.")
    return fields


def render(text, values):
    for key, val in values.items():
        text = text.replace("@" + key + "@", val)
    return text


def build_values(model, fields):
    app = plural(model.lower())
    quote = lambda names: ", ".join(f'"{n}"' for n in names)
    search = [n for n, k in fields if k in ("str", "text", "email")]
    return {
        "APP": app,
        "MODEL": model,
        "TITLE": app.replace("_", " ").title(),
        "LABEL": fields[0][0],
        "FIELDS": quote([n for n, _ in fields]),
        "SEARCH": quote(search),
        "MODEL_FIELDS": "\n".join(f"    {n} = {FIELD_TYPES[k]}" for n, k in fields),
        "HEADERS": "".join(f"<th>{n.replace('_', ' ').title()}</th>" for n, _ in fields),
        "CELLS": "".join(f"<td>{{{{ item.{n} }}}}</td>" for n, _ in fields),
        "COLSPAN": str(len(fields) + 1),
        "SAMPLE": "\n".join(f'    "{n}": {PY_SAMPLE[k]},' for n, k in fields),
        "POST": "\n".join(f'    "{n}": "{POST_SAMPLE[k]}",' for n, k in fields),
    }


APPS = '''from django.apps import AppConfig


class @MODEL@Config(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "@APP@"
'''

MODELS = '''from django.db import models


class @MODEL@(models.Model):
@MODEL_FIELDS@

    class Meta:
        ordering = ["@LABEL@"]

    def __str__(self):
        return str(self.@LABEL@)
'''

ADMIN = '''from django.contrib import admin

from .models import @MODEL@


@admin.register(@MODEL@)
class @MODEL@Admin(admin.ModelAdmin):
    list_display = (@FIELDS@,)
    search_fields = (@SEARCH@,)
'''

VIEWS = '''from django.db.models import Q
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from .models import @MODEL@

FIELDS = [@FIELDS@]
SEARCH_FIELDS = [@SEARCH@]


class @MODEL@ListView(ListView):
    model = @MODEL@
    template_name = "@APP@/list.html"
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


class @MODEL@CreateView(CreateView):
    model = @MODEL@
    fields = FIELDS
    template_name = "@APP@/form.html"
    success_url = reverse_lazy("@APP@:list")


class @MODEL@UpdateView(UpdateView):
    model = @MODEL@
    fields = FIELDS
    template_name = "@APP@/form.html"
    success_url = reverse_lazy("@APP@:list")


class @MODEL@DeleteView(DeleteView):
    model = @MODEL@
    template_name = "@APP@/confirm_delete.html"
    success_url = reverse_lazy("@APP@:list")
'''

URLS = '''from django.urls import path

from . import views

app_name = "@APP@"

urlpatterns = [
    path("", views.@MODEL@ListView.as_view(), name="list"),
    path("new/", views.@MODEL@CreateView.as_view(), name="create"),
    path("<int:pk>/edit/", views.@MODEL@UpdateView.as_view(), name="update"),
    path("<int:pk>/delete/", views.@MODEL@DeleteView.as_view(), name="delete"),
]
'''


TESTS = '''from django.test import TestCase
from django.urls import reverse

from .models import @MODEL@

LABEL = "@LABEL@"

SAMPLE = {
@SAMPLE@
}

POST = {
@POST@
}


class @MODEL@CrudTests(TestCase):
    def make(self, **extra):
        data = dict(SAMPLE)
        data.update(extra)
        return @MODEL@.objects.create(**data)

    def test_str_is_the_first_field(self):
        item = self.make()
        self.assertEqual(str(item), SAMPLE[LABEL])

    def test_list_page_shows_items(self):
        self.make()
        response = self.client.get(reverse("@APP@:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, SAMPLE[LABEL])

    def test_search_filters_items(self):
        self.make(**{LABEL: "Alpha thing"})
        self.make(**{LABEL: "Beta thing"})
        response = self.client.get(reverse("@APP@:list"), {"q": "alp"})
        self.assertContains(response, "Alpha thing")
        self.assertNotContains(response, "Beta thing")

    def test_create(self):
        response = self.client.post(reverse("@APP@:create"), POST)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(@MODEL@.objects.count(), 1)

    def test_update(self):
        item = self.make()
        data = dict(POST)
        data[LABEL] = "Changed"
        response = self.client.post(reverse("@APP@:update", args=[item.pk]), data)
        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(str(item), "Changed")

    def test_delete(self):
        item = self.make()
        response = self.client.post(reverse("@APP@:delete", args=[item.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(@MODEL@.objects.count(), 0)
'''

BASE = '''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>@TITLE@</title>
  <style>
    body { font-family: sans-serif; margin: 2rem; }
    table { border-collapse: collapse; margin-top: 1rem; }
    th, td { border: 1px solid #ccc; padding: 0.4rem 0.8rem; text-align: left; }
  </style>
</head>
<body>
  {% block content %}{% endblock %}
</body>
</html>
'''

LIST = '''{% extends "@APP@/base.html" %}
{% block content %}
<h1>@TITLE@</h1>
<form method="get">
  <input type="text" name="q" value="{{ q }}" placeholder="Search">
  <button type="submit">Search</button>
  <a href="{% url "@APP@:create" %}">Add new</a>
</form>
<table>
  <thead><tr>@HEADERS@<th></th></tr></thead>
  <tbody>
  {% for item in items %}
    <tr>@CELLS@<td><a href="{% url "@APP@:update" item.pk %}">Edit</a> <a href="{% url "@APP@:delete" item.pk %}">Delete</a></td></tr>
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
<form method="post">
  {% csrf_token %}
  {{ form.as_p }}
  <button type="submit">Save</button>
  <a href="{% url "@APP@:list" %}">Cancel</a>
</form>
{% endblock %}
'''

CONFIRM = '''{% extends "@APP@/base.html" %}
{% block content %}
<h1>Delete @MODEL@</h1>
<p>Delete "{{ object }}"? This cannot be undone.</p>
<form method="post">
  {% csrf_token %}
  <button type="submit">Yes, delete</button>
  <a href="{% url "@APP@:list" %}">Cancel</a>
</form>
{% endblock %}
'''


def insert_entry(text, pattern, entry, what):
    m = re.search(pattern, text, re.S)
    if not m:
        raise SystemExit(f"Could not find {what}")
    end = m.start(1) + len(m.group(1).rstrip())
    comma = "" if text[:end].endswith((",", "[")) else ","
    return text[:end] + comma + "\n    " + entry + "," + text[end:]


def fix_include_import(text):
    imp = re.search(r"^from django\.urls import (.+)$", text, re.M)
    if imp and "include" not in imp.group(1):
        names = sorted({n.strip() for n in imp.group(1).split(",")} | {"include"})
        text = text.replace(imp.group(0), "from django.urls import " + ", ".join(names), 1)
    return text


def run(ws, *args):
    r = subprocess.run([sys.executable, "manage.py", *args], cwd=ws,
                       capture_output=True, text=True, timeout=300)
    return r.returncode, r.stdout + r.stderr


def generate(ws, model, specs):
    ws = Path(ws).resolve()
    if not (ws / "manage.py").exists():
        raise SystemExit(f"{ws} is not a Django project (no manage.py).")
    if not re.fullmatch(r"[A-Z][A-Za-z0-9]*", model):
        raise SystemExit("Model name must be CamelCase, for example Product or OrderItem.")
    values = build_values(model, parse_fields(specs))
    app = values["APP"]
    app_dir = ws / app
    settings_p, urls_p = ws / "config" / "settings.py", ws / "config" / "urls.py"
    old_settings, old_urls = settings_p.read_text(), urls_p.read_text()
    if app_dir.exists() or f"'{app}'" in old_settings or f"{app}.urls" in old_urls:
        raise SystemExit(f"'{app}' already exists or is already registered. Nothing was changed.")

    def rollback(msg):
        shutil.rmtree(app_dir, ignore_errors=True)
        settings_p.write_text(old_settings)
        urls_p.write_text(old_urls)
        print("FAILED. Everything was rolled back.\n" + msg)
        raise SystemExit(1)

    files = {
        "__init__.py": "", "migrations/__init__.py": "",
        "apps.py": APPS, "models.py": MODELS, "admin.py": ADMIN, "views.py": VIEWS,
        "urls.py": URLS, "tests.py": TESTS,
        f"templates/{app}/base.html": BASE, f"templates/{app}/list.html": LIST,
        f"templates/{app}/form.html": FORM, f"templates/{app}/confirm_delete.html": CONFIRM,
    }
    for rel, text in files.items():
        target = app_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render(text, values))
    try:
        settings_p.write_text(insert_entry(old_settings, r"INSTALLED_APPS\s*=\s*\[(.*?)\n\]",
                                           f"'{app}'", "INSTALLED_APPS in config/settings.py"))
        new_urls = insert_entry(old_urls, r"urlpatterns\s*=\s*\[(.*?)\n\]",
                                f"path('{app}/', include('{app}.urls'))", "urlpatterns in config/urls.py")
        urls_p.write_text(fix_include_import(new_urls))
    except SystemExit as e:
        rollback(str(e))
    for label, args in (("makemigrations", ["makemigrations", app]), ("check", ["check"]),
                        ("tests", ["test", app])):
        code, out = run(ws, *args)
        if code != 0:
            rollback(f"{label} failed:\n{out[-2500:]}")
        if label == "tests":
            print(out[-400:])
    print(f"Created {app}/ with model {model}, admin, views, templates and tests. All checks passed.")
    print(f"Next:\n  cd {ws.name} && python manage.py migrate && python manage.py runserver\n"
          f"  open http://localhost:8000/{app}/\n"
          f"  git add -A {ws.name} && git commit -m 'Add {model} module'")


def main(argv):
    root = Path(__file__).resolve().parent.parent
    ws = root / "workspace_crm"
    if argv and argv[0].startswith("--ws="):
        ws = root / argv[0][5:]
        argv = argv[1:]
    if len(argv) < 3 or argv[0] != "crud":
        raise SystemExit("usage: ./wf make crud ModelName name:str price:decimal ...")
    generate(ws, argv[1], argv[2:])


if __name__ == "__main__":
    main(sys.argv[1:])
