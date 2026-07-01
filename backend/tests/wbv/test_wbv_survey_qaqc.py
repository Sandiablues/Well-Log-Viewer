from pathlib import Path

from app.inventory.models import ManagedSourceKind, ManagedSourceReference, ManagedWellRecord
from app.inventory.repository import ManagedWellInventoryRepository
from app.wbv.service import WbvService


def _record(managed_well_id: str, render_points: list[dict[str, float]]) -> ManagedWellRecord:
    return ManagedWellRecord(
        managed_well_id=managed_well_id,
        managed_well_uid="019f2000-0000-7000-8000-000000000004",
        well_id=managed_well_id.replace("managed-well:", ""),
        well_name="QAQC Test Well",
        source_references=[
            ManagedSourceReference(
                source_id=f"source:{managed_well_id}",
                source_kind=ManagedSourceKind.LAS,
                display_name="qaqc-test.las",
            )
        ],
        metadata={
            "wbv_trajectory_package": {
                "method": "minimum_curvature",
                "source": "deviation_survey",
                "station_count": len(render_points),
                "source_station_count": len(render_points),
                "render_points": render_points,
            }
        },
    )


def test_survey_qaqc_summary_is_added_to_viewer_package(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    repository.upsert_record(
        _record(
            "managed-well:qaqc-clean",
            [
                {"station_index": 0, "md": 0.0, "tvd": 0.0, "inclination": 0.0, "azimuth": 0.0, "dogleg_severity": 0.0},
                {"station_index": 1, "md": 100.0, "tvd": 99.9, "inclination": 1.0, "azimuth": 10.0, "dogleg_severity": 1.0},
            ],
        )
    )

    package = WbvService(repository=repository).get_viewer_package("managed-well:qaqc-clean")

    assert package.survey_qaqc.valid_point_count == 2
    assert package.survey_qaqc.md_monotonic is True
    assert package.survey_qaqc.tvd_monotonic is True
    assert package.survey_qaqc.max_station_gap == 100.0
    assert package.survey_qaqc.max_dogleg_severity == 1.0
    assert package.survey_qaqc.finding_count == 0


def test_survey_qaqc_detects_reversed_duplicate_and_invalid_angles(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    repository.upsert_record(
        _record(
            "managed-well:qaqc-bad",
            [
                {"station_index": 0, "md": 0.0, "tvd": 0.0, "inclination": 0.0, "azimuth": 0.0},
                {"station_index": 1, "md": 100.0, "tvd": 100.0, "inclination": 181.0, "azimuth": 360.0},
                {"station_index": 2, "md": 100.0, "tvd": 99.0, "inclination": 1.0, "azimuth": 20.0},
                {"station_index": 3, "md": 90.0, "tvd": 98.0, "inclination": 1.0, "azimuth": 20.0},
            ],
        )
    )

    summary = WbvService(repository=repository).get_survey_qaqc("managed-well:qaqc-bad").summary
    codes = {finding.code for finding in summary.findings}

    assert summary.md_monotonic is False
    assert summary.tvd_monotonic is False
    assert summary.duplicate_md_count == 1
    assert summary.reversed_md_count == 1
    assert summary.zero_length_interval_count == 1
    assert summary.invalid_inclination_count == 1
    assert summary.invalid_azimuth_count == 1
    assert {"duplicate_md", "reversed_md", "reversed_tvd", "invalid_inclination", "invalid_azimuth"}.issubset(codes)


def test_relative_geometry_derives_directional_values_with_provenance(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    record = _record(
        "managed-well:qaqc-derived",
        [
            {"station_index": 0, "md": 0.0, "tvd": 0.0, "x": 0.0, "y": 0.0},
            {"station_index": 1, "md": 100.0, "tvd": 99.0, "x": 10.0, "y": 0.0},
            {"station_index": 2, "md": 200.0, "tvd": 196.0, "x": 30.0, "y": 10.0},
        ],
    )
    record.metadata["wbv_trajectory_package"].update(
        {
            "source_type": "csv",
            "source_relative_path": "survey/test.csv",
            "coordinate_mode": "relative",
            "classification_message": "Relative geometry registered from source survey.",
        }
    )
    repository.upsert_record(record)

    package = WbvService(repository=repository).get_viewer_package("managed-well:qaqc-derived")

    assert package.trajectory.directional_values_status == "derived_or_mixed"
    assert package.trajectory.point_value_sources["inclination"] == "derived_from_relative_geometry"
    assert package.trajectory.point_value_sources["azimuth"] == "derived_from_relative_geometry"
    assert package.trajectory.render_points[1]["inclination_source"] == "derived_from_relative_geometry"
    assert package.trajectory.render_points[1]["azimuth_source"] == "derived_from_relative_geometry"
    assert package.trajectory.provenance["source_relative_path"] == "survey/test.csv"
    assert package.survey_qaqc.derived_inclination_count == 2
    assert package.survey_qaqc.derived_azimuth_count == 2
    assert package.survey_qaqc.overall_state == "warning"
