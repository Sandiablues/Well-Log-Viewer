from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class QuickViewSample(BaseModel):
    model_config=ConfigDict(extra='forbid', frozen=True)
    depth: float
    value: float

class QuickViewCurve(BaseModel):
    model_config=ConfigDict(extra='forbid', frozen=True)
    curve_id: str
    mnemonic: str
    description: str | None = None
    unit_label: str | None = None
    scale_type: Literal['linear','logarithmic'] = 'linear'
    scale_direction: Literal['normal','reverse'] = 'normal'
    scale_min: float
    scale_max: float
    review_required: bool = False
    scale_source: str = 'observed_p05_p95'
    catalogue_status: str = 'Unknown'
    scale_decision: str = 'Generic fallback'
    source_mnemonic: str | None = None
    source_description: str | None = None
    source_unit: str | None = None
    kr_catalogue_status: str | None = None
    kr_canonical_curve: str | None = None
    kr_family: str | None = None
    kr_unit_status: str | None = None
    display_unit: str | None = None
    display_transform: str | None = None
    display_range: tuple[float, float] | None = None
    scale_reason: str | None = None
    samples: tuple[QuickViewSample, ...]

class QuickViewTrack(BaseModel):
    model_config=ConfigDict(extra='forbid', frozen=True)
    track_id: str
    title: str
    scale_type: Literal['linear','logarithmic']
    curves: tuple[QuickViewCurve, ...]

class QuickViewPackage(BaseModel):
    model_config=ConfigDict(extra='forbid', frozen=True)
    contract_kind: Literal['wdv_quick_view']='wdv_quick_view'
    contract_version: Literal['wdv_quick_view_v1']='wdv_quick_view_v1'
    filename: str
    source_format: Literal['LAS','DLIS']
    fingerprint: str
    well_name: str='Not supplied'
    depth_min: float
    depth_max: float
    depth_unit_label: str | None = None
    tracks: tuple[QuickViewTrack, ...]
    warnings: tuple[str, ...]=()
