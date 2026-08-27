import hashlib
import json
import unicodedata
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


def text_key(value: Any) -> str:
    if value is None:
        return ""
    value = unicodedata.normalize("NFKC", str(value)).replace("\u00a0", " ")
    return " ".join(value.strip().split()).casefold()


def original_text(value: Any) -> str:
    return "" if value is None else " ".join(str(value).replace("\u00a0", " ").strip().split())


def account_key(value: Any) -> str:
    value = original_text(value)
    return value[:-2] if value.endswith(".0") and value[:-2].isdigit() else value


def money(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0.00")
    if isinstance(value, float):
        value = str(value)
    value = str(value).replace("\u00a0", "").replace(" ", "").replace(",", ".")
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def stable_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(encoded.encode()).hexdigest()
