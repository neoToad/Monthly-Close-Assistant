# CURRENT_TASK

## Stage

Build (Prompts 4–18) — IN PROGRESS. Prompt 17 complete; starting Prompt 18.

## Current task

Step 18 — README. Write a comprehensive project README that explains what the Monthly
Close Assistant does, how to set it up locally, how to run tests, how to use the key
management commands, and how to deploy via Docker / Railway.

## Completion criteria

- `README.md` at the repo root covers:
  - Project overview and high-level architecture.
  - Local setup (clone, env, Docker compose, migrations).
  - Running tests (`python manage.py test` and inside Docker).
  - Management commands (sync_quickbooks, run_reconciliation, generate_close_summary,
    seed_demo_data).
  - Dashboard and access control.
  - Deployment notes (Railway, CI).
- Update `docs/CHANGELOG.md` and `docs/TODO.md`.
- Commit with the Prompt 18 message and push.
- Stop after this commit; do not start stretch prompts or open a PR.

## Branch

`feature/close-assistant-build`
