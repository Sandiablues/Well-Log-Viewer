"""Backend-owned WDV template service backed by approved KR records.

This service exposes approved KR preview-template knowledge.  It does not
classify curves, choose curves for a loaded well, populate WDV tracks, or apply
layout state.  Those are later backend-owned services.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Iterable

from app.knowledge.managed_storage import serialize_record

from app.knowledge.governance import GovernanceStatus
from app.knowledge.managed_repository import ManagedKRRepository

from .models import (
    WdvCurveFamilyRequirementResponse,
    WdvKnowledgePolicy,
    WdvPreviewTemplateDetailResponse,
    WdvPreviewTemplateSummaryResponse,
    WdvPreviewTemplateTrackResponse,
    WdvScaleDefaultResponse,
    WdvTemplateDetailEnvelope,
    WdvTemplateListResponse,
    WdvTemplateReferenceSummaryResponse,
    WdvTemplateSelectionRuleResponse,
    WdvTrackObjectTypeResponse,
)

_RUNTIME_RECORD_TYPES = [
    "reference_source",
    "preview_template",
    "preview_template_track",
    "template_curve_family_requirement",
    "template_scale_default",
    "track_object_type",
    "template_selection_rule",
]


class WdvTemplateNotFoundError(KeyError):
    """Raised when an approved runtime template is not available."""


def _raw(record: Any) -> dict[str, Any]:
    """Return a flat JSON-like dictionary for typed or generic KR records."""
    data = getattr(record, "data", None)
    if isinstance(data, dict):
        out = dict(data)
    else:
        out = serialize_record(record)
    status = out.get("status")
    if isinstance(status, GovernanceStatus):
        out["status"] = status.value
    return out


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _is_approved_runtime(record: Any) -> bool:
    data = _raw(record)
    status = getattr(record, "status", None)
    if isinstance(status, GovernanceStatus):
        status_ok = status == GovernanceStatus.APPROVED
    else:
        status_ok = str(data.get("status") or status) == GovernanceStatus.APPROVED.value
    return (
        status_ok
        and data.get("rule_status") == "approved"
        and data.get("runtime_eligible") is True
        and data.get("production_eligible") is True
    )


def _policy() -> WdvKnowledgePolicy:
    return WdvKnowledgePolicy(
        approved_only=True,
        candidate_records_used=False,
        deprecated_records_used=False,
        frontend_inference_allowed=False,
        runtime_record_types=list(_RUNTIME_RECORD_TYPES),
    )


class WdvTemplateService:
    """Read approved WDV preview-template contracts from Managed KR."""

    def __init__(self, repository: ManagedKRRepository) -> None:
        self._repo = repository

    def _approved(self, record_type: str) -> list[Any]:
        return [r for r in self._repo.list_records(record_type=record_type) if _is_approved_runtime(r)]

    def _template_records(self) -> list[Any]:
        return sorted(
            self._approved("preview_template"),
            key=lambda r: (
                _raw(r).get("template_priority") is None,
                _raw(r).get("template_priority") or 9999,
                _raw(r).get("template_label") or _raw(r).get("template_key") or "",
            ),
        )

    def list_templates(self) -> WdvTemplateListResponse:
        templates = [self._summary(r) for r in self._template_records()]
        return WdvTemplateListResponse(
            template_count=len(templates),
            templates=templates,
            knowledge_policy=_policy(),
        )

    def get_template(self, template_key: str) -> WdvTemplateDetailEnvelope:
        template = None
        for record in self._template_records():
            if _raw(record).get("template_key") == template_key:
                template = record
                break
        if template is None:
            raise WdvTemplateNotFoundError(template_key)
        return WdvTemplateDetailEnvelope(
            template=self._detail(template),
            knowledge_policy=_policy(),
        )

    def reference_summary(self) -> WdvTemplateReferenceSummaryResponse:
        counts: Counter[str] = Counter()
        for record_type in _RUNTIME_RECORD_TYPES:
            counts[record_type] = len(self._approved(record_type))
        refs = []
        for record in self._approved("reference_source"):
            data = _raw(record)
            refs.append({
                "source_key": data.get("source_key"),
                "source_title": data.get("source_title"),
                "source_file": data.get("source_file"),
                "source_storage_path": data.get("source_storage_path"),
                "file_sha256": data.get("file_sha256"),
                "authority_level": data.get("authority_level"),
                "status": data.get("status"),
                "runtime_eligible": data.get("runtime_eligible"),
            })
        return WdvTemplateReferenceSummaryResponse(
            record_type_counts=dict(counts),
            reference_sources=refs,
            knowledge_policy=_policy(),
        )

    def _summary(self, record: Any) -> WdvPreviewTemplateSummaryResponse:
        data = _raw(record)
        return WdvPreviewTemplateSummaryResponse(
            template_key=str(data.get("template_key") or ""),
            template_label=str(data.get("template_label") or data.get("template_key") or ""),
            workflow_context=data.get("workflow_context"),
            primary_usage=data.get("primary_usage"),
            core_display_content=data.get("core_display_content"),
            required_curve_families=[str(v) for v in _list(data.get("required_curve_families"))],
            preferred_curve_families=[str(v) for v in _list(data.get("preferred_curve_families"))],
            optional_curve_families=[str(v) for v in _list(data.get("optional_curve_families"))],
            requires_renderer_capabilities=[str(v) for v in _list(data.get("requires_renderer_capabilities"))],
            track_count=int(data.get("track_count") or 0),
            preview_eligible=data.get("preview_eligible") is True,
            auto_build_eligible=data.get("auto_build_eligible") is True,
            production_eligible=data.get("production_eligible") is True,
            runtime_eligible=data.get("runtime_eligible") is True,
            status=str(data.get("status") or ""),
            rule_status=data.get("rule_status"),
            source_pages=[str(v) for v in _list(data.get("source_pages"))],
            evidence_refs=[str(v) for v in _list(data.get("evidence_refs"))],
        )

    def _detail(self, record: Any) -> WdvPreviewTemplateDetailResponse:
        summary = self._summary(record)
        template_key = summary.template_key
        requirements_by_track: dict[str, list[WdvCurveFamilyRequirementResponse]] = defaultdict(list)
        for req in self._requirements_for_template(template_key):
            data = _raw(req)
            requirements_by_track[str(data.get("track_id") or data.get("track_key") or "")].append(
                WdvCurveFamilyRequirementResponse(
                    curve_family=str(data.get("curve_family") or ""),
                    curve_role=data.get("curve_role"),
                    requirement_level=str(data.get("requirement_level") or "optional"),
                    preferred_mnemonics=[str(v) for v in _list(data.get("preferred_mnemonics"))],
                    max_auto_plotted_count=data.get("max_auto_plotted_count"),
                    selection_priority=data.get("selection_priority"),
                    selection_policy=data.get("selection_policy"),
                    requires_unit_family=data.get("requires_unit_family"),
                    requires_depth_role=data.get("requires_depth_role"),
                )
            )
        tracks = []
        for track in self._tracks_for_template(template_key):
            data = _raw(track)
            track_id = str(data.get("track_id") or "")
            tracks.append(
                WdvPreviewTemplateTrackResponse(
                    track_id=track_id,
                    track_key=str(data.get("track_key") or track_id),
                    track_number=int(data.get("track_number") or 0),
                    track_name=str(data.get("track_name") or data.get("track_key") or track_id),
                    track_role=data.get("track_role"),
                    renderer_type=str(data.get("renderer_type") or "line_curve"),
                    scale_behavior=data.get("scale_behavior"),
                    display_notes=data.get("display_notes"),
                    required_renderer_capability=data.get("required_renderer_capability"),
                    supports_overlay=data.get("supports_overlay") is True,
                    is_optional_track=data.get("is_optional_track") is True,
                    curve_families=[str(v) for v in _list(data.get("curve_families"))],
                    requirements=sorted(
                        requirements_by_track.get(track_id, []),
                        key=lambda item: (item.selection_priority is None, item.selection_priority or 9999, item.curve_family),
                    ),
                )
            )
        return WdvPreviewTemplateDetailResponse(
            **summary.model_dump(),
            tracks=tracks,
            selection_rule=self._selection_rule_for_template(template_key),
            scale_defaults=self._scale_defaults_for_template(tracks),
            track_object_types=self._track_object_types_for_template(tracks),
        )

    def _tracks_for_template(self, template_key: str) -> list[Any]:
        return sorted(
            [r for r in self._approved("preview_template_track") if _raw(r).get("template_key") == template_key],
            key=lambda r: (_raw(r).get("track_number") or 9999, _raw(r).get("track_id") or ""),
        )

    def _requirements_for_template(self, template_key: str) -> list[Any]:
        return sorted(
            [r for r in self._approved("template_curve_family_requirement") if _raw(r).get("template_key") == template_key],
            key=lambda r: (
                _raw(r).get("track_id") or "",
                _raw(r).get("selection_priority") or 9999,
                _raw(r).get("curve_family") or "",
            ),
        )

    def _selection_rule_for_template(self, template_key: str) -> WdvTemplateSelectionRuleResponse | None:
        for record in self._approved("template_selection_rule"):
            data = _raw(record)
            if data.get("template_key") != template_key:
                continue
            return WdvTemplateSelectionRuleResponse(
                rule_id=str(data.get("rule_id") or f"selection_rule_{template_key}"),
                workflow_context=data.get("workflow_context"),
                required_families=[str(v) for v in _list(data.get("required_families"))],
                preferred_families=[str(v) for v in _list(data.get("preferred_families"))],
                optional_families=[str(v) for v in _list(data.get("optional_families"))],
                renderer_requirements=[str(v) for v in _list(data.get("renderer_requirements"))],
                ranking_weight=data.get("ranking_weight"),
                minimum_coverage_threshold=data.get("minimum_coverage_threshold"),
                degraded_mode_allowed=data.get("degraded_mode_allowed") is True,
                missing_required_behavior=data.get("missing_required_behavior"),
                selection_notes=data.get("selection_notes"),
            )
        return None

    def _scale_defaults_for_template(
        self,
        tracks: Iterable[WdvPreviewTemplateTrackResponse],
    ) -> list[WdvScaleDefaultResponse]:
        families: set[str] = set()
        for track in tracks:
            families.update(track.curve_families)
            for req in track.requirements:
                families.add(req.curve_family)
        out = []
        for record in self._approved("template_scale_default"):
            data = _raw(record)
            if data.get("curve_family") not in families:
                continue
            out.append(
                WdvScaleDefaultResponse(
                    curve_family=str(data.get("curve_family") or ""),
                    unit_family=data.get("unit_family"),
                    scale_type=data.get("scale_type"),
                    scale_min=data.get("scale_min"),
                    scale_max=data.get("scale_max"),
                    display_direction=data.get("display_direction"),
                    override_allowed=data.get("override_allowed") is not False,
                    scale_confidence=data.get("scale_confidence"),
                    review_required=data.get("review_required") is True,
                    notes=data.get("notes"),
                )
            )
        return sorted(out, key=lambda item: (item.curve_family, item.unit_family or ""))

    def _track_object_types_for_template(
        self,
        tracks: Iterable[WdvPreviewTemplateTrackResponse],
    ) -> list[WdvTrackObjectTypeResponse]:
        renderer_types = {track.renderer_type for track in tracks}
        out = []
        for record in self._approved("track_object_type"):
            data = _raw(record)
            if data.get("object_type") not in renderer_types:
                continue
            out.append(
                WdvTrackObjectTypeResponse(
                    object_type=str(data.get("object_type") or ""),
                    default_renderer=data.get("default_renderer"),
                    compatible_data_types=[str(v) for v in _list(data.get("compatible_data_types"))],
                    preview_supported=data.get("preview_supported") is True,
                    auto_build_supported=data.get("auto_build_supported") is True,
                    requires_capability=data.get("requires_capability"),
                    fallback_behavior=data.get("fallback_behavior"),
                    review_required=data.get("review_required") is True,
                    notes=data.get("notes"),
                )
            )
        return sorted(out, key=lambda item: item.object_type)
