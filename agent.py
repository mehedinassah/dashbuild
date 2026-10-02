from ollama import chat
from pathlib import Path
import json
import re
import subprocess
import sys


# ============================================================
# CONFIGURATION
# ============================================================

MODEL = "qwen2.5-coder:7b"

PROJECT_ROOT = Path.cwd().resolve()
WORKSPACE = (PROJECT_ROOT / "workspace").resolve()

MAX_STEPS = 20


# ============================================================
# SAFE PATH HANDLING
# ============================================================

def safe_path(path):
    """
    Resolve a path inside the controlled workspace.

    The Git repository itself is outside the workspace,
    so Git tools use PROJECT_ROOT separately.
    """

    target = (WORKSPACE / path).resolve()

    try:
        target.relative_to(WORKSPACE)
    except ValueError:
        raise ValueError(
            "Access denied: path is outside the workspace."
        )

    return target


# ============================================================
# LIST FILES
# ============================================================

def list_files():
    try:
        files = []

        for path in WORKSPACE.rglob("*"):
            if path.is_file():
                files.append(
                    str(path.relative_to(WORKSPACE))
                )

        return files

    except Exception as e:
        return f"ERROR listing files: {e}"


# ============================================================
# READ FILE
# ============================================================

def read_file(path):
    try:
        target = safe_path(path)

        if not target.exists():
            return f"File not found: {path}"

        if not target.is_file():
            return f"Not a file: {path}"

        return target.read_text(
            encoding="utf-8"
        )

    except Exception as e:
        return f"ERROR reading file: {e}"


# ============================================================
# WRITE FILE
# ============================================================

def write_file(path, content):
    try:
        target = safe_path(path)

        target.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        target.write_text(
            content,
            encoding="utf-8"
        )

        return (
            f"File written successfully: {path}"
        )

    except Exception as e:
        return f"ERROR writing file: {e}"


# ============================================================
# RUN PYTHON
# ============================================================

def run_python(path):
    try:
        target = safe_path(path)

        if not target.exists():
            return f"File not found: {path}"

        if not target.is_file():
            return f"Not a file: {path}"

        if target.suffix != ".py":
            return (
                "ERROR: run_python can only execute "
                "Python files."
            )

        # Never execute pytest files with run_python.
        if target.name.startswith("test_"):
            return (
                "ERROR: Do not use run_python on test files. "
                "Use run_tests instead."
            )

        result = subprocess.run(
            [
                sys.executable,
                str(target)
            ],
            cwd=WORKSPACE,
            capture_output=True,
            text=True,
            timeout=10
        )

        output = []

        output.append(
            f"Exit code: {result.returncode}"
        )

        if result.stdout.strip():
            output.append(
                "STDOUT:\n" + result.stdout.strip()
            )

        if result.stderr.strip():
            output.append(
                "STDERR:\n" + result.stderr.strip()
            )

        return "\n\n".join(output)

    except subprocess.TimeoutExpired:
        return (
            "ERROR: Python program timed out "
            "after 10 seconds."
        )

    except Exception as e:
        return f"ERROR running Python: {e}"


# ============================================================
# RUN TESTS
# ============================================================

def run_tests(path=None):
    try:

        # ----------------------------------------------------
        # Automatically find a single test file
        # ----------------------------------------------------

        if path is None:

            test_files = [
                p
                for p in WORKSPACE.glob("test_*.py")
                if p.is_file()
            ]

            if len(test_files) == 1:

                path = str(
                    test_files[0].relative_to(WORKSPACE)
                )

            elif len(test_files) > 1:

                return (
                    "TEST RESULT: FAIL\n"
                    "REASON: Multiple test files found. "
                    "Specify which test file to run."
                )

            else:

                return (
                    "TEST RESULT: FAIL\n"
                    "REASON: No pytest test file was found."
                )

        # ----------------------------------------------------
        # Validate test path
        # ----------------------------------------------------

        target = safe_path(path)

        if not target.exists():
            return f"Not a file: {path}"

        if not target.is_file():
            return f"Not a file: {path}"

        if not target.name.startswith("test_"):
            return (
                "ERROR: run_tests requires a pytest "
                "file whose name starts with 'test_'."
            )

        # ----------------------------------------------------
        # Run pytest
        # ----------------------------------------------------

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                str(target)
            ],
            cwd=WORKSPACE,
            capture_output=True,
            text=True,
            timeout=20
        )

        output = (
            result.stdout.strip()
            + "\n"
            + result.stderr.strip()
        ).strip()

        # ----------------------------------------------------
        # Detect no tests
        # ----------------------------------------------------

        if (
            "no tests ran" in output.lower()
            or "collected 0 items" in output.lower()
        ):
            return (
                "TEST RESULT: FAIL\n"
                "REASON: No tests were collected.\n\n"
                + output
            )

        # ----------------------------------------------------
        # Detect collection errors
        # ----------------------------------------------------

        if "ERROR collecting" in output:
            return (
                "TEST RESULT: FAIL\n"
                "REASON: Pytest collection error.\n\n"
                + output
            )

        # ----------------------------------------------------
        # Normal pytest result
        # ----------------------------------------------------

        if result.returncode == 0:

            return (
                "TEST RESULT: PASS\n\n"
                + output
            )

        return (
            "TEST RESULT: FAIL\n\n"
            + output
        )

    except subprocess.TimeoutExpired:
        return (
            "TEST RESULT: FAIL\n"
            "REASON: Tests timed out after 20 seconds."
        )

    except Exception as e:
        return (
            "TEST RESULT: FAIL\n"
            f"REASON: {e}"
        )


