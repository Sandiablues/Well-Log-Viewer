"""
MultiViewer Well Log Viewer — LAS Import Service
WL-BUILD-001 scaffold

Backend owns all LAS parsing and curve extraction.
Frontend must never parse LAS files or construct curve samples independently.

This service is a placeholder skeleton for WL-BUILD-001.
Full LAS parsing (e.g. via lasio) will be wired in a later sprint.
"""

from __future__ import annotations

from typing import Any, List, Optional

import hashlib
import math
import re
from pathlib import Path

from app.knowledge.managed_repository import ManagedKRRepository
from app.knowledge.runtime_classification_service import (
    CurveClassificationBatchResult,
    CurveClassificationInput,
    RuntimeCurveClassificationService,
)
from app.knowledge.runtime_resolver import ApprovedKnowledgeRuntimeResolver

from .models import CurveMetadata, MsiDatasetRef, MsiSourceRef, Well


class LasImportError(Exception):
    """Raised when LAS import fails at any stage."""


class LasCurveInventoryClassificationResult:
    """Backend-owned classified LAS curve inventory contract.

    This object is produced from LAS curve metadata after parsing.  It is the
    integration boundary between LAS import/session inventory and KR runtime
    classification.  It does not parse LAS, does not mutate KR, and does not
    use candidate knowledge because classification is delegated to
    RuntimeCurveClassificationService.
    """

    def __init__(
        self,
        curve_metadata: List[CurveMetadata],
        classification_batch: CurveClassificationBatchResult,
    ) -> None:
        if len(curve_metadata) != classification_batch.curve_count:
            raise LasImportError(
                "Curve metadata and classification result counts do not match."
            )
        self.curve_metadata = list(curve_metadata)
        self.classification_batch = classification_batch

    @property
    def curve_count(self) -> int:
        return self.classification_batch.curve_count

    @property
    def resolved_count(self) -> int:
        return self.classification_batch.resolved_count

    @property
    def unknown_count(self) -> int:
        return self.classification_batch.unknown_count

    @property
    def review_required_count(self) -> int:
        return self.classification_batch.review_required_count

    @property
    def knowledge_policy(self) -> dict[str, Any]:
        return dict(self.classification_batch.knowledge_policy)

    def as_dict(self) -> dict[str, Any]:
        curves: list[dict[str, Any]] = []
        for metadata, classification in zip(
            self.curve_metadata,
            self.classification_batch.classifications,
        ):
            curves.append(
                {
                    "metadata": {
                        "mnemonic": metadata.mnemonic,
                        "unit": metadata.unit,
                        "description": metadata.description,
                        "null_value": metadata.null_value,
                    },
                    "classification": classification.as_dict(),
                }
            )
        return {
            "curve_count": self.curve_count,
            "resolved_count": self.resolved_count,
            "unknown_count": self.unknown_count,
            "review_required_count": self.review_required_count,
            "knowledge_policy": self.knowledge_policy,
            "curves": curves,
        }


    def mdp_summary(self) -> LasMdpCurveClassificationSummary:
        """Return a backend-owned summary for MDP/managed inventory display.

        The summary is derived only from this LAS inventory classification
        result.  It does not call frontend logic and does not read candidate KR
        records directly.  Runtime knowledge eligibility remains governed by
        the upstream approved-only classification batch.
        """
        display_group_counts: dict[str, int] = {}
        unknown_mnemonics: list[str] = []
        review_required_mnemonics: list[str] = []
        curves: list[dict[str, Any]] = []
        technical_curve_count = 0

        for metadata, classification in zip(
            self.curve_metadata,
            self.classification_batch.classifications,
        ):
            mnemonic = (metadata.mnemonic or "").strip()
            canonical_curve_id = getattr(classification, "canonical_curve_id", None)
            technical_curve_id = getattr(classification, "technical_curve_id", None)
            status = getattr(classification, "status", None)
            requires_review = bool(getattr(classification, "requires_review", False))

            display_group = canonical_curve_id or "unknown"
            display_group_counts[display_group] = display_group_counts.get(display_group, 0) + 1

            if technical_curve_id:
                technical_curve_count += 1
            if status == "unknown":
                unknown_mnemonics.append(mnemonic)
            if requires_review:
                review_required_mnemonics.append(mnemonic)

            curves.append(
                {
                    "mnemonic": mnemonic,
                    "unit": metadata.unit,
                    "description": metadata.description,
                    "status": status,
                    "requires_review": requires_review,
                    "canonical_curve_id": canonical_curve_id,
                    "technical_curve_id": technical_curve_id,
                    "display_name": getattr(classification, "display_name", None),
                    "product_group": getattr(classification, "product_group", None),
                    "product_subgroup": getattr(classification, "product_subgroup", None),
                    "measurement_family": getattr(classification, "measurement_family", None),
                    "measurement_depth": getattr(classification, "measurement_depth", None),
                    "tool_family": getattr(classification, "tool_family", None),
                }
            )

        return LasMdpCurveClassificationSummary(
            curve_count=self.curve_count,
            resolved_count=self.resolved_count,
            unknown_count=self.unknown_count,
            review_required_count=self.review_required_count,
            technical_curve_count=technical_curve_count,
            display_group_counts=display_group_counts,
            unknown_mnemonics=unknown_mnemonics,
            review_required_mnemonics=review_required_mnemonics,
            knowledge_policy=self.knowledge_policy,
            curves=curves,
        )

    def mdp_summary_dict(self) -> dict[str, Any]:
        """Return the MDP summary as a serializable dictionary."""
        return self.mdp_summary().as_dict()

    def wdv_template_recommendation(
        self,
        selected_mnemonics: Optional[List[str]] = None,
    ) -> LasWdvTemplateRecommendation:
        """Return a backend-owned WDV template recommendation.

        KR-TEMPLATE-1: This method derives a controlled Well Data Viewer
        template recommendation from the already-classified LAS curve inventory.
        It does not populate frontend tracks, does not mutate KR, and does not
        allow candidate knowledge to influence runtime truth.  The optional
        selected_mnemonics argument supports a build-from-selected workflow while
        preserving backend ownership of template logic.
        """
        selected_lookup: Optional[set[str]] = None
        if selected_mnemonics is not None:
            selected_lookup = {
                item.strip().upper()
                for item in selected_mnemonics
                if item is not None and item.strip()
            }

        selected_curves: list[dict[str, Any]] = []
        unresolved_mnemonics: list[str] = []
        grouped: dict[str, list[dict[str, Any]]] = {}

        for metadata, classification in zip(
            self.curve_metadata,
            self.classification_batch.classifications,
        ):
            mnemonic = (metadata.mnemonic or "").strip()
            normalized = mnemonic.upper()
            if selected_lookup is not None and normalized not in selected_lookup:
                continue

            status = getattr(classification, "status", None)
            canonical_curve_id = getattr(classification, "canonical_curve_id", None)
            curve_payload = {
                "mnemonic": mnemonic,
                "unit": metadata.unit,
                "description": metadata.description,
                "status": status,
                "canonical_curve_id": canonical_curve_id,
                "technical_curve_id": getattr(classification, "technical_curve_id", None),
                "display_name": getattr(classification, "display_name", None),
                "product_group": getattr(classification, "product_group", None),
                "product_subgroup": getattr(classification, "product_subgroup", None),
                "measurement_family": getattr(classification, "measurement_family", None),
                "measurement_depth": getattr(classification, "measurement_depth", None),
                "tool_family": getattr(classification, "tool_family", None),
            }
            selected_curves.append(curve_payload)

            if status == "unknown" or canonical_curve_id is None:
                unresolved_mnemonics.append(mnemonic)
                continue

            grouped.setdefault(str(canonical_curve_id), []).append(curve_payload)

        tracks = self._wdv_recommendation_tracks(grouped)
        canonical_ids = set(grouped.keys())
        has_gamma = "gamma_ray" in canonical_ids
        has_resistivity = bool(canonical_ids.intersection({"deep_resistivity", "shallow_resistivity"}))
        has_porosity = bool(canonical_ids.intersection({"bulk_density", "neutron_porosity"}))

        if has_gamma and has_resistivity and has_porosity:
            template_id = "triple_combo"
            template_name = "Triple Combo"
        elif tracks:
            template_id = "curve_inventory"
            template_name = "Classified Curve Inventory"
        else:
            template_id = "empty"
            template_name = "No Template Recommendation"

        warnings: list[str] = []
        if unresolved_mnemonics:
            warnings.append("Unresolved curves require review before template automation.")
        if selected_lookup is not None and not selected_curves:
            warnings.append("No selected mnemonics matched the classified LAS inventory.")

        return LasWdvTemplateRecommendation(
            template_id=template_id,
            template_name=template_name,
            recommendation_mode=(
                "build_from_selected"
                if selected_mnemonics is not None
                else "auto_build"
            ),
            available_curve_count=self.curve_count,
            selected_curve_count=len(selected_curves),
            tracks=tracks,
            unresolved_mnemonics=unresolved_mnemonics,
            knowledge_policy=self.knowledge_policy,
            warnings=warnings,
        )

    def wdv_template_recommendation_dict(
        self,
        selected_mnemonics: Optional[List[str]] = None,
    ) -> dict[str, Any]:
        """Return the WDV template recommendation as a serializable dictionary."""
        return self.wdv_template_recommendation(selected_mnemonics).as_dict()

    def qaqc_summary(self) -> LasCurveInventoryQaqcSummary:
        """Return a backend-owned QAQC summary for classified LAS curve inventory.

        KR-QAQC-1: This summary is derived from the classified inventory and
        backend template recommendation contract. It does not mutate KR, does
        not use frontend inference, and preserves the approved-only runtime
        knowledge policy from the upstream classification batch.
        """
        unknown_mnemonics: list[str] = []
        review_required_mnemonics: list[str] = []
        unit_gap_mnemonics: list[str] = []
        issues: list[dict[str, Any]] = []

        mnemonic_counts: dict[str, int] = {}
        canonical_counts: dict[str, int] = {}
        canonical_to_mnemonics: dict[str, list[str]] = {}

        for metadata, classification in zip(
            self.curve_metadata,
            self.classification_batch.classifications,
        ):
            mnemonic = (metadata.mnemonic or "").strip()
            normalized_mnemonic = mnemonic.upper()
            if normalized_mnemonic:
                mnemonic_counts[normalized_mnemonic] = mnemonic_counts.get(normalized_mnemonic, 0) + 1

            status = getattr(classification, "status", None)
            canonical_curve_id = getattr(classification, "canonical_curve_id", None)
            requires_review = bool(getattr(classification, "requires_review", False))

            if canonical_curve_id:
                canonical_key = str(canonical_curve_id)
                canonical_counts[canonical_key] = canonical_counts.get(canonical_key, 0) + 1
                canonical_to_mnemonics.setdefault(canonical_key, []).append(mnemonic)

            if status == "unknown" or canonical_curve_id is None:
                unknown_mnemonics.append(mnemonic)
                issues.append(
                    {
                        "issue_type": "unknown_curve",
                        "severity": "review_required",
                        "mnemonic": mnemonic,
                        "message": "Curve mnemonic is not resolved by approved runtime knowledge.",
                    }
                )

            if requires_review:
                review_required_mnemonics.append(mnemonic)
                issues.append(
                    {
                        "issue_type": "classification_review_required",
                        "severity": "review_required",
                        "mnemonic": mnemonic,
                        "message": "Curve classification requires backend review before automation.",
                    }
                )

            if canonical_curve_id and not (metadata.unit or "").strip():
                unit_gap_mnemonics.append(mnemonic)
                issues.append(
                    {
                        "issue_type": "unit_gap",
                        "severity": "warning",
                        "mnemonic": mnemonic,
                        "canonical_curve_id": canonical_curve_id,
                        "message": "Classified curve is missing a source unit.",
                    }
                )

        duplicate_mnemonics = sorted(
            mnemonic for mnemonic, count in mnemonic_counts.items() if count > 1
        )
        for mnemonic in duplicate_mnemonics:
            issues.append(
                {
                    "issue_type": "duplicate_mnemonic",
                    "severity": "warning",
                    "mnemonic": mnemonic,
                    "count": mnemonic_counts[mnemonic],
                    "message": "Duplicate source mnemonic appears in the LAS curve inventory.",
                }
            )

        duplicate_canonical_curve_ids = sorted(
            canonical_id for canonical_id, count in canonical_counts.items() if count > 1
        )
        for canonical_id in duplicate_canonical_curve_ids:
            issues.append(
                {
                    "issue_type": "duplicate_curve_category",
                    "severity": "info",
                    "canonical_curve_id": canonical_id,
                    "mnemonics": list(canonical_to_mnemonics.get(canonical_id, [])),
                    "count": canonical_counts[canonical_id],
                    "message": "Multiple curves map to the same backend display category.",
                }
            )

        canonical_ids = set(canonical_counts.keys())
        template_gap_groups: list[str] = []
        if "gamma_ray" not in canonical_ids:
            template_gap_groups.append("gamma_ray")
        if not canonical_ids.intersection({"deep_resistivity", "shallow_resistivity"}):
            template_gap_groups.append("resistivity")
        if not canonical_ids.intersection({"bulk_density", "neutron_porosity"}):
            template_gap_groups.append("porosity_density")

        for group in template_gap_groups:
            issues.append(
                {
                    "issue_type": "template_coverage_gap",
                    "severity": "info",
                    "template_group": group,
                    "message": "Recommended WDV template is missing this standard curve group.",
                }
            )

        warnings: list[str] = []
        if unknown_mnemonics:
            warnings.append("Unknown curves require review before automated display/template workflows.")
        if duplicate_mnemonics:
            warnings.append("Duplicate source mnemonics were detected in the curve inventory.")
        if unit_gap_mnemonics:
            warnings.append("One or more classified curves are missing source units.")
        if template_gap_groups:
            warnings.append("Standard WDV template coverage is incomplete for this curve inventory.")

        return LasCurveInventoryQaqcSummary(
            curve_count=self.curve_count,
            issue_count=len(issues),
            unknown_mnemonics=unknown_mnemonics,
            review_required_mnemonics=review_required_mnemonics,
            duplicate_mnemonics=duplicate_mnemonics,
            duplicate_canonical_curve_ids=duplicate_canonical_curve_ids,
            unit_gap_mnemonics=unit_gap_mnemonics,
            template_gap_groups=template_gap_groups,
            knowledge_policy=self.knowledge_policy,
            warnings=warnings,
            issues=issues,
        )

    def qaqc_summary_dict(self) -> dict[str, Any]:
        """Return the curve inventory QAQC summary as a serializable dictionary."""
        return self.qaqc_summary().as_dict()

    def _wdv_recommendation_tracks(
        self,
        grouped: dict[str, list[dict[str, Any]]],
    ) -> list[LasWdvTemplateTrackRecommendation]:
        track_rules = [
            ("gamma_ray", "Gamma Ray", ["gamma_ray"]),
            ("resistivity", "Resistivity", ["deep_resistivity", "shallow_resistivity"]),
            ("porosity_density", "Porosity / Density", ["bulk_density", "neutron_porosity"]),
            ("sonic", "Sonic", ["sonic"]),
        ]
        consumed: set[str] = set()
        tracks: list[LasWdvTemplateTrackRecommendation] = []

        for track_id, label, canonical_ids in track_rules:
            track_curves: list[dict[str, Any]] = []
            for canonical_id in canonical_ids:
                track_curves.extend(grouped.get(canonical_id, []))
                if canonical_id in grouped:
                    consumed.add(canonical_id)
            if track_curves:
                tracks.append(
                    LasWdvTemplateTrackRecommendation(
                        track_id=track_id,
                        label=label,
                        curve_mnemonics=[curve["mnemonic"] for curve in track_curves],
                        canonical_curve_ids=[
                            str(curve["canonical_curve_id"])
                            for curve in track_curves
                            if curve.get("canonical_curve_id")
                        ],
                        reason="Matched approved runtime curve classification.",
                    )
                )

        for canonical_id in sorted(set(grouped.keys()) - consumed):
            curves = grouped[canonical_id]
            tracks.append(
                LasWdvTemplateTrackRecommendation(
                    track_id=f"other_{canonical_id}",
                    label=str(canonical_id).replace("_", " ").title(),
                    curve_mnemonics=[curve["mnemonic"] for curve in curves],
                    canonical_curve_ids=[canonical_id],
                    reason="Classified curve does not map to a standard WDV template track yet.",
                )
            )

        return tracks


