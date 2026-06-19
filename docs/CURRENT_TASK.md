# CURRENT_TASK

## Stage

Executing `docs/plans/refactor_plan.md` Steps 1–5.

## Current task

Step 2.7 — Dead code cleanup (sequence item 1 of 5) — **completed**.

All deletions confirmed safe; full core suite passes **268 tests** (down from 269 because the unused `RefreshTokensTests` class was removed along with the dead `refresh_tokens` function).

Changes made:
- Removed unused `refresh_tokens` function and its `RefreshTokensTests` in `core/tests/test_quickbooks.py`.
- Removed unused `_lookup_suggestion` from `core/quickbooks/writes.py`.
- Removed `--skip-reports` argument and help text from `sync_quickbooks` command.
- Removed unused `DATE_TOLERANCE_DAYS` import from `core/agent/reconcile.py`.
- Removed unused `Optional` import from `core/quickbooks/writes.py`.
- Clarified the no-op `if not force: pass` block in `seed_bank_balances` as a comment.
- Pruned now-unused `django.utils.timezone` and `datetime.timedelta` imports in `core/quickbooks/client.py`.

## Next task

Step 2.2.C — Centralize dates and constants (sequence item 2 of 5).

Create `core/common/dates.py` and `core/common/constants.py`, move duplicated helpers and thresholds, update imports across engines.

## Branch

`feature/close-assistant-build`

## Latest commit

`87e4326` — docs(plans): add Step 1 audit for refactor plan.
