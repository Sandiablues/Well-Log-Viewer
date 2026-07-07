from types import SimpleNamespace

from app.source_intake.registration import (
    _managed_run_interval,
    _source_intake_provenance,
)


def test_managed_run_interval_uses_selected_canonical_unit():
    assert _managed_run_interval(189.8904, 3795.0648, "m") == "189.89–3795.06 m"
    assert _managed_run_interval(623.0, 12451.0, "ft") == "623–12451 ft"


def test_depth_decision_is_persisted_in_source_provenance():
    candidate = SimpleNamespace(
        source_file_id="candidate-f5",
        repository_id="repo",
        scan_id="scan",
        relative_path="WLC_PETROPHYSICAL_COMPOSITE_1.DLIS",
        original_path="/source/WLC_PETROPHYSICAL_COMPOSITE_1.DLIS",
        checksum="sha256-f5",
        parser_status=SimpleNamespace(value="parsed_with_warnings"),
        qaqc_status=SimpleNamespace(model_dump=lambda mode: {"status": "review_required"}),
        resolved_metadata=None,
        depth_normalization=SimpleNamespace(
            raw_unit="0.1 in",
            raw_start_depth=74760.0,
            raw_stop_depth=1494120.0,
            status=SimpleNamespace(value="human_resolved"),
            reason="human_target_unit_required",
            decision=SimpleNamespace(
                target_unit="m",
                actor="operator",
                decided_at="2026-07-06T08:00:00+00:00",
                reason="Volve source convention",
            ),
        ),
    )

    provenance = _source_intake_provenance(candidate)
    depth = provenance["depth_normalization"]
    assert depth["raw_unit"] == "0.1 in"
    assert depth["selected_target_unit"] == "m"
    assert depth["decision_actor"] == "operator"
    assert depth["decision_timestamp"] == "2026-07-06T08:00:00+00:00"
