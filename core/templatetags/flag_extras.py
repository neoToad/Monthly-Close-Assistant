"""Small template filters used by the ledger dashboard."""
from __future__ import annotations

from django import template

from core.models import FlagStatus

register = template.Library()


@register.filter(name="status_dot_class")
def status_dot_class(status: str) -> str:
    """Map a FlagStatus value to the ledger dot color class.

    Open flags use the amber ``flag`` dot; approved/confirmed states use the
    green ``confirmed`` dot; rejected states use the brick-red ``rejected`` dot.
    """
    mapping = {
        FlagStatus.OPEN: "flag",
        FlagStatus.APPROVED: "confirmed",
        FlagStatus.REJECTED: "rejected",
    }
    return mapping.get(status, "flag")
