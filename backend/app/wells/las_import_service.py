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

from backend.app.knowledge.managed_repository import ManagedKRRepository
from backend.app.knowledge.runtime_classification_service import (
    CurveClassificationBatchResult,
    CurveClassificationInput,
    RuntimeCurveClassificationService,
)
from backend.app.knowledge.runtime_resolver import ApprovedKnowledgeRuntimeResolver

from .models import CurveMetadata, MsiSourceRef, Well


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


class LasImportResult:
    """
    Value object returned by a successful LAS import.

    Populated by the backend parser; never constructed on the frontend.
    """

    def __init__(
        self,
        well: Well,
        curve_metadata: List[CurveMetadata],
        depth_unit: str,
        null_value: Optional[float],
        raw_header: dict,
    ) -> None:
        self.well = well
        self.curve_metadata = curve_metadata
        self.depth_unit = depth_unit
        self.null_value = null_value
        self.raw_header = raw_header


class LasImportService:
    """
    Backend-owned service responsible for:
    - Receiving a LAS source file (path or bytes)
    - Parsing well header and curve sections
    - Extracting curve metadata
    - Returning a LasImportResult for downstream MSI registration
    - Classifying extracted curve metadata through approved-only KR runtime

    WL-BUILD-001: parsing skeleton only.
    KR-LAS-1: adds the classification bridge for extracted curve metadata.
    LAS parsing implementation (lasio integration) remains deferred to a later
    sprint; frontend still must not parse LAS.
    """

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
        """Classify extracted LAS curve metadata through approved-only KR.

        This method is the KR-LAS-1 backend boundary.  It can be called by the
        future LAS parser after curve metadata has been extracted.  Input order
        is preserved so downstream MSI/session inventory can correlate each
        classification to its source curve.

        Candidate/rejected/deprecated knowledge cannot influence the result
        because RuntimeCurveClassificationService depends on
        ApprovedKnowledgeRuntimeResolver.
        """
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
            curve_metadata=list(curve_metadata),
            classification_batch=batch,
        )

    def import_from_path(self, file_path: str, source_ref: MsiSourceRef) -> LasImportResult:
        """
        Import a LAS file from a filesystem path.

        Args:
            file_path: Path to the LAS source file on the backend filesystem.
            source_ref: MSI source reference for this file, already registered
                        by the caller before invoking this service.

        Returns:
            LasImportResult containing well, curve metadata, and header info.

        Raises:
            LasImportError: If parsing fails for any reason.

        WL-BUILD-001: not yet implemented — raises NotImplementedError.
        """
        raise NotImplementedError(
            "LAS import not yet implemented. "
            "Wire lasio integration in the next sprint."
        )

    def import_from_bytes(self, file_bytes: bytes, source_ref: MsiSourceRef) -> LasImportResult:
        """
        Import a LAS file from raw bytes (e.g. from an upload stream).

        WL-BUILD-001: not yet implemented — raises NotImplementedError.
        """
        raise NotImplementedError(
            "LAS import from bytes not yet implemented."
        )