class LasMdpCurveClassificationSummary:
    """Backend-owned MDP curve classification summary contract.

    KR-MDP-1-R3: This is a compact summary derived from the approved-only
    LAS/KR classification result.  It is intended for MDP/managed inventory
    display and workflow decisions.  It does not classify curves itself, does
    not parse LAS, does not mutate KR, and does not use frontend inference.
    """

    def __init__(
        self,
        *,
        curve_count: int,
        resolved_count: int,
        unknown_count: int,
        review_required_count: int,
        technical_curve_count: int,
        display_group_counts: dict[str, int],
        unknown_mnemonics: list[str],
        review_required_mnemonics: list[str],
        knowledge_policy: dict[str, Any],
        curves: list[dict[str, Any]],
    ) -> None:
        self.curve_count = int(curve_count)
        self.resolved_count = int(resolved_count)
        self.unknown_count = int(unknown_count)
        self.review_required_count = int(review_required_count)
        self.technical_curve_count = int(technical_curve_count)
        self.display_group_counts = dict(display_group_counts)
        self.unknown_mnemonics = list(unknown_mnemonics)
        self.review_required_mnemonics = list(review_required_mnemonics)
        self.knowledge_policy = dict(knowledge_policy)
        self.curves = list(curves)

    @property
    def has_unknown_curves(self) -> bool:
        return self.unknown_count > 0

    @property
    def has_review_required_curves(self) -> bool:
        return self.review_required_count > 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "curve_count": self.curve_count,
            "resolved_count": self.resolved_count,
            "unknown_count": self.unknown_count,
            "review_required_count": self.review_required_count,
            "technical_curve_count": self.technical_curve_count,
            "has_unknown_curves": self.has_unknown_curves,
            "has_review_required_curves": self.has_review_required_curves,
            "display_group_counts": dict(self.display_group_counts),
            "unknown_mnemonics": list(self.unknown_mnemonics),
            "review_required_mnemonics": list(self.review_required_mnemonics),
            "knowledge_policy": dict(self.knowledge_policy),
            "curves": list(self.curves),
        }


