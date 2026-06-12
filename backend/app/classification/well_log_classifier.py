"""Deterministic well-log curve classifier.

The classifier is deliberately simple and evidence-based.  It does not try to
infer commercial interpretations; it maps curve/file metadata into backend-owned
WMDP product groups and curve families with confidence and reasons.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .well_log_vocabulary import (
    CASED_HOLE_CONTEXT_TERMS,
    CASED_HOLE_CURVE_FAMILIES,
    COMPLETION_INTEGRITY_FAMILIES,
    LITHOLOGY_CORE_MARKER_FAMILIES,
    OPEN_HOLE_CONTEXT_TERMS,
    OPEN_HOLE_CURVE_FAMILIES,
    PRESSURE_PRODUCTION_FLUID_FAMILIES,
    open_hole_subgroup_for_family,
)


@dataclass(frozen=True)
class WellLogClassification:
    product_category: str
    curve_family: str
    product_subgroup_key: str | None
    product_subgroup_label: str | None
    curve_description: str
    curve_unit: str | None
    classification_confidence: str
    classification_source: str
    classification_reasons: list[str] = field(default_factory=list)
    review_required: bool = False


def _clean(value: str | None) -> str:
    return (value or "").strip()


def _mnemonic_key(value: str | None) -> str:
    return _clean(value).upper()


def _joined_context(values: Iterable[str | None]) -> str:
    return " ".join(_clean(value).lower() for value in values if _clean(value))


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    return any(term in text for term in terms)


def _fallback_description(mnemonic: str, description: str | None) -> str:
    return _clean(description) or mnemonic or "Unclassified curve"


def classify_well_log_curve(
    *,
    mnemonic: str | None,
    description: str | None = None,
    unit: str | None = None,
    context_terms: Iterable[str | None] = (),
) -> WellLogClassification:
    """Classify one curve into a WMDP product group and family.

    Mnemonic alone is not always enough.  Ambiguous curves such as GR are kept
    open-hole only when no cased-hole context is present.  Cased-hole context
    wins over open-hole aliases where the evidence conflicts.
    """

    key = _mnemonic_key(mnemonic)
    cleaned_description = _clean(description)
    cleaned_unit = _clean(unit) or None
    context = _joined_context([description, unit, *context_terms])

    reasons: list[str] = []
    if key:
        reasons.append(f"Mnemonic {key} evaluated.")
    if cleaned_description:
        reasons.append("Curve description was available.")
    if cleaned_unit:
        reasons.append(f"Curve unit {cleaned_unit} was available.")

    has_cased_context = _contains_any(context, CASED_HOLE_CONTEXT_TERMS)
    has_open_context = _contains_any(context, OPEN_HOLE_CONTEXT_TERMS)

    if has_cased_context:
        reasons.append("Cased-hole context term detected.")
    if has_open_context:
        reasons.append("Open-hole context term detected.")

    if key in LITHOLOGY_CORE_MARKER_FAMILIES:
        family, default_description = LITHOLOGY_CORE_MARKER_FAMILIES[key]
        return WellLogClassification(
            product_category="lithology_core_markers",
            curve_family=family,
            product_subgroup_key=None,
            product_subgroup_label=None,
            curve_description=cleaned_description or default_description,
            curve_unit=cleaned_unit,
            classification_confidence="high",
            classification_source="backend_well_log_classifier",
            classification_reasons=[*reasons, f"Mnemonic {key} matched Lithology / Core / Markers vocabulary."],
            review_required=False,
        )

    if key in PRESSURE_PRODUCTION_FLUID_FAMILIES:
        family, default_description = PRESSURE_PRODUCTION_FLUID_FAMILIES[key]
        return WellLogClassification(
            product_category="pressure_production_fluid_data",
            curve_family=family,
            product_subgroup_key=None,
            product_subgroup_label=None,
            curve_description=cleaned_description or default_description,
            curve_unit=cleaned_unit,
            classification_confidence="high",
            classification_source="backend_well_log_classifier",
            classification_reasons=[*reasons, f"Mnemonic {key} matched Pressure / Production / Fluid vocabulary."],
            review_required=False,
        )

    if key in COMPLETION_INTEGRITY_FAMILIES:
        family, default_description = COMPLETION_INTEGRITY_FAMILIES[key]
        return WellLogClassification(
            product_category="completion_integrity_data",
            curve_family=family,
            product_subgroup_key=None,
            product_subgroup_label=None,
            curve_description=cleaned_description or default_description,
            curve_unit=cleaned_unit,
            classification_confidence="high",
            classification_source="backend_well_log_classifier",
            classification_reasons=[*reasons, f"Mnemonic {key} matched Completion / Integrity vocabulary."],
            review_required=False,
        )

    if key in CASED_HOLE_CURVE_FAMILIES or has_cased_context:
        family, default_description = CASED_HOLE_CURVE_FAMILIES.get(key, ("Cased-Hole Log", _fallback_description(key, cleaned_description)))
        confidence = "high" if key in CASED_HOLE_CURVE_FAMILIES else "medium"
        return WellLogClassification(
            product_category="cased_hole_logs",
            curve_family=family,
            product_subgroup_key=None,
            product_subgroup_label=None,
            curve_description=cleaned_description or default_description,
            curve_unit=cleaned_unit,
            classification_confidence=confidence,
            classification_source="backend_well_log_classifier",
            classification_reasons=[*reasons, "Cased-hole classification rule matched."],
            review_required=False,
        )

    if key in OPEN_HOLE_CURVE_FAMILIES:
        family, default_description = OPEN_HOLE_CURVE_FAMILIES[key]
        subgroup = open_hole_subgroup_for_family(family)
        confidence = "high" if has_open_context or cleaned_unit or key not in {"GR", "CGR", "SGR"} else "medium"
        return WellLogClassification(
            product_category="open_hole_logs",
            curve_family=family,
            product_subgroup_key=subgroup.subgroup_key,
            product_subgroup_label=subgroup.subgroup_label,
            curve_description=cleaned_description or default_description,
            curve_unit=cleaned_unit,
            classification_confidence=confidence,
            classification_source="backend_well_log_classifier",
            classification_reasons=[*reasons, f"Mnemonic {key} matched Open hole logs vocabulary."],
            review_required=False,
        )

    return WellLogClassification(
        product_category="other_review_required",
        curve_family="Unclassified",
        product_subgroup_key=None,
        product_subgroup_label=None,
        curve_description=_fallback_description(key, cleaned_description),
        curve_unit=cleaned_unit,
        classification_confidence="low",
        classification_source="backend_well_log_classifier",
        classification_reasons=[*reasons, "No deterministic curve-family rule matched."],
        review_required=True,
    )
