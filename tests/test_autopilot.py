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


def test_service_card_tests_must_call_a_function(ws):
    card = BENCH_CARDS[3]
    as_method = ("from django.test import TestCase\nfrom sales.models import Product\n\n"
                 "class T(TestCase):\n    def test_a(self):\n"
                 "        p = Product.objects.create(name='a', price='1', stock=3)\n"
                 "        p.reduce_stock(1)\n        self.assertEqual(p.stock, 2)\n")
    assert "import the function" in pipeline.check_tests(as_method, card)
    wrong_call = as_method.replace("from sales.models import Product",
                                   "from sales.models import Product\nfrom sales.services import reduce_stock")
    assert "plain function" in pipeline.check_tests(wrong_call, card)


def test_kind_note_differs_by_kind():
    assert "METHOD" in pipeline.kind_note(BENCH_CARDS[0])
    assert "FUNCTION" in pipeline.kind_note(BENCH_CARDS[3])


def test_think_option_is_passed_through(monkeypatch):
    seen = {}
    monkeypatch.setattr(worker, "_ollama_chat", lambda **kw: seen.update(kw) or "ok")
    monkeypatch.setitem(worker.CFG, "think", False)
    assert worker.chat(model="m", messages=[]) == "ok" and seen["think"] is False
    monkeypatch.delitem(worker.CFG, "think")
    seen.clear()
    worker.chat(model="m", messages=[])
    assert "think" not in seen


def test_rules_pass_think(ws, monkeypatch):
    got = {}
    def fake(**kw):
        got.update(kw)
        return NS(message=NS(content=json.dumps({"cards": [CARD]})))
    monkeypatch.setattr(rules_mod, "chat", fake)
    monkeypatch.setitem(rules_mod.CFG, "think", False)
    rules_mod.propose_cards("shop", ws, "fake")
    assert got["think"] is False


def test_prompt_reasks_until_y_or_n(ws, monkeypatch):
    use(monkeypatch, Fake([GOOD_TESTS], [GOOD_IMPL]))
    answers = iter(["def line_total(self):", "", "maybe", "y"])
    st = auto.run_cards(ws, [CARD], "fake", ask=lambda p: next(answers), log=quiet)
    assert st["done"] == ["sales_saleitem_line_total"]


def test_summary_shows_the_failing_test_line(ws):
    path = pipeline.test_file(ws, CARD)
    path.write_text(GOOD_TESTS)
    r = pipeline.run_suite(ws, pipeline.card_label(ws, CARD))
    path.unlink()
    assert "failed on this line of the test" in pipeline.summarize(r["output"])


def test_normalize_indent_fixes_deep_bodies():
    deep = "def f(self):\n            x = 1\n            if x:\n                return 2\n            return 3\n"
    out = codetools.normalize_indent(deep)
    assert out.splitlines()[1] == "    x = 1" and out.splitlines()[3] == "        return 2"
    new, err = codetools.upsert_def("class A:\n    pass\n", deep, "A")
    assert not err and "\n        x = 1\n" in new


def test_mutation_removes_calls_and_hints_are_specific():
    src = "class A:\n    def f(self):\n        self.x = 1\n        self.save()\n"
    descs = [d for d, _ in mutation.mutants(src, "f", "A")]
    assert any("removed a statement" in d for d in descs)
    hint = pipeline._survivor_hints(["line 17: changed the number 0"])
    assert "exactly 0 and exactly 1" in hint
    assert "refresh_from_db" in pipeline._survivor_hints(["line 3: removed a statement that calls something"])


def test_unsaved_change_is_caught(ws, monkeypatch):
    tests = '''
from django.test import TestCase
from sales.models import Product
from sales.services import reduce_stock


class T(TestCase):
    def test_a(self):
        p = Product.objects.create(name="a", price="1.00", stock=5)
        reduce_stock(p, 2)
        self.assertEqual(p.stock, 3)

    def test_b(self):
        p = Product.objects.create(name="a", price="1.00", stock=5)
        reduce_stock(p, 5)
        self.assertEqual(p.stock, 0)

    def test_c(self):
        p = Product.objects.create(name="a", price="1.00", stock=1)
        with self.assertRaises(ValueError):
            reduce_stock(p, 2)
        self.assertEqual(p.stock, 1)
'''
    impl = ("def reduce_stock(product, quantity):\n    if product.stock < quantity:\n"
            "        raise ValueError('no')\n    product.stock -= quantity\n    product.save()\n")
    use(monkeypatch, Fake([tests] * 2, [impl] * 2))
    r = pipeline.run_card(ws, BENCH_CARDS[3], "fake", attempts=1, log=quiet)
    assert r["status"] == "failed" and "refresh_from_db" in r["reason"]


# ---------- v9: field cards and change cards ----------
FIELD_CARD = {"app": "sales", "kind": "field", "class": "Sale", "name": "confirmed",
              "spec": "A sale is confirmed or not; new sales start as not confirmed.",
              "definition": "models.BooleanField(default=False)"}


