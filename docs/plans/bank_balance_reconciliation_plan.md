# Implementation Plan: Bank Balance Reconciliation

**Status:** ✅ Complete — all core features implemented.

## Summary

All major features have been implemented:

- ✅ `BankStatementBalance` model with `source` choices and unique-together constraint
- ✅ `FlagType.BALANCE_RECONCILIATION` and `bank_statement_balance` FK on `Flag`
- ✅ `seed_bank_balances` command (uses `fetch_account_current_balances` from QB API)
- ✅ `set_bank_balance` command and dashboard view for manual entry
- ✅ Balance check integrated into `run_reconciliation()` via `check_account_balances()`
- ✅ `BankStatementBalance` registered in Django admin
- ✅ Bank balances displayed on dashboard with Reconcile buttons
- ✅ Full test coverage

---

## Remaining Items / Future Improvements

### Open questions to resolve

1. **CSV upload / bank feed source** — The `BankStatementBalance.Source` has `csv_upload` and `bank_feed` choices defined, but no implementation yet. Should we add support for uploading bank statement CSVs or integrating with a real bank feed?

2. **Percentage tolerance** — The plan mentions "a percentage threshold (optional future work)" in addition to the dollar tolerance. Should we add this for accounts with large balances where small percentage differences matter?

3. **Auto-seed during sync** — Should `seed_bank_balances` be invoked automatically during `sync_quickbooks`? Currently it's a separate command. The plan mentions potentially adding a `--seed-balances` flag.

### Potential enhancements

- **Statement date tracking** — The model has a `statement_date` field but it's not being used yet. Consider populating this when seeding from QB or entering manually.

- **Balance history display** — The dashboard shows current month balances. Should we add a historical view showing balance trends across months?

- **Multi-account rollup** — For companies with multiple cash accounts, should we show a consolidated "total cash" balance alongside individual account balances?