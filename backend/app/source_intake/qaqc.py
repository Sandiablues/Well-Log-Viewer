"""Deterministic QAQC checks for WLV Source Intake candidates.

This module evaluates discovered/parsed/resolved source-intake candidates and
returns backend-owned QAQC status. It does not promote records into MSI/WMDP and
it does not create viewer representations.
"""

from __future__ import annotations

from collections import Counter
from enum import Enum
from typing import Iterable

from .models import (
    SourceFileCandidate,
    SourceIntakeCandidateRole,
    SourceIntakeFileType,
    SourceIntakeParseStatus,
    SourceIntakeQaqcCheck,
    SourceIntakeQaqcResult,
    SourceIntakeQaqcSeverity,
    SourceIntakeQaqcStatus,
)

_SEVERITY_RANK = {
    SourceIntakeQaqcSeverity.NONE: 0,
    SourceIntakeQaqcSeverity.LOW: 1,
    SourceIntakeQaqcSeverity.MEDIUM: 2,
    SourceIntakeQaqcSeverity.HIGH: 3,
}


def run_source_intake_qaqc(candidate: SourceFileCandidate) -> SourceIntakeQaqcResult:
    """Run deterministic candidate-level QAQC checks."""
    checks: list[SourceIntakeQaqcCheck] = []

    _check_file_integrity(candidate, checks)
    _check_candidate_role(candidate, checks)

    if candidate.detected_file_type == SourceIntakeFileType.LAS:
        _check_las_parse(candidate, checks)
        _check_well_identity(candidate, checks)
        _check_depth_log(candidate, checks)
        _check_curve_headers(candidate, checks)

    return _summarize(checks)


def _check_file_integrity(candidate: SourceFileCandidate, checks: list[SourceIntakeQaqcCheck]) -> None:
    if candidate.size_bytes > 0:
        checks.append(_pass("file.non_empty", "Source file is non-empty."))
    else:
        checks.append(_fail("file.non_empty", "Source file is empty.", field_name="size_bytes"))

    if candidate.checksum:
        checks.append(_pass("file.checksum", "Checksum/fingerprint is present."))
    else:
        checks.append(_fail("file.checksum", "Checksum/fingerprint is missing.", field_name="checksum"))


def _check_candidate_role(candidate: SourceFileCandidate, checks: list[SourceIntakeQaqcCheck]) -> None:
    if candidate.candidate_role == SourceIntakeCandidateRole.OTHER_REVIEW_REQUIRED:
        checks.append(
            _review(
                "candidate.role.review_required",
                "Candidate role requires review before registration or WMDP staging.",
                field_name="candidate_role",
                severity=SourceIntakeQaqcSeverity.MEDIUM,
            )
        )
        return

    if candidate.candidate_role == SourceIntakeCandidateRole.WELLBORE_GEOMETRY_CANDIDATE:
        checks.append(
            _review(
                "candidate.role.wellbore_geometry",
                "Wellbore Geometry candidate detected. Deviation-survey parsing and trajectory registration are not enabled in this block.",
                field_name="candidate_role",
                severity=SourceIntakeQaqcSeverity.MEDIUM,
            )
        )
        return

    checks.append(_pass("candidate.role.recognized", "Candidate role is recognized."))


def _check_las_parse(candidate: SourceFileCandidate, checks: list[SourceIntakeQaqcCheck]) -> None:
    if candidate.parser_status == SourceIntakeParseStatus.PARSE_FAILED:
        checks.append(
            _fail(
                "las.parse.failed",
                f"LAS metadata parse failed: {candidate.parse_error or 'unknown parser error'}",
                field_name="parser_status",
            )
        )
        return

    if candidate.parser_status == SourceIntakeParseStatus.NOT_PARSED:
        checks.append(
            _review(
                "las.parse.not_parsed",
                "LAS candidate has not been parsed yet.",
                field_name="parser_status",
                severity=SourceIntakeQaqcSeverity.MEDIUM,
            )
        )
        return

    if candidate.parser_status == SourceIntakeParseStatus.PARSED_WITH_WARNINGS:
        checks.append(
            _warning(
                "las.parse.warnings",
                "LAS metadata parsed with warnings.",
                field_name="parser_status",
                review_required=True,
            )
        )
    else:
        checks.append(_pass("las.parse.parsed", "LAS metadata parsed successfully."))

    if candidate.parsed_metadata is None:
        checks.append(_fail("las.metadata.present", "Parsed LAS metadata is missing."))
    else:
        checks.append(_pass("las.metadata.present", "Parsed LAS metadata is present."))


