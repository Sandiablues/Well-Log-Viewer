"""Backend-owned unit contract for governed WDV display-policy values.

This module is intentionally narrow.  It normalizes the unit tokens currently
used by WLV display-policy records and managed curves, then converts policy
bounds into the actual curve unit.  It is not a general engineering-units
framework.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math


class UnitConversionStatus(Enum):
    """Typed outcome of a policy-unit conversion request."""

    RESOLVED = "resolved"
    UNKNOWN_SOURCE_UNIT = "unknown_source_unit"
    UNKNOWN_TARGET_UNIT = "unknown_target_unit"
    INCOMPATIBLE_DIMENSIONS = "incompatible_dimensions"
    UNSUPPORTED_CONVERSION = "unsupported_conversion"
    NON_FINITE_VALUE = "non_finite_value"


@dataclass(frozen=True)
class UnitConversionResult:
    """Result of converting one numeric value between canonical units."""

    status: UnitConversionStatus
    value: float | None = None
    source_unit: str | None = None
    target_unit: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class UnitBoundsConversionResult:
    """Result of converting display-policy minimum and maximum bounds."""

    status: UnitConversionStatus
    minimum: float | None = None
    maximum: float | None = None
    source_unit: str | None = None
    target_unit: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class _UnitDefinition:
    dimension: str
    # Canonical value = input * scale + offset.
    scale_to_canonical: float = 1.0
    offset_to_canonical: float = 0.0


class WdvPolicyUnitContract:
    """Normalize and convert units used by WDV governed display policies.

    Canonical token normalization is separate from numeric conversion.  Every
    conversion is deterministic and dimension checked.  Unknown or unsupported
    requests fail explicitly; callers must never apply raw policy values after
    a failed conversion.
    """

    # Alias keys are normalized by ``_alias_key`` before lookup.
    _ALIASES: dict[str, str] = {
        # Dimensionless / porosity.
        "%": "%",
        "percent": "%",
        "pct": "%",
        "pu": "%",
        "p.u.": "%",
        "v/v": "v/v",
        "v_v": "v/v",
        "fraction": "v/v",
        "frac": "v/v",
        # Gamma ray.
        "gapi": "gapi",
        "api": "gapi",
        # Electrical potential.
        "mv": "mv",
        "millivolt": "mv",
        "millivolts": "mv",
        # Length.
        "in": "in",
        "inch": "in",
        "inches": "in",
        "mm": "mm",
        "millimeter": "mm",
        "millimeters": "mm",
        "millimetre": "mm",
        "millimetres": "mm",
        "cm": "cm",
        "centimeter": "cm",
        "centimeters": "cm",
        "centimetre": "cm",
        "centimetres": "cm",
        # Resistivity.
        "ohmm": "ohmm",
        "ohm.m": "ohmm",
        "ohm-m": "ohmm",
        "ohm*m": "ohmm",
        "ohm_m": "ohmm",
        "ohm m": "ohmm",
        # Density.
        "g/cc": "g/cc",
        "g/cm3": "g/cc",
        "g/cm^3": "g/cc",
        "gcc": "g/cc",
        "g/c3": "g/cc",
        "kg/m3": "kg/m3",
        "kg/m^3": "kg/m3",
        # Sonic slowness.
        "us/ft": "us/ft",
        "us/f": "us/ft",
        "µs/ft": "us/ft",
        "μs/ft": "us/ft",
        "usec/ft": "us/ft",
        "us/m": "us/m",
        "µs/m": "us/m",
        "μs/m": "us/m",
        "usec/m": "us/m",
        # Photoelectric factor.
        "b/e": "b/e",
        "barn/e": "b/e",
        "barns/e": "b/e",
        "barn/electron": "b/e",
        # Permeability.
        "md": "md",
        "millidarcy": "md",
        "millidarcies": "md",
        # Pressure.
        "psi": "psi",
        "kpa": "kpa",
        "bar": "bar",
        # Temperature.
        "degc": "degc",
        "°c": "degc",
        "celsius": "degc",
        "degf": "degf",
        "°f": "degf",
        "fahrenheit": "degf",
        # Spinner / rotational speed (identity only for now).
        "rpm": "rpm",
    }

    # Canonical-base choices:
    # - length: mm
    # - density: kg/m3
    # - slowness: us/m
    # - pressure: kPa
    # - temperature: degC
    _UNITS: dict[str, _UnitDefinition] = {
        "%": _UnitDefinition("fraction", 0.01, 0.0),
        "v/v": _UnitDefinition("fraction", 1.0, 0.0),
        "gapi": _UnitDefinition("gamma_ray"),
        "mv": _UnitDefinition("electric_potential"),
        "in": _UnitDefinition("length", 25.4, 0.0),
        "mm": _UnitDefinition("length", 1.0, 0.0),
        "cm": _UnitDefinition("length", 10.0, 0.0),
        "ohmm": _UnitDefinition("resistivity"),
        "g/cc": _UnitDefinition("density", 1000.0, 0.0),
        "kg/m3": _UnitDefinition("density", 1.0, 0.0),
        "us/ft": _UnitDefinition("slowness", 3.280839895013123, 0.0),
        "us/m": _UnitDefinition("slowness", 1.0, 0.0),
        "b/e": _UnitDefinition("photoelectric_factor"),
        "md": _UnitDefinition("permeability"),
        "psi": _UnitDefinition("pressure", 6.894757293168361, 0.0),
        "kpa": _UnitDefinition("pressure", 1.0, 0.0),
        "bar": _UnitDefinition("pressure", 100.0, 0.0),
        "degc": _UnitDefinition("temperature", 1.0, 0.0),
        "degf": _UnitDefinition("temperature", 5.0 / 9.0, -32.0 * 5.0 / 9.0),
        "rpm": _UnitDefinition("rotational_speed"),
    }

    @classmethod
    def normalize_unit(cls, raw_unit: object) -> str | None:
        """Return a canonical unit token, or ``None`` when unknown/blank."""

        if raw_unit is None:
            return None
        text = str(raw_unit).strip()
        if not text:
            return None
        return cls._ALIASES.get(cls._alias_key(text))

    @classmethod
    def convert_value(
        cls,
        value: object,
        *,
        source_unit: object,
        target_unit: object,
    ) -> UnitConversionResult:
        """Convert one finite numeric value from source to target unit."""

        source = cls.normalize_unit(source_unit)
        if source is None:
            return UnitConversionResult(
                status=UnitConversionStatus.UNKNOWN_SOURCE_UNIT,
                reason="unknown_source_unit",
            )

        target = cls.normalize_unit(target_unit)
        if target is None:
            return UnitConversionResult(
                status=UnitConversionStatus.UNKNOWN_TARGET_UNIT,
                source_unit=source,
                reason="unknown_target_unit",
            )

        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return UnitConversionResult(
                status=UnitConversionStatus.NON_FINITE_VALUE,
                source_unit=source,
                target_unit=target,
                reason="value_not_numeric",
            )
        if not math.isfinite(numeric):
            return UnitConversionResult(
                status=UnitConversionStatus.NON_FINITE_VALUE,
                source_unit=source,
                target_unit=target,
                reason="value_not_finite",
            )

        source_def = cls._UNITS.get(source)
        target_def = cls._UNITS.get(target)
        if source_def is None:
            return UnitConversionResult(
                status=UnitConversionStatus.UNKNOWN_SOURCE_UNIT,
                source_unit=source,
                target_unit=target,
                reason="source_definition_missing",
            )
        if target_def is None:
            return UnitConversionResult(
                status=UnitConversionStatus.UNKNOWN_TARGET_UNIT,
                source_unit=source,
                target_unit=target,
                reason="target_definition_missing",
            )
        if source_def.dimension != target_def.dimension:
            return UnitConversionResult(
                status=UnitConversionStatus.INCOMPATIBLE_DIMENSIONS,
                source_unit=source,
                target_unit=target,
                reason="incompatible_dimensions",
            )
        if target_def.scale_to_canonical == 0:
            return UnitConversionResult(
                status=UnitConversionStatus.UNSUPPORTED_CONVERSION,
                source_unit=source,
                target_unit=target,
                reason="target_scale_zero",
            )

        canonical_value = (
            numeric * source_def.scale_to_canonical
            + source_def.offset_to_canonical
        )
        converted = (
            canonical_value - target_def.offset_to_canonical
        ) / target_def.scale_to_canonical

        return UnitConversionResult(
            status=UnitConversionStatus.RESOLVED,
            value=converted,
            source_unit=source,
            target_unit=target,
        )

    @classmethod
    def convert_bounds(
        cls,
        minimum: object,
        maximum: object,
        *,
        source_unit: object,
        target_unit: object,
    ) -> UnitBoundsConversionResult:
        """Convert both policy bounds, preserving their original ordering."""

        low = cls.convert_value(
            minimum,
            source_unit=source_unit,
            target_unit=target_unit,
        )
        if low.status is not UnitConversionStatus.RESOLVED:
            return UnitBoundsConversionResult(
                status=low.status,
                source_unit=low.source_unit,
                target_unit=low.target_unit,
                reason=low.reason,
            )

        high = cls.convert_value(
            maximum,
            source_unit=source_unit,
            target_unit=target_unit,
        )
        if high.status is not UnitConversionStatus.RESOLVED:
            return UnitBoundsConversionResult(
                status=high.status,
                source_unit=high.source_unit,
                target_unit=high.target_unit,
                reason=high.reason,
            )

        return UnitBoundsConversionResult(
            status=UnitConversionStatus.RESOLVED,
            minimum=low.value,
            maximum=high.value,
            source_unit=low.source_unit,
            target_unit=low.target_unit,
        )

    @staticmethod
    def _alias_key(value: str) -> str:
        return " ".join(value.strip().lower().split())
