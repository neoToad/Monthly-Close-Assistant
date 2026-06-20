"""Shared tunable constants used by reconciliation, anomaly, and agent modules.

Keep environment-specific overrides in Django settings; these values are the safe
defaults used when no setting is configured.
"""
from __future__ import annotations

from decimal import Decimal

#: Two-sided amount-matching tolerance used by reconciliation and agent modules.
AMOUNT_TOLERANCE = Decimal("0.01")

#: Date-window tolerance in days used when matching bank/GL transactions.
DATE_TOLERANCE_DAYS = 1

#: Balance-level reconciliation tolerance (bank statement vs posted GL total).
BALANCE_TOLERANCE = Decimal("0.01")

#: QuickBooks account types treated as cash or cash-like for bank reconciliation.
CASH_LIKE_ACCOUNT_TYPES = {"Bank", "Other Current Asset"}

# --- Anomaly detection thresholds ------------------------------------------------

#: Minimum historical data points before a z-score anomaly check is meaningful.
MIN_ZSCORE_SAMPLES = 3

#: Z-score threshold for flagging a vendor amount as anomalous.
ZSCORE_THRESHOLD = 2.0

#: Window in days for duplicate-transaction detection.
DUPLICATE_WINDOW_DAYS = 7

#: Month-over-month category change threshold (e.g., 2.0 = 200%).
CATEGORY_MOM_THRESHOLD = 2.0

# --- Account-reconciliation agent thresholds -----------------------------------

#: Residual amount below which we assume bank fees / rounding.
BANK_FEES_THRESHOLD = Decimal("100.00")

#: Default offset accounts for deterministic suggestions.
DEFAULT_EXPENSE_ACCOUNT = "Uncategorized Expense"
DEFAULT_INCOME_ACCOUNT = "Miscellaneous Income"
DEFAULT_BANK_FEES_ACCOUNT = "Bank Fees"

# --- ConnectWise reconciliation thresholds -------------------------------------

#: Dollar leakage threshold for hourly/retainer clients before a flag is raised.
CONNECTWISE_UNBILLED_THRESHOLD = Decimal("100.00")

#: Target margin for flat-fee clients (revenue - cost) / revenue.
CONNECTWISE_TARGET_MARGIN = Decimal("0.35")

#: Warning margin threshold for flat-fee clients.
CONNECTWISE_MARGIN_WARN = Decimal("0.20")

#: Critical margin threshold for flat-fee clients (0% or negative).
CONNECTWISE_MARGIN_CRITICAL = Decimal("0.00")

#: Default fully-loaded hourly cost when no role-specific or client-specific rate exists.
CONNECTWISE_DEFAULT_BURDEN_RATE = Decimal("100.00")

# --- Synthetic bank feed parameters --------------------------------------------

#: Small amount deltas used to simulate fees, rounding, or FX differences.
AMOUNT_DELTAS = [Decimal("-2.50"), Decimal("-1.00"), Decimal("1.00"), Decimal("3.75")]

#: Day shifts used to simulate posting delays.
DATE_SHIFTS = [-2, -1, 1, 2]

#: Fake vendors used for bank-only (extra) transactions.
EXTRA_VENDORS = ["Bank Fee", "Interest Income", "ACH Transfer", "Wire Fee"]
