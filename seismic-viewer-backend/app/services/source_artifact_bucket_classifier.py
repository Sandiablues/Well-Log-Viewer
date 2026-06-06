"""
Source artifact bucket classifier for Source Intake / QAQC load sheets.

Purpose:
- Keep raw discovery broad: do not hide files.
- Classify discovered source files into simple review buckets.
- Avoid falsely labeling associated geoscience data as supporting documents.
- Keep deterministic rules here before any future AI/knowledge-assist layer.

Primary load-sheet buckets:
1. segy_data
2. supporting_document_high_confidence
3. supporting_associated_file_low_confidence
4. review_required

This service is intentionally conservative. When in doubt, it places non-SEG-Y
items into supporting_associated_file_low_confidence or review_required rather
than pretending the item is a true supporting document.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List, Optional


SEGY_EXTENSIONS = {".sgy", ".segy"}
HIGH_CONF_DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".rtf"}
TEXT_LIKE_EXTENSIONS = {".txt", ".csv", ".dat", ".asc", ".xyz", ".las"}
ARCHIVE_EXTENSIONS = {".zip", ".tar", ".gz", ".tgz", ".7z", ".rar"}


@dataclass(frozen=True)
class SourceArtifactClassification:
    artifact_bucket: str
    artifact_class: str
    artifact_subtype: str
    intake_role: str
    classification_confidence: str
    classification_source: str
    classification_reasons: List[str]
    stageable_as_primary: bool = False
    stageable_as_documentary_evidence: bool = False
    stageable_as_associated_file: bool = False
    user_confirmed_bucket: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _norm(value: str | None) -> str:
    return str(value or "").strip().lower()


def _tokens(filename: str, relative_path: str = "") -> str:
    text = f"{relative_path} {filename}".lower()
    text = text.replace("\\", "/")
    text = re.sub(r"[_\-.]+", " ", text)
    return text


def _has_any(text: str, terms: Iterable[str]) -> bool:
    return any(term in text for term in terms)


def classify_source_artifact(
    filename: str,
    relative_path: str = "",
    item_type: str | None = None,
    candidate_kind: str | None = None,
    candidate_role: str | None = None,
    document_type: str | None = None,
) -> SourceArtifactClassification:
    """
    Classify a discovered source file into a load-sheet review bucket.

    This classifier should be called by backend discovery/load-sheet services.
    It should not be implemented in the React UI.
    """

    name = filename or Path(relative_path or "").name
    suffix = Path(name).suffix.lower()
    text = _tokens(name, relative_path)
    item = _norm(item_type)
    kind = _norm(candidate_kind)
    role = _norm(candidate_role)
    doc_type = _norm(document_type)

    reasons: List[str] = []
    if suffix:
        reasons.append(f"extension={suffix}")
    if relative_path:
        parts = [p for p in relative_path.replace("\\", "/").split("/") if p]
        if len(parts) > 1:
            reasons.append(f"folder_context={'/'.join(parts[:-1])}")

    # 1) SEG-Y data.
    if suffix in SEGY_EXTENSIONS or item == "segy_file":
        if kind:
            reasons.append(f"candidate_kind={kind}")
        if role:
            reasons.append(f"candidate_role={role}")

        subtype = "segy"
        confidence = "high" if kind in {"3d_volume", "2d_line"} else "medium"
        stageable_primary = kind == "3d_volume" and role == "volume_candidate"

        return SourceArtifactClassification(
            artifact_bucket="segy_data",
            artifact_class="seismic_data",
            artifact_subtype=subtype,
            intake_role="primary_candidate" if stageable_primary else "review_required",
            classification_confidence=confidence,
            classification_source="deterministic_rule",
            classification_reasons=reasons or ["segy_extension_or_item_type"],
            stageable_as_primary=stageable_primary,
        )

    # 2) High-confidence documentary evidence.
    # Extension alone is not enough for TXT/CSV because these often carry
    # horizons, faults, velocity functions, well tracks, markers, etc.
    report_terms = {
        "report", "processing report", "acquisition report", "qc report",
        "quality control", "observer", "observer log", "field report",
        "navigation report", "nav report", "crs", "coordinate reference",
        "projection", "readme", "manifest", "delivery note", "metadata note",
        "transmittal",
    }

    if suffix in HIGH_CONF_DOCUMENT_EXTENSIONS or _has_any(text, report_terms) or doc_type in {
        "processing_report",
        "acquisition_report",
        "qc_report",
        "observer_log",
        "navigation_report",
        "delivery_manifest",
        "readme_metadata",
        "crs_note",
    }:
        subtype = "supporting_document"
        if "processing" in text:
            subtype = "processing_report"
        elif "acquisition" in text:
            subtype = "acquisition_report"
        elif "observer" in text:
            subtype = "observer_log"
        elif "navigation" in text or " nav " in f" {text} ":
            subtype = "navigation_report"
        elif "qc" in text or "quality control" in text:
            subtype = "qc_report"
        elif "readme" in text or "metadata" in text:
            subtype = "readme_metadata"
        elif "manifest" in text or "delivery" in text or "transmittal" in text:
            subtype = "delivery_manifest"
        elif "crs" in text or "coordinate reference" in text or "projection" in text:
            subtype = "crs_note"

        reasons.append("documentary_evidence_pattern")
        return SourceArtifactClassification(
            artifact_bucket="supporting_document_high_confidence",
            artifact_class="supporting_document",
            artifact_subtype=subtype,
            intake_role="documentary_evidence",
            classification_confidence="high",
            classification_source="deterministic_rule",
            classification_reasons=reasons,
            stageable_as_documentary_evidence=True,
        )

    # 3) Associated / supporting files, low confidence.
    # These are likely relevant source delivery artifacts, but not documentary
    # evidence. The user should review and decide how to handle them.
    associated_patterns = [
        ("horizon_surface", {"horizon", "surface", "top foresets", "truncation"}),
        ("fault_interpretation", {"fault"}),
        ("velocity_function", {"velocity", "velocities", "vfunc", "velocity function"}),
        ("well_log_las", {".las", " las ", "log", "logs"}),
        ("well_marker", {"marker", "markers", "tops"}),
        ("well_trajectory", {"welltrack", "well track", "trajectory", "deviation", "survey"}),
        ("time_depth_control", {"dt tvdss", "tvdss", "time depth", "depth time", "td", "checkshot"}),
        ("well_data_archive", {"all wells", "rawdata", "raw data", "well data"}),
    ]

    for subtype, terms in associated_patterns:
        if _has_any(text, terms) or (subtype == "well_log_las" and suffix == ".las"):
            reasons.append(f"associated_geoscience_pattern={subtype}")
            return SourceArtifactClassification(
                artifact_bucket="supporting_associated_file_low_confidence",
                artifact_class="associated_geoscience_file",
                artifact_subtype=subtype,
                intake_role="associated_file_review",
                classification_confidence="low",
                classification_source="deterministic_rule",
                classification_reasons=reasons,
                stageable_as_associated_file=True,
            )

    if suffix in ARCHIVE_EXTENSIONS:
        reasons.append("archive_extension")
        return SourceArtifactClassification(
            artifact_bucket="supporting_associated_file_low_confidence",
            artifact_class="archive_bundle",
            artifact_subtype="archive_bundle",
            intake_role="associated_file_review",
            classification_confidence="low",
            classification_source="deterministic_rule",
            classification_reasons=reasons,
            stageable_as_associated_file=True,
        )

    if suffix in TEXT_LIKE_EXTENSIONS:
        reasons.append("text_like_file_not_documentary_evidence")
        return SourceArtifactClassification(
            artifact_bucket="supporting_associated_file_low_confidence",
            artifact_class="associated_or_unknown_file",
            artifact_subtype="text_like_unknown",
            intake_role="associated_file_review",
            classification_confidence="low",
            classification_source="deterministic_rule",
            classification_reasons=reasons,
            stageable_as_associated_file=True,
        )

    # 4) Unknown / review required.
    reasons.append("no_confident_rule_match")
    return SourceArtifactClassification(
        artifact_bucket="review_required",
        artifact_class="unknown",
        artifact_subtype="unknown",
        intake_role="review_required",
        classification_confidence="low",
        classification_source="deterministic_rule",
        classification_reasons=reasons,
    )


def classify_source_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convenience helper for existing registry records.
    Returns original record plus artifact classification fields.
    """
    filename = (
        record.get("filename")
        or record.get("name")
        or Path(str(record.get("relative_path") or "")).name
    )

    classification = classify_source_artifact(
        filename=filename,
        relative_path=str(record.get("relative_path") or ""),
        item_type=record.get("item_type"),
        candidate_kind=record.get("candidate_kind"),
        candidate_role=record.get("candidate_role"),
        document_type=record.get("document_type"),
    ).to_dict()

    merged = dict(record)
    merged.update(classification)
    return merged
