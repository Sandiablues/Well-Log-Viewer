from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_wlv_health():
    response = client.get("/api/wlv/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["service"] == "wlv"


def test_list_wells_returns_seed_well():
    response = client.get("/api/wlv/wells")
    assert response.status_code == 200
    wells = response.json()
    assert len(wells) == 1
    assert wells[0]["well_id"] == "forge-21-31"
    assert wells[0]["curve_count"] >= 10
    assert wells[0]["interval_column_count"] >= 4


def test_get_well_detail_contains_header_context():
    response = client.get("/api/wlv/wells/forge-21-31")
    assert response.status_code == 200
    well = response.json()
    assert well["well_name"] == "Forge 21-31"
    assert well["api_number"] == "2700190539"
    assert well["depth_unit"] == "ft"
    assert well["depth_range"]["min"] == 300.5
    assert well["depth_range"]["max"] == 6076.0
    assert well["log_files"]


def test_curves_endpoint_returns_backend_curve_contracts():
    response = client.get("/api/wlv/wells/forge-21-31/curves")
    assert response.status_code == 200
    curves = response.json()
    mnemonics = {curve["mnemonic"] for curve in curves}
    assert {"GR", "SP", "AF90", "RHOB", "NPHI"}.issubset(mnemonics)
    assert all("samples_url" in curve for curve in curves)


def test_interval_columns_include_lithology_and_placeholders():
    response = client.get("/api/wlv/wells/forge-21-31/interval-columns")
    assert response.status_code == 200
    columns = response.json()
    types = {column["column_type"] for column in columns}
    assert {"lithology", "biostratigraphy", "formation", "facies"}.issubset(types)
    lithology = next(column for column in columns if column["column_type"] == "lithology")
    assert lithology["intervals"]


def test_viewer_package_endpoint_returns_well_multitrack_v1():
    response = client.get("/api/wlv/wells/forge-21-31/viewer-package")
    assert response.status_code == 200
    package = response.json()
    assert package["viewer_package_version"] == "well_multitrack_v1"
    assert package["well_id"] == "forge-21-31"
    assert package["depth_unit"] == "ft"
    assert package["tracks"]
    assert package["tracks"][0]["track_type"] == "depth"


def test_unknown_well_returns_404():
    response = client.get("/api/wlv/wells/not-a-well")
    assert response.status_code == 404
