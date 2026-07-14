from pathlib import Path


def test_source_intake_registration_response_does_not_rebuild_full_workbench():
    source = Path("app/source_intake/service.py").read_text(encoding="utf-8")
    start = source.index("def register_candidates(")
    end = source.index("def _registration_block_reason(", start)
    block = source[start:end]

    assert "workbench=None" in block
    assert "workbench=self.get_workbench()" not in block


def test_frontend_refreshes_wsi_and_mwd_after_compact_promotion_response():
    source = Path("../frontend/src/wells/source-intake/SourceIntakeWorkbench.tsx").read_text(
        encoding="utf-8"
    )
    start = source.index("const handleRegister")
    end = source.index("const setCandidateSelected", start)
    block = source[start:end]

    assert "await Promise.all([loadWorkbench(), loadManagedWells()]);" in block
    assert "setWorkbench(response.workbench)" not in block
