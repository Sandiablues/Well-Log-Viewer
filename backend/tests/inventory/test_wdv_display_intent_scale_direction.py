from pathlib import Path

from app.inventory.curve_sample_service import _read_las_curve_samples
from app.inventory.models import ManagedProductGroupItem
from app.inventory.service import ManagedWellInventoryService


def _las_text(curve_lines: str, rows: list[str], null_value: str = "-999.25") -> str:
    return f"""~Version
VERS. 2.0
~Well
STRT.FT 1000
STOP.FT 1010
STEP.FT 1
NULL. {null_value}
~Curve
DEPT.FT : Depth
{curve_lines}
~Ascii
""" + "\n".join(rows) + "\n"


def test_curve_sample_service_reports_percentile_diagnostics(tmp_path: Path) -> None:
    path = tmp_path / "dnph_percentiles.las"
    rows = [f"{1000 + idx} {-0.08 + idx * 0.003}" for idx in range(40)]
    path.write_text(_las_text("DNPH.V/V : Neutron Porosity", rows))

    payload = _read_las_curve_samples(path, "DNPH", max_samples=100)

    assert payload["sample_count"] == 40
    assert payload["value_p05"] is not None
    assert payload["value_p50"] is not None
    assert payload["value_p95"] is not None
    assert payload["value_p05"] < payload["value_p50"] < payload["value_p95"]


def test_standard_neutron_scale_reports_low_visual_variation_without_silent_rescale() -> None:
    item = ManagedProductGroupItem(
        product_id="p-dnph",
        display_name="Neutron Porosity",
        curve_name="DNPH",
        curve_type="Neutron Porosity",
        curve_description="Neutron Porosity",
        curve_unit="V/V",
        curve_family="neutron_porosity",
    )
    stats = {
        "statistics_status": "available",
        "robust_observed_min": -0.0803,
        "robust_observed_max": 0.2025,
        "observed_p05": -0.0519,
        "observed_p50": -0.0389,
        "observed_p95": -0.0259,
        "rejected_sample_count": 0,
    }

    scale = ManagedWellInventoryService._wdv_display_scale_contract(item, stats)

    assert scale["source"] == "robust_observed_statistics"
    assert scale["display_mode"] == "robust_observed"
    assert scale["recommended_display_mode"] == "robust_observed"
    assert scale["direction"] == "reversed"
    assert scale["standard_min"] == 0.45
    assert scale["standard_max"] == -0.15
    assert scale["display_left_value"] == scale["min"]
    assert scale["display_right_value"] == scale["max"]
    assert scale["numeric_min"] < scale["numeric_max"]
    assert scale["robust_observed_domain_source"] == "p05_p95"
    assert scale["min"] < 0.05
    assert scale["max"] < scale["min"]
    assert scale["max"] < -0.05
    assert scale["robust_observed_numeric_min"] < scale["robust_observed_numeric_max"]
    assert scale["robust_observed_display_left_value"] == scale["min"]
    assert scale["robust_observed_display_right_value"] == scale["max"]
    assert scale["visual_span_ratio"] < 0.08
    assert "low_visual_variation_on_standard_scale" in scale["warnings"]


def test_backend_contract_preserves_visual_diagnostics_for_loaded_curve() -> None:
    item = ManagedProductGroupItem(
        product_id="p-dnph",
        display_name="Neutron Porosity",
        curve_name="DNPH",
        curve_type="Neutron Porosity",
        curve_description="Neutron Porosity",
        curve_unit="V/V",
        curve_family="neutron_porosity",
    )
    stats = {
        "statistics_status": "available",
        "observed_min": -0.0803,
        "observed_max": 0.2025,
        "robust_observed_min": -0.0803,
        "robust_observed_max": 0.2025,
        "observed_p01": -0.0671,
        "observed_p05": -0.0519,
        "observed_p50": -0.0389,
        "observed_p95": -0.0259,
        "observed_p99": 0.0129,
        "valid_sample_count": 500,
        "raw_numeric_sample_count": 500,
        "rejected_sample_count": 0,
    }

    service = ManagedWellInventoryService.__new__(ManagedWellInventoryService)
    service._wdv_curve_sample_statistics = lambda _record, _item: stats  # type: ignore[method-assign]
    record = object()

    contract = service._wdv_curve_contract_from_product_item(record, item)  # type: ignore[arg-type]

    assert contract["curve_uid"].startswith("wlv_curve:")
    assert contract["well_uid"] is None
    assert contract["scale_direction"] == "reversed"
    assert contract["scale_source"] == "robust_observed_statistics"
    assert contract["display_scale_mode"] == "robust_observed"
    assert contract["recommended_display_scale_mode"] == "robust_observed"
    assert contract["standard_display_min"] == 0.45
    assert contract["standard_display_max"] == -0.15
    assert contract["display_left_value"] == contract["display_min"]
    assert contract["display_right_value"] == contract["display_max"]
    assert contract["numeric_min"] < contract["numeric_max"]
    assert contract["display_min"] < 0.05
    assert contract["display_max"] < contract["display_min"]
    assert contract["robust_observed_numeric_min"] < contract["robust_observed_numeric_max"]
    assert contract["visual_span_ratio"] < 0.08
    assert "low_visual_variation_on_standard_scale" in contract["scale_warnings"]
    assert contract["observed_p05"] == -0.0519
    assert contract["observed_p95"] == -0.0259
