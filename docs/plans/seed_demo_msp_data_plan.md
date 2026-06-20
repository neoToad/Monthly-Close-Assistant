# Plan: Seed Realistic MSP Demo Data Locally

**Status:** Draft / ready for implementation  
**Date:** 2026-06-20  

## Goal

Add a management command that seeds the local database with realistic MSP (managed service provider) financial data so the dashboard looks like a real company that Next Level Networks might serve. No QuickBooks sandbox writes are required; all data is created directly in the app's Postgres database and can be wiped/re-seeded at any time.

This gives a fast, deterministic, offline-friendly demo for:

- Bank reconciliation
- Anomaly detection
- Account-level balance reconciliation
- (Future) ConnectWise-to-QBO client reconciliation

## Why local seed instead of QBO sandbox push

Pushing data into the Intuit sandbox via the QuickBooks SDK is possible, but for an MVP it is slower, less deterministic, requires live credentials, and risks cluttering the sandbox company. Seeding locally:

- Works without any QuickBooks OAuth credentials.
- Produces the same dashboard state every run.
- Runs in CI and local dev instantly.
- Is safe to run repeatedly with `--force`.
- Can be extended later with a separate optional bridge that pushes the same seed into a sandbox.

## What "realistic MSP data" means

A fictional MSP called **Next Level Networks Demo** with:

- A plausible chart of accounts (cash, AR, AP, revenue, labor, subscriptions, circuits, etc.)
- A mix of flat-fee / managed-services clients and hourly / project clients
- Monthly vendor bills for common MSP stack costs
- Deposits and invoices representing client payments
- A few realistic discrepancies so reconciliation has something to catch

This is not meant to be a full accounting system — it is a believable slice of data for close-review demos.

## Proposed changes

### 1. New management command

`core/management/commands/seed_demo_msp_data.py`

```bash
python manage.py seed_demo_msp_data 2026-06 \
    --realm-id demo-msp \
    [--force] \
    [--include-bank-feed] \
    [--seed 123]
```

Arguments:

- `month` (required) — month in `YYYY-MM` format; transactions are spread across this month.
- `--realm-id` (default `demo-msp`) — the synthetic realm id. A `QuickBooksCompany` row is created on demand.
- `--force` — delete existing demo data for the `(realm_id, month)` and re-seed.
- `--include-bank-feed` — also call the existing `generate_bank_feed` engine so `BankTransaction` rows exist for reconciliation.
- `--seed` — optional random seed for date jitter; amounts stay fixed so demo math is stable.

### 2. Chart of accounts

Seed `QBAccount` rows for the demo realm:

| Account ID | Name | Type |
|---|---|---|
| 1000 | Operating Checking | Bank |
| 1200 | Accounts Receivable | Accounts Receivable |
| 2100 | Accounts Payable | Accounts Payable |
| 4000 | Managed Services Revenue | Income |
| 4100 | Project / Hourly Revenue | Income |
| 5000 | Technician Labor | Expense |
| 5100 | Subcontractor Costs | Expense |
| 5200 | Software & Subscriptions | Expense |
| 5300 | Telecom & Internet Circuits | Expense |
| 5400 | Mileage & Travel | Expense |
| 5500 | Office Supplies | Expense |
| 5600 | Bank Service Charges | Expense |

These are created idempotently keyed on `(company, account_id)`.

### 3. Customers and vendors

Represented as strings on `Transaction` rows. If the ConnectWise integration plan is implemented later, the same names will be used for `QBCustomer` and `ConnectWiseCompany` rows so `ClientMapping` can be pre-seeded.

**Flat-fee / managed services clients**

- Acme Manufacturing — $8,500/mo
- Beta Dental Group — $6,000/mo
- Gamma Law Firm — $12,000/mo

**Hourly / T&M clients**

- Delta Construction
- Epsilon Retail

**Vendors**

- Datto / Kaseya
- SentinelOne
- Microsoft 365 Licensing
- Comcast Business
- Paychex Payroll Services
- Amazon Business
- First National Bank

