import pytest

from app.wbv.models import WbvSurveyQaqcFinding, WbvSurveyQaqcSummary, WbvTrajectoryPackage
from app.wbv.service import WbvService


def test_distance_conversion_ft_to_m_preserves_source_object() -> None:
    source = WbvTrajectoryPackage(
        render_points=[
            {
                "md": 100.0,
                "tvd": 90.0,
                "x": 10.0,
                "y": 20.0,
                "z": -90.0,
                "dogleg_severity": 2.0,
            }
        ]
    )

    converted = WbvService._convert_trajectory_package(source, "ft", "m")

    assert source.render_points[0]["md"] == 100.0
    assert converted.render_points[0]["md"] == pytest.approx(30.48)
    assert converted.render_points[0]["tvd"] == pytest.approx(27.432)
    assert converted.render_points[0]["x"] == pytest.approx(3.048)
    assert converted.render_points[0]["z"] == pytest.approx(-27.432)
    assert converted.render_points[0]["dogleg_severity"] == pytest.approx(2.0 * 30.0 / 30.48)


def test_bounding_box_and_qaqc_distance_conversion() -> None:
    bbox = {"md": {"min": 0.0, "max": 1000.0}, "x": {"min": -10.0, "max": 20.0}}
    converted_bbox = WbvService._convert_bounding_box(bbox, "ft", "m")
    assert converted_bbox["md"]["max"] == pytest.approx(304.8)
    assert converted_bbox["x"]["min"] == pytest.approx(-3.048)

    summary = WbvSurveyQaqcSummary(
        max_station_gap=100.0,
        max_dogleg_severity=1.5,
        findings=[
            WbvSurveyQaqcFinding(
                code="gap",
                message="Station gap exceeds the configured threshold.",
                md_start=100.0,
                md_end=200.0,
            )
        ],
    )
    converted_summary = WbvService._convert_survey_qaqc(summary, "ft", "m")
    assert converted_summary.max_station_gap == pytest.approx(30.48)
    assert converted_summary.findings[0].md_start == pytest.approx(30.48)
    assert summary.max_station_gap == 100.0


def test_depth_unit_normalization() -> None:
    assert WbvService._normalize_depth_unit("feet") == "ft"
    assert WbvService._normalize_depth_unit("metres") == "m"
