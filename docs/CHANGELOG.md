# Changelog

All notable changes to the Monthly Close Assistant are recorded here, one entry per
commit, per the AGENTS.md workflow.

## feat(qb): fetch and store QuickBooks company names

- Added `CompanyInfo` fetch helper (`fetch_company_name`) in `core/quickbooks/client.py`
  that returns `CompanyName` with a `LegalName` fallback.
- Updated `core/quickbooks/tokens.py::store_tokens()` to accept an optional
  `company_name`; existing manually edited names are preserved when the API returns
  blank.
- `core/views.py::qb_oauth_callback` now fetches and stores the company name after
  token exchange; the OAuth redirect still succeeds if the name lookup fails.
- `core/management/commands/sync_quickbooks.py` refreshes each realm's company name
  before syncing and prints the name in command output.
- Removed the spurious `get_access_token`, `get_refresh_token`, and
  `is_access_token_expired` methods from `QuickBooksCompany` (they referenced fields
  that do not exist on that model).
- Updated `docs/PLAN.md` decision #1, `docs/TODO.md`, and `README.md` dashboard/CI
  sections.
- Removed stale `core/tests/test_cicd.py` because `.github/workflows/ci.yml` was
  deleted earlier; the full suite now passes inside Docker.
