"""One card = one small piece of business logic, built test-first.

The model writes tests -> Python checks they fail for the right reason and locks them ->
the model writes the code -> Python checks the whole suite, the lock, the names and a
mutation score. The model never decides pass or fail."""
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import textwrap
import time
from pathlib import Path

from . import codetools, mutation, wiring
from .config import CFG
from .notes import project_map
from .tools import python_problem, undefined_names
from .worker import run_worker

PROMPTS = Path(__file__).parent.parent / "prompts"


JUNK_WORDS = ("invalid", "malformed", "wrong", "garbage", "junk")


# ---------- cards ----------
def card_id(c):
    tag = f"_{c['tag']}" if c.get("tag") else ("_tile" if c.get("kind") == "tile" else "")
    return f"{c['app']}_{(c.get('class') or 'func')}_{c['name']}{tag}".lower()


def test_file(ws, c):
    tag = f"_{c['tag']}" if c.get("tag") else ""
    return Path(ws) / c["app"] / f"test_{(c.get('class') or 'func').lower()}_{c['name']}{tag}.py"


def target_file(ws, c):
    name = {"model": "models.py", "view": "views.py"}.get(c["kind"], "services.py")
    return Path(ws) / c["app"] / name


# ---------- running tests ----------
def _cfg(ws):
    p = Path(ws) / ".workforce.json"
    return json.loads(p.read_text()) if p.exists() else {}


def run_suite(ws, label=None, timeout=240):
    cmd = list(_cfg(ws).get("test_cmd") or ["python", "-m", "pytest", "-q"])
    if cmd[0] == "python":
        cmd[0] = sys.executable
    if label:
        cmd.append(label)
    # Files are rewritten many times per second (mutation checks). Python's bytecode cache keys on
    # mtime in whole seconds + size, so it can serve a stale mutant. Never trust it here.
    for pyc in Path(ws).glob("*/__pycache__/*.pyc"):
        pyc.unlink(missing_ok=True)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    try:
        r = subprocess.run(cmd, cwd=ws, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return {"ok": False, "ran": 0, "output": "TIMEOUT: tests took too long"}
    out = r.stdout + r.stderr
    m = re.search(r"Ran (\d+) tests?", out) or re.search(r"(\d+) passed", out)
    return {"ok": r.returncode == 0, "ran": int(m.group(1)) if m else 0, "output": out}


def card_label(ws, c, wide=False):
    """What to pass to the test command to run only this card's tests.
    wide=True runs every test of the app (used when a card changes existing code)."""
    cmd = _cfg(ws).get("test_cmd") or []
    if wide:
        return c["app"]
    if any("manage.py" in x for x in cmd):
        return f"{c['app']}.{test_file(ws, c).stem}"
    return str(test_file(ws, c).relative_to(ws))


# ---------- checking the tests the model wrote ----------
def check_tests(code, card):
    problem = codetools.safety_problem(code) or python_problem(code)
    if problem:
        return problem
    tree = ast.parse(code)
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and n.name.startswith("test"):
            return "put the tests inside a class that extends TestCase, not at module level"
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and any(
        (getattr(b, "id", None) or getattr(b, "attr", "")).endswith("TestCase") for b in n.bases)]
    if not classes:
        return "no test class found. Use: class SomethingTests(TestCase): with methods named test_..."
    methods = [m for c in classes for m in c.body
               if isinstance(m, ast.FunctionDef) and m.name.startswith("test_")]
    if not 1 <= len(methods) <= 8:
        return f"write between 1 and 8 test methods (you wrote {len(methods)})"
    for m in methods:
        has_assert = any(isinstance(x, ast.Assert) or (
            isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute)
            and x.func.attr.startswith("assert")) for x in ast.walk(m))
        if not has_assert:
            return f"{m.name} does not check anything. Add an assertEqual with an exact expected value"
    if card["kind"] == "view":
        bad = _check_view_tests(code, card)
        if bad:
            return bad
    elif card["name"] not in code:
        return f"the tests never mention '{card['name']}'"
    if "assertRaises" in code and card["kind"] != "view" and not re.search(r"rais|error|exception|fail|invalid", card["spec"], re.I):
        return ("the rule does not mention any error, so do not use assertRaises. Test only what the "
                "rule says. Do not invent errors, messages or extra behaviour.")
    spec_low = card["spec"].lower()
    for m in methods:
        for w in JUNK_WORDS:
            if w in m.name.lower() and w not in spec_low:
                return (f"{m.name} tests '{w}' input, but the rule never mentions that. Test only "
                        "what the rule says; do not invent extra checks.")
    for lit in re.findall(r"""["']([^"']*)["']""", code):
        for w in JUNK_WORDS:
            if w in lit.lower() and w not in spec_low and " " not in lit.strip():
                return (f"the test uses the value '{lit}', an invalid input the rule never mentions. "
                        "Test only what the rule says.")
    if card["kind"] == "service":
        imported = any(isinstance(n, ast.ImportFrom) and (n.module or "").endswith("services")
                       and any(a.name == card["name"] for a in n.names) for n in ast.walk(tree))
        if not imported:
            return (f"import the function first: from {card['app']}.services import {card['name']} "
                    "(it is a plain function, not a method)")
        for n in ast.walk(tree):
            if isinstance(n, ast.Attribute) and n.attr == card["name"] and not (
                    isinstance(n.value, ast.Name) and n.value.id == "services"):
                return f"'{card['name']}' is a plain function, call it as {card['name']}(...), not obj.{card['name']}(...)"
    if card["kind"] == "model":
        parents = {id(c): p for p in ast.walk(tree) for c in ast.iter_child_nodes(p)}
        for n in ast.walk(tree):
            if isinstance(n, ast.Attribute) and n.attr == card["name"]:
                par = parents.get(id(n))
                if not (isinstance(par, ast.Call) and par.func is n):
                    return (f"'{card['name']}' is a METHOD: call it with parentheses, "
                            f"for example item.{card['name']}()")
    und = undefined_names(code)
    if und:
        return und[0] + " (add the missing import)"
    return None


