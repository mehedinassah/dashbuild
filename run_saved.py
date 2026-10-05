import json
import sys
from pathlib import Path
from workforce.manager import run_task

start = int(sys.argv[1]) if len(sys.argv) > 1 else 1
ws = Path(__file__).parent / "workspace_crm"
model = "qwen2.5:7b"
plan = json.loads(Path("plan.json").read_text())
goal, tasks = plan["goal"], plan["tasks"]

done = list(tasks[:start - 1])
for i, t in enumerate(tasks, 1):
    if i < start:
        continue
    print("\n" + "#" * 60 + f"\nTASK {i} of {len(tasks)}: {t}\n" + "#" * 60)
    prompt = ""
    if done:
        prompt += "Already completed and committed:\n- " + "\n- ".join(done) + "\n"
    prompt += (f"\nYOUR TASK NOW (only this, nothing more):\n{t}\n\n"
               "Only write tests if the task above asks for tests. If you change models, "
               "run 'python manage.py makemigrations <app>' before the tests. "
               "Finish by running the tests.")
    out = run_task(model, ws, prompt, label=t)
    if out.get("status") != "committed":
        print(f"\nStopped at task {i} (status: {out.get('status')}). "
              f"After fixing it, resume with: python -u run_saved.py {i}")
        sys.exit(1)
    done.append(t)
print("\nALL TASKS COMMITTED.")