class LasWdvTemplateTrackRecommendation:
    """Backend-owned WDV track recommendation contract."""

    def __init__(
        self,
        *,
        track_id: str,
        label: str,
        curve_mnemonics: list[str],
        canonical_curve_ids: list[str],
        reason: str,
    ) -> None:
        self.track_id = track_id
        self.label = label
        self.curve_mnemonics = list(curve_mnemonics)
        self.canonical_curve_ids = list(canonical_curve_ids)
        self.reason = reason

    def as_dict(self) -> dict[str, Any]:
        return {
            "track_id": self.track_id,
            "label": self.label,
            "curve_mnemonics": list(self.curve_mnemonics),
            "canonical_curve_ids": list(self.canonical_curve_ids),
            "reason": self.reason,
        }


class LasWdvTemplateRecommendation:
    """Backend-owned WDV template recommendation contract.

    KR-TEMPLATE-1: This object describes what the backend recommends the WDV
    may offer to load.  It is not a frontend rendering instruction and does not
    auto-populate tracks.
    """

    def __init__(
        self,
        *,
        template_id: str,
        template_name: str,
        recommendation_mode: str,
        available_curve_count: int,
        selected_curve_count: int,
        tracks: list[LasWdvTemplateTrackRecommendation],
        unresolved_mnemonics: list[str],
        knowledge_policy: dict[str, Any],
        warnings: list[str],
    ) -> None:
        self.template_id = template_id
        self.template_name = template_name
        self.recommendation_mode = recommendation_mode
        self.available_curve_count = int(available_curve_count)
        self.selected_curve_count = int(selected_curve_count)
        self.tracks = list(tracks)
        self.unresolved_mnemonics = list(unresolved_mnemonics)
        self.knowledge_policy = dict(knowledge_policy)
        self.warnings = list(warnings)

    @property
    def has_recommendation(self) -> bool:
        return bool(self.tracks)

    def as_dict(self) -> dict[str, Any]:
        return {
            "template_id": self.template_id,
            "template_name": self.template_name,
            "recommendation_mode": self.recommendation_mode,
            "available_curve_count": self.available_curve_count,
            "selected_curve_count": self.selected_curve_count,
            "has_recommendation": self.has_recommendation,
            "tracks": [track.as_dict() for track in self.tracks],
            "unresolved_mnemonics": list(self.unresolved_mnemonics),
            "knowledge_policy": dict(self.knowledge_policy),
            "warnings": list(self.warnings),
        }


