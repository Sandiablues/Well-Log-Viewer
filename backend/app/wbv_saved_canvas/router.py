from fastapi import APIRouter, HTTPException
from .models import WbvRecoveryStateRecord, WbvRecoveryStateRequest, WbvSavedCanvasCreateRequest, WbvSavedCanvasMetadata, WbvSavedCanvasRecord, WbvSavedCanvasUpdateRequest
from .service import WbvSavedCanvasNotFound, WbvSavedCanvasService
router=APIRouter(prefix="/api/wlv/wbv/saved-canvases",tags=["wbv-saved-canvases"])
_service=WbvSavedCanvasService()
def nf(uid:str): return HTTPException(status_code=404,detail=f"WBV Saved Canvas not found: {uid}")
@router.get("",response_model=list[WbvSavedCanvasMetadata])
def list_saved_canvases(): return _service.list()
@router.get("/recovery-state",response_model=WbvRecoveryStateRecord)
def get_recovery_state():
    return _service.get_recovery_state()

@router.put("/recovery-state",response_model=WbvRecoveryStateRecord)
def update_recovery_state(request:WbvRecoveryStateRequest):
    return _service.update_recovery_state(request.state)

@router.post("",response_model=WbvSavedCanvasRecord)
def create_saved_canvas(request:WbvSavedCanvasCreateRequest):
    try: return _service.create(request)
    except ValueError as exc: raise HTTPException(status_code=422,detail=str(exc)) from exc
@router.get("/{saved_canvas_uid}",response_model=WbvSavedCanvasRecord)
def get_saved_canvas(saved_canvas_uid:str):
    try: return _service.get(saved_canvas_uid)
    except WbvSavedCanvasNotFound as exc: raise nf(saved_canvas_uid) from exc
@router.put("/{saved_canvas_uid}",response_model=WbvSavedCanvasRecord)
def update_saved_canvas(saved_canvas_uid:str,request:WbvSavedCanvasUpdateRequest):
    try: return _service.update(saved_canvas_uid,request)
    except WbvSavedCanvasNotFound as exc: raise nf(saved_canvas_uid) from exc
@router.post("/{saved_canvas_uid}/restore",response_model=WbvSavedCanvasRecord)
def restore_saved_canvas(saved_canvas_uid:str):
    try: return _service.activate(saved_canvas_uid)
    except WbvSavedCanvasNotFound as exc: raise nf(saved_canvas_uid) from exc
@router.delete("/{saved_canvas_uid}")
def delete_saved_canvas(saved_canvas_uid:str):
    try: _service.delete(saved_canvas_uid)
    except WbvSavedCanvasNotFound as exc: raise nf(saved_canvas_uid) from exc
    return {"ok":True,"saved_canvas_uid":saved_canvas_uid}
