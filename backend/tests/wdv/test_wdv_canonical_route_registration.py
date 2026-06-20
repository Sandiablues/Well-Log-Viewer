from fastapi.testclient import TestClient

from app.main import app


def test_canonical_uid_routes_are_registered() -> None:
    client = TestClient(app)
    openapi = client.get("/openapi.json").json()
    paths = openapi["paths"]

    assert "/api/wlv/v2/viewer-packages/{managed_well_uid}" in paths
    assert "/api/wlv/v2/curve-samples" in paths
    assert "/api/wlv/v2/wdv/sessions/{managed_well_uid}" in paths
    assert "/api/wlv/v2/wdv/session-commands/{managed_well_uid}/tracks" in paths
    assert (
        "/api/wlv/v2/wdv/session-commands/{managed_well_uid}/assignments"
        in paths
    )
    assert (
        "/api/wlv/v2/wdv/template-commands/{managed_well_uid}/apply"
        in paths
    )
