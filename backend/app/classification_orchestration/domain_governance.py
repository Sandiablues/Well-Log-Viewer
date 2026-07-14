"""Backend-owned measurement-domain and destination governance.

This layer answers two questions independently from curve-family classification:
1. What measurement domain does this source channel belong to?
2. Which application destination owns that domain?

It never invents a curve family and never makes the frontend infer placement.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from .contracts import CurveClassificationDecision, CurveClassificationRequest

ONTOLOGY_POLICY_VERSION = "measurement-domain-ontology-v1"


def _tokens(value: object) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", str(value or "").lower()))


@dataclass(frozen=True)
class MeasurementDomain:
    domain_key: str
    display_label: str


@dataclass(frozen=True)
class DestinationPolicy:
    destination_key: str
    display_in_wdv: bool
    owner: str


@dataclass(frozen=True)
class DomainPlacementDecision:
    measurement_domain_key: str
    measurement_domain_label: str
    destination_key: str
    destination_owner: str
    display_in_wdv: bool
    status: str
    confidence: float
    decision_source: str
    evidence: tuple[str, ...]
    ontology_version: str = ONTOLOGY_POLICY_VERSION

    def as_dict(self) -> dict:
        return {
            "measurement_domain_key": self.measurement_domain_key,
            "measurement_domain_label": self.measurement_domain_label,
            "destination_key": self.destination_key,
            "destination_owner": self.destination_owner,
            "display_in_wdv": self.display_in_wdv,
            "status": self.status,
            "confidence": self.confidence,
            "decision_source": self.decision_source,
            "evidence": list(self.evidence),
            "ontology_version": self.ontology_version,
        }


class MeasurementDomainRegistry:
    def __init__(self) -> None:
        self._domains = {
            "petrophysical_log": MeasurementDomain("petrophysical_log", "Petrophysical Log"),
            "directional_survey": MeasurementDomain("directional_survey", "Directional Survey"),
            "drilling_operational": MeasurementDomain("drilling_operational", "Drilling / Operational"),
            "tool_acquisition": MeasurementDomain("tool_acquisition", "Tool / Acquisition"),
            "unknown": MeasurementDomain("unknown", "Unknown"),
        }

    def get(self, key: str) -> MeasurementDomain:
        return self._domains.get(key, self._domains["unknown"])


class DestinationPolicyRegistry:
    def __init__(self) -> None:
        self._policies = {
            "petrophysical_log": DestinationPolicy("wdv", True, "WDV"),
            "directional_survey": DestinationPolicy("survey_workflow", False, "Survey/WBV"),
            "drilling_operational": DestinationPolicy("wdv_or_operations", True, "WDV/Operations"),
            "tool_acquisition": DestinationPolicy("acquisition_qaqc", False, "Acquisition/QAQC"),
            "unknown": DestinationPolicy("review", False, "Review"),
        }

    def for_domain(self, domain_key: str) -> DestinationPolicy:
        return self._policies.get(domain_key, self._policies["unknown"])


class MeasurementDomainResolver:
    """Resolve domain ownership from governed family or source semantics."""

    _DIRECTIONAL_PHRASES = (
        ("east", "departure"),
        ("north", "departure"),
        ("hole", "azimuth"),
        ("hole", "deviation"),
        ("sonde", "deviation"),
        ("relative", "bearing"),
    )
    _TOOL_ACQUISITION_PHRASES = (
        ("pad", "azimuth"),
        ("downhole", "force"),
        ("cable", "tension"),
        ("stuck", "tool", "indicator"),
        ("tool", "orientation"),
        ("tool", "status"),
    )

    def __init__(
        self,
        domains: MeasurementDomainRegistry | None = None,
        destinations: DestinationPolicyRegistry | None = None,
    ) -> None:
        self._domains = domains or MeasurementDomainRegistry()
        self._destinations = destinations or DestinationPolicyRegistry()

    @staticmethod
    def _phrase_match(tokens: set[str], phrase: tuple[str, ...]) -> bool:
        return all(term in tokens for term in phrase)

    def _decision(self, domain_key: str, confidence: float, source: str, evidence: tuple[str, ...]) -> DomainPlacementDecision:
        domain = self._domains.get(domain_key)
        destination = self._destinations.for_domain(domain.domain_key)
        return DomainPlacementDecision(
            domain.domain_key,
            domain.display_label,
            destination.destination_key,
            destination.owner,
            destination.display_in_wdv,
            "resolved" if domain.domain_key != "unknown" else "requires_review",
            confidence,
            source,
            evidence,
        )

    def resolve(
        self,
        request: CurveClassificationRequest,
        curve_decision: CurveClassificationDecision | None = None,
    ) -> DomainPlacementDecision:
        # A resolved canonical curve family is the strongest domain-placement
        # evidence. Family classification itself is not changed here.
        curve_resolved = bool(
            curve_decision
            and getattr(curve_decision, "curve_family_key", "unclassified") != "unclassified"
            and not bool(getattr(curve_decision, "review_required", True))
            and (
                bool(getattr(curve_decision, "resolved", False))
                or getattr(curve_decision, "classification_status", "") == "resolved"
            )
        )
        if curve_resolved:
            if curve_decision.curve_family_key == "drilling":
                return self._decision(
                    "drilling_operational",
                    max(0.90, curve_decision.confidence),
                    "governed_curve_family_domain",
                    (f"curve_family={curve_decision.curve_family_key}",),
                )
            return self._decision(
                "petrophysical_log",
                max(0.90, curve_decision.confidence),
                "governed_curve_family_domain",
                (f"curve_family={curve_decision.curve_family_key}",),
            )

        tokens = _tokens(request.description)
        if any(self._phrase_match(tokens, phrase) for phrase in self._DIRECTIONAL_PHRASES):
            return self._decision(
                "directional_survey",
                0.94,
                "governed_description_domain",
                (f"description={request.description!r}", "directional-survey semantic policy"),
            )
        if any(self._phrase_match(tokens, phrase) for phrase in self._TOOL_ACQUISITION_PHRASES):
            return self._decision(
                "tool_acquisition",
                0.92,
                "governed_description_domain",
                (f"description={request.description!r}", "tool/acquisition semantic policy"),
            )
        return self._decision(
            "unknown",
            0.0,
            "domain_unresolved",
            (f"description={request.description!r}",),
        )
