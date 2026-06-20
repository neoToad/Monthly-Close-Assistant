"""Analysis engines for the Monthly Close Assistant.

* ``reconciliation`` — match GL and bank transactions, create reconciliation flags.
* ``anomaly`` — rule-based anomaly detection on transactions.
* ``bank_feed`` — synthetic bank-transaction generator for testing.
"""
from __future__ import annotations

from core.engines.anomaly import run_anomaly_detection
from core.engines.bank_feed import generate_bank_feed
from core.engines.reconciliation import (
    check_account_balances,
    compute_posted_total,
    run_reconciliation,
)

__all__ = [
    "check_account_balances",
    "compute_posted_total",
    "generate_bank_feed",
    "run_anomaly_detection",
    "run_reconciliation",
]
