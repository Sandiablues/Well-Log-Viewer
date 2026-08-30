import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
import app.knowledge.api_lithology as api


def test_lithology_crud_round_trip(tmp_path: Path, monkeypatch) -> None:
    source_dir = Path("data/knowledge/lithology")
    target_dir = tmp_path / "lithology"
    target_dir.mkdir()
    (target_dir / "patterns").mkdir()
    for name in ("lithology-catalogue.json", "lithology-colour-palette.json"):
        (target_dir / name).write_bytes((source_dir / name).read_bytes())
    pattern = next((source_dir / "patterns").glob("*.svg"))
    (target_dir / "patterns" / pattern.name).write_bytes(pattern.read_bytes())

    monkeypatch.setattr(api, "_DATA_DIR", target_dir)
    monkeypatch.setattr(api, "_CATALOGUE", target_dir / "lithology-catalogue.json")
    monkeypatch.setattr(api, "_PALETTE", target_dir / "lithology-colour-palette.json")
    monkeypatch.setattr(api, "_PATTERN_DIR", target_dir / "patterns")
    monkeypatch.setattr(api, "_AUDIT_LOG", target_dir / "lithology-catalogue-audit.jsonl")
    monkeypatch.setattr(api, "_BACKUP_DIR", target_dir / "backups")
    api._invalidate()

    client = TestClient(app)
    payload = {
        "id": "lithology:custom-test",
        "fgdcCode": 99001,
        "name": "Custom Test",
        "formalName": "Custom Test Lithology",
        "description": "Test lithology entry.",
        "category": "custom",
        "subcategory": "test",
        "aliases": ["test rock"],
        "pattern": {"asset": f"patterns/{pattern.name}", "defaultScale": 1},
        "defaultBackground": "#D9D9D9",
        "defaultPattern": "#111111",
        "sourceStandard": "CUSTOM",
        "sourceSeries": "test",
        "sourceRepository": "pytest",
        "status": "active",
    }
    created = client.post("/api/wlv/knowledge/lithology/entries", json=payload)
    assert created.status_code == 201, created.text
    assert created.json()["name"] == "Custom Test"

    payload["name"] = "Custom Test Updated"
    updated = client.put("/api/wlv/knowledge/lithology/entries/lithology:custom-test", json=payload)
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Custom Test Updated"

    deleted = client.delete("/api/wlv/knowledge/lithology/entries/lithology:custom-test")
    assert deleted.status_code == 204
    document = json.loads((target_dir / "lithology-catalogue.json").read_text())
    assert not any(item["id"] == "lithology:custom-test" for item in document["entries"])
    assert (target_dir / "patterns" / pattern.name).is_file()
    assert (target_dir / "lithology-catalogue-audit.jsonl").is_file()
    assert list((target_dir / "backups").glob("*.json"))
