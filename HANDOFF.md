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

## Status 2026-10-14
- Autopilot v10 installed (67 tests pass in tests/). CRM suite: 55 tests pass (cd workspace_crm && python manage.py test).
- Model: qwen3:14b with "think": false in config.json.
- Built and approved cards: SaleItem.line_total, Sale.calculate_total, Product.in_stock, reduce_stock,
  confirm_sale (checks confirmed first, then stock, then lowers stock), Customer.total_spent,
  Sale.confirmed (field + migration), cancel_sale.
- Card kinds: model (new method), service (new function in services.py), field (new model field + migration,
  no model involved), and mode "change" with a "tag" (modify an existing function; skipped if its test file exists).
- Run cards: ./wfa auto --cards FILE --no-design   (commit the cards file first; the tree must be clean).
- Limits: each card has a 12-minute budget (config "card_minutes"); a failed card is rolled back.
- Known gaps: confirm_sale / cancel_sale are not wrapped in a database transaction; two items for the same
  product in one sale can pass the stock check separately. Rules written by a person work much better
  than rules proposed by the model.
- Next: let the model draft cards from one plain sentence, validated by Python, approved by the user.

## Status 2026-10-16
- Autopilot v13 installed (79 tests pass in tests/). CRM suite: 59 tests pass.
- New since the last status: ./wfa plan "one sentence" drafts cards (you keep/drop/edit each, then
  ./wfa auto --cards cards_plan.json --no-design). Cards built: Customer.notes, Customer.is_active
  (field cards with migrations) and create_sale (refuses inactive customers).
- Pipeline guards added: tests for inputs the rule never mentions are bounced; unused imports the model
  adds are removed; imports sent with a function are moved by Python; a locked test that crashes on its
  own line makes the attempt give up and rewrite the tests; 12-minute budget per card.
- Lesson: read every model-drafted card. Its plan put a rule in a method nothing called; a service
  function (create_sale) was the right place. Rules written by a person stay better than drafted ones.
- Known gaps: create_sale is not used by anything yet (no views/forms); no transactions around
  confirm_sale / cancel_sale; the model cannot create a whole new model/app yet.
- Next: views and forms for sales and customers, then the same for products.

## Status 2026-10-18
- View cards built by the agent: confirm_sale_view, cancel_sale_view, SaleCreateView.form_valid (v15/v16).
- Sale form no longer has an editable total (FIELDS = number, date, customer).
- card_minutes = 25 in config.json.
- CRM suite: 69 tests OK.
- Known gaps: no transactions around confirm/cancel; customer forms ignore notes/is_active; agent cannot create new modules yet.

## Shipped 2026-10-18 03:50 (auto/20261018-033514)
- Built: sales_func_record_payment, sales_sale_amount_paid, sales_func_payment
- Rules the agent rewrote itself: none
- Failed: none
- Test suite after merge: 76 tests OK

## Shipped 2026-10-18 09:01 (auto/20261018-082443)
- Built: sales_func_record_payment_view
- Rules the agent rewrote itself: none
- Failed: none
- Test suite after merge: 81 tests OK

## Shipped 2026-10-25 10:39 (auto/20261025-100919)
- Built: sales_sale_balance_due, sales_func_confirm_sale_refresh_total
- Rules the agent rewrote itself: none
- Failed: none
- Test suite after merge: 90 tests OK

## Shipped 2026-10-29 14:40 (auto/20261029-115222)
- Built: products_func_low_stock_products
- Rules the agent rewrote itself: none
- Failed: none
- Test suite after merge: 110 tests OK
