from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import json
import re
import shutil
import subprocess
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[2]
DOCUMENT_EXTS = {".pdf", ".doc", ".docx", ".txt", ".csv"}

PACKAGE_SEARCH_ROOTS = [
    BACKEND_ROOT / "data" / "external_repositories" / "test_document_evidence",
]



ALLOWED_DOCUMENT_EVIDENCE_UPDATE_FIELDS = {
    "identity.package_id",
    "identity.area_or_block",
    "survey.survey_type",
    "spatial.datum",
    "spatial.projection",
    "spatial.utm_zone",
    "spatial.central_meridian",
    "spatial.false_easting",
    "spatial.scale_factor",
    "spatial.crs",
    "acquisition.client_or_operator",
    "acquisition.contractor",
    "acquisition.vessel",
    "acquisition.date_range",
    "processing.processing_year",
    "geometry.sample_interval_ms",
    "geometry.record_length_ms",
    "geometry.bin_size",
}


FIELD_PATTERNS: list[dict[str, Any]] = [
    {"field": "identity.package_id", "label": "Package / survey identifier", "patterns": [r"\b[A-Z]{2}[0-9]{3}[A-Z][0-9]{4}\b"]},
    {
        "field": "identity.area_or_block",
        "label": "Area / block",
        "patterns": [
            r"\b(?:U\.?K\.?C\.?S\.?\s*)?Block\s+[0-9]{1,3}/[0-9]{1,3}[A-Za-z]?\b",
            r"\bUKCS\s+North\s+Sea\s+Block\s+[0-9]{1,3}/[0-9]{1,3}[A-Za-z]?\b",
            r"\bNorth\s+Sea\s+Blk\s+[0-9]{1,3}/[0-9]{1,3}[A-Za-z]?\b",
            r"\bAREA\.?\s+NORTH\s+SEA\s+BLK\s+[0-9]{1,3}/[0-9]{1,3}[A-Za-z]?\b",
        ],
    },
    {
        "field": "survey.survey_type",
        "label": "Survey type",
        "patterns": [
            r"\b3D\s+marine\s+seismic\s+survey\b",
            r"\b3D\s+seismic\s+survey\b",
            r"\b3-D\s+seismic\s+survey\b",
            r"\b3D\s+Seismic\s+Reflection\b",
            r"\b2D\s+seismic\s+survey\b",
            r"\b2-D\s+seismic\s+survey\b",
        ],
    },
    {
        "field": "spatial.crs",
        "label": "Coordinate reference system / CRS",
        "patterns": [
            r"\bWorld\s+Geodetic\s+System\s+1984\s*\(?WGS\s*84\)?\b",
            r"\bWorld\s+Geodetic\s+System\s+1984\s*\(?WGS84\)?\b",
            r"\bWGS\s*84\b",
            r"\bWGS84\b",
            r"\bEuropean\s+Datum\s+1950\s*\(?EDSO\)?\b",
            r"\bEuropean\s+Datum\s+1950\s*\(?ED50\)?\b",
            r"\bED50\b",
            r"\bEDSO\b",
            r"\bUniversal\s+Transverse\s+Mercator\s*\(?UTM\)?\b",
            r"\bUTM\s+Zone\s+[0-9]{1,2}\b",
        ],
    },
    {
        "field": "spatial.projection",
        "label": "Projection",
        "patterns": [
            r"\bUniversal\s+Transverse\s+Mercator\s*\(?UTM\)?\b",
            r"\bTransverse\s+Mercator\b",
            r"\bProjection\s+Type\s+UTM\b",
            r"\bPROJECTION\s+TYPE\s+UTM\b",
        ],
    },
    {
        "field": "spatial.datum",
        "label": "Datum",
        "patterns": [
            r"\bEuropean\s+Datum\s+1950\s*\(?EDSO\)?\b",
            r"\bEuropean\s+Datum\s+1950\s*\(?ED50\)?\b",
            r"\bWorld\s+Geodetic\s+System\s+1984\s*\(?WGS\s*84\)?\b",
            r"\bWorld\s+Geodetic\s+System\s+1984\s*\(?WGS84\)?\b",
            r"\bWGS\s*84\b",
            r"\bWGS84\b",
            r"\bED50\b",
            r"\bEDSO\b",
        ],
    },
    {
        "field": "spatial.utm_zone",
        "label": "UTM zone",
        "patterns": [
            r"\bUTM\s+Zone\s*[:=]?\s*([0-9]{1,2})\b",
            r"\bPROJECTION\s+ZONE\s+([0-9]{1,2})\b",
            r"\bProjection\s+Zone\s+([0-9]{1,2})\b",
            r"\bUniversal\s+Transverse\s+Mercator\s*\(?UTM\)?\s+3\s+deg\s+East\s+500,000\s+0\.9996\s+([0-9]{1,2})\b",
        ],
    },
    {
        "field": "spatial.central_meridian",
        "label": "Central meridian",
        "patterns": [
            r"\bProjection\s+Central\s+Meridian.*?\b(3\s+deg\s+East)\b",
            r"\bCentral\s+Meridian\s+False\s+Easting\s+Scale\s+Factor\s+Zone\s+Datum\s+Universal\s+Transverse\s+Mercator\s*\(?UTM\)?\s+(3\s+deg\s+East)\b",
        ],
    },
    {
        "field": "spatial.false_easting",
        "label": "False easting",
        "patterns": [
            r"\bUniversal\s+Transverse\s+Mercator\s*\(?UTM\)?\s+3\s+deg\s+East\s+(500,000)\s+0\.9996\s+[0-9]{1,2}\b",
        ],
    },
    {
        "field": "spatial.scale_factor",
        "label": "Scale factor",
        "patterns": [
            r"\bUniversal\s+Transverse\s+Mercator\s*\(?UTM\)?\s+3\s+deg\s+East\s+500,000\s+(0\.9996)\s+[0-9]{1,2}\b",
        ],
    },
    {
        "field": "acquisition.client_or_operator",
        "label": "Client / operator",
        "patterns": [r"\bFINA\s+PETROLEUM\s+DEVELOPMENT\s+LTD\.?\b", r"\bFINA\s+PLC\b"],
    },
    {
        "field": "acquisition.contractor",
        "label": "Acquisition contractor",
        "patterns": [r"\bSIMON[-\s]HORIZON\s+LIMITED\b", r"\bSIMON\s+HORIZON\s+LTD\.?\b"],
    },
    {
        "field": "acquisition.vessel",
        "label": "Survey vessel",
        "patterns": [r"\bM\.?V\.?\s+'?\s*SIMON\s+LABRADOR'?\b", r"\bMV\s+'?\s*SIMON\s+LABRADOR'?\b"],
    },
    {
        "field": "acquisition.date_range",
        "label": "Acquisition date range",
        "patterns": [
            r"\b(?:10th|20th)?\s*JANUARY\s+1992\s*[-–]\s*18th\s+MARCH\s+1992\b",
            r"\b20\s+January\s+(?:until|to)\s+18\s+March\s+1992\b",
            r"\bJANUARY\s+1992\s*[-–]\s*MARCH\s+1992\b",
        ],
    },
    {
        "field": "processing.processing_year",
        "label": "Processing year",
        "patterns": [
            r"\bApril\s+1993\b",
            r"\b1992[-–]93\s+3D\s+SURVEY\s+PROCESSING\s+REPORT\b",
            r"\bL992[-–]93\s+3D\s+SURVEY\s+PROCESSING\s+REPORT\b",
        ],
    },
    {
        "field": "geometry.sample_interval_ms",
        "label": "Sample interval",
        "patterns": [
            r"\bSample\s+interval\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:ms|msec|milliseconds)\b",
            r"\bSAMPLE\s+INTERVAL\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:MS|MSEC)\b",
        ],
    },
    {
        "field": "geometry.record_length_ms",
        "label": "Record length",
        "patterns": [
            r"\bRecord\s+length\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:ms|msec|milliseconds|sec|s)\b",
            r"\bRECORD\s+LENGTH\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:MS|MSEC|SEC|S)\b",
        ],
    },
    {
        "field": "geometry.bin_size",
        "label": "Bin size",
        "patterns": [
            r"\bBin\s+size\s*[:=]?\s*([0-9.]+\s*[xX×]\s*[0-9.]+\s*(?:m|metres|meters)?)\b",
            r"\bBIN\s+SIZE\s*[:=]?\s*([0-9.]+\s*[xX×]\s*[0-9.]+\s*(?:M|METRES|METERS)?)\b",
        ],
    },
]


def normalize_space(value: Any) -> str:
    return " ".join(str(value).split())


def evidence_snippet(text: str, start: int, end: int, width: int = 180) -> str:
    a = max(0, start - width)
    b = min(len(text), end + width)
    return normalize_space(text[a:b])


def resolve_package_path(package_id: str) -> Path | None:
    safe_package_id = Path(package_id).name
    for root in PACKAGE_SEARCH_ROOTS:
        candidate = root / safe_package_id
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None


def extract_text(doc: Path) -> tuple[str, str, int | None, str | None]:
    suffix = doc.suffix.lower()

    try:
        if suffix == ".pdf":
            try:
                from pypdf import PdfReader
            except Exception as exc:
                return "", "pypdf_missing", None, str(exc)

            reader = PdfReader(str(doc))
            page_texts = []
            for page in reader.pages:
                page_texts.append(page.extract_text() or "")
            return "\n".join(page_texts), "pypdf", len(reader.pages), None

        if suffix in {".doc", ".docx"} and shutil.which("textutil"):
            result = subprocess.run(
                ["textutil", "-convert", "txt", "-stdout", str(doc)],
                capture_output=True,
                text=True,
                timeout=60,
                errors="replace",
            )
            return result.stdout or "", "textutil", None, None

        if suffix in {".txt", ".csv"}:
            return doc.read_text(errors="replace"), "direct_read", None, None

        return "", "unsupported", None, None

    except Exception as exc:
        return "", "failed", None, str(exc)


def clean_value(field: str, value: str) -> str:
    v = normalize_space(value).strip(" ,.;:\"'")
    upper = v.upper()

    fixes = {
        "World Geodetic System 1984 (WGS84": "World Geodetic System 1984 (WGS84)",
        "World Geodetic System 1984 (WGS 84": "World Geodetic System 1984 (WGS84)",
        "European Datum 1950 (EDSO": "European Datum 1950 (EDSO)",
        "Universal Transverse Mercator (UTM": "Universal Transverse Mercator (UTM)",
        "WGS 84": "WGS84",
    }

    for bad, good in fixes.items():
        if v.lower() == bad.lower():
            return good

    if field in {"spatial.datum", "spatial.crs"}:
        if upper in {"WGS84", "WGS 84"}:
            return "WGS84"
        if upper == "ED50":
            return "ED50"
        if upper == "EDSO":
            return "European Datum 1950 (EDSO)"

    if field == "spatial.projection":
        if "TRANSVERSE MERCATOR" in upper or "UTM" in upper:
            return "Universal Transverse Mercator (UTM)"

    if field == "spatial.utm_zone":
        match = re.search(r"\b(\d{1,2})\b", v)
        if match:
            return match.group(1)

    if field == "spatial.false_easting":
        return v.replace(",", "")

    if field == "acquisition.vessel" and "SIMON" in upper and "LABRADOR" in upper:
        return "M.V. Simon Labrador"

    if field == "acquisition.date_range" and "JANUARY" in upper and "MARCH" in upper and "1992" in upper:
        return "20 January 1992 to 18 March 1992"

    if field == "processing.processing_year":
        if "992" in upper and "93" in upper:
            return "1992–93 processing report"
        if "APRIL" in upper and "1993" in upper:
            return "April 1993 processing report"

    if field == "acquisition.client_or_operator":
        if "FINA PETROLEUM DEVELOPMENT" in upper:
            return "Fina Petroleum Development Ltd"
        if "FINA PLC" in upper:
            return "Fina PLC"

    if field == "acquisition.contractor" and "SIMON" in upper and "HORIZON" in upper:
        return "Simon Horizon Ltd"

    if field == "survey.survey_type":
        if "3D" in upper or "3-D" in upper:
            return "3D seismic survey"
        if "2D" in upper or "2-D" in upper:
            return "2D seismic survey"

    if field == "identity.area_or_block":
        block = re.search(r"([0-9]{1,3}/[0-9]{1,3}[A-Za-z]?)", v)
        if block:
            return f"UKCS Block {block.group(1)}"

    return v


