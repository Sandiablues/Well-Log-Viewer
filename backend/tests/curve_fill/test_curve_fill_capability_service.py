from types import SimpleNamespace
from app.curve_fill_capabilities.service import CurveFillCapabilityService

def a(uid,curve,mnemonic,unit="ohm.m",name=None):
    return SimpleNamespace(assignment_uid=uid,managed_curve_uid=curve,managed_well_uid="well",observed_mnemonic=mnemonic,normalized_mnemonic=mnemonic,kr_curve_type_id=None,curve_family=None,display_name=name or mnemonic,unit=unit)
def session(assignments):
    t=SimpleNamespace(track_uid="track",managed_well_uid="well",assignments=tuple(assignments))
    return SimpleNamespace(managed_well_uid="well",session_uid="session",revision=7,tracks=(t,))
class Sessions:
    def __init__(self,s): self.s=s
    def get_session(self,_): return self.s

def test_resistivity_capabilities_are_backend_resolved():
    service=CurveFillCapabilityService(session_service=Sessions(session([a("owner","deep","RDEEP"),a("peer","shallow","RSHALLOW")])))
    result=service.get_capabilities("well","track","owner")
    assert next(m for m in result.modes if m.mode=="conditional").available
    assert next(p for p in result.presets if p.preset_id=="deep-over-shallow-resistivity").available
    assert not next(m for m in result.modes if m.mode=="crossover").available

def test_density_neutron_enables_only_approved_crossover():
    service=CurveFillCapabilityService(session_service=Sessions(session([a("owner","rhob","RHOB","g/cc"),a("peer","nphi","NPHI","v/v")])))
    result=service.get_capabilities("well","track","owner")
    cross=next(m for m in result.modes if m.mode=="crossover")
    assert cross.available and cross.reason is None
    preset=next(p for p in result.presets if p.preset_id=="density-neutron-crossover")
    assert preset.available and preset.overlay_policy_id=="density-neutron-overlay-v1"
    assert not next(m for m in result.modes if m.mode=="conditional").available

def test_cross_track_owner_is_rejected():
    service=CurveFillCapabilityService(session_service=Sessions(session([a("other","curve","GR","api")])))
    try: service.get_capabilities("well","track","missing")
    except ValueError as exc: assert "not assigned" in str(exc)
    else: raise AssertionError("expected ValueError")

def test_operand_eligibility_is_explicit_and_backend_owned():
    service=CurveFillCapabilityService(session_service=Sessions(session([a("owner","rhob","RHOB","g/cc"),a("peer","nphi","NPHI","v/v")])))
    result=service.get_capabilities("well","track","owner")
    peer=result.operands[0]
    assert peer.eligible_fill_modes == ("between", "crossover")
    assert peer.preset_ids == ("density-neutron-crossover",)
