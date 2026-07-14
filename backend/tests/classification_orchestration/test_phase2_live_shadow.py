from app.classification_orchestration import live_shadow_observer as observer

def test_report_path_override(monkeypatch,tmp_path):
    target=tmp_path/"report.jsonl"; monkeypatch.setenv("WLV_CLASSIFICATION_SHADOW_REPORT_PATH",str(target)); assert observer._report_path()==target
