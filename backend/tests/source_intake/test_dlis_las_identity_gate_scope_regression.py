from types import SimpleNamespace

from app.source_intake.identity_gate import apply_identity_gate
from app.source_intake.models import SourceIntakeFileType


def _field(value):
    return SimpleNamespace(value=value)


def _candidate(file_type):
    resolved = SimpleNamespace(
        well_name=_field("WELL"),
        uwi=_field("UNIQUE WELL ID"),
        operator=_field("COMPANY"),
        field=_field("FIELD"),
        block=_field(None),
        review_required=False,
        warning_count=0,
        warnings=[],
    )
    parsed = SimpleNamespace(
        log_header=SimpleNamespace(curve_count=2),
        curve_headers=[],
    )
    return SimpleNamespace(
        detected_file_type=file_type,
        parsed_metadata=parsed,
        resolved_metadata=resolved,
        review_required=False,
        warnings=[],
        source_file_id=f"{file_type.value}-candidate",
        relative_path=f"{file_type.value.lower()}/source",
        file_name=f"source.{file_type.value.lower()}",
    )


def test_weak_generic_las_identity_still_requires_review():
    candidate = _candidate(SourceIntakeFileType.LAS)

    apply_identity_gate([candidate])

    assert candidate.review_required is True
    assert candidate.warnings == [
        "Weak/generic LAS identity requires review before registration."
    ]
    assert candidate.resolved_metadata.review_required is True


def test_weak_generic_dlis_identity_does_not_receive_las_specific_review_warning():
    candidate = _candidate(SourceIntakeFileType.DLIS)

    apply_identity_gate([candidate])

    assert candidate.review_required is False
    assert candidate.warnings == []
    assert candidate.resolved_metadata.review_required is False
    assert candidate.resolved_metadata.warnings == []


def test_dlis_identity_does_not_supply_strong_identity_to_las_package_gate():
    strong_dlis = _candidate(SourceIntakeFileType.DLIS)
    strong_dlis.resolved_metadata.well_name.value = "F-1"
    strong_dlis.resolved_metadata.uwi.value = "DLIS-UWI"

    weak_las = _candidate(SourceIntakeFileType.LAS)

    apply_identity_gate([strong_dlis, weak_las])

    assert strong_dlis.review_required is False
    assert strong_dlis.warnings == []
    assert weak_las.review_required is True
    assert weak_las.warnings == [
        "Weak/generic LAS identity requires review before registration."
    ]
