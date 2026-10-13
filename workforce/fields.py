"""Field cards: add one field to a model and create its migration. No model involved:
you write the exact field, Python validates it, inserts it and checks the whole project."""
import ast
import os
import subprocess
import sys
import time
from pathlib import Path

ALLOWED = {"CharField", "TextField", "IntegerField", "PositiveIntegerField", "DecimalField",
           "BooleanField", "DateField", "DateTimeField", "EmailField", "FloatField", "ForeignKey"}
ON_DELETE = {"CASCADE", "PROTECT", "SET_NULL", "SET_DEFAULT", "DO_NOTHING"}


def _literal(node):
    if isinstance(node, ast.Constant):
        return True
    return isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) \
        and isinstance(node.operand, ast.Constant)


def check_definition(defn):
    """-> error text or None. Only plain Django fields with literal arguments are accepted."""
    try:
        call = ast.parse((defn or "").strip(), mode="eval").body
    except SyntaxError:
        return "the field definition is not valid Python"
    if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name) and call.func.value.id == "models"):
        return "write it like: models.BooleanField(default=False)"
    kind = call.func.attr
    if kind not in ALLOWED:
        return f"field type {kind} is not allowed (use one of: {', '.join(sorted(ALLOWED))})"
    for a in call.args:
        if not _literal(a):
            return "field arguments must be plain values such as 100, 'text' or True"
    kws = {}
    for kw in call.keywords:
        if kw.arg is None:
            return "do not use ** in a field definition"
        ok = _literal(kw.value) or (kw.arg == "on_delete" and isinstance(kw.value, ast.Attribute)
                                    and isinstance(kw.value.value, ast.Name)
                                    and kw.value.value.id == "models" and kw.value.attr in ON_DELETE)
        if not ok:
            return f"argument {kw.arg} must be a plain value"
        kws[kw.arg] = kw.value
    null_ok = "null" in kws and isinstance(kws["null"], ast.Constant) and kws["null"].value is True
    if "default" not in kws and not null_ok:
        return "give the field a default=... or null=True, so existing rows stay valid"
    if kind == "ForeignKey":
        if not call.args or not isinstance(call.args[0], ast.Constant) \
                or not isinstance(call.args[0].value, str) or "." not in call.args[0].value:
            return "a ForeignKey needs its target as 'app.Model', for example 'customers.Customer'"
        if "on_delete" not in kws:
            return "a ForeignKey needs on_delete=models.CASCADE (or PROTECT, SET_NULL)"
    if kind in ("CharField",) and "max_length" not in kws:
        return "a CharField needs max_length"
    if kind == "DecimalField" and not ("max_digits" in kws and "decimal_places" in kws):
        return "a DecimalField needs max_digits and decimal_places"
    return None


def _is_field_stmt(st):
    return (isinstance(st, ast.Assign) and isinstance(st.value, ast.Call)
            and isinstance(st.value.func, ast.Attribute)
            and isinstance(st.value.func.value, ast.Name) and st.value.func.value.id == "models")


def add_field(src, class_name, name, defn):
    """Insert `name = defn` after the last field of the class. -> (new_src, error)"""
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return None, f"models.py is not valid Python ({e.msg})"
    cls = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name), None)
    if cls is None:
        return None, f"class {class_name} does not exist"
    for st in cls.body:
        names = [t.id for t in getattr(st, "targets", []) if isinstance(t, ast.Name)]
        if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names = [st.name]
        if name in names:
            return None, f"'{name}' already exists on {class_name}"
    fields = [st for st in cls.body if _is_field_stmt(st)]
    lines = src.splitlines()
    if fields:
        at = fields[-1].end_lineno
    else:
        first = cls.body[0]
        doc = isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant)
        at = first.end_lineno if doc else first.lineno - 1
    lines[at:at] = [f"    {name} = {defn.strip()}"]
    new = "\n".join(lines).rstrip("\n") + "\n"
    try:
        ast.parse(new)
    except SyntaxError as e:
        return None, f"the result would not be valid Python ({e.msg})"
    return new, None


def _manage(ws, *args):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run([sys.executable, "manage.py", *args], cwd=ws, capture_output=True,
                          text=True, env=env, timeout=240)


def _migrations(ws, app):
    d = Path(ws) / app / "migrations"
    return {p.name for p in d.glob("*.py")} if d.exists() else set()


def run_field_card(ws, card, log=print):
    from .pipeline import card_id, run_suite
    ws = Path(ws)
    t0 = time.time()
    result = {"id": card_id(card), "status": "failed", "attempts": 1, "reason": "", "kill_rate": None,
              "model": "none (field card)", "files": [], "seconds": 0}

    def fail(why):
        result["reason"] = why
        result["seconds"] = round(time.time() - t0)
        return result

    err = check_definition(card.get("definition"))
    if err:
        return fail(err)
    models_py = ws / card["app"] / "models.py"
    mig_dir = ws / card["app"] / "migrations"
    if not (ws / "manage.py").exists() or not mig_dir.exists():
        return fail("this needs a Django project whose app has a migrations folder")
    base = run_suite(ws)
    if not base["ok"]:
        return fail("the existing tests are not green, fix them first:\n" + base["output"][-600:])
    original = models_py.read_text()
    before = _migrations(ws, card["app"])
    new_src, err = add_field(original, card["class"], card["name"], card["definition"])
    if err:
        return fail(err)

    def undo():
        models_py.write_text(original)
        for n in _migrations(ws, card["app"]) - before:
            (mig_dir / n).unlink(missing_ok=True)

    log(f"[{result['id']}] adding the field and creating its migration")
    models_py.write_text(new_src)
    r = _manage(ws, "makemigrations", card["app"], "--noinput")
    created = sorted(_migrations(ws, card["app"]) - before)
    if r.returncode or not created:
        undo()
        return fail("makemigrations did not work: " + (r.stderr or r.stdout)[-300:])
    chk = _manage(ws, "makemigrations", "--check", "--dry-run")
    if chk.returncode:
        undo()
        return fail("the project still has model changes without a migration")
    s = run_suite(ws)
    if not s["ok"] or s["ran"] != base["ran"]:
        out = s["output"][-500:]
        undo()
        return fail("the full test suite fails after adding the field:\n" + out)
    result.update(status="passed", files=[str(models_py.relative_to(ws))] + [
        str((mig_dir / n).relative_to(ws)) for n in created])
    result["seconds"] = round(time.time() - t0)
    return result
