
from __future__ import annotations

from app.inventory.models import ManagedProductGroup, ManagedProductGroupItem
from app.source_intake.registration import (
    _rebuild_classified_well_log_groups_from_general_family,
)


def _curve(
    *,
    product_id: str,
    mnemonic: str,
    product_category: str,
    general_family_key: str,
    general_family: str,
    measurement_domain_key: str | None,
    display_in_wdv: bool = True,
    classification_contract_version: str | None = "curve-classification-unified-shadow-v1",
    projection_version: str | None = "general-curve-family-projection-v1",
) -> ManagedProductGroupItem:
    return ManagedProductGroupItem(
        product_id=product_id,
        display_name=mnemonic,
        curve_name=mnemonic,
        curve_type=mnemonic,
        product_category=product_category,
        product_subgroup_key="other_review_required",
        product_subgroup_label="Other Review Required",
        curve_family=general_family,
        curve_family_key=general_family_key,
        general_curve_family=general_family,
        general_curve_family_key=general_family_key,
        general_curve_family_projection_version=projection_version,
        measurement_domain_key=measurement_domain_key,
        measurement_domain_label="Open-hole Log" if measurement_domain_key == "open_hole_log" else None,
        destination_key="wdv" if display_in_wdv else "other",
        destination_owner="WDV" if display_in_wdv else "Other",
        display_in_wdv=display_in_wdv,
        classification_contract_version=classification_contract_version,
        classification_confidence="high",
        classification_source="runtime_alias",
        review_required=False,
    )


def test_post_merge_regroup_moves_stale_review_well_log_curves_to_general_family():
    groups = [
        ManagedProductGroup(
            group_key="other_review_required",
            group_label="Other / Review required",
            items=[
                _curve(
                    product_id="itt",
                    mnemonic="ITT",
                    product_category="other_review_required",
                    general_family_key="sonic",
                    general_family="Sonic",
                    measurement_domain_key="open_hole_log",
                ),
                _curve(
                    product_id="pr",
                    mnemonic="PR",
                    product_category="other_review_required",
                    general_family_key="sonic",
                    general_family="Sonic",
                    measurement_domain_key="open_hole_log",
                ),
                _curve(
                    product_id="sphi",
                    mnemonic="SPHI",
                    product_category="other_review_required",
                    general_family_key="sonic",
                    general_family="Sonic",
                    measurement_domain_key="open_hole_log",
                ),
            ],
        )
    ]

    rebuilt = _rebuild_classified_well_log_groups_from_general_family(groups)
    by_key = {group.group_key: group for group in rebuilt}

    assert {item.curve_name for item in by_key["open_hole_logs"].items} == {
        "ITT", "PR", "SPHI"
    }
    assert {item.product_subgroup_key for item in by_key["open_hole_logs"].items} == {
        "sonic"
    }
    assert {item.product_subgroup_label for item in by_key["open_hole_logs"].items} == {
        "Sonic"
    }
    assert by_key["other_review_required"].items == []


def test_unclassified_curve_remains_in_review():
    groups = [
        ManagedProductGroup(
            group_key="other_review_required",
            group_label="Other / Review required",
            items=[
                _curve(
                    product_id="dsoz",
                    mnemonic="DSOZ",
                    product_category="other_review_required",
                    general_family_key="unclassified",
                    general_family="Unclassified",
                    measurement_domain_key=None,
                )
            ],
        )
    ]

    rebuilt = _rebuild_classified_well_log_groups_from_general_family(groups)
    by_key = {group.group_key: group for group in rebuilt}

    assert {item.curve_name for item in by_key["other_review_required"].items} == {
        "DSOZ"
    }


def test_non_classification_owned_geometry_item_is_not_rebucketed():
    geometry = _curve(
        product_id="geometry",
        mnemonic="DEVIATION",
        product_category="other_review_required",
        general_family_key="directional",
        general_family="Directional",
        measurement_domain_key="directional_survey",
        display_in_wdv=False,
        classification_contract_version=None,
        projection_version=None,
    )
    geometry.product_subgroup_key = "wellbore_geometry"
    geometry.product_subgroup_label = "Wellbore Geometry"

    groups = [
        ManagedProductGroup(
            group_key="other_review_required",
            group_label="Other / Review required",
            items=[geometry],
        )
    ]

    rebuilt = _rebuild_classified_well_log_groups_from_general_family(groups)
    by_key = {group.group_key: group for group in rebuilt}

    item = by_key["other_review_required"].items[0]
    assert item.product_subgroup_key == "wellbore_geometry"
    assert item.product_subgroup_label == "Wellbore Geometry"


def test_density_correction_and_density_share_same_mwd_general_family():
    groups = [
        ManagedProductGroup(
            group_key="open_hole_logs",
            group_label="Open hole logs",
            items=[
                _curve(
                    product_id="rhoz",
                    mnemonic="RHOZ",
                    product_category="open_hole_logs",
                    general_family_key="density",
                    general_family="Density",
                    measurement_domain_key="open_hole_log",
                ),
                _curve(
                    product_id="hdra",
                    mnemonic="HDRA",
                    product_category="open_hole_logs",
                    general_family_key="density",
                    general_family="Density",
                    measurement_domain_key="open_hole_log",
                ),
            ],
        )
    ]

    rebuilt = _rebuild_classified_well_log_groups_from_general_family(groups)
    items = next(g for g in rebuilt if g.group_key == "open_hole_logs").items

    assert {item.product_subgroup_key for item in items} == {"density"}
    assert {item.product_subgroup_label for item in items} == {"Density"}