class LasCurveInventoryQaqcSummary:
    """Backend-owned QAQC summary for classified LAS curve inventory.

    KR-QAQC-1: This contract summarizes review conditions that downstream MDP
    and WDV workflows may display or act upon. It is derived from approved-only
    runtime classification results and source curve metadata only.
    """

    def __init__(
        self,
        *,
        curve_count: int,
        issue_count: int,
        unknown_mnemonics: list[str],
        review_required_mnemonics: list[str],
        duplicate_mnemonics: list[str],
        duplicate_canonical_curve_ids: list[str],
        unit_gap_mnemonics: list[str],
        template_gap_groups: list[str],
        knowledge_policy: dict[str, Any],
        warnings: list[str],
        issues: list[dict[str, Any]],
    ) -> None:
        self.curve_count = int(curve_count)
        self.issue_count = int(issue_count)
        self.unknown_mnemonics = list(unknown_mnemonics)
        self.review_required_mnemonics = list(review_required_mnemonics)
        self.duplicate_mnemonics = list(duplicate_mnemonics)
        self.duplicate_canonical_curve_ids = list(duplicate_canonical_curve_ids)
        self.unit_gap_mnemonics = list(unit_gap_mnemonics)
        self.template_gap_groups = list(template_gap_groups)
        self.knowledge_policy = dict(knowledge_policy)
        self.warnings = list(warnings)
        self.issues = list(issues)

    @property
    def has_issues(self) -> bool:
        return self.issue_count > 0

    @property
    def has_review_blockers(self) -> bool:
        return bool(self.unknown_mnemonics or self.review_required_mnemonics)

    def as_dict(self) -> dict[str, Any]:
        return {
            "curve_count": self.curve_count,
            "issue_count": self.issue_count,
            "has_issues": self.has_issues,
            "has_review_blockers": self.has_review_blockers,
            "unknown_mnemonics": list(self.unknown_mnemonics),
            "review_required_mnemonics": list(self.review_required_mnemonics),
            "duplicate_mnemonics": list(self.duplicate_mnemonics),
            "duplicate_canonical_curve_ids": list(self.duplicate_canonical_curve_ids),
            "unit_gap_mnemonics": list(self.unit_gap_mnemonics),
            "template_gap_groups": list(self.template_gap_groups),
            "knowledge_policy": dict(self.knowledge_policy),
            "warnings": list(self.warnings),
            "issues": list(self.issues),
        }