# ============================================================
# GIT STATUS
# ============================================================

def git_status():
    try:

        result = subprocess.run(
            [
                "git",
                "status",
                "--short"
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:

            return (
                "GIT STATUS ERROR:\n"
                + result.stderr.strip()
            )

        if not result.stdout.strip():

            return "Git working tree is clean."

        return (
            "Git working tree changes:\n"
            + result.stdout.strip()
        )

    except subprocess.TimeoutExpired:

        return (
            "GIT STATUS ERROR: "
            "Git command timed out."
        )

    except Exception as e:

        return (
            f"GIT STATUS ERROR: {e}"
        )


# ============================================================
# GIT DIFF
# ============================================================

def git_diff():
    try:

        result = subprocess.run(
            [
                "git",
                "diff"
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:

            return (
                "GIT DIFF ERROR:\n"
                + result.stderr.strip()
            )

        if not result.stdout.strip():

            return (
                "Git diff is empty. "
                "There are no unstaged changes."
            )

        return result.stdout

    except subprocess.TimeoutExpired:

        return (
            "GIT DIFF ERROR: "
            "Git command timed out."
        )

    except Exception as e:

        return (
            f"GIT DIFF ERROR: {e}"
        )


# ============================================================
# PARSE TOOL REQUEST
# ============================================================

def parse_tool_request(text):

    if not text:
        return None

    text = text.strip()

    # --------------------------------------------------------
    # Remove Markdown fences
    # --------------------------------------------------------

    text = re.sub(
        r"^```json\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"^```\s*",
        "",
        text
    )

    text = re.sub(
        r"\s*```$",
        "",
        text
    )

    text = text.strip()

    # --------------------------------------------------------
    # Parse JSON
    # --------------------------------------------------------

    try:

        data = json.loads(text)

    except json.JSONDecodeError:

        return None

    # --------------------------------------------------------
    # Normal tool format
    # --------------------------------------------------------

    if (
        isinstance(data, dict)
        and isinstance(data.get("name"), str)
        and isinstance(data.get("arguments"), dict)
    ):

        return {
            "name": data["name"],
            "arguments": data["arguments"]
        }

    # --------------------------------------------------------
    # Direct write_file format
    # --------------------------------------------------------

    if (
        isinstance(data, dict)
        and "path" in data
        and "content" in data
    ):

        return {
            "name": "write_file",
            "arguments": {
                "path": data["path"],
                "content": data["content"]
            }
        }

    return None


# ============================================================
# EXECUTE TOOL
# ============================================================

def execute_tool(name, arguments):

    try:

        if name == "list_files":

            return list_files()

        elif name == "read_file":

            path = arguments.get("path")

            if not path:

                return (
                    "ERROR: read_file requires "
                    "a path argument."
                )

            return read_file(path)

        elif name == "write_file":

            path = arguments.get("path")
            content = arguments.get("content")

            if not path:

                return (
                    "ERROR: write_file requires "
                    "a path argument."
                )

            if content is None:

                return (
                    "ERROR: write_file requires "
                    "content."
                )

            return write_file(
                path,
                content
            )

        elif name == "run_python":

            path = arguments.get("path")

            if not path:

                return (
                    "ERROR: run_python requires "
                    "a path argument."
                )

            return run_python(path)

        elif name == "run_tests":

            path = arguments.get("path")

            return run_tests(path)

        elif name == "git_status":

            return git_status()

        elif name == "git_diff":

            return git_diff()

        else:

            return (
                f"ERROR: Unknown tool '{name}'. "
                "Available tools are: "
                "list_files, read_file, write_file, "
                "run_python, run_tests, "
                "git_status, git_diff."
            )

    except Exception as e:

        return (
            f"ERROR executing tool '{name}': {e}"
        )


# ============================================================
# AI SYSTEM PROMPT
# ============================================================

tools_description = """
You are an AI software development agent working inside
a controlled workspace.

Your job is to inspect files, write code, run programs,
create tests, diagnose failures, fix problems, and inspect
Git changes.

============================================================
AVAILABLE TOOLS
============================================================

1. list_files

Arguments:
{}

Purpose:
List files inside the controlled workspace.

Example:

{
    "name": "list_files",
    "arguments": {}
}


2. read_file

Arguments:
{
    "path": "calculator.py"
}

Purpose:
Read a file inside the workspace.

IMPORTANT:
Paths are relative to the workspace directory.

Do NOT use:
agent.py

Use:
calculator.py

Do NOT use:
workspace/test_calculator.py

Use:
test_calculator.py


3. write_file

Arguments:
{
    "path": "calculator.py",
    "content": "..."
}

Purpose:
Create or replace a file inside the workspace.


4. run_python

Arguments:
{
    "path": "calculator.py"
}

Purpose:
Run a Python source file inside the workspace.

Do not use this tool for pytest files.


5. run_tests

Arguments:
{
    "path": "test_calculator.py"
}

Purpose:
Run pytest against a test file.

When possible, always provide the test file path.

A test file should contain real pytest test functions.


6. git_status

Arguments:
{}

Purpose:
Show the current Git working tree status.

Use this when you need to know whether files have
been modified, added, or deleted.

Git operates from the project root, not the workspace.


7. git_diff

Arguments:
{}

Purpose:
Show the current unstaged Git diff.

Use this when you need to inspect exactly
what has changed in the working tree.


============================================================
GENERAL RULES
============================================================

1. Work only inside the workspace when reading or
   modifying project files.

2. Git inspection is allowed through git_status
   and git_diff.

3. Inspect existing files before modifying them.

4. Never assume a file exists.

5. Never invent test results.

6. Do not claim a program works unless you have
   actually executed or tested it.

7. When fixing code, inspect the relevant source first.

8. When tests fail, inspect the failure before fixing code.

9. After modifying code, run the relevant tests.

10. Do not claim success while required tests fail.

11. Do not commit, push, deploy, or delete anything
    through Git. Git commit will be added later as
    a separate controlled tool.

12. Follow the requested task sequence exactly.

13. If the task explicitly says not to modify files,
    do not modify files.

14. If the task explicitly says not to run tests,
    do not run tests.

15. Do not call tools that are prohibited by the task.


============================================================
PYTEST RULES
============================================================

Tests must be real pytest functions.

Correct:

def test_add():
    assert calculate(10, 5, "add") == 15

Incorrect:

def test_calculator(calculate):
    assert calculate

Do not create tests that merely reference a function.

Tests must actually call the code being tested.

For run_tests:

{
    "name": "run_tests",
    "arguments": {
        "path": "test_calculator.py"
    }
}


============================================================
GIT RULES
============================================================

For git_status:

{
    "name": "git_status",
    "arguments": {}
}

For git_diff:

{
    "name": "git_diff",
    "arguments": {}
}

Do not commit anything.

Do not push anything.

Do not deploy anything.

Do not delete anything through Git.


============================================================
TOOL CALL FORMAT
============================================================

Return exactly one JSON object when calling a tool.

Example:

{
    "name": "git_status",
    "arguments": {}
}

Do not wrap JSON in Markdown fences.

Do not explain the tool call.

After receiving a tool result, decide the next action.


============================================================
FINISHING RULE
============================================================

Finish only after the requested task has actually
been completed and verified.
"""


# ============================================================
# TASK
# ============================================================

task = """
Inspect the current project Git changes.

Perform these actions in exactly this order:

1. Call git_status:

{
    "name": "git_status",
    "arguments": {}
}

2. After receiving the git_status result, call git_diff:

{
    "name": "git_diff",
    "arguments": {}
}

3. After git_diff returns, give a short summary of:

- which files are modified
- whether the changes are staged or unstaged
- what the main changes are

4. Then finish the task.

IMPORTANT:

- Do not call git_status more than once.
- Do not call git_diff more than once.
- Do not call read_file.
- Do not call list_files.
- Do not call run_tests.
- Do not call run_python.
- Do not call write_file.
- Do not modify any files.
- Do not commit anything.
"""


# ============================================================
# RUN AGENT
# ============================================================

def main():

    previous_calls = []

    # --------------------------------------------------------
    # Required tool sequence for this task
    # --------------------------------------------------------

    required_tools = [
        "git_status",
        "git_diff"
    ]

    completed_required_tools = []

    # --------------------------------------------------------
    # Conversation
    # --------------------------------------------------------

    messages = [
        {
            "role": "system",
            "content": tools_description
        },
        {
            "role": "user",
            "content": task
        }
    ]

    # --------------------------------------------------------
    # Agent loop
    # --------------------------------------------------------

    for step in range(
        1,
        MAX_STEPS + 1
    ):

        print()
        print("=" * 60)
        print(
            f"AGENT STEP {step}"
        )
        print("=" * 60)

        # ----------------------------------------------------
        # Ask model
        # ----------------------------------------------------

        try:

            response = chat(
                model=MODEL,
                messages=messages
            )

        except Exception as e:

            print()
            print(
                "ERROR communicating with Ollama:"
            )
            print(e)

            break

        content = (
            response.message.content or ""
        ).strip()

        print()
        print("AI:")
        print(content)

        # ----------------------------------------------------
        # Parse tool request
        # ----------------------------------------------------

        request = parse_tool_request(
            content
        )

        # ----------------------------------------------------
        # AI finished
        # ----------------------------------------------------

        if request is None:

            # If the required Git tools were completed,
            # this is the model's final summary.

            if (
                completed_required_tools
                == required_tools
            ):

                print()
                print(
                    "=" * 60
                )
                print(
                    "AGENT FINISHED"
                )
                print(
                    "=" * 60
                )

                break

            # Otherwise the model finished too early.

            print()
            print(
                "ERROR: AI finished before completing "
                "the required tool sequence."
            )

            break

        name = request["name"]
        arguments = request["arguments"]

        # ----------------------------------------------------
        # Enforce required tool sequence
        # ----------------------------------------------------

        if (
            len(completed_required_tools)
            < len(required_tools)
        ):

            expected_tool = required_tools[
                len(completed_required_tools)
            ]

            if name != expected_tool:

                print()
                print(
                    f"BLOCKED: Expected tool "
                    f"'{expected_tool}', but AI requested "
                    f"'{name}'."
                )

                tool_result = (
                    f"ERROR: The next required tool is "
                    f"'{expected_tool}'. "
                    f"Do not call '{name}'."
                )

                messages.append(
                    {
                        "role": "assistant",
                        "content": content
                    }
                )

                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Tool '{name}' was blocked.\n\n"
                            f"{tool_result}"
                        )
                    }
                )

                continue

        # ----------------------------------------------------
        # Track repeated calls
        # ----------------------------------------------------

        signature = (
            name,
            json.dumps(
                arguments,
                sort_keys=True
            )
        )

        previous_calls.append(
            signature
        )

        # ----------------------------------------------------
        # Detect repeated calls
        # ----------------------------------------------------

        if (
            len(previous_calls) >= 3
            and
            previous_calls[-1]
            == previous_calls[-2]
            == previous_calls[-3]
        ):

            print()
            print(
                "WARNING: AI has repeated the same "
                "tool call three times."
            )

            tool_result = (
                "ERROR: You have repeated the same "
                "tool call three times without making "
                "progress. Stop repeating it and "
                "complete the task."
            )

        else:

            # ------------------------------------------------
            # Execute tool
            # ------------------------------------------------

            print()
            print(
                f"Executing tool: {name}"
            )

            tool_result = execute_tool(
                name,
                arguments
            )

            # ------------------------------------------------
            # Mark required tool complete
            # ------------------------------------------------

            if (
                len(completed_required_tools)
                < len(required_tools)
                and
                name
                == required_tools[
                    len(completed_required_tools)
                ]
            ):

                completed_required_tools.append(
                    name
                )

        # ----------------------------------------------------
        # Print result
        # ----------------------------------------------------

        print()
        print(
            "TOOL RESULT:"
        )
        print(tool_result)

        # ----------------------------------------------------
        # Stop after git_diff
        # ----------------------------------------------------

        if (
            completed_required_tools
            == required_tools
        ):

            print()
            print(
                "=" * 60
            )
            print(
                "GIT INSPECTION COMPLETE"
            )
            print(
                "=" * 60
            )
            print(
                "The required Git inspection is complete."
            )

            break

        # ----------------------------------------------------
        # Add conversation history
        # ----------------------------------------------------

        messages.append(
            {
                "role": "assistant",
                "content": content
            }
        )

        messages.append(
            {
                "role": "user",
                "content": (
                    f"Tool '{name}' returned:\n\n"
                    f"{tool_result}"
                )
            }
        )

    else:

        print()
        print(
            "=" * 60
        )
        print(
            "AGENT STOPPED"
        )
        print(
            "=" * 60
        )

        print(
            "Agent stopped because it reached "
            f"the maximum number of steps "
            f"({MAX_STEPS})."
        )


# ============================================================
# PYTHON ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