def test_field_card_adds_field_and_migration(ws):
    r = pipeline.run_card(ws, FIELD_CARD, "none", log=quiet)
    assert r["status"] == "passed", r["reason"]
    assert "confirmed = models.BooleanField(default=False)" in (ws / "sales/models.py").read_text()
    assert any("migrations/0002" in f for f in r["files"]) and r["kill_rate"] is None
    assert pipeline.run_suite(ws)["ok"]
    chk = subprocess.run([sys.executable, "manage.py", "makemigrations", "--check", "--dry-run"],
                         cwd=ws, capture_output=True)
    assert chk.returncode == 0


def test_field_card_rejects_unsafe_or_incomplete_definitions(ws):
    from workforce import fields
    assert fields.check_definition("models.BooleanField(default=False)") is None
    assert fields.check_definition("models.CharField(max_length=20, default='')") is None
    assert fields.check_definition("models.ForeignKey('customers.Customer', on_delete=models.PROTECT, null=True)") is None
    assert "default" in fields.check_definition("models.BooleanField()")
    assert "not allowed" in fields.check_definition("models.FilePathField(default='')")
    assert "on_delete" in fields.check_definition("models.ForeignKey('a.B', null=True)")
    assert "plain value" in fields.check_definition("models.IntegerField(default=__import__('os').getcwd())")
    assert fields.check_definition("print(1)")
    assert fields.check_definition("models.CharField(default='')")  # max_length missing


def test_field_card_failure_leaves_project_untouched(ws):
    before = (ws / "sales/models.py").read_text()
    bad = dict(FIELD_CARD, definition="models.BooleanField()")
    r = pipeline.run_card(ws, bad, "none", log=quiet)
    assert r["status"] == "failed" and (ws / "sales/models.py").read_text() == before
    assert git_clean(ws)


def test_add_field_goes_after_the_last_field():
    src = "class A(models.Model):\n    x = models.IntegerField(default=0)\n\n    def f(self):\n        return 1\n"
    new, err = fields_add(src)
    assert not err and new.index("y = ") < new.index("def f") and new.index("x = ") < new.index("y = ")
    assert fields_add("class A:\n    z = 1\n")[1] is None
    assert "already exists" in fields_add("class A(models.Model):\n    y = models.IntegerField(default=0)\n")[1]
    assert "does not exist" in fields_add("class B:\n    pass\n")[1]


def fields_add(src):
    from workforce import fields
    return fields.add_field(src, "A", "y", "models.BooleanField(default=False)")


def test_validate_field_and_change_cards(ws):
    change = {"app": "sales", "kind": "service", "name": "reduce_stock", "mode": "change",
              "tag": "no_negative", "spec": "reduce_stock also raises ValueError when quantity is negative."}
    bads = [dict(FIELD_CARD, name="customer_name"), dict(FIELD_CARD, definition="models.BooleanField()"),
            dict(change, tag=""), dict(change, mode="rewrite"),
            dict(change, name="nope"), dict(change, kind="model", **{"class": "Product"}, name="nope")]
    valid, problems = rules_mod.validate_cards(ws, [FIELD_CARD] + bads)
    assert [c["kind"] for c in valid] == ["field"] and len(problems) == len(bads)
    # a change card needs its target to exist: build it first
    use_service(ws)
    valid, problems = rules_mod.validate_cards(ws, [change])
    assert len(valid) == 1 and pipeline.card_id(valid[0]) == "sales_func_reduce_stock_no_negative"


SERVICE_TESTS = '''
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
SERVICE_IMPL = ("def reduce_stock(product, quantity):\n    if product.stock < quantity:\n"
                "        raise ValueError('not enough stock')\n    product.stock -= quantity\n"
                "    product.save()\n")


def use_service(ws, monkeypatch=None):
    """Put the plain reduce_stock service in the project (as an earlier card would have)."""
    (ws / "sales/services.py").write_text('"""Business logic functions."""\n\n\n' + SERVICE_IMPL)
    (ws / "sales/test_func_reduce_stock.py").write_text(SERVICE_TESTS)


CHANGE_CARD = {"app": "sales", "kind": "service", "class": "", "name": "reduce_stock", "mode": "change",
               "tag": "no_negative",
               "spec": "reduce_stock also raises ValueError when quantity is negative and then changes nothing."}

CHANGE_TESTS = '''
from django.test import TestCase
from sales.models import Product
from sales.services import reduce_stock


class ReduceStockNegativeTests(TestCase):
    def test_negative_is_refused(self):
        p = Product.objects.create(name="a", price="1.00", stock=5)
        with self.assertRaises(ValueError):
            reduce_stock(p, -1)
        p.refresh_from_db()
        self.assertEqual(p.stock, 5)

    def test_zero_is_fine(self):
        p = Product.objects.create(name="a", price="1.00", stock=5)
        reduce_stock(p, 0)
        p.refresh_from_db()
        self.assertEqual(p.stock, 5)

    def test_minus_two_is_refused(self):
        p = Product.objects.create(name="a", price="1.00", stock=3)
        with self.assertRaises(ValueError):
            reduce_stock(p, -2)
        p.refresh_from_db()
        self.assertEqual(p.stock, 3)
