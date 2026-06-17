# Monthly Close Assistant — Follow-Up Build Prompts (Phase 2)

Run these after the 18-step core build is working end to end. Grouped by goal:
more advanced agent capability, more production-grade robustness, and more
interview-ready polish. Pick and choose based on time available, none of these
depend on each other except where noted.

---

## A. Advanced Agent Capability

### A1. Multi-Agent Breakdown
```
Refactor the current single agent step into a small multi-agent setup using
CrewAI (or LangGraph, matching whatever's already in place): one agent that
reviews reconciliation Flags and writes a reconciliation-focused section, one
agent that reviews anomaly Flags and writes an anomaly-focused section, and a
final agent that combines both sections into the overall CloseSummary, written
in a consistent voice. Keep the same hard boundary: agents only produce text,
none of them can modify Flag, Transaction, or BankTransaction records.
```

### A2. Agent Self-Critique Pass
```
Add a second pass to the close summary generation where the agent reviews its
own draft against the underlying Flag data and checks for: any flagged item it
forgot to mention, any number in the summary that doesn't match the source data,
and any vague language that should be more specific. Have it output a revised
draft. Store both the first draft and the revised draft on the CloseSummary
model so the difference is visible.
```

### A3. Natural-Language Flag Querying
```
Add a simple endpoint and dashboard search box where a reviewer can type a
natural-language question about the current month's flags, e.g. "what's our
biggest anomaly this month" or "show me all reconciliation issues over $500",
and an agent step translates that into a filter against the Flag data and
returns a plain-language answer plus the matching records. Keep this strictly
read-only.
```

### A4. Confidence Scoring on Flags
```
Update anomaly detection to attach a confidence/severity score (e.g. 1-100) to
each Flag based on how far outside normal range it is, rather than a flat
severity label. Have the agent reference these scores in the close summary,
prioritizing high-confidence flags first and noting which flags are borderline
and might not need review.
```

---

## B. Production-Grade Robustness

### B1. Structured Logging & Observability
```
Replace print statements and basic logging across sync_quickbooks,
run_reconciliation, and generate_close_summary with Python's logging module,
using structured log entries (include month, record counts, duration, and
outcome for each run). Add a simple PipelineRun model that records each
management command execution: command name, start time, end time, status
(success/failure), and a summary of what it did, surfaced in Django admin.
```

### B2. Data Validation Layer
```
Add validation before any Transaction or BankTransaction record is saved:
reject records with negative amounts where they shouldn't exist, missing
required fields, or dates outside a reasonable range (e.g. more than 2 years
in the past or any date in the future). Log and skip invalid records rather
than crashing the sync, and surface a count of skipped records in the
sync_quickbooks output.
```

### B3. Permissions Beyond Login
```
Extend the authentication added earlier with a simple role distinction:
"reviewer" role can approve/reject flags and mark summaries reviewed, "viewer"
role can see the dashboard but not take any action. Use Django groups for this.
Update the dashboard templates to hide action buttons for viewer-role users.
```

### B4. Database Backups & Migration Safety
```
Add a documented backup strategy for the PostgreSQL database (a simple
pg_dump-based script and a README section on restoring from backup), and add
a pre-deploy check in the GitHub Actions workflow that fails the build if
there are unapplied migrations that aren't included in the PR.
```

### B5. Rate Limiting on Dashboard Actions
```
Add basic rate limiting to the flag approve/reject endpoints to prevent
accidental double-submission (e.g. a user double-clicking Approve) from
creating duplicate AuditLog entries or race conditions. Use Django's
cache framework or django-ratelimit for this.
```

---

## C. Interview-Ready Polish

### C1. Seeded "Interesting" Demo Scenario
```
Update seed_demo_data to generate a specific, narratively clear demo scenario
rather than fully random data: include one obvious duplicate payment, one
vendor with a clear 3-standard-deviation spike, one new vendor with no
history, and one timing-shift reconciliation mismatch, each with realistic
vendor names and amounts. Make sure the agent-generated summary clearly
calls out each of these four cases by name, so the demo tells a clean story
when walked through live.
```

### C2. Before/After Reconciliation View
```
Add a simple view or dashboard section that shows the raw bank feed and GL
side by side for a selected month, with mismatches highlighted, before
showing the resolved/flagged view. This gives a visual "here's the problem,
here's what the system caught" moment for a live walkthrough.
```

### C3. One-Command Local Demo
```
Add a Makefile (or shell script) with a single command, e.g. `make demo`,
that runs docker-compose up, waits for the database to be ready, runs
migrations, runs seed_demo_data, and prints the dashboard URL and login
credentials. The goal is one command from a fresh clone to a working demo
with zero manual steps.
```

### C4. Architecture Diagram Export
```
Generate a simple architecture diagram (Mermaid syntax in the README, or a
standalone PNG/SVG via a Python diagramming library) showing the data flow
from QuickBooks through Data Sync, Postgres, Analysis Engine, Agent Layer, and
the HTMX Dashboard. This should match the diagram already described in the
README and be easy to screen-share or include in a portfolio.
```

### C5. README "Design Decisions" Section
```
Add a "Design Decisions" section to the README explaining, in plain language,
why HTMX was chosen over a React SPA for this tool, why the agent is
restricted to draft-only output with no write access, why anomaly detection
uses explainable statistical rules instead of a black-box ML model, and why
the bank feed is deliberately corrupted from known data rather than fully
synthetic. This section should read like something you'd say out loud in an
interview, not generic documentation.
```

---

## Suggested Order

If time is limited, prioritize in this order: C1, C3, C5 (fastest, highest
interview payoff), then A2 and B1 (meaningfully deepen the technical story),
then the rest as time allows. B-section items are good to mention as "what
I'd add next for production" even if not fully built, that's a legitimate and
common interview answer.
