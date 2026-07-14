"""Governed semantic and batch-series evidence for shadow classification.

This module does not own final classification authority. It generates bounded
family candidates from source descriptions and engineering units, then allows
repeated batch structure to strengthen those candidates. Raw source values are
never rewritten and no mnemonic-specific production mappings live here.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Mapping, Sequence

from .contracts import ClassificationCandidate, ClassificationEvidence, CurveClassificationRequest
from .family_registry import CanonicalCurveFamilyRegistry

SEMANTIC_POLICY_VERSION = "classification-semantic-context-v1"


def _tokens(value: str | None) -> tuple[str, ...]:
    text = str(value or "").lower().replace("δ", "delta")
    return tuple(re.findall(r"[a-z0-9]+", text))


def _unit_key(value: str | None) -> str:
    return re.sub(r"[^a-z0-9%]+", "", str(value or "").strip().lower())


_UNIT_GROUPS: Mapping[str, frozenset[str]] = {
    "density": frozenset({"gcc", "gcm3", "kgm3"}),
    "resistivity": frozenset({"ohmm", "ohmmetre", "ohmmeter"}),
    "slowness": frozenset({"usft", "usm"}),
    "temperature": frozenset({"degc", "c", "degf", "f"}),
    "length": frozenset({"in", "inch", "inches", "mm", "cm", "m", "ft"}),
    "porosity": frozenset({"cfcf", "vv", "v/v", "%", "pu"}),
    "weight": frozenset({"t", "tonne", "tonnes", "kg", "lb", "lbf"}),
    "penetration_rate": frozenset({"mh", "mhr", "fth", "fthr", "ftmin"}),
}


@dataclass(frozen=True)
class SemanticFamilyRule:
    rule_id: str
    family_key: str
    family_label: str
    required_phrases: tuple[tuple[str, ...], ...]
    unit_group: str | None
    base_confidence: float
    batch_series: bool = False


@dataclass(frozen=True)
class SemanticResolution:
    candidate: ClassificationCandidate
    rule_id: str
    unit_outcome: str
    batch_series: bool
    policy_version: str = SEMANTIC_POLICY_VERSION


@dataclass(frozen=True)
class BatchSeriesSupport:
    curve_identity: str
    family_key: str
    family_label: str
    member_count: int
    confidence: float
    series_key: str
    evidence: tuple[ClassificationEvidence, ...]


_RULES: tuple[SemanticFamilyRule, ...] = (
    SemanticFamilyRule(
        "azimuthal_bulk_density",
        "density",
        "Density",
        (("azimuthal", "bulk", "density"),),
        "density",
        0.82,
        True,
    ),
    SemanticFamilyRule(
        "resistivity_attenuation_or_phase",
        "resistivity",
        "Resistivity",
        (("resistivity", "attenuation"), ("resistivity", "phase")),
        "resistivity",
        0.82,
        True,
    ),
    SemanticFamilyRule(
        "delta_t_slowness",
        "sonic",
        "Sonic",
        (("delta", "t"), ("slowness",)),
        "slowness",
        0.94,
    ),
    SemanticFamilyRule(
        "downhole_temperature",
        "temperature",
        "Temperature",
        (("downhole", "temperature"), ("temperature",)),
        "temperature",
        0.94,
    ),
    SemanticFamilyRule(
        "weight_on_bit",
        "drilling",
        "Drilling",
        (("weight", "on", "bit"),),
        "weight",
        0.93,
    ),
    SemanticFamilyRule(
        "rate_of_penetration",
        "drilling",
        "Drilling",
        (("rate", "of", "penetration"), ("rop",)),
        "penetration_rate",
        0.93,
    ),
    SemanticFamilyRule(
        "tool_standoff_geometry",
        "borehole_geometry",
        "Borehole Geometry",
        (("standoff",),),
        "length",
        0.91,
    ),
    SemanticFamilyRule(
        "sonic_porosity",
        "sonic",
        "Sonic",
        (("sonic", "porosity"),),
        "porosity",
        0.91,
    ),
)


class DescriptionSemanticResolver:
    """Generate one bounded family candidate from description + unit evidence."""

    def __init__(
        self,
        family_registry: CanonicalCurveFamilyRegistry | None = None,
        rules: Iterable[SemanticFamilyRule] = _RULES,
    ) -> None:
        self._registry = family_registry or CanonicalCurveFamilyRegistry.default()
        self._rules = tuple(rules)

    @staticmethod
    def _phrase_matches(tokens: set[str], phrase: tuple[str, ...]) -> bool:
        return all(term in tokens for term in phrase)

    @staticmethod
    def _unit_outcome(unit: str | None, unit_group: str | None) -> str:
        if unit_group is None:
            return "not_required"
        if not unit:
            return "missing_source_unit"
        key = _unit_key(unit)
        return "compatible" if key in _UNIT_GROUPS[unit_group] else "incompatible"

    def resolve(self, request: CurveClassificationRequest) -> SemanticResolution | None:
        tokens = set(_tokens(request.description))
        if not tokens:
            return None

        matches: list[SemanticResolution] = []
        for rule in self._rules:
            if not any(self._phrase_matches(tokens, phrase) for phrase in rule.required_phrases):
                continue
            family = self._registry.resolve(rule.family_key)
            if family is None:
                continue
            unit_outcome = self._unit_outcome(request.unit, rule.unit_group)
            if unit_outcome == "incompatible":
                continue
            confidence = rule.base_confidence if unit_outcome == "compatible" else min(rule.base_confidence, 0.72)
            evidence = (
                ClassificationEvidence(
                    "description_semantics",
                    "DescriptionSemanticResolver",
                    f"rule={rule.rule_id}; description={request.description!r}",
                    rule.base_confidence,
                ),
                ClassificationEvidence(
                    "engineering_unit",
                    "DescriptionSemanticResolver",
                    f"unit={request.unit!r}; unit_group={rule.unit_group}; outcome={unit_outcome}",
                    1.0 if unit_outcome == "compatible" else 0.5,
                ),
            )
            matches.append(SemanticResolution(
                ClassificationCandidate(
                    family.family_key,
                    family.display_label,
                    confidence,
                    evidence,
                ),
                rule.rule_id,
                unit_outcome,
                rule.batch_series,
            ))

        if not matches:
            return None
        matches.sort(key=lambda item: item.candidate.confidence, reverse=True)
        if len(matches) > 1 and matches[0].candidate.curve_family_key != matches[1].candidate.curve_family_key:
            return None
        return matches[0]


class BatchSeriesContextResolver:
    """Strengthen repeated semantic candidates without overriding conflicts."""

    _VOLATILE_TERMS = frozenset({
        "sector", "quadrant", "up", "down", "left", "right", "corrected",
        "mhz", "khz", "memory", "standard", "resolution",
    })

    @staticmethod
    def _curve_identity(request: CurveClassificationRequest, ordinal: int) -> str:
        return str(request.curve_id or request.channel_id or request.source_curve_index or f"ordinal:{ordinal}")

    @classmethod
    def _series_key(cls, request: CurveClassificationRequest, family_key: str) -> str:
        terms = []
        for token in _tokens(request.description):
            if token in cls._VOLATILE_TERMS or token.isdigit():
                continue
            if re.fullmatch(r"\d+(?:mhz|khz|ft|in)?", token):
                continue
            terms.append(token)
        stem = "_".join(terms[:8])
        return "|".join((
            str(request.source_uid or request.source_checksum or request.source_kind or "source"),
            str(request.logical_file_id or "logical"),
            str(request.frame_id or "frame"),
            family_key,
            stem,
        ))

    def resolve_batch(
        self,
        requests: Sequence[CurveClassificationRequest],
        semantic_resolver: DescriptionSemanticResolver,
    ) -> Mapping[str, BatchSeriesSupport]:
        provisional: list[tuple[int, CurveClassificationRequest, SemanticResolution, str]] = []
        for ordinal, request in enumerate(requests):
            semantic = semantic_resolver.resolve(request)
            if semantic is None or not semantic.batch_series or semantic.unit_outcome != "compatible":
                continue
            key = self._series_key(request, semantic.candidate.curve_family_key)
            provisional.append((ordinal, request, semantic, key))

        groups: dict[str, list[tuple[int, CurveClassificationRequest, SemanticResolution, str]]] = {}
        for item in provisional:
            groups.setdefault(item[3], []).append(item)

        output: dict[str, BatchSeriesSupport] = {}
        for key, members in groups.items():
            if len(members) < 2:
                continue
            family_keys = {m[2].candidate.curve_family_key for m in members}
            if len(family_keys) != 1:
                continue
            confidence = min(0.96, max(m[2].candidate.confidence for m in members) + 0.12)
            for ordinal, request, semantic, _ in members:
                identity = self._curve_identity(request, ordinal)
                output[identity] = BatchSeriesSupport(
                    identity,
                    semantic.candidate.curve_family_key,
                    semantic.candidate.curve_family_label,
                    len(members),
                    confidence,
                    key,
                    (
                        ClassificationEvidence(
                            "batch_series_context",
                            "BatchSeriesContextResolver",
                            f"series_key={key}; member_count={len(members)}",
                            confidence,
                        ),
                    ),
                )
        return output
