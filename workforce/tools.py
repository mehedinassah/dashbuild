import re
import subprocess
import sys
from pathlib import Path


def test_names(text):
    return set(re.findall(r"^\s*def (test_\w+)", text, re.M))


def make_tools(workspace, state):
    """Build workspace tools. `state` is a dict the controller shares with the worker."""
    ws = Path(workspace).resolve()
    state.setdefault("written", set())
    state.setdefault("tests_passed", False)

    def safe(path):
        path = str(path)
        if path.startswith("workspace/"):
            path = path[len("workspace/"):]
        p = (ws / path).resolve()
        if p != ws and ws not in p.parents:
            raise ValueError("path is outside the workspace")
        return p

    def list_files() -> str:
        """List all files in the workspace."""
        skip = {".pytest_cache", "__pycache__"}
        return "\n".join(sorted(
            str(p.relative_to(ws)) for p in ws.rglob("*")
            if p.is_file() and not (skip & set(p.parts))
        ))

    def read_file(path: str) -> str:
        """Read a file from the workspace.

        Args:
            path: Relative path, for example calculator.py
        """
        return safe(path).read_text()

    def write_file(path: str, content: str) -> str:
        """Write the complete new contents of a file. Use for new or very small files.

        Args:
            path: Relative path, for example calculator.py
            content: The full file contents
        """
        p = safe(path)
        if p.exists():
            old = p.read_text()
            missing = sorted(test_names(old) - test_names(content))
            if missing:
                return ("REJECTED: this would delete existing tests: "
                        + ", ".join(missing) + ". Keep every existing test. "
                        "To add new tests use append_file.")
            old_lines = len(old.splitlines())
            if old_lines >= 10 and len(content.splitlines()) < old_lines * 0.7:
                return ("REJECTED: the new file is much shorter than the old one. "
                        "Keep everything that is not part of the change.")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        state["written"].add(path)
        state["tests_passed"] = False
        return f"Wrote {path}"

    def append_file(path: str, text: str) -> str:
        """Add text to the END of an existing file. Use this to add new tests.

        Args:
            path: Relative path, for example test_calculator.py
            text: The new text to add (for example one or more new test functions)
        """
        p = safe(path)
        if not p.exists():
            return "ERROR: file does not exist. Use write_file to create it."
        old = p.read_text()
        sep = "" if old.endswith("\n") else "\n"
        return write_file(path, old + sep + "\n" + text.rstrip("\n") + "\n")

    def edit_file(path: str, old_text: str, new_text: str) -> str:
        """Replace one exact piece of text in a file. Copy old_text exactly from read_file.

        Args:
            path: Relative path, for example calculator.py
            old_text: One or more complete lines to replace. Must not be empty and must appear exactly once.
            new_text: The replacement text
        """
        if not old_text.strip():
            return ("ERROR: old_text is empty. Copy complete lines from read_file. "
                    "To add new tests at the end of a file, use append_file.")
        content = safe(path).read_text()
        n = content.count(old_text)
        if n == 0:
            return "ERROR: old_text not found. Read the file again and copy the lines exactly."
        if n > 1:
            where = [str(content.count("\n", 0, m.start()) + 1)
                     for m in re.finditer(re.escape(old_text), content)]
            return (f"ERROR: old_text appears {n} times (starting at lines "
                    f"{', '.join(where)}). Include more surrounding lines so it "
                    "matches exactly once.")
        return write_file(path, content.replace(old_text, new_text, 1))

    def run_tests() -> str:
        """Run pytest in the workspace and return the output."""
        r = subprocess.run([sys.executable, "-m", "pytest", "-q"],
                           cwd=ws, capture_output=True, text=True, timeout=120)
        state["tests_passed"] = (r.returncode == 0)
        return (r.stdout + r.stderr)[-3000:]

    return [list_files, read_file, write_file, append_file, edit_file, run_tests]
