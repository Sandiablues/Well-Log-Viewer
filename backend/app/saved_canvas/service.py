"""Saved Canvas application service.

Save is independent of recovery/committed-view/legacy snapshot persistence.
Restore validates first, then atomically replaces canonical session + committed
view state through one backend store transaction.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from threading import Lock
from typing import Any

from app.identity import new_uuid7_str
from app.wdv_session.canonical_service import (
    CanonicalSessionRevisionConflict,
    CanonicalWdvSessionService,
)
from app.wdv_workspace.models import WdvSavedViewState as WdvCanonicalViewState
from app.wdv_session.view_contract import project_canonical_session_view
from app.wdv_workspace.service import CanonicalWdvWorkspaceService

from .models import (
    SavedCanvasCreateRequest,
    SavedCanvasMetadata,
    SavedCanvasRecord,
    SavedCanvasRestoreRequest,
    SavedCanvasRestoreResponse,
    SavedCanvasUpdateRequest,
    SavedCanvasSnapshot,
)
from .repository import SavedCanvasRepository


class SavedCanvasWorkspaceRevisionConflict(RuntimeError):
    pass


class SavedCanvasRestoreInProgress(RuntimeError):
    pass


class SavedCanvasMissingDataError(ValueError):
    def __init__(self, missing: list[str]) -> None:
        self.missing = tuple(missing)
        super().__init__(
            "Saved Canvas cannot be restored because required managed data is missing: "
            + "; ".join(missing)
        )


class SavedCanvasWorkspaceConfigurationMismatch(ValueError):
    pass


class SavedCanvasService:
    _restore_lock = Lock()

    def __init__(
        self,
        *,
        inventory_service: Any,
        session_service: CanonicalWdvSessionService | None = None,
        repository: SavedCanvasRepository | None = None,
        workspace_service: CanonicalWdvWorkspaceService | None = None,
    ) -> None:
        self.inventory_service = inventory_service
        self.session_service = session_service or CanonicalWdvSessionService()
        self.repository = repository or SavedCanvasRepository()
        self.workspace_service = workspace_service or CanonicalWdvWorkspaceService(
            session_service=self.session_service
        )

    def create(self, workspace_id: str, request: SavedCanvasCreateRequest) -> SavedCanvasRecord:
        workspace = self.inventory_service.get_wdv_workspace()
        if workspace.workspace_id != workspace_id:
            raise ValueError(f"Unknown WDV workspace: {workspace_id}")
        if workspace.active_managed_well_uid is None:
            raise ValueError("Cannot save an empty WDV workspace with no active managed well")
        session = self.session_service.get_session(str(workspace.active_managed_well_uid))
        self._validate_view_state_track_ids(session.tracks, request.view_state)
        durable_session = session.model_copy(update={"selected_track_uid": None})
        durable_view_state = request.view_state.model_copy(
            update={"active_track_uids": (), "highlighted_track_uids": ()}
        )
        required_well_uids = tuple(
            sorted({track.managed_well_uid for track in durable_session.tracks})
        )
        record = SavedCanvasRecord(
            saved_canvas_uid=new_uuid7_str(),
            workspace_id=workspace_id,
            name=request.name,
            created_at=datetime.now(timezone.utc).isoformat(),
            snapshot=SavedCanvasSnapshot(
                workspace_id=workspace_id,
                source_workspace_revision=workspace.revision,
                source_session_revision=durable_session.revision,
                common_depth_unit=workspace.common_depth_unit,
                required_managed_well_uids=required_well_uids,
                session=durable_session,
                view_state=durable_view_state,
            ),
        )
        return self.repository.create(record)

    def update(
        self, workspace_id: str, saved_canvas_uid: str, request: SavedCanvasUpdateRequest
    ) -> SavedCanvasRecord:
        workspace = self.inventory_service.get_wdv_workspace()
        if workspace.workspace_id != workspace_id:
            raise ValueError(f"Unknown WDV workspace: {workspace_id}")
        if workspace.active_managed_well_uid is None:
            raise ValueError("Cannot save an empty WDV workspace with no active managed well")
        existing = self.repository.get(workspace_id, saved_canvas_uid)
        session = self.session_service.get_session(str(workspace.active_managed_well_uid))
        self._validate_view_state_track_ids(session.tracks, request.view_state)
        durable_session = session.model_copy(update={"selected_track_uid": None})
        durable_view_state = request.view_state.model_copy(
            update={"active_track_uids": (), "highlighted_track_uids": ()}
        )
        required_well_uids = tuple(
            sorted({track.managed_well_uid for track in durable_session.tracks})
        )
        replacement = existing.model_copy(
            update={
                "snapshot": SavedCanvasSnapshot(
                    workspace_id=workspace_id,
                    source_workspace_revision=workspace.revision,
                    source_session_revision=durable_session.revision,
                    common_depth_unit=workspace.common_depth_unit,
                    required_managed_well_uids=required_well_uids,
                    session=durable_session,
                    view_state=durable_view_state,
                )
            }
        )
        return self.repository.replace(replacement)

    def list(self, workspace_id: str) -> list[SavedCanvasMetadata]:
        self._validate_workspace_identity(workspace_id)
        return self.repository.list_metadata(workspace_id)

    def get(self, workspace_id: str, saved_canvas_uid: str) -> SavedCanvasRecord:
        self._validate_workspace_identity(workspace_id)
        return self.repository.get(workspace_id, saved_canvas_uid)

    def delete(self, workspace_id: str, saved_canvas_uid: str) -> SavedCanvasMetadata:
        self._validate_workspace_identity(workspace_id)
        return self.repository.delete(workspace_id, saved_canvas_uid)

    def restore(
        self,
        workspace_id: str,
        saved_canvas_uid: str,
        request: SavedCanvasRestoreRequest,
    ) -> SavedCanvasRestoreResponse:
        if not self._restore_lock.acquire(blocking=False):
            raise SavedCanvasRestoreInProgress(
                "Another Saved Canvas restore is already in progress"
            )
        try:
            workspace = self.inventory_service.get_wdv_workspace()
            if workspace.workspace_id != workspace_id:
                raise ValueError(f"Unknown WDV workspace: {workspace_id}")
            if workspace.active_managed_well_uid is None:
                raise ValueError(
                    "Cannot restore into an empty WDV workspace with no active managed well"
                )
            record = self.repository.get(workspace_id, saved_canvas_uid)
            snapshot = record.snapshot
            if snapshot.workspace_id != workspace_id:
                raise ValueError("Saved Canvas workspace identity mismatch")
            if snapshot.common_depth_unit != workspace.common_depth_unit:
                raise SavedCanvasWorkspaceConfigurationMismatch(
                    "Saved Canvas common depth unit differs from the current workspace; "
                    "restore is rejected before mutation until workspace-configuration replacement is atomic"
                )
            if snapshot.view_state.depth_unit != snapshot.common_depth_unit:
                raise ValueError("Saved Canvas depth-unit contract is internally inconsistent")
            self._validate_restore_resources(snapshot)
            self._validate_view_state_track_ids(
                snapshot.session.tracks, snapshot.view_state
            )
            active_well_uid = str(workspace.active_managed_well_uid)
            candidate = snapshot.session.model_copy(
                update={
                    "managed_well_uid": workspace.active_managed_well_uid,
                    "selected_track_uid": None,
                }
            )
            self.workspace_service.validate_session(active_well_uid, candidate)
            restored, committed = (
                self.session_service.replace_session_and_committed_view_authoritatively(
                    active_well_uid,
                    session=candidate,
                    view_state=snapshot.view_state.model_dump(mode="json"),
                    validator=lambda persisted: self.workspace_service.validate_session(
                        active_well_uid, persisted
                    ),
                )
            )
            restored_view = WdvCanonicalViewState.model_validate(
                committed["view_state"]
            )
            self.repository.set_active(workspace_id, saved_canvas_uid)
            self._validate_view_state_track_ids(restored.tracks, restored_view)
            return SavedCanvasRestoreResponse(
                saved_canvas_uid=record.saved_canvas_uid,
                workspace_id=workspace_id,
                name=record.name,
                restored_at=committed["committed_at"],
                session=project_canonical_session_view(restored),
                view_revision=int(committed["view_revision"]),
                view_state=restored_view,
            )
        finally:
            self._restore_lock.release()

    def _validate_workspace_identity(self, workspace_id: str) -> None:
        workspace = self.inventory_service.get_wdv_workspace()
        if workspace.workspace_id != workspace_id:
            raise ValueError(f"Unknown WDV workspace: {workspace_id}")

    def _validate_restore_resources(self, snapshot: SavedCanvasSnapshot) -> None:
        records = self.inventory_service.list_wells()
        records_by_uid = {
            str(record.managed_well_uid): record
            for record in records
            if record.managed_well_uid is not None
        }
        missing: list[str] = []
        for uid in snapshot.required_managed_well_uids:
            record = records_by_uid.get(str(uid))
            if record is None or not bool(getattr(record, "wmdp_available", True)):
                missing.append(f"managed well {uid}")
        products_by_uid: dict[str, Any] = {}
        products_by_id: dict[str, Any] = {}
        for record in records_by_uid.values():
            for group in getattr(record, "product_groups", ()):
                for item in getattr(group, "items", ()):
                    products_by_id[str(item.product_id)] = item
                    if item.managed_product_uid is not None:
                        products_by_uid[str(item.managed_product_uid)] = item
        for track in snapshot.session.tracks:
            for assignment in track.assignments:
                item = products_by_uid.get(str(assignment.managed_product_uid))
                if item is None:
                    missing.append(f"managed product {assignment.managed_product_uid}")
                    continue
                if str(getattr(item, "managed_curve_uid", "") or "") != str(
                    assignment.managed_curve_uid
                ):
                    missing.append(f"managed curve {assignment.managed_curve_uid}")
                if str(getattr(item, "managed_source_uid", "") or "") != str(
                    assignment.managed_source_uid
                ):
                    missing.append(f"managed source {assignment.managed_source_uid}")
        interval_state = snapshot.view_state.presentation_state.get(
            "interval_storage_state", {}
        )
        if isinstance(interval_state, dict):
            raw = interval_state.get("wlv.intervalTrack.descriptions.v2")
            if isinstance(raw, str) and raw.strip():
                try:
                    description_state = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        "Saved Canvas Core Description presentation state is malformed"
                    ) from exc
                core_product_id = str(
                    description_state.get("coreProductId") or ""
                ).strip()
                if core_product_id and core_product_id not in products_by_id:
                    missing.append(f"core product {core_product_id}")
        if missing:
            raise SavedCanvasMissingDataError(sorted(set(missing)))

    @staticmethod
    def _validate_view_state_track_ids(
        tracks: tuple[Any, ...], view_state: WdvCanonicalViewState
    ) -> None:
        track_uids = {track.track_uid for track in tracks}
        tie_member_uids = {
            track_uid
            for group in view_state.viewport_tie_groups
            for track_uid in group.member_track_uids
        }
        tie_leader_uids = {
            group.leader_track_uid for group in view_state.viewport_tie_groups
        }
        referenced = (
            set(view_state.active_track_uids)
            | set(view_state.highlighted_track_uids)
            | set(view_state.locked_track_uids)
            | set(view_state.locked_viewports_by_track_uid)
            | set(view_state.track_viewports_by_track_uid)
            | tie_member_uids
            | tie_leader_uids
            | set(view_state.viewport_tie_suspended_track_uids)
        )
        unknown = sorted(referenced - track_uids)
        if unknown:
            raise ValueError(
                "Saved Canvas view state references tracks absent from the canonical canvas: "
                + ", ".join(unknown)
            )
        if set(view_state.locked_viewports_by_track_uid) != set(
            view_state.locked_track_uids
        ):
            raise ValueError(
                "Every locked Saved Canvas track must have exactly one locked viewport"
            )
        seen_tie_members: set[str] = set()
        seen_group_ids: set[str] = set()
        for group in view_state.viewport_tie_groups:
            if group.group_id in seen_group_ids:
                raise ValueError(
                    f"Duplicate Saved Canvas Tie group_id: {group.group_id}"
                )
            seen_group_ids.add(group.group_id)
            overlap = seen_tie_members.intersection(group.member_track_uids)
            if overlap:
                raise ValueError(
                    "A Saved Canvas track may belong to only one viewport Tie: "
                    + ", ".join(sorted(overlap))
                )
            seen_tie_members.update(group.member_track_uids)
        suspended = set(view_state.viewport_tie_suspended_track_uids)
        if not suspended.issubset(seen_tie_members):
            raise ValueError(
                "Suspended Saved Canvas Tie tracks must belong to a saved Tie"
            )
