import pytest

from app.wbv.interaction_domain.contracts import WbvScreenObservationV2
from app.wbv.interaction_domain.projection import project_observation


IDENTITY_MATRIX = [
    1, 0, 0, 0,
    0, 1, 0, 0,
    0, 0, 1, 0,
    0, 0, 0, 1,
]


def _observation(*, pointer_x: float, pointer_y: float, tolerance: float = 5.0):
    return WbvScreenObservationV2(
        pointer_x_px=pointer_x,
        pointer_y_px=pointer_y,
        viewport_width_px=100.0,
        viewport_height_px=100.0,
        view_projection_matrix=IDENTITY_MATRIX,
        activation_tolerance_px=tolerance,
    )


def _points():
    return [
        {"md": 0.0, "tvd": 0.0, "x": 0.0, "y": 0.0, "z": 0.0},
        {"md": 100.0, "tvd": 100.0, "x": 0.0, "y": 0.0, "z": 0.0},
    ]


def test_activation_projection_still_rejects_pointer_outside_tolerance():
    with pytest.raises(ValueError, match="activation tolerance"):
        project_observation(
            _points(),
            _observation(pointer_x=90.0, pointer_y=50.0),
        )


def test_active_tracking_continuation_projects_without_reapplying_activation_tolerance():
    point = project_observation(
        _points(),
        _observation(pointer_x=90.0, pointer_y=50.0),
        enforce_activation_tolerance=False,
    )

    assert point.md == pytest.approx(50.0)
    assert point.tvd == pytest.approx(50.0)
    assert point.screen_distance_px > 5.0


def test_continuation_projection_remains_backend_authoritative():
    point = project_observation(
        _points(),
        _observation(pointer_x=90.0, pointer_y=20.0),
        enforce_activation_tolerance=False,
    )

    assert 0.0 <= point.segment_ratio <= 1.0
    assert point.segment_index == 0
    assert point.x == pytest.approx(0.0)
    assert point.y == pytest.approx(0.0)
    assert point.z == pytest.approx(0.0)
