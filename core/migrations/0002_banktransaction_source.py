"""Add BankTransaction.source column when the database is missing it.

The squashed ``0001_initial`` migration was edited after some databases had already
applied it. This migration safely adds the column only if it does not yet exist,
so it is a no-op on fresh databases and fixes existing ones without data loss.
"""
from __future__ import annotations

from django.db import migrations, models


def _column_exists(schema_editor, table_name: str, column_name: str) -> bool:
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
            """,
            [table_name, column_name],
        )
        return cursor.fetchone() is not None


def add_source_column_if_missing(apps, schema_editor) -> None:
    BankTransaction = apps.get_model("core", "BankTransaction")
    table_name = BankTransaction._meta.db_table
    if _column_exists(schema_editor, table_name, "source"):
        return

    field = models.CharField(
        max_length=20,
        choices=[
            ("synthetic", "Synthetic (test simulator)"),
            ("csv_import", "CSV import"),
            ("bank_feed_api", "Bank feed API"),
            ("manual", "Manual entry"),
        ],
        default="manual",
        help_text="How this bank transaction entered the system.",
    )
    field.set_attributes_from_name("source")
    schema_editor.add_field(BankTransaction, field)


def remove_source_column_if_present(apps, schema_editor) -> None:
    BankTransaction = apps.get_model("core", "BankTransaction")
    table_name = BankTransaction._meta.db_table
    if not _column_exists(schema_editor, table_name, "source"):
        return
    schema_editor.remove_field(BankTransaction, BankTransaction._meta.get_field("source"))


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            add_source_column_if_missing,
            reverse_code=remove_source_column_if_present,
        ),
    ]
