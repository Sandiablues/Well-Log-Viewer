from __future__ import annotations
from app.identity.wdv_contract_v2 import WdvCanonicalAssignment
from app.wdv_session.canonical_service import CanonicalWdvSessionService
from app.knowledge.curve_fill_policy_seed import APPROVED_CURVE_FILL_POLICY_SEEDS
from .models import CapabilityReason, CurveFillCapabilities, CurveFillPresetCapability, FillModeCapability, OperandCapability

def _keys(a: WdvCanonicalAssignment) -> set[str]:
    return {str(v).strip().upper() for v in (a.observed_mnemonic,a.normalized_mnemonic,a.kr_curve_type_id,a.curve_family) if v}

def _matches(a: WdvCanonicalAssignment, accepted: set[str]) -> bool:
    keys=_keys(a)
    return bool(keys & accepted) or any(any(token in key for token in accepted) for key in keys)

class CurveFillCapabilityService:
    def __init__(self, session_service: CanonicalWdvSessionService | None=None) -> None:
        self.session_service=session_service or CanonicalWdvSessionService()

    def get_capabilities(self, managed_well_uid: str, track_uid: str, owner_assignment_uid: str) -> CurveFillCapabilities:
        session=self.session_service.get_session(managed_well_uid)
        track=next((t for t in session.tracks if t.track_uid==track_uid),None)
        if track is None: raise ValueError("track_uid is not present in the canonical session")
        owner=next((a for a in track.assignments if a.assignment_uid==owner_assignment_uid),None)
        if owner is None: raise ValueError("owner_assignment_uid is not assigned to track_uid")
        if track.managed_well_uid != owner.managed_well_uid:
            raise ValueError("track and owner assignment have incompatible well ownership")
        peers=[a for a in track.assignments if a.assignment_uid != owner.assignment_uid]
        compatible_peers=[a for a in peers if owner.unit and a.unit and owner.unit.strip().lower()==a.unit.strip().lower()]
        policy_matches: dict[str, list[str]] = {}
        for peer in peers:
            matched=[]
            for policy in APPROVED_CURVE_FILL_POLICY_SEEDS:
                if (_matches(owner,policy.operand_a_aliases) and _matches(peer,policy.operand_b_aliases)) or (_matches(owner,policy.operand_b_aliases) and _matches(peer,policy.operand_a_aliases)):
                    matched.append(policy.preset_id)
            policy_matches[peer.assignment_uid]=matched
        crossover_peer=next((a for a in peers if "density-neutron-crossover" in policy_matches[a.assignment_uid]),None)
        operands=[]
        for peer in peers:
            eligible=["between"]
            if peer in compatible_peers:
                eligible.append("conditional")
            if "density-neutron-crossover" in policy_matches[peer.assignment_uid]:
                eligible.append("crossover")
            operands.append(OperandCapability(
                operand_type="curve",
                identity=peer.managed_curve_uid,
                display_name=peer.display_name,
                unit=peer.unit,
                managed_well_uid=peer.managed_well_uid,
                track_uid=track.track_uid,
                eligible_fill_modes=tuple(eligible),
                preset_ids=tuple(policy_matches[peer.assignment_uid]),
            ))
        operands=tuple(operands)
        modes=(
            FillModeCapability(mode="none",label="None",available=True),
            FillModeCapability(mode="left",label="Fill left of curve",available=True),
            FillModeCapability(mode="right",label="Fill right of curve",available=True),
            FillModeCapability(mode="between",label="Fill between curves",available=bool(peers),reason=None if peers else CapabilityReason(code="comparison_operand_missing",message="Fill between curves requires another curve in the same track.")),
            FillModeCapability(mode="conditional",label="Conditional Fill",available=bool(compatible_peers),reason=None if compatible_peers else CapabilityReason(code="compatible_operand_missing",message="Conditional Fill requires a same-track operand with compatible engineering units or an approved reference.")),
            FillModeCapability(mode="crossover",label="Crossover Fill",available=crossover_peer is not None,reason=None if crossover_peer else CapabilityReason(code="approved_overlay_missing",message="Crossover fill requires an approved paired-curve overlay.")),
        )
        preset_caps=[]
        for p in APPROVED_CURVE_FILL_POLICY_SEEDS:
            peer=next((a for a in peers if (_matches(owner,p.operand_a_aliases) and _matches(a,p.operand_b_aliases)) or (_matches(owner,p.operand_b_aliases) and _matches(a,p.operand_a_aliases))),None)
            reason=None if peer else CapabilityReason(code="preset_operands_unavailable",message=f"{p.label} requires its approved curve pair in the same track.")
            preset_caps.append(CurveFillPresetCapability(preset_id=p.preset_id,preset_revision=p.revision,label=p.label,fill_mode=p.fill_mode,available=peer is not None,default_condition=p.default_condition,overlay_policy_id=p.overlay_policy_id,overlay_policy_revision=p.revision if p.overlay_policy_id else None,default_fill=p.default_fill,default_opacity=p.default_opacity,deadband=p.deadband,reason=reason))
        return CurveFillCapabilities(managed_well_uid=session.managed_well_uid,session_uid=session.session_uid,session_revision=session.revision,track_uid=track.track_uid,owner_assignment_uid=owner.assignment_uid,modes=modes,operands=operands,presets=tuple(preset_caps))
