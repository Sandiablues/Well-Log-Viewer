from pathlib import Path

from app.source_intake.promotion_full_profiler import (
    PromotionProfilingRoute,
    _architectural_counts,
    _profile_rows,
)


def test_profiler_route_contract_is_installed():
    router = Path("app/source_intake/router.py").read_text(encoding="utf-8")
    assert "route_class=PromotionProfilingRoute" in router
    assert "profile_promotion_endpoint(" in router


def test_architectural_count_aggregation_is_deterministic():
    rows = [
        {
            "filename": "/x/runtime_resolver.py",
            "line": 10,
            "function": "build_snapshot",
            "primitive_calls": 3,
            "calls": 3,
            "self_time": 1.0,
            "cumulative_time": 2.0,
        },
        {
            "filename": "/x/runtime_classification_service.py",
            "line": 20,
            "function": "_classify_one",
            "primitive_calls": 67,
            "calls": 67,
            "self_time": 4.0,
            "cumulative_time": 7.0,
        },
    ]
    counts = _architectural_counts(rows)
    assert counts["runtime_snapshot_build"]["calls"] == 3
    assert counts["runtime_classify_one"]["calls"] == 67
