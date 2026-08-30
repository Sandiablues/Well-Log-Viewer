from pathlib import Path

import pytest

from app.knowledge.api_managed_instructions import list_instructions


@pytest.fixture(autouse=True)
def use_real_managed_kr(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent leaked temporary KR paths from other tests contaminating this suite."""
    managed_kr = Path("data/knowledge/managed_knowledge.json").resolve()
    assert managed_kr.is_file(), managed_kr
    monkeypatch.setenv("WLV_KR_MANAGED_KNOWLEDGE_PATH", str(managed_kr))


def test_exact_mnemonic_search_is_ranked_and_not_page_limited() -> None:
    payload = list_instructions(
        q="RDEP",
        limit=50,
        offset=0,
        approved_only=True,
    )

    assert payload.search_ranked is True
    assert payload.total_count >= 1
    rows = payload.instructions
    assert rows
    first = rows[0]
    searchable = " ".join(
        str(getattr(first, key, "") or "")
        for key in ("mnemonic", "alias", "canonical_curve_id", "subject", "must_do")
    ).upper()
    assert "RDEP" in searchable


def test_catalogue_pagination_returns_non_overlapping_pages() -> None:
    first = list_instructions(
        limit=500,
        offset=0,
        approved_only=True,
    )
    second = list_instructions(
        limit=500,
        offset=500,
        approved_only=True,
    )

    assert first.offset == 0
    assert second.offset == 500
    assert first.limit == 500
    assert second.limit == 500
    assert first.has_previous is False
    assert second.has_previous is True

    first_ids = {item.instruction_id for item in first.instructions}
    second_ids = {item.instruction_id for item in second.instructions}
    assert first_ids.isdisjoint(second_ids)
