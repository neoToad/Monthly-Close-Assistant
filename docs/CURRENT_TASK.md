# CURRENT_TASK

## Stage

Implementing `docs/plans/add_quickbooks_data_sources_plan.md`.

## Current step

**Step 1 — Extend the schema**
- Add `Bill`, `BillPayment`, `VendorCredit` to `core.models.SourceType`.
- Add `QBAccount` chart-of-accounts model and migration `0004_qbaccount.py`.
- Write failing model tests first, then make them pass.

## Branch

`feature/close-assistant-build`

## Next step

Commit `feat(models): add QBAccount model and extend SourceType choices`, then begin Step 2.