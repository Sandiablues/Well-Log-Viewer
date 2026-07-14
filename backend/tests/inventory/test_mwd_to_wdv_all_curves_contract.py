from types import SimpleNamespace

from app.inventory.service import ManagedWellInventoryService


def item(**overrides):
    values = {
        "selectable": True,
        "display_in_wdv": True,
        "product_category": "open_hole_logs",
        "source_kind": "las",
        "general_curve_family_key": "sonic",
        "review_required": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_unclassified_curve_with_display_routing_false_still_enters_wdv_inventory() -> None:
    curve = item(
        display_in_wdv=False,
        product_category="other_review_required",
        general_curve_family_key="unclassified",
        review_required=True,
    )
    assert ManagedWellInventoryService._is_wdv_loadable_product(curve) is True


def test_nonselectable_managed_curve_still_enters_wdv_inventory() -> None:
    curve = item(selectable=False)
    assert ManagedWellInventoryService._is_wdv_loadable_product(curve) is True


def test_resolved_curve_enters_wdv_inventory() -> None:
    assert ManagedWellInventoryService._is_wdv_loadable_product(item()) is True


def test_supporting_document_does_not_enter_wdv_curve_inventory() -> None:
    document = item(product_category="supporting_documents", source_kind="pdf")
    assert ManagedWellInventoryService._is_wdv_loadable_product(document) is False


def test_document_source_kind_does_not_enter_wdv_curve_inventory() -> None:
    document = item(product_category="other_review_required", source_kind="document")
    assert ManagedWellInventoryService._is_wdv_loadable_product(document) is False
