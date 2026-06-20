# Plan: Add Five High-Value QuickBooks Data Sources

Status: This plan has been pared down — implemented items were removed. Remaining content below lists open decisions and next steps.

Completed (summary)

- QBAccount model + migration implemented
- SourceType extended and SYNC_OBJECTS updated to include Bill, BillPayment, VendorCredit
- normalize_record updated to handle new QuickBooks record types
- sync_accounts implemented and wired into sync_quickbooks
- fetch_general_ledger_summary implemented and integrated into the close summary path
- generate_bank_feed supports `--cash-only` and filters cash-like sources
- Tests added for normalization, account sync, GL summary, and bank-feed filtering
- README and CHANGELOG updated

Remaining / open decisions

1. Sign convention for BillPayment and VendorCredit: confirm whether to keep QBO's positive TotalAmt and interpret by source_type (recommended) or normalize to signed values.
2. Bank feed default scope: decide whether to change default to cash-only (currently opt-in via `--cash-only`).
3. Account validation: decide if `Transaction.gl_account` should be validated against `QBAccount` (warn or fail on mismatch).
4. GL report granularity: decide whether to ingest per-transaction report rows (introduce `QBReportRow`) or keep month-level totals only.

Next steps

- Resolve the open decisions above and create concise issues/PRs for each.
- If desired, implement account-validation and/or change the bank-feed default in follow-up commits.
- Update docs/TODO.md and docs/CURRENT_TASK.md to reflect the chosen next work item.

(If further pruning is wanted — for example converting this file into a short checklist or moving remaining items into docs/TODO.md — say which format to keep.)