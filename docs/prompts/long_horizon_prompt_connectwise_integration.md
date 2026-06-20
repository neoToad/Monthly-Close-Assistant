# Monthly Close Assistant — Long Horizon Prompt: ConnectWise Integration (Mock/Test)

You are continuing the Monthly Close Assistant on the existing `feature/close-assistant-build` branch. The backend refactoring is complete, the dashboard exists, and the bank reconciliation flow is functional. This prompt implements the mock/test ConnectWise integration described in `docs/plans/connectwise_integration_plan.md`.

Start by reading these documents:

- [AGENTS.md](../../AGENTS.md) — the repo's working rules (TDD workflow, commit format, tracking files)
- [docs/plans/connectwise_integration_plan.md](../../plans/connectwise_integration_plan.md) — the full implementation spec
- [docs/plans/independent_bank_feed_plan.md](../../plans/independent_bank_feed_plan.md) — related bank-feed work, useful context

Execute **the seven implementation steps below, in order, then stop**. Do not add live ConnectWise API integration, CSV import, fuzzy client matching, or lag-aware reconciliation unless explicitly asked — those are future work.

---

## Scope (what this stage builds)

1. **Models + migration** — add `QBCustomer`, `Invoice`, `InvoiceLine`, `ConnectWiseCompany`, `ClientMapping`, `ConnectWiseWorkRole`, `TimeEntry`, `ExpenseEntry`, and `ProductEntry`; extend `FlagType` with ConnectWise flag types.
2. **QBO customer/invoice sync** — extend `sync_quickbooks` to pull and normalize `Customer` and `Invoice` records into the new models.
3. **Synthetic ConnectWise feed** — add `generate_connectwise_feed` management command and scenario fixtures for hourly leakage, flat-fee profit/erosion/loss, missing mapping, and mixed.
4. **ConnectWise reconciliation engine** — implement `run_connectwise_reconciliation` that compares ConnectWise activity to QBO invoices per client/month and creates flags for unbilled time, margin erosion, and missing mappings.
5. **Management command** — add `run_connectwise_reconciliation` CLI command.
6. **Dashboard section** — add a "Client Reconciliation (ConnectWise)" section below the bank balances panel, with actions to run reconciliation and generate the test feed.
7. **Docs update** — update `docs/TODO.md`, `docs/CURRENT_TASK.md`, and `docs/CHANGELOG.md`.

---

## Git setup

1. Stay on the existing `feature/close-assistant-build` branch. If you are elsewhere, check it out.
2. After completing **each** numbered step, stage all new and modified files, commit, and push.
3. Use the repo's commit format from `AGENTS.md`:
   ```
   <type>(<scope>): <summary>
   - <what changed>
   ```
   Reference the step in the summary or scope, e.g. `feat(models): connectwise step 1 — add QBO customer, invoice, and ConnectWise activity models`.

---

## Environment assumptions

- Python 3.13+ and Django run via Docker Compose per `AGENTS.md`.
- Tests run inside the web container: `docker compose exec web python manage.py test ...`.
- The app uses a **pre-production squashed migration** at `core/migrations/0001_initial.py`. Model changes are applied by editing this migration directly, then verifying with `makemigrations --check --dry-run`.
- No live ConnectWise credentials are required; all ConnectWise data is synthetic.
- No live QuickBooks data is required for tests; QBO customer/invoice sync is tested with mocked SDK responses.

---

## Testing (TDD — from AGENTS.md)

1. Write failing tests first.
2. Confirm they fail for the right reasons.
3. Write the minimum code to make them pass.
4. Refactor if needed, keeping tests green.

### Test conventions

- Add new test modules as needed:
  - `core/tests/test_connectwise_models.py` — model constraints and defaults
  - `core/tests/test_connectwise_feed.py` — synthetic feed generator and command
  - `core/tests/test_connectwise_reconciliation.py` — reconciliation engine
  - `core/tests/test_qbo_invoice_sync.py` — customer/invoice sync helpers (or extend `core/tests/test_views.py`)
  - `core/tests/test_views.py` — dashboard action tests for the ConnectWise section
