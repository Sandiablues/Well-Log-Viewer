from __future__ import annotations

import base64
import io
import math
import re
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter

MIN_EXTRACTED_CHARS = 1500
DEFAULT_MAX_SELECTED_PAGES = 50
DEFAULT_CONTEXT_PAGES = 1
DEFAULT_CONTEXT_BUDGET_FRACTION = 0.10
MAX_TERM_OCCURRENCES = 8
DEFAULT_OCR_FAST_TIMEOUT_SECONDS = 900
DEFAULT_OCR_ACCURATE_TIMEOUT_SECONDS = 1200
_OCR_HELPER = Path(__file__).with_name("macos_vision_ocr")


class EvidencePreparationError(RuntimeError):
    pass


def _resolve_pdf_object(value: Any) -> Any:
    try:
        return value.get_object()
    except Exception:
        return value


def _count_xobject_images(resources: Any, *, seen: set[int] | None = None) -> int:
    if resources is None:
        return 0
    seen = seen if seen is not None else set()
    resources = _resolve_pdf_object(resources)
    try:
        xobjects = _resolve_pdf_object(resources.get("/XObject"))
    except Exception:
        return 0
    if not xobjects:
        return 0

    count = 0
    try:
        values = xobjects.values()
    except Exception:
        return 0
    for raw in values:
        obj = _resolve_pdf_object(raw)
        marker = id(obj)
        if marker in seen:
            continue
        seen.add(marker)
        try:
            subtype = str(obj.get("/Subtype") or "")
        except Exception:
            subtype = ""
        if subtype == "/Image":
            count += 1
        elif subtype == "/Form":
            try:
                count += _count_xobject_images(obj.get("/Resources"), seen=seen)
            except Exception:
                pass
    return count


_DRAWING_OPERATOR_RE = re.compile(
    rb"(?<![A-Za-z])(?:m|l|c|v|y|h|re|S|s|f|F|f\*|B|B\*|b|b\*|n)(?![A-Za-z])"
)


def _page_content_metrics(page: Any) -> tuple[int, int]:
    try:
        contents = page.get_contents()
        if contents is None:
            return 0, 0
        data = contents.get_data()
        return len(data), len(_DRAWING_OPERATOR_RE.findall(data))
    except Exception:
        return 0, 0


def _graphics_audit(reader: PdfReader, pages: list[str]) -> dict[str, Any]:
    """Structural graphics-risk warning only; no image/geology interpretation."""
    image_pages: list[int] = []
    vector_signal_pages: list[int] = []
    sparse_text_visual_pages: list[int] = []
    visual_signal_pages: list[int] = []
    total_images = 0

    for page_no, page in enumerate(reader.pages, start=1):
        text_chars = len(pages[page_no - 1].strip()) if page_no - 1 < len(pages) else 0
        try:
            image_count = _count_xobject_images(page.get("/Resources"))
        except Exception:
            image_count = 0
        content_bytes, drawing_ops = _page_content_metrics(page)
        total_images += image_count

        image_signal = image_count > 0
        vector_signal = drawing_ops >= 180 and content_bytes >= 12000 and text_chars < 1800
        sparse_visual = ((image_signal and text_chars < 700) or (vector_signal and text_chars < 1000))

        if image_signal:
            image_pages.append(page_no)
        if vector_signal:
            vector_signal_pages.append(page_no)
        if sparse_visual:
            sparse_text_visual_pages.append(page_no)
        if image_signal or vector_signal:
            visual_signal_pages.append(page_no)

    total_pages = max(1, len(reader.pages))
    visual_count = len(set(visual_signal_pages))
    sparse_count = len(set(sparse_text_visual_pages))
    visual_ratio = visual_count / total_pages
    sparse_ratio = sparse_count / total_pages

    if sparse_ratio >= 0.15 or visual_ratio >= 0.35 or sparse_count >= 20:
        risk = "high"
        recommendation = (
            "High graphical-content risk detected. Deterministic text/OCR screening can omit important "
            "visual evidence. Consider disabling deterministic pre-screening and submitting the full "
            "original document to the LLM."
        )
    elif sparse_ratio >= 0.05 or visual_ratio >= 0.12 or visual_count >= 8:
        risk = "moderate"
        recommendation = (
            "Material graphical content detected. Deterministic screening may be used, but visual evidence "
            "on pages excluded by text ranking cannot be assessed locally."
        )
    elif visual_count:
        risk = "low"
        recommendation = (
            "Limited graphical content detected. Selected PDF pages will be preserved intact for LLM visual review."
        )
    else:
        risk = "none"
        recommendation = "No material PDF graphics signal was detected by the structural audit."

    return {
        "risk_level": risk,
        "requires_visual_review": risk in {"moderate", "high"},
        "recommendation": recommendation,
        "total_pages": len(reader.pages),
        "image_page_count": len(set(image_pages)),
        "vector_signal_page_count": len(set(vector_signal_pages)),
        "sparse_text_visual_page_count": sparse_count,
        "visual_signal_page_count": visual_count,
        "total_embedded_images": total_images,
        "image_pages": sorted(set(image_pages)),
        "vector_signal_pages": sorted(set(vector_signal_pages)),
        "sparse_text_visual_pages": sorted(set(sparse_text_visual_pages)),
        "visual_signal_pages": sorted(set(visual_signal_pages)),
        "policy": (
            "Structural warning only. The application does not interpret graphics. When deterministic "
            "screening is used, retained pages are forwarded as original PDF pages so the LLM can inspect graphics."
        ),
    }


