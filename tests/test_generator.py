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
