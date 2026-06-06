from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
import re

RULESET_VERSION = "metadata_identity_rules.v1"


@dataclass(frozen=True)
class IdentityRule:
    field: str
    aliases: tuple[str, ...]
    confidence: str
    priority: int
    canonical_survey_priority: int | None = None


IDENTITY_RULES: tuple[IdentityRule, ...] = (
    IdentityRule("survey_name", ("survey", "survey name", "survey title", "survey id", "survey identifier"), "high", 10, 10),
    IdentityRule("project_name", ("project", "project name", "project id", "project identifier"), "medium", 30, 30),
    IdentityRule("area_name", ("area", "area name", "survey area"), "medium", 40, 40),
    IdentityRule("field_name", ("field", "field name"), "medium", 50, None),
    IdentityRule("block_name", ("block", "block name"), "medium", 60, None),
    IdentityRule("prospect_name", ("prospect", "prospect name"), "medium", 70, None),
    IdentityRule("line_name", ("line", "line name", "line id", "line identifier", "line from file"), "medium", 20, None),
    IdentityRule("volume_name", ("volume", "volume name", "cube", "cube name", "volume id", "volume identifier"), "medium", 20, None),
)

_ALIAS_TO_RULES: tuple[tuple[re.Pattern[str], IdentityRule, str], ...] = tuple(
    (
        re.compile(r"^\s*" + re.escape(alias).replace(r"\ ", r"\s+") + r"\s*[:=]\s*(.+?)\s*$", re.IGNORECASE),
        rule,
        alias,
    )
    for rule in IDENTITY_RULES
    for alias in sorted(rule.aliases, key=len, reverse=True)
)

_NULL_VALUES = {"", "-", "--", "none", "null", "n/a", "na", "unknown", "not available"}


def clean_identity_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    text = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", text)
    text = text.strip().strip("'\"").strip()
    text = re.sub(r"\s+", " ", text)
    text = text.rstrip(";,.").strip().strip("'\"").strip()
    if text.lower() in _NULL_VALUES:
        return None
    return text or None


def _strip_segy_card_prefix(line: str) -> str:
    text = str(line or "")
    text = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", text)
    text = text.strip()
    return re.sub(r"^C\s*\d{1,2}\s+", "", text, flags=re.IGNORECASE).strip()


def _line_candidates(text: str | None) -> Iterable[tuple[str, str]]:
    if not text:
        return []
    lines: list[tuple[str, str]] = []
    for raw in str(text).splitlines():
        cleaned = _strip_segy_card_prefix(raw)
        if cleaned:
            lines.append((raw.rstrip(), cleaned))
    return lines


def extract_identity_candidates_from_textual_header(
    text: str | None,
    *,
    source: str,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for raw_line, line in _line_candidates(text):
        for pattern, rule, alias in _ALIAS_TO_RULES:
            match = pattern.match(line)
            if not match:
                continue
            value = clean_identity_value(match.group(1))
            if not value:
                continue
            key = (rule.field, value.lower(), alias.lower())
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                {
                    "field": rule.field,
                    "value": value,
                    "source": source,
                    "matched_alias": alias,
                    "evidence_line": raw_line.strip(),
                    "confidence": rule.confidence,
                    "priority": rule.priority,
                    "extractor_version": RULESET_VERSION,
                }
            )
            # One exact label match per line is enough. Prevent broad labels
            # from also matching the same line through fallback logic.
            break

    return candidates


def _decode_header_bytes(raw: bytes) -> tuple[str | None, str | None]:
    if not raw:
        return None, None

    candidates: list[tuple[int, str, str]] = []
    for encoding in ("ascii", "cp037", "latin-1"):
        try:
            text = raw.decode(encoding, errors="replace")
        except Exception:
            continue
        upper = text.upper()
        printable = sum(1 for ch in text if ch.isprintable() or ch in "\r\n\t")
        score = printable // 80
        if "C01" in upper or "C02" in upper:
            score += 5
        if "SURVEY" in upper:
            score += 10
        if "PROJECT" in upper:
            score += 4
        if "LINE" in upper:
            score += 2
        candidates.append((score, encoding, text))

    if not candidates:
        return None, None

    _, encoding, text = max(candidates, key=lambda item: item[0])
    return text, encoding


def read_segy_textual_header(path: str | Path | None) -> tuple[str | None, str | None]:
    if not path:
        return None, None
    segy_path = Path(path).expanduser()
    try:
        with segy_path.open("rb") as handle:
            raw = handle.read(3200)
    except Exception:
        return None, None
    return _decode_header_bytes(raw)