'''
CHANGE_IMPL = ("def reduce_stock(product, quantity):\n    if quantity < 0:\n"
               "        raise ValueError('negative quantity')\n"
               "    if product.stock < quantity:\n        raise ValueError('not enough stock')\n"
               "    product.stock -= quantity\n    product.save()\n")


def test_change_card_modifies_existing_function(ws, monkeypatch):
    use_service(ws)
    subprocess.run(["git", "add", "-A"], cwd=ws, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "svc"], cwd=ws, check=True)
    seen = {}
    fake = Fake([CHANGE_TESTS], [CHANGE_IMPL])
    real = fake.__call__

    def spy(**kw):
        seen["first"] = seen.get("first") or kw["messages"][1]["content"]
        return real(**kw)
    use(monkeypatch, spy)
    r = pipeline.run_card(ws, CHANGE_CARD, "fake", log=quiet)
    assert r["status"] == "passed", r["reason"]
    assert "CHANGES an existing function" in seen["first"] and "def reduce_stock" in seen["first"]
    assert (ws / "sales/test_func_reduce_stock_no_negative.py").exists()
    assert (ws / "sales/test_func_reduce_stock.py").read_text().strip() == SERVICE_TESTS.strip()
    assert "quantity < 0" in (ws / "sales/services.py").read_text()
    assert pipeline.run_suite(ws)["ok"]


def test_change_card_tests_that_already_pass_are_rejected(ws, monkeypatch):
    use_service(ws)
    subprocess.run(["git", "add", "-A"], cwd=ws, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "svc"], cwd=ws, check=True)
    # tests of the OLD behaviour only: they pass already, so they test nothing new
    use(monkeypatch, Fake([SERVICE_TESTS.replace("ReduceStockTests", f"OldAgain{i}") for i in range(30)], [CHANGE_IMPL] * 5))
    r = pipeline.run_card(ws, CHANGE_CARD, "fake", attempts=2, log=quiet)
    assert r["status"] == "failed"
    assert not (ws / "sales/test_func_reduce_stock_no_negative.py").exists()


# ---------- v10: time budget and repeated failures ----------
def test_card_stops_when_time_budget_is_used(ws, monkeypatch):
    monkeypatch.setitem(pipeline.CFG, "card_minutes", 0)
    use(monkeypatch, Fake([GOOD_TESTS, GOOD_TESTS], [WRONG_IMPL, WRONG_IMPL]))
    r = pipeline.run_card(ws, CARD, "fake", attempts=5, log=quiet)
    assert r["status"] == "failed" and r["attempts"] == 1 and "stopped after" in r["reason"]
    assert git_clean(ws)


def test_repeated_failure_gets_a_stronger_hint(ws, monkeypatch):
    use(monkeypatch, Fake([GOOD_TESTS], [WRONG_IMPL] * 6))
    seen = []
    real = pipeline.run_suite

    def spy(*a, **k):
        r = real(*a, **k)
        seen.append(r)
        return r
    monkeypatch.setattr(pipeline, "run_suite", spy)
    msgs = []
    orig_chat = worker.chat

    def watch(**kw):
        msgs.extend(m["content"] for m in kw["messages"] if m["role"] == "tool")
        return orig_chat(**kw)
    monkeypatch.setattr(worker, "chat", watch)
    pipeline.run_card(ws, CARD, "fake", attempts=1, log=quiet)
    assert any("EXACT FAILURE HAPPENED" in m for m in msgs)


def test_impl_prompt_says_check_before_changing():
    txt = (pipeline.PROMPTS / "card_impl.txt").read_text()
    assert "BEFORE you change" in txt or "raise before you change" in txt


def test_change_card_already_built_is_skipped(ws):
    use_service(ws)
    ok, _ = rules_mod.validate_cards(ws, [CHANGE_CARD])
    assert len(ok) == 1
    (ws / "sales/test_func_reduce_stock_no_negative.py").write_text("# built earlier\n")
    ok, problems = rules_mod.validate_cards(ws, [CHANGE_CARD])
    assert ok == [] and "already built" in problems[0]


# ---------- v11: ./wfa plan ----------
def _plan_args(ws, out):
    return NS(workspace=str(ws), model="fake", out=str(out), description="shop", no_preflight=True)


def test_plan_keep_drop_edit_and_fields_first(ws, monkeypatch, tmp_path):
    cards = [dict(CARD), dict(FIELD_CARD),
             {"app": "sales", "kind": "model", "class": "Product", "name": "is_cheap",
              "spec": "is_cheap returns True when price is below 5."}]
    monkeypatch.setattr(rules_mod, "chat", lambda **kw: NS(message=NS(content=json.dumps({"cards": cards}))))
    answers = iter(["maybe", "y", "y", "e", "is_cheap returns True when price is below 10.", "y"])
    out = tmp_path / "plan.json"
    lines = []
    rc = auto.run_plan(_plan_args(ws, out), ask=lambda q: next(answers), out=lines.append)
    assert rc == 0
    saved = json.loads(out.read_text())["cards"]
    assert [c["name"] for c in saved] == ["confirmed", "line_total", "is_cheap"]  # field first
    assert "below 10" in saved[2]["spec"]
    assert any("Please type" in l for l in lines)
    assert not (ws / "cards_plan.json").exists()


def test_plan_dropping_everything_writes_nothing(ws, monkeypatch, tmp_path):
    monkeypatch.setattr(rules_mod, "chat", lambda **kw: NS(message=NS(content=json.dumps({"cards": [CARD]}))))
    out = tmp_path / "plan.json"
    rc = auto.run_plan(_plan_args(ws, out), ask=lambda q: "n", out=lambda *a: None)
    assert rc == 1 and not out.exists()


def test_plan_rejects_bad_field_definition(ws, monkeypatch, tmp_path):
    bad = dict(FIELD_CARD, definition="models.BooleanField()")
    replies = [json.dumps({"cards": [bad]}), json.dumps({"cards": [bad]}), json.dumps({"cards": [bad]})]
    monkeypatch.setattr(rules_mod, "chat", lambda **kw: NS(message=NS(content=replies.pop(0))))
    rc = auto.run_plan(_plan_args(ws, tmp_path / "p.json"), ask=lambda q: "y", out=lambda *a: None)
    assert rc == 1


def test_rules_prompt_teaches_field_cards():
    txt = (pipeline.PROMPTS / "card_rules.txt").read_text()
    assert '"field"' in txt and "definition" in txt and "default=" in txt


# ---------- v12: no invented behaviour ----------
def test_tests_for_inputs_the_rule_never_mentions_are_bounced(ws):
    card = {"app": "sales", "kind": "service", "class": "", "name": "create_thing",
            "spec": "create_thing(customer) creates a thing. If the customer is inactive it raises ValueError."}
    base = '''
