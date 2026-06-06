from __future__ import annotations

from pathlib import Path
from typing import Any


def _name(value: Any) -> str:
    if value is None:
        return ""
    try:
        return Path(str(value)).name
    except Exception:
        return str(value)


def classify_document_name(name: Any) -> dict[str, Any]:
    filename = _name(name)
    lower = filename.lower()

    document_type = "unknown"
    document_role = "unknown"
    confidence = "low"
    reasons: list[str] = []

    if "processing" in lower or "proc" in lower:
        document_type = "processing_report"
        document_role = "processing_report"
        confidence = "medium"
        reasons.append("filename contains processing/proc")
    elif "acquisition" in lower or "acq" in lower:
        document_type = "acquisition_report"
        document_role = "acquisition_report"
        confidence = "medium"
        reasons.append("filename contains acquisition/acq")
    elif "qc" in lower:
        document_type = "qc_report"
        document_role = "qc_report"
        confidence = "medium"
        reasons.append("filename contains qc")
    elif lower.endswith((".pdf", ".doc", ".docx", ".txt", ".xls", ".xlsx")):
        document_type = "supporting_document"
        document_role = "supporting_document"
        confidence = "low"
        reasons.append("recognized document extension")

    return {
        "filename": filename,
        "document_type": document_type,
        "document_role": document_role,
        "classification": document_type,
        "confidence": confidence,
        "classification_confidence": confidence,
        "reasons": reasons,
        "classification_reasons": reasons,
        "source": "knowledge_compatibility_module",
    }


def classify_segy_name(name: Any) -> dict[str, Any]:
    filename = _name(name)
    lower = filename.lower()

    candidate_kind = "segy"
    candidate_role = "candidate"
    confidence = "low"
    reasons: list[str] = []

    if lower.endswith((".sgy", ".segy")):
        confidence = "medium"
        reasons.append("recognized SEG-Y extension")

    if ".2d." in lower or lower.endswith("2d.sgy") or lower.endswith("2d.segy"):
        candidate_kind = "2d_line"
        candidate_role = "line_candidate"
        confidence = "medium"
        reasons.append("filename indicates 2D")
    elif any(token in lower for token in ["3d", "volume", "cube", "subvolume", "inline", "crossline"]):
        candidate_kind = "3d_volume"
        candidate_role = "volume_candidate"
        confidence = "medium"
        reasons.append("filename indicates 3D/volume")

    return {
        "filename": filename,
        "candidate_kind": candidate_kind,
        "candidate_role": candidate_role,
        "classification": candidate_kind,
        "confidence": confidence,
        "classification_confidence": confidence,
        "reasons": reasons,
        "classification_reasons": reasons,
        "source": "knowledge_compatibility_module",
    }


def extract_processing_hints(name: Any) -> dict[str, Any]:
    filename = _name(name)
    lower = filename.lower()
    hints: list[str] = []

    for token in [
        "pst", "pstm", "psdm", "migration", "migrated", "stack", "final",
        "filtered", "reprocess", "prestack", "poststack"
    ]:
        if token in lower:
            hints.append(token)

    return {
        "filename": filename,
        "processing_hints": hints,
        "hints": hints,
        "source": "knowledge_compatibility_module",
    }


def build_qaqc_flags(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
    return []
