import json
from pathlib import Path

from app.inventory.models import ManagedInventorySnapshot, ManagedProductGroup, ManagedProductGroupItem, ManagedWellRecord
from app.inventory.repository import ManagedWellInventoryRepository
from app.inventory.reclassification_service import ManagedCurveReclassificationService
from app.knowledge.managed_repository import ManagedKRRepository

KR_PATH = Path(__file__).resolve().parents[2] / "data" / "knowledge" / "managed_knowledge.json"


def test_reclassification_is_repository_owned_and_idempotent(tmp_path):
    inventory_path = tmp_path / "managed_wells.json"
    repo = ManagedWellInventoryRepository(inventory_path)
    curves = [
        ("RDEP", "Deep Resistivity", "ohm.m"), ("RMED", "Medium Resistivity", "ohm.m"),
        ("DENC", "Density Correction", "g/cm3"), ("NEU", "Neutron", "v/v"),
        ("AC", "Multifrequency Compressional Slowness", "us/ft"), ("ACS", "Sonic Shear", "us/ft"),
        ("ROP", "Rate of Penetration", "m/h"),
    ]
    items = [ManagedProductGroupItem(
        product_id=f"p-{i}", observed_mnemonic=m, display_name=m, curve_name=m,
        curve_type=d, curve_description=d, curve_unit=u, source_kind="dlis",
        source_id="asset-1", provenance={"frame": "FRAME-1", "channel": m},
    ) for i, (m,d,u) in enumerate(curves)]
    well = ManagedWellRecord(
        managed_well_id="managed-well:volve-15-9-f-1-a", well_id="15/9-F-1 A",
        well_name="15/9-F-1 A", product_groups=[ManagedProductGroup(group_key="other_review_required", group_label="Other", items=items)],
    )
    repo.write_snapshot(ManagedInventorySnapshot(records=[well]))
    before_ids = [(x.product_id, x.source_id, x.provenance) for x in items]
    service = ManagedCurveReclassificationService(
        inventory_repository=repo,
        knowledge_repository=ManagedKRRepository(storage_path=KR_PATH),
    )
    first = service.reclassify_well(well.managed_well_id)
    assert first.changed_count == 7
    after_first_bytes = inventory_path.read_bytes()
    classified = [x for g in repo.get_record(well.managed_well_id).product_groups for x in g.items]
    assert all(not x.review_required and x.qa_flag == "Passed" for x in classified)
    assert [(x.product_id, x.source_id, x.provenance) for x in classified] == before_ids
    second = service.reclassify_well(well.managed_well_id)
    assert second.changed_count == 0
    assert inventory_path.read_bytes() == after_first_bytes
