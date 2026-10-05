import ast
import io
import json
import re
import subprocess
import sys
from pathlib import Path


def test_names(text):
    return set(re.findall(r"^\s*def (test_\w+)", text, re.M))


def undefined_names(src):
    try:
        from pyflakes import api, reporter
    except ImportError:
        return []
    out = io.StringIO()
    api.check(src, "code", reporter.Reporter(out, out))
    return [l for l in out.getvalue().splitlines() if "undefined name" in l]


def count_tests_run(ws):
    ws = Path(ws)
    p = ws / ".workforce.json"
    cfg = json.loads(p.read_text()) if p.exists() else {}
    cmd = list(cfg.get("test_cmd") or ["python", "-m", "pytest", "-q"])
    if cmd[0] == "python":
        cmd[0] = sys.executable
    r = subprocess.run(cmd, cwd=ws, capture_output=True, text=True, timeout=180)
    out = r.stdout + r.stderr
    m = re.search(r"Ran (\d+) tests?", out) or re.search(r"(\d+) passed", out)
    return int(m.group(1)) if m else None


def python_problem(src):
    """Return a description of an obvious structural problem, or None."""
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return (f"this is not valid Python (line {e.lineno}: {e.msg}). Write it "
                "again with correct line breaks and indentation.")
    undefined = undefined_names(src)
    if undefined:
        return ("a name is used but never imported or defined: " + undefined[0]
                + ". Add the missing import.")
    seen, imports = set(), set()
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in seen:
                return f"'{node.name}' is defined more than once. Keep a single definition."
            seen.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            key = ast.dump(node)
            if key in imports:
                return "the same import appears more than once. Remove the duplicate."
            imports.add(key)
    return None


def make_tools(workspace, state):
    """Build workspace tools. `state` is a dict the controller shares with the worker."""
    ws = Path(workspace).resolve()
    state.setdefault("written", set())
    state.setdefault("tests_passed", False)
    cfg_path = ws / ".workforce.json"
    cfg = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}

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
        if Path(str(path)).name == ".workforce.json":
            return "REJECTED: this file is protected."
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
        if str(path).endswith(".html"):
            for m in re.finditer(r"{%\s*extends\s+['\"]([^'\"]+)['\"]", content):
                target = m.group(1)
                found = any(q.as_posix() == target or q.as_posix().endswith("/" + target)
                            for q in ws.rglob("*.html"))
                if not found:
                    return ("REJECTED: the template extends '" + target + "' which does not "
                            "exist. Write a complete standalone HTML page with <html>, <head> "
                            "and <body>, and no extends tag.")
        if str(path).endswith(".py"):
            problem = python_problem(content)
            if problem:
                return "REJECTED: " + problem
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
        """Run the project tests and return the output."""
        cmd = list(cfg.get("test_cmd") or ["python", "-m", "pytest", "-q"])
        if cmd[0] == "python":
            cmd[0] = sys.executable
        r = subprocess.run(cmd, cwd=ws, capture_output=True, text=True, timeout=120)
        state["tests_passed"] = (r.returncode == 0)
        return (r.stdout + r.stderr)[-3000:]

    def run_command(command: str) -> str:
        """Run an allowed project command, for example: python manage.py makemigrations customers

        Args:
            command: The full command. Only allow-listed commands work.
        """
        parts = command.split()
        allowed = cfg.get("commands", [])
        if not parts or not any(parts[:len(a)] == a for a in allowed):
            return ("REJECTED: command not allowed. Allowed: "
                    + "; ".join(" ".join(a) for a in allowed))
        if parts[0] == "python":
            parts[0] = sys.executable
        r = subprocess.run(parts, cwd=ws, capture_output=True, text=True, timeout=120)
        return f"exit code {r.returncode}\n" + (r.stdout + r.stderr)[-3000:]

    tools = [list_files, read_file, write_file, append_file, edit_file, run_tests]
    if cfg.get("commands"):
        tools.append(run_command)
    return tools
