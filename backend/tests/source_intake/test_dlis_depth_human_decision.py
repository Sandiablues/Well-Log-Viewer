from app.source_intake.depth_units import convert_depth_to_target, requires_human_target_unit


def test_nonstandard_scaled_inches_require_human_target():
    assert requires_human_target_unit("0.1 in") is True
    assert convert_depth_to_target(74760, "0.1 in", "ft") == 623.0
    assert round(convert_depth_to_target(74760, "0.1 in", "m"), 4) == 189.8904


def test_canonical_m_and_ft_do_not_require_human_target():
    assert requires_human_target_unit("m") is False
    assert requires_human_target_unit("ft") is False
