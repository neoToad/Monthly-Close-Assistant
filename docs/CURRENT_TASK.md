# CURRENT_TASK

## Stage

Implementing `docs/plans/add_quickbooks_data_sources_plan.md`.

## Current step

**Step 2 — Sync the new transaction types**
- Import `Bill`, `BillPayment`, `VendorCredit` and extend `SYNC_OBJECTS`.
- Extend `normalize_record()` for the three AP types.
- Add `sync_accounts()` helper and wire it into `sync_quickbooks`.
- Print per-type counts for the new transaction sources.
- Write failing tests first, then implement.

## Branch

`feature/close-assistant-build`

## Next step

Commit `feat(qb): sync Bills, BillPayments, VendorCredits, and Accounts`, then begin Step 3.
