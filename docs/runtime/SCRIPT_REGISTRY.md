# Script Registry

Generated: 2026-06-06T21:35:51.939846+00:00

This registry records the intended ownership category for tracked runtime,
E2E, contract-test, recovery, and diagnostic scripts in the Seismic
Viewer / MultiViewer repository.

The purpose is to prevent accidental deletion of useful operational
scripts while making future cleanup decisions evidence-based.

## Categories

- `KEEP_RUNTIME` — required for local restore/deploy/runtime operation.
- `KEEP_E2E` — E2E gate or workflow validation harness.
- `KEEP_CONTRACT_TEST` — backend/API/service contract regression test.
- `KEEP_RECOVERY_TOOL` — recovery, migration, repair, backfill, or reconcile utility.
- `MANUAL_DIAGNOSTIC` — manual inspection/debug/probe tool.
- `NEEDS_REVIEW` — retained for now; must be reviewed before deletion.

## Summary

| Category | Count | Lines |
|---|---:|---:|
| KEEP_CONTRACT_TEST | 28 | 4493 |
| KEEP_E2E | 3 | 364 |
| KEEP_RECOVERY_TOOL | 4 | 339 |
| KEEP_RUNTIME | 2 | 163 |
| MANUAL_DIAGNOSTIC | 2 | 53 |
| NEEDS_REVIEW | 14 | 990 |

## Registry

