from pathlib import Path


def test_frontend_track_header_title_is_derived_from_current_curve_assignments() -> None:
    source = Path("frontend/src/wells/prototype/TrackLayoutPrototype.tsx")
    text = source.read_text()

    assert "function displayTitleForTrack(track: WellLogTrack, catalog: CurveCatalogItem[])" in text
    assert "mnemonics.join(' / ')" in text
    assert "<strong>{displayTitleForTrack(track, curveCatalog)}</strong>" in text


def test_frontend_package_state_preserves_backend_display_scale_mode_fields() -> None:
    source = Path("frontend/src/wells/prototype/wdvPackageState.ts")
    text = source.read_text()

    assert "display_scale_mode?: string | null" in text
    assert "recommended_display_scale_mode?: string | null" in text
    assert "standard_display_min?: number | null" in text
    assert "robust_observed_display_min?: number | null" in text
    assert "displayScaleMode: typeof curve.display_scale_mode" in text
    assert "recommendedDisplayScaleMode: typeof curve.recommended_display_scale_mode" in text
