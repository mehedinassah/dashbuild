"""The autopilot: describe a business -> the agent designs, proposes rules, builds each one
test-first on a git branch. You approve each card (or pass --yes)."""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from . import notes, pipeline, rules, scorecard
from .config import CFG

ROOT = Path(__file__).parent.parent
STATE = ROOT / "autopilot_state.json"


def git(ws, *args, check=True):
    r = subprocess.run(["git", *args], cwd=ws, capture_output=True, text=True)
    if check and r.returncode:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


def preflight(ws, model, check_ollama=True):
    if not (Path(ws) / "manage.py").exists() and not (Path(ws) / ".workforce.json").exists():
        return f"{ws} does not look like a workspace project"
    if git(ws, "status", "--porcelain", check=False).strip():
        return "the git tree has uncommitted changes. Commit or stash them first."
    if check_ollama:
        try:
            import ollama
            names = [m.model for m in ollama.list().models]
        except Exception as e:
            return f"cannot reach Ollama ({e}). Is it running?"
        if not any(n == model or n.split(":")[0] == model for n in names):
            return f"model {model} is not installed. Run: ollama pull {model}"
    return None


def load_state():
    return json.loads(STATE.read_text()) if STATE.exists() else {"done": [], "failed": {}, "declined": []}


def save_state(s):
    STATE.write_text(json.dumps(s, indent=1))


def show_change(ws, files):
    git(ws, "add", "-N", *files, check=False)
    print(git(ws, "diff", "--", *files, check=False))


def revert(ws, files):
    for f in files:
        git(ws, "reset", "-q", "--", f, check=False)  # also undoes the intent-to-add from show_change
        tracked = subprocess.run(["git", "ls-files", "--error-unmatch", f], cwd=ws,
                                 capture_output=True).returncode == 0
        if tracked:
            git(ws, "checkout", "--", f)
        else:
            (Path(ws) / f).unlink(missing_ok=True)


def run_cards(ws, cards, model, yes=False, ask=input, state=None, log=print, root=None,
              repair=None, repair_fn=None):
    state = state if state is not None else load_state()
    repair = CFG.get("repair_rounds", 2) if repair is None else repair
    repair_fn = repair_fn or rules.repair_spec
    for c in cards:
        cid = pipeline.card_id(c)
        if cid in state["done"]:
            log(f"skip {cid} (already done)")
            continue
        res = pipeline.run_card(ws, c, model, log=log)
        rounds = 0
        while res["status"] != "passed" and rounds < repair and rules.repairable(c, res["reason"]):
            rounds += 1
            try:
                new = repair_fn(ws, c, res["reason"], model)
            except Exception as e:  # a model hiccup must never stop the run
                log(f"[repair] could not rewrite the rule: {e}")
                new = None
            if not new:
                break
            log(f"[repair {rounds}/{repair}] {cid} failed. The model rewrote the rule:\n  {new}")
            c = dict(c, spec=new)
            state.setdefault("repaired", {})[cid] = new
            save_state(state)
            res = pipeline.run_card(ws, c, model, log=log)
        scorecard.record(res, root)
        if res["status"] != "passed":
            log(f"FAILED {cid}: {res['reason'][:300]}")
            state["failed"][cid] = res["reason"][:300]
            save_state(state)
            continue
        show_change(ws, res["files"])
        if res["kill_rate"] is None:
            log(f"PASSED {cid} (migration created, whole test suite green)")
        else:
            log(f"PASSED {cid} (bug-detection score {res['kill_rate']:.0%}, {res['attempts']} attempt(s))")
        approve = True if yes else None
        while approve is None:
            a = ask("Keep and commit this? Type y or n, then Enter: ").strip().lower()
            if a in ("y", "yes"):
                approve = True
            elif a in ("n", "no"):
                approve = False
            else:
                log("Please type just y or n.")
        if approve:
            git(ws, "add", *res["files"])
            git(ws, "-c", "user.name=workforce", "-c", "user.email=workforce@local",
                "commit", "-qm", f"auto: {cid}\n\n{c['spec']}")
            state["done"].append(cid)
            state["failed"].pop(cid, None)
        else:
            revert(ws, res["files"])
            state["declined"].append(cid)
        save_state(state)
    return state


