from __future__ import annotations

from typing import Tuple


def _printable_score(text: str) -> float:
    if not text:
        return -9999.0

    printable = 0
    useful = 0
    bad = 0

    for ch in text:
        code = ord(ch)

        if ch in "\n\r\t" or 32 <= code <= 126:
            printable += 1
        else:
            bad += 1

        if ch.isalnum() or ch in " .,:;-/()[]_+=#":
            useful += 1

        if ch == "\ufffd":
            bad += 5

    upper = text.upper()

    score = 0.0
    score += printable / max(len(text), 1) * 100.0
    score += useful / max(len(text), 1) * 60.0

    # SEG-Y textual headers commonly have C01/C 1 style line prefixes.
    for token in ["C01", "C 1", "C02", "C 2", "CLIENT", "LINE", "REEL", "DATE", "SAMPLE", "TRACE"]:
        if token in upper:
            score += 10.0

    # Penalize common bad-decode symptoms.
    score -= bad * 2.0
    score -= upper.count("@") * 0.15
    score -= upper.count("\x00") * 5.0

    return score


def _format_40_lines(text: str) -> str:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")

    # If the decode already contains line breaks, preserve them.
    if "\n" in cleaned.strip():
        return "\n".join(line.rstrip() for line in cleaned.splitlines()).strip()

    # SEG-Y textual header is 3200 bytes = 40 rows x 80 chars.
    lines = [cleaned[i:i + 80].rstrip() for i in range(0, min(len(cleaned), 3200), 80)]
    return "\n".join(lines).strip()


def decode_segy_text_header(raw: bytes) -> Tuple[str, str, float]:
    """
    Decode the 3200-byte SEG-Y textual header.

    Returns:
      decoded_text, encoding_used, confidence_score
    """
    header = raw[:3200]

    candidates = []

    for encoding in ["ascii", "cp037", "cp500", "latin-1"]:
        try:
            decoded = header.decode(encoding, errors="replace")
        except Exception:
            continue

        formatted = _format_40_lines(decoded)
        candidates.append((formatted, encoding, _printable_score(formatted)))

    if not candidates:
        return "", "unknown", -9999.0

    candidates.sort(key=lambda item: item[2], reverse=True)
    return candidates[0]
