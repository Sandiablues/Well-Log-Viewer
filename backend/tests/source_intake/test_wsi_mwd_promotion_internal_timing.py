from pathlib import Path

from app.source_intake.promotion_performance import elapsed_ms, log_path, now


def test_promotion_performance_clock_and_log_path_contract():
    started = now()
    assert elapsed_ms(started) >= 0
    assert log_path().name == "wsi_mwd_promotion_performance.jsonl"


def test_promotion_timing_markers_are_installed():
    service = Path("app/source_intake/service.py").read_text(encoding="utf-8")
    registration = Path("app/source_intake/registration.py").read_text(encoding="utf-8")

    for marker in (
        "promotion_started",
        "source_intake_snapshot_loaded",
        "candidate_registration_completed",
        "source_intake_snapshot_saved",
        "promotion_completed",
    ):
        assert marker in service

    for marker in (
        "managed_inventory_repository_listed",
        "runtime_kr_classification_completed",
        "classification_authority_evaluation_completed",
        "managed_curve_items_constructed",
        "managed_product_groups_constructed",
        "managed_product_groups_merged",
        "managed_inventory_upsert_completed",
    ):
        assert marker in registration
