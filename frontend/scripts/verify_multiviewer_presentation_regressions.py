#!/usr/bin/env python3
from pathlib import Path
import subprocess, sys

ROOT=Path.home()/"Applications"/"MultiViewer"/"Well-Log-Viewer"/"frontend"
SCRIPTS=ROOT/"scripts"

checks=[
    ("WBV View presentation", SCRIPTS/"verify_wbv_view_presentation_guard.py"),
    ("WBV Core / Interval interaction", SCRIPTS/"verify_wbv_core_interval_regression_contract.py"),
    ("WDV menu presentation", SCRIPTS/"verify_wdv_menu_presentation_guard.py"),
    ("WDV master scope", SCRIPTS/"verify_wdv_master_scope_guard.py"),
    ("WDV Quick View presentation", SCRIPTS/"verify_wdv_quick_view_presentation_guard.py"),
    ("WDV Properties presentation", SCRIPTS/"verify_wdv_properties_presentation_guard.py"),
    ("WDV Well Metadata / Status presentation", SCRIPTS/"verify_wdv_well_metadata_status_presentation_guard.py"),
    ("WDV Add Track presentation", SCRIPTS/"verify_wdv_add_track_presentation_guard.py"),
    ("WDV Curve Header Action Menu presentation", SCRIPTS/"verify_wdv_curve_header_action_menu_presentation_guard.py"),
    ("WDV Final Consolidation presentation", SCRIPTS/"verify_wdv_final_consolidation_presentation_guard.py"),
    ("WBV/WLV Final Consolidation presentation", SCRIPTS/"verify_wbv_wlv_final_consolidation_presentation_guard.py"),
    ("SDV 2D/3D Final Consolidation presentation", SCRIPTS/"verify_sdv_2d_3d_final_consolidation_presentation_guard.py"),
    ("Final Presentation Governance Baseline", SCRIPTS/"verify_multiviewer_final_presentation_governance_baseline.py"),
    ("Phase41D SDV Cascade Authority", SCRIPTS/"verify_multiviewer_phase41d_sdv_cascade_authority.py"),
    ("Right-Panel Role Normalization", SCRIPTS/"verify_multiviewer_right_panel_role_normalization.py"),
    ("Right-Panel Shared Role Parity", SCRIPTS/"verify_multiviewer_right_panel_shared_role_parity.py"),
    ("WBV Right-Panel Master Typography Ownership", SCRIPTS/"verify_multiviewer_wbv_right_panel_master_typography_ownership.py"),
    ("WBV Right-Panel Label Weight Parity", SCRIPTS/"verify_multiviewer_wbv_right_panel_label_weight_parity.py"),
    ("SDV Right-Panel Muted Label Brightness", SCRIPTS/"verify_multiviewer_sdv_right_panel_muted_label_brightness.py"),
    ("Master Theme Authority", SCRIPTS/"verify_multiviewer_master_theme_authority.py"),
    ("Global Theme Switch", SCRIPTS/"verify_multiviewer_global_theme_switch.py"),
    ("Role-Based Light Theme Wiring", SCRIPTS/"verify_multiviewer_role_based_light_theme_wiring.py"),
    ("Light Palette Rebalance", SCRIPTS/"verify_multiviewer_light_palette_rebalance.py"),
    ("Multi-Grey Contrast Palette", SCRIPTS/"verify_multiviewer_multi_grey_contrast_palette.py"),
    ("Darker Multi-Grey Depth Contrast", SCRIPTS/"verify_multiviewer_darker_multi_grey_depth_contrast.py"),
    ("Light Theme Depth & Elevation", SCRIPTS/"verify_multiviewer_light_theme_depth_elevation.py"),
]

print("=== MULTIVIEWER PRESENTATION REGRESSION SUITE ===")
for label,path in checks:
    if not path.is_file():
        print(f"FAIL: {label}: missing guard {path}")
        raise SystemExit(1)
    print(f"--- {label} ---")
    p=subprocess.run([sys.executable,str(path)])
    if p.returncode:
        print(f"FAIL: {label}")
        raise SystemExit(p.returncode)

print("============================================================")
print("MULTIVIEWER PRESENTATION REGRESSION SUITE PASS")
print("WBV View: PASS")
print("WBV Core / Interval: PASS")
print("WDV Menu / Toolbar: PASS")
print("WDV Master Scope: PASS")
print("WDV Quick View: PASS")
print("WDV Properties: PASS")
print("WDV Well Metadata / Status: PASS")
print("WDV Add Track: PASS")
print("WDV Curve Header Action Menu: PASS")
print("WDV Final Consolidation: PASS")
print("WBV/WLV Final Consolidation: PASS")
print("SDV 2D/3D Final Consolidation: PASS")
print("Final Presentation Governance Baseline: PASS")
print("Phase41D SDV Cascade Authority: PASS")
print("Right-Panel Role Normalization: PASS")
print("Right-Panel Shared Role Parity: PASS")
print("WBV Right-Panel Master Typography Ownership: PASS")
print("WBV Right-Panel Label Weight Parity: PASS")
print("SDV Right-Panel Muted Label Brightness: PASS")
print("Master Theme Authority: PASS")
print("Global Theme Switch: PASS")
print("Role-Based Light Theme Wiring: PASS")
print("Light Palette Rebalance: PASS")
print("Multi-Grey Contrast Palette: PASS")
print("Darker Multi-Grey Depth Contrast: PASS")
print("Light Theme Depth & Elevation: PASS")
print("============================================================")
