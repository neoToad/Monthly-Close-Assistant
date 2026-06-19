# Implementation Plan: QuickBooks Transaction Editor

**Status:** Draft — awaiting approval.

## Goal

Add a focused, safe "QuickBooks Transaction Editor" to the Monthly Close Assistant.
The editor lets reviewers open a single existing QuickBooks transaction from a
reconciliation flag, edit a controlled set of fields, preview the change, and write
it back to QuickBooks. It is designed for the narrow case where the assistant's
adjusting-entry approach is not enough and the original transaction itself is wrong
(e.g., wrong amount, wrong account, wrong date, missing memo).

This is **not** a general ledger replacement. It intentionally supports only the
fields that reconciliation flags commonly need to fix, and it leaves a full audit
trail in the local `Flag` and `Transaction` records.

## Design decisions

1. **Scope to one transaction at a time.** The editor opens from an existing flag or
   from a transaction row. It does not bulk-edit.
2. **Only edit records the local DB already knows about.** The editor reads the
   existing local `Transaction` and the corresponding python-quickbooks object. This
   keeps account-name/vendor/category resolution simple and avoids partial edits.
3. **Controlled field list.** Allow editing only:
   - `TxnDate`
   - `TotalAmt` / line `Amount` (with line-level split support for JournalEntry)
   - `EntityRef` (vendor/payee name)
   - `AccountRef` / line account (via local `QBAccount` lookup)
   - `PrivateNote` / memo
   - Optional: `DocNumber`, `DepartmentRef`, `LocationRef` if available
   Higher-risk fields (tax, currency, exchange rates, linked transactions, item-based
   line items) are out of scope for the first version.
4. **No deletions, no creates in the editor.** The editor only updates existing
   objects. New adjusting entries continue to flow through the reconciliation agent.
5. **Same confirmation safety model as reconciliation writes.** The editor must
   support a dry-run preview, require an explicit confirmation token before calling
   QuickBooks, show a sandbox/production badge, and audit what was changed.
6. **Audit everything locally.** After a successful QB update, write:
   - A `Flag` note or audit JSON on the originating flag describing the change.
   - A history entry (new model or appended JSON) on the local `Transaction` so the
     original values can be reconstructed.
7. **Require active QB token and realm scoping.** Like `reconcile_account_apply`,
   the editor requires a connected QuickBooks realm and builds a fresh QB client.

## User-facing flow

### Entry points

- **Flag row action:** An "Edit in QuickBooks" button on open reconciliation flags
  that have a linked `Transaction`.
- **Transaction detail view:** A read-only detail page for any `Transaction` with an
  "Edit in QuickBooks" button when the record is editable.

### Editor modal / page

The editor opens in a modal or dedicated page showing:

- **Header:** transaction type, QuickBooks id, environment badge, and a warning that
  the change will be written to QuickBooks.
- **Read-only context:**
  - Current local values.
  - Associated `BankTransaction` rows (if any).
  - Open flags that reference this transaction.
- **Editable form:**
  - Date (`TxnDate`)
  - Vendor / payee (`EntityRef` name)
  - Total amount
  - GL account (`AccountRef` or line `AccountRef`, dropdown from `QBAccount`)
  - Memo (`PrivateNote`)
  - For `JournalEntry`: a line editor showing debit/credit lines and accounts.
- **Preview button:** shows the exact python-quickbooks object diff before writing.
- **Apply button:** confirms and writes to QuickBooks.

### Preview → confirm → execute

1. User edits fields and clicks **Preview changes**.
2. Backend returns a diff view:
   - Original vs. new `TxnDate`
   - Original vs. new `TotalAmt`
   - Original vs. new vendor
   - Original vs. new account
   - Original vs. new memo
3. User clicks **Update QuickBooks**.
4. Backend calls the appropriate `python-quickbooks` `.save()`. It then calls
   `qb_client.sync_transactions()` or a single-record sync helper to refresh the
   local `Transaction` row.
5. Backend re-runs `run_reconciliation(month, realm_id)` for the affected month
   and refreshes the relevant dashboard partial (flag table and/or bank balances).

## Data model changes

### New: `TransactionEditHistory`

Track every edit so the original transaction state can be reconstructed.

