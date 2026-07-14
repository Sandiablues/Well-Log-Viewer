from app.classification_orchestration.general_family_projection import (
    project_general_curve_family,
    project_mwd_product_group,
)


def test_backend_emits_canonical_human_family_labels() -> None:
    expected = {
        "neutron_porosity": "Neutron Porosity",
        "photoelectric_factor": "Photoelectric Factor",
        "spontaneous_potential": "Spontaneous Potential",
    }
    for family_key, family_label in expected.items():
        projected = project_general_curve_family(family_key, family_key)
        assert projected.family_key == family_key
        assert projected.family_label == family_label
        assert projected.family_label != projected.family_key


def test_petrophysical_log_projects_to_open_hole_logs_for_resolved_wdv_curve() -> None:
    assert project_mwd_product_group(
        current_product_category="other_review_required",
        measurement_domain_key="petrophysical_log",
        general_family_key="sonic",
        display_in_wdv=True,
    ) == "open_hole_logs"


def test_neutron_porosity_petrophysical_log_projects_to_open_hole_logs() -> None:
    assert project_mwd_product_group(
        current_product_category="other_review_required",
        measurement_domain_key="petrophysical_log",
        general_family_key="neutron_porosity",
        display_in_wdv=True,
    ) == "open_hole_logs"


def test_unclassified_curve_remains_in_review_bucket() -> None:
    assert project_mwd_product_group(
        current_product_category="other_review_required",
        measurement_domain_key="petrophysical_log",
        general_family_key="unclassified",
        display_in_wdv=True,
    ) == "other_review_required"


def test_non_wdv_curve_is_not_relocated() -> None:
    assert project_mwd_product_group(
        current_product_category="other_review_required",
        measurement_domain_key="petrophysical_log",
        general_family_key="sonic",
        display_in_wdv=False,
    ) == "other_review_required"


def test_existing_non_review_product_category_is_preserved() -> None:
    assert project_mwd_product_group(
        current_product_category="cased_hole_logs",
        measurement_domain_key="petrophysical_log",
        general_family_key="sonic",
        display_in_wdv=True,
    ) == "cased_hole_logs"
