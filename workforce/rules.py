"""The model proposes business-logic cards; Python validates every one."""
import ast
import json
import re
from pathlib import Path

from ollama import chat

from . import fields, ui
from .config import CFG
from .notes import project_map, scan
from .pipeline import PROMPTS, card_id
from .pipeline import test_file as pipeline_test_file

KEEP_OVERRIDABLE = {"save", "clean", "delete"}


def validate_cards(ws, cards):
    """-> (valid_cards, problems)"""
    ws = Path(ws)
    apps = scan(ws)
    valid, problems, seen = [], [], set()
    if not isinstance(cards, list):
        return [], ["'cards' must be a list"]
    for i, c in enumerate(cards, 1):
        tag = f"card {i}"
        if not isinstance(c, dict):
            problems.append(f"{tag}: must be an object")
            continue
        c = {k: (str(c.get(k) or "")).strip() for k in
             ("app", "kind", "class", "name", "spec", "mode", "tag", "definition",
              "url", "button", "show_if", "url_name")}
        if c["kind"] not in ("model", "service", "field", "view"):
            problems.append(f"{tag}: kind must be 'model', 'service', 'field' or 'view'")
            continue
        if c["app"] not in apps:
            problems.append(f"{tag}: app '{c['app']}' does not exist (apps: {', '.join(apps)})")
            continue
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", c["name"]):
            problems.append(f"{tag}: name '{c['name']}' must be snake_case")
            continue
        if not (10 if c["kind"] == "field" else 25) <= len(c["spec"]) <= 500:
            problems.append(f"{tag}: spec must be 25-500 characters")
            continue
        if c["kind"] == "field":
            info = apps[c["app"]].get(c["class"])
            if info is None:
                problems.append(f"{tag}: class '{c['class']}' not found in {c['app']}")
                continue
            if c["name"] in {f[0] for f in info["fields"]} or c["name"] in info["methods"]:
                problems.append(f"{tag}: '{c['name']}' already exists on {c['class']}")
                continue
            bad = fields.check_definition(c["definition"])
            if bad:
                problems.append(f"{tag}: {bad}")
                continue
            c["mode"] = c["tag"] = ""
        elif c["kind"] == "view":
            bad = ui.check_view_card(c)
            vp, up = ws / c["app"] / "views.py", ws / c["app"] / "urls.py"
            if not bad and not (vp.exists() and up.exists()):
                bad = f"{c['app']} has no views.py or urls.py"
            if not bad:
                vsrc, usrc = vp.read_text(), up.read_text()
                if c["class"]:
                    cls = next((n for n in ast.parse(vsrc).body
                                if isinstance(n, ast.ClassDef) and n.name == c["class"]), None)
                    if cls is None:
                        bad = f"class {c['class']} not found in {c['app']}/views.py"
                    elif c["name"] in [m.name for m in cls.body if isinstance(m, ast.FunctionDef)]:
                        bad = f"{c['class']} already has a method {c['name']}"
                    else:
                        app_, name_ = c["url_name"].split(":")
                        if app_ == c["app"] and f'name="{name_}"' not in usrc:
                            bad = f"{c['app']}/urls.py has no route named {name_}"
                elif f"def {c['name']}(" in vsrc or f'name="{c["name"]}"' in usrc:
                    bad = f"'{c['name']}' already exists in {c['app']}"
            if bad:
                problems.append(f"{tag}: {bad}")
                continue
            c["mode"] = c["tag"] = ""
        elif c["mode"] == "change":
            if not re.fullmatch(r"[a-z][a-z0-9_]{1,30}", c["tag"]):
                problems.append(f"{tag}: a change card needs a short snake_case 'tag', for example 'no_double_confirm'")
                continue
            if pipeline_test_file(ws, c).exists():
                problems.append(f"{tag}: already built (its test file {pipeline_test_file(ws, c).name} exists)")
                continue
            if c["kind"] == "model":
                info = apps[c["app"]].get(c["class"])
                if info is None or c["name"] not in info["methods"]:
                    problems.append(f"{tag}: '{c['name']}' does not exist on {c['class']}, so it cannot be changed")
                    continue
            else:
                c["class"] = ""
                svc = ws / c["app"] / "services.py"
                if not (svc.exists() and f"def {c['name']}(" in svc.read_text()):
                    problems.append(f"{tag}: '{c['name']}' does not exist in services.py, so it cannot be changed")
                    continue
        elif c["mode"]:
            problems.append(f"{tag}: mode can only be 'change'")
            continue
        elif c["kind"] == "model":
            info = apps[c["app"]].get(c["class"])
            if info is None:
                problems.append(f"{tag}: class '{c['class']}' not found in {c['app']}")
                continue
            if c["name"] in {f[0] for f in info["fields"]} or (
                    c["name"] in info["methods"] and c["name"] not in KEEP_OVERRIDABLE):
                problems.append(f"{tag}: '{c['name']}' already exists on {c['class']}")
                continue
        elif c["kind"] == "service":
            c["class"] = ""
            svc = ws / c["app"] / "services.py"
            if svc.exists() and f"def {c['name']}(" in svc.read_text():
                problems.append(f"{tag}: '{c['name']}' already exists in services.py")
                continue
        cid = card_id(c)
        if cid in seen:
            problems.append(f"{tag}: duplicate of an earlier card")
            continue
        seen.add(cid)
        valid.append(c)
    valid.sort(key=lambda c: c["kind"] != "field")  # fields first, order otherwise kept
    if len(valid) > 8:
        problems.append("more than 8 cards; keeping the first 8")
        valid = valid[:8]
    return valid, problems


def propose_cards(description, ws, model=None, tries=3, log=print):
    model = model or CFG["model"]
    system = (PROMPTS / "card_rules.txt").read_text()
    user = f"Business: {description}\n\nProject map:\n{project_map(ws)}"
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    best, problems = [], []
    for t in range(tries):
        extra = {"think": CFG["think"]} if "think" in CFG else {}
        resp = chat(model=model, messages=messages, format="json", **extra,
                    options={"num_ctx": CFG["num_ctx"], "temperature": CFG["temperature"],
                             "num_predict": CFG["num_predict"]})
        text = resp.message.content or ""
        try:
            cards = json.loads(text).get("cards")
        except (ValueError, AttributeError):
            problems = ["reply was not valid JSON with a 'cards' list"]
            messages += [{"role": "assistant", "content": text},
                         {"role": "user", "content": "Reply with valid JSON only."}]
            continue
        valid, problems = validate_cards(ws, cards)
        if len(valid) > len(best):
            best = valid
        if valid and not problems:
            return valid, []
        messages += [{"role": "assistant", "content": text},
                     {"role": "user", "content": "Fix these problems and resend all cards: "
                      + "; ".join(problems)}]
    return best, problems
