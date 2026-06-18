from dataclasses import dataclass

from app.inventory.wdv_viewer_package import (
    build_wdv_viewer_package,
    summarize_wdv_viewer_package,
)


@dataclass
class Record:
    managed_well_id: str = "managed-well:alpha"
    managed_well_uid: str = "01977a8e-8000-7000-8000-000000000001"
    managed_wellbore_uid: str | None = None
    well_id: str = "alpha"
    well_name: str = "Alpha"
    wellbore_id: str | None = None
    wellbore_name: str | None = None
    operator: str | None = None
    field: str | None = None
    country: str | None = None
    depth_unit: str = "ft"


@dataclass
class Product:
    product_id: str
    managed_product_uid: str
    managed_curve_uid: str | None
    display_name: str
    curve_name: str


def curve_builder(_record, item):
    return {
        "product_id": item.product_id,
        "managed_product_uid": item.managed_product_uid,
        "managed_curve_uid": item.managed_curve_uid,
        "curve_uid": item.managed_curve_uid,
        "curve_id": item.curve_name,
        "display_curve_id": item.curve_name,
        "display_name": item.display_name,
        "is_renderable": True,
        "support_status": "renderable",
    }


def test_package_counts_equal_exact_valid_curve_array_length():
    items = [
        Product("p1", "mp1", "c1", "Gamma", "GR"),
        Product("p2", "mp2", "c2", "Density", "RHOB"),
    ]
    package = build_wdv_viewer_package(
        record=Record(),
        loaded_items=items,
        curve_builder=curve_builder,
        updated_at="2026-06-18T00:00:00Z",
        depth_domain={"min": 0.0, "max": 1000.0, "unit": "ft", "source": "test", "contributing_product_ids": ["p1", "p2"]},
    )
    assert package["loaded_product_count"] == 2
    assert package["viewer_curve_count"] == 2
    assert package["displayable_curve_count"] == len(package["curves"]) == 2
    assert "loaded_curve_items" not in package
    assert summarize_wdv_viewer_package(package, ["p1", "p2"]) == (2, 2, 2)


def test_invalid_and_duplicate_curves_are_dispositioned_not_counted():
    items = [
        Product("p1", "mp1", "c1", "Gamma", "GR"),
        Product("p2", "mp2", "c1", "Duplicate Gamma", "GR2"),
        Product("p3", "mp3", None, "Missing identity", "BAD"),
    ]
    package = build_wdv_viewer_package(
        record=Record(),
        loaded_items=items,
        curve_builder=curve_builder,
        updated_at="2026-06-18T00:00:00Z",
        depth_domain={"min": 0.0, "max": 1000.0, "unit": "ft", "source": "test", "contributing_product_ids": ["p1", "p2", "p3"]},
    )
    assert package["loaded_product_count"] == 3
    assert package["displayable_curve_count"] == len(package["curves"]) == 1
    reasons = {reason for item in package["unsupported_products"] for reason in item["reasons"]}
    assert "duplicate_curve_uid" in reasons
    assert "missing_curve_uid" in reasons


def test_missing_package_never_falls_back_to_product_count():
    assert summarize_wdv_viewer_package(None, ["p1", "p2", "p3"]) == (3, 0, 0)