from django.test import TestCase
from sales.services import create_thing


class T(TestCase):
    def test_inactive_raises(self):
        with self.assertRaises(ValueError):
            create_thing(None)
%s'''
    ok = base % ""
    assert pipeline.check_tests(ok, card) is None
    by_name = base % '''
    def test_create_thing_with_invalid_date(self):
        with self.assertRaises(ValueError):
            create_thing(None)
'''
    assert "never mentions" in pipeline.check_tests(by_name, card)
    by_value = base % '''
    def test_other(self):
        with self.assertRaises(ValueError):
            create_thing("invalid_date")
'''
    assert "invalid input" in pipeline.check_tests(by_value, card)
    mentioned = dict(card, spec=card["spec"] + " An invalid customer also raises ValueError.")
    assert pipeline.check_tests(by_name, mentioned) is None


def test_unused_new_imports_are_removed_but_old_ones_stay():
    old = "from a import b\n\n\ndef f():\n    return b\n"
    new = ("from a import b\nfrom django.utils.dateparse import parse_date\nimport datetime\n"
           "from decimal import Decimal, ROUND_UP\n\n\ndef f():\n    return b\n\n\ndef g(x):\n"
           "    return Decimal(x)\n")
    out = codetools.drop_unused_new_imports(old, new)
    assert "parse_date" not in out and "datetime" not in out and "ROUND_UP" not in out
    assert "from decimal import Decimal" in out and "from a import b" in out
    # an import that was already there is never touched, even if unused
    assert codetools.drop_unused_new_imports("import os_like\n", "import os_like\n") == "import os_like\n"
    compile(out, "x", "exec")


def test_impl_prompt_forbids_extras():
    assert "ONLY what the rule says" in (pipeline.PROMPTS / "card_impl.txt").read_text()


# ---------- v13: broken tests are blamed, imports sent with the function are accepted ----------
def test_split_imports_moves_imports_out_of_a_single_function():
    imps, rest = codetools.split_imports("import datetime\nfrom decimal import Decimal\n\ndef f(x):\n    return Decimal(x)\n")
    assert imps == ["import datetime", "from decimal import Decimal"] and rest.startswith("def f")
    assert codetools.split_imports("def f():\n    pass\n") == ([], "def f():\n    pass\n")
    two = "import os_x\ndef f():\n    pass\ndef g():\n    pass\n"
    assert codetools.split_imports(two) == ([], two)


def test_function_sent_with_its_imports_is_accepted(ws, monkeypatch):
    impl = ("from decimal import Decimal\n\n"
            "def line_total(self):\n    return self.product.price * self.quantity\n")
    use(monkeypatch, Fake([GOOD_TESTS], [impl]))
    r = pipeline.run_card(ws, CARD, "fake", log=quiet)
    assert r["status"] == "passed", r["reason"]
    src = (ws / "sales/models.py").read_text()
    assert "def line_total" in src and "Decimal" not in src.split("class Product")[0].replace("DecimalField", "")


def test_test_error_tells_a_broken_test_from_a_wrong_assertion(ws):
    broken = GOOD_TESTS.replace('self.assertEqual(self.make("5.00", 3).line_total(), Decimal("15.00"))',
                                'self.assertEqual(self.make("5.00", 3).quantity.strftime("%Y"), "x")')
    (ws / "sales/test_x.py").write_text(broken)
    out = pipeline.run_suite(ws)["output"]
    te = pipeline.test_error(out, "line_total")
    assert te and "strftime" in te[1] + te[2] and te[0] == "test_basic"
    (ws / "sales/test_x.py").write_text(GOOD_TESTS)
    assert pipeline.test_error(pipeline.run_suite(ws)["output"], "line_total") is None  # feature missing: not a test bug


def test_attempt_is_aborted_when_the_locked_test_itself_crashes(ws, monkeypatch):
    broken = GOOD_TESTS.replace('self.assertEqual(self.make("5.00", 3).line_total(), Decimal("15.00"))',
                                'self.assertEqual(self.make("5.00", 3).quantity.strftime("%Y"), "x")')
    impls = [f"def line_total(self):\n    # try {i}\n    return self.product.price * self.quantity\n"
             for i in range(10)]
    use(monkeypatch, Fake([broken], impls))
    # the red check cannot see this: the test fails "for the right reason" because line_total is missing
    # only if it fails with AssertionError, so craft the check to allow it by running through the pipeline
    monkeypatch.setattr(pipeline, "classify_red", lambda *a: (True, ""))
    r = pipeline.run_card(ws, CARD, "fake", attempts=1, log=quiet)
    assert r["status"] == "failed" and "previous tests were wrong" in r["reason"]
    assert "strftime" in r["reason"]
    assert git_clean(ws)


def test_card_tests_prompt_covers_dates():
    txt = (pipeline.PROMPTS / "card_tests.txt").read_text()
    assert "datetime.date" in txt and "strftime" in txt


# ---------- v14: view cards ----------
from workforce import wiring  # noqa: E402

SHIP_SERVICE = '''"""Business logic functions."""