class LasCurveSamples:
    """One source-ordered LAS curve and its backend-owned samples."""

    def __init__(
        self,
        *,
        curve_index: int,
        mnemonic: str,
        unit: Optional[str],
        description: Optional[str],
        values: List[Optional[float]],
    ) -> None:
        self.curve_index = int(curve_index)
        self.mnemonic = mnemonic
        self.unit = unit
        self.description = description
        self.values = list(values)

    @property
    def sample_count(self) -> int:
        return len(self.values)

    def as_dict(self) -> dict[str, Any]:
        return {
            "curve_index": self.curve_index,
            "mnemonic": self.mnemonic,
            "unit": self.unit,
            "description": self.description,
            "sample_count": self.sample_count,
            "values": list(self.values),
        }


class LasImportResult:
    """Backend-owned parsed LAS product contract.

    The original source fingerprint, source-ordered curve metadata, depth
    samples, and all curve samples remain correlated in one result. Duplicate
    mnemonics are deliberately preserved by curve index.
    """

    def __init__(
        self,
        well: Well,
        curve_metadata: List[CurveMetadata],
        depth_unit: str,
        null_value: Optional[float],
        raw_header: dict,
        *,
        source_fingerprint: str,
        las_version: Optional[str],
        wrap: bool,
        depth_mnemonic: str,
        depth_values: List[Optional[float]],
        curves: List[LasCurveSamples],
        source_bytes: bytes,
        warnings: Optional[List[str]] = None,
    ) -> None:
        self.well = well
        self.curve_metadata = list(curve_metadata)
        self.depth_unit = depth_unit
        self.null_value = null_value
        self.raw_header = raw_header
        self.source_fingerprint = source_fingerprint
        self.las_version = las_version
        self.wrap = bool(wrap)
        self.depth_mnemonic = depth_mnemonic
        self.depth_values = list(depth_values)
        self.curves = list(curves)
        self.source_bytes = bytes(source_bytes)
        self.warnings = list(warnings or [])

    @property
    def sample_count(self) -> int:
        return len(self.depth_values)

    @property
    def curve_count(self) -> int:
        return len(self.curves)

    def as_dict(self, *, include_samples: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "well": self.well.model_dump(mode="json"),
            "curve_metadata": [item.model_dump(mode="json") for item in self.curve_metadata],
            "depth_unit": self.depth_unit,
            "null_value": self.null_value,
            "raw_header": self.raw_header,
            "source_fingerprint": self.source_fingerprint,
            "las_version": self.las_version,
            "wrap": self.wrap,
            "depth_mnemonic": self.depth_mnemonic,
            "sample_count": self.sample_count,
            "curve_count": self.curve_count,
            "warnings": list(self.warnings),
        }
        if include_samples:
            payload["depth_values"] = list(self.depth_values)
            payload["curves"] = [curve.as_dict() for curve in self.curves]
        return payload


