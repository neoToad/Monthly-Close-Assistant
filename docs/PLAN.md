# Implementation Plan: Multi-Company QuickBooks Support

**Status:** Implemented. See `docs/CHANGELOG.md` for the completed entry and
`docs/CURRENT_TASK.md` for the current state.

## Goal
Scope all data and dashboard actions by QuickBooks realm (company), allowing multiple sandbox companies to be connected and reviewed independently.

## Approach
Followed the plan in `docs/plans/multi_company_qb_plan.md` with these concrete decisions:

1. **Company name source:** Fetch from the QuickBooks Online `CompanyInfo` endpoint. `QuickBooksCompany.name` is populated automatically during OAuth and refreshed on every `sync_quickbooks` run. Manually edited names are preserved when the API returns blank.
2. **Default company behavior:** When no `company` query parameter is provided, default to the most recently connected realm (`QBToken.objects.order_by("-updated_at").first()`).
3. **CloseSummary uniqueness:** Changed from unique `(month)` to unique together `(realm_id, month)`.
4. **Transaction uniqueness:** Changed from unique `qb_transaction_id` to unique together `(realm_id, qb_transaction_id)` so transaction IDs from different companies do not collide.
5. **Flag realm scoping:** Added a denormalized `realm_id` column to `Flag` for fast filtering, populated automatically from the linked transaction or bank transaction.

## Step-by-Step Plan

### Step 1 — Models + Migration ✅
- [x] Add `realm_id` (CharField, indexed, non-nullable after backfill) to `Transaction`, `BankTransaction`, `Flag`, and `CloseSummary`.
- [x] Add new `QuickBooksCompany` model (`realm_id` PK, `name`, `is_connected`, `created_at`).
- [x] Change `Transaction` unique constraint from `qb_transaction_id` to `(realm_id, qb_transaction_id)`.
- [x] Change `CloseSummary` unique constraint from `month` to `(realm_id, month)`.
- [x] Migration strategy:
  1. Add nullable `realm_id` fields.
  2. Create `QuickBooksCompany`.
  3. Data-migration backfills existing rows from the most recently updated `QBToken.realm_id`.
  4. Make `realm_id` non-nullable.
  5. Apply new unique constraints.

### Step 2 — OAuth / Token persistence ✅
- [x] In `core/quickbooks/tokens.py::store_tokens`, create/update a `QuickBooksCompany` record for the realm.
- [x] Remove the `QB_SANDBOX_COMPANY_ID` fallback from `store_tokens`.
- [x] Remove `QB_SANDBOX_COMPANY_ID` from `.env.example`, `README.md`, `docs/DEPLOY.md`, `core/quickbooks/client.py` docstring, and `core/tests/test_scaffold.py`.

### Step 3 — Sync layer ✅
- [x] `core/quickbooks/client.py::sync_transactions(qb_client, qb_token=None, realm_id=None)` tags new `Transaction` rows with the given `realm_id`.
- [x] `core/management/commands/sync_quickbooks.py` adds `--realm-id`; if omitted, syncs all connected companies sequentially.
- [x] `core/views.py::qb_sync_now` reads `realm_id` from POST and syncs that company; falls back to most recent token if missing.
- [x] `core/tasks.py::sync_quickbooks_task` calls `sync_quickbooks` without args (sync all connected companies nightly).

### Step 4 — Dashboard company selector ✅
- [x] Add `?company=<realm_id>` query parameter support.
- [x] `_available_months(realm_id=None)` and `_dashboard_context(month, realm_id=None)` filter by realm.
- [x] `dashboard()` reads `company` from `request.GET`, defaults to most recently connected company, passes a `companies` list to the template.
- [x] Update `core/templates/core/dashboard_content.html`:
  - Add a company `<select>` next to the month selector.
  - Include hidden `realm_id` in the sync/reconcile/draft-summary forms so actions target the selected company.

### Step 5 — Reconciliation, anomaly, summary ✅
- [x] `run_reconciliation(month, realm_id=None)` filters `Transaction` and `BankTransaction` by `realm_id`.
- [x] `run_anomaly_detection(month, realm_id=None)` filters transactions by `realm_id`.
- [x] `draft_close_summary(month, realm_id=None)` filters inputs by `realm_id`.
- [x] `core/views.py::reconcile_month` and `draft_summary` pass the selected `realm_id`.
- [x] Management commands `run_reconciliation` and `generate_close_summary` gain `--realm-id`.

### Step 6 — Bank feed ✅
- [x] `core/bank_feed.py::generate_bank_feed(month, realm_id=None, ...)` filters source transactions by `realm_id`.
- [x] `core/management/commands/generate_bank_feed.py` gains `--realm-id`.

### Step 7 — Tests (TDD) ✅
Wrote failing tests first, then implemented:
- [x] `core/tests/test_realm_scoping.py` — migration backfill, realm-scoped unique constraints, `QuickBooksCompany` creation.
- [x] `core/tests/test_quickbooks.py` — `sync_transactions` tags rows with `realm_id`.
- [x] `core/tests/test_views.py` — company selector, sync/reconcile/summary target selected realm, dashboard scopes by company.
- [x] `core/tests/test_multi_company.py` — multi-company sync/reconcile/summary/bank-feed separation.

### Step 8 — Docs ✅
- [x] Update `docs/CURRENT_TASK.md` throughout.
- [x] Append to `docs/CHANGELOG.md` after commit.
- [x] Update `docs/TODO.md` to add and then check off the multi-company section.
- [x] Update `README.md` management-command table and dashboard section to mention company scoping.

## Expected Commit Message
```
feat(core,ui): support multiple QuickBooks sandbox companies
- Add realm_id to Transaction, BankTransaction, Flag, CloseSummary
- Add QuickBooksCompany model and create it on OAuth token storage
- Scope dashboard, sync, reconciliation, anomaly, summary, and bank feed by realm
- Remove QB_SANDBOX_COMPANY_ID fallback
```

## Files Expected to Change
- `core/models.py`
- `core/migrations/0003_multi_company.py`
- `core/quickbooks/tokens.py`
- `core/quickbooks/client.py`
- `core/views.py`
- `core/templates/core/dashboard_content.html`
- `core/bank_feed.py`
- `core/reconciliation/engine.py`
- `core/anomaly/rules.py`
- `core/agent/summary.py`
- `core/management/commands/sync_quickbooks.py`
- `core/management/commands/generate_bank_feed.py`
- `core/management/commands/run_reconciliation.py`
- `core/management/commands/generate_close_summary.py`
- `core/tests/test_models.py`
- `core/tests/test_quickbooks.py`
- `core/tests/test_views.py`
- `core/tests/test_management.py` (or new `core/tests/test_realm_scoping.py`)
- `.env.example`
- `README.md`
- `docs/DEPLOY.md`
- `docs/TODO.md`
- `docs/CURRENT_TASK.md`
- `docs/CHANGELOG.md`