def _check_view_tests(code, card):
    expected = card.get("url_name") or f"{card['app']}:{card['name']}"
    if "self.client" not in code:
        return "call the page through the test client, for example self.client.post(reverse('app:name', args=[obj.pk]))"
    if "reverse(" not in code:
        return "get the address with reverse('app:name'), never type the URL by hand"
    if expected not in code:
        return f"the tests must call reverse('{expected}')"
    if re.search(r"mock|patch", code, re.I):
        return ("do not mock or patch anything. Create real rows in the test database and let the real "
                "service run")
    if card.get("class") and "get_messages" in code and "messages" not in card.get("spec", "").lower():
        return ("this rule shows errors on the FORM, not as messages. Check "
                "response.context['form'].non_field_errors(), not get_messages")
    if "assertRaises" in code:
        return ("a view does not raise errors to the user. Test the response instead: status code, "
                "redirect, the saved data and the messages")
    return None


def count_tests(code):
    tree = ast.parse(code)
    return sum(1 for c in tree.body if isinstance(c, ast.ClassDef)
               for m in c.body if isinstance(m, ast.FunctionDef) and m.name.startswith("test_"))


ERR_LINE = re.compile(r"^(?:[A-Za-z_]\w*\.)*[A-Z]\w*(?:Error|Exception|Operation|DoesNotExist|NoReverseMatch|"
                      r"Invalid\w*|Warning|Exists|Denied|Refused)\b")


GENERIC_ERR = re.compile(r"^(?:[A-Za-z_]\w*\.)*[A-Z]\w*(?::|$)")


def _is_err(line):
    """Last line of a traceback: an exception name (dotted or not), optionally followed by ': message'."""
    line = line.strip()
    if line.startswith(("ERROR:", "FAIL:")):
        return False
    return bool(ERR_LINE.match(line) or GENERIC_ERR.match(line)) or line.startswith("AssertionError")


