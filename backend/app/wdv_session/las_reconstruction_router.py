"""API for backend-owned complete-LAS WDV reconstruction."""
from fastapi import APIRouter, Depends, HTTPException, Query

from app.inventory.repository import ManagedWellNotFoundError
from app.wdv_session.las_reconstruction_models import LasReconstructionPlan, LasSourceList, LogImageSourceList, LoadCompleteLasCommand, LoadCompleteLasResponse
from app.wdv_session.las_reconstruction_service import LasReconstructionError, LasReconstructionService
from app.wdv_session.canonical_service import CanonicalSessionRevisionConflict, CanonicalSessionCommandReplayConflict

router = APIRouter(prefix="/api/wlv/v2/wdv/las", tags=["wlv-complete-las-reconstruction"])

def get_service() -> LasReconstructionService:
    return LasReconstructionService()

def translate(call):
    try:
        return call()
    except ManagedWellNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (CanonicalSessionRevisionConflict, CanonicalSessionCommandReplayConflict) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (LasReconstructionError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

@router.get("/{managed_well_uid}/sources", response_model=LasSourceList)
def get_sources(managed_well_uid: str, service: LasReconstructionService = Depends(get_service)):
    return translate(lambda: service.list_sources(managed_well_uid))

@router.get("/{managed_well_uid}/log-images", response_model=LogImageSourceList)
def get_log_images(managed_well_uid: str, service: LasReconstructionService = Depends(get_service)):
    return translate(lambda: service.list_log_images(managed_well_uid))

@router.get("/{managed_well_uid}/plan", response_model=LasReconstructionPlan)
def get_plan(managed_well_uid: str, source_id: str = Query(..., min_length=1), service: LasReconstructionService = Depends(get_service)):
    return translate(lambda: service.build_plan(managed_well_uid, source_id))

@router.post("/{managed_well_uid}/load-complete", response_model=LoadCompleteLasResponse)
def load_complete(managed_well_uid: str, command: LoadCompleteLasCommand, service: LasReconstructionService = Depends(get_service)):
    return translate(lambda: service.load_complete_las(managed_well_uid, command))
