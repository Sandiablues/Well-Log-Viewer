from app.classification_orchestration.general_family_projection import project_mwd_product_group


def test_resolved_wdv_open_hole_curve_moves_from_stale_review_bucket_to_open_hole_logs():
    assert project_mwd_product_group(
        current_product_category="other_review_required",
        measurement_domain_key="open_hole_log",
        general_family_key="sonic",
        display_in_wdv=True,
    ) == "open_hole_logs"


def test_resolved_wdv_cased_hole_curve_moves_from_stale_review_bucket_to_cased_hole_logs():
    assert project_mwd_product_group(
        current_product_category="other_review_required",
        measurement_domain_key="cased_hole_log",
        general_family_key="cement_bond",
        display_in_wdv=True,
    ) == "cased_hole_logs"


def test_unclassified_curve_remains_review_required():
    assert project_mwd_product_group(
        current_product_category="other_review_required",
        measurement_domain_key="open_hole_log",
        general_family_key="unclassified",
        display_in_wdv=True,
    ) == "other_review_required"


def test_non_wdv_curve_is_not_forced_into_log_product_group():
    assert project_mwd_product_group(
        current_product_category="other_review_required",
        measurement_domain_key="open_hole_log",
        general_family_key="directional",
        display_in_wdv=False,
    ) == "other_review_required"


def test_existing_governed_product_category_is_never_rewritten():
    assert project_mwd_product_group(
        current_product_category="pressure_production_fluid_data",
        measurement_domain_key="open_hole_log",
        general_family_key="pressure",
        display_in_wdv=True,
    ) == "pressure_production_fluid_data"
