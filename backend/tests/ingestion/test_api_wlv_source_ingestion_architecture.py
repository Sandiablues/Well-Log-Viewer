from fastapi.testclient import TestClient

from app.main import app
from app.ingestion.models import WellLogSourceFormat
from app.ingestion.service import WellLogSourceIngestionService

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



def test_scan_well_folder_classifies_candidate_files(tmp_path) -> None:
    (tmp_path / "curves").mkdir()
    (tmp_path / "images").mkdir()
    (tmp_path / "reports").mkdir()
    (tmp_path / "curves" / "forge_21_31.las").write_text("~Version\n", encoding="utf-8")
    (tmp_path / "curves" / "run_01.dlis").write_text("dlis placeholder", encoding="utf-8")
    (tmp_path / "images" / "fmi.tiff").write_bytes(b"tiff placeholder")
    (tmp_path / "reports" / "final_report.pdf").write_bytes(b"pdf placeholder")
    (tmp_path / "notes.txt").write_text("unknown", encoding="utf-8")

    response = client.post(
        "/api/wlv/ingestion/well-folders/scan",
        json={"parent_path": str(tmp_path), "include_subfolders": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["action"] == "scanned"
    assert payload["summary"]["candidate_count"] == 5
    assert payload["summary"]["las_count"] == 1
    assert payload["summary"]["dlis_count"] == 1
    assert payload["summary"]["raster_log_count"] == 1
    assert payload["summary"]["document_count"] == 1
    assert payload["summary"]["unknown_count"] == 1
    roles = {candidate["candidate_role"] for candidate in payload["candidates"]}
    assert "numeric_curve_las" in roles
    assert "frame_channel_dlis" in roles
    assert "raster_log_tiff" in roles
    assert "pdf_document_or_field_print" in roles
    assert "review_required_unknown" in roles
    assert payload["notes"][0].startswith("Backend-owned folder scan only")


def test_scan_well_folder_root_only_excludes_subfolders(tmp_path) -> None:
    (tmp_path / "root.las").write_text("~Version\n", encoding="utf-8")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "nested.las").write_text("~Version\n", encoding="utf-8")

    response = client.post(
        "/api/wlv/ingestion/well-folders/scan",
        json={"parent_path": str(tmp_path), "include_subfolders": False},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["candidate_count"] == 1
    assert payload["candidates"][0]["relative_path"] == "root.las"


def test_scan_well_folder_rejects_missing_folder(tmp_path) -> None:
    response = client.post(
        "/api/wlv/ingestion/well-folders/scan",
        json={"parent_path": str(tmp_path / "missing")},
    )

    assert response.status_code == 400
    assert "does not exist" in response.json()["detail"]
