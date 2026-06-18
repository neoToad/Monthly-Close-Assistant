# CURRENT_TASK

## Stage

Build (Prompts 4–18) — IN PROGRESS. Prompt 15 complete; starting Prompt 16.

## Current task

Step 16 — CI/CD. Add a GitHub Actions workflow that lints, runs the full Django test
suite inside Docker compose, and verifies the Docker image builds on every push and
pull request to `feature/close-assistant-build` and `main`.

## Completion criteria

- `.github/workflows/ci.yml` created.
- Workflow triggers on push/PR to `feature/close-assistant-build` and `main`.
- Steps: checkout, build Docker compose stack, run `python manage.py test` inside the
  backend container, report results.
- Keep `docs/CURRENT_TASK.md`, `docs/CHANGELOG.md`, `docs/TODO.md` updated.
- Commit with the Prompt 16 message and push.

## Branch

`feature/close-assistant-build`
