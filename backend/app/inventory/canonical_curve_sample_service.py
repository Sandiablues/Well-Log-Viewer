"""Canonical curve-sample service addressed only by managed UUIDv7 identity."""

from __future__ import annotations

from pathlib import Path

from app.depth_reference import (
    source_contract_from_metadata,
    transform_sample_payload,
    well_depth_contract_from_record,
)

from app.identity.wdv_contract_v2 import (
    WdvCurveSampleProvenance,
    WdvCurveSampleRequest,
    WdvCurveSampleResponse,
)
from app.inventory.canonical_identity_resolver import CanonicalInventoryIdentityResolver
from app.inventory.curve_sample_service import (
    CurveSampleServiceError,
    _read_source_curve_samples,
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
        source_path = self._source_path(
            source=resolved.source,
            product_provenance=provenance,
        )
        if source_path is None:
            raise CurveSampleServiceError(
                "No readable source path for "
                f"managed_curve_uid={request.managed_curve_uid}; "
                f"managed_source_uid={resolved.managed_source_uid}"
            )

        parsed, sample_source = _read_source_curve_samples(
            source_path=source_path, curve_mnemonic=product.curve_name or product.display_name,
            max_samples=request.max_samples, source_kind=product.source_kind, provenance=provenance,
        )
        source_contract = source_contract_from_metadata(resolved.source.metadata)
        well_contract = self._well_depth_contract(resolved.well)
        parsed = transform_sample_payload(
            parsed,
            source_contract=source_contract,
            target_unit=well_contract["unit"],
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
                sample_source=sample_source,
                source_path=str(source_path),
                source_intake_candidate_id=product.source_intake_candidate_id,
                checksum=None,
                generated_at=None,
            ),
            samples=samples,
        )


    @staticmethod
    def _well_depth_contract(well: object) -> dict[str, object]:
        return well_depth_contract_from_record(well)

    @staticmethod
    def _source_path(
        *,
        source: object,
        product_provenance: dict[str, object],
    ) -> Path | None:
        """Resolve samples from the canonical managed-source record.

        The managed source is the authority for the retained source asset. Curve
        provenance is accepted only as a compatibility fallback for inventory
        records created before source-level asset ownership was enforced.
        """

        candidates: list[object] = [
            getattr(source, "original_path", None),
        ]

        source_metadata = getattr(source, "metadata", None)
        if isinstance(source_metadata, dict):
            candidates.extend(
                CanonicalCurveSampleService._path_candidates(source_metadata)
            )

        candidates.extend(
            CanonicalCurveSampleService._path_candidates(product_provenance)
        )

        seen: set[str] = set()
        for value in candidates:
            if not value:
                continue
            token = str(value).strip()
            if not token or token in seen:
                continue
            seen.add(token)
            path = Path(token).expanduser()
            if path.exists() and path.is_file():
                return path.resolve()
        return None

    @staticmethod
    def _path_candidates(payload: dict[str, object]) -> list[object]:
        candidates: list[object] = [
            payload.get("storage_uri"),
            payload.get("original_uri"),
            payload.get("original_path"),
            payload.get("path"),
            payload.get("source_path"),
        ]
        for asset_key in ("dlis_asset", "las_asset"):
            asset = payload.get(asset_key)
            if isinstance(asset, dict):
                candidates.extend(
                    [
                        asset.get("original_uri"),
                        asset.get("storage_uri"),
                        asset.get("original_path"),
                        asset.get("path"),
                    ]
                )
        return candidates
