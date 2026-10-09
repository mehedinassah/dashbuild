import subprocess
import sys

import pytest

from workforce.generator import generate, parse_fields, plural


def test_plural():
    assert plural("product") == "products"
    assert plural("category") == "categories"
    assert plural("box") == "boxes"
    assert plural("day") == "days"


def test_parse_fields_errors():
    for bad in (["Name:str"], ["name:weird"], ["price:int"], ["name:str", "name:int"], []):
        with pytest.raises(SystemExit):
            parse_fields(bad)


def test_generate_full_module(tmp_path):
    subprocess.run([sys.executable, "-m", "django", "startproject", "config", str(tmp_path)],
                   check=True, capture_output=True)
    generate(tmp_path, "Product", ["name:str", "price:decimal", "stock:int", "active:bool"])
    assert (tmp_path / "products" / "models.py").exists()
    assert "'products'" in (tmp_path / "config" / "settings.py").read_text()
    assert "products.urls" in (tmp_path / "config" / "urls.py").read_text()
    with pytest.raises(SystemExit):
        generate(tmp_path, "Product", ["name:str"])


def test_generated_project_passes_all_its_tests_and_has_a_dashboard(tmp_path):
    subprocess.run([sys.executable, "-m", "django", "startproject", "config", str(tmp_path)],
                   check=True, capture_output=True)
    generate(tmp_path, "Product", ["name:str", "price:decimal"])
    assert (tmp_path / "core" / "templates" / "core" / "base.html").exists()
    r = subprocess.run([sys.executable, "manage.py", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_restyle_keeps_everything_working(tmp_path):
    from workforce.generator import restyle
    subprocess.run([sys.executable, "-m", "django", "startproject", "config", str(tmp_path)],
                   check=True, capture_output=True)
    generate(tmp_path, "Product", ["name:str"])
    restyle(tmp_path)
    assert "Recent" in (tmp_path / "core" / "templates" / "core" / "dashboard.html").read_text()


def test_unique_foreign_keys_and_protected_delete(tmp_path):
    subprocess.run([sys.executable, "-m", "django", "startproject", "config", str(tmp_path)],
                   check=True, capture_output=True)
    generate(tmp_path, "Customer", ["name:str:unique", "email:email"])
    generate(tmp_path, "Invoice", ["number:str:unique", "customer:fk:Customer", "total:decimal"])
    generate(tmp_path, "InvoiceItem", ["description:str", "invoice:fk:Invoice", "quantity:int"])
    assert "unique=True" in (tmp_path / "customers" / "models.py").read_text()
    assert "ForeignKey" in (tmp_path / "invoices" / "models.py").read_text()
    with pytest.raises(SystemExit):
        generate(tmp_path, "Order", ["ref:str", "buyer:fk:Nobody"])
    (tmp_path / "invoices" / "test_protect.py").write_text(
        "from django.test import TestCase\n"
        "from django.urls import reverse\n"
        "from core.factories import make_instance\n"
        "from customers.models import Customer\n"
        "from .models import Invoice\n\n\n"
        "class ProtectTests(TestCase):\n"
        "    def test_cannot_delete_a_used_customer(self):\n"
        "        invoice = make_instance(Invoice)\n"
        "        response = self.client.post(reverse('customers:delete', args=[invoice.customer.pk]))\n"
        "        self.assertEqual(response.status_code, 200)\n"
        "        self.assertTrue(Customer.objects.filter(pk=invoice.customer.pk).exists())\n"
    )
    r = subprocess.run([sys.executable, "manage.py", "test"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
