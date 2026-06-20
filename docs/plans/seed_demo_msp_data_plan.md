# Plan: Seed Realistic MSP Demo Data Locally

**Status:** Implemented
**Date:** 2026-06-20

## Goal

Add a management command that seeds the local database with realistic MSP (managed service provider) financial data so the dashboard looks like a real company that Next Level Networks might serve. No QuickBooks sandbox writes are required; all data is created directly in the app's Postgres database and can be wiped/re-seeded at any time.

This gives a fast, deterministic, offline-friendly demo for:

- Bank reconciliation
- Anomaly detection
- Account-level balance reconciliation
- (Future) ConnectWise-to-QBO client reconciliation

## Why local seed instead of QBO sandbox push

Pushing data into the Intuit sandbox via the QuickBooks SDK is possible, but for an MVP it is slower, less deterministic, requires live credentials, and risks cluttering the sandbox company. Seeding locally:

- Works without any QuickBooks OAuth credentials.
- Produces the same dashboard state every run.
- Runs in CI and local dev instantly.
- Is safe to run repeatedly with `--force`.
- Can be extended later with a separate optional bridge that pushes the same seed into a sandbox.

## What "realistic MSP data" means

A fictional MSP called **Next Level Networks Demo** with:

- A plausible chart of accounts (cash, AR, AP, revenue, labor, subscriptions, circuits, etc.)
- A mix of flat-fee / managed-services clients and hourly / project clients
- Monthly vendor bills for common MSP stack costs
- Deposits and invoices representing client payments
- A few realistic discrepancies so reconciliation has something to catch

This is not meant to be a full accounting system — it is a believable slice of data for close-review demos.

## Future work (out of scope)

* A separate optional command `push_demo_to_qbo_sandbox` that writes the same fixture data into a real QuickBooks sandbox company via the SDK, then pulls it back with `sync_quickbooks`.
* Multi-month historical seeding so anomaly detection has richer history.
* Configurable client/vendor lists via external JSON or command-line arguments.
* Seeding `QBCustomer` and `Invoice` rows once those models exist.
* Seeding `ConnectWiseCompany`, `ClientMapping`, and activity rows once the ConnectWise plan is implemented.

## Note on QuickBooks sandbox

This plan intentionally does **not** push data into QuickBooks Online. All data lives in the app's database. If a future demo requires showing live QBO read/write, that should be a separate plan that builds a one-way bridge from this local seed into the sandbox.