| Category | Lines | Script | Rationale |
|---|---:|---|---|
| KEEP_CONTRACT_TEST | 389 | `seismic-viewer-backend/scripts/e2e/test_existing_managed_3d_viewer.py` | Backend/API/service contract regression test. |
| KEEP_CONTRACT_TEST | 277 | `seismic-viewer-backend/scripts/e2e/test_managed_data_load_unload_viewer_availability.py` | Backend/API/service contract regression test. |
| KEEP_CONTRACT_TEST | 398 | `seismic-viewer-backend/scripts/e2e/test_source_intake_document_info_continuity.py` | Backend/API/service contract regression test. |
| KEEP_CONTRACT_TEST | 281 | `seismic-viewer-backend/scripts/e2e/test_source_intake_workbench_v2_nondestructive.py` | Backend/API/service contract regression test. |
| KEEP_CONTRACT_TEST | 50 | `seismic-viewer-backend/scripts/test_2d_render_quality_static_contract.py` | Backend/API/service contract regression test. |
| KEEP_CONTRACT_TEST | 63 | `seismic-viewer-backend/scripts/test_3d_active_slice_design_static_contract.py` | Backend/API/service contract regression test. |
| KEEP_CONTRACT_TEST | 36 | `seismic-viewer-backend/scripts/test_3d_slice_detail_static_contract.py` | Backend/API/service contract regression test. |
| KEEP_CONTRACT_TEST | 71 | `seismic-viewer-backend/scripts/test_job_history_retention_policy.py` | Job history retention contract test. |
| KEEP_CONTRACT_TEST | 119 | `seismic-viewer-backend/scripts/test_managed_data_bulk_delete_contract.py` | Backend/API/service contract regression test. |
| KEEP_CONTRACT_TEST | 116 | `seismic-viewer-backend/scripts/test_managed_data_bulk_viewer_actions_contract.py` | Backend/API/service contract regression test. |
| KEEP_CONTRACT_TEST | 74 | `seismic-viewer-backend/scripts/test_managed_data_query_contract.py` | Backend/API/service contract regression test. |
| KEEP_CONTRACT_TEST | 234 | `seismic-viewer-backend/scripts/test_msi_admin_edit_boundary_contract.py` | Backend/API/service contract regression test. |
| KEEP_CONTRACT_TEST | 408 | `seismic-viewer-backend/scripts/test_msi_contract.py` | Backend/API/service contract regression test. |
| KEEP_CONTRACT_TEST | 436 | `seismic-viewer-backend/scripts/test_msi_dataset_display_name_contract.py` | Backend/API/service contract regression test. |
| KEEP_CONTRACT_TEST | 89 | `seismic-viewer-backend/scripts/test_msi_info_contract.py` | Backend/API/service contract regression test. |
| KEEP_CONTRACT_TEST | 30 | `seismic-viewer-backend/scripts/test_msi_info_contract_static.py` | Backend/API/service contract regression test. |
| KEEP_CONTRACT_TEST | 143 | `seismic-viewer-backend/scripts/test_msi_metadata_documents_contract.py` | Backend/API/service contract regression test. |
| KEEP_CONTRACT_TEST | 274 | `seismic-viewer-backend/scripts/test_msi_registration_contract.py` | Backend/API/service contract regression test. |
| KEEP_CONTRACT_TEST | 94 | `seismic-viewer-backend/scripts/test_msi_representation_resolver.py` | Backend/API/service contract regression test. |
| KEEP_CONTRACT_TEST | 95 | `seismic-viewer-backend/scripts/test_section2d_window_contract.py` | Backend/API/service contract regression test. |
| KEEP_CONTRACT_TEST | 97 | `seismic-viewer-backend/scripts/test_source_intake_document_assignment_state_contract.py` | Backend/API/service contract regression test. |
| KEEP_CONTRACT_TEST | 115 | `seismic-viewer-backend/scripts/test_source_intake_workbench_contract.py` | Backend/API/service contract regression test. |
| KEEP_CONTRACT_TEST | 87 | `seismic-viewer-backend/scripts/test_storage_inventory_contract.py` | Backend/API/service contract regression test. |
| KEEP_CONTRACT_TEST | 111 | `seismic-viewer-backend/scripts/test_storage_managed_zarr_copy_contract.py` | Backend/API/service contract regression test. |
| KEEP_CONTRACT_TEST | 111 | `seismic-viewer-backend/scripts/test_storage_managed_zarr_copy_status_contract.py` | Backend/API/service contract regression test. |
| KEEP_CONTRACT_TEST | 99 | `seismic-viewer-backend/scripts/test_storage_migration_plan_contract.py` | Backend/API/service contract regression test. |
| KEEP_CONTRACT_TEST | 89 | `seismic-viewer-backend/scripts/test_storage_migration_review_export_contract.py` | Backend/API/service contract regression test. |
| KEEP_CONTRACT_TEST | 107 | `seismic-viewer-backend/scripts/test_storage_mount_contract.py` | Backend/API/service contract regression test. |
| KEEP_E2E | 164 | `seismic-viewer-backend/scripts/test_e2e_1a_msi_info_contract.py` | Current or recent E2E gate harness. |
| KEEP_E2E | 105 | `seismic-viewer-backend/scripts/test_e2e_1b_metadata_warning_semantics.py` | Current or recent E2E gate harness. |
| KEEP_E2E | 95 | `seismic-viewer-backend/scripts/test_e2e_1c_metadata_completeness_documents.py` | Current or recent E2E gate harness. |
| KEEP_RECOVERY_TOOL | 36 | `seismic-viewer-backend/scripts/backfill_normalized_metadata.py` | Recovery, migration, repair, backfill, or reconcile utility. |
| KEEP_RECOVERY_TOOL | 157 | `seismic-viewer-backend/scripts/backfill_textual_headers.py` | Recovery, migration, repair, backfill, or reconcile utility. |
| KEEP_RECOVERY_TOOL | 76 | `seismic-viewer-backend/scripts/reconcile_msi_converted.py` | Recovery, migration, repair, backfill, or reconcile utility. |
| KEEP_RECOVERY_TOOL | 70 | `seismic-viewer-backend/scripts/sync_duplicate_text_headers.py` | Recovery, migration, repair, backfill, or reconcile utility. |
| KEEP_RUNTIME | 124 | `scripts/runtime/deploy_local_runtime.sh` | Canonical runtime/restore/deploy support. |
| KEEP_RUNTIME | 39 | `scripts/runtime/restore_from_git.sh` | Canonical runtime/restore/deploy support. |
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
