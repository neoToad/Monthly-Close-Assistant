# Monthly Close Assistant — Long Horizon Prompt: Expand QuickBooks Data Sources

You are continuing the Monthly Close Assistant on branch `feature/close-assistant-build`. This prompt drives the implementation of `docs/plans/add_quickbooks_data_sources_plan.md`.

Before starting, read:

- [AGENTS.md](../../AGENTS.md) — working rules (TDD, commit format, tracking files, Docker test context)
- [docs/plans/add_quickbooks_data_sources_plan.md](../plans/add_quickbooks_data_sources_plan.md) — the detailed implementation plan for this feature
- [CLAUDE.md](../../CLAUDE.md) — project instructions (points to AGENTS.md)

This plan is intentionally bounded: add **five** high-value QuickBooks data sources and nothing else. Do not extend scope to real bank feeds, CSV import, deployment hardening, or roles/permissions.

---

## Scope (what this stage builds)

Add five QuickBooks data sources to the existing multi-company, realm-scoped close workflow:

1. **Bill** — accrued vendor invoices (`quickbooks.objects.bill.Bill`). Stored as `Transaction` with `source_type="Bill"`.
2. **BillPayment** — cash payments against bills (`quickbooks.objects.billpayment.BillPayment`). Stored as `Transaction` with `source_type="BillPayment"`.
3. **VendorCredit** — vendor credit memos (`quickbooks.objects.vendorcredit.VendorCredit`). Stored as `Transaction` with `source_type="VendorCredit"`.
4. **Account** — QuickBooks chart of accounts (`quickbooks.objects.account.Account`). Stored in a new `QBAccount` model keyed on `(realm_id, account_id)`.
5. **GeneralLedger report** — month-level account totals from the Reports API (`quickbooks.reports.generalledger.GeneralLedger`). Used as a cross-check input to the close-summary agent; no new DB table.

After this stage, the app covers the core AP/cash-out flow, can validate GL account context against the chart of accounts, and can compare its own totals to QuickBooks' GL report during close summary drafting.

---

## Git setup

1. Work on the existing branch `feature/close-assistant-build`. Do not create a new branch.
2. Make one commit per logical change (see commit sequence below).
3. Use the repo's commit format from AGENTS.md:
   ```
   <type>(<scope>): <summary>
   - <what changed>
   ```
   Reference the step number in the summary or scope, e.g. `feat(models): step 1 — add QBAccount and extend SourceType choices`.

---

## Environment assumptions

- Docker Compose stack is running (`docker compose up --build` or already running).
- Django tests must run inside the `web` container:
  ```bash
  docker compose exec web python manage.py test ...
  ```
- python-quickbooks is already installed; use its object classes:
  - `quickbooks.objects.bill.Bill`
  - `quickbooks.objects.billpayment.BillPayment`
  - `quickbooks.objects.vendorcredit.VendorCredit`
  - `quickbooks.objects.account.Account`
  - `quickbooks.reports.generalledger.GeneralLedger`

---

## Testing (TDD — from AGENTS.md)

Testing is part of every step:

1. Write failing tests first.
2. Confirm they fail for the right reasons.
3. Write the minimum code to make them pass.
4. Refactor if needed, keeping tests green.

- Add new tests to the appropriate files:
  - `core/tests/test_quickbooks.py` — normalization, account sync, GL report fetch.
  - `core/tests/test_models.py` — `QBAccount` model shape and constraints.
  - `core/tests/test_views.py` — sync command output and new source counts.
  - `core/tests/test_multi_company.py` — cross-realm account isolation.
  - `core/tests/test_management.py` — bank feed `--cash-only` behavior.
- Run targeted tests inside Docker as you go, then run the full suite before each commit.
- No commit while tests are failing.
- Never write implementation before tests.

---

## Implementation order and commits

Execute these in order. Stop after each commit and run the full suite.

### Step 1 — Extend the schema
**Commit:** `feat(models): add QBAccount model and extend SourceType choices`

- Add `Bill`, `BillPayment`, `VendorCredit` to `core/models.py::SourceType`.
- Add a new `QBAccount` model in `core/models.py`:
  - `realm_id`, `account_id`, `name`, `account_type`, `account_sub_type`, `active`.
  - Unique together on `(realm_id, account_id)`.
- Generate migration `core/migrations/0004_qbaccount.py`.
- Write failing model tests first, then make them pass.

### Step 2 — Sync the new transaction types
**Commit:** `feat(qb): sync Bills, BillPayments, VendorCredits, and Accounts`

- Import `Bill`, `BillPayment`, `VendorCredit` in `core/quickbooks/client.py`.
- Extend `SYNC_OBJECTS` with the three new types.
- Extend `normalize_record()` to handle each new type. Map:
  - `Bill`: `VendorRef` → vendor, first `Line.AccountRef` → `gl_account`, fallback `APAccountRef`.
  - `BillPayment`: `VendorRef` → vendor, `BankAccountRef` or `CreditCardAccountRef` → `gl_account`.
  - `VendorCredit`: `VendorRef` → vendor, first `Line.AccountRef` → `gl_account`.
