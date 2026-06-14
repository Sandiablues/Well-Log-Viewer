"""KR-backed WDV layout preset recommendation service.

This service consumes approved/production-eligible Managed KR template_rule
records plus Managed Well Inventory records and returns a side-effect-free WDV
layout recommendation contract.

It does not modify MDP state, WDV state, viewer packages, source-intake records,
or knowledge records. Frontend integration must render this JSON only; applying
a preset belongs to a later backend-owned WDV session-state block.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from .models import (
    WdvDisplayScaleRecommendation,
    WdvLayoutPresetDefinition,
    WdvLayoutPresetListResponse,
    WdvLayoutPresetRecommendationResponse,
    WdvLayoutPresetTrackDefinition,
    WdvPresetCurveCandidate,
    WdvPresetTrackRecommendation,
)

_OTHER_REVIEW_GROUPS = {"other_review_required", "other", "review_required"}
_LOW_CONFIDENCE = {"low", "unknown", "unclassified", "review_required"}
_PRODUCTION_ELIGIBLE_STATUSES = {"seed", "approved"}
_TEMPLATE_ALIASES = {
    # Request compatibility only. The returned preset_id remains the KR template_key.
    "triple_combo": "basic_triple_combo_openhole",
    "basic_triple_combo": "basic_triple_combo_openhole",
    "full_suite": "full_suite_openhole",
    "cased_hole_integrity": "cased_hole_cement_evaluation",
    "cement_evaluation": "cased_hole_cement_evaluation",
}
_GENERIC_TRACK_PURPOSE = "KR-approved WDV template track generated from template_rule.track_order."


@dataclass(frozen=True)
class _TrackSpec:
    track_id: str
    label: str
    purpose: str = _GENERIC_TRACK_PURPOSE
    required_families: tuple[str, ...] = field(default_factory=tuple)
    optional_families: tuple[str, ...] = field(default_factory=tuple)
    overlay_rules: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    max_curves: Optional[int] = None


@dataclass(frozen=True)
class _TemplateSpec:
    preset_id: str
    name: str
    description: str
    kr_record_id: str
    kr_record_status: str
    production_eligible: bool
    tracks: tuple[_TrackSpec, ...]
    required_families: tuple[str, ...] = field(default_factory=tuple)
    preferred_families: tuple[str, ...] = field(default_factory=tuple)
    fallback_families: tuple[str, ...] = field(default_factory=tuple)
    missing_curve_behavior: Optional[str] = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def optional_families(self) -> tuple[str, ...]:
        values = [*self.preferred_families, *self.fallback_families]
        return tuple(dict.fromkeys(values))


def _normalize_key(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[^A-Za-z0-9]+", "_", text)
    return text.strip("_").lower()


def _upper_mnemonic(value: Any) -> str:
    return str(value or "").strip().upper()


def _title_from_key(value: Any) -> str:
    return _normalize_key(value).replace("_", " ").title()


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        if isinstance(dumped, dict):
            return dumped
    if hasattr(value, "dict"):
        dumped = value.dict()
        if isinstance(dumped, dict):
            return dumped
    raw = getattr(value, "__dict__", None)
    if isinstance(raw, dict):
        return dict(raw)
    return {}


def _status_value(value: Any) -> str:
    raw = getattr(value, "value", value)
    return _normalize_key(raw)


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(v) for v in value if str(v or "").strip()]
    return [str(value)] if str(value or "").strip() else []


def _extract_canonical_curve_id(item: dict[str, Any]) -> Optional[str]:
    direct = item.get("canonical_curve_id") or item.get("curve_id")
    if direct and direct != item.get("product_id"):
        return str(direct)
    for reason in item.get("classification_reasons") or []:
        match = re.search(r"Canonical curve:\s*([A-Za-z0-9_\-]+)\.??", str(reason))
        if match:
            return match.group(1)
    return None


def _confidence_rank(value: Any) -> int:
    confidence = _normalize_key(value)
    if confidence == "high":
        return 30
    if confidence == "medium":
        return 20
    if confidence == "low":
        return 5
    return 10


def _source_rank(value: Any) -> int:
    source = _normalize_key(value)
    if source in {"runtime_alias", "runtime_canonical", "runtime_curve_definition"}:
        return 30
    if source in {"seed", "approved"}:
        return 25
    if source == "backend_well_log_classifier":
        return 10
    return 0


def _candidate_sort_key(item: dict[str, Any]) -> tuple[int, int, str]:
    return (
        -_confidence_rank(item.get("classification_confidence")),
        -_source_rank(item.get("classification_source")),
        _upper_mnemonic(item.get("curve_name") or item.get("mnemonic")),
    )


def _tokens(value: str) -> set[str]:
    return {part for part in _normalize_key(value).split("_") if part}


def _track_family_score(track_id: str, family: str) -> int:
    track = _normalize_key(track_id)
    fam = _normalize_key(family)
    if not track or not fam:
        return 0
    if track == fam:
        return 100
    if track in fam or fam in track:
        return 75
    overlap = _tokens(track) & _tokens(fam)
    return len(overlap) * 10


def _best_track_for_family(track_ids: list[str], family: str) -> Optional[str]:
    scored = [(_track_family_score(track_id, family), track_id) for track_id in track_ids]
    scored = [item for item in scored if item[0] > 0]
    if not scored:
        return None
    scored.sort(key=lambda item: (-item[0], item[1]))
    return scored[0][1]


class WdvLayoutPresetService:
    """Build WDV layout preset recommendations from approved KR template rules."""

    def __init__(
        self,
        inventory_service: Any | None = None,
        knowledge_repository: Any | None = None,
        display_recommendation_service: Any | None = None,
        use_default_knowledge_repository: bool = True,
        use_default_display_service: bool = True,
    ) -> None:
        self._inventory_service = inventory_service
        self._knowledge_repository = knowledge_repository
        self._display_recommendation_service = display_recommendation_service
        self._use_default_knowledge_repository = use_default_knowledge_repository
        self._use_default_display_service = use_default_display_service

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_presets(self) -> WdvLayoutPresetListResponse:
        specs = self._load_template_specs()
        warnings: list[str] = []
        if not specs:
            warnings.append(
                "No approved production-eligible KR template_rule records are available for WDV presets."
            )
        return WdvLayoutPresetListResponse(
            preset_count=len(specs),
            presets=[self._preset_to_model(spec) for spec in specs],
            warnings=warnings,
            knowledge_policy=self._knowledge_policy(),
        )

    def recommend_preset(
        self,
        managed_well_id: str,
        preset_id: str = "basic_triple_combo_openhole",
    ) -> WdvLayoutPresetRecommendationResponse:
        spec = self._get_preset(preset_id)
        well = self._get_managed_well(managed_well_id)
        well_dict = _as_dict(well)

        eligible, excluded_other = self._eligible_product_items(well_dict)
        family_index = self._build_family_index(eligible)

        tracks: list[WdvPresetTrackRecommendation] = []
        selected_product_ids: set[str] = set()
        missing_required_families: list[str] = []

        for track_spec in spec.tracks:
            track = self._recommend_track(track_spec, family_index, selected_product_ids)
            tracks.append(track)
            missing_required_families.extend(track.missing_required_families)
            for curve in track.curves:
                selected_product_ids.add(curve.product_id)

        missing_required_families = list(dict.fromkeys(missing_required_families))
        required_family_count = len(spec.required_families)
        missing_family_count = len(missing_required_families)
        if required_family_count <= 0:
            completeness_score = 1.0 if any(track.curves for track in tracks) else 0.0
        else:
            completeness_score = max(
                0.0,
                min(1.0, (required_family_count - missing_family_count) / required_family_count),
            )

        selected_curve_count = sum(len(track.curves) for track in tracks)
        if missing_required_families:
            recommendation_status = "partial" if selected_curve_count else "not_recommended"
        else:
            recommendation_status = "ready" if selected_curve_count else "not_recommended"

        warnings: list[str] = []
        if excluded_other:
            warnings.append(
                f"Excluded {excluded_other} Other / Review Required curve(s) from preset automation."
            )
        if missing_required_families:
            warnings.append("Missing required curve families for a complete preset recommendation.")

        return WdvLayoutPresetRecommendationResponse(
            managed_well_id=str(well_dict.get("managed_well_id") or managed_well_id),
            well_name=well_dict.get("well_name"),
            preset_id=spec.preset_id,
            preset_name=spec.name,
            kr_template_record_id=spec.kr_record_id,
            kr_template_status=spec.kr_record_status,
            recommendation_status=recommendation_status,
            completeness_score=round(completeness_score, 3),
            available_curve_count=len(eligible),
            selected_curve_count=selected_curve_count,
            excluded_other_review_count=excluded_other,
            missing_required_families=missing_required_families,
            tracks=tracks,
            warnings=warnings,
            knowledge_policy=self._knowledge_policy(),
            apply_ready=False,
        )

    # ------------------------------------------------------------------
    # KR template access
    # ------------------------------------------------------------------

    def _get_knowledge_repository(self) -> Any | None:
        if self._knowledge_repository is not None:
            return self._knowledge_repository
        if not self._use_default_knowledge_repository:
            return None
        from backend.app.knowledge.api_managed_knowledge import get_managed_repository

        self._knowledge_repository = get_managed_repository()
        return self._knowledge_repository

    def _load_template_records(self) -> list[dict[str, Any]]:
        repo = self._get_knowledge_repository()
        if repo is None:
            return []

        records: list[Any]
        if hasattr(repo, "list_production_eligible_records"):
            records = repo.list_production_eligible_records(record_type="template_rule")
        elif hasattr(repo, "list_records"):
            records = repo.list_records(record_type="template_rule")
        else:
            return []

        result: list[dict[str, Any]] = []
        for raw in records or []:
            record = _as_dict(raw)
            status = _status_value(record.get("status"))
            record_type = _normalize_key(record.get("record_type"))
            if record_type != "template_rule":
                continue
            if status not in _PRODUCTION_ELIGIBLE_STATUSES:
                continue
            record["status"] = status
            result.append(record)
        return result

    def _load_template_specs(self) -> list[_TemplateSpec]:
        specs: list[_TemplateSpec] = []
        for record in self._load_template_records():
            try:
                specs.append(self._template_from_record(record))
            except ValueError:
                continue
        specs.sort(key=lambda spec: spec.preset_id)
        return specs

    def _resolve_preset_id(self, preset_id: str) -> str:
        key = _normalize_key(preset_id)
        return _TEMPLATE_ALIASES.get(key, key)

    def _get_preset(self, preset_id: str) -> _TemplateSpec:
        target = self._resolve_preset_id(preset_id)
        for spec in self._load_template_specs():
            if spec.preset_id == target:
                return spec
        raise ValueError(
            f"Unknown or non-approved WDV layout preset: {preset_id}. "
            "Only approved production-eligible KR template_rule records are available."
        )

    def _template_from_record(self, record: dict[str, Any]) -> _TemplateSpec:
        template_key = _normalize_key(record.get("template_key"))
        if not template_key:
            raise ValueError("template_rule record missing template_key")
        track_order = [_normalize_key(v) for v in _as_str_list(record.get("track_order"))]
        track_order = [v for v in track_order if v]
        if not track_order:
            raise ValueError(f"template_rule {template_key} missing track_order")

        required = tuple(dict.fromkeys(_normalize_key(v) for v in _as_str_list(record.get("required_curve_families")) if _normalize_key(v)))
        preferred = tuple(dict.fromkeys(_normalize_key(v) for v in _as_str_list(record.get("preferred_curve_families")) if _normalize_key(v)))
        fallback = tuple(dict.fromkeys(_normalize_key(v) for v in _as_str_list(record.get("fallback_curve_families")) if _normalize_key(v)))
        overlay_rules = [_as_dict(rule) for rule in record.get("overlay_rules") or []]

        tracks = self._tracks_from_template(
            track_order=track_order,
            required_families=required,
            preferred_families=preferred,
            fallback_families=fallback,
            overlay_rules=overlay_rules,
        )

        return _TemplateSpec(
            preset_id=template_key,
            name=str(record.get("template_label") or _title_from_key(template_key)),
            description=str(record.get("description") or record.get("template_label") or _title_from_key(template_key)),
            kr_record_id=str(record.get("record_id") or template_key),
            kr_record_status=_status_value(record.get("status")),
            production_eligible=True,
            tracks=tuple(tracks),
            required_families=required,
            preferred_families=preferred,
            fallback_families=fallback,
            missing_curve_behavior=record.get("missing_curve_behavior"),
            notes=tuple(_as_str_list(record.get("notes"))),
        )

    def _tracks_from_template(
        self,
        track_order: list[str],
        required_families: tuple[str, ...],
        preferred_families: tuple[str, ...],
        fallback_families: tuple[str, ...],
        overlay_rules: list[dict[str, Any]],
    ) -> list[_TrackSpec]:
        track_ids = list(dict.fromkeys(track_order))
        required_by_track: dict[str, list[str]] = {track: [] for track in track_ids}
        optional_by_track: dict[str, list[str]] = {track: [] for track in track_ids}
        overlay_by_track: dict[str, list[dict[str, Any]]] = {track: [] for track in track_ids}

        def ensure_track(track_id: str) -> None:
            if track_id not in track_ids:
                track_ids.append(track_id)
                required_by_track[track_id] = []
                optional_by_track[track_id] = []
                overlay_by_track[track_id] = []

        for family in required_families:
            track = _best_track_for_family(track_ids, family) or family
            ensure_track(track)
            required_by_track[track].append(family)

        for family in [*preferred_families, *fallback_families]:
            track = _best_track_for_family(track_ids, family) or family
            ensure_track(track)
            optional_by_track[track].append(family)

        for rule in overlay_rules:
            track = _normalize_key(rule.get("track")) or "overlay"
            ensure_track(track)
            overlay_by_track[track].append(rule)
            for family in _as_str_list(rule.get("overlay_families")):
                norm_family = _normalize_key(family)
                if norm_family:
                    optional_by_track[track].append(norm_family)

        tracks: list[_TrackSpec] = []
        for track_id in track_ids:
            required = tuple(dict.fromkeys(required_by_track.get(track_id, [])))
            optional = tuple(
                family
                for family in dict.fromkeys(optional_by_track.get(track_id, []))
                if family not in set(required)
            )
            tracks.append(
                _TrackSpec(
                    track_id=track_id,
                    label=_title_from_key(track_id),
                    required_families=required,
                    optional_families=optional,
                    overlay_rules=tuple(overlay_by_track.get(track_id, [])),
                )
            )
        return tracks

    # ------------------------------------------------------------------
    # Inventory access and recommendation logic
    # ------------------------------------------------------------------

    def _get_inventory_service(self) -> Any:
        if self._inventory_service is not None:
            return self._inventory_service
        from backend.app.inventory.service import ManagedWellInventoryService

        self._inventory_service = ManagedWellInventoryService()
        return self._inventory_service

    def _get_managed_well(self, managed_well_id: str) -> Any:
        service = self._get_inventory_service()
        if hasattr(service, "get_well"):
            return service.get_well(managed_well_id)
        if hasattr(service, "list_wells"):
            for well in service.list_wells():
                well_dict = _as_dict(well)
                if well_dict.get("managed_well_id") == managed_well_id or well_dict.get("well_id") == managed_well_id:
                    return well
        raise LookupError(f"Managed well not found: {managed_well_id}")

    def _eligible_product_items(self, well: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
        eligible: list[dict[str, Any]] = []
        excluded_other = 0

        for group_raw in well.get("product_groups") or []:
            group = _as_dict(group_raw)
            group_key = _normalize_key(group.get("group_key") or group.get("product_group_key"))
            items = group.get("items") or group.get("products") or group.get("product_items") or []
            for item_raw in items:
                item = _as_dict(item_raw)
                category = _normalize_key(item.get("product_category") or group_key)
                subgroup = _normalize_key(item.get("product_subgroup_key"))
                confidence = _normalize_key(item.get("classification_confidence"))
                if group_key in _OTHER_REVIEW_GROUPS or category in _OTHER_REVIEW_GROUPS:
                    excluded_other += 1
                    continue
                if subgroup in _OTHER_REVIEW_GROUPS:
                    excluded_other += 1
                    continue
                if confidence in _LOW_CONFIDENCE:
                    continue
                if not item.get("product_id"):
                    continue
                if not (item.get("curve_name") or item.get("mnemonic") or item.get("source_curve_name")):
                    continue
                enriched = dict(item)
                enriched["_group_key"] = group_key
                enriched["_canonical_curve_id"] = _extract_canonical_curve_id(item)
                enriched["_normalized_family"] = self._item_family(item)
                eligible.append(enriched)

        return eligible, excluded_other

    def _item_family(self, item: dict[str, Any]) -> str:
        family = _normalize_key(item.get("curve_family"))
        if family:
            return family
        subgroup = _normalize_key(item.get("product_subgroup_key"))
        if subgroup:
            return subgroup
        canonical = _normalize_key(_extract_canonical_curve_id(item))
        if canonical:
            return canonical
        return _normalize_key(item.get("curve_name") or item.get("mnemonic"))

    def _item_families(self, item: dict[str, Any]) -> set[str]:
        families = {
            self._item_family(item),
            _normalize_key(item.get("product_subgroup_key")),
            _normalize_key(item.get("_canonical_curve_id")),
        }
        product_subgroup_label = _normalize_key(item.get("product_subgroup_label"))
        if product_subgroup_label:
            families.add(product_subgroup_label)
        families.discard("")
        return families

    def _build_family_index(self, items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        index: dict[str, list[dict[str, Any]]] = {}
        for item in items:
            for family in self._item_families(item):
                index.setdefault(family, []).append(item)

        for family, family_items in index.items():
            deduped: dict[str, dict[str, Any]] = {}
            for item in sorted(family_items, key=_candidate_sort_key):
                mnemonic = _upper_mnemonic(
                    item.get("curve_name") or item.get("mnemonic") or item.get("source_curve_name")
                )
                deduped.setdefault(mnemonic, item)
            index[family] = list(deduped.values())
        return index

    def _recommend_track(
        self,
        spec: _TrackSpec,
        family_index: dict[str, list[dict[str, Any]]],
        selected_product_ids: set[str],
    ) -> WdvPresetTrackRecommendation:
        selected: list[dict[str, Any]] = []
        missing_required: list[str] = []

        for family in spec.required_families:
            matches = self._available_family(family, family_index, selected_product_ids)
            if not matches:
                missing_required.append(family)
                continue
            selected.extend(matches)

        for family in spec.optional_families:
            matches = self._available_family(family, family_index, selected_product_ids)
            for item in matches:
                if item.get("product_id") not in {x.get("product_id") for x in selected}:
                    selected.append(item)

        if spec.max_curves is not None:
            selected = selected[: spec.max_curves]

        curves = [self._curve_candidate(item) for item in selected]
        if missing_required:
            status = "partial" if curves else "missing"
            reason = "One or more required KR template curve families are missing."
        elif curves:
            status = "recommended"
            reason = "Matched managed inventory curves to approved KR template_rule family requirements."
        else:
            status = "empty"
            reason = "No eligible managed inventory curves matched this KR template track."

        return WdvPresetTrackRecommendation(
            track_id=spec.track_id,
            label=spec.label,
            status=status,
            required_families=list(spec.required_families),
            optional_families=list(spec.optional_families),
            overlay_rules=list(spec.overlay_rules),
            curves=curves,
            missing_required_families=missing_required,
            missing_optional_families=[
                family
                for family in spec.optional_families
                if _normalize_key(family) not in family_index
            ],
            reason=reason,
        )

    def _available_family(
        self,
        family: str,
        family_index: dict[str, list[dict[str, Any]]],
        selected_product_ids: set[str],
    ) -> list[dict[str, Any]]:
        matches: list[dict[str, Any]] = []
        seen_product_ids: set[str] = set()
        for item in family_index.get(_normalize_key(family), []):
            product_id = str(item.get("product_id") or "")
            if not product_id or product_id in selected_product_ids or product_id in seen_product_ids:
                continue
            seen_product_ids.add(product_id)
            matches.append(item)
        return sorted(matches, key=_candidate_sort_key)

    def _curve_candidate(self, item: dict[str, Any]) -> WdvPresetCurveCandidate:
        mnemonic = _upper_mnemonic(item.get("curve_name") or item.get("mnemonic") or item.get("source_curve_name"))
        display_scale = self._display_scale_for_item(item)
        canonical_curve_id = item.get("_canonical_curve_id")
        family = self._item_family(item)
        evidence = [str(reason) for reason in item.get("classification_reasons") or [] if str(reason)]
        source = str(item.get("classification_source") or "managed_inventory")
        confidence = str(item.get("classification_confidence") or "unknown")

        return WdvPresetCurveCandidate(
            product_id=str(item.get("product_id")),
            curve_name=str(item.get("curve_name") or mnemonic),
            mnemonic=mnemonic,
            display_name=item.get("display_name") or item.get("curve_type") or item.get("curve_description"),
            canonical_curve_id=canonical_curve_id,
            curve_family=family,
            product_category=item.get("product_category"),
            product_subgroup_key=item.get("product_subgroup_key"),
            product_subgroup_label=item.get("product_subgroup_label"),
            classification_source=source,
            classification_confidence=confidence,
            unit=item.get("curve_unit") or item.get("unit"),
            display_scale=display_scale,
            reason=(
                f"Selected {mnemonic} from Managed Well Inventory for an approved KR "
                f"template_rule using {source} classification ({confidence})."
            ),
            evidence=evidence,
        )

    # ------------------------------------------------------------------
    # Display rule resolution
    # ------------------------------------------------------------------

    def _get_display_recommendation_service(self) -> Any | None:
        if self._display_recommendation_service is not None:
            return self._display_recommendation_service
        if not self._use_default_display_service:
            return None
        try:
            from backend.app.knowledge.api_managed_knowledge import (
                get_managed_repository,
                get_recommendation_service,
            )

            self._display_recommendation_service = get_recommendation_service(get_managed_repository())
        except Exception:
            self._display_recommendation_service = None
        return self._display_recommendation_service

    def _display_scale_for_item(self, item: dict[str, Any]) -> WdvDisplayScaleRecommendation:
        from_kr8 = self._display_scale_from_kr8(item)
        if from_kr8 is not None:
            return from_kr8
        return WdvDisplayScaleRecommendation(
            scale_type=None,
            display_min=None,
            display_max=None,
            default_unit=item.get("curve_unit") or item.get("unit"),
            source="unresolved",
        )

    def _display_scale_from_kr8(self, item: dict[str, Any]) -> WdvDisplayScaleRecommendation | None:
        service = self._get_display_recommendation_service()
        if service is None:
            return None
        try:
            try:
                from backend.app.knowledge.display_recommendation_service import (
                    CurveRecommendInput,
                    DisplayRecommendationRequest,
                )

                request = DisplayRecommendationRequest(
                    curves=[
                        CurveRecommendInput(
                            curve_id=str(item.get("product_id")),
                            mnemonic=_upper_mnemonic(item.get("curve_name") or item.get("mnemonic")),
                            unit=item.get("curve_unit") or item.get("unit"),
                            description=item.get("curve_description") or item.get("description"),
                        )
                    ],
                    well_id=None,
                    source=None,
                )
            except Exception:
                from types import SimpleNamespace

                request = SimpleNamespace(
                    curves=[
                        SimpleNamespace(
                            curve_id=str(item.get("product_id")),
                            mnemonic=_upper_mnemonic(item.get("curve_name") or item.get("mnemonic")),
                            unit=item.get("curve_unit") or item.get("unit"),
                            description=item.get("curve_description") or item.get("description"),
                        )
                    ],
                    well_id=None,
                    source=None,
                )
            result = service.recommend_display(request)
            rec = result.recommendations[0] if result.recommendations else None
            if rec is None or rec.recommendation_status != "recommended":
                return None
            return WdvDisplayScaleRecommendation(
                scale_type=rec.scale_type,
                display_min=rec.recommended_min,
                display_max=rec.recommended_max,
                default_unit=rec.unit,
                reverse_scale=(
                    rec.recommended_min is not None
                    and rec.recommended_max is not None
                    and rec.recommended_min > rec.recommended_max
                ),
                preferred_track_family=rec.preferred_track_group,
                source="kr8_display_recommendation",
            )
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Response helpers
    # ------------------------------------------------------------------

    def _preset_to_model(self, spec: _TemplateSpec) -> WdvLayoutPresetDefinition:
        return WdvLayoutPresetDefinition(
            preset_id=spec.preset_id,
            name=spec.name,
            description=spec.description,
            category="kr_template",
            kr_record_id=spec.kr_record_id,
            kr_record_status=spec.kr_record_status,
            production_eligible=spec.production_eligible,
            source="managed_kr_template_rule",
            tracks=[
                WdvLayoutPresetTrackDefinition(
                    track_id=track.track_id,
                    label=track.label,
                    purpose=track.purpose,
                    required_families=list(track.required_families),
                    optional_families=list(track.optional_families),
                    overlay_rules=list(track.overlay_rules),
                    max_curves=track.max_curves,
                )
                for track in spec.tracks
            ],
            required_families=list(spec.required_families),
            optional_families=list(spec.preferred_families),
            fallback_families=list(spec.fallback_families),
            missing_curve_behavior=spec.missing_curve_behavior,
            notes=list(spec.notes),
        )

    def _knowledge_policy(self) -> dict[str, Any]:
        return {
            "backend_owns_recommendation": True,
            "frontend_may_not_classify_curves": True,
            "template_rule_source": "managed_kr_production_eligible",
            "candidate_template_rules_used": False,
            "candidate_knowledge_used": False,
            "other_review_required_excluded_by_default": True,
            "side_effect_free": True,
            "does_not_apply_tracks": True,
            "display_scale_source": "kr8_display_recommendation_or_unresolved",
        }
