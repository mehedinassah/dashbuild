import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

import workforce.worker as worker
import workforce.rules as rules_mod
from workforce import auto, codetools, mutation, notes, pipeline, scorecard
from workforce.fixture import BENCH_CARDS, make_project

CARD = BENCH_CARDS[0]  # SaleItem.line_total

GOOD_TESTS = '''
from decimal import Decimal
from django.test import TestCase
from sales.models import Product, Sale, SaleItem


class LineTotalTests(TestCase):
    def make(self, price, qty):
        sale = Sale.objects.create(customer_name="A")
        p = Product.objects.create(name="p", price=Decimal(price), stock=10)
        return SaleItem.objects.create(sale=sale, product=p, quantity=qty)

    def test_basic(self):
        self.assertEqual(self.make("5.00", 3).line_total(), Decimal("15.00"))

    def test_zero_quantity(self):
        self.assertEqual(self.make("5.00", 0).line_total(), Decimal("0.00"))

    def test_single(self):
        self.assertEqual(self.make("19.99", 1).line_total(), Decimal("19.99"))

    def test_four(self):
        self.assertEqual(self.make("2.50", 4).line_total(), Decimal("10.00"))
'''

WEAK_TESTS = GOOD_TESTS.split("    def test_basic")[0] + '''    def test_a(self):
        self.assertIsNotNone(self.make("5.00", 3).line_total())

    def test_b(self):
        self.assertIsNotNone(self.make("2.00", 2).line_total())
'''

NO_MENTION = "from django.test import TestCase\n\nclass T(TestCase):\n    def test_x(self):\n        self.assertTrue(True)\n"
BAD_FIELD = GOOD_TESTS.replace("price=Decimal(price)", "cost=Decimal(price)")
NO_ASSERT = GOOD_TESTS.replace('self.assertEqual(self.make("5.00", 3).line_total(), Decimal("15.00"))',
                               'self.make("5.00", 3).line_total()')

GOOD_IMPL = "def line_total(self):\n    return self.product.price * self.quantity\n"
WRONG_IMPL = "def line_total(self):\n    return 0\n"


class Fake:
    """A scripted stand-in for the model."""

    def __init__(self, tests=(), impls=()):
        self.tests, self.impls = list(tests), list(impls)

    @staticmethod
    def call(name, **args):
        return NS(message=NS(content="", tool_calls=[NS(function=NS(name=name, arguments=args))]),
                  done_reason="stop")

    @staticmethod
    def text(t):
        return NS(message=NS(content=t, tool_calls=None), done_reason="stop")

    def __call__(self, model=None, messages=None, tools=None, options=None, **kw):
        names = [t.__name__ for t in tools]
        tool_msgs = [m for m in messages if m["role"] == "tool"]
        last = tool_msgs[-1]["content"] if tool_msgs else ""
        if "write_tests" in names:
            if last.startswith("OK"):
                return self.text("DONE")
            if not tool_msgs:
                return self.call("show_models")
            return self.call("write_tests", code=self.tests.pop(0))
        if last.startswith("OK, all tests pass"):
            return self.text("DONE")
        setter = "set_method" if "set_method" in names else "set_function"
        if last.startswith("Saved"):
            return self.call("run_tests")
        if not self.impls:
            return self.text("DONE")
        return self.call(setter, code=self.impls.pop(0))


@pytest.fixture(scope="module")
def template(tmp_path_factory):
    return make_project(tmp_path_factory.mktemp("tpl") / "proj")


@pytest.fixture
def ws(template, tmp_path, monkeypatch):
    dst = tmp_path / "proj"
    shutil.copytree(template, dst)
    monkeypatch.setattr(scorecard, "ROOT", tmp_path)
    monkeypatch.setattr(auto, "STATE", tmp_path / "state.json")
    return dst


def use(monkeypatch, fake):
    monkeypatch.setattr(worker, "chat", fake)


def git_clean(ws):
    return subprocess.run(["git", "status", "--porcelain"], cwd=ws, capture_output=True,
                          text=True).stdout.strip() == ""


quiet = lambda *a, **k: None