### 4. GL transactions to seed

For the target month, create `Transaction` rows of the following source types:

**Deposits** (client payments hitting the checking account)
- Acme Manufacturing — $8,500
- Beta Dental Group — $6,000
- Gamma Law Firm — $12,000
- Delta Construction — partial payment $3,200 (against ~$5,000 of work)
- Epsilon Retail — $1,800

**Bills** (vendor invoices to pay later)
- Paychex — technician payroll burden — $14,000
- Datto — BDR subscription — $2,400
- SentinelOne — endpoint security — $1,800
- Microsoft 365 Licensing — $1,200
- Comcast Business — fiber circuit — $950
- Subcontractor LLC — emergency router install — $1,500

**Purchases** (direct expenses paid from checking or credit card)
- Amazon Business — networking supplies — $450
- Mileage reimbursement entries — $220
- Office supplies — $85

**Journal Entries** (payroll allocation, small adjustments)
- Debit Technician Labor / Credit Wages Payable — $3,500
- Small adjusting entry — $100

**Bill Payments**
- Pay Paychex bill — $14,000
- Pay Datto bill — $2,400
- Pay Comcast bill — $950

**Vendor Credits**
- SentinelOne one-month service credit — -$300

### 5. Bank statement balances

Seed one `BankStatementBalance` row for the operating checking account:

- `qb_account_id = 1000`
- `account_name = Operating Checking`
- `ending_balance` set to a realistic month-end value that does **not** exactly match the posted GL total, so the balance-reconciliation check produces a flag.

### 6. Optional synthetic bank feed

When `--include-bank-feed` is passed, the command calls the existing `generate_bank_feed` engine for the same month/realm with default discrepancy rates. This populates `BankTransaction` rows so `run_reconciliation` immediately produces flags.

### 7. Data structure in code

Use an inline Python data structure in the command module rather than JSON fixtures, because:

- Dates are relative to the target month.
- Amounts and vendor/client names are stable and readable.
- It is easy to extend with conditional branches for future models.

A helper module `core/fixtures/msp_demo_data.py` can hold the static lists so the command stays readable:

```python
ACCOUNTS = [...]
CUSTOMERS = {...}
VENDORS = {...]
DEPOSITS = [...]
BILLS = [...]
PURCHASES = [...]
JOURNAL_ENTRIES = [...]
BILL_PAYMENTS = [...]
VENDOR_CREDITS = [...]
```

### 8. Date placement

Each transaction's `date` falls inside the target month, jittered by up to a few days if `--seed` is provided. Core recurring items (e.g. monthly invoices/deposits) are placed near the 1st or 15th to feel realistic.

### 9. Forward compatibility

The command will be written so it can be extended later to seed:

- `QBCustomer` and `Invoice` rows when the ConnectWise integration plan adds those models.
- `ConnectWiseCompany`, `ClientMapping`, `TimeEntry`, `ExpenseEntry`, and `ProductEntry` when the ConnectWise reconciliation plan is implemented.

Those extensions are out of scope for this MVP but the fixture structure should leave obvious hooks for them.

## Files touched

### New files

* `core/management/commands/seed_demo_msp_data.py`
* `core/fixtures/msp_demo_data.py`
* `core/tests/test_seed_demo_msp_data.py`

### Modified files

* `docs/TODO.md` — add demo-data section.
* `docs/CURRENT_TASK.md` — reflect active work.
* `docs/CHANGELOG.md` — summarize the new command.

No model or migration changes are required.

## Test plan

### Command tests

* `seed_demo_msp_data 2026-06` creates the expected `QuickBooksCompany` and `QBAccount` rows.
* It creates the expected counts of `Transaction` rows by `source_type`.
* It creates one `BankStatementBalance` row for the checking account.
* Without `--force`, running the command twice raises `CommandError`.
* With `--force`, it deletes and re-creates rows; counts remain stable.
* With `--include-bank-feed`, it also creates `BankTransaction` rows.

