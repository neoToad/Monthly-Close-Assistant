# Current Task

Step 6 — ConnectWise dashboard section — IN PROGRESS.

Status:
- Steps 4 and 5 (reconciliation engine + command) are complete and verified.
- Now adding dashboard UI:
  - `connectwise_reconciliation_view` (POST /dashboard/connectwise/reconcile/)
  - `generate_connectwise_feed_view` (POST /dashboard/connectwise/generate/)
  - URL wiring in `core/urls.py`
  - `core/templates/core/connectwise_section.html` partial
  - Inclusion in `core/templates/core/dashboard_content.html`
  - Dashboard context helpers for summary metrics and ConnectWise flags
  - View tests in `core/tests/test_views.py`

Next:
- Implement the two views following the existing dashboard action patterns.
- Render a Client Reconciliation section below bank balances.
- Add tests covering rendering, reconciliation run, and feed generation.
- Run full suite, then proceed to Step 7 (final docs/verification).
