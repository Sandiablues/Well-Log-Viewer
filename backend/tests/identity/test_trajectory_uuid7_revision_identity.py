from app.inventory.identity_reconciliation import reconcile_managed_record_identity
from app.inventory.models import ManagedSourceKind, ManagedSourceReference, ManagedWellRecord
from app.identity import parse_uuid7
from app.wbv.models import WbvManagedTrajectoryRecord


def _record(package_value: int, *, existing_uid: str | None = None) -> ManagedWellRecord:
    trajectory = {
        "trajectory_id": "traj:source-intake:abc",
        "managed_trajectory_uid": existing_uid,
        "trajectory_name": "Deviation survey",
        "source_file_id": "occ:abc",
        "status": "approved",
        "wbv_eligible": True,
        "trajectory_package": {"render_points": [{"md": 0, "x": package_value}]},
    }
    return ManagedWellRecord(
        managed_well_id="managed-well:a",
        well_id="well:a",
        well_name="A",
        source_references=[
            ManagedSourceReference(
                source_id="occ:abc",
                source_kind=ManagedSourceKind.DOCUMENT,
                display_name="survey.csv",
            )
        ],
        metadata={"wbv_trajectory_records": [trajectory], "active_trajectory_id": "traj:source-intake:abc"},
    )


def _trajectory(record: ManagedWellRecord) -> WbvManagedTrajectoryRecord:
    return WbvManagedTrajectoryRecord(**record.metadata["wbv_trajectory_records"][0])


def test_first_upsert_assigns_distinct_trajectory_revision_and_representation_uids() -> None:
    saved = reconcile_managed_record_identity(_record(1))
    trajectory = _trajectory(saved)
    parse_uuid7(trajectory.managed_trajectory_uid)
    parse_uuid7(trajectory.trajectory_revision_uid)
    parse_uuid7(trajectory.representation_uid)
    parse_uuid7(trajectory.source_occurrence_uid)
    assert len({trajectory.managed_trajectory_uid, trajectory.trajectory_revision_uid, trajectory.representation_uid}) == 3
    assert trajectory.revision_number == 1
    assert saved.metadata["active_trajectory_uid"] == trajectory.managed_trajectory_uid


def test_repeat_upsert_reuses_all_identity_for_same_revision() -> None:
    first = reconcile_managed_record_identity(_record(1))
    second = reconcile_managed_record_identity(_record(1), existing=first)
    a = _trajectory(first)
    b = _trajectory(second)
    assert b.managed_trajectory_uid == a.managed_trajectory_uid
    assert b.trajectory_revision_uid == a.trajectory_revision_uid
    assert b.representation_uid == a.representation_uid
    assert b.revision_number == 1


def test_changed_package_preserves_trajectory_but_creates_new_revision_and_representation() -> None:
    first = reconcile_managed_record_identity(_record(1))
    second = reconcile_managed_record_identity(_record(2), existing=first)
    a = _trajectory(first)
    b = _trajectory(second)
    assert b.managed_trajectory_uid == a.managed_trajectory_uid
    assert b.trajectory_revision_uid != a.trajectory_revision_uid
    assert b.representation_uid != a.representation_uid
    assert b.revision_number == 2
    assert b.supersedes_trajectory_revision_uid == a.trajectory_revision_uid


def test_legacy_trajectory_record_remains_readable_without_generated_uid() -> None:
    raw = WbvManagedTrajectoryRecord(
        trajectory_id="legacy",
        trajectory_name="Legacy",
    )
    assert raw.managed_trajectory_uid is None
    assert raw.trajectory_revision_uid is None
    assert raw.representation_uid is None
