# Monthly Close Assistant — Long Horizon Prompt: Foundation (Prompts 1–3)

You are building the Monthly Close Assistant, an AI-assisted reconciliation and
close-summary tool. This prompt drives the foundation stage of the build. Start
by reading these documents:

- [Monthly_Close_Assistant_CLI_Agent_Prompts_Full.md](../Monthly_Close_Assistant_CLI_Agent_Prompts_Full.md) — your implementation spec
- [Monthly_Close_Assistant_Project.md](../Monthly_Close_Assistant_Project.md) — the project plan (architecture, tech stack, and the "why")
- [AGENTS.md](../../AGENTS.md) — the repo's working rules (TDD workflow, commit format, tracking files)

The prompts document is your implementation spec — but for this stage, execute
**only prompts 1, 2, and 3**, in order, then stop. Do not start prompt 4 or
beyond; those belong to later stages and depend on the foundation you build here.

Track each step's completion in CURRENT_TASK.md and CHANGELOG.md (see below) — do
not edit the spec document itself.

---

## Scope (what this stage builds)

- **Prompt 1 — Project Scaffolding:** a Django project `close_assistant` with a
  `core` app inside it, PostgreSQL configured from environment variables
  (DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT) loaded via python-decouple,
  django-htmx installed and wired into a `base.html` template, and a
  `.env.example` listing every required variable. No real `.env` is committed.
- **Prompt 2 — Postgres Schema:** Django models for `Transaction`,
  `BankTransaction`, `Flag`, and `CloseSummary` in the `core` app (field shapes
  per the spec), migrations written and applied, and all four models registered
  in Django admin.
- **Prompt 3 — QuickBooks OAuth + Data Pull:** QuickBooks Online OAuth 2.0 using
  python-quickbooks and intuit-oauth — a view to start the flow, a callback view
  to receive and store access/refresh tokens securely, and a token-refresh
  helper — reading QB_CLIENT_ID, QB_CLIENT_SECRET, QB_REDIRECT_URI, and the
  sandbox company realm ID from environment variables. Then a
  `sync_quickbooks` management command that authenticates with the stored
  tokens, pulls Purchase, Deposit, and JournalEntry records from the QuickBooks
  sandbox company, normalizes each into the `Transaction` model, and skips
  records that already exist (match on `qb_transaction_id`). The fuller
  QuickBooks env config (QB_ENVIRONMENT, refresh buffer, etc.) is formalized in
  a later prompt — for now, read only what prompt 3 requires.

---

## Git Setup (do this first)

1. If a branch named `feature/close-assistant-build` does not exist, create it
   from `main` and check it out.
2. After completing each numbered prompt (1, 2, 3), stage all new and modified
   files, commit, and push.
3. Use the repo's commit format from AGENTS.md:
   ```
   <type>(<scope>): <summary>
   - <what changed>
   ```
   Types: `feat` `fix` `test` `refactor` `chore` `docs`. Reference the step in
   the summary or scope, e.g. `feat(core): step 1 — Django project scaffold with Postgres + HTMX`.

---

## Environment Assumptions

- Python 3.11+
- PostgreSQL running locally; the Django app connects via DB_NAME, DB_USER,
  DB_PASSWORD, DB_HOST (e.g. `localhost`), DB_PORT (e.g. `5432`)
- Repo root is the working directory; all commands run there unless noted
- python-decouple, django-htmx, python-quickbooks, and intuit-oauth are
  installed via pip into the project's virtualenv
- For prompt 3's end-to-end test: a QuickBooks Online **sandbox** app registered
  at developer.intuit.com, supplying QB_CLIENT_ID, QB_CLIENT_SECRET,
  QB_REDIRECT_URI, and the sandbox company realm ID. If live sandbox credentials
  are not available, still implement and unit-test the OAuth flow and sync
  command against mocked QuickBooks responses, and note in CHANGELOG.md that the
  live pull was not exercised against the sandbox.

---

## Testing (TDD — from AGENTS.md)

Testing is not a separate prompt; it is part of every step, per the AGENTS.md
TDD workflow:

1. Write failing tests first
2. Confirm they fail for the right reasons
3. Write the minimum code to make them pass
4. Refactor if needed, keeping tests green

- Django tests live in the `core` app, split into `test_models.py`,
  `test_views.py`, and `test_serializers.py` as appropriate.
- Run tests for this stage locally against the local Postgres:
  `python manage.py test`. (The Docker-based test context in AGENTS.md applies
  once Docker is added in a later stage; this stage has no Docker yet.)
- No commit while tests are failing. Never write implementation before tests.

---

## Tracking Files

Maintain docs/CURRENT_TASK.md, docs/CHANGELOG.md, and docs/TODO.md per AGENTS.md
---

## Refactoring and Improvements

As you build, use your judgment to refactor and add sensible improvements beyond
what the spec explicitly describes. Good candidates include: better error
messages, type hints, docstrings, input validation, DRY service abstractions
(e.g. a `core/quickbooks/client.py` for the OAuth + sync logic), defensive
handling of edge cases (empty result sets, missing fields, expired tokens), or
small UX touches in `base.html`. You do not need to ask permission for these —
just do them and note them in CHANGELOG.md under the relevant entry.

---

## Rules

- Never write implementation before tests (TDD).
- Complete, commit, and push each step (1, 2, 3) before starting the next.
- If a step produces errors, fix them before moving on. Do not proceed on broken code.
- Do not batch multiple steps into one commit — one commit per prompt.
- No commit message if tests are failing.
- Always commit CURRENT_TASK.md, CHANGELOG.md, and TODO.md alongside the step's code files.
- Never commit secrets, keys, or credentials — keep them in `.env` (gitignored) and document them in `.env.example`.
- All markdown files live in the `docs/` folder.

---

## When All Three Steps Are Complete

- Update CURRENT_TASK.md to reflect that the Foundation stage (prompts 1–3) is
  finished and that the build continues at prompt 4.
- Confirm all three commits are on `feature/close-assistant-build` with correct
  messages.
- List any files not committed.
- Print a summary of what was built, all improvements made beyond the spec, and
  any deviations.
- Push the branch to remote.
- Do not open a pull request, and do not begin prompt 4 — stop here.