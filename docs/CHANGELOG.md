# Changelog

All notable changes to the Monthly Close Assistant are recorded here, one entry per
commit, per the AGENTS.md workflow.

## feat(engines): connectwise step 4 — add reconciliation engine

- Implemented `core/engines/connectwise_reconciliation.py::run_connectwise_reconciliation`.
- Compares ConnectWise activity (time, expenses, products) to QBO invoice totals per
  client and month, creating three new flag types:
  - `CONNECTWISE_UNBILLED` for hourly/retainer clients with leakage above threshold.
  - `CONNECTWISE_MARGIN` for flat-fee clients whose margin falls below target/warn/critical.
  - `CONNECTWISE_MISSING_MAPPING` for ConnectWise companies without a `ClientMapping`.
- Burden rate resolution is hierarchical: `ConnectWiseWorkRole.burden_rate`, then
  `ClientMapping.default_burden_rate`, then a global default read from Django settings
  (`CONNECTWISE_DEFAULT_BURDEN_RATE`) with a safe constant fallback.
- Added ConnectWise threshold constants to `core/common/constants.py`:
  `CONNECTWISE_UNBILLED_THRESHOLD`, `CONNECTWISE_TARGET_MARGIN`,
  `CONNECTWISE_MARGIN_WARN`, `CONNECTWISE_MARGIN_CRITICAL`, and
  `CONNECTWISE_DEFAULT_BURDEN_RATE`.
- Exported `run_connectwise_reconciliation` from `core/engines/__init__.py`.
- Added 8 tests in `core/tests/test_connectwise_reconciliation.py` covering leakage,
  margin erosion, profitable flat-fee clients, missing mappings, idempotency,
  role-specific burden rates, and large-leakage severity.
- Fixed the role-specific burden-rate test value so it genuinely crosses the margin target.
- Full core test suite passes **347 tests**.

## feat(engines): connectwise step 3 — synthetic connectwise feed generator

- Added six scenario fixtures under `core/fixtures/connectwise_scenarios/`:
  `hourly_leakage`, `flat_fee_profitable`, `flat_fee_margin_erosion`,
  `flat_fee_loss`, `missing_mapping`, and `mixed`.
- Implemented `core/engines/connectwise_feed.py::generate_connectwise_feed` to load a
  fixture and create `ConnectWiseCompany`, `QBCustomer`, `ClientMapping`,
  `ConnectWiseWorkRole`, `TimeEntry`, `ExpenseEntry`, and `ProductEntry` rows for a
  target month/realm.
- Generator is idempotent on `(company, connectwise_entry_id)`, supports `--force` to
  overwrite existing month activity, and accepts an optional `--seed` for reproducibility.
- Added `core/management/commands/generate_connectwise_feed.py` mirroring the existing
  bank-feed command interface.
- Added `core/tests/test_connectwise_feed.py` with 9 tests covering scenario row counts,
  flat-fee mapping creation, missing-mapping scenarios, mixed scenarios, force overwrite,
  idempotency, seed reproducibility, and command output.
- Exported `generate_connectwise_feed` from `core/engines/__init__.py`.
- Full core test suite passes **339 tests**; `makemigrations --check --dry-run` reports
  no changes.

## feat(quickbooks): connectwise step 2 — sync QBO customers and invoices

- Added `sync_customers` and `sync_invoices` helpers in `core/quickbooks/client.py`
  using the existing `call_with_retry` wrapper.
- `sync_customers` upserts `QBCustomer` rows keyed on `(company, customer_id)` and
  updates names/active status on re-runs.
- `sync_invoices` upserts `Invoice` rows keyed on `(company, qb_invoice_id)`,
  replaces `InvoiceLine` detail on updates, and skips invoices whose QBO customer
  is not yet present locally.
- Wired both helpers into the `sync_quickbooks` management command with
  `--skip-customers` and `--skip-invoices` flags.
- Updated command output to report customer and invoice counts alongside accounts.
- Added `core/tests/test_qbo_invoice_sync.py` with 13 tests covering customer/invoice
  creation, updates, idempotency, skipping, and command flags.
- Updated existing `sync_quickbooks` command tests in `core/tests/test_views.py` and
  `core/tests/test_multi_company.py` to patch the new helpers.
- Full core test suite passes **330 tests**.

## feat(models): connectwise step 1 — add QBO customer, invoice, and ConnectWise activity models

