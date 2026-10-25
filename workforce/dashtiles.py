"""Dashboard tile cards. The agent builds a metric as a tested function (a service card); a tile card then puts
its result on the dashboard. No model is involved here: Python writes core/dashboard_tiles.py, one include
template, and two lines in the dashboard view, then proves the page still renders."""
import ast
import pprint
import re
import time
from pathlib import Path

STYLES = ("money", "number", "list", "bars")
LABEL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 ,&'-]{0,29}$")
VIEW_IMPORT = "from .dashboard_tiles import metrics"

TILES_SOURCE = '''"""Dashboard tiles. Written by the autopilot: each tile shows the result of one function."""
from decimal import Decimal, InvalidOperation
from importlib import import_module

TILES = %(tiles)s


def _num(x):
    try:
        return f"{Decimal(x):,.2f}"
    except (InvalidOperation, TypeError, ValueError):
        return str(x)


def _item(r):
    if isinstance(r, tuple) and len(r) == 2:
        return f"{r[0]} \\u2014 {_num(r[1])}"
    if hasattr(r, "stock"):
        return f"{r} \\u2014 {r.stock} left"
    return str(r)


def tile_data(style, value):
    """-> the dict the template renders."""
    if style == "money":
        return {"kind": "stat", "display": _num(value)}
    if style == "number":
        return {"kind": "stat", "display": str(value)}
    rows = list(value)[:8]
    if style == "bars":
        nums = [Decimal(str(r[1])) for r in rows]
        top = max(nums) if nums and max(nums) > 0 else None
        return {"kind": "panel", "bars": [
            {"label": str(r[0]), "value": _num(r[1]), "pct": int(100 * n / top) if top else 0}
            for r, n in zip(rows, nums)]}
    return {"kind": "panel", "items": [_item(r) for r in rows]}


def metrics():
    out = []
    for t in TILES:
        try:
            mod, fn = t["func"].rsplit(".", 1)
            data = tile_data(t["style"], getattr(import_module(mod), fn)())
        except Exception:
            data = {"kind": "stat", "display": "n/a"}
        out.append(dict(data, label=t["label"]))
    return out
'''

METRICS_HTML = '''{% if metrics %}
<div class="cards">
  {% for m in metrics %}{% if m.kind == "stat" %}
  <div class="card"><span class="num">{{ m.display }}</span><span class="label">{{ m.label }}</span></div>
  {% endif %}{% endfor %}
</div>
<div class="grid2">
  {% for m in metrics %}{% if m.kind == "panel" %}
  <section class="panel wide">
    <h2>{{ m.label }}</h2>
    {% if m.items %}<ul class="recent">{% for i in m.items %}<li>{{ i }}</li>{% endfor %}</ul>
    {% elif m.bars %}{% for b in m.bars %}<div style="margin:.4rem 0"><div style="display:flex;justify-content:space-between"><span>{{ b.label }}</span><span>{{ b.value }}</span></div><div style="height:8px;border-radius:4px;background:var(--surface)"><div style="height:8px;border-radius:4px;width:{{ b.pct }}%;background:var(--accent)"></div></div></div>{% endfor %}
    {% else %}<p class="muted">Nothing yet.</p>{% endif %}
  </section>
  {% endif %}{% endfor %}
</div>
{% endif %}
'''


def check_tile_card(c):
    if c.get("style") not in STYLES:
        return f"style must be one of: {', '.join(STYLES)}"
    if not LABEL_RE.match(c.get("label") or ""):
        return "label must be 1-30 letters, digits or spaces, for example 'Revenue'"
    return None


def function_ok(ws, app, name):
    """The function must exist in <app>/services.py and be callable with no arguments. -> error or None"""
    p = Path(ws) / app / "services.py"
    if not p.exists():
        return f"{app}/services.py does not exist: build the function first with a service card"
    fn = next((n for n in ast.parse(p.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == name), None)
    if fn is None:
        return f"{name} does not exist in {app}/services.py: build it first with a service card"
    a = fn.args
    if len(a.defaults) < len(a.posonlyargs) + len(a.args) or any(d is None for d in a.kw_defaults):
        return f"{name} needs arguments; a tile can only call a function that works with no arguments"
    return None


def find_core(ws):
    for p in sorted(Path(ws).glob("*/views.py")):
        src = p.read_text()
        if "def dashboard(" in src and '"cards": cards' in src:
            return p.parent.name, p, src
    return None, None, None


def read_tiles(src):
    tree = ast.parse(src)
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "TILES" for t in n.targets):
            return ast.literal_eval(n.value)
    return []


