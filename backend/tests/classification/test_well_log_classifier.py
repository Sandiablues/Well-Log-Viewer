from __future__ import annotations

from backend.app.classification.well_log_classifier import classify_well_log_curve


def test_open_hole_common_curves_classify_to_open_hole() -> None:
    cases = [
        ("GR", "Gamma Ray", "GAPI", "Gamma Ray"),
        ("RHOB", "Bulk Density", "G/C3", "Density"),
        ("NPHI", "Neutron Porosity", "V/V", "Neutron Porosity"),
        ("DTCO", "Delta-T Compressional", "US/F", "Sonic Compressional"),
        ("DTSM", "Delta-T Shear", "US/F", "Sonic Shear"),
        ("CALI", "Caliper", "IN", "Caliper"),
        ("PEF", "Photoelectric Factor", "B/E", "Photoelectric Factor"),
        ("SP", "Spontaneous Potential", "MV", "Spontaneous Potential"),
    ]
    for mnemonic, description, unit, family in cases:
        result = classify_well_log_curve(mnemonic=mnemonic, description=description, unit=unit)
        assert result.product_category == "open_hole_logs"
        assert result.curve_family == family
        assert result.curve_description == description
        assert result.classification_confidence in {"high", "medium"}
        assert result.review_required is False


def test_cased_hole_common_curves_classify_to_cased_hole() -> None:
    cases = [
        ("CBL", "Cement Bond Log", "Cement Evaluation"),
        ("VDL", "Variable Density Log", "Cement Evaluation"),
        ("CCL", "Casing Collar Locator", "Completion / Depth Correlation"),
        ("TEMP", "Temperature", "Production Logging"),
        ("FLOW", "Flow Rate", "Production Logging"),
        ("MIT", "Multi-Finger Imaging Tool", "Casing Inspection"),
        ("MFC", "Multi-Finger Caliper", "Casing Inspection"),
        ("MTT", "Magnetic Thickness Tool", "Casing Inspection"),
        ("SIGMA", "Neutron Capture Sigma", "Pulsed Neutron"),
    ]
    for mnemonic, description, family in cases:
        result = classify_well_log_curve(mnemonic=mnemonic, description=description)
        assert result.product_category == "cased_hole_logs"
        assert result.curve_family == family
        assert result.review_required is False


def test_cased_context_overrides_ambiguous_gamma_ray() -> None:
    result = classify_well_log_curve(
        mnemonic="GR",
        description="Gamma ray for cased hole production log correlation",
        unit="GAPI",
    )
    assert result.product_category == "cased_hole_logs"
    assert result.curve_family == "Cased-Hole Log"
    assert result.review_required is False


def test_additional_product_groups_are_supported() -> None:
    assert classify_well_log_curve(mnemonic="TOP", description="Formation Top").product_category == "lithology_core_markers"
    assert classify_well_log_curve(mnemonic="MOB", description="Mobility").product_category == "pressure_production_fluid_data"
    assert classify_well_log_curve(mnemonic="PERF", description="Perforation").product_category == "completion_integrity_data"


def test_unknown_curve_requires_review() -> None:
    result = classify_well_log_curve(mnemonic="XYZ", description="Unknown vendor curve")
    assert result.product_category == "other_review_required"
    assert result.curve_family == "Unclassified"
    assert result.classification_confidence == "low"
    assert result.review_required is True
