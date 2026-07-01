from pathlib import Path

import pytest

from app.inventory.models import ManagedWellRecord
from app.inventory.repository import ManagedWellInventoryRepository
from app.wbv.models import WbvDisplayLayerConfiguration, WbvTrackConfiguration
from app.wbv.service import WbvService


def test_display_layer_configuration_round_trip(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    repository.upsert_record(
        ManagedWellRecord(
            managed_well_id="managed-well:forge",
            well_id="forge",
            well_name="Forge",
        )
    )
    service = WbvService(repository=repository)
    saved = service.set_display_layer_configuration(
        "managed-well:forge",
        [
            WbvDisplayLayerConfiguration(
                layer_type="curve_overlays",
                visible=True,
                source_product_id="forge-las",
                selected_item_ids=["curve-gr", "curve-rhob"],
            )
        ],
    )
    assert saved.layers[0].visible is True
    assert saved.layers[0].selected_item_ids == ["curve-gr", "curve-rhob"]

    loaded = WbvService(repository=repository).get_display_layer_configuration("managed-well:forge")
    assert loaded.layers[0].source_product_id == "forge-las"
    assert loaded.layers[0].selected_item_ids == ["curve-gr", "curve-rhob"]


def test_display_layer_configuration_rejects_duplicate_layer_types(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    repository.upsert_record(
        ManagedWellRecord(
            managed_well_id="managed-well:forge",
            well_id="forge",
            well_name="Forge",
        )
    )
    service = WbvService(repository=repository)
    layers = [
        WbvDisplayLayerConfiguration(layer_type="formation_tops"),
        WbvDisplayLayerConfiguration(layer_type="formation_tops"),
    ]
    try:
        service.set_display_layer_configuration("managed-well:forge", layers)
    except ValueError as exc:
        assert "Duplicate" in str(exc)
    else:
        raise AssertionError("duplicate layer types must be rejected")


def _service_with_record(tmp_path: Path) -> tuple[WbvService, ManagedWellRecord]:
    repository = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    record = ManagedWellRecord(
        managed_well_id="managed-well:forge",
        well_id="forge",
        well_name="Forge",
    )
    repository.upsert_record(record)
    return WbvService(repository=repository), record


def test_display_layer_configuration_persists_curve_level_settings(tmp_path: Path) -> None:
    service, record = _service_with_record(tmp_path)
    request = [
        WbvDisplayLayerConfiguration(
            layer_type="curve_overlays",
            visible=True,
            source_product_id="source-las-1",
            selected_item_ids=["curve-gr", "curve-rhob"],
            curve_settings=[
                {
                    "curve_product_id": "curve-gr",
                    "display_order": 0,
                    "scale": {"source": "manual", "minimum": 0.0, "maximum": 150.0},
                    "appearance": {"color": "#55cc88", "radial_lane": 0},
                },
                {
                    "curve_product_id": "curve-rhob",
                    "display_order": 1,
                    "scale": {"source": "kr_family", "direction": "reversed"},
                    "appearance": {
                        "color": "#f0b35a",
                        "display_mode": "ribbon",
                        "radial_lane": 1,
                        "fill_mode": "to_baseline",
                        "fill_side": "negative",
                        "fill_color": "#d09042",
                        "fill_opacity": 0.4,
                        "fill_baseline_source": "manual",
                        "fill_baseline_value": 2.35,
                        "fill_outline": False,
                    },
                },
            ],
        )
    ]

    saved = service.set_display_layer_configuration(record.managed_well_id, request)

    assert [item.curve_product_id for item in saved.layers[0].curve_settings] == [
        "curve-gr",
        "curve-rhob",
    ]
    assert saved.layers[0].curve_settings[0].scale.maximum == 150.0
    assert saved.layers[0].curve_settings[1].appearance.display_mode == "ribbon"
    appearance = saved.layers[0].curve_settings[1].appearance
    assert appearance.fill_mode == "to_baseline"
    assert appearance.fill_side == "negative"
    assert appearance.fill_color == "#d09042"
    assert appearance.fill_opacity == 0.4
    assert appearance.fill_baseline_source == "manual"
    assert appearance.fill_baseline_value == 2.35
    assert appearance.fill_outline is False


def test_display_layer_configuration_rejects_settings_for_unselected_curve(tmp_path: Path) -> None:
    service, record = _service_with_record(tmp_path)
    with pytest.raises(ValueError, match="unselected curves"):
        service.set_display_layer_configuration(
            record.managed_well_id,
            [
                WbvDisplayLayerConfiguration(
                    layer_type="curve_overlays",
                    selected_item_ids=["curve-gr"],
                    curve_settings=[{"curve_product_id": "curve-rhob"}],
                )
            ],
        )



def test_display_layer_configuration_rejects_manual_fill_without_baseline(tmp_path: Path) -> None:
    service, record = _service_with_record(tmp_path)
    with pytest.raises(ValueError, match="Manual curve fill baseline requires a value"):
        service.set_display_layer_configuration(
            record.managed_well_id,
            [
                WbvDisplayLayerConfiguration(
                    layer_type="curve_overlays",
                    selected_item_ids=["curve-gr"],
                    curve_settings=[
                        {
                            "curve_product_id": "curve-gr",
                            "appearance": {
                                "fill_mode": "to_baseline",
                                "fill_baseline_source": "manual",
                            },
                        }
                    ],
                )
            ],
        )


def test_display_layer_configuration_persists_between_curves_fill(tmp_path: Path) -> None:
    service, record = _service_with_record(tmp_path)
    saved = service.set_display_layer_configuration(
        record.managed_well_id,
        [
            WbvDisplayLayerConfiguration(
                layer_type="curve_overlays",
                selected_item_ids=["curve-gr", "curve-rhob"],
                curve_settings=[
                    {
                        "curve_product_id": "curve-gr",
                        "appearance": {
                            "radial_lane": 0,
                            "fill_mode": "between_curves",
                            "fill_target_curve_product_id": "curve-rhob",
                        },
                    },
                    {
                        "curve_product_id": "curve-rhob",
                        "appearance": {"radial_lane": 0},
                    },
                ],
            )
        ],
        tracks=[
            WbvTrackConfiguration(
                track_id="curve-track-0",
                display_name="Track 1",
                display_order=0,
            )
        ],
    )
    appearance = saved.layers[0].curve_settings[0].appearance
    assert appearance.fill_mode == "between_curves"
    assert appearance.fill_target_curve_product_id == "curve-rhob"


def test_display_layer_configuration_rejects_between_curves_target_in_other_track(tmp_path: Path) -> None:
    service, record = _service_with_record(tmp_path)
    with pytest.raises(ValueError, match="share a track"):
        service.set_display_layer_configuration(
            record.managed_well_id,
            [
                WbvDisplayLayerConfiguration(
                    layer_type="curve_overlays",
                    selected_item_ids=["curve-gr", "curve-rhob"],
                    curve_settings=[
                        {
                            "curve_product_id": "curve-gr",
                            "appearance": {
                                "track_id": "curve-track-0",
                                "fill_mode": "between_curves",
                                "fill_target_curve_product_id": "curve-rhob",
                            },
                        },
                        {
                            "curve_product_id": "curve-rhob",
                            "appearance": {"track_id": "curve-track-1"},
                        },
                    ],
                )
            ],
            tracks=[
                WbvTrackConfiguration(
                    track_id="curve-track-0",
                    display_name="Track 1",
                    display_order=0,
                ),
                WbvTrackConfiguration(
                    track_id="curve-track-1",
                    display_name="Track 2",
                    display_order=1,
                ),
            ],
        )



def test_curve_overlay_requires_curve_track_and_normalizes_legacy_lane(tmp_path: Path) -> None:
    service, record = _service_with_record(tmp_path)
    tracks = [
        WbvTrackConfiguration(track_id="image-track", display_name="Image", track_type="image", display_order=0),
        WbvTrackConfiguration(track_id="curve-track", display_name="Curves", track_type="curve", display_order=1),
    ]
    with pytest.raises(ValueError, match="must be assigned to a curve track"):
        service.set_display_layer_configuration(
            record.managed_well_id,
            [WbvDisplayLayerConfiguration(
                layer_type="curve_overlays",
                selected_item_ids=["curve-gr"],
                curve_settings=[{"curve_product_id": "curve-gr", "appearance": {"track_id": "image-track"}}],
            )],
            tracks=tracks,
        )

    saved = service.set_display_layer_configuration(
        record.managed_well_id,
        [WbvDisplayLayerConfiguration(
            layer_type="curve_overlays",
            selected_item_ids=["curve-gr", "curve-rhob"],
            curve_settings=[
                {"curve_product_id": "curve-rhob", "display_order": 9, "appearance": {"track_id": "curve-track", "radial_lane": 0}},
                {"curve_product_id": "curve-gr", "display_order": 2, "appearance": {"track_id": "curve-track", "radial_lane": 0}},
            ],
        )],
        tracks=tracks,
    )
    settings = saved.layers[0].curve_settings
    assert [item.display_order for item in settings] == [0, 1]
    assert all(item.appearance.radial_lane == 1 for item in settings)
