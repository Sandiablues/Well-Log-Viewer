from app.main import app


def test_canonical_workspace_route_is_registered() -> None:
    paths = {route.path for route in app.routes}
    assert "/api/wlv/v2/wdv/workspaces/{managed_well_uid}" in paths