### Reconciliation integration test

* After seeding with `--include-bank-feed`, running `run_reconciliation` creates reconciliation flags.
* The balance-reconciliation check creates a `BALANCE_RECONCILIATION` flag because the seeded statement balance intentionally does not equal the posted GL total.

### Anomaly integration test

* After seeding, running `run_reconciliation` creates anomaly flags (e.g. category MoM jump, new vendor, duplicate) if the seeded data triggers them.

### Dashboard smoke test

* Seed data, open `/dashboard/`, select `demo-msp` and the target month, and confirm the bank balances panel, flags, and summary section render.

## Command output

Example console output:

```
Seeded Next Level Networks Demo for 2026-06:
  Accounts: 12
  Transactions: 22 (Deposits=5, Bills=6, Purchases=3, JournalEntry=2, BillPayment=3, VendorCredit=1)
  Bank statement balance: $42,315.50 for Operating Checking
  Bank feed rows: 0 (use --include-bank-feed to generate)
```

With `--include-bank-feed`:

```
Seeded Next Level Networks Demo for 2026-06:
  Accounts: 12
  Transactions: 22
  Bank statement balance: $42,315.50 for Operating Checking
  Bank feed rows: 20 (1 dropped, 1 duplicated, 1 amount shift, 1 date shift, 1 extra)
```

## Risks and open decisions

| Risk | Mitigation |
|---|---|
| Seeding a huge month of data slows tests. | Keep the fixture small (one month, ~25 transactions). Tests use `--force` and scope to a unique realm id. |
| Demo data accidentally mixes with real synced data. | Default to a clearly synthetic `realm_id` (`demo-msp`). `--force` only deletes rows scoped to that realm + month. |
| Fixed amounts make the demo feel stale after repeated runs. | Date jitter via `--seed` keeps it fresh; amounts stay fixed so assertions are stable. |
| Future ConnectWise plan needs the same customer names. | Use consistent names in this fixture and document them for the ConnectWise plan. |

## Future work (out of scope)

* A separate optional command `push_demo_to_qbo_sandbox` that writes the same fixture data into a real QuickBooks sandbox company via the SDK, then pulls it back with `sync_quickbooks`.
* Multi-month historical seeding so anomaly detection has richer history.
* Configurable client/vendor lists via external JSON or command-line arguments.
* Seeding `QBCustomer` and `Invoice` rows once those models exist.
* Seeding `ConnectWiseCompany`, `ClientMapping`, and activity rows once the ConnectWise plan is implemented.

## Commit plan

Single commit:

`feat(demo): add seed_demo_msp_data command with realistic MSP fixture`

1. Add `core/fixtures/msp_demo_data.py` with accounts, customers, vendors, and transactions.
2. Add `core/management/commands/seed_demo_msp_data.py` with `--force`, `--include-bank-feed`, and `--seed`.
3. Add `core/tests/test_seed_demo_msp_data.py` covering idempotency, counts, and reconciliation integration.
4. Update `docs/TODO.md`, `docs/CURRENT_TASK.md`, `docs/CHANGELOG.md`.

## Verification

```bash
# Seed the demo
docker compose exec web python manage.py seed_demo_msp_data 2026-06 --include-bank-feed

# Run reconciliation and see flags
docker compose exec web python manage.py run_reconciliation 2026-06 --realm-id demo-msp

# Open the dashboard
docker compose exec web python manage.py createsuperuser  # if needed
# Browse to http://localhost:8000/dashboard/?company=demo-msp&month=2026-06
```

Expected: bank balances panel shows Operating Checking with a difference flag, reconciliation flags appear, and the close summary can be drafted.

## Note on QuickBooks sandbox

This plan intentionally does **not** push data into QuickBooks Online. All data lives in the app's database. If a future demo requires showing live QBO read/write, that should be a separate plan that builds a one-way bridge from this local seed into the sandbox.