# dashbuild

**A local AI coding agent that builds a Django app one small, tested change at a time.
The model proposes. Python decides.**

dashbuild runs on your own machine with an open-weight model through [Ollama](https://ollama.com). No cloud, no API
costs. You describe a change as a short rule (a "card"). The model writes tests first, then the code. Plain Python
checks the work and a human approves every change before it is committed.

It was built to find out how far a small local model (14B parameters, 6 GB graphics card) can be trusted to write
real business software when it is surrounded by strict, deterministic checks. The demo project is a small CRM that the
agent built, card by card.

## How a change is made

```
 a card (one rule)  ->  baseline: the whole test suite is green
        |
        v
 model writes TESTS first  ->  static checks (no mocks, real imports, no invented behaviour)
        |                      tests must fail, and for the RIGHT reason (the feature is missing)
        v
 tests are LOCKED (SHA-256)  ->  model writes the CODE; it cannot touch the tests
        |
        v
 gates (Python, no model):  tests unchanged | full suite green | test count exact |
                            mutation score >= 70% (the tests must catch deliberately broken code)
        |
        v
 you read the diff and type y or n  ->  commit on a branch  ->  ./wfa ship merges it
```

If a card fails, everything is rolled back and the failed tests are kept for inspection. After repeated failures the
model rewrites the card's rule (never the tests) and tries again, up to twice.

## Card kinds

| Kind | What it does | Who does the work |
|---|---|---|
| `model` / `service` | One new method or function with its business rule | model, test-first |
| `change` | Modify an existing function, old tests must keep passing | model, test-first |
| `field` | Add a field and its migration | Python only |
| `class` | Create a whole new model, migration and admin entry | Python only |
| `view` | A screen action: route, button, input box, list column, messages | model writes view and tests, Python wires the pages |
| `tile` | Put a metric on the dashboard (number, list or bar chart) | Python only |

```json
{"app": "sales", "kind": "service", "class": "", "name": "record_payment",
 "spec": "record_payment(sale, amount) creates and returns a Payment for that sale. If sale.confirmed is False raise ValueError('Sale is not confirmed'). If amount is not greater than zero raise ValueError('Amount must be positive'). In both cases create no Payment."}
```

## Commands

```
./wfa plan "one sentence"                  # the model drafts cards, you keep / drop / edit each
./wfa auto --cards cards.json --no-design  # build the cards, approve each diff
./wfa ship                                 # merge, run the tests, write the handoff, back up
./wfa score                                # what each model has managed so far
./wfa map                                  # the project map the agent sees
```

## What it has built

The agent built most of the demo CRM in `workspace_crm/`: line totals and sale totals, stock checks and reduction,
confirm and cancel with rollback rules, customer rules, payments with a balance, the confirm / cancel / pay buttons
with messages, a create-sale form and dashboard metrics. N tests, all written by the agent under the checks above.

## Results so far

From `./wfa score`, covering all development runs (including early versions of the pipeline):

| Model | Cards tried | Passed | Passed first try | Avg time per card |
|---|---|---|---|---|
| qwen3:14b | 48 | 31 (65%) | 23 (48%) | 12 min |
| qwen2.5:7b | 20 | 8 (40%) | 2 (10%) | 4 min |
| Python-only cards (field, class) | 4 | 4 (100%) | 4 | 2 s |

Model size matters a lot, and moving mechanical work (fields, models, page wiring) out of the model and into Python
made those steps reliable.

## What went wrong, and what it taught the pipeline

- **A fake mock.** The model "mocked" a service by reassigning a local variable, which does nothing. Now any test
  that mentions mocking or patching is rejected.
- **The wrong exception.** `Decimal('abc')` raises `InvalidOperation`, not `ValueError`. The model repeated the same
  broken view five times, and the test runner only reported "failed". Now the real exception is shown to the model,
  and the instructions state the fact.
- **A test that contradicted its own rule.** It posted a total of 100.00 and asserted 100.00, while the service always
  sets 0.00. Now five identical failures end the attempt and blame the tests, and a repair step rewrites the rule.

## Limits (honest list)

- It is supervised: you approve every change. That is a design choice, not a missing feature.
- A 14B model is weak at writing tests. Some steps are done by fixed templates in Python because of that.
- The CRM is basic. There is no POS or ERP yet, no user roles, and confirm / cancel are not wrapped in transactions.
- It targets Django projects only.

## Requirements

Python 3.14, [Ollama](https://ollama.com) with `ollama pull qwen3:14b`, and a virtual environment with `django` and
`ollama`. The agent's settings are in `config.json` (model, attempts, minutes per card, backup folder).

## Layout

```
workforce/     the engine (pipeline, rules, gates, mutation testing, wiring, ship, score)
prompts/       the instructions given to the model
tests/         tests for the engine itself
workspace_crm/ the demo Django project built by the agent
cards_*.json   example card files
```

## Credits and license

Built and designed by Mehedi Hassan. MIT license, see `LICENSE`.