def patch_view(src):
    """Add the import and pass metrics() to the dashboard template. -> (new_src, error)"""
    if VIEW_IMPORT in src and "metrics()" in src:
        return src, None
    if '"total": total}' not in src:
        return None, "the dashboard view has a shape I do not know (expected render(..., {'cards': cards, 'total': total}))"
    new = src.replace('"total": total}', '"total": total, "metrics": metrics()}', 1)
    lines = new.splitlines()
    tree = ast.parse(new)
    last = max((n.end_lineno for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))), default=0)
    lines[last:last] = [VIEW_IMPORT]
    return "\n".join(lines).rstrip("\n") + "\n", None


def patch_template(src):
    if "_metrics.html" in src:
        return src, None
    marker = '<div class="cards">'
    if marker not in src:
        return None, "the dashboard template has no <div class=\"cards\"> block"
    return src.replace(marker, '{% include "core/_metrics.html" %}\n' + marker, 1), None


def apply_tile(ws, card):
    """-> ({path: original_text_or_None}, error). Writes nothing when it returns an error."""
    ws = Path(ws)
    core, views_p, views_src = find_core(ws)
    if core is None:
        return {}, "no dashboard view found (a views.py with def dashboard and 'cards': cards)"
    tpl_p = ws / core / "templates" / core / "dashboard.html"
    inc_p = ws / core / "templates" / core / "_metrics.html"
    tiles_p = ws / core / "dashboard_tiles.py"
    if not tpl_p.exists():
        return {}, f"{core}/templates/{core}/dashboard.html does not exist"
    new_views, err = patch_view(views_src)
    if err:
        return {}, err
    new_tpl, err = patch_template(tpl_p.read_text())
    if err:
        return {}, err
    tiles = read_tiles(tiles_p.read_text()) if tiles_p.exists() else []
    func = f"{card['app']}.services.{card['name']}"
    entry = {"label": card["label"], "func": func, "style": card["style"]}
    tiles = [t for t in tiles if t["func"] != func] + [entry]
    new_tiles = TILES_SOURCE % {"tiles": pprint.pformat(tiles, width=100, sort_dicts=False)}
    changed = {}
    for p, text in ((views_p, new_views), (tpl_p, new_tpl), (inc_p, METRICS_HTML), (tiles_p, new_tiles)):
        old = p.read_text() if p.exists() else None
        if old != text:
            changed[p] = old
            p.write_text(text)
    return changed, None


def undo(changed):
    for p, old in changed.items():
        if old is None:
            p.unlink(missing_ok=True)
        else:
            p.write_text(old)


def run_tile_card(ws, card, log=print):
    from .fields import _manage
    from .pipeline import card_id, run_suite
    ws = Path(ws)
    t0 = time.time()
    result = {"id": card_id(card), "status": "failed", "attempts": 1, "reason": "", "kill_rate": None,
              "model": "none (tile card)", "files": [], "seconds": 0}

    def fail(why):
        result["reason"] = why
        result["seconds"] = round(time.time() - t0)
        return result

    err = check_tile_card(card) or function_ok(ws, card["app"], card["name"])
    if err:
        return fail(err)
    base = run_suite(ws)
    if not base["ok"]:
        return fail("the existing tests are not green, fix them first:\n" + base["output"][-600:])
    log(f"[{result['id']}] putting '{card['label']}' on the dashboard")
    changed, err = apply_tile(ws, card)
    if err:
        return fail(err)
    s = run_suite(ws)
    if not s["ok"] or s["ran"] != base["ran"]:
        undo(changed)
        return fail("the full test suite fails after adding the tile:\n" + s["output"][-500:])
    core = find_core(ws)[0]
    code = ("import sys\nfrom django.test import RequestFactory\n"
            f"from {core}.views import dashboard\n"
            "r = dashboard(RequestFactory().get('/'))\nhtml = r.content.decode()\n"
            f"print('STATUS=%d' % r.status_code, 'LABEL_OK' if {card['label']!r} in html else 'LABEL_MISSING',"
            " 'NA' if '>n/a<' in html else 'VALUES_OK')\n")
    r = _manage(ws, "shell", "-c", code)
    out = (r.stdout or "").strip().splitlines()[-1:] or [""]
    if r.returncode or "STATUS=200" not in out[0] or "LABEL_OK" not in out[0]:
        undo(changed)
        return fail("the dashboard page does not render with the tile: " + ((r.stderr or r.stdout)[-300:]))
    if "NA" in out[0]:
        undo(changed)
        return fail(f"{card['name']}() raised an error on the real database, so the tile would show n/a. "
                    "Run it in `python manage.py shell` to see the error.")
    result.update(status="passed", files=[str(p.relative_to(ws)) for p in changed])
    result["seconds"] = round(time.time() - t0)
    return result
