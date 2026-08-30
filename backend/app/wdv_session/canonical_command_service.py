"""Atomic backend-owned WDV track and assignment commands."""

from __future__ import annotations

from collections.abc import Callable

from app.identity import new_uuid7_str
from app.identity.wdv_contract_v2 import (
    WdvCanonicalAssignment,
    WdvCanonicalSession,
    WdvCanonicalTrack,
)
from app.inventory.canonical_identity_resolver import CanonicalInventoryIdentityResolver
from app.wdv_display.policy_service import (
    WdvCurveDisplayPolicyService,
    compute_display_policy_revision,
)
from app.wdv_session.canonical_commands import (
    AddCurveAssignmentCommand,
    BootstrapCurveAssignmentCommand,
    CreateConfiguredTrackCommand,
    CreateTrackCommand,
    ClearCanvasCommand,
    RemoveCurveAssignmentCommand,
    RemoveTrackCommand,
    MoveCurveAssignmentCommand,
    ReorderCurveAssignmentsCommand,
    ReorderTracksCommand,
    ResetCurveTrackWidthsCommand,
    SelectTrackCommand,
    UpdateCurveAssignmentCommand,
    UpdateCurveLineStyleCommand,
    UpdateTrackCommand,
)
from app.wdv_session.assignment_policy_service import (
    CanonicalWdvAssignmentPolicyService,
)
from app.wdv_session.canonical_service import CanonicalWdvSessionService
from app.wdv_workspace.service import CanonicalWdvWorkspaceService
from app.wdv_workspace.transaction_service import (
    CanonicalWdvWorkspaceTransactionService,
)
from app.wells.canonical_viewer_package_service import CanonicalViewerPackageService


class CanonicalWdvCommandError(ValueError):
    pass


