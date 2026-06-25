from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.identity import new_uuid7_str
from app.wdv_session.canonical_command_router import get_service, router
from app.wdv_session.canonical_command_service import (
    CanonicalWdvCommandError,
    CanonicalWdvCommandService,
)
from app.wdv_session.canonical_commands import (
    BootstrapCurveAssignmentCommand,
    CreateTrackCommand,
)
from app.wdv_session.canonical_service import (
    CanonicalSessionRevisionConflict,
    CanonicalWdvSessionService,
)


class FakeResolver:
    def __init__(self, well_uid: str, curve_uid: str) -> None:
        self.well_uid = well_uid
        self.curve_uid = curve_uid
        self.product_uid = new_uuid7_str()
        self.source_uid = new_uuid7_str()

    def resolve_curve(self, managed_well_uid: str, managed_curve_uid: str):
        assert managed_well_uid == self.well_uid
        assert managed_curve_uid == self.curve_uid
        return SimpleNamespace(
            managed_well_uid=self.well_uid,
            managed_curve_uid=self.curve_uid,
            managed_product_uid=self.product_uid,
            managed_source_uid=self.source_uid,
            managed_wellbore_uid=None,
            product=SimpleNamespace(
                kr_curve_type_id="density",
                observed_mnemonic="RHOZ",
                curve_name="RHOZ",
                display_name="Bulk Density",
                normalized_mnemonic="RHOZ",
                curve_family="density",
                curve_unit="G/C3",
            ),
        )


def governed_density_policy(_product):
    return {
        "min": 1.95,
        "max": 2.95,
        "type": "linear",
        "direction": "normal",
        "source": "managed_knowledge_family_default",
    }


def build_service(tmp_path: Path, well_uid: str, curve_uid: str):
    sessions = CanonicalWdvSessionService(
        tmp_path / "sessions.json",
        policy_revision_fn=lambda: "policy-revision-test",
    )
    service = CanonicalWdvCommandService(
        session_service=sessions,
        resolver=FakeResolver(well_uid, curve_uid),
        policy_revision_fn=lambda: "policy-revision-test",
        display_policy_resolver=governed_density_policy,
    )
    return sessions, service


def test_empty_session_bootstrap_creates_track_and_assignment_atomically(
    tmp_path: Path,
) -> None:
    well_uid = new_uuid7_str()
    curve_uid = new_uuid7_str()
    sessions, service = build_service(tmp_path, well_uid, curve_uid)

    initial = sessions.get_session(well_uid)
    result = service.bootstrap_assignment(
        well_uid,
        BootstrapCurveAssignmentCommand(
            expected_revision=initial.revision,
            managed_curve_uid=curve_uid,
        ),
    )

    assert result.revision == initial.revision + 1
    assert result.state_status == "active"
    assert result.selected_track_uid == result.tracks[0].track_uid
    assert len(result.tracks) == 1

    track = result.tracks[0]
    assert track.track_type == "curve"
    assert track.track_number == 0
    assert track.track_name == "Bulk Density"
    assert track.lattice == "linear"
    assert len(track.assignments) == 1

    assignment = track.assignments[0]
    assert assignment.track_uid == track.track_uid
    assert assignment.managed_curve_uid == curve_uid
    assert assignment.stack_index == 0
    assert assignment.scale_min == 1.95
    assert assignment.scale_max == 2.95
    assert assignment.scale_type == "linear"
    assert assignment.scale_direction == "normal"
    assert assignment.source == "canonical_empty_session_bootstrap"
    assert result.display_policy_revision == "policy-revision-test"

    persisted = sessions.get_session(well_uid)
    assert persisted == result


def test_bootstrap_rejects_nonempty_session_and_stale_revision(tmp_path: Path) -> None:
    well_uid = new_uuid7_str()
    curve_uid = new_uuid7_str()
    sessions, service = build_service(tmp_path, well_uid, curve_uid)

    initial = sessions.get_session(well_uid)
    existing = service.create_track(
        well_uid,
        CreateTrackCommand(
            expected_revision=initial.revision,
            track_name="Existing",
        ),
    )

    with pytest.raises(CanonicalWdvCommandError):
        service.bootstrap_assignment(
            well_uid,
            BootstrapCurveAssignmentCommand(
                expected_revision=existing.revision,
                managed_curve_uid=curve_uid,
            ),
        )

    second_well_uid = new_uuid7_str()
    second_curve_uid = new_uuid7_str()
    second_sessions, second_service = build_service(
        tmp_path / "second",
        second_well_uid,
        second_curve_uid,
    )
    second_initial = second_sessions.get_session(second_well_uid)
    second_service.bootstrap_assignment(
        second_well_uid,
        BootstrapCurveAssignmentCommand(
            expected_revision=second_initial.revision,
            managed_curve_uid=second_curve_uid,
        ),
    )
    with pytest.raises(CanonicalSessionRevisionConflict):
        second_service.bootstrap_assignment(
            second_well_uid,
            BootstrapCurveAssignmentCommand(
                expected_revision=second_initial.revision,
                managed_curve_uid=second_curve_uid,
            ),
        )


def test_bootstrap_endpoint_returns_canonical_session(tmp_path: Path) -> None:
    well_uid = new_uuid7_str()
    curve_uid = new_uuid7_str()
    _sessions, service = build_service(tmp_path, well_uid, curve_uid)

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_service] = lambda: service
    client = TestClient(app)

    response = client.post(
        f"/api/wlv/v2/wdv/session-commands/{well_uid}/assignments/bootstrap",
        json={
            "expected_revision": 0,
            "managed_curve_uid": curve_uid,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["state_status"] == "active"
    assert payload["revision"] == 1
    assert payload["tracks"][0]["assignments"][0]["managed_curve_uid"] == curve_uid


def test_product_openapi_registers_bootstrap_endpoint() -> None:
    from app.main import app as product_app

    client = TestClient(product_app)
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert (
        "/api/wlv/v2/wdv/session-commands/{managed_well_uid}/assignments/bootstrap"
        in response.json()["paths"]
    )
