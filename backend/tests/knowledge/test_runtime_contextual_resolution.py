from pathlib import Path

from app.knowledge.managed_repository import ManagedKRRepository
from app.knowledge.runtime_classification_service import CurveClassificationInput, RuntimeCurveClassificationService
from app.knowledge.runtime_resolver import ApprovedKnowledgeRuntimeResolver

KR_PATH = Path(__file__).resolve().parents[2] / "data" / "knowledge" / "managed_knowledge.json"


def classifier():
    # Explicit storage is intentional: the knowledge-suite autouse fixture
    # isolates the default repository. These integration tests validate the
    # captured approved KR, not a fresh seed-only temporary repository.
    return RuntimeCurveClassificationService(
        ApprovedKnowledgeRuntimeResolver(ManagedKRRepository(storage_path=KR_PATH))
    )


def inputs():
    return [
        CurveClassificationInput(source_mnemonic="RDEP", description="Deep Resistivity", unit="ohm.m"),
        CurveClassificationInput(source_mnemonic="RMED", description="Medium Resistivity", unit="ohm.m"),
        CurveClassificationInput(source_mnemonic="DENC", description="Density Correction", unit="g/cm3"),
        CurveClassificationInput(source_mnemonic="NEU", description="Neutron", unit="v/v"),
        CurveClassificationInput(source_mnemonic="AC", description="Multifrequency Compressional Slowness", unit="us/ft"),
        CurveClassificationInput(source_mnemonic="ACS", description="Sonic Shear", unit="us/ft"),
        CurveClassificationInput(source_mnemonic="ROP", description="Rate of Penetration", unit="m/h"),
    ]


def test_contextual_resolution_common_curves():
    results = classifier().classify_curves(inputs()).classifications
    assert all(r.resolved and not r.requires_review for r in results)
    assert [r.family for r in results] == [
        "Resistivity", "Resistivity", "Density Correction",
        "Neutron Porosity", "Sonic", "Sonic", "Drilling",
    ]


def test_ambiguous_ac_remains_review():
    result = classifier().classify_curve(CurveClassificationInput(source_mnemonic="AC"))
    assert not result.resolved and result.requires_review
    assert result.warnings == ["No approved runtime knowledge match found"]


def test_contextual_results_are_deterministic_across_instances_batch_and_single():
    expected = [classifier().classify_curve(item).as_dict() for item in inputs()]
    repeated = [classifier().classify_curve(item).as_dict() for item in inputs()]
    batch = [item.as_dict() for item in classifier().classify_curves(inputs()).classifications]
    assert repeated == expected
    assert batch == expected


def test_contextual_resolution_does_not_fabricate_canonical_identity():
    by_mnemonic = {r.source_mnemonic: r for r in classifier().classify_curves(inputs()).classifications}
    assert by_mnemonic["RDEP"].canonical_curve_id is None
    assert by_mnemonic["DENC"].canonical_curve_id is None
    assert by_mnemonic["NEU"].canonical_curve_id
    assert by_mnemonic["AC"].canonical_curve_id is None
    assert by_mnemonic["ACS"].canonical_curve_id is None
    assert by_mnemonic["ROP"].canonical_curve_id is None
    # RMED has one exact approved display-name match and may receive that ID.
    assert by_mnemonic["RMED"].canonical_curve_id


def test_rop_uses_named_governed_policy_not_canonical_kr_identity():
    result = classifier().classify_curve(inputs()[-1])
    assert result.resolution_source == "runtime_contextual_consensus"
    assert result.canonical_curve_id is None
    assert any("governed backend measurement policy" in warning for warning in result.warnings)
    assert any("backend_policy:measurement:rate_of_penetration:v1" in warning for warning in result.warnings)
