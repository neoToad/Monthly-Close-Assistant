# Plan: Support Multiple QuickBooks Sandbox Companies

## User's Choice

**Approach:** Add a company selector to the dashboard, similar to the existing month selector. All dashboard views and actions filter by the selected QuickBooks realm (company).

## Goal

Allow connecting and working with three separate QuickBooks sandbox companies, with clear separation of transactions, bank feeds, flags, and close summaries per company.

## Current State

- `QBToken` already stores one row per `realm_id` and uses `realm_id` as a unique key.
- `get_active_token()` returns the most recently refreshed token by default.
- The `Transaction` model has no realm/company field, and `qb_transaction_id` is globally unique across the table. This means transaction IDs from different QuickBooks companies could collide.
- The dashboard currently only scopes by month, not by company.

## Proposed Implementation

### Step 1 — Model changes (migration required)

Add a `realm_id` field to the data models so every row is scoped to a QuickBooks company.

Models to update:
- `Transaction` — add `realm_id` CharField, indexed
- `BankTransaction` — add `realm_id` CharField, indexed
- `Flag` — add `realm_id` CharField (or infer from linked transaction/bank row)
- `CloseSummary` — add `realm_id` CharField, and change the unique constraint from `(month)` to `(realm_id, month)`

Migration strategy:
- Add nullable `realm_id` fields in the migration.
- Provide a data migration that backfills existing rows from the most recently refreshed `QBToken`. For multi-user/multi-realm ambiguity, this is a best-effort default.
- After backfill, make `realm_id` non-nullable.

### Step 2 — Store company metadata

Introduce a lightweight `QuickBooksCompany` model:

```python
class QuickBooksCompany(models.Model):
    realm_id = models.CharField(max_length=50, unique=True, primary_key=True)
    name = models.CharField(max_length=200, blank=True, default="")
    is_connected = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

- Create or update this record in the OAuth callback after token exchange.
- Use it to populate the company selector dropdown.
- If no `QuickBooksCompany` name is stored, fall back to showing the realm id.

### Step 3 — Remove deprecated `QB_SANDBOX_COMPANY_ID` (small cleanup)

- Remove `QB_SANDBOX_COMPANY_ID` from `.env.example`.
- Remove it from `core/quickbooks/tokens.py` fallback in `store_tokens()`.
- Remove it from `core/quickbooks/client.py` module docstring.
- Remove it from `core/tests/test_scaffold.py` env-var checklist.
- Remove it from `README.md`, `docs/DEPLOY.md`, and any prompt docs.
- This variable is unnecessary because the OAuth callback provides the real `realm_id`.

### Step 4 — Update sync logic

- `core/quickbooks/client.py`:
  - `sync_transactions(qb_client, qb_token, realm_id=None)` should accept an explicit realm and tag new `Transaction` rows with it.
- `core/views.py`:
  - `qb_sync_now` reads `realm_id` from the POST body and syncs that company.
  - If no `realm_id` is provided, fall back to the most recently connected company.
- `core/management/commands/sync_quickbooks.py`:
  - Add an optional `--realm-id` argument. If omitted, sync all connected companies sequentially.

### Step 5 — Update dashboard to filter by company

- Add `realm_id` to the dashboard query parameters (`?company=...&month=...`).
- `core/views.py`:
  - `dashboard()` reads `company` from `request.GET`.
  - `_available_months()` and `_dashboard_context()` filter by `realm_id`.
  - If no company is selected, default to the most recently connected company.
  - Pass a list of connected companies to the template for the selector.
- `core/templates/core/dashboard_content.html`:
  - Add a company `<select>` next to the month selector.
  - Include a hidden `realm_id` in the sync/reconcile/draft-summary forms so actions target the selected company.

### Step 6 — Update reconciliation and summary

- `run_reconciliation(month, realm_id=None)` — filter both `Transaction` and `BankTransaction` by `realm_id`.
- `run_anomaly_detection(month, realm_id=None)` — filter transactions by `realm_id`.
- `draft_close_summary(month, realm_id=None)` — filter inputs by `realm_id`.
- `core/views.py`:
  - `reconcile_month` and `draft_summary` pass the selected `realm_id` through.
- Management commands `run_reconciliation` and `generate_close_summary` gain `--realm-id` arguments.

### Step 7 — Update bank feed generator

- `core/bank_feed.py`:
  - `generate_bank_feed(month, realm_id=None, ...)` — filter source `Transaction` rows by `realm_id`.
- `core/management/commands/generate_bank_feed.py`:
  - Add `--realm-id` argument.

### Step 8 — Update tests

- Add migration tests to ensure `realm_id` is backfilled and non-nullable.
- Update existing reconciliation, sync, summary, and dashboard tests to provide a `realm_id`.
- Add multi-company tests:
  - Syncing company A does not create transactions tagged as company B.
  - Dashboard shows only the selected company's months and flags.
  - `CloseSummary` uniqueness is per `(realm_id, month)`.

### Step 9 — Documentation + changelog

- Update `README.md` to explain connecting multiple companies.
- Update `docs/TODO.md` and `docs/CHANGELOG.md`.
- Update `docs/CURRENT_TASK.md` throughout implementation.

## Open Decisions

1. **Company name source:** Do we fetch the company display name from QuickBooks during OAuth (one extra API call), or let users manually edit names later?
2. **Default company behavior:** When no company is selected, default to the most recently connected, or show a "Select a company" empty state?
3. **CloseSummary uniqueness:** Change from unique `(month)` to unique `(realm_id, month)` — this is required for multi-company separation.
4. **Flag realm scoping:** Add `realm_id` directly to `Flag` for fast filtering, or always derive it from `transaction__realm_id` / `bank_transaction__realm_id`?

## Estimated Scope

- ~10–12 files changed.
- One Django migration (schema + data).
- New tests for multi-company behavior.
- Small UI change (company selector in dashboard).

## Files Expected to Change

- `core/models.py`
- `core/migrations/` (new migration)
- `core/quickbooks/client.py`
- `core/quickbooks/tokens.py` (possibly create company record)
- `core/views.py`
- `core/urls.py` (no change if using query param)
- `core/management/commands/sync_quickbooks.py`
- `core/management/commands/generate_bank_feed.py`
- `core/management/commands/run_reconciliation.py`
- `core/management/commands/generate_close_summary.py`
- `core/bank_feed.py`
- `core/reconciliation/engine.py`
- `core/anomaly/rules.py`
- `core/agent/summary.py`
- `core/templates/core/dashboard_content.html`
- `core/tests/test_quickbooks.py`
- `core/tests/test_views.py`
- `core/tests/test_management.py`
- `core/tests/test_reconciliation.py` (if it exists) or new tests
- `README.md`, `docs/TODO.md`, `docs/CHANGELOG.md`, `docs/CURRENT_TASK.md`