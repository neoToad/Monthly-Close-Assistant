# Implementation Plan: AI-Assisted Account Reconciliation & QuickBooks Fix Writes

**Status:** ✅ Complete — all core features implemented.

## Summary

All major features have been implemented:

- ✅ `AccountReconciliationState` model with status tracking and suggestion caching
- ✅ `core/agents/account_reconcile.py` — deterministic + optional LLM suggestion engine
- ✅ `core/services/qb_writes.py` — QuickBooks write helpers (`create_journal_entry`, `create_purchase`, `create_deposit`, `apply_suggestion`)
- ✅ Reconcile modal UI with suggestion preview and apply flow
- ✅ Management commands (`suggest_account_fixes`, `apply_account_fix`)
- ✅ Full test coverage (`test_agent_reconcile.py`, `test_qb_writes.py`, `test_reconcile_commands.py`)

---

## Remaining Items / Future Improvements

### Open questions to resolve

1. **Local Transaction creation after QB write** — Currently relies on user running `sync_quickbooks` again. Should we create local `Transaction` rows immediately after a QB write so the panel updates without an extra sync step?

2. **LLM reasoning display** — Should the modal show the LLM reasoning? Recommendation: yes, but only a one-sentence explanation per suggestion; full reasoning can go in a tooltip.

3. **Undo support** — Should we support undo? Recommendation: not for MVP. Instead, write an audit note to the `Flag` reason and let the user delete the QB object manually if needed.

### Potential enhancements

- **Unmatched GL row handling** — The deterministic suggestions describe unmatched GL rows in the prompt but never suggest them as writes. Consider adding flagging or suggestions for these.

- **Idempotency enforcement** — The plan mentions "idempotency key per suggestion id + month" but this is only partially implemented via `AccountReconciliationState.applied_suggestions`. Consider strengthening deduplication at the view/command layer.

- **Matched-but-different detection** — The agent detects matched rows with amount differences and includes them in the prompt, but no UI is built to display these differences in the modal.

### Documentation updates

- `README.md` — Document the AI-assisted account reconciliation workflow
- `docs/CHANGELOG.md` — Add entry for this feature (if not already done)
