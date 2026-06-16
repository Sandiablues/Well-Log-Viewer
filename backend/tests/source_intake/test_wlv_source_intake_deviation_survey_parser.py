from pathlib import Path

from app.source_intake.deviation_survey_parser import parse_deviation_survey_preview
from app.source_intake.models import SourceRepositoryCreateRequest
from app.source_intake.service import WlvSourceIntakeService


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_deviation_survey_parser_maps_required_columns_and_preview_rows(tmp_path: Path) -> None:
    source = tmp_path / "FORGE_21_31_Final_Deviation_Survey.csv"
    _write(
        source,
        "MD,INC,AZI,TVD,Northing,Easting\n"
        "0,0,0,0,5000,6000\n"
        "1000,2.5,45,999,5010,6010\n"
        "2000,4.0,90,1995,5040,6050\n",
    )

    preview = parse_deviation_survey_preview(source)

    assert preview.station_count == 3
    assert preview.preview_station_count == 3
    assert preview.md_min == 0
    assert preview.md_max == 2000
    assert preview.tvd_max == 1995
    assert preview.column_mapping.measured_depth == "MD"
    assert preview.column_mapping.inclination == "INC"
    assert preview.column_mapping.azimuth == "AZI"
    assert preview.column_mapping.tvd == "TVD"
    assert preview.stations_preview[1].inclination == 2.5


def test_source_intake_attaches_deviation_preview_without_registering_to_mdp(tmp_path: Path) -> None:
    root = tmp_path / "Forge_21_31"
    _write(
        root / "FORGE_21_31_Final_Deviation_Survey.csv",
        "MD,INC,AZI,TVD\n0,0,0,0\n1000,1.5,20,999\n2000,2.0,22,1998\n",
    )

    service = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")
    repository = service.create_repository(SourceRepositoryCreateRequest(root_path=str(root), include_subfolders=True))
    result = service.scan_repository(repository.repository_id)

    candidate = result.candidates[0]
    assert candidate.candidate_role == "wellbore_geometry_candidate"
    assert candidate.parser_status == "parsed"
    assert candidate.geometry_preview is not None
    assert candidate.geometry_preview.station_count == 3
    assert candidate.registration_status == "not_registered"
    assert candidate.managed_well_id is None
    assert candidate.review_required is True
    assert candidate.qaqc_status.review_required is True
    assert any(check.check_id == "geometry.preview.present" for check in candidate.qaqc_status.checks)

    diagnostics = service.get_candidate_diagnostics(candidate.source_file_id)

    # GEOM-4 makes parsed wellbore-geometry candidates eligible for explicit
    # registration while still preserving review_required QAQC state.
    assert diagnostics.mdp_ready_status == "ready"
    assert any(flag.code == "parse_complete" for flag in diagnostics.flags)


def test_deviation_preview_parse_failure_keeps_candidate_review_required(tmp_path: Path) -> None:
    root = tmp_path / "Forge_21_31"
    _write(root / "FORGE_21_31_Final_Deviation_Survey.csv", "Depth,Value\n0,1\n")

    service = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")
    repository = service.create_repository(SourceRepositoryCreateRequest(root_path=str(root), include_subfolders=True))
    result = service.scan_repository(repository.repository_id)

    candidate = result.candidates[0]
    assert candidate.candidate_role == "wellbore_geometry_candidate"
    assert candidate.parser_status == "parse_failed"
    assert candidate.geometry_preview is None
    assert candidate.review_required is True
    assert candidate.qaqc_status.status == "fail"
    assert "missing required column" in (candidate.parse_error or "").lower()
