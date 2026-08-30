"""
Transient local AI bridge for the Well Metadata Extractor.

The bridge sends one rendered page at a time to the locally installed Ollama
model. It does not persist source pages, prompts, model responses, embeddings,
or extracted metadata.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ValidationError, field_validator


router = APIRouter(prefix="/api/wme/ai", tags=["wme-ai"])

OLLAMA_BASE_URL = os.getenv("WME_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("WME_OLLAMA_MODEL", "wme-qwen")
MAX_PAGE_TEXT = 12_000
MAX_IMAGE_BASE64 = 16_000_000

WELL_INFO_SCHEMA_VERSION = "2.0.0"
CANONICAL_WELL_INFO_FIELD_KEYS = {
    "well_name", "wellbore_name", "uwi", "field", "site", "block", "operator", "country", "well_status",
    "latitude", "longitude", "northing", "easting", "coordinate_system", "utm_zone", "geodetic_datum",
    "epsg_code", "north_reference", "grid_convergence", "depth_unit", "depth_reference", "reference_elevation", "surface_seabed_elevation", "water_depth", "seabed_depth_below_reference", "wellhead_depth_below_reference", "total_depth_md", "total_depth_tvd", "survey_start_md", "survey_end_md", "survey_start_tvd", "survey_end_tvd", "data_start_md", "data_end_md",
    "depth_reference", "depth_reference", "reference_elevation", "surface_seabed_elevation", "water_depth", "seabed_depth_below_reference", "wellhead_depth_below_reference", "total_depth_md", "total_depth_tvd",
    "trajectory_source", "survey_status", "survey_type", "calculation_method", "station_count",
    "survey_start_md", "survey_end_md", "survey_end_tvd", "maximum_inclination", "final_north_offset", "final_east_offset",
}
LEGACY_WELL_INFO_FIELD_KEYS = {
    "latitude_deg", "longitude_deg", "northing_m", "easting_m",
    "rotary_table_elevation_msl_m", "water_depth_m", "wellhead_seabed_depth_m",
    "first_md_m", "final_md_m", "final_tvd_m", "maximum_inclination_deg",
    "final_north_offset_m", "final_east_offset_m",
}

NUMERIC_FIELD_KEYS = {
    "northing", "easting", "grid_convergence", "data_start_md", "data_end_md",
    "reference_elevation", "surface_seabed_elevation", "water_depth", "seabed_depth_below_reference", "wellhead_depth_below_reference", "total_depth_md", "total_depth_tvd", "survey_start_md",
    "survey_end_md", "survey_end_tvd", "maximum_inclination", "final_north_offset",
    "final_east_offset",
}

FIELD_EVIDENCE_REQUIREMENTS: dict[str, tuple[re.Pattern[str], ...]] = {
    "well_name": (re.compile(r"\bwell(?:\s+name)?\s*[:|]", re.I),),
    "wellbore_name": (re.compile(r"\bwellbore(?:\s+name)?\s*[:|]", re.I),),
    "uwi": (re.compile(r"\b(?:UWI|API|local\s+(?:well\s+)?identifier|well\s+ID)\s*[:|]", re.I),),
    "field": (re.compile(r"\bfield\s*[:|]", re.I),),
    "site": (re.compile(r"\b(?:well\s+)?site\s*[:|]", re.I),),
    "block": (re.compile(r"\bblock\s*[:|]", re.I),),
    "operator": (re.compile(r"\boperator\s*[:|]", re.I),),
    "latitude": (re.compile(r"\b(?:latitude|lat|geographic)\b", re.I),),
    "longitude": (re.compile(r"\b(?:longitude|lon|long|geographic)\b", re.I),),
    "utm_zone": (re.compile(r"\bUTM\s+zone\s+(?:[1-9]|[1-5]\d|60)(?:[C-HJ-NP-X]|N|S)?\b", re.I),),
    "reference_elevation": (re.compile(r"\b(?:KB|RKB|RT|rotary\s+table|kelly\s+bushing)\s+elevation\b", re.I),),
    "water_depth": (re.compile(r"\bwater\s+depth\b", re.I),),
    "wellhead_depth_below_reference": (re.compile(r"\b(?:wellhead|sea\s*bed|seabed)\s+(?:depth|elevation)\b", re.I),),
    "survey_end_md": (re.compile(r"\b(?:total\s+depth|final\s+MD|TD)\b.*\bMD\b", re.I),),
    "survey_end_tvd": (re.compile(r"\b(?:total\s+depth|final\s+TVD|TD)\b.*\bTVD\b", re.I),),
}

UNIT_PATTERN = re.compile(
    r"(?<![A-Za-z])(?:m|metres?|meters?|ft|feet|deg(?:rees?)?|°|g/cc|psi|bar)\b",
    re.I,
)

def _numeric_token(value: str) -> str | None:
    match = re.search(r"[+-]?(?:\d{1,3}(?:[ ,]\d{3})+|\d+)(?:[.,]\d+)?", value)
    if not match:
        return None
    return match.group(0).replace(" ", "").replace(",", "")


def _label_bound_numeric(evidence: str, label_pattern: str) -> str | None:
    pattern = re.compile(
        rf"(?:{label_pattern})\s*[:|]?\s*"
        r"([+-]?(?:\d{1,3}(?:[ ,]\d{3})+|\d+)(?:[.,]\d+)?)",
        re.I,
    )
    match = pattern.search(evidence)
    if not match:
        return None
    return match.group(1).replace(" ", "").replace(",", "")


def _evidence_supports_field(field_key: str, evidence: str, value: str = "") -> bool:
    cleaned = evidence.strip()
    requirements = FIELD_EVIDENCE_REQUIREMENTS.get(field_key)
    if requirements and not any(pattern.search(cleaned) for pattern in requirements):
        return False

    if field_key == "uwi" and re.search(r"\bwell(?:\s+name)?\s*[:|]", cleaned, re.I):
        if not re.search(r"\b(?:UWI|API|local\s+(?:well\s+)?identifier|well\s+ID)\s*[:|]", cleaned, re.I):
            return False
    if field_key == "block" and re.search(r"\blicen[cs]e\b", cleaned, re.I) and not re.search(r"\bblock\b", cleaned, re.I):
        return False
    if field_key == "operator" and re.search(r"\bowners?\b", cleaned, re.I) and not re.search(r"\boperator\b", cleaned, re.I):
        return False
    if field_key == "site" and re.search(r"\bfield\b", cleaned, re.I) and not re.search(r"\bsite\b", cleaned, re.I):
        return False
    if field_key == "field" and re.search(r"\bsite\b", cleaned, re.I) and not re.search(r"\bfield\b", cleaned, re.I):
        return False
    if field_key == "utm_zone" and not re.search(r"\bUTM\s+zone\b", cleaned, re.I):
        return False
    if field_key == "wellhead_depth_below_reference" and re.search(r"\bsea\s*bed\s+at\b", cleaned, re.I):
        return False

    proposed = _numeric_token(value)
    if field_key == "reference_elevation":
        bound = _label_bound_numeric(cleaned, r"(?:KB|RKB|RT|rotary\s+table|kelly\s+bushing)\s+elevation")
        if proposed is None or bound is None or proposed != bound:
            return False
    if field_key == "water_depth":
        bound = _label_bound_numeric(cleaned, r"water\s+depth")
        if proposed is None or bound is None or proposed != bound:
            return False
    if field_key == "wellhead_depth_below_reference":
        bound = _label_bound_numeric(cleaned, r"(?:wellhead|sea\s*bed|seabed)\s+(?:depth|elevation)")
        if proposed is None or bound is None or proposed != bound:
            return False

    return True

def _normalize_numeric_proposal(proposal: WmeAiProposal) -> WmeAiProposal | None:
    if proposal.field_key not in NUMERIC_FIELD_KEYS:
        return proposal

    raw_value = proposal.value.strip()
    raw_unit = proposal.unit.strip()
    match = re.search(r"[+-]?(?:\d{1,3}(?:[ ,]\d{3})+|\d+)(?:[.,]\d+)?", raw_value)
    if not match:
        return None

    numeric = match.group(0).replace(" ", "").replace(",", "")
    detected_unit = raw_unit
    if not detected_unit:
        unit_match = UNIT_PATTERN.search(raw_value)
        if unit_match:
            detected_unit = unit_match.group(0).replace("degrees", "deg").replace("degree", "deg")

    return proposal.model_copy(update={"value": numeric, "unit": detected_unit})

def _sanitize_proposal(proposal: WmeAiProposal) -> WmeAiProposal | None:
    if not _evidence_supports_field(proposal.field_key, proposal.evidence, proposal.value):
        return None

    normalized = _normalize_numeric_proposal(proposal)
    if normalized is None:
        return None

    if normalized.value_status == "actual" and not re.search(
        r"\b(?:actual|as[- ]drilled|as[- ]built|final|completed|abandoned|P\s*&\s*A)\b",
        normalized.evidence,
        re.I,
    ):
        normalized = normalized.model_copy(update={"value_status": "unknown"})

    return normalized




STRICT_DETERMINISTIC_FIELDS = {
    "reference_elevation",
    "wellhead_depth_below_reference",
}


def _clean_numeric_text(value: str) -> str:
    return value.replace(" ", "").replace(",", "")


def _make_deterministic_proposal(
    field_key: str,
    value: str,
    unit: str,
    evidence: str,
    *,
    reference: str = "",
    value_status: Literal["actual", "planned", "proposed", "forecast", "unknown"] = "unknown",
) -> WmeAiProposal:
    return WmeAiProposal(
        field_key=field_key,
        value=value,
        unit=unit,
        reference=reference,
        value_status=value_status,
        location_type="unknown",
        evidence=evidence,
    )


def _extract_strict_summary_fields(page_text: str) -> list[WmeAiProposal]:
    """Parse strongly labelled summary values before invoking the model.

    These fields are deliberately excluded from AI extraction. A value is
    returned only when the complete label can be bound deterministically.
    """
    normalized = page_text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"\s+", " ", line).strip() for line in normalized.split("\n")]
    lines = [line for line in lines if line]
    joined = "\n".join(lines)
    proposals: list[WmeAiProposal] = []

    # Best case: label and value survived on the same extracted line.
    direct = re.search(
        r"\b(?:KB|RKB|RT|Rotary Table|Kelly Bushing) Elevation\b"
        r"\s*[:|]?\s*([+-]?\d+(?:[.,]\d+)?)\s*(m|ft)\b",
        joined,
        re.I,
    )
    if direct:
        value = direct.group(1).replace(",", ".")
        unit = direct.group(2)
        proposals.append(
            _make_deterministic_proposal(
                "reference_elevation",
                value,
                unit,
                direct.group(0),
            )
        )
    else:
        # Common PDF extraction failure: labels are emitted first and their
        # aligned values follow as a value block. Bind the first standalone
        # elevation-like value after the complete KB Elevation label, while
        # rejecting MD/TVD-labelled depth values.
        label_index = next(
            (
                index
                for index, line in enumerate(lines)
                if re.fullmatch(
                    r"(?:KB|RKB|RT|Rotary Table|Kelly Bushing) Elevation",
                    line,
                    re.I,
                )
            ),
            None,
        )
        if label_index is not None:
            for candidate in lines[label_index + 1 : label_index + 18]:
                if re.search(r"\b(?:MD|TVD)\b", candidate, re.I):
                    continue
                match = re.fullmatch(r"([+-]?\d+(?:[.,]\d+)?)\s*(m|ft)", candidate, re.I)
                if not match:
                    continue
                value = match.group(1).replace(",", ".")
                unit = match.group(2)
                evidence = f"KB Elevation | {candidate}"
                proposals.append(
                    _make_deterministic_proposal(
                        "reference_elevation",
                        value,
                        unit,
                        evidence,
                    )
                )
                break

    # Wellhead / seabed depth is accepted only when the full field label and
    # value are explicit. A plotted 'SEA BED at ...' event is never accepted.
    seabed = re.search(
        r"\b(?:Wellhead\s*/\s*Seabed Depth|Wellhead Depth|Seabed Depth|"
        r"Sea Bed Depth|Mudline Depth)\b\s*[:|]?\s*"
        r"([+-]?\d+(?:[.,]\d+)?)\s*(m|ft)\b",
        joined,
        re.I,
    )
    if seabed and not re.search(r"\bSEA BED at\b", seabed.group(0), re.I):
        proposals.append(
            _make_deterministic_proposal(
                "wellhead_depth_below_reference",
                seabed.group(1).replace(",", "."),
                seabed.group(2),
                seabed.group(0),
            )
        )

    return proposals

class WmeAiStatus(BaseModel):
    available: bool
    service: str = "ollama"
    model: str = OLLAMA_MODEL
    detail: str


class WmeAiExtractRequest(BaseModel):
    selected_well: str = ""
    selected_wellbore: str = ""
    source_file: str
    page_number: int = Field(ge=1)
    page_image: str = ""
    page_text: str = ""
    missing_fields: list[str] = Field(min_length=1, max_length=50)
    scan_mode: Literal["fast", "deep"] = "fast"
    document_identity_verified: bool = False

    @field_validator("page_image")
    @classmethod
    def validate_image_size(cls, value: str) -> str:
        cleaned = value.strip()
        if cleaned and len(cleaned) < 100:
            raise ValueError("Rendered page image is invalid")
        if len(cleaned) > MAX_IMAGE_BASE64:
            raise ValueError("Rendered page image is too large")
        return cleaned

    @field_validator("missing_fields")
    @classmethod
    def normalize_fields(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            key = str(item).strip()
            if key in LEGACY_WELL_INFO_FIELD_KEYS:
                raise ValueError(
                    f'Legacy Well Info field key "{key}" is not supported; use schema version {WELL_INFO_SCHEMA_VERSION}'
                )
            if key and key not in CANONICAL_WELL_INFO_FIELD_KEYS:
                raise ValueError(f'Unsupported Well Info field key "{key}"')
            if key and key not in seen:
                seen.add(key)
                normalized.append(key)
        if not normalized:
            raise ValueError("At least one missing field is required")
        return normalized


class WmeAiProposal(BaseModel):
    field_key: str
    value: str
    unit: str = ""
    reference: str = ""
    value_status: Literal["actual", "planned", "proposed", "forecast", "unknown"] = "unknown"
    location_type: Literal[
        "wellhead",
        "slot_centre",
        "surface_location",
        "bottomhole",
        "structure_centre",
        "unknown",
    ] = "unknown"
    subject_identity_match: Literal["selected", "other", "uncertain"] = "uncertain"
    evidence: str


class WmeAiExtractResponse(BaseModel):
    well_identity_match: Literal["match", "mismatch", "uncertain"]
    page_relevance: Literal["relevant", "irrelevant", "uncertain"]
    proposals: list[WmeAiProposal]
    model: str = OLLAMA_MODEL


def _request_json(url: str, payload: dict[str, Any] | None = None, timeout: float = 8.0) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="GET" if payload is None else "POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _model_available() -> tuple[bool, str]:
    try:
        payload = _request_json(f"{OLLAMA_BASE_URL}/api/tags", timeout=4.0)
    except urllib.error.URLError as exc:
        return False, f"Ollama is not reachable: {exc.reason}"
    except Exception as exc:  # defensive boundary around the local service
        return False, f"Ollama status check failed: {exc}"

    names = {
        str(model.get("name", ""))
        for model in payload.get("models", [])
        if isinstance(model, dict)
    }
    available = OLLAMA_MODEL in names or f"{OLLAMA_MODEL}:latest" in names
    if not available:
        return False, f'Local model "{OLLAMA_MODEL}" is not installed'
    return True, "Local AI is ready"


@router.get("/status", response_model=WmeAiStatus)
async def status() -> WmeAiStatus:
    available, detail = await asyncio.to_thread(_model_available)
    return WmeAiStatus(available=available, detail=detail)


def _response_schema(allowed_fields: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["well_identity_match", "page_relevance", "proposals"],
        "properties": {
            "well_identity_match": {
                "type": "string",
                "enum": ["match", "mismatch", "uncertain"],
            },
            "page_relevance": {
                "type": "string",
                "enum": ["relevant", "irrelevant", "uncertain"],
            },
            "proposals": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "field_key",
                        "value",
                        "unit",
                        "reference",
                        "value_status",
                        "location_type",
                        "subject_identity_match",
                        "evidence",
                    ],
                    "properties": {
                        "field_key": {"type": "string", "enum": allowed_fields},
                        "value": {"type": "string"},
                        "unit": {"type": "string"},
                        "reference": {"type": "string"},
                        "value_status": {
                            "type": "string",
                            "enum": ["actual", "planned", "proposed", "forecast", "unknown"],
                        },
                        "location_type": {
                            "type": "string",
                            "enum": [
                                "wellhead",
                                "slot_centre",
                                "surface_location",
                                "bottomhole",
                                "structure_centre",
                                "unknown",
                            ],
                        },
                        "subject_identity_match": {
                            "type": "string",
                            "enum": ["selected", "other", "uncertain"],
                        },
                        "evidence": {"type": "string"},
                    },
                },
            },
        },
    }


def _normalize_model_payload(parsed: Any) -> dict[str, Any]:
    if isinstance(parsed, dict):
        if {"well_identity_match", "page_relevance", "proposals"}.issubset(parsed):
            return parsed
        if {"field_key", "value", "evidence"}.issubset(parsed):
            return {
                "well_identity_match": "uncertain",
                "page_relevance": "relevant",
                "proposals": [parsed],
            }

    if isinstance(parsed, list):
        proposals = [
            item
            for item in parsed
            if isinstance(item, dict)
            and {"field_key", "value", "evidence"}.issubset(item)
        ]
        if proposals:
            return {
                "well_identity_match": "uncertain",
                "page_relevance": "relevant",
                "proposals": proposals,
            }

    raise ValueError("Model JSON does not match the WME response envelope")


def _parse_model_json(content: str) -> dict[str, Any]:
    candidate = content.strip()

    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate, flags=re.IGNORECASE)
        candidate = re.sub(r"\s*```$", "", candidate)

    parsed_candidates: list[Any] = []

    try:
        parsed_candidates.append(json.loads(candidate))
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for match in re.finditer(r"[\{\[]", candidate):
        try:
            parsed, _ = decoder.raw_decode(candidate[match.start():])
        except json.JSONDecodeError:
            continue
        parsed_candidates.append(parsed)

    for parsed in parsed_candidates:
        if isinstance(parsed, dict) and {"well_identity_match", "page_relevance", "proposals"}.issubset(parsed):
            return _normalize_model_payload(parsed)

    standalone_proposals: list[dict[str, Any]] = []
    seen_proposals: set[tuple[str, str, str]] = set()

    for parsed in parsed_candidates:
        proposal_items: list[Any] = []
        if isinstance(parsed, dict) and {"field_key", "value", "evidence"}.issubset(parsed):
            proposal_items = [parsed]
        elif isinstance(parsed, list):
            proposal_items = parsed

        for item in proposal_items:
            if not (
                isinstance(item, dict)
                and {"field_key", "value", "evidence"}.issubset(item)
            ):
                continue

            identity = (
                str(item.get("field_key", "")).strip(),
                str(item.get("value", "")).strip(),
                str(item.get("evidence", "")).strip(),
            )
            if identity in seen_proposals:
                continue
            seen_proposals.add(identity)
            standalone_proposals.append(item)

    if standalone_proposals:
        return {
            "well_identity_match": "uncertain",
            "page_relevance": "relevant",
            "proposals": standalone_proposals,
        }

    for parsed in parsed_candidates:
        try:
            return _normalize_model_payload(parsed)
        except ValueError:
            continue

    raise json.JSONDecodeError("No valid WME JSON payload found", candidate, 0)

def _ollama_chat(payload: dict[str, Any]) -> str:
    raw = _request_json(f'{OLLAMA_BASE_URL}/api/chat', payload=payload, timeout=240.0)
    content = raw.get('message', {}).get('content')
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError('The local model returned no structured response')
    return content


def _normalize_identity_token(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _explicit_subject_tokens(text: str) -> set[str]:
    tokens: set[str] = set()

    labelled_pattern = re.compile(
        r"\b(?:well(?:bore)?|borehole|sidetrack|branch)"
        r"(?:\s+(?:name|number|no\.?|id))?\s*[:#-]?\s*"
        r"([A-Z0-9][A-Z0-9/_-]{2,})",
        re.IGNORECASE,
    )
    petroleum_pattern = re.compile(
        r"\b\d{1,3}/\d{1,3}(?:-[A-Z0-9]+)+(?:\s*[A-Z])?\b",
        re.IGNORECASE,
    )

    for match in labelled_pattern.finditer(text):
        token = _normalize_identity_token(match.group(1))
        if token:
            tokens.add(token)

    for match in petroleum_pattern.finditer(text):
        token = _normalize_identity_token(match.group(0))
        if token:
            tokens.add(token)

    return tokens


def _authoritative_subject_binding(
    proposal: WmeAiProposal,
    request: WmeAiExtractRequest,
) -> WmeAiProposal:
    if not request.document_identity_verified:
        return proposal

    selected_tokens = {
        token
        for token in (
            _normalize_identity_token(request.selected_well),
            _normalize_identity_token(request.selected_wellbore),
        )
        if token
    }

    evidence_tokens = _explicit_subject_tokens(proposal.evidence)

    if not evidence_tokens:
        # In a verified document, unqualified page evidence belongs to the
        # selected well unless a different subject is explicitly named.
        return proposal.model_copy(update={"subject_identity_match": "selected"})

    if selected_tokens and any(
        evidence == selected
        or evidence.endswith(selected)
        or selected.endswith(evidence)
        for evidence in evidence_tokens
        for selected in selected_tokens
    ):
        return proposal.model_copy(update={"subject_identity_match": "selected"})

    return proposal.model_copy(update={"subject_identity_match": "other"})



def _extract(request: WmeAiExtractRequest) -> WmeAiExtractResponse:
    available, detail = _model_available()
    if not available:
        raise RuntimeError(detail)

    selected_identity = " / ".join(
        part for part in (request.selected_well.strip(), request.selected_wellbore.strip()) if part
    ) or "not supplied"

    page_text = request.page_text[:MAX_PAGE_TEXT]
    deterministic = [
        proposal
        for proposal in _extract_strict_summary_fields(page_text)
        if proposal.field_key in request.missing_fields
    ]
    deterministic_keys = {proposal.field_key for proposal in deterministic}
    ai_fields = [
        field_key
        for field_key in request.missing_fields
        if field_key not in STRICT_DETERMINISTIC_FIELDS
    ]

    if not ai_fields:
        return WmeAiExtractResponse(
            well_identity_match="uncertain",
            page_relevance="relevant" if deterministic else "uncertain",
            proposals=deterministic,
            model=OLLAMA_MODEL,
        )

    fields = ", ".join(ai_fields)

    prompt = f"""Selected well identity: {selected_identity}
