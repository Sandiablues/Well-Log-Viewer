"""Application service for WDV-to-WBV publication."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Iterable

from app.identity import new_uuid7_str, parse_uuid7
from app.identity.wdv_contract_v2 import WdvCanonicalSession
from app.wdv_session.canonical_service import CanonicalWdvSessionService
from app.wbv.models import WbvCurveOverlayRenderContract
from app.wbv_layout.repository import WbvTrackLayoutRepository
from app.wbv_layout.service import WbvTrackLayoutService

from .adapter import WbvPublishedPackageRenderAdapter
from .models import (
    WbvOverlayPackage,
    WbvOverlayPackageList,
    WbvPackageLifecycleRequest,
    WbvOverlayPackageRevisionSnapshot,
    WbvPackageChangeSummary,
    WbvPresentationOverrides,
    WbvPresentationOverridesUpdateRequest,
    WbvPublishedTrackPresentationContract,
    WbvPublicationProvenance,
    WbvPublishAsNewRequest,
    WbvPublishPreview,
    WbvPublishPreviewRequest,
    WbvUpdateExistingRequest,
    WbvUpdateExistingResult,
    WbvUpdatePreview,
)
from .repository import WbvOverlayPackageRepository


def _index(items: Iterable[Any], key: Callable[[Any], str]) -> dict[str, Any]:
    return {key(item): item for item in items}


def _changed_ids(before: dict[str, Any], after: dict[str, Any]) -> tuple[str, ...]:
    return tuple(sorted(uid for uid in before.keys() & after.keys() if before[uid] != after[uid]))


def _session_graph(session: WdvCanonicalSession) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    tracks = _index(session.tracks, lambda item: item.track_uid)
    assignments = _index(
        (assignment for track in session.tracks for assignment in track.assignments),
        lambda item: item.assignment_uid,
    )
    fills = _index(session.curve_fills, lambda item: item.rule_uid)
    return tracks, assignments, fills


class WbvOverlayPublicationService:
    def __init__(self, repository=None, session_service=None, render_adapter=None, layout_service=None) -> None:
        self.repository = repository or WbvOverlayPackageRepository()
        self.session_service = session_service or CanonicalWdvSessionService()
        if layout_service is not None:
            self.layout_service = layout_service
        elif repository is not None and hasattr(self.repository, "storage_path"):
            self.layout_service = WbvTrackLayoutService(WbvTrackLayoutRepository(self.repository.storage_path.with_name("track_layouts_v1.json")))
        else:
            self.layout_service = WbvTrackLayoutService()
        self.render_adapter = render_adapter or WbvPublishedPackageRenderAdapter(layout_service=self.layout_service)

    def _committed_view_for_session(self, well_uid: str, session: WdvCanonicalSession) -> tuple[int | None, dict[str, Any]]:
        """Return only the committed WDV view authored for this exact canonical revision."""
        committed = self.session_service.get_workspace_committed_view_state(well_uid)
        if not committed:
            return None, {}
        if committed.get("session_revision") != session.revision:
            return None, {}
        view_revision = committed.get("view_revision")
        view_state = committed.get("view_state")
        return (
            int(view_revision) if isinstance(view_revision, int) and view_revision >= 0 else None,
            dict(view_state) if isinstance(view_state, dict) else {},
        )

    @staticmethod
    def _presentation_state(view_state: dict[str, Any]) -> dict[str, Any]:
        raw = view_state.get("presentation_state")
        return dict(raw) if isinstance(raw, dict) else {}

    def preview(self, managed_well_uid: str, request: WbvPublishPreviewRequest) -> WbvPublishPreview:
        well_uid = str(parse_uuid7(managed_well_uid))
        session = self.session_service.get_session(well_uid)
        assignment_count = sum(len(track.assignments) for track in session.tracks)
        warnings = list(session.warnings)
        if session.state_status != "active":
            warnings.append("WDV session is not active")
        if assignment_count == 0:
            warnings.append("WDV session has no curve assignments")
        view_revision, view_state = self._committed_view_for_session(well_uid, session)
        if view_revision is None:
            warnings.append("WDV has no committed presentation state for the current canonical revision")
        elif not self._presentation_state(view_state):
            warnings.append("WDV committed view has no presentation_state payload")
        return WbvPublishPreview(
            managed_well_uid=well_uid,
            source_session_uid=session.session_uid,
            source_revision=session.revision,
            track_count=len(session.tracks),
            assignment_count=assignment_count,
            fill_rule_count=len(session.curve_fills),
            warnings=tuple(warnings),
            publishable=session.state_status == "active" and assignment_count > 0,
        )

    def publish_as_new(self, managed_well_uid: str, request: WbvPublishAsNewRequest) -> WbvOverlayPackage:
        well_uid = str(parse_uuid7(managed_well_uid))
        existing = self.repository.find_by_command_uid(request.command_uid)
        if existing is not None:
            if (
                existing.managed_well_uid == well_uid
                and existing.provenance.publication_command_uid == request.command_uid
                and existing.provenance.operation == "publish_new"
            ):
                return existing
            raise ValueError("Publication command UID was already used")
        session = self._publishable_session(well_uid)
        source_view_revision, published_view_state = self._committed_view_for_session(well_uid, session)
        now = datetime.now(timezone.utc).isoformat()
        package = WbvOverlayPackage(
            package_uid=new_uuid7_str(),
            managed_well_uid=well_uid,
            package_name=request.package_name.strip(),
            status="active" if request.activate else "inactive",
            source_wdv_session_uid=session.session_uid,
            source_wdv_revision=session.revision,
            published_snapshot=session.model_copy(deep=True),
            source_wdv_view_revision=source_view_revision,
            published_view_state=published_view_state,
            wbv_overrides=self._default_layout_assignments(well_uid, session),
            provenance=WbvPublicationProvenance(
                published_at=now,
                published_by=request.published_by.strip(),
                publication_command_uid=request.command_uid,
                source_session_uid=session.session_uid,
                source_revision=session.revision,
                operation="publish_new",
            ),
            created_at=now,
            updated_at=now,
        )
        return self.repository.save_new(package)

    def preview_update(self, managed_well_uid: str, package_uid: str) -> WbvUpdatePreview:
        package = self.get_package(managed_well_uid, package_uid)
        session = self.session_service.get_session(package.managed_well_uid)
        warnings = list(session.warnings)
        assignment_count = sum(len(track.assignments) for track in session.tracks)
        publishable = session.state_status == "active" and assignment_count > 0
        if session.state_status != "active":
            warnings.append("WDV session is not active")
        if assignment_count == 0:
            warnings.append("WDV session has no curve assignments")
        current_view_revision, _current_view_state = self._committed_view_for_session(well_uid, session)
        changes = self._change_summary(package, session)
        return WbvUpdatePreview(
            managed_well_uid=package.managed_well_uid,
            package_uid=package.package_uid,
            package_revision=package.package_revision,
            source_session_uid=session.session_uid,
            source_revision=session.revision,
            update_available=any(
                (
                    session.session_uid != package.source_wdv_session_uid,
                    session.revision != package.source_wdv_revision,
                    bool(changes.tracks_added),
                    bool(changes.tracks_removed),
                    bool(changes.tracks_changed),
                    bool(changes.assignments_added),
                    bool(changes.assignments_removed),
                    bool(changes.assignments_changed),
                    bool(changes.fills_added),
                    bool(changes.fills_removed),
                    bool(changes.fills_changed),
                    current_view_revision != package.source_wdv_view_revision,
                )
            ),
            publishable=publishable,
            warnings=tuple(warnings),
            changes=changes,
        )

    def update_existing(
        self,
        managed_well_uid: str,
        package_uid: str,
        request: WbvUpdateExistingRequest,
    ) -> WbvUpdateExistingResult:
        well_uid = str(parse_uuid7(managed_well_uid))
        target_uid = str(parse_uuid7(package_uid))
        replay = self.repository.find_by_command_uid(request.command_uid)
        if replay is not None:
            if (
                replay.managed_well_uid == well_uid
                and replay.package_uid == target_uid
                and replay.provenance.publication_command_uid == request.command_uid
                and replay.provenance.operation == "update_existing"
            ):
                return WbvUpdateExistingResult(
                    package=replay,
                    changes=self._change_summary_from_history(replay),
                )
            raise ValueError("Publication command UID was already used")

        current = self.get_package(well_uid, target_uid)
        if current.status == "archived":
            raise ValueError("Archived packages cannot be updated")
        if current.package_revision != request.expected_package_revision:
            raise ValueError(
                f"Stale package revision: expected {request.expected_package_revision}, "
                f"current {current.package_revision}"
            )
        session = self._publishable_session(well_uid)
        source_view_revision, published_view_state = self._committed_view_for_session(well_uid, session)
        changes = self._change_summary(current, session)
        now = datetime.now(timezone.utc).isoformat()
        retained_overrides = self._retain_compatible_overrides(current.wbv_overrides, session)
        retained_overrides = self._complete_layout_assignments(well_uid, retained_overrides, session)
        history_entry = WbvOverlayPackageRevisionSnapshot(
            package_revision=current.package_revision,
            source_wdv_session_uid=current.source_wdv_session_uid,
            source_wdv_revision=current.source_wdv_revision,
            published_snapshot=current.published_snapshot.model_copy(deep=True),
            source_wdv_view_revision=current.source_wdv_view_revision,
            published_view_state=dict(current.published_view_state),
            wbv_overrides=current.wbv_overrides.model_copy(deep=True),
            provenance=current.provenance,
            saved_at=now,
        )
        updated = current.model_copy(
            update={
                "package_revision": current.package_revision + 1,
                "status": "active" if request.activate else current.status,
                "source_wdv_session_uid": session.session_uid,
                "source_wdv_revision": session.revision,
                "published_snapshot": session.model_copy(deep=True),
                "source_wdv_view_revision": source_view_revision,
                "published_view_state": published_view_state,
                "wbv_overrides": retained_overrides,
                "provenance": WbvPublicationProvenance(
                    published_at=now,
                    published_by=request.published_by.strip(),
                    publication_command_uid=request.command_uid,
                    source_session_uid=session.session_uid,
                    source_revision=session.revision,
                    operation="update_existing",
                ),
                "revision_history": (*current.revision_history, history_entry),
                "updated_at": now,
            }
        )
        saved = self.repository.replace_existing(
            updated,
            expected_package_revision=request.expected_package_revision,
        )
        return WbvUpdateExistingResult(package=saved, changes=changes)

    def list_packages(self, managed_well_uid: str, *, include_archived: bool = False) -> WbvOverlayPackageList:
        well_uid = str(parse_uuid7(managed_well_uid))
        packages = self.repository.list_for_well(well_uid)
        if not include_archived:
            packages = tuple(item for item in packages if item.status != "archived")
        return WbvOverlayPackageList(managed_well_uid=well_uid, packages=packages)

    def get_package(self, managed_well_uid: str, package_uid: str) -> WbvOverlayPackage:
        well_uid = str(parse_uuid7(managed_well_uid))
        package = self.repository.get(str(parse_uuid7(package_uid)))
        if package.managed_well_uid != well_uid:
            raise ValueError("Package does not belong to the requested managed well")
        return package

    def set_active(self, managed_well_uid: str, package_uid: str, active: bool) -> WbvOverlayPackage:
        return self.repository.set_active(
            str(parse_uuid7(managed_well_uid)),
            str(parse_uuid7(package_uid)),
            active=active,
        )

    def change_lifecycle(
        self,
        managed_well_uid: str,
        package_uid: str,
        request: WbvPackageLifecycleRequest,
    ) -> WbvOverlayPackage:
        current = self.get_package(managed_well_uid, package_uid)
        if current.package_revision != request.expected_package_revision:
            raise ValueError(
                f"Stale package revision: expected {request.expected_package_revision}, "
                f"current {current.package_revision}"
            )
        if request.action == "archive":
            if current.status == "archived":
                return current
            cleared_tracks = tuple(
                item.model_copy(update={"destination_track_uid": None, "visible": False})
                for item in current.wbv_overrides.tracks
            )
            overrides = current.wbv_overrides.model_copy(
                update={"package_visible": False, "tracks": cleared_tracks}
            )
            next_status = "archived"
        else:
            if current.status != "archived":
                return current
            overrides = current.wbv_overrides.model_copy(update={"package_visible": False})
            next_status = "inactive"

        now = datetime.now(timezone.utc).isoformat()
        updated = current.model_copy(
            update={
                "package_revision": current.package_revision + 1,
                "status": next_status,
                "wbv_overrides": overrides,
                "updated_at": now,
            }
        )
        return self.repository.replace_existing(
            updated,
            expected_package_revision=request.expected_package_revision,
        )

    def delete_package(
        self,
        managed_well_uid: str,
        package_uid: str,
        *,
        expected_package_revision: int,
    ) -> None:
        well_uid = str(parse_uuid7(managed_well_uid))
        target_uid = str(parse_uuid7(package_uid))
        self.repository.delete_existing(
            well_uid,
            target_uid,
            expected_package_revision=expected_package_revision,
        )

    def update_presentation_overrides(
        self,
        managed_well_uid: str,
        package_uid: str,
        request: WbvPresentationOverridesUpdateRequest,
    ) -> WbvOverlayPackage:
        current = self.get_package(managed_well_uid, package_uid)
        if current.status == "archived":
            raise ValueError("Archived packages cannot be edited")
        if current.package_revision != request.expected_package_revision:
            raise ValueError(
                f"Stale package revision: expected {request.expected_package_revision}, "
                f"current {current.package_revision}"
            )
        now = datetime.now(timezone.utc).isoformat()
        updated = current.model_copy(
            update={
                "package_revision": current.package_revision + 1,
                "wbv_overrides": request.overrides.model_copy(deep=True),
                "updated_at": now,
            }
        )
        return self.repository.replace_existing(
            updated,
            expected_package_revision=request.expected_package_revision,
        )

    def get_render_package(self, managed_well_uid: str, package_uid: str) -> WbvCurveOverlayRenderContract:
        package = self.get_package(managed_well_uid, package_uid)
        if package.status == "archived":
            raise ValueError("Archived packages cannot be rendered")
        return self.render_adapter.compile(package)

    def get_track_presentation_package(
        self,
        managed_well_uid: str,
        package_uid: str,
    ) -> WbvPublishedTrackPresentationContract:
        package = self.get_package(managed_well_uid, package_uid)
        if package.status == "archived":
            raise ValueError("Archived packages cannot be rendered")
        presentation = self._presentation_state(package.published_view_state)

        selected_top_ids = presentation.get("selected_formation_top_ids")
        selected_lithology_ids = presentation.get("selected_lithology_interval_ids")
        styles = presentation.get("formation_top_overlay_styles_by_track_id")
        order = presentation.get("track_order_uids")
        widths = presentation.get("track_widths_by_uid")

        return WbvPublishedTrackPresentationContract(
            managed_well_uid=package.managed_well_uid,
            package_uid=package.package_uid,
            package_revision=package.package_revision,
            source_wdv_session_uid=package.source_wdv_session_uid,
            source_wdv_revision=package.source_wdv_revision,
            source_wdv_view_revision=package.source_wdv_view_revision,
            presentation_state=presentation,
            selected_formation_top_ids=tuple(str(item) for item in selected_top_ids) if isinstance(selected_top_ids, list) else (),
            selected_lithology_interval_ids=tuple(str(item) for item in selected_lithology_ids) if isinstance(selected_lithology_ids, list) else (),
            formation_top_overlay_styles_by_track_id=dict(styles) if isinstance(styles, dict) else {},
            track_order_uids=tuple(str(item) for item in order) if isinstance(order, list) else (),
            track_widths_by_uid={
                str(key): float(value)
                for key, value in widths.items()
                if isinstance(value, (int, float))
            } if isinstance(widths, dict) else {},
            curve_render_package=self.render_adapter.compile(package),
        )

    def _default_layout_assignments(self, well_uid: str, session: WdvCanonicalSession) -> WbvPresentationOverrides:
        source_tracks = [track for track in session.tracks if track.track_type == "curve"]
        layout = self.layout_service.ensure_curve_capacity(well_uid, len(source_tracks))
        destinations = [track for track in layout.tracks if track.track_type == "curve"]
        from .models import WbvTrackPresentationOverride
        return WbvPresentationOverrides(tracks=tuple(
            WbvTrackPresentationOverride(track_uid=source.track_uid, destination_track_uid=dest.track_uid)
            for source, dest in zip(source_tracks, destinations)
        ))

    def _complete_layout_assignments(self, well_uid: str, overrides: WbvPresentationOverrides, session: WdvCanonicalSession) -> WbvPresentationOverrides:
        source_tracks = [track for track in session.tracks if track.track_type == "curve"]
        layout = self.layout_service.ensure_curve_capacity(well_uid, len(source_tracks))
        destinations = [track for track in layout.tracks if track.track_type == "curve"]
        existing = {item.track_uid: item for item in overrides.tracks}
        from .models import WbvTrackPresentationOverride
        used = {item.destination_track_uid for item in overrides.tracks if item.destination_track_uid}
        available = [item for item in destinations if item.track_uid not in used]
        completed = []
        for source in source_tracks:
            item = existing.get(source.track_uid)
            if item is None:
                destination = available.pop(0) if available else destinations[0]
                item = WbvTrackPresentationOverride(track_uid=source.track_uid, destination_track_uid=destination.track_uid)
            completed.append(item)
        return overrides.model_copy(update={"tracks": tuple(completed)})

    def _publishable_session(self, well_uid: str) -> WdvCanonicalSession:
        session = self.session_service.get_session(well_uid)
        if session.state_status != "active" or sum(len(track.assignments) for track in session.tracks) == 0:
            raise ValueError("Only an active WDV session with curve assignments can be published")
        return session

    @staticmethod
    def _retain_compatible_overrides(
        overrides: WbvPresentationOverrides,
        session: WdvCanonicalSession,
    ) -> WbvPresentationOverrides:
        tracks, assignments, _ = _session_graph(session)
        return overrides.model_copy(
            update={
                "tracks": tuple(item for item in overrides.tracks if item.track_uid in tracks),
                "curves": tuple(item for item in overrides.curves if item.assignment_uid in assignments),
            },
            deep=True,
        )

    @staticmethod
    def _change_summary(package: WbvOverlayPackage, session: WdvCanonicalSession) -> WbvPackageChangeSummary:
        before_tracks, before_assignments, before_fills = _session_graph(package.published_snapshot)
        after_tracks, after_assignments, after_fills = _session_graph(session)
        retained_track_overrides = sum(1 for item in package.wbv_overrides.tracks if item.track_uid in after_tracks)
        retained_curve_overrides = sum(1 for item in package.wbv_overrides.curves if item.assignment_uid in after_assignments)
        return WbvPackageChangeSummary(
            source_revision_from=package.source_wdv_revision,
            source_revision_to=session.revision,
            tracks_added=tuple(sorted(after_tracks.keys() - before_tracks.keys())),
            tracks_removed=tuple(sorted(before_tracks.keys() - after_tracks.keys())),
            tracks_changed=_changed_ids(before_tracks, after_tracks),
            assignments_added=tuple(sorted(after_assignments.keys() - before_assignments.keys())),
            assignments_removed=tuple(sorted(before_assignments.keys() - after_assignments.keys())),
            assignments_changed=_changed_ids(before_assignments, after_assignments),
            fills_added=tuple(sorted(after_fills.keys() - before_fills.keys())),
            fills_removed=tuple(sorted(before_fills.keys() - after_fills.keys())),
            fills_changed=_changed_ids(before_fills, after_fills),
            retained_track_override_count=retained_track_overrides,
            dropped_track_override_count=len(package.wbv_overrides.tracks) - retained_track_overrides,
            retained_curve_override_count=retained_curve_overrides,
            dropped_curve_override_count=len(package.wbv_overrides.curves) - retained_curve_overrides,
        )

    @staticmethod
    def _change_summary_from_history(package: WbvOverlayPackage) -> WbvPackageChangeSummary:
        if not package.revision_history:
            return WbvPackageChangeSummary(
                source_revision_from=package.source_wdv_revision,
                source_revision_to=package.source_wdv_revision,
                retained_track_override_count=len(package.wbv_overrides.tracks),
                dropped_track_override_count=0,
                retained_curve_override_count=len(package.wbv_overrides.curves),
                dropped_curve_override_count=0,
            )
        prior = package.revision_history[-1]
        synthetic = package.model_copy(
            update={
                "source_wdv_session_uid": prior.source_wdv_session_uid,
                "source_wdv_revision": prior.source_wdv_revision,
                "published_snapshot": prior.published_snapshot,
                "wbv_overrides": prior.wbv_overrides,
            }
        )
        return WbvOverlayPublicationService._change_summary(synthetic, package.published_snapshot)