def ship_sale(sale):
    items = list(sale.saleitem_set.all())
    for it in items:
        if it.quantity > it.product.stock:
            raise ValueError("Not enough stock")
    for it in items:
        it.product.stock -= it.quantity
        it.product.save()
'''

VIEW_CARD = {"app": "sales", "kind": "view", "class": "", "name": "ship_sale_view", "url": "<int:pk>/ship/",
             "button": "Ship", "show_if": "item.customer_name",
             "spec": "ship_sale_view(request, pk) ships the sale with ship_sale. A ValueError from it is shown "
                     "as an error message and nothing changes. Success shows 'Sale shipped.' Always redirect "
                     "to sales:list. Only POST is allowed."}

VIEW_TESTS = '''
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from sales.models import Product, Sale, SaleItem


class ShipSaleViewTests(TestCase):
    def make(self, stock, qty):
        sale = Sale.objects.create(customer_name="A")
        product = Product.objects.create(name="p", price="1.00", stock=stock)
        SaleItem.objects.create(sale=sale, product=product, quantity=qty)
        return sale, product

    def test_ships_and_redirects(self):
        sale, product = self.make(5, 2)
        r = self.client.post(reverse("sales:ship_sale_view", args=[sale.pk]))
        self.assertRedirects(r, reverse("sales:list"))
        product.refresh_from_db()
        self.assertEqual(product.stock, 3)
        self.assertEqual([str(m) for m in get_messages(r.wsgi_request)], ["Sale shipped."])

    def test_not_enough_stock_shows_the_error(self):
        sale, product = self.make(1, 2)
        r = self.client.post(reverse("sales:ship_sale_view", args=[sale.pk]))
        self.assertRedirects(r, reverse("sales:list"))
        product.refresh_from_db()
        self.assertEqual(product.stock, 1)
        self.assertEqual([str(m) for m in get_messages(r.wsgi_request)], ["Not enough stock"])

    def test_get_is_refused(self):
        sale, product = self.make(5, 2)
        r = self.client.get(reverse("sales:ship_sale_view", args=[sale.pk]))
        self.assertEqual(r.status_code, 405)
        product.refresh_from_db()
        self.assertEqual(product.stock, 5)
'''

VIEW_IMPL = '''from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST
from .services import ship_sale


@require_POST
def ship_sale_view(request, pk):
    sale = get_object_or_404(Sale, pk=pk)
    try:
        ship_sale(sale)
    except ValueError as e:
        messages.error(request, str(e))
    else:
        messages.success(request, "Sale shipped.")
    return redirect("sales:list")
'''


def _commit_all(ws, msg="base"):
    subprocess.run(["git", "add", "-A"], cwd=ws, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", msg], cwd=ws, check=True)


def test_view_card_check_rules():
    assert wiring.check_view_card(VIEW_CARD) is None
    assert "url" in wiring.check_view_card(dict(VIEW_CARD, url="/ship/"))
    assert "url" in wiring.check_view_card(dict(VIEW_CARD, url="ship"))
    assert "button" in wiring.check_view_card(dict(VIEW_CARD, button="<b>x</b>"))
    assert "show_if" in wiring.check_view_card(dict(VIEW_CARD, show_if="__import__('os')"))
    assert "pk" in wiring.check_view_card(dict(VIEW_CARD, url="export/"))
    assert "url_name" in wiring.check_view_card({"class": "X", "url_name": ""})
    assert wiring.check_view_card({"class": "X", "url_name": "sales:create"}) is None


def test_wire_url_messages_and_button_are_idempotent(ws):
    assert wiring.wire_url(ws, "sales", "<int:pk>/ship/", "ship_sale_view") is None
    assert wiring.wire_url(ws, "sales", "<int:pk>/ship/", "ship_sale_view") is None
    urls = (ws / "sales/urls.py").read_text()
    assert urls.count("ship_sale_view") == 2 and 'path("<int:pk>/ship/", views.ship_sale_view' in urls
    ch = wiring.ensure_messages_block(ws)
    assert len(ch) == 1 and wiring.ensure_messages_block(ws) == {}
    base = (ws / "core/templates/core/base.html").read_text()
    assert base.index('class="messages"') < base.index("{% block content %}") and ".message.error" in base
    ch = wiring.add_row_button(ws, "sales", "ship_sale_view", "Ship", "not item.shipped")
    assert len(ch) == 1 and wiring.add_row_button(ws, "sales", "ship_sale_view", "Ship") == {}
    lst = (ws / "sales/templates/sales/list.html").read_text()
    assert "{% if not item.shipped %}" in lst and "{% csrf_token %}" in lst and ">Ship<" in lst


def test_view_card_end_to_end_with_button_and_messages(ws, monkeypatch):
    (ws / "sales/services.py").write_text(SHIP_SERVICE)
    _commit_all(ws)
    use(monkeypatch, Fake([VIEW_TESTS], [VIEW_IMPL]))
    r = pipeline.run_card(ws, VIEW_CARD, "fake", log=quiet)
    assert r["status"] == "passed", r["reason"]
    assert set(r["files"]) >= {"sales/views.py", "sales/urls.py", "sales/test_func_ship_sale_view.py",
                               "sales/templates/sales/list.html", "core/templates/core/base.html"}
    from django.test.utils import override_settings  # noqa: F401  (the suite itself renders the pages)
    sale_check = '''
