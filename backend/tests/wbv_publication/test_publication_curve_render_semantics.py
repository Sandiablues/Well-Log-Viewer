from __future__ import annotations

from types import SimpleNamespace

from app.wbv_publication.adapter import WbvPublishedPackageRenderAdapter


def _rule(
    rule_type: str,
    *,
    color: str,
    opacity: float,
    target_uid: str | None = None,
    boundary: str | None = None,
    order: int = 0,
):
    return SimpleNamespace(
        rule_type=SimpleNamespace(value=rule_type),
        style=SimpleNamespace(color=color, opacity=opacity),
        curve_b_assignment_uid=target_uid,
        boundary=(
            SimpleNamespace(value=boundary)
            if boundary is not None
            else None
        ),
        order=order,
    )


def test_crossover_compiles_as_distinct_crossover_mode():
    target_assignment_uid = "nphi-assignment"
    target_product_uid = "nphi-product"
    assignments = {
        target_assignment_uid: SimpleNamespace(
            managed_product_uid=target_product_uid
        )
    }

    result = WbvPublishedPackageRenderAdapter._resolve_fill(
        [
            _rule(
                "crossover",
                color="#3fd966",
                opacity=0.45,
                target_uid=target_assignment_uid,
            )
        ],
        assignments,
        default_color="#000000",
        default_opacity=0.0,
    )

    assert result == (
        "crossover",
        target_product_uid,
        "#3fd966",
        0.45,
        0.0,
    )


def test_nphi_boundary_fill_remains_independent():
    result = WbvPublishedPackageRenderAdapter._resolve_fill(
        [
            _rule(
                "to_boundary",
                color="#f4f1f1",
                opacity=0.45,
                boundary="left",
            )
        ],
        {},
        default_color="#000000",
        default_opacity=0.0,
    )

    assert result == (
        "to_baseline",
        None,
        "#f4f1f1",
        0.45,
        0.0,
    )


def test_logarithmic_normalization_for_resistivity():
    normalize = WbvPublishedPackageRenderAdapter._normalize

    assert normalize(0.2, 0.2, 2000.0, True) == 0.0
    assert round(normalize(20.0, 0.2, 2000.0, True), 6) == 0.5
    assert normalize(2000.0, 0.2, 2000.0, True) == 1.0
