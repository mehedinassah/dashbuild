import json
import subprocess
import time
from pathlib import Path
from .tools import make_tools, test_names, count_tests_run
from .worker import run_worker
from .review import review

CODER_SYSTEM = (
    "You are a coding agent. Call one tool at a time and wait for its result. "
    "Always read a file before changing it. append_file adds new text at the end "
    "of a file; use it to add new tests. edit_file replaces complete lines copied "
    "exactly from read_file. write_file replaces a whole file; use it for new or "
    "very small files. Never delete or rename existing tests. If a change makes "
    "an existing test fail because behavior genuinely changed, fix that test so "
    "it still checks what its name says (for example by using a different invalid "
    "input), and never just change its expected value to match. After writing "
    "code, call run_tests. Fix failures. When tests pass, reply with a one-line "
    "summary."
)


def _git(ws, *args):
    return subprocess.run(["git", *args], cwd=ws, capture_output=True,
                          text=True, timeout=60)


def project_notes(ws):
    p = Path(ws) / ".workforce.json"
    notes = json.loads(p.read_text()).get("notes", "") if p.exists() else ""
    return ("\n\nPROJECT RULES:\n" + notes) if notes else ""


def _new_test_names(ws):
    _git(ws, "add", "-N", "--", ".")
    names = _git(ws, "diff", "HEAD", "--name-only", "--relative", "--", ".").stdout.split()
    added = []
    for rel in names:
        base = Path(rel).name
        if not ((base.startswith("test_") or base == "tests.py") and base.endswith(".py")):
            continue
        old = _git(ws, "show", f"HEAD:./{rel}")
        old_names = test_names(old.stdout) if old.returncode == 0 else set()
        added += sorted(test_names((ws / rel).read_text()) - old_names)
    return added


def _reset(ws):
    """Restore the workspace folder to the last commit."""
    _git(ws, "reset", "-q", "--", ".")
    _git(ws, "checkout", "HEAD", "--", ".")
    _git(ws, "clean", "-fd", "--", ".")


def run_task(model, workspace, task, max_attempts=3, state_file="state.json", label=None):
    ws = Path(workspace).resolve()

    dirty = _git(ws, "status", "--porcelain", "--", ".").stdout.strip()
    if dirty:
        print("Workspace has uncommitted changes. Commit or reset them first:\n" + dirty)
        return {"status": "dirty_workspace"}

    history, touched, feedback, approved = [], set(), None, False
    reviewer_notes = ''
    baseline = count_tests_run(ws)
    print(f"Baseline: {baseline} tests run at the last commit.")

    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
            print("\nResetting workspace to the last commit for a clean retry.")
            _reset(ws)
        print("\n" + "=" * 60 + f"\nATTEMPT {attempt} of {max_attempts}: CODER\n" + "=" * 60)
        prompt = task
        if feedback:
            prompt += ("\n\nYOUR PREVIOUS ATTEMPT WAS REJECTED:\n"
                       f"{feedback}\n\nYour changes were reverted, so the files are "
                       "back to their original state. Start again and avoid "
                       "these problems.")
        state = {}
        res = run_worker(model=model, system=CODER_SYSTEM + project_notes(ws), task=prompt,
                         tools=make_tools(ws, state), state=state)
        touched |= set(res.get("files", []))

        if res["status"] != "done":
            feedback = ("You ran out of steps without finishing. Work in smaller "
                        "steps and call run_tests after each change.")
            history.append({"attempt": attempt, "stage": "coder", "result": res["status"]})
            continue

        added = _new_test_names(ws)
        if added and baseline is not None:
            now = count_tests_run(ws)
            if now is not None and now < baseline + len(added):
                print(f"\nBLOCKING: tests were added but the runner ran only {now} (expected at least {baseline + len(added)}).")
                feedback = ("You added tests (" + ", ".join(added) + ") but the test runner "
                            "does not run them. Write tests as methods named test_something "
                            "inside a class that inherits from django.test.TestCase, and use "
                            "self.client. Never write module-level test functions or use "
                            "pytest fixtures.")
                history.append({"attempt": attempt, "stage": "collect-check", "blocking": True,
                                "notes": feedback})
                continue
        print("\n" + "=" * 60 + f"\nATTEMPT {attempt}: REVIEWER\n" + "=" * 60)
        rev = review(model, ws, task)
        notes = rev.get("summary") or ""
        history.append({"attempt": attempt, "stage": "review", "verdict": rev["verdict"],
                        "blocking": bool(rev.get("auto")), "notes": notes[:3000]})
        if rev.get("auto"):
            print("\nBLOCKING REJECT from automated checks")
            feedback = notes[:1500]
            continue
        print("\nAutomated checks passed. Reviewer opinion (advisory):", rev["verdict"])
        reviewer_notes = rev["verdict"] + "\n" + notes
        approved = True
        break

    outcome = {"task": task, "model": model, "when": time.strftime("%F %T"),
               "approved": approved, "history": history}

    if not approved:
        outcome["status"] = "failed"
        print("\nSTOPPED: no approved result after all attempts.")
        print("The last attempt's changes are still in the workspace. Inspect with: git diff")
    else:
        print("\n" + "=" * 60 + "\nAPPROVED. CHANGES TO COMMIT:\n" + "=" * 60)
        print(_git(ws, "diff", "HEAD", "--relative", "--", ".").stdout)
        print("-" * 60)
        print("REVIEWER OPINION (advisory, from the small model):")
        print(reviewer_notes[:1500])
        print("-" * 60)
        answer = input("Commit these changes? [y/N] ").strip().lower()
        if answer == "y":
            _git(ws, "add", "-A", "--", ".")
            c = _git(ws, "commit", "-m", f"Worker: {(label or task)[:60]}")
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
