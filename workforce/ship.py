"""./wfa ship: merge the finished autopilot branch, prove the suite is green, write the handoff, back up.
Everything here is plain git and Python: no model involved."""
import tarfile
import time
from pathlib import Path

from . import auto, pagecheck, pipeline
from .config import CFG

SKIP_DIRS = {".venv", "__pycache__", "node_modules", ".pytest_cache"}


def default_branch(ws):
    for b in ("master", "main"):
        if auto.git(ws, "rev-parse", "--verify", "-q", b, check=False).strip():
            return b
    return None


def _skip(member):
    parts = Path(member.name).parts
    if SKIP_DIRS & set(parts) or Path(member.name).name.startswith("db.sqlite3"):
        return None
    return member


def backup(top, dest_dir):
    dest_dir = Path(dest_dir).expanduser()
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / f"{Path(top).name}-backup-{time.strftime('%Y%m%d-%H%M')}.tar.gz"
    with tarfile.open(out, "w:gz") as t:
        t.add(top, arcname=Path(top).name, filter=_skip)
    return out


def run_ship(args, out=print):
    ws = Path(args.workspace).resolve()
    if auto.git(ws, "status", "--porcelain", check=False).strip():
        out("Cannot ship: the git tree has uncommitted changes. Commit or stash them first.")
        return 1
    state = auto.load_state()
    branch = args.branch or state.get("branch")
    main = default_branch(ws)
    if not branch or not main:
        out("Nothing to ship: no autopilot branch is recorded. Run ./wfa auto first.")
        return 1
    if not auto.git(ws, "rev-parse", "--verify", "-q", branch, check=False).strip():
        out(f"Nothing to ship: branch {branch} does not exist (already shipped?).")
        return 1
    new = auto.git(ws, "log", "--format=%s", f"{main}..{branch}", check=False).strip().splitlines()
    auto.git(ws, "checkout", "-q", main)
    before = auto.git(ws, "rev-parse", "HEAD").strip()
    if not new:
        auto.git(ws, "branch", "-D", branch, check=False)
        out(f"{branch} held no new work (every card failed or was declined). Branch removed.")
        return 0
    pages_before = pagecheck.check(ws)
    r = auto.subprocess.run(["git", "merge", "--no-edit", branch], cwd=ws, capture_output=True, text=True)
    if r.returncode:
        auto.git(ws, "merge", "--abort", check=False)
        out("The merge did not go through, nothing was changed:\n" + (r.stdout + r.stderr)[-400:])
        return 1
    suite = pipeline.run_suite(ws)
    if not suite["ok"]:
        auto.git(ws, "reset", "--hard", before)
        out("The merged project fails its tests, so the merge was undone. Branch kept.\n"
            + suite["output"][-600:])
        return 1
    bad = pagecheck.new_problems(pages_before, pagecheck.check(ws))
    if bad:
        auto.git(ws, "reset", "--hard", before)
        out("The merged project has page problems, so the merge was undone. Branch kept.\n  " + "\n  ".join(bad[:5]))
        return 1
    auto.git(ws, "branch", "-d", branch, check=False)
    top = Path(auto.git(ws, "rev-parse", "--show-toplevel").strip())
    built = [s.replace("auto: ", "") for s in new if s.startswith("auto: ")]
    repaired = sorted((state.get("repaired") or {}).keys())
    failed = sorted(state.get("failed", {}))
    lines = [f"\n## Shipped {time.strftime('%Y-%m-%d %H:%M')} ({branch})",
             f"- Built: {', '.join(built) or 'nothing'}",
             f"- Rules the agent rewrote itself: {', '.join(repaired) or 'none'}",
             f"- Failed: {', '.join(failed) or 'none'}",
             f"- Test suite after merge: {suite['ran']} tests OK"]
    h = top / "HANDOFF.md"
    h.write_text((h.read_text() if h.exists() else "# Handoff\n") + "\n".join(lines) + "\n")
    auto.git(ws, "add", str(h))
    auto.git(ws, "-c", "user.name=workforce", "-c", "user.email=workforce@local", "commit", "-qm",
             f"ship {branch}")
    dest = args.backup_dir or CFG.get("backup_dir") or str(Path.home() / "ai-workforce-backups")
    zipf = backup(top, dest)
    state["shipped"] = branch
    state["branch"] = None
    auto.save_state(state)
    out(f"Shipped {len(built)} card(s). The suite is green ({suite['ran']} tests).")
    out(f"Handoff updated in {h.name}. Backup: {zipf} ({zipf.stat().st_size // 1024} KB)")
    return 0
