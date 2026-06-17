"""Structured deviation/directional survey parser for WLV Source Intake.

This parser supports both bounded scan-time preview and complete registration-time
parsing. It does not itself register trajectories, set active WBV state, or create
viewer packages.
"""

from __future__ import annotations

import csv
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from .models import (
    SourceIntakeDeviationSurveyColumnMapping,
    SourceIntakeDeviationSurveyPreview,
    SourceIntakeDeviationSurveyStationPreview,
)


class DeviationSurveyParseError(ValueError):
    """Raised when a structured deviation survey cannot be preview-parsed."""


_ALIAS_GROUPS: dict[str, tuple[str, ...]] = {
    "measured_depth": (
        "md", "measureddepth", "measured_depth", "measured depth", "dept", "depth", "hole depth",
    ),
    "inclination": (
        "inc", "incl", "inclination", "inclination_deg", "angle", "drift", "deviation",
    ),
    "azimuth": (
        "azi", "azim", "azimuth", "azimuth_deg", "bearing", "direction",
    ),
    "tvd": (
        "tvd", "true vertical depth", "true_vertical_depth", "vertical depth",
    ),
    "x_offset": (
        "x", "x offset", "x_offset", "ew", "east west", "departure", "e w",
    ),
    "y_offset": (
        "y", "y offset", "y_offset", "ns", "north south", "latitude offset", "n s",
    ),
    "northing": ("northing", "north", "n"),
    "easting": ("easting", "east", "e"),
}

_REQUIRED_FIELDS = ("measured_depth", "inclination", "azimuth")
_PREVIEW_LIMIT = 25


def parse_deviation_survey_preview(path: Path) -> SourceIntakeDeviationSurveyPreview:
    """Parse a structured survey file into a bounded backend-owned preview."""
    return _parse_deviation_survey(path, station_limit=_PREVIEW_LIMIT, parser_id="wlv_deviation_survey_parser_v2_preview")


def parse_deviation_survey_full(path: Path) -> SourceIntakeDeviationSurveyPreview:
    """Parse every valid survey station for durable MSI/WBV registration."""
    return _parse_deviation_survey(path, station_limit=None, parser_id="wlv_deviation_survey_parser_v2_full")


def _parse_deviation_survey(
    path: Path,
    *,
    station_limit: int | None,
    parser_id: str,
) -> SourceIntakeDeviationSurveyPreview:
    ext = path.suffix.lower().lstrip(".")
    if ext == "csv":
        headers, rows = _read_csv(path)
        source_format = "CSV"
    elif ext in {"txt", "asc"}:
        headers, rows = _read_text_table(path)
        source_format = "TEXT"
    elif ext in {"xlsx", "xls"}:
        if ext == "xls":
            raise DeviationSurveyParseError("Legacy .xls deviation survey parsing is not available without a binary Excel dependency.")
        headers, rows = _read_xlsx_first_sheet(path)
        source_format = "XLSX"
    else:
        raise DeviationSurveyParseError(f"Structured deviation survey parser does not support .{ext or 'unknown'} files.")

    if not headers:
        raise DeviationSurveyParseError("Deviation survey table has no header row.")

    mapping, warnings = _map_columns(headers)
    missing = [field for field in _REQUIRED_FIELDS if getattr(mapping, field) is None]
    if missing:
        label = ", ".join("MD" if field == "measured_depth" else field for field in missing)
        raise DeviationSurveyParseError(f"Deviation survey is missing required column(s): {label}")

    stations: list[SourceIntakeDeviationSurveyStationPreview] = []
    row_warnings: list[str] = []
    previous_md: float | None = None
    md_values: list[float] = []
    tvd_values: list[float] = []

    for row_index, raw_row in enumerate(rows, start=2):
        if not any(str(value).strip() for value in raw_row):
            continue
        row = _row_dict(headers, raw_row)
        try:
            md = _required_number(row, mapping.measured_depth, "MD")
            inc = _required_number(row, mapping.inclination, "inclination")
            azi = _required_number(row, mapping.azimuth, "azimuth")
        except DeviationSurveyParseError as exc:
            row_warnings.append(f"Row {row_index}: {exc}")
            continue

        tvd = _optional_number(row, mapping.tvd)
        x_offset = _optional_number(row, mapping.x_offset)
        y_offset = _optional_number(row, mapping.y_offset)
        northing = _optional_number(row, mapping.northing)
        easting = _optional_number(row, mapping.easting)

        if previous_md is not None and md <= previous_md:
            row_warnings.append(f"Row {row_index}: MD is not strictly increasing ({md:g} after {previous_md:g}).")
        previous_md = md

        if inc < 0 or inc > 180:
            row_warnings.append(f"Row {row_index}: inclination {inc:g} is outside 0-180 degrees.")
        if azi < 0 or azi >= 360:
            row_warnings.append(f"Row {row_index}: azimuth {azi:g} is outside 0-360 degrees.")
        if tvd is not None and tvd < 0:
            row_warnings.append(f"Row {row_index}: TVD {tvd:g} is negative.")

        md_values.append(md)
        if tvd is not None:
            tvd_values.append(tvd)

        if station_limit is None or len(stations) < station_limit:
            stations.append(
                SourceIntakeDeviationSurveyStationPreview(
                    row_index=row_index,
                    md=md,
                    inclination=inc,
                    azimuth=azi,
                    tvd=tvd,
                    x_offset=x_offset,
                    y_offset=y_offset,
                    northing=northing,
                    easting=easting,
                )
            )

    if not md_values:
        raise DeviationSurveyParseError("Deviation survey has no valid station rows after header mapping.")

    if mapping.tvd is None:
        warnings.append("TVD column was not mapped; preview is station-based only until trajectory calculation is added.")
    if mapping.x_offset is None and mapping.y_offset is None and mapping.northing is None and mapping.easting is None:
        warnings.append("No X/Y or Northing/Easting columns were mapped; spatial offsets will require later trajectory calculation.")

    warnings.extend(row_warnings)

    return SourceIntakeDeviationSurveyPreview(
        parser_id=parser_id,
        source_format=source_format,
        row_count=len(rows),
        station_count=len(md_values),
        preview_station_count=len(stations),
        column_mapping=mapping,
        md_min=min(md_values),
        md_max=max(md_values),
        tvd_min=min(tvd_values) if tvd_values else None,
        tvd_max=max(tvd_values) if tvd_values else None,
        warning_count=len(warnings),
        error_count=0,
        warnings=warnings,
        errors=[],
        stations_preview=stations,
    )