def _selected_pdf_bytes(pdf_bytes: bytes, selected_pages: list[int]) -> bytes:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    total_pages = len(reader.pages)
    normalized = [page for page in selected_pages if 1 <= page <= total_pages]
    if normalized == list(range(1, total_pages + 1)):
        return pdf_bytes

    writer = PdfWriter()
    for page_no in normalized:
        writer.add_page(reader.pages[page_no - 1])
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _profile_list(profile: dict[str, Any], key: str) -> list[str]:
    value = profile.get(key)
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _weights(profile: dict[str, Any]) -> dict[str, int]:
    raw = profile.get("weights")
    raw = raw if isinstance(raw, dict) else {}

    def pick(name: str, default: int) -> int:
        try:
            return int(raw.get(name, default))
        except (TypeError, ValueError):
            return default

    return {
        "target": pick("target", 10),
        "context": pick("context", 4),
        "depth": pick("depth", 3),
        "cooccurrence": pick("cooccurrence", 12),
        "negative": pick("negative", -3),
        "structured": pick("structured", 8),
    }


def _term_pattern(term: str) -> re.Pattern[str]:
    """Compile a conservative term matcher.

    The previous implementation used str.count(), which made short tokens such as
    RT/MD/KB match inside unrelated words (for example "report" or "start").
    Short alphanumeric terms now require token boundaries. Longer phrases retain
    phrase/stem behavior for existing managed profiles such as "stratigraph".
    """
    cleaned = str(term or "").strip()
    escaped = re.escape(cleaned)
    if len(cleaned) <= 3 and re.fullmatch(r"[A-Za-z0-9.]+", cleaned):
        return re.compile(r"(?<![A-Za-z0-9])" + escaped + r"(?![A-Za-z0-9])", re.I)
    return re.compile(escaped, re.I)


def _term_occurrences(text: str, term: str) -> int:
    return min(len(_term_pattern(term).findall(text)), MAX_TERM_OCCURRENCES)


def _term_stats(text: str, terms: list[str]) -> tuple[int, int, float]:
    """Return raw occurrence count, distinct-term count, and saturated hit value.

    Incidence matters, but repeated copies of one generic word must not dominate
    pages containing several distinct domain signals. Each term therefore receives
    diminishing returns after its first occurrence while still retaining frequency
    information.
    """
    total_occurrences = 0
    distinct_terms = 0
    saturated_hits = 0.0
    for term in terms:
        count = _term_occurrences(text, term)
        if not count:
            continue
        total_occurrences += count
        distinct_terms += 1
        # 1st = 1.0; occurrences 2-4 = +0.5 each; 5-8 = +0.25 each.
        saturated_hits += (
            1.0
            + 0.5 * min(count - 1, 3)
            + 0.25 * max(min(count, MAX_TERM_OCCURRENCES) - 4, 0)
        )
    return total_occurrences, distinct_terms, saturated_hits


def _normalized_lines(text: str) -> list[str]:
    return [
        re.sub(r"\s+", " ", line).strip()
        for line in text.splitlines()
        if line.strip()
    ]


