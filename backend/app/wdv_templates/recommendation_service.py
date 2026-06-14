"""Backend-owned WDV template recommendation service.

This service evaluates approved KR-backed WDV preview templates against the
curves/data currently available to the Well Data Viewer.  It returns a
recommendation contract only.  It does not apply a template, populate tracks,
or mutate WDV/MDP/inventory state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from backend.app.knowledge.governance import GovernanceStatus
from backend.app.knowledge.managed_repository import ManagedKRRepository
from backend.app.knowledge.managed_storage import serialize_record

from .models import (
    CONTRACT_VERSION,
    WdvRecommendedCurveResponse,
    WdvTemplateRecommendationEnvelope,
    WdvTemplateRecommendationRequest,
    WdvTemplateRecommendationTrackResponse,
    WdvTemplateRecommendationItemResponse,
    WdvTemplateRequirementCoverageResponse,
)
from .service import WdvTemplateService

_RECOMMENDATION_CONTRACT_VERSION = "wdv_template_recommendation_v1"

_INFRASTRUCTURE_FAMILIES = {
    "depth",
    "measured_depth",
    "tvd",
    "tvdss",
}

_FAMILY_SYNONYMS: dict[str, set[str]] = {
    "gamma_ray": {"gamma", "gamma_ray", "spectral_gamma_ray", "cgr", "sgr"},
    "spontaneous_potential": {"sp", "spontaneous_potential"},
    "caliper": {"caliper", "borehole", "borehole_quality", "multi_arm_caliper"},
    "bit_size": {"bit_size", "bitsize", "bs"},
    "resistivity": {
        "resistivity",
        "deep_resistivity",
        "medium_resistivity",
        "shallow_resistivity",
        "deep_induction_resistivity",
        "medium_induction_resistivity",
        "deep_laterolog_resistivity",
        "shallow_laterolog_resistivity",
        "micro_resistivity_pad",
    },
    "density": {"density", "bulk_density", "rhob", "rhoz"},
    "density_correction": {"density_correction", "drho"},
    "neutron_porosity": {"neutron", "neutron_porosity", "nphi", "tnph", "cnpor"},
    "photoelectric_factor": {"photoelectric_factor", "pef", "pe"},
    "sonic_slowness": {"sonic", "sonic_slowness", "dt", "dtc", "dts", "compressional_sonic", "shear_sonic"},
    "compressional_sonic": {"compressional_sonic", "sonic_slowness", "dtc", "dt"},
    "shear_sonic": {"shear_sonic", "sonic_slowness", "dts"},
    "porosity": {"porosity", "phi", "phie", "phit"},
    "shale_volume": {"shale_volume", "vsh", "vcl"},
    "water_saturation": {"water_saturation", "sw", "swt"},
    "permeability": {"permeability", "perm", "k"},
    "pressure": {"pressure", "press", "p"},
    "temperature": {"temperature", "temp", "bht"},
    "spinner_flow": {"spinner_flow", "flow", "spinner", "rpm", "spin"},
    "collar_locator": {"collar_locator", "ccl"},
    "variable_density_log": {"variable_density_log", "vdl"},
    "borehole_image": {"borehole_image", "image", "fmi", "ubi", "xrmi"},
    "dip_azimuth": {"dip_azimuth", "dip", "azi", "tadpole"},
    "lithology": {"lithology", "facies"},
}


@dataclass(frozen=True)
class LoadedCurveCandidate:
    """Internal normalized representation of a WDV-loaded curve/data object."""

    product_id: str
    curve_id: str
    mnemonic: str
    display_name: str
    unit: str | None
    raw_curve_family: str | None
    curve_family: str | None
    depth_role: str | None = None
    canonical_curve_id: str | None = None
    track_family: str | None = None
    source: dict[str, Any] = field(default_factory=dict)
    rank_hint: int = 9999
    unresolved_reason: str | None = None


@dataclass(frozen=True)
class TemplateRecordSet:
    templates: list[dict[str, Any]]
    tracks_by_template: dict[str, list[dict[str, Any]]]
    requirements_by_template: dict[str, list[dict[str, Any]]]
    selection_rules_by_template: dict[str, dict[str, Any]]
    scale_defaults_by_family: dict[str, list[dict[str, Any]]]


def _raw(record: Any) -> dict[str, Any]:
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


def _text(value: Any) -> str:
    return str(value or "").strip()


def _key(value: Any) -> str:
    text = _text(value).lower().strip()
    return text.replace("-", "_").replace("/", "_").replace(" ", "_")


def _status_value(record_or_data: Any) -> str:
    status = getattr(record_or_data, "status", None)
    if isinstance(status, GovernanceStatus):
        return status.value
    if isinstance(record_or_data, dict):
        status = record_or_data.get("status", status)
    return str(status or "")


def _is_runtime_approved(record: Any, *, require_rule_status: bool = False) -> bool:
    data = _raw(record)
    if _status_value(data) != GovernanceStatus.APPROVED.value:
        return False
    if data.get("runtime_eligible") is False:
        return False
    if data.get("production_eligible") is False:
        return False
    if require_rule_status and data.get("rule_status") != "approved":
        return False
    return True


def _normalize_family(value: Any) -> str | None:
    key = _key(value)
    if not key:
        return None
    for canonical, aliases in _FAMILY_SYNONYMS.items():
        if key == canonical or key in aliases:
            return canonical
    if "resist" in key or key in {"rt", "ild", "ilm", "lld", "lls", "msfl", "rxo"}:
        return "resistivity"
    if "gamma" in key or key in {"gr", "sgr", "cgr"}:
        return "gamma_ray"
    if "density" in key or key in {"rhob", "rhoz"}:
        return "density"
    if "neutron" in key or key in {"nphi", "tnph", "cnpor"}:
        return "neutron_porosity"
    if "sonic" in key or key in {"dt", "dtc", "dts"}:
        return "sonic_slowness"
    if "caliper" in key or key in {"cali", "hcal", "dcal"}:
        return "caliper"
    if key in _INFRASTRUCTURE_FAMILIES:
        return "depth"
    return key


def _families_match(requirement_family: str | None, curve_family: str | None) -> bool:
    req = _normalize_family(requirement_family)
    cur = _normalize_family(curve_family)
    if not req or not cur:
        return False
    if req == cur:
        return True
    req_group = _FAMILY_SYNONYMS.get(req, {req}) | {req}
    cur_group = _FAMILY_SYNONYMS.get(cur, {cur}) | {cur}
    return bool(req_group.intersection(cur_group))


def _depth_role(value: Any) -> str | None:
    key = _key(value)
    if not key:
        return None
    if any(token in key for token in ["msfl", "rxo", "sfl", "shallow", "flushed", "micro"]):
        return "shallow"
    if any(token in key for token in ["ilm", "medium", "at30", "at20", "lls"]):
        return "medium"
    if any(token in key for token in ["ild", "lld", "deep", "true", "rt", "at90"]):
        return "deep"
    return None


class WdvTemplateRecommendationService:
    """Recommend approved WDV templates without applying layout state."""

    def __init__(self, repository: ManagedKRRepository) -> None:
        self._repo = repository
        self._template_service = WdvTemplateService(repository=repository)
        self._classification_maps = self._build_classification_maps()

    def recommend_from_request(
        self,
        request: WdvTemplateRecommendationRequest,
    ) -> WdvTemplateRecommendationEnvelope:
        curves = self._curves_from_payload([item.model_dump() for item in request.loaded_curve_items])
        if request.selected_product_ids:
            selected_ids = {str(v) for v in request.selected_product_ids}
            curves = [c for c in curves if c.product_id in selected_ids or c.curve_id in selected_ids]
        return self._recommend(
            curves,
            workflow_context=request.workflow_context,
            include_ineligible=request.include_ineligible,
            source="explicit_loaded_curve_items",
        )

    def recommend_for_managed_well(
        self,
        managed_well_id: str,
        *,
        workflow_context: str | None = None,
        include_ineligible: bool = True,
    ) -> WdvTemplateRecommendationEnvelope:
        from backend.app.inventory.service import ManagedWellInventoryService

        package = ManagedWellInventoryService().get_viewer_package_contract(managed_well_id)
        curves = self._curves_from_viewer_package(package)
        return self._recommend(
            curves,
            workflow_context=workflow_context,
            include_ineligible=include_ineligible,
            source=f"managed_well_viewer_package:{managed_well_id}",
        )

    def _recommend(
        self,
        curves: list[LoadedCurveCandidate],
        *,
        workflow_context: str | None,
        include_ineligible: bool,
        source: str,
    ) -> WdvTemplateRecommendationEnvelope:
        record_set = self._record_set()
        family_set = {c.curve_family for c in curves if c.curve_family}
        unresolved = [c for c in curves if not c.curve_family]
        recommendations: list[WdvTemplateRecommendationItemResponse] = []

        for template in record_set.templates:
            recommendation = self._recommend_template(
                template=template,
                record_set=record_set,
                curves=curves,
                family_set={str(v) for v in family_set if v},
                workflow_context=workflow_context,
            )
            if recommendation.is_eligible or include_ineligible:
                recommendations.append(recommendation)

        recommendations = sorted(
            recommendations,
            key=lambda item: (
                not item.is_eligible,
                -item.score,
                item.template_priority is None,
                item.template_priority or 9999,
                item.template_label,
            ),
        )
        ranked = []
        for index, item in enumerate(recommendations, start=1):
            ranked.append(item.model_copy(update={"rank": index}))

        return WdvTemplateRecommendationEnvelope(
            contract_version=_RECOMMENDATION_CONTRACT_VERSION,
            service="wdv_template_recommendation_service",
            source=source,
            available_curve_count=len(curves),
            classified_curve_count=len([c for c in curves if c.curve_family]),
            unresolved_curve_count=len(unresolved),
            unresolved_curves=[self._curve_response(c, "unresolved") for c in unresolved],
            recommendation_count=len(ranked),
            recommendations=ranked,
            knowledge_policy={
                "approved_only": True,
                "candidate_records_used": False,
                "deprecated_records_used": False,
                "frontend_inference_allowed": False,
                "runtime_record_types": [
                    "preview_template",
                    "preview_template_track",
                    "template_curve_family_requirement",
                    "template_scale_default",
                    "track_object_type",
                    "template_selection_rule",
                    "curve_definition",
                    "alias",
                    "alias_enrichment",
                    "classification_rule",
                ],
            },
        )

    def _recommend_template(
        self,
        *,
        template: dict[str, Any],
        record_set: TemplateRecordSet,
        curves: list[LoadedCurveCandidate],
        family_set: set[str],
        workflow_context: str | None,
    ) -> WdvTemplateRecommendationItemResponse:
        template_key = str(template.get("template_key") or "")
        tracks = record_set.tracks_by_template.get(template_key, [])
        requirements = record_set.requirements_by_template.get(template_key, [])
        selection_rule = record_set.selection_rules_by_template.get(template_key, {})
        required = [str(v) for v in _list(selection_rule.get("required_families") or template.get("required_curve_families"))]
        preferred = [str(v) for v in _list(selection_rule.get("preferred_families") or template.get("preferred_curve_families"))]
        optional = [str(v) for v in _list(selection_rule.get("optional_families") or template.get("optional_curve_families"))]

        required_coverage = self._coverage(required, family_set)
        preferred_coverage = self._coverage(preferred, family_set)
        optional_coverage = self._coverage(optional, family_set)

        missing_required = required_coverage.missing_families
        is_eligible = not missing_required and template.get("preview_eligible") is True
        if workflow_context:
            expected_context = _key(selection_rule.get("workflow_context") or template.get("workflow_context"))
            requested_context = _key(workflow_context)
            if expected_context and requested_context and expected_context != requested_context:
                # Context mismatch does not make a template impossible, but lowers its rank.
                context_penalty = 12.0
            else:
                context_penalty = 0.0
        else:
            context_penalty = 0.0

        track_recommendations = []
        selected_curve_ids: set[str] = set()
        alternate_curve_ids: set[str] = set()
        missing_by_track: set[str] = set()
        requirements_by_track: dict[str, list[dict[str, Any]]] = {}
        for req in requirements:
            requirements_by_track.setdefault(str(req.get("track_id") or req.get("track_key") or ""), []).append(req)

        for track in tracks:
            track_id = str(track.get("track_id") or "")
            track_reco = self._recommend_track(
                track=track,
                requirements=requirements_by_track.get(track_id, []),
                curves=curves,
                scale_defaults_by_family=record_set.scale_defaults_by_family,
            )
            selected_curve_ids.update(c.curve_id for c in track_reco.selected_curves)
            alternate_curve_ids.update(c.curve_id for c in track_reco.alternate_curves)
            missing_by_track.update(track_reco.missing_curve_families)
            track_recommendations.append(track_reco)

        selected_curves = [self._curve_response(c, "selected") for c in curves if c.curve_id in selected_curve_ids]
        alternate_curves = [
            self._curve_response(c, "alternate")
            for c in curves
            if c.curve_id in alternate_curve_ids and c.curve_id not in selected_curve_ids
        ]
        excluded_curves = [
            self._curve_response(c, "loaded_not_selected")
            for c in curves
            if c.curve_id not in selected_curve_ids and c.curve_id not in alternate_curve_ids
        ]

        required_total = len(required_coverage.available_families) + len(required_coverage.missing_families)
        preferred_total = len(preferred_coverage.available_families) + len(preferred_coverage.missing_families)
        optional_total = len(optional_coverage.available_families) + len(optional_coverage.missing_families)
        required_score = 60.0 if required_total == 0 else 60.0 * len(required_coverage.available_families) / required_total
        preferred_score = 25.0 if preferred_total == 0 else 25.0 * len(preferred_coverage.available_families) / preferred_total
        optional_score = 10.0 if optional_total == 0 else 10.0 * len(optional_coverage.available_families) / optional_total
        rank_weight = float(selection_rule.get("ranking_weight") or 0.0)
        priority_bonus = max(0.0, 5.0 - float(template.get("template_priority") or 5.0))
        score = max(0.0, round(required_score + preferred_score + optional_score + rank_weight + priority_bonus - context_penalty, 3))

        reason_codes: list[str] = []
        if is_eligible:
            reason_codes.append("required_families_covered")
        else:
            reason_codes.append("missing_required_families")
        if selected_curves:
            reason_codes.append("representative_curves_selected")
        if missing_by_track:
            reason_codes.append("track_requirements_missing")
        if context_penalty:
            reason_codes.append("workflow_context_mismatch_penalty")

        return WdvTemplateRecommendationItemResponse(
            template_key=template_key,
            template_label=str(template.get("template_label") or template_key),
            workflow_context=template.get("workflow_context"),
            template_priority=template.get("template_priority"),
            is_eligible=is_eligible,
            rank=0,
            score=score,
            required_coverage=required_coverage,
            preferred_coverage=preferred_coverage,
            optional_coverage=optional_coverage,
            missing_required_families=missing_required,
            missing_preferred_families=preferred_coverage.missing_families,
            selected_curve_count=len(selected_curves),
            alternate_curve_count=len(alternate_curves),
            excluded_curve_count=len(excluded_curves),
            selected_curves=selected_curves,
            alternate_curves=alternate_curves,
            excluded_curves=excluded_curves,
            tracks=track_recommendations,
            renderer_requirements=[str(v) for v in _list(selection_rule.get("renderer_requirements"))],
            reason_codes=reason_codes,
        )

    def _recommend_track(
        self,
        *,
        track: dict[str, Any],
        requirements: list[dict[str, Any]],
        curves: list[LoadedCurveCandidate],
        scale_defaults_by_family: dict[str, list[dict[str, Any]]],
    ) -> WdvTemplateRecommendationTrackResponse:
        selected: list[LoadedCurveCandidate] = []
        alternates: list[LoadedCurveCandidate] = []
        missing: list[str] = []
        seen_selected: set[str] = set()
        seen_alternate: set[str] = set()
        scale_defaults = []

        for req in sorted(requirements, key=lambda r: (r.get("selection_priority") or 9999, r.get("curve_family") or "")):
            family = str(req.get("curve_family") or "")
            if not family:
                continue
            if _normalize_family(family) in _INFRASTRUCTURE_FAMILIES:
                continue
            matches = [c for c in curves if _families_match(family, c.curve_family)]
            if not matches:
                if req.get("requirement_level") in {"required", "preferred"}:
                    missing.append(family)
                continue
            max_count = int(req.get("max_auto_plotted_count") or 1)
            chosen = self._choose_representatives(family, matches, max_count=max_count)
            for curve in chosen:
                if curve.curve_id not in seen_selected:
                    selected.append(curve)
                    seen_selected.add(curve.curve_id)
            for curve in matches:
                if curve.curve_id not in seen_selected and curve.curve_id not in seen_alternate:
                    alternates.append(curve)
                    seen_alternate.add(curve.curve_id)
            for scale in scale_defaults_by_family.get(_normalize_family(family) or family, []):
                if scale not in scale_defaults:
                    scale_defaults.append(scale)

        return WdvTemplateRecommendationTrackResponse(
            track_id=str(track.get("track_id") or ""),
            track_key=str(track.get("track_key") or track.get("track_id") or ""),
            track_number=int(track.get("track_number") or 0),
            track_name=str(track.get("track_name") or track.get("track_key") or track.get("track_id") or ""),
            track_role=track.get("track_role"),
            renderer_type=str(track.get("renderer_type") or "line_curve"),
            required_renderer_capability=track.get("required_renderer_capability"),
            selected_curves=[self._curve_response(c, "selected_for_track") for c in selected],
            alternate_curves=[self._curve_response(c, "alternate_for_track") for c in alternates],
            missing_curve_families=sorted(set(missing)),
            scale_defaults=[
                {
                    "curve_family": s.get("curve_family"),
                    "unit_family": s.get("unit_family"),
                    "scale_type": s.get("scale_type"),
                    "scale_min": s.get("scale_min"),
                    "scale_max": s.get("scale_max"),
                    "display_direction": s.get("display_direction"),
                }
                for s in scale_defaults
            ],
        )

    def _choose_representatives(
        self,
        family: str,
        matches: list[LoadedCurveCandidate],
        *,
        max_count: int,
    ) -> list[LoadedCurveCandidate]:
        ordered = sorted(matches, key=lambda c: (c.rank_hint, c.mnemonic, c.product_id))
        if max_count <= 1 or _normalize_family(family) != "resistivity":
            return ordered[:max_count]
        chosen: list[LoadedCurveCandidate] = []
        for role in ["deep", "medium", "shallow"]:
            role_matches = [c for c in ordered if c.depth_role == role]
            if role_matches:
                chosen.append(role_matches[0])
        for curve in ordered:
            if len(chosen) >= max_count:
                break
            if curve not in chosen:
                chosen.append(curve)
        return chosen[:max_count]

    def _coverage(self, families: list[str], family_set: set[str]) -> WdvTemplateRequirementCoverageResponse:
        normalized = []
        for family in families:
            norm = _normalize_family(family)
            if norm and norm not in normalized:
                normalized.append(norm)
        available = []
        missing = []
        for family in normalized:
            if family in _INFRASTRUCTURE_FAMILIES or any(_families_match(family, present) for present in family_set):
                available.append(family)
            else:
                missing.append(family)
        total = len(available) + len(missing)
        ratio = 1.0 if total == 0 else round(len(available) / total, 4)
        return WdvTemplateRequirementCoverageResponse(
            available_families=available,
            missing_families=missing,
            coverage_ratio=ratio,
        )

    def _curves_from_payload(self, items: Iterable[dict[str, Any]]) -> list[LoadedCurveCandidate]:
        out = []
        for index, item in enumerate(items):
            if item.get("is_renderable") is False:
                continue
            if item.get("support_status") == "unsupported_curve":
                continue
            product_id = _text(item.get("product_id") or item.get("productId") or f"loaded_curve_{index}")
            curve_id = _text(
                item.get("display_curve_id")
                or item.get("displayCurveId")
                or item.get("curve_id")
                or item.get("curveId")
                or product_id
            )
            mnemonic = _text(item.get("original_mnemonic") or item.get("originalMnemonic") or item.get("mnemonic") or curve_id)
            display_name = _text(item.get("normalized_name") or item.get("display_name") or item.get("displayName") or mnemonic)
            canonical_curve_id = _text(item.get("canonical_curve_id") or item.get("canonicalCurveId")) or None
            raw_family = _text(item.get("curve_family") or item.get("curveFamily") or item.get("track_family") or item.get("trackFamily")) or None
            family = self._classify_family(
                mnemonic=mnemonic,
                canonical_curve_id=canonical_curve_id,
                raw_family=raw_family,
                display_name=display_name,
                unit=item.get("unit"),
            )
            role = _depth_role(" ".join([mnemonic, display_name, canonical_curve_id or "", raw_family or ""]))
            out.append(
                LoadedCurveCandidate(
                    product_id=product_id,
                    curve_id=curve_id,
                    mnemonic=mnemonic,
                    display_name=display_name,
                    unit=item.get("unit"),
                    raw_curve_family=raw_family,
                    curve_family=family,
                    depth_role=role,
                    canonical_curve_id=canonical_curve_id,
                    track_family=_text(item.get("track_family") or item.get("trackFamily")) or None,
                    source=dict(item),
                    rank_hint=self._rank_hint(mnemonic, canonical_curve_id, family, role),
                    unresolved_reason=None if family else "No approved KR family match found.",
                )
            )
        return out

    def _curves_from_viewer_package(self, package: dict[str, Any]) -> list[LoadedCurveCandidate]:
        items = package.get("loaded_curve_items") or []
        if not items:
            for track in package.get("tracks") or []:
                items.extend(track.get("curves") or [])
        return self._curves_from_payload(items)

    def _classify_family(
        self,
        *,
        mnemonic: str,
        canonical_curve_id: str | None,
        raw_family: str | None,
        display_name: str,
        unit: Any,
    ) -> str | None:
        for value in [raw_family, canonical_curve_id, mnemonic, display_name]:
            family = _normalize_family(value)
            if family and family not in {"unknown", "none"}:
                if value in [raw_family] or family in _FAMILY_SYNONYMS or family in _INFRASTRUCTURE_FAMILIES:
                    return family
        mnemonic_key = _key(mnemonic).upper()
        if mnemonic_key in self._classification_maps["alias_to_family"]:
            return self._classification_maps["alias_to_family"][mnemonic_key]
        if canonical_curve_id and canonical_curve_id in self._classification_maps["canonical_to_family"]:
            return self._classification_maps["canonical_to_family"][canonical_curve_id]
        for value in [mnemonic, display_name, unit]:
            family = _normalize_family(value)
            if family and family in _FAMILY_SYNONYMS:
                return family
        return None

    def _rank_hint(
        self,
        mnemonic: str,
        canonical_curve_id: str | None,
        family: str | None,
        depth_role: str | None,
    ) -> int:
        key = _key(" ".join([mnemonic, canonical_curve_id or ""]))
        preferred_order = [
            ("gr", 1), ("cgr", 2), ("sgr", 3),
            ("rt", 1), ("ild", 2), ("lld", 3), ("ilm", 4), ("lls", 5), ("msfl", 6), ("rxo", 7),
            ("rhob", 1), ("rhoz", 2),
            ("nphi", 1), ("tnph", 2),
            ("dtc", 1), ("dt", 2), ("dts", 3),
            ("pef", 1), ("drho", 1),
        ]
        for token, rank in preferred_order:
            if token in key:
                return rank
        if family == "resistivity" and depth_role == "deep":
            return 5
        if family == "resistivity" and depth_role == "medium":
            return 6
        if family == "resistivity" and depth_role == "shallow":
            return 7
        return 9999

    def _build_classification_maps(self) -> dict[str, dict[str, str]]:
        canonical_to_family: dict[str, str] = {}
        alias_to_family: dict[str, str] = {}

        for record in self._repo.list_records(record_type="curve_definition"):
            if not _is_runtime_approved(record):
                continue
            data = _raw(record)
            canonical = _text(data.get("canonical_curve_id"))
            family = _normalize_family(data.get("family") or data.get("product_group") or canonical)
            if canonical and family:
                canonical_to_family[canonical] = family

        for record_type in ["alias", "alias_enrichment", "classification_rule"]:
            for record in self._repo.list_records(record_type=record_type):
                if not _is_runtime_approved(record):
                    continue
                data = _raw(record)
                aliases = [
                    data.get("alias"),
                    data.get("normalized_alias"),
                    data.get("match_value"),
                ]
                family = _normalize_family(
                    data.get("curve_family")
                    or data.get("measurement_family")
                    or data.get("technical_family")
                    or data.get("display_canonical_curve_id")
                    or data.get("canonical_curve_id")
                )
                canonical = _text(data.get("canonical_curve_id") or data.get("display_canonical_curve_id"))
                if not family and canonical:
                    family = canonical_to_family.get(canonical)
                if not family:
                    continue
                for alias in aliases:
                    alias_text = _text(alias)
                    if alias_text:
                        alias_to_family[alias_text.upper()] = family

        return {
            "canonical_to_family": canonical_to_family,
            "alias_to_family": alias_to_family,
        }

    def _record_set(self) -> TemplateRecordSet:
        def approved_template_record_type(record_type: str) -> list[dict[str, Any]]:
            out = []
            for record in self._repo.list_records(record_type=record_type):
                data = _raw(record)
                if (
                    data.get("status") == GovernanceStatus.APPROVED.value
                    and data.get("rule_status") == "approved"
                    and data.get("runtime_eligible") is True
                    and data.get("production_eligible") is True
                ):
                    out.append(data)
            return out

        templates = sorted(
            approved_template_record_type("preview_template"),
            key=lambda r: (r.get("template_priority") or 9999, r.get("template_label") or r.get("template_key") or ""),
        )
        tracks = approved_template_record_type("preview_template_track")
        requirements = approved_template_record_type("template_curve_family_requirement")
        selection_rules = approved_template_record_type("template_selection_rule")
        scale_defaults = approved_template_record_type("template_scale_default")

        tracks_by_template: dict[str, list[dict[str, Any]]] = {}
        for track in tracks:
            tracks_by_template.setdefault(str(track.get("template_key") or ""), []).append(track)
        for key in tracks_by_template:
            tracks_by_template[key] = sorted(tracks_by_template[key], key=lambda r: (r.get("track_number") or 9999, r.get("track_id") or ""))

        requirements_by_template: dict[str, list[dict[str, Any]]] = {}
        for req in requirements:
            requirements_by_template.setdefault(str(req.get("template_key") or ""), []).append(req)

        selection_rules_by_template = {
            str(rule.get("template_key") or ""): rule
            for rule in selection_rules
            if rule.get("template_key")
        }

        scale_defaults_by_family: dict[str, list[dict[str, Any]]] = {}
        for scale in scale_defaults:
            family = _normalize_family(scale.get("curve_family"))
            if family:
                scale_defaults_by_family.setdefault(family, []).append(scale)

        return TemplateRecordSet(
            templates=templates,
            tracks_by_template=tracks_by_template,
            requirements_by_template=requirements_by_template,
            selection_rules_by_template=selection_rules_by_template,
            scale_defaults_by_family=scale_defaults_by_family,
        )

    def _curve_response(self, curve: LoadedCurveCandidate, reason: str) -> WdvRecommendedCurveResponse:
        return WdvRecommendedCurveResponse(
            product_id=curve.product_id,
            curve_id=curve.curve_id,
            mnemonic=curve.mnemonic,
            display_name=curve.display_name,
            unit=curve.unit,
            curve_family=curve.curve_family,
            raw_curve_family=curve.raw_curve_family,
            canonical_curve_id=curve.canonical_curve_id,
            depth_role=curve.depth_role,
            selection_reason=reason if curve.curve_family else curve.unresolved_reason or reason,
        )