def failing_tests(output):
    """-> [(test_name, final_error_line)] parsed from Django/unittest output."""
    out = []
    for m in re.finditer(r"^(?:ERROR|FAIL): (\w+) \(.*?(?=^={10,}|\Z)", output, re.M | re.S):
        block = m.group(0)
        errs = [l.strip() for l in block.splitlines() if _is_err(l)]
        out.append((m.group(1), (errs[-1] if errs else "failed")[:220]))
    return out


def summarize(output, limit=1500):
    """A short, readable failure summary for the small model, including the failing test line."""
    fails = failing_tests(output)
    if not fails:
        return output[-limit:]
    lines = [f"{len(fails)} test(s) failed:"] + [f"- {n}: {e}" for n, e in fails]
    seen = set()
    for m in re.finditer(r'File "[^"]*?(test_\w+\.py)", line (\d+), in (\w+)\n\s+(.+)', output):
        if m.group(3) not in seen:
            seen.add(m.group(3))
            lines.append(f"  {m.group(3)} failed on this line of the test: {m.group(4).strip()[:150]}")
    for l in output.splitlines():
        if l.strip().startswith("File") and "site-packages" not in l and "/usr/" not in l \
                and ("models.py" in l or "services.py" in l):
            lines.append(l.strip()[:160])
    return "\n".join(lines)[:limit]


def test_error(output, name=""):
    """If the failing tests crash on a line of the TEST file itself (not an assertion, not inside the
    code under test), return (test_name, error, line). The code cannot fix that: the test is wrong."""
    found = None
    for m in re.finditer(r"^(?:ERROR|FAIL): (\w+) \(.*?(?=^={10,}|\Z)", output, re.M | re.S):
        block = m.group(0)
        frames = re.findall(r'File "([^"]+)", line (\d+), in \w+\n\s+(.+)', block)
        errs = [l.strip() for l in block.splitlines() if _is_err(l)]
        if not frames or not errs or errs[-1].startswith("AssertionError"):
            return None
        if name and name in errs[-1]:
            continue  # "the thing does not exist" is the code's job, not a broken test
        path, _, text = frames[-1]
        if not Path(path).name.startswith("test_"):
            return None
        found = (m.group(1), errs[-1][:160], text.strip()[:140])
    return found


def _missing(text, name):
    """The error is just 'the thing being built does not exist yet'."""
    return bool(re.search(rf"(AttributeError|ImportError|ModuleNotFoundError)[^\n]*"
                          rf"({re.escape(name)}|\.services)", text)
                or re.search(rf"NoReverseMatch[^\n]*{re.escape(name)}", text))


def classify_red(output, ok, name):
    """Every test must fail because the feature is missing, never for another reason."""
    if ok:
        return False, ("these tests already pass, so they do not test anything new. "
                       f"Test the behaviour of '{name}', which does not exist yet.")
    if "SyntaxError" in output or "NameError" in output:
        return False, "the tests have an error: " + _last_error(output)
    fails = failing_tests(output)
    if not fails:
        if _missing(output, name):
            return True, ""
        return False, "the tests could not run: " + _last_error(output)
    lines = test_lines(output)
    for tname, err in fails:
        if err.startswith("AssertionError") or _missing(err, name):
            continue
        where = f" on the line `{lines[tname]}`" if tname in lines else ""
        return False, (f"{tname} fails for the wrong reason: {err}{where}. A test must fail only because "
                       f"'{name}' is missing. Create every required related row (a SaleItem needs "
                       "both a sale and a product), never create rows with missing required fields, and "
                       "never mock anything.")
    return True, ""


def test_lines(output):
    """{test_name: the last line of the TEST file that ran when it failed}"""
    out = {}
    for m in re.finditer(r"^(?:ERROR|FAIL): (\w+) \(.*?(?=^={10,}|\Z)", output, re.M | re.S):
        frames = re.findall(r'File "([^"]+)", line \d+, in \w+\n\s+(.+)', m.group(0))
        mine = [t for f, t in frames if Path(f).name.startswith("test_")]
        if mine:
            out[m.group(1)] = mine[-1].strip()[:140]
    return out


