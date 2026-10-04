import ast
import subprocess
from pathlib import Path
from .tools import make_tools
from .worker import run_worker

REVIEW_SYSTEM = (
    "You are a code reviewer. You cannot edit files. Call one tool at a time. "
    "First call get_diff, then read_file on the changed files. Check only these "
    "things: (1) every requirement stated in the task is met; (2) no existing "
    "test was deleted; (3) no existing test was weakened, for example by "
    "changing its expected value just to make it pass, or by turning it into a "
    "duplicate of another test; (4) the code has no obvious bugs or duplicated "
    "definitions. Do NOT ask for extra features, extra edge cases, or tests the "
    "task did not mention. Pay attention to any AUTOMATED FINDINGS in the task. "
    "Run run_tests once. Finish with a short list of problems, then a last line "
    "that is exactly 'VERDICT: APPROVE' or 'VERDICT: REJECT'."
)


def _git(ws, *args):
    return subprocess.run(["git", *args], cwd=ws, capture_output=True,
                          text=True, timeout=30)


def _tests(src):
    """Map test function name -> (body dump, source text)."""
    out = {}
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            body = "\n".join(ast.dump(n) for n in node.body)
            out[node.name] = (body, ast.get_source_segment(src, node) or node.name)
    return out


def test_findings(ws):
    """Deterministic checks on changed test files. Returns (hard, soft)."""
    hard, soft = [], []
    names = _git(ws, "diff", "HEAD", "--name-only", "--relative", "--", ".").stdout.split()
    for rel in names:
        base = Path(rel).name
        if not ((base.startswith("test_") or base == "tests.py") and base.endswith(".py")):
            continue
        old_src = _git(ws, "show", f"HEAD:./{rel}")
        if old_src.returncode != 0 or not (ws / rel).exists():
            continue
        try:
            old, new = _tests(old_src.stdout), _tests((ws / rel).read_text())
        except SyntaxError as e:
            hard.append(f"{rel}: does not parse ({e})")
            continue
        for name in old:
            if name not in new:
                hard.append(f"{rel}: existing test {name} was deleted")
        for name, (body, src) in new.items():
            if name in old and old[name][0] != body:
                twin = [n for n, (b, _) in new.items() if n != name and b == body]
                if twin:
                    hard.append(f"{rel}: {name} was changed so it now duplicates "
                                f"{twin[0]}; it no longer tests what its name says")
                else:
                    soft.append(f"{rel}: existing test {name} was CHANGED.\n"
                                f"OLD:\n{old[name][1]}\nNEW:\n{src}\n"
                                "Does the new version still test what its name says?")
    return hard, soft


def review(model, workspace, task, auto_reject=True):
    ws = Path(workspace).resolve()
    _git(ws, "add", "-N", "--", ".")
    hard, soft = test_findings(ws)
    if hard and auto_reject:
        print("AUTOMATED REJECT:\n- " + "\n- ".join(hard))
        return {"verdict": "REJECT", "summary": "\n".join(hard), "auto": True}

    state = {}
    base = {f.__name__: f for f in make_tools(ws, state)}

    def get_diff() -> str:
        """Show all uncommitted changes in the workspace as a git diff."""
        r = _git(ws, "diff", "HEAD", "--relative", "--", ".")
        return (r.stdout or "No changes.")[:6000]

    findings = ""
    if hard or soft:
        findings = "\n\nAUTOMATED FINDINGS:\n" + "\n\n".join(hard + soft)
    tools = [base["list_files"], base["read_file"], base["run_tests"], get_diff]
    result = run_worker(
        model=model, system=REVIEW_SYSTEM,
        task=f"The coder was given this task:\n{task}{findings}\n\nReview the changes.",
        tools=tools, state=state, require_tests=False, max_steps=8)
    summary = result.get("summary") or ""
    # Anything unclear counts as a rejection.
    result["verdict"] = "APPROVE" if "VERDICT: APPROVE" in summary.upper() else "REJECT"
    return result
