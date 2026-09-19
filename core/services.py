"""Business rules for pricing and invoice reports.

This module intentionally contains no pandas or presentation code.  Keeping the
calculation rules here makes the web UI, Excel export and PDF export use exactly
the same values.
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP


ZERO = Decimal("0")
PRICE_STEP = Decimal("0.001")
MONEY_STEP = Decimal("0.01")
QTY_STEP = Decimal("0.01")


def as_decimal(value, default=ZERO):
    if value is None or value == "":
        return default
    try:
        return Decimal(str(value))
    except (ValueError, TypeError, ArithmeticError):
        return default


def price3(value):
    """Invoice price: three decimals, truncated like the reference pipeline."""
    return max(as_decimal(value), ZERO).quantize(PRICE_STEP, rounding=ROUND_DOWN)


def money2(value):
    return as_decimal(value).quantize(MONEY_STEP, rounding=ROUND_HALF_UP)


def quantity2(value):
    return as_decimal(value).quantize(QTY_STEP, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class PricingResult:
    gta_price: Decimal
    eko_base_price: Decimal
    discount: Decimal
    margin: Decimal
    eko_total: Decimal
    gta_total: Decimal
    profit: Decimal


def calculate_pricing(*, quantity, transaction_price, product, price_record=None):
    """Apply the rules from the original EKO processing notebooks.

    Priority is margin, discount, negotiated final price, transaction price.
    A price record is expected to be the latest record on or before the
    transaction date.
    """
    qty = quantity2(quantity)
    eko_price = as_decimal(transaction_price)
    margin = as_decimal(getattr(price_record, "margin", ZERO))
    discount = as_decimal(getattr(price_record, "discount", ZERO))
    negotiated = getattr(price_record, "final_price", None)
    base = as_decimal(getattr(price_record, "eko_price", None), eko_price)

    if margin > ZERO:
        gta_price = price3(base + margin)
    elif discount > ZERO:
        gta_price = price3(max(eko_price - discount, ZERO))
    elif negotiated is not None:
        gta_price = price3(negotiated)
    else:
        gta_price = price3(eko_price)

    normalized_product = " ".join(str(product or "").upper().split())
    if normalized_product in {"E GAS LPG", "Е GAS LPG", "Е GАS LPG"}:
        profit = (Decimal("0.015") - discount) * qty
    elif margin > ZERO:
        profit = margin * qty
    elif discount > ZERO:
        profit = (eko_price - discount - base) * qty
    else:
        profit = (gta_price - base) * qty

    return PricingResult(
        gta_price=gta_price,
        eko_base_price=price3(base),
        discount=price3(discount),
        margin=price3(margin),
        eko_total=money2(qty * eko_price),
        gta_total=money2(qty * gta_price),
        profit=money2(profit),
    )
