from app.classification_orchestration.general_family_projection import (
    project_general_curve_family,
    project_mwd_product_group,
)


def _project(detailed_key, detailed_label, domain, product_category, display_in_wdv=True):
    family = project_general_curve_family(detailed_key, detailed_label)
    category = project_mwd_product_group(
        current_product_category=product_category,
        measurement_domain_key=domain,
        general_family_key=family.family_key,
        display_in_wdv=display_in_wdv,
    )
    return category, family.family_key, family.family_label


def test_f21_31_style_sonic_curves_use_same_family_in_mwd_and_wdv():
    for detailed_key, detailed_label in [
        ("sonic", "Sonic"),
        ("sonic_compressional", "Sonic Compressional"),
        ("sonic_shear", "Sonic Shear"),
    ]:
        category, mwd_key, mwd_label = _project(
            detailed_key,
            detailed_label,
            "open_hole_log",
            "other_review_required",
        )
        assert category == "open_hole_logs"
        assert (mwd_key, mwd_label) == ("sonic", "Sonic")
        # WDV consumes the same persisted general family pair.
        wdv_key, wdv_label = mwd_key, mwd_label
        assert (wdv_key, wdv_label) == (mwd_key, mwd_label)


def test_genuinely_unclassified_curves_remain_in_review():
    category, family_key, family_label = _project(
        "unclassified",
        "Unclassified",
        "open_hole_log",
        "other_review_required",
    )
    assert category == "other_review_required"
    assert family_key == "unclassified"
    assert family_label == "Unclassified"