def _last_error(output):
    errs = [l for l in output.splitlines() if re.match(r"\w*(Error|Exception|NoReverseMatch)\b", l)]
    return errs[-1][:200] if errs else output[-200:]


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def kind_note(card):
    n = card["name"]
    if card["kind"] == "view":
        return _view_note(card)
    if card["kind"] == "model":
        return (f"\nThe feature is a METHOD of {card['class']}. Tests call it with parentheses, for "
                f"example obj.{n}(). Never write obj.{n} without parentheses. In your code write a "
                "normal def with self (no @property).\n")
    return (f"\nThe feature is a plain FUNCTION in {card['app']}/services.py, NOT a method of any model. "
            f"Tests import it with: from {card['app']}.services import {n}   and call it as a function, "
            f"for example {n}(product, 3). Never call it as product.{n}(...).\n")


def current_source(ws, card):
    """The code of the function a 'change' card modifies (None if it is not there)."""
    target = target_file(ws, card)
    if not target.exists():
        return None
    src = target.read_text()
    fn = codetools.find_def(ast.parse(src), card["name"], card.get("class") or None)
    if fn is None:
        return None
    s, e = codetools._span(fn)
    return textwrap.dedent("\n".join(src.splitlines()[s:e]))


def view_source(ws, card):
    """For a card that adds a method to a view class: the class and its FIELDS, so the model sees which
    form fields exist and which model the form saves."""
    if card.get("kind") != "view" or not card.get("class"):
        return ""
    src = target_file(ws, card).read_text()
    tree = ast.parse(src)
    parts = []
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "FIELDS" for t in n.targets):
            parts.append(ast.get_source_segment(src, n))
        if isinstance(n, ast.ClassDef) and n.name == card["class"]:
            parts.append(ast.get_source_segment(src, n))
    return "\nThe view code today (views.py):\n" + "\n\n".join(p for p in parts if p) + "\n"


def change_note(ws, card, phase):
    if card.get("mode") != "change":
        return ""
    cur = current_source(ws, card) or ""
    if phase == "tests":
        how = ("Write tests ONLY for the NEW behaviour that the rule adds. The tests of the old "
               "behaviour already exist. Your tests must fail against the current code.")
    else:
        how = ("Send the complete new version of this function: keep everything it does today and "
               "add the new behaviour. The old tests must keep passing too.")
    return f"\nThis card CHANGES an existing function. Its current code is:\n{cur}\n{how}\n"


VIEW_SKELETON = '''
Use this shape for the test file (replace the examples with the rows and names of THIS card):

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
# import the models you need

class SomethingViewTests(TestCase):
    def setUp(self):
        # create REAL rows with Model.objects.create(...), keep them in self.xxx
        ...

    def shown(self, response):
        return [(m.level_tag, str(m)) for m in get_messages(response.wsgi_request)]

    def test_success(self):
        response = self.client.post(reverse("app:name", args=[self.obj.pk]))
        self.assertRedirects(response, reverse("app:list"))
        self.assertEqual(self.shown(response), [("success", "the success text from the rule")])
        # then: obj.refresh_from_db() and assertEqual on the stored value that really changed

    def test_refused_by_the_rule(self):
        # set up data so the service really refuses (for example not enough stock), do NOT patch anything
        response = self.client.post(reverse("app:name", args=[self.other.pk]))
        self.assertRedirects(response, reverse("app:list"))
        self.assertEqual([level for level, text in self.shown(response)], ["error"])  # never guess the error text
        # then: refresh_from_db() and assert the values are STILL what you set up (never the opposite)

    def test_get_is_refused(self):
        response = self.client.get(reverse("app:name", args=[self.obj.pk]))
        self.assertEqual(response.status_code, 405)

Rules: never use mock or patch. A set-up value and its later assertion must agree: if you create a sale with
confirmed=True and the action is refused, assert it is still True.
'''


