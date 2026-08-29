"""CSV amount normalization: strips currency symbols and picks precision."""

import re
from decimal import Decimal, InvalidOperation

CURRENCY_RE = re.compile(r"[^\d.,-]")
PLURAL_WORDS = {"usd", "eur", "gbp", "cents", "cent"}


def normalize_amount(raw: str) -> Decimal:
    cleaned = CURRENCY_RE.sub("", raw.strip().lower())
    for word in PLURAL_WORDS:
        cleaned = cleaned.replace(word, "")
    cleaned = cleaned.strip().rstrip(".")
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"unparseable amount: {raw!r}") from exc


def row_amount(row: dict, field: str = "amount") -> Decimal:
    value = row.get(field)
    if value is None:
        raise KeyError(f"missing field: {field}")
    if isinstance(value, Decimal):
        return value
    return normalize_amount(str(value))
