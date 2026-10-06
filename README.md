# Local AI Workforce

A small team of AI agents that runs fully on this laptop through Ollama.
No cloud, no API keys, no cost. Open-weight models only.

## How it works

The model proposes, Python decides. The model can only act through tools,
and every tool call passes checks written in plain Python.

    plan.json -> run_saved.py -> manager.run_task -> worker (coder) -> checks
                                      |                                  |
                                 you approve  <-- diff + reviewer note <-+
                                      |
                                 git commit

## Files

- workforce/tools.py    the tools and all the safety checks (most important file)
- workforce/worker.py   the loop: one tool call at a time, repeat guard, reply cap
- workforce/review.py   automated test-weakening check (blocks) + LLM reviewer (advisory only)
- workforce/manager.py  attempts, clean reset between retries, approval prompt, commit
- workforce/planner.py  the model proposes a task list (weak; hand-written plans are better)
- run_saved.py [N]      runs plan.json, optionally starting at task N
- manager_main.py       runs one task: python -u manager_main.py "task" MODEL FOLDER
- agent.py              the old single-file agent, kept only for reference
- workspace/            calculator practice project
- workspace_crm/        Django project; .workforce.json holds its test command,
                        allowed commands and project rules for the coder

## Daily use

    cd ~/ai-workforce && source .venv/bin/activate
    # edit plan.json (one small task per file works best), then:
    python -u run_saved.py          # or: python -u run_saved.py 3  to resume at task 3

At each [y/N] prompt READ THE DIFF. The reviewer note is only a hint: the small
model has approved broken work several times. Answer n to keep the changes in
the folder, then fix by hand.

## Rules that work with a 7B model

- One task = one small change in one file. Tests for it in the next task.
- Project wiring (settings.py, config/urls.py) is done by hand.
- Always check the diff against the task wording.
- Check that new tests can fail (temporarily break the code and watch them fail).

## Reset an unfinished task

    git reset -q -- workspace_crm && git checkout -- workspace_crm && git clean -fd -- workspace_crm

## Troubleshooting

- "Workspace has uncommitted changes": commit or run the reset line above.
- Looks stuck: press Ctrl+C. Check "ollama ps" in another terminal. A step over
  3 minutes is a problem; the reply cap is num_predict in workforce/worker.py.
- Ollama errors: "ollama list" and "ollama ps"; log: journalctl -u ollama -n 50
- Change the model: edit the model name in run_saved.py (or pass it to manager_main.py).
  Any model with "tools" capability in "ollama show NAME" can be tried.
- Run the unit tests after any code change: python -m pytest tests -q

## Known limits

- The model forgets imports, duplicates code, drops half of a multi-file task,
  and cannot reliably edit long framework files.
- Its reviewer opinion cannot be trusted. Only the Python checks block.
- Output quality depends on the model. Better free models arrive over time;
  switching is a one-word change.

## Generator (no AI)

    ./wf make crud Product name:str sku:str price:decimal stock:int

Creates a full Django module (model, admin, views, URLs, templates, tests), wires it
into settings and urls, runs makemigrations/check/tests, and rolls back on failure.
Field types: str, text, int, decimal, bool, date, email. First field must be str.
Then run: cd workspace_crm && python manage.py migrate
Generator code: workforce/generator.py (templates are the strings in that file).