from django.test import TestCase
from django.urls import reverse
from sales.models import Sale


class PagesTests(TestCase):
    def test_list_shows_button_and_message(self):
        sale = Sale.objects.create(customer_name="A")
        r = self.client.post(reverse("sales:ship_sale_view", args=[sale.pk]), follow=True)
        self.assertContains(r, "Sale shipped.")
        self.assertContains(r, ">Ship<")
        self.assertContains(r, 'class="message success"')
'''
    (ws / "sales/test_pages_tmp.py").write_text(sale_check)
    out = pipeline.run_suite(ws)
    assert out["ok"], out["output"][-800:]


def test_view_card_failure_restores_urls_and_templates(ws, monkeypatch):
    (ws / "sales/services.py").write_text(SHIP_SERVICE)
    _commit_all(ws)
    wrong = VIEW_IMPL.replace('messages.success(request, "Sale shipped.")', 'messages.success(request, "Done")')
    use(monkeypatch, Fake([VIEW_TESTS] * 3, [wrong] * 3))
    r = pipeline.run_card(ws, VIEW_CARD, "fake", attempts=1, log=quiet)
    assert r["status"] == "failed"
    assert git_clean(ws)


def test_view_tests_must_use_the_client_and_reverse(ws):
    card = dict(VIEW_CARD)
    no_client = "from django.test import TestCase\n\nclass T(TestCase):\n    def test_x(self):\n        self.assertTrue(True)\n"
    assert "test client" in pipeline.check_tests(no_client, card)
    raising = VIEW_TESTS.replace("self.assertEqual(r.status_code, 405)",
                                 "with self.assertRaises(ValueError):\n            pass")
    assert "does not raise" in pipeline.check_tests(raising, card)
    wrong_name = VIEW_TESTS.replace("sales:ship_sale_view", "sales:other")
    assert "must call reverse" in pipeline.check_tests(wrong_name, card)
    assert pipeline.check_tests(VIEW_TESTS, card) is None


def _add_create_view(ws):
    with open(ws / "sales/views.py", "a") as f:
        f.write('''

class SaleCreateView(CreateView):
    model = Sale
    fields = ["customer_name"]
    template_name = "sales/form.html"
    success_url = reverse_lazy("sales:list")
''')
    src = (ws / "sales/views.py").read_text().replace(
        "from django.views.generic import ListView",
        "from django.urls import reverse_lazy\nfrom django.views.generic import CreateView, ListView")
    (ws / "sales/views.py").write_text(src)
    u = (ws / "sales/urls.py").read_text().replace(
        '    path("", views.SaleListView.as_view(), name="list"),',
        '    path("", views.SaleListView.as_view(), name="list"),\n    path("new/", views.SaleCreateView.as_view(), name="create"),')
    (ws / "sales/urls.py").write_text(u)
    (ws / "sales/templates/sales/form.html").write_text(
        '{% extends "sales/base.html" %}{% block content %}<form method="post">{% csrf_token %}'
        '{{ form.as_p }}<button>Save</button></form>{% endblock %}\n')


CLASS_CARD = {"app": "sales", "kind": "view", "class": "SaleCreateView", "name": "form_valid",
              "url_name": "sales:create",
              "spec": "form_valid refuses a customer_name of 'blocked': it adds the error 'Customer is blocked' "
                      "to the form, shows the form again and creates no Sale. Any other name is saved and the "
                      "page redirects to sales:list."}

CLASS_TESTS = '''
from django.test import TestCase
from django.urls import reverse
from sales.models import Sale


