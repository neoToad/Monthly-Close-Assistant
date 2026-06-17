# Current Task

## Stage
Foundation (Prompts 1–3) — in progress.

## Current step
**Step 3 — QuickBooks OAuth + Data Pull** (active, TDD). Steps 1–2 are complete and
committed; see CHANGELOG.md.

## What I am actively working on
Implementing QuickBooks Online OAuth 2.0 + a `sync_quickbooks` management command,
test-first against **mocked** QuickBooks responses (no live sandbox credentials):
- OAuth **start** view (redirect to the Intuit authorize URL) + **callback** view
  (receive and store access/refresh tokens securely) + a **token-refresh** helper.
- `sync_quickbooks` command: authenticate with stored tokens, pull Purchase / Deposit /
  JournalEntry from the sandbox company, normalize each into `Transaction`, and skip
  records already present (match on `qb_transaction_id`).
- Reads QB_CLIENT_ID, QB_CLIENT_SECRET, QB_REDIRECT_URI, and the sandbox realm id from
  env.

## TDD status
- [ ] Write `core/tests/test_quickbooks.py` (normalization, skip-existing, refresh,
      token encryption) and `core/tests/test_views.py` (OAuth start/callback,
      `sync_quickbooks` command) — all mocked; confirm failures.
- [ ] Implement `core/quickbooks/client.py` service, `QBToken` storage, views, URLs,
      and the management command.
- [ ] Tests green (`python manage.py test`).

## Decisions / blockers
- DRY service abstraction `core/quickbooks/client.py` for OAuth + token refresh + data
  pull (suggested by the foundation prompt).
- Token storage: a `QBToken` model (singleton per realm) holding encrypted
  access/refresh tokens, realm_id, and access-token expiry — added via a new migration.
  Tokens encrypted at rest with Fernet keyed by `QB_TOKEN_ENCRYPTION_KEY` (env);
  plaintext fallback for dev with a clear warning. `cryptography` is already installed.
- intuit-oauth imports as `intuitlib.client.AuthClient` / `intuitlib.enums.Scopes`
  (see memory). AuthClient `environment` hardcoded to `sandbox` for now; QB_ENVIRONMENT
  is formalized in Prompt 4. Retry/backoff deferred to Prompt 5.
- Live sandbox pull NOT exercised (no credentials); noted in CHANGELOG and TODO.

## Next step
Finish Step 3 (tests green) → commit & push → Foundation stage complete; stop before
Prompt 4.