def _candidate_sort_key(candidate: dict[str, Any]) -> tuple[int, int, str]:
    priority = int(candidate.get("priority") or 999)
    confidence_rank = {"high": 0, "medium": 1, "low": 2}.get(str(candidate.get("confidence") or "low"), 2)
    return (priority, confidence_rank, str(candidate.get("value") or ""))


def _select_best(candidates: list[dict[str, Any]], field: str) -> dict[str, Any] | None:
    matching = [item for item in candidates if item.get("field") == field and item.get("value")]
    if not matching:
        return None
    return sorted(matching, key=_candidate_sort_key)[0]


def _select_canonical_survey_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    # Prefer explicit survey labels. If no explicit survey label is present,
    # allow project/area as a controlled medium-confidence fallback. Do not
    # promote field/block/prospect to survey_name.
    explicit = _select_best(candidates, "survey_name")
    if explicit:
        return explicit

    fallback: list[dict[str, Any]] = []
    for item in candidates:
        field = item.get("field")
        if field not in {"project_name", "area_name"}:
            continue
        alias = str(item.get("matched_alias") or "").lower()
        fallback_priority = 30 if field == "project_name" else 40
        item = dict(item)
        item["canonical_field"] = "survey_name"
        item["canonical_reason"] = f"{field}_fallback_no_explicit_survey_name"
        item["priority"] = fallback_priority
        item["confidence"] = "medium" if field == "project_name" else "low"
        fallback.append(item)
    if not fallback:
        return None
    return sorted(fallback, key=_candidate_sort_key)[0]


def canonicalize_identity_candidates(candidates: list[dict[str, Any]] | None) -> dict[str, Any]:
    candidates = [item for item in (candidates or []) if isinstance(item, dict) and item.get("value")]
    result: dict[str, Any] = {
        "identity_candidates": candidates,
        "identity_extraction": {
            "extractor_version": RULESET_VERSION,
            "candidate_count": len(candidates),
        },
    }

    survey = _select_canonical_survey_candidate(candidates)
    line = _select_best(candidates, "line_name")
    volume = _select_best(candidates, "volume_name")

    for field, candidate in (("survey_name", survey), ("line_name", line), ("volume_name", volume)):
        if candidate and candidate.get("value"):
            result[field] = candidate.get("value")
            result[f"{field}_source"] = candidate.get("source")
            result[f"{field}_evidence"] = candidate.get("evidence_line")
            result[f"{field}_matched_alias"] = candidate.get("matched_alias")
            result[f"{field}_confidence"] = candidate.get("confidence")

    return result


def extract_canonical_identity_from_textual_header(text: str | None, *, source: str) -> dict[str, Any]:
    candidates = extract_identity_candidates_from_textual_header(text, source=source)
    return canonicalize_identity_candidates(candidates)


def extract_canonical_identity_from_segy_path(path: str | Path | None) -> dict[str, Any]:
    text, encoding = read_segy_textual_header(path)
    identity = extract_canonical_identity_from_textual_header(text, source="segy_textual_header")
    if encoding:
        identity.setdefault("identity_extraction", {})["text_header_encoding"] = encoding
    if path and any(identity.get(key) for key in ("survey_name", "line_name", "volume_name")):
        identity.setdefault("identity_extraction", {})["source_path"] = str(Path(path).expanduser())
    return identity


def _candidate_from_existing_field(field: str, value: Any, *, source: str) -> dict[str, Any] | None:
    clean = clean_identity_value(value)
    if not clean:
        return None
    return {
        "field": field,
        "value": clean,
        "source": source,
        "matched_alias": field,
        "evidence_line": f"existing {field}",
        "confidence": "high",
        "priority": 1,
        "extractor_version": RULESET_VERSION,
    }


