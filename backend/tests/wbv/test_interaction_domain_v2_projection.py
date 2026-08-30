import pytest
from app.wbv.interaction_domain.contracts import WbvScreenObservationV2
from app.wbv.interaction_domain.projection import normalized_trajectory, project_observation


def observation(x: float, y: float, tolerance: float = 25.0) -> WbvScreenObservationV2:
    return WbvScreenObservationV2(
        pointer_x_px=x,
        pointer_y_px=y,
        viewport_width_px=100,
        viewport_height_px=100,
        view_projection_matrix=[1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1],
        activation_tolerance_px=tolerance,
    )


def points():
    return [
        {"md": 0, "tvd": 0, "x": 0, "y": 0, "z": 0, "inclination": 0, "azimuth": 0},
        {"md": 100, "tvd": 100, "x": 0, "y": 0, "z": -100, "inclination": 10, "azimuth": 20},
    ]


def test_backend_projection_interpolates_authoritative_fields():
    selected = project_observation(points(), observation(50, 50))
    assert selected.md == 50
    assert selected.tvd == 50
    assert selected.inclination == 5
    assert selected.azimuth == 10
    assert selected.segment_index == 0
    assert selected.segment_ratio == 0.5


def test_projection_rejects_outside_governed_tolerance():
    with pytest.raises(ValueError, match="activation tolerance"):
        project_observation(points(), observation(90, 50, tolerance=10))


def test_normalization_matches_renderer_contract():
    normalized = normalized_trajectory(points())
    assert normalized[0][1] == 2.675
    assert normalized[1][1] == -2.675
