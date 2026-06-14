from backend.app.inventory.models import ManagedProductGroup, ManagedProductGroupItem
from backend.app.source_intake.registration import _merge_product_groups


def _item(
    *,
    product_id: str,
    curve_name: str,
    category: str,
    candidate_id: str,
    source: str,
) -> ManagedProductGroupItem:
    return ManagedProductGroupItem(
        product_id=product_id,
        display_name=curve_name,
        curve_name=curve_name,
        curve_type=curve_name,
        product_category=category,
        classification_source=source,
        source_intake_candidate_id=candidate_id,
    )


def test_merge_product_groups_replaces_stale_source_intake_candidate_items() -> None:
    stale = _item(
        product_id="source-intake-curve:candidate-1:1:af20",
        curve_name="AF20",
        category="other_review_required",
        candidate_id="candidate-1",
        source="backend_well_log_classifier",
    )
    unrelated = _item(
        product_id="source-intake-curve:candidate-2:1:gr",
        curve_name="GR",
        category="open_hole_logs",
        candidate_id="candidate-2",
        source="runtime_alias",
    )
    rebuilt = _item(
        product_id="source-intake-curve:candidate-1:1:af20",
        curve_name="AF20",
        category="open_hole_logs",
        candidate_id="candidate-1",
        source="runtime_alias",
    )

    merged = _merge_product_groups(
        [
            ManagedProductGroup(group_key="other_review_required", group_label="Other / Review Required", items=[stale]),
            ManagedProductGroup(group_key="open_hole_logs", group_label="Open Hole Logs", items=[unrelated]),
        ],
        [
            ManagedProductGroup(group_key="open_hole_logs", group_label="Open Hole Logs", items=[rebuilt]),
        ],
    )

    by_group = {group.group_key: group for group in merged}

    assert not by_group["other_review_required"].items
    assert {item.curve_name for item in by_group["open_hole_logs"].items} == {"AF20", "GR"}

    af20 = next(item for item in by_group["open_hole_logs"].items if item.curve_name == "AF20")
    assert af20.classification_source == "runtime_alias"
    assert af20.product_category == "open_hole_logs"
