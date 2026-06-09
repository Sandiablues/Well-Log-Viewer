from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_wlv_system_status_contract() -> None:
    response = client.get("/api/wlv/system/status")
    assert response.status_code == 200
    payload = response.json()

    assert payload["ok"] is True
    assert payload["service"] == "wlv-backend"
    assert payload["scope"] == "runtime_ops"
    assert payload["repository"]["type"] == "seed_repository"
    assert payload["repository"]["well_count"] >= 1
    assert "forge-21-31" in payload["repository"]["well_ids"]
    assert payload["maintenance"]["destructive_actions_enabled"] is False
    assert payload["contracts"]["system_status"] == "/api/wlv/system/status"
