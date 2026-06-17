# Current Task

## Stage
**Foundation (Prompts 1–3) — COMPLETE.** The next stage begins at Prompt 4.

## What was just finished
Step 3 — QuickBooks Online OAuth 2.0 + `sync_quickbooks` (TDD, mocked). Committed and
pushed. See CHANGELOG.md "Step 3".

- OAuth start + callback views (`/quickbooks/oauth/start/`,
  `/quickbooks/oauth/callback/`) wired via `core/urls.py`.
- `core/quickbooks/client.py` (OAuth, token-refresh, pull, normalize, sync) +
  `core/quickbooks/tokens.py` (Fernet encryption-at-rest + `QBToken` persistence).
- `QBToken` model + migration `core.0002_qbtoken`; admin hides token fields.
- `sync_quickbooks` management command (idempotent on `qb_transaction_id`).
- Tests: `core/tests/test_quickbooks.py` + `core/tests/test_views.py`; full suite
  **46 green**.

## Status
- [x] Prompt 1 — scaffold (committed `5273be9`).
- [x] Prompt 2 — models/migrations/admin (committed `206f47a`).
- [x] Prompt 3 — QuickBooks OAuth + sync (committed this step).
- [x] Tracking files updated; branch pushed.

## Decision / blocker notes (carried into Prompt 4+)
- Live sandbox pull was **not** exercised (no credentials); mocked tests only.
- Intuit `environment` hardcoded `"sandbox"` → `QB_ENVIRONMENT` configurable in P4.
- No retry/backoff → P5.
- See `docs/TODO.md` for the open follow-ups.

## Next step
**Stop here** — per the foundation prompt, do not begin Prompt 4 and do not open a PR.