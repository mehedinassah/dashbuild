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
WORKSPACE = Path("workspace").resolve()
MAX_STEPS = 20


# ============================================================
# AGENT STATE
# ============================================================

last_test_file = None
previous_calls = []


# ============================================================
# SAFE PATH
# ============================================================

def safe_path(path):
    if not path:
        raise ValueError("Path cannot be empty.")

    target = (WORKSPACE / path).resolve()

    try:
        target.relative_to(WORKSPACE)
    except ValueError:
        raise ValueError("Access denied: path is outside the workspace.")

    return target


# ============================================================
# LIST FILES
# ============================================================

def list_files():
    files = []

    for path in WORKSPACE.rglob("*"):
        if path.is_file():
            files.append(
                str(path.relative_to(WORKSPACE))
            )

    return files


# ============================================================
# READ FILE
# ============================================================

def read_file(path):
    target = safe_path(path)

    if not target.exists():
        return f"File not found: {path}"

    if not target.is_file():
        return f"Not a file: {path}"

    try:
        return target.read_text(encoding="utf-8")

    except Exception as e:
        return f"ERROR reading file: {e}"


# ============================================================
# WRITE FILE
# ============================================================

def write_file(path, content):
    target = safe_path(path)

    try:
        target.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        target.write_text(
            content,
            encoding="utf-8"
        )

        return f"Successfully wrote {path}"

    except Exception as e:
        return f"ERROR writing file: {e}"


# ============================================================
# RUN PYTHON
# ============================================================

def run_python(path):
    target = safe_path(path)

    if not target.exists():
        return f"File not found: {path}"

    if not target.is_file():
        return f"Not a file: {path}"

    if target.suffix != ".py":
        return (
            "ERROR: run_python only supports Python "
            "files ending in .py."
        )

    if target.name.startswith("test_"):
        return (
            "ERROR: This is a pytest test file. "
            "Do NOT use run_python. "
            "Use run_tests instead."
        )

    try:
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

        output = ""

        if result.stdout:
            output += result.stdout

        if result.stderr:
            output += (
                "\nSTDERR:\n"
                + result.stderr
            )

        return (
            f"EXIT CODE: {result.returncode}\n"
            f"{output}"
        )

    except subprocess.TimeoutExpired:
        return (
            "ERROR: Python execution timed out "
            "after 10 seconds."
        )

    except Exception as e:
        return f"ERROR running Python: {e}"


# ============================================================
# RUN TESTS
# ============================================================

def run_tests(path=None):
    global last_test_file

    # --------------------------------------------------------
    # Automatically determine test file
    # --------------------------------------------------------

    if not path:

        if last_test_file:
            path = last_test_file

        else:

            test_files = [
                p for p in WORKSPACE.glob("test_*.py")
                if p.is_file()
            ]

            if len(test_files) == 1:
                path = str(
                    test_files[0].relative_to(WORKSPACE)
                )

            elif len(test_files) > 1:
                return (
                    "ERROR: Multiple test files found. "
                    "Specify which test file to run."
                )

            else:
                return (
                    "TEST RESULT: FAIL\n"
                    "REASON: No pytest test file was found."
                )

    last_test_file = path

    target = safe_path(path)

    if not target.exists():
        return (
            "TEST RESULT: FAIL\n"
            f"REASON: Test file not found: {path}"
        )

    if not target.is_file():
        return (
            "TEST RESULT: FAIL\n"
            f"REASON: Not a file: {path}"
        )

    if target.suffix != ".py":
        return (
            "TEST RESULT: FAIL\n"
            "REASON: Test file must be a .py file."
        )

    try:

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                str(target),
                "-v"
            ],
            cwd=WORKSPACE,
            capture_output=True,
            text=True,
            timeout=20
        )

        output = result.stdout

        if result.stderr:
            output += (
                "\nSTDERR:\n"
                + result.stderr
            )

        # ----------------------------------------------------
        # No tests
        # ----------------------------------------------------

        if "no tests ran" in output.lower():

            return (
                "TEST RESULT: FAIL\n"
                "REASON: Pytest discovered no tests.\n"
                "The test file must contain real functions "
                "whose names start with test_.\n\n"
                + output
                + f"\nEXIT CODE: {result.returncode}"
            )

        # ----------------------------------------------------
        # Collection error
        # ----------------------------------------------------

        if "ERROR collecting" in output:

            return (
                "TEST RESULT: FAIL\n"
                "REASON: Pytest encountered a collection "
                "error.\n\n"
                + output
                + f"\nEXIT CODE: {result.returncode}"
            )

        # ----------------------------------------------------
        # PASS
        # ----------------------------------------------------

        if result.returncode == 0:

            return (
                "TEST RESULT: PASS\n\n"
                + output
            )

        # ----------------------------------------------------
        # FAIL
        # ----------------------------------------------------

        return (
            "TEST RESULT: FAIL\n\n"
            + output
            + f"\nEXIT CODE: {result.returncode}"
        )

    except subprocess.TimeoutExpired:

        return (
            "TEST RESULT: FAIL\n"
            "REASON: Tests timed out after 20 seconds."
        )

    except Exception as e:

        return (
            "TEST RESULT: FAIL\n"
            f"REASON: Error running pytest: {e}"
        )


