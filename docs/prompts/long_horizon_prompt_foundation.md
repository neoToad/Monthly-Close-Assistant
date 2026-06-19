# Monthly Close Assistant — Long Horizon Prompt: Build (Prompts 4–18)

You are continuing the Monthly Close Assistant, an AI-assisted reconciliation and
close-summary tool. The foundation stage (prompts 1–3) is already complete on
`feature/close-assistant-build`: the Django project and `core` app are scaffolded,
the Transaction / BankTransaction / Flag / CloseSummary schema is in Postgres, and
QuickBooks OAuth 2.0 plus the `sync_quickbooks` management command are implemented
and tested.

Start by reading these documents:

- [Monthly_Close_Assistant_CLI_Agent_Prompts_Full.md](../Monthly_Close_Assistant_CLI_Agent_Prompts_Full.md) — the full implementation spec (prompts 1–18, plus stretch prompts)
- [Monthly_Close_Assistant_Project.md](../Monthly_Close_Assistant_Project.md) — the project plan (architecture, tech stack, and the "why")
- [AGENTS.md](../../AGENTS.md) — the repo's working rules (TDD workflow, commit format, tracking files)

The prompts document is your implementation spec. For this stage, execute **prompts
4 through 18, in order, then stop**. Do not start a stretch prompt until prompts
4–18 are fully committed and pushed.

Track each step's completion in `docs/CURRENT_TASK.md` and `docs/CHANGELOG.md`
(see below) — do not edit the spec document itself.

---

## Scope (what this stage builds)

Continue from the completed foundation. Each prompt below maps to the matching
numbered prompt in the full spec.

- **Prompt 4 — QuickBooks Secrets & Environment Config:** harden `.env.example`
  with documented entries for `QB_CLIENT_ID`, `QB_CLIENT_SECRET`, `QB_REDIRECT_URI`,
  `QB_SANDBOX_COMPANY_ID`, `QB_ENVIRONMENT`, and `QB_TOKEN_REFRESH_BUFFER_MINUTES`;
  make the OAuth client read `QB_ENVIRONMENT` and point at the correct QuickBooks
  API base URL.
- **Prompt 5 — Error Handling & Edge Cases (QuickBooks Sync):** catch mid-sync
  token expiry, refresh once and retry, then fail loudly with clear logs; add
  exponential backoff (up to 3 attempts) for rate limiting and timeout.
- **Prompt 6 — Fake Bank Feed Generator:** a `generate_bank_feed` management
  command that reads a month's Transaction records and produces BankTransaction
  records with configurable rates for drops, duplicates, amount shifts, date shifts,
  and extra bank-only transactions. Use Pandas and print a discrepancy summary.
- **Prompt 7 — Reconciliation Logic:** a Pandas-based reconciliation module that
  matches Transaction and BankTransaction records for a month (vendor, amount within
  $0.01, date within 1 day) and creates `Flag` records for mismatches or one-sided
  entries. Wire it into a `run_reconciliation` management command.
- **Prompt 8 — Anomaly Detection:** rule-based anomaly checks on a month's
  Transaction data: vendor amount > 2σ from historical average, duplicates within
  a 7-day window, new vendors, and categories with > 200% month-over-month change.
  Create `Flag` records with `flag_type="anomaly"`. Integrate into
  `run_reconciliation` so it runs both reconciliation and anomaly checks.
- **Prompt 9 — Idempotency for Reconciliation & Sync:** ensure re-running
  `run_reconciliation` does not duplicate `Flag` records; keep `sync_quickbooks`
  idempotent via `qb_transaction_id`; make `generate_bank_feed` prompt or require
  `--force` if bank data already exists for the month.
- **Prompt 10 — Agent Layer:** install and configure an agent framework (CrewAI,
  or LangGraph + LangChain-Anthropic) and build a step that reads open `Flag`
  records plus monthly category totals / prior-month comparison, then drafts a
  plain-language close summary. Save the result as a `CloseSummary` with
  `status="draft"`. Wire it into a `generate_close_summary` management command.
- **Prompt 11 — Demo Data Seeding:** a single `seed_demo_data` management command
  that creates demo Transactions with Faker, runs `generate_bank_feed`, runs
  reconciliation/anomaly detection, and runs the agent summary generator — all
  safe to run repeatedly without duplicates.
- **Prompt 12 — Celery Scheduled Sync:** install Celery and Redis, configure Celery
  with Django, and add a nightly scheduled task that runs `sync_quickbooks`.
- **Prompt 13 — HTMX Review Dashboard:** build `/dashboard/` with a month selector
  (`hx-get`), a table of open flags with Approve/Reject buttons (`hx-post` partial
  row swap), and a CloseSummary draft section with a Mark Reviewed action and
  reviewer notes field.
- **Prompt 14 — Dashboard Access Control:** require login on `/dashboard/` and all
  flag / close-summary action views using Django's built-in auth (`@login_required`).
