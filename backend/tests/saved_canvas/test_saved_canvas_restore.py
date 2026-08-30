from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.identity import new_uuid7_str
from app.identity.wdv_contract_v2 import WdvCanonicalSession, WdvCanonicalTrack
from app.saved_canvas.models import SavedCanvasCreateRequest, SavedCanvasRestoreRequest
from app.saved_canvas.repository import SavedCanvasRepository
from app.saved_canvas.service import (
    SavedCanvasMissingDataError,
    SavedCanvasRestoreInProgress,
    SavedCanvasService,
    SavedCanvasWorkspaceConfigurationMismatch,
)
from app.wdv_session.canonical_service import CanonicalSessionRevisionConflict
from app.wdv_workspace.models import (
    WdvSavedDepthViewport,
    WdvSavedViewState,
    WdvSavedViewportTieGroup,
)


class FakeGroup:
    def __init__(self, items=()): self.items=list(items)

class FakeRecord:
    def __init__(self, well_uid, items=()):
        self.managed_well_uid=well_uid; self.wmdp_available=True; self.product_groups=[FakeGroup(items)]

class FakeInventory:
    def __init__(self, well_uid, records, unit='m'):
        self.revision=10; self.active_well_uid=well_uid; self.unit=unit; self.records=records
    def get_wdv_workspace(self):
        return SimpleNamespace(workspace_id='default', revision=self.revision, active_managed_well_uid=self.active_well_uid, common_depth_unit=self.unit)
    def list_wells(self): return list(self.records)

class FakeWorkspaceService:
    def validate_session(self, managed_well_uid, session):
        if str(session.managed_well_uid)!=str(managed_well_uid): raise ValueError('wrong working well')
        return session

class FakeSessionService:
    def __init__(self, session): self.session=session; self.replace_calls=0
    def get_session(self, _): return self.session
    def replace_session_and_committed_view_transactionally(self, managed_well_uid, *, expected_revision, session, view_state, validator=None):
        if self.session.revision != expected_revision: raise CanonicalSessionRevisionConflict('stale')
        candidate=session.model_copy(update={'revision':expected_revision+1})
        if validator: validator(candidate)
        self.replace_calls += 1; self.session=candidate
        return candidate, {'committed_at':'2026-08-16T10:00:00+00:00','session_revision':candidate.revision,'view_revision':0,'view_state':view_state}

class BlockingSessionService(FakeSessionService):
    def __init__(self, session, entered, release): super().__init__(session); self.entered=entered; self.release=release
    def replace_session_and_committed_view_transactionally(self,*a,**kw):
        self.entered.set(); self.release.wait(timeout=3); return super().replace_session_and_committed_view_transactionally(*a,**kw)

def make_state(width=100):
    well=new_uuid7_str()
    a=WdvCanonicalTrack(track_uid=new_uuid7_str(),managed_well_uid=well,track_number=0,track_name='A',track_type='depth',width_px=width)
    b=WdvCanonicalTrack(track_uid=new_uuid7_str(),managed_well_uid=well,track_number=1,track_name='B',track_type='depth',width_px=width+10)
    session=WdvCanonicalSession(session_uid=new_uuid7_str(),managed_well_uid=well,revision=5,state_status='active',tracks=(a,b),updated_at='2026-08-16T09:00:00+00:00')
    tie=WdvSavedDepthViewport(min=1000,max=1100); locked=WdvSavedDepthViewport(min=1020,max=1080)
    view=WdvSavedViewState(depth_unit='m',global_viewport=tie,locked_track_uids=(b.track_uid,),locked_viewports_by_track_uid={b.track_uid:locked},track_viewports_by_track_uid={a.track_uid:tie,b.track_uid:locked},viewport_tie_groups=(WdvSavedViewportTieGroup(group_id='g',leader_track_uid=a.track_uid,member_track_uids=(a.track_uid,b.track_uid),viewport=tie),),viewport_tie_suspended_track_uids=(b.track_uid,),presentation_state={'track_order_uids':[a.track_uid,b.track_uid],'track_widths_by_uid':{a.track_uid:width,b.track_uid:width+10}})
    return well,session,view

