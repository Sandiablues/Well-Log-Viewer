from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class CapabilityReason(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    code: str
    message: str

class FillModeCapability(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    mode: Literal["none","left","right","between","conditional","crossover"]
    label: str
    available: bool
    reason: CapabilityReason | None = None

class OperandCapability(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    operand_type: Literal["curve","constant_reference","stepped_reference","derived_reference"]
    identity: str
    display_name: str
    unit: str | None = None
    managed_well_uid: str
    track_uid: str
    available: bool = True
    eligible_fill_modes: tuple[Literal["between","conditional","crossover"], ...] = ()
    preset_ids: tuple[str, ...] = ()
    reason: CapabilityReason | None = None

class CurveFillPresetCapability(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    preset_id: str
    preset_revision: str
    label: str
    fill_mode: Literal["conditional","crossover"]
    available: bool
    default_condition: Literal["a_greater_than_b","a_less_than_b"] | None = None
    overlay_policy_id: str | None = None
    overlay_policy_revision: str | None = None
    default_fill: str
    default_opacity: float = Field(ge=0, le=1)
    deadband: float | None = Field(default=None, ge=0)
    minimum_interval: float | None = Field(default=None, ge=0)
    reason: CapabilityReason | None = None

class CurveFillCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    contract_version: Literal["curve_fill_capabilities_v1"] = "curve_fill_capabilities_v1"
    managed_well_uid: str
    session_uid: str
    session_revision: int
    track_uid: str
    owner_assignment_uid: str
    modes: tuple[FillModeCapability, ...]
    operands: tuple[OperandCapability, ...]
    presets: tuple[CurveFillPresetCapability, ...]
