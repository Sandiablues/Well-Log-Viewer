"""Backend-owned Curve Fill capability contracts.

The frontend receives only resolved, assignment-addressed choices and reasons.
It must not infer unit compatibility, crossover eligibility, or policy identity.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.curve_fill_v2.models import Boundary, Comparison, RuleType
from app.curve_fill_v2.policy import GENERIC_VISUAL_CROSSOVER_V1
from app.curve_fill_v2.paint_catalog import PATTERNS, load_rasters
from app.identity.wdv_contract_v2 import WdvCanonicalAssignment
from app.wdv_session.canonical_service import CanonicalWdvSessionService


class CurveFillCapabilityError(ValueError):
    pass


class CurveFillOperandCapability(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    assignment_uid: str
    managed_curve_uid: str
    display_name: str
    mnemonic: str
    curve_family: str | None = None
    unit: str | None = None
    eligible: bool
    disable_reason: str | None = None


class CurveFillModeCapability(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    rule_type: RuleType
    eligible: bool
    disable_reason: str | None = None
    comparisons: tuple[Comparison, ...] = ()
    boundaries: tuple[Boundary, ...] = ()
    overlay_policy_uid: str | None = None
    overlay_policy_revision: str | None = None
    curve_b_operands: tuple[CurveFillOperandCapability, ...] = ()


class CurveFillPatternCapability(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    pattern_uid: str
    label: str


class CurveFillRasterCapability(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    raster_asset_uid: str
    label: str
    top_depth: float
    base_depth: float
    depth_unit: str


class CurveFillPaintCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    appearances: tuple[str, ...] = ("solid", "pattern", "raster")
    patterns: tuple[CurveFillPatternCapability, ...] = ()
    rasters: tuple[CurveFillRasterCapability, ...] = ()


class CurveFillCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    contract_version: str = "wdv_curve_fill_capabilities_v2"
    managed_well_uid: str
    session_revision: int = Field(ge=0)
    track_uid: str
    curve_a_assignment_uid: str
    curve_a_mnemonic: str
    modes: tuple[CurveFillModeCapability, ...]
    paint: CurveFillPaintCapabilities


class CanonicalCurveFillCapabilityService:
    def __init__(self, session_service: CanonicalWdvSessionService | None = None) -> None:
        self.session_service = session_service or CanonicalWdvSessionService()

    @staticmethod
    def _operand(assignment: WdvCanonicalAssignment, *, eligible: bool, reason: str | None = None) -> CurveFillOperandCapability:
        return CurveFillOperandCapability(
            assignment_uid=assignment.assignment_uid,
            managed_curve_uid=assignment.managed_curve_uid,
            display_name=assignment.display_name,
            mnemonic=assignment.normalized_mnemonic or assignment.observed_mnemonic,
            curve_family=assignment.curve_family,
            unit=assignment.unit,
            eligible=eligible,
            disable_reason=reason,
        )

    def get_capabilities(self, managed_well_uid: str, *, track_uid: str, curve_a_assignment_uid: str) -> CurveFillCapabilities:
        session = self.session_service.get_session(managed_well_uid)
        track = next((item for item in session.tracks if item.track_uid == track_uid), None)
        if track is None or track.track_type != "curve":
            raise CurveFillCapabilityError("Curve Fill capabilities require a curve track")
        assignment_a = next((item for item in track.assignments if item.assignment_uid == curve_a_assignment_uid), None)
        if assignment_a is None:
            raise CurveFillCapabilityError("Curve A assignment is not in the target track")

        others = tuple(item for item in track.assignments if item.assignment_uid != assignment_a.assignment_uid)
        operands = tuple(self._operand(item, eligible=True) for item in others)
        has_curve_b = bool(operands)
        modes = (
            CurveFillModeCapability(
                rule_type=RuleType.TO_BOUNDARY,
                eligible=True,
                boundaries=(Boundary.LEFT, Boundary.RIGHT),
            ),
            CurveFillModeCapability(
                rule_type=RuleType.BETWEEN_CURVES,
                eligible=has_curve_b,
                disable_reason=None if has_curve_b else "no_curve_b_assignment",
                curve_b_operands=operands,
            ),
            CurveFillModeCapability(
                rule_type=RuleType.CONDITIONAL,
                eligible=has_curve_b,
                disable_reason=None if has_curve_b else "no_curve_b_assignment",
                comparisons=(Comparison.GREATER_THAN, Comparison.LESS_THAN),
                curve_b_operands=operands,
            ),
            CurveFillModeCapability(
                rule_type=RuleType.CROSSOVER,
                eligible=has_curve_b,
                disable_reason=None if has_curve_b else "no_curve_b_assignment",
                overlay_policy_uid=GENERIC_VISUAL_CROSSOVER_V1.uid,
                overlay_policy_revision=GENERIC_VISUAL_CROSSOVER_V1.revision,
                curve_b_operands=operands,
            ),
        )
        return CurveFillCapabilities(
            managed_well_uid=managed_well_uid,
            session_revision=session.revision,
            track_uid=track_uid,
            curve_a_assignment_uid=curve_a_assignment_uid,
            curve_a_mnemonic=assignment_a.normalized_mnemonic or assignment_a.observed_mnemonic,
            modes=modes,
            paint=CurveFillPaintCapabilities(
                patterns=tuple(CurveFillPatternCapability(pattern_uid=p.pattern_uid, label=p.label) for p in PATTERNS),
                rasters=tuple(CurveFillRasterCapability(
                    raster_asset_uid=r.raster_asset_uid, label=r.label, top_depth=r.top_depth, base_depth=r.base_depth, depth_unit=r.depth_unit
                ) for r in load_rasters(managed_well_uid)),
            ),
        )
