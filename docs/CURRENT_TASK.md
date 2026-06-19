# CURRENT_TASK

## Stage

`docs/plans/add_quickbooks_data_sources_plan.md` is complete and committed.

## Current task

All six steps of the QuickBooks data-source expansion are implemented:

1. ✅ Extended `SourceType` and added `QBAccount` model + migration.
2. ✅ Sync Bills, BillPayments, VendorCredits, and Accounts.
3. ✅ Added test coverage for normalization, account sync, and realm isolation.
4. ✅ Scoped bank feed to cash-like transaction types with `--cash-only`.
5. ✅ Added GeneralLedger report cross-check in close summary.
6. ✅ Updated project documentation.

Full test suite: **211 tests pass** inside Docker.

## Branch

`feature/close-assistant-build`

## Next step

Await further instructions.
