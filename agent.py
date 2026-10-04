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
# GIT COMMIT
# ============================================================

def git_commit(message, approved=False):

    if not approved:
        return (
            "GIT COMMIT BLOCKED: "
            "Explicit approval is required before committing."
        )

    if not message or not message.strip():
        return (
            "GIT COMMIT ERROR: "
            "A commit message is required."
        )

    try:

        status_result = subprocess.run(
            [
                "git",
                "status",
                "--porcelain"
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10
        )

        if status_result.returncode != 0:

            return (
                "GIT COMMIT ERROR: "
                + status_result.stderr.strip()
            )

        if not status_result.stdout.strip():

            return (
                "GIT COMMIT SKIPPED: "
                "Working tree is clean. Nothing to commit."
            )

        commit_result = subprocess.run(
            [
                "git",
                "add",
                "-A"
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10
        )

        if commit_result.returncode != 0:

            return (
                "GIT COMMIT ERROR while staging: "
                + commit_result.stderr.strip()
            )

        commit_result = subprocess.run(
            [
                "git",
                "commit",
                "-m",
                message.strip()
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=20
        )

        if commit_result.returncode != 0:

            return (
                "GIT COMMIT ERROR: "
                + commit_result.stderr.strip()
            )

        return (
            "GIT COMMIT SUCCESS:\n"
            + commit_result.stdout.strip()
        )

    except subprocess.TimeoutExpired:

        return (
            "GIT COMMIT ERROR: "
            "Git command timed out."
        )

    except Exception as e:

        return (
            f"GIT COMMIT ERROR: {e}"
        )


# ============================================================
# PARSE TOOL REQUEST
# ============================================================

def parse_tool_request(text):

    if not text:
        return None

    text = text.strip()

    # --------------------------------------------------------
    # Helper: validate a parsed JSON object
    # --------------------------------------------------------

    def extract_tool(data):

        if not isinstance(data, dict):
            return None

        # Normal tool format
        if (
            isinstance(data.get("name"), str)
            and isinstance(data.get("arguments"), dict)
        ):
            return {
                "name": data["name"],
                "arguments": data["arguments"]
            }

        # Direct write_file format
        if (
            "path" in data
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

    # --------------------------------------------------------
    # 1. Try the entire response first
    # --------------------------------------------------------

    cleaned = text

    cleaned = re.sub(
        r"```json\s*",
        "",
        cleaned,
        flags=re.IGNORECASE
    )

    cleaned = re.sub(
        r"```\s*",
        "",
        cleaned
    )

    cleaned = cleaned.strip()

    try:

        data = json.loads(cleaned)

        result = extract_tool(data)

        if result:
            return result

    except json.JSONDecodeError:
        pass

    # --------------------------------------------------------
    # 2. Search for JSON objects inside the response
    # --------------------------------------------------------

    decoder = json.JSONDecoder()

    for match in re.finditer(r"\{", text):

        start = match.start()

        try:

            data, end = decoder.raw_decode(
                text[start:]
            )

            result = extract_tool(data)

            if result:
                return result

        except json.JSONDecodeError:
            continue

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

        elif name == "git_commit":

            message = arguments.get("message")
            approved = arguments.get("approved", False)

            if not message:
                return (
                    "ERROR: git_commit requires "
                    "a commit message."
                )

            return git_commit(
                message,
                approved
            )

        else:

            return (
                f"ERROR: Unknown tool '{name}'. "
                "Available tools are: "
                "list_files, read_file, write_file, "
                "run_python, run_tests, "
                "git_status, git_diff, git_commit."
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


8. git_commit

Arguments:
{
    "message": "Describe the change",
    "approved": false
}

Purpose:
Create a Git commit for the current working tree.

IMPORTANT:
- A commit is blocked unless approved is exactly true.
- Never set approved to true unless the task explicitly
  provides approval to commit.
- The tool stages all current changes before committing.
- Do not commit unrelated changes.


============================================================
GENERAL RULES
============================================================

1. Work only inside the workspace when reading or
   modifying project files.

2. Git inspection is allowed through git_status
   and git_diff.

3. Git commits are allowed only through git_commit and
   only when explicit approval is provided.

4. Inspect existing files before modifying them.

5. Never assume a file exists.

6. Never invent test results.

7. Do not claim a program works unless you have
   actually executed or tested it.

8. When fixing code, inspect the relevant source first.

9. When tests fail, inspect the failure before fixing code.

10. After modifying code, run the relevant tests.

11. Do not claim success while required tests fail.

12. Do not push, deploy, or delete anything through Git.

13. Do not call git_commit unless the task explicitly
    authorizes a commit.

14. Never set git_commit approved=true without explicit
    approval from the task/user.

15. Follow the requested task sequence exactly.

16. If the task explicitly says not to modify files,
    do not modify files.

17. If the task explicitly says not to run tests,
    do not run tests.

18. Do not call tools that are prohibited by the task.


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

For git_commit:

{
    "name": "git_commit",
    "arguments": {
        "message": "Describe the change",
        "approved": false
    }
}

A Git commit requires explicit approval.

Never use "approved": true unless the task explicitly
authorizes the commit.

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
You are working on the existing calculator project.

Your goal is to improve the calculator by adding a new
"modulus" operation.

Follow this workflow:

============================================================
PHASE 1: PLAN
============================================================

Before using any tool, write a short plan containing:

1. What files you need to inspect.
2. What code needs to change.
3. What tests need to be created or updated.
4. How you will verify the change.

Do not modify anything during the planning phase.

============================================================
PHASE 2: INSPECT
============================================================

Inspect the relevant existing files before modifying them.

At minimum, inspect:

calculator.py
test_calculator.py

Do not assume their contents.

============================================================
PHASE 3: IMPLEMENT
============================================================

Add support for:

calculate(a, b, "modulus")

Expected behavior:

calculate(10, 3, "modulus") == 1

Also handle:

calculate(10, 0, "modulus")

Use a sensible error response for division/modulus by zero
that is consistent with the existing calculator behavior.

Do not remove or break the existing operations:

add
subtract
multiply
divide
invalid operation

============================================================
PHASE 4: TEST
============================================================

Update or create real pytest tests for the new behavior.

Run the tests using run_tests.

The existing tests must continue to pass.

============================================================
PHASE 5: FAILURE RECOVERY
============================================================

If tests fail:

1. Read the test failure.
2. Inspect the relevant source code.
3. Determine the cause.
4. Fix the code or tests.
5. Run the tests again.

Do not claim success while tests are failing.

You may repeat the fix/test cycle when necessary,
but do not make pointless repeated changes.

============================================================
PHASE 6: FINAL REVIEW
============================================================

After the tests pass:

1. Call git_status.
2. Call git_diff.
3. Give a short summary of:
   - files changed
   - functionality added
   - tests performed
   - test result

Do not commit anything.

============================================================
IMPORTANT RULES
============================================================

- Work only inside the controlled workspace.
- Inspect files before modifying them.
- Do not modify agent.py.
- Do not modify files unrelated to the calculator task.
- Do not invent test results.
- Do not call git_commit.
- Do not push.
- Do not deploy.
- Do not delete anything.
"""

# ============================================================
# RUN AGENT
# ============================================================

def main():

    previous_calls = []

    # --------------------------------------------------------
    # Controller state
    # --------------------------------------------------------

    written_files = set()

    tests_passed = False
    git_status_checked = False
    git_diff_checked = False

    # For the current task, both files must actually be modified.
    required_modified_files = {
        "calculator.py",
        "test_calculator.py"
    }

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
        print(f"AGENT STEP {step}")
        print("=" * 60)

        # ----------------------------------------------------
        # Ask model
        # ----------------------------------------------------

        try:

            response = chat(
                model=MODEL,
                messages=messages,
                options={"num_ctx": 8192, "temperature": 0}
            )

        except Exception as e:

            print()
            print("ERROR communicating with Ollama:")
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

        request = parse_tool_request(content)

        # ----------------------------------------------------
        # Model gave no tool request
        # ----------------------------------------------------

        if request is None:

            # Only allow completion after the controller
            # confirms every required milestone.

            if (
                required_modified_files.issubset(
                    written_files
                )
                and tests_passed
                and git_status_checked
                and git_diff_checked
            ):

                print()
                print("=" * 60)
                print("AGENT FINISHED")
                print("=" * 60)

                break

            # Model attempted to finish too early.

            missing = []

            if not required_modified_files.issubset(
                written_files
            ):
                missing.append(
                    "modify both calculator.py and test_calculator.py"
                )

            if not tests_passed:
                missing.append(
                    "run and pass pytest"
                )

            if not git_status_checked:
                missing.append(
                    "run git_status"
                )

            if not git_diff_checked:
                missing.append(
                    "run git_diff"
                )

            correction = (
                "You cannot finish yet. "
                "The controller requires these remaining steps:\n"
                + "\n".join(
                    f"- {item}"
                    for item in missing
                )
                + "\n\n"
                "Do not merely describe code in text. "
                "Use the actual tools."
            )

            print()
            print("CONTROLLER:")
            print(correction)

            messages.append(
                {
                    "role": "assistant",
                    "content": content
                }
            )

            messages.append(
                {
                    "role": "user",
                    "content": correction
                }
            )

            continue

        name = request["name"]
        arguments = request["arguments"]

        # ----------------------------------------------------
        # Never allow Git commit through autonomous loop
        # ----------------------------------------------------

        if name == "git_commit":

            tool_result = (
                "ERROR: git_commit is not allowed during "
                "this autonomous task. Do not commit."
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
                    "content": tool_result
                }
            )

            continue

        # ----------------------------------------------------
        # Controller rules
        # ----------------------------------------------------

        blocked = False
        tool_result = ""

        # ----------------------------------------------------
        # Block access outside workspace
        # ----------------------------------------------------

        if name == "read_file":

            path = arguments.get("path", "")

            if path == "agent.py" or path.startswith(
                "../"
            ):

                blocked = True

                tool_result = (
                    "ERROR: agent.py is outside the "
                    "controlled workspace. "
                    "Only files inside workspace/ may be "
                    "read or modified. "
                    "Use calculator.py or "
                    "test_calculator.py."
                )

        # ----------------------------------------------------
        # Do not test before actual modifications
        # ----------------------------------------------------

        if name == "run_tests":

            if not required_modified_files.issubset(
                written_files
            ):

                blocked = True

                missing_files = (
                    required_modified_files
                    - written_files
                )

                tool_result = (
                    "ERROR: Tests are blocked because the "
                    "required files have not actually been "
                    "modified yet.\n\n"
                    "You must use write_file for:\n"
                    + "\n".join(
                        f"- {path}"
                        for path in sorted(
                            missing_files
                        )
                    )
                    + "\n\n"
                    "Do not print code and claim that it was "
                    "written. Actually call write_file."
                )

        # ----------------------------------------------------
        # Do not inspect final Git state too early
        # ----------------------------------------------------

        if name == "git_status":

            if not required_modified_files.issubset(
                written_files
            ):

                blocked = True

                tool_result = (
                    "ERROR: git_status is premature. "
                    "First modify both calculator.py and "
                    "test_calculator.py, then run tests."
                )

            elif not tests_passed:

                blocked = True

                tool_result = (
                    "ERROR: git_status is premature. "
                    "First run pytest and make sure the "
                    "tests pass."
                )

            elif git_status_checked:

                blocked = True

                tool_result = (
                    "ERROR: git_status has already been "
                    "completed. Do not call it again."
                )

        # ----------------------------------------------------
        # git_diff only after git_status
        # ----------------------------------------------------

        if name == "git_diff":

            if not git_status_checked:

                blocked = True

                tool_result = (
                    "ERROR: git_diff is premature. "
                    "Run git_status first."
                )

            elif git_diff_checked:

                blocked = True

                tool_result = (
                    "ERROR: git_diff has already been "
                    "completed. Do not call it again."
                )

        # ----------------------------------------------------
        # Block repeated identical calls
        # ----------------------------------------------------

        signature = (
            name,
            json.dumps(
                arguments,
                sort_keys=True
            )
        )

        previous_calls.append(signature)

        repeated = (
            len(previous_calls) >= 3
            and
            previous_calls[-1]
            == previous_calls[-2]
            == previous_calls[-3]
        )

        if repeated:

            blocked = True

            tool_result = (
                "ERROR: You have repeated the same "
                "tool call three times without making "
                "progress. Choose the next required step."
            )

        # ----------------------------------------------------
        # Execute tool
        # ----------------------------------------------------

        if not blocked:

            print()
            print(
                f"Executing tool: {name}"
            )

            tool_result = execute_tool(
                name,
                arguments
            )

            # ------------------------------------------------
            # Track successful write_file calls
            # ------------------------------------------------

            if name == "write_file":

                path = arguments.get("path")

                if (
                    path in required_modified_files
                    and
                    tool_result.startswith(
                        "WRITE SUCCESS"
                    )
                ):

                    written_files.add(path)

            # ------------------------------------------------
            # Track successful tests
            # ------------------------------------------------

            if name == "run_tests":

                if tool_result.startswith(
                    "TEST RESULT: PASS"
                ):

                    tests_passed = True

                else:

                    tests_passed = False

            # ------------------------------------------------
            # Track Git status
            # ------------------------------------------------

            if name == "git_status":

                if tool_result.startswith(
                    "GIT STATUS"
                ):

                    git_status_checked = True

            # ------------------------------------------------
            # Track Git diff
            # ------------------------------------------------

            if name == "git_diff":

                if tool_result.startswith(
                    "GIT DIFF"
                ):

                    git_diff_checked = True

        else:

            print()
            print(
                f"BLOCKED: {tool_result}"
            )

        # ----------------------------------------------------
        # Print result
        # ----------------------------------------------------

        print()
        print("TOOL RESULT:")
        print(tool_result)

        # ----------------------------------------------------
        # Show controller state
        # ----------------------------------------------------

        print()
        print("CONTROLLER STATE:")
        print(
            f"Modified files: "
            f"{sorted(written_files)}"
        )
        print(
            f"Tests passed: "
            f"{tests_passed}"
        )
        print(
            f"Git status checked: "
            f"{git_status_checked}"
        )
        print(
            f"Git diff checked: "
            f"{git_diff_checked}"
        )

        # ----------------------------------------------------
        # Send tool result back to model
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
                    f"Tool '{name}' result:\n\n"
                    f"{tool_result}\n\n"
                    "Continue the task using the actual "
                    "tools. Do not claim that an action was "
                    "performed unless the tool result "
                    "confirms it."
                )
            }
        )

    else:

        print()
        print("=" * 60)
        print("AGENT STOPPED: MAX STEPS REACHED")
        print("=" * 60)


if __name__ == "__main__":
    main()