# ============================================================
# PARSE TOOL REQUEST
# ============================================================

def parse_tool_request(text):

    text = text.strip()

    # Remove markdown fences

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

    try:
        data = json.loads(text)

    except json.JSONDecodeError:
        return None

    # Normal format

    if (
        isinstance(data, dict)
        and "name" in data
    ):

        return {
            "name": data["name"],
            "arguments": data.get(
                "arguments",
                {}
            )
        }

    # Direct write_file format

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

    if arguments is None:
        arguments = {}

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

        else:

            return (
                f"ERROR: Unknown tool '{name}'. "
                "Available tools are: "
                "list_files, read_file, write_file, "
                "run_python, run_tests."
            )

    except Exception as e:

        return (
            f"ERROR executing {name}: {e}"
        )


# ============================================================
# SYSTEM PROMPT
# ============================================================

tools_description = """
You are an AI software development agent working inside
a controlled workspace.

Your job is to inspect files, write code, run programs,
create tests, diagnose failures, and fix problems.

============================================================
AVAILABLE TOOLS
============================================================

1. list_files

Arguments:
{}

Purpose:
List files in the workspace.


2. read_file

Arguments:
{
    "path": "filename"
}

Purpose:
Read a file.


3. write_file

Arguments:
{
    "path": "filename",
    "content": "file contents"
}

Purpose:
Create or replace a file.


4. run_python

Arguments:
{
    "path": "filename.py"
}

Purpose:
Run a normal Python program.

Never use this on pytest test files.


5. run_tests

Arguments:
{
    "path": "test_filename.py"
}

Purpose:
Run pytest.

If you omit the arguments object or path,
the system will automatically use the existing
test file when possible.

However, when possible, ALWAYS provide the path.

============================================================
GENERAL RULES
============================================================

1. Work only inside the workspace.

2. Inspect existing files before modifying them.

3. Understand the existing implementation before
   changing it.

4. Do not assume code is correct just because it
   executes without a Python error.

5. Use tests to verify behavior.

6. When tests fail, inspect the failure carefully.

7. Read the relevant source file before fixing it.

8. Use write_file to make fixes.

9. Run the tests again after making a fix.

10. Do not claim success while required tests fail.

============================================================
PYTEST RULES
============================================================

When creating pytest tests:

ALWAYS create real pytest test functions.

Every test must have a name beginning with:

test_

Correct:

from calculator import calculate


def test_add():
    assert calculate(10, 5, "add") == 15


def test_subtract():
    assert calculate(10, 5, "subtract") == 5


Incorrect:

import calculator

assert calculator.calculate(10, 5, "add") == 15

Never use module-level assertions as the only tests.

============================================================
TEST WORKFLOW
============================================================

When working on a bug:

1. Inspect the source.
2. Create or inspect tests.
3. Run run_tests.
4. If tests fail:
   - read the failure
   - inspect the source
   - identify the cause
   - fix the source
   - run run_tests again
5. Continue until tests pass.

If pytest says:

no tests ran

that is a FAILURE.

If pytest says:

ERROR collecting

that is a FAILURE.

If pytest says:

FAILED

that is a FAILURE.

Only a successful pytest result is considered PASS.

For example:

6 passed

means the tests passed.

============================================================
IMPORTANT TOOL RULE
============================================================

NEVER use run_python on a file beginning with:

test_

Use run_tests instead.

run_python is for executing normal programs.

run_tests is for pytest.

============================================================
TOOL CALL FORMAT
============================================================

When using a tool, return ONLY JSON.

Correct:

{
    "name": "read_file",
    "arguments": {
        "path": "calculator.py"
    }
}

For list_files:

{
    "name": "list_files",
    "arguments": {}
}

For run_tests:

{
    "name": "run_tests",
    "arguments": {
        "path": "test_calculator.py"
    }
}

Do not wrap JSON in Markdown fences.

Do not explain the tool call.

============================================================
LOOP PREVENTION
============================================================

Do not blindly repeat the same action.

If a tool returns an error:

1. Understand the error.
2. Change your approach.
3. Use the appropriate tool.

If run_tests fails:

Do NOT repeatedly call run_tests without changing
or inspecting something.

If the test file is wrong:

Use read_file and then write_file.

If the source is wrong:

Use read_file and then write_file.

Do not repeatedly use run_python to execute tests.

============================================================
FINISHING RULE
============================================================

Do not finish just because the source code looks correct.

Finish only after the required tests have actually
passed.
"""


