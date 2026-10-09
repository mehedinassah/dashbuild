"""Deterministic CRUD module generator for the Django project. No AI involved.

Usage: ./wf make crud Product name:str price:decimal stock:int
Field types: str, text, int, decimal, bool, date, email. The first field must be str.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .ui import APPS, BASE, CONFIRM, CORE_FILES, FORM, LIST

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


def model_field(kind, extra):
    if kind == "fk":
        return f'models.ForeignKey("{plural(extra.lower())}.{extra}", on_delete=models.PROTECT)'
    base = FIELD_TYPES[kind]
    return base[:-1] + ", unique=True)" if extra == "unique" else base


def parse_fields(specs):
    """Each spec is name:type, name:type:unique or name:fk:ModelName."""
    fields = []
    for spec in specs:
        parts = spec.split(":")
        if len(parts) > 3:
            raise SystemExit(f"Too many ':' in {spec!r}")
        name = parts[0]
        kind = parts[1] if len(parts) > 1 and parts[1] else "str"
        extra = parts[2] if len(parts) > 2 else ""
        if not re.fullmatch(r"[a-z][a-z0-9_]*", name) or name in RESERVED:
            raise SystemExit(f"Bad field name {name!r}: use lowercase letters, digits and underscores.")
        if kind == "fk":
            if not re.fullmatch(r"[A-Z][A-Za-z0-9]*", extra):
                raise SystemExit(f"{name}: write a link as {name}:fk:ModelName")
        elif kind not in FIELD_TYPES:
            raise SystemExit(f"Bad type {kind!r} for {name}. Types: {', '.join(FIELD_TYPES)}, fk")
        elif extra not in ("", "unique"):
            raise SystemExit(f"Unknown option {extra!r} for {name}. The only option is unique.")
        if any(name == f[0] for f in fields):
            raise SystemExit(f"Duplicate field: {name}")
        fields.append((name, kind, extra))
    if not fields:
        raise SystemExit("Give at least one field, for example name:str")
    if fields[0][1] != "str":
        raise SystemExit("The first field must be a str field: it is the display name and the main search field.")
    return fields


def build_values(model, fields):
    app = plural(model.lower())
    quote = lambda names: ", ".join(f'"{n}"' for n in names)
    for n, k, e in fields:
        if k == "fk" and e == model:
            raise SystemExit(f"{n}: a model cannot point at itself ({model}).")
    search = [n for n, k, e in fields if k in ("str", "text", "email")]
    return {
        "APP": app,
        "MODEL": model,
        "TITLE": app.replace("_", " ").title(),
        "LABEL": fields[0][0],
        "FIELDS": quote([f[0] for f in fields]),
        "SEARCH": quote(search),
        "MODEL_FIELDS": "\n".join(f"    {n} = {model_field(k, e)}" for n, k, e in fields),
        "HEADERS": "".join(f"<th>{n.replace('_', ' ').title()}</th>" for n, _, _ in fields),
        "CELLS": "".join(f"<td>{{{{ item.{n} }}}}</td>" for n, _, _ in fields),
        "COLSPAN": str(len(fields) + 1),
    }


def render(text, values):
    for key, val in values.items():
        text = text.replace("@" + key + "@", val)
    return text




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

VIEWS = '''from django.db.models import ProtectedError, Q
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

    def form_valid(self, form):
        try:
            return super().form_valid(form)
        except ProtectedError:
            context = self.get_context_data(object=self.object, protected=True)
            return self.render_to_response(context)
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

from core.factories import make_instance, post_data

from .models import @MODEL@

LABEL = "@LABEL@"


class @MODEL@CrudTests(TestCase):
    def test_str_is_the_first_field(self):
        item = make_instance(@MODEL@)
        self.assertEqual(str(item), str(getattr(item, LABEL)))

    def test_list_page_shows_items(self):
        item = make_instance(@MODEL@)
        response = self.client.get(reverse("@APP@:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, getattr(item, LABEL))

    def test_search_filters_items(self):
        make_instance(@MODEL@, **{LABEL: "Alpha thing"})
        make_instance(@MODEL@, **{LABEL: "Beta thing"})
        response = self.client.get(reverse("@APP@:list"), {"q": "alp"})
        self.assertContains(response, "Alpha thing")
        self.assertNotContains(response, "Beta thing")

    def test_create(self):
        response = self.client.post(reverse("@APP@:create"), post_data(@MODEL@))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(@MODEL@.objects.count(), 1)

    def test_update(self):
        item = make_instance(@MODEL@)
        data = post_data(@MODEL@, **{LABEL: "Changed"})
        response = self.client.post(reverse("@APP@:update", args=[item.pk]), data)
        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(str(item), "Changed")

    def test_delete(self):
        item = make_instance(@MODEL@)
        response = self.client.post(reverse("@APP@:delete", args=[item.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(@MODEL@.objects.count(), 0)
'''

FACTORIES = '''"""Helpers for generated tests: build valid sample records for any model."""
import itertools
from decimal import Decimal

from django.db import models

_counter = itertools.count(1)


def sample_value(field, n):
    if isinstance(field, models.ForeignKey):
        return make_instance(field.related_model)
    if isinstance(field, models.BooleanField):
        return True
    if isinstance(field, models.DecimalField):
        return Decimal(n)
    if isinstance(field, models.IntegerField):
        return n
    if isinstance(field, models.DateField):
        return "2026-01-15"
    if isinstance(field, models.EmailField):
        return f"sample{n}@example.com"
    if isinstance(field, models.TextField):
        return f"Some text {n}"
    return f"Sample {n}"


def make_instance(model, **overrides):
    n = next(_counter)
    data = {}
    for field in model._meta.concrete_fields:
        if not field.primary_key:
            data[field.name] = sample_value(field, n)
    data.update(overrides)
    return model.objects.create(**data)


def post_data(model, **overrides):
    n = next(_counter)
    data = {}
    for field in model._meta.concrete_fields:
        if field.primary_key:
            continue
        if isinstance(field, models.ForeignKey):
            data[field.name] = make_instance(field.related_model).pk
        elif isinstance(field, models.BooleanField):
            data[field.name] = "on"
        else:
            data[field.name] = sample_value(field, n)
    data.update(overrides)
    return data
'''


def add_test_helpers(ws):
    target = Path(ws) / "core" / "factories.py"
    if not target.exists():
        target.write_text(FACTORIES)


def check_fk_targets(ws, fields):
    for name, kind, extra in fields:
        if kind == "fk" and not (Path(ws) / plural(extra.lower()) / "models.py").exists():
            raise SystemExit(f"{name}: the module {extra} does not exist yet. Generate it first.")



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
    fields = parse_fields(specs)
    values = build_values(model, fields)
    check_fk_targets(ws, fields)
    ensure_core(ws)
    add_test_helpers(ws)
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
    if argv and argv[0] == "restyle":
        restyle(ws)
        return
    if len(argv) < 3 or argv[0] not in ("crud", "refresh"):
        raise SystemExit("usage: ./wf make crud|refresh ModelName name:str price:decimal ...")
    (generate if argv[0] == "crud" else refresh)(ws, argv[1], argv[2:])


def ensure_core(ws):
    """Create the shared 'core' app (layout, menu, dashboard) once, and wire it in."""
    ws = Path(ws).resolve()
    if (ws / "core").exists():
        return
    settings_p, urls_p = ws / "config" / "settings.py", ws / "config" / "urls.py"
    old_settings, old_urls = settings_p.read_text(), urls_p.read_text()
    try:
        for rel, text in CORE_FILES.items():
            target = ws / "core" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
        settings_p.write_text(insert_entry(old_settings, r"INSTALLED_APPS\s*=\s*\[(.*?)\n\]",
                                           "'core'", "INSTALLED_APPS in config/settings.py"))
        new_urls = insert_entry(old_urls, r"urlpatterns\s*=\s*\[(.*?)\n\]",
                                "path('', include('core.urls'))", "urlpatterns in config/urls.py")
        urls_p.write_text(fix_include_import(new_urls))
        for label, args in (("check", ["check"]), ("core tests", ["test", "core"])):
            code, out = run(ws, *args)
            if code != 0:
                raise SystemExit(label + " failed:\n" + out[-1500:])
    except SystemExit:
        shutil.rmtree(ws / "core", ignore_errors=True)
        settings_p.write_text(old_settings)
        urls_p.write_text(old_urls)
        raise
    print("Created the shared 'core' app (layout, menu, dashboard at /).")


def refresh(ws, model, specs):
    """Re-render the look (templates and app config) of an existing generated module."""
    ws = Path(ws).resolve()
    fields = parse_fields(specs)
    values = build_values(model, fields)
    check_fk_targets(ws, fields)
    app = values["APP"]
    app_dir = ws / app
    if not app_dir.exists():
        raise SystemExit(f"{app}/ does not exist. Use 'crud' to create it.")
    ensure_core(ws)
    add_test_helpers(ws)
    files = {
        "apps.py": APPS,
        f"templates/{app}/base.html": BASE,
        f"templates/{app}/list.html": LIST,
        f"templates/{app}/form.html": FORM,
        f"templates/{app}/confirm_delete.html": CONFIRM,
    }
    old = {rel: ((app_dir / rel).read_text() if (app_dir / rel).exists() else None) for rel in files}
    for rel, text in files.items():
        target = app_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render(text, values))
    code, out = run(ws, "test", app)
    if code != 0:
        for rel, text in old.items():
            if text is None:
                (app_dir / rel).unlink(missing_ok=True)
            else:
                (app_dir / rel).write_text(text)
        print("FAILED. The old files were restored.\n" + out[-2500:])
        raise SystemExit(1)
    print(f"Refreshed {app}/ (look and menu entry). Tests passed.")


def restyle(ws):
    """Rewrite the shared layout, menu and dashboard of an existing project."""
    ws = Path(ws).resolve()
    if not (ws / "core").exists():
        raise SystemExit("No core app yet. Generate a module first: ./wf make crud ...")
    from .theme import CORE_OVERRIDES
    old = {}
    for rel, text in CORE_OVERRIDES.items():
        target = ws / "core" / rel
        old[rel] = target.read_text() if target.exists() else None
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    code, out = run(ws, "test")
    if code != 0:
        for rel, text in old.items():
            target = ws / "core" / rel
            if text is None:
                target.unlink(missing_ok=True)
            else:
                target.write_text(text)
        print("FAILED. The old files were restored.\n" + out[-2500:])
        raise SystemExit(1)
    print("Restyled core (layout, menu, dashboard). All project tests passed.")


if __name__ == "__main__":
    main(sys.argv[1:])
