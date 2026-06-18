"""``generate_bank_feed`` management command (Prompt 6).

Reads ``Transaction`` records for a given month and creates a deliberately imperfect
set of ``BankTransaction`` records for reconciliation testing. Discrepancy rates are
configurable via command-line options.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from core.bank_feed import generate_bank_feed


class Command(BaseCommand):
    help = (
        "Generate BankTransaction records for a month from Transaction records, "
        "introducing configurable discrepancies for reconciliation testing."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("month", help="Month in YYYY-MM format.")
        parser.add_argument(
            "--drop-rate",
            type=float,
            default=0.05,
            help="Fraction of GL transactions to drop from the bank feed (default 0.05).",
        )
        parser.add_argument(
            "--dup-rate",
            type=float,
            default=0.03,
            help="Fraction of remaining transactions to duplicate (default 0.03).",
        )
        parser.add_argument(
            "--amount-shift-rate",
            type=float,
            default=0.04,
            help="Fraction of rows to nudge by a small amount delta (default 0.04).",
        )
        parser.add_argument(
            "--date-shift-rate",
            type=float,
            default=0.05,
            help="Fraction of rows to shift by 1-2 days (default 0.05).",
        )
        parser.add_argument(
            "--extra-rate",
            type=float,
            default=0.03,
            help="Fraction of extra bank-only transactions to add (default 0.03).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Overwrite existing BankTransaction records for the month.",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=None,
            help="Random seed for reproducible discrepancy generation.",
        )

    def handle(self, *args, **options) -> None:
        month = options["month"]

        try:
            result = generate_bank_feed(
                month=month,
                drop_rate=options["drop_rate"],
                dup_rate=options["dup_rate"],
                amount_shift_rate=options["amount_shift_rate"],
                date_shift_rate=options["date_shift_rate"],
                extra_rate=options["extra_rate"],
                force=options["force"],
                seed=options["seed"],
            )
        except ValueError as exc:
            raise CommandError(str(exc))

        if result.get("message"):
            self.stdout.write(self.style.WARNING(result["message"]))
            return

        self.stdout.write(self.style.SUCCESS(
            f"Bank feed generated for {month}: created={result['created']} bank rows"
        ))
        self.stdout.write("Discrepancy summary:")
        self.stdout.write(f"  Dropped:          {result['dropped']}")
        self.stdout.write(f"  Duplicated:       {result['duplicated']}")
        self.stdout.write(f"  Amount shifts:    {result['amount_shifts']}")
        self.stdout.write(f"  Date shifts:      {result['date_shifts']}")
        self.stdout.write(f"  Extra bank-only:  {result['extras']}")