CLASS_SKELETON = '''
For a form view, post EVERY field listed in FIELDS (shown below). Send dates as text like "2023-10-05",
related rows by primary key (customer.pk) and numbers as text like "0". Check the shown-again form with
response.context["form"].non_field_errors() and a successful save with assertRedirects. Never mock.
Create real rows in setUp (for example a customer) and never assert the opposite of what you set up.
Never replace or reassign a function in the test (that does nothing). To make a service refuse, set up REAL
data that makes it refuse (for example a customer with is_active=False). Use a NEW unique value for every
unique field you post (a number that no existing row has).
Example of the shown-again check:
    response = self.client.post(reverse("app:create"), {"number": "N1", "date": "2023-10-05",
                                "customer": inactive.pk, "total": "0"})
    self.assertEqual(response.status_code, 200)
    self.assertTrue(response.context["form"].non_field_errors())
    self.assertEqual(Sale.objects.count(), 0)
'''


def _view_note(card):
    base = ("\nThe feature is part of a Django VIEW in {app}/views.py. Test it ONLY through the test client "
            "and reverse(...). To read messages shown to the user use: "
            "from django.contrib.messages import get_messages ; "
            "msgs = [str(m) for m in get_messages(response.wsgi_request)]. "
            "A redirect is checked with self.assertRedirects(response, reverse('app:list')).\n").format(app=card["app"])
    if card.get("class"):
        return CLASS_SKELETON + base + (f"It is the method {card['name']}(self, ...) of the existing class {card['class']}. "
                       f"Tests call the page with reverse('{card['url_name']}'). Send form data with "
                       "self.client.post(url, {...}); a form that is shown again has status 200 and "
                       "response.context['form'].errors. Write ONE method with self as first argument.\n")
    inp = ""
    if card.get("input"):
        inp = (f"The page posts ONE text field named {card['input']}. Tests send it like "
               f"self.client.post(url, {{'{card['input']}': '10.00'}}) and the view reads it with "
               f"request.POST.get('{card['input']}', ''). Test one value that is not a number too, "
               "for example 'abc'. IMPORTANT for the code: Decimal('abc') raises decimal.InvalidOperation, NOT "
               "ValueError. Use: from decimal import Decimal, InvalidOperation ; try: amount = "
               f"Decimal(request.POST.get('{card['input']}', '')) ; except InvalidOperation: show the "
               "error message and redirect. In a test, to make the service refuse, set up REAL data that "
               "it refuses (read its rule) and assert that nothing was created.\n")
    return VIEW_SKELETON + inp + base + (f"It is a plain FUNCTION view {card['name']}(request, pk) (no class). Tests call it with "
                   f"reverse('{card['app']}:{card['name']}', args=[obj.pk]). "
                   "In your code: from django.contrib import messages ; "
                   "from django.shortcuts import get_object_or_404, redirect ; "
                   "from django.views.decorators.http import require_POST ; decorate the view with "
                   "@require_POST (so a GET gives status 405); on success call messages.success(request, ...); "
                   "when the service raises ValueError call messages.error(request, str(e)); "
                   "always redirect (redirect('app:list')).\n")


def _prompt(name, card=None):
    return (PROMPTS / name).read_text() + (kind_note(card) if card else "")


# ---------- the two phases ----------
def phase_tests(ws, card, model, feedback):
    path, label = test_file(ws, card), card_label(ws, card)
    state = {"written": set(), "tests_passed": False}

    def show_models() -> str:
        """Show the models, fields and relations of the project."""
        return project_map(ws)

    def write_tests(code: str) -> str:
        """Write the complete test file for this card.

        Args:
            code: The full Python source of the test file.
        """
        problem = check_tests(code, card)
        if problem:
            return "REJECTED: " + problem
        path.write_text(code.rstrip("\n") + "\n")
        r = run_suite(ws, label)
        good, why = classify_red(r["output"], r["ok"], card["name"])
        if not good:
            path.unlink()
            if card.get("mode") == "change" and "already pass" in why:
                why = ("these tests already pass on the current code, so they do not test the NEW "
                       "behaviour. Test only what the rule adds, with inputs the current code gets wrong.")
            return "REJECTED: " + why
        state["wrote"] = True
        state["written"].add(str(path))
        return ("OK: the tests fail as they should, because the feature does not exist yet. "
                "Reply DONE.")

    task = (f"Card: {card['kind']} {card.get('class') or ''}.{card['name']}\n"
            f"Rule: {card['spec']}\n\nProject:\n{project_map(ws)}\n"
            + change_note(ws, card, "tests") + view_source(ws, card))
    if feedback:
        task += f"\nLast attempt failed because: {feedback}\n"
    res = run_worker(model=model, system=_prompt("card_tests.txt", card), task=task,
                     tools=[show_models, write_tests], state=state, max_steps=8,
                     require_tests=False,
                     finish_check=lambda: [] if state.get("wrote") else
                     ["you have not written valid tests yet; call write_tests"])
    if not (state.get("wrote") and path.exists()):
        return None, "the model did not produce acceptable tests"
    return count_tests(path.read_text()), None


