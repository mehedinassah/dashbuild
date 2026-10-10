"""A short, always-correct map of the project, built from the code itself (AST),
so the small model never has to guess field names or relation names."""
import ast
from pathlib import Path


def _field(call):
    """models.CharField(...) -> ('CharField', fk_target, related_name, required)"""
    if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name) and call.func.value.id == "models"):
        return None
    kind = call.func.attr
    target = related = None
    if kind in ("ForeignKey", "OneToOneField") and call.args:
        a = call.args[0]
        target = a.value if isinstance(a, ast.Constant) else getattr(a, "id", None)
    for kw in call.keywords:
        if kw.arg == "related_name" and isinstance(kw.value, ast.Constant):
            related = kw.value.value
    return kind, target, related


def scan(ws):
    """-> {app: {Class: {"fields": [(name, kind, fk)], "methods": [..], "reverse": [..]}}}"""
    ws = Path(ws)
    apps = {}
    for mp in sorted(ws.glob("*/models.py")):
        try:
            tree = ast.parse(mp.read_text())
        except SyntaxError:
            continue
        classes = {}
        for c in tree.body:
            if not isinstance(c, ast.ClassDef):
                continue
            info = {"fields": [], "methods": [], "reverse": []}
            for st in c.body:
                if isinstance(st, ast.Assign) and len(st.targets) == 1 \
                        and isinstance(st.targets[0], ast.Name):
                    f = _field(st.value)
                    if f:
                        info["fields"].append((st.targets[0].id,) + f[:2] + (f[2],))
                elif isinstance(st, ast.FunctionDef):
                    info["methods"].append(st.name)
            classes[c.name] = info
        apps[mp.parent.name] = classes
    for app, classes in apps.items():
        for cname, info in classes.items():
            for fname, kind, target, related in info["fields"]:
                if target:
                    tname = target.split(".")[-1]
                    for a2, cl2 in apps.items():
                        if tname in cl2:
                            rel = related or f"{cname.lower()}_set"
                            cl2[tname]["reverse"].append(f"{rel} (all {cname} rows via {cname}.{fname})")
    return apps


def project_map(ws, max_chars=3000):
    ws = Path(ws)
    lines = []
    for app, classes in scan(ws).items():
        if not classes:
            continue
        lines.append(f"app {app} (import: from {app}.models import ...)")
        for cname, info in classes.items():
            fl = ", ".join(f"{n}: {k}" + (f"->{t}" if t else "") for n, k, t, _ in info["fields"])
            lines.append(f"  class {cname}: fields [{fl}]")
            if info["methods"]:
                lines.append(f"    methods: {', '.join(info['methods'])}")
            for r in info["reverse"]:
                lines.append(f"    reverse: .{r}")
        svc = ws / app / "services.py"
        if svc.exists():
            try:
                names = [n.name for n in ast.parse(svc.read_text()).body
                         if isinstance(n, ast.FunctionDef)]
            except SyntaxError:
                names = []
            if names:
                lines.append(f"  services ({app}/services.py): {', '.join(names)}")
    text = "\n".join(lines)
    notes = ws / "NOTES.md"
    if notes.exists():
        text += "\n\nProject notes:\n" + notes.read_text()[:1000]
    return text[:max_chars]
