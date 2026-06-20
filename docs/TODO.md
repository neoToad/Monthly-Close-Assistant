# TODO

## Bank feed independence (`docs/plans/independent_bank_feed_plan.md`)

- Complete: add `BankTransaction.source` field and `BankTransactionSource` choices.
- Complete: set `source=synthetic` on every row created by the synthetic generator.
- Complete: add CSV import engine `core/engines/bank_feed_import.py`.
- Complete: add `import_bank_feed` management command.
- Complete: add `import_bank_feed_view` and dashboard CSV upload form.
- Complete: relabel synthetic generator button and add testing-only subtitle.
- Complete: add independent simulator scenario and `--scenario` / `--scenario-file` support.
- Complete: full test suite passes.

## Multi-company QuickBooks support

- Complete: create `QuickBooksCompany` model with `realm_id` as primary key.
- Complete: add `company` foreign keys to realm-scoped models.
- Complete: backfill existing rows and replace realm-only unique constraints.
- Complete: add `QuickBooksCompanyManager.for_realm(realm_id)`.
- Complete: update tests and docs.

## Bank balance reconciliation

- Complete: add `BankStatementBalance` model and balance-reconciliation flag type.
- Complete: add manual and sandbox bank-balance entry commands.
- Complete: integrate balance checks into `run_reconciliation`.
- Complete: expose bank balances on the dashboard.
- Complete: update README and changelog.

## AI-assisted account reconciliation

- Complete: add `AccountReconciliationState` and reconciliation status choices.
- Complete: add deterministic and optional LLM suggestion engine.
- Complete: add QuickBooks write wrappers.
- Complete: add reconcile-account modal, preview, confirmation, and dashboard integration.
- Complete: add management commands and tests.
- Complete: add failure-mode tests for partial writes and post-apply sync failures.

## Synthetic bank feed

- Complete: add synthetic bank feed command.
- Complete: expose dashboard generation with force/cash-only support.
- Complete: add view tests for dashboard generation.

## ConnectWise integration (`docs/plans/connectwise_integration_plan.md`)

- Complete: Step 1 — add QBO customer/invoice and ConnectWise activity models.
- Complete: Step 2 — sync QBO customers and invoices.
- Complete: Step 3 — synthetic ConnectWise feed generator with scenarios.
- Complete: Step 4 — ConnectWise-to-QBO reconciliation engine.
- Complete: Step 5 — `run_connectwise_reconciliation` management command.
- Complete: Step 6 — dashboard Client Reconciliation (ConnectWise) section.
- Complete: Step 7 — documentation and final verification.

## Refactor plan (`docs/plans/refactor_plan.md`)

- Complete: Step 1 audit and Step 2 execution.
- Complete: package reorganization into `core/agents`, `core/engines`, and `core/services`.
- Complete: migration squash into `core/migrations/0001_initial.py`.
- Complete: recommended next step items from the refactor plan.