Source file: {request.source_file}
Source page: {request.page_number}
Scan mode: {request.scan_mode}
Document identity already verified by application: {request.document_identity_verified}

Extract only these currently missing fields:
{fields}

Page text supplied by the application:
--- PAGE TEXT START ---
{page_text}
--- PAGE TEXT END ---

Use the supplied page text as the primary evidence. When a page image is supplied, use it to verify values that are missing, ambiguous, or poorly represented in the text extraction.

Mandatory rules:
- Return only requested field keys.
- Return a proposal only when its value is explicitly visible on this page.
- Do not infer, calculate, estimate, normalize to an unstated datum, or use outside knowledge.
- When document identity is already verified, do not reject the entire page merely because it mentions another well, sidetrack, offset well, target, or reference well.
- Bind every proposal using subject_identity_match:
  - selected: belongs to the selected well or wellbore;
  - other: use only when the supporting evidence explicitly names a different well, sidetrack, offset/reference well, or unrelated subject;
  - uncertain: use only when evidence explicitly identifies a subject but it cannot be resolved.
- In a verified document, unqualified evidence defaults to the selected well. Do not mark it other merely because the page discusses multiple wells elsewhere.
- Use page-level mismatch only when the document itself is unrelated to the selected well.
- Distinguish actual from planned, proposed, and forecast values.
- Distinguish wellhead, slot-centre, surface-location, bottomhole, and structure-centre coordinates.
- Do not return structure-centre coordinates as well coordinates.
- Preserve visible units and depth or coordinate references.
- Treat coordinate-reference information as one linked block. Check surrounding labels for latitude, longitude, northing, easting, coordinate system, UTM zone, geodetic datum, EPSG code, north reference, and grid convergence.
- UTM zone requires the explicit phrase "UTM zone" followed by a zone number. Never take a leading digit from northing as the zone.
- One visible label may populate only its matching field. Never reuse one labelled value for a semantically adjacent field.
- Well or Well Name is not UWI. Populate UWI only from an explicit UWI, API, Local Identifier, or Well ID label.
- Licence or License is not Block. Populate Block only from an explicit Block label.
- Owners are not Operator. Populate Operator only from an explicit Operator label.
- Site requires an explicit Site or Well Site label. Never copy a value labelled Field into Site.
- Field requires an explicit Field label. Never copy a Site value into Field.
- RT / KB elevation and Wellhead / Seabed Depth are resolved deterministically before this AI call and are not requested from the model.
- Water depth requires an explicit Water Depth label and the number immediately associated with it.
- Wellhead / seabed depth requires an explicit Wellhead Depth, Seabed Depth, or Sea Bed Depth label. Do not use a plotted "SEA BED at ... MD/TVD" event or first survey MD.
- final_md evidence must explicitly associate a total/final depth with MD. final_tvd evidence must explicitly associate a total/final depth with TVD.
- Return geodetic datum or grid convergence only when explicitly visible in the page image or page text. Do not infer either value from an EPSG code, UTM zone, country, or coordinate values.
- For numeric fields, put only the numeric token in value and put the unit in unit. Keep N/E directional qualifiers in evidence or reference.
- Evidence must quote the shortest visible text that supports the value.
- Return an empty proposals array when evidence is insufficient.
"""

    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "keep_alive": "10m",
        "format": _response_schema(ai_fields),
        "messages": [
            {
                "role": "user",
                "content": prompt,
                **(
                    {"images": [request.page_image]}
                    if request.page_image and len(page_text.strip()) < 800
                    else {}
                ),
            }
        ],
        "think": False,
        "options": {
            "temperature": 0,
            "seed": 42,
            "num_ctx": 8192,
            "num_predict": 1200,
        },
    }

    content = _ollama_chat(payload)
    try:
        parsed = _parse_model_json(content)
    except json.JSONDecodeError:
        retry_payload = {
            **payload,
            "format": "json",
            "messages": [
                *payload["messages"],
                {"role": "assistant", "content": content[:12000]},
                {
                    "role": "user",
                    "content": (
                        "Your previous response was not valid JSON. "
                        "Return only one compact JSON object matching the requested schema. "
                        "Do not include reasoning, Markdown, commentary, or code fences."
                    ),
                },
            ],
        }
        retry_content = _ollama_chat(retry_payload)
        parsed = _parse_model_json(retry_content)

    try:
        response = WmeAiExtractResponse.model_validate({**parsed, "model": OLLAMA_MODEL})
    except ValidationError:
        retry_payload = {
            **payload,
            "format": _response_schema(ai_fields),
            "messages": [
                *payload["messages"],
                {"role": "assistant", "content": json.dumps(parsed)},
                {
                    "role": "user",
                    "content": (
                        "Return exactly one JSON object with top-level keys "
                        "well_identity_match, page_relevance, and proposals. "
                        "Return only valid JSON."
                    ),
                },
            ],
        }
        retry_content = _ollama_chat(retry_payload)
        retry_parsed = _parse_model_json(retry_content)
        response = WmeAiExtractResponse.model_validate(
            {**retry_parsed, "model": OLLAMA_MODEL}
        )

    allowed = set(ai_fields)
    filtered: list[WmeAiProposal] = []
    for proposal in response.proposals:
        if proposal.field_key not in allowed:
            continue
        if not proposal.value.strip() or not proposal.evidence.strip():
            continue
        sanitized = _sanitize_proposal(proposal)
        if sanitized is None:
            continue
        filtered.append(_authoritative_subject_binding(sanitized, request))

    merged = [*deterministic, *filtered]
    response_identity = response.well_identity_match
    if request.document_identity_verified:
        response_identity = "match" if merged else "uncertain"

    return response.model_copy(
        update={
            "well_identity_match": response_identity,
            "proposals": merged,
        }
    )


@router.post("/extract", response_model=WmeAiExtractResponse)
async def extract(request: WmeAiExtractRequest) -> WmeAiExtractResponse:
    try:
        return await asyncio.to_thread(_extract, request)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise HTTPException(status_code=502, detail=f"Ollama rejected the request: {detail}") from exc
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=503, detail=f"Ollama is not reachable: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="The local model returned invalid JSON") from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=502,
            detail="The local model returned JSON with an invalid WME response structure",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
