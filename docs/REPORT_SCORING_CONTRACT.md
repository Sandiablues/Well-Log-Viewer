# Report Scoring Contract

This document defines the current reporting/scoring contract for the Seismic Viewer metadata reports.

The purpose is to prevent future changes from mixing together different concepts:

- metadata maturity
- technical readiness
- evidence strength
- validation status
- optimized-cache/conversion state

## Report payload shape

Both indexed SEG-Y reports and converted Zarr reports must expose the same top-level payload keys:

- dataset_id
- display_name
- dataset_type
- metadata_score
- technical_readiness
- validation
- categories
- source
- geometry
- headers
- missing_fields
- derived_fields
- warnings

The shared report renderer should consume this normalized payload and should not need to know whether the source is indexed SEG-Y or converted Zarr, except for optional source-specific sections such as textual-header preview.

## metadata_score

`metadata_score` represents metadata maturity/completeness.

It must not be used as a proxy for whether the dataset can be viewed.

Examples:

- Indexed SEG-Y may be viewable and technically usable while still having provisional metadata.
- Converted Zarr may have high metadata completeness if viewer metadata, headers, normalized metadata, and core geometry are present.

Current examples:

- Indexed SEG-Y: 60%, provisional_headers_only
- Converted Zarr: 96%, complete

## technical_readiness

`technical_readiness` represents whether the dataset can be used by the viewer/runtime.

It is separate from metadata maturity.

Current examples:

- Indexed SEG-Y: 90%, indexed_provisional
- Converted Zarr: 100%, converted_volume_resolved

A high technical readiness score does not mean metadata validation is complete.

## validation

`validation` represents the current validation state.

It should distinguish:

- headers_only
- usable
- document_validation not started
- CRS validation not started
- consistency status
- evidence strength

Current indexed SEG-Y state:

- headers_only
- document_validation: not_started
- crs_validation: not_started

Current converted Zarr state:

- usable
- evidence_strength: strong
- consistency: consistent
- document_validation: not_started
- crs_validation: not_started

## categories

Category structures may differ by source maturity level.

Indexed SEG-Y currently uses simpler categories:

- geometry
- headers
- documents
- optimized_cache

Converted Zarr currently uses richer categories:

- identity
- geometry
- evidence

This is acceptable as long as the shared renderer handles both safely.

Future work may normalize category names, but this is not required for E1/E2 acceptance.

## Indexed SEG-Y rules

Indexed SEG-Y reports are provisional unless additional validation is completed.

Indexed SEG-Y can have:

- strong geometry/header-derived viewer evidence
- fast preview support
- incomplete business metadata
- incomplete document validation
- incomplete CRS validation
- no optimized Zarr cache yet

The report must make that distinction visible.

## Converted Zarr rules

Converted Zarr reports should use the canonical metadata summary service.

They must not assume metadata lives at:

`data/zarr/<volume_id>/viewer_metadata.json`

Converted volume sidecars may use paths such as:

`data/zarr/<volume_id>.zarr.viewer_metadata.json`

The report module must rely on `build_metadata_summary(volume_id)` for converted volumes.

## Renderer rule

The shared report renderer should remain presentation-focused.

Route files should stay thin.

Route handlers should call report-service functions instead of carrying large inline HTML/CSS blocks.

## Current accepted implementation

The accepted report-service module is:

`seismic-viewer-backend/app/reports/metadata_score_report.py`

The accepted shared CSS file is:

`seismic-viewer-backend/app/reports/static/metadata_score_report.css`

The accepted runtime identity route is:

`/api/runtime/identity`

The accepted converted-volume report loader uses:

`build_metadata_summary(volume_id)`

## Acceptance checks

Before accepting report/scoring changes:

1. Confirm exactly one backend listener on port 8000.
2. Confirm `/api/runtime/identity` reports the expected live source files.
3. Confirm indexed SEG-Y report opens.
4. Confirm converted Zarr report opens.
5. Confirm converted report contains `converted_volume_resolved`.
6. Confirm converted report does not contain `missing_viewer_metadata`.
7. Confirm indexed SEG-Y metadata maturity remains visibly provisional/header-derived.
8. Confirm technical readiness is not confused with metadata completeness.