# ---------- end to end ----------
def test_happy_path(ws, monkeypatch):
    use(monkeypatch, Fake([GOOD_TESTS], [GOOD_IMPL]))
    r = pipeline.run_card(ws, CARD, "fake", log=quiet)
    assert r["status"] == "passed", r["reason"]
    assert r["attempts"] == 1 and r["kill_rate"] == 1.0
    assert "def line_total" in (ws / "sales/models.py").read_text()
    assert (ws / "sales/test_saleitem_line_total.py").exists()
    assert pipeline.run_suite(ws)["ok"]


def test_weak_tests_are_rejected_then_good_ones_pass(ws, monkeypatch):
    use(monkeypatch, Fake([WEAK_TESTS, GOOD_TESTS], [GOOD_IMPL, GOOD_IMPL]))
    r = pipeline.run_card(ws, CARD, "fake", log=quiet)
    assert r["status"] == "passed" and r["attempts"] == 2


def test_only_weak_tests_fails_and_restores(ws, monkeypatch):
    before = (ws / "sales/models.py").read_text()
    use(monkeypatch, Fake([WEAK_TESTS] * 2, [GOOD_IMPL] * 2))
    r = pipeline.run_card(ws, CARD, "fake", attempts=2, log=quiet)
    assert r["status"] == "failed" and "too weak" in r["reason"]
    assert (ws / "sales/models.py").read_text() == before
    assert not (ws / "sales/test_saleitem_line_total.py").exists()
    assert git_clean(ws)


def test_bad_tests_are_bounced_before_locking(ws, monkeypatch):
    use(monkeypatch, Fake([NO_MENTION, BAD_FIELD, NO_ASSERT, GOOD_TESTS], [GOOD_IMPL]))
    r = pipeline.run_card(ws, CARD, "fake", log=quiet)
    assert r["status"] == "passed" and r["attempts"] == 1


def test_cheating_code_is_blocked(ws, monkeypatch):
    evil = ["import os\ndef line_total(self):\n    return 1\n",
            "def line_total(self):\n    return open('/etc/passwd').read()\n",
            "def __str__(self):\n    return 'x'\n",
            "def quantity(self):\n    return 1\n"]
    f = Fake([GOOD_TESTS], evil + [GOOD_IMPL])
    use(monkeypatch, f)
    r = pipeline.run_card(ws, CARD, "fake", log=quiet)
    assert r["status"] == "passed"
    src = (ws / "sales/models.py").read_text()
    assert "os" not in src.replace("Product", "") .split("import")[0] and "passwd" not in src


def test_wrong_implementation_fails_and_restores(ws, monkeypatch):
    before = (ws / "sales/models.py").read_text()
    use(monkeypatch, Fake([GOOD_TESTS] * 2, [WRONG_IMPL] * 30))
    r = pipeline.run_card(ws, CARD, "fake", attempts=2, log=quiet)
    assert r["status"] == "failed"
    assert (ws / "sales/models.py").read_text() == before
    assert git_clean(ws)
    assert (ws / ".autopilot/failed/test_saleitem_line_total.py").exists()


def test_user_declines_and_everything_reverts(ws, monkeypatch):
    use(monkeypatch, Fake([GOOD_TESTS], [GOOD_IMPL]))
    st = auto.run_cards(ws, [CARD], "fake", ask=lambda p: "n", log=quiet)
    assert st["declined"] and not st["done"]
    assert git_clean(ws) and "line_total" not in (ws / "sales/models.py").read_text()


def test_user_accepts_and_it_is_committed(ws, monkeypatch):
    use(monkeypatch, Fake([GOOD_TESTS], [GOOD_IMPL]))
    st = auto.run_cards(ws, [CARD], "fake", ask=lambda p: "y", log=quiet)
    assert st["done"] == ["sales_saleitem_line_total"]
    log = subprocess.run(["git", "log", "--oneline"], cwd=ws, capture_output=True, text=True).stdout
    assert "auto: sales_saleitem_line_total" in log and git_clean(ws)
    assert scorecard.load()[0]["status"] == "passed"


