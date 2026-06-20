"""Canonical curve-sample service addressed only by managed UUIDv7 identity."""

from __future__ import annotations

from pathlib import Path

from app.identity.wdv_contract_v2 import (
    WdvCurveSampleProvenance,
    WdvCurveSampleRequest,
    WdvCurveSampleResponse,
)
from app.inventory.canonical_identity_resolver import CanonicalInventoryIdentityResolver
from app.inventory.curve_sample_service import (
    CurveSampleServiceError,
    _read_las_curve_samples,
)


class CanonicalCurveSampleService:
    def __init__(self, resolver: CanonicalInventoryIdentityResolver | None = None) -> None:
        self.resolver = resolver or CanonicalInventoryIdentityResolver()

    def get_curve_samples(self, request: WdvCurveSampleRequest) -> WdvCurveSampleResponse:
        resolved = self.resolver.resolve_curve(
            request.managed_well_uid,
            request.managed_curve_uid,
        )
        product = resolved.product
        provenance = product.provenance if isinstance(product.provenance, dict) else {}
        source_path = self._source_path(provenance)
        if source_path is None:
            raise CurveSampleServiceError(
                f"No readable LAS source path for managed_curve_uid={request.managed_curve_uid}"
            )

        parsed = _read_las_curve_samples(
            source_path=source_path,
            curve_mnemonic=product.curve_name or product.display_name,
            max_samples=request.max_samples,
        )
        samples = tuple((float(depth), float(value)) for depth, value in parsed["samples"])
        return WdvCurveSampleResponse(
            managed_well_uid=resolved.managed_well_uid,
            managed_curve_uid=resolved.managed_curve_uid,
            managed_product_uid=resolved.managed_product_uid,
            managed_source_uid=resolved.managed_source_uid,
            sample_revision=request.sample_revision,
            observed_mnemonic=product.curve_name or product.display_name,
            normalized_mnemonic=product.curve_name,
            display_name=product.display_name,
            curve_family=product.curve_family,
            depth_unit=parsed["depth_unit"],
            value_unit=parsed["value_unit"] or product.curve_unit or None,
            depth_min=parsed["depth_min"],
            depth_max=parsed["depth_max"],
            value_min=parsed["value_min"],
            value_max=parsed["value_max"],
            robust_value_min=parsed.get("robust_value_min"),
            robust_value_max=parsed.get("robust_value_max"),
            value_p01=parsed.get("value_p01"),
            value_p05=parsed.get("value_p05"),
            value_p50=parsed.get("value_p50"),
            value_p95=parsed.get("value_p95"),
            value_p99=parsed.get("value_p99"),
            sample_count=parsed["sample_count"],
            returned_sample_count=len(samples),
            raw_numeric_sample_count=parsed.get("raw_numeric_sample_count"),
            rejected_sample_count=parsed.get("rejected_sample_count", 0),
            rejected_null_count=parsed.get("rejected_null_count", 0),
            rejected_sentinel_count=parsed.get("rejected_sentinel_count", 0),
            rejected_nonfinite_count=parsed.get("rejected_nonfinite_count", 0),
            rejected_plausibility_count=parsed.get("rejected_plausibility_count", 0),
            rejected_row_count=parsed.get("rejected_row_count", 0),
            decimation_stride=parsed["decimation_stride"],
            provenance=WdvCurveSampleProvenance(
                sample_source="las_original_path",
                source_path=str(source_path),
                source_intake_candidate_id=product.source_intake_candidate_id,
                checksum=None,
                generated_at=None,
            ),
            samples=samples,
        )

    @staticmethod
    def _source_path(provenance: dict[str, object]) -> Path | None:
        for key in ("original_path", "path", "source_path"):
            value = provenance.get(key)
            if not value:
                continue
            path = Path(str(value)).expanduser()
            if path.exists() and path.is_file():
                return path.resolve()
        return None
