"""``seed_demo_data`` management command (Prompt 11).

Creates demo ``Transaction`` records for a month with Faker, generates an imperfect
bank feed, runs reconciliation + anomaly detection, and drafts a close summary.
Safe to run repeatedly.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from core.demo_seed import seed_demo_data


class Command(BaseCommand):
    help = (
        "Seed demo data for a month and run the full close pipeline: create "
        "synthetic Transactions, generate a bank feed, reconcile, detect anomalies, "
        "and draft a close summary."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("month", help="Month in YYYY-MM format.")
        parser.add_argument(
            "--count",
            type=int,
            default=20,
            help="Number of demo transactions to create (default 20).",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=None,
            help="Random seed for reproducible demo data generation.",
        )

    def handle(self, *args, **options) -> None:
        month = options["month"]
        result = seed_demo_data(
            month=month,
            count=options["count"],
            seed=options["seed"],
        )

        self.stdout.write(
            self.style.SUCCESS(f"Demo data seeded for {month}")
        )
        self.stdout.write(f"  Transactions created:        {result['transactions_created']}")
        self.stdout.write(f"  Bank transactions created:   {result['bank_transactions_created']}")
        self.stdout.write(f"  Reconciliation flags created: {result['reconciliation_flags_created']}")
        self.stdout.write(f"  Close summary:               {result['summary_month']}")
