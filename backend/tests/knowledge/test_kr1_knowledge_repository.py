"""Tests for the WLV Knowledge Repository KR-1 implementation.

Covers:
- KnowledgeRepository data contracts
- All five /api/wlv/knowledge/* endpoint shapes
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.models import KR_VERSION

client = TestClient(app)


# ---------------------------------------------------------------------------
# Repository unit tests
# ---------------------------------------------------------------------------

@pytest.fixture
def kr() -> KnowledgeRepository:
    return KnowledgeRepository()


def test_kr_health_fields(kr: KnowledgeRepository) -> None:
    h = kr.get_health()
    assert h.service == "wlv_knowledge_repository"
    assert h.status == "ok"
    assert h.mode == "read_only"
    assert h.version == KR_VERSION
    assert h.product_group_count == 8
    assert h.curve_definition_count >= 10
    assert h.display_rule_count >= 10
    assert h.template_count == 0


def test_kr_product_groups_count(kr: KnowledgeRepository) -> None:
    resp = kr.get_product_groups()
    assert resp.version == KR_VERSION
    assert len(resp.groups) == 8


def test_kr_product_groups_keys(kr: KnowledgeRepository) -> None:
    resp = kr.get_product_groups()
    keys = {g.key for g in resp.groups}
    expected = {
        "open_hole_logs",
        "cased_hole_logs",
        "rasters_images",
        "lithology_core_markers",
        "pressure_production_fluid_data",
        "completion_integrity_data",
        "supporting_documents",
        "other_review_required",
    }
    assert keys == expected


def test_kr_product_groups_ordered(kr: KnowledgeRepository) -> None:
    resp = kr.get_product_groups()
    orders = [g.order for g in resp.groups]
    assert orders == sorted(orders)


def test_kr_open_hole_has_subgroups(kr: KnowledgeRepository) -> None:
    resp = kr.get_product_groups()
    open_hole = next(g for g in resp.groups if g.key == "open_hole_logs")
    assert len(open_hole.subgroups) >= 10
    subgroup_keys = {s.key for s in open_hole.subgroups}
    required = {
        "gamma_ray",
        "resistivity",
        "sonic_acoustic",
        "density_neutron_porosity",
        "sp_electrochemical",
        "nmr",
        "borehole_geometry_imaging",
        "dip_directional",
        "formation_pressure_sampling",
        "petrophysical_interpretation",
        "other_open_hole_review",
    }
    assert required.issubset(subgroup_keys)


def test_kr_open_hole_subgroups_ordered(kr: KnowledgeRepository) -> None:
    resp = kr.get_product_groups()
    open_hole = next(g for g in resp.groups if g.key == "open_hole_logs")
    orders = [s.order for s in open_hole.subgroups]
    assert orders == sorted(orders)


def test_kr_cased_hole_has_subgroups(kr: KnowledgeRepository) -> None:
    resp = kr.get_product_groups()
    cased = next(g for g in resp.groups if g.key == "cased_hole_logs")
    assert len(cased.subgroups) >= 4


def test_kr_curve_definitions_count(kr: KnowledgeRepository) -> None:
    resp = kr.get_curve_definitions()
    assert resp.version == KR_VERSION
    assert len(resp.curve_definitions) >= 10


def test_kr_curve_definitions_have_required_fields(kr: KnowledgeRepository) -> None:
    resp = kr.get_curve_definitions()
    for defn in resp.curve_definitions:
        assert defn.canonical_curve_id
        assert defn.display_name
        assert defn.family
        assert defn.product_group == "open_hole_logs"
        assert isinstance(defn.aliases, list)


def test_kr_gamma_ray_definition(kr: KnowledgeRepository) -> None:
    resp = kr.get_curve_definitions()
    gr = next((d for d in resp.curve_definitions if d.canonical_curve_id == "gamma_ray"), None)
    assert gr is not None
    assert gr.display_name == "Gamma Ray"
    assert gr.product_subgroup == "gamma_ray"
    assert "GR" in gr.standard_mnemonics
    assert "GR" in gr.all_known_mnemonics
    assert "GR" not in gr.aliases


def test_kr_display_rules_count(kr: KnowledgeRepository) -> None:
    resp = kr.get_display_rules()
    assert resp.version == KR_VERSION
    assert len(resp.display_rules) >= 10


def test_kr_display_rules_have_required_fields(kr: KnowledgeRepository) -> None:
    resp = kr.get_display_rules()
    for rule in resp.display_rules:
        assert rule.canonical_curve_id
        assert rule.preferred_track_family
        assert rule.scale_type in {"linear", "log"}
        assert isinstance(rule.display_min, float)
        assert isinstance(rule.display_max, float)


def test_kr_gamma_ray_display_rule(kr: KnowledgeRepository) -> None:
    resp = kr.get_display_rules()
    gr = next((r for r in resp.display_rules if r.canonical_curve_id == "gamma_ray"), None)
    assert gr is not None
    assert gr.scale_type == "linear"
    assert gr.preferred_track_family == "gamma_ray_sp"


def test_kr_resistivity_display_rule_is_log(kr: KnowledgeRepository) -> None:
    resp = kr.get_display_rules()
    rt = next((r for r in resp.display_rules if r.canonical_curve_id == "deep_resistivity"), None)
    assert rt is not None
    assert rt.scale_type == "log"


def test_kr_templates_empty(kr: KnowledgeRepository) -> None:
    resp = kr.get_templates()
    assert resp.version == KR_VERSION
    assert resp.templates == []


# ---------------------------------------------------------------------------
# HTTP endpoint tests
# ---------------------------------------------------------------------------

def test_endpoint_health() -> None:
    resp = client.get("/api/wlv/knowledge/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "wlv_knowledge_repository"
    assert data["status"] == "ok"
    assert data["mode"] == "read_only"
    assert data["version"] == KR_VERSION
    assert data["product_group_count"] == 8
    assert data["template_count"] == 0


def test_endpoint_product_groups() -> None:
    resp = client.get("/api/wlv/knowledge/product-groups")
    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == KR_VERSION
    groups = data["groups"]
    assert len(groups) == 8
    open_hole = next(g for g in groups if g["key"] == "open_hole_logs")
    assert open_hole["label"] == "Open-hole Logs"
    assert len(open_hole["subgroups"]) >= 10


def test_endpoint_product_groups_subgroup_structure() -> None:
    resp = client.get("/api/wlv/knowledge/product-groups")
    data = resp.json()
    open_hole = next(g for g in data["groups"] if g["key"] == "open_hole_logs")
    gamma_ray = next(s for s in open_hole["subgroups"] if s["key"] == "gamma_ray")
    assert gamma_ray["label"] == "Gamma Ray"
    assert isinstance(gamma_ray["order"], int)


def test_endpoint_curve_definitions() -> None:
    resp = client.get("/api/wlv/knowledge/curve-definitions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == KR_VERSION
    assert len(data["curve_definitions"]) >= 10
    gr = next((d for d in data["curve_definitions"] if d["canonical_curve_id"] == "gamma_ray"), None)
    assert gr is not None
    assert "GR" in gr["standard_mnemonics"]
    assert "GR" in gr["all_known_mnemonics"]
    assert "GR" not in gr["aliases"]


def test_endpoint_display_rules() -> None:
    resp = client.get("/api/wlv/knowledge/display-rules")
    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == KR_VERSION
    assert len(data["display_rules"]) >= 10
    gr = next((r for r in data["display_rules"] if r["canonical_curve_id"] == "gamma_ray"), None)
    assert gr is not None
    assert gr["scale_type"] == "linear"


def test_endpoint_templates() -> None:
    resp = client.get("/api/wlv/knowledge/templates")
    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == KR_VERSION
    assert data["templates"] == []


def test_endpoint_product_groups_all_groups_have_labels() -> None:
    resp = client.get("/api/wlv/knowledge/product-groups")
    data = resp.json()
    for group in data["groups"]:
        assert group["label"], f"Group {group['key']} missing label"


def test_endpoint_product_groups_ordering_is_stable() -> None:
    resp1 = client.get("/api/wlv/knowledge/product-groups")
    resp2 = client.get("/api/wlv/knowledge/product-groups")
    assert resp1.json()["groups"] == resp2.json()["groups"]
