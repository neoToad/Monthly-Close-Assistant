# Plan: Add Five High-Value QuickBooks Data Sources

## Goal

Expand the Monthly Close Assistant beyond `Purchase`, `Deposit`, and `JournalEntry` so the close workflow covers the main AP/cash flow records and can cross-check its totals against QuickBooks master data and reports.

## The five additions

1. **Bill** — unpaid vendor invoices; the accrual-side obligation that a `Purchase` or check may later settle.
2. **BillPayment** — cash payment against one or more bills; this is a true bank/cash movement.
3. **VendorCredit** — vendor credits that reduce amounts owed; important so reconciliation does not flag legitimate reductions as missing money.
4. **Account** — the QuickBooks chart of accounts. Used to validate `gl_account` strings, map account types, and eventually drive account-level close checks.
5. **GeneralLedger report** — a period-level cross-check so the close summary can compare internal category totals to QuickBooks' own GL totals.

## Why these five

- **Bills + BillPayments + VendorCredits** together describe the AP/cash-out flow that `Purchase` alone misses. A bookkeeper doing month-end close needs both the accrued liability and the cash settlement.
- **VendorCredit** prevents false-positive reconciliation flags when a credit memo legitimately reduces a vendor balance.
- **Account** master data makes `gl_account` values trustworthy and lets future features group transactions by account type (expense, asset, liability, etc.).
- **GeneralLedger report** gives a source-of-truth sanity check without requiring us to perfectly reconstruct the GL from individual transactions.

## Current state

- `core/quickbooks/client.py::SYNC_OBJECTS` maps three types: `Purchase`, `Deposit`, `JournalEntry`.
- `normalize_record()` knows how to read `EntityRef`, `AccountRef`, `DepositToAccountRef`, and `JournalEntryLineDetail`.
- `Transaction.source_type` is a `TextChoices` with only those three values.
- `Transaction` has no foreign key to a chart-of-accounts table; `gl_account` is a free-text string.
- `generate_bank_feed()` derives bank rows from **all** `Transaction` rows for a month+realm.

## Proposed implementation

### Step 1 — Extend `SourceType` and `normalize_record`

Add source-type choices:

```python
class SourceType(models.TextChoices):
    PURCHASE = "Purchase", "Purchase"
    DEPOSIT = "Deposit", "Deposit"
    JOURNAL_ENTRY = "JournalEntry", "Journal Entry"
    BILL = "Bill", "Bill"
    BILL_PAYMENT = "BillPayment", "Bill Payment"
    VENDOR_CREDIT = "VendorCredit", "Vendor Credit"
```

Extend `SYNC_OBJECTS`:

```python
SYNC_OBJECTS = {
    "Purchase": Purchase,
    "Deposit": Deposit,
    "JournalEntry": JournalEntry,
    "Bill": Bill,
    "BillPayment": BillPayment,
    "VendorCredit": VendorCredit,
}
```

Extend `normalize_record()` to handle the new types. Common fields:

| Record type | Date field | Vendor / payee | Amount | GL account source |
|---|---|---|---|---|
| `Bill` | `TxnDate` | `VendorRef.name` | `TotalAmt` | First `AccountRef` from `Line` expenses; fallback `APAccountRef` |
| `BillPayment` | `TxnDate` | `VendorRef.name` | `TotalAmt` (positive in QBO; treat as positive and let the bank feed decide sign) | `BankAccountRef.name` or `CreditCardAccountRef.name` |
| `VendorCredit` | `TxnDate` | `VendorRef.name` | `TotalAmt` | First `AccountRef` from `Line` expenses |

### Step 2 — Add a lightweight chart-of-accounts model

```python
class QBAccount(models.Model):
    realm_id = models.CharField(max_length=50, db_index=True)
    account_id = models.CharField(max_length=50, db_index=True)
    name = models.CharField(max_length=200)
    account_type = models.CharField(max_length=100, blank=True, default="")
    account_sub_type = models.CharField(max_length=100, blank=True, default="")
    active = models.BooleanField(default=True)

    class Meta:
        unique_together = [["realm_id", "account_id"]]
        ordering = ["name"]
```

Add `sync_accounts(qb_client, qb_token=None, realm_id=None)` in `core/quickbooks/client.py` that calls `Account.all(qb=client)` and upserts rows keyed on `(realm_id, account_id)`. This is a separate sync path from `sync_transactions()` because accounts are master data, not transactions.

Wire `sync_accounts` into `sync_quickbooks` after transaction sync so each realm's chart is current.

### Step 3 — GeneralLedger report cross-check

Add a read-only helper, not a full ingestion:

```python
def fetch_general_ledger_summary(qb_client, month: str, qb_token=None) -> dict:
    ...
```

Use `quickbooks.reports.generalledger.GeneralLedger` (or the report endpoint) for the month and return `{account_name: total_amount}`. Wrap with `call_with_retry`. This function is called from `core/agent/summary.py::gather_inputs()` to include QuickBooks GL totals as an extra validation input for the close summary.

No new database table for report rows at this stage; the report is fetched on demand when drafting a summary.

### Step 4 — Reconcile amount signs and bank feed scope

- **Bill**: positive amount, but it is an accrual (not yet cash). Keep as positive in `Transaction`.
- **BillPayment**: positive amount in QBO, but it represents cash leaving. Keep positive; the reconciliation engine matches it against a positive bank debit.
- **VendorCredit**: positive amount in QBO but reduces liability. Keep positive; if it appears on a bank statement as a credit/deposit, the bank feed sign logic handles it.

