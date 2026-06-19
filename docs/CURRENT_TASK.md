# CURRENT_TASK

## Stage

Executing `docs/plans/refactor_plan.md`.

## Current task

Step 1 — Audit (complete).

The full architectural audit is documented in `docs/plans/refactor_plan.md`. Findings cover module structure, business-logic drift into views, duplicated helpers (`_month_bounds`, `_prior_month`, `CASH_LIKE_ACCOUNT_TYPES`, posted-GL sums), inconsistent naming, missing type hints/docstrings, error-handling gaps, test-coverage holes, dead code, and best-practice opportunities.

No production code was changed in this step; the deliverable is the audit document itself.

## Next step

Step 2 — Refactor Plan execution, starting with the recommended sequence:

1. Dead code cleanup (2.7.A–F)
2. Centralize dates and constants (2.2.C)
3. Type hints and docstrings pass (2.4)
4. Extract `compute_posted_total` and grouped queries (2.1.B, 2.8.A)
5. Extract service layer for apply flow (2.1.A)
6. Move QB write helpers to `core/services/qb_writes.py` (2.1.C)
7. Centralize retry/backoff (2.5.A)
8. Add missing idempotency tests (2.6)
9. Package reorganization (2.2.A full target)
10. Migration squash (2.8.E)

## Branch

`feature/close-assistant-build`

## Latest commit

Added `docs/plans/refactor_plan.md` and audit findings; no code changes.
