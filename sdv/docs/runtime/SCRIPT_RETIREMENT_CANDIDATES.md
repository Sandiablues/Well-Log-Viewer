# Script Retirement Candidates

Generated: 2026-06-06T21:35:51.939846+00:00

No script in this list is approved for deletion by this document alone.
This file is a review queue for future hardening blocks.

Deletion requires a separate dependency proof block, build/runtime gates,
and explicit approval.

## Current Review Queue

| Current Category | Lines | Script | Review Reason |
|---|---:|---|---|
| MANUAL_DIAGNOSTIC | 32 | `seismic-viewer-backend/scripts/create_dummy_segy.py` | Manual inspection/debug/probe tool. |
| MANUAL_DIAGNOSTIC | 21 | `seismic-viewer-backend/scripts/debug_segy.py` | Manual inspection/debug/probe tool. |
| NEEDS_REVIEW | 53 | `scripts/check_metadata_reports.py` | Tracked script not yet assigned a durable ownership category. |
| NEEDS_REVIEW | 62 | `scripts/check_runtime_identity.py` | Tracked script not yet assigned a durable ownership category. |
| NEEDS_REVIEW | 21 | `scripts/dev_rebuild_restart.sh` | Tracked script not yet assigned a durable ownership category. |
| NEEDS_REVIEW | 166 | `scripts/smoke_lifecycle_contract.py` | Tracked script not yet assigned a durable ownership category. |
| NEEDS_REVIEW | 198 | `seismic-viewer-backend/main.py` | Tracked script not yet assigned a durable ownership category. |
| NEEDS_REVIEW | 64 | `seismic-viewer-backend/scripts/audit_msi_ownership.py` | Tracked script not yet assigned a durable ownership category. |
| NEEDS_REVIEW | 33 | `seismic-viewer-backend/scripts/build_segy_index.py` | Tracked script not yet assigned a durable ownership category. |
| NEEDS_REVIEW | 119 | `seismic-viewer-backend/scripts/check_document_evidence_regression.py` | Tracked script not yet assigned a durable ownership category. |
| NEEDS_REVIEW | 64 | `seismic-viewer-backend/scripts/check_metadata_reports.py` | Tracked script not yet assigned a durable ownership category. |
| NEEDS_REVIEW | 20 | `seismic-viewer-backend/scripts/e2e/run_existing_managed_3d_viewer.sh` | Tracked script not yet assigned a durable ownership category. |
| NEEDS_REVIEW | 73 | `seismic-viewer-backend/scripts/e2e/run_managed_data_load_unload_viewer_availability.sh` | Tracked script not yet assigned a durable ownership category. |
| NEEDS_REVIEW | 11 | `seismic-viewer-backend/scripts/e2e/run_source_intake_document_info_continuity.sh` | Tracked script not yet assigned a durable ownership category. |
| NEEDS_REVIEW | 84 | `seismic-viewer-backend/scripts/e2e/run_source_intake_workbench_v2_nondestructive.sh` | Tracked script not yet assigned a durable ownership category. |
| NEEDS_REVIEW | 22 | `seismic-viewer-backend/scripts/test_conversion.py` | Tracked script not yet assigned a durable ownership category. |

## Review Rules

- Do not delete recovery or backfill tools unless there is a replacement.
- Do not delete E2E or contract tests unless the same gate exists elsewhere.
- Do not delete diagnostic tools during active hardening unless they are clearly obsolete.
- Prefer archiving/removing in small blocks with compile, build, runtime health, and bundle checks.
