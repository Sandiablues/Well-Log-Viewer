from fastapi import APIRouter, File, HTTPException, UploadFile
from .models import QuickViewPackage
from .service import QuickViewError, WdvQuickViewService
router=APIRouter(prefix='/api/wlv/v2/wdv',tags=['wdv-quick-view'])
_service=WdvQuickViewService()
@router.post('/quick-view',response_model=QuickViewPackage)
async def quick_view(file:UploadFile=File(...)):
    try:return _service.parse(filename=file.filename or '',content=await file.read())
    except QuickViewError as exc:raise HTTPException(status_code=422,detail=str(exc)) from exc
    finally:await file.close()