def test_service_card(ws, monkeypatch):
    card = BENCH_CARDS[3]
    tests = '''
from django.test import TestCase
from sales.models import Product
from sales.services import reduce_stock


class ReduceStockTests(TestCase):
    def test_reduces(self):
        p = Product.objects.create(name="a", price="1.00", stock=5)
        reduce_stock(p, 2)
        p.refresh_from_db()
        self.assertEqual(p.stock, 3)

    def test_exact(self):
        p = Product.objects.create(name="a", price="1.00", stock=5)
        reduce_stock(p, 5)
        p.refresh_from_db()
        self.assertEqual(p.stock, 0)

    def test_too_much(self):
        p = Product.objects.create(name="a", price="1.00", stock=1)
        with self.assertRaises(ValueError):
            reduce_stock(p, 2)
        p.refresh_from_db()
        self.assertEqual(p.stock, 1)
'''
    impl = ("def reduce_stock(product, quantity):\n    if product.stock < quantity:\n"
            "        raise ValueError('not enough stock')\n    product.stock -= quantity\n"
            "    product.save()\n")
    use(monkeypatch, Fake([tests], [impl]))
    r = pipeline.run_card(ws, card, "fake", log=quiet)
    assert r["status"] == "passed", r["reason"]


def test_auto_cli_with_cards_file(ws, monkeypatch, tmp_path):
    use(monkeypatch, Fake([GOOD_TESTS], [GOOD_IMPL]))
    cf = tmp_path / "cards.json"
    cf.write_text(json.dumps({"cards": [CARD]}))
    rc = auto.main(["auto", "--workspace", str(ws), "--cards", str(cf), "--yes", "--no-preflight"])
    assert rc == 0
    branch = subprocess.run(["git", "branch", "--show-current"], cwd=ws, capture_output=True,
                            text=True).stdout.strip()
    assert branch.startswith("auto/")


def test_preflight_refuses_dirty_tree(ws):
    (ws / "x.txt").write_text("x")
    assert "uncommitted" in auto.preflight(ws, "m", check_ollama=False)


# ---------- unit tests ----------
def test_upsert_insert_replace_and_decorator():
    src = "class A:\n    x = 1\n\n    @property\n    def f(self):\n        return 1\n\n\nclass B:\n    pass\n"
    new, err = codetools.upsert_def(src, "def g(self):\n    return 2", "A")
    assert not err and "def g" in new and new.index("def g") < new.index("class B")
    new2, err = codetools.upsert_def(new, "@property\ndef f(self):\n    return 9", "A")
    assert not err and new2.count("def f") == 1 and "return 9" in new2
    _, err = codetools.upsert_def(src, "def x(self):\n    return 2", "A")
    assert "field" in err
    _, err = codetools.upsert_def(src, "def g():\n    return 2", "A")
    assert "self" in err
    _, err = codetools.upsert_def(src, "def g(self):\n    return 2\ndef h(self):\n    pass", "A")
    assert "ONE" in err


def test_add_import_dedupes_and_blocks():
    src = '"""doc"""\nfrom a import b\n\nx = 1\n'
    new, _ = codetools.add_import(src, "from decimal import Decimal")
    assert new.splitlines()[2] == "from decimal import Decimal"
    again, _ = codetools.add_import(new, "from decimal import Decimal")
    assert again == new
    assert codetools.add_import(src, "import os")[1]
    assert codetools.add_import(src, "x = 1")[1]


def test_safety_problem():
    assert codetools.safety_problem("import subprocess")
    assert codetools.safety_problem("eval('1')")
    assert codetools.safety_problem("def f(:")
    assert codetools.safety_problem("def f(x):\n    return x + 1") is None


def test_mutants_cover_and_are_valid():
    src = "class A:\n    def f(self, a, b):\n        if a > b and a:\n            return a * 2\n        return not b\n"
    ms = mutation.mutants(src, "f", "A")
    assert len(ms) >= 5
    for desc, code in ms:
        compile(code, "m", "exec")
        assert code.strip() != src.strip()
    assert mutation.mutants("def g():\n    pass\n", "g") == []


