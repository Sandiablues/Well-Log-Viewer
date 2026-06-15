import math

from app.wbv.trajectory_models import DeviationSurveyStation, TrajectoryCoordinateMode
from app.wbv.trajectory_service import calculate_minimum_curvature_trajectory


def _codes(result) -> set[str]:
    return {issue.code for issue in result.warnings}


def test_minimum_curvature_vertical_well_returns_relative_tvd_only() -> None:
    result = calculate_minimum_curvature_trajectory(
        [
            DeviationSurveyStation(md=0.0, inclination=0.0, azimuth=0.0, depth_unit="ft", angle_unit="deg"),
            DeviationSurveyStation(md=1000.0, inclination=0.0, azimuth=0.0, depth_unit="ft", angle_unit="deg"),
        ]
    )

    assert result.is_valid is True
    assert result.coordinate_mode == TrajectoryCoordinateMode.RELATIVE
    assert result.depth_unit == "ft"
    assert len(result.render_points) == 2
    final = result.render_points[-1]
    assert final.md == 1000.0
    assert final.tvd == 1000.0
    assert final.x == 0.0
    assert final.y == 0.0
    assert final.z == -1000.0
    assert final.dogleg_severity == 0.0
    assert result.bounding_box is not None
    assert result.bounding_box.min_z == -1000.0
    assert result.bounding_box.max_z == -0.0


def test_minimum_curvature_build_section_calculates_east_offset_and_dogleg() -> None:
    result = calculate_minimum_curvature_trajectory(
        [
            {"md": 0.0, "inclination": 0.0, "azimuth": 0.0, "depth_unit": "ft", "angle_unit": "deg"},
            {"md": 1000.0, "inclination": 90.0, "azimuth": 90.0, "depth_unit": "ft", "angle_unit": "deg"},
        ]
    )

    assert result.is_valid is True
    final = result.render_points[-1]
    expected = 1000.0 * 2.0 / math.pi
    assert final.tvd == pytest_approx(expected)
    assert final.x == pytest_approx(expected)
    assert final.y == pytest_approx(0.0)
    assert final.z == pytest_approx(-expected)
    assert final.dogleg_severity == pytest_approx(9.0)


def test_result_serializes_to_wbv_trajectory_package_shape() -> None:
    result = calculate_minimum_curvature_trajectory(
        [
            {"md": 0.0, "inclination": 0.0, "azimuth": 0.0},
            {"md": 100.0, "inclination": 0.0, "azimuth": 0.0},
        ],
        depth_unit="m",
    )

    package = result.to_wbv_trajectory_package()

    assert package["method"] == "minimum_curvature"
    assert package["source"] == "deviation_survey"
    assert len(package["stations"]) == 2
    assert len(package["render_points"]) == 2
    assert package["render_points"][-1]["md"] == 100.0
    assert package["render_points"][-1]["z"] == -100.0


def test_non_monotonic_md_is_rejected_without_render_points() -> None:
    result = calculate_minimum_curvature_trajectory(
        [
            {"md": 0.0, "inclination": 0.0, "azimuth": 0.0, "depth_unit": "ft", "angle_unit": "deg"},
            {"md": 100.0, "inclination": 1.0, "azimuth": 10.0, "depth_unit": "ft", "angle_unit": "deg"},
            {"md": 100.0, "inclination": 2.0, "azimuth": 20.0, "depth_unit": "ft", "angle_unit": "deg"},
        ]
    )

    assert result.is_valid is False
    assert result.render_points == []
    assert "non_monotonic_md" in _codes(result)


def test_missing_inclination_or_azimuth_is_rejected() -> None:
    result = calculate_minimum_curvature_trajectory(
        [
            {"md": 0.0, "inclination": 0.0, "azimuth": 0.0, "depth_unit": "ft", "angle_unit": "deg"},
            {"md": 100.0, "inclination": None, "azimuth": 90.0, "depth_unit": "ft", "angle_unit": "deg"},
        ]
    )

    assert result.is_valid is False
    assert result.render_points == []
    assert "missing_inclination" in _codes(result)
    assert "survey_station_validation_failed" in _codes(result)


def test_inconsistent_units_are_rejected() -> None:
    result = calculate_minimum_curvature_trajectory(
        [
            {"md": 0.0, "inclination": 0.0, "azimuth": 0.0, "depth_unit": "ft", "angle_unit": "deg"},
            {"md": 100.0, "inclination": 0.0, "azimuth": 0.0, "depth_unit": "m", "angle_unit": "deg"},
        ]
    )

    assert result.is_valid is False
    assert result.render_points == []
    assert "inconsistent_depth_unit" in _codes(result)


def test_radian_inputs_are_normalized_to_degrees() -> None:
    result = calculate_minimum_curvature_trajectory(
        [
            {"md": 0.0, "inclination": 0.0, "azimuth": 0.0, "depth_unit": "m", "angle_unit": "rad"},
            {"md": 100.0, "inclination": math.pi / 2.0, "azimuth": math.pi / 2.0, "depth_unit": "m", "angle_unit": "rad"},
        ]
    )

    assert result.is_valid is True
    assert result.angle_unit == "deg"
    assert result.stations[-1].inclination == pytest_approx(90.0)
    assert result.stations[-1].azimuth == pytest_approx(90.0)


def pytest_approx(value: float):
    import pytest

    return pytest.approx(value, abs=1.0e-6)
