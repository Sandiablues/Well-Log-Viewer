"""Backend-owned scalar DLIS sample reader for WDV sample contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable
import math

from app.source_intake.depth_units import (
    UnsupportedDepthUnitError,
    clean_depth_value,
    convert_depth_to_target,
    require_depth_unit_conversion,
)

try:
    from dlisio import dlis
except ImportError:  # pragma: no cover - exercised by deployment validation
    dlis = None


class DlisSampleReaderError(ValueError):
    """Raised when a requested DLIS scalar channel cannot be read safely."""


def read_dlis_curve_samples(
    *,
    source_path: Path,
    curve_mnemonic: str,
    max_samples: int,
    logical_file_id: str | None = None,
    frame_id: str | None = None,
    channel_mnemonic: str | None = None,
    target_depth_unit: str | None = None,
) -> dict[str, Any]:
    """Read one scalar DLIS channel and return the common WDV statistics contract.

    Logical-file, frame, channel, and index identities are selected from managed
    provenance when supplied. No mnemonic inference or frontend-owned fallback is
    performed beyond using ``curve_mnemonic`` as the requested channel name.
    """

    if dlis is None:
        raise DlisSampleReaderError("DLIS sample access requires 'dlisio'.")

    source = Path(source_path).expanduser()
    if not source.is_file():
        raise DlisSampleReaderError(f"DLIS source is unavailable: {source}")

    target_name = str(channel_mnemonic or curve_mnemonic).strip()
    if not target_name:
        raise DlisSampleReaderError("DLIS channel mnemonic is required.")

    try:
        with dlis.load(str(source)) as physical:
            logical = _select_logical_file(physical, logical_file_id)
            resolved_logical_id = _logical_file_id(logical)
            frame = _select_frame(logical, frame_id)
            resolved_frame_id = _frame_id(frame)
            channels = list(getattr(frame, "channels", ()) or ())
            if not channels:
                raise DlisSampleReaderError(
                    f"DLIS frame has no channels: {resolved_logical_id}/{resolved_frame_id}"
                )

            index_name = _index_channel_name(frame, channels)
            index_channel = _select_channel(channels, index_name, role="index")
            channel = _select_channel(channels, target_name, role="curve")

            _require_scalar(index_channel, index_name, role="index")
            _require_scalar(channel, target_name, role="curve")

            curves = frame.curves(strict=False)
            depths = curves[index_name]
            values = curves[target_name]
            raw_depth_unit = getattr(index_channel, "units", None)
            source_conversion = require_depth_unit_conversion(raw_depth_unit)
            depth_unit = (
                str(target_depth_unit).strip().casefold()
                if target_depth_unit is not None
                else source_conversion.normalized_unit
            )
            if depth_unit not in {"m", "ft"}:
                raise DlisSampleReaderError(
                    f"Unsupported managed depth unit: {depth_unit!r}"
                )
            value_unit = _clean_optional_text(getattr(channel, "units", None))
            null_values = _channel_null_values(channel)
    except DlisSampleReaderError:
        raise
    except UnsupportedDepthUnitError as exc:
        raise DlisSampleReaderError(str(exc)) from exc
    except Exception as exc:
        raise DlisSampleReaderError(
            f"DLIS samples are unreadable for {target_name}: {source}"
        ) from exc

    samples: list[list[float]] = []
    raw_numeric_count = 0
    rejected_null_count = 0
    rejected_sentinel_count = 0
    rejected_nonfinite_count = 0
    rejected_row_count = 0

    for raw_depth, raw_value in _paired_values(depths, values):
        try:
            depth = clean_depth_value(
                convert_depth_to_target(_scalar_float(raw_depth), raw_depth_unit, depth_unit)
            )
            value = _scalar_float(raw_value)
        except (TypeError, ValueError, OverflowError):
            rejected_row_count += 1
            continue

        if not math.isfinite(depth) or not math.isfinite(value):
            rejected_nonfinite_count += 1
            continue

        raw_numeric_count += 1
        if any(_same_numeric_value(value, marker) for marker in null_values):
            rejected_null_count += 1
            continue
        if _looks_like_common_null_sentinel(value):
            rejected_sentinel_count += 1
            continue

        samples.append([depth, value])

    if not samples:
        raise DlisSampleReaderError(
            f"No valid numeric DLIS samples found for curve {target_name}: {source}"
        )

    returned, stride = _decimate(samples, max_samples)
    depth_values = [row[0] for row in samples]
    curve_values = [row[1] for row in samples]

    return {
        "depth_unit": depth_unit,
        "value_unit": value_unit,
        "depth_min": min(depth_values),
        "depth_max": max(depth_values),
        "value_min": min(curve_values),
        "value_max": max(curve_values),
        "robust_value_min": _percentile(curve_values, 0.05),
        "robust_value_max": _percentile(curve_values, 0.95),
        "value_p01": _percentile(curve_values, 0.01),
        "value_p05": _percentile(curve_values, 0.05),
        "value_p50": _percentile(curve_values, 0.50),
        "value_p95": _percentile(curve_values, 0.95),
        "value_p99": _percentile(curve_values, 0.99),
        "sample_count": len(samples),
        "raw_numeric_sample_count": raw_numeric_count,
        "rejected_sample_count": (
            rejected_null_count
            + rejected_sentinel_count
            + rejected_nonfinite_count
            + rejected_row_count
        ),
        "rejected_null_count": rejected_null_count,
        "rejected_sentinel_count": rejected_sentinel_count,
        "rejected_nonfinite_count": rejected_nonfinite_count,
        "rejected_plausibility_count": 0,
        "rejected_row_count": rejected_row_count,
        "decimation_stride": stride,
        "samples": returned,
        "source_format": "DLIS",
        "dlis_logical_file_id": resolved_logical_id,
        "dlis_frame_id": resolved_frame_id,
        "dlis_channel_mnemonic": target_name,
        "dlis_index_channel": index_name,
    }


def _select_logical_file(physical: Iterable[Any], requested_id: str | None) -> Any:
    logical_files = list(physical)
    if not logical_files:
        raise DlisSampleReaderError("DLIS physical file contains no logical files.")
    if requested_id is None:
        return logical_files[0]
    match = next((item for item in logical_files if _logical_file_id(item) == requested_id), None)
    if match is None:
        raise DlisSampleReaderError(f"DLIS logical file is unavailable: {requested_id}")
    return match


def _select_frame(logical: Any, requested_id: str | None) -> Any:
    frames = list(getattr(logical, "frames", ()) or ())
    if not frames:
        raise DlisSampleReaderError(f"DLIS logical file has no frames: {_logical_file_id(logical)}")
    if requested_id is None:
        return frames[0]
    match = next((item for item in frames if _frame_id(item) == requested_id), None)
    if match is None:
        raise DlisSampleReaderError(f"DLIS frame is unavailable: {requested_id}")
    return match


def _select_channel(channels: list[Any], requested_name: str, *, role: str) -> Any:
    match = next((item for item in channels if _channel_name(item) == requested_name), None)
    if match is None:
        raise DlisSampleReaderError(f"DLIS {role} channel is unavailable: {requested_name}")
    return match


def _logical_file_id(logical: Any) -> str:
    header = getattr(logical, "fileheader", None)
    return str(getattr(header, "id", "") or getattr(logical, "name", "") or "0")


def _frame_id(frame: Any) -> str:
    return str(getattr(frame, "name", "") or getattr(frame, "id", "") or "0")


def _channel_name(channel: Any) -> str:
    return str(getattr(channel, "name", "") or "")


def _index_channel_name(frame: Any, channels: list[Any]) -> str:
    raw = getattr(frame, "index", None)
    if hasattr(raw, "name"):
        raw = getattr(raw, "name")
    name = str(raw or "").strip()
    if name:
        return name
    return _channel_name(channels[0])


def _dimensions(channel: Any) -> tuple[int, ...]:
    raw = getattr(channel, "dimension", None)
    if raw is None:
        return ()
    try:
        return tuple(int(value) for value in raw)
    except TypeError:
        return (int(raw),)


def _require_scalar(channel: Any, name: str, *, role: str) -> None:
    dimensions = _dimensions(channel)
    if dimensions not in ((), (1,)):
        raise DlisSampleReaderError(
            f"DLIS {role} channel is not scalar: {name} dimensions={list(dimensions)}"
        )


def _channel_null_values(channel: Any) -> tuple[float, ...]:
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


def _paired_values(depths: Any, values: Any) -> Iterable[tuple[Any, Any]]:
    try:
        return zip(depths, values, strict=False)
    except TypeError:  # pragma: no cover - Python compatibility fallback
        return zip(depths, values)


def _scalar_float(value: Any) -> float:
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, (list, tuple)):
        if len(value) != 1:
            raise ValueError("non-scalar value")
        value = value[0]
    return float(value)


def _decimate(samples: list[list[float]], max_samples: int) -> tuple[list[list[float]], int]:
    stride = max(1, math.ceil(len(samples) / max_samples)) if max_samples > 0 else 1
    returned = samples[::stride]
    if returned[-1] != samples[-1]:
        returned.append(samples[-1])
    return returned, stride



def _clean_optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _same_numeric_value(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=0.0, abs_tol=max(1.0e-12, abs(right) * 1.0e-12))


def _looks_like_common_null_sentinel(value: float) -> bool:
    return any(
        _same_numeric_value(value, marker)
        for marker in (-999.0, -999.25, -9999.0, -9999.25, -99999.0)
    )


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * min(1.0, max(0.0, fraction))
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
