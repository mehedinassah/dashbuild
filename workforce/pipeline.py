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
import time
from pathlib import Path

from . import codetools, mutation
from .config import CFG
from .notes import project_map
from .tools import python_problem, undefined_names
from .worker import run_worker

PROMPTS = Path(__file__).parent.parent / "prompts"


# ---------- cards ----------
def card_id(c):
    return f"{c['app']}_{(c.get('class') or 'func')}_{c['name']}".lower()


def test_file(ws, c):
    return Path(ws) / c["app"] / f"test_{(c.get('class') or 'func').lower()}_{c['name']}.py"


def target_file(ws, c):
    return Path(ws) / c["app"] / ("models.py" if c["kind"] == "model" else "services.py")


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


def card_label(ws, c):
    """What to pass to the test command to run only this card's tests."""
    cmd = _cfg(ws).get("test_cmd") or []
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
    if card["name"] not in code:
        return f"the tests never mention '{card['name']}'"
    if "assertRaises" in code and not re.search(r"rais|error|exception|fail|invalid", card["spec"], re.I):
        return ("the rule does not mention any error, so do not use assertRaises. Test only what the "
                "rule says. Do not invent errors, messages or extra behaviour.")
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


def count_tests(code):
    tree = ast.parse(code)
    return sum(1 for c in tree.body if isinstance(c, ast.ClassDef)
               for m in c.body if isinstance(m, ast.FunctionDef) and m.name.startswith("test_"))


def failing_tests(output):
    """-> [(test_name, final_error_line)] parsed from Django/unittest output."""
    out = []
    for m in re.finditer(r"^(?:ERROR|FAIL): (\w+) \(.*?(?=^={10,}|\Z)", output, re.M | re.S):
        block = m.group(0)
        errs = [l.strip() for l in block.splitlines() if re.match(r"^[\w.]*(Error|Exception)\b", l.strip())
                or l.strip().startswith("AssertionError")]
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


def _missing(text, name):
    """The error is just 'the thing being built does not exist yet'."""
    return bool(re.search(rf"(AttributeError|ImportError|ModuleNotFoundError)[^\n]*"
                          rf"({re.escape(name)}|\.services)", text))


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
    for tname, err in fails:
        if err.startswith("AssertionError") or _missing(err, name):
            continue
        return False, (f"{tname} fails for the wrong reason: {err}. A test must fail only because "
                       f"'{name}' is missing. Create every required related row (a SaleItem needs "
                       "both a sale and a product) and never create rows with missing required fields.")
    return True, ""


def _last_error(output):
    errs = [l for l in output.splitlines() if re.match(r"\w*(Error|Exception)\b", l)]
    return errs[-1][:200] if errs else output[-200:]


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def kind_note(card):
    n = card["name"]
    if card["kind"] == "model":
        return (f"\nThe feature is a METHOD of {card['class']}. Tests call it with parentheses, for "
                f"example obj.{n}(). Never write obj.{n} without parentheses. In your code write a "
                "normal def with self (no @property).\n")
    return (f"\nThe feature is a plain FUNCTION in {card['app']}/services.py, NOT a method of any model. "
            f"Tests import it with: from {card['app']}.services import {n}   and call it as a function, "
            f"for example {n}(product, 3). Never call it as product.{n}(...).\n")


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
            return "REJECTED: " + why
        state["wrote"] = True
        state["written"].add(str(path))
        return ("OK: the tests fail as they should, because the feature does not exist yet. "
                "Reply DONE.")

    task = (f"Card: {card['kind']} {card.get('class') or ''}.{card['name']}\n"
            f"Rule: {card['spec']}\n\nProject:\n{project_map(ws)}\n")
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

    def set_method(code: str) -> str:
        """Save the method for this card (replaces it if it exists). Send ONE complete method.

        Args:
            code: The complete method, starting with def and with self as the first argument.
        """
        err = _check_name(code)
        if err:
            return "REJECTED: " + err
        return _apply(*codetools.upsert_def(target.read_text(), code, cls))

    def set_function(code: str) -> str:
        """Save the function for this card (replaces it if it exists). Send ONE complete function.

        Args:
            code: The complete function, starting with def.
        """
        err = _check_name(code)
        if err:
            return "REJECTED: " + err
        return _apply(*codetools.upsert_def(target.read_text(), code))

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
        return "OK, all tests pass. Reply DONE." if r["ok"] else summarize(r["output"])

    tools = [show_models, set_method if cls else set_function, add_import, run_tests]
    tests_src = test_file(ws, card).read_text()
    task = (f"Card: {card['kind']} {cls or ''}.{card['name']}\nRule: {card['spec']}\n\n"
            f"Project:\n{project_map(ws)}\n\nLocked tests that must pass:\n{tests_src}\n")
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
    label = card_label(ws, card)
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
    feedback = ""
    for n in range(1, attempts + 1):
        result["attempts"] = n
        log(f"[{result['id']}] attempt {n}: writing tests")
        if tf.exists():
            tf.unlink()
        if original is None:
            target.unlink(missing_ok=True)
        else:
            target.write_text(original)
        n_new, why = phase_tests(ws, card, model, feedback)
        if why:
            feedback = why
            continue
        locked = _sha(tf)
        log(f"[{result['id']}] tests locked ({n_new}); writing code")
        res, state = phase_impl(ws, card, model, feedback)
        if res["status"] != "done":
            feedback = ("the code could not satisfy the tests. " + (state.get("last_fail") or "")
                        + " If a test asserts something the rule does not state, do not write that "
                        "test; test only what the rule says.")
            continue
        ok, why, rate = gates(ws, card, locked, n_new, base["ran"], state)
        result["kill_rate"] = rate
        if ok:
            result.update(status="passed", reason="", files=[
                str(target.relative_to(ws)), str(tf.relative_to(ws))])
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
    result["reason"] = feedback
    result["seconds"] = round(time.time() - t0)
    return result
