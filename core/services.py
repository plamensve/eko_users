"""Business rules for pricing and invoice reports.

This module intentionally contains no pandas or presentation code.  Keeping the
calculation rules here makes the web UI, Excel export and PDF export use exactly
the same values.
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_EVEN, ROUND_HALF_UP


ZERO = Decimal("0")
PRICE_STEP = Decimal("0.001")
MONEY_STEP = Decimal("0.01")
AMOUNT_STEP = Decimal("0.001")
QTY_STEP = Decimal("0.01")
QTY_CALC_STEP = Decimal("0.000001")
PROFIT_STEP = Decimal("0.000001")
E_GAS_LPG_BASE_PROFIT_PER_LITER = Decimal("0.015")


def as_decimal(value, default=ZERO):
    if value is None or value == "":
        return default
    try:
        return Decimal(str(value))
    except (ValueError, TypeError, ArithmeticError):
        return default


def round3(value):
    """Match pandas .round(3) used by the verified EKO pipeline."""
    return as_decimal(value).quantize(PRICE_STEP, rounding=ROUND_HALF_EVEN)


def price3(value):
    """Final GTA price: truncate to three decimals exactly like the EKO pipeline."""
    return max(as_decimal(value), ZERO).quantize(PRICE_STEP, rounding=ROUND_DOWN)


def amount3(value):
    """Transaction amount precision used by the verified EKO pipeline."""
    return as_decimal(value).quantize(AMOUNT_STEP, rounding=ROUND_HALF_EVEN)


def profit6(value):
    """Profit precision used by the verified EKO pipeline."""
    return as_decimal(value).quantize(PROFIT_STEP, rounding=ROUND_HALF_EVEN)


def quantity6(value):
    """Calculation quantity precision used by the verified EKO pipeline."""
    return as_decimal(value).quantize(QTY_CALC_STEP, rounding=ROUND_HALF_EVEN)


def money2(value):
    """Two-decimal presentation helper retained for non-calculation callers."""
    return as_decimal(value).quantize(MONEY_STEP, rounding=ROUND_HALF_UP)


def quantity2(value):
    """Two-decimal presentation helper retained for non-calculation callers."""
    return as_decimal(value).quantize(QTY_STEP, rounding=ROUND_HALF_UP)


def normalize_product_key(value):
    """Normalize visually identical Latin/Cyrillic letters in product names."""
    text = " ".join(str(value or "").upper().split())
    return text.translate(str.maketrans({
        "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M",
        "Н": "H", "О": "O", "Р": "P", "С": "C", "Т": "T", "Х": "X",
    }))


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
    # The verified notebook rounds transaction/base prices, margin and discount
    # to three decimals before applying the business rules. Quantities keep six
    # decimals for calculations. Only the final GTA unit price is truncated.
    qty = quantity6(quantity)
    eko_price = round3(transaction_price)
    margin = round3(getattr(price_record, "margin", ZERO))
    discount = round3(getattr(price_record, "discount", ZERO))
    negotiated = getattr(price_record, "final_price", None)
    base_source = getattr(price_record, "eko_price", None)
    base = round3(eko_price if base_source is None else base_source)

    if margin > ZERO:
        gta_price = price3(base + margin)
    elif discount > ZERO:
        gta_price = price3(max(eko_price - discount, ZERO))
    elif negotiated is not None:
        gta_price = price3(negotiated)
    else:
        gta_price = price3(eko_price)

    normalized_product = normalize_product_key(product)
    if normalized_product == "E GAS LPG":
        # Rule from the reference EKO pipeline.
        profit = (E_GAS_LPG_BASE_PROFIT_PER_LITER - discount) * qty
    elif margin > ZERO:
        profit = margin * qty
    elif discount > ZERO:
        profit = (eko_price - discount - base) * qty
    else:
        profit = (gta_price - base) * qty

    return PricingResult(
        gta_price=gta_price,
        eko_base_price=base,
        discount=discount,
        margin=margin,
        eko_total=amount3(qty * eko_price),
        gta_total=amount3(qty * gta_price),
        profit=profit6(profit),
    )
