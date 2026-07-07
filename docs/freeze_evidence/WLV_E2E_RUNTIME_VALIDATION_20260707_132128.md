# WLV End-to-End Runtime Validation Evidence

- Validation timestamp: 20260707_132128
- Branch: feature/wlv-native-las-wdv-20260630
- Git HEAD: 93be4f6b5e6109cdd141fa70c1e14650c142f147
- Result: PASS
- Real LAS source: /Users/donarcher/Desktop/WLV_Data/21-31_WirelineLogs/Ormat_Forge21-31_8.5inchsection/Ormat_Forge 21-31_8.5 inch section/Triple Combo/LAS/DM9E-00185_Ormat_Carson_Forge-21-31_TCOM_ConCu_R02_L002Up.las
- Real LAS SHA-256: 3e820f76b51623afd326840826ffeb50a37ee4bb6ad39eb9270bdc51bf2722ff
- Real DLIS source: /Users/donarcher/Desktop/WLV_Data/21-31_WirelineLogs/Ormat_Forge21-31_8.5inchsection/Ormat_Forge 21-31_8.5 inch section/Triple Combo/DLIS/DM9E-00185_Ormat_Carson_Forge-21-31_TCOM_ConCu_R02_L002Up.dlis
- Real DLIS SHA-256: a3b905fc67d65ee2ac9e2507db4c6c9573a9662a4b6e0397721ec09e3bf5524c
- Authoritative source immutability: PASS
- Backend end-to-end acceptance: PASS
- Frontend recovery acceptance: PASS
- Frontend production build: PASS

## Validated chain

- Real LAS is opened read-only and parsed into a disposable derived asset path.
- Real DLIS is opened through a read-only external-reference path.
- WSI external references, lifecycle, reference tracking, cleanup, rebuild, overlays, saved workspaces, and source recovery pass.
- WMD lifecycle, reference ownership, cleanup eligibility, cleanup execution, rebuild, and source recovery pass.
- WDV and WBV reference reconciliation, active-well switching, bulk load/unload, export ownership, viewer-session reset, and stale-reference reconciliation pass.
- LAS reconstruction, canonical WDV viewer-package behavior, WBV session authority, and managed trajectory selection pass.
- The authoritative LAS and DLIS source bytes and filesystem metadata are unchanged after validation.

## Working tree status

