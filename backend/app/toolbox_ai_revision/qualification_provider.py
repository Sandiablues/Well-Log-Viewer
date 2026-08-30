from __future__ import annotations

import base64
import json
import random
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .qualification_evidence import EvidencePreparationError, prepare_evidence
import re

OPENAI_CANDIDATE_MODEL = "gpt-5.6-luna"
OPENAI_JUDGE_MODEL = "gpt-5.6-terra"
ANTHROPIC_CANDIDATE_MODEL = "claude-haiku-4-5"
ANTHROPIC_JUDGE_MODEL = "claude-haiku-4-5"
GEMINI_MODEL = "gemini-3.6-flash"

PROVIDERS = ("openai", "anthropic", "gemini")


class ProviderCallError(RuntimeError):
    def __init__(self, provider: str, message: str, *, status: int | None = None):
        super().__init__(message)
        self.provider = provider
        self.status = status


def _repo_root() -> Path:
    # .../Well-Log-Viewer/backend/app/toolbox_ai_revision/qualification_provider.py
    return Path(__file__).resolve().parents[3]


def load_provider_keys() -> dict[str, str]:
    values = {
        "openai": "",
        "anthropic": "",
        "gemini": "",
    }
    env_file = _repo_root() / ".env.ai"
    if not env_file.exists():
        return values

    mapping = {
        "OPENAI_API_KEY": "openai",
        "ANTHROPIC_API_KEY": "anthropic",
        "GEMINI_API_KEY": "gemini",
    }
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        target = mapping.get(key.strip())
        if target:
            values[target] = value.strip()
    return values


def provider_status() -> dict[str, dict[str, Any]]:
    keys = load_provider_keys()
    return {
        "openai": {
            "configured": bool(keys["openai"]),
            "label": "OpenAI",
            "model": f"{OPENAI_CANDIDATE_MODEL} candidate / {OPENAI_JUDGE_MODEL} judge",
            "candidate_model": OPENAI_CANDIDATE_MODEL,
            "judge_model": OPENAI_JUDGE_MODEL,
        },
        "anthropic": {
            "configured": bool(keys["anthropic"]),
            "label": "Claude",
            "model": f"{ANTHROPIC_CANDIDATE_MODEL} candidate / {ANTHROPIC_JUDGE_MODEL} judge",
            "candidate_model": ANTHROPIC_CANDIDATE_MODEL,
            "judge_model": ANTHROPIC_JUDGE_MODEL,
        },
        "gemini": {"configured": bool(keys["gemini"]), "label": "Gemini", "model": GEMINI_MODEL},
    }


def _post_json(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    provider: str,
    *,
    timeout_seconds: int,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            data = response.read().decode("utf-8")
            return json.loads(data)
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body_text)
            message = (
                parsed.get("error", {}).get("message")
                if isinstance(parsed.get("error"), dict)
                else parsed.get("message")
            ) or body_text
        except Exception:
            message = body_text
        raise ProviderCallError(provider, str(message), status=exc.code) from exc
    except urllib.error.URLError as exc:
        raise ProviderCallError(provider, str(exc.reason)) from exc
    except TimeoutError as exc:
        raise ProviderCallError(provider, "Provider request timed out.") from exc


_GEMINI_OUTPUT_LIMIT_CACHE: int | None = None


def _get_json(
    url: str,
    headers: dict[str, str],
    provider: str,
    *,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8", errors="replace")
            payload = json.loads(raw)
            return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _gemini_output_token_limit(key: str) -> int | None:
    global _GEMINI_OUTPUT_LIMIT_CACHE
    if _GEMINI_OUTPUT_LIMIT_CACHE is not None:
        return _GEMINI_OUTPUT_LIMIT_CACHE

    payload = _get_json(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}",
        {"x-goog-api-key": key},
        "gemini",
    )
    raw_limit = payload.get("outputTokenLimit")
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        return None
    if limit <= 0:
        return None
    _GEMINI_OUTPUT_LIMIT_CACHE = limit
    return limit


