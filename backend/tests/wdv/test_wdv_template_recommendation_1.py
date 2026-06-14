"""WDV-BACKEND-TEMPLATE-RECOMMENDATION-1 tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def _sample_loaded_curve_items() -> list[dict[str, object]]:
    return [
        {
            "product_id": "curve_gr",
            "display_curve_id": "GR",
            "mnemonic": "GR",
            "display_name": "Gamma Ray",
            "curve_family": "gamma_ray",
            "unit": "API",
        },
        {
            "product_id": "curve_ild",
            "display_curve_id": "ILD",
            "mnemonic": "ILD",
            "display_name": "Deep Induction Resistivity",
            "curve_family": "resistivity",
            "canonical_curve_id": "deep_induction_resistivity",
            "unit": "ohm-m",
        },
        {
            "product_id": "curve_ilm",
            "display_curve_id": "ILM",
            "mnemonic": "ILM",
            "display_name": "Medium Induction Resistivity",
            "curve_family": "resistivity",
            "canonical_curve_id": "medium_induction_resistivity",
            "unit": "ohm-m",
        },
        {
            "product_id": "curve_msfl",
            "display_curve_id": "MSFL",
            "mnemonic": "MSFL",
            "display_name": "Micro Spherically Focused Log",
            "curve_family": "resistivity",
            "canonical_curve_id": "micro_resistivity_pad",
            "unit": "ohm-m",
        },
        {
            "product_id": "curve_rhob",
            "display_curve_id": "RHOB",
            "mnemonic": "RHOB",
            "display_name": "Bulk Density",
            "curve_family": "density",
            "unit": "g/cc",
        },
        {
            "product_id": "curve_nphi",
            "display_curve_id": "NPHI",
            "mnemonic": "NPHI",
            "display_name": "Neutron Porosity",
            "curve_family": "neutron_porosity",
            "unit": "v/v",
        },
        {
            "product_id": "curve_dt",
            "display_curve_id": "DT",
            "mnemonic": "DT",
            "display_name": "Sonic Slowness",
            "curve_family": "sonic_slowness",
            "unit": "us/ft",
        },
    ]


def test_evaluate_recommendations_returns_backend_owned_ranked_contract() -> None:
    response = client.post(
        "/api/wlv/wdv/templates/recommendations/evaluate",
        json={"loaded_curve_items": _sample_loaded_curve_items(), "workflow_context": "open_hole"},
    )
    assert response.status_code == 200
    data = response.json()

    assert data["service"] == "wdv_template_recommendation_service"
    assert data["contract_version"] == "wdv_template_recommendation_v1"
    assert data["knowledge_policy"]["approved_only"] is True
    assert data["knowledge_policy"]["candidate_records_used"] is False
    assert data["knowledge_policy"]["frontend_inference_allowed"] is False
    assert data["available_curve_count"] == 7
    assert data["classified_curve_count"] == 7
    assert data["recommendation_count"] >= 20

    recommendations = data["recommendations"]
    triple = next(item for item in recommendations if item["template_key"] == "open_hole_triple_combo")
    assert triple["is_eligible"] is True
    assert triple["missing_required_families"] == []
    assert triple["selected_curve_count"] >= 4
    assert "required_families_covered" in triple["reason_codes"]

    selected_mnemonics = {curve["mnemonic"] for curve in triple["selected_curves"]}
    assert {"GR", "ILD", "RHOB", "NPHI"}.issubset(selected_mnemonics)

    resistivity_track = next(track for track in triple["tracks"] if "resistivity" in track["track_id"])
    resistivity_mnemonics = [curve["mnemonic"] for curve in resistivity_track["selected_curves"]]
    assert set(resistivity_mnemonics) == {"ILD", "ILM", "MSFL"}
    assert len(resistivity_mnemonics) == 3


def test_evaluate_recommendations_reports_unresolved_without_applying_tracks() -> None:
    response = client.post(
        "/api/wlv/wdv/templates/recommendations/evaluate",
        json={
            "loaded_curve_items": [
                {"product_id": "curve_gr", "display_curve_id": "GR", "mnemonic": "GR", "display_name": "Gamma Ray"},
                {"product_id": "curve_unknown", "display_curve_id": "NO_SUCH", "mnemonic": "NO_SUCH", "display_name": "Unknown Curve"},
            ]
        },
    )
    assert response.status_code == 200
    data = response.json()

    assert data["available_curve_count"] == 2
    assert data["unresolved_curve_count"] == 1
    assert data["unresolved_curves"][0]["mnemonic"] == "NO_SUCH"
    assert data["recommendations"]
    assert all("tracks" in item for item in data["recommendations"])


def test_existing_template_detail_route_still_works_after_recommendation_routes() -> None:
    response = client.get("/api/wlv/wdv/templates/open_hole_triple_combo")
    assert response.status_code == 200
    data = response.json()
    assert data["template"]["template_key"] == "open_hole_triple_combo"
    assert data["knowledge_policy"]["candidate_records_used"] is False
