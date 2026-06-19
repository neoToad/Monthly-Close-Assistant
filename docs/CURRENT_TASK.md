# Current Task

## Completed: Refactor plan steps 1–5

All five planned refactor increments have been implemented on branch
`feature/close-assistant-build`. The full core test suite passes **276 tests**.

### Step 1 — Audit
- Delivered `docs/plans/refactor_plan.md` with the full Step 1 audit and Step 2
  execution plan.

### Step 2 — Dead code cleanup (2.7.A–F)
- Removed unused `refresh_tokens` and its tests.
- Removed unused `_lookup_suggestion` in `core/quickbooks/writes.py`.
- Removed the no-op `--skip-reports` argument.
- Removed unused imports and clarified the `--force` block in
  `seed_bank_balances`.

### Step 3 — Centralize dates and constants (2.2.C)
- Added `core/common/dates.py` with `month_bounds`, `prior_month`, and
  `month_bounds_for_query`.
- Added `core/common/constants.py` with `CASH_LIKE_ACCOUNT_TYPES`,
  `AMOUNT_TOLERANCE`, `DATE_TOLERANCE_DAYS`, `BALANCE_TOLERANCE`, anomaly
  thresholds, and default agent accounts.
- Updated `core/views.py`, `core/reconciliation/engine.py`,
  `core/agent/reconcile.py`, `core/agent/summary.py`, `core/anomaly/rules.py`,
  `core/bank_feed.py`, `core/quickbooks/client.py`, and
  `core/management/commands/seed_bank_balances.py` to import shared helpers.

### Step 4 — Type hints and docstrings pass (2.4)
- Added return types and parameter docstrings across touched modules.
- Tightened `create_journal_entry` type hints in `core/quickbooks/writes.py`.
- Improved docstrings in `core/agent/reconcile.py` and
  `core/reconciliation/engine.py`.

### Step 5 — Extract `compute_posted_total` and grouped queries (2.1.B, 2.8.A)
- Added `compute_posted_total(month, account_name, realm_id=None)` in
  `core/reconciliation/engine.py`.
- Updated `_bank_balances_context`, `check_account_balances`, and
  `gather_account_inputs` to use the shared helper.
- Replaced manual sums and per-row `bank_transactions.count()` calls with
  `Sum` aggregates and `Count("bank_transactions")` annotations.
- Added `ComputePostedTotalTests` in `core/tests/test_reconciliation.py` and
  fixed the `_make_txn` helper to generate unique `qb_transaction_id` values.

### Step 6 — Extract service layer for apply flow (2.1.A)
- Added `core/services/__init__.py` and `core/services/reconciliation.py`.
- Implemented `apply_account_reconciliation_suggestions(...)` to centralize
  dry-run preview, QB client building, suggestion application, post-apply sync,
  reconciliation rerun, state update, and flag audit notes.
- Refactored `core/views.py:reconcile_account_apply` to a thin wrapper that
  validates parameters and renders the appropriate partial.
- Refactored `core/management/commands/apply_account_fix.py` to call the same
  service and translate results to CLI output / `CommandError`.
- Added `core/tests/test_services.py` with direct service-layer coverage.
- Updated existing view/command tests to patch dependencies inside the service
  module.

## Next: Step 6 — Move QB write helpers to `core/services/qb_writes.py`

The recommended next increment is Step 6 from the refactor plan: move
`apply_suggestion` and the `create_*` helpers out of `core/quickbooks/writes.py`
into `core/services/qb_writes.py` so the agent layer (`core.agent.*`) cannot
import QuickBooks write logic. This enforces the read-only agent boundary
identified in the Step 1 audit.
