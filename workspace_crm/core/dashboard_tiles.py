"""Dashboard tiles. Written by the autopilot: each tile shows the result of one function."""
from decimal import Decimal, InvalidOperation
from importlib import import_module

TILES = [{'label': 'Revenue', 'func': 'sales.services.total_revenue', 'style': 'money'},
 {'label': 'Outstanding', 'func': 'sales.services.outstanding_balance', 'style': 'money'},
 {'label': 'Sales by month', 'func': 'sales.services.sales_by_month', 'style': 'bars'},
 {'label': 'Top customers', 'func': 'sales.services.top_customers', 'style': 'list'},
 {'label': 'Low stock', 'func': 'products.services.low_stock_products', 'style': 'list'}]


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
