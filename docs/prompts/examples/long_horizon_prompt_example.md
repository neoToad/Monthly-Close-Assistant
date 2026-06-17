You are refactoring PolicyIQ. Start by reading documents:
- [refactoring-plan.md](../refactoring-plan.md)

The prompt plan is your implementation spec — execute every prompt in it, in order. Mark the phase as completed in the file after it has been completed.

---

## Git Setup (do this first)

1. If a branch named `feature/policyiq-build` does not exist, create it from main and check it out.
2. After completing each numbered step in the prompt plan (1.1, 1.2, 1.3, etc.), stage all new and modified files, commit, and push.
3. Use this commit message format: `[PhaseX.Y] Short description of what was built`

---

## Environment Assumptions

- Python 3.11+
- PostgreSQL running locally, database `policyiq`, user `policyiq_user`
- Ollama running at http://localhost:11434 with `nomic-embed-text` and `llama3.2` already pulled
- Repo root is the working directory

---

## Tracking Files

Maintain two markdown files in the repo root throughout the entire build. Update them continuously — not just at the end.

### docs/CURRENT_TASK.md
Keep this file up to date at all times. It should always reflect exactly what is happening right now and should be updated
before working on the step:
- The current step number and name
- What you are actively working on
- Any blockers or decisions being made
- What the next step will be

Overwrite it completely each time you move to a new step. It should never describe a completed step — only the live current state.

### docs/CHANGELOG.md
Append an entry after every commit. Each entry should include:
- The step number and commit message
- A plain-English summary of what was built
- Any refactors or improvements made beyond the spec (see below)
- Any deviations from the spec and why


---

## Refactoring and Improvements

As you build, use your judgment to refactor and add sensible improvements beyond what the spec explicitly describes. Good candidates include: better error messages, type hints, docstrings, input validation, DRY service abstractions, defensive handling of edge cases, or small UX improvements in templates. You do not need to ask permission for these — just do them and note them in CHANGELOG.md under the relevant entry.

---

## Rules

- Complete, commit, and push to remote each step before starting the next.
- If a step produces errors, fix them before moving on. Do not proceed on broken code.
- Do not batch multiple steps into one commit.
- Always commit CURRENT_TASK.md and CHANGELOG.md alongside the step's code files.
- All md files are located in the docs folder.

---

## When All Steps Are Complete

- Update CURRENT_TASK.md to reflect that the build is finished.
- Confirm all commits are on the branch with correct messages.
- List any files not committed.
- Print a summary of what was built, all improvements made beyond the spec, and any deviations.
- Push the branch to remote.
- Do not open a pull request.
