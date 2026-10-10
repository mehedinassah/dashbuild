"""Same four cards, in a throwaway project, for each model. Tells you which model to use."""
import tempfile

from . import pipeline, scorecard
from .fixture import BENCH_CARDS, make_project


def bench_model(model, log=print):
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        ws = make_project(tmp)
        for card in BENCH_CARDS:
            res = pipeline.run_card(ws, card, model, log=log)
            res["id"] = "bench_" + res["id"]
            scorecard.record(res)
            results.append(res)
            if res["status"] == "passed":
                pipeline.subprocess.run(["git", "add", "-A"], cwd=ws, capture_output=True)
                pipeline.subprocess.run(["git", "-c", "user.name=b", "-c", "user.email=b@b",
                                         "commit", "-qm", res["id"]], cwd=ws, capture_output=True)
    return results


def run(models):
    table = []
    for m in models:
        print(f"\n=== benchmarking {m} ===")
        rs = bench_model(m)
        table.append((m, sum(r["status"] == "passed" for r in rs), len(rs),
                      sum(r["seconds"] for r in rs)))
    print("\nmodel                     passed   total seconds")
    for m, ok, n, secs in table:
        print(f"{m:25} {ok}/{n}      {secs}")
    return 0