- **Prompt 15 — Dockerize:** add a `Dockerfile` and `docker-compose.yml` with
  services for Django, PostgreSQL, Redis, and a Celery worker; migrate on startup;
  reference `.env.example`.
- **Prompt 16 — CI/CD:** a GitHub Actions workflow that runs the test suite on push
  to `main` and, if tests pass, triggers a Railway deploy using GitHub secrets.
- **Prompt 17 — Deploy:** deploy the Dockerized project to Railway, provision
  PostgreSQL and Redis add-ons, and configure environment variables. If Railway
  credentials are not available, still complete the Docker/CI setup and note in
  `CHANGELOG.md` that live deploy was not exercised.
- **Prompt 18 — README:** write a `README.md` covering what the project does, the
  data-flow architecture, setup (env vars, migrations, `seed_demo_data`), manual
  pipeline order, and Docker usage.

---

## Git Setup

1. Stay on the existing `feature/close-assistant-build` branch. If it has been
   deleted or you are elsewhere, recreate it from `main` and check it out.
2. After completing **each** numbered prompt (4 through 18), stage all new and
   modified files, commit, and push.
3. Use the repo's commit format from `AGENTS.md`:
   ```
   <type>(<scope>): <summary>
   - <what changed>
   ```
   Types: `feat` `fix` `test` `refactor` `chore` `docs`. Reference the step in
   the summary or scope, e.g.
   `feat(core): step 4 — QuickBooks env config, sandbox/production switch`.

---

## Environment Assumptions

- Python 3.11+
- PostgreSQL running locally **until Docker is added in Prompt 15**; after that,
  use the Docker-based test context from `AGENTS.md` (`docker compose exec backend
  python manage.py test ...`).
- Redis running locally for Prompts 12–15, then via Docker compose.
- Repo root is the working directory; all commands run there unless noted.
- Pandas, NumPy, Faker, Celery, Redis, CrewAI/LangGraph, and any other prompt-specific
  dependencies are added to `requirements.txt` as each prompt is reached.
- For prompts that can be unit-tested without live credentials (QuickBooks OAuth,
  sync, bank feed, reconciliation, anomaly detection, agent summary, demo seed):
  write tests against mocked or generated data and note in `CHANGELOG.md` if the
  live integration was not exercised.
- For Prompt 17 (Railway deploy): if live Railway credentials/project access is
  unavailable, still complete the Dockerfile, compose setup, and CI workflow in
  Prompts 15–16, then document in `CHANGELOG.md` that live deployment was not
  performed.

---

## Testing (TDD — from AGENTS.md)

Testing is part of every step, per the `AGENTS.md` TDD workflow:

1. Write failing tests first
2. Confirm they fail for the right reasons
3. Write the minimum code to make them pass
4. Refactor if needed, keeping tests green

- Django tests live in the `core` app, split into `test_models.py`, `test_views.py`,
  `test_management.py`, and any additional modules as appropriate.
- Before Prompt 15, run tests against the local Postgres: `python manage.py test`.
- After Prompt 15, run tests inside the backend container per `AGENTS.md`.
- No commit while tests are failing. Never write implementation before tests.

---

## Tracking Files

Maintain `docs/CURRENT_TASK.md`, `docs/CHANGELOG.md`, and `docs/TODO.md` per
`AGENTS.md`.

At the start of this stage, set `docs/CURRENT_TASK.md` to Prompt 4. Overwrite it
completely each time you move to a new prompt so it always reflects the live
state.

---

## Refactoring and Improvements

As you build, use your judgment to refactor and add sensible improvements beyond
what the spec explicitly describes. Good candidates include: service abstractions
(e.g. `core/reconciliation/engine.py`, `core/anomaly/rules.py`, `core/agent/summary.py`),
validation helpers, logging, type hints, docstrings, HTMX partial templates,
admin usability improvements, and defensive handling for empty datasets or missing
fields. You do not need to ask permission — just do them and note them in
`CHANGELOG.md` under the relevant entry.

---

## Rules

- Never write implementation before tests (TDD).
- Complete, commit, and push each step (4 through 18) before starting the next.
- If a step produces errors, fix them before moving on. Do not proceed on broken code.
- Do not batch multiple steps into one commit — one commit per prompt.
- No commit message if tests are failing.
- Always commit `CURRENT_TASK.md`, `CHANGELOG.md`, and `TODO.md` alongside the
  step's code files.
- Never commit secrets, keys, or credentials — keep them in `.env` (gitignored) and
  document them in `.env.example`.
- All markdown files live in the `docs/` folder.

---

## When All Eighteen Steps Are Complete

- Update `CURRENT_TASK.md` to reflect that prompts 1–18 are finished.
- Confirm all eighteen commits are on `feature/close-assistant-build` with correct
  messages.
- List any files not committed.
- Print a summary of what was built, all improvements made beyond the spec, and
  any deviations or un-exercised live integrations.
- Push the branch to remote.
- Do not open a pull request, and do not start a stretch prompt, unless the user
  explicitly asks — stop here.
