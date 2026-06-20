"""Static MSP demo data for the ``seed_demo_msp_data`` management command.

This fixture describes a fictional managed-service provider called **Next Level
Networks Demo**. Amounts are fixed so demo assertions stay stable; the management
command jitters dates when ``--seed`` is provided.

All transaction amounts are signed from the perspective of the named GL account:
positive amounts increase the account, negative amounts decrease it. Cash activity
that hits ``Operating Checking`` uses signed amounts so the balance-reconciliation
check produces a deterministic difference against the seeded statement balance.
"""
from __future__ import annotations

from decimal import Decimal

COMPANY_NAME = "Next Level Networks Demo"

ACCOUNTS = [
    {"account_id": "1000", "name": "Operating Checking", "account_type": "Bank"},
    {"account_id": "1200", "name": "Accounts Receivable", "account_type": "Accounts Receivable"},
    {"account_id": "2100", "name": "Accounts Payable", "account_type": "Accounts Payable"},
    {"account_id": "4000", "name": "Managed Services Revenue", "account_type": "Income"},
    {"account_id": "4100", "name": "Project / Hourly Revenue", "account_type": "Income"},
    {"account_id": "5000", "name": "Technician Labor", "account_type": "Expense"},
    {"account_id": "5100", "name": "Subcontractor Costs", "account_type": "Expense"},
    {"account_id": "5200", "name": "Software & Subscriptions", "account_type": "Expense"},
    {"account_id": "5300", "name": "Telecom & Internet Circuits", "account_type": "Expense"},
    {"account_id": "5400", "name": "Mileage & Travel", "account_type": "Expense"},
    {"account_id": "5500", "name": "Office Supplies", "account_type": "Expense"},
    {"account_id": "5600", "name": "Bank Service Charges", "account_type": "Expense"},
]

CUSTOMERS = {
    "Acme Manufacturing": {"billing_model": "flat_fee", "monthly_amount": Decimal("8500.00")},
    "Beta Dental Group": {"billing_model": "flat_fee", "monthly_amount": Decimal("6000.00")},
    "Gamma Law Firm": {"billing_model": "flat_fee", "monthly_amount": Decimal("12000.00")},
    "Delta Construction": {"billing_model": "hourly"},
    "Epsilon Retail": {"billing_model": "hourly"},
}

VENDORS = [
    "Datto / Kaseya",
    "SentinelOne",
    "Microsoft 365 Licensing",
    "Comcast Business",
    "Paychex Payroll Services",
    "Amazon Business",
    "First National Bank",
    "Subcontractor LLC",
]

# Cash-in deposits that hit Operating Checking.
DEPOSITS = [
    {"vendor": "Acme Manufacturing", "amount": Decimal("8500.00"), "day": 3, "category": "Managed Services Revenue", "gl_account": "Operating Checking"},
    {"vendor": "Beta Dental Group", "amount": Decimal("6000.00"), "day": 1, "category": "Managed Services Revenue", "gl_account": "Operating Checking"},
    {"vendor": "Gamma Law Firm", "amount": Decimal("12000.00"), "day": 15, "category": "Managed Services Revenue", "gl_account": "Operating Checking"},
    {"vendor": "Delta Construction", "amount": Decimal("3200.00"), "day": 20, "category": "Project / Hourly Revenue", "gl_account": "Operating Checking"},
    {"vendor": "Epsilon Retail", "amount": Decimal("1800.00"), "day": 18, "category": "Project / Hourly Revenue", "gl_account": "Operating Checking"},
]

# Bills increase Accounts Payable; they are not cash activity yet.
BILLS = [
    {"vendor": "Paychex Payroll Services", "amount": Decimal("14000.00"), "day": 30, "category": "Technician Labor", "gl_account": "Accounts Payable"},
    {"vendor": "Datto / Kaseya", "amount": Decimal("2400.00"), "day": 5, "category": "Software & Subscriptions", "gl_account": "Accounts Payable"},
    {"vendor": "SentinelOne", "amount": Decimal("1800.00"), "day": 10, "category": "Software & Subscriptions", "gl_account": "Accounts Payable"},
    {"vendor": "Microsoft 365 Licensing", "amount": Decimal("1200.00"), "day": 12, "category": "Software & Subscriptions", "gl_account": "Accounts Payable"},
    {"vendor": "Comcast Business", "amount": Decimal("950.00"), "day": 8, "category": "Telecom & Internet Circuits", "gl_account": "Accounts Payable"},
    {"vendor": "Subcontractor LLC", "amount": Decimal("1500.00"), "day": 22, "category": "Subcontractor Costs", "gl_account": "Accounts Payable"},
]

# Direct expenses paid from Operating Checking (cash out).
PURCHASES = [
    {"vendor": "Amazon Business", "amount": Decimal("-450.00"), "day": 14, "category": "Networking Supplies", "gl_account": "Operating Checking"},
    {"vendor": "Mileage Reimbursement", "amount": Decimal("-220.00"), "day": 25, "category": "Mileage & Travel", "gl_account": "Operating Checking"},
    {"vendor": "Office Depot", "amount": Decimal("-85.00"), "day": 28, "category": "Office Supplies", "gl_account": "Operating Checking"},
]

# Adjusting / allocation entries.
JOURNAL_ENTRIES = [
    {"vendor": "Payroll Allocation", "amount": Decimal("3500.00"), "day": 30, "category": "Technician Labor", "gl_account": "Technician Labor"},
    {"vendor": "First National Bank", "amount": Decimal("100.00"), "day": 30, "category": "Bank Service Charges", "gl_account": "Bank Service Charges"},
]

# Bill payments reduce cash and AP.
BILL_PAYMENTS = [
    {"vendor": "Paychex Payroll Services", "amount": Decimal("-14000.00"), "day": 30, "category": "Bill Payment", "gl_account": "Operating Checking"},
    {"vendor": "Datto / Kaseya", "amount": Decimal("-2400.00"), "day": 7, "category": "Bill Payment", "gl_account": "Operating Checking"},
    {"vendor": "Comcast Business", "amount": Decimal("-950.00"), "day": 9, "category": "Bill Payment", "gl_account": "Operating Checking"},
]

VENDOR_CREDITS = [
    {"vendor": "SentinelOne", "amount": Decimal("-300.00"), "day": 15, "category": "Software & Subscriptions", "gl_account": "Accounts Payable"},
]

# Ending bank statement balance for Operating Checking. This value is intentionally
# different from the sum of checking-account GL activity so the balance-
# reconciliation check raises a flag.
OPERATING_CHECKING_STATEMENT_BALANCE = Decimal("42315.50")

# Transaction buckets in the order they are seeded, used for deterministic
# qb_transaction_id generation.
TRANSACTION_BUCKETS = [
    ("Deposit", DEPOSITS),
    ("Bill", BILLS),
    ("Purchase", PURCHASES),
    ("JournalEntry", JOURNAL_ENTRIES),
    ("BillPayment", BILL_PAYMENTS),
    ("VendorCredit", VENDOR_CREDITS),
]