Update `generate_bank_feed()` so it can optionally restrict source transactions to those types that represent actual cash movement (`Purchase`, `Deposit`, `JournalEntry` with bank/cash lines, `BillPayment`). Default remains "all transactions" for backward compatibility; add a `--cash-only` flag to the management command. This avoids generating fake bank rows from non-cash `Bill` records.

### Step 5 — Update sync command

`sync_quickbooks` currently pulls transactions only. After this change:

1. Sync transactions (existing types + Bill/BillPayment/VendorCredit).
2. Sync accounts.
3. Print per-type counts for the new transaction sources.

Add `--skip-accounts` and `--skip-reports` flags for faster syncs when only transactions are needed.

### Step 6 — Update dashboard / close summary

- `gather_inputs()` adds a `qb_gl_totals` key from `fetch_general_ledger_summary()` when a provider/key is not needed (report fetch uses OAuth token only).
- The deterministic summary appends a "QuickBooks GL cross-check" paragraph when `qb_gl_totals` is available.
- No dashboard UI changes in this phase; the report is input to the agent.

### Step 7 — Tests (TDD)

#### `core/tests/test_quickbooks.py`
- `BillNormalizeTests` — maps `Bill` fields to `Transaction`.
- `BillPaymentNormalizeTests` — maps `BillPayment` fields.
- `VendorCreditNormalizeTests` — maps `VendorCredit` fields.
- `SyncAccountsTests` — upserts `QBAccount` rows keyed on `(realm_id, account_id)`.
- `GeneralLedgerSummaryTests` — returns account totals from a mocked report response.

#### `core/tests/test_views.py` and `test_multi_company.py`
- Update `SimpleNamespace_purchase()`/`_purchase()` helpers are unchanged, but sync tests should include a `Bill` and assert per-type counts.

#### `core/tests/test_realm_scoping.py`
- `QBAccount` unique-together per realm.

#### `core/tests/test_management.py`
- `generate_bank_feed` with `--cash-only` excludes `Bill` source rows.

### Step 8 — Documentation

- Update `docs/PLAN.md` decision notes about data sources.
- Append to `docs/CHANGELOG.md` after each commit.
- Update `docs/TODO.md` with a checklist for this feature.
- Update `docs/CURRENT_TASK.md` as work progresses.
- Update `README.md` features list and management-command table.

## Open decisions

1. **Sign convention for BillPayment and VendorCredit:** Do we store QBO's positive `TotalAmt` and rely on source_type to interpret direction, or normalize to signed amounts (`BillPayment` negative because it's cash out, `VendorCredit` negative because it reduces expense/AP)? Recommended: keep QBO's positive amounts and let reconciliation/source_type logic handle semantics, matching how `Purchase` and `Deposit` already work.
2. **Bank feed default scope:** Should `generate_bank_feed` default to cash-only sources to avoid fake bank rows from `Bill`? Recommended: add `--cash-only` as an opt-in first; change default only after reconciliation tests prove it improves signal.
3. **Account validation:** Should we validate `Transaction.gl_account` against `QBAccount.name` during sync and warn on mismatches? Recommended: defer to a follow-up; this plan only stores the chart for context.
4. **GL report granularity:** Month-level account totals are enough for a summary cross-check. If later we want per-transaction report rows, we can add a `QBReportRow` model.

## Estimated scope

- ~6–8 implementation files changed.
- One new Django model + migration (`QBAccount`).
- New tests for normalization, account sync, and bank-feed scope.
- Small agent/summary enhancement.

## Files expected to change

- `core/models.py` — add `SourceType` choices and `QBAccount` model.
- `core/migrations/0004_qbaccount.py` — new migration.
- `core/quickbooks/client.py` — add imports, extend `SYNC_OBJECTS`, `normalize_record`, `sync_accounts`, `fetch_general_ledger_summary`.
- `core/management/commands/sync_quickbooks.py` — sync accounts, print new type counts.
- `core/bank_feed.py` — add `cash_only` filtering.
- `core/management/commands/generate_bank_feed.py` — add `--cash-only` flag.
- `core/agent/summary.py` — include `qb_gl_totals` in summary inputs.
- `core/tests/test_quickbooks.py` — normalization + account + report tests.
- `core/tests/test_views.py` — sync command output tests.
- `core/tests/test_multi_company.py` — cross-realm account isolation.
- `core/tests/test_management.py` — bank feed `--cash-only` test.
- `README.md`, `docs/TODO.md`, `docs/CHANGELOG.md`, `docs/CURRENT_TASK.md`.

## Expected commit sequence

```
feat(models): add QBAccount model and extend SourceType choices
- Add Bill, BillPayment, VendorCredit to SourceType
- Create QBAccount chart-of-accounts model and migration

feat(qb): sync Bills, BillPayments, VendorCredits, and Accounts
- Extend SYNC_OBJECTS and normalize_record for AP records
- Add sync_accounts helper
- Wire account sync into sync_quickbooks command

test(qb): cover new QuickBooks normalization and account sync
- Add tests for Bill/BillPayment/VendorCredit/QBAccount

feat(reconcile): scope bank feed to cash-like transaction types
- Add cash_only option to generate_bank_feed and management command
- Exclude non-cash Bill records by default when --cash-only is set

feat(agent): cross-check close summary against QuickBooks GeneralLedger
- Fetch GL report summary and include in agent inputs
- Update deterministic fallback to mention QB totals

docs(qb): document expanded QuickBooks data sources
- Update README, PLAN, TODO, CHANGELOG
```