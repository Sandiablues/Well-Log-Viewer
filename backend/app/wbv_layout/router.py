from fastapi import APIRouter,Depends,HTTPException
from .models import WbvLayoutCommandRequest,WbvTrackLayout
from .service import WbvTrackLayoutService
router=APIRouter(prefix="/api/wlv/wbv/layouts",tags=["wlv-wbv-layouts"])
_service=WbvTrackLayoutService()
def get_service(): return _service
@router.get("/wells/{managed_well_uid}",response_model=WbvTrackLayout)
def get_layout(managed_well_uid:str,service=Depends(get_service)):
 try:return service.get_layout(managed_well_uid)
 except ValueError as e:raise HTTPException(422,str(e)) from e
@router.post("/wells/{managed_well_uid}/commands",response_model=WbvTrackLayout)
def command(managed_well_uid:str,request:WbvLayoutCommandRequest,service=Depends(get_service)):
 try:return service.command(managed_well_uid,request)
 except ValueError as e:raise HTTPException(409 if str(e).startswith("Stale") else 422,str(e)) from e
