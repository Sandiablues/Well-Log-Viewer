from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from app.services.metadata_repository import (
    load_metadata_evidence,
    save_normalized_metadata,
    get_normalized_metadata,
    normalized_metadata_path,
    resolve_volume_path,
)
from app.services.metadata_schema import (
    SOURCE_BINARY_HEADER,
    SOURCE_TRACE_HEADER_SUMMARY,
    SOURCE_VIEWER_METADATA,
    SOURCE_CONVERSION_METADATA,
    SOURCE_RULE_ENRICHED,
    STATUS_EXTRACTED,
    STATUS_SUGGESTED,
    STATUS_AUTO_APPLIED,
    normalized_field,
    missing_field,
    empty_normalized_metadata,
)


def _deep_get(data: Any, keys: list[str]) -> Any:
    if not isinstance(data, dict):
        return None

    current: Any = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]

    return current


def _first_value(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _infer_sample_interval_ms(evidence: Dict[str, Any]) -> dict:
    binary = evidence.get("binary_header")
    viewer = evidence.get("viewer_metadata")
    conversion = evidence.get("conversion_metadata")

    value_ms = _first_value(
        _deep_get(viewer, ["sample_interval_ms"]),
        _deep_get(viewer, ["sampleRateMs"]),
        _deep_get(viewer, ["sampleIntervalMs"]),
        _deep_get(conversion, ["sample_interval_ms"]),
        _deep_get(binary, ["sample_interval_ms"]),
    )

    if value_ms is not None:
        try:
            value_ms = float(value_ms)
        except Exception:
            pass

        return normalized_field(
            value_ms,
            SOURCE_VIEWER_METADATA,
            1.0,
            STATUS_EXTRACTED,
            ["viewer_metadata", "binary_header"],
        )

    value_us = _first_value(
        _deep_get(viewer, ["sample_interval_us"]),
        _deep_get(binary, ["sample_interval_us"]),
        _deep_get(conversion, ["sample_interval_us"]),
    )

    if value_us is not None:
        try:
            return normalized_field(
                float(value_us) / 1000.0,
                SOURCE_BINARY_HEADER,
                1.0,
                STATUS_EXTRACTED,
                ["binary_header", "viewer_metadata"],
            )
        except Exception:
            return normalized_field(
                value_us,
                SOURCE_BINARY_HEADER,
                0.60,
                STATUS_SUGGESTED,
                ["binary_header", "unit_conversion_failed"],
            )

    return missing_field("sample interval not found in binary/viewer/conversion metadata")


def _infer_shape(evidence: Dict[str, Any]) -> dict:
    viewer = evidence.get("viewer_metadata")
    conversion = evidence.get("conversion_metadata")

    value = _first_value(
        _deep_get(viewer, ["volume", "shape"]),
        _deep_get(viewer, ["shape"]),
        _deep_get(viewer, ["zarr_shape"]),
        _deep_get(conversion, ["volume", "shape"]),
        _deep_get(conversion, ["shape"]),
        _deep_get(conversion, ["zarr_shape"]),
    )

    if value is None:
        return missing_field("zarr shape not found")

    return normalized_field(
        value,
        SOURCE_VIEWER_METADATA,
        1.0,
        STATUS_EXTRACTED,
        ["viewer_metadata"],
    )


def _infer_dataset_type(evidence: Dict[str, Any], shape_field: dict) -> dict:
    trace = evidence.get("trace_header_summary")
    viewer = evidence.get("viewer_metadata")

    explicit = _first_value(
        _deep_get(viewer, ["dataset_type"]),
        _deep_get(viewer, ["type"]),
        _deep_get(trace, ["dataset_type"]),
    )

    if explicit:
        return normalized_field(
            explicit,
            SOURCE_VIEWER_METADATA,
            1.0,
            STATUS_EXTRACTED,
            ["viewer_metadata"],
        )

    is_3d = _deep_get(viewer, ["volume", "is_3d"])
    if is_3d is True:
        return normalized_field(
            "3D volume",
            SOURCE_VIEWER_METADATA,
            1.0,
            STATUS_EXTRACTED,
            ["viewer_metadata.volume.is_3d"],
        )
    if is_3d is False:
        return normalized_field(
            "2D line",
            SOURCE_VIEWER_METADATA,
            1.0,
            STATUS_EXTRACTED,
            ["viewer_metadata.volume.is_3d"],
        )

    shape = shape_field.get("value")
    if isinstance(shape, list) and len(shape) >= 3:
        return normalized_field(
            "3D volume",
            SOURCE_RULE_ENRICHED,
            0.98,
            STATUS_AUTO_APPLIED,
            ["zarr_shape", "axis_count"],
        )

    if isinstance(shape, list) and len(shape) == 2:
        return normalized_field(
            "2D line",
            SOURCE_RULE_ENRICHED,
            0.95,
            STATUS_AUTO_APPLIED,
            ["zarr_shape", "axis_count"],
        )

    return missing_field("dataset type could not be inferred")


def _infer_record_length_ms(sample_interval_field: dict, sample_count_field: dict) -> dict:
    sample_interval = sample_interval_field.get("value")
    sample_count = sample_count_field.get("value")

    try:
        if sample_interval is not None and sample_count is not None:
            return normalized_field(
                float(sample_interval) * float(sample_count),
                SOURCE_RULE_ENRICHED,
                0.98,
                STATUS_AUTO_APPLIED,
                ["sample_interval_ms", "sample_count"],
            )
    except Exception:
        pass

    return missing_field("record length requires sample interval and sample count")


def _infer_sample_count(shape_field: dict, evidence: Dict[str, Any]) -> dict:
    viewer = evidence.get("viewer_metadata")
    binary = evidence.get("binary_header")
    trace = evidence.get("trace_header_summary")

    explicit = _first_value(
        _deep_get(viewer, ["volume", "sample_count"]),
        _deep_get(viewer, ["sample_count"]),
        _deep_get(viewer, ["samples"]),
        _deep_get(binary, ["samples_per_trace"]),
        _deep_get(binary, ["sample_count"]),
        _deep_get(trace, ["first_trace_header", "samples_in_trace"]),
    )

    if explicit is not None:
        return normalized_field(
            explicit,
            SOURCE_BINARY_HEADER,
            1.0,
            STATUS_EXTRACTED,
            ["binary_header", "trace_header_summary"],
        )

    shape = shape_field.get("value")
    if isinstance(shape, list) and len(shape) >= 1:
        return normalized_field(
            shape[-1],
            SOURCE_RULE_ENRICHED,
            0.90,
            STATUS_AUTO_APPLIED,
            ["zarr_shape"],
        )

    return missing_field("sample count not found")


def _infer_vertical_domain(evidence: Dict[str, Any]) -> dict:
    viewer = evidence.get("viewer_metadata")
    text = evidence.get("text_header") or ""

    explicit = _first_value(
        _deep_get(viewer, ["vertical_domain"]),
        _deep_get(viewer, ["domain"]),
    )

    if explicit:
        return normalized_field(
            explicit,
            SOURCE_VIEWER_METADATA,
            1.0,
            STATUS_EXTRACTED,
            ["viewer_metadata"],
        )

    header_upper = text.upper()
    if "TIME" in header_upper or "TWT" in header_upper or "TWO WAY TIME" in header_upper:
        return normalized_field(
            "time",
            SOURCE_RULE_ENRICHED,
            0.90,
            STATUS_AUTO_APPLIED,
            ["textual_header"],
        )

    if "DEPTH" in header_upper:
        return normalized_field(
            "depth",
            SOURCE_RULE_ENRICHED,
            0.80,
            STATUS_SUGGESTED,
            ["textual_header"],
        )

    return normalized_field(
        "time",
        SOURCE_RULE_ENRICHED,
        0.65,
        STATUS_SUGGESTED,
        ["seismic_default_assumption", "sample_interval_present"],
    )


def _infer_display_name(volume_id: str, evidence: Dict[str, Any], dataset_type_field: dict) -> dict:
    registry = evidence.get("volume_registry")
    viewer = evidence.get("viewer_metadata")
    conversion = evidence.get("conversion_metadata")

    value = _first_value(
        _deep_get(registry, ["display_name"]),
        _deep_get(registry, ["filename"]),
        _deep_get(registry, ["original_filename"]),
        _deep_get(registry, ["source_file_name"]),
        _deep_get(viewer, ["display_name"]),
        _deep_get(viewer, ["name"]),
        _deep_get(viewer, ["source_file_name"]),
        _deep_get(viewer, ["source", "filename"]),
        _deep_get(conversion, ["source_file_name"]),
        _deep_get(conversion, ["input_file"]),
    )

    if value:
        clean = Path(str(value)).name
        source = SOURCE_VIEWER_METADATA
        basis = ["viewer_metadata.source.filename"]

        if registry and clean != f"{volume_id}.sgy":
            source = "volume_registry"
            basis = ["volumes_json.filename"]

        return normalized_field(
            clean,
            source,
            0.98,
            STATUS_AUTO_APPLIED,
            basis,
        )

    suffix = dataset_type_field.get("value") or "dataset"
    return normalized_field(
        f"{volume_id} {suffix}",
        SOURCE_RULE_ENRICHED,
        0.75,
        STATUS_SUGGESTED,
        ["volume_id", "dataset_type"],
    )


def _infer_geometry_fields(evidence: Dict[str, Any], shape_field: dict) -> dict:
    trace = evidence.get("trace_header_summary") or {}
    viewer = evidence.get("viewer_metadata") or {}
    shape = shape_field.get("value")

    fields = {}

    mappings = {
        "inline_min": [["inline_min"], ["inline_min_sampled"], ["inline", "min"]],
        "inline_max": [["inline_max"], ["inline_max_sampled"], ["inline", "max"]],
        "inline_count": [["inline_count"], ["inline", "count"]],
        "crossline_min": [["crossline_min"], ["crossline_min_sampled"], ["crossline", "min"]],
        "crossline_max": [["crossline_max"], ["crossline_max_sampled"], ["crossline", "max"]],
        "crossline_count": [["crossline_count"], ["crossline", "count"]],
        "trace_count": [["trace_count"], ["volume", "trace_count"], ["traces"], ["num_traces"]],
        "x_min": [["x_min"], ["cdp_x_min_sampled"], ["x", "min"]],
        "x_max": [["x_max"], ["cdp_x_max_sampled"], ["x", "max"]],
        "y_min": [["y_min"], ["cdp_y_min_sampled"], ["y", "min"]],
        "y_max": [["y_max"], ["cdp_y_max_sampled"], ["y", "max"]],
    }

    for field_name, key_paths in mappings.items():
        value = None
        for key_path in key_paths:
            value = _first_value(_deep_get(trace, key_path), _deep_get(viewer, key_path))
            if value is not None:
                break

        if value is not None:
            fields[field_name] = normalized_field(
                value,
                SOURCE_TRACE_HEADER_SUMMARY,
                1.0,
                STATUS_EXTRACTED,
                ["trace_header_summary", "viewer_metadata"],
            )
        else:
            fields[field_name] = missing_field(f"{field_name} not found")

    if isinstance(shape, list):
        if len(shape) == 2:
            if fields["trace_count"]["value"] is None:
                fields["trace_count"] = normalized_field(
                    shape[0],
                    SOURCE_VIEWER_METADATA,
                    1.0,
                    STATUS_EXTRACTED,
                    ["volume.shape"],
                )
        elif len(shape) >= 3:
            if fields["inline_count"]["value"] is None:
                fields["inline_count"] = normalized_field(
                    shape[0],
                    SOURCE_RULE_ENRICHED,
                    0.85,
                    STATUS_SUGGESTED,
                    ["zarr_shape"],
                )
            if fields["crossline_count"]["value"] is None:
                fields["crossline_count"] = normalized_field(
                    shape[1],
                    SOURCE_RULE_ENRICHED,
                    0.85,
                    STATUS_SUGGESTED,
                    ["zarr_shape"],
                )

    return fields


def _infer_quality(normalized: Dict[str, Any], evidence: Dict[str, Any]) -> dict:
    warnings = []

    if normalized["geometry"]["sample_interval_ms"]["value"] is None:
        warnings.append("Sample interval not found.")

    if normalized["geometry"]["sample_count"]["value"] is None:
        warnings.append("Sample count not found.")

    if normalized["coordinate_crs"]["epsg_code"]["value"] is None:
        warnings.append("CRS/EPSG not confirmed.")

    if not evidence.get("text_header"):
        warnings.append("SEG-Y textual header sidecar not found.")

    if not evidence.get("binary_header"):
        warnings.append("SEG-Y binary header sidecar not found.")

    total_fields = 0
    populated_fields = 0

    def walk(obj: Any):
        nonlocal total_fields, populated_fields
        if isinstance(obj, dict):
            if "value" in obj and "confidence" in obj:
                total_fields += 1
                if obj.get("value") is not None:
                    populated_fields += 1
            else:
                for v in obj.values():
                    walk(v)

    walk(normalized)

    completeness = round(populated_fields / total_fields, 3) if total_fields else 0.0

    return {
        "metadata_completeness_score": normalized_field(
            completeness,
            SOURCE_RULE_ENRICHED,
            0.95,
            STATUS_AUTO_APPLIED,
            ["normalized_field_population"],
        ),
        "warnings": warnings,
    }


def build_normalized_metadata(volume_id: str) -> dict:
    volume_path, evidence = load_metadata_evidence(volume_id)

    shape = _infer_shape(evidence)
    dataset_type = _infer_dataset_type(evidence, shape)
    sample_interval_ms = _infer_sample_interval_ms(evidence)
    sample_count = _infer_sample_count(shape, evidence)
    record_length_ms = _infer_record_length_ms(sample_interval_ms, sample_count)
    vertical_domain = _infer_vertical_domain(evidence)
    display_name = _infer_display_name(volume_id, evidence, dataset_type)
    geometry_fields = _infer_geometry_fields(evidence, shape)

    normalized = empty_normalized_metadata(
        volume_id=volume_id,
        volume_path=str(volume_path),
        evidence_paths=evidence["evidence_paths"],
    )

    normalized["identity"] = {
        "display_name": display_name,
        "dataset_type": dataset_type,
        "source_file_name": normalized_field(
            display_name["value"],
            display_name["source"],
            display_name["confidence"],
            display_name["status"],
            display_name["basis"],
        ),
        "survey_name": missing_field("survey name not confirmed"),
        "line_name": (
            display_name
            if dataset_type.get("value") == "2d_line"
            else missing_field("line name not applicable for 3D volume")
        ),
        "volume_name": (
            display_name
            if dataset_type.get("value") == "3d_volume"
            else missing_field("volume name not applicable for 2D line")
        ),
    }

    normalized["geometry"] = {
        **geometry_fields,
        "sample_count": sample_count,
        "sample_interval_ms": sample_interval_ms,
        "record_length_ms": record_length_ms,
        "vertical_domain": vertical_domain,
        "zarr_shape": shape,
    }

    normalized["coordinate_crs"] = {
        "crs_name": missing_field("CRS name not confirmed"),
        "epsg_code": missing_field("EPSG code not confirmed"),
        "crs_confidence": normalized_field(
            0.0,
            SOURCE_RULE_ENRICHED,
            1.0,
            STATUS_AUTO_APPLIED,
            ["no_confirmed_crs"],
        ),
    }

    normalized["processing"] = {
        "processing_stage": missing_field("processing stage not confirmed"),
        "migration_type": missing_field("migration type not confirmed"),
        "stack_type": missing_field("stack type not confirmed"),
        "domain": vertical_domain,
    }

    normalized["conversion"] = {
        "source_format": normalized_field(
            "SEG-Y",
            SOURCE_CONVERSION_METADATA,
            0.95,
            STATUS_AUTO_APPLIED,
            ["conversion_context"],
        ),
        "target_format": normalized_field(
            "Zarr",
            SOURCE_CONVERSION_METADATA,
            1.0,
            STATUS_AUTO_APPLIED,
            ["conversion_context"],
        ),
        "zarr_shape": shape,
        "zarr_chunks": missing_field("zarr chunks not found"),
        "geometry_source": missing_field("geometry source not found"),
    }

    dataset_type_value = (
        normalized.get("identity", {})
        .get("dataset_type", {})
        .get("value")
    )

    if dataset_type_value == "2D line":
        recommended_initial_view = "line"
        recommended_initial_view_confidence = 0.85
        recommended_initial_view_basis = ["2d_line_default"]
    else:
        recommended_initial_view = "inline"
        recommended_initial_view_confidence = 0.80
        recommended_initial_view_basis = ["3d_volume_default"]

    normalized["viewer_defaults"] = {
        "recommended_initial_view": normalized_field(
            recommended_initial_view,
            SOURCE_RULE_ENRICHED,
            recommended_initial_view_confidence,
            STATUS_SUGGESTED,
            recommended_initial_view_basis,
        ),
        "default_color_map": normalized_field(
            "seismic",
            SOURCE_RULE_ENRICHED,
            0.75,
            STATUS_SUGGESTED,
            ["viewer_default"],
        ),
        "default_gain": normalized_field(
            1.0,
            SOURCE_RULE_ENRICHED,
            0.75,
            STATUS_SUGGESTED,
            ["viewer_default"],
        ),
        "default_clip_percentile": normalized_field(
            99,
            SOURCE_RULE_ENRICHED,
            0.75,
            STATUS_SUGGESTED,
            ["viewer_default"],
        ),
    }

    normalized["quality"] = _infer_quality(normalized, evidence)

    save_normalized_metadata(volume_id, normalized)
    return normalized


__all__ = [
    "build_normalized_metadata",
    "get_normalized_metadata",
    "normalized_metadata_path",
    "resolve_volume_path",
]
