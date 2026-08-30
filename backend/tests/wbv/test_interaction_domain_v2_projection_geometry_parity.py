from __future__ import annotations

import pytest

from app.wbv.interaction_domain.contracts import WbvScreenObservationV2
from app.wbv.interaction_domain.projection import (
    TARGET_WELL_HEIGHT,
    normalized_trajectory,
    project_observation,
)


IDENTITY_MATRIX = [
    1, 0, 0, 0,
    0, 1, 0, 0,
    0, 0, 1, 0,
    0, 0, 0, 1,
]


def observation(x: float, y: float, tolerance: float = 25.0) -> WbvScreenObservationV2:
    return WbvScreenObservationV2(
        pointer_x_px=x,
        pointer_y_px=y,
        viewport_width_px=100,
        viewport_height_px=100,
        view_projection_matrix=IDENTITY_MATRIX,
        activation_tolerance_px=tolerance,
    )


def test_backend_uses_exact_renderer_target_height_contract():
    assert TARGET_WELL_HEIGHT == 5.35
    points = [
        {"md": 0, "tvd": 0, "x": 0, "y": 0, "z": 0},
        {"md": 100, "tvd": 100, "x": 0, "y": 0, "z": -100},
    ]
    normalized = normalized_trajectory(points)
    assert normalized[0][1] == pytest.approx(2.675)
    assert normalized[1][1] == pytest.approx(-2.675)


def test_backend_scene_contract_accepts_renderer_coordinate_aliases():
    canonical = [
        {"md": 0, "tvd": 0, "x": 10, "y": -5, "z": 0},
        {"md": 100, "tvd": 100, "x": 30, "y": 15, "z": -100},
    ]
    aliases = [
        {"md": 0, "tvd": 0, "east_departure": 10, "north_departure": -5, "z": 0},
        {"md": 100, "tvd": 100, "east_departure": 30, "north_departure": 15, "z": -100},
    ]
    assert normalized_trajectory(aliases) == pytest.approx(normalized_trajectory(canonical))


def test_backend_scene_contract_uses_md_when_tvd_is_absent():
    tvd_points = [
        {"md": 0, "tvd": 0, "x": 0, "y": 0, "z": 0},
        {"md": 100, "tvd": 100, "x": 0, "y": 0, "z": -999},
    ]
    md_only_points = [
        {"md": 0, "x": 0, "y": 0, "z": 0},
        {"md": 100, "x": 0, "y": 0, "z": -999},
    ]
    assert normalized_trajectory(md_only_points) == pytest.approx(normalized_trajectory(tvd_points))


def test_backend_scene_contract_uses_absolute_z_only_as_final_depth_fallback():
    points = [
        {"md": None, "tvd": None, "x": 0, "y": 0, "z": 0},
        {"md": None, "tvd": None, "x": 0, "y": 0, "z": -100},
    ]
    normalized = normalized_trajectory(points)
    assert normalized[0][1] == pytest.approx(2.675)
    assert normalized[1][1] == pytest.approx(-2.675)


def test_projection_accepts_click_on_exact_backend_projected_segment():
    points = [
        {"md": 0, "tvd": 0, "x": 0, "y": 0, "z": 0},
        {"md": 100, "tvd": 100, "x": 0, "y": 0, "z": -100},
    ]
    # Under identity projection, the normalized vertical segment crosses x=50.
    selected = project_observation(points, observation(50, 50, tolerance=1))
    assert selected.md == pytest.approx(50)
    assert selected.tvd == pytest.approx(50)
    assert selected.screen_distance_px == pytest.approx(0)


def test_projection_still_rejects_real_miss_without_widening_tolerance():
    points = [
        {"md": 0, "tvd": 0, "x": 0, "y": 0, "z": 0},
        {"md": 100, "tvd": 100, "x": 0, "y": 0, "z": -100},
    ]
    with pytest.raises(ValueError, match="activation tolerance"):
        project_observation(points, observation(90, 50, tolerance=10))