- Patch QuickBooks SDK calls and token lookups; do not contact the live sandbox.
- After any model change, run `docker compose exec web python manage.py makemigrations --check --dry-run` and confirm no new migration is generated.
- No commit while tests are failing.

---

## Step boundaries

Execute the work in this order. Refer to `docs/plans/connectwise_integration_plan.md` for detailed file lists, test coverage, and migration notes.

| Step | Commit scope | Key deliverables |
|---|---|---|
| 1 | Models and migration | `QBCustomer`, `Invoice`, `InvoiceLine`, `ConnectWiseCompany`, `ClientMapping`, `ConnectWiseWorkRole`, `TimeEntry`, `ExpenseEntry`, `ProductEntry`; extended `FlagType`. Updated `core/migrations/0001_initial.py`. |
| 2 | QBO customer/invoice sync | `sync_customers`, `sync_invoices`; `sync_quickbooks` wiring; `--skip-customers`, `--skip-invoices` flags. |
| 3 | Synthetic ConnectWise feed | Scenario fixtures under `core/fixtures/connectwise_scenarios/`; `core/engines/connectwise_feed.py`; `generate_connectwise_feed` command. |
| 4 | ConnectWise reconciliation engine | `core/engines/connectwise_reconciliation.py` with leakage, margin, and missing-mapping flag logic. |
| 5 | Management command | `run_connectwise_reconciliation` CLI command with summary output. |
| 6 | Dashboard section | `generate_connectwise_feed_view`, `connectwise_reconciliation_view`, URLs, templates, HTMX partials. |
| 7 | Documentation | Updated `docs/CURRENT_TASK.md`, `docs/TODO.md`, `docs/CHANGELOG.md`. |

---

## Tracking files

Maintain `docs/CURRENT_TASK.md`, `docs/CHANGELOG.md`, and `docs/TODO.md` per `AGENTS.md`.

At the start of this stage, set `docs/CURRENT_TASK.md` to "ConnectWise Step 1 — Models and migration". Overwrite it completely each time you move to a new step so it always reflects the live state.

---

## Refactoring and improvements

Use your judgment to add sensible improvements beyond the spec. Good candidates include:

- Extracting shared helpers between the bank-feed and ConnectWise feed generators.
- Adding logging at each reconciliation step.
- Adding validation for `flat_fee_amount` requiring `billing_model="flat_fee"`.
- Adding a model admin for `ClientMapping` to make manual mapping easier.
- Documenting fixture file format in a README under `core/fixtures/connectwise_scenarios/`.

You do not need to ask permission — just do them and note them in `CHANGELOG.md` under the relevant entry.

---

## Rules

- Never write implementation before tests (TDD).
- Complete, commit, and push each step before starting the next.
- If a step produces errors, failing tests, or migration drift, fix them before moving on.
- Do not batch multiple steps into one commit — one commit per step.
- No commit message if tests are failing.
- Always commit `CURRENT_TASK.md`, `CHANGELOG.md`, and `TODO.md` alongside the step's code files.
- Never commit secrets, keys, or credentials.
- All markdown files live in the `docs/` folder.
- After any model change, run `makemigrations --check --dry-run` before committing.

---

## When all seven steps are complete

- Update `docs/CURRENT_TASK.md` to reflect that the ConnectWise integration stage is finished.
- Confirm all seven commits are on `feature/close-assistant-build` with correct messages.
- List any files not committed.
- Print a summary of what was built, all improvements made beyond the spec, and any deviations.
- Push the branch to remote.
- Do not open a pull request, and do not start the next plan (independent bank feed, demo MSP seed, or live ConnectWise API), unless the user explicitly asks — stop here.