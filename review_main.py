import sys
from pathlib import Path
from workforce.review import review

MODEL = sys.argv[1] if len(sys.argv) > 1 else "qwen2.5:7b"
WORKSPACE = Path(__file__).parent / "workspace"
TASK = ("Add a 'modulus' operation to calculate() in calculator.py, handling "
        "modulus by zero like divide does. Add tests for it in test_calculator.py, "
        "including the zero case. Keep all existing tests passing.")

result = review(MODEL, WORKSPACE, TASK, auto_reject=(len(sys.argv) < 3 or sys.argv[2] != "llm"))
print("\nVERDICT:", result["verdict"])
