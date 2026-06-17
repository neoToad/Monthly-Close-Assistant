# TODO

Items deferred to later stages (per the prompt sequence). Moved here from the running
plan so the current step stays uncluttered.

## Prompt 4 — QuickBooks Secrets & Environment Config
- Extend `.env.example` with documented comments for QB_CLIENT_ID, QB_CLIENT_SECRET,
  QB_REDIRECT_URI, QB_SANDBOX_COMPANY_ID, QB_ENVIRONMENT (sandbox|production), and
  QB_TOKEN_REFRESH_BUFFER_MINUTES.
- Make the QuickBooks AuthClient `environment` env-driven (currently hardcoded to
  `sandbox` in `core/quickbooks/client.py`) and point at the correct API base URL.

## Prompt 5 — Error Handling & Edge Cases (QuickBooks Sync)
- Catch mid-sync access-token-expiry → refresh + retry once before failing loudly.
- Rate-limiting / timeout → exponential backoff up to 3 attempts, then clear error.
- Ensure all failures produce clear log output (no silent crashes).

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