def _read_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(text.splitlines(), dialect))
    return _split_header_rows(rows)


def _read_text_table(path: Path) -> tuple[list[str], list[list[str]]]:
    lines = [line.strip() for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines() if line.strip()]
    if not lines:
        return [], []
    delimiter = _detect_text_delimiter(lines[0])
    rows = [_split_text_line(line, delimiter) for line in lines]
    return _split_header_rows(rows)


def _read_xlsx_first_sheet(path: Path) -> tuple[list[str], list[list[str]]]:
    ns = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    try:
        with zipfile.ZipFile(path) as zf:
            shared_strings = _xlsx_shared_strings(zf, ns)
            workbook = ET.fromstring(zf.read("xl/workbook.xml"))
            first_sheet = workbook.find("main:sheets/main:sheet", ns)
            if first_sheet is None:
                raise DeviationSurveyParseError("XLSX workbook has no visible sheet.")
            rel_id = first_sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
            target = None
            for rel in rels:
                if rel.attrib.get("Id") == rel_id:
                    target = rel.attrib.get("Target")
                    break
            if not target:
                raise DeviationSurveyParseError("Unable to resolve XLSX first sheet relationship.")
            sheet_path = "xl/" + target.lstrip("/")
            sheet = ET.fromstring(zf.read(sheet_path))
    except DeviationSurveyParseError:
        raise
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        raise DeviationSurveyParseError(f"Unable to read XLSX workbook: {exc}") from exc

    indexed_rows: list[tuple[int, list[str]]] = []
    for row in sheet.findall("main:sheetData/main:row", ns):
        values: dict[int, str] = {}
        for cell in row.findall("main:c", ns):
            ref = cell.attrib.get("r", "A1")
            col_index = _xlsx_column_index(ref)
            cell_type = cell.attrib.get("t")
            value_node = cell.find("main:v", ns)
            inline_node = cell.find("main:is/main:t", ns)
            value = ""
            if inline_node is not None and inline_node.text is not None:
                value = inline_node.text
            elif value_node is not None and value_node.text is not None:
                raw = value_node.text
                if cell_type == "s":
                    try:
                        value = shared_strings[int(raw)]
                    except Exception:
                        value = raw
                else:
                    value = raw
            values[col_index] = value
        if values:
            width = max(values) + 1
            indexed_rows.append((int(row.attrib.get("r", len(indexed_rows) + 1)), [values.get(index, "") for index in range(width)]))
    rows = [row_values for _, row_values in sorted(indexed_rows, key=lambda item: item[0])]
    return _split_header_rows(rows)


