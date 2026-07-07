from __future__ import annotations

from types import SimpleNamespace

from app.wbv_publication.adapter import WbvPublishedPackageRenderAdapter


def test_crossover_remains_distinct_from_between_curves():
    target = SimpleNamespace(managed_product_uid="nphi-product")
    rule = SimpleNamespace(
        rule_type=SimpleNamespace(value="crossover"),
        curve_b_assignment_uid="nphi-assignment",
        style=SimpleNamespace(color="#3fd966", opacity=0.45),
        boundary=None,
    )

    result = WbvPublishedPackageRenderAdapter._resolve_fill(
        [rule],
        {"nphi-assignment": target},
        default_color="#000000",
        default_opacity=0.0,
    )

    assert result[0] == "crossover"
    assert result[1] == "nphi-product"


def test_boundary_fill_remains_independent():
    rule = SimpleNamespace(
        rule_type=SimpleNamespace(value="to_boundary"),
        curve_b_assignment_uid=None,
        style=SimpleNamespace(color="#f4f1f1", opacity=0.45),
        boundary=SimpleNamespace(value="left"),
    )

    result = WbvPublishedPackageRenderAdapter._resolve_fill(
        [rule],
        {},
        default_color="#000000",
        default_opacity=0.0,
    )

    assert result[0] == "to_baseline"
    assert result[2] == "#f4f1f1"
