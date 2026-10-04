import json
import subprocess
import time
from pathlib import Path
from .tools import make_tools
from .worker import run_worker
from .review import review

CODER_SYSTEM = (
    "You are a coding agent. Call one tool at a time and wait for its result. "
    "Always read a file before changing it. To change an existing file, use edit_file with a small old_text; use write_file only for new files. Never delete existing tests. If a "
    "change makes an existing test fail because the behavior genuinely changed, "
    "fix that test so it still checks what its name says (for example by using "
    "a different invalid input), and never just change its expected value to "
    "match. After writing code, call run_tests. Fix failures. When tests pass, "
    "reply with a one-line summary."
)


def _git(ws, *args):
    return subprocess.run(["git", *args], cwd=ws, capture_output=True,
                          text=True, timeout=60)


def run_task(model, workspace, task, max_attempts=3, state_file="state.json"):
    ws = Path(workspace).resolve()

    dirty = _git(ws, "status", "--porcelain", "--", ".").stdout.strip()
    if dirty:
        print("Workspace has uncommitted changes. Commit or reset them first:\n" + dirty)
        return {"status": "dirty_workspace"}

    history, touched, feedback, approved = [], set(), None, False

    for attempt in range(1, max_attempts + 1):
        print("\n" + "=" * 60 + f"\nATTEMPT {attempt} of {max_attempts}: CODER\n" + "=" * 60)
        prompt = task
        if feedback:
            prompt += ("\n\nYOUR PREVIOUS ATTEMPT WAS REJECTED BY THE REVIEWER:\n"
                       f"{feedback}\n\nThe files already contain your previous "
                       "changes. Read them, then fix only these problems.")
        state = {}
        res = run_worker(model=model, system=CODER_SYSTEM, task=prompt,
                         tools=make_tools(ws, state), state=state)
        touched |= set(res.get("files", []))

        if res["status"] != "done":
            feedback = ("You ran out of steps without finishing. Work in smaller "
                        "steps and call run_tests after each change.")
            history.append({"attempt": attempt, "stage": "coder", "result": res["status"]})
            continue

        print("\n" + "=" * 60 + f"\nATTEMPT {attempt}: REVIEWER\n" + "=" * 60)
        rev = review(model, ws, task)
        history.append({"attempt": attempt, "stage": "review",
                        "verdict": rev["verdict"], "notes": (rev.get("summary") or "")[:1500]})
        print("\nVERDICT:", rev["verdict"])
        if rev["verdict"] == "APPROVE":
            approved = True
            break
        feedback = (rev.get("summary") or "")[:1500]

    outcome = {"task": task, "model": model, "when": time.strftime("%F %T"),
               "approved": approved, "history": history}

    if not approved:
        outcome["status"] = "failed"
        print("\nSTOPPED: no approved result after all attempts.")
        print("The changes are still in the workspace. Inspect them with: git diff")
    else:
        print("\n" + "=" * 60 + "\nAPPROVED. CHANGES TO COMMIT:\n" + "=" * 60)
        print(_git(ws, "diff", "HEAD", "--relative", "--", ".").stdout)
        answer = input("Commit these changes? [y/N] ").strip().lower()
        if answer == "y":
            _git(ws, "add", "--", *sorted(touched))
            c = _git(ws, "commit", "-m", f"Worker: {task[:60]}")
            print(c.stdout or c.stderr)
            outcome["status"] = "committed"
        else:
            outcome["status"] = "approved_not_committed"
            print("Not committed. Discard with: git checkout workspace")

    runs = []
    if Path(state_file).exists():
        runs = json.loads(Path(state_file).read_text())
    runs.append(outcome)
    Path(state_file).write_text(json.dumps(runs, indent=2))
    return outcome
