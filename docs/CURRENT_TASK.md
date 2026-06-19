# Current Task

## Refactor Steps 6–8 complete

All three planned refactor increments have been implemented and verified. The full core
suite now passes **290 tests**.

### Step 6 — Move QB write helpers to `core/services/qb_writes.py`
- Created `core/services/qb_writes.py` and migrated all QB adjusting-entry helpers.
- Removed the obsolete `core/quickbooks/writes.py` module.
- Enforced the read-only agent boundary: `core.agent` modules no longer import QB client
  or QB write logic.
- Added `core/tests/test_architecture.py` to guard the boundary.

### Step 7 — Centralize retry/backoff
- Created `core/services/retry.py` with a generic `with_retry` helper.
- Wrapped QB write `.save()` calls and LLM `.invoke()` calls with retry/backoff.
- Added `core/tests/test_retry.py`.

### Step 8 — Add missing idempotency tests
- Added idempotency coverage for reconciliation dry-run/apply, `set_bank_balance`,
  `seed_bank_balances`, `generate_bank_feed --force --seed`, and the set-balance view.
- Implemented `applied_suggestions` deduplication in
  `apply_account_reconciliation_suggestions` so repeated applies skip already-applied
  suggestions.

### Next
None remaining for Steps 6–8. The next planned increments from `docs/plans/refactor_plan.md`
would be package reorganization (2.2.A full target) and migration squash (2.8.E), which are
explicitly recommended to wait until all prior refactor work is green.