class LasImportService:
    """Canonical backend LAS parser and approved-KR classification boundary."""

    _GENERIC_IDENTITIES = {
        "WELL", "WELL NAME", "WELL ID", "WELLID", "UNIQUE WELL ID",
        "UWI", "API", "UNKNOWN", "N/A", "NA", "NONE", "NULL",
    }
    _DEPTH_MNEMONICS = {"DEPT", "DEPTH", "MD", "TDEP"}

    def __init__(
        self,
        classification_service: Optional[RuntimeCurveClassificationService] = None,
    ) -> None:
        self._classification_service = (
            classification_service
            if classification_service is not None
            else RuntimeCurveClassificationService(
                ApprovedKnowledgeRuntimeResolver(ManagedKRRepository())
            )
        )

    def classify_curve_metadata(
        self,
        curve_metadata: List[CurveMetadata],
    ) -> LasCurveInventoryClassificationResult:
        if curve_metadata is None:
            raise LasImportError("curve_metadata is required")
        inputs: list[CurveClassificationInput] = []
        for index, metadata in enumerate(curve_metadata):
            mnemonic = (metadata.mnemonic or "").strip()
            inputs.append(
                CurveClassificationInput(
                    curve_id=mnemonic or f"las_curve_{index}",
                    source_mnemonic=mnemonic,
                    unit=metadata.unit,
                    description=metadata.description,
                    source_curve_index=index,
                    context={"null_value": metadata.null_value},
                )
            )
        batch = self._classification_service.classify_curves(inputs)
        return LasCurveInventoryClassificationResult(
            curve_metadata=list(curve_metadata), classification_batch=batch
        )

    def import_from_path(self, file_path: str, source_ref: MsiSourceRef) -> LasImportResult:
        path = Path(file_path)
        if not path.is_file():
            raise LasImportError(f"LAS source file does not exist: {file_path}")
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise LasImportError(f"Could not read LAS source file: {file_path}") from exc
        if source_ref.filename is None:
            source_ref = source_ref.model_copy(update={"filename": path.name})
        return self.import_from_bytes(payload, source_ref)

    def import_from_bytes(self, file_bytes: bytes, source_ref: MsiSourceRef) -> LasImportResult:
        if not isinstance(file_bytes, (bytes, bytearray)) or not file_bytes:
            raise LasImportError("LAS source bytes are required")
        if not source_ref or not (source_ref.source_id or "").strip():
            raise LasImportError("A registered MSI source reference is required")

        payload = bytes(file_bytes)
        text = self._decode(payload)
        sections = self._sections(text)
        version_lines = sections.get("VERSION", []) + sections.get("V", [])
        well_lines = sections.get("WELL", []) + sections.get("W", [])
        curve_lines = sections.get("CURVE", []) + sections.get("C", [])
        ascii_lines = sections.get("ASCII", []) + sections.get("A", [])
        if not curve_lines:
            raise LasImportError("LAS curve section is missing or empty")
        if not ascii_lines:
            raise LasImportError("LAS ASCII data section is missing or empty")

        version_header = self._header_map(version_lines)
        well_header = self._header_map(well_lines)
        curves_header = self._parse_header_lines(curve_lines)
        if not curves_header:
            raise LasImportError("LAS curve definitions could not be parsed")

        version = self._header_value(version_header, "VERS")
        wrap_value = (self._header_value(version_header, "WRAP") or "NO").strip().upper()
        wrap = wrap_value.startswith("Y")
        null_value = self._float_header(well_header, "NULL")
        rows = self._ascii_rows(ascii_lines, len(curves_header), wrap=wrap)
        if not rows:
            raise LasImportError("LAS ASCII data contains no numeric samples")

        warnings: list[str] = []
        if any(len(row) != len(curves_header) for row in rows):
            raise LasImportError("LAS sample column count does not match curve definitions")

        depth_index = self._depth_index(curves_header)
        depth_def = curves_header[depth_index]
        depth_values = [self._clean_sample(row[depth_index], null_value) for row in rows]
        depth_unit = self._normalize_depth_unit(depth_def[1] or self._header_unit(well_header, "STRT") or "ft")

        curve_metadata: list[CurveMetadata] = []
        curve_samples: list[LasCurveSamples] = []
        for index, (mnemonic, unit, _value, description) in enumerate(curves_header):
            if index == depth_index:
                continue
            values = [self._clean_sample(row[index], null_value) for row in rows]
            curve_metadata.append(
                CurveMetadata(
                    mnemonic=mnemonic,
                    unit=unit,
                    description=description,
                    null_value=null_value,
                )
            )
            curve_samples.append(
                LasCurveSamples(
                    curve_index=index,
                    mnemonic=mnemonic,
                    unit=unit,
                    description=description,
                    values=values,
                )
            )

        raw_well_name = self._first_header_value(well_header, ("WELL", "WEL", "WELLNAME", "NAME"))
        raw_well_id = self._first_header_value(well_header, ("UWI", "API", "WELLID", "WELL_ID"))
        well_name = self._clean_identity(raw_well_name)
        well_id = self._clean_identity(raw_well_id)
        if well_name is None:
            warnings.append("LAS well name is missing or generic and requires managed-well resolution.")
            well_name = (source_ref.filename or source_ref.source_id).rsplit(".", 1)[0]
        if well_id is None:
            warnings.append("LAS UWI/API is missing or generic; source identity is used until resolution.")
            well_id = f"las-source-{hashlib.sha256(payload).hexdigest()[:16]}"

        fingerprint = hashlib.sha256(payload).hexdigest()
        well = Well(
            well_id=well_id,
            well_name=well_name,
            dataset_ref=MsiDatasetRef(
                dataset_id=f"las-product:{fingerprint}",
                display_name=source_ref.filename or well_name,
            ),
            source_ref=source_ref,
        )
        raw_header = {
            "version": version_header,
            "well": well_header,
            "curves": [
                {"mnemonic": m, "unit": u, "value": v, "description": d}
                for m, u, v, d in curves_header
            ],
        }
        return LasImportResult(
            well=well,
            curve_metadata=curve_metadata,
            depth_unit=depth_unit,
            null_value=null_value,
            raw_header=raw_header,
            source_fingerprint=fingerprint,
            las_version=version,
            wrap=wrap,
            depth_mnemonic=depth_def[0],
            depth_values=depth_values,
            curves=curve_samples,
            source_bytes=payload,
            warnings=warnings,
        )

    @staticmethod
    def _decode(payload: bytes) -> str:
        for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                return payload.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise LasImportError("LAS source encoding is unsupported")

    @staticmethod
    def _sections(text: str) -> dict[str, list[str]]:
        aliases = {"V": "VERSION", "W": "WELL", "C": "CURVE", "P": "PARAMETER", "O": "OTHER", "A": "ASCII"}
        sections: dict[str, list[str]] = {}
        current: Optional[str] = None
        for raw in text.splitlines():
            stripped = raw.strip()
            if not stripped:
                continue
            if stripped.startswith("~"):
                label = stripped[1:].split(maxsplit=1)[0].upper()
                current = aliases.get(label, label)
                sections.setdefault(current, [])
            elif current is not None:
                sections[current].append(raw)
        return sections

    @staticmethod
    def _parse_header_lines(lines: List[str]) -> list[tuple[str, Optional[str], Optional[str], Optional[str]]]:
        result = []
        for raw in lines:
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            left, sep, right = stripped.partition(":")
            description = right.strip() or None if sep else None
            match = re.match(r"^\s*([^\s.]+)\s*\.\s*([^\s]*)\s*(.*?)\s*$", left)
            if not match:
                continue
            mnemonic = match.group(1).strip()
            unit = match.group(2).strip() or None
            value = match.group(3).strip() or None
            result.append((mnemonic, unit, value, description))
        return result

    @classmethod
    def _header_map(cls, lines: List[str]) -> dict[str, dict[str, Optional[str]]]:
        out: dict[str, dict[str, Optional[str]]] = {}
        value_keys = {
            "VERS", "WRAP", "DLM", "WELL", "WEL", "WELLNAME", "NAME",
            "UWI", "API", "WELLID", "WELL_ID", "FLD", "FIELD", "COMP",
            "COMPANY", "CTRY", "COUNTRY", "LOC", "SRVC", "DATE", "NULL",
        }
        for mnemonic, unit, value, description in cls._parse_header_lines(lines):
            key = mnemonic.upper()
            # These LAS records carry their value after the dot and do not have
            # a physical unit. The generic header regex cannot distinguish the
            # first value token from a unit, so join it back explicitly.
            if key in value_keys and unit is not None:
                value = " ".join(part for part in (unit, value) if part)
                unit = None
            elif value is None and unit is not None:
                value, unit = unit, None
            out[key] = {"unit": unit, "value": value, "description": description}
        return out

    @staticmethod
    def _header_value(header: dict[str, dict[str, Optional[str]]], key: str) -> Optional[str]:
        item = header.get(key.upper())
        return item.get("value") if item else None

    @staticmethod
    def _header_unit(header: dict[str, dict[str, Optional[str]]], key: str) -> Optional[str]:
        item = header.get(key.upper())
        return item.get("unit") if item else None

    @classmethod
    def _first_header_value(cls, header: dict[str, dict[str, Optional[str]]], keys: tuple[str, ...]) -> Optional[str]:
        for key in keys:
            value = cls._header_value(header, key)
            if value:
                return value
        return None

    @classmethod
    def _float_header(cls, header: dict[str, dict[str, Optional[str]]], key: str) -> Optional[float]:
        value = cls._header_value(header, key)
        try:
            return float(value) if value is not None else None
        except ValueError:
            return None

    @staticmethod
    def _ascii_rows(lines: List[str], column_count: int, *, wrap: bool) -> list[list[float]]:
        rows: list[list[float]] = []
        pending: list[float] = []
        for raw in lines:
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            values: list[float] = []
            for token in stripped.replace(",", " ").split():
                try:
                    values.append(float(token))
                except ValueError as exc:
                    raise LasImportError(f"Non-numeric LAS ASCII token: {token}") from exc
            if wrap:
                pending.extend(values)
                while len(pending) >= column_count:
                    rows.append(pending[:column_count])
                    pending = pending[column_count:]
            elif values:
                rows.append(values)
        if pending:
            raise LasImportError("Wrapped LAS ASCII data ends with an incomplete sample row")
        return rows

    @classmethod
    def _depth_index(cls, curves: list[tuple[str, Optional[str], Optional[str], Optional[str]]]) -> int:
        for index, item in enumerate(curves):
            if item[0].strip().upper() in cls._DEPTH_MNEMONICS:
                return index
        return 0

    @staticmethod
    def _clean_sample(value: float, null_value: Optional[float]) -> Optional[float]:
        if not math.isfinite(value):
            return None
        if null_value is not None and math.isclose(value, null_value, rel_tol=0.0, abs_tol=1e-12):
            return None
        return value

    @classmethod
    def _clean_identity(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = re.sub(r"\s+", " ", value.strip())
        if not cleaned or cleaned.upper() in cls._GENERIC_IDENTITIES:
            return None
        return cleaned

    @staticmethod
    def _normalize_depth_unit(unit: str) -> str:
        normalized = unit.strip().lower()
        if normalized in {"m", "meter", "meters", "metre", "metres"}:
            return "m"
        if normalized in {"f", "ft", "feet", "foot"}:
            return "ft"
        return normalized or "ft"

