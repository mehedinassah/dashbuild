import sys
from pathlib import Path
from workforce.manager import run_task

DEFAULT_TASK = ("Add a 'modulus' operation to calculate() in calculator.py, handling "
                "modulus by zero like divide does. Add tests for it in "
                "test_calculator.py, including the zero case. Keep all existing "
                "tests passing.")

task = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TASK
model = sys.argv[2] if len(sys.argv) > 2 else "qwen2.5:7b"
ws = sys.argv[3] if len(sys.argv) > 3 else "workspace"
run_task(model, Path(__file__).parent / ws, task)
