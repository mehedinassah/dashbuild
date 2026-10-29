"""Structure-aware code edits. The model hands over ONE function; Python decides
where it goes, so the model never deals with paths or exact-text matching."""
import ast
import textwrap

BANNED_IMPORTS = {"os", "sys", "subprocess", "shutil", "socket", "ctypes", "requests",
                  "urllib", "http", "pickle", "importlib", "pathlib", "builtins"}
BANNED_CALLS = {"eval", "exec", "open", "__import__", "compile", "input", "globals", "setattr"}


def safety_problem(code):
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"this is not valid Python (line {e.lineno}: {e.msg})"
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name.split(".")[0] in BANNED_IMPORTS:
                    return f"importing '{a.name}' is not allowed"
        elif isinstance(n, ast.ImportFrom):
            if (n.module or "").split(".")[0] in BANNED_IMPORTS:
                return f"importing from '{n.module}' is not allowed"
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
                and n.func.id in BANNED_CALLS:
            return f"calling '{n.func.id}' is not allowed"
    return None


def one_def(code):
    """Parse code that must be exactly one function. Returns (node, error)."""
    code = textwrap.dedent(code).strip("\n")
    problem = safety_problem(code)
    if problem:
        return None, problem
    tree = ast.parse(code)
    if len(tree.body) != 1 or not isinstance(tree.body[0], (ast.FunctionDef, ast.AsyncFunctionDef)):
        return None, "send exactly ONE function (def ...) and nothing else"
    return tree.body[0], None


def normalize_indent(code):
    """Make the body of a function use exactly 4 spaces, whatever the model sent."""
    code = textwrap.dedent(code).strip("\n")
    try:
        fn = ast.parse(code).body[0]
    except (SyntaxError, IndexError):
        return code
    lines = code.splitlines()
    first = fn.body[0].lineno - 1
    body_indent = len(lines[first]) - len(lines[first].lstrip())
    delta = 4 - body_indent
    if delta == 0:
        return code
    rest = lines[first:]
    if any(l.strip() and len(l) - len(l.lstrip()) < body_indent for l in rest):
        return code
    out = lines[:first]
    for l in rest:
        if not l.strip():
            out.append("")
        elif delta > 0:
            out.append(" " * delta + l)
        else:
            out.append(l[-delta:])
    new = "\n".join(out)
    try:
        ast.parse(new)
    except SyntaxError:
        return code
    return new


def _span(node):
    start = min([node.lineno] + [d.lineno for d in node.decorator_list])
    return start - 1, node.end_lineno


def find_def(tree, name, class_name=None):
    body = tree.body
    if class_name:
        cls = next((n for n in body if isinstance(n, ast.ClassDef) and n.name == class_name), None)
        if cls is None:
            return None
        body = cls.body
    return next((n for n in body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and n.name == name), None)


def upsert_def(src, code, class_name=None):
    """Insert or replace one function (or method). Returns (new_src, error)."""
    fn, err = one_def(code)
    if err:
        return None, err
    code = normalize_indent(code)
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return None, f"the target file is currently not valid Python: {e.msg}"
    lines = src.splitlines()
    indent = ""
    if class_name:
        cls = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name), None)
        if cls is None:
            return None, f"class {class_name} does not exist"
        if not fn.args.args or fn.args.args[0].arg not in ("self", "cls"):
            return None, "a method must take 'self' as its first argument"
        for st in cls.body:
            names = []
            if isinstance(st, ast.Assign):
                names = [t.id for t in st.targets if isinstance(t, ast.Name)]
            elif isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name):
                names = [st.target.id]
            if fn.name in names:
                return None, f"'{fn.name}' is already a field of {class_name}; choose another name"
        indent = "    "
        existing = find_def(tree, fn.name, class_name)
        anchor_end = cls.end_lineno
    else:
        existing = find_def(tree, fn.name)
        anchor_end = len(lines)
    block = textwrap.indent(code, indent).splitlines()
    if existing:
        s, e = _span(existing)
        lines[s:e] = block
    else:
        lead = [""] if class_name else ["", ""]
        lines[anchor_end:anchor_end] = lead + block
    new = "\n".join(lines).rstrip("\n") + "\n"
    try:
        ast.parse(new)
    except SyntaxError as e:
        return None, f"the result would not be valid Python ({e.msg})"
    return new, None


def add_import(src, statement):
    """Add one import line if it is not there yet. Returns (new_src, error)."""
    statement = textwrap.dedent(statement).strip()
    problem = safety_problem(statement)
    if problem:
        return None, problem
    tree = ast.parse(statement)
    if len(tree.body) != 1 or not isinstance(tree.body[0], (ast.Import, ast.ImportFrom)):
        return None, "send exactly one import statement"
    want = ast.dump(tree.body[0])
    mod = ast.parse(src)
    last = 0
    for i, n in enumerate(mod.body):
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            if ast.dump(n) == want:
                return src, None
            last = n.end_lineno
        elif i == 0 and isinstance(n, ast.Expr) and isinstance(getattr(n, "value", None), ast.Constant):
            last = n.end_lineno
    lines = src.splitlines()
    lines[last:last] = [statement]
    return "\n".join(lines).rstrip("\n") + "\n", None