def _extract_openai_text(payload: dict[str, Any]) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    chunks: list[str] = []
    for item in payload.get("output", []) if isinstance(payload.get("output"), list) else []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []) if isinstance(item.get("content"), list) else []:
            if isinstance(content, dict):
                text = content.get("text")
                if isinstance(text, str):
                    chunks.append(text)
    return "\n".join(chunks).strip()


def _extract_anthropic_text(payload: dict[str, Any]) -> str:
    chunks: list[str] = []
    for item in payload.get("content", []) if isinstance(payload.get("content"), list) else []:
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            chunks.append(item["text"])
    return "\n".join(chunks).strip()


def _extract_gemini_text(payload: dict[str, Any]) -> str:
    chunks: list[str] = []
    candidates = payload.get("candidates", [])
    if not isinstance(candidates, list):
        return ""
    for candidate in candidates[:1]:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content", {})
        if not isinstance(content, dict):
            continue
        parts = content.get("parts", [])
        if not isinstance(parts, list):
            continue
        for part in parts:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                chunks.append(part["text"])
    return "\n".join(chunks).strip()


def _text_evidence_blocks(evidence_files: list[dict[str, Any]]) -> list[str]:
    blocks: list[str] = []
    for item in evidence_files:
        mime = str(item.get("mime_type") or "")
        if mime == "application/pdf":
            continue
        data = str(item.get("content_base64") or "")
        if not data:
            continue
        try:
            decoded = base64.b64decode(data).decode("utf-8", errors="replace")
        except Exception:
            continue
        blocks.append(f"\n--- EVIDENCE FILE: {item.get('name', 'unnamed')} ---\n{decoded}\n--- END EVIDENCE ---")
    return blocks


def _pdf_evidence_files(evidence_files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item for item in evidence_files
        if str(item.get("mime_type") or "") == "application/pdf" and str(item.get("content_base64") or "")
    ]


def adaptive_timeout_seconds(evidence_files: list[dict[str, Any]] | None = None) -> int:
    """Scale provider timeout with evidence size.

    Base: 180 seconds.
    Add: 20 seconds per MiB of supplied evidence.
    Clamp: 180..900 seconds.
    """
    total_bytes = 0
    for item in evidence_files or []:
        size = item.get("size")
        if isinstance(size, (int, float)) and size > 0:
            total_bytes += int(size)
            continue
        data = item.get("content_base64")
        if isinstance(data, str) and data:
            # Approximate decoded bytes without actually decoding again.
            total_bytes += int(len(data) * 0.75)

    total_mib = total_bytes / (1024 * 1024)
    calculated = int(round(180 + (20 * total_mib)))
    return max(180, min(900, calculated))


