"""Plain-English description -> modules. The local model proposes, Python validates,
you approve, and the generator builds.

    ./wf design "a small POS with sales and sale items"
    ./wf design --build        # build from a hand-edited design.json, no AI involved
"""
import json
import re
import sys
from pathlib import Path

from ollama import chat

from .config import CFG
from .generator import generate, parse_fields, plural

ROOT = Path(__file__).resolve().parent.parent

SYSTEM = (
    "You design the database for a small business application built with Django. "
    'Answer with JSON only, in this form: {"modules": [{"model": "Product", '
    '"fields": ["name:str", "sku:str:unique", "price:decimal", "stock:int"]}]}\n'
    "Rules:\n"
    "- Model names are singular CamelCase.\n"
    "- Each field is name:type. The name is lowercase_with_underscores. "
    "Types: str, text, int, decimal, bool, date, email.\n"
    "- Add :unique after the type for values that must never repeat, like sku:str:unique.\n"
    "- A link to another model is name:fk:ModelName, for example customer:fk:Customer. "
    "The linked model must be in your list or in EXISTING MODELS.\n"
    "- The FIRST field of every model must be a str field (a name, title, number or description).\n"
    "- Do not add id, created or updated fields. Use 2 to 8 fields per model.\n"
    "- Do not define a model that is listed in EXISTING MODELS."
)


def existing_models(ws):
    out = []
    for models_py in sorted(Path(ws).glob("*/models.py")):
        text = models_py.read_text()
        for m in re.finditer(r"^class (\w+)\(models\.Model\):\n(.*?)(?=^class |\Z)", text, re.S | re.M):
            names = re.findall(r"^\s+(\w+) = models\.", m.group(2), re.M)
            out.append(f"{m.group(1)} ({', '.join(names)})")
    return "; ".join(out) or "none"


def validate(spec, ws):
    """Returns (modules in build order, errors, skipped because already built)."""
    ws = Path(ws)
    items = spec.get("modules") if isinstance(spec, dict) else None
    if not isinstance(items, list) or not items:
        return None, ['the top level must be {"modules": [ ... ]}'], []
    errors, mods, names, skipped = [], [], set(), []
    for m in items:
        if not isinstance(m, dict):
            errors.append("each module must be an object with model and fields")
            continue
        model, fields = m.get("model"), m.get("fields")
        if not isinstance(model, str) or not re.fullmatch(r"[A-Z][A-Za-z0-9]*", model):
            errors.append(f"bad model name {model!r}: use CamelCase like Product")
            continue
        if model in names or model in skipped:
            errors.append(f"{model} appears twice")
            continue
        if not isinstance(fields, list) or not all(isinstance(f, str) for f in fields):
            errors.append(f"{model}: fields must be a list of strings like name:str")
            continue
        try:
            parsed = parse_fields(fields)
        except SystemExit as e:
            errors.append(f"{model}: {e}")
            continue
        if (ws / plural(model.lower())).exists():
            skipped.append(model)
            continue
        names.add(model)
        mods.append({"model": model, "fields": fields,
                     "deps": {e for _, k, e in parsed if k == "fk"}})
    for m in mods:
        for d in m["deps"]:
            if d == m["model"]:
                errors.append(f"{d} cannot point at itself")
            elif d not in names and not (ws / plural(d.lower())).exists():
                errors.append(f"{m['model']} points at {d}, which is neither in your list nor already built")
    if errors:
        return None, errors, skipped
    ordered, done, pending = [], set(), list(mods)
    while pending:
        progress = False
        for m in list(pending):
            if all(d in done or d not in names for d in m["deps"]):
                ordered.append(m)
                done.add(m["model"])
                pending.remove(m)
                progress = True
        if not progress:
            return None, ["circular relationship between: " + ", ".join(x["model"] for x in pending)], skipped
    return ordered, [], skipped


def propose(description, ws, tries=3):
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"EXISTING MODELS: {existing_models(ws)}\n\nDESCRIPTION:\n{description}\n\nReturn the JSON now."},
    ]
    for attempt in range(1, tries + 1):
        print(f"Asking {CFG['model']} for a design (attempt {attempt})...")
        resp = chat(model=CFG["model"], format="json", messages=messages,
                    options={"num_ctx": CFG["num_ctx"], "temperature": 0.3, "num_predict": 1500})
        text = resp.message.content or ""
        try:
            ordered, errors, skipped = validate(json.loads(text), ws)
        except ValueError:
            ordered, errors, skipped = None, ["your answer was not valid JSON"], []
        if not errors:
            return ordered, skipped
        print("The design had problems:\n- " + "\n- ".join(errors))
        messages += [{"role": "assistant", "content": text},
                     {"role": "user", "content": "Fix these problems and answer again with JSON only:\n- " + "\n- ".join(errors)}]
    return None, []


def build_from_file(ws, path=None):
    path = Path(path or ROOT / "design.json")
    ordered, errors, skipped = validate(json.loads(path.read_text()), ws)
    if errors:
        print(f"{path.name} has problems:\n- " + "\n- ".join(errors))
        return False
    for name in skipped:
        print(f"Skipping {name}: it is already built.")
    for m in ordered:
        print(f"\n== Building {m['model']} ==")
        try:
            generate(ws, m["model"], m["fields"])
        except SystemExit:
            print(f"Stopped at {m['model']} (it was rolled back; modules built before it are kept).")
            return False
    print("\nAll modules built. Next:\n  cd workspace_crm && python manage.py migrate\n"
          "  ./wf serve   (then open http://localhost:8000/)\n"
          "  git add -A && git commit -m 'Add modules from design'")
    return True


def run_design(description, ws):
    modules, skipped = propose(description, ws)
    if not modules:
        print("The model could not produce a valid design. Try a simpler description, or write design.json by hand.")
        return
    for name in skipped:
        print(f"(Skipping {name}: it is already built.)")
    spec = {"description": description,
            "modules": [{"model": m["model"], "fields": m["fields"]} for m in modules]}
    (ROOT / "design.json").write_text(json.dumps(spec, indent=2))
    print("\nPROPOSED DESIGN (build order):")
    for m in modules:
        print(f"  {m['model']}: {', '.join(m['fields'])}")
    print("\nYou can edit design.json now (add, remove or change anything).")
    if input("Press Enter to build, or q to quit: ").strip().lower() == "q":
        print("Nothing was built. Build later with: ./wf design --build")
        return
    build_from_file(ws)


def main(argv):
    ws = ROOT / "workspace_crm"
    if argv and argv[0] == "--build":
        build_from_file(ws)
    elif argv:
        run_design(" ".join(argv), ws)
    else:
        raise SystemExit('usage: ./wf design "describe the business" | ./wf design --build')


if __name__ == "__main__":
    main(sys.argv[1:])
