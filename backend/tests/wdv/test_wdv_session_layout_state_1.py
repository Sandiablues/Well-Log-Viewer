from __future__ import annotations

import importlib

from fastapi.testclient import TestClient


def _client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("WLV_WDV_SESSION_LAYOUT_STORE", str(tmp_path / "session_layouts.json"))
    main = importlib.import_module("backend.app.main")
    return TestClient(main.app)


def test_get_empty_backend_owned_wdv_layout(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)

    response = client.get("/api/wlv/wdv/sessions/well-a/layout")

    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "wdv_session_layout_state_service"
    assert payload["contract_version"] == "wdv_session_layout_state_v1"
    assert payload["managed_well_id"] == "well-a"
    assert payload["state_status"] == "empty"
    assert payload["tracks"] == []


def test_put_layout_persists_backend_owned_wdv_tracks(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    request = {
        "selected_track_id": "track-gr",
        "source": "test_backend_owned_layout",
        "tracks": [
            {
                "track_id": "track-gr",
                "track_key": "gamma-ray",
                "track_number": 1,
                "track_name": "Gamma Ray",
                "track_type": "curve",
                "renderer_type": "line_curve",
                "curves": [
                    {
                        "assignment_id": "assign-gr-1",
                        "curve_id": "curve-gr",
                        "product_id": "product-gr",
                        "mnemonic": "GR",
                        "curve_family": "gamma_ray",
                        "stack_index": 0,
                        "visible": True,
                        "scale_min": 0,
                        "scale_max": 150,
                        "scale_type": "linear",
                    }
                ],
            }
        ],
    }

    put_response = client.put("/api/wlv/wdv/sessions/well-a/layout", json=request)
    assert put_response.status_code == 200
    put_payload = put_response.json()
    assert put_payload["state_status"] == "active"
    assert put_payload["revision"] == 1
    assert put_payload["selected_track_id"] == "track-gr"
    assert put_payload["tracks"][0]["curves"][0]["mnemonic"] == "GR"

    get_response = client.get("/api/wlv/wdv/sessions/well-a/layout")
    assert get_response.status_code == 200
    get_payload = get_response.json()
    assert get_payload["state_status"] == "active"
    assert get_payload["revision"] == 1
    assert get_payload["tracks"][0]["track_id"] == "track-gr"


def test_clear_layout_is_backend_owned_and_idempotent(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    request = {
        "selected_track_id": None,
        "tracks": [
            {
                "track_id": "track-res",
                "track_name": "Resistivity",
                "track_type": "curve",
                "curves": [],
            }
        ],
    }
    assert client.put("/api/wlv/wdv/sessions/well-a/layout", json=request).status_code == 200

    clear_response = client.post("/api/wlv/wdv/sessions/well-a/layout/clear", json={"reason": "test_clear"})
    assert clear_response.status_code == 200
    clear_payload = clear_response.json()
    assert clear_payload["state_status"] == "cleared"
    assert clear_payload["source"] == "test_clear"
    assert clear_payload["tracks"] == []
    assert clear_payload["revision"] == 2

    clear_again = client.post("/api/wlv/wdv/sessions/well-a/layout/clear", json={"reason": "test_clear_again"})
    assert clear_again.status_code == 200
    assert clear_again.json()["revision"] == 3


def test_layout_rejects_duplicate_track_ids(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    request = {
        "tracks": [
            {"track_id": "track-a", "track_name": "A", "curves": []},
            {"track_id": "track-a", "track_name": "A duplicate", "curves": []},
        ],
    }

    response = client.put("/api/wlv/wdv/sessions/well-a/layout", json=request)

    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "invalid_wdv_layout_state"

def test_depth_only_layout_is_persisted_as_empty(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    request = {
        "selected_track_id": "depth-track",
        "source": "test_depth_only_clear",
        "tracks": [
            {
                "track_id": "depth-track",
                "track_name": "MD",
                "track_type": "depth",
                "width_px": 86,
                "curves": [],
            }
        ],
    }

    put_response = client.put("/api/wlv/wdv/sessions/well-a/layout", json=request)

    assert put_response.status_code == 200
    payload = put_response.json()
    assert payload["state_status"] == "empty"
    assert payload["selected_track_id"] is None
    assert payload["tracks"] == []

    get_response = client.get("/api/wlv/wdv/sessions/well-a/layout")
    assert get_response.status_code == 200
    restored = get_response.json()
    assert restored["state_status"] == "empty"
    assert restored["tracks"] == []


def test_empty_curve_tracks_are_persisted_as_empty(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    request = {
        "selected_track_id": "empty-curve-track",
        "source": "test_empty_curve_track_clear",
        "tracks": [
            {
                "track_id": "empty-curve-track",
                "track_name": "Gamma Ray",
                "track_type": "curve",
                "curves": [],
            }
        ],
    }

    put_response = client.put("/api/wlv/wdv/sessions/well-a/layout", json=request)

    assert put_response.status_code == 200
    payload = put_response.json()
    assert payload["state_status"] == "empty"
    assert payload["selected_track_id"] is None
    assert payload["tracks"] == []

