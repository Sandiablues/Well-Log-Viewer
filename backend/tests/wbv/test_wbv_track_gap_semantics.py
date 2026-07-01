from app.wbv.models import WbvTrackConfiguration


def test_track_configuration_persists_previous_track_gap() -> None:
    track = WbvTrackConfiguration(
        track_id="curve-track-2",
        display_name="Track 2",
        display_order=1,
        side="right",
        wellbore_offset=0.15,
        previous_track_gap=0.27,
    )

    payload = track.model_dump(mode="json")

    assert payload["wellbore_offset"] == 0.15
    assert payload["previous_track_gap"] == 0.27


def test_track_configuration_migrates_existing_tracks_with_default_gap() -> None:
    track = WbvTrackConfiguration.model_validate(
        {
            "track_id": "curve-track-legacy",
            "display_name": "Legacy Track",
            "display_order": 1,
            "side": "right",
            "wellbore_offset": 0.15,
        }
    )

    assert track.previous_track_gap == 0.05
