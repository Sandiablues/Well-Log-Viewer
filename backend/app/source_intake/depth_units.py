"""Governed depth-unit parsing and normalization for source intake.

This module interprets engineering depth units, including scaled encodings used
by DLIS frame indices. It never guesses an unknown unit. Metric-family depths
normalize to metres; imperial-family depths normalize to feet. The original
unit token and scale remain available for provenance.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
import unicodedata


@dataclass(frozen=True)
class DepthUnitConversion:
    factor: float | None
    normalized_unit: str | None
    raw_unit: str | None
    scale: float | None
    base_unit: str | None
    status: str
    reason: str | None = None

    @property
    def supported(self) -> bool:
        return self.status == "supported" and self.factor is not None

    def convert(self, value: float) -> float:
        if not self.supported:
            raise UnsupportedDepthUnitError(self.reason or "Unsupported depth unit")
        return float(value) * float(self.factor)


class UnsupportedDepthUnitError(ValueError):
    """Raised when a source depth unit cannot be normalized safely."""


_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
_FRACTION = rf"(?:{_NUMBER})\s*/\s*(?:{_NUMBER})"
_SCALED_UNIT = re.compile(
    rf"^(?:(?P<scale>{_NUMBER}|{_FRACTION})\s*(?:\*|x|×)?\s*)?(?P<unit>[a-zA-Zµμ]+)$",
    re.IGNORECASE,
)

# Canonical base-unit definitions: alias -> (canonical base, target unit, factor)
_UNIT_DEFINITIONS: dict[str, tuple[str, str, float]] = {}


def _register(canonical: str, target: str, factor: float, aliases: tuple[str, ...]) -> None:
    for alias in aliases:
        _UNIT_DEFINITIONS[alias] = (canonical, target, factor)


# Metric family normalizes to metres.
_register("nm", "m", 1e-9, ("nm", "nanometer", "nanometre", "nanometers", "nanometres"))
_register("um", "m", 1e-6, ("um", "µm", "μm", "micrometer", "micrometre", "micrometers", "micrometres"))
_register("mm", "m", 1e-3, ("mm", "millimeter", "millimetre", "millimeters", "millimetres"))
_register("cm", "m", 1e-2, ("cm", "centimeter", "centimetre", "centimeters", "centimetres"))
_register("dm", "m", 1e-1, ("dm", "decimeter", "decimetre", "decimeters", "decimetres"))
_register("m", "m", 1.0, ("m", "meter", "metre", "meters", "metres"))
_register("km", "m", 1e3, ("km", "kilometer", "kilometre", "kilometers", "kilometres"))

# Imperial family normalizes to feet.
_register("mil", "ft", 1.0 / 12000.0, ("mil", "mils"))
_register("in", "ft", 1.0 / 12.0, ("in", "inch", "inches"))
_register("ft", "ft", 1.0, ("ft", "foot", "feet"))
_register("yd", "ft", 3.0, ("yd", "yard", "yards"))


def _clean_token(value: object) -> str | None:
    if value is None:
        return None
    token = unicodedata.normalize("NFKC", str(value)).strip()
    token = re.sub(r"\s+", " ", token)
    return token or None


def _parse_scale(token: str | None) -> float:
    if token is None:
        return 1.0
    if "/" in token:
        numerator, denominator = token.split("/", 1)
        denominator_value = float(denominator.strip())
        if denominator_value == 0:
            raise ValueError("depth-unit scale denominator is zero")
        return float(numerator.strip()) / denominator_value
    return float(token)


def depth_unit_conversion(unit: object) -> DepthUnitConversion:
    raw = _clean_token(unit)
    if raw is None:
        return DepthUnitConversion(
            factor=None, normalized_unit=None, raw_unit=None, scale=None,
            base_unit=None, status="unsupported", reason="missing_depth_unit",
        )

    compact = raw.replace(" ", "")
    match = _SCALED_UNIT.fullmatch(compact)
    if match is None:
        return DepthUnitConversion(
            factor=None, normalized_unit=None, raw_unit=raw, scale=None,
            base_unit=None, status="unsupported", reason="malformed_depth_unit",
        )

    try:
        scale = _parse_scale(match.group("scale"))
    except (TypeError, ValueError, OverflowError):
        return DepthUnitConversion(
            factor=None, normalized_unit=None, raw_unit=raw, scale=None,
            base_unit=None, status="unsupported", reason="invalid_depth_scale",
        )

    if not math.isfinite(scale) or scale <= 0:
        return DepthUnitConversion(
            factor=None, normalized_unit=None, raw_unit=raw, scale=scale,
            base_unit=None, status="unsupported", reason="nonpositive_depth_scale",
        )

    alias = match.group("unit").casefold()
    definition = _UNIT_DEFINITIONS.get(alias)
    if definition is None:
        return DepthUnitConversion(
            factor=None, normalized_unit=None, raw_unit=raw, scale=scale,
            base_unit=alias, status="unsupported", reason="unknown_depth_unit",
        )

    canonical, target, base_factor = definition
    return DepthUnitConversion(
        factor=scale * base_factor,
        normalized_unit=target,
        raw_unit=raw,
        scale=scale,
        base_unit=canonical,
        status="supported",
    )


def require_depth_unit_conversion(unit: object) -> DepthUnitConversion:
    conversion = depth_unit_conversion(unit)
    if not conversion.supported:
        raise UnsupportedDepthUnitError(
            f"Cannot normalize depth unit {conversion.raw_unit!r}: {conversion.reason}"
        )
    return conversion


def is_canonical_depth_unit(unit: object) -> bool:
    raw = _clean_token(unit)
    if raw is None:
        return False
    return raw.casefold() in {"m", "meter", "metre", "meters", "metres", "ft", "foot", "feet"}


def requires_human_target_unit(unit: object) -> bool:
    conversion = depth_unit_conversion(unit)
    return conversion.supported and not is_canonical_depth_unit(unit)


def convert_depth_to_target(value: float, unit: object, target_unit: str) -> float:
    conversion = require_depth_unit_conversion(unit)
    target = str(target_unit).strip().casefold()
    physical_ft = float(value) * float(conversion.factor) if conversion.normalized_unit == "ft" else float(value) * float(conversion.factor) / 0.3048
    if target == "ft":
        return physical_ft
    if target == "m":
        return physical_ft * 0.3048
    raise UnsupportedDepthUnitError(f"Unsupported target depth unit: {target_unit!r}")
