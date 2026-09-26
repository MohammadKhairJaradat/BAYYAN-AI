"""Exact JOD amounts for new financial contracts."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN

FILS = Decimal("0.001")
RATE_PRECISION = Decimal("0.000001")
MAX_STORED_MONEY = Decimal("999999999999.999")


def parse_money(value: Decimal | str | int) -> Decimal:
    """Accept exact representations; floats are forbidden on the new path."""
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError("Money must be a decimal string, integer or Decimal")
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError):
        raise ValueError("Invalid money amount") from None
    if not amount.is_finite() or amount < 0:
        raise ValueError("Money amount must be finite and non-negative")
    if amount > MAX_STORED_MONEY:
        raise ValueError("Money amount exceeds the supported storage range")
    if amount != amount.quantize(FILS):
        raise ValueError("Money amount cannot have more than three decimal places")
    return amount


def format_money(value: Decimal) -> str:
    return format(value.quantize(FILS, rounding=ROUND_HALF_EVEN), ".3f")


def format_legacy_amount(value: Decimal) -> str:
    """Keep two-digit legacy JSON until a nonzero fil requires a third digit."""
    cents = Decimal("0.01")
    if value == value.quantize(cents):
        return format(value, ".2f")
    return format_money(value)


def format_rate(value: Decimal) -> str:
    return format(value.quantize(RATE_PRECISION, rounding=ROUND_HALF_EVEN), ".6f")
