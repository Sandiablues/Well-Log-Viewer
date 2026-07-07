from pathlib import Path

from app.inventory.models import ManagedWellRecord
from app.inventory.repository import ManagedWellInventoryRepository
from app.inventory.wdv_workspace import WdvWorkspaceService


def test_common_depth_unit_is_backend_owned_and_persisted(tmp_path: Path) -> None:
    repo = ManagedWellInventoryRepository(storage_path=tmp_path / "managed.json")
    service = WdvWorkspaceService(repo, storage_path=tmp_path / "wdv_workspace.json")

    initial = service.get_workspace()
    assert initial.common_depth_unit == "m"

    updated = service.set_common_depth_unit("ft")
    assert updated.common_depth_unit == "ft"
    assert updated.revision > initial.revision

    restored = WdvWorkspaceService(repo, storage_path=tmp_path / "wdv_workspace.json").get_workspace()
    assert restored.common_depth_unit == "ft"


def test_common_depth_unit_rejects_unsupported_unit(tmp_path: Path) -> None:
    repo = ManagedWellInventoryRepository(storage_path=tmp_path / "managed.json")
    service = WdvWorkspaceService(repo, storage_path=tmp_path / "wdv_workspace.json")
    try:
        service.set_common_depth_unit("yards")
    except ValueError as exc:
        assert "Common Depth Unit" in str(exc)
    else:
        raise AssertionError("unsupported unit must be rejected")
