"""Compile an independently retained WBV publication into the existing WBV render contract."""
from __future__ import annotations

import math
from collections.abc import Callable

from app.identity.wdv_contract_v2 import WdvCurveSampleRequest, WdvCurveSampleResponse
from app.inventory.canonical_curve_sample_service import CanonicalCurveSampleService
from app.wbv_layout.service import WbvTrackLayoutService
from app.wbv.models import (
    WbvCurveOverlayRenderContract,
    WbvCurveOverlayRenderCurve,
    WbvCurveOverlayRenderSample,
    WbvTrackConfiguration,
)

from .models import WbvOverlayPackage

SampleProvider = Callable[[WdvCurveSampleRequest], WdvCurveSampleResponse]


class WbvPublishedPackageRenderAdapter:
    """Pure adapter from retained WDV semantics to the established WBV renderer payload."""

    def __init__(self, sample_provider: SampleProvider | None = None, layout_service: WbvTrackLayoutService | None = None) -> None:
        service = CanonicalCurveSampleService()
        self._sample_provider = sample_provider or service.get_curve_samples
        self._layout_service = layout_service

    def compile(self, package: WbvOverlayPackage, *, max_samples: int = 12000) -> WbvCurveOverlayRenderContract:
        snapshot = package.published_snapshot
        track_override = {item.track_uid: item for item in package.wbv_overrides.tracks}
        curve_override = {item.assignment_uid: item for item in package.wbv_overrides.curves}
        assignments = {
            item.assignment_uid: item
            for track in snapshot.tracks
            for item in track.assignments
        }
        fill_rules_by_curve_a: dict[str, list[object]] = {}
        for rule in snapshot.curve_fills:
            if not rule.enabled:
                continue
            fill_rules_by_curve_a.setdefault(
                rule.curve_a_assignment_uid,
                [],
            ).append(rule)
        for rules in fill_rules_by_curve_a.values():
            rules.sort(key=lambda rule: int(rule.order))

        if self._layout_service is not None:
            layout = self._layout_service.get_layout(package.managed_well_uid)
            layout_tracks = list(layout.tracks)
        else:
            from app.wbv_layout.models import WbvLayoutTrack
            layout_tracks = []
            for order, source in enumerate(item for item in snapshot.tracks if item.track_type == "curve"):
                source_override = track_override.get(source.track_uid)
                layout_tracks.append(WbvLayoutTrack(
                    track_uid=(source_override.destination_track_uid if source_override and source_override.destination_track_uid else source.track_uid),
                    display_name=source.track_name,
                    track_type="curve",
                    display_order=order,
                    visible=True,
                    position="right",
                    angular_position_deg=(source_override.angular_position_deg if source_override and source_override.angular_position_deg is not None else 0.0),
                    distance_from_wellbore=(source_override.radial_offset if source_override and source_override.radial_offset is not None else 0.15),
                    width=(source_override.radial_width if source_override and source_override.radial_width is not None else 1.0),
                    opacity=1.0,
                ))
        layout_by_uid = {item.track_uid: item for item in layout_tracks}
        resolved_offsets: dict[str, float] = {}
        for position in ("right", "left", "center"):
            position_tracks = [
                item
                for item in layout_tracks
                if item.position == position
            ]
            previous = None
            for item in position_tracks:
                if previous is None:
                    resolved_offsets[item.track_uid] = item.distance_from_wellbore
                else:
                    resolved_offsets[item.track_uid] = (
                        resolved_offsets[previous.track_uid]
                        + previous.width
                        + item.previous_track_gap
                    )
                previous = item

        tracks: list[WbvTrackConfiguration] = []
        for item in layout_tracks:
            if item.track_type != "curve" or not item.visible:
                continue
            source_override = next((value for value in track_override.values() if value.destination_track_uid == item.track_uid), None)
            if source_override is None and self._layout_service is None:
                source_override = track_override.get(item.track_uid)
            tracks.append(WbvTrackConfiguration(
                track_id=item.track_uid, display_name=item.display_name, track_type="curve", display_order=item.display_order,
                side=item.position,
                geometry_type=(source_override.geometry_type if source_override is not None else "radial_panel"),
                radial_lane=(source_override.radial_lane if source_override and source_override.radial_lane is not None else item.display_order),
                angular_position_deg=item.angular_position_deg,
                orientation_mode="camera_facing",
                thickness=(source_override.thickness if source_override and source_override.thickness is not None else 0.05),
                width=item.width,
                background_mode=("custom" if item.background_mode == "solid" else "transparent"),
                background_color=item.background_color,
                background_opacity=(item.opacity if item.background_mode == "solid" else 0.0),
                border_visible=item.outline_visible,
                border_color="#5f6d73",
                grid_mode=item.grid_mode,
                grid_color="#44545d",
                wellbore_offset=resolved_offsets.get(item.track_uid, item.distance_from_wellbore),
                previous_track_gap=item.previous_track_gap,
            ))
        curves: list[WbvCurveOverlayRenderCurve] = []
        curve_tracks = [item for item in snapshot.tracks if item.track_type == "curve"]
        for order, track in enumerate(curve_tracks):
            override = track_override.get(track.track_uid)
            if override is not None and not override.visible:
                continue
            destination_uid = override.destination_track_uid if override and override.destination_track_uid else (track.track_uid if self._layout_service is None else None)
            destination = layout_by_uid.get(destination_uid) if destination_uid else None
            if destination is None or destination.track_type != "curve" or not destination.visible:
                continue
            lane = destination.display_order
            radial_distance = resolved_offsets.get(
                destination.track_uid,
                destination.distance_from_wellbore,
            )
            for assignment in track.assignments:
                override_curve = curve_override.get(assignment.assignment_uid)
                if not assignment.visible or not assignment.line_visible:
                    continue
                if override_curve is not None and override_curve.visible is False:
                    continue
                if assignment.scale_min is None or assignment.scale_max is None:
                    continue
                response = self._sample_provider(WdvCurveSampleRequest(
                    managed_well_uid=package.managed_well_uid,
                    managed_curve_uid=assignment.managed_curve_uid,
                    sample_revision=str(package.source_wdv_revision),
                    max_samples=max_samples,
                ))
                low = min(float(assignment.scale_min), float(assignment.scale_max))
                high = max(float(assignment.scale_min), float(assignment.scale_max))
                logarithmic = assignment.scale_type == "logarithmic"
                reversed_scale = assignment.scale_direction == "reversed"
                samples: list[WbvCurveOverlayRenderSample] = []
                for md, value in response.samples:
                    normalized = self._normalize(float(value), low, high, logarithmic)
                    if normalized is None:
                        continue
                    if reversed_scale:
                        normalized = 1.0 - normalized
                    samples.append(WbvCurveOverlayRenderSample(md=float(md), value=float(value), normalized=normalized))

                (
                    fill_mode,
                    target_product_uid,
                    fill_color,
                    fill_opacity,
                    baseline,
                ) = self._resolve_fill(
                    fill_rules_by_curve_a.get(
                        assignment.assignment_uid,
                        [],
                    ),
                    assignments,
                    default_color=(
                        assignment.fill_color
                        or assignment.color
                        or "#58d39b"
                    ),
                    default_opacity=assignment.fill_opacity / 100.0,
                )

                opacity = assignment.line_opacity / 100.0
                if override_curve is not None and override_curve.opacity is not None:
                    opacity = override_curve.opacity
                if override is not None and override.opacity is not None:
                    opacity *= override.opacity
                opacity *= destination.opacity
                line_width = assignment.line_width or 1.5
                if override_curve is not None and override_curve.line_width is not None:
                    line_width = override_curve.line_width
                radial_width = 1.0
                if override_curve is not None and override_curve.radial_exaggeration is not None:
                    radial_width = override_curve.radial_exaggeration
                else:
                    radial_width = destination.width

                curves.append(WbvCurveOverlayRenderCurve(
                    assignment_uid=assignment.assignment_uid,
                    curve_product_id=assignment.managed_product_uid,
                    display_name=assignment.display_name,
                    mnemonic=assignment.observed_mnemonic,
                    unit=assignment.unit,
                    display_order=assignment.stack_index,
                    radial_lane=lane,
                    track_id=destination.track_uid,
                    radial_width=radial_width,
                    color=(
                        override_curve.color
                        if override_curve is not None and override_curve.color is not None
                        else assignment.color or "#58d39b"
                    ),
                    line_width=float(line_width),
                    opacity=float(opacity),
                    label_visible=bool(override_curve.label_visible) if override_curve is not None and override_curve.label_visible is not None else False,
                    label_content=override_curve.label_content if override_curve is not None and override_curve.label_content is not None else "mnemonic",
                    label_anchor=override_curve.label_anchor if override_curve is not None and override_curve.label_anchor is not None else "top",
                    label_custom_md=override_curve.label_custom_md if override_curve is not None else None,
                    label_size=override_curve.label_size if override_curve is not None and override_curve.label_size is not None else 1.0,
                    label_weight=override_curve.label_weight if override_curve is not None and override_curve.label_weight is not None else 800,
                    label_alignment=override_curve.label_alignment if override_curve is not None and override_curve.label_alignment is not None else "center",
                    label_position=override_curve.label_position if override_curve is not None and override_curve.label_position is not None else "on_track",
                    label_horizontal_adjustment=override_curve.label_horizontal_adjustment if override_curve is not None and override_curve.label_horizontal_adjustment is not None else 0.0,
                    label_vertical_adjustment=override_curve.label_vertical_adjustment if override_curve is not None and override_curve.label_vertical_adjustment is not None else 0.0,
                    scale_color=override_curve.scale_color if override_curve is not None and override_curve.scale_color is not None else "#b7c5d0",
                    scale_opacity=override_curve.scale_opacity if override_curve is not None and override_curve.scale_opacity is not None else 1.0,
                    scale_line_width=override_curve.scale_line_width if override_curve is not None and override_curve.scale_line_width is not None else 1.0,
                    scale_size=override_curve.scale_size if override_curve is not None and override_curve.scale_size is not None else 1.0,
                    fill_mode=fill_mode,
                    fill_target_curve_product_id=target_product_uid,
                    fill_color=fill_color,
                    fill_opacity=fill_opacity,
                    fill_outline=True,
                    baseline_normalized=baseline,
                    display_min=float(assignment.scale_min),
                    display_max=float(assignment.scale_max),
                    scale_type=assignment.scale_type or "linear",
                    display_direction=assignment.scale_direction or "normal",
                    range_source=assignment.effective_range_source,
                    policy_revision=snapshot.display_policy_revision,
                    provenance={
                        "intent_source": "published_wdv_overlay_package",
                        "package_uid": package.package_uid,
                        "package_revision": package.package_revision,
                        "source_wdv_session_uid": package.source_wdv_session_uid,
                        "source_wdv_revision": package.source_wdv_revision,
                        "assignment_uid": assignment.assignment_uid,
                        "managed_curve_uid": assignment.managed_curve_uid,
                    },
                    samples=samples,
                ))

        curves.sort(key=lambda item: (item.radial_lane, item.display_order, item.mnemonic.casefold()))
        return WbvCurveOverlayRenderContract(
            managed_well_id=package.managed_well_uid,
            track_spacing=package.wbv_overrides.track_spacing or 0.05,
            tracks=tracks,
            curves=curves,
        )

    @staticmethod
    def _resolve_fill(
        rules,
        assignments,
        *,
        default_color: str,
        default_opacity: float,
    ) -> tuple[str, str | None, str, float, float]:
        """Resolve one curve's render fill without mutating other curve rules.

        A density-neutron crossover is compiled on its source curve as a
        between-curves fill. A separate NPHI boundary rule remains compiled on
        NPHI independently.
        """
        fill_mode = "none"
        target_product_uid = None
        fill_color = default_color
        fill_opacity = default_opacity
        baseline = 0.0

        for rule in rules:
            rule_type = rule.rule_type.value
            if rule_type in {"between_curves", "crossover"}:
                target = assignments.get(
                    rule.curve_b_assignment_uid or ""
                )
                if target is None:
                    continue
                fill_mode = rule_type
                target_product_uid = target.managed_product_uid
                fill_color = rule.style.color
                fill_opacity = float(rule.style.opacity)
                break
            if rule_type == "to_boundary":
                fill_mode = "to_baseline"
                fill_color = rule.style.color
                fill_opacity = float(rule.style.opacity)
                baseline = (
                    0.0
                    if getattr(rule.boundary, "value", None) == "left"
                    else 1.0
                )
                break

        return (
            fill_mode,
            target_product_uid,
            fill_color,
            fill_opacity,
            baseline,
        )

    @staticmethod
    def _normalize(value: float, low: float, high: float, logarithmic: bool) -> float | None:
        if high <= low:
            return None
        if logarithmic:
            if value <= 0 or low <= 0 or high <= 0:
                return None
            ratio = (math.log10(value) - math.log10(low)) / (math.log10(high) - math.log10(low))
        else:
            ratio = (value - low) / (high - low)
        return max(0.0, min(1.0, ratio))
