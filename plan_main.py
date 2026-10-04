import sys
from pathlib import Path
from workforce.planner import run_plan

goal = sys.argv[1]
ws = sys.argv[2] if len(sys.argv) > 2 else "workspace_crm"
model = sys.argv[3] if len(sys.argv) > 3 else "qwen2.5:7b"
run_plan(model, Path(__file__).parent / ws, goal)
