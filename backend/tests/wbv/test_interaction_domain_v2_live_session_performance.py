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
        self.get_count = 0
        self.upsert_count = 0

    def get_record(self, managed_well_id: str):
        self.get_count += 1
        return self.record

    def upsert_record(self, record):
        self.upsert_count += 1
        self.record = record
        return record


_OBSERVATION = WbvScreenObservationV2(
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


def _point(index: int) -> WbvAuthoritativePointV2:
    value = float(index)
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


def _service(monkeypatch):
    initial = WbvInteractionStateV2(
        managed_well_id="managed-well:test",
        revision=10,
        selection_mode="point",
        selected_point_visible=True,
        updated_at=utc_now_iso(),
    )
    repository = _FakeRepository(initial)
    provider = lambda _: SimpleNamespace(
        trajectory=SimpleNamespace(
            render_points=[
                {"md": 0, "tvd": 0, "x": 0, "y": 0, "z": 0},
                {"md": 100, "tvd": 100, "x": 0, "y": 0, "z": -100},
            ]
        )
    )
    service = WbvInteractionDomainService(repository, trajectory_package_provider=provider)
    counter = {"value": 0}

    def project(*args, **kwargs):
        counter["value"] += 1
        return _point(counter["value"])

    monkeypatch.setattr(
        "app.wbv.interaction_domain.service.project_observation",
        project,
    )
    return service, repository


def test_live_tracking_updates_do_not_persist_each_sample(monkeypatch):
    service, repository = _service(monkeypatch)

    started = service.start_tracking(
        "managed-well:test",
        WbvTrackSessionCommandV2(
            sequence=1,
            observation=_OBSERVATION,
            expected_revision=10,
        ),
    )
    assert repository.upsert_count == 1

    state = started
    for sequence in range(2, 122):
        state = service.update_tracking(
            "managed-well:test",
            WbvTrackSessionCommandV2(
                session_id=started.active_tracking_session_id,
                sequence=sequence,
                observation=_OBSERVATION,
            ),
        )

    assert repository.upsert_count == 1
    assert state.revision == started.revision + 120
    assert state.tracking_status == "tracking"
    assert service.get("managed-well:test").selected_point == state.selected_point

    committed = service.commit_tracking(
        "managed-well:test",
        WbvTrackSessionCommandV2(
            session_id=started.active_tracking_session_id,
            sequence=122,
            observation=_OBSERVATION,
        ),
    )

    assert repository.upsert_count == 2
    assert committed.tracking_status == "committed"
    assert committed.active_tracking_session_id is None


def test_stale_sequence_does_not_mutate_or_persist(monkeypatch):
    service, repository = _service(monkeypatch)
    started = service.start_tracking(
        "managed-well:test",
        WbvTrackSessionCommandV2(
            sequence=5,
            observation=_OBSERVATION,
            expected_revision=10,
        ),
    )

    stale = service.update_tracking(
        "managed-well:test",
        WbvTrackSessionCommandV2(
            session_id=started.active_tracking_session_id,
            sequence=5,
            observation=_OBSERVATION,
        ),
    )

    assert stale.fallback_status == "stale_command"
    assert repository.upsert_count == 1
    assert service.get("managed-well:test").revision == started.revision


def test_cancel_restores_starting_point_and_persists_once(monkeypatch):
    service, repository = _service(monkeypatch)
    started = service.start_tracking(
        "managed-well:test",
        WbvTrackSessionCommandV2(
            sequence=1,
            observation=_OBSERVATION,
            expected_revision=10,
        ),
    )
    service.update_tracking(
        "managed-well:test",
        WbvTrackSessionCommandV2(
            session_id=started.active_tracking_session_id,
            sequence=2,
            observation=_OBSERVATION,
        ),
    )

    cancelled = service.cancel_tracking(
        "managed-well:test",
        WbvTrackSessionCommandV2(
            session_id=started.active_tracking_session_id,
            sequence=3,
        ),
    )

    assert repository.upsert_count == 2
    assert cancelled.tracking_status == "cancelled"
    assert cancelled.active_tracking_session_id is None
    assert cancelled.selected_point is None