def _contains_term(text: str, term: str) -> bool:
    return bool(_term_pattern(term).search(text))


def _local_cooccurrence_hits(text: str, required: list[Any]) -> tuple[int, int]:
    """Count relationship incidence on the same extracted row/line.

    A page-wide pair is retained as a weak broad relationship only when the pair
    never appears locally. This prevents a single binary relationship flag from
    treating one explicit row and twenty explicit rows as equivalent.
    """
    lines = _normalized_lines(text)
    local_hits = 0
    broad_only_hits = 0
    for pair in required:
        if not isinstance(pair, list) or len(pair) < 2:
            continue
        terms = [str(term).strip() for term in pair if str(term).strip()]
        if len(terms) < 2:
            continue
        line_hits = sum(
            1 for line in lines
            if all(_contains_term(line, term) for term in terms)
        )
        if line_hits:
            local_hits += min(line_hits, MAX_TERM_OCCURRENCES)
        elif all(_contains_term(text, term) for term in terms):
            broad_only_hits += 1
    return local_hits, broad_only_hits


_DEPTH_NUMBER_RE = re.compile(
    r"(?<!\w)\d{2,5}(?:\.\d+)?\s*(?:m|ft)?"
    r"(?:\s*(?:MD|TVD|TVDSS|RKB|RT|KB|MSL))?(?!\w)",
    re.I,
)


def _structured_target_depth_hits(text: str, target_terms: list[str]) -> int:
    """Count rows/lines that locally associate a target signal with a depth-like number."""
    hits = 0
    for line in _normalized_lines(text):
        if not _DEPTH_NUMBER_RE.search(line):
            continue
        if any(_contains_term(line, term) for term in target_terms):
            hits += 1
    return min(hits, 12)


_EXPLICIT_DEPTH_RE = re.compile(
    r"(?:\b\d{2,5}(?:\.\d+)?\s*(?:m|ft)\b|"
    r"\b\d{2,5}(?:\.\d+)?\s*(?:MD|TVD|TVDSS|RKB|RT|KB|MSL)\b)",
    re.I,
)
_TOP_NAMED_DEPTH_RE = re.compile(
    r"\btop\b.{0,90}\b[A-ZÅØÆ][A-Za-zÅØÆåøæ'/-]{2,}\b.{0,90}\b\d{3,5}(?:\.\d+)?\b"
)


def _strong_evidence_hits(text: str, target_terms: list[str]) -> int:
    """Detect explicit local evidence that negative context must not suppress.

    Strong evidence is intentionally conservative and generic:
    - a target term locally paired with an explicit depth unit/reference;
    - a named Top locally paired with a plausible depth;
    - or a Formation Tops/Lithostratigraphy heading with structured rows.
    """
    hits = 0
    lines = _normalized_lines(text)
    for line in lines:
        has_target = any(_contains_term(line, term) for term in target_terms)
        if has_target and _EXPLICIT_DEPTH_RE.search(line):
            hits += 1
            continue
        if _TOP_NAMED_DEPTH_RE.search(line):
            hits += 1

    if re.search(r"\b(?:formation\s+tops?|lithostrat(?:igraphy|igraphic)?)\b", text, re.I):
        hits += min(2, _structured_target_depth_hits(text, target_terms))
    return min(hits, 12)


