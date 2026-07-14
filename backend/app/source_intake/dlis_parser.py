"""Lean native DLIS inspection for WLV Source Intake."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import math

from .depth_units import depth_unit_conversion, requires_human_target_unit

try:
    from dlisio import dlis
except ImportError as exc:  # pragma: no cover
    dlis = None
    _DLIS_IMPORT_ERROR = exc
else:
    _DLIS_IMPORT_ERROR = None


class DlisInspectionError(ValueError):
    pass


@dataclass(frozen=True)
class DlisScalarChannel:
    logical_file_id: str
    frame_id: str
    mnemonic: str
    description: str | None
    unit: str | None
    dimensions: tuple[int, ...]
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
        return f"{self.logical_file_id}|{self.frame_id}|{self.mnemonic}"


@dataclass(frozen=True)
class DlisChannelInventoryItem:
    logical_file_id: str
    frame_id: str
    mnemonic: str
    description: str | None
    unit: str | None
    dimensions: tuple[int, ...]
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
class DlisInspection:
    parser_id: str
    source_format: str
    well_name: str | None
    uwi: str | None
    operator: str | None
    field: str | None
    service_company: str | None
    logical_file_count: int
    frame_count: int
    scalar_channels: tuple[DlisScalarChannel, ...]
    channel_inventory: tuple[DlisChannelInventoryItem, ...]
    non_scalar_channel_count: int
    warnings: tuple[str, ...] = field(default_factory=tuple)


def inspect_dlis(path: Path) -> DlisInspection:
    if dlis is None:
        raise DlisInspectionError("DLIS support requires the backend dependency 'dlisio'.") from _DLIS_IMPORT_ERROR
    source = Path(path)
    if not source.is_file():
        raise DlisInspectionError(f"DLIS source file does not exist: {source}")

    scalar_channels: list[DlisScalarChannel] = []
    channel_inventory: list[DlisChannelInventoryItem] = []
    warnings: list[str] = []
    non_scalar_count = 0
    logical_file_count = frame_count = 0
    well_name = uwi = operator = field_name = service_company = None

    try:
        with dlis.load(str(source)) as physical_file:
            logical_file_count = len(physical_file)
            for logical_index, logical_file in enumerate(physical_file):
                logical_id = _text(getattr(getattr(logical_file, "fileheader", None), "id", None)) or f"logical_file_{logical_index + 1}"
                origin = logical_file.origins[0] if logical_file.origins else None
                if origin is not None:
                    well_name = well_name or _text(getattr(origin, "well_name", None))
                    uwi = uwi or _text(getattr(origin, "well_id", None))
                    operator = operator or _text(getattr(origin, "company", None))
                    field_name = field_name or _text(getattr(origin, "field_name", None))
                    service_company = service_company or _text(getattr(origin, "producer_name", None))

                for frame_index, frame in enumerate(logical_file.frames):
                    frame_count += 1
                    frame_id = _text(getattr(frame, "name", None)) or f"frame_{frame_index + 1}"
                    channels = list(frame.channels)
                    if not channels:
                        warnings.append(f"{logical_id}/{frame_id}: frame has no channels.")
                        continue
                    index_name = _text(getattr(frame, "index", None)) or _text(getattr(channels[0], "name", None))
                    index_channel = next((channel for channel in channels if _text(getattr(channel, "name", None)) == index_name), None)
                    if index_channel is None or index_name is None:
                        warnings.append(f"{logical_id}/{frame_id}: frame has no usable index channel.")
                        continue
                    try:
                        curves = frame.curves(strict=False)
                    except Exception as exc:
                        warnings.append(f"{logical_id}/{frame_id}: frame samples could not be read: {exc}")
                        continue
                    if index_name not in curves.dtype.names:
                        warnings.append(f"{logical_id}/{frame_id}: index channel is unavailable in frame data.")
                        continue
                    raw_depth_unit = _text(getattr(index_channel, "units", None))
                    depth_conversion = depth_unit_conversion(raw_depth_unit)
                    raw_top_depth, raw_base_depth = _raw_depth_range(curves[index_name])
                    decision_required = requires_human_target_unit(raw_depth_unit)
                    if decision_required:
                        top_depth, base_depth, depth_unit = None, None, None
                    else:
                        top_depth, base_depth, depth_unit = _normalized_depth_range(
                            curves[index_name], depth_conversion
                        )
                    if decision_required:
                        warnings.append(
                            f"{logical_id}/{frame_id}: index channel {index_name} uses non-standard "
                            f"depth encoding {raw_depth_unit!r}; a human must choose metres or feet."
                        )
                    elif not depth_conversion.supported:
                        warnings.append(
                            f"{logical_id}/{frame_id}: index channel {index_name} has "
                            f"unsupported depth unit {raw_depth_unit!r} "
                            f"({depth_conversion.reason}); frame requires human review."
                        )

                    for channel in channels:
                        mnemonic = _text(getattr(channel, "name", None))
                        if not mnemonic:
                            continue
                        dimensions = tuple(int(value) for value in (getattr(channel, "dimension", []) or []))
                        description = _text(getattr(channel, "long_name", None))
                        unit = _text(getattr(channel, "units", None))
                        is_index = mnemonic == index_name
                        is_scalar = dimensions in ((), (1,))
                        sample_count = len(curves[mnemonic]) if mnemonic in curves.dtype.names else None
                        unsupported_reason = None
                        supported = is_scalar and sample_count is not None and depth_conversion.supported and not decision_required
                        if decision_required:
                            unsupported_reason = "depth_target_unit_review_required"
                        elif not depth_conversion.supported:
                            unsupported_reason = "unsupported_depth_unit"
                        elif not is_scalar:
                            non_scalar_count += 1
                            unsupported_reason = "multidimensional_channel"
                        elif sample_count is None:
                            unsupported_reason = "channel_data_unavailable"
                        channel_inventory.append(DlisChannelInventoryItem(
                            logical_file_id=logical_id,
                            frame_id=frame_id,
                            mnemonic=mnemonic,
                            description=description,
                            unit=unit,
                            dimensions=dimensions,
                            index_channel=index_name,
                            sample_count=sample_count,
                            role="index" if is_index else "curve",
                            supported=supported,
                            unsupported_reason=unsupported_reason,
                            raw_depth_unit=raw_depth_unit,
                            depth_scale_factor=depth_conversion.factor,
                            normalized_depth_unit=depth_conversion.normalized_unit,
                            depth_normalization_status="review_required" if decision_required else depth_conversion.status,
                            depth_normalization_reason="human_target_unit_required" if decision_required else depth_conversion.reason,
                        ))
                        if is_index:
                            continue
                        if not depth_conversion.supported:
                            continue
                        if not is_scalar:
                            warnings.append(
                                f"{logical_id}/{frame_id}/{mnemonic}: multidimensional channel {list(dimensions)} is present but unsupported; scalar channels remain ingestible."
                            )
                            continue
                        if sample_count is None:
                            warnings.append(f"{logical_id}/{frame_id}/{mnemonic}: channel data is unavailable.")
                            continue
                        curve_statistics = _curve_statistics_from_frame_arrays(
                            depths=curves[index_name],
                            values=curves[mnemonic],
                            channel=channel,
                            depth_conversion=depth_conversion,
                        )
                        scalar_channels.append(DlisScalarChannel(
                            logical_file_id=logical_id,
                            frame_id=frame_id,
                            mnemonic=mnemonic,
                            description=description,
                            unit=unit,
                            dimensions=dimensions,
                            index_channel=index_name,
                            sample_count=sample_count,
                            top_depth=top_depth,
                            base_depth=base_depth,
                            depth_unit=depth_unit,
                            raw_depth_unit=raw_depth_unit,
                            depth_scale_factor=depth_conversion.factor,
                            depth_normalization_status="review_required" if decision_required else depth_conversion.status,
                            depth_normalization_reason="human_target_unit_required" if decision_required else depth_conversion.reason,
                            raw_top_depth=raw_top_depth,
                            raw_base_depth=raw_base_depth,
                            curve_statistics=curve_statistics,
                        ))
                        if not unit:
                            warnings.append(f"{logical_id}/{frame_id}/{mnemonic}: channel unit is missing.")
            if not scalar_channels:
                warnings.append("No depth-indexed scalar channels were found.")
            if non_scalar_count:
                warnings.append(f"{non_scalar_count} non-scalar DLIS channel(s) are present but not supported in Phase 1.")
    except Exception as exc:
        raise DlisInspectionError(f"DLIS inspection failed: {exc}") from exc

    return DlisInspection(
        parser_id="dlis_frame_channel_adapter_v1", source_format="DLIS",
        well_name=well_name, uwi=uwi, operator=operator, field=field_name,
        service_company=service_company, logical_file_count=logical_file_count,
        frame_count=frame_count, scalar_channels=tuple(scalar_channels),
        channel_inventory=tuple(channel_inventory),
        non_scalar_channel_count=non_scalar_count,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def _text(value: Any) -> str | None:
    if value is None: return None
    text = str(value).strip()
    return text or None


def _normalized_depth_range(values: Any, conversion) -> tuple[float | None, float | None, str | None]:
    if not conversion.supported:
        return None, None, None
    try:
        numeric = [float(value) for value in values]
    except Exception:
        return None, None, conversion.normalized_unit
    if not numeric:
        return None, None, conversion.normalized_unit
    normalized = [conversion.convert(value) for value in numeric]
    return min(normalized), max(normalized), conversion.normalized_unit


def _raw_depth_range(values: Any) -> tuple[float | None, float | None]:
    try:
        numeric = [float(value) for value in values]
    except Exception:
        return None, None
    if not numeric:
        return None, None
    return min(numeric), max(numeric)



def _curve_statistics_from_frame_arrays(
    *,
    depths: Any,
    values: Any,
    channel: Any,
    depth_conversion: Any,
) -> dict[str, Any]:
    """Derive persisted statistics from an already-loaded DLIS frame."""
    valid_depths: list[float] = []
    valid_values: list[float] = []

    raw_numeric_sample_count = 0
    rejected_null_count = 0
    rejected_sentinel_count = 0
    rejected_nonfinite_count = 0
    rejected_row_count = 0

    null_values = _curve_statistics_channel_null_values(channel)

    for raw_depth, raw_value in zip(depths, values, strict=False):
        try:
            depth = _curve_statistics_scalar_float(raw_depth)
            value = _curve_statistics_scalar_float(raw_value)
        except (TypeError, ValueError, OverflowError):
            rejected_row_count += 1
            continue

        if not math.isfinite(depth) or not math.isfinite(value):
            rejected_nonfinite_count += 1
            continue

        raw_numeric_sample_count += 1

        if any(
            _curve_statistics_same_numeric_value(value, marker)
            for marker in null_values
        ):
            rejected_null_count += 1
            continue

        if _curve_statistics_common_null_sentinel(value):
            rejected_sentinel_count += 1
            continue

        valid_depths.append(depth_conversion.convert(depth))
        valid_values.append(value)

    rejected_sample_count = (
        rejected_null_count
        + rejected_sentinel_count
        + rejected_nonfinite_count
        + rejected_row_count
    )

    base = {
        "contract_version": "managed_curve_statistics_v1",
        "valid_sample_count": len(valid_values),
        "raw_numeric_sample_count": raw_numeric_sample_count,
        "rejected_sample_count": rejected_sample_count,
        "rejected_null_count": rejected_null_count,
        "rejected_sentinel_count": rejected_sentinel_count,
        "rejected_nonfinite_count": rejected_nonfinite_count,
        "rejected_plausibility_count": 0,
        "rejected_row_count": rejected_row_count,
    }

    if not valid_values:
        return {
            **base,
            "statistics_status": "unavailable",
        }

    return {
        **base,
        "statistics_status": "available",
        "depth_min": min(valid_depths),
        "depth_max": max(valid_depths),
        "value_min": min(valid_values),
        "value_max": max(valid_values),
        "robust_value_min": _curve_statistics_percentile(valid_values, 0.05),
        "robust_value_max": _curve_statistics_percentile(valid_values, 0.95),
        "value_p01": _curve_statistics_percentile(valid_values, 0.01),
        "value_p05": _curve_statistics_percentile(valid_values, 0.05),
        "value_p50": _curve_statistics_percentile(valid_values, 0.50),
        "value_p95": _curve_statistics_percentile(valid_values, 0.95),
        "value_p99": _curve_statistics_percentile(valid_values, 0.99),
    }


def _curve_statistics_scalar_float(value: Any) -> float:
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, (list, tuple)):
        if len(value) != 1:
            raise ValueError("non-scalar value")
        value = value[0]
    return float(value)


def _curve_statistics_channel_null_values(channel: Any) -> tuple[float, ...]:
    values: list[float] = []
    for attribute in ("null", "null_value", "invalid", "absent_value"):
        raw = getattr(channel, attribute, None)
        if raw is None:
            continue
        candidates = raw if isinstance(raw, (list, tuple, set)) else (raw,)
        for candidate in candidates:
            try:
                value = float(candidate)
            except (TypeError, ValueError):
                continue
            if math.isfinite(value):
                values.append(value)
    return tuple(dict.fromkeys(values))


def _curve_statistics_same_numeric_value(left: float, right: float) -> bool:
    return math.isclose(
        left,
        right,
        rel_tol=0.0,
        abs_tol=max(1.0e-12, abs(right) * 1.0e-12),
    )


def _curve_statistics_common_null_sentinel(value: float) -> bool:
    return any(
        _curve_statistics_same_numeric_value(value, marker)
        for marker in (-999.0, -999.25, -9999.0, -9999.25, -99999.0)
    )


def _curve_statistics_percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]

    position = (len(ordered) - 1) * min(1.0, max(0.0, fraction))
    lower = int(math.floor(position))
    upper = int(math.ceil(position))

    if lower == upper:
        return ordered[lower]

    return ordered[lower] + (
        ordered[upper] - ordered[lower]
    ) * (position - lower)
