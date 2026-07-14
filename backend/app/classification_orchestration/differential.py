"""Deterministic legacy-vs-shadow differential reporting."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import CurveClassificationDecision


@dataclass(frozen=True)
class ClassificationDifferential:
    agreement: bool
    classification: str
    material_fields: tuple[str, ...]
    legacy: CurveClassificationDecision
    shadow: CurveClassificationDecision

    def as_dict(self) -> dict[str, Any]:
        return {
            "agreement": self.agreement,
            "classification": self.classification,
            "material_fields": list(self.material_fields),
            "legacy": self.legacy.as_dict(),
            "shadow": self.shadow.as_dict(),
        }


def compare_classifications(
    legacy: CurveClassificationDecision,
    shadow: CurveClassificationDecision,
) -> ClassificationDifferential:
    fields: list[str] = []
    if legacy.curve_family_key != shadow.curve_family_key:
        fields.append("curve_family_key")
    if legacy.review_required != shadow.review_required:
        fields.append("review_required")
    if legacy.classification_status != shadow.classification_status:
        fields.append("classification_status")

    agreement = not fields
    if agreement:
        classification = "agreement"
    elif legacy.curve_family_key == "unclassified" and shadow.curve_family_key != "unclassified":
        classification = "newly_classified"
    elif legacy.curve_family_key != "unclassified" and shadow.curve_family_key == "unclassified":
        classification = "newly_unclassified"
    elif "curve_family_key" in fields:
        classification = "material_conflict"
    else:
        classification = "contract_difference"

    return ClassificationDifferential(
        agreement=agreement,
        classification=classification,
        material_fields=tuple(fields),
        legacy=legacy,
        shadow=shadow,
    )
