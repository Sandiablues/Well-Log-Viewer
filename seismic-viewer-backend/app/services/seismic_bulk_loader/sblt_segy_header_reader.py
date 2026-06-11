"""
SBLT-5: SEG-Y fixed-header reader using Python stdlib only.

Reads only:
  - Textual header:       bytes 0–3199     (3200 bytes, EBCDIC or ASCII)
  - Binary header:        bytes 3200–3599  (400 bytes)
  - First trace header:   bytes 3600–3839  (240 bytes, optional)

Does NOT:
  - Read trace sample data.
  - Build geometry.
  - Scan folders.
  - Index SEG-Y.
  - Convert to Zarr.
  - Register MSI records.

No third-party dependencies.  No MDE imports.  No SBLT session imports.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Size constants
# ---------------------------------------------------------------------------

TEXTUAL_HEADER_BYTES = 3200
BINARY_HEADER_BYTES = 400
TRACE_HEADER_BYTES = 240
MIN_FILE_SIZE = TEXTUAL_HEADER_BYTES + BINARY_HEADER_BYTES  # 3600 bytes

# ---------------------------------------------------------------------------
# Data sample format code → name
# ---------------------------------------------------------------------------

DATA_SAMPLE_FORMAT_MAP: dict[int, str] = {
    1: "IBM float",
    2: "32-bit integer",
    3: "16-bit integer",
    5: "IEEE float",
    8: "8-bit integer",
}

# Measurement system code → name
MEASUREMENT_SYSTEM_MAP: dict[int, str] = {
    1: "meters",
    2: "feet",
}


# ---------------------------------------------------------------------------
# Textual header decoding
# ---------------------------------------------------------------------------

def _decode_textual_header(raw_bytes: bytes) -> tuple[str, str]:
    """
    Decode 3200-byte textual header.

    Tries EBCDIC (cp037) then Latin-1.  Selects the encoding that yields the
    higher ratio of printable + whitespace characters.

    Returns (decoded_text, encoding_guess).
    """
    candidates: list[tuple[str, str, float]] = []
    for enc in ("cp037", "latin-1"):
        try:
            text = raw_bytes.decode(enc, errors="replace")
            printable = sum(
                1 for c in text if c.isprintable() or c in ("\n", "\r", "\t", " ")
            )
            ratio = printable / max(len(text), 1)
            candidates.append((text, enc, ratio))
        except Exception:
            pass

    if not candidates:
        return raw_bytes.decode("latin-1", errors="replace"), "latin-1"

    best = max(candidates, key=lambda x: x[2])
    return best[0], best[1]


def _split_textual_lines(text: str) -> list[str]:
    """
    Split decoded textual header into up to 80 lines (max 80 chars each).

    SEG-Y EBCDIC headers are typically 40 lines × 80 chars with no embedded
    newlines.  ASCII headers may already have newlines.
    Stores only non-blank lines to keep the payload compact.
    """
    # Strip null chars
    text = text.replace("\x00", " ")

    # If already line-broken (ASCII-style), use those breaks
    if text.count("\n") >= 10:
        lines = [ln.rstrip("\r")[:80] for ln in text.split("\n")]
        return [ln for ln in lines if ln.strip()][:80]

    # Standard EBCDIC: 40 lines × 80 chars
    lines = []
    for i in range(40):
        start = i * 80
        end = start + 80
        line = text[start:end] if start < len(text) else ""
        if line.strip():
            lines.append(line.rstrip())
    return lines


# ---------------------------------------------------------------------------
# Binary header parsing
# ---------------------------------------------------------------------------

def _parse_binary_header(binary_bytes: bytes, endian: str = ">") -> dict[str, Any]:
    """
    Parse the 400-byte binary header.

    Byte offsets below are 0-indexed relative to the start of binary_bytes
    (i.e. relative to file byte 3200).

    SEG-Y Rev 1 field map (1-indexed file bytes → 0-indexed binary-header offset):
        job_id              bytes 3201-3204 → offset  0:4   (4-byte signed int)
        line_number         bytes 3205-3208 → offset  4:8   (4-byte signed int)
        reel_number         bytes 3209-3212 → offset  8:12  (4-byte signed int)
        sample_interval_us  bytes 3217-3218 → offset 16:18  (2-byte unsigned int)
        samples_per_trace   bytes 3221-3222 → offset 20:22  (2-byte unsigned int)
        data_sample_format  bytes 3225-3226 → offset 24:26  (2-byte unsigned int)
        measurement_system  bytes 3255-3256 → offset 54:56  (2-byte unsigned int)

    Args:
        binary_bytes: Exactly 400 bytes (binary header only, not offset from 0).
        endian:       ">" = big-endian (SEG-Y standard).

    Returns a dict with the parsed fields plus diagnostics.
    """
    int4_fmt = endian + "i"
    uint2_fmt = endian + "H"

    def _i4(offset: int) -> int | None:
        try:
            return struct.unpack_from(int4_fmt, binary_bytes, offset)[0]
        except struct.error:
            return None

    def _u2(offset: int) -> int | None:
        try:
            return struct.unpack_from(uint2_fmt, binary_bytes, offset)[0]
        except struct.error:
            return None

    job_id = _i4(0)
    line_number = _i4(4)
    reel_number = _i4(8)
    sample_interval_us = _u2(16)
    samples_per_trace = _u2(20)
    data_sample_format_code = _u2(24)
    measurement_system_raw = _u2(54)

    errors: list[str] = []
    warnings: list[str] = []

    # Sanity checks
    if sample_interval_us is not None:
        if sample_interval_us == 0:
            warnings.append("sample_interval_us is 0 — may indicate endianness issue")
        elif sample_interval_us > 32000:
            warnings.append(
                f"sample_interval_us={sample_interval_us} > 32000 µs; "
                "may indicate endianness mismatch"
            )

    if samples_per_trace is not None:
        if samples_per_trace == 0:
            warnings.append("samples_per_trace is 0 — may indicate endianness issue")
        elif samples_per_trace > 50000:
            warnings.append(
                f"samples_per_trace={samples_per_trace} unusually large; "
                "may indicate endianness mismatch"
            )

    if data_sample_format_code is not None and data_sample_format_code > 0:
        if data_sample_format_code not in DATA_SAMPLE_FORMAT_MAP:
            warnings.append(
                f"data_sample_format_code={data_sample_format_code} is unknown"
            )

    # measurement_system: 1=meters, 2=feet; 0=unset
    measurement_system: int | None = None
    if measurement_system_raw in (1, 2):
        measurement_system = measurement_system_raw

    return {
        "job_id": job_id,
        "line_number": line_number,
        "reel_number": reel_number,
        "sample_interval_us": sample_interval_us,
        "samples_per_trace": samples_per_trace,
        "data_sample_format_code": data_sample_format_code,
        "measurement_system": measurement_system,
        "measurement_system_raw": measurement_system_raw,
        "errors": errors,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Internal summary builder
# ---------------------------------------------------------------------------

def _make_error_summary(
    file_size: int,
    bytes_read: int,
    error_msg: str,
) -> dict[str, Any]:
    return {
        "textual_header_read": False,
        "binary_header_read": False,
        "first_trace_header_read": False,
        "bytes_read": bytes_read,
        "file_size_bytes": file_size,
        "encoding_guess": "unknown",
        "endian_guess": "unknown",
        "warnings": [],
        "errors": [error_msg],
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def read_segy_fixed_headers(path: Path) -> dict[str, Any]:
    """
    Read only the fixed SEG-Y headers from a file.

    Reads at most TEXTUAL_HEADER_BYTES + BINARY_HEADER_BYTES + TRACE_HEADER_BYTES
    bytes.  Never reads trace sample data.  Never builds geometry.

    Args:
        path: Resolved, absolute, readable Path to the SEG-Y file.

    Returns:
        {
            "ok": bool,                  # True iff both textual + binary headers read OK
            "binary_fields": dict|None,  # Parsed binary header fields
            "textual_lines": list|None,  # Decoded textual header lines (compact)
            "header_read_summary": {     # Diagnostic summary
                "textual_header_read": bool,
                "binary_header_read": bool,
                "first_trace_header_read": bool,
                "bytes_read": int,
                "file_size_bytes": int,
                "encoding_guess": str,
                "endian_guess": str,
                "warnings": list[str],
                "errors": list[str],
            },
            "error": str|None,           # High-level error string if not ok
        }
    """
    summary_warnings: list[str] = []
    summary_errors: list[str] = []

    # --- Stat ---
    try:
        file_size = path.stat().st_size
    except OSError as exc:
        return {
            "ok": False,
            "binary_fields": None,
            "textual_lines": None,
            "header_read_summary": _make_error_summary(0, 0, f"Cannot stat file: {exc}"),
            "error": f"Cannot stat file: {exc}",
        }

    # --- Minimum size check ---
    if file_size < MIN_FILE_SIZE:
        return {
            "ok": False,
            "binary_fields": None,
            "textual_lines": None,
            "header_read_summary": {
                "textual_header_read": False,
                "binary_header_read": False,
                "first_trace_header_read": False,
                "bytes_read": 0,
                "file_size_bytes": file_size,
                "encoding_guess": "unknown",
                "endian_guess": "unknown",
                "warnings": [],
                "errors": [
                    f"File too small: {file_size} bytes < "
                    f"{MIN_FILE_SIZE} required for fixed headers"
                ],
            },
            "error": (
                f"SEGY_HEADER_TOO_SMALL: file has {file_size} bytes; "
                f"minimum {MIN_FILE_SIZE} required"
            ),
        }

    # --- Read fixed bytes ---
    read_target = min(
        TEXTUAL_HEADER_BYTES + BINARY_HEADER_BYTES + TRACE_HEADER_BYTES,
        file_size,
    )
    try:
        with open(path, "rb") as fh:
            raw = fh.read(read_target)
    except OSError as exc:
        return {
            "ok": False,
            "binary_fields": None,
            "textual_lines": None,
            "header_read_summary": _make_error_summary(file_size, 0, f"Cannot read file: {exc}"),
            "error": f"Cannot read file: {exc}",
        }

    bytes_read = len(raw)
    textual_raw = raw[:TEXTUAL_HEADER_BYTES]
    binary_raw = raw[TEXTUAL_HEADER_BYTES: TEXTUAL_HEADER_BYTES + BINARY_HEADER_BYTES]
    trace_raw = raw[TEXTUAL_HEADER_BYTES + BINARY_HEADER_BYTES:]

    textual_ok = len(textual_raw) == TEXTUAL_HEADER_BYTES
    binary_ok = len(binary_raw) == BINARY_HEADER_BYTES
    trace_ok = len(trace_raw) >= TRACE_HEADER_BYTES

    # --- Decode textual header ---
    encoding_guess = "unknown"
    textual_lines: list[str] = []
    if textual_ok:
        decoded_text, encoding_guess = _decode_textual_header(textual_raw)
        textual_lines = _split_textual_lines(decoded_text)

    # --- Parse binary header ---
    binary_fields: dict[str, Any] | None = None
    endian_guess = "big"
    if binary_ok:
        binary_fields = _parse_binary_header(binary_raw, endian=">")
        summary_warnings.extend(binary_fields.get("warnings", []))
        summary_errors.extend(binary_fields.get("errors", []))

        # Heuristic: flag if values look suspiciously large
        si = binary_fields.get("sample_interval_us")
        spt = binary_fields.get("samples_per_trace")
        if (si is not None and si > 16000) or (spt is not None and spt > 32767):
            summary_warnings.append(
                "Binary header values may indicate little-endian encoding; "
                "big-endian (SEG-Y standard) was used"
            )
            endian_guess = "big (possibly little)"

    return {
        "ok": textual_ok and binary_ok,
        "binary_fields": binary_fields,
        "textual_lines": textual_lines,
        "header_read_summary": {
            "textual_header_read": textual_ok,
            "binary_header_read": binary_ok,
            "first_trace_header_read": trace_ok,
            "bytes_read": bytes_read,
            "file_size_bytes": file_size,
            "encoding_guess": encoding_guess,
            "endian_guess": endian_guess,
            "warnings": summary_warnings,
            "errors": summary_errors,
        },
        "error": None,
    }