def test_project_map_has_reverse_names(ws):
    m = notes.project_map(ws)
    assert "saleitem_set" in m and "price: DecimalField" in m


def test_validate_cards(ws):
    good = dict(CARD)
    bad = [dict(good, kind="nope"), dict(good, app="ghost"), dict(good, name="Bad Name"),
           dict(good, spec="short"), dict(good, **{"class": "Ghost"}), dict(good, name="stock", **{"class": "Product"})]
    valid, problems = rules_mod.validate_cards(ws, [good, good] + bad)
    assert len(valid) == 1 and len(problems) == len(bad) + 1


def test_propose_cards_retries_until_valid(ws, monkeypatch):
    replies = ["not json", json.dumps({"cards": [dict(CARD, app="ghost")]}),
               json.dumps({"cards": [CARD]})]
    monkeypatch.setattr(rules_mod, "chat", lambda **kw: NS(message=NS(content=replies.pop(0))))
    cards, problems = rules_mod.propose_cards("shop", ws, "fake")
    assert len(cards) == 1 and not problems


def test_scorecard_summary(tmp_path):
    scorecard.record({"id": "a", "model": "m1", "status": "passed", "attempts": 1,
                      "kill_rate": 1, "seconds": 10, "reason": ""}, tmp_path)
    scorecard.record({"id": "b", "model": "m1", "status": "failed", "attempts": 3,
                      "kill_rate": None, "seconds": 30, "reason": "x"}, tmp_path)
    s = scorecard.summary(tmp_path)
    assert "m1" in s and "2" in s


def test_bench_fixture_baseline_green(ws):
    assert pipeline.run_suite(ws)["ok"]


# ---------- regression: the flaws found by the first real benchmark ----------
PROP_TESTS = GOOD_TESTS.replace(".line_total()", ".line_total")
NO_PRODUCT = GOOD_TESTS.replace('''    def test_four(self):''', '''    def test_none(self):
        sale = Sale.objects.create(customer_name="A")
        item = SaleItem.objects.create(sale=sale, quantity=2)
        self.assertIsNone(item.line_total())

    def test_four(self):''')


def test_property_style_tests_are_bounced(ws):
    assert "parentheses" in pipeline.check_tests(PROP_TESTS, CARD)
    assert pipeline.check_tests(GOOD_TESTS, CARD) is None


def test_tests_that_crash_for_other_reasons_are_bounced(ws):
    path = pipeline.test_file(ws, CARD)
    path.write_text(NO_PRODUCT)
    r = pipeline.run_suite(ws, pipeline.card_label(ws, CARD))
    path.unlink()
    good, why = pipeline.classify_red(r["output"], r["ok"], "line_total")
    assert not good and "test_none" in why and "wrong reason" in why


def test_summary_is_short_and_names_the_error(ws):
    path = pipeline.test_file(ws, CARD)
    path.write_text(NO_PRODUCT)
    r = pipeline.run_suite(ws, pipeline.card_label(ws, CARD))
    path.unlink()
    s = pipeline.summarize(r["output"])
    assert "IntegrityError" in s and len(s) < 1500


def test_invented_error_tests_are_bounced(ws):
    invented = GOOD_TESTS + '''
    def test_error(self):
        with self.assertRaises(ValueError):
            self.make("5.00", 1).line_total()
'''
    assert "assertRaises" in pipeline.check_tests(invented, CARD)
    svc = dict(BENCH_CARDS[3])  # its rule does say 'raises ValueError'
    assert pipeline.check_tests(
        "from django.test import TestCase\nfrom sales.services import reduce_stock\n\n"
        "class T(TestCase):\n    def test_a(self):\n        with self.assertRaises(ValueError):\n"
        "            reduce_stock(None, 1)\n", svc) is None


def test_impl_failure_feedback_names_the_failing_test(ws, monkeypatch):
    use(monkeypatch, Fake([GOOD_TESTS], [WRONG_IMPL] * 30))
    r = pipeline.run_card(ws, CARD, "fake", attempts=1, log=quiet)
    assert r["status"] == "failed" and "test_basic" in r["reason"]
