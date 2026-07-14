"""Cross-stage classification parity contract for cutover preparation.

The frontend remains a renderer.  Backend stages may carry additional metadata,
but the classification identity projected to Quick View, WSI, MWD and WDV must
not drift.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Any

from .unified_result import UnifiedCurveClassificationResult


STAGE_ORDER = ("quick_view", "wsi", "mwd", "wdv")


@dataclass(frozen=True)
class ClassificationParityProjection:
    curve_identity: str
    curve_family_key: str | None
    curve_family_label: str | None
    measurement_domain_key: str
    destination_key: str
    display_in_wdv: bool
    review_required: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "curve_identity": self.curve_identity,
            "curve_family_key": self.curve_family_key,
            "curve_family_label": self.curve_family_label,
            "measurement_domain_key": self.measurement_domain_key,
            "destination_key": self.destination_key,
            "display_in_wdv": self.display_in_wdv,
            "review_required": self.review_required,
        }


def project_unified_result(result: UnifiedCurveClassificationResult) -> ClassificationParityProjection:
    identity = str(result.curve_id if result.curve_id is not None else result.source_curve_index)
    if not identity or identity == "None":
        raise ValueError("Unified result lacks stable curve identity for parity projection")
    return ClassificationParityProjection(
        curve_identity=identity,
        curve_family_key=result.curve_family_key,
        curve_family_label=result.curve_family_label,
        measurement_domain_key=result.measurement_domain_key,
        destination_key=result.destination_key,
        display_in_wdv=result.display_in_wdv,
        review_required=result.review_required,
    )


def verify_stage_parity(
    stage_payloads: Mapping[str, Iterable[ClassificationParityProjection]],
) -> tuple[str, ...]:
    missing_stages = [stage for stage in STAGE_ORDER if stage not in stage_payloads]
    if missing_stages:
        raise ValueError(f"Missing parity stages: {missing_stages}")

    indexed: dict[str, dict[str, ClassificationParityProjection]] = {}
    for stage in STAGE_ORDER:
        rows = list(stage_payloads[stage])
        mapping: dict[str, ClassificationParityProjection] = {}
        for row in rows:
            if row.curve_identity in mapping:
                raise ValueError(f"Duplicate curve identity in {stage}: {row.curve_identity}")
            mapping[row.curve_identity] = row
        indexed[stage] = mapping

    reference_ids = set(indexed[STAGE_ORDER[0]])
    errors: list[str] = []

    for stage in STAGE_ORDER[1:]:
        stage_ids = set(indexed[stage])
        if stage_ids != reference_ids:
            errors.append(
                f"{stage}: identity_set_mismatch "
                f"missing={sorted(reference_ids - stage_ids)} "
                f"extra={sorted(stage_ids - reference_ids)}"
            )

    for identity in sorted(reference_ids):
        reference = indexed[STAGE_ORDER[0]][identity]
        for stage in STAGE_ORDER[1:]:
            candidate = indexed[stage].get(identity)
            if candidate is None:
                continue
            if candidate != reference:
                errors.append(
                    f"{stage}:{identity}: classification_projection_mismatch "
                    f"expected={reference.as_dict()} actual={candidate.as_dict()}"
                )

    return tuple(errors)
