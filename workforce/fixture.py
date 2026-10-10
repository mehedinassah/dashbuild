"""A tiny Django project used by the benchmark and the tests."""
import json
import subprocess
import sys
from pathlib import Path

FILES = {
    "manage.py": '''import os, sys
if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)
''',
    "config/__init__.py": "",
    "config/settings.py": '''from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = "bench"
DEBUG = True
INSTALLED_APPS = ["django.contrib.contenttypes", "django.contrib.auth", "sales"]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
''',
    "sales/__init__.py": "",
    "sales/models.py": '''from django.db import models


class Product(models.Model):
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.IntegerField(default=0)


class Sale(models.Model):
    customer_name = models.CharField(max_length=100)


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.IntegerField(default=1)
''',
    "sales/tests.py": '''from django.test import TestCase
from .models import Product


class SmokeTest(TestCase):
    def test_product_saves(self):
        p = Product.objects.create(name="x", price="1.00", stock=1)
        self.assertEqual(Product.objects.count(), 1)
        self.assertEqual(p.name, "x")
''',
    ".workforce.json": json.dumps({"test_cmd": ["python", "manage.py", "test"], "commands": []}),
    ".gitignore": "db.sqlite3\n__pycache__/\n*.pyc\n",
}

BENCH_CARDS = [
    {"app": "sales", "kind": "model", "class": "SaleItem", "name": "line_total",
     "spec": "line_total returns the price of the product multiplied by the quantity, as a Decimal."},
    {"app": "sales", "kind": "model", "class": "Product", "name": "in_stock",
     "spec": "in_stock returns True when stock is greater than zero, otherwise False."},
    {"app": "sales", "kind": "model", "class": "Sale", "name": "compute_total",
     "spec": "compute_total returns the sum of line_total over all items of this sale "
             "(0 when the sale has no items)."},
    {"app": "sales", "kind": "service", "class": "", "name": "reduce_stock",
     "spec": "reduce_stock(product, quantity) lowers product.stock by quantity and saves the product; "
             "if stock is less than quantity it raises ValueError and changes nothing."},
]


def make_project(path, git=True):
    path = Path(path)
    for rel, text in FILES.items():
        p = path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    subprocess.run([sys.executable, "manage.py", "makemigrations", "sales"], cwd=path,
                   capture_output=True, check=True)
    if git:
        for cmd in (["init", "-q"], ["add", "-A"],
                    ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init"]):
            subprocess.run(["git", *cmd], cwd=path, capture_output=True, check=True)
    return path
