from fastapi import APIRouter, Depends, HTTPException, Query
from .models import CurveFillCapabilities
from .service import CurveFillCapabilityService
router=APIRouter(prefix="/api/wlv/v2/wdv/curve-fill-capabilities",tags=["wlv-wdv-curve-fill-capabilities"])
def get_service()->CurveFillCapabilityService: return CurveFillCapabilityService()
@router.get("/{managed_well_uid}",response_model=CurveFillCapabilities)
def get_capabilities(managed_well_uid:str,track_uid:str=Query(...),owner_assignment_uid:str=Query(...),service:CurveFillCapabilityService=Depends(get_service))->CurveFillCapabilities:
    try: return service.get_capabilities(managed_well_uid,track_uid,owner_assignment_uid)
    except ValueError as exc: raise HTTPException(status_code=422,detail=str(exc)) from exc