def drop_unused_new_imports(original_src, new_src):
    """Remove imports the model added but never uses. Imports that were already there stay."""
    try:
        old_tree, tree = ast.parse(original_src or ""), ast.parse(new_src)
    except SyntaxError:
        return new_src
    had = {ast.dump(n) for n in old_tree.body if isinstance(n, (ast.Import, ast.ImportFrom))}
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    lines = new_src.splitlines()
    edits = []
    for n in tree.body:
        if not isinstance(n, (ast.Import, ast.ImportFrom)) or ast.dump(n) in had:
            continue
        keep = [a for a in n.names
                if (a.asname or a.name.split(".")[0]) in used or a.name == "*"]
        if len(keep) == len(n.names):
            continue
        if keep:
            names = ", ".join(a.name + (f" as {a.asname}" if a.asname else "") for a in keep)
            text = (f"from {'.' * n.level}{n.module or ''} import {names}" if isinstance(n, ast.ImportFrom)
                    else f"import {names}")
        else:
            text = None
        edits.append((n.lineno - 1, n.end_lineno, text))
    for start, end, text in sorted(edits, reverse=True):
        lines[start:end] = [text] if text else []
    out = "\n".join(lines).rstrip("\n") + "\n"
    try:
        ast.parse(out)
    except SyntaxError:
        return new_src
    return out


def split_imports(code):
    """'import x' lines sent together with ONE function -> ([import lines], the function alone).
    Anything else is returned unchanged."""
    text = textwrap.dedent(code).strip("\n")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return [], code
    imps = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    rest = [n for n in tree.body if n not in imps]
    if not imps or len(rest) != 1 or not isinstance(rest[0], (ast.FunctionDef, ast.AsyncFunctionDef)):
        return [], code
    lines = text.splitlines()
    s, e = _span(rest[0])
    return ["\n".join(lines[n.lineno - 1:n.end_lineno]) for n in imps], "\n".join(lines[s:e])


# ---------- Python fixes the imports the model forgets ----------
KNOWN_IMPORTS = {
    "Decimal": "from decimal import Decimal",
    "InvalidOperation": "from decimal import InvalidOperation",
    "date": "from datetime import date",
    "datetime": "from datetime import datetime",
    "timedelta": "from datetime import timedelta",
    "timezone": "from django.utils import timezone",
    "Q": "from django.db.models import Q",
    "F": "from django.db.models import F",
    "Sum": "from django.db.models import Sum",
    "Count": "from django.db.models import Count",
    "Avg": "from django.db.models import Avg",
    "Max": "from django.db.models import Max",
    "Min": "from django.db.models import Min",
    "Coalesce": "from django.db.models.functions import Coalesce",
    "transaction": "from django.db import transaction",
    "messages": "from django.contrib import messages",
    "reverse": "from django.urls import reverse",
    "redirect": "from django.shortcuts import redirect",
    "render": "from django.shortcuts import render",
    "get_object_or_404": "from django.shortcuts import get_object_or_404",
    "TestCase": "from django.test import TestCase",
    "ValidationError": "from django.core.exceptions import ValidationError",
    "json": "import json",
    "math": "import math",
}


def _undefined(src):
    try:
        from pyflakes import api, reporter
    except ImportError:
        return []
    import io
    import re
    out = io.StringIO()
    api.check(src, "code", reporter.Reporter(out, out))
    return sorted({m.group(1) for m in re.finditer(r"undefined name '(\w+)'", out.getvalue())})


def project_models(ws):
    """{ModelName: app} for every model class found in <app>/models.py."""
    from pathlib import Path
    found = {}
    for p in sorted(Path(ws).glob("*/models.py")):
        try:
            tree = ast.parse(p.read_text())
        except SyntaxError:
            continue
        for n in tree.body:
            if isinstance(n, ast.ClassDef):
                found.setdefault(n.name, p.parent.name)
    return found


def autofix_imports(src, ws=None):
    """Add imports for well-known names the code uses but never imports. Python does this, not the model.
    With ws given, the project's own models are fixed too (only use that for test files: in app code a
    module-level model import can be circular). -> (new_src, [statements added])"""
    try:
        ast.parse(src)
    except SyntaxError:
        return src, []
    table = dict(KNOWN_IMPORTS)
    if ws is not None:
        for name, app in project_models(ws).items():
            table.setdefault(name, f"from {app}.models import {name}")
    added = []
    for name in _undefined(src):
        stmt = table.get(name)
        if not stmt:
            continue
        new, err = add_import(src, stmt)
        if err or new is None:
            continue
        if new != src:
            src = new
            added.append(stmt)
    return src, added
