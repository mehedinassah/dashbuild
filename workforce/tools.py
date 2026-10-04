import re
import subprocess
import sys
from pathlib import Path


def count_tests(text):
    return len(re.findall(r"^\s*def test_", text, re.M))


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
        """Write the complete new contents of a file in the workspace.

        Args:
            path: Relative path, for example calculator.py
            content: The full file contents
        """
        p = safe(path)
        if p.exists():
            old = p.read_text()
            if count_tests(content) < count_tests(old):
                return ("REJECTED: this would delete existing tests "
                        f"({count_tests(old)} -> {count_tests(content)}). "
                        "Keep every existing test. Update a test only if the "
                        "behavior it checks has genuinely changed.")
            old_lines = len(old.splitlines())
            if old_lines >= 10 and len(content.splitlines()) < old_lines * 0.7:
                return ("REJECTED: the new file is much shorter than the old one. "
                        "Read the file again and write the full contents, "
                        "keeping everything that is not part of the change.")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        state["written"].add(path)
        state["tests_passed"] = False
        return f"Wrote {path}"

    def edit_file(path: str, old_text: str, new_text: str) -> str:
        """Replace one exact piece of text in a file. Prefer this over write_file
        for changes to existing files.

        Args:
            path: Relative path, for example calculator.py
            old_text: Text to replace. It must appear exactly once in the file.
            new_text: The replacement text
        """
        content = safe(path).read_text()
        n = content.count(old_text)
        if n == 0:
            return "ERROR: old_text not found. Read the file again and copy the text exactly."
        if n > 1:
            return f"ERROR: old_text appears {n} times. Include more surrounding lines so it is unique."
        return write_file(path, content.replace(old_text, new_text, 1))

    def run_tests() -> str:
        """Run pytest in the workspace and return the output."""
        r = subprocess.run([sys.executable, "-m", "pytest", "-q"],
                           cwd=ws, capture_output=True, text=True, timeout=120)
        state["tests_passed"] = (r.returncode == 0)
        return (r.stdout + r.stderr)[-3000:]

    return [list_files, read_file, write_file, edit_file, run_tests]
