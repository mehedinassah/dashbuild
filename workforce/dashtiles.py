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
        return {"label": str(r[0]), "value": _num(r[1])}
    if hasattr(r, "stock"):
        return {"label": str(r), "value": f"{r.stock} left"}
    return {"label": str(r), "value": ""}


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
    return {"kind": "panel", "rows": [_item(r) for r in rows]}


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

DASH_CSS = '''<style>
.dash{--bg:#131a2b;--line:#232d45;--text:#e8ecf4;--muted:#8b96ab;--accent:#38bdf8;max-width:1240px}
.dash h1{margin:0;font-size:1.6rem;font-weight:650;color:var(--text)}
.dash .sub{color:var(--muted);margin:.3rem 0 .5rem}
.dash .sec{font-size:.72rem;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);margin:2rem 0 .75rem;font-weight:600}
.dash .kpis{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:1rem}
.dash .kpi{display:flex;flex-direction:column;gap:.35rem;padding:1.1rem 1.25rem;background:var(--bg);border:1px solid var(--line);border-radius:12px;color:var(--text);text-decoration:none}
.dash a.kpi:hover{border-color:var(--accent)}
.dash .kpi .val{font-size:1.9rem;font-weight:700;line-height:1.1;font-variant-numeric:tabular-nums}
.dash .kpi .lbl{color:var(--muted);font-size:.85rem}
.dash .row3{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:1rem}
.dash .box{background:var(--bg);border:1px solid var(--line);border-radius:12px;padding:1.1rem 1.25rem}
.dash .box h3{margin:0 0 .6rem;font-size:.95rem;font-weight:600;color:var(--text)}
.dash .li{display:flex;justify-content:space-between;gap:1rem;padding:.5rem 0;border-top:1px solid var(--line);font-size:.9rem;color:var(--text)}
.dash .box h3 + .li{border-top:0}
.dash .li span:last-child{color:var(--muted);font-variant-numeric:tabular-nums;white-space:nowrap}
.dash .bar{margin:.55rem 0}
.dash .bar .li{border:0;padding:0 0 .3rem}
.dash .track{height:6px;border-radius:3px;background:var(--line)}
.dash .fill{height:6px;border-radius:3px;background:var(--accent)}
.dash .empty{color:var(--muted);font-size:.9rem;margin:.25rem 0}
.dash .more{display:inline-block;margin-top:.7rem;color:var(--accent);font-size:.85rem;text-decoration:none}
</style>
'''

DASHBOARD_HTML = '''{% extends "core/base.html" %}
{% block title %}Dashboard{% endblock %}
{% block content %}
{# dash-v2: written by the autopilot, edit freely #}
''' + DASH_CSS + '''<div class="dash">
  <h1>Dashboard</h1>
  <p class="sub">{{ total }} records across {{ cards|length }} modules</p>
  {% include "core/_metrics.html" %}
  <div class="sec">Modules</div>
  <div class="kpis">
    {% for card in cards %}
    <a class="kpi" href="{{ card.url }}"><span class="val">{{ card.count }}</span><span class="lbl">{{ card.icon }} {{ card.title }}</span></a>
    {% empty %}
    <p class="empty">No modules yet. Create one with: ./wf make crud Product name:str price:decimal</p>
    {% endfor %}
  </div>
  <div class="sec">Recent activity</div>
  <div class="row3">
    {% for card in cards %}
    <div class="box">
      <h3>{{ card.icon }} {{ card.title }}</h3>
      {% if card.recent %}{% for r in card.recent %}<div class="li"><span>{{ r }}</span></div>{% endfor %}
      {% else %}<p class="empty">Nothing yet.</p>{% endif %}
      <a class="more" href="{{ card.url }}">View all &rarr;</a>
    </div>
    {% endfor %}
  </div>
</div>
{% endblock %}
'''

METRICS_HTML = '''{% if metrics %}
<div class="sec">Overview</div>
<div class="kpis">
  {% for m in metrics %}{% if m.kind == "stat" %}<div class="kpi"><span class="val">{{ m.display }}</span><span class="lbl">{{ m.label }}</span></div>{% endif %}{% endfor %}
</div>
<div class="row3" style="margin-top:1rem">
  {% for m in metrics %}{% if m.kind == "panel" %}
  <div class="box">
    <h3>{{ m.label }}</h3>
    {% if m.rows %}{% for i in m.rows %}<div class="li"><span>{{ i.label }}</span><span>{{ i.value }}</span></div>{% endfor %}
    {% elif m.bars %}{% for b in m.bars %}<div class="bar"><div class="li"><span>{{ b.label }}</span><span>{{ b.value }}</span></div><div class="track"><div class="fill" style="width:{{ b.pct }}%"></div></div></div>{% endfor %}
    {% else %}<p class="empty">Nothing yet.</p>{% endif %}
  </div>
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
    if "dash-v2" in src:
        return src, None
    if '<div class="cards">' not in src and "_metrics.html" not in src:
        return None, "the dashboard template has no <div class=\"cards\"> block"
    return DASHBOARD_HTML, None


def refresh(ws):
    """Bring an existing project's dashboard files to the current design. -> list of files written."""
    ws = Path(ws)
    core, _, _ = find_core(ws)
    if core is None:
        return []
    tpl_p = ws / core / "templates" / core / "dashboard.html"
    inc_p = ws / core / "templates" / core / "_metrics.html"
    tiles_p = ws / core / "dashboard_tiles.py"
    if not (tpl_p.exists() and tiles_p.exists()):
        return []
    tiles = read_tiles(tiles_p.read_text())
    new_tpl, err = patch_template(tpl_p.read_text())
    if err:
        return []
    out = []
    for p, text in ((tpl_p, new_tpl), (inc_p, METRICS_HTML),
                    (tiles_p, TILES_SOURCE % {"tiles": pprint.pformat(tiles, width=100, sort_dicts=False)})):
        if not p.exists() or p.read_text() != text:
            p.write_text(text)
            out.append(str(p))
    return out


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
    from . import pagecheck
    pages_before = pagecheck.check(ws)
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
    bad = pagecheck.new_problems(pages_before, pagecheck.check(ws))
    if bad:
        undo(changed)
        return fail("page check failed after adding the tile: " + "; ".join(bad[:3]))
    result.update(status="passed", files=[str(p.relative_to(ws)) for p in changed])
    result["seconds"] = round(time.time() - t0)
    return result