def call_provider(
    provider: str,
    prompt: str,
    evidence_files: list[dict[str, Any]] | None = None,
    *,
    role: str = "candidate",
) -> tuple[str, str]:
    keys = load_provider_keys()
    evidence_files = evidence_files or []
    timeout_seconds = adaptive_timeout_seconds(evidence_files)
    if provider not in PROVIDERS:
        raise ProviderCallError(provider, f"Unknown provider: {provider}")
    key = keys.get(provider, "")
    if not key:
        raise ProviderCallError(provider, "Provider API key is not configured.")

    text_prompt = prompt + "".join(_text_evidence_blocks(evidence_files))
    pdfs = _pdf_evidence_files(evidence_files)

    if provider == "openai":
        openai_model = OPENAI_JUDGE_MODEL if role == "judge" else OPENAI_CANDIDATE_MODEL
        content: list[dict[str, Any]] = [{"type": "input_text", "text": text_prompt}]
        for item in pdfs:
            content.append({
                "type": "input_file",
                "filename": str(item.get("name") or "evidence.pdf"),
                "file_data": f"data:application/pdf;base64,{item['content_base64']}",
            })
        response = _post_json(
            "https://api.openai.com/v1/responses",
            {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
            },
            {
                "model": openai_model,
                "input": [{"role": "user", "content": content}],
            },
            provider,
            timeout_seconds=timeout_seconds,
        )
        return _extract_openai_text(response), openai_model

    if provider == "anthropic":
        anthropic_model = ANTHROPIC_JUDGE_MODEL if role == "judge" else ANTHROPIC_CANDIDATE_MODEL
        content: list[dict[str, Any]] = [{"type": "text", "text": text_prompt}]
        for item in pdfs:
            content.append({
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": item["content_base64"],
                },
                "title": str(item.get("name") or "evidence.pdf"),
            })
        response = _post_json(
            "https://api.anthropic.com/v1/messages",
            {
                "Content-Type": "application/json",
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
            },
            {
                "model": anthropic_model,
                "max_tokens": 64000,
                "messages": [{"role": "user", "content": content}],
            },
            provider,
            timeout_seconds=timeout_seconds,
        )
        return _extract_anthropic_text(response), anthropic_model

    parts: list[dict[str, Any]] = [{"text": text_prompt}]
    for item in pdfs:
        parts.append({
            "inlineData": {
                "mimeType": "application/pdf",
                "data": item["content_base64"],
            }
        })
    generation_config: dict[str, Any] = {
        "responseMimeType": "application/json",
    }
    gemini_output_limit = _gemini_output_token_limit(key)
    if gemini_output_limit is not None:
        generation_config["maxOutputTokens"] = gemini_output_limit

    response = _post_json(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        {
            "Content-Type": "application/json",
            "x-goog-api-key": key,
        },
        {
            "contents": [{"parts": parts}],
            "generationConfig": generation_config,
        },
        provider,
        timeout_seconds=timeout_seconds,
    )
    gemini_text = _extract_gemini_text(response)
    if gemini_text:
        return gemini_text, GEMINI_MODEL

    diagnostic = {
        "conclusion": {
            "status": "unresolved",
            "summary": "Gemini returned no extractable text content.",
        },
        "findings": [],
        "unresolved_evidence": [],
        "conflicts": [],
        "evidence_used": [],
        "hypotheses": [],
        "confidence": 0.0,
        "rule_compliance": False,
        "limitations": [
            "Gemini API completed but no text part could be extracted from the response envelope."
        ],
        "provider_response_empty_text": True,
        "provider_response_envelope": response,
    }
    return json.dumps(diagnostic, ensure_ascii=False), GEMINI_MODEL