- Added `QBCustomer`, `ConnectWiseCompany`, `ClientMapping`, `ConnectWiseWorkRole`,
  `Invoice`, `InvoiceLine`, `TimeEntry`, `ExpenseEntry`, and `ProductEntry` to
  `core/models.py` with realm/company scoping and appropriate unique constraints.
- Extended `FlagType` with `CONNECTWISE_UNBILLED`, `CONNECTWISE_MARGIN`, and
  `CONNECTWISE_MISSING_MAPPING`; increased `Flag.flag_type` max_length to 30.
- Updated the pre-production squashed migration `core/migrations/0001_initial.py`
  to include all new tables and flag-type choices.
- Registered the new models in `core/admin.py`, including a `ClientMappingAdmin`
  tuned for manual mapping workflows.
- Added model-level validation ensuring `ClientMapping.flat_fee_amount` is populated
  when `billing_model=flat_fee`.
- Added `core/tests/test_connectwise_models.py` with 22 tests covering defaults,
  choices, constraints, and the flat-fee validation rule.
- Updated `core/tests/test_models.py` admin-registration test to include the new
  models.
- Full core test suite passes **317 tests**; `makemigrations --check --dry-run`
  reports no changes.

## test(services): add missing idempotency tests (refactor plan 2.6)

- Added `test_dry_run_is_idempotent` and `test_apply_is_idempotent_via_applied_suggestions`
  to `core/tests/test_services.py`; the apply test verifies that
  `apply_account_reconciliation_suggestions` skips suggestions already recorded in
  `AccountReconciliationState.applied_suggestions` and reports them as already applied.
- Added `test_set_bank_balance_is_idempotent` and `test_seed_without_force_is_idempotent`
  to `core/tests/test_management.py`, asserting single rows with stable/latest values.
- Added `test_force_with_seed_is_idempotent` for `generate_bank_feed`, asserting identical
  counts and amounts across two forced runs with the same seed (new row ids expected).
- Added `test_set_bank_balance_view_is_idempotent` to `core/tests/test_views.py`.
- Full core test suite passes **290 tests**.

## feat(services): centralize retry/backoff in `core/services/retry` (refactor plan 2.5.A)

- Added `core/services/retry.py` with a generic `with_retry` helper supporting
  configurable exceptions, exponential backoff with optional jitter, max sleep cap,
  and an optional `on_retry` callback.
- Wrapped `.save()` calls in `core/services/qb_writes.py` with `with_retry` for
  `QuickbooksException`, `ConnectionError`, and `TimeoutError`.
- Wrapped LLM `.invoke()` calls in `core/agent/reconcile.py` and `core/agent/summary.py`
  with `with_retry` for transient provider failures.
- Added `core/tests/test_retry.py` covering first-attempt success, recovery after
  transient failures, exhaustion, non-retryable exceptions, and callback invocation.

## refactor(services): move QB write helpers to `core/services/qb_writes` (refactor plan 2.1.C)

- Moved `apply_suggestion`, `create_journal_entry`, `create_purchase`, `create_deposit`,
  and account-ref helpers from `core/quickbooks/writes.py` to the new
  `core/services/qb_writes.py` module.
- Updated `core/services/reconciliation.py` and
  `core/management/commands/suggest_account_fixes.py` to import from the new location;
  removed the now-empty `core/quickbooks/writes.py` module.
- Refactored `core/agent/reconcile.py` and `core/agent/summary.py` so the agent layer
  no longer imports `core.quickbooks.client`. Live QB data (`qb_current_balance`,
  `qb_gl_totals`) is now fetched by callers and passed in as plain inputs.
- Updated `core/views.py` to fetch current balances for the reconcile-account modal and
  pass them to the agent as `qb_current_balance`.
- Updated all affected tests to patch the new `core.services.qb_writes.apply_suggestion`
  path and to pass `qb_gl_totals` directly to `gather_inputs`.
- Added `core/tests/test_architecture.py` with `AgentLayerBoundaryTests` enforcing that
  `core.agent` modules never import from `core.services.qb_writes` or
  `core.quickbooks.client`.

## refactor(dead-code): remove unused helpers and scaffolding (refactor plan 2.7.A–F)

- Removed unused `refresh_tokens` function from `core/quickbooks/client.py` and the
  matching `RefreshTokensTests` class in `core/tests/test_quickbooks.py`.
- Removed unused `_lookup_suggestion` helper from `core/quickbooks/writes.py`.
- Removed the no-op `--skip-reports` argument and help text from
  `core/management/commands/sync_quickbooks.py`.
