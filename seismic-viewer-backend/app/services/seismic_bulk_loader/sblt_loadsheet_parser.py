"""
SBLT-1: Loadsheet parser for prepared seismic bulk loadsheets.

Ownership: backend SBLT service.

Supported formats:
- .csv  — always supported (Python stdlib csv module)
- .xlsx — supported only if openpyxl is importable without dependency changes.
          If openpyxl is not available, raises UnsupportedFormatError with a clear message.

SBLT-1 scope:
- Read the file and return rows with original column names and original values.
- Do not canonicalise columns.
- Do not normalise metadata.
- Do not validate file references.
- Do not classify 2D/3D.

Each returned row dict has the shape:
    {
        "source_row_number": int,   # 1-based; header is implied row 1
        "source_values": dict,      # original column name → original raw value (str)
    }

source_row_number uses spreadsheet-style numbering:
- Row 1 is the header row.
- First data row is row 2.
- This matches what a user sees when they open the file in Excel/Calc.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


class ParseError(Exception):
    """Raised when the loadsheet cannot be parsed."""


class UnsupportedFormatError(ValueError):
    """Raised when the loadsheet format is not supported in this build."""


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------

def _parse_csv(path: Path) -> list[dict[str, Any]]:
    """
    Parse a CSV loadsheet.

    Returns a list of rows. Each row is:
        {"source_row_number": int, "source_values": dict}

    source_row_number is 2-based (row 1 = header).
    Empty rows (all blank values) are skipped.
    """
    rows: list[dict[str, Any]] = []

    try:
        with path.open(newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames is None:
                raise ParseError("CSV has no header row or is empty.")

            # csv.DictReader starts data at the second physical line (row 2 in
            # spreadsheet numbering). reader.line_num starts at 1 after the
            # header has been consumed.
            for data_row in reader:
                # reader.line_num reflects the last line read (1-based from the
                # file start), so this correctly tracks spreadsheet row numbers.
                source_row_number = reader.line_num

                # Skip rows where every value is blank.
                values = {k: (v or "") for k, v in data_row.items() if k is not None}
                if all(v.strip() == "" for v in values.values()):
                    continue

                rows.append({
                    "source_row_number": source_row_number,
                    "source_values": values,
                })

    except UnicodeDecodeError:
        # Retry with latin-1 for legacy files.
        rows = _parse_csv_latin1(path)
    except (OSError, IOError) as exc:
        raise ParseError(f"Cannot read CSV file: {exc}") from exc

    return rows


def _parse_csv_latin1(path: Path) -> list[dict[str, Any]]:
    """Fallback CSV parser with latin-1 encoding."""
    rows: list[dict[str, Any]] = []
    try:
        with path.open(newline="", encoding="latin-1") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames is None:
                raise ParseError("CSV has no header row or is empty (latin-1 fallback).")
            for data_row in reader:
                source_row_number = reader.line_num
                values = {k: (v or "") for k, v in data_row.items() if k is not None}
                if all(v.strip() == "" for v in values.values()):
                    continue
                rows.append({
                    "source_row_number": source_row_number,
                    "source_values": values,
                })
    except (OSError, IOError) as exc:
        raise ParseError(f"Cannot read CSV file (latin-1 fallback): {exc}") from exc
    return rows


# ---------------------------------------------------------------------------
# XLSX
# ---------------------------------------------------------------------------

def _parse_xlsx(path: Path) -> list[dict[str, Any]]:
    """
    Parse an XLSX loadsheet using openpyxl.

    Raises UnsupportedFormatError if openpyxl is not importable.
    """
    try:
        import openpyxl  # noqa: F401 — checked for availability only
    except ImportError:
        raise UnsupportedFormatError(
            "XLSX loadsheets require openpyxl, which is not installed in this "
            "backend environment. Please convert your loadsheet to CSV and retry, "
            "or ask the administrator to install openpyxl."
        )

    try:
        wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    except Exception as exc:
        raise ParseError(f"Cannot open XLSX file: {exc}") from exc

    try:
        ws = wb.active
        if ws is None:
            raise ParseError("XLSX workbook has no active sheet.")

        rows_iter = ws.iter_rows(values_only=True)

        # First row is the header.
        try:
            header_row = next(rows_iter)
        except StopIteration:
            raise ParseError("XLSX file is empty — no header row found.")

        headers = [str(h) if h is not None else f"Column_{i}" for i, h in enumerate(header_row)]
        if not any(h.strip() for h in headers):
            raise ParseError("XLSX header row is blank.")

        rows: list[dict[str, Any]] = []
        # Physical row 1 = header. Data rows start at physical row 2.
        physical_row_number = 1
        for data_row in rows_iter:
            physical_row_number += 1
            values = {headers[i]: (str(cell) if cell is not None else "") for i, cell in enumerate(data_row)}
            if all(v.strip() == "" for v in values.values()):
                continue
            rows.append({
                "source_row_number": physical_row_number,
                "source_values": values,
            })

    finally:
        wb.close()

    return rows


# ---------------------------------------------------------------------------
# Public dispatcher
# ---------------------------------------------------------------------------

def parse_loadsheet(path: str | Path) -> list[dict[str, Any]]:
    """
    Parse a prepared seismic loadsheet from a file path.

    Returns a list of row dicts:
        [{"source_row_number": int, "source_values": dict}, ...]

    Raises:
        ValueError      — path is not absolute, file does not exist,
                          or extension is not supported.
        UnsupportedFormatError — XLSX requested but openpyxl not available.
        ParseError      — file cannot be parsed.
    """
    p = Path(path)

    if not p.is_absolute():
        raise ValueError(f"loadsheet_path must be an absolute path. Got: {path!r}")

    if not p.exists():
        raise FileNotFoundError(f"Loadsheet file not found: {path!r}")

    ext = p.suffix.lower()

    if ext == ".csv":
        return _parse_csv(p)

    if ext in {".xlsx", ".xls"}:
        return _parse_xlsx(p)

    raise ValueError(
        f"Unsupported loadsheet format: {ext!r}. "
        "Supported formats in this build: .csv"
        " (and .xlsx if openpyxl is installed)."
    )