def phase_impl(ws, card, model, feedback):
    target = target_file(ws, card)
    state = {"written": set(), "tests_passed": False, "undefined": {}}
    cls = card.get("class") or None
    if not target.exists():
        target.write_text('"""Business logic functions."""\n')

    def refresh_undefined():
        und = undefined_names(target.read_text())
        base = state.setdefault("base_und", set())
        new = [u for u in und if _und_name(u) not in base]
        state["undefined"] = {str(target): new[0]} if new else {}
        return new

    state["base_und"] = {_und_name(u) for u in undefined_names(target.read_text())}

    def show_models() -> str:
        """Show the models, fields and relations of the project."""
        return project_map(ws)

    def _apply(new, err):
        if err:
            return "REJECTED: " + err
        if card["kind"] == "view" and not cls and \
                codetools.find_def(ast.parse(new), card["name"]) is not None:
            bad = wiring.wire_url(ws, card["app"], card["url"], card["name"])
            if bad:
                return "REJECTED: " + bad
        target.write_text(new)
        state["written"].add(str(target))
        state["tests_passed"] = False
        new_und = refresh_undefined()
        return "Saved." + (f" WARNING: {new_und[0]} (add the missing import)" if new_und else "")

    def _check_name(code):
        fn, err = codetools.one_def(code)
        if err:
            return err
        exists = codetools.find_def(ast.parse(target.read_text()), fn.name, cls) is not None
        if fn.name != card["name"] and (fn.name.startswith("_") is False or exists):
            return (f"you may only define '{card['name']}' (or a new helper whose name starts "
                    f"with an underscore), not '{fn.name}'")
        return None

    def _with_imports(code, place):
        """The model often sends 'import ...' lines together with the function. Accept that: Python
        moves the imports to the top of the file and saves the function."""
        imps, rest = codetools.split_imports(code)
        for stmt in imps:
            new, err = codetools.add_import(target.read_text(), stmt)
            if err:
                return "REJECTED: " + err
            target.write_text(new)
        err = _check_name(rest)
        if err:
            return "REJECTED: " + err
        return _apply(*place(rest))

    def set_method(code: str) -> str:
        """Save the method for this card (replaces it if it exists). Send ONE complete method.

        Args:
            code: The complete method, starting with def and with self as the first argument.
        """
        return _with_imports(code, lambda c: codetools.upsert_def(target.read_text(), c, cls))

    def set_function(code: str) -> str:
        """Save the function for this card (replaces it if it exists). Send ONE complete function.

        Args:
            code: The complete function, starting with def.
        """
        return _with_imports(code, lambda c: codetools.upsert_def(target.read_text(), c))

    def add_import(statement: str) -> str:
        """Add one import line to the file, for example: from decimal import Decimal

        Args:
            statement: One import statement.
        """
        return _apply(*codetools.add_import(target.read_text(), statement))

    def run_tests() -> str:
        """Run all project tests and show the result."""
        r = run_suite(ws)
        state["tests_passed"] = r["ok"]
        state["last_fail"] = "" if r["ok"] else summarize(r["output"], 500)
        if r["ok"]:
            return "OK, all tests pass. Reply DONE."
        out = summarize(r["output"])
        te = test_error(r["output"], card["name"])
        if te:
            k = state.setdefault("test_errs", {})
            k[te] = k.get(te, 0) + 1
            if k[te] >= 4:
                state["abort"] = ("the locked test itself crashes: " + te[1] + " on its line `" + te[2] +
                                  "` (" + te[0] + "). Write tests that do not do that")
        seen = state.setdefault("fail_counts", {})
        seen[out] = seen.get(out, 0) + 1
        if seen[out] >= 5:
            first = out.splitlines()[1] if len(out.splitlines()) > 1 else out
            state["abort"] = ("the same failure happened " + str(seen[out]) + " times with different code (" +
                              first.strip()[:200] + "). Probably a test is wrong: it must not contradict its "
                              "own set-up (for example creating something with confirmed=True and then "
                              "asserting it is False), must not guess texts it cannot know, and must test "
                              "only what the rule says")
        if seen[out] >= 2:
            out += ("\nTHIS EXACT FAILURE HAPPENED " + str(seen[out]) + " TIMES. Your approach is wrong. "
                    "Read the failing test line again. If the test expects data to be unchanged, your code "
                    "must raise BEFORE it changes or saves anything: move every check to the top.")
        return out

    tools = [show_models, set_method if cls else set_function, add_import, run_tests]
    tests_src = test_file(ws, card).read_text()
    task = (f"Card: {card['kind']} {cls or ''}.{card['name']}\nRule: {card['spec']}\n\n"
            f"Project:\n{project_map(ws)}\n\nLocked tests that must pass:\n{tests_src}\n"
            + change_note(ws, card, "impl") + view_source(ws, card))
    if feedback:
        task += f"\nLast attempt failed because: {feedback}\n"
    res = run_worker(model=model, system=_prompt("card_impl.txt", card), task=task, tools=tools,
                     state=state, max_steps=CFG["max_steps"], require_tests=True)
    return res, state