```
 M backend/app/curve_fill_v2/canonical_service.py
 M backend/app/curve_fill_v2/capabilities.py
 M backend/app/curve_fill_v2/policy.py
 M backend/app/curve_fill_v2/service.py
 M backend/app/identity/wdv_contract_v2.py
 M backend/app/ingestion/adapters.py
 M backend/app/inventory/api_inventory.py
 M backend/app/inventory/canonical_curve_sample_service.py
 M backend/app/inventory/curve_sample_service.py
 M backend/app/inventory/dlis_sample_reader.py
 M backend/app/inventory/models.py
 M backend/app/inventory/service.py
 M backend/app/inventory/wdv_workspace.py
 M backend/app/knowledge/runtime_classification_service.py
 M backend/app/main.py
 M backend/app/source_intake/depth_units.py
 M backend/app/source_intake/las_asset_store.py
 M backend/app/source_intake/metadata_resolver.py
 M backend/app/source_intake/models.py
 M backend/app/source_intake/readiness.py
 M backend/app/source_intake/registration.py
 M backend/app/source_intake/resolution_service.py
 M backend/app/source_intake/router.py
 M backend/app/source_intake/service.py
 D backend/app/wbv/fixtures/forge_21_31_downlog_vertical_wbv_trajectory_package.json
 M backend/app/wbv/models.py
 M backend/app/wbv/service.py
 M backend/app/wbv/trajectory_seed_registry.json
 M backend/app/wells/canonical_viewer_package_router.py
 M backend/app/wells/seed_repository.py
 M backend/pyproject.toml
 M backend/tests/curve_fill_v2/test_curve_fill_v2_canonical_persistence.py
 M backend/tests/curve_fill_v2/test_curve_fill_v2_engine.py
 M backend/tests/curve_fill_v2/test_curve_fill_v2_workflow_capabilities.py
 M backend/tests/inventory/test_dlis_wdv_sample_pipeline.py
 M backend/tests/source_intake/test_las_asset_store.py
 M frontend/src/styles/inspection.css
 M frontend/src/styles/track-layout-prototype.css
 M frontend/src/wells/fixtures/mockWellMultitrackPackage.ts
 M frontend/src/wells/prototype/TrackLayoutPrototype.tsx
 M frontend/src/wells/prototype/WellLogPropertiesPanelSlot.tsx
 M frontend/src/wells/prototype/lithologyTrackData.ts
 M frontend/src/wells/prototype/managedCurveSamples.ts
 M frontend/src/wells/prototype/mockTrackLayoutData.ts
 M frontend/src/wells/prototype/realLasTrackLayoutData.ts
 M frontend/src/wells/prototype/wellLogPropertiesPanelContract.ts
 M frontend/src/wells/source-intake/SourceIntakeWorkbench.tsx
 M frontend/src/wells/wbv/Wellbore3DPage.tsx
 M frontend/src/wells/wbv/WellboreTrajectoryRenderer.tsx
 M frontend/src/wells/wbv/__tests__/wbvIntervalAoiContract.test.ts
 M frontend/src/wells/wbv/__tests__/wbvLiveInteraction.test.ts
 M frontend/src/wells/wdv/WdvPageBoundary.tsx
 M frontend/src/wells/wdv/WdvPresentationPrimitives.tsx
 M frontend/src/wells/wdv/__tests__/wdvPageBoundaryCanonicalSession.test.ts
?? .wlv_freeze_evidence/
?? .wlv_patch_backups/
?? .wlv_retired_frontend_authority/
?? .wlv_runtime_logs/
?? backend.log
?? backend/app/inventory/wmd_lifecycle_service.py
?? backend/app/source_intake/canonical_metadata.py
?? backend/app/source_intake/dlis_asset_store.py
?? backend/app/source_intake/lifecycle_service.py
?? backend/app/source_intake/metadata_adoption.py
?? backend/app/wbv_layout/
?? backend/app/wbv_publication/
?? backend/app/wells/canonical_wdv_metadata_contract.py
?? backend/scripts/
?? backend/tests/inventory/test_common_depth_las_dlis_conversion.py
?? backend/tests/inventory/test_dlis_managed_depth_unit_propagation.py
?? backend/tests/inventory/test_simple_depth_rebuild_regression.py
?? backend/tests/inventory/test_wdv_common_depth_unit.py
?? backend/tests/inventory/test_wdv_curve_samples_common_depth_unit.py
?? backend/tests/inventory/test_wdv_wbv_export_session_reference_completion_block3.py
?? backend/tests/inventory/test_wdv_wbv_lifecycle_alignment_block1.py
?? backend/tests/inventory/test_wdv_wbv_session_workspace_reconciliation_block2.py
?? backend/tests/inventory/test_wmd_controlled_cleanup_block3.py
?? backend/tests/inventory/test_wmd_controlled_cleanup_execution_block4.py
?? backend/tests/inventory/test_wmd_downstream_recovery_integration_block7.py
?? backend/tests/inventory/test_wmd_rebuild_after_cleanup_block5.py
?? backend/tests/inventory/test_wmd_reference_integration_block2.py
?? backend/tests/inventory/test_wmd_source_recovery_block6.py
?? backend/tests/inventory/test_wmd_transient_lifecycle_block1.py
?? backend/tests/source_intake/test_canonical_metadata_workflow.py
?? backend/tests/source_intake/test_dlis_asset_store.py
?? backend/tests/source_intake/test_external_source_reference_contract.py
?? backend/tests/source_intake/test_f5_depth_contract_propagation.py
?? backend/tests/source_intake/test_metadata_adoption_preview.py
?? backend/tests/source_intake/test_transient_lifecycle_contract.py
?? backend/tests/source_intake/test_wlv_source_intake_block13_source_recovery.py
?? backend/tests/source_intake/test_wlv_source_intake_block3_reference_tracking.py
?? backend/tests/source_intake/test_wlv_source_intake_block4_reference_integration.py
?? backend/tests/source_intake/test_wlv_source_intake_block6_source_retention.py
?? backend/tests/source_intake/test_wlv_source_intake_block7_controlled_cleanup.py
?? backend/tests/source_intake/test_wlv_source_intake_block8_all_derived_rebuild.py
?? backend/tests/source_intake/test_wlv_source_intake_direct_file_ingest.py
?? backend/tests/source_intake/test_wlv_source_intake_lifecycle_service.py
?? backend/tests/source_intake/test_wlv_source_intake_overlay_export.py
?? backend/tests/source_intake/test_wlv_source_intake_saved_workspace_retention.py
?? backend/tests/source_intake/test_wsi_block14_legacy_retention_retirement.py
?? backend/tests/source_intake/test_wsi_block9_transient_wmd_availability.py
?? backend/tests/wbv/test_wbv_session_uuidv7_authority.py
?? backend/tests/wbv_publication/
?? frontend/src/wells/contracts/
?? frontend/src/wells/inventory/
?? frontend/src/wells/wbv/__tests__/publicationApi.test.ts
?? frontend/src/wells/wbv/__tests__/wbvMarkerPresentation.test.ts
?? frontend/src/wells/wbv/__tests__/wbvZoomAndManageButton.test.ts
?? frontend/src/wells/wbv/publicationApi.ts
?? frontend/src/wells/wdv/__tests__/depthRangeState.test.ts
?? frontend/src/wells/wdv/depthRangeState.ts
```

## Scope note

The test suite uses isolated temporary application state. It validates the real authoritative LAS and DLIS files without mutating the user's live WSI/WMD workspace or deleting live application records.
