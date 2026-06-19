# Monthly Close Assistant — Long Horizon Prompt: Design System (Prompts D1–D7)

You are continuing the Monthly Close Assistant on the existing
`feature/close-assistant-build` branch. The core backend (prompts 1–12) and the
functional HTMX dashboard (prompts 13–14) must already be complete and committed
before starting this stage. These prompts implement the "ledger" design system: a
calm, financial-instrument-panel look instead of default Django/Bootstrap styling.

Start by reading these documents:

- [AGENTS.md](../../AGENTS.md) — the repo's working rules (TDD workflow, commit format, tracking files)
- [Monthly_Close_Assistant_Design_System_Prompts.md](../Monthly_Close_Assistant_Design_System_Prompts.md) — the concrete design-system instructions used by this long-horizon prompt

For this stage, execute **prompts D1 through D7, in order, then stop**. Review each
step visually before moving to the next. Use the referenced design-system
instructions as the detailed spec for each D-prompt.

Track each step's completion in `docs/CURRENT_TASK.md` and `docs/CHANGELOG.md`
(see below) — do not edit the spec document itself.

---

## Scope (what this stage builds)

- **D1 — Design Tokens & Base Styles:** create a single CSS file
  (`static/css/tokens.css`) defining the design system as CSS custom properties
  (colors, typography, spacing), import the Google Fonts in `base.html`, and apply
  the base page styles globally.
- **D2 — Page Shell & Header:** rebuild the dashboard's base template header into
  a single-row ledger-style header with the page title, a custom month selector,
  and a status ledger strip showing open/approved/rejected counts.
- **D3 — Flagged Items Table Redesign:** restyle the flagged-items table to look
  like a ledger with hairline dividers, plain-text action buttons, colored status
  dots, and HTMX row-swap behavior that fades out resolved actions.
- **D4 — Draft Summary Section:** restyle the close-summary section with an
  eyebrow label, document-like readable text, a hairline divider, and
  plain-text-style "Mark Reviewed" action plus a subdued reviewer-notes
  textarea.
- **D5 — Empty & Loading States:** add an empty state for months with no flags
  and a subtle opacity-based loading state for HTMX-driven month switching and
  approve/reject actions.
- **D6 — Responsive & Accessibility Pass:** make the flagged-items table stack on
  mobile, add visible keyboard-focus outlines, and verify WCAG AA contrast for
  the token colors.
- **D7 — Self-Critique Pass:** review the rendered dashboard against the design
  constraints (no shadows, no pill badges, serif only for title/month, amber only
  for open flags, green only for approved/confirmed) and fix any violations.

---

## Git Setup

1. Stay on the existing `feature/close-assistant-build` branch. If you are on a
   different branch, check it out. Do **not** create a new branch for the design
   system work.
2. After completing **each** numbered prompt (D1 through D7), stage all new and
   modified files, commit, and push.
3. Use the repo's commit format from `AGENTS.md`:
   ```
   <type>(<scope>): <summary>
   - <what changed>
   ```
   Types: `feat` `fix` `test` `refactor` `chore` `docs`. Reference the step in
   the summary or scope, e.g.
   `feat(ui): D1 — design tokens and base ledger styles`.

---

## Environment Assumptions

- The Django project is already running locally or via Docker per `AGENTS.md`.
- The dashboard exists at `/dashboard/` and already lists flags, supports month
  selection, and supports Approve/Reject actions via HTMX.
- `seed_demo_data` (or equivalent demo data) is available so the dashboard has
  visible flags and a draft summary for visual review.
- All new static assets live under `static/` and templates under `templates/`.
- All markdown files live in the `docs/` folder.

---

## Testing & Verification

Testing for the design-system stage is visual and template-level rather than
algorithmic, but still follows the `AGENTS.md` quality workflow:

1. Before changing templates, add or update tests that assert the rendered
   HTML structure you expect (element classes, data attributes, partial template
   names, form targets, status dot presence, and the correct Google Fonts link).
2. Confirm the tests fail for the right reasons (missing CSS classes, missing
   partials, wrong element order, etc.).
3. Implement the template/static changes and make the tests pass.
4. Refactor if needed, keeping tests green.

Additional checks:

- Load `/dashboard/` in a browser after each prompt and verify the visual result
  matches the prompt description.
- Use browser dev tools to confirm no `box-shadow` is applied, no border-radius
  exceeds `4px`, and the font stacks match the tokens.
- Test the mobile stacked layout below 640px.
- Confirm keyboard focus states are visible on the month selector, approve/reject
  buttons, and "Mark Reviewed" action.
- Use a contrast checker to verify WCAG AA for `--color-ink`, `--color-slate`,
  `--color-flag`, and `--color-rejected` against `--color-paper`.

- No commit while tests are failing. Never write implementation before tests.

---

## Tracking Files

Maintain `docs/CURRENT_TASK.md`, `docs/CHANGELOG.md`, and `docs/TODO.md` per
`AGENTS.md`.

At the start of this stage, set `docs/CURRENT_TASK.md` to "D1 — Design Tokens &
Base Styles". Overwrite it completely each time you move to a new prompt so it
always reflects the live state.

---

## Refactoring and Improvements

Use your judgment to add sensible improvements beyond what each prompt
explicitly describes. Good candidates include: extracting reusable template
partials (e.g., a status-dot snippet), adding `aria-live` regions for HTMX swaps,
css-only loading indicators via `.htmx-request`, utility classes that wrap the
token values, or small accessibility improvements like visible focus outlines and
`aria-label` on icon-only status dots. You do not need to ask permission — just
do them and note them in `CHANGELOG.md` under the relevant entry.

---

## Rules

- Never write implementation before tests (TDD).
- Complete, commit, and push each step (D1 through D7) before starting the next.
- If a step produces errors, visual regressions, or failing tests, fix them
  before moving on. Do not proceed on broken code.
- Do not batch multiple steps into one commit — one commit per prompt.
- No commit message if tests are failing.
- Always commit `CURRENT_TASK.md`, `CHANGELOG.md`, and `TODO.md` alongside the
  step's code files.
- Never commit secrets, keys, or credentials.
- All markdown files live in the `docs/` folder.

---

## When All Seven Design Steps Are Complete

- Update `CURRENT_TASK.md` to reflect that prompts D1–D7 are finished and that the
  design-system stage is complete.
- Confirm all seven commits are on `feature/close-assistant-build` with correct
  messages.
- List any files not committed.
- Print a summary of what was styled, all improvements made beyond the spec, any
  deviations, and the results of the visual/accessibility checks.
- Push the branch to remote.
- Do not open a pull request, and do not start a stretch prompt, unless the user
  explicitly asks — stop here.