def _merge_unique_candidates(*candidate_groups: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for group in candidate_groups:
        for item in group or []:
            if not isinstance(item, dict):
                continue
            field = str(item.get("field") or "")
            value = str(item.get("value") or "")
            source = str(item.get("source") or "")
            line = str(item.get("evidence_line") or "")
            if not field or not value:
                continue
            key = (field, value.lower(), source, line)
            if key in seen:
                continue
            seen.add(key)
            merged.append(dict(item))
    return merged


def _candidates_from_mapping(mapping: dict[str, Any] | None, *, source: str) -> list[dict[str, Any]]:
    if not isinstance(mapping, dict):
        return []

    candidates: list[dict[str, Any]] = []
    for field in ("survey_name", "line_name", "volume_name"):
        candidate = _candidate_from_existing_field(field, mapping.get(field), source=source)
        if candidate:
            candidates.append(candidate)

    existing_candidates = mapping.get("identity_candidates")
    if isinstance(existing_candidates, list):
        candidates.extend([item for item in existing_candidates if isinstance(item, dict)])

    for key in ("decoded_text_header", "textual_header", "segy_textual_header", "text_header"):
        text = mapping.get(key)
        if text:
            candidates.extend(
                extract_identity_candidates_from_textual_header(text, source=f"{source}.{key}")
            )

    metadata = mapping.get("metadata")
    if isinstance(metadata, dict):
        candidates.extend(_candidates_from_mapping(metadata, source=f"{source}.metadata"))

    return candidates


def _identity_from_text_sidecar(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {}
    identity = extract_canonical_identity_from_textual_header(text, source="segy_textual_header_sidecar")
    if any(identity.get(key) for key in ("survey_name", "line_name", "volume_name")):
        identity.setdefault("identity_extraction", {})["sidecar_path"] = str(path)
    return identity


def _source_path_from_reference(source_reference: dict[str, Any]) -> Path | None:
    repository_id = clean_identity_value(source_reference.get("repository_id"))
    relative_path = clean_identity_value(source_reference.get("relative_path") or source_reference.get("source_relative_path"))
    if not repository_id or not relative_path:
        return None
    try:
        from app.services.repository_registry_service import get_repository
        repo = get_repository(repository_id)
    except Exception:
        repo = None
    if not isinstance(repo, dict):
        return None
    root_path = clean_identity_value(repo.get("root_path"))
    if not root_path:
        return None
    return Path(root_path).expanduser() / relative_path


def _candidate_sidecar_paths(*, backend_root: Path, source_reference: dict[str, Any], segy_file: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for volume_id in (
        source_reference.get("volume_id"),
        segy_file.get("volume_id"),
    ):
        clean_volume_id = clean_identity_value(volume_id)
        if clean_volume_id:
            paths.extend(
                [
                    backend_root / "data" / "zarr" / f"{clean_volume_id}.zarr.segy_text_header.txt",
                    backend_root / "data" / "zarr" / f"{clean_volume_id}.segy_text_header.txt",
                    backend_root / "data" / "uploads" / f"{clean_volume_id}.segy_text_header.txt",
                ]
            )

    for zarr_url in (source_reference.get("zarr_url"), segy_file.get("zarr_url")):
        clean_zarr_url = clean_identity_value(zarr_url)
        if not clean_zarr_url:
            continue
        if clean_zarr_url.startswith("/data/"):
            zarr_path = backend_root / clean_zarr_url.lstrip("/")
            paths.extend([Path(str(zarr_path) + ".segy_text_header.txt"), zarr_path / ".segy_text_header.txt"])
        elif clean_zarr_url.startswith("/endrepo/"):
            try:
                from app.storage.service import resolve_endrepo_zarr_url_path
                zarr_path = resolve_endrepo_zarr_url_path(clean_zarr_url)
                paths.extend([Path(str(zarr_path) + ".segy_text_header.txt"), zarr_path / ".segy_text_header.txt"])
            except Exception:
                pass

    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        marker = str(path)
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(path)
    return unique


def resolve_canonical_identity(
    source_reference: dict[str, Any] | None,
    *,
    segy_file: dict[str, Any] | None = None,
    backend_root: Path | None = None,
) -> dict[str, Any]:
    source_reference = source_reference if isinstance(source_reference, dict) else {}
    segy_file = segy_file if isinstance(segy_file, dict) else {}
    root = backend_root or Path(__file__).resolve().parents[2]

    candidate_groups: list[list[dict[str, Any]]] = [
        _candidates_from_mapping(segy_file, source="source_segy_registry"),
        _candidates_from_mapping(source_reference, source="source_reference"),
    ]

    source_path = _source_path_from_reference(source_reference)
    if source_path and source_path.exists() and source_path.is_file():
        path_identity = extract_canonical_identity_from_segy_path(source_path)
        path_candidates = path_identity.get("identity_candidates")
        if isinstance(path_candidates, list):
            for item in path_candidates:
                if isinstance(item, dict):
                    item.setdefault("source_path", str(source_path))
            candidate_groups.append(path_candidates)

    for sidecar_path in _candidate_sidecar_paths(backend_root=root, source_reference=source_reference, segy_file=segy_file):
        if sidecar_path.exists() and sidecar_path.is_file():
            sidecar_identity = _identity_from_text_sidecar(sidecar_path)
            sidecar_candidates = sidecar_identity.get("identity_candidates")
            if isinstance(sidecar_candidates, list):
                candidate_groups.append(sidecar_candidates)

    merged = _merge_unique_candidates(*candidate_groups)
    identity = canonicalize_identity_candidates(merged)
    if source_path and any(identity.get(key) for key in ("survey_name", "line_name", "volume_name")):
        identity.setdefault("identity_extraction", {})["source_path"] = str(source_path)
    return identity