```text
id                AutoField
company           FK → QuickBooksCompany   CASCADE
realm_id          CharField(50)
transaction       FK → Transaction          CASCADE  (the local row)
qb_transaction_id CharField(100)
field_name        CharField(50)             e.g. "TxnDate", "TotalAmt", "AccountRef"
old_value         TextField                 JSON or plain text
new_value         TextField                 JSON or plain text
edited_by         FK → User                 nullable
edited_at         DateTimeField             auto_now_add
qb_write_success    BooleanField              default=True
qb_object_json      TextField                 optional snapshot of the QB object
```

This table is append-only. One edit produces one row per changed field.

### `Flag` additions (re-use existing `notes`)

When an edit originates from a flag, append an audit note:

```text
Updated QuickBooks via transaction editor: changed TotalAmt from $100.00 to $102.50,
AccountRef from "5000 - Supplies" to "5200 - Software". QB object id: QB-1.
```

If the existing `notes` field is not enough, extend it with an optional
`audit_json` JSONField later.

## Backend design

### New module: `core/quickbooks/updates.py`

Thin wrappers around python-quickbooks object updates. Each function reads the
existing QB object, applies the allowed edits, calls `.save(qb=qb_client)`, and
returns the updated object id plus a diff dict.

```text
update_quickbooks_transaction(
    qb_client: QuickBooks,
    transaction: Transaction,
    edits: dict,
    realm_id: str,
) -> dict
```

`edits` shape:

```json
{
  "TxnDate": "2026-06-15",
  "TotalAmt": "102.50",
  "EntityRef": "Acme Corp",
  "AccountRef": "5200 - Software",
  "PrivateNote": "Corrected category"
}
```

Dispatcher per source type:

```text
_update_purchase(qb_client, qb_obj, edits, account_refs)
_update_deposit(qb_client, qb_obj, edits, account_refs)
_update_journal_entry(qb_client, qb_obj, edits, account_refs)
_update_bill(qb_client, qb_obj, edits, account_refs)
_update_bill_payment(qb_client, qb_obj, edits, account_refs)
_update_vendor_credit(qb_client, qb_obj, edits, account_refs)
```

Each helper:
- Loads the QB object by id with `Purchase.get(...)`, `Deposit.get(...)`, etc.
- Applies only the allowed fields.
- Resolves account/vendor names to `Ref` objects using `QBAccount` and cached
  vendor lookups (or a new `QBVendor` model if needed).
- Calls `.save(qb=qb_client)`.
- Returns `{"object_type": "Purchase", "id": "QB-1", "diff": {...}}`.

### Fetch helper: `core/quickbooks/client.py`

Add `fetch_quickbooks_transaction(qb_client, source_type, qb_transaction_id)` to
retrieve a single QB object by id for preview. It returns a `SimpleNamespace` or
python-quickbooks object.

### New view: `edit_quickbooks_transaction`

Three-step POST/GET endpoint:

1. **GET `dashboard/transaction/<int:transaction_id>/edit/`**
   - Renders the editor form with current local values and a dropdown of editable
     `QBAccount` options.
2. **POST `dashboard/transaction/<int:transaction_id>/edit/preview/`**
   - Accepts form fields, builds the diff against the live QB object, and returns
     the preview HTML.
3. **POST `dashboard/transaction/<int:transaction_id>/edit/apply/`**
   - Requires `confirm=true` (or `dry_run=false`) and `reason`.
   - Calls `update_quickbooks_transaction`.
   - Syncs the single updated record back to the local `Transaction`.
   - Creates `TransactionEditHistory` rows for each changed field.
   - Updates the originating `Flag.notes` if the editor was opened from a flag.
   - Re-runs reconciliation for the month.
   - Returns the updated dashboard partial.

### New management command: `edit_quickbooks_transaction`

```bash
python manage.py edit_quickbooks_transaction \
  --realm-id <id> \
  --qb-transaction-id <id> \
  --field TotalAmt \
  --value 102.50 \
  --reason "Bank showed $102.50"
```

Useful for automation and advanced CLI flows. Supports `--dry-run` (default true)
and `--apply`.

## UI files

