# Handoff (written 2026-10-06 morning)

## Goal
Free, local, customizable AI workforce (Ollama, open-weight models) that builds
CRM / ERP / POS software. No cloud, no cost. User wants to run and change it
without help from any outside AI.

## Machine
Ubuntu on WSL2, Ryzen 7 6800H, RTX 3060 6 GB (about 1.2 GB used by Windows),
WSL sees 9.7 GB RAM. Python 3.14, Ollama 0.35.0, Django 6.1.1.
Model in use: qwen2.5:7b (set in config.json). qwen2.5-coder:7b was a poor agent.
qwen3:8b and gemma4:e4b were never successfully pulled or tested.
Always: cd ~/ai-workforce && source .venv/bin/activate. Run python with -u.

## What exists (all in git)
- workforce/tools.py    tools + guards (deleted tests, shrinking files, invalid or duplicate
                        python, missing template parents, undefined names, allow-listed commands)
- workforce/worker.py   one tool call at a time, reply cap, repeat guard
- workforce/review.py   automated test-weakening check (blocks) + LLM reviewer (advisory only,
                        it approved bad work 5 times)
- workforce/manager.py  3 attempts, clean reset, tests-must-run check, human [y/N] before commit
- workforce/planner.py  weak; hand-written plan.json works better
- workforce/generator.py + ui.py   NO-AI CRUD generator and shared layout/dashboard
- workforce/config.py, config.json, prompts/coder.txt, prompts/reviewer.txt  editable settings
- wf launcher: ./wf run [N] | task | test | reset | status | serve | models | make crud/refresh
- tests/ (guards + generator), README.md (handbook)
- workspace/ calculator practice project (done)
- workspace_crm/ Django project: customers (agent-built list+search, hand-wired URLs),
  products (generated CRUD), core (shared layout + dashboard at /, if the last step succeeded)

## Last step (UNVERIFIED when this note was written)
Added ui.py, ensure_core, refresh command, dashboard at /, restyled products,
customers/apps.py (crud_module + list_url) and a new customers template.
Check: ./wf test should show 17 passed; workspace_crm tests should be OK;
./wf serve then open http://localhost:8000/ (dashboard), /products/, /customers/, /admin/.

## Known issues
- Products allows duplicate SKUs (no unique support yet).
- /customers/ only lists and searches; add/delete is through /admin/.
- 7B model: forgets imports, drops half of multi-file tasks, cannot edit long framework
  files; so wiring (settings.py, config/urls.py) is done by hand or by the generator.

## Next steps
1. Verify the last step (above). Fix anything broken.
2. unique fields in generator (sku:str:unique).
3. Foreign keys in generator (customer:fk:Customer) for Invoice / InvoiceItem.
4. First business logic through the agents in small one-file tasks
   (invoice totals, stock reduction on sale, low-stock report).
5. Planner: one file per task, file-coverage check, human-only wiring tasks.
6. Specialist workers (security, devops), shared project notes file.
7. Test qwen3:8b; consider .wslconfig RAM increase (ask: total laptop RAM?).

## Backup command (flag order matters: --exclude before the folder)
cd ~ && tar czf ai-workforce-backup-$(date +%F).tar.gz --exclude=.venv --exclude=__pycache__ --exclude=db.sqlite3 ai-workforce
