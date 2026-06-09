from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.ingestion.models import WellLogSourceFormat
from backend.app.ingestion.service import WellLogSourceIngestionService

client = TestClient(app)


def test_ingestion_health_lists_supported_formats() -> None:
    response = client.get("/api/wlv/ingestion/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["service"] == "wlv-source-ingestion"
    assert payload["adapter_count"] >= 5
    assert "las" in payload["supported_formats"]
    assert "dlis" in payload["supported_formats"]
    assert "cgm" in payload["supported_formats"]
    assert "tiff" in payload["supported_formats"]


def test_supported_formats_include_numeric_frame_and_raster_categories() -> None:
    response = client.get("/api/wlv/ingestion/supported-formats")
    assert response.status_code == 200
    payload = response.json()
    by_format = {item["source_format"]: item for item in payload}
    assert by_format["las"]["source_category"] == "numeric_curve"
    assert by_format["dlis"]["source_category"] == "frame_channel"
    assert by_format["cgm"]["source_category"] == "vector_log"
    assert by_format["tiff"]["source_category"] == "raster_log"
    assert by_format["las"]["adapter_status"] == "active"


def test_detect_format_for_las_source_file() -> None:
    response = client.post("/api/wlv/ingestion/detect-format", json={"file_name": "Forge_21_31.las"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["detected_format"] == "las"
    assert payload["source_category"] == "numeric_curve"
    assert payload["is_supported"] is True
    assert payload["adapter_id"] == "las_numeric_curve_adapter_v1"
    assert "extract_curve_inventory" in payload["capabilities"]


def test_detect_format_for_dlis_cgm_and_tiff_sources() -> None:
    cases = [
        ("run_01.DLIS", "dlis", "frame_channel"),
        ("field_print.CGM", "cgm", "vector_log"),
        ("image_log.TIFF", "tiff", "raster_log"),
        ("scan.tif", "tiff", "raster_log"),
    ]
    for file_name, source_format, category in cases:
        response = client.post("/api/wlv/ingestion/detect-format", json={"file_name": file_name})
        assert response.status_code == 200
        payload = response.json()
        assert payload["detected_format"] == source_format
        assert payload["source_category"] == category
        assert payload["is_supported"] is True


def test_detect_unknown_source_requires_review() -> None:
    response = client.post("/api/wlv/ingestion/detect-format", json={"file_name": "unknown.xyz"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["detected_format"] == "unknown"
    assert payload["source_category"] == "unknown"
    assert payload["is_supported"] is False
    assert payload["adapter_id"] == "unknown_source_review_adapter_v1"


def test_service_contract_is_format_neutral() -> None:
    service = WellLogSourceIngestionService()
    formats = {item.source_format for item in service.supported_formats()}
    assert WellLogSourceFormat.LAS in formats
    assert WellLogSourceFormat.DLIS in formats
    assert WellLogSourceFormat.CGM in formats
    assert WellLogSourceFormat.TIFF in formats
    assert WellLogSourceFormat.PDF in formats
