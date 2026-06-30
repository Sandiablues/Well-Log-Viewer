"""Product-id-backed WDV curve sample service.

This service is the WDV rendering data boundary for managed loaded curves. The
frontend must not render managed product curves from prototype fixture aliases.
It should request samples by product_id and render only samples returned by this
backend-owned service.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import gzip
import json
import math
import re

from .models import ManagedProductGroupItem, ManagedWellRecord
from .repository import ManagedWellInventoryRepository, ManagedWellNotFoundError


class CurveSampleServiceError(ValueError):
    """Raised when product-backed curve samples cannot be safely returned."""


class CurveSampleService:
    def __init__(self, repository: ManagedWellInventoryRepository | None = None) -> None:
        self.repository = repository or ManagedWellInventoryRepository()

    def get_curve_samples(self, managed_well_id: str, product_id: str, max_samples: int = 12000) -> dict[str, Any]:
        record = self.repository.get_record(managed_well_id)
        item = self._find_product_item(record, product_id)
        sample_store = self._sample_store_path_for_item(item)
        source_path = self._source_path_for_item(item)
        if sample_store is not None:
            parsed = _read_managed_las_curve_samples(
                sample_store=sample_store,
                source_curve_index=self._source_curve_index(item),
                max_samples=max_samples,
            )
            sample_source = "managed_las_sample_store"
            provenance_path = sample_store
        elif source_path is not None:
            parsed = _read_las_curve_samples(
                source_path=source_path,
                curve_mnemonic=item.curve_name or item.display_name,
                max_samples=max_samples,
            )
            sample_source = "las_original_path"
            provenance_path = source_path
        else:
            raise CurveSampleServiceError(f"No readable managed LAS samples or source path is available for product: {product_id}")

        return {
            "ok": True,
            "contract_kind": "wdv_product_curve_samples",
            "contract_version": "wdv_product_curve_samples_v1",
            "managed_well_id": record.managed_well_id,
            "well_id": record.well_id,
            "well_name": record.well_name,
            "product_id": item.product_id,
            "managed_curve_uid": str(item.managed_curve_uid) if item.managed_curve_uid else None,
            "curve_uid": item.curve_uid or (str(item.managed_curve_uid) if item.managed_curve_uid else None),
            "curve_id": item.curve_name,
            "mnemonic": item.curve_name,
            "display_name": item.display_name,
            "curve_family": item.curve_family,
            "source_id": item.source_id,
            "source_intake_candidate_id": item.source_intake_candidate_id,
            "source_path": str(provenance_path),
            "sample_source": sample_source,
            "depth_unit": parsed["depth_unit"],
            "value_unit": parsed["value_unit"] or item.curve_unit or "",
            "depth_min": parsed["depth_min"],
            "depth_max": parsed["depth_max"],
            "value_min": parsed["value_min"],
            "value_max": parsed["value_max"],
            "robust_value_min": parsed.get("robust_value_min"),
            "robust_value_max": parsed.get("robust_value_max"),
            "value_p01": parsed.get("value_p01"),
            "value_p05": parsed.get("value_p05"),
            "value_p50": parsed.get("value_p50"),
            "value_p95": parsed.get("value_p95"),
            "value_p99": parsed.get("value_p99"),
            "sample_count": parsed["sample_count"],
            "raw_numeric_sample_count": parsed.get("raw_numeric_sample_count"),
            "rejected_sample_count": parsed.get("rejected_sample_count", 0),
            "rejected_null_count": parsed.get("rejected_null_count", 0),
            "rejected_sentinel_count": parsed.get("rejected_sentinel_count", 0),
            "rejected_nonfinite_count": parsed.get("rejected_nonfinite_count", 0),
            "rejected_plausibility_count": parsed.get("rejected_plausibility_count", 0),
            "rejected_row_count": parsed.get("rejected_row_count", 0),
            "decimation_stride": parsed["decimation_stride"],
            "samples": parsed["samples"],
        }

    def _find_product_item(self, record: ManagedWellRecord, product_id: str) -> ManagedProductGroupItem:
        for group in record.product_groups:
            for item in group.items:
                if item.product_id == product_id:
                    return item
        raise ManagedWellNotFoundError(product_id)

    @staticmethod
    def _sample_store_path_for_item(item: ManagedProductGroupItem) -> Path | None:
        provenance = item.provenance if isinstance(item.provenance, dict) else {}
        candidates = [provenance.get("las_samples_uri")]
        asset = provenance.get("las_asset")
        if isinstance(asset, dict):
            candidates.append(asset.get("samples_uri"))
        for candidate in candidates:
            if not candidate:
                continue
            path = Path(str(candidate)).expanduser()
            if path.exists() and path.is_file():
                return path.resolve()
        return None

    @staticmethod
    def _source_curve_index(item: ManagedProductGroupItem) -> int:
        provenance = item.provenance if isinstance(item.provenance, dict) else {}
        value = provenance.get("source_curve_index")
        if value is None:
            raise CurveSampleServiceError(f"Managed LAS curve is missing source_curve_index: {item.product_id}")
        try:
            index = int(value)
        except (TypeError, ValueError) as exc:
            raise CurveSampleServiceError(f"Invalid source_curve_index for {item.product_id}: {value}") from exc
        if index < 0:
            raise CurveSampleServiceError(f"Invalid source_curve_index for {item.product_id}: {index}")
        return index

    @staticmethod
    def _source_path_for_item(item: ManagedProductGroupItem) -> Path | None:
        provenance = item.provenance if isinstance(item.provenance, dict) else {}
        candidates = [
            provenance.get("original_path"),
            provenance.get("path"),
            provenance.get("source_path"),
        ]
        for candidate in candidates:
            if not candidate:
                continue
            path = Path(str(candidate)).expanduser()
            if path.exists() and path.is_file():
                return path.resolve()
        return None


def _read_managed_las_curve_samples(sample_store: Path, source_curve_index: int, max_samples: int) -> dict[str, Any]:
    try:
        with gzip.open(sample_store, "rt", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise CurveSampleServiceError(f"Managed LAS sample store is unreadable: {sample_store}") from exc
    if payload.get("storage_contract") != "wlv_las_samples_v1":
        raise CurveSampleServiceError(f"Unsupported managed LAS sample contract: {sample_store}")
    depths = payload.get("depth_values")
    curves = payload.get("curves")
    if not isinstance(depths, list) or not isinstance(curves, list):
        raise CurveSampleServiceError(f"Managed LAS sample store is incomplete: {sample_store}")
    curve = next((item for item in curves if isinstance(item, dict) and int(item.get("curve_index", -1)) == source_curve_index), None)
    if curve is None:
        raise CurveSampleServiceError(f"Managed LAS curve index {source_curve_index} is absent: {sample_store}")
    values = curve.get("values")
    if not isinstance(values, list) or len(values) != len(depths):
        raise CurveSampleServiceError(f"Managed LAS depth/value arrays disagree for curve index {source_curve_index}")
    samples = []
    rejected = 0
    for depth, value in zip(depths, values):
        if depth is None or value is None:
            rejected += 1
            continue
        try:
            depth_value = float(depth)
            curve_value = float(value)
        except (TypeError, ValueError):
            rejected += 1
            continue
        if not math.isfinite(depth_value) or not math.isfinite(curve_value):
            rejected += 1
            continue
        samples.append([depth_value, curve_value])
    if not samples:
        raise CurveSampleServiceError(f"No valid managed LAS samples for curve index {source_curve_index}")
    stride = max(1, math.ceil(len(samples) / max_samples)) if max_samples > 0 else 1
    returned = samples[::stride]
    if returned[-1] != samples[-1]:
        returned.append(samples[-1])
    depth_values = [row[0] for row in samples]
    curve_values = [row[1] for row in samples]
    robust_min, robust_max = _robust_value_domain(curve_values)
    return {
        "depth_unit": str(payload.get("depth_unit") or "ft"),
        "value_unit": curve.get("unit"),
        "depth_min": min(depth_values),
        "depth_max": max(depth_values),
        "value_min": min(curve_values),
        "value_max": max(curve_values),
        "robust_value_min": robust_min,
        "robust_value_max": robust_max,
        "value_p01": _value_percentile(curve_values, 0.01),
        "value_p05": _value_percentile(curve_values, 0.05),
        "value_p50": _value_percentile(curve_values, 0.50),
        "value_p95": _value_percentile(curve_values, 0.95),
        "value_p99": _value_percentile(curve_values, 0.99),
        "sample_count": len(samples),
        "raw_numeric_sample_count": len(samples),
        "rejected_sample_count": rejected,
        "rejected_null_count": rejected,
        "rejected_sentinel_count": 0,
        "rejected_nonfinite_count": 0,
        "rejected_plausibility_count": 0,
        "rejected_row_count": 0,
        "decimation_stride": stride,
        "samples": returned,
    }


def _read_las_curve_samples(source_path: Path, curve_mnemonic: str, max_samples: int) -> dict[str, Any]:
    text = source_path.read_text(encoding="utf-8", errors="replace")
    sections = _split_las_sections(text)
    curve_lines = _parse_curve_section(sections.get("C") or sections.get("CURVE") or [])
    well_lines = _parse_well_section(sections.get("W") or sections.get("WELL") or [])
    rows = _parse_ascii_rows(sections.get("A") or sections.get("ASCII") or [])
    if not curve_lines:
        raise CurveSampleServiceError(f"LAS curve section is empty: {source_path}")
    if not rows:
        raise CurveSampleServiceError(f"LAS ASCII sample section is empty: {source_path}")

    depth_index = _depth_column_index(curve_lines)
    curve_index = _curve_column_index(curve_lines, curve_mnemonic)
    curve_line = curve_lines[curve_index]
    depth_unit = _normalize_depth_unit(curve_lines[depth_index].get("unit") or well_lines.get("STRT", {}).get("unit") or "ft")
    value_unit = curve_line.get("unit")
    null_header = well_lines.get("NULL", {})
    # LAS NULL is commonly written as `NULL. -999.25 : ...`. The header parser
    # may treat the value after the dot as the unit token when no separate value
    # token exists, so check both fields.
    null_value = _float_or_none(null_header.get("value") or null_header.get("unit"))

    family_hint = _infer_curve_family(
        mnemonic=str(curve_line.get("mnemonic") or curve_mnemonic),
        unit=value_unit or "",
        description=str(curve_line.get("value") or ""),
    )

    samples: list[list[float]] = []
    raw_numeric_count = 0
    rejected_null_count = 0
    rejected_sentinel_count = 0
    rejected_nonfinite_count = 0
    rejected_plausibility_count = 0
    rejected_row_count = 0

    for row in rows:
        if len(row) <= max(depth_index, curve_index):
            rejected_row_count += 1
            continue
        depth = row[depth_index]
        value = row[curve_index]
        if not math.isfinite(depth) or not math.isfinite(value):
            rejected_nonfinite_count += 1
            continue

        raw_numeric_count += 1

        if null_value is not None and _same_numeric_value(value, null_value):
            rejected_null_count += 1
            continue
        if _looks_like_common_null_sentinel(value):
            rejected_sentinel_count += 1
            continue
        if not _value_is_plausible_for_curve(value, family_hint, value_unit or "", str(curve_line.get("mnemonic") or curve_mnemonic)):
            rejected_plausibility_count += 1
            continue

        samples.append([depth, value])

    if not samples:
        raise CurveSampleServiceError(f"No valid numeric samples found for curve {curve_mnemonic}: {source_path}")

    stride = max(1, math.ceil(len(samples) / max_samples)) if max_samples > 0 else 1
    returned = samples[::stride]
    if returned[-1] != samples[-1]:
        returned.append(samples[-1])

    depths = [sample[0] for sample in samples]
    values = [sample[1] for sample in samples]
    robust_min, robust_max = _robust_value_domain(values)
    value_p01 = _value_percentile(values, 0.01)
    value_p05 = _value_percentile(values, 0.05)
    value_p50 = _value_percentile(values, 0.50)
    value_p95 = _value_percentile(values, 0.95)
    value_p99 = _value_percentile(values, 0.99)

    return {
        "depth_unit": depth_unit,
        "value_unit": value_unit,
        "curve_family_hint": family_hint,
        "depth_min": min(depths),
        "depth_max": max(depths),
        "value_min": min(values),
        "value_max": max(values),
        "robust_value_min": robust_min,
        "robust_value_max": robust_max,
        "value_p01": value_p01,
        "value_p05": value_p05,
        "value_p50": value_p50,
        "value_p95": value_p95,
        "value_p99": value_p99,
        "sample_count": len(samples),
        "raw_numeric_sample_count": raw_numeric_count,
        "rejected_sample_count": (
            rejected_null_count
            + rejected_sentinel_count
            + rejected_nonfinite_count
            + rejected_plausibility_count
            + rejected_row_count
        ),
        "rejected_null_count": rejected_null_count,
        "rejected_sentinel_count": rejected_sentinel_count,
        "rejected_nonfinite_count": rejected_nonfinite_count,
        "rejected_plausibility_count": rejected_plausibility_count,
        "rejected_row_count": rejected_row_count,
        "decimation_stride": stride,
        "samples": returned,
    }
def _split_las_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("~"):
            current = stripped[1:].split(maxsplit=1)[0].upper()
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections.setdefault(current, []).append(line)
    return sections


def _parse_curve_section(lines: list[str]) -> list[dict[str, str | None]]:
    output: list[dict[str, str | None]] = []
    for line in lines:
        parsed = _parse_las_header_line(line)
        if parsed and parsed["mnemonic"]:
            output.append(parsed)
    return output


def _parse_well_section(lines: list[str]) -> dict[str, dict[str, str | None]]:
    output: dict[str, dict[str, str | None]] = {}
    for line in lines:
        parsed = _parse_las_header_line(line)
        if parsed and parsed["mnemonic"]:
            output[str(parsed["mnemonic"]).upper()] = parsed
    return output


def _parse_las_header_line(raw: str) -> dict[str, str | None] | None:
    stripped = raw.strip()
    if not stripped or stripped.startswith("#"):
        return None
    left = stripped.split(":", 1)[0].strip()
    match = re.match(r"^\s*([A-Za-z0-9_\-]+)\s*(?:\.\s*([^\s]*))?\s*(.*?)\s*$", left)
    if not match:
        return None
    mnemonic = match.group(1).strip()
    unit = (match.group(2) or "").strip() or None
    value = (match.group(3) or "").strip() or None
    return {"mnemonic": mnemonic, "unit": unit, "value": value}


def _parse_ascii_rows(lines: list[str]) -> list[list[float]]:
    rows: list[list[float]] = []
    for raw in lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        values: list[float] = []
        for token in stripped.replace(",", " ").split():
            try:
                values.append(float(token))
            except ValueError:
                values = []
                break
        if values:
            rows.append(values)
    return rows


def _depth_column_index(curves: list[dict[str, str | None]]) -> int:
    for index, line in enumerate(curves):
        if str(line.get("mnemonic") or "").upper() in {"DEPT", "DEPTH", "MD"}:
            return index
    return 0


def _curve_column_index(curves: list[dict[str, str | None]], curve_mnemonic: str) -> int:
    requested = str(curve_mnemonic or "").upper()
    for index, line in enumerate(curves):
        if str(line.get("mnemonic") or "").upper() == requested:
            return index
    available = ", ".join(str(line.get("mnemonic")) for line in curves[:40])
    raise CurveSampleServiceError(f"Curve {curve_mnemonic} was not found in LAS curve section. Available: {available}")


def _float_or_none(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).split()[0])
    except (TypeError, ValueError, IndexError):
        return None



def _same_numeric_value(left: float, right: float, tolerance: float = 1e-9) -> bool:
    return abs(float(left) - float(right)) <= tolerance


def _looks_like_common_null_sentinel(value: float) -> bool:
    sentinels = (-999.25, -999.0, -9999.0, -99999.0, -999999.0, -1.0e30)
    return any(abs(value - sentinel) <= 1e-6 for sentinel in sentinels)


def _infer_curve_family(mnemonic: str, unit: str, description: str = "") -> str:
    key = f"{mnemonic} {unit} {description}".lower()
    if any(token in key for token in ("ohmm", "ohm.m", "ohm-m", "resist")):
        return "resistivity"
    if any(token in key for token in ("gapi", "api", "gamma")):
        return "gamma_ray"
    if any(token in key for token in ("g/cm", "g/cc", "g/c3", "density", "rho")):
        return "density"
    if any(token in key for token in ("v/v", "v/v_decimal", "porosity", "neutron", "nphi", "npor", "tnph", "hnpo", "htnp", "dnph")):
        return "neutron_porosity"
    if any(token in key for token in ("us/f", "us/ft", "sonic", "dtco", "dtsm")):
        return "sonic"
    if " in" in f" {key}" or "caliper" in key or "borehole" in key:
        return "caliper"
    return "unknown"


def _value_is_plausible_for_curve(value: float, family: str, unit: str, mnemonic: str) -> bool:
    # These are deliberately broad engineering sanity ranges. They are not
    # display defaults; they only prevent LAS null/fill/extreme corrupt values
    # from contaminating statistics or rendering samples.
    family_key = family.lower()
    unit_key = unit.lower()
    mnemonic_key = mnemonic.lower()

    if family_key == "density" or "g/c" in unit_key:
        return -20.0 <= value <= 20.0
    if family_key == "neutron_porosity":
        return -1.5 <= value <= 1.5
    if family_key == "gamma_ray":
        return -50.0 <= value <= 1000.0
    if family_key == "sonic":
        return 0.0 < value <= 1000.0
    if family_key == "caliper":
        return 0.0 <= value <= 200.0
    if family_key == "resistivity" or "ohm" in unit_key:
        return 0.0 < value <= 1.0e8

    # Unknown curves should not be over-filtered, but absurd LAS artifacts
    # should not become display-scale truth.
    return -1.0e6 < value < 1.0e6



def _value_percentile(values: list[float], fraction: float) -> float:
    if not values:
        raise CurveSampleServiceError("Cannot compute percentile from empty value list.")
    ordered = sorted(float(v) for v in values if math.isfinite(v))
    if not ordered:
        raise CurveSampleServiceError("Cannot compute percentile from non-finite value list.")
    if len(ordered) == 1:
        return ordered[0]
    bounded = min(1.0, max(0.0, fraction))
    position = (len(ordered) - 1) * bounded
    lower_index = int(math.floor(position))
    upper_index = int(math.ceil(position))
    if lower_index == upper_index:
        return ordered[lower_index]
    lower = ordered[lower_index]
    upper = ordered[upper_index]
    return lower + (upper - lower) * (position - lower_index)

def _robust_value_domain(values: list[float]) -> tuple[float, float]:
    if not values:
        raise CurveSampleServiceError("Cannot compute robust domain from empty value list.")
    ordered = sorted(float(v) for v in values if math.isfinite(v))
    if not ordered:
        raise CurveSampleServiceError("Cannot compute robust domain from non-finite value list.")
    if len(ordered) < 20:
        return ordered[0], ordered[-1]
    low_index = max(0, int(math.floor((len(ordered) - 1) * 0.01)))
    high_index = min(len(ordered) - 1, int(math.ceil((len(ordered) - 1) * 0.99)))
    low = ordered[low_index]
    high = ordered[high_index]
    if high <= low:
        return ordered[0], ordered[-1]
    return low, high
def _normalize_depth_unit(unit: str) -> str:
    lowered = unit.lower().strip()
    if lowered in {"m", "meter", "metre", "meters", "metres"}:
        return "m"
    if lowered in {"ft", "feet", "foot", "f"}:
        return "ft"
    return lowered or "ft"
