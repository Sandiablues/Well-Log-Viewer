"""Backend-owned depth-reference contracts for WLV.

Raw source indices remain immutable provenance.  Every managed source owns a
source-native normalized depth contract, while every managed well owns one
canonical WDV display unit.  Conversion occurs only at managed aggregation and
sample/render boundaries.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, Iterable, Mapping

CONTRACT_VERSION = "wlv_depth_reference_v1"
_CANONICAL = {"m": "m", "meter": "m", "metre": "m", "meters": "m", "metres": "m",
              "ft": "ft", "f": "ft", "foot": "ft", "feet": "ft"}
_BASE_TO_M = {
    "nm": 1e-9, "um": 1e-6, "µm": 1e-6, "μm": 1e-6,
    "mm": 1e-3, "cm": 1e-2, "dm": 1e-1,
    "m": 1.0, "meter": 1.0, "metre": 1.0, "meters": 1.0, "metres": 1.0,
    "km": 1e3,
    "mil": 0.0000254, "mils": 0.0000254,
    "in": 0.0254, "inch": 0.0254, "inches": 0.0254,
    "ft": 0.3048, "f": 0.3048, "foot": 0.3048, "feet": 0.3048,
    "yd": 0.9144, "yard": 0.9144, "yards": 0.9144,
}
_SCALED = re.compile(r"^\s*(?:(?P<scale>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(?:\*|x|×)?\s*)?(?P<unit>[A-Za-zµμ]+)\s*$")


class DepthReferenceError(ValueError):
    """Raised when a depth reference cannot be resolved without guessing."""


@dataclass(frozen=True)
class DepthRange:
    minimum: float
    maximum: float
    unit: str

    def __post_init__(self) -> None:
        if self.unit not in {"m", "ft"}:
            raise DepthReferenceError(f"Unsupported canonical depth unit: {self.unit!r}")
        if not math.isfinite(self.minimum) or not math.isfinite(self.maximum):
            raise DepthReferenceError("Depth range must be finite")
        if self.maximum < self.minimum:
            raise DepthReferenceError("Depth range maximum is less than minimum")


def canonical_depth_unit(unit: object) -> str | None:
    token = str(unit or "").strip().casefold()
    return _CANONICAL.get(token)


def _factor_to_metres(unit: object) -> float:
    token = str(unit or "").strip()
    match = _SCALED.fullmatch(token)
    if match is None:
        raise DepthReferenceError(f"Unsupported depth unit: {unit!r}")
    scale = float(match.group("scale") or 1.0)
    base = match.group("unit").casefold()
    factor = _BASE_TO_M.get(base)
    if factor is None or not math.isfinite(scale) or scale <= 0:
        raise DepthReferenceError(f"Unsupported depth unit: {unit!r}")
    return scale * factor


def convert_depth(value: float, source_unit: object, target_unit: object) -> float:
    target = canonical_depth_unit(target_unit)
    if target is None:
        raise DepthReferenceError(f"Unsupported target depth unit: {target_unit!r}")
    metres = float(value) * _factor_to_metres(source_unit)
    return metres if target == "m" else metres / 0.3048


def convert_range(minimum: float, maximum: float, source_unit: object, target_unit: object) -> DepthRange:
    converted = sorted((convert_depth(minimum, source_unit, target_unit), convert_depth(maximum, source_unit, target_unit)))
    target = canonical_depth_unit(target_unit)
    assert target is not None
    return DepthRange(converted[0], converted[1], target)


def make_source_depth_contract(
    *,
    raw_unit: object,
    raw_minimum: float | None,
    raw_maximum: float | None,
    normalized_unit: object,
    normalized_minimum: float | None,
    normalized_maximum: float | None,
    basis: str,
    decision: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    unit = canonical_depth_unit(normalized_unit)
    if unit is None:
        raise DepthReferenceError(f"Source-native normalized unit must be m or ft, got {normalized_unit!r}")
    if normalized_minimum is None or normalized_maximum is None:
        raise DepthReferenceError("Source-native normalized range is incomplete")
    ordered = sorted((float(normalized_minimum), float(normalized_maximum)))
    if not all(math.isfinite(value) for value in ordered):
        raise DepthReferenceError("Source-native normalized range is non-finite")
    return {
        "contract_version": CONTRACT_VERSION,
        "raw": {
            "unit": str(raw_unit).strip() if raw_unit is not None else None,
            "minimum": float(raw_minimum) if raw_minimum is not None else None,
            "maximum": float(raw_maximum) if raw_maximum is not None else None,
        },
        "source_native": {
            "unit": unit,
            "minimum": ordered[0],
            "maximum": ordered[1],
        },
        "normalization": {
            "basis": str(basis),
            "decision": dict(decision) if decision else None,
        },
    }


def source_contract_from_metadata(
    metadata: Mapping[str, Any] | None,
    *,
    fallback_target_unit: object | None = None,
) -> dict[str, Any] | None:
    payload = dict(metadata or {})
    current = payload.get("depth_reference") or payload.get("depth_contract")
    if isinstance(current, dict) and current.get("contract_version") == CONTRACT_VERSION:
        native = current.get("source_native")
        if isinstance(native, dict) and canonical_depth_unit(native.get("unit")):
            return current

    parsed = payload.get("parsed_metadata")
    if not isinstance(parsed, dict):
        return None
    log_header = parsed.get("log_header")
    if not isinstance(log_header, dict):
        return None
    start = log_header.get("start_depth")
    stop = log_header.get("stop_depth")
    unit = log_header.get("depth_unit")
    canonical = canonical_depth_unit(unit)
    if start is None or stop is None:
        return None
    if canonical is not None:
        return make_source_depth_contract(
            raw_unit=unit,
            raw_minimum=float(start),
            raw_maximum=float(stop),
            normalized_unit=canonical,
            normalized_minimum=float(start),
            normalized_maximum=float(stop),
            basis="source_native",
        )
    target = canonical_depth_unit(fallback_target_unit)
    if target is None:
        return None
    try:
        normalized = convert_range(float(start), float(stop), unit, target)
    except DepthReferenceError:
        return None
    return make_source_depth_contract(
        raw_unit=unit,
        raw_minimum=float(start),
        raw_maximum=float(stop),
        normalized_unit=target,
        normalized_minimum=normalized.minimum,
        normalized_maximum=normalized.maximum,
        basis="managed_well_reference",
    )


def source_native_range(contract: Mapping[str, Any]) -> DepthRange:
    native = contract.get("source_native")
    if not isinstance(native, Mapping):
        raise DepthReferenceError("Source depth contract has no source_native section")
    unit = canonical_depth_unit(native.get("unit"))
    if unit is None:
        raise DepthReferenceError("Source depth contract has an invalid source-native unit")
    return DepthRange(float(native["minimum"]), float(native["maximum"]), unit)


def choose_canonical_well_unit(
    *,
    existing_contract: Mapping[str, Any] | None,
    existing_well_unit: object,
    source_contracts: Iterable[Mapping[str, Any]],
    preferred_unit: object | None = None,
) -> str:
    if isinstance(existing_contract, Mapping):
        unit = canonical_depth_unit(existing_contract.get("unit"))
        if unit:
            return unit
    preferred = canonical_depth_unit(preferred_unit)
    if preferred:
        return preferred
    existing = canonical_depth_unit(existing_well_unit)
    if existing:
        return existing

    contracts = list(source_contracts)
    human_units: list[str] = []
    for contract in contracts:
        normalization = contract.get("normalization")
        decision = normalization.get("decision") if isinstance(normalization, Mapping) else None
        unit = canonical_depth_unit(decision.get("target_unit")) if isinstance(decision, Mapping) else None
        if unit:
            human_units.append(unit)
    if human_units and len(set(human_units)) == 1:
        return human_units[0]
    native_units = sorted({source_native_range(contract).unit for contract in contracts})
    if len(native_units) == 1:
        return native_units[0]
    raise DepthReferenceError(
        "Managed well has mixed source-native depth units and no explicit canonical well depth unit"
    )


def build_well_depth_contract(
    *,
    existing_contract: Mapping[str, Any] | None,
    existing_well_unit: object,
    source_contracts: Iterable[Mapping[str, Any]],
    preferred_unit: object | None = None,
) -> dict[str, Any]:
    contracts = list(source_contracts)
    if not contracts:
        raise DepthReferenceError("Managed well has no source depth contracts")
    unit = choose_canonical_well_unit(
        existing_contract=existing_contract,
        existing_well_unit=existing_well_unit,
        source_contracts=contracts,
        preferred_unit=preferred_unit,
    )
    converted = [
        convert_range(r.minimum, r.maximum, r.unit, unit)
        for r in (source_native_range(contract) for contract in contracts)
    ]
    return {
        "contract_version": CONTRACT_VERSION,
        "unit": unit,
        "minimum": min(item.minimum for item in converted),
        "maximum": max(item.maximum for item in converted),
        "source_contract_count": len(converted),
    }


def transform_sample_payload(
    parsed: Mapping[str, Any],
    *,
    source_contract: Mapping[str, Any] | None,
    target_unit: object,
) -> dict[str, Any]:
    target = canonical_depth_unit(target_unit)
    if target is None:
        raise DepthReferenceError(f"Invalid canonical WDV depth unit: {target_unit!r}")
    payload = dict(parsed)
    parsed_unit = payload.get("depth_unit")

    # The reader may return a raw scaled encoding (for example ``0.1 in``).
    # When that happens, the source contract is the only permitted authority
    # for normalization.  Otherwise the reader's canonical m/ft unit is used.
    source_unit: object = parsed_unit
    if source_contract is not None:
        raw = source_contract.get("raw")
        native = source_contract.get("source_native")
        raw_unit = raw.get("unit") if isinstance(raw, Mapping) else None
        native_unit = native.get("unit") if isinstance(native, Mapping) else None
        if raw_unit and str(parsed_unit or "").strip().casefold() == str(raw_unit).strip().casefold():
            source_unit = raw_unit
        elif canonical_depth_unit(parsed_unit) is None and native_unit:
            raise DepthReferenceError(
                f"Sample reader depth unit {parsed_unit!r} disagrees with managed source depth contract"
            )

    def convert(value: object) -> float:
        return convert_depth(float(value), source_unit, target)

    samples = payload.get("samples") or []
    payload["samples"] = [[convert(row[0]), float(row[1])] for row in samples]
    if payload.get("depth_min") is not None:
        payload["depth_min"] = convert(payload["depth_min"])
    if payload.get("depth_max") is not None:
        payload["depth_max"] = convert(payload["depth_max"])
    if payload.get("depth_min") is not None and payload.get("depth_max") is not None:
        payload["depth_min"], payload["depth_max"] = sorted((payload["depth_min"], payload["depth_max"]))
    payload["depth_unit"] = target
    payload["source_native_depth_unit"] = canonical_depth_unit(parsed_unit) or str(parsed_unit or "")
    return payload


def well_depth_contract_from_record(well: object) -> dict[str, Any]:
    metadata = getattr(well, "metadata", None)
    existing = metadata.get("depth_reference") if isinstance(metadata, dict) else None
    sources = list(getattr(well, "source_references", ()) or ())
    initial = [
        contract
        for contract in (source_contract_from_metadata(getattr(source, "metadata", None)) for source in sources)
        if contract is not None
    ]
    unit = choose_canonical_well_unit(
        existing_contract=existing if isinstance(existing, Mapping) else None,
        existing_well_unit=getattr(well, "depth_unit", None),
        source_contracts=initial,
    )
    complete = [
        contract
        for contract in (
            source_contract_from_metadata(getattr(source, "metadata", None), fallback_target_unit=unit)
            for source in sources
        )
        if contract is not None
    ]
    return build_well_depth_contract(
        existing_contract=existing if isinstance(existing, Mapping) else None,
        existing_well_unit=unit,
        source_contracts=complete,
    )
