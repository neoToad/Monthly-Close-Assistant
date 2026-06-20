# TODO

## Demo data

- [x] Add `seed_demo_msp_data` management command with realistic MSP fixture.
- [ ] Multi-month historical seeding so anomaly detection has richer history.
- [ ] Configurable client/vendor lists via external JSON or command-line arguments.
- [ ] Optional `push_demo_to_qbo_sandbox` bridge that writes the same fixture into a QBO sandbox company via the SDK, then pulls it back with `sync_quickbooks`.
- [ ] Seed `QBCustomer` and `Invoice` rows once those models are fully wired into the reconciliation workflow.
- [ ] Seed `ConnectWiseCompany`, `ClientMapping`, `TimeEntry`, `ExpenseEntry`, and `ProductEntry` rows once the ConnectWise reconciliation plan is implemented.