def _extract_json_object(text: str) -> dict[str, Any] | None:
    cleaned = text.strip()
    if not cleaned:
        return None

    # 1. Exact JSON response.
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    # 2. Prefer explicit fenced JSON anywhere in a prose response.
    fenced_blocks = re.findall(
        r"```(?:json)?\s*(\{.*?\})\s*```",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for block in fenced_blocks:
        try:
            parsed = json.loads(block)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            continue

    # 3. Balanced-object scan. This avoids first-"{" / last-"}" slicing,
    # which fails when providers emit prose before/after the JSON.
    in_string = False
    escaped = False
    depth = 0
    start_index: int | None = None

    for index, char in enumerate(cleaned):
        if in_string:
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue

        if char == "{":
            if depth == 0:
                start_index = index
            depth += 1
            continue

        if char == "}" and depth:
            depth -= 1
            if depth == 0 and start_index is not None:
                candidate = cleaned[start_index:index + 1]
                try:
                    parsed = json.loads(candidate)
                    if isinstance(parsed, dict):
                        return parsed
                except Exception:
                    pass
                start_index = None

    return None


def candidate_prompt(candidate_package: dict[str, Any]) -> str:
    mode = str(candidate_package.get("qualification_mode") or "known-answer")
    discovery_note = """
This is a DISCOVERY COMPARISON. There is no hidden correct answer supplied to you.
Investigate the supplied evidence thoroughly and return every defensible finding relevant to the task.
Do not stop after the first match. Identify conflicts, ambiguity, and missing information.
""" if mode == "discovery" else """
This is a KNOWN-ANSWER qualification test. Determine the result from the supplied evidence.
"""

    ai_rules = candidate_package.get("ai_standard_rules")
    ai_rules = ai_rules if isinstance(ai_rules, dict) else {}
    output_contract = ai_rules.get("output_contract")
    has_contract = isinstance(output_contract, dict) and bool(output_contract)

    if has_contract:
        response_contract = f"""
The ACTIVE AI STANDARD defines the authoritative domain output contract below.
Use these exact domain sections and field names. The values shown are type/examples,
not literal values to copy. Do not collapse unresolved_evidence or conflicts into findings.

ACTIVE STANDARD OUTPUT CONTRACT:
{json.dumps(output_contract, indent=2)}

Wrap those domain sections in one JSON object that may also include:
- test_case_id
- conclusion
- evidence_used
- hypotheses
- confidence
- rule_compliance

The active standard's domain contract overrides any older generic candidate shape.
"""
    else:
        response_contract = """
Return ONE JSON object only, with this structure:
{
  "test_case_id": "...",
  "conclusion": {"status": "resolved|unresolved|partial", "summary": "..."},
  "findings": [
    {
      "marker": "formation/marker name or other discovered item",
      "depth": 0.0,
      "unit": "m",
      "source": "exact evidence filename",
      "location": "page/section/table if determinable",
      "confidence": "High|Medium|Low",
      "notes": "brief supporting or conflicting evidence"
    }
  ],
  "evidence_used": ["exact supplied evidence filename", "..."],
  "hypotheses": [
    {"description": "...", "status": "supported|rejected|unresolved", "reason": "..."}
  ],
  "confidence": 0.0,
  "rule_compliance": true,
  "limitations": ["..."]
}
"""

    return f"""You are being qualified as an AI engine for MultiViewer.

Use ONLY the supplied AI standard, task, and evidence. Do not invent missing evidence.
If the supplied evidence is insufficient, say so explicitly.
{discovery_note}

AI STANDARD AND TEST PACKAGE:
{json.dumps(candidate_package, indent=2)}

{response_contract}

Requirements:
- Inspect the complete supplied evidence relevant to the task, not only the first obvious occurrence.
- Evidence names in evidence_used and findings.source must match supplied evidence filenames where those fields are present.
- Include page/section/table locations when the document permits it.
- Distinguish explicit source facts from inference.
- Respect the active standard's validity rules and classification rules.
- Do not claim to have inspected material that was not supplied.
- Do not expose chain-of-thought. Give concise reasons/evidence only.
"""

def normalize_candidate(provider: str, model: str, text: str, index: int) -> dict[str, Any]:
    parsed = _extract_json_object(text)
    run_id = f"{provider}-{index}"
    if parsed is None:
        return {
            "run_id": run_id,
            "model": {"provider": provider, "model": model},
            "conclusion": {"status": "unresolved", "summary": text.strip()},
            "findings": [],
            "evidence_used": [],
            "hypotheses": [],
            "confidence": 0.0,
            "rule_compliance": False,
            "limitations": ["Provider response was not valid JSON."],
            "parse_error": True,
            "review_required": True,
            "review_reason": "Provider response was not valid candidate JSON.",
            "raw_text": text,
            "parsed_candidate": None,
        }

    parsed_snapshot = json.loads(json.dumps(parsed))
    parsed["run_id"] = run_id
    parsed["model"] = {"provider": provider, "model": model}
    parsed.setdefault("evidence_used", [])
    parsed.setdefault("findings", [])
    parsed.setdefault("unresolved_evidence", [])
    parsed.setdefault("conflicts", [])
    parsed.setdefault("hypotheses", [])
    parsed.setdefault("confidence", 0.0)
    parsed.setdefault("rule_compliance", True)
    parsed.setdefault("limitations", [])
    parsed["parse_error"] = False
    parsed["raw_text"] = text
    parsed["parsed_candidate"] = parsed_snapshot

    findings = parsed.get("findings")
    unresolved = parsed.get("unresolved_evidence")
    conflicts = parsed.get("conflicts")
    finding_count = len(findings) if isinstance(findings, list) else 0
    unresolved_count = len(unresolved) if isinstance(unresolved, list) else 0
    conflict_count = len(conflicts) if isinstance(conflicts, list) else 0
    parsed["unresolved_evidence_count"] = unresolved_count
    parsed["conflict_count"] = conflict_count
    parsed["review_required"] = finding_count == 0
    if bool(parsed.get("provider_response_empty_text")):
        parsed["review_reason"] = "Provider completed but returned no extractable text. Inspect provider response envelope."
    elif finding_count == 0 and (unresolved_count or conflict_count):
        parsed["review_reason"] = (
            f"Provider returned zero findings, with {unresolved_count} unresolved evidence item(s) "
            f"and {conflict_count} conflict item(s)."
        )
    else:
        parsed["review_reason"] = "Provider returned zero parsed findings." if finding_count == 0 else ""
    return parsed


def anonymize_candidates(candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    shuffled = list(candidates)
    random.SystemRandom().shuffle(shuffled)
    anonymous: list[dict[str, Any]] = []
    mapping: dict[str, str] = {}
    for idx, candidate in enumerate(shuffled):
        anonymous_id = f"Candidate {chr(ord('A') + idx)}"
        mapping[anonymous_id] = str(candidate.get("run_id"))
        anonymous.append({
            "candidate_id": anonymous_id,
            "conclusion": candidate.get("conclusion"),
            "findings": candidate.get("findings", []),
            "evidence_used": candidate.get("evidence_used", []),
            "hypotheses": candidate.get("hypotheses", []),
            "confidence": candidate.get("confidence"),
            "rule_compliance": candidate.get("rule_compliance"),
            "limitations": candidate.get("limitations", []),
        })
    return anonymous, mapping


def judge_prompt(
    candidate_package: dict[str, Any],
    answer_key: dict[str, Any],
    anonymous_candidates: list[dict[str, Any]],
) -> str:
    mode = str(candidate_package.get("qualification_mode") or "known-answer")
    if mode == "discovery":
        basis = """There is NO hidden answer key for this discovery comparison.
Independently inspect the same supplied evidence. Judge which candidate found the most complete,
accurate, source-grounded result. Penalize missed relevant findings, invented findings,
weak source locations, failure to recognize conflicts, and premature stopping."""
    else:
        basis = f"""Score against this hidden answer key:
{json.dumps(answer_key, indent=2)}"""

    return f"""You are an independent blinded judge for the MultiViewer AI Qualification Harness.

You are evaluating anonymous candidate outputs. You do NOT know which provider produced them.
Do not infer or reward writing style. You have the same evidence supplied to the candidates.
{basis}

TEST PACKAGE:
{json.dumps(candidate_package, indent=2)}

ANONYMOUS CANDIDATES:
{json.dumps(anonymous_candidates, indent=2)}

Score every candidate from 0-100 on:
- correctness
- evidence_grounding
- thoroughness
- hypothesis_quality
- rule_compliance
- confidence_calibration
- overall

For discovery comparisons, thoroughness means the candidate investigated the evidence deeply enough
to find the defensible relevant items, not merely that its prose is long.
A fabricated source/evidence claim or material rule violation should drive overall toward FAIL-level scoring.

Return ONE JSON object only:
{{
  "scores": [
    {{
      "candidate_id": "Candidate A",
      "correctness": 0,
      "evidence_grounding": 0,
      "thoroughness": 0,
      "hypothesis_quality": 0,
      "rule_compliance": 0,
      "confidence_calibration": 0,
      "overall": 0,
      "reason": "brief evidence-based reason"
    }}
  ],
  "ranking": ["Candidate A", "Candidate B"]
}}

Do not expose chain-of-thought. Give only concise evaluation reasons.
"""

def normalize_judge(provider: str, model: str, text: str, mapping: dict[str, str]) -> dict[str, Any]:
    parsed = _extract_json_object(text)
    if parsed is None:
        return {
            "judge": {"provider": provider, "model": model},
            "scores": [],
            "ranking": [],
            "parse_error": True,
            "raw_text": text,
        }

    normalized_scores: list[dict[str, Any]] = []
    scores = parsed.get("scores", [])
    if isinstance(scores, list):
        for score in scores:
            if not isinstance(score, dict):
                continue
            anonymous_id = str(score.get("candidate_id", ""))
            run_id = mapping.get(anonymous_id)
            if not run_id:
                continue
            item = dict(score)
            item["run_id"] = run_id
            item["candidate_id"] = anonymous_id
            normalized_scores.append(item)

    ranking_run_ids = [
        mapping[item]
        for item in parsed.get("ranking", [])
        if isinstance(item, str) and item in mapping
    ] if isinstance(parsed.get("ranking"), list) else []

    return {
        "judge": {"provider": provider, "model": model},
        "scores": normalized_scores,
        "ranking": ranking_run_ids,
        "parse_error": False,
    }


def aggregate_judges(candidates: list[dict[str, Any]], judges: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = (
        "correctness",
        "evidence_grounding",
        "thoroughness",
        "hypothesis_quality",
        "rule_compliance",
        "confidence_calibration",
        "overall",
    )
    summary: dict[str, Any] = {}
    for candidate in candidates:
        run_id = str(candidate.get("run_id"))
        per_metric: dict[str, list[float]] = {metric: [] for metric in metrics}
        reasons: list[str] = []
        judge_count = 0
        for judge in judges:
            for score in judge.get("scores", []):
                if str(score.get("run_id")) != run_id:
                    continue
                judge_count += 1
                for metric in metrics:
                    value = score.get(metric)
                    if isinstance(value, (int, float)):
                        per_metric[metric].append(float(value))
                reason = score.get("reason")
                if isinstance(reason, str) and reason.strip():
                    reasons.append(reason.strip())
        summary[run_id] = {
            "judge_count": judge_count,
            "metrics": {
                metric: round(sum(values) / len(values), 1) if values else None
                for metric, values in per_metric.items()
            },
            "reasons": reasons,
        }
    return summary


def run_qualification(
    candidate_package: dict[str, Any],
    answer_key: dict[str, Any],
    providers: list[str],
    judges: list[str],
    *,
    evidence_files: list[dict[str, Any]] | None = None,
    progress_callback: Callable[[str, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    evidence_files = evidence_files or []
    candidates: list[dict[str, Any]] = []
    provider_errors: list[dict[str, Any]] = []

    def progress(event: str, **payload: Any) -> None:
        if progress_callback is not None:
            progress_callback(event, payload)

    progress(
        "run_started",
        provider_count=len(providers),
        judge_count=len(judges),
        evidence_count=len(evidence_files),
    )

    try:
        deterministic_enabled = bool(candidate_package.get("deterministic_screening_enabled", True))
        deterministic_profile = candidate_package.get("deterministic_screening_profile")
        evidence_files, preparation_summary = prepare_evidence(
            evidence_files,
            deterministic_enabled=deterministic_enabled,
            deterministic_profile=deterministic_profile if isinstance(deterministic_profile, dict) else {},
        )
    except EvidencePreparationError as exc:
        progress("evidence_preparation_failed", message=str(exc))
        raise

    for summary in preparation_summary:
        progress("evidence_prepared", **summary)

    candidate_timeout = adaptive_timeout_seconds(evidence_files)
    progress(
        "timeout_selected",
        stage="candidate",
        timeout_seconds=candidate_timeout,
        evidence_bytes=sum(
            int(item.get("size") or 0)
            for item in evidence_files
            if isinstance(item, dict)
        ),
    )

    def run_candidate(index: int, provider: str) -> tuple[int, str, dict[str, Any] | None, dict[str, Any] | None]:
        progress("candidate_started", provider=provider, index=index, total=len(providers))
        try:
            text, model = call_provider(
                provider,
                candidate_prompt(candidate_package),
                evidence_files,
                role="candidate",
            )
            candidate = normalize_candidate(provider, model, text, index)
            progress(
                "candidate_completed",
                provider=provider,
                model=model,
                index=index,
                total=len(providers),
                finding_count=len(candidate.get("findings", [])),
                unresolved_evidence_count=int(candidate.get("unresolved_evidence_count") or 0),
                conflict_count=int(candidate.get("conflict_count") or 0),
                review_required=bool(candidate.get("review_required")),
            )
            return index, provider, candidate, None
        except ProviderCallError as exc:
            error = {
                "provider": provider,
                "stage": "candidate",
                "status": exc.status,
                "message": str(exc),
            }
            progress(
                "candidate_failed",
                provider=provider,
                index=index,
                total=len(providers),
                status=exc.status,
                message=str(exc),
            )
            return index, provider, None, error

    with ThreadPoolExecutor(max_workers=max(1, len(providers))) as executor:
        futures = {
            executor.submit(run_candidate, index, provider): (index, provider)
            for index, provider in enumerate(providers, start=1)
        }
        candidate_rows: list[tuple[int, dict[str, Any]]] = []
        for future in as_completed(futures):
            index, _provider, candidate, error = future.result()
            if candidate is not None:
                candidate_rows.append((index, candidate))
            if error is not None:
                provider_errors.append(error)

    candidates = [candidate for _, candidate in sorted(candidate_rows, key=lambda item: item[0])]

    judge_outputs: list[dict[str, Any]] = []
    if candidates and judges:
        progress("judge_stage_started", candidate_count=len(candidates), judge_count=len(judges))
        judge_timeout = adaptive_timeout_seconds(evidence_files)
        progress(
            "timeout_selected",
            stage="judge",
            timeout_seconds=judge_timeout,
            evidence_bytes=sum(
                int(item.get("size") or 0)
                for item in evidence_files
                if isinstance(item, dict)
            ),
        )

        def run_judge(index: int, provider: str) -> tuple[int, dict[str, Any] | None, dict[str, Any] | None]:
            progress("judge_started", provider=provider, index=index, total=len(judges))
            try:
                anonymous, mapping = anonymize_candidates(candidates)
                text, model = call_provider(
                    provider,
                    judge_prompt(candidate_package, answer_key, anonymous),
                    evidence_files,
                    role="judge",
                )
                judge_result = normalize_judge(provider, model, text, mapping)
                progress(
                    "judge_completed",
                    provider=provider,
                    model=model,
                    index=index,
                    total=len(judges),
                    score_count=len(judge_result.get("scores", [])),
                )
                return index, judge_result, None
            except ProviderCallError as exc:
                error = {
                    "provider": provider,
                    "stage": "judge",
                    "status": exc.status,
                    "message": str(exc),
                }
                progress(
                    "judge_failed",
                    provider=provider,
                    index=index,
                    total=len(judges),
                    status=exc.status,
                    message=str(exc),
                )
                return index, None, error

        with ThreadPoolExecutor(max_workers=max(1, len(judges))) as executor:
            futures = {
                executor.submit(run_judge, index, provider): (index, provider)
                for index, provider in enumerate(judges, start=1)
            }
            judge_rows: list[tuple[int, dict[str, Any]]] = []
            for future in as_completed(futures):
                index, judge_result, error = future.result()
                if judge_result is not None:
                    judge_rows.append((index, judge_result))
                if error is not None:
                    provider_errors.append(error)

        judge_outputs = [judge for _, judge in sorted(judge_rows, key=lambda item: item[0])]

    progress(
        "run_completed",
        candidate_count=len(candidates),
        judge_count=len(judge_outputs),
        error_count=len(provider_errors),
    )

    return {
        "schema_version": "multiviewer_ai_qualification_run_v0_1",
        "candidates": candidates,
        "judges": judge_outputs,
        "judge_summary": aggregate_judges(candidates, judge_outputs),
        "errors": provider_errors,
        "provider_status": provider_status(),
        "evidence_preparation": preparation_summary,
        "evidence_files": [
            {"name": item.get("name"), "mime_type": item.get("mime_type"), "size": item.get("size")}
            for item in evidence_files
        ],
    }
