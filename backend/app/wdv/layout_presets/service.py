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
            for curve in track.selected_curves:
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

        selected_curve_count = sum(track.selected_curve_count for track in tracks)
        alternate_curve_count = sum(track.alternate_curve_count for track in tracks)
        track_excluded_curve_count = sum(track.excluded_curve_count for track in tracks)
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
            alternate_curve_count=alternate_curve_count,
            track_excluded_curve_count=track_excluded_curve_count,
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

    def _rank_track_candidates(
        self,
        spec: _TrackSpec,
        candidate_items: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
        """Rank candidate curves into display-ready selections and alternates.

        This is deliberately deterministic and backend-owned. It is not a
        frontend convenience filter. The policy is intentionally conservative:
        it chooses a small display-ready subset while preserving valid
        alternates for later user override through a backend-owned apply flow.
        """

        policy = self._selection_policy_for_track(spec)
        if not candidate_items:
            return [], [], [], policy

        deduped = self._dedupe_candidate_items(candidate_items)
        track_id = _normalize_key(spec.track_id)

        if track_id == "resistivity":
            selected, alternates = self._select_resistivity_candidates(deduped)
        elif track_id == "density_neutron":
            selected, alternates = self._select_one_per_family(
                deduped,
                family_order=("density", "neutron_porosity"),
                max_selected=2,
            )
        else:
            selected, alternates = self._select_generic_candidates(
                spec=spec,
                candidate_items=deduped,
                max_selected=int(policy["max_initial_curves"]),
            )

        selected_ids = {str(item.get("product_id")) for item in selected}
        ranked_alternates = [item for item in alternates if str(item.get("product_id")) not in selected_ids]
        return selected, ranked_alternates, [], policy

    def _selection_policy_for_track(self, spec: _TrackSpec) -> dict[str, Any]:
        track_id = _normalize_key(spec.track_id)
        required = [_normalize_key(v) for v in spec.required_families]
        optional = [_normalize_key(v) for v in spec.optional_families]
        families = list(dict.fromkeys([*required, *optional]))

        max_initial = spec.max_curves
        policy_name = "one_best_curve_per_family"
        if track_id == "resistivity":
            max_initial = 3 if max_initial is None else min(max_initial, 3)
            policy_name = "resistivity_depth_of_investigation_tiers"
        elif track_id == "density_neutron":
            max_initial = 2 if max_initial is None else min(max_initial, 2)
            policy_name = "density_neutron_overlay_pair"
        elif track_id in {"sonic"}:
            max_initial = 3 if max_initial is None else min(max_initial, 3)
            policy_name = "sonic_primary_and_shear_subset"
        elif max_initial is None:
            max_initial = max(1, min(3, len(families) or 1))

        return {
            "policy_name": policy_name,
            "max_initial_curves": int(max_initial),
            "frontend_may_not_expand_selection": True,
            "alternates_require_backend_apply_flow": True,
            "ranking_inputs": [
                "approved_kr_template_rule",
                "managed_inventory_curve_family",
                "classification_confidence",
                "classification_source",
                "mnemonic_priority",
                "display_rule_availability",
            ],
        }

    def _dedupe_candidate_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_product: dict[str, dict[str, Any]] = {}
        for item in sorted(items, key=_candidate_sort_key):
            product_id = str(item.get("product_id") or "")
            if product_id:
                by_product.setdefault(product_id, item)
        return list(by_product.values())

    def _select_resistivity_candidates(
        self,
        candidate_items: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        selected: list[dict[str, Any]] = []
        alternates: list[dict[str, Any]] = []
        used_ids: set[str] = set()
        tier_order = ("deep", "medium", "shallow")

        for tier in tier_order:
            tier_items = [item for item in candidate_items if self._resistivity_tier(item) == tier]
            ranked = self._rank_items_for_family(tier_items, preferred_family="resistivity", tier=tier)
            if ranked:
                best = ranked[0]
                selected.append(best)
                used_ids.add(str(best.get("product_id")))
                alternates.extend(ranked[1:])

        alternate_ids = {str(item.get("product_id")) for item in alternates}
        remaining = [
            item
            for item in candidate_items
            if str(item.get("product_id")) not in used_ids
            and str(item.get("product_id")) not in alternate_ids
        ]
        alternates.extend(self._rank_items_for_family(remaining, preferred_family="resistivity"))
        return selected, alternates

    def _select_one_per_family(
        self,
        candidate_items: list[dict[str, Any]],
        family_order: tuple[str, ...],
        max_selected: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        selected: list[dict[str, Any]] = []
        alternates: list[dict[str, Any]] = []
        used_ids: set[str] = set()

        for family in family_order:
            matches = [item for item in candidate_items if family in self._item_families(item)]
            ranked = self._rank_items_for_family(matches, preferred_family=family)
            if ranked and len(selected) < max_selected:
                selected.append(ranked[0])
                used_ids.add(str(ranked[0].get("product_id")))
                alternates.extend(ranked[1:])
            else:
                alternates.extend(ranked)

        alternate_ids = {str(item.get("product_id")) for item in alternates}
        remaining = [
            item
            for item in candidate_items
            if str(item.get("product_id")) not in used_ids
            and str(item.get("product_id")) not in alternate_ids
        ]
        alternates.extend(self._rank_items_for_family(remaining))
        return selected, alternates

    def _select_generic_candidates(
        self,
        spec: _TrackSpec,
        candidate_items: list[dict[str, Any]],
        max_selected: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        family_order = tuple(dict.fromkeys([*spec.required_families, *spec.optional_families]))
        if family_order:
            selected, alternates = self._select_one_per_family(
                candidate_items,
                family_order=tuple(_normalize_key(v) for v in family_order),
                max_selected=max_selected,
            )
            return selected[:max_selected], [*selected[max_selected:], *alternates]

        ranked = self._rank_items_for_family(candidate_items)
        return ranked[:max_selected], ranked[max_selected:]

    def _rank_items_for_family(
        self,
        items: list[dict[str, Any]],
        preferred_family: str | None = None,
        tier: str | None = None,
    ) -> list[dict[str, Any]]:
        ranked: list[tuple[tuple[int, int, int, str], dict[str, Any]]] = []
        for item in items:
            score, reasons = self._selection_score(item, preferred_family=preferred_family, tier=tier)
            enriched = dict(item)
            enriched["_selection_score"] = float(score)
            enriched["_ranking_reasons"] = reasons
            ranked.append(((-score, *_candidate_sort_key(item)), enriched))
        ranked.sort(key=lambda value: value[0])
        return [item for _, item in ranked]

    def _selection_score(
        self,
        item: dict[str, Any],
        preferred_family: str | None = None,
        tier: str | None = None,
    ) -> tuple[int, list[str]]:
        mnemonic = _upper_mnemonic(item.get("curve_name") or item.get("mnemonic") or item.get("source_curve_name"))
        family = _normalize_key(preferred_family or self._item_family(item))
        score = _confidence_rank(item.get("classification_confidence")) + _source_rank(item.get("classification_source"))
        reasons = [
            f"classification_confidence={item.get('classification_confidence') or 'unknown'}",
            f"classification_source={item.get('classification_source') or 'managed_inventory'}",
        ]

        priority = self._mnemonic_priority(mnemonic=mnemonic, family=family, tier=tier)
        score += priority
        reasons.append(f"mnemonic_priority={priority}")
        if tier:
            reasons.append(f"resistivity_tier={tier}")
        if self._display_scale_for_item(item).scale_type:
            score += 5
            reasons.append("display_rule_available")
        return score, reasons

    def _mnemonic_priority(self, mnemonic: str, family: str, tier: str | None = None) -> int:
        m = _upper_mnemonic(mnemonic)
        fam = _normalize_key(family)
        exact_priority = {
            "gamma_ray": {"GR": 100, "ECGR": 85, "HGR": 80, "GR_EDTC": 70, "GR_STGC": 65},
            "density": {"RHOZ": 100, "RHOB": 95, "RHOM": 75, "RHL": 65, "HDRB": 60, "DPHZ": 45},
            "neutron_porosity": {"NPHI": 100, "TNPH": 90, "NPOR": 80, "DNPH": 70, "HTNP": 60, "HNPO": 55},
            "caliper": {"CALI": 100, "HCAL": 85, "DCAL": 75},
            "photoelectric_factor": {"PEFZ": 100, "PEFS": 85, "PEFL": 80, "HPRA": 60},
            "sonic": {"DTCO": 100, "DTC": 95, "DTSM": 85, "DTST": 80},
            "spontaneous_potential": {"SP": 100, "SPAR": 80},
            "collar_locator": {"CCL": 100},
            "cement_bond": {"CBL": 100, "CBLAMP": 85, "AMP3FT": 75},
            "variable_density": {"VDL": 100},
        }
        if fam == "resistivity":
            return self._resistivity_priority(m, tier=tier)
        for key, values in exact_priority.items():
            if fam == key or key in fam:
                return values.get(m, 40)
        return 40

    def _resistivity_tier(self, item: dict[str, Any]) -> str:
        mnemonic = _upper_mnemonic(item.get("curve_name") or item.get("mnemonic") or item.get("source_curve_name"))
        numbers = [int(value) for value in re.findall(r"(\d+)", mnemonic)]
        if numbers:
            value = max(numbers)
            if value >= 60:
                return "deep"
            if value >= 20:
                return "medium"
            return "shallow"
        if any(token in mnemonic for token in ("RT", "RD", "DEEP")):
            return "deep"
        if any(token in mnemonic for token in ("RX", "MS", "MED")):
            return "medium"
        return "other"

    def _resistivity_priority(self, mnemonic: str, tier: str | None = None) -> int:
        m = _upper_mnemonic(mnemonic)
        prefix_priority = 0
        if m.startswith("AT"):
            prefix_priority = 100
        elif m.startswith("AO"):
            prefix_priority = 90
        elif m.startswith("AF"):
            prefix_priority = 80
        elif m.startswith("AOR"):
            prefix_priority = 70
        elif m.startswith("RS"):
            prefix_priority = 60
        else:
            prefix_priority = 40

        desired = {"deep": 90, "medium": 30, "shallow": 10}.get(tier or "", None)
        numbers = [int(value) for value in re.findall(r"(\d+)", m)]
        if desired is not None and numbers:
            distance = min(abs(value - desired) for value in numbers)
            return prefix_priority + max(0, 40 - distance)
        return prefix_priority

    def _recommend_track(
        self,
        spec: _TrackSpec,
        family_index: dict[str, list[dict[str, Any]]],
        selected_product_ids: set[str],
    ) -> WdvPresetTrackRecommendation:
        candidate_items: list[dict[str, Any]] = []
        missing_required: list[str] = []

        for family in spec.required_families:
            matches = self._available_family(family, family_index, selected_product_ids)
            if not matches:
                missing_required.append(family)
                continue
            candidate_items.extend(matches)

        for family in spec.optional_families:
            matches = self._available_family(family, family_index, selected_product_ids)
            for item in matches:
                if item.get("product_id") not in {x.get("product_id") for x in candidate_items}:
                    candidate_items.append(item)

        selected_items, alternate_items, excluded_items, policy = self._rank_track_candidates(
            spec=spec,
            candidate_items=candidate_items,
        )

        selected_curves = [
            self._curve_candidate(
                item,
                role="selected",
                rank=index + 1,
                ranking_reasons=item.get("_ranking_reasons") or [],
                selection_score=item.get("_selection_score"),
            )
            for index, item in enumerate(selected_items)
        ]
        alternate_curves = [
            self._curve_candidate(
                item,
                role="alternate",
                rank=index + 1,
                ranking_reasons=item.get("_ranking_reasons") or [],
                selection_score=item.get("_selection_score"),
            )
            for index, item in enumerate(alternate_items)
        ]
        excluded_curves = [
            self._curve_candidate(
                item,
                role="excluded",
                rank=index + 1,
                ranking_reasons=item.get("_ranking_reasons") or [],
                selection_score=item.get("_selection_score"),
            )
            for index, item in enumerate(excluded_items)
        ]

        if missing_required:
            status = "partial" if selected_curves else "missing"
            reason = "One or more required KR template curve families are missing."
        elif selected_curves:
            status = "recommended"
            reason = "Ranked managed inventory curves into display-ready selections and alternates."
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
            selected_curves=selected_curves,
            alternate_curves=alternate_curves,
            excluded_curves=excluded_curves,
            curves=selected_curves,
            candidate_curve_count=len(candidate_items),
            selected_curve_count=len(selected_curves),
            alternate_curve_count=len(alternate_curves),
            excluded_curve_count=len(excluded_curves),
            selection_policy=policy,
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

    def _curve_candidate(
        self,
        item: dict[str, Any],
        role: str = "selected",
        rank: int | None = None,
        ranking_reasons: list[str] | None = None,
        selection_score: float | None = None,
    ) -> WdvPresetCurveCandidate:
        mnemonic = _upper_mnemonic(item.get("curve_name") or item.get("mnemonic") or item.get("source_curve_name"))
        display_scale = self._display_scale_for_item(item)
        canonical_curve_id = item.get("_canonical_curve_id")
        family = self._item_family(item)
        evidence = [str(reason) for reason in item.get("classification_reasons") or [] if str(reason)]
        source = str(item.get("classification_source") or "managed_inventory")
        confidence = str(item.get("classification_confidence") or "unknown")
        verb = {
            "selected": "Selected",
            "alternate": "Ranked as alternate",
            "excluded": "Excluded",
        }.get(role, "Considered")

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
            selection_role=role,
            rank=rank,
            selection_score=selection_score,
            ranking_reasons=ranking_reasons or [],
            reason=(
                f"{verb} {mnemonic} from Managed Well Inventory for an approved KR "
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
