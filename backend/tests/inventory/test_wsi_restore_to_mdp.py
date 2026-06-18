from pathlib import Path

from app.inventory.models import (
    ManagedProductGroup,
    ManagedProductGroupItem,
    ManagedSourceKind,
    ManagedSourceReference,
    ManagedWellRecord,
    ManagedWmdpState,
)
from app.inventory.repository import ManagedWellInventoryRepository
from app.inventory.service import ManagedWellInventoryService


def test_restore_source_candidate_to_mdp_preserves_msi_identity(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(tmp_path / "managed_wells.json")
    service = ManagedWellInventoryService(repository=repository)

    record = ManagedWellRecord(
        managed_well_id="managed-well-1",
        well_id="well-1",
        well_name="Test Well",
        wmdp_available=False,
        wmdp_state=ManagedWmdpState.REMOVED_FROM_WMDP,
        source_references=[
            ManagedSourceReference(
                source_id="candidate-1",
                source_kind=ManagedSourceKind.LAS,
                display_name="test.las",
            )
        ],
        product_groups=[
            ManagedProductGroup(
                group_key="open_hole",
                group_label="Open Hole",
                items=[
                    ManagedProductGroupItem(
                        product_id="product-1",
                        display_name="GR",
                        curve_name="GR",
                        curve_type="gamma_ray",
                        source_id="candidate-1",
                        source_intake_candidate_id="candidate-1",
                        wmdp_state=ManagedWmdpState.REMOVED_FROM_WMDP,
                    ),
                    ManagedProductGroupItem(
                        product_id="product-sibling",
                        display_name="DT",
                        curve_name="DT",
                        curve_type="sonic",
                        source_id="candidate-2",
                        source_intake_candidate_id="candidate-2",
                        wmdp_state=ManagedWmdpState.REMOVED_FROM_WMDP,
                    ),
                ],
            )
        ],
    )
    repository.upsert_record(record)

    response = service.restore_source_candidates_to_mdp(["candidate-1"])

    assert response.result.restored_managed_well_ids == ["managed-well-1"]
    assert response.result.restored_product_ids == ["product-1"]
    restored = service.get_well("managed-well-1")
    assert restored.wmdp_available is True
    assert restored.wmdp_state == ManagedWmdpState.STAGED_IN_WMDP
    assert restored.product_groups[0].items[0].wmdp_state == ManagedWmdpState.STAGED_IN_WMDP
    assert restored.product_groups[0].items[1].wmdp_state == ManagedWmdpState.REMOVED_FROM_WMDP

    second = service.restore_source_candidates_to_mdp(["candidate-1"])
    assert second.result.restored_product_ids == []
    assert second.result.already_visible_managed_well_ids == ["managed-well-1"]
    assert second.result.already_visible_product_ids == ["product-1"]


def test_restore_reports_missing_candidate_without_creating_records(tmp_path: Path) -> None:
    service = ManagedWellInventoryService(
        repository=ManagedWellInventoryRepository(tmp_path / "managed_wells.json")
    )

    response = service.restore_source_candidates_to_mdp(["missing-candidate"])

    assert response.result.missing_source_candidate_ids == ["missing-candidate"]
    assert service.list_wells() == []
