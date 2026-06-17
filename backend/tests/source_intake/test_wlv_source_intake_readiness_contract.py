from pathlib import Path
from app.source_intake.models import SourceIntakeBulkResolutionRequest, SourceIntakeResolutionAction, SourceIntakeResolutionDecision, SourceRepositoryCreateRequest
from app.source_intake.service import WlvSourceIntakeService

LAS = """~Version
VERS. 2.0
~Well
STRT.FT 100
STOP.FT 101
STEP.FT 1
NULL. -999.25
WELL. WELL
~Curve
DEPT.FT : Depth
GR.API : Gamma Ray
~ASCII
100 50
101 51
"""

def test_backend_readiness_blocks_unresolved_and_allows_resolved_warning(tmp_path: Path) -> None:
    root=tmp_path/'repo'; root.mkdir(); (root/'a.las').write_text(LAS)
    service=WlvSourceIntakeService(storage_path=tmp_path/'source.json')
    repo=service.create_repository(SourceRepositoryCreateRequest(root_path=str(root)))
    candidate=service.scan_repository(repo.repository_id).candidates[0]
    assert candidate.registration_eligible is False
    assert any(r.code == 'canonical_well_unresolved' for r in candidate.registration_block_reasons)
    service.resolve_candidates(SourceIntakeBulkResolutionRequest(decisions=[SourceIntakeResolutionDecision(
        occurrence_id=candidate.occurrence_id,
        action=SourceIntakeResolutionAction.METADATA_OVERRIDE,
        actor='reviewer', reason='confirmed', resolved_values={'well_name':'Forge 21-31','uwi':'2700190539'},
    )]))
    resolved=service.get_workbench().candidates[0]
    assert resolved.registration_eligible is True
    assert resolved.canonical_well_resolved is True
    assert resolved.hard_failure_count == 0


def test_readiness_survives_rescan_after_resolution(tmp_path: Path) -> None:
    root=tmp_path/'repo'; root.mkdir(); (root/'a.las').write_text(LAS)
    service=WlvSourceIntakeService(storage_path=tmp_path/'source.json')
    repo=service.create_repository(SourceRepositoryCreateRequest(root_path=str(root)))
    candidate=service.scan_repository(repo.repository_id).candidates[0]
    service.resolve_candidates(SourceIntakeBulkResolutionRequest(decisions=[SourceIntakeResolutionDecision(
        occurrence_id=candidate.occurrence_id, action=SourceIntakeResolutionAction.METADATA_OVERRIDE,
        actor='reviewer', reason='confirmed', resolved_values={'well_name':'Forge 21-31','uwi':'2700190539'},
    )]))
    rescanned=service.scan_repository(repo.repository_id).candidates[0]
    assert rescanned.registration_eligible is True