def run_auto(args):
    ws = Path(args.workspace).resolve()
    model = args.model or CFG["model"]
    problem = preflight(ws, model, check_ollama=not args.no_preflight)
    if problem:
        print("Cannot start:", problem)
        return 1
    state = load_state() if args.resume else {"done": [], "failed": {}, "declined": []}
    if not args.resume:
        branch = "auto/" + time.strftime("%Y%m%d-%H%M%S")
        git(ws, "checkout", "-q", "-b", branch)
        state["branch"] = branch
        print("Working on branch", branch, "- your main branch is untouched.")
    if args.cards:
        cards, problems = rules.validate_cards(ws, json.loads(Path(args.cards).read_text())["cards"])
    else:
        if args.description and not args.no_design and not args.resume:
            from . import design
            print("Designing modules...")
            modules, skipped = design.propose(args.description, str(ws))
            design.build_from_file(str(ws))
            if git(ws, "status", "--porcelain", check=False).strip():
                git(ws, "add", "-A")
                git(ws, "-c", "user.name=workforce", "-c", "user.email=workforce@local",
                    "commit", "-qm", "auto: generate modules from design")
        print("Proposing business rules...")
        cards, problems = rules.propose_cards(args.description or "", ws, model)
        if args.save_cards:
            Path(args.save_cards).write_text(json.dumps({"cards": cards}, indent=1))
    for p in problems:
        print("note:", p)
    if not cards:
        print("No valid cards. Write your own with --cards cards.json")
        return 1
    print(f"{len(cards)} card(s):")
    for c in cards:
        print(f"  - {pipeline.card_id(c)}: {c['spec']}")
    save_state(state)
    state = run_cards(ws, cards, model, yes=args.yes, state=state)
    print(f"\nDone: {len(state['done'])} built, {len(state['failed'])} failed, "
          f"{len(state['declined'])} declined.")
    for k, v in state["failed"].items():
        print(f"  failed {k}: {v[:120]}")
    print(f"Review:  git log --oneline   (branch {state.get('branch')})")
    print("Keep it:  ./wfa ship     (merges, tests, writes the handoff, backs up)")
    print("Discard: git checkout master && git branch -D " + str(state.get("branch")))
    return 0


def run_plan(args, ask=input, out=print):
    """One sentence -> the model drafts cards -> Python validates -> you keep, drop or edit each."""
    ws = Path(args.workspace).resolve()
    model = args.model or CFG["model"]
    problem = preflight(ws, model, check_ollama=not args.no_preflight)
    if problem and "uncommitted" not in problem:
        out("Cannot start: " + problem)
        return 1
    out("Drafting cards...")
    cards, problems = rules.propose_cards(args.description, ws, model)
    for p in problems:
        out("note: " + p)
    if not cards:
        out("The model proposed no valid cards. Try a more specific sentence, or write the cards yourself.")
        return 1
    kept = []
    for i, c in enumerate(cards, 1):
        what = (f"field {c['class']}.{c['name']} = {c['definition']}" if c["kind"] == "field"
                else f"{c['kind']} {(c['class'] + '.') if c['class'] else ''}{c['name']}")
        out(f"\nCard {i} of {len(cards)}: {what}\n  Rule: {c['spec']}")
        while True:
            a = ask("Keep this card? y = keep, n = drop, e = change the rule text: ").strip().lower()
            if a in ("y", "yes"):
                kept.append(c)
                break
            if a in ("n", "no"):
                break
            if a in ("e", "edit"):
                c = dict(c, spec=ask("New rule text: ").strip())
                out("  Rule: " + c["spec"])
                continue
            out("Please type y, n or e.")
    kept, problems = rules.validate_cards(ws, kept)
    for p in problems:
        out("note: " + p)
    if not kept:
        out("No cards kept.")
        return 1
    Path(args.out).write_text(json.dumps({"cards": kept}, indent=1) + "\n")
    out(f"\nSaved {len(kept)} card(s) to {args.out}. Read the file, change anything you like, then:")
    out(f"  git add {args.out} && git commit -m 'Add cards'")
    out(f"  ./wfa auto --cards {args.out} --no-design")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="wfa")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("auto", help="design, propose rules and build them test-first")
    a.add_argument("description", nargs="?", default="")
    a.add_argument("--workspace", default=str(ROOT / "workspace_crm"))
    a.add_argument("--model")
    a.add_argument("--yes", action="store_true", help="commit every passing card without asking")
    a.add_argument("--cards", help="use your own cards.json instead of asking the model")
    a.add_argument("--save-cards", help="write the proposed cards to this file")
    a.add_argument("--resume", action="store_true")
    a.add_argument("--no-design", action="store_true")
    a.add_argument("--no-preflight", action="store_true")
    pl = sub.add_parser("plan", help="one sentence -> the model drafts cards, you keep/drop/edit them")
    pl.add_argument("description")
    pl.add_argument("--workspace", default=str(ROOT / "workspace_crm"))
    pl.add_argument("--model")
    pl.add_argument("--out", default="cards_plan.json")
    pl.add_argument("--no-preflight", action="store_true")
    sh = sub.add_parser("ship", help="merge the finished branch, run the tests, write the handoff, back up")
    sh.add_argument("--workspace", default=str(ROOT / "workspace_crm"))
    sh.add_argument("--branch")
    sh.add_argument("--backup-dir")
    sub.add_parser("score", help="show what each model has managed")
    m = sub.add_parser("map", help="print the project map the agent sees")
    m.add_argument("--workspace", default=str(ROOT / "workspace_crm"))
    b = sub.add_parser("bench", help="compare models on a fixed set of cards")
    b.add_argument("models", nargs="+")
    args = ap.parse_args(argv)
    if args.cmd == "auto":
        return run_auto(args)
    if args.cmd == "plan":
        return run_plan(args)
    if args.cmd == "ship":
        from . import ship
        return ship.run_ship(args)
    if args.cmd == "score":
        print(scorecard.summary())
        return 0
    if args.cmd == "map":
        print(notes.project_map(args.workspace))
        return 0
    from . import bench
    return bench.run(args.models)


if __name__ == "__main__":
    sys.exit(main())