def _score_page(text: str, profile: dict[str, Any]) -> tuple[int, list[str]]:
    weights = _weights(profile)
    target_terms = _profile_list(profile, "target_terms")
    context_terms = _profile_list(profile, "context_terms")
    depth_terms = _profile_list(profile, "depth_terms")
    negative_terms = _profile_list(profile, "negative_terms")
    required = profile.get("required_cooccurrence")
    required = required if isinstance(required, list) else []

    target_occ, target_distinct, target_hits = _term_stats(text, target_terms)
    context_occ, context_distinct, context_hits = _term_stats(text, context_terms)
    depth_occ, depth_distinct, depth_hits = _term_stats(text, depth_terms)
    negative_occ, negative_distinct, negative_hits = _term_stats(text, negative_terms)

    # Positive relevance is scored first. Negative/anti-relevance evidence is
    # applied later and asymmetrically so operational context cannot erase an
    # explicit marker/depth pick.
    score = (
        target_hits * weights["target"]
        + context_hits * weights["context"]
        + depth_hits * weights["depth"]
    )
    reasons: list[str] = []
    if target_occ:
        reasons.append(
            f"{target_occ} target occurrence(s) across {target_distinct} distinct term(s)"
        )
    if context_occ:
        reasons.append(
            f"{context_occ} context occurrence(s) across {context_distinct} distinct term(s)"
        )
    if depth_occ:
        reasons.append(
            f"{depth_occ} depth occurrence(s) across {depth_distinct} distinct term(s)"
        )

    local_relationship_hits, broad_relationship_hits = _local_cooccurrence_hits(text, required)
    if local_relationship_hits:
        score += local_relationship_hits * weights["cooccurrence"]
        reasons.append(f"{local_relationship_hits} local relationship occurrence(s)")
    if broad_relationship_hits:
        weak_weight = max(1, abs(weights["cooccurrence"]) // 4)
        score += broad_relationship_hits * weak_weight
        reasons.append(f"{broad_relationship_hits} broad relationship signal(s)")

    structured_hits = _structured_target_depth_hits(text, target_terms)
    if structured_hits:
        # Local target + numeric-depth rows are substantially stronger than a loose
        # page-wide coexistence of geological/technical words and numbers.
        score += structured_hits * weights["structured"] * 2
        reasons.append(f"{structured_hits} structured target/depth row(s)")

    strong_hits = _strong_evidence_hits(text, target_terms)
    if strong_hits:
        reasons.append(f"{strong_hits} protected explicit evidence signal(s)")

    if negative_occ:
        # Inverse evidence is useful for pages dominated by operational/noise
        # material, but it must not linearly cancel explicit target/depth evidence.
        if strong_hits:
            negative_factor = 0.05
        elif structured_hits:
            negative_factor = 0.25
        else:
            negative_factor = 1.0
        negative_penalty = negative_hits * weights["negative"] * negative_factor
        score += negative_penalty
        reasons.append(
            f"{negative_occ} negative occurrence(s) across {negative_distinct} distinct term(s); "
            f"inverse factor {negative_factor:.2f}"
        )

    if strong_hits:
        protected_floor = (
            weights["target"]
            + weights["cooccurrence"]
            + 2 * weights["structured"]
        )
        score = max(score, protected_floor)

    return int(round(score)), reasons



def _ocr_options(profile: dict[str, Any]) -> dict[str, Any]:
    raw = profile.get("ocr_fallback")
    raw = raw if isinstance(raw, dict) else {}
    return {
        "enabled": bool(raw.get("enabled", True)),
        "provider": str(raw.get("provider") or "macos_vision"),
        "ranking_mode": str(raw.get("ranking_mode") or "fast"),
        "selected_mode": str(raw.get("selected_mode") or "accurate"),
    }


def _run_macos_vision_ocr(
    pdf_bytes: bytes,
    *,
    page_numbers: list[int] | None,
    mode: str,
) -> dict[int, str]:
    if sys.platform != "darwin":
        raise EvidencePreparationError(
            "Image-only PDF OCR fallback requires macOS Vision on this runtime."
        )
    if not _OCR_HELPER.exists() or not os.access(_OCR_HELPER, os.X_OK):
        raise EvidencePreparationError(
            f"macOS Vision OCR helper is unavailable: {_OCR_HELPER}"
        )

    timeout = (
        DEFAULT_OCR_ACCURATE_TIMEOUT_SECONDS
        if mode == "accurate"
        else DEFAULT_OCR_FAST_TIMEOUT_SECONDS
    )
    pages_arg = "all" if not page_numbers else ",".join(str(int(p)) for p in page_numbers)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as handle:
        handle.write(pdf_bytes)
        handle.flush()
        try:
            completed = subprocess.run(
                [str(_OCR_HELPER), handle.name, mode, pages_arg],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise EvidencePreparationError(
                f"macOS Vision OCR timed out after {timeout}s ({mode} mode)."
            ) from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or "").strip()[-1200:]
            raise EvidencePreparationError(
                f"macOS Vision OCR failed ({mode} mode): {detail or exc.returncode}"
            ) from exc

    try:
        payload = json.loads(completed.stdout)
    except Exception as exc:
        raise EvidencePreparationError(
            "macOS Vision OCR returned unreadable JSON."
        ) from exc

    if not isinstance(payload, dict):
        raise EvidencePreparationError("macOS Vision OCR returned an invalid payload.")

    results: dict[int, str] = {}
    for key, value in payload.items():
        try:
            page_no = int(key)
        except (TypeError, ValueError):
            continue
        results[page_no] = str(value or "").replace("\x00", " ").strip()
    return results


def _extract_pdf_pages(
    item: dict[str, Any],
    *,
    deterministic_profile: dict[str, Any],
) -> tuple[str, bytes, list[str], str, dict[str, Any]]:
    name = str(item.get("name") or "evidence.pdf")
    encoded = str(item.get("content_base64") or "")
    if not encoded:
        raise EvidencePreparationError(f"{name}: no PDF content supplied.")
    try:
        pdf_bytes = base64.b64decode(encoded)
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception as exc:
        raise EvidencePreparationError(f"{name}: local PDF reader failed: {exc}") from exc

    pages: list[str] = []
    total_chars = 0
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        text = text.replace("\x00", " ").strip()
        pages.append(text)
        total_chars += len(text)

    graphics_audit = _graphics_audit(reader, pages)

    if total_chars >= MIN_EXTRACTED_CHARS:
        return name, pdf_bytes, pages, "native_text", graphics_audit

    options = _ocr_options(deterministic_profile)
    if not options["enabled"]:
        raise EvidencePreparationError(
            f"{name}: only {total_chars:,} extractable text characters were found and OCR fallback is disabled."
        )
    if options["provider"] != "macos_vision":
        raise EvidencePreparationError(
            f"{name}: unsupported OCR fallback provider {options['provider']!r}."
        )

    ocr_map = _run_macos_vision_ocr(
        pdf_bytes,
        page_numbers=None,
        mode=options["ranking_mode"],
    )
    pages = [ocr_map.get(page_no, "") for page_no in range(1, len(reader.pages) + 1)]
    ocr_chars = sum(len(text) for text in pages)
    if ocr_chars < MIN_EXTRACTED_CHARS:
        raise EvidencePreparationError(
            f"{name}: image-only fallback recovered only {ocr_chars:,} OCR characters; "
            "the scan is not adequate for deterministic screening."
        )
    graphics_audit = _graphics_audit(reader, pages)
    return name, pdf_bytes, pages, "vision_ocr_fast", graphics_audit


def _package_pages(
    item: dict[str, Any],
    name: str,
    pdf_bytes: bytes,
    pages: list[str],
    selected_pages: list[int],
    *,
    mode: str,
    graphics_audit: dict[str, Any] | None = None,
    page_reasons: dict[int, list[str]] | None = None,
    direct_pages: list[int] | None = None,
    context_pages: list[int] | None = None,
    graphics_rescue_pages: list[int] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    actual_pages = [page_no for page_no in selected_pages if 1 <= page_no <= len(pages)]
    if not actual_pages:
        raise EvidencePreparationError(f"{name}: no valid PDF pages were selected.")

    blocks: list[str] = []
    for page_no in actual_pages:
        text = pages[page_no - 1]
        if text:
            blocks.append(f"\n===== SOURCE: {name} | PAGE {page_no} =====\n{text}\n")
    selected_text = "".join(blocks)

    selected_pdf = _selected_pdf_bytes(pdf_bytes, actual_pages)
    prepared = {
        "name": name,
        "mime_type": "application/pdf",
        "size": len(selected_pdf),
        "content_base64": base64.b64encode(selected_pdf).decode("ascii"),
        "preprocessed_from_pdf": True,
        "source_pages": actual_pages,
        "deterministic_screening": mode.startswith("deterministic_pdf_"),
        "selected_pdf_pages_preserved": True,
    }
    summary = {
        "name": name,
        "mode": mode,
        "original_size": int(item.get("size") or len(pdf_bytes)),
        "prepared_size": len(selected_pdf),
        "prepared_mime_type": "application/pdf",
        "selected_pdf_pages_preserved": True,
        "total_pages": len(pages),
        "selected_page_count": len(actual_pages),
        "selected_pages": actual_pages,
        "selected_chars": len(selected_text),
        "estimated_tokens": max(1, round(len(selected_text) / 4)) if selected_text else 0,
        "graphics_audit": graphics_audit or {},
    }
    if direct_pages is not None:
        direct_set = set(direct_pages)
        summary["direct_selected_pages"] = [page for page in actual_pages if page in direct_set]
    if context_pages is not None:
        context_set = set(context_pages)
        summary["context_selected_pages"] = [page for page in actual_pages if page in context_set]
    if graphics_rescue_pages is not None:
        rescue_set = set(graphics_rescue_pages)
        summary["graphics_rescue_pages"] = [page for page in actual_pages if page in rescue_set]
        summary["graphics_rescue_page_count"] = len(summary["graphics_rescue_pages"])
    if page_reasons is not None:
        summary["selection_reasons"] = {str(page): page_reasons.get(page, []) for page in actual_pages}
    return prepared, summary

def _context_budget(max_pages: int, context_pages: int, profile: dict[str, Any]) -> int:
    if context_pages <= 0 or max_pages <= 1:
        return 0
    raw = profile.get("context_budget_fraction", DEFAULT_CONTEXT_BUDGET_FRACTION)
    try:
        fraction = min(0.25, max(0.0, float(raw)))
    except (TypeError, ValueError):
        fraction = DEFAULT_CONTEXT_BUDGET_FRACTION
    # context_pages=1 => 10% by default; larger radii may reserve proportionally
    # more, but never more than 25% of the total page budget.
    fraction = min(0.25, fraction * max(1, context_pages))
    return min(max_pages - 1, int(math.floor(max_pages * fraction)))


def _minimum_direct_score(profile: dict[str, Any]) -> int:
    """Minimum deterministic evidence score required for direct page selection.

    The page ceiling is a maximum, not a quota. Pages below this floor are not
    added merely because unused capacity remains.
    """
    raw = profile.get("min_direct_score", profile.get("minimum_direct_score", 20))
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 20



def _graphics_rescue_budget(profile: dict[str, Any], risk_level: str, remaining_capacity: int) -> int:
    config = profile.get("graphics_rescue")
    if not isinstance(config, dict) or not bool(config.get("enabled")) or remaining_capacity <= 0:
        return 0
    allowed = config.get("risk_levels", ["high"])
    if isinstance(allowed, str):
        allowed = [allowed]
    if risk_level not in {str(value).lower() for value in allowed if value is not None}:
        return 0
    by_risk = config.get("max_pages_by_risk", {})
    raw = by_risk.get(risk_level) if isinstance(by_risk, dict) else None
    if raw is None:
        raw = config.get("max_pages", 0)
    try:
        configured = max(0, int(raw or 0))
    except (TypeError, ValueError):
        configured = 0
    return min(remaining_capacity, configured)


def _contiguous_page_runs(page_numbers: list[int]) -> list[list[int]]:
    runs: list[list[int]] = []
    for page_no in sorted(set(page_numbers)):
        if not runs or page_no != runs[-1][-1] + 1:
            runs.append([page_no])
        else:
            runs[-1].append(page_no)
    return runs


def _select_graphics_rescue_pages(
    *,
    graphics_audit: dict[str, Any],
    selected_pages: set[int],
    direct_pages: list[int],
    page_scores: dict[int, int],
    budget: int,
) -> list[int]:
    if budget <= 0:
        return []

    sparse_pages = [
        int(page_no)
        for page_no in (graphics_audit.get("sparse_text_visual_pages") or [])
        if isinstance(page_no, (int, float)) and int(page_no) not in selected_pages
    ]
    if not sparse_pages:
        return []

    image_pages = {int(page_no) for page_no in (graphics_audit.get("image_pages") or [])}
    vector_pages = {int(page_no) for page_no in (graphics_audit.get("vector_signal_pages") or [])}
    direct_set = set(direct_pages)

    def priority(page_no: int) -> tuple[int, int, int, int]:
        structural = (2 if page_no in image_pages else 0) + (2 if page_no in vector_pages else 0)
        text_score = max(0, int(page_scores.get(page_no, 0)))
        if direct_set:
            nearest = min(abs(page_no - seed) for seed in direct_set)
            proximity = 3 if nearest <= 2 else 2 if nearest <= 5 else 1 if nearest <= 10 else 0
        else:
            proximity = 0
        # Prefer stronger visual structure, then any text evidence, then nearby context.
        return (structural, text_score, proximity, -page_no)

    runs = _contiguous_page_runs(sparse_pages)
    ranked_runs = [
        sorted(run, key=priority, reverse=True)
        for run in runs
    ]
    ranked_runs.sort(key=lambda run: priority(run[0]), reverse=True)

    chosen: list[int] = []
    round_index = 0
    while len(chosen) < budget:
        added = False
        for run in ranked_runs:
            if round_index < len(run):
                chosen.append(run[round_index])
                added = True
                if len(chosen) >= budget:
                    break
        if not added:
            break
        round_index += 1
    return chosen

def _prepare_pdf(
    item: dict[str, Any],
    *,
    deterministic_enabled: bool,
    deterministic_profile: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    name, pdf_bytes, pages, extraction_mode, graphics_audit = _extract_pdf_pages(
        item,
        deterministic_profile=deterministic_profile,
    )

    if not deterministic_enabled:
        return _package_pages(
            item, name, pdf_bytes, pages, list(range(1, len(pages) + 1)),
            mode=("full_pdf_ocr" if extraction_mode == "vision_ocr_fast" else "full_pdf_text"),
            graphics_audit=graphics_audit,
        )

    try:
        max_pages = max(1, int(deterministic_profile.get("max_selected_pages") or DEFAULT_MAX_SELECTED_PAGES))
    except (TypeError, ValueError):
        max_pages = DEFAULT_MAX_SELECTED_PAGES
    try:
        context_radius = max(0, int(deterministic_profile.get("context_pages") or DEFAULT_CONTEXT_PAGES))
    except (TypeError, ValueError):
        context_radius = DEFAULT_CONTEXT_PAGES

    # If the entire document fits within the per-document budget, preserve it all.
    # Screening exists to reduce oversized documents, not to throw away affordable
    # evidence from documents already within the configured limit.
    if len(pages) <= max_pages:
        all_pages = list(range(1, len(pages) + 1))
        reasons = {page: ["document fits within per-document page budget"] for page in all_pages}
        return _package_pages(
            item, name, pdf_bytes, pages, all_pages,
            mode=("deterministic_pdf_ocr" if extraction_mode == "vision_ocr_fast" else "deterministic_pdf_text"),
            graphics_audit=graphics_audit,
            page_reasons=reasons,
            direct_pages=all_pages,
            context_pages=[],
        )

    scored: list[tuple[int, int, list[str]]] = []
    page_scores: dict[int, int] = {}
    for index, text in enumerate(pages, start=1):
        score, reasons = _score_page(text, deterministic_profile)
        page_scores[index] = score
        if score > 0:
            scored.append((index, score, reasons))

    ranked = sorted(scored, key=lambda row: (-row[1], row[0]))
    if not ranked:
        raise EvidencePreparationError(
            f"{name}: the active deterministic screening profile selected no pages. "
            "Switch deterministic screening off or revise the profile before using an LLM."
        )

    min_direct_score = _minimum_direct_score(deterministic_profile)
    eligible_ranked = [row for row in ranked if row[1] >= min_direct_score]
    score_floor_bypassed = bool(deterministic_profile.get("bypass_min_direct_score", False))
    if not eligible_ranked:
        top_score = ranked[0][1]
        if score_floor_bypassed:
            # Explicit operator override: keep deterministic scoring/ranking but
            # bypass only the minimum direct-score admission floor for this document.
            eligible_ranked = ranked
        else:
            raise EvidencePreparationError(
                f"{name}: no page cleared the deterministic minimum direct score "
                f"{min_direct_score}; highest page score was {top_score}. "
                "Revise the managed screening profile rather than padding the page budget with weak evidence."
            )

    context_budget = _context_budget(max_pages, context_radius, deterministic_profile)
    direct_quota = max(1, max_pages - context_budget)

    direct_rows = eligible_ranked[:direct_quota]
    direct_pages = [page_no for page_no, _, _ in direct_rows]
    direct_set = set(direct_pages)
    reasons_by_page: dict[int, list[str]] = {
        page_no: [
            f"score {score}",
            *(["minimum direct score bypassed by operator"] if score_floor_bypassed and score < min_direct_score else []),
            *reasons,
        ]
        for page_no, score, reasons in direct_rows
    }

    # Context is chosen only after direct evidence pages are locked. It can fill its
    # reserved budget but can never evict a directly ranked page.
    rank_score = {page_no: score for page_no, score, _ in eligible_ranked}
    context_candidates: dict[int, tuple[float, int, int]] = {}
    for page_no, seed_score, _ in direct_rows:
        for distance in range(1, context_radius + 1):
            for candidate in (page_no - distance, page_no + distance):
                if not 1 <= candidate <= len(pages) or candidate in direct_set:
                    continue
                own_score = rank_score.get(candidate, 0)
                # Prefer context around stronger evidence seeds, then context that
                # carries some signal of its own, then closer pages.
                priority = float(seed_score) + float(own_score) * 0.5 - distance
                current = context_candidates.get(candidate)
                proposed = (priority, seed_score, distance)
                if current is None or proposed > current:
                    context_candidates[candidate] = proposed

    context_ranked = sorted(
        context_candidates.items(),
        key=lambda row: (-row[1][0], row[0]),
    )
    chosen_context = [page for page, _ in context_ranked[:context_budget]]
    for page in chosen_context:
        reasons_by_page.setdefault(page, []).append("reserved adjacent context")

    selected_set = direct_set | set(chosen_context)

    rescue_budget = _graphics_rescue_budget(
        deterministic_profile,
        str(graphics_audit.get("risk_level") or "none").lower(),
        max_pages - len(selected_set),
    )
    graphics_rescue_pages = _select_graphics_rescue_pages(
        graphics_audit=graphics_audit,
        selected_pages=selected_set,
        direct_pages=direct_pages,
        page_scores=page_scores,
        budget=rescue_budget,
    )
    for page in graphics_rescue_pages:
        selected_set.add(page)
        reasons_by_page.setdefault(page, []).append(
            "graphics rescue: sparse-text visual page retained for LLM diagram review"
        )

    # Do not backfill unused capacity with weak text pages. max_selected_pages is a ceiling, not a
    # target. Weak pages below min_direct_score remain excluded even when fewer
    # than max_selected_pages are selected.
    selected_pages = sorted(selected_set)

    # For scanned/image-only PDFs, ranking uses the faster local Vision pass across
    # all pages. Only the final selected pages are then re-read in accurate mode.
    if extraction_mode == "vision_ocr_fast":
        options = _ocr_options(deterministic_profile)
        accurate_map = _run_macos_vision_ocr(
            pdf_bytes,
            page_numbers=selected_pages,
            mode=options["selected_mode"],
        )
        for page_no, text in accurate_map.items():
            if 1 <= page_no <= len(pages) and text:
                pages[page_no - 1] = text
        reasons_by_page.setdefault(selected_pages[0], []).append(
            "image-only PDF ranked with local macOS Vision OCR; selected pages refined in accurate OCR mode"
        )

    return _package_pages(
        item, name, pdf_bytes, pages, selected_pages,
        mode=("deterministic_pdf_ocr" if extraction_mode == "vision_ocr_fast" else "deterministic_pdf_text"),
        graphics_audit=graphics_audit,
        page_reasons=reasons_by_page,
        direct_pages=direct_pages,
        context_pages=chosen_context,
        graphics_rescue_pages=graphics_rescue_pages,
    )


def prepare_evidence(
    evidence_files: list[dict[str, Any]],
    *,
    deterministic_enabled: bool = True,
    deterministic_profile: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    prepared: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    profile = deterministic_profile if isinstance(deterministic_profile, dict) else {}

    # IMPORTANT: max_selected_pages is intentionally applied inside _prepare_pdf(),
    # once for each PDF independently. There is no shared cross-document page pool.
    for item in evidence_files:
        name = str(item.get("name") or "evidence")
        mime = str(item.get("mime_type") or "")
        if mime == "application/pdf" or name.lower().endswith(".pdf"):
            compact, summary = _prepare_pdf(
                item,
                deterministic_enabled=deterministic_enabled,
                deterministic_profile=profile,
            )
            prepared.append(compact)
            summaries.append(summary)
        else:
            prepared.append(dict(item))
            size = int(item.get("size") or 0)
            summaries.append({
                "name": name,
                "mode": "direct_text",
                "original_size": size,
                "selected_chars": size,
                "estimated_tokens": max(1, round(size / 4)) if size else 0,
            })

    return prepared, summaries
