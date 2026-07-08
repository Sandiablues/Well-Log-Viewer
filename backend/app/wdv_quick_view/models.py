from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class QuickViewMetadataValue(BaseModel):
    model_config=ConfigDict(extra='forbid', frozen=True)
    value: str | int | float | bool | None = None
    unit: str | None = None
    source: str | None = None
    confidence: Literal['explicit','derived','not_supplied','unresolved'] = 'not_supplied'

class QuickViewFileInfo(BaseModel):
    model_config=ConfigDict(extra='forbid', frozen=True)
    source_file_name: QuickViewMetadataValue
    file_type: QuickViewMetadataValue
    format_version: QuickViewMetadataValue
    file_size_bytes: QuickViewMetadataValue
    content_fingerprint: QuickViewMetadataValue
    parser_name: QuickViewMetadataValue
    parser_status: QuickViewMetadataValue
    temporary_only: QuickViewMetadataValue

class QuickViewWellInfo(BaseModel):
    model_config=ConfigDict(extra='forbid', frozen=True)
    well_name: QuickViewMetadataValue
    well_id: QuickViewMetadataValue
    uwi: QuickViewMetadataValue
    api: QuickViewMetadataValue
    field: QuickViewMetadataValue
    operator: QuickViewMetadataValue
    country: QuickViewMetadataValue
    state_province: QuickViewMetadataValue
    county_area: QuickViewMetadataValue
    latitude: QuickViewMetadataValue
    longitude: QuickViewMetadataValue
    x: QuickViewMetadataValue
    y: QuickViewMetadataValue
    datum: QuickViewMetadataValue

class QuickViewIndexInfo(BaseModel):
    model_config=ConfigDict(extra='forbid', frozen=True)
    source_mnemonic: QuickViewMetadataValue
    source_unit: QuickViewMetadataValue
    resolved_unit: QuickViewMetadataValue
    start: QuickViewMetadataValue
    stop: QuickViewMetadataValue
    step: QuickViewMetadataValue
    sample_count: QuickViewMetadataValue
    is_regular: QuickViewMetadataValue

class QuickViewCurveCounts(BaseModel):
    model_config=ConfigDict(extra='forbid', frozen=True)
    total_curves: int
    renderable_curves: int
    non_renderable_curves: int
    curves_with_units: int
    curves_missing_units: int

class QuickViewRecognitionSummary(BaseModel):
    model_config=ConfigDict(extra='forbid', frozen=True)
    kr_exact: int = 0
    kr_alias: int = 0
    kr_family: int = 0
    unit_domain: int = 0
    unknown: int = 0
    review_required: int = 0

class QuickViewScalingSummary(BaseModel):
    model_config=ConfigDict(extra='forbid', frozen=True)
    governed: int = 0
    kr_known_fallback: int = 0
    unit_domain_fallback: int = 0
    generic_fallback: int = 0
    unit_mismatch: int = 0

class QuickViewCurveInfo(BaseModel):
    model_config=ConfigDict(extra='forbid', frozen=True)
    index: QuickViewIndexInfo
    curve_counts: QuickViewCurveCounts
    recognition_summary: QuickViewRecognitionSummary
    scaling_summary: QuickViewScalingSummary

class QuickViewQaqcFlag(BaseModel):
    model_config=ConfigDict(extra='forbid', frozen=True)
    code: str
    severity: Literal['info','warning','error']
    message: str
    count: int | None = None
    source: str | None = None
    visible_by_default: bool = True

class QuickViewEarlyQaqc(BaseModel):
    model_config=ConfigDict(extra='forbid', frozen=True)
    severity: Literal['ok','info','warning','error'] = 'ok'
    flags: tuple[QuickViewQaqcFlag, ...] = ()

class QuickViewMetadata(BaseModel):
    model_config=ConfigDict(extra='forbid', frozen=True)
    file_info: QuickViewFileInfo
    well_info: QuickViewWellInfo
    curve_info: QuickViewCurveInfo
    early_qaqc: QuickViewEarlyQaqc


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
    quick_view_metadata: QuickViewMetadata | None = None