- Add `sync_accounts(qb_client, qb_token=None, realm_id=None)` that calls `Account.all(qb=client)` and upserts into `QBAccount` keyed on `(realm_id, account_id)`.
- Wire `sync_accounts` into `core/management/commands/sync_quickbooks.py` after transaction sync.
- Print per-type counts for the new transaction sources in command output.
- Write failing tests first, then implement.

### Step 3 — Test coverage for normalization and account sync
**Commit:** `test(qb): cover new QuickBooks normalization and account sync`

- Add `BillNormalizeTests`, `BillPaymentNormalizeTests`, `VendorCreditNormalizeTests` to `core/tests/test_quickbooks.py`.
- Add `SyncAccountsTests` verifying upsert by `(realm_id, account_id)`.
- Add `test_sync_command_prints_new_source_counts` to `core/tests/test_views.py::SyncCommandTests`.
- Add realm-isolation tests for `QBAccount` to `core/tests/test_multi_company.py`.
- Add `QBAccount` model tests to `core/tests/test_models.py`.

### Step 4 — Scope bank feed to cash-like transaction types
**Commit:** `feat(reconcile): scope bank feed to cash-like transaction types`

- Add a `cash_only: bool = False` parameter to `core/bank_feed.py::generate_bank_feed()`.
- When `cash_only=True`, restrict source `Transaction` rows to source types that represent actual cash movement: `Purchase`, `Deposit`, `JournalEntry` (bank/cash lines), and `BillPayment`.
  - For `JournalEntry`, include it only if `gl_account` belongs to an `QBAccount` with `account_type` in `("Bank", "Other Current Asset")` or similar cash-like types. If `QBAccount` data is missing, include `JournalEntry` by default to avoid regressions.
- Add `--cash-only` flag to `core/management/commands/generate_bank_feed.py`.
- Add tests in `core/tests/test_management.py` and `core/tests/test_multi_company.py`.

### Step 5 — GeneralLedger report cross-check in close summary
**Commit:** `feat(agent): cross-check close summary against QuickBooks GeneralLedger`

- Add `fetch_general_ledger_summary(qb_client, month, qb_token=None)` to `core/quickbooks/client.py` that returns `{account_name: total_amount}` for the month.
- Call it from `core/agent/summary.py::gather_inputs()` when `ANTHROPIC_API_KEY` is absent or present (it is cheap and uses existing OAuth).
- Include `qb_gl_totals` in the agent inputs; update `build_prompt()` and `_deterministic_summary()` to add a "QuickBooks GL cross-check" paragraph when totals are available.
- Add tests for the fetch helper and the deterministic summary output.

### Step 6 — Documentation
**Commit:** `docs(qb): document expanded QuickBooks data sources`

- Update `docs/PLAN.md` notes about data sources.
- Update `docs/TODO.md` to check off this feature.
- Append to `docs/CHANGELOG.md` with a per-step summary.
- Update `docs/CURRENT_TASK.md` to mark completion.
- Update `README.md` features list and management-command table.

---

## Sign conventions (locked decision)

Store QuickBooks' positive `TotalAmt` for all transaction types. Do not flip signs. Rely on `source_type` and future reconciliation logic to interpret direction. This matches how `Purchase` and `Deposit` already work.

---

## Bank feed default behavior (locked decision)

`generate_bank_feed()` defaults to `cash_only=False` to preserve existing tests and behavior. Add `--cash-only` as an opt-in flag. Consider changing the default in a follow-up after reconciliation tests prove cash-only improves signal.

---

## Account validation (out of scope for this stage)

Do not validate `Transaction.gl_account` against `QBAccount.name` during sync in this plan. Only store the chart of accounts and use it for the `JournalEntry` cash-line filter and the GL report cross-check. Validation can be added later.

---

## Tracking files

Maintain these per AGENTS.md:

- `docs/CURRENT_TASK.md` — overwrite with the current step and next step at the start of each step.
- `docs/CHANGELOG.md` — append one entry per commit.
- `docs/TODO.md` — add and check off the feature checklist.

---

## Refactoring and improvements

As you build, use judgment to add sensible improvements: helper functions for repeated normalization logic, clearer docstrings, defensive handling of missing optional fields, type hints, or small logging improvements. Note these in CHANGELOG.md.

---

## Rules

- Never write implementation before tests.
- Complete, commit, and run the full suite after each step.
- Do not batch multiple steps into one commit.
- No commit message if tests are failing.
- Always commit `docs/CURRENT_TASK.md`, `docs/CHANGELOG.md`, and `docs/TODO.md` alongside code files.
- Never commit secrets or credentials.

---

## When all six steps are complete

- Update `docs/CURRENT_TASK.md` to mark the data-source expansion as complete.
- Confirm all six commits are on `feature/close-assistant-build` with correct messages.
- List any uncommitted files.
- Print a summary of what was built, improvements beyond the spec, and any deviations.
- Do not open a pull request or start another feature unless instructed.
