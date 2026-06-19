# CURRENT_TASK

## Stage

Implementing `docs/plans/add_quickbooks_data_sources_plan.md`.

## Current step

**Step 5 — GeneralLedger report cross-check in close summary**
- Add `fetch_general_ledger_summary(qb_client, month, qb_token=None)` to
  `core/quickbooks/client.py` using `qb_client.get_report("GeneralLedger")`.
- Call it from `core/agent/summary.py::gather_inputs()` and include `qb_gl_totals`.
- Update `build_prompt()` and `_deterministic_summary()` to mention QB GL totals.
- Write failing tests first, then implement.

## Branch

`feature/close-assistant-build`

## Next step

Commit `feat(agent): cross-check close summary against QuickBooks GeneralLedger`, then begin Step 6.
