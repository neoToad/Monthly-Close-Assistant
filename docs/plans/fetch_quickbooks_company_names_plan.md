# Plan: Fetch QuickBooks Company Names — **COMPLETE**

## Summary

All implementation steps have been completed. The feature is fully functional:

- **`fetch_company_name` helper** — `core/quickbooks/client.py` lines 249-267
- **`store_tokens` accepts `company_name`** — `core/quickbooks/tokens.py` line 67
- **OAuth callback fetches and stores name** — `core/views.py` lines 218-224
- **Sync command refreshes names** — `core/management/commands/sync_quickbooks.py` lines 58-69
- **Tests** — `FetchCompanyNameTests` and `StoreTokensTests` in `test_quickbooks.py`; OAuth callback tests in `test_views.py`
- **Documentation** — README.md documents company names (lines 194-195)

## Original Goal

Populate `QuickBooksCompany.name` automatically from the QuickBooks Online `CompanyInfo`
endpoint, so the dashboard company selector shows real company names instead of raw
`realm_id` values.

## What Was Skipped

**Step 5 (Optional)** — Dashboard "Sync QuickBooks" button does not refresh company names.
This was an intentional decision to keep web syncs fast; names update on OAuth and CLI
syncs instead.

## Open Decisions (Resolved)

1. **Update name on every web sync?** — No, only on OAuth and management command syncs.
2. **Preserve manually edited names?** — Yes; updates only happen when API returns non-empty.
3. **Fetch `CompanyName` vs `LegalName`?** — `CompanyName` primary, `LegalName` fallback.