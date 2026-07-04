"""Deterministic contextual curve resolution from approved KR evidence.

Exact canonical and alias resolution remains the responsibility of the runtime
classification service.  This module is only a conservative fallback when
mnemonic identity is insufficient.  It derives broad classification from
approved curve definitions using description semantics and compatible units.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable
from collections import Counter

from .managed_models import CurveDefinitionRecord


@dataclass(frozen=True)
class ContextualResolution:
    display_name: str
    family: str
    product_group: str
    product_subgroup: str | None
    default_unit: str | None
    confidence: float
    supporting_record_ids: tuple[str, ...]
    canonical_curve_id: str | None = None
    knowledge_record_id: str | None = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class _EvidencePolicy:
    unit_family: str
    required_all: frozenset[str] = frozenset()
    required_any: frozenset[str] = frozenset()
    ignored_query_terms: frozenset[str] = frozenset()


_EVIDENCE_POLICIES = (
    _EvidencePolicy("resistivity", required_all=frozenset({"resistivity"}), required_any=frozenset({"deep", "medium", "shallow"})),
    _EvidencePolicy("density", required_all=frozenset({"density", "correction"})),
    _EvidencePolicy("porosity", required_all=frozenset({"neutron"})),
    _EvidencePolicy("slowness", required_any=frozenset({"compressional", "shear"}), ignored_query_terms=frozenset({"multifrequency", "sonic"})),
)

# Explicit governed fallback where no approved curve definition exists.  This
# is a measurement policy, not a mnemonic alias: description and unit are both
# required and no canonical identity is fabricated.
_GOVERNED_FALLBACKS = (
    {
        "unit_family": "penetration_rate",
        "required_all": frozenset({"rate", "penetration"}),
        "display_name": "Rate of Penetration",
        "family": "Drilling",
        "product_group": "open_hole_logs",
        "product_subgroup": "drilling_derived",
        "default_unit": "m/h",
        "policy_id": "backend_policy:measurement:rate_of_penetration:v1",
    },
)


def resolve_contextual_curve(
    *,
    source_mnemonic: str,
    description: str | None,
    unit: str | None,
    curve_definitions: Iterable[CurveDefinitionRecord],
) -> ContextualResolution | None:
    del source_mnemonic  # contextual resolution must not become a hidden alias table
    description_text = _normalize_text(description)
    query_tokens = frozenset(_tokens(description))
    unit_family = _normalize_unit(unit)
    if not description_text or not unit_family:
        return None

    policy = next((item for item in _EVIDENCE_POLICIES if item.unit_family == unit_family), None)
    if policy is not None and _query_satisfies_policy(query_tokens, policy):
        semantic_tokens = query_tokens - policy.ignored_query_terms
        scored = [
            (record, _record_match_score(record, semantic_tokens, policy))
            for record in curve_definitions
            if _normalize_unit(record.default_unit) == unit_family
        ]
        scored = [(record, score) for record, score in scored if score is not None]
        best_score = max((score for _, score in scored), default=None)
        candidates = [record for record, score in scored if score == best_score]
        resolution = _consensus_resolution(
            description_text=description_text,
            original_description=_clean(description),
            original_unit=_clean(unit),
            candidates=candidates,
        )
        if resolution is not None:
            return resolution

    return _governed_fallback(query_tokens, unit_family, unit)


def _query_satisfies_policy(tokens: frozenset[str], policy: _EvidencePolicy) -> bool:
    if not policy.required_all.issubset(tokens):
        return False
    return not policy.required_any or bool(tokens & policy.required_any)


def _record_match_score(
    record: CurveDefinitionRecord,
    semantic_tokens: frozenset[str],
    policy: _EvidencePolicy,
) -> int | None:
    display_tokens = frozenset(_tokens(record.display_name))
    evidence_tokens = display_tokens | frozenset(_tokens(record.description))
    if not policy.required_all.issubset(evidence_tokens):
        return None
    selected_any = semantic_tokens & policy.required_any
    if selected_any and not selected_any.issubset(display_tokens):
        return None
    governed_vocabulary = policy.required_all | policy.required_any | {"slowness", "correction", "porosity"}
    required_query_terms = semantic_tokens & governed_vocabulary
    if not required_query_terms.issubset(evidence_tokens):
        return None
    # Display-name agreement is stronger than free-text description agreement.
    return 3 * len(semantic_tokens & display_tokens) + len(semantic_tokens & evidence_tokens)


def _consensus_resolution(
    *,
    description_text: str,
    original_description: str,
    original_unit: str,
    candidates: list[CurveDefinitionRecord],
) -> ContextualResolution | None:
    if not candidates:
        return None

    groups = {(_clean(record.product_group), _clean(record.product_subgroup) or None) for record in candidates}
    if len(groups) != 1:
        return None
    product_group, product_subgroup = next(iter(groups))
    family_counts = Counter(_family_key(record.family) for record in candidates if _clean(record.family))
    if not family_counts:
        return None
    family_key, family_count = family_counts.most_common(1)[0]
    if family_count / len(candidates) < 0.75:
        return None
    family_values = [record.family for record in candidates if _family_key(record.family) == family_key]
    family = Counter(family_values).most_common(1)[0][0]
    if not product_group:
        return None

    exact = [record for record in candidates if _normalize_text(record.display_name) == description_text]
    exact_canonical_ids = {record.canonical_curve_id for record in exact if record.canonical_curve_id}
    canonical_curve_id = None
    knowledge_record_id = None
    display_name = original_description
    if len(exact_canonical_ids) == 1:
        canonical_curve_id = next(iter(exact_canonical_ids))
        chosen = min((record for record in exact if record.canonical_curve_id == canonical_curve_id), key=lambda r: r.record_id)
        knowledge_record_id = chosen.record_id
        display_name = chosen.display_name

    approved_units = {_clean(record.default_unit) for record in candidates if _clean(record.default_unit)}
    default_unit = next(iter(approved_units)) if len(approved_units) == 1 else (original_unit or None)
    record_ids = tuple(sorted({record.record_id for record in candidates}))
    unique = canonical_curve_id is not None
    return ContextualResolution(
        display_name=display_name,
        family=family,
        product_group=product_group,
        product_subgroup=product_subgroup,
        default_unit=default_unit,
        confidence=0.94 if unique else 0.90,
        supporting_record_ids=record_ids,
        canonical_curve_id=canonical_curve_id,
        knowledge_record_id=knowledge_record_id,
        warnings=((
            "Approved KR contextual evidence resolved one exact canonical curve."
            if unique
            else "Approved KR contextual evidence reached broad classification consensus; no canonical curve was assigned."
        ),),
    )


def _governed_fallback(tokens: frozenset[str], unit_family: str, unit: str | None) -> ContextualResolution | None:
    for policy in _GOVERNED_FALLBACKS:
        if unit_family != policy["unit_family"]:
            continue
        if not policy["required_all"].issubset(tokens):
            continue
        return ContextualResolution(
            display_name=str(policy["display_name"]),
            family=str(policy["family"]),
            product_group=str(policy["product_group"]),
            product_subgroup=str(policy["product_subgroup"]),
            default_unit=_clean(unit) or str(policy["default_unit"]),
            confidence=0.90,
            supporting_record_ids=(str(policy["policy_id"]),),
            warnings=(
                "Resolved by an explicit governed backend measurement policy; no approved canonical KR definition was assigned.",
            ),
        )
    return None


def _family_key(value: str | None) -> str:
    return " ".join(_tokens(_clean(value).replace("_", " ")))


def _normalize_unit(value: str | None) -> str:
    text = _clean(value).lower().replace(" ", "")
    aliases = {
        "ohm.m": "resistivity", "ohmm": "resistivity", "ohm-m": "resistivity", "ohm_m": "resistivity", "ohmmeter": "resistivity",
        "g/cm3": "density", "g/cc": "density", "g/c3": "density", "gm/cc": "density",
        "v/v": "porosity", "%": "porosity", "pu": "porosity", "fraction": "porosity",
        "us/ft": "slowness", "µs/ft": "slowness", "μs/ft": "slowness", "usec/ft": "slowness", "us/f": "slowness",
        "m/h": "penetration_rate", "m/hr": "penetration_rate", "ft/h": "penetration_rate", "ft/hr": "penetration_rate",
    }
    return aliases.get(text, text)


def _tokens(value: str | None) -> tuple[str, ...]:
    return tuple(re.findall(r"[a-z0-9]+", _clean(value).lower()))


def _normalize_text(value: str | None) -> str:
    return " ".join(_tokens(value))


def _clean(value: object) -> str:
    return str(value or "").strip()