def _und_name(line):
    m = re.search(r"undefined name '(\w+)'", line)
    return m.group(1) if m else line


# ---------- the gates (only Python decides) ----------
def mutation_score(ws, card, limit=8):
    target = target_file(ws, card)
    original = target.read_text()
    muts = mutation.mutants(original, card["name"], card.get("class") or None, limit)
    if not muts:
        return 1.0, [], 0
    label = card_label(ws, card, wide=card.get("mode") == "change")
    survived = []
    try:
        for desc, src in muts:
            target.write_text(src)
            r = run_suite(ws, label, timeout=90)
            if r["ok"]:
                survived.append(desc)
    finally:
        target.write_text(original)
    return 1 - len(survived) / len(muts), survived, len(muts)


def _survivor_hints(survived):
    tips = []
    for d in survived[:3]:
        m = re.search(r"changed the number (-?\d+)\b", d)
        if m:
            n = int(m.group(1))
            tips.append(f"{d}: add tests whose input is exactly {n} and exactly {n + 1}")
        elif "removed a statement" in d:
            tips.append(f"{d}: after calling the code, re-load the object with obj.refresh_from_db() "
                        "and check the stored value")
        elif "comparison" in d:
            tips.append(f"{d}: add tests with a value exactly at the comparison limit and one on each side")
        else:
            tips.append(d + ": add a test whose exact expected value depends on this part")
    return "; ".join(tips)


def gates(ws, card, locked_hash, n_new, baseline_ran, state):
    tf, target = test_file(ws, card), target_file(ws, card)
    if not tf.exists() or _sha(tf) != locked_hash:
        return False, "the locked tests were changed", None
    tree = ast.parse(target.read_text())
    if codetools.find_def(tree, card["name"], card.get("class") or None) is None:
        return False, f"'{card['name']}' is not defined in {target.name}", None
    if state.get("undefined"):
        return False, "undefined names: " + "; ".join(state["undefined"].values()), None
    r = run_suite(ws)
    if not r["ok"]:
        return False, "the full test suite fails:\n" + summarize(r["output"], 800), None
    if r["ran"] != baseline_ran + n_new:
        return False, (f"expected {baseline_ran + n_new} tests to run but {r['ran']} ran"), None
    rate, survived, total = mutation_score(ws, card)
    if rate < CFG.get("min_kill_rate", 0.7):
        return False, ("the tests are too weak: " + _survivor_hints(survived)), rate
    return True, "", rate


