from app.knowledge.runtime_classification_service import (
    CurveClassificationInput,
    RuntimeCurveClassificationService,
)
from app.knowledge.runtime_resolver import (
    RuntimeKnowledgePolicy,
    RuntimeKnowledgeSnapshot,
)


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

    def list_runtime_records(self, record_type=None):
        raise AssertionError(
            "Per-curve runtime record queries are forbidden in batch classification"
        )

    def list_approved_alias_enrichments(self, normalized_alias=None):
        raise AssertionError(
            "Per-curve alias enrichment queries are forbidden in batch classification"
        )


def test_batch_classification_builds_one_runtime_snapshot_for_67_curves():
    resolver = CountingResolver()
    service = RuntimeCurveClassificationService(resolver)

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
    assert result.curve_count == 67
    assert len(result.classifications) == 67


def test_single_curve_classification_builds_one_runtime_snapshot():
    resolver = CountingResolver()
    service = RuntimeCurveClassificationService(resolver)

    result = service.classify_curve(
        CurveClassificationInput(source_mnemonic="UNKNOWN")
    )

    assert resolver.build_snapshot_calls == 1
    assert result.resolved is False
