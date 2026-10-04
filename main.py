import sys
from pathlib import Path
from workforce.tools import make_tools
from workforce.worker import run_worker

MODEL = sys.argv[1] if len(sys.argv) > 1 else "qwen2.5:7b"
WORKSPACE = Path(__file__).parent / "workspace"

CODER_SYSTEM = (
    "You are a coding agent. Call one tool at a time and wait for its result. "
    "Always read a file before changing it. Never delete existing tests; when "
    "behavior changes, update only the affected test. After writing code, call "
    "run_tests. Fix failures. When tests pass, reply with a one-line summary."
)

TASK = ("Add a 'modulus' operation to calculate() in calculator.py, handling "
        "modulus by zero like divide does. Add tests for it in test_calculator.py, "
        "including the zero case. Keep all existing tests passing.")

state = {}
tools = make_tools(WORKSPACE, state)
result = run_worker(model=MODEL, system=CODER_SYSTEM, task=TASK, tools=tools, state=state)
print("\nRESULT:", result)
