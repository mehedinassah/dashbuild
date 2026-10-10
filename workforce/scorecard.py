"""An honest record of what each model actually managed."""
import json
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent


def _path(root=None):
    return Path(root or ROOT) / "scorecard.json"


def load(root=None):
    p = _path(root)
    return json.loads(p.read_text()) if p.exists() else []


def record(result, root=None):
    rows = load(root)
    rows.append({"time": time.strftime("%Y-%m-%d %H:%M"), "id": result["id"],
                 "model": result["model"], "status": result["status"],
                 "attempts": result["attempts"], "kill_rate": result["kill_rate"],
                 "seconds": result["seconds"], "reason": (result["reason"] or "")[:200]})
    _path(root).write_text(json.dumps(rows, indent=1))


def summary(root=None):
    rows = load(root)
    if not rows:
        return "No cards run yet."
    by = {}
    for r in rows:
        m = by.setdefault(r["model"], {"n": 0, "ok": 0, "first": 0, "secs": 0})
        m["n"] += 1
        m["ok"] += r["status"] == "passed"
        m["first"] += r["status"] == "passed" and r["attempts"] == 1
        m["secs"] += r["seconds"]
    out = [f"{'model':24} {'cards':>5} {'passed':>7} {'1st try':>8} {'avg sec':>8}"]
    for model, m in by.items():
        out.append(f"{model:24} {m['n']:>5} {m['ok']:>7} {m['first']:>8} {m['secs'] // m['n']:>8}")
    return "\n".join(out)
