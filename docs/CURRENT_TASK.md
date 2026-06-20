# Current Task

ConnectWise integration — COMPLETE.

Status:
- All seven steps from `docs/plans/connectwise_integration_plan.md` are implemented
  and verified on `feature/close-assistant-build`.
- Final verification:
  - `docker compose exec web python manage.py makemigrations --check --dry-run` — no changes.
  - `docker compose exec web python manage.py test -v 2` — **353 tests pass**.

Completed deliverables:
- Step 1: QBO customer/invoice and ConnectWise master/activity models.
- Step 2: QBO customer and invoice sync.
- Step 3: Synthetic ConnectWise feed generator with six scenarios.
- Step 4: ConnectWise-to-QBO reconciliation engine with three flag types.
- Step 5: `run_connectwise_reconciliation` management command.
- Step 6: Dashboard Client Reconciliation (ConnectWise) section with actions and metrics.
- Step 7: Documentation updated in `docs/TODO.md`, `docs/CHANGELOG.md`, and this file.

Next work:
- No further ConnectWise work in this plan. Pick the next TODO item or plan.
