"""Canonical WDV workspace aggregate service."""

from __future__ import annotations

from app.identity import parse_uuid7
from app.identity.wdv_contract_v2 import WdvCanonicalSession
from app.wdv_session.canonical_service import (
    CanonicalSessionRevisionConflict,
    CanonicalViewRevisionConflict,
    CanonicalWdvSessionService,
)
from app.wells.canonical_viewer_package_service import CanonicalViewerPackageService

from .models import WdvCanonicalWorkspace, WdvSavedViewState


class CanonicalWdvWorkspaceService:
    """Build and validate the complete backend-owned workspace for one well."""

    def __init__(
        self,
        viewer_package_service: CanonicalViewerPackageService | None = None,
        session_service: CanonicalWdvSessionService | None = None,
    ) -> None:
        self.session_service = session_service or CanonicalWdvSessionService()
        self.viewer_package_service = (
            viewer_package_service
            or CanonicalViewerPackageService(session_service=self.session_service)
        )

    def get_workspace(self, managed_well_uid: str) -> WdvCanonicalWorkspace:
        well_uid = str(parse_uuid7(managed_well_uid))
        package = self.viewer_package_service.generate(well_uid)
        return WdvCanonicalWorkspace(
            managed_well_uid=package.managed_well_uid,
            managed_wellbore_uid=package.managed_wellbore_uid,
            well_name=package.well_name,
            wellbore_name=package.wellbore_name,
            depth_range=package.depth_range,
            curve_registry=package.curves,
            session=package.session,
            warnings=package.warnings,
        )

    def validate_session(
        self,
        managed_well_uid: str,
        session: WdvCanonicalSession,
    ) -> WdvCanonicalWorkspace:
        """Validate a candidate session against the well's canonical registry.

        This method is used inside the atomic transaction lock before the
        candidate session is persisted.
        """
        well_uid = str(parse_uuid7(managed_well_uid))
        if session.managed_well_uid != well_uid:
            raise ValueError(
                "Candidate session managed_well_uid must match transaction well"
            )
        package = self.viewer_package_service.generate(well_uid)
        return WdvCanonicalWorkspace(
            managed_well_uid=package.managed_well_uid,
            managed_wellbore_uid=package.managed_wellbore_uid,
            well_name=package.well_name,
            wellbore_name=package.wellbore_name,
            depth_range=package.depth_range,
            curve_registry=package.curves,
            session=session,
            warnings=package.warnings,
        )

    @staticmethod
    def _validate_saved_view_track_ids(
        session: WdvCanonicalSession,
        view_state: WdvSavedViewState,
    ) -> None:
        track_uids = {track.track_uid for track in session.tracks}
        tie_member_uids = {
            track_uid
            for group in view_state.viewport_tie_groups
            for track_uid in group.member_track_uids
        }
        tie_leader_uids = {group.leader_track_uid for group in view_state.viewport_tie_groups}
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
                "Saved view references tracks absent from the canonical canvas: "
                + ", ".join(unknown)
            )
        if set(view_state.locked_viewports_by_track_uid) != set(view_state.locked_track_uids):
            raise ValueError(
                "Every locked track must have exactly one saved locked viewport"
            )

        seen_tie_members: set[str] = set()
        seen_group_ids: set[str] = set()
        for group in view_state.viewport_tie_groups:
            if group.group_id in seen_group_ids:
                raise ValueError(f"Duplicate viewport Tie group_id: {group.group_id}")
            seen_group_ids.add(group.group_id)
            overlap = seen_tie_members.intersection(group.member_track_uids)
            if overlap:
                raise ValueError(
                    "A track may belong to only one viewport Tie: "
                    + ", ".join(sorted(overlap))
                )
            seen_tie_members.update(group.member_track_uids)

        suspended = set(view_state.viewport_tie_suspended_track_uids)
        if not suspended.issubset(seen_tie_members):
            unknown_suspended = sorted(suspended - seen_tie_members)
            raise ValueError(
                "Suspended viewport Tie tracks must belong to a saved Tie: "
                + ", ".join(unknown_suspended)
            )


    def commit_view_state(
        self,
        managed_well_uid: str,
        *,
        expected_session_revision: int,
        expected_view_revision: int,
        view_state: WdvSavedViewState,
    ) -> dict:
        session = self.session_service.get_session(managed_well_uid)
        if session.revision != expected_session_revision:
            raise CanonicalSessionRevisionConflict(
                f"Expected revision {expected_session_revision}, found {session.revision}"
            )
        self._validate_saved_view_track_ids(session, view_state)
        return self.session_service.commit_workspace_view_state(
            managed_well_uid,
            expected_session_revision=expected_session_revision,
            expected_view_revision=expected_view_revision,
            view_state=view_state.model_dump(mode="json"),
        )

    def get_committed_view_state(self, managed_well_uid: str) -> dict:
        committed = self.session_service.get_workspace_committed_view_state(
            managed_well_uid
        )
        if committed is None:
            return {
                "available": False,
                "committed_at": None,
                "session_revision": None,
                "current_session_revision": self.session_service.get_session(managed_well_uid).revision,
                "view_revision": -1,
                "stale": False,
                "view_state": None,
            }

        session = self.session_service.get_session(managed_well_uid)
        committed_session_revision = committed.get("session_revision")
        if committed_session_revision != session.revision:
            return {
                "available": False,
                "committed_at": committed.get("committed_at"),
                "session_revision": committed_session_revision,
                "current_session_revision": session.revision,
                "view_revision": -1,
                "stale": True,
                "view_state": None,
            }

        view_state = WdvSavedViewState.model_validate(committed["view_state"])
        self._validate_saved_view_track_ids(session, view_state)
        return {
            "available": True,
            "committed_at": committed.get("committed_at"),
            "session_revision": committed_session_revision,
            "current_session_revision": session.revision,
            "view_revision": committed.get("view_revision", -1),
            "stale": False,
            "view_state": view_state.model_dump(mode="json"),
        }

    def _validated_exact_committed_view(
        self,
        managed_well_uid: str,
        *,
        expected_revision: int,
        expected_view_revision: int,
    ) -> WdvSavedViewState:
        session = self.session_service.get_session(managed_well_uid)
        if session.revision != expected_revision:
            raise CanonicalSessionRevisionConflict(
                f"Expected revision {expected_revision}, found {session.revision}"
            )
        committed = self.get_committed_view_state(managed_well_uid)
        if (
            not committed.get("available")
            or committed.get("stale")
            or committed.get("session_revision") != expected_revision
        ):
            raise CanonicalViewRevisionConflict(
                "No committed view exists for the expected canonical session revision"
            )
        current_view_revision = int(committed.get("view_revision", -1))
        if current_view_revision != expected_view_revision:
            raise CanonicalViewRevisionConflict(
                f"Expected view revision {expected_view_revision}, found {current_view_revision}"
            )
        view_state = WdvSavedViewState.model_validate(committed["view_state"])
        self._validate_saved_view_track_ids(session, view_state)
        return view_state

    def save_snapshot_from_committed_view(
        self,
        managed_well_uid: str,
        *,
        expected_revision: int,
        expected_view_revision: int,
    ) -> dict:
        self._validated_exact_committed_view(
            managed_well_uid,
            expected_revision=expected_revision,
            expected_view_revision=expected_view_revision,
        )
        return self.session_service.save_workspace_snapshot_from_committed_view(
            managed_well_uid,
            expected_revision=expected_revision,
            expected_view_revision=expected_view_revision,
        )

    def save_recovery_state_from_committed_view(
        self,
        managed_well_uid: str,
        *,
        expected_revision: int,
        expected_view_revision: int,
    ) -> dict:
        self._validated_exact_committed_view(
            managed_well_uid,
            expected_revision=expected_revision,
            expected_view_revision=expected_view_revision,
        )
        return self.session_service.save_workspace_recovery_from_committed_view(
            managed_well_uid,
            expected_revision=expected_revision,
            expected_view_revision=expected_view_revision,
        )

    def save_snapshot(
        self,
        managed_well_uid: str,
        *,
        expected_revision: int,
        view_state: WdvSavedViewState,
    ) -> dict:
        workspace = self.get_workspace(managed_well_uid)
        if workspace.session.revision != expected_revision:
            from app.wdv_session.canonical_service import CanonicalSessionRevisionConflict
            raise CanonicalSessionRevisionConflict(
                f"Expected revision {expected_revision}, found {workspace.session.revision}"
            )
        self._validate_saved_view_track_ids(workspace.session, view_state)
        return self.session_service.save_workspace_snapshot(
            managed_well_uid,
            expected_revision=expected_revision,
            view_state=view_state.model_dump(mode="json"),
        )

    def save_recovery_state(
        self,
        managed_well_uid: str,
        *,
        expected_revision: int,
        view_state: WdvSavedViewState,
    ) -> dict:
        workspace = self.get_workspace(managed_well_uid)
        if workspace.session.revision != expected_revision:
            from app.wdv_session.canonical_service import CanonicalSessionRevisionConflict
            raise CanonicalSessionRevisionConflict(
                f"Expected revision {expected_revision}, found {workspace.session.revision}"
            )
        self._validate_saved_view_track_ids(workspace.session, view_state)
        return self.session_service.save_workspace_recovery_state(
            managed_well_uid,
            expected_revision=expected_revision,
            view_state=view_state.model_dump(mode="json"),
        )

    def get_recovery_state(self, managed_well_uid: str) -> dict:
        recovery = self.session_service.get_workspace_recovery_state(managed_well_uid)
        if recovery is None:
            return {
                "available": False,
                "saved_at": None,
                "session_revision": None,
                "current_session_revision": None,
                "stale": False,
                "view_state": None,
            }

        workspace = self.get_workspace(managed_well_uid)
        recovery_revision = recovery.get("session_revision")
        current_revision = workspace.session.revision

        # Recovery is a checkpoint for one exact canonical session revision.
        # Never parse or expose its view payload when that revision no longer
        # matches the durable canonical session. This prevents stale recovery
        # from rebinding tracks/viewports after canonical content has changed.
        if not isinstance(recovery_revision, int) or recovery_revision != current_revision:
            return {
                "available": False,
                "saved_at": recovery.get("saved_at"),
                "session_revision": recovery_revision,
                "current_session_revision": current_revision,
                "stale": True,
                "view_state": None,
            }

        view_state = WdvSavedViewState.model_validate(recovery["view_state"])
        self._validate_saved_view_track_ids(workspace.session, view_state)
        return {
            "available": True,
            "saved_at": recovery.get("saved_at"),
            "session_revision": recovery_revision,
            "current_session_revision": current_revision,
            "stale": False,
            "view_state": view_state.model_dump(mode="json"),
        }

    def get_snapshot(self, managed_well_uid: str) -> dict:
        snapshot = self.session_service.get_workspace_snapshot(managed_well_uid)
        if snapshot is None:
            return {"available": False, "saved_at": None, "view_state": None}
        view_state = WdvSavedViewState.model_validate(snapshot["view_state"])
        self._validate_saved_view_track_ids(snapshot["session"], view_state)
        return {
            "available": True,
            "saved_at": snapshot.get("saved_at"),
            "view_state": view_state.model_dump(mode="json"),
        }

    def restore_snapshot(
        self,
        managed_well_uid: str,
        *,
        expected_revision: int,
    ) -> dict:
        restored, raw_view_state, saved_at = self.session_service.restore_workspace_snapshot(
            managed_well_uid,
            expected_revision=expected_revision,
            validator=lambda candidate: self.validate_session(
                managed_well_uid,
                candidate,
            ),
        )
        view_state = WdvSavedViewState.model_validate(raw_view_state)
        self._validate_saved_view_track_ids(restored, view_state)
        return {
            "available": True,
            "saved_at": saved_at,
            "session": restored,
            "view_state": view_state.model_dump(mode="json"),
        }

