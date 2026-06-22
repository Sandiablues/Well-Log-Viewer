"""Concise numeric display label formatter for WDV curve-scale values.

Policy (all rules apply in order):

1.  Preserve the original numeric value unchanged everywhere except the label.
2.  Convert through decimal string representation (``repr(value)``), never
    binary string truncation of the float.
3.  Normalise signed zero (``-0.0``) to ``"0"``.
4.  Round to 3 significant figures using ``decimal.ROUND_HALF_UP``.
5.  Strip insignificant trailing fractional zeros; strip a trailing decimal
    point if nothing remains after stripping.
6.  Significant integer zeros are preserved naturally (e.g. ``150.0 → "150"``).
7.  Use fixed-point notation when ``0.001 <= abs(rounded_value) < 10_000_000``.
    The boundary is evaluated against the **rounded** value, not the original.
8.  Use scientific notation outside that range.
9.  Non-finite values must never reach this formatter — upstream validation
    (``FiniteNumber`` / ``allow_inf_nan=False``) is the authoritative gate.
    A ``ValueError`` is raised here as a secondary defence; it must never
    fire in production.
"""

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation


def format_scale_value(value: float) -> str:
    """Return a concise display label for a finite scale value.

    Args:
        value: A finite floating-point scale limit.

    Returns:
        A concise string representation rounded to 3 significant figures.

    Raises:
        ValueError: If *value* is non-finite (should never occur in production).
    """
    if not math.isfinite(value):
        raise ValueError(
            f"Non-finite scale value must not reach the formatter: {value!r}"
        )

    # Rule 3: normalise signed zero.
    if value == 0.0:
        return "0"

    # Rule 2: convert through decimal string representation.
    try:
        d = Decimal(repr(value))
    except InvalidOperation as exc:  # pragma: no cover — guarded above
        raise ValueError(f"Cannot convert {value!r} to Decimal") from exc

    abs_d = abs(d)

    # Rule 4: round to 3 significant figures.
    # floor(log10(abs_d)) gives the exponent of the most-significant digit.
    # e.g. 38.86    → log_val=1 → places=-(1-2)=1  → quantizer=1E-1 (0.1)  → 38.9
    #      -2.05    → log_val=0 → places=-(0-2)=2  → quantizer=1E-2 (0.01) → -2.05
    #      150.0    → log_val=2 → places=-(2-2)=0  → quantizer=1E0  (1)    → 150
    #      9994999  → log_val=6 → places=-(6-2)=-4 → quantizer=1E4  (10000)→ 9990000
    # IMPORTANT: use Decimal(f"1E{n}") so the quantizer carries the correct
    # decimal exponent.  Decimal(10)**4 == Decimal('10000') has exponent 0 and
    # would round to the nearest integer, not the nearest 10 000.
    log_val = math.floor(math.log10(float(abs_d)))
    places = -(log_val - 2)
    quantizer = Decimal(f"1E{-places}")
    rounded = d.quantize(quantizer, rounding=ROUND_HALF_UP)

    # Rule 7/8: notation boundary evaluated against the rounded value.
    abs_rounded = abs(float(rounded))

    if abs_rounded == 0.0:
        # Rounded to zero (extremely rare for realistic scale limits).
        return "0"

    if 0.001 <= abs_rounded < 10_000_000:
        # Rules 5 & 6: fixed-point, strip trailing fractional zeros.
        formatted = format(rounded, "f")
        if "." in formatted:
            formatted = formatted.rstrip("0").rstrip(".")
        return formatted

    # Rule 8: scientific notation for very small or very large values.
    return f"{float(rounded):.2e}"