def make_service(tmp_path, session, view, well, session_service=None):
    inv=FakeInventory(well,[FakeRecord(well)]); ss=session_service or FakeSessionService(session); repo=SavedCanvasRepository(tmp_path/'saved.json')
    svc=SavedCanvasService(inventory_service=inv,session_service=ss,repository=repo,workspace_service=FakeWorkspaceService())
    saved=svc.create('default',SavedCanvasCreateRequest(name='A',expected_workspace_revision=10,view_state=view))
    return svc,inv,ss,saved

def test_restore_round_trips_session_lock_tie_and_presentation(tmp_path: Path):
    well,session,view=make_state(100); svc,inv,ss,saved=make_service(tmp_path,session,view,well)
    ss.session=session.model_copy(update={'revision':9,'tracks':tuple(t.model_copy(update={'width_px':300+i}) for i,t in enumerate(session.tracks))})
    result=svc.restore('default',saved.saved_canvas_uid,SavedCanvasRestoreRequest(expected_workspace_revision=10,expected_session_revision=9))
    assert [t.width_px for t in result.session.tracks]==[100,110]
    assert result.session.revision==10 and result.view_revision==0
    assert result.view_state.locked_track_uids==view.locked_track_uids
    assert result.view_state.viewport_tie_groups==view.viewport_tie_groups
    assert result.view_state.presentation_state==view.presentation_state
    assert ss.replace_calls==1

def test_nonsequential_a_c_b_a_restore_is_exact(tmp_path: Path):
    well,session,view=make_state(100); inv=FakeInventory(well,[FakeRecord(well)]); ss=FakeSessionService(session); repo=SavedCanvasRepository(tmp_path/'saved.json'); svc=SavedCanvasService(inventory_service=inv,session_service=ss,repository=repo,workspace_service=FakeWorkspaceService())
    saves=[]
    for name,width in [('A',100),('B',200),('C',300)]:
        tracks=tuple(t.model_copy(update={'width_px':width+i*10}) for i,t in enumerate(session.tracks)); ss.session=session.model_copy(update={'revision':5+len(saves),'tracks':tracks}); v=view.model_copy(update={'presentation_state':{'marker':name}}); saves.append(svc.create('default',SavedCanvasCreateRequest(name=name,expected_workspace_revision=10,view_state=v)))
    expected={'A':[100,110],'B':[200,210],'C':[300,310]}; ss.session=session.model_copy(update={'revision':20})
    for name,index in [('A',0),('C',2),('B',1),('A',0)]:
        r=svc.restore('default',saves[index].saved_canvas_uid,SavedCanvasRestoreRequest(expected_workspace_revision=10,expected_session_revision=ss.session.revision)); assert [t.width_px for t in r.session.tracks]==expected[name]; assert r.view_state.presentation_state['marker']==name

def test_missing_data_aborts_before_mutation(tmp_path: Path):
    well,session,view=make_state(); svc,inv,ss,saved=make_service(tmp_path,session,view,well); inv.records=[]
    before=ss.session
    with pytest.raises(SavedCanvasMissingDataError): svc.restore('default',saved.saved_canvas_uid,SavedCanvasRestoreRequest(expected_workspace_revision=10,expected_session_revision=5))
    assert ss.session==before and ss.replace_calls==0

def test_depth_unit_mismatch_aborts_before_mutation(tmp_path: Path):
    well,session,view=make_state(); svc,inv,ss,saved=make_service(tmp_path,session,view,well); inv.unit='ft'
    with pytest.raises(SavedCanvasWorkspaceConfigurationMismatch): svc.restore('default',saved.saved_canvas_uid,SavedCanvasRestoreRequest(expected_workspace_revision=10,expected_session_revision=5))
    assert ss.replace_calls==0

def test_restore_is_single_flight(tmp_path: Path):
    well,session,view=make_state(); entered=threading.Event(); release=threading.Event(); ss=BlockingSessionService(session,entered,release); svc,inv,ss,saved=make_service(tmp_path,session,view,well,ss); errors=[]
    def first():
        try: svc.restore('default',saved.saved_canvas_uid,SavedCanvasRestoreRequest(expected_workspace_revision=10,expected_session_revision=5))
        except Exception as exc: errors.append(exc)
    th=threading.Thread(target=first); th.start(); assert entered.wait(timeout=2)
    with pytest.raises(SavedCanvasRestoreInProgress): svc.restore('default',saved.saved_canvas_uid,SavedCanvasRestoreRequest(expected_workspace_revision=10,expected_session_revision=5))
    release.set(); th.join(timeout=2); assert not errors