class CanonicalWdvCommandService:
    def __init__(
        self,
        session_service: CanonicalWdvSessionService | None = None,
        resolver: CanonicalInventoryIdentityResolver | None = None,
        transaction_service: CanonicalWdvWorkspaceTransactionService | None = None,
        *,
        policy_revision_fn: Callable[[], str] | None = None,
        display_policy_resolver: Callable[[object], dict] | None = None,
    ) -> None:
        self.resolver = resolver or CanonicalInventoryIdentityResolver()
        self._policy_revision_fn: Callable[[], str] = (
            policy_revision_fn
            if policy_revision_fn is not None
            else compute_display_policy_revision
        )
        self._display_policy_resolver: Callable[[object], dict] = (
            display_policy_resolver
            if display_policy_resolver is not None
            else WdvCurveDisplayPolicyService.resolve
        )
        self.assignment_policy_service = CanonicalWdvAssignmentPolicyService(
            resolver=self.resolver,
            display_policy_resolver=self._display_policy_resolver,
        )
        self.session_service = session_service or CanonicalWdvSessionService()
        self.session_service.configure_policy_refresh(
            policy_revision_fn=self._policy_revision_fn,
            assignment_policy_refresh_fn=(
                self.assignment_policy_service.refresh_assignment
            ),
        )
        if transaction_service is None:
            workspace_service = None
            if isinstance(self.resolver, CanonicalInventoryIdentityResolver):
                viewer_package_service = CanonicalViewerPackageService(
                    resolver=self.resolver,
                    session_service=self.session_service,
                )
                workspace_service = CanonicalWdvWorkspaceService(
                    viewer_package_service=viewer_package_service,
                    session_service=self.session_service,
                )
            transaction_service = CanonicalWdvWorkspaceTransactionService(
                session_service=self.session_service,
                workspace_service=workspace_service,
            )
        self.transaction_service = transaction_service

    def _execute(self, managed_well_uid: str, command, mutation):
        payload = command.model_dump(
            mode="json",
            exclude={"expected_revision", "command_id"},
        )
        current_policy_revision = self._policy_revision_fn()

        def mutation_with_policy_revision(
            session: WdvCanonicalSession,
        ) -> WdvCanonicalSession:
            mutated = mutation(session)
            return mutated.model_copy(
                update={
                    "display_policy_revision": current_policy_revision,
                }
            )

        return self.transaction_service.execute(
            managed_well_uid,
            expected_revision=command.expected_revision,
            command_name=command.__class__.__name__,
            command_payload=payload,
            command_id=command.command_id,
            mutation=mutation_with_policy_revision,
        )

    def create_track(
        self,
        managed_well_uid: str,
        command: CreateTrackCommand,
    ) -> WdvCanonicalSession:
        def mutate(session: WdvCanonicalSession) -> WdvCanonicalSession:
            track = WdvCanonicalTrack(
                track_uid=new_uuid7_str(),
                managed_well_uid=managed_well_uid,
                track_key=command.track_key,
                track_number=command.track_number,
                track_name=command.track_name,
                track_type=command.track_type,
                renderer_type=command.renderer_type,
                track_role=command.track_role,
                width_px=command.width_px,
                lattice=command.lattice,
                lattice_source=command.lattice_source,
                source_template_key=command.source_template_key,
                source_application_plan_uid=command.source_application_plan_uid,
                assignments=(),
            )
            tracks = (*session.tracks, track)
            return session.model_copy(
                update={
                    "state_status": "active",
                    "tracks": tracks,
                    "selected_track_uid": (
                        track.track_uid
                        if command.select_created_track
                        else session.selected_track_uid
                    ),
                }
            )

        return self._execute(managed_well_uid, command, mutate)

    @staticmethod
    def _canonical_scale_type(value) -> str:
        key = str(value or "").strip().lower()
        return "logarithmic" if key in {"log", "logarithmic"} else "linear"

    @staticmethod
    def _canonical_scale_direction(value) -> str:
        key = str(value or "").strip().lower()
        return "reversed" if key in {
            "reverse",
            "reversed",
            "right_to_left",
            "decreasing",
        } else "normal"

    @staticmethod
    def _renumber_tracks(
        tracks: tuple[WdvCanonicalTrack, ...],
    ) -> tuple[WdvCanonicalTrack, ...]:
        return tuple(
            track.model_copy(update={"track_number": index})
            for index, track in enumerate(tracks)
        )

    def create_configured_track(
        self,
        managed_well_uid: str,
        command: CreateConfiguredTrackCommand,
    ) -> WdvCanonicalSession:
        def mutate(session: WdvCanonicalSession) -> WdvCanonicalSession:
            reference_uid = command.insert_position.reference_track_uid
            insertion_index = len(session.tracks)

            if command.insert_position.mode in {
                "before_track",
                "after_track",
            }:
                reference_index = next(
                    (
                        index
                        for index, track in enumerate(session.tracks)
                        if track.track_uid == reference_uid
                    ),
                    None,
                )
                if reference_index is None:
                    raise CanonicalWdvCommandError(
                        f"Unknown reference_track_uid: {reference_uid}"
                    )
                insertion_index = reference_index
                if command.insert_position.mode == "after_track":
                    insertion_index += 1

            track_uid = new_uuid7_str()
            assignments = tuple(
                self.assignment_policy_service.create_assignment(
                    managed_well_uid=managed_well_uid,
                    managed_curve_uid=managed_curve_uid,
                    track_uid=track_uid,
                    stack_index=index,
                    assignment_source="configured_track_backend_command",
                )
                for index, managed_curve_uid in enumerate(
                    command.initial_managed_curve_uids
                )
            )

            track = WdvCanonicalTrack(
                track_uid=track_uid,
                managed_well_uid=managed_well_uid,
                track_key=command.track_key,
                track_name=command.track_name,
                track_type=command.track_type,
                renderer_type=command.renderer_type,
                track_role=command.track_role,
                width_px=command.width_px,
                lattice=command.lattice,
                lattice_source=command.lattice_source,
                lattice_override=command.lattice_override,
                scale_mode=command.scale_mode,
                depth_basis=command.depth_basis,
                source_template_key=command.source_template_key,
                source_application_plan_uid=command.source_application_plan_uid,
                assignments=assignments,
            )

            tracks = list(session.tracks)
            tracks.insert(insertion_index, track)
            normalized_tracks = self._renumber_tracks(tuple(tracks))

            return session.model_copy(
                update={
                    "state_status": "active",
                    "tracks": normalized_tracks,
                    "selected_track_uid": (
                        track.track_uid
                        if command.select_created_track
                        else session.selected_track_uid
                    ),
                }
            )

        return self._execute(managed_well_uid, command, mutate)


    def clear_canvas(
        self,
        managed_well_uid: str,
        command: ClearCanvasCommand,
    ) -> WdvCanonicalSession:
        def mutate(session: WdvCanonicalSession) -> WdvCanonicalSession:
            tracks = (
                tuple(track for track in session.tracks if track.track_type == "depth")
                if command.preserve_depth_tracks
                else ()
            )
            selected = session.selected_track_uid
            if not any(track.track_uid == selected for track in tracks):
                selected = tracks[0].track_uid if tracks else None
            retained_track_uids = {track.track_uid for track in tracks}
            return session.model_copy(
                update={
                    "tracks": self._renumber_tracks(tracks),
                    "curve_fills": tuple(
                        rule for rule in session.curve_fills
                        if rule.track_uid in retained_track_uids
                    ),
                    "selected_track_uid": selected,
                    "state_status": "active" if tracks else "empty",
                }
            )

        return self._execute(managed_well_uid, command, mutate)


    def remove_track(
        self,
        managed_well_uid: str,
        command: RemoveTrackCommand,
    ) -> WdvCanonicalSession:
        def mutate(session: WdvCanonicalSession) -> WdvCanonicalSession:
            retained_tracks = tuple(
                track for track in session.tracks
                if track.track_uid != command.track_uid
            )
            if len(retained_tracks) == len(session.tracks):
                raise CanonicalWdvCommandError(
                    f"Unknown track_uid: {command.track_uid}"
                )

            # WDV_REMOVE_TRACK_INBOUND_REFERENCE_CLEANUP_V1_0_0
            #
            # Track deletion is an atomic canonical mutation. A retained track
            # must never be left pointing at the removed track through its
            # Depth Range Locator source UID, because canonical validation
            # requires that source UID to resolve to a track in the same
            # session.
            tracks = tuple(
                track.model_copy(
                    update={
                        "depth_range_locator_enabled": False,
                        "depth_range_locator_source_track_uid": None,
                        "depth_range_locator_mode": None,
                        "depth_range_locator_presentation": None,
                        "depth_range_locator_side": None,
                    }
                )
                if track.depth_range_locator_source_track_uid == command.track_uid
                else track
                for track in retained_tracks
            )

            selected = session.selected_track_uid
            if selected == command.track_uid:
                selected = tracks[0].track_uid if tracks else None

            return session.model_copy(
                update={
                    "tracks": tracks,
                    "curve_fills": tuple(
                        rule for rule in session.curve_fills
                        if rule.track_uid != command.track_uid
                    ),
                    "selected_track_uid": selected,
                    "state_status": "active" if tracks else "empty",
                }
            )

        return self._execute(managed_well_uid, command, mutate)

    def bootstrap_assignment(
        self,
        managed_well_uid: str,
        command: BootstrapCurveAssignmentCommand,
    ) -> WdvCanonicalSession:
        """Create the first curve track and assignment in one transaction.

        The command is deliberately restricted to sessions with no tracks.
        Existing sessions must use the normal track and assignment commands,
        which prevents this bootstrap path from becoming a second layout
        authority.
        """
        resolved = self.resolver.resolve_curve(
            managed_well_uid,
            command.managed_curve_uid,
        )
        def mutate(session: WdvCanonicalSession) -> WdvCanonicalSession:
            if session.tracks:
                raise CanonicalWdvCommandError(
                    "Canonical empty-session bootstrap requires a session with no tracks"
                )

            track_uid = new_uuid7_str()
            track_name = (
                command.track_name
                or resolved.product.display_name
                or resolved.product.normalized_mnemonic
                or resolved.product.observed_mnemonic
                or "Curve Track"
            )
            assignment = self.assignment_policy_service.create_assignment_from_resolved(
                resolved=resolved,
                track_uid=track_uid,
                stack_index=0,
                assignment_source=command.source,
                visible=command.visible,
                color=command.color,
                line_style=command.line_style,
                line_width=command.line_width,
                fill_mode=command.fill_mode,
            )
            track = WdvCanonicalTrack(
                track_uid=track_uid,
                managed_well_uid=managed_well_uid,
                track_key="canonical-bootstrap-curve-track",
                track_number=0,
                track_name=track_name,
                track_type="curve",
                renderer_type="curve",
                track_role="curve",
                width_px=command.width_px,
                lattice=assignment.scale_type,
                lattice_source="backend_display_policy",
                scale_mode="per_curve",
                assignments=(assignment,),
            )
            return session.model_copy(
                update={
                    "state_status": "active",
                    "tracks": (track,),
                    "selected_track_uid": track_uid,
                    "display_policy_revision": self._policy_revision_fn(),
                }
            )

        return self._execute(managed_well_uid, command, mutate)


    def add_assignment(
        self,
        managed_well_uid: str,
        command: AddCurveAssignmentCommand,
    ) -> WdvCanonicalSession:
        resolved = self.resolver.resolve_curve(
            managed_well_uid,
            command.managed_curve_uid,
        )
        def mutate(session: WdvCanonicalSession) -> WdvCanonicalSession:
            target = next(
                (track for track in session.tracks if track.track_uid == command.track_uid),
                None,
            )
            if target is None:
                raise CanonicalWdvCommandError(
                    f"Unknown track_uid: {command.track_uid}"
                )
            if target.track_type != "curve":
                raise CanonicalWdvCommandError(
                    "Curve assignments may only be added to curve tracks"
                )
            if target.managed_well_uid != managed_well_uid:
                raise CanonicalWdvCommandError(
                    "Curve assignments may only be added to tracks owned by the working well"
                )

            target_stack_index = (
                len(target.assignments)
                if command.target_stack_index is None
                else command.target_stack_index
            )
            if target_stack_index > len(target.assignments):
                raise CanonicalWdvCommandError(
                    "target_stack_index may not exceed the target "
                    "assignment count"
                )

            assignment = self.assignment_policy_service.create_assignment_from_resolved(
                resolved=resolved,
                track_uid=target.track_uid,
                stack_index=target_stack_index,
                assignment_source=command.source,
                visible=command.visible,
                color=command.color,
                line_style=command.line_style,
                line_width=command.line_width,
                fill_mode=command.fill_mode,
            )

            assignments = list(target.assignments)
            assignments.insert(target_stack_index, assignment)
            normalized_assignments = tuple(
                item.model_copy(update={"stack_index": index})
                for index, item in enumerate(assignments)
            )

            tracks = tuple(
                track.model_copy(
                    update={"assignments": normalized_assignments}
                )
                if track.track_uid == target.track_uid else track
                for track in session.tracks
            )
            return session.model_copy(
                update={
                    "tracks": tracks,
                    "state_status": "active",
                    "selected_track_uid": target.track_uid,
                    "display_policy_revision": self._policy_revision_fn(),
                }
            )

        return self._execute(managed_well_uid, command, mutate)

    def remove_assignment(
        self,
        managed_well_uid: str,
        command: RemoveCurveAssignmentCommand,
    ) -> WdvCanonicalSession:
        def mutate(session: WdvCanonicalSession) -> WdvCanonicalSession:
            found = False
            tracks: list[WdvCanonicalTrack] = []
            for track in session.tracks:
                kept = tuple(
                    item for item in track.assignments
                    if item.assignment_uid != command.assignment_uid
                )
                if len(kept) != len(track.assignments):
                    found = True
                    kept = tuple(
                        item.model_copy(update={"stack_index": index})
                        for index, item in enumerate(kept)
                    )
                    track = track.model_copy(update={"assignments": kept})
                tracks.append(track)
            if not found:
                raise CanonicalWdvCommandError(
                    f"Unknown assignment_uid: {command.assignment_uid}"
                )
            return session.model_copy(
                update={
                    "tracks": tuple(tracks),
                    "curve_fills": tuple(
                        rule for rule in session.curve_fills
                        if rule.curve_a_assignment_uid != command.assignment_uid
                        and rule.curve_b_assignment_uid != command.assignment_uid
                    ),
                }
            )

        return self._execute(managed_well_uid, command, mutate)

    def reorder_assignments(
        self,
        managed_well_uid: str,
        command: ReorderCurveAssignmentsCommand,
    ) -> WdvCanonicalSession:
        def mutate(session: WdvCanonicalSession) -> WdvCanonicalSession:
            target = next(
                (track for track in session.tracks if track.track_uid == command.track_uid),
                None,
            )
            if target is None:
                raise CanonicalWdvCommandError(
                    f"Unknown track_uid: {command.track_uid}"
                )
            existing = {item.assignment_uid: item for item in target.assignments}
            if set(command.assignment_uids) != set(existing):
                raise CanonicalWdvCommandError(
                    "assignment_uids must exactly match the target track assignments"
                )
            reordered = tuple(
                existing[uid].model_copy(update={"stack_index": index})
                for index, uid in enumerate(command.assignment_uids)
            )
            tracks = tuple(
                track.model_copy(update={"assignments": reordered})
                if track.track_uid == target.track_uid else track
                for track in session.tracks
            )
            return session.model_copy(update={"tracks": tracks})

        return self._execute(managed_well_uid, command, mutate)

    def reset_curve_track_widths(
        self,
        managed_well_uid: str,
        command: ResetCurveTrackWidthsCommand,
    ) -> WdvCanonicalSession:
        def mutate(session: WdvCanonicalSession) -> WdvCanonicalSession:
            applicable = tuple(
                track
                for track in session.tracks
                if track.track_type == "curve"
                and (
                    not command.visible_curve_tracks_only
                    or track.visible
                )
            )
            if not applicable:
                raise CanonicalWdvCommandError(
                    "No applicable curve tracks are available for width reset"
                )

            applicable_uids = {track.track_uid for track in applicable}
            tracks = tuple(
                track.model_copy(update={"width_px": command.width_px})
                if track.track_uid in applicable_uids
                else track
                for track in session.tracks
            )
            return session.model_copy(update={"tracks": tracks})

        return self._execute(managed_well_uid, command, mutate)


    def select_track(
        self,
        managed_well_uid: str,
        command: SelectTrackCommand,
    ) -> WdvCanonicalSession:
        def mutate(session: WdvCanonicalSession) -> WdvCanonicalSession:
            if (
                command.track_uid is not None
                and all(track.track_uid != command.track_uid for track in session.tracks)
            ):
                raise CanonicalWdvCommandError(
                    f"Unknown track_uid: {command.track_uid}"
                )
            return session.model_copy(
                update={"selected_track_uid": command.track_uid}
            )

        return self._execute(managed_well_uid, command, mutate)


    def update_track(
        self,
        managed_well_uid: str,
        command: UpdateTrackCommand,
    ) -> WdvCanonicalSession:
        def mutate(session: WdvCanonicalSession) -> WdvCanonicalSession:
            found = False
            tracks: list[WdvCanonicalTrack] = []
            patch = command.model_dump(
                exclude={
                    "expected_revision",
                    "track_uid",
                },
                exclude_none=True,
            )
            for track in session.tracks:
                if track.track_uid == command.track_uid:
                    found = True
                    if command.depth_basis is not None and track.track_type != "depth":
                        raise CanonicalWdvCommandError(
                            "depth_basis may only be set on depth tracks"
                        )
                    if (
                        command.renderer_type is not None
                        or command.track_role is not None
                    ) and track.track_type != "annotation":
                        raise CanonicalWdvCommandError(
                            "renderer_type/track_role updates are only valid "
                            "for annotation tracks"
                        )
                    has_core_appearance_patch = any(value is not None for value in (
                        command.core_base_color,
                        command.core_brightness,
                        command.core_shading_mode,
                        command.core_shading_strength,
                        command.core_description_overlay_enabled,
                        command.core_description_overlay_position,
                        command.core_description_overlay_width_pct,
                        command.core_description_overlay_font_size,
                        command.core_description_overlay_show_md,
                    ))
                    if has_core_appearance_patch and not (
                        track.track_type == "image"
                        and track.renderer_type == "core_image"
                    ):
                        raise CanonicalWdvCommandError(
                            "Core appearance updates are valid only for core_image tracks"
                        )
                    has_completion_appearance_patch = any(value is not None for value in (
                        command.completion_schematic_position,
                        command.completion_schematic_width_px,
                        command.completion_symbol_scale,
                        command.completion_line_weight,
                        command.completion_show_labels,
                        command.completion_label_position,
                        command.completion_label_font_size,
                        command.completion_label_offset_px,
                        command.completion_label_vertical_offset_px,
                        command.completion_label_max_width_px,
                        command.completion_label_collision_mode,
                        command.completion_label_wrap,
                    ))
                    if has_completion_appearance_patch and not (
                        track.track_type == "annotation"
                        and track.renderer_type == "completion_components"
                    ):
                        raise CanonicalWdvCommandError(
                            "Completion appearance updates are valid only for completion_components tracks"
                        )
                    track = track.model_copy(update=patch)
                tracks.append(track)
            if not found:
                raise CanonicalWdvCommandError(
                    f"Unknown track_uid: {command.track_uid}"
                )
            invalidated_rules = tuple(
                rule.model_copy(update={
                    "state": type(rule.state)("pending_geometry"),
                    "state_reason": None,
                    "geometry_revision": None,
                })
                if rule.track_uid == command.track_uid and rule.enabled
                else rule
                for rule in session.curve_fills
            )
            return session.model_copy(update={
                "tracks": tuple(tracks),
                "curve_fills": invalidated_rules,
            })

        return self._execute(managed_well_uid, command, mutate)

    def reorder_tracks(
        self,
        managed_well_uid: str,
        command: ReorderTracksCommand,
    ) -> WdvCanonicalSession:
        def mutate(session: WdvCanonicalSession) -> WdvCanonicalSession:
            existing = {track.track_uid: track for track in session.tracks}
            if len(command.track_uids) != len(set(command.track_uids)):
                raise CanonicalWdvCommandError("track_uids must be unique")
            if set(command.track_uids) != set(existing):
                raise CanonicalWdvCommandError(
                    "track_uids must exactly match the session tracks"
                )
            tracks = tuple(
                existing[track_uid].model_copy(
                    update={"track_number": index}
                )
                for index, track_uid in enumerate(command.track_uids)
            )
            return session.model_copy(update={"tracks": tracks})

        return self._execute(managed_well_uid, command, mutate)

    def update_curve_line_style(
        self,
        managed_well_uid: str,
        command: UpdateCurveLineStyleCommand,
    ) -> WdvCanonicalSession:
        """Atomically replace user-owned Line values without policy refresh."""

        def mutate(session: WdvCanonicalSession) -> WdvCanonicalSession:
            found = False
            tracks: list[WdvCanonicalTrack] = []
            style_patch = {
                "line_visible": command.line_visible,
                "color": command.color,
                "line_width": command.line_width,
                "line_style": command.line_style,
                "line_opacity": command.line_opacity,
            }

            for track in session.tracks:
                assignments: list[WdvCanonicalAssignment] = []
                changed = False
                for assignment in track.assignments:
                    if assignment.assignment_uid == command.assignment_uid:
                        found = True
                        changed = True
                        assignment = assignment.model_copy(update=style_patch)
                    assignments.append(assignment)
                if changed:
                    track = track.model_copy(update={"assignments": tuple(assignments)})
                tracks.append(track)

            if not found:
                raise CanonicalWdvCommandError(
                    f"Unknown assignment_uid: {command.assignment_uid}"
                )

            return session.model_copy(update={"tracks": tuple(tracks)})

        return self._execute(managed_well_uid, command, mutate)


    def update_assignment(
        self,
        managed_well_uid: str,
        command: UpdateCurveAssignmentCommand,
    ) -> WdvCanonicalSession:
        def mutate(session: WdvCanonicalSession) -> WdvCanonicalSession:
            found = False
            tracks: list[WdvCanonicalTrack] = []
            patch = command.model_dump(
                exclude={
                    "expected_revision",
                    "assignment_uid",
                    "clear_paired_managed_curve_uid",
                    "range_override_mode",
                    "manual_scale_min",
                    "manual_scale_max",
                    "scale_type",
                    "scale_direction",
                },
                exclude_none=True,
            )
            if command.scale_type is not None:
                patch["scale_type_override"] = command.scale_type
            if command.scale_direction is not None:
                patch["scale_direction_override"] = command.scale_direction
            if command.clear_paired_managed_curve_uid:
                patch["paired_managed_curve_uid"] = None
            if command.range_override_mode is not None:
                patch["range_override_mode"] = command.range_override_mode
                patch["manual_scale_min"] = command.manual_scale_min
                patch["manual_scale_max"] = command.manual_scale_max

            for track in session.tracks:
                assignments: list[WdvCanonicalAssignment] = []
                changed = False
                for assignment in track.assignments:
                    if assignment.assignment_uid == command.assignment_uid:
                        found = True
                        changed = True
                        assignment = assignment.model_copy(update=patch)
                        assignment = (
                            self.assignment_policy_service.refresh_assignment(
                                assignment
                            )
                        )
                    assignments.append(assignment)
                if changed:
                    track = track.model_copy(
                        update={"assignments": tuple(assignments)}
                    )
                tracks.append(track)

            if not found:
                raise CanonicalWdvCommandError(
                    f"Unknown assignment_uid: {command.assignment_uid}"
                )
            invalidated_rules = tuple(
                rule.model_copy(update={
                    "state": type(rule.state)("pending_geometry"),
                    "state_reason": None,
                    "geometry_revision": None,
                })
                if rule.enabled and (
                    rule.curve_a_assignment_uid == command.assignment_uid
                    or rule.curve_b_assignment_uid == command.assignment_uid
                ) else rule
                for rule in session.curve_fills
            )
            return session.model_copy(
                update={
                    "tracks": tuple(tracks),
                    "curve_fills": invalidated_rules,
                    "display_policy_revision": self._policy_revision_fn(),
                }
            )

        return self._execute(managed_well_uid, command, mutate)

    def move_assignment(
        self,
        managed_well_uid: str,
        command: MoveCurveAssignmentCommand,
    ) -> WdvCanonicalSession:
        def mutate(session: WdvCanonicalSession) -> WdvCanonicalSession:
            moving: WdvCanonicalAssignment | None = None
            source_track_uid: str | None = None
            target = next(
                (
                    track
                    for track in session.tracks
                    if track.track_uid == command.target_track_uid
                ),
                None,
            )
            if target is None:
                raise CanonicalWdvCommandError(
                    f"Unknown target_track_uid: {command.target_track_uid}"
                )
            if target.track_type != "curve":
                raise CanonicalWdvCommandError(
                    "Assignments may only be moved to curve tracks"
                )

            for track in session.tracks:
                for assignment in track.assignments:
                    if assignment.assignment_uid == command.assignment_uid:
                        moving = assignment
                        source_track_uid = track.track_uid
                        break
                if moving is not None:
                    break

            if moving is None or source_track_uid is None:
                raise CanonicalWdvCommandError(
                    f"Unknown assignment_uid: {command.assignment_uid}"
                )
            if target.managed_well_uid != moving.managed_well_uid:
                raise CanonicalWdvCommandError(
                    "Assignments may not be moved between tracks owned by different wells"
                )

            target_without_moving = [
                item
                for item in target.assignments
                if item.assignment_uid != command.assignment_uid
            ]
            insertion_index = min(
                command.target_stack_index,
                len(target_without_moving),
            )
            moved = moving.model_copy(
                update={"track_uid": command.target_track_uid}
            )
            target_without_moving.insert(insertion_index, moved)

            tracks: list[WdvCanonicalTrack] = []
            for track in session.tracks:
                if track.track_uid == command.target_track_uid:
                    normalized = tuple(
                        item.model_copy(update={"stack_index": index})
                        for index, item in enumerate(target_without_moving)
                    )
                    tracks.append(
                        track.model_copy(update={"assignments": normalized})
                    )
                    continue

                if track.track_uid == source_track_uid:
                    remaining = tuple(
                        item.model_copy(update={"stack_index": index})
                        for index, item in enumerate(
                            item
                            for item in track.assignments
                            if item.assignment_uid != command.assignment_uid
                        )
                    )
                    tracks.append(
                        track.model_copy(update={"assignments": remaining})
                    )
                    continue

                tracks.append(track)

            return session.model_copy(
                update={
                    "tracks": tuple(tracks),
                    "curve_fills": tuple(
                        rule for rule in session.curve_fills
                        if rule.curve_a_assignment_uid != command.assignment_uid
                        and rule.curve_b_assignment_uid != command.assignment_uid
                    ),
                    "selected_track_uid": command.target_track_uid,
                }
            )

        return self._execute(managed_well_uid, command, mutate)
