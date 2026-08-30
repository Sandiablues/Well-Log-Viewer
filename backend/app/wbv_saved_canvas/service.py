from __future__ import annotations
import json, os, threading, uuid
from copy import deepcopy
from pathlib import Path
from typing import Any
from .models import WbvSavedCanvasCreateRequest, WbvSavedCanvasMetadata, WbvSavedCanvasRecord, WbvSavedCanvasUpdateRequest, utc_now_iso

class WbvSavedCanvasNotFound(KeyError):
    pass

class WbvSavedCanvasService:
    _lock = threading.RLock()
    def __init__(self, storage_path: Path | None = None) -> None:
        backend_root = Path(__file__).resolve().parents[2]
        self.storage_path = storage_path or backend_root / "data" / "wbv" / "saved_canvases_v1.json"
    @staticmethod
    def _empty() -> dict[str, Any]:
        return {"contract_version":"wbv_saved_canvases_v1","active_saved_canvas_uid":None,"saved_canvases":[],"recovery_state":{},"recovery_updated_at":None}
    def _read(self) -> dict[str, Any]:
        if not self.storage_path.exists(): return self._empty()
        try: raw=json.loads(self.storage_path.read_text())
        except Exception: return self._empty()
        if not isinstance(raw,dict) or raw.get("contract_version")!="wbv_saved_canvases_v1": return self._empty()
        if not isinstance(raw.get("saved_canvases"),list): raw["saved_canvases"]=[]
        return raw
    def _write(self,payload:dict[str,Any])->None:
        self.storage_path.parent.mkdir(parents=True,exist_ok=True)
        temp=self.storage_path.with_suffix(self.storage_path.suffix+f".tmp-{os.getpid()}-{uuid.uuid4().hex}")
        temp.write_text(json.dumps(payload,indent=2,sort_keys=True))
        os.replace(temp,self.storage_path)
    @staticmethod
    def _meta(item:dict[str,Any],active_uid:str|None)->WbvSavedCanvasMetadata:
        uid=str(item["saved_canvas_uid"]); active=uid==active_uid
        return WbvSavedCanvasMetadata(saved_canvas_uid=uid,name=str(item["name"]),created_at=str(item["created_at"]),updated_at=str(item["updated_at"]),schema_version=int(item.get("schema_version",1)),active=active,is_active=active)
    def list(self)->list[WbvSavedCanvasMetadata]:
        with self._lock:
            p=self._read(); a=p.get("active_saved_canvas_uid")
            return [self._meta(i,a) for i in p["saved_canvases"] if isinstance(i,dict) and i.get("saved_canvas_uid")]
    def get_recovery_state(self):
        from .models import WbvRecoveryStateRecord
        with self._lock:
            payload = self._read()
            raw = payload.get("recovery_state")
            state = deepcopy(raw) if isinstance(raw, dict) else {}
            return WbvRecoveryStateRecord(
                schema_version=1,
                updated_at=payload.get("recovery_updated_at"),
                state=state,
            )

    def update_recovery_state(self, state: dict[str, Any]):
        from .models import WbvRecoveryStateRecord
        safe_state = json.loads(json.dumps(state))
        now = utc_now_iso()
        with self._lock:
            payload = self._read()
            payload["recovery_state"] = safe_state
            payload["recovery_updated_at"] = now
            self._write(payload)
        return WbvRecoveryStateRecord(schema_version=1, updated_at=now, state=deepcopy(safe_state))

    def create(self,r:WbvSavedCanvasCreateRequest)->WbvSavedCanvasRecord:
        name=r.name.strip()
        if not name: raise ValueError("Saved Canvas name is required.")
        now=utc_now_iso(); uid=str(uuid.uuid4())
        item={"saved_canvas_uid":uid,"name":name,"created_at":now,"updated_at":now,"schema_version":1,"snapshot":json.loads(json.dumps(r.snapshot))}
        with self._lock:
            p=self._read(); p["saved_canvases"].append(item); p["active_saved_canvas_uid"]=uid; self._write(p)
        return self.get(uid)
    def get(self,uid:str)->WbvSavedCanvasRecord:
        with self._lock:
            p=self._read(); a=p.get("active_saved_canvas_uid")
            for i in p["saved_canvases"]:
                if isinstance(i,dict) and i.get("saved_canvas_uid")==uid:
                    m=self._meta(i,a)
                    return WbvSavedCanvasRecord(**m.model_dump(),snapshot=deepcopy(i.get("snapshot") or {}))
        raise WbvSavedCanvasNotFound(uid)
    def update(self,uid:str,r:WbvSavedCanvasUpdateRequest)->WbvSavedCanvasRecord:
        with self._lock:
            p=self._read(); found=False
            for n,i in enumerate(p["saved_canvases"]):
                if isinstance(i,dict) and i.get("saved_canvas_uid")==uid:
                    j=deepcopy(i); j["snapshot"]=json.loads(json.dumps(r.snapshot)); j["updated_at"]=utc_now_iso(); p["saved_canvases"][n]=j; found=True; break
            if not found: raise WbvSavedCanvasNotFound(uid)
            p["active_saved_canvas_uid"]=uid; self._write(p)
        return self.get(uid)
    def activate(self,uid:str)->WbvSavedCanvasRecord:
        with self._lock:
            p=self._read()
            if not any(isinstance(i,dict) and i.get("saved_canvas_uid")==uid for i in p["saved_canvases"]): raise WbvSavedCanvasNotFound(uid)
            p["active_saved_canvas_uid"]=uid; self._write(p)
        return self.get(uid)
    def delete(self,uid:str)->None:
        with self._lock:
            p=self._read(); before=len(p["saved_canvases"])
            p["saved_canvases"]=[i for i in p["saved_canvases"] if not (isinstance(i,dict) and i.get("saved_canvas_uid")==uid)]
            if len(p["saved_canvases"])==before: raise WbvSavedCanvasNotFound(uid)
            if p.get("active_saved_canvas_uid")==uid: p["active_saved_canvas_uid"]=None
            self._write(p)
