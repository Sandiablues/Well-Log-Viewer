from __future__ import annotations

from dataclasses import dataclass, asdict
from statistics import median
from typing import Any


@dataclass(frozen=True)
class DsmFinding:
    rule_id: str
    category: str
    severity: str
    message: str
    station_index: int | None = None
    field: str | None = None
    observed_value: Any = None
    expected_condition: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def assess_deviation_survey(
    stations: list[dict[str, Any]],
    *,
    survey_metadata: dict[str, Any] | None = None,
) -> list[DsmFinding]:
    """Apply deterministic DSM publication and review QAQC.

    This function never edits station values. It only returns findings.
    """
    findings: list[DsmFinding] = []
    metadata = survey_metadata or {}

    if len(stations) < 2:
        findings.append(DsmFinding(
            "DSM-PUB-001", "Publication blockers", "failure",
            "At least two accepted survey stations are required.",
            expected_condition="station count >= 2",
            observed_value=len(stations),
        ))

    depth_units = {str(row.get("depth_unit") or "").strip().lower() for row in stations if row.get("depth_unit")}
    if len(depth_units) > 1:
        findings.append(DsmFinding(
            "DSM-UNIT-001", "Units and references", "failure",
            "Accepted stations contain mixed unresolved depth units.",
            observed_value=sorted(depth_units),
            expected_condition="one resolved depth unit",
        ))

    dogleg_units = {str(row.get("dogleg_unit") or "").strip().lower() for row in stations if row.get("dogleg_unit")}
    if len(dogleg_units) > 1:
        findings.append(DsmFinding(
            "DSM-UNIT-002", "Units and references", "failure",
            "Accepted stations contain mixed unresolved dogleg units.",
            observed_value=sorted(dogleg_units),
            expected_condition="one resolved dogleg denominator",
        ))

    if not metadata.get("datum"):
        findings.append(DsmFinding(
            "DSM-REF-001", "Units and references", "warning",
            "Survey datum is not recorded.",
            field="datum",
        ))
    if not metadata.get("coordinate_origin"):
        findings.append(DsmFinding(
            "DSM-REF-001", "Units and references", "warning",
            "Coordinate origin is not recorded.",
            field="coordinate_origin",
        ))

    md_values: list[tuple[int, float]] = []
    intervals: list[float] = []
    previous_md: float | None = None

    for index, row in enumerate(stations):
        md = _number(row.get("measured_depth"))
        inc = _number(row.get("inclination"))
        azi = _number(row.get("azimuth"))
        tvd = _number(row.get("true_vertical_depth"))
        dls = _number(row.get("dogleg_severity"))

        for field, value in (("measured_depth", md), ("inclination", inc), ("azimuth", azi)):
            if value is None:
                findings.append(DsmFinding(
                    "DSM-REQ-001", "Required fields", "failure",
                    f"Station {index + 1} requires numeric {field}.",
                    station_index=index, field=field, observed_value=row.get(field),
                ))

        if md is not None:
            md_values.append((index, md))
            if previous_md is not None:
                interval = md - previous_md
                intervals.append(interval)
                if interval <= 0:
                    findings.append(DsmFinding(
                        "DSM-MD-001", "Depth sequence", "failure",
                        f"Station {index + 1} MD is not strictly increasing.",
                        station_index=index, field="measured_depth",
                        observed_value=md, expected_condition=f"> {previous_md}",
                    ))
            previous_md = md

        if inc is not None and not 0 <= inc <= 180:
            findings.append(DsmFinding(
                "DSM-INC-001", "Inclination and azimuth", "failure",
                f"Station {index + 1} inclination is outside 0–180 degrees.",
                station_index=index, field="inclination", observed_value=inc,
            ))

        if azi is not None and not 0 <= azi < 360:
            findings.append(DsmFinding(
                "DSM-AZI-001", "Inclination and azimuth", "failure",
                f"Station {index + 1} azimuth is outside 0–<360 degrees.",
                station_index=index, field="azimuth", observed_value=azi,
            ))

        if md is not None and tvd is not None and tvd > md + 1e-9:
            findings.append(DsmFinding(
                "DSM-TVD-001", "Trajectory calculation", "warning",
                f"Station {index + 1} source TVD exceeds MD.",
                station_index=index, field="true_vertical_depth",
                observed_value=tvd, expected_condition=f"<= {md} when datum and units match",
            ))

        if dls is not None and dls < 0:
            findings.append(DsmFinding(
                "DSM-DLS-001", "Trajectory calculation", "failure",
                f"Station {index + 1} has negative dogleg severity.",
                station_index=index, field="dogleg_severity", observed_value=dls,
            ))

        station_type = str(row.get("station_type") or "").strip().lower()
        if station_type == "extrapolated":
            findings.append(DsmFinding(
                "DSM-EXT-001", "Extrapolated and calculated stations", "information",
                f"Station {index + 1} is explicitly extrapolated.",
                station_index=index, field="station_type", observed_value=station_type,
            ))
        elif station_type == "casing":
            findings.append(DsmFinding(
                "DSM-CAS-001", "Extrapolated and calculated stations", "information",
                f"Station {index + 1} is a casing or marker position.",
                station_index=index, field="station_type", observed_value=station_type,
            ))

    by_md: dict[float, list[int]] = {}
    for index, md in md_values:
        by_md.setdefault(md, []).append(index)
    for md, indices in by_md.items():
        if len(indices) > 1:
            findings.append(DsmFinding(
                "DSM-MD-002", "Depth sequence", "failure",
                f"Duplicate accepted MD {md:g} occurs at stations {', '.join(str(i + 1) for i in indices)}.",
                field="measured_depth", observed_value=md,
            ))

    positive_intervals = [value for value in intervals if value > 0]
    if len(positive_intervals) >= 4:
        typical = median(positive_intervals)
        if typical > 0:
            for offset, value in enumerate(intervals, start=1):
                if value > typical * 5:
                    findings.append(DsmFinding(
                        "DSM-MD-003", "Survey completeness", "warning",
                        f"Large unexplained station gap of {value:g} compared with local median {typical:g}.",
                        station_index=offset, field="measured_depth",
                        observed_value=value,
                    ))

    for index in range(1, len(stations)):
        previous = stations[index - 1]
        current = stations[index]
        inc = _number(current.get("inclination"))
        previous_azi = _number(previous.get("azimuth"))
        current_azi = _number(current.get("azimuth"))
        if inc is not None and inc >= 1.0 and previous_azi is not None and current_azi is not None:
            raw = abs(current_azi - previous_azi)
            delta = min(raw, 360 - raw)
            if delta >= 150:
                findings.append(DsmFinding(
                    "DSM-AZI-002", "Inclination and azimuth", "warning",
                    f"Station {index + 1} has an abrupt azimuth reversal of {delta:g} degrees.",
                    station_index=index, field="azimuth", observed_value=current_azi,
                ))

    return findings


def publication_state(findings: list[DsmFinding]) -> str:
    if any(item.severity == "failure" for item in findings):
        return "blocked"
    if any(item.severity == "warning" for item in findings):
        return "ready_with_warnings"
    return "ready"
