from __future__ import annotations

from dataclasses import dataclass
import json

import pytest

from app.classification_orchestration.family_registry import (
    CanonicalCurveFamily,
    CanonicalCurveFamilyRegistry,
)
from app.classification_orchestration import live_shadow_observer as observer


@dataclass
class FakeCurveDefinition:
    family: str


class FakeRuntimeResolver:
    def __init__(self, families):
        self._families = families

    def list_runtime_records(self, *, record_type):
        assert record_type == "curve_definition"
        return [FakeCurveDefinition(family=value) for value in self._families]


def test_default_registry_entrypoint_exists_and_preserves_deterministic_vocabulary():
    registry = CanonicalCurveFamilyRegistry.default()
    assert registry.require("Gamma Ray").family_key == "gamma_ray"
    assert registry.require("gamma_ray").display_label == "Gamma Ray"
    assert registry.require("NMR").display_label == "NMR"
    assert registry.require("Drilling").family_key == "drilling"


def test_registry_composes_approved_runtime_kr_families_without_manual_family_patches():
    registry = CanonicalCurveFamilyRegistry.from_authoritative_sources(
        FakeRuntimeResolver(["NMR", "Borehole Geometry", "Temperature", "Drilling", "gamma_ray"])
    )
    assert registry.require("NMR").family_key == "nmr"
    assert registry.require("Borehole Geometry").family_key == "borehole_geometry"
    assert registry.require("borehole_geometry").display_label == "Borehole Geometry"
    assert registry.require("Temperature").family_key == "temperature"
    assert registry.require("Drilling").family_key == "drilling"
    # Existing governed deterministic label wins over a later machine-key form.
    assert registry.require("gamma_ray").display_label == "Gamma Ray"


def test_same_canonical_family_merges_nomenclature_instead_of_overwriting_display_label():
    registry = CanonicalCurveFamilyRegistry()
    registry.register_source_family("Gamma Ray")
    registry.register_source_family("gamma_ray")
    registry.register_source_family("GAMMA RAY")
    assert registry.require("gamma_ray").display_label == "Gamma Ray"
    assert registry.require("GAMMA RAY").family_key == "gamma_ray"


def test_alias_collision_across_different_canonical_keys_is_rejected():
    registry = CanonicalCurveFamilyRegistry()
    registry.register(CanonicalCurveFamily("family_a", "Family A", aliases=("shared",)))
    with pytest.raises(ValueError, match="alias collision"):
        registry.register(CanonicalCurveFamily("family_b", "Family B", aliases=("shared",)))


def test_runtime_decision_never_collapses_approved_runtime_family_to_unclassified():
    class RuntimeResult:
        family = "Borehole Geometry"
        confidence = 0.95
        requires_review = False
        resolved = True
        resolution_source = "exact_kr"
        def as_dict(self): return {"family": self.family}

    request = observer.CurveClassificationRequest(source_mnemonic="ABDC01")
    decision = observer.runtime_decision(request, RuntimeResult(), CanonicalCurveFamilyRegistry.default())
    assert decision.curve_family_key == "borehole_geometry"
    assert decision.curve_family_label == "Borehole Geometry"
    assert decision.review_required is False


def test_live_shadow_emit_writes_observable_jsonl(monkeypatch, tmp_path):
    target = tmp_path / "shadow.jsonl"
    monkeypatch.setenv("WLV_CLASSIFICATION_SHADOW_REPORT_PATH", str(target))
    request = observer.CurveClassificationRequest(source_mnemonic="GR")

    class RuntimeResult:
        family = "Gamma Ray"
        confidence = 1.0
        requires_review = False
        resolved = True
        resolution_source = "standard_mnemonic"
        def as_dict(self): return {"family": self.family}

    decision = observer.runtime_decision(request, RuntimeResult(), CanonicalCurveFamilyRegistry.default())
    observer._emit("test_entrypoint", decision)
    payload = json.loads(target.read_text(encoding="utf-8").strip())
    assert payload["observer_version"] == "classification-live-shadow-v2"
    assert payload["authoritative_unchanged"] is True
    assert payload["authoritative"]["curve_family_key"] == "gamma_ray"
