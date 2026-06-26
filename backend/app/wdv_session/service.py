"""Backend-owned WDV layout/session state service."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from .models import (
    WDV_SESSION_LAYOUT_CONTRACT_VERSION,
    WdvSessionCurveAssignmentState,
    WdvSessionCurveAssignmentView,
    WdvSessionLayoutPutRequest,
    WdvSessionLayoutStateResponse,
    WdvSessionLayoutStateView,
    WdvSessionTrackLayoutView,
)


def _to_assignment_view(
    a: "WdvSessionCurveAssignmentState",
) -> "WdvSessionCurveAssignmentView":
    from app.wdv_display.number_format import format_scale_value

    scale_min = a.scale_min
    scale_max = a.scale_max

    # Read-time repair for stored log assignments with a non-positive scale_min.
    #
    # Background: the _add_visual_variation_diagnostics heuristic previously
    # overrode log-type governed ranges (e.g. resistivity 0.2–2000) with
    # padded observed statistics when the linear visual_span_ratio < 0.08.
    # This could produce a negative scale_min (e.g. -3.76 for Forge AT30),
    # which is persisted in session_layouts.json and is invalid for log
    # rendering.  That heuristic is now guarded against log-type scales, but
    # existing stored sessions still carry the bad values.
    #
    # Contract:
    #   - Triggered only when scale_type == "log" and scale_min <= 0.
    #   - Re-resolves the governed display policy from stored curve metadata
    #     (curve_family, unit, mnemonic) with no observed-stats override.
    #   - Returns the governed numeric bounds and backend-formatted labels.
    #   - Does NOT mutate session_layouts.json; the repaired values exist only
    #     in the outbound response DTO.  Persistence follows the normal explicit
    #     PUT /layout save path.
    if (
        a.scale_type == "log"
        and scale_min is not None
        and float(scale_min) <= 0
    ):
        from app.inventory.models import ManagedProductGroupItem
        from app.wdv_display.policy_service import WdvCurveDisplayPolicyService

        item = ManagedProductGroupItem(
            product_id=a.curve_id,
            display_name=a.display_name or a.mnemonic or a.curve_id,
            curve_name=a.mnemonic or a.curve_id,
            curve_type="curve",
            curve_unit=a.unit or "",
            curve_family=a.curve_family or "Unclassified",
            selectable=True,
        )
        # No sample stats: policy returns the pure governed range (e.g. 0.2–2000
        # for resistivity) without any low_visual_variation override.
        governed = WdvCurveDisplayPolicyService.resolve(item, {})
        scale_min = float(governed["min"])
        scale_max = float(governed["max"])

    dump = a.model_dump()
    dump["scale_min"] = scale_min
    dump["scale_max"] = scale_max
    dump["scale_min_label"] = (
        format_scale_value(float(scale_min)) if scale_min is not None else None
    )
    dump["scale_max_label"] = (
        format_scale_value(float(scale_max)) if scale_max is not None else None
    )
    return WdvSessionCurveAssignmentView(**dump)


def _to_layout_view(
    session: "WdvSessionLayoutStateResponse",
) -> "WdvSessionLayoutStateView":
    return WdvSessionLayoutStateView(
        **session.model_dump(exclude={"tracks"}),
        tracks=[
            WdvSessionTrackLayoutView(
                **track.model_dump(exclude={"curves"}),
                curves=[_to_assignment_view(a) for a in track.curves],
            )
            for track in session.tracks
        ],
    )


class WdvSessionLayoutStateService:
    """Durable local backend-owned WDV layout/session state service.

    This is intentionally lightweight JSON storage for the local/dev profile,
    but the contract and service boundary are enterprise-shaped: callers use
    a backend API and do not depend on frontend-local layout truth.
    """

    _lock = RLock()

    def __init__(self, storage_path: Path | None = None) -> None:
        self.storage_path = storage_path or self.default_storage_path()

    @staticmethod
    def default_storage_path() -> Path:
        override = os.environ.get("WLV_WDV_SESSION_LAYOUT_STORE")
        if override:
            return Path(override).expanduser().resolve()
        return Path(__file__).resolve().parents[3] / "data" / "wdv" / "session_layouts.json"

    def get_layout(self, managed_well_id: str) -> WdvSessionLayoutStateView:
        data = self._read_store()
        session = data.get("sessions", {}).get(managed_well_id)
        if not session:
            return _to_layout_view(self._empty_session(managed_well_id))
        return _to_layout_view(WdvSessionLayoutStateResponse.model_validate(session))

    def put_layout(
        self,
        managed_well_id: str,
        request: WdvSessionLayoutPutRequest,
    ) -> WdvSessionLayoutStateView:
        self._validate_layout_request(request)
        with self._lock:
            data = self._read_store()
            sessions = data.setdefault("sessions", {})
            current_revision = int(sessions.get(managed_well_id, {}).get("revision", 0) or 0)
            layout_tracks = self._normalise_persisted_tracks(request.tracks)
            selected_track_id = request.selected_track_id if layout_tracks else None
            existing_session = sessions.get(managed_well_id, {})
            session = WdvSessionLayoutStateResponse(
                managed_well_id=managed_well_id,
                managed_well_uid=request.managed_well_uid or existing_session.get("managed_well_uid"),
                layout_session_id=f"wdv_layout_session:{managed_well_id}",
                revision=current_revision + 1,
                state_status="active" if layout_tracks else "empty",
                source=request.source,
                updated_at=self._now(),
                selected_track_id=selected_track_id,
                tracks=layout_tracks,
                warnings=[],
            )
            sessions[managed_well_id] = session.model_dump(mode="json")
            self._write_store(data)
            return _to_layout_view(session)

    def clear_layout(self, managed_well_id: str, reason: str = "user_requested_clear") -> WdvSessionLayoutStateView:
        with self._lock:
            data = self._read_store()
            sessions = data.setdefault("sessions", {})
            current_revision = int(sessions.get(managed_well_id, {}).get("revision", 0) or 0)
            existing_session = sessions.get(managed_well_id, {})
            session = WdvSessionLayoutStateResponse(
                managed_well_id=managed_well_id,
                managed_well_uid=existing_session.get("managed_well_uid"),
                layout_session_id=f"wdv_layout_session:{managed_well_id}",
                revision=current_revision + 1,
                state_status="cleared",
                source=reason,
                updated_at=self._now(),
                selected_track_id=None,
                tracks=[],
                warnings=[],
            )
            sessions[managed_well_id] = session.model_dump(mode="json")
            self._write_store(data)
            return _to_layout_view(session)

    def _empty_session(self, managed_well_id: str) -> WdvSessionLayoutStateResponse:
        return WdvSessionLayoutStateResponse(
            managed_well_id=managed_well_id,
            layout_session_id=f"wdv_layout_session:{managed_well_id}",
            revision=0,
            state_status="empty",
            source="backend_owned_session_state",
            updated_at=self._now(),
            selected_track_id=None,
            tracks=[],
            warnings=[],
        )

    def _read_store(self) -> dict[str, Any]:
        if not self.storage_path.exists():
            return {"schema_version": WDV_SESSION_LAYOUT_CONTRACT_VERSION, "sessions": {}}
        try:
            raw = json.loads(self.storage_path.read_text())
        except json.JSONDecodeError:
            return {"schema_version": WDV_SESSION_LAYOUT_CONTRACT_VERSION, "sessions": {}}
        if not isinstance(raw, dict):
            return {"schema_version": WDV_SESSION_LAYOUT_CONTRACT_VERSION, "sessions": {}}
        raw.setdefault("schema_version", WDV_SESSION_LAYOUT_CONTRACT_VERSION)
        raw.setdefault("sessions", {})
        return raw

    def _write_store(self, data: dict[str, Any]) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data["schema_version"] = WDV_SESSION_LAYOUT_CONTRACT_VERSION
        data.setdefault("sessions", {})
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=str(self.storage_path.parent),
            delete=False,
        ) as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
            tmp_name = handle.name
        Path(tmp_name).replace(self.storage_path)

    @staticmethod
    def _normalise_persisted_tracks(tracks: list[Any]) -> list[Any]:
        """Persist only renderable WDV template/track content.

        A depth/reference track by itself is not a populated WDV section.
        Empty curve tracks are also not restorable display content.  This
        prevents a cleared viewer from relaunching with an inherited depth
        track and no curve section.
        """
        has_curve_assignment = any(
            getattr(track, "track_type", None) == "curve" and bool(getattr(track, "curves", None))
            for track in tracks
        )
        return tracks if has_curve_assignment else []

    def _validate_layout_request(self, request: WdvSessionLayoutPutRequest) -> None:
        track_ids: set[str] = set()
        assignment_ids: set[str] = set()
        for track in request.tracks:
            if track.track_id in track_ids:
                raise ValueError(f"Duplicate WDV track_id in layout request: {track.track_id}")
            track_ids.add(track.track_id)
            for curve in track.curves:
                if curve.assignment_id in assignment_ids:
                    raise ValueError(f"Duplicate WDV assignment_id in layout request: {curve.assignment_id}")
                assignment_ids.add(curve.assignment_id)
        if request.selected_track_id and request.selected_track_id not in track_ids:
            raise ValueError("selected_track_id must refer to a track in the supplied layout")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