- Removed unused `DATE_TOLERANCE_DAYS` import from `core/agent/reconcile.py`.
- Removed unused `Optional` import from `core/quickbooks/writes.py`.
- Replaced the empty `if not force: pass` block in
  `core/management/commands/seed_bank_balances.py` with an explanatory comment.
- Pruned now-unused `django.utils.timezone` / `datetime.timedelta` imports in
  `core/quickbooks/client.py`.
- Full core test suite passes **268 tests** (one fewer than before because dead code's
  dedicated tests were removed).

## docs(plans): add Step 1 audit for refactor plan

- Added `docs/plans/refactor_plan.md` documenting the full Step 1 audit of the
  `feature/close-assistant-build` branch.
- Catalogued drift from the advertised Data Sync → Postgres → Analysis → Agent →
  Dashboard architecture (agent layer entangled with QB writes, engine logic in
  views, scattered realm/company resolution).
- Listed duplicated helpers (`_month_bounds`, `_prior_month`, `CASH_LIKE_ACCOUNT_TYPES`,
  posted-GL total computation), inconsistent naming, missing type hints and
  docstrings, error-handling gaps, and test-coverage holes.
- Identified dead code (`refresh_tokens`, `writes.py:_lookup_suggestion`,
  `--skip-reports` scaffolding, unused imports) and best-practice opportunities
  (grouped queries, retry abstraction, idempotency tests).
- Proposed a sequenced refactor plan in Step 2, plus open questions and explicitly
  out-of-scope items.
- No production code changed in this step.

## feat(ui): expose Generate Bank Feed action on the dashboard

- Added `generate_bank_feed_view` in `core/views.py` that calls
  `core.bank_feed.generate_bank_feed` via POST, supports `force` and `cash_only`
  flags, and refreshes the dashboard with a summary notice or error message.
- Wired URL `/dashboard/bank-feed/generate/` in `core/urls.py`.
- Added a "Generate Bank Feed" button to `core/templates/core/dashboard_content.html`
  in the dashboard actions bar.
- Added `GenerateBankFeedViewTests` in `core/tests/test_views.py` covering row
  creation, no-transaction notice, existing-data protection, and force overwrite.
- Full suite now passes **269 tests**.

## feat(reconcile): implement AI-assisted account reconciliation workflow

- Added `AccountReconciliationState` model keyed on `(company, qb_account_id, month)`
  with `ReconciliationStatus` choices, statement/posted/difference totals,
  `last_suggestions`, and `applied_suggestions` for idempotency.
- Added `Flag.notes` text field so balance-reconciliation flags can carry an audit
  trail of applied QuickBooks objects.
- Implemented `core/agent/reconcile.py::suggest_account_fixes()` with deterministic
  fallback suggestions for bank-only rows and residual gaps, plus optional Anthropic
  / OpenAI LLM enhancement via `langchain_anthropic` / `langchain_openai`.
- Added `core/quickbooks/writes.py` wrappers for `JournalEntry`, `Purchase`, and
  `Deposit` creation that map local `QBAccount` names to QuickBooks `AccountRef`
  objects.
- Added dashboard views (`reconcile_account_suggest`, `reconcile_account_apply`) with
  a confirmation-token safety model: dry-run preview first, then live QB writes only
  after explicit confirmation; post-write sync, reconciliation rerun, and dashboard
  partial swap.
- Added `core/templates/core/reconcile_account_modal.html`,
  `core/templates/core/account_suggestions.html`, and updated
  `bank_balances_section.html` / `dashboard_content.html` with HTMX-driven modal and
  reconcile button styling.
- Added `suggest_account_fixes` and `apply_account_fix` management commands with
  dry-run-by-default behavior and focused tests in
  `core/tests/test_reconcile_commands.py`.
- Added model, agent, QB write, view, and command tests; full suite now passes
  **265 tests**.

## feat(models): attach all realm-scoped models to QuickBooksCompany

- Added a `company` foreign key from `Transaction`, `BankTransaction`, `Flag`,
  `CloseSummary`, `QBAccount`, `BankStatementBalance`, and `QBToken` to
  `QuickBooksCompany`, with `on_delete=models.CASCADE` for referential integrity
  and cascading cleanup.
- Replaced `(realm_id, ...)` unique constraints with `(company, ...)` constraints;
  kept denormalized `realm_id` as an indexed filter for CLI ergonomics and
  backwards-compatible queries.