def _xlsx_shared_strings(zf: zipfile.ZipFile, ns: dict[str, str]) -> list[str]:
    try:
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    values: list[str] = []
    for item in root.findall("main:si", ns):
        parts = [node.text or "" for node in item.findall(".//main:t", ns)]
        values.append("".join(parts))
    return values


def _xlsx_column_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha()).upper() or "A"
    value = 0
    for ch in letters:
        value = value * 26 + (ord(ch) - ord("A") + 1)
    return value - 1


def _split_header_rows(rows: list[list[str]]) -> tuple[list[str], list[list[str]]]:
    normalized_rows = [[str(cell).strip() for cell in row] for row in rows]
    normalized_rows = [row for row in normalized_rows if any(cell for cell in row)]
    if not normalized_rows:
        return [], []
    headers = [cell.strip() for cell in normalized_rows[0]]
    return headers, normalized_rows[1:]


def _detect_text_delimiter(line: str) -> str | None:
    if "," in line:
        return ","
    if "\t" in line:
        return "\t"
    if ";" in line:
        return ";"
    return None


def _split_text_line(line: str, delimiter: str | None) -> list[str]:
    if delimiter:
        return [item.strip() for item in line.split(delimiter)]
    return [item.strip() for item in re.split(r"\s+", line.strip())]


def _map_columns(headers: list[str]) -> tuple[SourceIntakeDeviationSurveyColumnMapping, list[str]]:
    normalized_headers = [(_normalize_header(header), header) for header in headers if header.strip()]
    selected: dict[str, str | None] = {field: None for field in _ALIAS_GROUPS}
    used_headers: set[str] = set()
    warnings: list[str] = []

    # First pass: exact normalized alias equality. This is deterministic and
    # prevents short aliases such as "n" from matching INC or Northing.
    for field, aliases in _ALIAS_GROUPS.items():
        alias_keys = {_normalize_header(alias) for alias in aliases}
        for key, header in normalized_headers:
            if header in used_headers:
                continue
            if key in alias_keys:
                selected[field] = header
                used_headers.add(header)
                break

    # Second pass: conservative token/phrase matching for descriptive headers.
    # One- and two-character aliases are deliberately excluded from fuzzy use.
    for field, aliases in _ALIAS_GROUPS.items():
        if selected[field] is not None:
            continue
        for key, header in normalized_headers:
            if header in used_headers:
                continue
            if any(_header_matches_alias(key, alias) for alias in aliases):
                selected[field] = header
                used_headers.add(header)
                break

    mapped_headers = {value for value in selected.values() if value}
    unmapped_headers = [header for header in headers if header and header not in mapped_headers]
    if unmapped_headers:
        warnings.append("Unmapped deviation-survey column(s): " + ", ".join(unmapped_headers[:8]))

    return SourceIntakeDeviationSurveyColumnMapping(
        measured_depth=selected["measured_depth"],
        inclination=selected["inclination"],
        azimuth=selected["azimuth"],
        tvd=selected["tvd"],
        x_offset=selected["x_offset"],
        y_offset=selected["y_offset"],
        northing=selected["northing"],
        easting=selected["easting"],
        unmapped_headers=unmapped_headers,
    ), warnings


def _header_matches_alias(normalized_header: str, alias: str) -> bool:
    alias_key = _normalize_header(alias)
    if len(alias_key.replace(" ", "")) < 3:
        return False
    header_tokens = normalized_header.split()
    alias_tokens = alias_key.split()
    if len(alias_tokens) == 1:
        return alias_tokens[0] in header_tokens
    width = len(alias_tokens)
    return any(header_tokens[index:index + width] == alias_tokens for index in range(len(header_tokens) - width + 1))

def _normalize_header(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"\([^)]*\)", "", value)
    value = re.sub(r"\[[^]]*\]", "", value)
    value = value.replace("/", " ").replace("-", " ").replace("_", " ")
    return " ".join(value.split())


def _row_dict(headers: list[str], row: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for index, header in enumerate(headers):
        result[header] = row[index].strip() if index < len(row) else ""
    return result


def _required_number(row: dict[str, str], header: str | None, label: str) -> float:
    value = _optional_number(row, header)
    if value is None:
        raise DeviationSurveyParseError(f"{label} value is missing or non-numeric")
    return value


def _optional_number(row: dict[str, str], header: str | None) -> float | None:
    if header is None:
        return None
    raw = str(row.get(header, "")).strip()
    if raw == "":
        return None
    raw = raw.replace(",", "")
    try:
        return float(raw)
    except ValueError:
        return None
