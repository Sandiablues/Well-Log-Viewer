from app.knowledge.runtime_classification_service import (
    CurveClassificationInput,
    RuntimeCurveClassificationService,
)
from app.knowledge.runtime_resolver import RuntimeKnowledgePolicy, RuntimeKnowledgeSnapshot


class CountingResolver:
    def __init__(self):
        self.build_snapshot_calls = 0

    def build_snapshot(self):
        self.build_snapshot_calls += 1
        return RuntimeKnowledgeSnapshot(
            kr_version="test",
            policy=RuntimeKnowledgePolicy(),
            records=(),
            evidence=(),
        )


def test_batch_shadow_observer_receives_the_existing_runtime_resolver_once(monkeypatch):
    resolver = CountingResolver()
    service = RuntimeCurveClassificationService(resolver)
    captured = []

    def fake_batch_observer(*, curves, authoritative_results, runtime_resolver):
        captured.append((list(curves), list(authoritative_results), runtime_resolver))

    monkeypatch.setattr(
        "app.classification_orchestration.live_shadow_observer.observe_runtime_batch_authoritative",
        fake_batch_observer,
    )

    curves = [
        CurveClassificationInput(
            source_mnemonic=f"UNKNOWN_{index}",
            curve_id=f"curve-{index}",
            source_curve_index=index,
        )
        for index in range(67)
    ]

    result = service.classify_curves(curves)

    assert resolver.build_snapshot_calls == 1
    assert len(captured) == 1
    observed_curves, observed_results, observed_resolver = captured[0]
    assert len(observed_curves) == 67
    assert len(observed_results) == 67
    assert observed_resolver is resolver
    assert result.curve_count == 67
