from backend.app.knowledge.curve_knowledge import normalize_viewer_curve, normalize_viewer_package_for_wdv


def test_curve_knowledge_normalizes_aliases_to_backend_render_contract() -> None:
    curve = normalize_viewer_curve({"curve_id": "RHOB", "mnemonic": "RHOB", "unit": "G/C3"})

    assert curve["original_mnemonic"] == "RHOB"
    assert curve["canonical_curve_id"] == "bulk_density"
    assert curve["curve_family"] == "density"
    assert curve["display_curve_id"] == "RHOZ"
    assert curve["curve_id"] == "RHOZ"
    assert curve["is_renderable"] is True


def test_curve_knowledge_marks_unknown_curves_non_renderable() -> None:
    curve = normalize_viewer_curve({"curve_id": "XYZ1", "mnemonic": "XYZ1"})

    assert curve["canonical_curve_id"] == "unknown"
    assert curve["is_renderable"] is False
    assert curve["support_status"] == "unsupported_curve"


def test_viewer_package_normalization_excludes_unknown_curves_safely() -> None:
    package = normalize_viewer_package_for_wdv(
        {
            "depth_unit": "ft",
            "tracks": [
                {"track_id": "depth", "track_type": "depth", "title": "Depth", "curves": []},
                {
                    "track_id": "main",
                    "track_type": "curve",
                    "title": "Main",
                    "curves": [
                        {"curve_id": "GR", "mnemonic": "GR", "unit": "API"},
                        {"curve_id": "XYZ1", "mnemonic": "XYZ1"},
                    ],
                },
            ],
        }
    )

    assert [track["track_id"] for track in package["tracks"]] == ["depth", "main"]
    assert package["tracks"][1]["curves"][0]["canonical_curve_id"] == "gamma_ray"
    assert package["unsupported_products"][0]["original_mnemonic"] == "XYZ1"
