# CURRENT_TASK

## Stage

Implementing `docs/plans/add_quickbooks_data_sources_plan.md`.

## Current step

**Step 3 — Test coverage for normalization and account sync**
- Add focused normalization test classes for `Bill`, `BillPayment`, `VendorCredit`.
- Add `SyncAccountsTests` verifying upsert by `(realm_id, account_id)`.
- Add `test_sync_command_prints_new_source_counts`.
- Add realm-isolation tests for `QBAccount`.
- Add `QBAccount` model tests.

## Branch

`feature/close-assistant-build`

## Next step

Commit `test(qb): cover new QuickBooks normalization and account sync`, then begin Step 4.
