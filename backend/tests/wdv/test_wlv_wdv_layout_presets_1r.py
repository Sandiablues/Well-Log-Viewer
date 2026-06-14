"""WLV-WDV-LAYOUT-PRESETS-1R tests.

This block verifies that WDV layout preset definitions come from approved KR
``template_rule`` records, not static frontend/backend preset lists. The endpoint
is recommendation-only and must not apply tracks or mutate WDV session state.
"""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.wdv.layout_presets.router import get_layout_preset_service, router
from backend.app.wdv.layout_presets.service import WdvLayoutPresetService


class _FakeInventoryService:
    def __init__(self, well: dict):
        self._well = well

    def get_well(self, managed_well_id: str) -> dict:
        if managed_well_id != self._well["managed_well_id"]:
            raise LookupError(managed_well_id)
        return self._well


class _FakeKnowledgeRepository:
    def __init__(self, records: list[dict]):
        self._records = records

    def list_production_eligible_records(self, record_type: str | None = None) -> list[dict]:
        records = self._records
        if record_type is not None:
            records = [r for r in records if r.get("record_type") == record_type]
        # Deliberately return all matching record types. The service must still
        # enforce approved/seed status and exclude candidates.
        return records


class _FakeDisplayRecommendationService:
    def recommend_display(self, request):
        curve = request.curves[0]
        mnemonic = curve.mnemonic.upper()
        if mnemonic.startswith("AT") or mnemonic.startswith("AF"):
            scale_type = "log"
            low, high = 0.2, 2000.0
        elif mnemonic == "GR":
            scale_type = "linear"
            low, high = 0.0, 150.0
        else:
            scale_type = "linear"
            low, high = None, None
        return SimpleNamespace(
            recommendations=[
                SimpleNamespace(
                    recommendation_status="recommended",
                    scale_type=scale_type,
                    recommended_min=low,
                    recommended_max=high,
                    unit=curve.unit,
                    preferred_track_group=None,
                )
            ]
        )


def _template(
    key: str = "basic_triple_combo_openhole",
    status: str = "approved",
) -> dict:
    return {
        "record_id": f"template:{key}",
        "record_type": "template_rule",
        "template_key": key,
        "template_label": "Basic Triple Combo Open-Hole Display",
        "track_order": ["gamma_ray_sp", "resistivity", "density_neutron", "sonic"],
        "required_curve_families": ["gamma_ray", "resistivity"],
        "preferred_curve_families": ["density", "neutron_porosity", "sonic"],
        "fallback_curve_families": ["caliper", "photoelectric_factor"],
        "overlay_rules": [
            {
                "track": "density_neutron",
                "overlay_families": ["density", "neutron_porosity"],
                "note": "Density-neutron overlay.",
            }
        ],
        "missing_curve_behavior": "skip",
        "status": status,
    }


def _item(
    name: str,
    family: str,
    subgroup: str,
    product_id: str | None = None,
    confidence: str = "high",
    source: str = "runtime_alias",
    category: str = "open_hole_logs",
) -> dict:
    return {
        "product_id": product_id or f"pid:{name.lower()}",
        "curve_name": name,
        "display_name": name,
        "curve_family": family,
        "curve_unit": "GAPI" if name == "GR" else "OHMM",
        "product_category": category,
        "product_subgroup_key": subgroup,
        "product_subgroup_label": subgroup.replace("_", " ").title(),
        "classification_source": source,
        "classification_confidence": confidence,
        "classification_reasons": [f"Runtime KR resolved mnemonic {name}.", f"Canonical curve: {family}."],
    }


def _well(items: list[dict], other_items: list[dict] | None = None) -> dict:
    return {
        "managed_well_id": "managed-well:test",
        "well_id": "test-well",
        "well_name": "Test Well",
        "product_groups": [
            {
                "group_key": "open_hole_logs",
                "group_label": "Open hole logs",
                "items": items,
            },
            {
                "group_key": "other_review_required",
                "group_label": "Other / Review Required",
                "items": other_items or [],
            },
        ],
    }