class SaleCreateFormTests(TestCase):
    def test_blocked_name_is_refused(self):
        r = self.client.post(reverse("sales:create"), {"customer_name": "blocked"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("Customer is blocked", r.context["form"].non_field_errors())
        self.assertEqual(Sale.objects.count(), 0)

    def test_other_name_is_saved(self):
        r = self.client.post(reverse("sales:create"), {"customer_name": "Ann"})
        self.assertRedirects(r, reverse("sales:list"))
        self.assertEqual(Sale.objects.get().customer_name, "Ann")

    def test_name_blocked_with_other_case_is_saved(self):
        r = self.client.post(reverse("sales:create"), {"customer_name": "Blocked"})
        self.assertRedirects(r, reverse("sales:list"))
        self.assertEqual(Sale.objects.filter(customer_name="Blocked").count(), 1)
'''

CLASS_IMPL = '''def form_valid(self, form):
    if form.cleaned_data["customer_name"] == "blocked":
        form.add_error(None, "Customer is blocked")
        return self.form_invalid(form)
    return super().form_valid(form)
'''


def test_view_card_adds_a_method_to_an_existing_view_class(ws, monkeypatch):
    _add_create_view(ws)
    _commit_all(ws)
    ok, problems = rules_mod.validate_cards(ws, [CLASS_CARD])
    assert len(ok) == 1 and not problems
    use(monkeypatch, Fake([CLASS_TESTS], [CLASS_IMPL]))
    r = pipeline.run_card(ws, CLASS_CARD, "fake", log=quiet)
    assert r["status"] == "passed", r["reason"]
    src = (ws / "sales/views.py").read_text()
    assert "def form_valid" in src and src.index("class SaleCreateView") < src.index("def form_valid")
    assert "sales/urls.py" not in r["files"]  # an existing route: nothing to wire


def test_validate_view_cards(ws):
    _add_create_view(ws)
    bad = [dict(CLASS_CARD, **{"class": "Ghost"}), dict(CLASS_CARD, url_name="sales:ghost"),
           dict(CLASS_CARD, name="get_success_url", url_name=""), dict(VIEW_CARD, url="ship"),
           dict(VIEW_CARD, name="SaleListView")]
    ok, problems = rules_mod.validate_cards(ws, [VIEW_CARD, CLASS_CARD] + bad)
    assert [c["name"] for c in ok] == ["ship_sale_view", "form_valid"] and len(problems) == len(bad)


def test_view_class_source_is_shown_to_the_model(ws, monkeypatch):
    _add_create_view(ws)
    _commit_all(ws)
    seen = []
    fake = Fake([CLASS_TESTS], [CLASS_IMPL])
    real = fake.__call__

    def spy(**kw):
        seen.append(kw["messages"][1]["content"])
        return real(**kw)
    use(monkeypatch, spy)
    r = pipeline.run_card(ws, CLASS_CARD, "fake", log=quiet)
    assert r["status"] == "passed", r["reason"]
    assert all("class SaleCreateView(CreateView)" in m and "fields = " in m for m in seen)


# ---------- v15: what the real run of the three view cards showed ----------
def test_view_tests_with_mocks_are_bounced(ws):
    mocked = VIEW_TESTS.replace("from django.urls import reverse",
                                "from django.urls import reverse\nfrom unittest.mock import patch")
    assert "do not mock" in pipeline.check_tests(mocked, dict(VIEW_CARD))


def test_wrong_reason_message_names_the_test_line(ws):
    bad = VIEW_TESTS.replace('stock=stock)', 'stock=stock, bogus_field=1)')
    (ws / "sales/test_x.py").write_text(bad)
    r = pipeline.run_suite(ws)
    ok, why = pipeline.classify_red(r["output"], r["ok"], "ship_sale_view")
    assert not ok and "on the line `" in why and "never mock" in why


def test_view_note_has_a_worked_skeleton_and_form_rules():
    note = pipeline.kind_note(VIEW_CARD)
    assert "def test_refused_by_the_rule" in note and "never use mock" in note.lower()
    assert "assert it is still True" in note
    cls_note = pipeline.kind_note(CLASS_CARD)
    assert "post EVERY field" in cls_note and "non_field_errors" in cls_note


def test_same_assertion_failure_five_times_blames_the_tests(ws, monkeypatch):
    # tests that contradict themselves: nothing the code does can make them pass
    contradictory = GOOD_TESTS.replace('self.assertEqual(self.make("5.00", 3).line_total(), Decimal("15.00"))',
                                       'self.assertEqual(self.make("5.00", 3).quantity, 99)')
    impls = [f"def line_total(self):\n    # try {i}\n    return self.product.price * self.quantity\n"
             for i in range(12)]
    use(monkeypatch, Fake([contradictory], impls))
    monkeypatch.setattr(pipeline, "classify_red", lambda *a, **k: (True, ""))
    r = pipeline.run_card(ws, CARD, "fake", attempts=1, log=quiet)
    assert r["status"] == "failed" and "Probably a test is wrong" in r["reason"]
    assert git_clean(ws)


def test_fake_mock_by_reassigning_a_function_is_bounced(ws):
    fake = VIEW_TESTS + "\n# x\ndef mock_create_sale(*a):\n    raise ValueError('x')\n"
    assert "do not mock" in pipeline.check_tests(fake, dict(VIEW_CARD))


def test_form_view_tests_must_not_look_for_messages_unless_the_rule_says_so(ws):
    card = dict(VIEW_CARD, **{"class": "SaleCreateView", "url_name": "sales:ship_sale_view",
                              "spec": "form_valid adds the error to the form with form.add_error"})
    code = VIEW_TESTS + "\n    def shown(self, r):\n        return list(get_messages(r.wsgi_request))\n"
    why = pipeline.check_tests(code, card)
    assert why and "FORM" in why


# ---------- v17: self-repair and ship ----------
def _fake_chat_spec(spec):
    return lambda **kw: NS(message=NS(content=json.dumps({"spec": spec})))


def test_repair_spec_returns_a_new_valid_rule(ws):
    new = rules_mod.repair_spec(ws, dict(CARD), "the same failure happened 5 times", "m",
                                chat_fn=_fake_chat_spec("line_total returns unit price times quantity; "
                                                        "tests must not assert any other value."))
    assert new and "tests must not assert" in new


def test_repair_spec_rejects_unchanged_or_short(ws):
    same = _fake_chat_spec(CARD["spec"])
    assert rules_mod.repair_spec(ws, dict(CARD), "x", "m", chat_fn=same) is None
    assert rules_mod.repair_spec(ws, dict(CARD), "x", "m", chat_fn=_fake_chat_spec("short")) is None


def test_repairable_skips_fields_and_red_baselines():
    assert not rules_mod.repairable({"kind": "field"}, "anything")
    assert not rules_mod.repairable({"kind": "model"}, "the existing tests are not green, fix them first")
    assert rules_mod.repairable({"kind": "model"}, "the same failure happened 5 times")


def test_failed_card_is_retried_with_a_rewritten_rule(ws, monkeypatch):
    # first run: the model's tests are weak and every attempt fails; after the rewrite it passes
    use(monkeypatch, Fake([WEAK_TESTS] * 5 + [GOOD_TESTS], [GOOD_IMPL] * 6))
    monkeypatch.setitem(auto.CFG, "card_attempts", 5)
    seen = []

    def fix(w, card, reason, model):
        seen.append(reason)
        return "line_total returns unit price times quantity. Check the exact product of price and quantity."
    state = {"done": [], "failed": {}, "declined": []}
    out = []
    st = auto.run_cards(ws, [dict(CARD)], "fake", yes=True, state=state, log=out.append, repair=1,
                        repair_fn=fix)
    assert seen and st["done"] and "repaired" in st
    assert any("rewrote the rule" in str(l) for l in out)


def test_repair_is_off_when_zero_rounds(ws, monkeypatch):
    use(monkeypatch, Fake([WEAK_TESTS] * 5, [GOOD_IMPL] * 5))
    called = []
    st = auto.run_cards(ws, [dict(CARD)], "fake", yes=True,
                        state={"done": [], "failed": {}, "declined": []}, log=quiet, repair=0,
                        repair_fn=lambda *a: called.append(1))
    assert not called and not st["done"] and st["failed"]


def _git(ws, *a):
    return subprocess.run(["git", *a], cwd=ws, capture_output=True, text=True).stdout.strip()


def test_ship_merges_tests_writes_handoff_and_backs_up(ws, monkeypatch, tmp_path):
    use(monkeypatch, Fake([GOOD_TESTS], [GOOD_IMPL]))
    cf = tmp_path / "cards.json"
    cf.write_text(json.dumps({"cards": [CARD]}))
    assert auto.main(["auto", "--workspace", str(ws), "--cards", str(cf), "--yes", "--no-preflight"]) == 0
    branch = _git(ws, "branch", "--show-current")
    assert branch.startswith("auto/")
    bdir = tmp_path / "backups"
    msgs = []
    from workforce import ship
    args = NS(workspace=str(ws), branch=None, backup_dir=str(bdir))
    assert ship.run_ship(args, out=msgs.append) == 0, msgs
    assert _git(ws, "branch", "--show-current") in ("master", "main")
    assert "def line_total" in (ws / "sales/models.py").read_text()
    assert branch not in _git(ws, "branch")
    assert "Shipped" in (ws / "HANDOFF.md").read_text()
    assert len(list(bdir.glob("*.tar.gz"))) == 1
    assert git_clean(ws)
    # shipping again has nothing to do
    assert ship.run_ship(args, out=msgs.append) == 1


def test_ship_refuses_a_dirty_tree(ws, tmp_path):
    from workforce import ship
    (ws / "x.txt").write_text("x")
    msgs = []
    assert ship.run_ship(NS(workspace=str(ws), branch=None, backup_dir=str(tmp_path)), out=msgs.append) == 1
    assert "uncommitted" in msgs[0]


def test_ship_undoes_the_merge_when_tests_fail(ws, monkeypatch, tmp_path):
    from workforce import ship
    _git(ws, "checkout", "-q", "-b", "auto/x")
    (ws / "sales/test_broken.py").write_text(
        "from django.test import TestCase\nclass T(TestCase):\n    def test_x(self):\n        self.assertTrue(False)\n")
    _git(ws, "add", "-A")
    _git(ws, "-c", "user.name=a", "-c", "user.email=a@b", "commit", "-qm", "auto: broken")
    st = {"done": [], "failed": {}, "declined": [], "branch": "auto/x"}
    monkeypatch.setattr(auto, "load_state", lambda: st)
    msgs = []
    assert ship.run_ship(NS(workspace=str(ws), branch=None, backup_dir=str(tmp_path)), out=msgs.append) == 1
    assert not (ws / "sales/test_broken.py").exists()
    assert "auto/x" in _git(ws, "branch")
