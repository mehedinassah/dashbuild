import json
from pathlib import Path
from ollama import chat
from .manager import run_task

PLANNER_SYSTEM = (
    "You are a technical planner for a small Django project. Split the goal into "
    "the smallest possible ordered steps. Rules: 3 to 6 tasks. Each task changes "
    "at most two files and names them by path. Each task does one thing, for "
    "example 'add a view', 'add the URL', 'add the template', 'add tests'. Later "
    "tasks may depend on earlier ones. Do not plan to install packages, run "
    "migrate, or edit settings unless the goal requires it. Answer with JSON "
    'only, in this form: {"tasks": ["first task", "second task"]}'
)


def project_context(ws):
    ws = Path(ws)
    skip = {"__pycache__", "migrations", ".git"}
    files = sorted(str(p.relative_to(ws)) for p in ws.rglob("*")
                   if p.is_file() and not (skip & set(p.parts))
                   and p.name != "db.sqlite3")
    out = ["Files:\n" + "\n".join(files)]
    for p in sorted(ws.rglob("*.py")):
        if p.name in {"models.py", "views.py", "urls.py"} and not (skip & set(p.parts)):
            out.append(f"--- {p.relative_to(ws)} ---\n" + p.read_text()[:1200])
    return "\n\n".join(out)


def _clean(item):
    if isinstance(item, dict):
        item = next((v for v in item.values() if isinstance(v, str)), "")
    return item.strip() if isinstance(item, str) else ""


def make_plan(model, goal, ws, tries=3):
    user = (f"GOAL:\n{goal}\n\nCURRENT PROJECT:\n{project_context(ws)}\n\n"
            "Return the JSON plan now.")
    for _ in range(tries):
        resp = chat(model=model, format="json",
                    messages=[{"role": "system", "content": PLANNER_SYSTEM},
                              {"role": "user", "content": user}],
                    options={"num_ctx": 8192, "temperature": 0.3, "num_predict": 1500})
        try:
            tasks = [_clean(t) for t in json.loads(resp.message.content)["tasks"]]
            if 1 <= len(tasks) <= 8 and all(len(t) > 15 for t in tasks):
                return tasks
        except (ValueError, KeyError, TypeError):
            pass
        print("Planner gave an unusable answer, retrying...")
    return None


def run_plan(model, ws, goal, plan_file="plan.json"):
    tasks = make_plan(model, goal, ws)
    if not tasks:
        print("The planner could not produce a usable plan.")
        return
    Path(plan_file).write_text(json.dumps({"goal": goal, "tasks": tasks}, indent=2))
    print("\nPROPOSED PLAN:")
    for i, t in enumerate(tasks, 1):
        print(f"  {i}. {t}")
    print(f"\nYou can edit {plan_file} now (change, delete or reorder tasks).")
    if input("Press Enter to start, or type q to quit: ").strip().lower() == "q":
        print("Stopped before any coding.")
        return
    tasks = json.loads(Path(plan_file).read_text())["tasks"]

    done = []
    for i, t in enumerate(tasks, 1):
        print("\n" + "#" * 60 + f"\nTASK {i} of {len(tasks)}: {t}\n" + "#" * 60)
        prompt = f"Overall goal: {goal}\n"
        if done:
            prompt += "Already completed and committed:\n- " + "\n- ".join(done) + "\n"
        prompt += (f"\nYOUR TASK NOW (only this, nothing more):\n{t}\n\n"
                   "Add or update tests for what you build. If you change models, "
                   "run 'python manage.py makemigrations <app>' before the tests. "
                   "Finish by running the tests.")
        out = run_task(model, ws, prompt, label=t)
        if out.get("status") != "committed":
            print(f"\nStopped at task {i} (status: {out.get('status')}). "
                  "Later tasks depend on it, so nothing further was run.")
            return
        done.append(t)
    print("\nALL TASKS COMMITTED. Run 'python manage.py migrate' yourself when ready.")