def run_card(ws, card, model=None, attempts=None, log=print):
    """Build one card. On success the new files are left in place (not committed)."""
    if card.get("kind") == "field":
        from .fields import run_field_card
        return run_field_card(ws, card, log)
    if card.get("kind") == "class":
        from .fields import run_class_card
        return run_class_card(ws, card, log)
    if card.get("kind") == "tile":
        from .dashtiles import run_tile_card
        return run_tile_card(ws, card, log)
    model = model or CFG["model"]
    attempts = attempts or CFG.get("card_attempts", 5)
    ws = Path(ws)
    tf, target = test_file(ws, card), target_file(ws, card)
    t0 = time.time()
    result = {"id": card_id(card), "status": "failed", "attempts": 0, "reason": "",
              "kill_rate": None, "model": model, "files": [], "seconds": 0}

    base = run_suite(ws)
    if not base["ok"]:
        result["reason"] = "the existing tests are not green, fix them first:\n" + base["output"][-600:]
        return result
    original = target.read_text() if target.exists() else None
    urls_py = Path(ws) / card["app"] / "urls.py"
    urls_original = urls_py.read_text() if urls_py.exists() else None

    def restore_urls():
        if urls_original is not None and urls_py.exists():
            urls_py.write_text(urls_original)
    feedback = ""
    budget = CFG.get("card_minutes", 12) * 60
    for n in range(1, attempts + 1):
        if n > 1 and time.time() - t0 > budget:
            log(f"[{result['id']}] time budget of {budget // 60} minutes used, stopping this card")
            feedback = f"stopped after {budget // 60} minutes (last problem: {feedback[:200]})"
            break
        result["attempts"] = n
        log(f"[{result['id']}] attempt {n}: writing tests")
        if tf.exists():
            tf.unlink()
        if original is None:
            target.unlink(missing_ok=True)
        else:
            target.write_text(original)
        restore_urls()
        n_new, why = phase_tests(ws, card, model, feedback)
        if why:
            feedback = why
            continue
        locked = _sha(tf)
        log(f"[{result['id']}] tests locked ({n_new}); writing code")
        res, state = phase_impl(ws, card, model, feedback)
        if res["status"] == "done" and target.exists():
            cleaned = codetools.drop_unused_new_imports(original or "", target.read_text())
            if cleaned != target.read_text():
                target.write_text(cleaned)
                log(f"[{result['id']}] removed imports the code does not use")
        if state.get("abort"):
            feedback = "the previous tests were wrong: " + state["abort"]
            continue
        if res["status"] != "done":
            feedback = ("the code could not satisfy the tests. " + (state.get("last_fail") or "")
                        + " If a test asserts something the rule does not state, do not write that "
                        "test; test only what the rule says.")
            continue
        ok, why, rate = gates(ws, card, locked, n_new, base["ran"], state)
        result["kill_rate"] = rate
        if ok and card["kind"] == "view":
            changed = wiring.apply(ws, card)
            if changed:
                chk = run_suite(ws)
                if not chk["ok"]:
                    for path, text in changed.items():
                        path.write_text(text)
                    ok, why = False, "the pages stopped working after wiring them:\n" + summarize(chk["output"], 600)
        if ok:
            files = [str(target.relative_to(ws)), str(tf.relative_to(ws))]
            if card["kind"] == "view":
                if urls_original is not None and urls_py.read_text() != urls_original:
                    files.append(str(urls_py.relative_to(ws)))
                files += [str(p.relative_to(ws)) for p in changed]
            result.update(status="passed", reason="", files=files)
            result["seconds"] = round(time.time() - t0)
            return result
        feedback = why
    # failed: leave the project exactly as it was, keep the evidence
    if tf.exists():
        keep = ws / ".autopilot" / "failed"
        keep.mkdir(parents=True, exist_ok=True)
        (keep.parent / ".gitignore").write_text("*\n")
        (keep / tf.name).write_text(tf.read_text())
        tf.unlink()
    if original is None:
        target.unlink(missing_ok=True)
    else:
        target.write_text(original)
    restore_urls()
    result["reason"] = feedback
    result["seconds"] = round(time.time() - t0)
    return result
