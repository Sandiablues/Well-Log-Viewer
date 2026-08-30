from pathlib import Path
import json

from app.knowledge.managed_repository import ManagedKRRepository
from app.knowledge.runtime_resolver import ApprovedKnowledgeRuntimeResolver
from app.knowledge.runtime_classification_service import (
    CurveClassificationInput,
    RuntimeCurveClassificationService,
)

EXPECTED = {
    "GRBM": "gamma_ray",
    "GRDM": "gamma_ray",
    "HCNL": "neutron_porosity",
    "HDEN": "bulk_density",
    "HRD": "deep_resistivity",
    "HRM": "medium_resistivity",
    "HRS": "shallow_resistivity",
    "RDEP": "deep_resistivity",
    "RMED": "medium_resistivity",
    "RSHAL": "shallow_resistivity",
    "HRD1": "density_auxiliary_count_rate",
    "HRD2": "density_auxiliary_count_rate",
}

def test_visible_managed_mnemonics_drive_runtime_classification(tmp_path: Path) -> None:
    source = Path("data/knowledge/managed_knowledge.json")
    target = tmp_path / "managed_knowledge.json"
    target.write_text(source.read_text())

    repo = ManagedKRRepository(storage_path=target)
    resolver = ApprovedKnowledgeRuntimeResolver(repo)
    service = RuntimeCurveClassificationService(resolver)

    managed = {
        getattr(record, "mnemonic", ""): record
        for record in repo.list_records("standard_mnemonic")
    }
    for mnemonic, canonical in EXPECTED.items():
        assert mnemonic in managed
        assert managed[mnemonic].canonical_curve_id == canonical
        result = service.classify_curve(CurveClassificationInput(source_mnemonic=mnemonic))
        assert result.resolved
        assert result.canonical_curve_id == canonical
        assert result.resolution_source == "runtime_standard_mnemonic"
