"""Governed tool/frame/channel context evidence for shadow classification.

This module is deliberately generic:
- it does not contain mnemonic-specific mappings;
- it never invents a curve family;
- it can only propose families already present in the canonical registry;
- a resolved context candidate requires at least two independent signals;
- peer context cannot override a hard unit conflict.

Context signals are derived from source descriptions, acquisition-domain terms,
tool/frame/channel metadata when supplied, and already-resolved peers in the
same source/logical-file/frame scope.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Mapping, Sequence

from .contracts import (
    ClassificationCandidate,
    ClassificationEvidence,
    CurveClassificationRequest,
)
from .family_registry import CanonicalCurveFamilyRegistry

CONTEXT_POLICY_VERSION = "classification-tool-frame-channel-context-v1"


def _tokens(value: object) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", str(value or "").lower()))


def _context_key(request: CurveClassificationRequest) -> tuple[str, str, str]:
    source = str(
        request.source_uid
        or request.source_checksum
        or request.context.get("source_file")
        or request.source_kind
        or "source"
    )
    logical = str(request.logical_file_id or request.context.get("logical_file_id") or "logical")
    frame = str(request.frame_id or request.context.get("frame_id") or "frame")
    return source, logical, frame


@dataclass(frozen=True)
class ContextDomainRule:
    rule_id: str
    family_key: str
    family_label: str
    any_phrases: tuple[tuple[str, ...], ...]
    measurement_terms: tuple[str, ...] = ()
    tool_terms: tuple[str, ...] = ()
    minimum_peer_support: int = 1
    base_confidence: float = 0.88


@dataclass(frozen=True)
class ContextSupport:
    curve_identity: str
    family_key: str
    family_label: str
    confidence: float
    rule_id: str
    signal_count: int
    peer_support: int
    context_key: tuple[str, str, str]
    evidence: tuple[ClassificationEvidence, ...]
    policy_version: str = CONTEXT_POLICY_VERSION


_RULES: tuple[ContextDomainRule, ...] = (
    ContextDomainRule(
        "acoustic_wave_processing",
        "sonic",
        "Sonic",
        (
            ("compressional",),
            ("shear", "velocity"),
            ("peak", "coherence"),
            ("semblance",),
            ("transit", "time"),
            ("travel", "time"),
            ("poisson", "ratio"),
            ("velocity", "ratio"),
        ),
        measurement_terms=("compressional", "shear", "coherence", "semblance", "transit", "velocity", "poisson"),
        tool_terms=("monopole", "dipole", "receiver", "transmitter", "acoustic", "sonic"),
        base_confidence=0.91,
    ),
    ContextDomainRule(
        "magnetic_resonance_measurement",
        "nmr",
        "NMR",
        (
            ("magnetic", "resonance"),
            ("mr", "bulk", "volume"),
            ("mean", "t2"),
            ("t2",),
            ("cbw", "cutoff"),
        ),
        measurement_terms=("resonance", "t2", "cbw", "irreducible"),
        tool_terms=("magtrak", "nmr", "mr"),
        base_confidence=0.92,
    ),
    ContextDomainRule(
        "neutron_counting_measurement",
        "neutron_porosity",
        "Neutron Porosity",
        (
            ("thermal", "count", "rate"),
            ("neutron", "count", "rate"),
        ),
        measurement_terms=("thermal", "count", "rate", "neutron"),
        tool_terms=("neutron", "thermal"),
        base_confidence=0.91,
    ),
    ContextDomainRule(
        "drilling_mechanical_measurement",
        "drilling",
        "Drilling",
        (
            ("collar", "rotational", "speed"),
            ("rotational", "speed"),
        ),
        measurement_terms=("collar", "rotational", "speed"),
        tool_terms=("drilling", "collar"),
        base_confidence=0.90,
    ),
)


class ToolFrameChannelContextResolver:
    """Resolve bounded family support from acquisition context plus peer evidence."""

    def __init__(
        self,
        family_registry: CanonicalCurveFamilyRegistry | None = None,
        rules: Iterable[ContextDomainRule] = _RULES,
    ) -> None:
        self._registry = family_registry or CanonicalCurveFamilyRegistry.default()
        self._rules = tuple(rules)

    @staticmethod
    def _identity(request: CurveClassificationRequest, ordinal: int) -> str:
        return str(
            request.curve_id
            or request.channel_id
            or request.source_curve_index
            or f"ordinal:{ordinal}"
        )

    @staticmethod
    def _phrase_match(tokens: set[str], phrase: tuple[str, ...]) -> bool:
        return all(term in tokens for term in phrase)

    def resolve_batch(
        self,
        requests: Sequence[CurveClassificationRequest],
        resolved_peer_families: Mapping[str, str],
    ) -> Mapping[str, ContextSupport]:
        peer_counts: dict[tuple[str, str, str], dict[str, int]] = {}
        identity_to_request: dict[str, CurveClassificationRequest] = {}

        for ordinal, request in enumerate(requests):
            identity = self._identity(request, ordinal)
            identity_to_request[identity] = request
            family_key = resolved_peer_families.get(identity)
            if not family_key or family_key == "unclassified":
                continue
            key = _context_key(request)
            peer_counts.setdefault(key, {})
            peer_counts[key][family_key] = peer_counts[key].get(family_key, 0) + 1

        output: dict[str, ContextSupport] = {}
        for ordinal, request in enumerate(requests):
            identity = self._identity(request, ordinal)
            if identity in resolved_peer_families and resolved_peer_families[identity] != "unclassified":
                continue

            description_tokens = _tokens(request.description)
            tool_tokens = _tokens(request.tool_name)
            for key, value in request.context.items():
                if key in {"tool_name", "tool", "channel_type", "acquisition_method", "service_name"}:
                    tool_tokens.update(_tokens(value))

            key = _context_key(request)
            matches: list[ContextSupport] = []
            for rule in self._rules:
                family = self._registry.resolve(rule.family_key)
                if family is None:
                    continue

                description_match = any(
                    self._phrase_match(description_tokens, phrase)
                    for phrase in rule.any_phrases
                )
                measurement_match = bool(description_tokens.intersection(rule.measurement_terms))
                tool_match = bool(tool_tokens.intersection(rule.tool_terms))
                peer_support = peer_counts.get(key, {}).get(family.family_key, 0)

                signals = []
                evidence = []
                if description_match:
                    signals.append("description_domain")
                    evidence.append(ClassificationEvidence(
                        "description_domain",
                        "ToolFrameChannelContextResolver",
                        f"rule={rule.rule_id}; description={request.description!r}",
                        rule.base_confidence,
                    ))
                if measurement_match and not description_match:
                    signals.append("measurement_terms")
                    evidence.append(ClassificationEvidence(
                        "measurement_terms",
                        "ToolFrameChannelContextResolver",
                        f"rule={rule.rule_id}; matched governed measurement-domain terms",
                        0.72,
                    ))
                if tool_match:
                    signals.append("tool_channel_context")
                    evidence.append(ClassificationEvidence(
                        "tool_channel_context",
                        "ToolFrameChannelContextResolver",
                        f"rule={rule.rule_id}; tool/context metadata supported family",
                        0.82,
                    ))
                if peer_support >= rule.minimum_peer_support:
                    signals.append("resolved_peer_context")
                    evidence.append(ClassificationEvidence(
                        "resolved_peer_context",
                        "ToolFrameChannelContextResolver",
                        f"context={key}; family={family.family_key}; resolved_peer_count={peer_support}",
                        min(0.95, 0.70 + min(peer_support, 10) * 0.025),
                    ))

                # Require two independent signals. A description-domain match and
                # a peer-context match are independent; tool metadata can replace
                # peer support when actual tool/channel metadata is available.
                if len(set(signals)) < 2:
                    continue

                confidence = min(
                    0.96,
                    rule.base_confidence
                    + (0.03 if peer_support >= 2 else 0.0)
                    + (0.02 if tool_match else 0.0),
                )
                matches.append(ContextSupport(
                    identity,
                    family.family_key,
                    family.display_label,
                    confidence,
                    rule.rule_id,
                    len(set(signals)),
                    peer_support,
                    key,
                    tuple(evidence),
                ))

            if not matches:
                continue
            matches.sort(key=lambda item: (item.confidence, item.signal_count, item.peer_support), reverse=True)
            if len(matches) > 1 and matches[0].family_key != matches[1].family_key and matches[0].confidence == matches[1].confidence:
                continue
            output[identity] = matches[0]

        return output