- `core/templates/core/transaction_editor_modal.html` — editor shell with form and diff.
- `core/templates/core/transaction_editor_preview.html` — preview of changes.
- `core/templates/core/flag_row.html` — add "Edit in QuickBooks" button for eligible flags.
- `core/templates/core/transaction_detail.html` — optional read-only detail view.
- Update `core/static/css/tokens.css` for editor form and diff styling.

## Files expected to change

- `core/models.py` — add `TransactionEditHistory`.
- `core/migrations/` — new migration for `TransactionEditHistory`.
- `core/quickbooks/updates.py` — new.
- `core/quickbooks/client.py` — add `fetch_quickbooks_transaction`.
- `core/views.py` — add `edit_quickbooks_transaction`, `edit_quickbooks_transaction_preview`,
  `edit_quickbooks_transaction_apply`.
- `core/urls.py` — add editor endpoints.
- `core/management/commands/edit_quickbooks_transaction.py` — new.
- `core/templates/core/flag_row.html` — add edit button.
- `core/templates/core/transaction_editor_modal.html` — new.
- `core/templates/core/transaction_editor_preview.html` — new.
- `core/tests/test_qb_updates.py` — new.
- `core/tests/test_views.py` — add editor view tests.
- `core/tests/test_management.py` — add command tests.
- `README.md` — document the editor and safety model.
- `docs/CURRENT_TASK.md`.
- `docs/CHANGELOG.md`.
- `docs/TODO.md`.

## Test plan (TDD)

### Model tests

- `TransactionEditHistory` stores old/new values per field.
- `TransactionEditHistory` links to `Transaction` and `QuickBooksCompany`.

### QB update tests (mocked)

- `update_quickbooks_transaction` dispatches to the right source-type helper.
- Purchase amount and account updates produce the expected python-quickbooks object.
- JournalEntry line updates preserve balanced debits/credits.
- Unknown account name fails fast with a clear error.
- Missing QB object returns a graceful error.

### View tests

- GET editor returns the form with current values and `QBAccount` dropdown.
- Preview endpoint returns a diff without touching QuickBooks.
- Apply endpoint writes to QB, records history, and updates the dashboard.
- Apply without `confirm=true` is rejected.
- Apply without active QB token shows a "connect QuickBooks" notice.

### Command tests

- CLI dry-run prints the diff and does not call QB.
- CLI `--apply` writes to QB and records history.

## Expected commit sequence

1. `feat(models): add TransactionEditHistory for QB edit audit trail`
2. `feat(qb): add fetch and update helpers for existing QB transactions`
3. `feat(ui): add transaction editor modal and preview`
4. `feat(views): execute confirmed QB transaction edits and refresh dashboard`
5. `feat(cli): add edit_quickbooks_transaction management command`
6. `docs: document transaction editor and safety model`

## Open questions

1. Should the editor support line-level edits for `Purchase`/`Deposit`, or only the
   top-level `AccountRef`/`TotalAmt`? **Recommendation:** top-level only for MVP;
   line-level stays read-only.
2. How should vendor name changes resolve to `EntityRef`? **Recommendation:** use
   a cached `QBVendor` lookup if we add vendor sync, otherwise allow free text and
   warn if the vendor is not found in QuickBooks.
3. Should the editor auto-create a reversing/offsetting entry when the amount
   change is large? **Recommendation:** no — the reconciliation agent handles
   gaps; the editor only corrects the original transaction.
4. Should the editor be available for `Bill`/`BillPayment`/`VendorCredit`?
   **Recommendation:** yes, but only the same safe field set (date, amount, vendor,
   account, memo).
5. Should we sync the whole month after an edit or just the single record?
   **Recommendation:** single-record sync helper for speed, then run
   `run_reconciliation` to refresh flags.

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Partial update corrupts a QB transaction | Only allow a small, well-tested set of fields; preview every change. |
| Account/vendor lookup mismatch | Fail fast before `.save()`; show dropdowns populated from synced `QBAccount`. |
| Unintentional production edit | Environment badge + explicit confirmation token; dry-run by default. |
| Loss of original value history | Append-only `TransactionEditHistory` rows store old/new per field. |
| Concurrent edits from QB UI and assistant | Sync the record immediately after save; reconciliation flags will reflect the latest state. |
| Currency / multi-currency complexity | Out of scope for MVP; block edits on non-USD realms or show a warning. |
