
from pathlib import Path

from backend.app.inventory.curve_sample_service import _read_las_curve_samples
from backend.app.inventory.models import ManagedProductGroupItem
from backend.app.inventory.service import ManagedWellInventoryService


def _las_text(curve_lines: str, rows: list[str], null_value: str = "-999.25") -> str:
    return f"""~Version
VERS. 2.0
~Well
STRT.FT 1000
STOP.FT 1005
STEP.FT 1
NULL. {null_value}
~Curve
DEPT.FT : Depth
{curve_lines}
~Ascii
""" + "\n".join(rows) + "\n"


def test_curve_samples_exclude_las_null_and_density_plausibility_artifacts(tmp_path: Path) -> None:
    path = tmp_path / "density_artifacts.las"
    path.write_text(
        _las_text(
            "HDRB.g/cm3 : Difference Between Bulk Density",
            [
                "1000 -999.25",
                "1001 -7312.510115",
                "1002 350.013215",
                "1003 -3.1933",
                "1004 1.7138",
                "1005 0.2500",
            ],
        )
    )

    payload = _read_las_curve_samples(path, "HDRB", max_samples=100)

    assert payload["value_min"] == -3.1933
    assert payload["value_max"] == 1.7138
    assert payload["rejected_null_count"] == 1
    assert payload["rejected_plausibility_count"] == 2
    assert payload["sample_count"] == 3


def test_curve_samples_exclude_common_null_sentinel_when_header_is_missing(tmp_path: Path) -> None:
    path = tmp_path / "sentinel_artifacts.las"
    path.write_text(
        _las_text(
            "RHOZ.G/C3 : Bulk Density",
            [
                "1000 -9999",
                "1001 2.31",
                "1002 2.44",
            ],
            null_value="-999.25",
        )
    )

    payload = _read_las_curve_samples(path, "RHOZ", max_samples=100)

    assert payload["value_min"] == 2.31
    assert payload["value_max"] == 2.44
    assert payload["rejected_sentinel_count"] == 1
    assert payload["sample_count"] == 2


def test_density_correction_curve_uses_sanitized_observed_statistics_not_density_default() -> None:
    item = ManagedProductGroupItem(
        product_id="p-hdrb",
        display_name="Difference Between Bulk Density",
        curve_name="HDRB",
        curve_type="Difference Between Bulk Density",
        curve_description="Difference Between Bulk Density (RHOZ) and Apparent Density from Back Scatter MonoSensor Inversion",
        curve_unit="g/cm3",
        curve_family="density",
    )
    stats = {
        "statistics_status": "available",
        "robust_observed_min": -3.1933,
        "robust_observed_max": 1.7138,
        "rejected_sample_count": 3,
    }

    scale = ManagedWellInventoryService._wdv_display_scale_contract(item, stats)

    assert scale["source"] == "observed_statistics"
    assert scale["min"] < -3.0
    assert scale["max"] > 1.7
    assert scale["min"] != 1.95
    assert scale["max"] != 2.95
    assert "suspected_correction_or_delta_curve" in scale["warnings"]
    assert "invalid_samples_rejected" in scale["warnings"]


def test_true_density_curve_keeps_standard_density_scale_when_observed_values_support_it() -> None:
    item = ManagedProductGroupItem(
        product_id="p-rhoz",
        display_name="Bulk Density",
        curve_name="RHOZ",
        curve_type="Bulk Density",
        curve_description="Bulk Density",
        curve_unit="G/C3",
        curve_family="density",
    )
    stats = {
        "statistics_status": "available",
        "robust_observed_min": 2.1,
        "robust_observed_max": 2.65,
        "rejected_sample_count": 2,
    }

    scale = ManagedWellInventoryService._wdv_display_scale_contract(item, stats)

    assert scale["source"] == "template_default"
    assert scale["type"] == "linear"
    assert scale["min"] == 1.95
    assert scale["max"] == 2.95
    assert "invalid_samples_rejected" in scale["warnings"]


def test_neutron_correction_curve_does_not_blindly_use_generic_neutron_default() -> None:
    item = ManagedProductGroupItem(
        product_id="p-dnph",
        display_name="Neutron Porosity",
        curve_name="DNPH",
        curve_type="Neutron Porosity Delta",
        curve_description="Neutron Porosity Difference",
        curve_unit="V/V",
        curve_family="neutron_porosity",
    )
    stats = {
        "statistics_status": "available",
        "robust_observed_min": -0.09694,
        "robust_observed_max": 0.26914,
        "rejected_sample_count": 0,
    }

    scale = ManagedWellInventoryService._wdv_display_scale_contract(item, stats)

    assert scale["source"] == "observed_statistics"
    assert scale["direction"] == "reversed"
    assert scale["min"] > scale["max"]
    assert scale["min"] < 0.45
    assert scale["max"] > -0.15
    assert "suspected_correction_or_delta_curve" in scale["warnings"]


def test_resistivity_remains_logarithmic() -> None:
    item = ManagedProductGroupItem(
        product_id="p-at90",
        display_name="Deep Resistivity",
        curve_name="AT90",
        curve_type="Deep Resistivity",
        curve_description="Deep Resistivity",
        curve_unit="OHMM",
        curve_family="resistivity",
    )
    stats = {
        "statistics_status": "available",
        "robust_observed_min": 0.3,
        "robust_observed_max": 120.0,
        "rejected_sample_count": 0,
    }

    scale = ManagedWellInventoryService._wdv_display_scale_contract(item, stats)

    assert scale["type"] == "log"
    assert scale["min"] == 0.2
    assert scale["max"] == 2000.0
