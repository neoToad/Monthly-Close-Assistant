# TODO

Items deferred to later stages (per the prompt sequence). Moved here from the running
plan so the current step stays uncluttered.

## Prompt 4 — QuickBooks Secrets & Environment Config
- Add documented comments for `QB_ENVIRONMENT` (sandbox|production) and
  `QB_TOKEN_REFRESH_BUFFER_MINUTES` to `.env.example` (the QB_CLIENT_ID / SECRET /
  REDIRECT_URI / SANDBOX_COMPANY_ID / TOKEN_ENCRYPTION_KEY vars were already added
  in Prompt 3).
- Make the QuickBooks AuthClient `environment` env-driven (currently hardcoded to
  `sandbox` in `core/quickbooks/client.py`) and point at the correct API base URL.

## Prompt 5 — Error Handling & Edge Cases (QuickBooks Sync)
- Catch mid-sync access-token-expiry → refresh + retry once before failing loudly.
  (`QBToken.is_access_token_expired()` already exists; wire it into the sync path.)
- Rate-limiting / timeout → exponential backoff up to 3 attempts, then clear error.
- Ensure all failures produce clear log output (no silent crashes).
- Persist refreshed tokens back to `QBToken` after a refresh (currently
  `refresh_tokens` returns a dict but does not store; `store_tokens` does).

## Prompt 6+ — Later stages
- Fake bank feed generator, reconciliation, anomaly detection, idempotency, agent
  layer, demo seed, Celery, HTMX dashboard, auth, Docker, CI/CD, deploy, README.

## Open questions / future layout
- Django project currently lives at repo root (per the Foundation prompt). If a later
  Docker stage expects a `backend/` subdirectory layout (per AGENTS.md Docker test
  context), reconcile then — either set the container WORKDIR to the repo root or
  reorganize the project into `backend/`.

## Live QuickBooks sandbox pull
- Not exercised against a live sandbox in Prompt 3 (no sandbox credentials available).
  OAuth flow and `sync_quickbooks` are unit-tested against mocked QuickBooks responses.
  Revisit once sandbox credentials are supplied.