from app.inventory.models import (
    ManagedProductGroup,
    ManagedProductGroupItem,
    ManagedSourceKind,
    ManagedSourceReference,
)
from app.source_intake.registration import (
    _merge_product_groups,
    _merge_source_references,
)


SOURCE_SHA = "a" * 64


def _curve(*, candidate_id: str, product_id: str, mnemonic: str) -> ManagedProductGroupItem:
    return ManagedProductGroupItem(
        product_id=product_id,
        display_name=mnemonic,
        curve_name=mnemonic,
        curve_type="Test",
        source_intake_candidate_id=candidate_id,
        provenance={
            "checksum": SOURCE_SHA,
            "source_intake_candidate_id": candidate_id,
        },
    )


def test_same_source_checksum_new_occurrence_replaces_old_managed_curves():
    existing = [
        ManagedProductGroup(
            group_key="open_hole_logs",
            group_label="Open Hole Logs",
            items=[
                _curve(
                    candidate_id="occurrence-a",
                    product_id="source-intake-curve:occurrence-a:0:GR",
                    mnemonic="GR",
                ),
                _curve(
                    candidate_id="occurrence-a",
                    product_id="source-intake-curve:occurrence-a:1:RHOB",
                    mnemonic="RHOB",
                ),
            ],
        )
    ]
    incoming = [
        ManagedProductGroup(
            group_key="open_hole_logs",
            group_label="Open Hole Logs",
            items=[
                _curve(
                    candidate_id="occurrence-b",
                    product_id="source-intake-curve:occurrence-b:0:GR",
                    mnemonic="GR",
                ),
                _curve(
                    candidate_id="occurrence-b",
                    product_id="source-intake-curve:occurrence-b:1:RHOB",
                    mnemonic="RHOB",
                ),
            ],
        )
    ]

    merged = _merge_product_groups(existing, incoming)

    items = [
        item
        for group in merged
        for item in group.items
    ]

    assert len(items) == 2
    assert {item.source_intake_candidate_id for item in items} == {"occurrence-b"}
    assert {
        item.product_id
        for item in items
    } == {
        "source-intake-curve:occurrence-b:0:GR",
        "source-intake-curve:occurrence-b:1:RHOB",
    }


def test_same_source_checksum_new_occurrence_replaces_old_source_reference():
    old = ManagedSourceReference(
        source_id="occurrence-a",
        source_kind=ManagedSourceKind.LAS,
        display_name="F 21-31",
        checksum=SOURCE_SHA,
    )
    new = ManagedSourceReference(
        source_id="occurrence-b",
        source_kind=ManagedSourceKind.LAS,
        display_name="F 21-31",
        checksum=SOURCE_SHA,
    )

    merged = _merge_source_references([old], new)

    assert len(merged) == 1
    assert merged[0].source_id == "occurrence-b"
    assert merged[0].checksum == SOURCE_SHA


def test_different_source_checksum_is_not_removed():
    old = ManagedSourceReference(
        source_id="source-a",
        source_kind=ManagedSourceKind.LAS,
        display_name="Source A",
        checksum="b" * 64,
    )
    new = ManagedSourceReference(
        source_id="source-b",
        source_kind=ManagedSourceKind.LAS,
        display_name="Source B",
        checksum=SOURCE_SHA,
    )

    merged = _merge_source_references([old], new)

    assert {reference.source_id for reference in merged} == {"source-a", "source-b"}
