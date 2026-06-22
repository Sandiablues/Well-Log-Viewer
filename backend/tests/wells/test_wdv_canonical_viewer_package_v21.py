from pathlib import Path
from types import SimpleNamespace

from app.identity import new_uuid7_str
from app.inventory.models import (
    ManagedProductGroup,
    ManagedProductGroupItem,
    ManagedSourceKind,
    ManagedSourceReference,
    ManagedWellRecord,
)
from app.wdv_session.canonical_service import CanonicalWdvSessionService
from app.wells.canonical_viewer_package_service import CanonicalViewerPackageService


class FakeResolver:
    def __init__(self, well: ManagedWellRecord) -> None:
        self.well = well

    def resolve_well(self, managed_well_uid: str) -> ManagedWellRecord:
        assert managed_well_uid == str(self.well.managed_well_uid)
        return self.well


def test_viewer_package_uses_only_canonical_curve_identity(tmp_path: Path) -> None:
    well_uid = new_uuid7_str()
    wellbore_uid = new_uuid7_str()
    source_uid = new_uuid7_str()
    product_uid = new_uuid7_str()
    curve_uid = new_uuid7_str()

    source = ManagedSourceReference(
        source_id="legacy-source",
        managed_source_uid=source_uid,
        source_kind=ManagedSourceKind.LAS,
        display_name="Well LAS",
    )
    product = ManagedProductGroupItem(
        product_id="legacy-product",
        managed_product_uid=product_uid,
        managed_curve_uid=curve_uid,
        managed_wellbore_uid=wellbore_uid,
        managed_source_uid=source_uid,
        display_name="Gamma Ray",
        curve_name="GR",
        curve_type="curve",
        curve_unit="API",
        curve_family="gamma_ray",
        selectable=True,
    )
    well = ManagedWellRecord(
        managed_well_id="legacy-well",
        managed_well_uid=well_uid,
        managed_wellbore_uid=wellbore_uid,
        well_id="legacy-well",
        well_name="Test Well",
        depth_unit="ft",
        top_depth=1000.0,
        base_depth=2000.0,
        source_references=[source],
        product_groups=[
            ManagedProductGroup(
                group_key="open_hole",
                group_label="Open Hole",
                items=[product],
            )
        ],
    )

    service = CanonicalViewerPackageService(
        resolver=FakeResolver(well),
        session_service=CanonicalWdvSessionService(tmp_path / "sessions.json"),
    )

    package = service.generate(well_uid)
    curve = package.curves[0]

    assert package.managed_well_uid == well_uid
    assert curve.managed_curve_uid == curve_uid
    assert curve.managed_product_uid == product_uid
    assert curve.managed_source_uid == source_uid
    assert curve.observed_mnemonic == "GR"
    assert curve.display_policy.curve_class == "gamma"
    assert curve.display_policy.lattice == "linear"
    assert curve.display_policy.display_min == 0.0
    assert curve.display_policy.display_max == 150.0
    assert curve.display_policy.source == "managed_knowledge_family_default"
    assert package.session.session_uid == service.generate(well_uid).session.session_uid

    payload = package.model_dump()
    assert "curve_id" not in payload["curves"][0]
    assert "curve_uid" not in payload["curves"][0]
    assert "product_id" not in payload["curves"][0]
