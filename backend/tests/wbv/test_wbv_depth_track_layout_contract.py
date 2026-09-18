from app.wbv_layout.models import WbvLayoutCommandRequest, WbvLayoutTrack

def test_depth_track_contract_defaults():
    track = WbvLayoutTrack(track_uid="018f3d7b-7c00-7000-8000-000000000001", display_name="Depth", track_type="depth", display_order=0)
    assert track.track_type == "depth"
    assert track.depth_type == "MD"
    assert track.depth_increment == 100.0
    assert track.label_increment == 500.0
    assert track.label_size == 1.0
    assert track.show_depth_units is True
    assert track.outline_color == "#b9f3ff"
    assert track.tick_color == "#b9f3ff"
    assert track.label_color == "#b9f3ff"

def test_depth_track_command_settings():
    request = WbvLayoutCommandRequest(expected_revision=1, command="add_track", track_type="depth", depth_type="TVDSS", depth_increment=50.0, label_increment=250.0, label_size=1.5, show_depth_units=False, outline_color="#112233", tick_color="#445566", label_color="#778899")
    assert request.depth_type == "TVDSS"
    assert request.depth_increment == 50.0
    assert request.label_increment == 250.0
    assert request.label_size == 1.5
    assert request.show_depth_units is False
    assert request.outline_color == "#112233"
    assert request.tick_color == "#445566"
    assert request.label_color == "#778899"