def group_key(field: str, clean: str) -> str:
    c = clean.lower()

    if field in {"spatial.crs", "spatial.datum"}:
        if "ed50" in c or "edso" in c or "european datum 1950" in c:
            return f"{field}|European Datum 1950 / ED50"
        if "wgs84" in c or "wgs 84" in c or "world geodetic system 1984" in c:
            return f"{field}|WGS84"
        if "utm" in c or "transverse mercator" in c:
            return f"{field}|Universal Transverse Mercator (UTM)"

    if field == "spatial.projection" and ("transverse mercator" in c or "utm" in c):
        return f"{field}|Universal Transverse Mercator (UTM)"

    if field == "identity.area_or_block":
        block = re.search(r"([0-9]{1,3}/[0-9]{1,3}[a-z]?)", c)
        if block:
            return f"{field}|UKCS Block {block.group(1)}"

    if field == "acquisition.vessel" and "simon labrador" in c:
        return f"{field}|M.V. Simon Labrador"

    if field == "acquisition.date_range" and "january" in c and "march" in c and "1992" in c:
        return f"{field}|20 January 1992 to 18 March 1992"

    if field == "processing.processing_year" and "1992" in c and "93" in c:
        return f"{field}|1992–93 processing report"

    return f"{field}|{clean}"


def confidence_for(field: str, evidence: str) -> str:
    evidence_l = evidence.lower()
    if field.startswith("spatial."):
        if any(x in evidence_l for x in ["geodetic data", "projection", "datum", "central meridian", "false easting", "scale factor"]):
            return "high"
        return "medium"
    if field.startswith(("identity.", "survey.", "acquisition.")):
        return "high"
    return "medium"


def confidence_from_group(items: list[dict[str, Any]]) -> str:
    highs = sum(1 for item in items if item.get("confidence") == "high")
    docs = {item.get("source_document") for item in items}

    if highs >= 1 and len(docs) >= 2:
        return "high"
    if highs >= 1:
        return "medium_high"
    return "medium"


def action_for_field(field: str) -> str:
    if field.startswith("spatial."):
        return "fill_or_confirm_spatial_metadata"
    if field.startswith("identity."):
        return "fill_or_confirm_identity_metadata"
    if field.startswith("acquisition."):
        return "fill_or_confirm_acquisition_metadata"
    if field.startswith("processing."):
        return "fill_or_confirm_processing_metadata"
    if field.startswith("survey."):
        return "fill_or_confirm_survey_metadata"
    if field.startswith("geometry."):
        return "fill_or_confirm_geometry_metadata"
    return "review_candidate_metadata"


def severity_for_field(field: str) -> str:
    high_fields = {
        "spatial.datum",
        "spatial.projection",
        "spatial.utm_zone",
        "spatial.crs",
        "geometry.sample_interval_ms",
        "geometry.record_length_ms",
        "identity.area_or_block",
    }
    return "high" if field in high_fields else "medium"