def _service(
    well: dict,
    kr_records: list[dict] | None = None,
) -> WdvLayoutPresetService:
    return WdvLayoutPresetService(
        inventory_service=_FakeInventoryService(well),
        knowledge_repository=_FakeKnowledgeRepository(kr_records or [_template()]),
        display_recommendation_service=_FakeDisplayRecommendationService(),
        use_default_knowledge_repository=False,
        use_default_display_service=False,
    )


def test_preset_list_comes_from_approved_kr_template_rules_only() -> None:
    service = _service(
        _well([]),
        kr_records=[
            _template("basic_triple_combo_openhole", "approved"),
            _template("candidate_should_not_be_runtime", "candidate"),
        ],
    )

    response = service.list_presets()

    assert response.preset_count == 1
    assert [preset.preset_id for preset in response.presets] == ["basic_triple_combo_openhole"]
    assert response.presets[0].kr_record_status == "approved"
    assert response.presets[0].source == "managed_kr_template_rule"
    assert response.knowledge_policy["candidate_template_rules_used"] is False
    assert "triple_combo" not in [preset.preset_id for preset in response.presets]


def test_candidate_template_rules_do_not_influence_runtime_presets() -> None:
    service = _service(
        _well([]),
        kr_records=[_template("basic_triple_combo_openhole", "candidate")],
    )

    response = service.list_presets()

    assert response.preset_count == 0
    assert response.presets == []
    assert response.warnings == [
        "No approved production-eligible KR template_rule records are available for WDV presets."
    ]


def test_kr_triple_combo_recommendation_excludes_other_and_does_not_apply_tracks() -> None:
    service = _service(
        _well(
            [
                _item("GR", "gamma_ray", "gamma_ray"),
                _item("AT90", "resistivity", "resistivity"),
                _item("RHOZ", "density", "density_neutron_porosity"),
                _item("NPHI", "neutron_porosity", "density_neutron_porosity"),
                _item("DCAL", "caliper", "borehole_geometry_imaging"),
            ],
            other_items=[_item("UNKNOWN", "unknown", "review_required", category="other_review_required")],
        )
    )

    response = service.recommend_preset("managed-well:test", "triple_combo")

    assert response.preset_id == "basic_triple_combo_openhole"
    assert response.kr_template_status == "approved"
    assert response.recommendation_status == "ready"
    assert response.apply_ready is False
    assert response.knowledge_policy["does_not_apply_tracks"] is True
    assert response.excluded_other_review_count == 1
    assert response.selected_curve_count >= 4
    assert response.missing_required_families == []

    track_map = {track.track_id: track for track in response.tracks}
    assert [curve.mnemonic for curve in track_map["gamma_ray_sp"].curves] == ["GR"]
    assert [curve.mnemonic for curve in track_map["resistivity"].curves] == ["AT90"]
    assert {curve.mnemonic for curve in track_map["density_neutron"].curves} == {"RHOZ", "NPHI"}
    assert track_map["resistivity"].curves[0].display_scale.scale_type == "log"


def test_recommendation_reports_missing_required_families_from_kr_template() -> None:
    service = _service(_well([_item("GR", "gamma_ray", "gamma_ray")]))

    response = service.recommend_preset("managed-well:test", "basic_triple_combo_openhole")

    assert response.recommendation_status == "partial"
    assert response.missing_required_families == ["resistivity"]
    assert response.apply_ready is False


def test_router_contract_can_be_mounted_without_frontend_changes() -> None:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_layout_preset_service] = lambda: _service(
        _well(
            [
                _item("GR", "gamma_ray", "gamma_ray"),
                _item("AT90", "resistivity", "resistivity"),
                _item("RHOZ", "density", "density_neutron_porosity"),
            ]
        )
    )

    client = TestClient(app)

    list_response = client.get("/api/wlv/wdv/layout-presets")
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["contract_version"] == "wdv_layout_presets_v1r"
    assert payload["presets"][0]["source"] == "managed_kr_template_rule"

    recommend_response = client.get(
        "/api/wlv/wdv/layout-presets/recommend",
        params={"well_id": "managed-well:test", "preset_id": "triple_combo"},
    )
    assert recommend_response.status_code == 200
    payload = recommend_response.json()
    assert payload["preset_id"] == "basic_triple_combo_openhole"
    assert payload["apply_ready"] is False
    assert payload["knowledge_policy"]["frontend_may_not_classify_curves"] is True
