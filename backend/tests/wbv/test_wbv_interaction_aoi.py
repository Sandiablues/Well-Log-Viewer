from pathlib import Path
from types import SimpleNamespace
import json
import pytest
from app.inventory.repository import ManagedWellInventoryRepository
from app.inventory.wdv_workspace import WdvWorkspaceService
from app.wbv.interaction import WbvInteractionService, WbvPickedPoint
from app.inventory.models import ManagedInventorySnapshot, ManagedWellRecord, ManagedSourceKind, ManagedWdvState, ManagedProductGroup, ManagedProductGroupItem


def seeded(tmp_path: Path):
    store = tmp_path / "managed.json"
    repo = ManagedWellInventoryRepository(store)
    record = ManagedWellRecord(
        managed_well_id="mw-1", managed_well_uid="01900000-0000-7000-8000-000000000002", well_id="w-1", well_name="Well 1",
        metadata={"managed_trajectories": [{"trajectory_id":"t-1","trajectory_revision_uid":"01900000-0000-7000-8000-000000000001","is_active":True,"trajectory_package":{"render_points":[{"md":100.0},{"md":200.0}]}}]},
        product_groups=[ManagedProductGroup(group_key="g", group_label="G", items=[ManagedProductGroupItem(product_id="p-1", source_kind=ManagedSourceKind.LAS, display_name="P", curve_name="GR", curve_type="gamma_ray", wdv_state=ManagedWdvState.LOADED_TO_WDV)])],
    )
    repo.write_snapshot(ManagedInventorySnapshot(records=[record]))
    WdvWorkspaceService(repo).reconcile(preferred_active="mw-1")
    return repo


def test_modes_are_backend_mutually_exclusive(tmp_path):
    service = WbvInteractionService(seeded(tmp_path))
    state = service.set_mode("mw-1", "point")
    assert state.selected_point_visible and not state.interval_visible
    state = service.set_mode("mw-1", "interval")
    assert state.interval_visible and not state.selected_point_visible


def test_interval_persists_and_sends_aoi(tmp_path):
    repo = seeded(tmp_path); service = WbvInteractionService(repo)
    service.set_mode("mw-1", "interval")
    service.pick_interval("mw-1", WbvPickedPoint(md=180.0))
    state = service.pick_interval("mw-1", WbvPickedPoint(md=120.0))
    assert state.saved_interval.top_md == 120.0
    assert state.saved_interval.base_md == 180.0
    result = service.send_interval_to_wdv("mw-1")
    assert result.command_status == "applied"
    assert WdvWorkspaceService(repo)._read_store()["active_aoi"]["interval_id"] == state.saved_interval.interval_id


def test_click_rejected_when_mode_disabled(tmp_path):
    service = WbvInteractionService(seeded(tmp_path))
    with pytest.raises(ValueError):
        service.select_point("mw-1", WbvPickedPoint(md=150.0))


def test_selection_validates_against_same_viewer_package_rendered_by_wbv(tmp_path):
    repo = seeded(tmp_path)
    record = repo.get_record("mw-1")
    repo.upsert_record(record.model_copy(update={"metadata": {}}))

    def viewer_package(_managed_well_id: str):
        return SimpleNamespace(
            trajectory=SimpleNamespace(
                render_points=[SimpleNamespace(md=0.0), SimpleNamespace(md=6000.0)]
            )
        )

    service = WbvInteractionService(repo, trajectory_package_provider=viewer_package)
    service.set_mode("mw-1", "point")
    state = service.select_point("mw-1", WbvPickedPoint(md=3000.0, tvd=2700.0))
    assert state.selected_point is not None
    assert state.selected_point.md == 3000.0


def test_viewer_package_range_rejects_out_of_range_pick(tmp_path):
    repo = seeded(tmp_path)

    def viewer_package(_managed_well_id: str):
        return SimpleNamespace(
            trajectory=SimpleNamespace(
                render_points=[SimpleNamespace(md=100.0), SimpleNamespace(md=200.0)]
            )
        )

    service = WbvInteractionService(repo, trajectory_package_provider=viewer_package)
    service.set_mode("mw-1", "point")
    with pytest.raises(ValueError, match="outside the active trajectory range"):
        service.select_point("mw-1", WbvPickedPoint(md=250.0))
