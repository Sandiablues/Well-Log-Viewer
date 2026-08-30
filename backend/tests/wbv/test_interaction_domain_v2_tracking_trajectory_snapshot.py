from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from app.inventory.models import utc_now_iso
from app.wbv.interaction_domain.contracts import (
    WbvAuthoritativePointV2,
    WbvInteractionStateV2,
    WbvScreenObservationV2,
    WbvTrackSessionCommandV2,
)
from app.wbv.interaction_domain.service import WbvInteractionDomainService


@dataclass
class _FakeRecord:
    metadata: dict
    updated_at: str = ""

    def model_copy(self, update):
        return _FakeRecord(
            metadata=update.get("metadata", self.metadata),
            updated_at=update.get("updated_at", self.updated_at),
        )


class _FakeRepository:
    def __init__(self, state: WbvInteractionStateV2):
        payload = state.model_dump(mode="json")
        payload.pop("managed_well_id", None)
        self.record = _FakeRecord(metadata={"wbv_interaction_state_v2": payload})

    def get_record(self, managed_well_id: str):
        return self.record

    def upsert_record(self, record):
        self.record = record
        return record


OBSERVATION = WbvScreenObservationV2(
    pointer_x_px=50,
    pointer_y_px=50,
    viewport_width_px=100,
    viewport_height_px=100,
    view_projection_matrix=[
        1, 0, 0, 0,
        0, 1, 0, 0,
        0, 0, 1, 0,
        0, 0, 0, 1,
    ],
    activation_tolerance_px=20,
)


def _point(sequence: int) -> WbvAuthoritativePointV2:
    value = float(sequence)
    return WbvAuthoritativePointV2(
        md=value,
        tvd=value,
        x=0,
        y=0,
        z=-value,
        segment_index=0,
        segment_ratio=0.5,
        screen_distance_px=0,
    )


def test_tracking_session_reuses_one_authoritative_trajectory_snapshot(monkeypatch):
    initial = WbvInteractionStateV2(
        managed_well_id="managed-well:test",
        revision=10,
        selection_mode="point",
        selected_point_visible=True,
        updated_at=utc_now_iso(),
    )
    repository = _FakeRepository(initial)
    provider_calls = {"count": 0}

    def provider(_managed_well_id: str):
        provider_calls["count"] += 1
        return SimpleNamespace(
            trajectory=SimpleNamespace(
                render_points=[
                    {"md": 0, "tvd": 0, "x": 0, "y": 0, "z": 0},
                    {"md": 100, "tvd": 100, "x": 0, "y": 0, "z": -100},
                ]
            )
        )

    projection_calls = {"count": 0}

    def project(points, observation, **kwargs):
        projection_calls["count"] += 1
        assert isinstance(points, tuple)
        assert len(points) == 2
        return _point(projection_calls["count"])

    monkeypatch.setattr(
        "app.wbv.interaction_domain.service.project_observation",
        project,
    )

    service = WbvInteractionDomainService(
        repository,
        trajectory_package_provider=provider,
    )

    started = service.start_tracking(
        "managed-well:test",
        WbvTrackSessionCommandV2(
            sequence=1,
            observation=OBSERVATION,
            expected_revision=10,
        ),
    )

    for sequence in range(2, 122):
        service.update_tracking(
            "managed-well:test",
            WbvTrackSessionCommandV2(
                session_id=started.active_tracking_session_id,
                sequence=sequence,
                observation=OBSERVATION,
            ),
        )

    service.commit_tracking(
        "managed-well:test",
        WbvTrackSessionCommandV2(
            session_id=started.active_tracking_session_id,
            sequence=122,
            observation=OBSERVATION,
        ),
    )

    assert provider_calls["count"] == 1
    assert projection_calls["count"] == 122