- Generated migration `core/migrations/0006_alter_bankstatementbalance_unique_together_and_more.py`
  with a `RunPython` backfill that lazily creates missing `QuickBooksCompany` rows
  from existing `realm_id` values and links all affected rows before making the
  foreign keys non-nullable.
- Added `QuickBooksCompanyManager.for_realm(realm_id)` so every creation path can
  resolve the canonical company row in one place.
- Updated `core/quickbooks/client.py` (sync transactions/accounts),
  `core/quickbooks/tokens.py` (store tokens), `core/bank_feed.py`,
  `core/reconciliation/engine.py`, `core/anomaly/rules.py`, `core/agent/summary.py`,
  and `core/views.py` to write `company` on every realm-scoped create/upsert.
- Updated management commands `sync_quickbooks`, `generate_bank_feed`,
  `run_reconciliation`, `generate_close_summary`, `set_bank_balance`, and
  `seed_bank_balances` to require/accept `--realm-id` and resolve the company.
- Updated all test helpers and fixtures to set `company`; full suite now passes
  **232 tests**.

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

## feat(ui): expose bank balance reconciliation on the dashboard

- Added a "Bank Balances" panel to `core/templates/core/dashboard_content.html`
  showing each cash account's stored ending balance, posted GL total, and
  reconciled/unreconciled status.
- Added an inline "Set Bank Balance" form (POST to `/dashboard/balance/set/`) that
  creates or updates `BankStatementBalance` rows without leaving the dashboard.
- Added `flag_type_class` and `flag_type_label` template filters so
  `BALANCE_RECONCILIATION` flags render a distinct "Balance" badge and CSS class.
- Added `_bank_balances_context()` helper in `core/views.py` and the
  `set_bank_balance` view that returns the `bank_balances_section.html` partial for
  HTMX swapping.
- Added dashboard view tests for the balances panel, unreconciled gap styling, and
  the set-balance form.

## docs(ui,reconcile): document dashboard bank balance reconciliation

- Updated README feature list and dashboard section to describe the Bank Balances
  panel and inline balance entry.
- Updated latest test count to **230 tests**.
- Updated `docs/CURRENT_TASK.md` and appended entries to `docs/CHANGELOG.md`.


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
- Updated `core/management/commands/sync_quickbooks.py` refreshes each realm's company name
  before syncing and prints the name in command output.
- Removed the spurious `get_access_token`, `get_refresh_token`, and
  `is_access_token_expired` methods from `QuickBooksCompany` (they referenced fields
  that do OR models. Kept as single module per Django convention.

## Test Counts

- After dead-code cleanup: **268 tests** passing.

## refactor(reconcile): extract `compute_posted_total` and grouped queries (refactor plan 2.1.B, 2.8.A)

- Added `compute_posted_total(month, account_name, realm_id=None)` in
  `core/reconciliation/engine.py` as the single source of truth for posted-GL
  cash-account totals.
- Updated `core/views.py:_bank_balances_context`,
  `core/reconciliation/engine.py:check_account_balances`, and
  `core/agent/reconcile.py:gather_account_inputs` to use the new helper.
- Replaced manual generator sums with `Sum` aggregates and replaced the
  per-row `bank_transactions.count()` loop in `gather_account_inputs` with a
  `Count("bank_transactions")` annotation.
- Added `select_related("matched_transaction_id")` on bank-row queries to avoid
  N+1 lookups.
- Added `ComputePostedTotalTests` in `core/tests/test_reconciliation.py` and
  fixed `_make_txn` to generate unique `qb_transaction_id` values.
- Full suite now passes **272 tests**.

## refactor(services): extract apply-flow service layer (refactor plan 2.1.A)

- Added `core/services/reconciliation.py` with
  `apply_account_reconciliation_suggestions(...)` that centralizes dry-run
  preview, QuickBooks client construction, selected-suggestion writes via
  `qb_writes.apply_suggestion`, post-apply transaction sync, reconciliation
  rerun, `AccountReconciliationState` update, and balance-reconciliation flag
  audit notes.
- Refactored `core/views.py:reconcile_account_apply` to a thin HTTP wrapper
  that calls the service and renders the modal or bank-balances partial.
- Refactored `core/management/commands/apply_account_fix.py` to delegate to
  the same service, so the view and command share one code path.
- Added `core/tests/test_services.py` with direct service-layer coverage for
  dry run, unknown suggestion, missing token, and successful apply paths.
- Updated `core/tests/test_views.py` and `core/tests/test_reconcile_commands.py`
  to patch dependencies inside the new service module.
- Full suite now passes **276 tests**.
