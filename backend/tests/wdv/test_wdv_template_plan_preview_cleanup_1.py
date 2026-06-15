"""WDV-TEMPLATE-PLAN-PREVIEW-CLEANUP-1 tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _duplicated_loaded_items() -> list[dict[str, object]]:
    return [
        {"item_id": "gr_a", "mnemonic": "GR", "curveFamily": "gamma_ray", "unit": "API"},
        {"item_id": "gr_b", "mnemonic": "GR", "curveFamily": "gamma_ray", "unit": "API"},
        {"item_id": "ild_a", "mnemonic": "ILD", "curveFamily": "resistivity", "canonical_curve_id": "deep_induction_resistivity", "unit": "ohm.m"},
        {"item_id": "ild_b", "mnemonic": "ILD", "curveFamily": "resistivity", "canonical_curve_id": "deep_induction_resistivity", "unit": "ohm.m"},
        {"item_id": "ilm_a", "mnemonic": "ILM", "curveFamily": "resistivity", "canonical_curve_id": "medium_induction_resistivity", "unit": "ohm.m"},
        {"item_id": "ilm_b", "mnemonic": "ILM", "curveFamily": "resistivity", "canonical_curve_id": "medium_induction_resistivity", "unit": "ohm.m"},
        {"item_id": "rhob_a", "mnemonic": "RHOB", "curveFamily": "density", "unit": "g/cc"},
        {"item_id": "rhob_b", "mnemonic": "RHOB", "curveFamily": "density", "unit": "g/cc"},
        {"item_id": "nphi_a", "mnemonic": "NPHI", "curveFamily": "neutron_porosity", "unit": "v/v"},
        {"item_id": "nphi_b", "mnemonic": "NPHI", "curveFamily": "neutron_porosity", "unit": "v/v"},
    ]


def test_application_plan_dedupes_representative_curve_selection() -> None:
    response = client.post(
        "/api/wlv/wdv/templates/application-plans/build",
        json={
            "templateKey": "open_hole_triple_combo",
            "workflowContext": "open_hole",
            "loaded_items": _duplicated_loaded_items(),
        },
    )
    assert response.status_code == 200
    plan = response.json()["plan"]

    selected = plan["selected_curves"]
    selected_keys = [
        (
            curve.get("canonical_curve_id") or "",
            curve.get("mnemonic") or "",
            curve.get("curve_family") or curve.get("raw_curve_family") or "",
            curve.get("depth_role") or "",
            curve.get("unit") or "",
        )
        for curve in selected
    ]

    assert len(selected_keys) == len(set(selected_keys))
    assert plan["selected_curve_count"] == len(selected)
    assert {curve["mnemonic"] for curve in selected}.issuperset({"GR", "ILD", "RHOB", "NPHI"})


def test_recommendation_track_selection_does_not_repeat_same_representative() -> None:
    response = client.post(
        "/api/wlv/wdv/templates/recommendations/evaluate",
        json={"loaded_items": _duplicated_loaded_items(), "workflowContext": "open_hole"},
    )
    assert response.status_code == 200
    triple = next(
        item for item in response.json()["recommendations"]
        if item["template_key"] == "open_hole_triple_combo"
    )
    for track in triple["tracks"]:
        keys = [
            (
                curve.get("canonical_curve_id") or "",
                curve.get("mnemonic") or "",
                curve.get("curve_family") or curve.get("raw_curve_family") or "",
                curve.get("depth_role") or "",
                curve.get("unit") or "",
            )
            for curve in track["selected_curves"]
        ]
        assert len(keys) == len(set(keys))


def _visibly_duplicated_loaded_items() -> list[dict[str, object]]:
    return [
        {
            "item_id": "af10_primary",
            "mnemonic": "AF10",
            "curveFamily": "resistivity",
            "canonical_curve_id": "deep_resistivity",
            "depth_role": "deep",
            "unit": "ohm.m",
        },
        {
            "item_id": "af10_duplicate",
            "mnemonic": "AF10",
            "curveFamily": "resistivity",
            "canonical_curve_id": "shallow_resistivity",
            "depth_role": "shallow",
            "unit": "ohm.m",
        },
        {
            "item_id": "af30_primary",
            "mnemonic": "AF30",
            "curveFamily": "resistivity",
            "canonical_curve_id": "medium_resistivity",
            "depth_role": "medium",
            "unit": "ohm.m",
        },
        {
            "item_id": "af30_duplicate",
            "mnemonic": "AF30",
            "curveFamily": "resistivity",
            "canonical_curve_id": "medium_resistivity_alt",
            "depth_role": "medium",
            "unit": "ohm.m",
        },
        {"item_id": "ecgr_a", "mnemonic": "ECGR", "curveFamily": "gamma_ray", "unit": "API"},
        {"item_id": "ecgr_b", "mnemonic": "ECGR", "curveFamily": "gamma_ray", "unit": "API"},
        {"item_id": "nphi_a", "mnemonic": "NPHI", "curveFamily": "neutron_porosity", "unit": "v/v"},
        {"item_id": "nphi_b", "mnemonic": "NPHI", "curveFamily": "neutron_porosity", "unit": "v/v"},
    ]


def _visible_key(curve: dict[str, object]) -> tuple[str, str]:
    name = curve.get("mnemonic") or curve.get("display_name") or curve.get("curve_id") or curve.get("product_id") or ""
    family = curve.get("curve_family") or curve.get("raw_curve_family") or ""
    return (str(name).strip().lower(), str(family).strip().lower())


def test_application_plan_dedupes_selected_curves_by_visible_modal_identity() -> None:
    response = client.post(
        "/api/wlv/wdv/templates/application-plans/build",
        json={
            "templateKey": "open_hole_triple_combo",
            "workflowContext": "open_hole",
            "loaded_items": _visibly_duplicated_loaded_items(),
        },
    )
    assert response.status_code == 200
    plan = response.json()["plan"]

    visible_keys = [_visible_key(curve) for curve in plan["selected_curves"]]
    assert len(visible_keys) == len(set(visible_keys))
    assert plan["selected_curve_count"] == len(plan["selected_curves"])
    assert ("af10", "resistivity") in visible_keys
    assert ("af30", "resistivity") in visible_keys
    assert visible_keys.count(("af10", "resistivity")) == 1
    assert visible_keys.count(("af30", "resistivity")) == 1


def test_recommendations_dedupe_track_and_aggregate_selected_curves_by_visible_identity() -> None:
    response = client.post(
        "/api/wlv/wdv/templates/recommendations/evaluate",
        json={"loaded_items": _visibly_duplicated_loaded_items(), "workflowContext": "open_hole"},
    )
    assert response.status_code == 200
    triple = next(
        item for item in response.json()["recommendations"]
        if item["template_key"] == "open_hole_triple_combo"
    )

    aggregate_keys = [_visible_key(curve) for curve in triple["selected_curves"]]
    assert len(aggregate_keys) == len(set(aggregate_keys))

    for track in triple["tracks"]:
        track_keys = [_visible_key(curve) for curve in track["selected_curves"]]
        assert len(track_keys) == len(set(track_keys))