# ============================================================
# TASK
# ============================================================

task = """
Fix the existing calculator project.

The calculator must support:

calculate(10, 5, "add") == 15

calculate(10, 5, "subtract") == 5

calculate(10, 5, "multiply") == 50

calculate(10, 5, "divide") == 2

calculate(10, 0, "divide") == "Error: Division by zero"

calculate(10, 5, "modulus") == "Error: Invalid operation"


Your task:

1. Inspect the workspace.

2. Inspect calculator.py.

3. Create a proper pytest test file named:

test_calculator.py

4. Every test must be a real pytest test function.

5. Run the tests with run_tests.

6. If tests fail, inspect the failure.

7. Fix the source code if necessary.

8. Run the tests again.

9. Continue until all required tests pass.

10. Do not use run_python on the test file.

11. Do not finish until pytest reports that
all required tests pass.
"""


# ============================================================
# MESSAGES
# ============================================================

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


# ============================================================
# AGENT LOOP
# ============================================================

for step in range(1, MAX_STEPS + 1):

    print()
    print("=" * 60)
    print(f"AGENT STEP {step}")
    print("=" * 60)

    try:

        response = chat(
            model=MODEL,
            messages=messages
        )

    except Exception as e:

        print()
        print("ERROR communicating with Ollama:")
        print(e)
        break

    content = response.message.content.strip()

    print()
    print("AI:")
    print(content)

    request = parse_tool_request(content)

    # --------------------------------------------------------
    # AI finished
    # --------------------------------------------------------

    if request is None:

        print()
        print("=" * 60)
        print("AGENT FINISHED")
        print("=" * 60)

        break

    name = request["name"]
    arguments = request["arguments"]

    # --------------------------------------------------------
    # Track repeated calls
    # --------------------------------------------------------

    signature = (
        name,
        json.dumps(
            arguments,
            sort_keys=True
        )
    )

    # Only warn about repeated calls if they are genuinely
    # repeated several times in a row.
    #
    # A tool can legitimately be called again after the
    # underlying file has changed.

    previous_calls.append(signature)

    if len(previous_calls) >= 3:

        if (
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
                "progress. Stop repeating it. "
                "Inspect the previous result and take "
                "a different action."
            )

        else:

            print()
            print(f"Executing tool: {name}")

            tool_result = execute_tool(
                name,
                arguments
            )

    else:

        print()
        print(f"Executing tool: {name}")

        tool_result = execute_tool(
            name,
            arguments
        )

    print()
    print("TOOL RESULT:")
    print(tool_result)

    # --------------------------------------------------------
    # Add conversation history
    # --------------------------------------------------------

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
    print("=" * 60)
    print("AGENT STOPPED")
    print("=" * 60)

    print(
        "Agent stopped because it reached "
        f"the maximum number of steps ({MAX_STEPS})."
    )