def _check_well_identity(candidate: SourceFileCandidate, checks: list[SourceIntakeQaqcCheck]) -> None:
    resolved = candidate.resolved_metadata
    parsed = candidate.parsed_metadata

    if resolved is not None:
        if resolved.well_name.value:
            checks.append(_pass("identity.well_name.present", "Well name resolved from source metadata."))
        else:
            checks.append(
                _review(
                    "identity.well_name.missing",
                    "Well name is missing from resolved source metadata.",
                    field_name="well_name",
                    severity=SourceIntakeQaqcSeverity.HIGH,
                )
            )

        if resolved.uwi.value:
            checks.append(_pass("identity.uwi.present", "UWI/API resolved from source metadata."))
        else:
            checks.append(
                _review(
                    "identity.uwi.missing",
                    "Missing UWI/API; review required before registration.",
                    field_name="uwi",
                    severity=SourceIntakeQaqcSeverity.MEDIUM,
                )
            )

        for warning in resolved.warnings:
            checks.append(
                _review(
                    "identity.resolver.warning",
                    warning,
                    severity=SourceIntakeQaqcSeverity.MEDIUM,
                )
            )
        return

    if parsed is not None and parsed.well_header.well_name:
        checks.append(_pass("identity.well_name.present", "Well name parsed from LAS well header."))
    else:
        checks.append(
            _review(
                "identity.well_name.missing",
                "Well name is missing from LAS well header.",
                field_name="well_name",
                severity=SourceIntakeQaqcSeverity.HIGH,
            )
        )


def _check_depth_log(candidate: SourceFileCandidate, checks: list[SourceIntakeQaqcCheck]) -> None:
    parsed = candidate.parsed_metadata
    log_header = parsed.log_header if parsed is not None else None
    if log_header is None:
        checks.append(_fail("log.header.present", "LAS log header is missing."))
        return

    checks.append(_pass("log.header.present", "LAS log header is present."))

    if log_header.start_depth is None:
        checks.append(_review("depth.start.missing", "Start depth is missing.", field_name="start_depth"))
    else:
        checks.append(_pass("depth.start.present", "Start depth is present."))

    if log_header.stop_depth is None:
        checks.append(_review("depth.stop.missing", "Stop depth is missing.", field_name="stop_depth"))
    else:
        checks.append(_pass("depth.stop.present", "Stop depth is present."))

    if log_header.step is None:
        checks.append(_review("depth.step.missing", "Depth step is missing.", field_name="step", severity=SourceIntakeQaqcSeverity.MEDIUM))
    else:
        checks.append(_pass("depth.step.present", "Depth step is present."))

    if log_header.start_depth is not None and log_header.stop_depth is not None:
        if log_header.stop_depth > log_header.start_depth:
            checks.append(_pass("depth.range.valid", "Depth range is valid."))
        else:
            checks.append(_fail("depth.range.invalid", "Stop depth must be greater than start depth.", field_name="stop_depth"))

    if log_header.curve_count > 0:
        checks.append(_pass("curve.count.positive", f"LAS contains {log_header.curve_count} curve(s)."))
    else:
        checks.append(_fail("curve.count.zero", "LAS contains no non-depth curves.", field_name="curve_count"))


