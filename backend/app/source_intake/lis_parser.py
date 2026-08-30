"""Native LIS79/LTI inspection for WLV Source Intake.

This parser is intentionally separate from the existing LAS and DLIS parsers.
It accepts both .lis and .lti containers, verifies content by attempting a
native dlisio.lis load, inventories every logical file and data-format
specification, and exposes scalar depth-indexed channels through the common WSI
metadata contract.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
import math

from .depth_units import (
    clean_depth_value,
    convert_depth_to_target,
    depth_unit_conversion,
    requires_human_target_unit,
)

try:
    from dlisio import lis
except ImportError as exc:  # pragma: no cover
    lis = None
    _LIS_IMPORT_ERROR = exc
else:
    _LIS_IMPORT_ERROR = None


class LisInspectionError(ValueError):
    pass


@dataclass(frozen=True)
class LisScalarChannel:
    logical_file_id: str
    log_set_id: str
    mnemonic: str
    description: str | None
    unit: str | None
    index_channel: str
    sample_count: int
    top_depth: float | None
    base_depth: float | None
    depth_unit: str | None
    raw_depth_unit: str | None = None
    depth_scale_factor: float | None = None
    depth_normalization_status: str = "supported"
    depth_normalization_reason: str | None = None
    raw_top_depth: float | None = None
    raw_base_depth: float | None = None
    curve_statistics: dict[str, Any] | None = None

    @property
    def source_curve_name(self) -> str:
        return f"{self.logical_file_id}|{self.log_set_id}|{self.mnemonic}"


@dataclass(frozen=True)
class LisChannelInventoryItem:
    logical_file_id: str
    log_set_id: str
    mnemonic: str
    description: str | None
    unit: str | None
    index_channel: str
    sample_count: int | None
    role: str
    supported: bool
    unsupported_reason: str | None = None
    raw_depth_unit: str | None = None
    depth_scale_factor: float | None = None
    normalized_depth_unit: str | None = None
    depth_normalization_status: str = "supported"
    depth_normalization_reason: str | None = None


@dataclass(frozen=True)
class LisInspection:
    parser_id: str
    source_format: str
    well_name: str | None
    uwi: str | None
    operator: str | None
    field: str | None
    service_company: str | None
    logical_file_count: int
    log_set_count: int
    scalar_channels: tuple[LisScalarChannel, ...]
    channel_inventory: tuple[LisChannelInventoryItem, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)


def inspect_lis(path: Path) -> LisInspection:
    if lis is None:
        raise LisInspectionError("LIS/LTI support requires the backend dependency 'dlisio'.") from _LIS_IMPORT_ERROR
    source = Path(path)
    if not source.is_file():
        raise LisInspectionError(f"LIS/LTI source file does not exist: {source}")

    scalar_channels: list[LisScalarChannel] = []
    inventory: list[LisChannelInventoryItem] = []
    warnings: list[str] = []
    logical_count = log_set_count = 0
    well_name = uwi = operator = field_name = service_company = None

    try:
        with lis.load(str(source)) as physical:
            logical_files = list(physical)
            logical_count = len(logical_files)
            if not logical_files:
                raise LisInspectionError("LIS/LTI physical file contains no logical files.")
            for logical_index, logical in enumerate(logical_files, start=1):
                logical_id = _logical_id(logical, logical_index)
                header_text = _safe_header_text(logical)
                well_name = well_name or _header_value(header_text, "WELL", "WELL NAME", "WN")
                uwi = uwi or _header_value(header_text, "UWI", "API", "WELL ID")
                operator = operator or _header_value(header_text, "COMP", "COMPANY", "OPERATOR")
                field_name = field_name or _header_value(header_text, "FIELD", "FLD")
                service_company = service_company or _header_value(header_text, "SERVICE COMPANY", "SRVC")

                specs = list(logical.data_format_specs())
                if not specs:
                    warnings.append(f"{logical_id}: logical file contains no data-format specifications.")
                    continue
                for spec_index, spec in enumerate(specs, start=1):
                    log_set_count += 1
                    log_set_id = _log_set_id(spec, spec_index)
                    try:
                        curves = lis.curves(logical, spec)
                    except Exception as exc:
                        warnings.append(f"{logical_id}/{log_set_id}: samples could not be read: {exc}")
                        continue
                    names = list(curves.dtype.names or ())
                    if not names:
                        warnings.append(f"{logical_id}/{log_set_id}: no curve fields were returned.")
                        continue
                    descriptors = _spec_descriptors(spec)
                    index_name = _index_name(spec, names, descriptors)
                    if index_name not in names:
                        warnings.append(f"{logical_id}/{log_set_id}: index channel {index_name!r} is unavailable.")
                        continue
                    index_desc = descriptors.get(index_name, {})
                    raw_depth_unit = _text(index_desc.get("unit"))
                    conversion = depth_unit_conversion(raw_depth_unit)
                    raw_top, raw_base = _numeric_range(curves[index_name])
                    review_required = requires_human_target_unit(raw_depth_unit)
                    if review_required:
                        top = base = depth_unit = None
                        status = "review_required"
                        reason = "Non-standard encoded depth unit requires a human target unit."
                    elif conversion.supported:
                        factor = conversion.factor or 1.0
                        top = conversion.convert(raw_top) if raw_top is not None else None
                        base = conversion.convert(raw_base) if raw_base is not None else None
                        depth_unit = conversion.normalized_unit
                        status = "supported"
                        reason = None
                    else:
                        top = base = depth_unit = None
                        status = "unsupported"
                        reason = conversion.reason
                    if status != "supported":
                        warnings.append(f"{logical_id}/{log_set_id}: index {index_name} uses unsupported or review-required depth unit {raw_depth_unit!r}.")

                    for name in names:
                        desc = descriptors.get(name, {})
                        role = "index" if name == index_name else "curve"
                        values = curves[name]
                        sample_count = len(values)
                        scalar = getattr(values.dtype, 'shape', ()) in ((), (1,))
                        supported = scalar and status == "supported"
                        unsupported_reason = None if supported else (reason or "non_scalar_channel")
                        item = LisChannelInventoryItem(
                            logical_file_id=logical_id, log_set_id=log_set_id,
                            mnemonic=name, description=_text(desc.get("description")),
                            unit=_text(desc.get("unit")), index_channel=index_name,
                            sample_count=sample_count, role=role, supported=supported,
                            unsupported_reason=unsupported_reason, raw_depth_unit=raw_depth_unit,
                            depth_scale_factor=conversion.factor if conversion.supported else None,
                            normalized_depth_unit=depth_unit,
                            depth_normalization_status=status,
                            depth_normalization_reason=reason,
                        )
                        inventory.append(item)
                        if role == "index" or not supported:
                            continue
                        stats = _statistics(values)
                        scalar_channels.append(LisScalarChannel(
                            logical_file_id=logical_id, log_set_id=log_set_id,
                            mnemonic=name, description=_text(desc.get("description")),
                            unit=_text(desc.get("unit")), index_channel=index_name,
                            sample_count=sample_count, top_depth=top, base_depth=base,
                            depth_unit=depth_unit, raw_depth_unit=raw_depth_unit,
                            depth_scale_factor=conversion.factor if conversion.supported else None,
                            depth_normalization_status=status, depth_normalization_reason=reason,
                            raw_top_depth=raw_top, raw_base_depth=raw_base,
                            curve_statistics=stats,
                        ))
    except LisInspectionError:
        raise
    except Exception as exc:
        raise LisInspectionError(f"LIS/LTI inspection failed: {exc}") from exc

    return LisInspection(
        parser_id="lis79_logset_channel_adapter_v1", source_format="LIS",
        well_name=well_name, uwi=uwi, operator=operator, field=field_name,
        service_company=service_company, logical_file_count=logical_count,
        log_set_count=log_set_count, scalar_channels=tuple(scalar_channels),
        channel_inventory=tuple(inventory), warnings=tuple(warnings),
    )


def _logical_id(logical: Any, index: int) -> str:
    for attr in ("name", "id"):
        value = _text(getattr(logical, attr, None))
        if value: return value
    return f"logical_file_{index}"


def _log_set_id(spec: Any, index: int) -> str:
    for attr in ("name", "id", "sequence_number"):
        value = _text(getattr(spec, attr, None))
        if value: return value
    return f"log_set_{index}"


def _safe_header_text(logical: Any) -> str:
    try:
        return "\n".join(str(item) for item in logical.header())
    except Exception:
        return ""


def _header_value(text: str, *labels: str) -> str | None:
    upper = text.upper()
    for label in labels:
        token = label.upper()
        pos = upper.find(token)
        if pos < 0: continue
        line = text[pos:].splitlines()[0]
        for sep in ("=", ":"):
            if sep in line:
                value = line.split(sep, 1)[1].strip(" \t'\"")
                if value: return value[:200]
    return None


def _spec_descriptors(spec: Any) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    candidates = getattr(spec, "specs", None) or getattr(spec, "entries", None) or ()
    for item in candidates:
        name = _text(getattr(item, "mnemonic", None) or getattr(item, "name", None))
        if not name: continue
        result[name] = {
            "unit": getattr(item, "units", None) or getattr(item, "unit", None),
            "description": getattr(item, "description", None) or getattr(item, "long_name", None),
        }
    return result


def _index_name(spec: Any, names: list[str], descriptors: dict[str, dict[str, Any]]) -> str:
    for attr in ("index_mnemonic", "index", "depth_mnemonic"):
        raw = getattr(spec, attr, None)
        if hasattr(raw, "mnemonic"): raw = getattr(raw, "mnemonic")
        value = _text(raw)
        if value and value in names: return value
    for name in names:
        if name.upper() in {"DEPT", "DEPTH", "MD", "TDEP"}: return name
    return names[0]


def _numeric_range(values: Iterable[Any]) -> tuple[float | None, float | None]:
    clean = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number): clean.append(number)
    return (min(clean), max(clean)) if clean else (None, None)


def _statistics(values: Iterable[Any]) -> dict[str, Any]:
    clean = []
    for value in values:
        try: number = float(value)
        except (TypeError, ValueError): continue
        if math.isfinite(number): clean.append(number)
    if not clean: return {"valid_count": 0}
    return {"valid_count": len(clean), "minimum": min(clean), "maximum": max(clean)}


def _text(value: Any) -> str | None:
    if value is None: return None
    text = str(value).strip()
    return text or None


# LIS / LTI WDV CURVE SAMPLES V1.0.0

def read_lis_curve_samples(
    *,
    source_path: Path,
    curve_mnemonic: str,
    max_samples: int,
    source_curve_name: str | None = None,
    logical_file_id: str | None = None,
    log_set_id: str | None = None,
    target_depth_unit: str | None = None,
) -> dict[str, Any]:
    """Read one scalar LIS/LTI channel for WDV rendering.

    The Source Intake inventory records a stable composite source name in the
    form ``logical_file_id|log_set_id|mnemonic``.  This reader uses that exact
    identity where available, instead of selecting a same-named channel from a
    different logical file or log set.
    """
    if lis is None:
        raise LisInspectionError("LIS/LTI support requires the backend dependency 'dlisio'.") from _LIS_IMPORT_ERROR

    source = Path(source_path)
    if not source.is_file():
        raise LisInspectionError(f"LIS/LTI source file does not exist: {source}")

    composite_parts = [part.strip() for part in str(source_curve_name or "").split("|")]
    if len(composite_parts) == 3:
        logical_file_id = logical_file_id or composite_parts[0]
        log_set_id = log_set_id or composite_parts[1]
        curve_mnemonic = composite_parts[2] or curve_mnemonic

    requested_mnemonic = str(curve_mnemonic or "").strip().casefold()
    requested_logical = str(logical_file_id or "").strip().casefold()
    requested_log_set = str(log_set_id or "").strip().casefold()
    matches: list[tuple[str, str, Any, Any, str, dict[str, Any]]] = []

    try:
        with lis.load(str(source)) as physical:
            for logical_index, logical in enumerate(list(physical), start=1):
                actual_logical_id = _logical_id(logical, logical_index)
                if requested_logical and actual_logical_id.strip().casefold() != requested_logical:
                    continue
                for spec_index, spec in enumerate(list(logical.data_format_specs()), start=1):
                    actual_log_set_id = _log_set_id(spec, spec_index)
                    if requested_log_set and actual_log_set_id.strip().casefold() != requested_log_set:
                        continue
                    curves = lis.curves(logical, spec)
                    names = list(curves.dtype.names or ())
                    descriptors = _spec_descriptors(spec)
                    for name in names:
                        if str(name).strip().casefold() == requested_mnemonic:
                            matches.append((actual_logical_id, actual_log_set_id, logical, spec, name, descriptors))

            if not matches:
                identity = source_curve_name or f"{logical_file_id or '*'}|{log_set_id or '*'}|{curve_mnemonic}"
                raise LisInspectionError(f"LIS/LTI curve was not found: {identity}")
            if len(matches) > 1 and not (requested_logical and requested_log_set):
                identities = ", ".join(f"{lf}|{ls}|{name.strip()}" for lf, ls, _, _, name, _ in matches[:12])
                raise LisInspectionError(
                    f"LIS/LTI curve identity is ambiguous for {curve_mnemonic!r}; use source_curve_name. Matches: {identities}"
                )

            actual_logical_id, actual_log_set_id, logical, spec, actual_name, descriptors = matches[0]
            curves = lis.curves(logical, spec)
            names = list(curves.dtype.names or ())
            index_name = _index_name(spec, names, descriptors)
            if index_name not in names:
                raise LisInspectionError(
                    f"LIS/LTI index channel {index_name!r} is unavailable for {actual_logical_id}|{actual_log_set_id}"
                )

            index_desc = descriptors.get(index_name, {})
            curve_desc = descriptors.get(actual_name, {})
            raw_depth_unit = _text(index_desc.get("unit"))
            conversion = depth_unit_conversion(raw_depth_unit)
            if requires_human_target_unit(raw_depth_unit) or not conversion.supported:
                raise LisInspectionError(
                    f"LIS/LTI depth unit {raw_depth_unit!r} is not safely supported for WDV rendering."
                )
            normalized_depth_unit = conversion.normalized_unit or raw_depth_unit or "m"
            value_unit = _text(curve_desc.get("unit"))

            depths_raw = curves[index_name]
            values_raw = curves[actual_name]
            if len(depths_raw) != len(values_raw):
                raise LisInspectionError(
                    f"LIS/LTI depth/value arrays disagree for {actual_logical_id}|{actual_log_set_id}|{actual_name.strip()}"
                )

            samples: list[list[float]] = []
            rejected_nonfinite = 0
            rejected_null = 0
            for raw_depth, raw_value in zip(depths_raw, values_raw):
                depth = _lis_scalar_number(raw_depth)
                value = _lis_scalar_number(raw_value)
                if depth is None or value is None:
                    rejected_null += 1
                    continue
                if not math.isfinite(depth) or not math.isfinite(value):
                    rejected_nonfinite += 1
                    continue
                if _lis_common_null_sentinel(value):
                    rejected_null += 1
                    continue

                normalized_depth = conversion.convert(depth)
                render_depth = (
                    clean_depth_value(convert_depth_to_target(normalized_depth, normalized_depth_unit, target_depth_unit))
                    if target_depth_unit is not None
                    else clean_depth_value(normalized_depth)
                )
                samples.append([float(render_depth), float(value)])

            if not samples:
                raise LisInspectionError(
                    f"No valid numeric LIS/LTI samples found for {actual_logical_id}|{actual_log_set_id}|{actual_name.strip()}"
                )

            stride = max(1, math.ceil(len(samples) / max_samples)) if max_samples > 0 else 1
            returned = samples[::stride]
            if returned[-1] != samples[-1]:
                returned.append(samples[-1])

            depths = [sample[0] for sample in samples]
            values = [sample[1] for sample in samples]
            ordered_values = sorted(values)
            robust_min, robust_max = _lis_robust_domain(ordered_values)
            output_depth_unit = str(target_depth_unit or normalized_depth_unit).strip().casefold()
            return {
                "source_format": "LIS",
                "depth_unit": output_depth_unit,
                "value_unit": value_unit,
                "depth_min": min(depths),
                "depth_max": max(depths),
                "value_min": min(values),
                "value_max": max(values),
                "robust_value_min": robust_min,
                "robust_value_max": robust_max,
                "value_p01": _lis_percentile(ordered_values, 0.01),
                "value_p05": _lis_percentile(ordered_values, 0.05),
                "value_p50": _lis_percentile(ordered_values, 0.50),
                "value_p95": _lis_percentile(ordered_values, 0.95),
                "value_p99": _lis_percentile(ordered_values, 0.99),
                "sample_count": len(samples),
                "raw_numeric_sample_count": len(samples) + rejected_null + rejected_nonfinite,
                "rejected_sample_count": rejected_null + rejected_nonfinite,
                "rejected_null_count": rejected_null,
                "rejected_sentinel_count": 0,
                "rejected_nonfinite_count": rejected_nonfinite,
                "rejected_plausibility_count": 0,
                "rejected_row_count": 0,
                "decimation_stride": stride,
                "lis_logical_file_id": actual_logical_id,
                "lis_log_set_id": actual_log_set_id,
                "lis_channel_mnemonic": actual_name.strip(),
                "lis_index_channel": index_name.strip(),
                "samples": returned,
            }
    except LisInspectionError:
        raise
    except Exception as exc:
        raise LisInspectionError(f"LIS/LTI sample read failed: {exc}") from exc


def _lis_scalar_number(value: Any) -> float | None:
    """Return a scalar numeric value from numpy scalars, one-element arrays or masks."""
    if value is None or bool(getattr(value, "mask", False)):
        return None
    candidate = value
    shape = getattr(candidate, "shape", ())
    if shape not in ((), None):
        try:
            if getattr(candidate, "size", 0) != 1:
                return None
            candidate = candidate.reshape(-1)[0]
        except Exception:
            return None
    try:
        return float(candidate)
    except (TypeError, ValueError):
        return None


def _lis_common_null_sentinel(value: float) -> bool:
    return any(abs(value - sentinel) <= 1e-6 for sentinel in (-999.25, -999.0, -9999.0, -99999.0, -999999.0, -1.0e30))


def _lis_percentile(ordered: list[float], fraction: float) -> float:
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * min(1.0, max(0.0, fraction))
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _lis_robust_domain(ordered: list[float]) -> tuple[float, float]:
    if len(ordered) < 20:
        return ordered[0], ordered[-1]
    low = _lis_percentile(ordered, 0.01)
    high = _lis_percentile(ordered, 0.99)
    return (low, high) if high > low else (ordered[0], ordered[-1])
