# Plan: Fetch QuickBooks Company Names

## User's Choice

**Approach:** Populate `QuickBooksCompany.name` automatically from the QuickBooks Online
`CompanyInfo` endpoint, so the dashboard company selector shows real company names instead
of raw `realm_id` values.

## Goal

When a user connects a QuickBooks sandbox company via OAuth, the assistant should fetch
and store the company's display name. Existing connected companies should also pick up
their names on the next sync. The dashboard selector already falls back from `name` to
`realm_id`, so this change is purely about filling the `name` field.

## Current State

- `core/models.py::QuickBooksCompany` already has a `name` CharField (blank, default `""`).
- `core/quickbooks/tokens.py::store_tokens()` creates/updates the `QuickBooksCompany`
  record but only sets `is_connected=True`; `name` is left blank.
- `core/templates/core/dashboard_content.html` displays
  `{{ company.name|default:company.realm_id }}`, so the UI is ready.
- `python-quickbooks==0.9.12` exposes `quickbooks.objects.company_info.CompanyInfo` with a
  `CompanyName` attribute. The v3 API supports `GET /company/{realmId}/companyinfo/1`.
- The `QuickBooksCompany` model has three spurious methods copied from `QBToken`
  (`get_access_token`, `get_refresh_token`, `is_access_token_expired`) that reference
  non-existent fields. They should be removed as a small cleanup while we touch the model.

## Proposed Implementation

### Step 1 — Add a `CompanyInfo` fetch helper in `core/quickbooks/client.py`

- Import `CompanyInfo` from `quickbooks.objects.company_info`.
- Add `fetch_company_name(qb_client, qb_token=None) -> str`.
  - Use `CompanyInfo.get(id=1, qb=qb_client)` wrapped with `call_with_retry` so auth
    refresh and transient retries are handled for free.
  - Read `CompanyName`; if blank, fall back to `LegalName`; if still blank, return `""`.
  - Log a warning and return `""` if the API call fails, so callers don't crash.

### Step 2 — Update `core/quickbooks/tokens.py::store_tokens()`

- Accept an optional `company_name: str = ""` keyword argument.
- When creating/updating the `QuickBooksCompany` record, include the name in the
  `defaults` dict so a fresh connection or a re-auth writes the name immediately.
- Keep `name` editable for the user/admin; only overwrite it when a non-empty value is
  supplied. This prevents an empty API response from blanking out a manually entered name.

### Step 3 — Fetch name during OAuth callback (`core/views.py`)

- In `qb_oauth_callback`, after `store_tokens` succeeds, build a `QuickBooks` client with
  `qb_client.build_quickbooks_client(token)`.
- Call `qb_client.fetch_company_name(qb, qb_token=token)`.
- If a non-empty name comes back, update `QuickBooksCompany.objects.filter(
  realm_id=realm_id).update(name=name)` (or re-call `store_tokens` with the name if we want
  the same code path).
- Wrap the fetch in a narrow `try/except` and log any failure; the OAuth flow must still
  redirect to the dashboard even if the name lookup fails.

### Step 4 — Refresh names during sync (`core/management/commands/sync_quickbooks.py`)

- After building the QB client for a realm, call `fetch_company_name` and update the
  `QuickBooksCompany` record before pulling transactions.
- This backfills names for companies that were connected before this feature and keeps
  names current if they change in QuickBooks.
- Update command output to include the company name when known, e.g.
  `Syncing QuickBooks realm {realm_id} ({name})...`.

### Step 5 — (Optional) Update `qb_sync_now` dashboard action

- The management command already covers periodic/CLI sync. The dashboard "Sync
  QuickBooks" button could also refresh the name, but doing it in `sync_transactions`
  adds an extra API call to every web sync. **Decision:** skip the web sync path for now
  to avoid slowing the dashboard; names update on OAuth and on command syncs.

### Step 6 — Clean up spurious methods on `QuickBooksCompany`

- Remove `get_access_token`, `get_refresh_token`, and `is_access_token_expired` from
  `QuickBooksCompany`. They reference fields that do not exist on the model and will raise
  `AttributeError` if ever called.

### Step 7 — Tests (TDD)

Write failing tests first, then implement.

#### `core/tests/test_quickbooks.py`
- `FetchCompanyNameTests`:
  - Returns `CompanyName` from a mocked `CompanyInfo.get`.
  - Falls back to `LegalName` when `CompanyName` is blank.
  - Returns `""` when both are blank.
  - Returns `""` and logs on API failure (mock `CompanyInfo.get` raising).
- `StoreTokensTests`:
  - Update existing test to assert that passing `company_name` sets the name.
  - Assert that `store_tokens` without `company_name` leaves an existing name intact.

#### `core/tests/test_views.py::OAuthCallbackViewTests`
- After token exchange, `QuickBooksCompany` record has `name` populated from the mocked
  `fetch_company_name`.
- Callback still redirects successfully when `fetch_company_name` raises; name stays blank.

#### `core/tests/test_views.py::SyncCommandTests`
- When syncing a realm, the `QuickBooksCompany` record is created/updated with the name
  returned by the mocked `fetch_company_name`.

#### `core/tests/test_models.py` or `test_realm_scoping.py`
- `QuickBooksCompany` no longer has the three spurious token methods (or a regression test
  ensuring `__str__` still falls back to `realm_id` when name is blank).

### Step 8 — Documentation

- Update `docs/PLAN.md` decision #1: company name source is now fetched from QuickBooks
  `CompanyInfo` on OAuth and sync.
- Update `docs/TODO.md` with a new unchecked item for this feature.
- Update `docs/CURRENT_TASK.md` as work progresses.
- Append to `docs/CHANGELOG.md` after commit.
- Update `README.md` dashboard section to note that company names come from QuickBooks.

## Open Decisions

1. **Update name on every web sync?** Recommended: no, only on OAuth and management
   command syncs, to keep the dashboard sync button fast. We can revisit if names go stale.
2. **Preserve manually edited names?** Recommended: yes; `store_tokens` and sync update only
   when a non-empty name is returned from QuickBooks, so an admin-entered name is not
   overwritten by a blank API response.
3. **Fetch `CompanyName` vs `LegalName`?** Use `CompanyName` as primary, `LegalName` as
   fallback.

## Estimated Scope

- ~4–5 implementation files changed.
- ~3–4 test files updated.
- No new Django migration needed (existing `name` field is already present).

## Files Expected to Change

- `core/quickbooks/client.py`
- `core/quickbooks/tokens.py`
- `core/views.py`
- `core/management/commands/sync_quickbooks.py`
- `core/models.py` (cleanup only)
- `core/tests/test_quickbooks.py`
- `core/tests/test_views.py`
- `core/tests/test_models.py` or `core/tests/test_realm_scoping.py`
- `docs/PLAN.md`
- `docs/TODO.md`
- `docs/CURRENT_TASK.md`
- `docs/CHANGELOG.md`
- `README.md`

## Expected Commit Message

```
feat(qb): fetch and store QuickBooks company names
- Add CompanyInfo fetch helper that returns CompanyName/LegalName
- Store company name during OAuth callback and sync_quickbooks command
- Preserve manually edited names when API returns blank
- Remove spurious token methods from QuickBooksCompany model
```