def _check_curve_headers(candidate: SourceFileCandidate, checks: list[SourceIntakeQaqcCheck]) -> None:
    parsed = candidate.parsed_metadata
    curves = parsed.curve_headers if parsed is not None else []
    if not curves:
        checks.append(_fail("curve.headers.present", "Curve headers are missing."))
        return

    checks.append(_pass("curve.headers.present", "Curve headers are present."))

    mnemonics = []
    for index, curve in enumerate(curves, start=1):
        if curve.mnemonic and curve.mnemonic.strip():
            mnemonics.append(curve.mnemonic.strip().upper())
        else:
            checks.append(
                _fail(
                    "curve.mnemonic.missing",
                    f"Curve header {index} is missing a mnemonic.",
                    field_name="curve_headers.mnemonic",
                )
            )

        if curve.unit and curve.unit.strip():
            continue
        checks.append(
            _warning(
                "curve.unit.missing",
                f"Curve {curve.mnemonic or index} is missing a unit.",
                field_name="curve_headers.unit",
                review_required=False,
            )
        )

    duplicates = sorted(item for item, count in Counter(mnemonics).items() if count > 1)
    for mnemonic in duplicates:
        checks.append(
            _review(
                "curve.mnemonic.duplicate",
                f"Duplicate curve mnemonic detected: {mnemonic}.",
                field_name="curve_headers.mnemonic",
                severity=SourceIntakeQaqcSeverity.MEDIUM,
            )
        )


def _summarize(checks: Iterable[SourceIntakeQaqcCheck]) -> SourceIntakeQaqcResult:
    check_list = list(checks)
    warning_count = sum(1 for check in check_list if check.status in {SourceIntakeQaqcStatus.WARNING, SourceIntakeQaqcStatus.REVIEW_REQUIRED})
    failure_count = sum(1 for check in check_list if check.status == SourceIntakeQaqcStatus.FAIL)
    review_required = any(check.review_required or check.status == SourceIntakeQaqcStatus.REVIEW_REQUIRED for check in check_list)
    severity = _max_severity(check.severity for check in check_list)

    if failure_count:
        status = SourceIntakeQaqcStatus.FAIL
    elif review_required:
        status = SourceIntakeQaqcStatus.REVIEW_REQUIRED
    elif warning_count:
        status = SourceIntakeQaqcStatus.WARNING
    else:
        status = SourceIntakeQaqcStatus.PASS

    return SourceIntakeQaqcResult(
        status=status,
        severity=severity,
        check_count=len(check_list),
        warning_count=warning_count,
        failure_count=failure_count,
        review_required=review_required,
        messages=[check.message for check in check_list if check.status != SourceIntakeQaqcStatus.PASS],
        checks=check_list,
    )


def _max_severity(severities: Iterable[SourceIntakeQaqcSeverity]) -> SourceIntakeQaqcSeverity:
    selected = SourceIntakeQaqcSeverity.NONE
    for severity in severities:
        if _SEVERITY_RANK[severity] > _SEVERITY_RANK[selected]:
            selected = severity
    return selected


def _pass(check_id: str, message: str, field_name: str | None = None) -> SourceIntakeQaqcCheck:
    return SourceIntakeQaqcCheck(
        check_id=check_id,
        status=SourceIntakeQaqcStatus.PASS,
        severity=SourceIntakeQaqcSeverity.NONE,
        message=message,
        field_name=field_name,
    )


def _warning(
    check_id: str,
    message: str,
    field_name: str | None = None,
    review_required: bool = False,
    severity: SourceIntakeQaqcSeverity = SourceIntakeQaqcSeverity.LOW,
) -> SourceIntakeQaqcCheck:
    return SourceIntakeQaqcCheck(
        check_id=check_id,
        status=SourceIntakeQaqcStatus.WARNING,
        severity=severity,
        message=message,
        field_name=field_name,
        review_required=review_required,
    )


def _review(
    check_id: str,
    message: str,
    field_name: str | None = None,
    severity: SourceIntakeQaqcSeverity = SourceIntakeQaqcSeverity.MEDIUM,
) -> SourceIntakeQaqcCheck:
    return SourceIntakeQaqcCheck(
        check_id=check_id,
        status=SourceIntakeQaqcStatus.REVIEW_REQUIRED,
        severity=severity,
        message=message,
        field_name=field_name,
        review_required=True,
    )


def _fail(check_id: str, message: str, field_name: str | None = None) -> SourceIntakeQaqcCheck:
    return SourceIntakeQaqcCheck(
        check_id=check_id,
        status=SourceIntakeQaqcStatus.FAIL,
        severity=SourceIntakeQaqcSeverity.HIGH,
        message=message,
        field_name=field_name,
        review_required=True,
    )
