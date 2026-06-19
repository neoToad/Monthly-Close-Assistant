# Changelog

All notable changes to the Monthly Close Assistant are recorded here, one entry per
commit, per the AGENTS.md workflow.

## feat(reconcile): add account-level bank balance reconciliation

- Added `BankStatementBalance` model keyed on `(realm_id, qb_account_id, month)` to
  store the ending bank balance for a cash account, plus a `source` field tracking
  whether the value came from a manual entry, QB API, CSV upload, or bank feed.
- Added `FlagType.BALANCE_RECONCILIATION` and a nullable `bank_statement_balance` FK
  on `Flag` so balance-reconciliation flags can be replaced idempotently by account
  and month.
- Added `set_bank_balance` management command for manual ending-balance entry.
- Added `core/quickbooks/client.py::fetch_account_current_balances()` and the
  `seed_bank_balances` management command as a sandbox convenience to populate
  `BankStatementBalance` from QuickBooks' live `CurrentBalance` values.
- Added `check_account_balances()` in `core/reconciliation/engine.py`; it sums GL
  activity by account name and creates a `HIGH` severity flag when the stored bank
  balance differs from the posted GL total by more than $0.01.
- Wired `check_account_balances()` into `run_reconciliation()` and updated the
  `run_reconciliation` command output to show `Accounts checked` and `Balance flags`.
- Added model, command, and engine tests; full suite now passes **227 tests**.

## docs(reconcile): document bank balance reconciliation feature

- Updated README feature list and management-command table to describe the new
  `set_bank_balance` and `seed_bank_balances` commands and the balance-level
  reconciliation check.
- Updated `docs/CURRENT_TASK.md` and appended the feature entry to
  `docs/CHANGELOG.md`.

## feat(models): add QBAccount model and extend SourceType choices

- Added `Bill`, `BillPayment`, and `VendorCredit` to `core.models.SourceType`.
- Added `QBAccount` model keyed on `(realm_id, account_id)` with `name`,
  `account_type`, `account_sub_type`, and `active` fields.
- Generated migration `core/migrations/0004_qbaccount.py` and registered
  `QBAccount` in the Django admin.
- Added model tests for new `SourceType` choices and `QBAccount` constraints.

## feat(qb): sync Bills, BillPayments, VendorCredits, and Accounts

- Imported `Bill`, `BillPayment`, `VendorCredit`, and `Account` from python-quickbooks.
- Extended `SYNC_OBJECTS` with `Bill`, `BillPayment`, and `VendorCredit`.
- Extended `normalize_record()` to map vendor and GL account fields for the three
  new AP/cash-out record types.
- Added `sync_accounts()` helper that upserts `QBAccount` rows keyed on
  `(realm_id, account_id)` via `Account.all()`.
- Wired `sync_accounts()` into the `sync_quickbooks` command after transaction sync,
  with `--skip-accounts` and `--skip-reports` flags for faster syncs.
- Updated command output to print per-type counts for all transaction source types.
- Added tests for new normalization paths, `sync_accounts`, and sync command output.

## test(qb): cover new QuickBooks normalization and account sync

- Reorganized Bill/BillPayment/VendorCredit normalization tests into focused
  `BillNormalizeTests`, `BillPaymentNormalizeTests`, and `VendorCreditNormalizeTests`
  classes.
- Added `SyncAccountsTests` verifying upsert behavior keyed on `(realm_id, account_id)`.
- Added `test_sync_command_prints_new_source_counts` for Bill source counts.
- Added `RealmIsolationQBAccountTests` for cross-realm account isolation.
- Added missing vendor-fallback edge-case assertions for the new record types.

## feat(reconcile): scope bank feed to cash-like transaction types

- Added `cash_only: bool = False` parameter to `core/bank_feed.py::generate_bank_feed()`.
- When `cash_only=True`, source transactions are filtered to actual cash-movement
  types: `Purchase`, `Deposit`, `BillPayment`, and `JournalEntry` lines whose
  `gl_account` maps to a cash-like `QBAccount` (Bank / Other Current Asset).
- If no `QBAccount` data exists for the realm, `JournalEntry` rows are included by
  default to preserve existing behavior.
- Added `--cash-only` flag to the `generate_bank_feed` management command.
- Added tests for `--cash-only` filtering, cash-like JournalEntry scoping, and
  realm-isolated cash-only bank feeds.

## feat(agent): cross-check close summary against QuickBooks GeneralLedger

- Added `fetch_general_ledger_summary()` in `core/quickbooks/client.py` that uses
  `qb_client.get_report("GeneralLedger")` and parses the nested report response into
  `{account_name: total_amount}`. Returns `{}` on API failure so summaries still draft.
- Updated `core/agent/summary.py::gather_inputs()` to accept an optional
  `qb_api_client` and include `qb_gl_totals` in the agent inputs.
- Updated `build_prompt()` and `_deterministic_summary()` to append a
  "QuickBooks GL cross-check" paragraph when totals are available.
- Added `GeneralLedgerSummaryTests` and `GeneralLedgerCrossCheckTests` for the fetch
  helper and deterministic summary output.

## docs(qb): document expanded QuickBooks data sources

- Updated `docs/PLAN.md` with a "Data sources" section describing the six
  transaction types, `QBAccount` master data, and GeneralLedger report cross-check.
- Updated `README.md` feature list, management-command table, and latest test count
  (211 tests).
- Updated `docs/TODO.md` to check off the data-source expansion checklist.

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