def _build_package_document_evidence_base(package_id: str) -> dict[str, Any]:
    package_path = resolve_package_path(package_id)

    if package_path is None:
        return {
            "package": package_id,
            "analysis_type": "document_evidence_analysis_sheet",
            "status": "package_not_found",
            "search_roots": [str(p) for p in PACKAGE_SEARCH_ROOTS],
            "summary": {
                "documents_scanned": 0,
                "raw_observations": 0,
                "grouped_recommendations": 0,
                "pending_user_review": 0,
            },
            "recommended_actions": [],
            "matches": [],
            "discrepancies": [],
            "unresolved": [],
            "note": "No metadata was updated.",
        }

    docs = sorted(p for p in package_path.rglob("*") if p.is_file() and p.suffix.lower() in DOCUMENT_EXTS)
    documents: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []

    for doc in docs:
        rel = str(doc.relative_to(package_path))
        text, method, pages, error = extract_text(doc)
        compact = normalize_space(text)

        documents.append({
            "path": rel,
            "suffix": doc.suffix.lower(),
            "size_bytes": doc.stat().st_size,
            "extract_method": method,
            "page_count": pages,
            "text_chars": len(compact),
            "status": "readable_text" if len(compact) >= 1000 else ("weak_or_partial_text" if compact else "no_text_extracted"),
            "error": error,
        })

        for spec in FIELD_PATTERNS:
            for pattern in spec["patterns"]:
                for match in re.finditer(pattern, text, flags=re.IGNORECASE | re.DOTALL):
                    raw_value = match.group(1) if match.groups() else match.group(0)
                    value = clean_value(spec["field"], raw_value)
                    snippet = evidence_snippet(text, match.start(), match.end())

                    observations.append({
                        "observation_id": f"obs_{len(observations) + 1:04d}",
                        "field": spec["field"],
                        "label": spec["label"],
                        "candidate_value": value,
                        "raw_candidate_value": normalize_space(raw_value),
                        "source_document": rel,
                        "evidence_text": snippet,
                        "confidence": confidence_for(spec["field"], snippet),
                        "status": "candidate_evidence",
                    })

    seen = set()
    deduped: list[dict[str, Any]] = []
    for obs in observations:
        key = (
            obs["field"],
            obs["candidate_value"].lower(),
            obs["source_document"],
            obs["evidence_text"][:180].lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(obs)

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for obs in deduped:
        groups[group_key(obs["field"], obs["candidate_value"])].append(obs)

    recommendations: list[dict[str, Any]] = []
    discrepancies: list[dict[str, Any]] = []

    requested_package_id = package_path.name

    for idx, (_, items) in enumerate(sorted(groups.items()), start=1):
        field = items[0]["field"]
        value_counts = Counter(item["candidate_value"] for item in items)
        recommended_value, _ = value_counts.most_common(1)[0]
        sources = sorted({item["source_document"] for item in items})

        if field == "identity.package_id" and str(recommended_value).upper() != requested_package_id.upper():
            discrepancies.append({
                "field": field,
                "label": items[0].get("label", field),
                "current_context_value": requested_package_id,
                "candidate_value": recommended_value,
                "severity": "medium",
                "confidence": confidence_from_group(items),
                "evidence_count": len(items),
                "source_count": len(sources),
                "sources": sources,
                "status": "candidate_conflicts_with_package_context",
                "recommended_action": "review_document_package_reference_before_using",
                "evidence": items[:10],
            })
            continue

        recommendations.append({
            "recommendation_id": f"rec_{idx:04d}",
            "field": field,
            "label": items[0].get("label", field),
            "recommended_value": recommended_value,
            "action": action_for_field(field),
            "severity": severity_for_field(field),
            "confidence": confidence_from_group(items),
            "evidence_count": len(items),
            "source_count": len(sources),
            "sources": sources,
            "status": "pending_user_review",
            "decision": None,
            "decision_reason": None,
            "evidence": items[:10],
        })

    priority_order = {
        "identity.package_id": 10,
        "identity.area_or_block": 20,
        "survey.survey_type": 30,
        "spatial.datum": 40,
        "spatial.projection": 45,
        "spatial.utm_zone": 50,
        "spatial.central_meridian": 55,
        "spatial.false_easting": 56,
        "spatial.scale_factor": 57,
        "spatial.crs": 60,
        "acquisition.client_or_operator": 70,
        "acquisition.contractor": 80,
        "acquisition.vessel": 90,
        "acquisition.date_range": 100,
        "processing.processing_year": 110,
        "geometry.sample_interval_ms": 120,
        "geometry.record_length_ms": 130,
        "geometry.bin_size": 140,
    }

    recommendations.sort(key=lambda r: (priority_order.get(r["field"], 999), -r["evidence_count"], str(r["recommended_value"])))
    for idx, rec in enumerate(recommendations, start=1):
        rec["recommendation_id"] = f"rec_{idx:04d}"

    # AREA_BLOCK_EVIDENCE_ROLE_CLASSIFICATION
    # Classify area/block observations by evidence role.
    # This is intentionally generic:
    # - no hard-coded package IDs
    # - no hard-coded block IDs
    # - no metadata updates
    # - weaker/nearby/OCR-looking block references remain reviewable as discrepancies
    area_recs = [r for r in recommendations if r.get("field") == "identity.area_or_block"]

    if len(area_recs) > 1:
        def _block_match(value: str):
            return re.search(r"\b([0-9]{1,3})/([0-9]{1,3})([A-Za-z]?)\b", value or "")

        def _block_root(value: str) -> str | None:
            m = _block_match(value)
            if not m:
                return None
            return f"{m.group(1)}/{m.group(2)}"

        def _has_trailing_letter(value: str) -> bool:
            m = _block_match(value)
            return bool(m and m.group(3))

        roots_with_letter = {
            _block_root(str(r.get("recommended_value") or ""))
            for r in area_recs
            if _has_trailing_letter(str(r.get("recommended_value") or ""))
        }
        roots_with_letter.discard(None)

        def _area_role_and_score(rec: dict[str, Any]) -> tuple[str, int, list[str]]:
            value = str(rec.get("recommended_value") or "")
            evidence_text = " ".join(
                str(e.get("evidence_text") or "")
                for e in rec.get("evidence", [])
            ).lower()

            evidence_count = int(rec.get("evidence_count") or 0)
            source_count = int(rec.get("source_count") or 0)

            score = 0
            reasons: list[str] = []

            strong_primary_terms = [
                "survey area",
                "client survey area",
                "area date of survey",
                "date of survey contractor",
                "survey requirements",
                "perform the 3d survey",
                "perform the 2d survey",
                "survey of",
                "prospect area",
                "quality control report on",
                "processing report",
            ]

            weak_reference_terms = [
                "proposed",
                "base map",
                "depth map",
                "migration aperture",
                "adjacent",
                "neighbouring",
                "neighboring",
                "nearby",
                "amoco",
                "mustang",
                "map label",
            ]

            if any(term in evidence_text for term in strong_primary_terms):
                score += 8
                reasons.append("strong_primary_context")

            if source_count >= 2:
                score += 4
                reasons.append("multi_source_support")
            elif source_count == 1:
                score += 1
                reasons.append("single_source_support")

            if evidence_count >= 8:
                score += 4
                reasons.append("high_evidence_count")
            elif evidence_count >= 3:
                score += 2
                reasons.append("moderate_evidence_count")
            elif evidence_count == 1:
                score += 0

            if _has_trailing_letter(value):
                score += 2
                reasons.append("specific_sub_block")

            root = _block_root(value)

            if root and root in roots_with_letter and not _has_trailing_letter(value):
                score -= 4
                reasons.append("partial_block_when_specific_sub_block_exists")

            if any(term in evidence_text for term in weak_reference_terms):
                score -= 5
                reasons.append("weak_or_map_reference_context")

            # OCR or extraction damage often creates implausible variants beside stronger block evidence.
            if re.search(r"\b[0-9]{1,3}/[0-9]{3,}\b", value):
                score -= 3
                reasons.append("possible_ocr_block_variant")

            if score >= 10:
                return "primary_area_candidate", score, reasons

            if "partial_block_when_specific_sub_block_exists" in reasons:
                return "partial_block_reference", score, reasons

            if "weak_or_map_reference_context" in reasons or "possible_ocr_block_variant" in reasons:
                return "related_or_map_reference", score, reasons

            return "secondary_area_candidate_requires_review", score, reasons

        scored_area_recs = []
        for rec in area_recs:
            role, score, reasons = _area_role_and_score(rec)
            rec["evidence_role"] = role
            rec["area_context_score"] = score
            rec["area_context_reasons"] = reasons
            scored_area_recs.append((rec, role, score, reasons))

        primary_candidates = [
            item for item in scored_area_recs
            if item[1] == "primary_area_candidate"
        ]

        if primary_candidates:
            primary_area = max(
                primary_candidates,
                key=lambda item: (
                    item[2],
                    int(item[0].get("source_count") or 0),
                    int(item[0].get("evidence_count") or 0),
                    str(item[0].get("recommended_value") or ""),
                ),
            )[0]

            retained_recommendations = []
            for rec, role, score, reasons in scored_area_recs:
                if rec is primary_area:
                    retained_recommendations.append(rec)
                    continue

                discrepancies.append({
                    "field": rec.get("field"),
                    "label": rec.get("label"),
                    "current_context_value": primary_area.get("recommended_value"),
                    "candidate_value": rec.get("recommended_value"),
                    "severity": "low" if role in {"partial_block_reference", "related_or_map_reference"} else "medium",
                    "confidence": rec.get("confidence"),
                    "evidence_count": rec.get("evidence_count"),
                    "source_count": rec.get("source_count"),
                    "sources": rec.get("sources", []),
                    "status": role,
                    "evidence_role": role,
                    "area_context_score": score,
                    "area_context_reasons": reasons,
                    "recommended_action": "review_as_related_or_secondary_area_reference_before_using_as_metadata",
                    "evidence": rec.get("evidence", []),
                })

            for rec in recommendations:
                if rec.get("field") != "identity.area_or_block":
                    retained_recommendations.append(rec)

            # Restore deterministic ordering after moving secondary area/block candidates.
            priority_order = {
                "identity.package_id": 10,
                "identity.area_or_block": 20,
                "survey.survey_type": 30,
                "spatial.datum": 40,
                "spatial.projection": 45,
                "spatial.utm_zone": 50,
                "spatial.central_meridian": 55,
                "spatial.false_easting": 56,
                "spatial.scale_factor": 57,
                "spatial.crs": 60,
                "acquisition.client_or_operator": 70,
                "acquisition.contractor": 80,
                "acquisition.vessel": 90,
                "acquisition.date_range": 100,
                "processing.processing_year": 110,
                "geometry.sample_interval_ms": 120,
                "geometry.record_length_ms": 130,
                "geometry.bin_size": 140,
            }

            retained_recommendations.sort(
                key=lambda r: (
                    priority_order.get(r.get("field"), 999),
                    -int(r.get("evidence_count") or 0),
                    str(r.get("recommended_value") or ""),
                )
            )

            recommendations = retained_recommendations

            for idx, rec in enumerate(recommendations, start=1):
                rec["recommendation_id"] = f"rec_{idx:04d}"

    # Keep only the strongest package-level area/block recommendation.
    # Other detected blocks may be neighbouring blocks, map labels, OCR damage,
    # or partial block references. They remain visible as discrepancies/review items
    # rather than being promoted as metadata update recommendations.
    area_recs = [r for r in recommendations if r.get("field") == "identity.area_or_block"]

    if len(area_recs) > 1:
        def _area_block_score(rec: dict[str, Any]) -> tuple[int, int, int, str]:
            value = str(rec.get("recommended_value") or "")
            evidence_count = int(rec.get("evidence_count") or 0)
            source_count = int(rec.get("source_count") or 0)

            # Prefer full block IDs with a trailing letter, e.g. 42/27b.
            has_trailing_letter = 1 if re.search(r"\b[0-9]{1,3}/[0-9]{1,3}[A-Za-z]\b", value) else 0

            # Prefer direct package-area evidence by volume of evidence and source diversity.
            return (
                source_count,
                evidence_count,
                has_trailing_letter,
                value,
            )

        primary_area = max(area_recs, key=_area_block_score)

        retained_recommendations = []
        for rec in recommendations:
            if rec.get("field") != "identity.area_or_block":
                retained_recommendations.append(rec)
                continue

            if rec is primary_area:
                retained_recommendations.append(rec)
                continue

            discrepancies.append({
                "field": rec.get("field"),
                "label": rec.get("label"),
                "current_context_value": primary_area.get("recommended_value"),
                "candidate_value": rec.get("recommended_value"),
                "severity": "low",
                "confidence": rec.get("confidence"),
                "evidence_count": rec.get("evidence_count"),
                "source_count": rec.get("source_count"),
                "sources": rec.get("sources", []),
                "status": "candidate_related_or_nearby_block_not_primary",
                "recommended_action": "review_as_related_area_reference_not_metadata_replacement",
                "evidence": rec.get("evidence", []),
            })

        recommendations = retained_recommendations

        for idx, rec in enumerate(recommendations, start=1):
            rec["recommendation_id"] = f"rec_{idx:04d}"

    return {
        "package": package_path.name,
        "analysis_type": "document_evidence_analysis_sheet",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "package_path": str(package_path),
        "documents_scanned": documents,
        "summary": {
            "documents_scanned": len(documents),
            "raw_observations": len(deduped),
            "grouped_recommendations": len(recommendations),
            "high_confidence_recommendations": sum(1 for r in recommendations if r["confidence"] == "high"),
            "medium_high_confidence_recommendations": sum(1 for r in recommendations if r["confidence"] == "medium_high"),
            "pending_user_review": len(recommendations),
            "fields_with_recommendations": dict(Counter(r["field"] for r in recommendations)),
            "discrepancy_count": len(discrepancies),
        },
        "recommended_actions": recommendations,
        "matches": [],
        "discrepancies": discrepancies,
        "unresolved": [],
        "note": "Read-only analysis sheet. No metadata was updated.",
    }



def record_recommendation_decision(
    package_id: str,
    recommendation_id: str,
    decision: str,
    reason: str | None = None,
    decided_by: str = "local_user",
) -> dict[str, Any]:
    """Record a user decision for a document-evidence recommendation.

    This is intentionally non-mutating:
    - does not update normalized metadata
    - does not update canonical metadata
    - only writes decision/audit records beside the staged package
    """
    allowed = {"accept", "decline", "ignore", "defer"}

    normalized_decision = str(decision or "").strip().lower()
    if normalized_decision not in allowed:
        return {
            "ok": False,
            "status": "invalid_decision",
            "allowed_decisions": sorted(allowed),
            "package": package_id,
            "recommendation_id": recommendation_id,
            "note": "No metadata was updated.",
        }

    package_path = resolve_package_path(package_id)
    if package_path is None:
        return {
            "ok": False,
            "status": "package_not_found",
            "package": package_id,
            "recommendation_id": recommendation_id,
            "note": "No metadata was updated.",
        }

    report = build_package_document_evidence(package_id)
    recommendations = report.get("recommended_actions", [])
    discrepancies = report.get("discrepancies", [])

    target = None
    target_type = "recommendation"

    for rec in recommendations:
        if rec.get("recommendation_id") == recommendation_id:
            target = rec
            break

    if target is None:
        for idx, disc in enumerate(discrepancies, start=1):
            disc_id = disc.get("discrepancy_id") or f"disc_{idx:04d}"
            if disc_id == recommendation_id:
                target = dict(disc)
                target["discrepancy_id"] = disc_id
                target_type = "discrepancy"
                break

    if target is None:
        return {
            "ok": False,
            "status": "recommendation_not_found",
            "package": package_id,
            "recommendation_id": recommendation_id,
            "note": "No metadata was updated.",
        }

    now = datetime.now(timezone.utc).isoformat()

    decision_record = {
        "package": package_path.name,
        "target_type": target_type,
        "recommendation_id": recommendation_id,
        "decision": normalized_decision,
        "reason": reason,
        "decided_by": decided_by,
        "decided_at": now,
        "field": target.get("field"),
        "recommended_value": target.get("recommended_value"),
        "candidate_value": target.get("candidate_value"),
        "current_context_value": target.get("current_context_value"),
        "confidence": target.get("confidence"),
        "severity": target.get("severity"),
        "source_count": target.get("source_count"),
        "evidence_count": target.get("evidence_count"),
        "status": "decision_recorded_no_metadata_update",
    }

    decisions_path = package_path / "_document_evidence_decisions.json"
    audit_path = package_path / "_document_evidence_alteration_log.jsonl"

    if decisions_path.exists():
        try:
            decisions_data = json.loads(decisions_path.read_text())
        except Exception:
            decisions_data = {"decisions": []}
    else:
        decisions_data = {"decisions": []}

    existing = decisions_data.setdefault("decisions", [])

    previous_record = None
    retained = []
    for d in existing:
        same_target = (
            d.get("recommendation_id") == recommendation_id
            and d.get("target_type") == target_type
        )
        if same_target:
            previous_record = d
            continue
        retained.append(d)

    retained.append(decision_record)
    decisions_data["decisions"] = retained
    decisions_data["updated_at"] = now

    decisions_path.write_text(json.dumps(decisions_data, indent=2))

    should_append_audit = True
    if previous_record:
        same_decision = previous_record.get("decision") == decision_record.get("decision")
        same_reason = (previous_record.get("reason") or "") == (decision_record.get("reason") or "")
        if same_decision and same_reason:
            should_append_audit = False

    if should_append_audit:
        audit_event = {
            "event_type": "document_evidence_decision_recorded",
            "timestamp": now,
            "package": package_path.name,
            "target_type": target_type,
            "recommendation_id": recommendation_id,
            "decision": normalized_decision,
            "field": decision_record.get("field"),
            "recommended_value": decision_record.get("recommended_value"),
            "candidate_value": decision_record.get("candidate_value"),
            "note": "Decision recorded only. No metadata was updated.",
        }

        with audit_path.open("a") as f:
            f.write(json.dumps(audit_event) + "\n")

    return {
        "ok": True,
        "status": "decision_recorded_no_metadata_update",
        "package": package_path.name,
        "recommendation_id": recommendation_id,
        "decision": normalized_decision,
        "decisions_path": str(decisions_path),
        "audit_path": str(audit_path),
        "audit_appended": should_append_audit,
        "note": "Decision recorded only. No metadata was updated.",
    }



def load_recommendation_decisions(package_id: str) -> dict[str, Any]:
    """Load stored document-evidence decisions for a package."""
    package_path = resolve_package_path(package_id)
    if package_path is None:
        return {}

    decisions_path = package_path / "_document_evidence_decisions.json"
    if not decisions_path.exists():
        return {}

    try:
        data = json.loads(decisions_path.read_text())
    except Exception:
        return {}

    out: dict[str, Any] = {}
    for item in data.get("decisions", []):
        rec_id = item.get("recommendation_id")
        if rec_id:
            out[rec_id] = item

    return out



def build_metadata_update_plan(package_id: str) -> dict[str, Any]:
    """Build a dry-run metadata update plan from accepted document-evidence decisions.

    This function is intentionally read-only:
    - it does not update normalized metadata
    - it does not update canonical metadata
    - it does not trigger rescoring
    - it only lists accepted recommendations that would be eligible for later application
    """
    report = build_package_document_evidence(package_id)
    stored = load_recommendation_decisions(package_id)

    accepted_updates: list[dict[str, Any]] = []
    ignored_or_deferred: list[dict[str, Any]] = []

    for rec in report.get("recommended_actions", []):
        rec_id = rec.get("recommendation_id")
        decision = stored.get(rec_id, {})
        decision_value = decision.get("decision", "pending")

        if decision_value == "accept":
            accepted_updates.append({
                "recommendation_id": rec_id,
                "field": rec.get("field"),
                "label": rec.get("label"),
                "proposed_value": rec.get("recommended_value"),
                "confidence": rec.get("confidence"),
                "severity": rec.get("severity"),
                "evidence_count": rec.get("evidence_count"),
                "source_count": rec.get("source_count"),
                "sources": rec.get("sources", []),
                "decision": decision_value,
                "decision_reason": decision.get("reason"),
                "decided_at": decision.get("decided_at"),
                "status": "accepted_ready_for_manual_apply_preview",
                "note": "Dry-run only. No metadata was updated.",
            })
        elif decision_value in {"decline", "ignore", "defer"}:
            ignored_or_deferred.append({
                "recommendation_id": rec_id,
                "field": rec.get("field"),
                "proposed_value": rec.get("recommended_value"),
                "decision": decision_value,
                "decision_reason": decision.get("reason"),
                "status": "not_in_update_plan",
            })

    return {
        "package": report.get("package", package_id),
        "analysis_type": "metadata_update_plan_dry_run",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "accepted_update_count": len(accepted_updates),
        "accepted_updates": accepted_updates,
        "excluded_decisions": ignored_or_deferred,
        "summary": {
            "stored_decision_count": len(stored),
            "accepted": sum(1 for d in stored.values() if d.get("decision") == "accept"),
            "deferred": sum(1 for d in stored.values() if d.get("decision") == "defer"),
            "declined": sum(1 for d in stored.values() if d.get("decision") == "decline"),
            "ignored": sum(1 for d in stored.values() if d.get("decision") == "ignore"),
        },
        "note": "Dry-run only. No metadata was updated.",
    }



def _get_nested_value(data: dict[str, Any], dotted_path: str) -> Any:
    cur: Any = data
    for part in dotted_path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _load_current_metadata_context(package_id: str) -> dict[str, Any]:
    """Load available current metadata context for preview purposes only.

    This currently looks for common local sidecar names beside the staged package.
    Missing metadata is allowed and simply returns an empty context.
    """
    package_path = resolve_package_path(package_id)
    if package_path is None:
        return {}

    candidates = [
        package_path / ".normalized_metadata.json",
        package_path / "normalized_metadata.json",
        package_path / "metadata_summary.json",
        package_path / "viewer_metadata.json",
    ]

    for p in candidates:
        if p.exists():
            try:
                return json.loads(p.read_text())
            except Exception:
                return {}

    return {}




def _resolve_package_volume_link(package_id: str) -> dict[str, Any]:
    """Resolve whether a document-evidence package is linked to a real volume.

    Current FN923F0001 test packages are staged under test_document_evidence and
    may not correspond to a loaded/converted volume. Metadata application must
    remain blocked until a package_id -> volume_id link exists.
    """
    package_path = resolve_package_path(package_id)
    if package_path is None:
        return {
            "package": package_id,
            "volume_id": None,
            "target_status": "package_not_found",
            "apply_allowed": False,
        }

    # Placeholder for later package registry lookup.
    # For now, only explicit sidecar links are considered valid.
    link_candidates = [
        package_path / "_document_evidence_volume_link.json",
        package_path / "_volume_link.json",
    ]

    for p in link_candidates:
        if p.exists():
            try:
                data = json.loads(p.read_text())
            except Exception:
                continue

            volume_id = data.get("volume_id")
            if volume_id:
                return {
                    "package": package_path.name,
                    "package_path": str(package_path),
                    "volume_id": volume_id,
                    "target_status": "linked_volume_available",
                    "apply_allowed": True,
                    "link_path": str(p),
                }

    return {
        "package": package_path.name,
        "package_path": str(package_path),
        "volume_id": None,
        "target_status": "package_only_no_volume_link",
        "apply_allowed": False,
        "note": "No package-to-volume link exists. Metadata apply must remain blocked.",
    }

def build_metadata_apply_preview(package_id: str) -> dict[str, Any]:
    """Build a controlled dry-run apply preview from accepted recommendations.

    This is intentionally read-only:
    - it does not update normalized metadata
    - it does not update canonical metadata
    - it does not trigger rescoring
    """
    plan = build_metadata_update_plan(package_id)
    target = _resolve_package_volume_link(package_id)
    current_metadata = _load_current_metadata_context(package_id)

    preview_items: list[dict[str, Any]] = []
    blocked_items: list[dict[str, Any]] = []

    for item in plan.get("accepted_updates", []):
        field = item.get("field")
        proposed_value = item.get("proposed_value")
        allowed = field in ALLOWED_DOCUMENT_EVIDENCE_UPDATE_FIELDS and bool(target.get("apply_allowed"))

        preview = {
            "recommendation_id": item.get("recommendation_id"),
            "field": field,
            "current_value": _get_nested_value(current_metadata, field) if field else None,
            "proposed_value": proposed_value,
            "confidence": item.get("confidence"),
            "severity": item.get("severity"),
            "evidence_count": item.get("evidence_count"),
            "source_count": item.get("source_count"),
            "sources": item.get("sources", []),
            "decision_reason": item.get("decision_reason"),
            "decided_at": item.get("decided_at"),
            "allowed_field": field in ALLOWED_DOCUMENT_EVIDENCE_UPDATE_FIELDS,
            "apply_allowed": allowed,
            "target_status": target.get("target_status"),
            "volume_id": target.get("volume_id"),
            "apply_status": "preview_only_allowed" if allowed else (
                "blocked_no_volume_link" if not target.get("apply_allowed") else "blocked_field_not_in_allowlist"
            ),
            "note": "Preview only. No metadata was updated.",
        }

        if allowed:
            preview_items.append(preview)
        else:
            blocked_items.append(preview)

    return {
        "package": plan.get("package", package_id),
        "analysis_type": "metadata_apply_preview",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target": target,
        "preview_update_count": len(preview_items),
        "blocked_update_count": len(blocked_items),
        "preview_updates": preview_items,
        "blocked_updates": blocked_items,
        "summary": {
            "accepted_update_count": plan.get("accepted_update_count", 0),
            "preview_update_count": len(preview_items),
            "blocked_update_count": len(blocked_items),
            "stored_decision_count": plan.get("summary", {}).get("stored_decision_count", 0),
        },
        "note": "Preview only. No metadata was updated.",
    }



def _summarize_audit_log(package_id: str) -> dict[str, Any]:
    package_path = resolve_package_path(package_id)
    if package_path is None:
        return {
            "audit_log_found": False,
            "event_count": 0,
            "latest_events": [],
        }

    audit_path = package_path / "_document_evidence_alteration_log.jsonl"
    if not audit_path.exists():
        return {
            "audit_log_found": False,
            "event_count": 0,
            "latest_events": [],
            "audit_path": str(audit_path),
        }

    events: list[dict[str, Any]] = []
    for line in audit_path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except Exception:
            events.append({
                "event_type": "unparseable_audit_line",
                "raw": line,
            })

    return {
        "audit_log_found": True,
        "audit_path": str(audit_path),
        "event_count": len(events),
        "latest_events": events[-10:],
    }


def build_document_evidence_review_bundle(package_id: str) -> dict[str, Any]:
    """Build one consolidated package-local review bundle.

    This is a standalone review/export object. It does not link to the app
    database, does not write metadata, and does not call save_normalized_metadata.
    """
    evidence = build_package_document_evidence(package_id)
    stored_decisions = load_recommendation_decisions(package_id)
    update_plan = build_metadata_update_plan(package_id)
    apply_preview = build_metadata_apply_preview(package_id)
    audit_summary = _summarize_audit_log(package_id)

    decision_counts: dict[str, int] = {}
    for item in stored_decisions.values():
        decision = item.get("decision", "unknown")
        decision_counts[decision] = decision_counts.get(decision, 0) + 1

    package_path = resolve_package_path(package_id)

    return {
        "package": evidence.get("package", package_id),
        "analysis_type": "document_evidence_review_bundle",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "package_path": str(package_path) if package_path else None,
        "database_link_status": "not_linked",
        "volume_link_status": apply_preview.get("target", {}),
        "summary": {
            "documents_scanned": evidence.get("summary", {}).get("documents_scanned", 0),
            "raw_observations": evidence.get("summary", {}).get("raw_observations", 0),
            "grouped_recommendations": evidence.get("summary", {}).get("grouped_recommendations", 0),
            "discrepancy_count": evidence.get("summary", {}).get("discrepancy_count", 0),
            "stored_decision_count": len(stored_decisions),
            "decision_counts": decision_counts,
            "accepted_update_count": update_plan.get("accepted_update_count", 0),
            "preview_update_count": apply_preview.get("preview_update_count", 0),
            "blocked_update_count": apply_preview.get("blocked_update_count", 0),
            "audit_event_count": audit_summary.get("event_count", 0),
        },
        "documents_scanned": evidence.get("documents_scanned", []),
        "recommended_actions": evidence.get("recommended_actions", []),
        "discrepancies": evidence.get("discrepancies", []),
        "stored_decisions": stored_decisions,
        "decision_summary": evidence.get("decision_summary", {}),
        "metadata_update_plan": update_plan,
        "metadata_apply_preview": apply_preview,
        "audit_summary": audit_summary,
        "note": "Standalone review bundle only. No metadata was updated and no application database link was created.",
    }



def export_document_evidence_review_bundle(package_id: str) -> dict[str, Any]:
    """Write the consolidated review bundle to the package folder.

    Package-local export only:
    - does not update metadata
    - does not link to the app database
    - does not call save_normalized_metadata
    """
    package_path = resolve_package_path(package_id)
    if package_path is None:
        return {
            "ok": False,
            "status": "package_not_found",
            "package": package_id,
            "note": "No metadata was updated and no database link was created.",
        }

    bundle = build_document_evidence_review_bundle(package_id)
    out_path = package_path / "_document_evidence_review_bundle.json"
    out_path.write_text(json.dumps(bundle, indent=2))

    audit_path = package_path / "_document_evidence_alteration_log.jsonl"
    event = {
        "event_type": "document_evidence_review_bundle_exported",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "package": package_path.name,
        "output_path": str(out_path),
        "database_link_status": bundle.get("database_link_status"),
        "target_status": bundle.get("volume_link_status", {}).get("target_status"),
        "note": "Review bundle exported only. No metadata was updated.",
    }

    with audit_path.open("a") as f:
        f.write(json.dumps(event) + "\n")

    return {
        "ok": True,
        "status": "review_bundle_exported",
        "package": package_path.name,
        "output_path": str(out_path),
        "audit_path": str(audit_path),
        "summary": bundle.get("summary", {}),
        "database_link_status": bundle.get("database_link_status"),
        "volume_link_status": bundle.get("volume_link_status"),
        "note": "Review bundle exported only. No metadata was updated and no database link was created.",
    }



# ---------------------------------------------------------------------------
# Metadata evidence validation / unit-normalization layer
# ---------------------------------------------------------------------------

def _evidence_text_blob(rec: dict[str, Any]) -> str:
    return " ".join(
        str(e.get("evidence_text") or "")
        for e in rec.get("evidence", [])
        if isinstance(e, dict)
    )


def _normalize_timing_value_to_ms(value: str, unit: str) -> int | None:
    try:
        number = float(str(value).replace(",", "."))
    except Exception:
        return None

    unit_norm = str(unit or "").strip().lower()

    if unit_norm in {"ms", "msec", "millisecond", "milliseconds"}:
        return int(round(number))

    if unit_norm in {"s", "sec", "secs", "second", "seconds"}:
        return int(round(number * 1000))

    return None


def _collect_timing_candidates(recommendations: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Extract timing candidates with context and units from evidence snippets.

    This prevents values like "4s" from being stored as 4 ms.
    """
    out: dict[str, list[dict[str, Any]]] = {
        "geometry.sample_interval_ms": [],
        "geometry.record_length_ms": [],
    }

    timing_recs = [
        r for r in recommendations
        if str(r.get("field") or "").startswith("geometry.")
    ]

    for rec in timing_recs:
        for e in rec.get("evidence", []):
            if not isinstance(e, dict):
                continue

            txt = str(e.get("evidence_text") or "")
            src = e.get("source_document")

            for m in re.finditer(
                r"\b(sample\s+rate|sampling\s+rate|sample\s+interval|sampling\s+interval)\b"
                r"[^0-9]{0,40}"
                r"([0-9]+(?:[.,][0-9]+)?)\s*(ms|msec|milliseconds?|s|sec|seconds?)\b",
                txt,
                flags=re.IGNORECASE,
            ):
                normalized = _normalize_timing_value_to_ms(m.group(2), m.group(3))
                if normalized is None:
                    continue

                out["geometry.sample_interval_ms"].append({
                    "field": "geometry.sample_interval_ms",
                    "candidate_value": normalized,
                    "raw_candidate_value": f"{m.group(2)} {m.group(3)}",
                    "unit": "ms",
                    "source_document": src,
                    "evidence_text": txt[max(0, m.start() - 140):m.end() + 180],
                    "validation_status": "valid",
                    "validation_reasons": ["matched_sample_interval_context", "unit_normalized_to_ms"],
                })

            for m in re.finditer(
                r"\b(record\s+length|recording\s+length|record\s+time|recording\s+time)\b"
                r"[^0-9]{0,40}"
                r"([0-9]+(?:[.,][0-9]+)?)\s*(ms|msec|milliseconds?|s|sec|seconds?)\b",
                txt,
                flags=re.IGNORECASE,
            ):
                normalized = _normalize_timing_value_to_ms(m.group(2), m.group(3))
                if normalized is None:
                    continue

                status = "valid"
                reasons = ["matched_record_length_context", "unit_normalized_to_ms"]

                if normalized < 500 or normalized > 20000:
                    status = "rejected"
                    reasons.append("record_length_outside_expected_range_500_20000_ms")

                out["geometry.record_length_ms"].append({
                    "field": "geometry.record_length_ms",
                    "candidate_value": normalized,
                    "raw_candidate_value": f"{m.group(2)} {m.group(3)}",
                    "unit": "ms",
                    "source_document": src,
                    "evidence_text": txt[max(0, m.start() - 140):m.end() + 180],
                    "validation_status": status,
                    "validation_reasons": reasons,
                })

    # Sample interval sanity range.
    filtered_sample = []
    for item in out["geometry.sample_interval_ms"]:
        v = item["candidate_value"]
        if 0.25 <= float(v) <= 8:
            filtered_sample.append(item)
        else:
            item["validation_status"] = "rejected"
            item["validation_reasons"].append("sample_interval_outside_expected_range_0_25_8_ms")

    out["geometry.sample_interval_ms"] = filtered_sample
    out["geometry.record_length_ms"] = [
        item for item in out["geometry.record_length_ms"]
        if item.get("validation_status") == "valid"
    ]

    return out


def _mode_value(items: list[dict[str, Any]]) -> tuple[Any, int]:
    counts: dict[Any, int] = {}
    for item in items:
        v = item.get("candidate_value")
        counts[v] = counts.get(v, 0) + 1

    if not counts:
        return None, 0

    value = sorted(counts.items(), key=lambda kv: (-kv[1], str(kv[0])))[0][0]
    return value, counts[value]


def _make_validated_recommendation(
    recommendation_id: str,
    field: str,
    value: Any,
    evidence: list[dict[str, Any]],
    label: str | None = None,
    confidence: str = "medium_high",
) -> dict[str, Any]:
    sources = sorted({
        str(e.get("source_document"))
        for e in evidence
        if e.get("source_document")
    })

    return {
        "recommendation_id": recommendation_id,
        "field": field,
        "label": label or field,
        "recommended_value": value,
        "action": action_for_field(field),
        "severity": severity_for_field(field),
        "confidence": confidence,
        "evidence_count": len(evidence),
        "source_count": len(sources),
        "sources": sources,
        "status": "pending_user_review",
        "decision": None,
        "decision_reason": None,
        "validation_status": "valid",
        "validation_reasons": sorted({
            reason
            for e in evidence
            for reason in e.get("validation_reasons", [])
        }),
        "evidence": evidence[:10],
    }


def _make_validation_discrepancy(
    field: str,
    status: str,
    candidates: list[dict[str, Any]],
    recommended_action: str,
    severity: str = "medium",
) -> dict[str, Any]:
    values = sorted({
        str(c.get("candidate_value"))
        for c in candidates
        if c.get("candidate_value") is not None
    })

    sources = sorted({
        str(c.get("source_document"))
        for c in candidates
        if c.get("source_document")
    })

    # Preserve representative evidence for every distinct candidate value.
    # Do not allow the first N repeated observations to hide minority conflicts.
    by_value: dict[str, list[dict[str, Any]]] = {}
    for c in candidates:
        v = c.get("candidate_value")
        if v is None:
            continue
        by_value.setdefault(str(v), []).append(c)

    representative_evidence: list[dict[str, Any]] = []
    candidate_counts: dict[str, int] = {}

    for value in values:
        items = by_value.get(value, [])
        candidate_counts[value] = len(items)

        # Keep up to 4 examples per distinct value.
        representative_evidence.extend(items[:4])

    return {
        "field": field,
        "label": field,
        "current_context_value": None,
        "candidate_value": values,
        "candidate_counts": candidate_counts,
        "severity": severity,
        "confidence": "requires_review",
        "evidence_count": len(candidates),
        "representative_evidence_count": len(representative_evidence),
        "source_count": len(sources),
        "sources": sources,
        "status": status,
        "validation_status": "requires_review",
        "validation_reasons": sorted({
            reason
            for c in candidates
            for reason in c.get("validation_reasons", [])
        }),
        "recommended_action": recommended_action,
        "evidence": representative_evidence,
    }


def _extract_crs_components(recommendations: list[dict[str, Any]]) -> dict[str, Any]:
    related = [
        r for r in recommendations
        if str(r.get("field") or "").startswith("spatial.")
    ]

    blob = " ".join(_evidence_text_blob(r) for r in related)

    components: dict[str, Any] = {
        "evidence": [],
    }

    evidence_items: list[dict[str, Any]] = []
    for r in related:
        for e in r.get("evidence", []):
            if isinstance(e, dict):
                evidence_items.append(e)

    components["evidence"] = evidence_items[:10]

    if re.search(r"\bED50\b", blob, flags=re.IGNORECASE):
        components["datum"] = "ED50"

    if re.search(r"\bWGS[-\s]?84\b", blob, flags=re.IGNORECASE):
        components.setdefault("alternate_datum_mentions", []).append("WGS-84")

    if re.search(r"\bUTM\b|Universal\s+Transverse\s+Mercator", blob, flags=re.IGNORECASE):
        components["projection"] = "UTM"

    zone_match = re.search(
        r"(?:Zone\s*:?\s*|Central\s+Merid\.?\s*:?.{0,40}?)([0-9]{1,2})\b",
        blob,
        flags=re.IGNORECASE,
    )
    if zone_match:
        try:
            zone = int(zone_match.group(1))
            if 1 <= zone <= 60:
                components["utm_zone"] = zone
        except Exception:
            pass

    # AM923-style OCR text often has:
    # Scale Factor: FalseNorthing: FalseEasting: Central Merid.: Zone:
    # 0.9996 o 500000 3°E 31
    compact = " ".join(blob.split())

    sf_match = re.search(r"\b(0\.9996)\b", compact)
    if sf_match:
        components["scale_factor"] = 0.9996

    fe_match = re.search(r"\b500000\b", compact)
    if fe_match:
        components["false_easting"] = 500000

    cm_match = re.search(r"\b([0-9]{1,2})\s*°\s*E\b", compact, flags=re.IGNORECASE)
    if cm_match:
        components["central_meridian"] = f"{cm_match.group(1)}°E"

    return components


def _apply_timing_validation(report: dict[str, Any]) -> None:
    recommendations = list(report.get("recommended_actions", []))
    discrepancies = list(report.get("discrepancies", []))

    timing_candidates = _collect_timing_candidates(recommendations)

    # Remove existing timing recommendations; rebuild them from validated observations.
    retained = [
        r for r in recommendations
        if r.get("field") not in {
            "geometry.sample_interval_ms",
            "geometry.record_length_ms",
        }
    ]

    sample_candidates = timing_candidates.get("geometry.sample_interval_ms", [])
    if sample_candidates:
        sample_value, _ = _mode_value(sample_candidates)
        retained.append(_make_validated_recommendation(
            recommendation_id="pending",
            field="geometry.sample_interval_ms",
            value=sample_value,
            evidence=[c for c in sample_candidates if c.get("candidate_value") == sample_value],
            label="Sample interval",
            confidence="high" if len(sample_candidates) >= 3 else "medium_high",
        ))

    record_candidates = timing_candidates.get("geometry.record_length_ms", [])
    record_values = sorted({
        c.get("candidate_value")
        for c in record_candidates
        if c.get("candidate_value") is not None
    })

    if len(record_values) == 1:
        record_value = record_values[0]
        retained.append(_make_validated_recommendation(
            recommendation_id="pending",
            field="geometry.record_length_ms",
            value=record_value,
            evidence=record_candidates,
            label="Record length",
            confidence="high" if len(record_candidates) >= 3 else "medium_high",
        ))
    elif len(record_values) > 1:
        discrepancies.append(_make_validation_discrepancy(
            field="geometry.record_length_ms",
            status="conflicting_record_length_candidates",
            candidates=record_candidates,
            recommended_action="review_record_length_conflict_before_using_as_metadata",
            severity="medium",
        ))

    report["recommended_actions"] = retained
    report["discrepancies"] = discrepancies


def _apply_crs_validation(report: dict[str, Any]) -> None:
    recommendations = list(report.get("recommended_actions", []))
    discrepancies = list(report.get("discrepancies", []))

    components = _extract_crs_components(recommendations)

    retained = [
        r for r in recommendations
        if r.get("field") not in {
            "spatial.crs",
            "spatial.projection",
            "spatial.utm_zone",
            "spatial.central_meridian",
            "spatial.false_easting",
            "spatial.scale_factor",
        }
    ]

    evidence = components.get("evidence", [])

    if components.get("projection"):
        retained.append(_make_validated_recommendation(
            recommendation_id="pending",
            field="spatial.projection",
            value=components["projection"],
            evidence=evidence,
            label="Projection",
            confidence="medium_high",
        ))

    if components.get("utm_zone"):
        retained.append(_make_validated_recommendation(
            recommendation_id="pending",
            field="spatial.utm_zone",
            value=components["utm_zone"],
            evidence=evidence,
            label="UTM zone",
            confidence="medium_high",
        ))

    if components.get("central_meridian"):
        retained.append(_make_validated_recommendation(
            recommendation_id="pending",
            field="spatial.central_meridian",
            value=components["central_meridian"],
            evidence=evidence,
            label="Central meridian",
            confidence="medium_high",
        ))

    if components.get("false_easting"):
        retained.append(_make_validated_recommendation(
            recommendation_id="pending",
            field="spatial.false_easting",
            value=components["false_easting"],
            evidence=evidence,
            label="False easting",
            confidence="medium_high",
        ))

    if components.get("scale_factor"):
        retained.append(_make_validated_recommendation(
            recommendation_id="pending",
            field="spatial.scale_factor",
            value=components["scale_factor"],
            evidence=evidence,
            label="Scale factor",
            confidence="medium_high",
        ))

    if components.get("datum") and components.get("projection") and components.get("utm_zone"):
        crs_value = f"{components['datum']} / {components['projection']} Zone {components['utm_zone']}"
        retained.append(_make_validated_recommendation(
            recommendation_id="pending",
            field="spatial.crs",
            value=crs_value,
            evidence=evidence,
            label="Coordinate reference system",
            confidence="medium_high",
        ))
    else:
        for r in recommendations:
            if r.get("field") == "spatial.crs":
                discrepancies.append({
                    "field": "spatial.crs",
                    "label": "Coordinate reference system",
                    "current_context_value": None,
                    "candidate_value": r.get("recommended_value"),
                    "severity": "medium",
                    "confidence": "requires_review",
                    "evidence_count": r.get("evidence_count"),
                    "source_count": r.get("source_count"),
                    "sources": r.get("sources", []),
                    "status": "incomplete_crs_candidate",
                    "validation_status": "requires_review",
                    "validation_reasons": [
                        "datum_alone_is_not_complete_crs",
                        "requires_datum_projection_and_zone_or_epsg",
                    ],
                    "recommended_action": "do_not_use_as_full_crs_without_projection_zone_or_epsg",
                    "evidence": r.get("evidence", []),
                })

    report["recommended_actions"] = retained
    report["discrepancies"] = discrepancies


def _refresh_report_summary_after_validation(report: dict[str, Any]) -> None:
    recommendations = report.get("recommended_actions", [])
    discrepancies = report.get("discrepancies", [])

    priority_order = {
        "identity.package_id": 10,
        "identity.area_or_block": 20,
        "survey.survey_type": 30,
        "spatial.datum": 40,
        "spatial.projection": 45,
        "spatial.utm_zone": 50,
        "spatial.central_meridian": 55,
        "spatial.false_easting": 56,
        "spatial.scale_factor": 57,
        "spatial.crs": 60,
        "acquisition.client_or_operator": 70,
        "acquisition.contractor": 80,
        "acquisition.vessel": 90,
        "acquisition.date_range": 100,
        "processing.processing_year": 110,
        "geometry.sample_interval_ms": 120,
        "geometry.record_length_ms": 130,
        "geometry.bin_size": 140,
    }

    recommendations.sort(
        key=lambda r: (
            priority_order.get(r.get("field"), 999),
            -int(r.get("evidence_count") or 0),
            str(r.get("recommended_value") or ""),
        )
    )

    for idx, rec in enumerate(recommendations, start=1):
        rec["recommendation_id"] = f"rec_{idx:04d}"

    field_counts: dict[str, int] = {}
    for r in recommendations:
        field = r.get("field")
        if field:
            field_counts[field] = field_counts.get(field, 0) + 1

    high = sum(1 for r in recommendations if r.get("confidence") == "high")
    med_high = sum(1 for r in recommendations if r.get("confidence") == "medium_high")

    summary = report.setdefault("summary", {})
    summary["grouped_recommendations"] = len(recommendations)
    summary["high_confidence_recommendations"] = high
    summary["medium_high_confidence_recommendations"] = med_high
    summary["pending_user_review"] = len(recommendations)
    summary["fields_with_recommendations"] = field_counts
    summary["discrepancy_count"] = len(discrepancies)
    summary["validation_layer_applied"] = True





# VALIDATION_LAYER_V2_FIXED_FULL_TEXT_SCAN




# DOCUMENT_TEXT_CACHE_V1

def _safe_cache_name(relative_path: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", relative_path)
    safe = safe.strip("._")
    if not safe:
        safe = "document"
    return safe + ".txt"


def _document_cache_paths(package_path: Path) -> tuple[Path, Path]:
    cache_dir = package_path / "_document_text_cache"
    manifest_path = package_path / "_document_text_cache_manifest.json"
    return cache_dir, manifest_path


def _load_text_cache_manifest(package_path: Path) -> dict[str, Any]:
    _, manifest_path = _document_cache_paths(package_path)
    if not manifest_path.exists():
        return {
            "version": 1,
            "documents": {},
        }

    try:
        data = json.loads(manifest_path.read_text())
        if not isinstance(data, dict):
            return {"version": 1, "documents": {}}
        data.setdefault("version", 1)
        data.setdefault("documents", {})
        return data
    except Exception:
        return {
            "version": 1,
            "documents": {},
            "manifest_error": "failed_to_parse_existing_manifest",
        }


def _write_text_cache_manifest(package_path: Path, manifest: dict[str, Any]) -> None:
    _, manifest_path = _document_cache_paths(package_path)
    manifest["version"] = 1
    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
    manifest_path.write_text(json.dumps(manifest, indent=2))


def _doc_file_signature(doc: Path) -> dict[str, Any]:
    st = doc.stat()
    return {
        "size_bytes": st.st_size,
        "mtime_ns": st.st_mtime_ns,
    }


def _extract_document_text_uncached(doc: Path) -> dict[str, Any]:
    suffix = doc.suffix.lower()
    text = ""
    method = "unsupported"
    pages = None
    error = None

    try:
        if suffix == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(str(doc))
            pages = len(reader.pages)
            parts = []
            for page in reader.pages:
                try:
                    parts.append(page.extract_text() or "")
                except Exception:
                    parts.append("")
            text = "\n".join(parts)
            method = "pypdf"

        elif suffix in {".doc", ".docx"}:
            import shutil as _shutil
            import subprocess as _subprocess

            if _shutil.which("textutil"):
                r = _subprocess.run(
                    ["textutil", "-convert", "txt", "-stdout", str(doc)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    errors="replace",
                )
                text = r.stdout or ""
                method = "textutil"
                if r.returncode != 0:
                    error = r.stderr or f"textutil exited {r.returncode}"
            else:
                method = "textutil_missing"

        elif suffix in {".txt", ".csv"}:
            text = doc.read_text(errors="replace")
            method = "direct_read"

    except Exception as e:
        error = str(e)

    compact_len = len(" ".join(text.split()))

    if compact_len >= 1000:
        status = "readable_text"
    elif compact_len > 0:
        status = "weak_or_partial_text"
    else:
        status = "no_text_extracted"

    return {
        "text": text,
        "method": method,
        "page_count": pages,
        "text_chars": compact_len,
        "status": status,
        "error": error,
    }


def _extract_package_texts_cached(package_id: str) -> list[dict[str, Any]]:
    """Extract package document text using a package-local cache.

    Cache invalidation uses file size + modified time. This is intentionally
    package-local and does not touch the application database.
    """
    package_path = resolve_package_path(package_id)
    if package_path is None:
        return []

    docs = [
        p for p in sorted(package_path.rglob("*"))
        if p.is_file()
        and p.suffix.lower() in {".pdf", ".doc", ".docx", ".txt", ".csv"}
        and not p.name.startswith("_document_evidence_")
        and "_document_text_cache" not in p.parts
    ]

    cache_dir, _ = _document_cache_paths(package_path)
    cache_dir.mkdir(parents=True, exist_ok=True)

    manifest = _load_text_cache_manifest(package_path)
    manifest_docs = manifest.setdefault("documents", {})

    out: list[dict[str, Any]] = []
    cache_hits = 0
    cache_misses = 0

    for doc in docs:
        rel = str(doc.relative_to(package_path))
        sig = _doc_file_signature(doc)
        entry = manifest_docs.get(rel, {})
        cache_file_name = entry.get("cache_file") or _safe_cache_name(rel)
        cache_path = cache_dir / cache_file_name

        cached_ok = (
            cache_path.exists()
            and entry.get("size_bytes") == sig["size_bytes"]
            and entry.get("mtime_ns") == sig["mtime_ns"]
        )

        if cached_ok:
            text = cache_path.read_text(errors="replace")
            cache_hits += 1
            item = {
                "source_document": rel,
                "suffix": doc.suffix.lower(),
                "method": entry.get("method", "cache"),
                "page_count": entry.get("page_count"),
                "text": text,
                "text_chars": len(" ".join(text.split())),
                "status": entry.get("status", "cached_text"),
                "error": entry.get("error"),
                "cache_status": "hit",
                "cache_path": str(cache_path),
            }
        else:
            extracted = _extract_document_text_uncached(doc)
            cache_misses += 1
            cache_file_name = _safe_cache_name(rel)
            cache_path = cache_dir / cache_file_name
            cache_path.write_text(extracted.get("text") or "")

            manifest_docs[rel] = {
                "source_document": rel,
                "cache_file": cache_file_name,
                "size_bytes": sig["size_bytes"],
                "mtime_ns": sig["mtime_ns"],
                "method": extracted.get("method"),
                "page_count": extracted.get("page_count"),
                "text_chars": extracted.get("text_chars"),
                "status": extracted.get("status"),
                "error": extracted.get("error"),
                "cached_at": datetime.now(timezone.utc).isoformat(),
            }

            item = {
                "source_document": rel,
                "suffix": doc.suffix.lower(),
                "method": extracted.get("method"),
                "page_count": extracted.get("page_count"),
                "text": extracted.get("text") or "",
                "text_chars": extracted.get("text_chars"),
                "status": extracted.get("status"),
                "error": extracted.get("error"),
                "cache_status": "miss_written",
                "cache_path": str(cache_path),
            }

        out.append(item)

    manifest["cache_summary"] = {
        "package": package_path.name,
        "document_count": len(docs),
        "cache_hits": cache_hits,
        "cache_misses": cache_misses,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_text_cache_manifest(package_path, manifest)

    return out

def _v2_extract_package_texts(package_id: str) -> list[dict[str, Any]]:
    return _extract_package_texts_cached(package_id)


def _v2_snippet(text: str, start: int, end: int, width: int = 200) -> str:
    a = max(0, start - width)
    b = min(len(text), end + width)
    return " ".join(text[a:b].split())


def _v2_collect_timing(package_id: str) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {
        "geometry.sample_interval_ms": [],
        "geometry.record_length_ms": [],
    }

    for doc in _v2_extract_package_texts(package_id):
        text = doc.get("text") or ""
        src = doc.get("source_document")

        if not text.strip():
            continue

        for m in re.finditer(
            r"\b(sample\s+rate|sampling\s+rate|sample\s+interval|sampling\s+interval)\b"
            r"[^0-9]{0,80}"
            r"([0-9]+(?:[.,][0-9]+)?)\s*(ms|msec|milliseconds?|s|sec|seconds?)\b",
            text,
            flags=re.IGNORECASE,
        ):
            normalized = _normalize_timing_value_to_ms(m.group(2), m.group(3))
            if normalized is None:
                continue

            sample_context = _v2_snippet(text, m.start(), m.end(), width=220).lower()

            conditional_or_instrument_note = any(
                phrase in sample_context
                for phrase in [
                    "less than",
                    "when acquisition sample rate",
                    "digital filtering used when",
                    "anti alias filters for",
                    "filters for 2 msec",
                    "filters for 2ms",
                    "filters for 4 msec",
                    "filters for 4ms",
                ]
            )

            if 0.25 <= float(normalized) <= 8 and not conditional_or_instrument_note:
                out["geometry.sample_interval_ms"].append({
                    "field": "geometry.sample_interval_ms",
                    "candidate_value": normalized,
                    "raw_candidate_value": f"{m.group(2)} {m.group(3)}",
                    "unit": "ms",
                    "source_document": src,
                    "evidence_text": _v2_snippet(text, m.start(), m.end()),
                    "validation_status": "valid",
                    "validation_reasons": [
                        "v2_full_text_scan",
                        "matched_sample_interval_context",
                        "unit_normalized_to_ms",
                    ],
                })

        for m in re.finditer(
            r"\b(record\s+length|recording\s+length|record\s+time|recording\s+time)\b"
            r"[^0-9]{0,100}"
            r"([0-9]+(?:[.,][0-9]+)?)\s*(ms|msec|milliseconds?|s|sec|seconds?)\b",
            text,
            flags=re.IGNORECASE,
        ):
            normalized = _normalize_timing_value_to_ms(m.group(2), m.group(3))
            if normalized is None:
                continue

            if 500 <= normalized <= 20000:
                out["geometry.record_length_ms"].append({
                    "field": "geometry.record_length_ms",
                    "candidate_value": normalized,
                    "raw_candidate_value": f"{m.group(2)} {m.group(3)}",
                    "unit": "ms",
                    "source_document": src,
                    "evidence_text": _v2_snippet(text, m.start(), m.end()),
                    "validation_status": "valid",
                    "validation_reasons": [
                        "v2_full_text_scan",
                        "matched_record_length_context",
                        "unit_normalized_to_ms",
                    ],
                })

    return out


def _v2_collect_crs(package_id: str) -> dict[str, Any]:
    docs = _v2_extract_package_texts(package_id)
    snippets: list[str] = []
    evidence: list[dict[str, Any]] = []

    for doc in docs:
        text = doc.get("text") or ""
        src = doc.get("source_document")

        if not text.strip():
            continue

        for m in re.finditer(
            r".{0,180}\b(ED50|European\s+Datum\s+1950|EDSO|WGS[-\s]?84|UTM|"
            r"Universal\s+Transverse\s+Mercator|Projection|Datum|Zone|"
            r"Central\s+Merid\.?|False\s*Easting|Scale\s+Factor)\b.{0,320}",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            snip = _v2_snippet(text, m.start(), m.end(), width=20)
            snippets.append(snip)
            evidence.append({
                "source_document": src,
                "candidate_value": None,
                "raw_candidate_value": m.group(1),
                "evidence_text": snip,
                "validation_status": "valid",
                "validation_reasons": ["v2_full_text_scan", "crs_component_context"],
            })

    compact = " ".join(" ".join(snippets).split())
    components: dict[str, Any] = {"evidence": evidence[:12]}

    if re.search(r"\bED50\b|European\s+Datum\s+1950|EDSO", compact, flags=re.IGNORECASE):
        components["datum"] = "ED50"

    if re.search(r"\bUTM\b|Universal\s+Transverse\s+Mercator", compact, flags=re.IGNORECASE):
        components["projection"] = "UTM"

    structured = re.search(
        r"Projection\s+Central\s+Meridian\s+False\s+Easting\s+Scale\s+Factor\s+Zone\s+Datum\s+"
        r".{0,160}?UTM\)?\s+([0-9]{1,2})\s*(?:deg|°)\s*East\s+500,?000\s+0\.9996\s+([0-9]{1,2})\s+",
        compact,
        flags=re.IGNORECASE,
    )

    structured_alt = re.search(
        r"Scale\s+Factor\s*:?.{0,120}False\s*Easting\s*:?.{0,120}"
        r"Central\s+Merid\.?\s*:?.{0,120}Zone\s*:?.{0,120}"
        r"(0\.9996)\s+\S+\s+(500000)\s+([0-9]{1,2})\s*°\s*E\s+([0-9]{1,2})\b",
        compact,
        flags=re.IGNORECASE,
    )

    processing_header_zone = re.search(
        r"PROJECTION\s+TYPE\s+UTM\s+H19\s+PRO\.?\]?ECTION\s+ZONE\s+([0-9]{1,2})\]",
        compact,
        flags=re.IGNORECASE,
    )

    if structured:
        components["scale_factor"] = 0.9996
        components["false_easting"] = 500000
        components["central_meridian"] = f"{structured.group(1)}°E"
        zone = int(structured.group(2))
        if 1 <= zone <= 60:
            components["utm_zone"] = zone
    elif structured_alt:
        components["scale_factor"] = 0.9996
        components["false_easting"] = 500000
        components["central_meridian"] = f"{structured_alt.group(3)}°E"
        zone = int(structured_alt.group(4))
        if 1 <= zone <= 60:
            components["utm_zone"] = zone
    elif processing_header_zone:
        # OCR commonly renders "31" as "3]" in SEG-Y textual header scans.
        raw_zone = processing_header_zone.group(1)
        if raw_zone == "3":
            zone = 31
        else:
            zone = int(raw_zone)
        if 1 <= zone <= 60:
            components["utm_zone"] = zone
    else:
        if re.search(r"\b0\.9996\b", compact):
            components["scale_factor"] = 0.9996

        if re.search(r"\b500000\b", compact):
            components["false_easting"] = 500000

        cm = re.search(r"\b([0-9]{1,2})\s*°\s*E\b", compact, flags=re.IGNORECASE)
        if cm:
            components["central_meridian"] = f"{cm.group(1)}°E"

        zone = re.search(r"\bZone\s*:?\s*([0-9]{1,2})\b", compact, flags=re.IGNORECASE)
        if zone:
            z = int(zone.group(1))
            central_meridian_is_3e = bool(re.search(r"3\s*(?:deg|°)\s*East|03\s+OO\s+OO", compact, flags=re.IGNORECASE))
            if z == 3 and central_meridian_is_3e:
                components.setdefault("rejected_zone_candidates", []).append({
                    "candidate": 3,
                    "reason": "zone_3_rejected_as_central_meridian_3e_confusion",
                })
            elif 1 <= z <= 60:
                components["utm_zone"] = z

    return components


def _v2_apply_timing_validation(report: dict[str, Any]) -> None:
    package_id = str(report.get("package") or "")
    if not package_id:
        return

    recommendations = list(report.get("recommended_actions", []))
    discrepancies = list(report.get("discrepancies", []))

    timing = _v2_collect_timing(package_id)

    retained = [
        r for r in recommendations
        if r.get("field") not in {
            "geometry.sample_interval_ms",
            "geometry.record_length_ms",
        }
    ]

    sample_candidates = timing.get("geometry.sample_interval_ms", [])
    sample_value, _ = _mode_value(sample_candidates)
    if sample_value is not None:
        retained.append(_make_validated_recommendation(
            recommendation_id="pending",
            field="geometry.sample_interval_ms",
            value=sample_value,
            evidence=[c for c in sample_candidates if c.get("candidate_value") == sample_value],
            label="Sample interval",
            confidence="high" if len(sample_candidates) >= 3 else "medium_high",
        ))

    record_candidates = timing.get("geometry.record_length_ms", [])
    record_values = sorted({
        c.get("candidate_value")
        for c in record_candidates
        if c.get("candidate_value") is not None
    })

    if len(record_values) == 1:
        retained.append(_make_validated_recommendation(
            recommendation_id="pending",
            field="geometry.record_length_ms",
            value=record_values[0],
            evidence=record_candidates,
            label="Record length",
            confidence="high" if len(record_candidates) >= 3 else "medium_high",
        ))
    elif len(record_values) > 1:
        discrepancies.append(_make_validation_discrepancy(
            field="geometry.record_length_ms",
            status="conflicting_record_length_candidates",
            candidates=record_candidates,
            recommended_action="review_record_length_conflict_before_using_as_metadata",
            severity="medium",
        ))

    report["recommended_actions"] = retained
    report["discrepancies"] = discrepancies


def _v2_apply_crs_validation(report: dict[str, Any]) -> None:
    package_id = str(report.get("package") or "")
    if not package_id:
        return

    recommendations = list(report.get("recommended_actions", []))
    discrepancies = list(report.get("discrepancies", []))
    components = _v2_collect_crs(package_id)
    evidence = components.get("evidence", [])

    retained = [
        r for r in recommendations
        if r.get("field") not in {
            "spatial.crs",
            "spatial.projection",
            "spatial.utm_zone",
            "spatial.central_meridian",
            "spatial.false_easting",
            "spatial.scale_factor",
        }
    ]

    if components.get("projection"):
        retained.append(_make_validated_recommendation("pending", "spatial.projection", components["projection"], evidence, "Projection", "medium_high"))

    if components.get("utm_zone"):
        retained.append(_make_validated_recommendation("pending", "spatial.utm_zone", components["utm_zone"], evidence, "UTM zone", "medium_high"))

    if components.get("central_meridian"):
        retained.append(_make_validated_recommendation("pending", "spatial.central_meridian", components["central_meridian"], evidence, "Central meridian", "medium_high"))

    if components.get("false_easting"):
        retained.append(_make_validated_recommendation("pending", "spatial.false_easting", components["false_easting"], evidence, "False easting", "medium_high"))

    if components.get("scale_factor"):
        retained.append(_make_validated_recommendation("pending", "spatial.scale_factor", components["scale_factor"], evidence, "Scale factor", "medium_high"))

    if components.get("datum") and components.get("projection") and components.get("utm_zone"):
        crs_value = f"{components['datum']} / {components['projection']} Zone {components['utm_zone']}"
        retained.append(_make_validated_recommendation("pending", "spatial.crs", crs_value, evidence, "Coordinate reference system", "medium_high"))

    for r in recommendations:
        if r.get("field") == "spatial.crs" and r.get("recommended_value") in {"ED50", "WGS84", "WGS-84"}:
            discrepancies.append({
                "field": "spatial.crs",
                "label": "Coordinate reference system",
                "current_context_value": None,
                "candidate_value": r.get("recommended_value"),
                "severity": "medium",
                "confidence": "requires_review",
                "evidence_count": r.get("evidence_count"),
                "source_count": r.get("source_count"),
                "sources": r.get("sources", []),
                "status": "incomplete_crs_candidate",
                "validation_status": "requires_review",
                "validation_reasons": [
                    "datum_alone_is_not_complete_crs",
                    "requires_datum_projection_and_zone_or_epsg",
                ],
                "recommended_action": "do_not_use_as_full_crs_without_projection_zone_or_epsg",
                "evidence": r.get("evidence", []),
            })

    report["recommended_actions"] = retained
    report["discrepancies"] = discrepancies


def _apply_metadata_evidence_validation_layer_v2(report: dict[str, Any]) -> dict[str, Any]:
    _v2_apply_timing_validation(report)
    _v2_apply_crs_validation(report)
    _refresh_report_summary_after_validation(report)
    report["validation_layer_applied"] = True
    report["validation_layer_version"] = "v2_full_text_scan"
    return report

def _apply_metadata_evidence_validation_layer(report: dict[str, Any]) -> dict[str, Any]:
    """Apply field-specific validation and unit-normalization.

    This layer prevents raw regex hits from being promoted unless they pass
    field/context/unit sanity checks.
    """
    _apply_timing_validation(report)
    _apply_crs_validation(report)
    _refresh_report_summary_after_validation(report)
    report["validation_layer_applied"] = True
    return report





# VALIDATED_EVIDENCE_RESULT_CACHE_V1

VALIDATED_EVIDENCE_CACHE_VERSION = "v1_validation_v2_full_text_scan"


def _validated_evidence_cache_path(package_path: Path) -> Path:
    return package_path / "_document_evidence_validated_cache.json"


def _file_mtime_ns_or_none(path: Path) -> int | None:
    try:
        return path.stat().st_mtime_ns if path.exists() else None
    except Exception:
        return None


def _validated_evidence_cache_signature(package_id: str) -> dict[str, Any]:
    package_path = resolve_package_path(package_id)
    if package_path is None:
        return {
            "package": package_id,
            "package_found": False,
            "cache_version": VALIDATED_EVIDENCE_CACHE_VERSION,
        }

    _, text_manifest_path = _document_cache_paths(package_path)
    decisions_path = package_path / "_document_evidence_decisions.json"

    doc_sigs = []
    docs = [
        p for p in sorted(package_path.rglob("*"))
        if p.is_file()
        and p.suffix.lower() in {".pdf", ".doc", ".docx", ".txt", ".csv"}
        and not p.name.startswith("_document_evidence_")
        and "_document_text_cache" not in p.parts
    ]

    for doc in docs:
        try:
            st = doc.stat()
            doc_sigs.append({
                "source_document": str(doc.relative_to(package_path)),
                "size_bytes": st.st_size,
                "mtime_ns": st.st_mtime_ns,
            })
        except Exception:
            continue

    return {
        "package": package_path.name,
        "package_found": True,
        "cache_version": VALIDATED_EVIDENCE_CACHE_VERSION,
        "document_signatures": doc_sigs,
        "text_manifest_mtime_ns": _file_mtime_ns_or_none(text_manifest_path),
        "decisions_mtime_ns": _file_mtime_ns_or_none(decisions_path),
    }


def _load_validated_evidence_cache(package_id: str) -> dict[str, Any] | None:
    package_path = resolve_package_path(package_id)
    if package_path is None:
        return None

    cache_path = _validated_evidence_cache_path(package_path)
    if not cache_path.exists():
        return None

    try:
        payload = json.loads(cache_path.read_text())
    except Exception:
        return None

    expected_sig = _validated_evidence_cache_signature(package_id)

    if payload.get("cache_signature") != expected_sig:
        return None

    report = payload.get("report")
    if not isinstance(report, dict):
        return None

    report["_validated_evidence_cache"] = {
        "status": "hit",
        "cache_path": str(cache_path),
        "cached_at": payload.get("cached_at"),
        "cache_version": VALIDATED_EVIDENCE_CACHE_VERSION,
    }
    return report


def _write_validated_evidence_cache(package_id: str, report: dict[str, Any]) -> None:
    package_path = resolve_package_path(package_id)
    if package_path is None:
        return

    cache_path = _validated_evidence_cache_path(package_path)

    clean_report = dict(report)
    clean_report.pop("_validated_evidence_cache", None)

    payload = {
        "cache_type": "validated_document_evidence_report",
        "cache_version": VALIDATED_EVIDENCE_CACHE_VERSION,
        "cached_at": datetime.now(timezone.utc).isoformat(),
        "cache_signature": _validated_evidence_cache_signature(package_id),
        "report": clean_report,
        "note": "Package-local validated evidence result cache. No metadata was updated and no database link was created.",
    }

    cache_path.write_text(json.dumps(payload, indent=2))


def _build_package_document_evidence_uncached_validated(package_id: str) -> dict[str, Any]:
    report = _build_package_document_evidence_base(package_id)
    return _apply_metadata_evidence_validation_layer_v2(report)

def build_package_document_evidence(package_id: str) -> dict[str, Any]:
    cached = _load_validated_evidence_cache(package_id)
    if cached is not None:
        return cached

    report = _build_package_document_evidence_uncached_validated(package_id)
    report["_validated_evidence_cache"] = {
        "status": "miss_written",
        "cache_version": VALIDATED_EVIDENCE_CACHE_VERSION,
    }
    _write_validated_evidence_cache(package_id, report)
    return report



def get_document_text_cache_status(package_id: str) -> dict[str, Any]:
    """Return read-only status for the package-local document text cache.

    This does not extract text, update metadata, or link to the database.
    """
    package_path = resolve_package_path(package_id)
    if package_path is None:
        return {
            "ok": False,
            "package": package_id,
            "status": "package_not_found",
            "note": "No metadata was updated.",
        }

    cache_dir, manifest_path = _document_cache_paths(package_path)

    docs = [
        p for p in sorted(package_path.rglob("*"))
        if p.is_file()
        and p.suffix.lower() in {".pdf", ".doc", ".docx", ".txt", ".csv"}
        and not p.name.startswith("_document_evidence_")
        and "_document_text_cache" not in p.parts
    ]

    manifest = _load_text_cache_manifest(package_path)
    manifest_docs = manifest.get("documents", {})

    cached_documents: list[dict[str, Any]] = []
    missing_or_stale_documents: list[dict[str, Any]] = []

    for doc in docs:
        rel = str(doc.relative_to(package_path))
        sig = _doc_file_signature(doc)
        entry = manifest_docs.get(rel, {})
        cache_file = entry.get("cache_file")
        cache_path = cache_dir / cache_file if cache_file else None

        cached_ok = (
            bool(cache_path)
            and cache_path.exists()
            and entry.get("size_bytes") == sig["size_bytes"]
            and entry.get("mtime_ns") == sig["mtime_ns"]
        )

        item = {
            "source_document": rel,
            "size_bytes": sig["size_bytes"],
            "mtime_ns": sig["mtime_ns"],
            "cached": cached_ok,
            "cache_file": cache_file,
            "cache_path": str(cache_path) if cache_path else None,
            "method": entry.get("method"),
            "page_count": entry.get("page_count"),
            "text_chars": entry.get("text_chars"),
            "status": entry.get("status"),
            "error": entry.get("error"),
            "cached_at": entry.get("cached_at"),
        }

        if cached_ok:
            cached_documents.append(item)
        else:
            missing_or_stale_documents.append(item)

    return {
        "ok": True,
        "package": package_path.name,
        "status": "cache_status",
        "package_path": str(package_path),
        "cache_manifest_exists": manifest_path.exists(),
        "cache_manifest_path": str(manifest_path),
        "cache_dir_exists": cache_dir.exists(),
        "cache_dir_path": str(cache_dir),
        "document_count": len(docs),
        "cache_hits_possible": len(cached_documents),
        "missing_or_stale_count": len(missing_or_stale_documents),
        "cached_documents": cached_documents,
        "missing_or_stale_documents": missing_or_stale_documents,
        "cache_summary": manifest.get("cache_summary", {}),
        "note": "Read-only cache status. No metadata was updated and no database link was created.",
    }



def list_document_evidence_package_index() -> dict[str, Any]:
    """Return a compact standalone index of staged document-evidence packages.

    This is read-only and package-local:
    - does not update metadata
    - does not link to the app database
    - does not call save_normalized_metadata
    """
    packages: list[dict[str, Any]] = []

    seen: set[str] = set()

    for root in PACKAGE_SEARCH_ROOTS:
        if not root.exists():
            continue

        for package_path in sorted(p for p in root.iterdir() if p.is_dir()):
            package_id = package_path.name

            if package_id in seen:
                continue
            seen.add(package_id)

            cache_status = get_document_text_cache_status(package_id)
            validated = _load_validated_evidence_cache(package_id)

            summary = {}
            validation_layer_version = None
            evidence_cache_status = "missing_or_stale"

            if validated is not None:
                summary = validated.get("summary", {})
                validation_layer_version = validated.get("validation_layer_version")
                evidence_cache_status = validated.get("_validated_evidence_cache", {}).get("status", "hit")

            apply_preview = build_metadata_apply_preview(package_id)

            packages.append({
                "package": package_id,
                "package_path": str(package_path),
                "document_count": cache_status.get("document_count"),
                "cache_hits_possible": cache_status.get("cache_hits_possible"),
                "missing_or_stale_count": cache_status.get("missing_or_stale_count"),
                "text_cache_ready": cache_status.get("missing_or_stale_count") == 0,
                "validated_evidence_cache_status": evidence_cache_status,
                "validation_layer_version": validation_layer_version,
                "grouped_recommendations": summary.get("grouped_recommendations"),
                "discrepancy_count": summary.get("discrepancy_count"),
                "raw_observations": summary.get("raw_observations"),
                "database_link_status": "not_linked",
                "target_status": apply_preview.get("target", {}).get("target_status"),
                "apply_allowed": apply_preview.get("target", {}).get("apply_allowed"),
                "links": {
                    "evidence_json": f"/api/document-evidence/packages/{package_id}",
                    "evidence_report": f"/api/document-evidence/packages/{package_id}/report",
                    "review_bundle_json": f"/api/document-evidence/packages/{package_id}/review-bundle",
                    "review_bundle_export": f"/api/document-evidence/packages/{package_id}/review-bundle/export",
                    "apply_preview_json": f"/api/document-evidence/packages/{package_id}/metadata-update-plan/apply-preview",
                    "apply_preview_report": f"/api/document-evidence/packages/{package_id}/metadata-update-plan/apply-preview/report",
                    "text_cache_status": f"/api/document-evidence/packages/{package_id}/text-cache/status",
                },
            })

    return {
        "ok": True,
        "analysis_type": "document_evidence_package_index",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "package_count": len(packages),
        "packages": packages,
        "note": "Standalone package index only. No metadata was updated and no database link was created.",
    }
