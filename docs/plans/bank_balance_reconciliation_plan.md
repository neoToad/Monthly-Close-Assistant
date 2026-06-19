# Implementation Plan: Bank Balance Reconciliation

**Status:** Draft — awaiting approval.

## Goal

Give the Monthly Close Assistant an account-level reconciliation control: compare the
ending bank balance for a cash account against the posted GL activity for that account
in the same month, and raise a `Flag` when they differ by more than a small tolerance.

This catches the current sandbox issue where the bank balance is **–$3,621.93** and the
posted GL balance is **–$568.38** — a $3,053.55 gap that should be surfaced as a close
blocker.

## Design decisions

1. **Canonical source of truth (Path B):** A new `BankStatementBalance` model keyed on
   `(realm_id, qb_account_id, month)` stores the user-provided (or statement-provided)
   ending balance per account per month. This mirrors how real bank reconciliation works.
2. **Sandbox auto-seeder (Path A):** A management command `seed_bank_balances` reads
   ending balances from QuickBooks and writes them into `BankStatementBalance`. This
   makes sandbox iteration fast while keeping the core feature production-realistic.
3. **Balance check lives in the reconciliation engine:** `run_reconciliation()` will
   call a new helper `check_account_balances()` after the existing row-by-row matching.
4. **Flags reuse the existing `Flag` model:** Add `FlagType.BALANCE_RECONCILIATION` and a
   nullable `bank_statement_balance` FK so balance flags can be cleaned up idempotently
   by account/month without adding a generic `month` field to every flag.
5. **Matching by account name:** `Transaction.gl_account` already stores the QB account
   name, so the check sums transactions whose `gl_account` matches the `BankStatementBalance`
   account name.
6. **Tolerances:** Use a configurable amount tolerance (default $0.01) and a percentage
   threshold (optional future work) so trivial rounding differences do not create noise.

## Data model

### `BankStatementBalance` (`core/models.py`)

```text
realm_id         CharField(50)    indexed
qb_account_id    CharField(50)    indexed
account_name     CharField(200)   denormalized, human-readable
month            CharField(7)     YYYY-MM, validated
ending_balance   DecimalField(12,2)
source           CharField        choices: qb_api, manual, csv_upload, bank_feed
statement_date   DateField        usually last day of month
unique_together  (realm_id, qb_account_id, month)
```

### `Flag` changes

- Add `FlagType.BALANCE_RECONCILIATION` to the `FlagType` choices.
- Add nullable FK `bank_statement_balance` → `BankStatementBalance` (`CASCADE`).
  Used only for balance-reconciliation flags; both `transaction` and
  `bank_transaction` remain null for those flags.

## Sandbox auto-seed from QuickBooks

Add `core/quickbooks/client.py::fetch_account_ending_balances(qb_client, month)` that
uses the **TrialBalance** report as of the last day of the month. TrialBalance returns
ending balances per account, which is exactly the control we need.

If `TrialBalance` is unavailable or unparsable in the python-quickbooks library, fall
back to the existing `GeneralLedger` report and extract the ending total for each
`Bank` / `Other Current Asset` account.

Returns `{account_id: (name, ending_balance)}`.

New command `seed_bank_balances`:

```bash
python manage.py seed_bank_balances 2026-06 --realm-id <realm>
```

Options:
- `--realm-id` — scope to one realm; if omitted, seeds all connected realms.
- `--force` — overwrite existing `BankStatementBalance` rows for the month.

It creates `BankStatementBalance` rows with `source="qb_api"` for every cash-like
account (`QBAccount.account_type` in `{"Bank", "Other Current Asset"}`).

## Manual entry command (core feature)

New command `set_bank_balance`:

```bash
python manage.py set_bank_balance 2026-06 \
  --realm-id <realm> \
  --account-id <qb_account_id> \
  --balance -3621.93 \
  --name "Operating Checking"
```

Creates or updates a `BankStatementBalance` row with `source="manual"`.

Also register `BankStatementBalance` in Django admin so it can be edited through the UI.

## Reconciliation engine changes

In `core/reconciliation/engine.py`:

1. Add `check_account_balances(month, realm_id=None)`:
   - Load `BankStatementBalance` rows for the month/realm.
   - For each row:
     - Sum `Transaction.amount` where `realm_id=...`, `gl_account=account_name`,
       and `date` is in the month.
     - Compute difference vs `ending_balance`.
     - If absolute difference > `BALANCE_TOLERANCE` (default $0.01):
       - Delete existing `Flag` rows with `flag_type=BALANCE_RECONCILIATION` and
         `bank_statement_balance=row`.
       - Create a new flag with severity `HIGH` and a reason like:
         ```text
         Bank ending balance ($-3,621.93) for "Operating Checking" in 2026-06 does not match posted GL total ($-568.38); difference $-3,053.55.
         ```
   - Return dict with `balance_flags_created` and `accounts_checked`.

2. Call `check_account_balances()` inside `run_reconciliation()` after row-level
   matching, and include its counts in the returned summary dict.

3. Update `run_reconciliation` management command output to print balance-reconciliation
   counts.

## Files expected to change

- `core/models.py`
- `core/migrations/0005_bankstatementbalance_and_flag_balance_type.py`
- `core/admin.py`
- `core/reconciliation/engine.py`
- `core/management/commands/set_bank_balance.py` (new)
- `core/management/commands/seed_bank_balances.py` (new)
- `core/quickbooks/client.py`
- `core/tests/test_models.py`
- `core/tests/test_reconciliation.py` or `core/tests/test_management.py`
- `core/tests/test_quickbooks.py`
- `README.md`
- `docs/CURRENT_TASK.md`
- `docs/CHANGELOG.md`
- `docs/TODO.md`

## Test plan (TDD)

Per `AGENTS.md`, write failing tests first.

### Model tests
- `BankStatementBalance` unique-together on `(realm_id, qb_account_id, month)`.
- Same account id allowed in different realms.
- Admin registration.

### Manual command tests
- `set_bank_balance` creates a row with `source="manual"`.
- Re-running updates the same row.

### QB auto-seed tests (mocked)
- `seed_bank_balances` calls the QB report helper and creates rows with `source="qb_api"`.
- `--force` overwrites existing rows.
- Non-cash-like accounts are skipped.

### Balance reconciliation tests
- Exact match → no balance flag.
- Difference within $0.01 tolerance → no flag.
- Difference of $1.00 → one `BALANCE_RECONCILIATION` flag with severity `HIGH`.
- Missing `BankStatementBalance` for an account → no flag.
- Re-running is idempotent (old balance flag replaced, not duplicated).
- Realm scoping: a balance in realm-a does not create flags for realm-b.

## Expected commit sequence

1. `feat(models): add BankStatementBalance and BALANCE_RECONCILIATION flag type`
2. `feat(manual): add set_bank_balance management command`
3. `feat(qb): add seed_bank_balances command to auto-seed sandbox balances from QB`
4. `feat(reconcile): compare account ending balances to posted GL totals and flag gaps`
5. `docs: document bank balance reconciliation commands and feature`

## Open questions

1. Should the dashboard display stored bank balances? Not required for flagging, but
   useful. Defer to a follow-up if needed.
2. Should `seed_bank_balances` be invoked automatically during `sync_quickbooks`? For
   now keep it as a separate command to avoid surprising overwrites; can add a
   `--seed-balances` flag later.
3. Do we want a percentage tolerance in addition to the dollar tolerance? Keep it
   simple: dollar tolerance only for this build.