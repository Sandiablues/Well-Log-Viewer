from pathlib import Path

from app.identity import new_uuid7_str
from app.inventory.canonical_identity_resolver import CanonicalInventoryIdentityResolver
from app.inventory.models import (
    ManagedProductGroup, ManagedProductGroupItem, ManagedSourceKind,
    ManagedSourceReference, ManagedWellRecord,
)
from app.inventory.repository import ManagedWellInventoryRepository
from app.inventory.service import ManagedWellInventoryService
from app.wdv_session.canonical_command_service import CanonicalWdvCommandService
from app.wdv_session.canonical_service import CanonicalWdvSessionService
from app.wdv_session.las_reconstruction_models import LoadCompleteLasCommand
from app.wdv_session.las_reconstruction_service import LasReconstructionService


def _build(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("WLV_UNIFIED_MULTIWELL_SESSION", "0")
    repo = ManagedWellInventoryRepository(tmp_path / "inventory.json")
    well_uid = new_uuid7_str()
    source_uid = new_uuid7_str()
    source_id = "source-las-1"
    source = ManagedSourceReference(
        source_id=source_id,
        managed_source_uid=source_uid,
        source_kind=ManagedSourceKind.LAS,
        display_name="field.las",
        file_name="field.las",
        checksum="abc123",
        metadata={"las_asset_id": "las-asset:sha256:abc123"},
    )
    products = []
    for index, mnemonic in enumerate(("GR", "RHOB", "NPHI")):
        products.append(ManagedProductGroupItem(
            product_id=f"curve-{index}",
            managed_product_uid=new_uuid7_str(),
            managed_curve_uid=new_uuid7_str(),
            managed_source_uid=source_uid,
            well_uid=well_uid,
            source_uid=source_uid,
            display_name=mnemonic,
            curve_name=mnemonic,
            curve_type=mnemonic,
            curve_unit="API" if mnemonic == "GR" else "g/cc",
            curve_family="Gamma Ray" if mnemonic == "GR" else "Density",
            review_required=(mnemonic == "NPHI"),
            selectable=True,
            source_kind="las",
            source_id=source_id,
            provenance={"source_curve_index": index, "source_curve_position": index + 1},
        ))
    record = ManagedWellRecord(
        managed_well_id="managed-well:test",
        managed_well_uid=well_uid,
        well_id="test",
        well_name="Test Well",
        source_references=[source],
        product_groups=[ManagedProductGroup(group_key="open_hole_logs", group_label="Open Hole", items=products)],
    )
    repo.upsert_record(record)
    resolver = CanonicalInventoryIdentityResolver(repo)
    sessions = CanonicalWdvSessionService(
        tmp_path / "sessions.json",
        policy_revision_fn=lambda: "policy-test",
    )
    commands = CanonicalWdvCommandService(
        session_service=sessions,
        resolver=resolver,
        policy_revision_fn=lambda: "policy-test",
        display_policy_resolver=lambda _resolved: {
            "scale_min": 0.0,
            "scale_max": 100.0,
            "scale_type": "linear",
            "scale_direction": "normal",
            "display_policy_source": "curve",
            "display_review_required": False,
        },
    )
    inventory = ManagedWellInventoryService(repository=repo)
    service = LasReconstructionService(repo, inventory, commands)
    return service, repo, well_uid, source_id, products


def test_plan_is_file_scoped_and_source_ordered(tmp_path, monkeypatch):
    service, _repo, well_uid, source_id, _products = _build(tmp_path, monkeypatch)
    plan = service.build_plan(well_uid, source_id)
    assert plan.original_filename == "field.las"
    assert plan.asset_id == "las-asset:sha256:abc123"
    assert [curve.mnemonic for curve in plan.curves] == ["GR", "RHOB", "NPHI"]
    assert plan.eligible_curve_count == 2
    assert plan.review_curve_count == 1


def test_inventory_only_loads_eligible_curves_without_tracks(tmp_path, monkeypatch):
    service, repo, well_uid, source_id, products = _build(tmp_path, monkeypatch)
    response = service.load_complete_las(well_uid, LoadCompleteLasCommand(
        expected_revision=0,
        source_id=source_id,
        placement="inventory_only",
    ))
    assert response.session.tracks == ()
    assert response.loaded_product_ids == (products[0].product_id, products[1].product_id)
    record = repo.get_record("managed-well:test")
    loaded = [item.product_id for group in record.product_groups for item in group.items if item.wdv_state.value == "loaded_to_wdv"]
    assert loaded == [products[0].product_id, products[1].product_id]


def test_append_tracks_is_revision_guarded_and_skips_review_curves(tmp_path, monkeypatch):
    service, _repo, well_uid, source_id, products = _build(tmp_path, monkeypatch)
    response = service.load_complete_las(well_uid, LoadCompleteLasCommand(
        expected_revision=0,
        source_id=source_id,
        placement="append_tracks",
        track_width_px=175,
    ))
    assert response.session.revision == 1
    assert [track.track_name for track in response.session.tracks] == ["GR", "RHOB"]
    assert all(track.width_px == 175 for track in response.session.tracks)
    assert response.added_managed_curve_uids == (
        str(products[0].managed_curve_uid), str(products[1].managed_curve_uid)
    )


def test_list_sources_uses_managed_source_records_not_viewer_curve_labels(tmp_path, monkeypatch):
    service, _repo, well_uid, source_id, _products = _build(tmp_path, monkeypatch)
    result = service.list_sources(well_uid)
    assert result.managed_well_uid == well_uid
    assert len(result.sources) == 1
    source = result.sources[0]
    assert source.source_id == source_id
    assert source.label == "field.las"
    assert source.original_filename == "field.las"
    assert source.curve_count == 3
    assert source.asset_available is True
    assert source.source_fingerprint == "abc123"


def test_list_log_images_is_separate_from_las_inventory(tmp_path, monkeypatch):
    service, repo, well_uid, _source_id, _products = _build(tmp_path, monkeypatch)
    record = repo.get_record("managed-well:test")
    image_source = ManagedSourceReference(
        source_id="source-image-1",
        managed_source_uid=new_uuid7_str(),
        source_kind=ManagedSourceKind.RASTER_LOG,
        display_name="field-print.tif",
        file_name="field-print.tif",
        file_format="TIFF",
        checksum="image123",
    )
    repo.upsert_record(record.model_copy(update={
        "source_references": [*record.source_references, image_source],
    }))
    las_sources = service.list_sources(well_uid)
    image_sources = service.list_log_images(well_uid)
    assert [source.source_id for source in las_sources.sources] == ["source-las-1"]
    assert [source.source_id for source in image_sources.sources] == ["source-image-1"]
    assert image_sources.sources[0].file_format == "TIFF"


def test_append_tracks_does_not_reload_already_loaded_inventory(tmp_path, monkeypatch):
    service, _repo, well_uid, source_id, _products = _build(tmp_path, monkeypatch)

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("append_tracks must not mutate WDV inventory")

    monkeypatch.setattr(service.inventory_service, "load_managed_well_to_wdv", fail_if_called)
    response = service.load_complete_las(well_uid, LoadCompleteLasCommand(
        expected_revision=0,
        source_id=source_id,
        placement="append_tracks",
    ))
    assert response.session.revision == 1
    assert [track.track_name for track in response.session.tracks] == ["GR", "RHOB"]
    assert response.loaded_product_ids == ()


def test_multiple_las_sources_keep_exact_file_scoped_curve_counts(tmp_path, monkeypatch):
    service, repo, well_uid, source_id, products = _build(tmp_path, monkeypatch)
    record = repo.get_record("managed-well:test")
    second_source_id = "source-las-2"
    second_source_uid = new_uuid7_str()
    second_source = ManagedSourceReference(
        source_id=second_source_id,
        managed_source_uid=second_source_uid,
        source_kind=ManagedSourceKind.LAS,
        display_name="sonic.las",
        file_name="sonic.las",
        checksum="def456",
        metadata={"las_asset_id": "las-asset:sha256:def456"},
    )
    second_curve = ManagedProductGroupItem(
        product_id="curve-sonic-0",
        managed_product_uid=new_uuid7_str(),
        managed_curve_uid=new_uuid7_str(),
        managed_source_uid=second_source_uid,
        well_uid=well_uid,
        source_uid=second_source_uid,
        display_name="DTCO",
        curve_name="DTCO",
        curve_type="DTCO",
        curve_unit="US/F",
        curve_family="Sonic",
        review_required=False,
        selectable=True,
        source_kind="las",
        source_id=second_source_id,
        provenance={"source_curve_index": 0, "source_curve_position": 1},
    )
    groups = list(record.product_groups)
    groups[0] = groups[0].model_copy(update={"items": [*groups[0].items, second_curve]})
    repo.upsert_record(record.model_copy(update={
        "source_references": [*record.source_references, second_source],
        "product_groups": groups,
    }))

    listed = service.list_sources(well_uid)
    counts = {item.source_id: item.curve_count for item in listed.sources}
    assert counts == {source_id: len(products), second_source_id: 1}
    assert [curve.mnemonic for curve in service.build_plan(well_uid, second_source_id).curves] == ["DTCO"]


def test_append_tracks_response_does_not_reference_inventory_load_result(tmp_path, monkeypatch):
    service, _repo, well_uid, source_id, products = _build(tmp_path, monkeypatch)
    response = service.load_complete_las(well_uid, LoadCompleteLasCommand(
        expected_revision=0,
        source_id=source_id,
        placement="append_tracks",
    ))
    assert response.loaded_product_ids == ()
    assert response.added_managed_curve_uids == (
        str(products[0].managed_curve_uid), str(products[1].managed_curve_uid)
    )
