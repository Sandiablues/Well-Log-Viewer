from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from .models import (
    QuickViewCurve,
    QuickViewCurveCounts,
    QuickViewCurveInfo,
    QuickViewEarlyQaqc,
    QuickViewFileInfo,
    QuickViewIndexInfo,
    QuickViewMetadata,
    QuickViewMetadataValue,
    QuickViewPackage,
    QuickViewQaqcFlag,
    QuickViewRecognitionSummary,
    QuickViewSample,
    QuickViewScalingSummary,
    QuickViewTrack,
    QuickViewWellInfo,
)
from app.inventory.models import ManagedProductGroupItem
from app.wdv_display.kr_family_policy_resolver import ManagedKrFamilyDisplayPolicyResolver
from app.knowledge.curve_knowledge import CURVE_DEFINITIONS, resolve_curve_definition


class QuickViewError(ValueError):
    pass


def _meta_value(
    value: Any,
    *,
    unit: str | None = None,
    source: str | None = None,
    confidence: str | None = None,
) -> QuickViewMetadataValue:
    supplied = value is not None and str(value).strip() != ''
    return QuickViewMetadataValue(
        value=value if supplied else None,
        unit=unit,
        source=source if supplied or source else None,
        confidence=confidence or ('explicit' if supplied else 'not_supplied'),
    )


def _derived_meta(value: Any, *, unit: str | None = None, source: str | None = None) -> QuickViewMetadataValue:
    return QuickViewMetadataValue(value=value, unit=unit, source=source, confidence='derived')


def _unresolved_meta(value: Any, *, unit: str | None = None, source: str | None = None) -> QuickViewMetadataValue:
    return QuickViewMetadataValue(value=value if value is not None else None, unit=unit, source=source, confidence='unresolved')


def _parse_las_header_line(line: str) -> dict[str, str | None] | None:
    left, _, description = line.partition(':')
    match = re.match(r'^\s*([^\.\s]+)\s*\.\s*(.*)$', left.rstrip())
    if not match:
        return None
    mnemonic = match.group(1).strip().upper()
    after_dot = match.group(2)
    # LAS uses MNEM.UNIT VALUE, but blank units are common in ~WELL.  Preserve
    # whether a token appeared immediately after the dot: ``DEPT.F`` has unit
    # F, while ``WELL .      #21D-14`` has no unit and the full text is value.
    raw_after_dot = left[left.find('.') + 1:]
    if raw_after_dot and not raw_after_dot[0].isspace():
        parts = after_dot.split(None, 1)
        unit = parts[0].strip() if parts else None
        value = parts[1].strip() if len(parts) > 1 else None
    else:
        unit = None
        value = after_dot.strip() or None
    return {
        'mnemonic': mnemonic,
        'unit': unit,
        'value': value,
        'description': description.strip() or None,
    }


def _las_section_index(lines: list[str], section_name: str) -> dict[str, dict[str, str | None]]:
    result: dict[str, dict[str, str | None]] = {}
    for line in lines:
        parsed = _parse_las_header_line(line)
        if parsed is not None:
            result[str(parsed['mnemonic'])] = parsed | {'source': f'LAS.~{section_name}.{parsed["mnemonic"]}'}
    return result


def _las_value(index: dict[str, dict[str, str | None]], *keys: str) -> QuickViewMetadataValue:
    for key in keys:
        item = index.get(key.upper())
        if item and item.get('value'):
            return _meta_value(item.get('value'), unit=item.get('unit'), source=item.get('source'))
    return _meta_value(None)


def _parse_float_or_none(value: str | None) -> float | None:
    try:
        return float(str(value).strip()) if value is not None and str(value).strip() else None
    except (TypeError, ValueError):
        return None


def _median_step(values: list[float]) -> float | None:
    ordered = [float(value) for value in values if math.isfinite(float(value))]
    if len(ordered) < 2:
        return None
    deltas = sorted(abs(ordered[index] - ordered[index - 1]) for index in range(1, len(ordered)) if ordered[index] != ordered[index - 1])
    if not deltas:
        return None
    return float(deltas[len(deltas) // 2])


def _is_regular_index(values: list[float], step: float | None) -> bool | None:
    if step is None or len(values) < 3:
        return None
    tolerance = max(abs(step) * 1e-4, 1e-6)
    for index in range(1, len(values)):
        if abs(abs(values[index] - values[index - 1]) - abs(step)) > tolerance:
            return False
    return True


def _curve_counts(total_curves: int, rendered_curves: list[QuickViewCurve], source_units: list[str | None]) -> QuickViewCurveCounts:
    missing_units = sum(1 for unit in source_units if not str(unit or '').strip())
    return QuickViewCurveCounts(
        total_curves=total_curves,
        renderable_curves=len(rendered_curves),
        non_renderable_curves=max(total_curves - len(rendered_curves), 0),
        curves_with_units=max(total_curves - missing_units, 0),
        curves_missing_units=missing_units,
    )


def _recognition_summary(curves: list[QuickViewCurve]) -> QuickViewRecognitionSummary:
    counts = {'KR exact': 0, 'KR alias': 0, 'KR family': 0, 'Unit domain': 0, 'Unknown': 0}
    review_required = 0
    for curve in curves:
        status = str(curve.kr_catalogue_status or curve.catalogue_status or 'Unknown')
        counts[status if status in counts else 'Unknown'] += 1
        if curve.review_required:
            review_required += 1
    return QuickViewRecognitionSummary(
        kr_exact=counts['KR exact'],
        kr_alias=counts['KR alias'],
        kr_family=counts['KR family'],
        unit_domain=counts['Unit domain'],
        unknown=counts['Unknown'],
        review_required=review_required,
    )


def _scaling_summary(curves: list[QuickViewCurve]) -> QuickViewScalingSummary:
    governed = kr_known = unit_domain = generic = mismatch = 0
    for curve in curves:
        decision = str(curve.scale_decision or '')
        if decision == 'Governed':
            governed += 1
        elif decision == 'KR-known fallback':
            kr_known += 1
        elif decision == 'Unit mismatch fallback':
            mismatch += 1
        elif decision in {'Unit-log fallback', 'Unit-linear fallback'}:
            unit_domain += 1
        elif decision == 'Generic fallback':
            generic += 1
        else:
            generic += 1
    return QuickViewScalingSummary(
        governed=governed,
        kr_known_fallback=kr_known,
        unit_domain_fallback=unit_domain,
        generic_fallback=generic,
        unit_mismatch=mismatch,
    )


def _qaqc_severity(flags: list[QuickViewQaqcFlag]) -> str:
    if any(flag.severity == 'error' for flag in flags):
        return 'error'
    if any(flag.severity == 'warning' for flag in flags):
        return 'warning'
    if any(flag.severity == 'info' for flag in flags):
        return 'info'
    return 'ok'


def _quick_view_metadata(
    *,
    filename: str,
    source_format: str,
    content: bytes,
    format_version: str | None,
    parser_name: str,
    parser_status: str,
    well_info: QuickViewWellInfo,
    index_info: QuickViewIndexInfo,
    curve_counts: QuickViewCurveCounts,
    recognition_summary: QuickViewRecognitionSummary,
    scaling_summary: QuickViewScalingSummary,
    qaqc_flags: list[QuickViewQaqcFlag],
) -> QuickViewMetadata:
    fingerprint = hashlib.sha256(content).hexdigest()
    return QuickViewMetadata(
        file_info=QuickViewFileInfo(
            source_file_name=_meta_value(Path(filename).name, source='upload.filename'),
            file_type=_meta_value(source_format, source='file.extension'),
            format_version=_meta_value(format_version),
            file_size_bytes=_derived_meta(len(content), source='upload.content_length'),
            content_fingerprint=_derived_meta(f'sha256:{fingerprint}', source='upload.content'),
            parser_name=_derived_meta(parser_name),
            parser_status=_derived_meta(parser_status),
            temporary_only=_derived_meta(True),
        ),
        well_info=well_info,
        curve_info=QuickViewCurveInfo(
            index=index_info,
            curve_counts=curve_counts,
            recognition_summary=recognition_summary,
            scaling_summary=scaling_summary,
        ),
        early_qaqc=QuickViewEarlyQaqc(
            severity=_qaqc_severity(qaqc_flags),
            flags=tuple(qaqc_flags),
        ),
    )


def _not_supplied_well_info() -> QuickViewWellInfo:
    empty = _meta_value(None)
    return QuickViewWellInfo(
        well_name=empty,
        well_id=empty,
        uwi=empty,
        api=empty,
        field=empty,
        operator=empty,
        country=empty,
        state_province=empty,
        county_area=empty,
        latitude=empty,
        longitude=empty,
        x=empty,
        y=empty,
        datum=empty,
    )


_STANDARD_UNITS = {
    'GAPI', 'API', 'OHMM', 'OHM.M', 'OHM-M', 'MV', 'US/F', 'US/FT', 'US/M',
    'G/CC', 'G/C3', 'V/V', 'PU', 'IN', 'MM', 'DEGC', 'DEGF',
}

_COMMON_MISSING_VALUES = (
    -999.0, -999.25, -999.9, -9999.0, -9999.25,
    999.0, 999.25, 9999.0, 9999.25,
)




@dataclass(frozen=True)
class _QuickViewCatalogueMatch:
    status: str
    canonical_curve_id: str | None = None
    family: str | None = None
    display_unit: str | None = None
    display_transform: str | None = None
    reason: str = ''

    @property
    def is_kr_known(self) -> bool:
        return self.status in {'KR exact', 'KR alias'}

@dataclass(frozen=True)
class _DepthTransform:
    factor: float
    offset: float
    unit_label: str | None
    resolved: bool
    source_unit: str | None

    def apply(self, value: Any) -> float:
        return float(value) * self.factor + self.offset


def _normalise_unit_text(unit: str | None) -> str:
    token = str(unit or '').strip().lower()
    token = token.replace('″', 'in').replace('”', 'in').replace('′', 'ft')
    token = token.replace('×', '*').replace('·', '*')
    token = re.sub(r'[\[\](){}]', '', token)
    token = re.sub(r'\s+', ' ', token)
    return token.strip()


def _numeric_scale(text: str) -> float | None:
    token = text.strip()
    try:
        return float(token)
    except ValueError:
        pass
    match = re.fullmatch(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*/\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))', token)
    if not match:
        return None
    denominator = float(match.group(2))
    if denominator == 0:
        return None
    return float(match.group(1)) / denominator


def _depth_transform_from_unit(unit: str | None) -> _DepthTransform:
    """Resolve DLIS/LAS index engineering units from explicit source metadata only.

    Metric declarations are normalised to metres. Imperial declarations are
    normalised to feet. Fractional engineering units such as ``0.1 in``,
    ``1/10 in`` and ``in/10`` are supported. Unknown declarations remain raw
    and unlabeled; no plausibility inference is performed.
    """

    source = str(unit).strip() if unit is not None and str(unit).strip() else None
    token = _normalise_unit_text(source)
    if not token:
        return _DepthTransform(1.0, 0.0, None, False, source)

    aliases = {
        'm': ('metric', 1.0),
        'meter': ('metric', 1.0),
        'meters': ('metric', 1.0),
        'metre': ('metric', 1.0),
        'metres': ('metric', 1.0),
        'cm': ('metric', 0.01),
        'centimeter': ('metric', 0.01),
        'centimeters': ('metric', 0.01),
        'centimetre': ('metric', 0.01),
        'centimetres': ('metric', 0.01),
        'mm': ('metric', 0.001),
        'millimeter': ('metric', 0.001),
        'millimeters': ('metric', 0.001),
        'millimetre': ('metric', 0.001),
        'millimetres': ('metric', 0.001),
        'ft': ('imperial', 1.0),
        'foot': ('imperial', 1.0),
        'feet': ('imperial', 1.0),
        'f': ('imperial', 1.0),
        'in': ('imperial-inch', 1.0),
        'inch': ('imperial-inch', 1.0),
        'inches': ('imperial-inch', 1.0),
    }

    def build(scale: float, base: str) -> _DepthTransform | None:
        resolved = aliases.get(base)
        if resolved is None or not math.isfinite(scale) or scale == 0:
            return None
        family, base_factor = resolved
        if family == 'metric':
            return _DepthTransform(scale * base_factor, 0.0, 'm', True, source)
        if family == 'imperial':
            return _DepthTransform(scale * base_factor, 0.0, 'ft', True, source)
        return _DepthTransform(scale / 12.0, 0.0, 'ft', True, source)

    direct = build(1.0, token)
    if direct is not None:
        return direct

    # Prefix form: .1 in, 0.1inch, 1/10 in, 2.54 cm
    prefix = re.fullmatch(
        r'(?P<scale>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:\s*/\s*[+-]?(?:\d+(?:\.\d*)?|\.\d+))?)\s*\*?\s*'
        r'(?P<base>[a-z]+)',
        token,
    )
    if prefix:
        scale = _numeric_scale(prefix.group('scale'))
        result = build(scale, prefix.group('base')) if scale is not None else None
        if result is not None:
            return result

    # Suffix division form: in/10, ft/100, m/100
    suffix = re.fullmatch(r'(?P<base>[a-z]+)\s*/\s*(?P<divisor>[+-]?(?:\d+(?:\.\d*)?|\.\d+))', token)
    if suffix:
        divisor = float(suffix.group('divisor'))
        result = build(1.0 / divisor, suffix.group('base')) if divisor != 0 else None
        if result is not None:
            return result

    return _DepthTransform(1.0, 0.0, None, False, source)


def _channel_declared_missing(channel: object) -> set[float]:
    values: set[float] = set()
    for name in ('null_value', 'null', 'missing_value', 'fill_value', 'invalid_value'):
        raw = getattr(channel, name, None)
        try:
            if raw is not None:
                values.add(float(raw))
        except (TypeError, ValueError):
            pass

    # Vendor extensions sometimes expose numeric missing values through a
    # dictionary rather than the standard DLIS properties indicator list.
    properties = getattr(channel, 'properties', None)
    if isinstance(properties, dict):
        for key in ('NULL', 'MISSING', 'FILL', 'INVALID'):
            raw = properties.get(key)
            try:
                if raw is not None:
                    values.add(float(raw))
            except (TypeError, ValueError):
                pass
    return values


def _matches_missing(value: float, missing: float) -> bool:
    tolerance = max(1e-7, abs(missing) * 1e-9)
    return math.isclose(value, missing, rel_tol=0.0, abs_tol=tolerance)


def _is_missing_value(value: float, declared: set[float]) -> bool:
    if not math.isfinite(value):
        return True
    if any(_matches_missing(value, missing) for missing in declared):
        return True
    if any(_matches_missing(value, missing) for missing in _COMMON_MISSING_VALUES):
        return True
    return abs(value) >= 1e29


def _clean_scalar_samples(
    depth_values: Any,
    curve_values: Any,
    declared_missing: set[float],
    *,
    depth_transform: _DepthTransform | None = None,
) -> list[QuickViewSample]:
    transform = depth_transform or _DepthTransform(1.0, 0.0, None, False, None)
    samples: list[QuickViewSample] = []
    for depth, value in zip(depth_values, curve_values):
        try:
            d = transform.apply(depth)
            v = float(value)
        except (TypeError, ValueError, OverflowError):
            continue
        if not math.isfinite(d) or _is_missing_value(v, declared_missing):
            continue
        samples.append(QuickViewSample(depth=d, value=v))
    return samples


def _pct(values: list[float], p: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise QuickViewError('No numeric curve samples.')
    pos = (len(ordered) - 1) * p
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return ordered[lo]
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def _adaptive_padding_fraction(target_footprint: float = 0.30) -> float:
    """Return side padding needed so the core percentile span occupies target fraction.

    Example: target 0.30 -> displayed span = core / 0.30, so side padding
    is 0.75 * core on each side.  The footprint target is clamped to avoid
    accidental over-expansion or over-tight scaling.
    """
    target = min(max(float(target_footprint), 0.30), 0.55)
    return max(((1.0 / target) - 1.0) / 2.0, 0.0)


def _safe_range(values: list[float], logarithmic: bool = False, padding_fraction: float = 0.0) -> tuple[float, float]:
    usable = [v for v in values if math.isfinite(v) and (v > 0 if logarithmic else True)]
    if not usable:
        raise QuickViewError('No renderable values.')
    if logarithmic:
        return _safe_log_range(usable, padding_fraction=padding_fraction)
    lo, hi = _pct(usable, .10), _pct(usable, .90)
    if lo == hi:
        pad = max(abs(lo) * .05, 1e-6)
        lo -= pad
        hi += pad
    else:
        pad = abs(hi - lo) * max(float(padding_fraction), 0.0)
        lo -= pad
        hi += pad
    return float(lo), float(hi)


def _safe_log_range(values: list[float], padding_fraction: float = 0.0) -> tuple[float, float]:
    """Return a positive-only adaptive P10-P90 display range in log10 space."""
    usable = [float(v) for v in values if math.isfinite(v) and float(v) > 0.0]
    if not usable:
        raise QuickViewError('No positive renderable values for logarithmic scale.')
    log_values = [math.log10(v) for v in usable]
    lo_log, hi_log = _pct(log_values, .10), _pct(log_values, .90)
    if lo_log == hi_log:
        pad = 0.05
        lo_log -= pad
        hi_log += pad
    else:
        pad = abs(hi_log - lo_log) * max(float(padding_fraction), 0.0)
        lo_log -= pad
        hi_log += pad
    low = 10.0 ** lo_log
    high = 10.0 ** hi_log
    floor = min(usable)
    if not math.isfinite(low) or low <= 0.0:
        low = floor
    if not math.isfinite(high) or high <= low:
        high = max(max(usable), low * 10.0)
    return float(low), float(high)


def _canonical_curve_unit(unit: str | None) -> str:
    token = str(unit or '').strip().upper()
    token = token.replace('Ω', 'OHM')
    token = token.replace('Ω', 'OHM')
    token = token.replace('µ', 'U')
    token = token.replace('μ', 'U')
    token = re.sub(r'[\[\](){}]', '', token)
    token = re.sub(r'\s+', '', token)
    token = token.replace('OHM*M', 'OHMM').replace('OHM·M', 'OHMM')
    token = token.replace('OHM.M', 'OHMM').replace('OHM-M', 'OHMM')
    token = token.replace('OHMMETERS', 'OHMMETER').replace('OHMMETRES', 'OHMMETRE')
    return token


def _unit_domain(unit: str | None) -> str:
    """Resolve only safe physical display domains from engineering units."""
    token = _canonical_curve_unit(unit)
    if token in {'OHMM', 'OHMMETER', 'OHMMETRE', 'OHM'}:
        return 'resistivity'
    if token in {'PU', 'PERCENT', 'PCT', '%', 'V/V', 'VV', 'V/VOL', 'VOLUME/VOLUME'}:
        return 'porosity_like'
    if token in {'GAPI', 'API'}:
        return 'gamma_like'
    if token in {'IN', 'INCH', 'INCHES', 'MM', 'CM'}:
        return 'length_like'
    if token in {'US/F', 'US/FT', 'US/M', 'USEC/FT', 'USEC/M', 'MICROSECOND/FT', 'MICROSECOND/M'}:
        return 'sonic_like'
    return 'generic'


def _near_flatline(values: list[float]) -> bool:
    finite = [float(v) for v in values if math.isfinite(v)]
    if len(finite) < 2:
        return True
    p10 = _pct(finite, .10)
    p50 = _pct(finite, .50)
    p90 = _pct(finite, .90)
    spread = abs(p90 - p10)
    reference = max(abs(p50), max(abs(v) for v in finite), 1.0)
    return spread <= reference * 1e-4


def _curve_display_contract(
    *,
    mnemonic: str,
    description: str | None,
    unit: str | None,
    values: list[float],
) -> tuple[str, str, float, float, bool, str, str, str]:
    """Resolve Quick View display contract in the only safe order.

    Order is deliberately strict:
      1. KR exact mnemonic catalogue match.
      2. KR approved alias match.
      3. KR family/domain match.
      4. Source-unit domain fallback.
      5. Generic fallback.

    A known KR exact/alias match must never be reported as Generic fallback.
    """
    finite = [float(v) for v in values if math.isfinite(v)]
    if not finite:
        raise QuickViewError('No renderable values.')

    catalogue = _quick_view_catalogue_match(mnemonic=mnemonic, description=description, unit=unit)
    item = _quick_view_policy_item(
        mnemonic=mnemonic,
        description=description,
        unit=unit,
        kr_curve_type_id=catalogue.canonical_curve_id if catalogue.is_kr_known else None,
        curve_family=catalogue.family or '',
    )

    unit_domain = _unit_domain(unit)
    resolved = ManagedKrFamilyDisplayPolicyResolver.resolve_with_unit_resolution(item)
    policy = resolved.policy
    unit_result = resolved.unit_resolution
    usable_policy = (
        policy is not None
        and str(policy.get('source') or '') == 'managed_knowledge_curve_rule'
        and unit_result is not None
        and unit_result.resolved_bounds_usable
        and unit_result.resolved_min is not None
        and unit_result.resolved_max is not None
        and math.isfinite(float(unit_result.resolved_min))
        and math.isfinite(float(unit_result.resolved_max))
        and float(unit_result.resolved_min) != float(unit_result.resolved_max)
    )

    if usable_policy and catalogue.is_kr_known and not _near_flatline(finite):
        scale_type = (
            'logarithmic'
            if str(policy.get('type') or '').lower() in {'log', 'logarithmic'}
            else 'linear'
        )
        low = float(unit_result.resolved_min)
        high = float(unit_result.resolved_max)
        if scale_type != 'logarithmic' or (low > 0 and high > 0):
            direction = (
                'reverse'
                if str(policy.get('direction') or '').lower() in {'reverse', 'reversed'}
                else 'normal'
            )
            return (
                scale_type,
                direction,
                low,
                high,
                False,
                'managed_knowledge_curve_rule',
                catalogue.status,
                'Governed',
            )

    padding = _adaptive_padding_fraction(target_footprint=0.30)
    if unit_domain == 'resistivity':
        fallback_low, fallback_high = _safe_range(
            finite,
            logarithmic=True,
            padding_fraction=padding,
        )
        # Keep scale_source as the physical fallback mechanism for legacy
        # callers/tests.  The render-facing catalogue/decision fields remain
        # authoritative for KR status: KR exact/alias curves report
        # scale_decision='KR-known fallback' or 'Unit mismatch fallback', not
        # Generic fallback.
        if catalogue.is_kr_known:
            return (
                'logarithmic',
                'normal',
                fallback_low,
                fallback_high,
                True,
                'fallback_unit_domain_resistivity_log_p10_p90',
                catalogue.status,
                _known_curve_fallback_decision(unit_result),
            )
        return (
            'logarithmic',
            'normal',
            fallback_low,
            fallback_high,
            True,
            'fallback_unit_domain_resistivity_log_p10_p90',
            catalogue.status if catalogue.status == 'KR family' else 'Unit domain',
            'Unit-log fallback',
        )

    fallback_low, fallback_high = _safe_range(
        finite,
        logarithmic=False,
        padding_fraction=padding,
    )
    if catalogue.is_kr_known:
        if unit_domain != 'generic':
            fallback_source = f'fallback_unit_domain_{unit_domain}_linear_p10_p90'
        else:
            fallback_source = 'fallback_generic_linear_p10_p90'
        return (
            'linear',
            'normal',
            fallback_low,
            fallback_high,
            True,
            fallback_source,
            catalogue.status,
            _known_curve_fallback_decision(unit_result),
        )
    if catalogue.status == 'KR family':
        return (
            'linear',
            'normal',
            fallback_low,
            fallback_high,
            True,
            'fallback_kr_family_linear_p10_p90',
            'KR family',
            'Unit-linear fallback',
        )
    if unit_domain != 'generic':
        return (
            'linear',
            'normal',
            fallback_low,
            fallback_high,
            True,
            f'fallback_unit_domain_{unit_domain}_linear_p10_p90',
            'Unit domain',
            'Unit-linear fallback',
        )
    return (
        'linear',
        'normal',
        fallback_low,
        fallback_high,
        True,
        'fallback_generic_linear_p10_p90',
        'Unknown',
        'Generic fallback',
    )


def _quick_view_policy_item(
    *,
    mnemonic: str,
    description: str | None,
    unit: str | None,
    kr_curve_type_id: str | None = None,
    curve_family: str = '',
) -> ManagedProductGroupItem:
    return ManagedProductGroupItem(
        product_id=f'quick-view:{mnemonic}',
        display_name=mnemonic,
        curve_name=mnemonic,
        observed_mnemonic=mnemonic,
        normalized_mnemonic=mnemonic.upper(),
        curve_type=mnemonic,
        curve_description=description,
        curve_unit=unit,
        curve_family=curve_family,
        kr_curve_type_id=kr_curve_type_id,
        source_kind='quick_view',
    )


def _quick_view_catalogue_match(
    *,
    mnemonic: str,
    description: str | None,
    unit: str | None,
) -> _QuickViewCatalogueMatch:
    """KR-first catalogue classification for one Quick View source mnemonic.

    This function does classification only.  It does not choose a display scale.
    Exact mnemonic evidence is checked before alias evidence.  Combined lookup
    tables are used only after the exact pass, because they may contain both
    canonical mnemonics and aliases.
    """
    key = str(mnemonic or '').strip().upper()
    if not key:
        return _QuickViewCatalogueMatch(status='Unknown', reason='empty source mnemonic')

    exact = _curve_knowledge_exact_match(key)
    if exact is not None:
        return exact

    index = _quick_view_kr_index()
    if index is not None:
        exact = _managed_kr_exact_match(key, index)
        if exact is not None:
            return exact

        alias = _managed_kr_alias_match(key, index)
        if alias is not None:
            return alias

    alias = _curve_knowledge_alias_match(key)
    if alias is not None:
        return alias

    family = _quick_view_family_match(mnemonic=mnemonic, description=description, unit=unit)
    if family is not None:
        return family

    if _unit_domain(unit) != 'generic':
        return _QuickViewCatalogueMatch(status='Unit domain', reason='source unit maps to a known display domain')
    return _QuickViewCatalogueMatch(status='Unknown', reason='no KR exact, alias, family, or unit-domain match')


def _quick_view_kr_index() -> Any | None:
    try:
        from app.knowledge.managed_storage import ManagedStorage

        return ManagedKrFamilyDisplayPolicyResolver._index(ManagedStorage())
    except Exception:
        return None


def _curve_knowledge_exact_match(key: str) -> _QuickViewCatalogueMatch | None:
    for definition in CURVE_DEFINITIONS:
        if definition.is_standard_mnemonic(key):
            return _QuickViewCatalogueMatch(
                status='KR exact',
                canonical_curve_id=definition.canonical_curve_id,
                family=definition.curve_family,
                display_unit=definition.default_unit,
                display_transform=definition.scale_type,
                reason='source mnemonic matches backend KR standard mnemonic',
            )
    return None


def _curve_knowledge_alias_match(key: str) -> _QuickViewCatalogueMatch | None:
    definition = resolve_curve_definition(key)
    if definition is None or not definition.is_alias_mnemonic(key):
        return None
    return _QuickViewCatalogueMatch(
        status='KR alias',
        canonical_curve_id=definition.canonical_curve_id,
        family=definition.curve_family,
        display_unit=definition.default_unit,
        display_transform=definition.scale_type,
        reason='source mnemonic matches backend KR approved alias',
    )


def _managed_kr_exact_match(key: str, index: Any) -> _QuickViewCatalogueMatch | None:
    canonical = getattr(index, 'standard_mnemonic_to_canonical', {}).get(key)
    if canonical:
        record = getattr(index, 'curve_definitions', {}).get(canonical)
        return _QuickViewCatalogueMatch(
            status='KR exact',
            canonical_curve_id=str(canonical),
            family=_first_text_attr(record, 'family', 'curve_family') if record is not None else None,
            display_unit=_first_text_attr(record, 'default_unit', 'preferred_unit', 'display_unit') if record is not None else None,
            display_transform=None,
            reason='source mnemonic matches managed KR standard mnemonic',
        )

    for canonical, record in getattr(index, 'curve_definitions', {}).items():
        for candidate in _managed_curve_exact_candidates(record, canonical):
            if candidate == key:
                return _QuickViewCatalogueMatch(
                    status='KR exact',
                    canonical_curve_id=str(canonical),
                    family=_first_text_attr(record, 'family', 'curve_family'),
                    display_unit=_first_text_attr(record, 'default_unit', 'preferred_unit', 'display_unit'),
                    display_transform=None,
                    reason='source mnemonic matches managed KR curve-definition mnemonic field',
                )
    return None


def _managed_curve_exact_candidates(record: Any, canonical: str) -> set[str]:
    values: set[str] = set()
    for attr in (
        'mnemonic',
        'normalized_mnemonic',
        'standard_mnemonic',
        'primary_mnemonic',
        'display_mnemonic',
        'render_curve_id',
        'canonical_mnemonic',
        'canonical_curve_mnemonic',
        'curve_mnemonic',
    ):
        value = getattr(record, attr, None)
        if value is not None:
            normalized = str(value).strip().upper()
            if normalized:
                values.add(normalized)
    # Some managed KR imports use canonical_curve_id itself as the exact
    # mnemonic.  This is safe only when it is already mnemonic-shaped, not a
    # semantic ID such as gamma_ray or neutron_porosity.
    canonical_key = str(canonical or '').strip().upper()
    if canonical_key and re.fullmatch(r'[A-Z][A-Z0-9_]{0,15}', canonical_key):
        values.add(canonical_key)
    return values


def _managed_kr_alias_match(key: str, index: Any) -> _QuickViewCatalogueMatch | None:
    canonical = getattr(index, 'alias_to_canonical', {}).get(key)
    if not canonical:
        return None
    record = getattr(index, 'curve_definitions', {}).get(canonical)
    return _QuickViewCatalogueMatch(
        status='KR alias',
        canonical_curve_id=str(canonical),
        family=_first_text_attr(record, 'family', 'curve_family') if record is not None else None,
        display_unit=_first_text_attr(record, 'default_unit', 'preferred_unit', 'display_unit') if record is not None else None,
        display_transform=None,
        reason='source mnemonic matches managed KR approved alias after exact pass failed',
    )


def _quick_view_family_match(
    *,
    mnemonic: str,
    description: str | None,
    unit: str | None,
) -> _QuickViewCatalogueMatch | None:
    item = _quick_view_policy_item(
        mnemonic=mnemonic,
        description=description,
        unit=unit,
    )
    try:
        policy = ManagedKrFamilyDisplayPolicyResolver.resolve(item)
    except Exception:
        policy = None
    if policy is not None and str(policy.get('source') or '') == 'managed_knowledge_family_default':
        return _QuickViewCatalogueMatch(
            status='KR family',
            family=str(policy.get('curve_family') or '') or None,
            display_transform=str(policy.get('type') or '') or None,
            reason='source evidence resolved to managed KR family default',
        )
    return None


def _first_text_attr(record: Any, *attrs: str) -> str | None:
    if record is None:
        return None
    for attr in attrs:
        value = getattr(record, attr, None)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _known_curve_fallback_decision(unit_result: Any | None) -> str:
    status = str(getattr(getattr(unit_result, 'status', None), 'value', getattr(unit_result, 'status', '')) or '').lower()
    if 'incompatible' in status or 'mismatch' in status:
        return 'Unit mismatch fallback'
    return 'KR-known fallback'


def _quick_view_scale_decision(scale_source: str, scale_type: str) -> str:
    source = str(scale_source or '').lower()
    if source == 'managed_knowledge_curve_rule' or 'governed' in source or 'kr_' in source:
        return 'Governed'
    if 'resistivity_log' in source or (scale_type == 'logarithmic' and 'fallback_unit_domain' in source):
        return 'Unit-log fallback'
    if 'fallback_unit_domain' in source:
        return 'Unit-linear fallback'
    return 'Generic fallback'


def _quick_view_catalogue_status(
    *,
    mnemonic: str,
    policy: dict[str, object] | None,
    unit_domain: str,
) -> str:
    source = str((policy or {}).get('source') or '').lower()
    if source == 'managed_knowledge_curve_rule':
        match_type = str(
            (policy or {}).get('match_type')
            or (policy or {}).get('match_kind')
            or (policy or {}).get('resolution_kind')
            or (policy or {}).get('matched_as')
            or ''
        ).lower()
        if 'alias' in match_type:
            return 'KR alias'

        normalized = str(mnemonic or '').strip().upper()
        canonical_candidates = [
            (policy or {}).get('mnemonic'),
            (policy or {}).get('curve_name'),
            (policy or {}).get('curve_type'),
            (policy or {}).get('canonical_mnemonic'),
            (policy or {}).get('canonical_curve_mnemonic'),
            (policy or {}).get('kr_mnemonic'),
        ]
        for candidate in canonical_candidates:
            if candidate is not None and str(candidate).strip().upper() == normalized:
                return 'KR exact'

        aliases = (policy or {}).get('aliases') or (policy or {}).get('curve_aliases') or ()
        try:
            if any(str(alias).strip().upper() == normalized for alias in aliases):
                return 'KR alias'
        except TypeError:
            pass

        return 'KR exact'

    if 'family' in source:
        return 'KR family'

    family_fields = [
        (policy or {}).get('family'),
        (policy or {}).get('curve_family'),
        (policy or {}).get('resolved_family'),
        (policy or {}).get('family_id'),
    ]
    if any(str(value or '').strip() for value in family_fields):
        return 'KR family'

    if unit_domain != 'generic':
        return 'Unit domain'
    return 'Unknown'


def _trusted_unit(unit: str | None) -> str | None:
    token = str(unit or '').strip().upper()
    return token if token in _STANDARD_UNITS else None


def _is_resistivity(mnemonic: str, description: str | None, unit: str | None, values: list[float]) -> bool:
    evidence = ' '.join([mnemonic, description or '', unit or '']).upper()
    return all(v > 0 for v in values if math.isfinite(v)) and (
        'RESIST' in evidence
        or 'OHMM' in evidence
        or re.match(r'^(RES|RT|ILD|ILM|LL|RXO)', mnemonic.upper()) is not None
    )


def _resistivity_family(curve: QuickViewCurve) -> tuple[str, str]:
    """Return a deterministic resistivity family key and display title.

    Grouping is based only on source mnemonic/description evidence. It avoids
    placing unrelated resistivity tools into one overloaded track while keeping
    related shallow/medium/deep channels comparable on one shared log scale.
    """
    mnemonic = curve.mnemonic.upper().strip()
    description = str(curve.description or '').upper()
    evidence = f'{mnemonic} {description}'

    if any(token in evidence for token in ('MICRO', 'MSFL', 'MICROSPHERIC', 'MICROLATERAL', 'RXO')):
        return ('micro', 'Micro Resistivity')
    if any(token in evidence for token in ('ARC ', 'ARC-', 'PHASE-SHIFT', 'PROPAGATION')) or mnemonic in {'RDEP', 'RMED', 'RSHAL'}:
        return ('propagation', 'Propagation Resistivity')
    if any(token in evidence for token in ('ARRAY INDUCTION', 'AIT', 'HDIL', 'HRAI')) or re.match(r'^(A|AT|AF|AI)\d+', mnemonic):
        return ('array_induction', 'Array Induction Resistivity')
    if any(token in evidence for token in ('LATEROLOG', 'DLL', 'DUAL LATERAL')) or re.match(r'^(LLD|LLS|LL3|LL7|LL8)', mnemonic):
        return ('laterolog', 'Laterolog Resistivity')
    if any(token in evidence for token in ('INDUCTION', 'ILD', 'ILM', 'SFL')) or re.match(r'^(ILD|ILM|SFL)', mnemonic):
        return ('induction', 'Induction Resistivity')
    if any(token in evidence for token in ('BUTTON', 'PAD RESISTIVITY', 'AZIMUTHAL')):
        return ('azimuthal', 'Azimuthal Resistivity')

    # Stable source-family fallback: mnemonic stem before investigation-depth
    # digits, then a normalized description stem when available.
    stem = re.sub(r'[-_]?\d+(?:\.\d+)?[A-Z]*$', '', mnemonic).strip('-_')
    if stem and stem not in {'R', 'RES', 'RT'}:
        return (f'stem:{stem}', f'{stem} Resistivity')
    description_stem = re.sub(r'\b(?:SHALLOW|MEDIUM|DEEP|\d+(?:\.\d+)?\s*(?:IN|INCH|FT|MHZ|KHZ))\b', ' ', description)
    description_stem = re.sub(r'\s+', ' ', description_stem).strip(' -_')
    if description_stem:
        return (f'description:{description_stem}', description_stem.title())
    return ('generic', 'Resistivity')


def _shared_resistivity_scale(curves: list[QuickViewCurve]) -> list[QuickViewCurve]:
    """Apply one governed log scale to comparable known resistivity curves.

    Curves already using the observed fallback remain independent because they
    are unknown, unscaled, or near-flatline by contract.
    """
    governed = [
        curve for curve in curves
        if curve.scale_type == 'logarithmic'
        and curve.scale_source != 'observed_p10_p90'
        and curve.scale_min > 0
        and curve.scale_max > curve.scale_min
    ]
    if not governed:
        return curves
    shared_min = min(curve.scale_min for curve in governed)
    shared_max = max(curve.scale_max for curve in governed)
    return [
        curve.model_copy(update={'scale_min': shared_min, 'scale_max': shared_max})
        if curve in governed else curve
        for curve in curves
    ]


def _group(curves: list[QuickViewCurve]) -> tuple[QuickViewTrack, ...]:
    """Create exactly one Quick View track per curve.

    Quick View is a source-content inspection utility. It must not infer or
    impose composite-log layouts. Every renderable source curve is therefore
    displayed independently using its own resolved display contract.
    """
    return tuple(
        QuickViewTrack(
            track_id=f'qv-track-{index}',
            title=curve.mnemonic,
            scale_type=curve.scale_type,
            curves=(curve,),
        )
        for index, curve in enumerate(curves)
    )


def _channel_field(data: Any, channel: Any) -> str | None:
    """Return the reliable structured-array field for a DLIS channel."""
    candidates: list[str] = []
    fingerprint = getattr(channel, 'fingerprint', None)
    name = str(getattr(channel, 'name', '') or '').strip()
    if fingerprint:
        candidates.append(str(fingerprint))
    if name:
        candidates.append(name)
    for candidate in candidates:
        try:
            data[candidate]
            return candidate
        except (KeyError, ValueError, IndexError, TypeError):
            pass

    # Last-resort mnemonic match for strict=False duplicate suffixes.
    names = list(getattr(getattr(data, 'dtype', None), 'names', None) or ())
    for candidate in candidates:
        for field in names:
            if field == candidate or field.startswith(candidate + '.') or field.startswith(candidate + '('):
                return field
    return None


def _frame_index_channel(frame: Any, channels: list[Any]) -> Any | None:
    if not channels or getattr(frame, 'index_type', None) is None:
        return None
    index_name = str(getattr(frame, 'index', '') or '').strip()
    if index_name:
        for channel in channels:
            if str(getattr(channel, 'name', '') or '').strip() == index_name:
                return channel
    # RP66/dlisio contract: when index_type exists, the first channel is index.
    return channels[0]


@dataclass(frozen=True)
class _DlisFramePackage:
    curves: tuple[QuickViewCurve, ...]
    depths: tuple[float, ...]
    depth_unit_label: str | None
    warning: str | None
    frame_name: str
    index_mnemonic: str | None
    source_index_unit: str | None


class WdvQuickViewService:
    def parse(self, *, filename: str, content: bytes) -> QuickViewPackage:
        suffix = Path(filename).suffix.lower()
        if suffix == '.las':
            return self._las(filename, content)
        if suffix == '.dlis':
            return self._dlis(filename, content)
        raise QuickViewError('Quick View accepts only LAS or DLIS files.')

    def _las(self, filename: str, content: bytes) -> QuickViewPackage:
        text = content.decode('utf-8', errors='replace')
        sections: dict[str, list[str]] = {}
        current = None
        for raw in text.splitlines():
            stripped = raw.strip()
            if stripped.startswith('~'):
                current = stripped[1:].split()[0].upper()
                sections.setdefault(current, [])
            elif current and stripped and not stripped.startswith('#'):
                sections[current].append(raw)

        version_section = sections.get('VERSION') or sections.get('V') or []
        well = sections.get('WELL') or sections.get('W') or []
        curves_section = sections.get('CURVE') or sections.get('C') or []
        ascii_section = sections.get('ASCII') or sections.get('A') or []
        version_index = _las_section_index(version_section, 'VERSION')
        well_index = _las_section_index(well, 'WELL')

        headers: list[tuple[str, str | None, str | None]] = []
        for line in curves_section:
            parsed = _parse_las_header_line(line)
            if parsed is not None:
                headers.append((str(parsed['mnemonic']), parsed.get('unit'), parsed.get('description')))

        rows: list[list[float]] = []
        for line in ascii_section:
            try:
                row = [float(value) for value in line.replace(',', ' ').split()]
            except ValueError:
                continue
            if len(row) >= len(headers):
                rows.append(row)
        if not headers or not rows:
            raise QuickViewError('LAS has no renderable curve table.')

        null_item = well_index.get('NULL')
        null = _parse_float_or_none(null_item.get('value') if null_item else None)
        if null is None:
            null = -999.25

        well_name_value = _las_value(well_index, 'WELL', 'WEL', 'WELLNAME')
        well_name = str(well_name_value.value).strip() if well_name_value.value is not None else None
        depth_unit = headers[0][1]
        transform = _depth_transform_from_unit(depth_unit)
        depths = [transform.apply(row[0]) for row in rows if math.isfinite(row[0])]
        output: list[QuickViewCurve] = []
        for index, (mnemonic, unit, description) in enumerate(headers[1:], 1):
            samples = _clean_scalar_samples(
                [row[0] for row in rows],
                [row[index] for row in rows],
                {null},
                depth_transform=transform,
            )
            if not samples:
                continue
            values = [sample.value for sample in samples]
            scale_type, direction, low, high, policy_review, scale_source, catalogue_status, scale_decision = _curve_display_contract(
                mnemonic=mnemonic, description=description, unit=unit, values=values
            )
            trusted = _trusted_unit(unit)
            catalogue = _quick_view_catalogue_match(mnemonic=mnemonic, description=description, unit=unit)
            output.append(QuickViewCurve(
                curve_id=f'qv-{index}-{mnemonic}',
                mnemonic=mnemonic,
                description=description,
                unit_label=trusted,
                scale_type=scale_type,
                scale_direction=direction,
                scale_min=low,
                scale_max=high,
                review_required=policy_review or trusted is None,
                scale_source=scale_source,
                catalogue_status=catalogue_status,
                scale_decision=scale_decision,
                source_mnemonic=mnemonic,
                source_description=description,
                source_unit=unit,
                kr_catalogue_status=catalogue_status,
                kr_canonical_curve=catalogue.canonical_curve_id,
                kr_family=catalogue.family,
                kr_unit_status='usable' if scale_decision == 'Governed' else scale_decision,
                display_unit=trusted or catalogue.display_unit,
                display_transform=scale_type,
                display_range=(low, high),
                scale_reason=f'{catalogue_status} -> {scale_decision} via {scale_source}',
                samples=tuple(samples),
            ))
        if not output:
            raise QuickViewError('LAS contains no renderable numeric curves.')

        warnings = [] if transform.resolved else ['LAS index unit unresolved; displaying raw index without a unit.']
        qaqc_flags: list[QuickViewQaqcFlag] = []
        wrap_item = version_index.get('WRAP')
        wrap_value = str(wrap_item.get('value') or '').strip().upper() if wrap_item else ''
        if wrap_value:
            severity = 'warning' if wrap_value == 'YES' else 'info'
            message = 'LAS WRAP=YES declared; parser warning if wrapped rows are inconsistent.' if wrap_value == 'YES' else 'LAS WRAP=NO.'
            qaqc_flags.append(QuickViewQaqcFlag(
                code='las_wrap_mode',
                severity=severity,
                message=message,
                source=wrap_item.get('source') if wrap_item else 'LAS.~VERSION.WRAP',
                visible_by_default=(wrap_value == 'YES'),
            ))
        else:
            qaqc_flags.append(QuickViewQaqcFlag(
                code='las_wrap_mode_missing',
                severity='info',
                message='LAS WRAP mode was not supplied; parser treated rows as unwrapped.',
                source='LAS.~VERSION.WRAP',
                visible_by_default=False,
            ))

        source_units = [unit for _, unit, _ in headers[1:]]
        counts = _curve_counts(len(headers) - 1, output, source_units)
        if counts.curves_missing_units:
            qaqc_flags.append(QuickViewQaqcFlag(
                code='missing_curve_units',
                severity='warning',
                message=f'{counts.curves_missing_units} curves have no source unit.',
                count=counts.curves_missing_units,
            ))
        if not transform.resolved:
            qaqc_flags.append(QuickViewQaqcFlag(
                code='unresolved_index_unit',
                severity='warning',
                message='LAS index unit is unresolved; displaying raw index values.',
                source='LAS.~CURVE.' + headers[0][0],
            ))
        recognition = _recognition_summary(output)
        if recognition.unknown:
            qaqc_flags.append(QuickViewQaqcFlag(
                code='unknown_curve_mnemonics',
                severity='info',
                message=f'{recognition.unknown} curves were not recognized by KR or unit domain.',
                count=recognition.unknown,
            ))
        scaling = _scaling_summary(output)
        if scaling.unit_mismatch:
            qaqc_flags.append(QuickViewQaqcFlag(
                code='unit_mismatch',
                severity='warning',
                message=f'{scaling.unit_mismatch} curves have source units incompatible with KR policy.',
                count=scaling.unit_mismatch,
            ))
        if counts.non_renderable_curves:
            qaqc_flags.append(QuickViewQaqcFlag(
                code='non_renderable_curves',
                severity='warning',
                message=f'{counts.non_renderable_curves} curves were not renderable.',
                count=counts.non_renderable_curves,
            ))

        step_item = well_index.get('STEP')
        step_raw = _parse_float_or_none(step_item.get('value') if step_item else None)
        resolved_step = transform.apply(step_raw) if step_raw is not None else _median_step(depths)
        regular = _is_regular_index(depths, resolved_step)
        if regular is False:
            qaqc_flags.append(QuickViewQaqcFlag(
                code='irregular_index_sampling',
                severity='warning',
                message='Depth/index sampling is irregular.',
            ))

        well_info = QuickViewWellInfo(
            well_name=well_name_value,
            well_id=_las_value(well_index, 'WELLID', 'WID'),
            uwi=_las_value(well_index, 'UWI'),
            api=_las_value(well_index, 'API'),
            field=_las_value(well_index, 'FLD', 'FIELD'),
            operator=_las_value(well_index, 'COMP', 'COMPANY', 'OPERATOR', 'OPER'),
            country=_las_value(well_index, 'COUN', 'COUNTRY', 'CTRY'),
            state_province=_las_value(well_index, 'STAT', 'STATE', 'PROV', 'PROVINCE'),
            county_area=_las_value(well_index, 'CNTY', 'COUNTY', 'AREA'),
            latitude=_las_value(well_index, 'LAT', 'LATI', 'LATITUDE'),
            longitude=_las_value(well_index, 'LON', 'LONG', 'LONGITUDE'),
            x=_las_value(well_index, 'X', 'XCOORD', 'EASTING'),
            y=_las_value(well_index, 'Y', 'YCOORD', 'NORTHING'),
            datum=_las_value(well_index, 'DATUM', 'CRS'),
        )
        index_info = QuickViewIndexInfo(
            source_mnemonic=_meta_value(headers[0][0], source='LAS.~CURVE.' + headers[0][0]),
            source_unit=_meta_value(depth_unit, source='LAS.~CURVE.' + headers[0][0]),
            resolved_unit=_meta_value(transform.unit_label, source='QuickView.depth_unit_resolver', confidence='derived' if transform.resolved else 'unresolved'),
            start=_derived_meta(min(depths), unit=transform.unit_label, source='LAS.~A'),
            stop=_derived_meta(max(depths), unit=transform.unit_label, source='LAS.~A'),
            step=_derived_meta(resolved_step, unit=transform.unit_label, source=step_item.get('source') if step_item else 'LAS.~A'),
            sample_count=_derived_meta(len(depths), source='LAS.~A'),
            is_regular=_derived_meta(regular, source='LAS.~A'),
        )
        version_item = version_index.get('VERS') or version_index.get('VERSION')
        metadata = _quick_view_metadata(
            filename=filename,
            source_format='LAS',
            content=content,
            format_version=str(version_item.get('value')).strip() if version_item and version_item.get('value') else None,
            parser_name='las_quick_view_parser',
            parser_status='parsed_with_warnings' if any(flag.severity in {'warning', 'error'} for flag in qaqc_flags) else 'parsed',
            well_info=well_info,
            index_info=index_info,
            curve_counts=counts,
            recognition_summary=recognition,
            scaling_summary=scaling,
            qaqc_flags=qaqc_flags,
        )
        return QuickViewPackage(
            filename=Path(filename).name,
            source_format='LAS',
            fingerprint=hashlib.sha256(content).hexdigest(),
            well_name=well_name or 'Not supplied',
            depth_min=min(depths),
            depth_max=max(depths),
            depth_unit_label=transform.unit_label,
            tracks=_group(output),
            warnings=tuple(warnings),
            quick_view_metadata=metadata,
        )

    def _parse_dlis_frame(self, *, frame: Any, logical_index: int, frame_index: int) -> _DlisFramePackage | None:
        channels = list(getattr(frame, 'channels', ()) or ())
        index_channel = _frame_index_channel(frame, channels)
        if index_channel is None:
            return None
        try:
            data = frame.curves(strict=False)
        except Exception:
            return None

        index_field = _channel_field(data, index_channel)
        if index_field is None:
            return None
        depth_array = data[index_field]
        if getattr(depth_array, 'ndim', 1) != 1:
            return None

        raw_index_unit = str(getattr(index_channel, 'units', '') or '').strip() or None
        transform = _depth_transform_from_unit(raw_index_unit)
        depths: list[float] = []
        for raw_depth in depth_array:
            try:
                depth = transform.apply(raw_depth)
            except (TypeError, ValueError, OverflowError):
                continue
            if math.isfinite(depth):
                depths.append(depth)
        if not depths:
            return None

        frame_curves: list[QuickViewCurve] = []
        for channel_index, channel in enumerate(channels):
            if channel is index_channel:
                continue
            field = _channel_field(data, channel)
            if field is None:
                continue
            array = data[field]
            if getattr(array, 'ndim', 1) != 1:
                continue
            mnemonic = str(getattr(channel, 'name', '') or '').strip()
            if not mnemonic:
                continue
            declared_missing = _channel_declared_missing(channel)
            samples = _clean_scalar_samples(
                depth_array,
                array,
                declared_missing,
                depth_transform=transform,
            )
            if len(samples) < 2:
                continue
            unit = str(getattr(channel, 'units', '') or '').strip() or None
            long_name = getattr(channel, 'long_name', None)
            description = str(long_name).strip() if long_name is not None and str(long_name).strip() else None
            values = [sample.value for sample in samples]
            try:
                scale_type, direction, low, high, policy_review, scale_source, catalogue_status, scale_decision = _curve_display_contract(
                    mnemonic=mnemonic, description=description, unit=unit, values=values
                )
            except QuickViewError:
                continue
            trusted = _trusted_unit(unit)
            catalogue = _quick_view_catalogue_match(mnemonic=mnemonic, description=description, unit=unit)
            frame_curves.append(QuickViewCurve(
                curve_id=f'qv-{logical_index}-{frame_index}-{channel_index}-{mnemonic}',
                mnemonic=mnemonic,
                description=description,
                unit_label=trusted,
                scale_type=scale_type,
                scale_direction=direction,
                scale_min=low,
                scale_max=high,
                review_required=policy_review or trusted is None,
                scale_source=scale_source,
                catalogue_status=catalogue_status,
                scale_decision=scale_decision,
                source_mnemonic=mnemonic,
                source_description=description,
                source_unit=unit,
                kr_catalogue_status=catalogue_status,
                kr_canonical_curve=catalogue.canonical_curve_id,
                kr_family=catalogue.family,
                kr_unit_status='usable' if scale_decision == 'Governed' else scale_decision,
                display_unit=trusted or catalogue.display_unit,
                display_transform=scale_type,
                display_range=(low, high),
                scale_reason=f'{catalogue_status} -> {scale_decision} via {scale_source}',
                samples=tuple(samples),
            ))
        if not frame_curves:
            return None

        frame_name = str(getattr(frame, 'name', '') or f'frame-{frame_index}')
        warning = None
        if not transform.resolved:
            rendered_unit = raw_index_unit or 'not supplied'
            warning = (
                f'DLIS frame {frame_name} index unit {rendered_unit!r} is unresolved; '
                'displaying raw index values without a unit.'
            )
        return _DlisFramePackage(
            curves=tuple(frame_curves),
            depths=tuple(depths),
            depth_unit_label=transform.unit_label,
            warning=warning,
            frame_name=frame_name,
            index_mnemonic=str(getattr(index_channel, 'name', '') or '').strip() or None,
            source_index_unit=raw_index_unit,
        )

    def _dlis(self, filename: str, content: bytes) -> QuickViewPackage:
        try:
            from dlisio import dlis
        except Exception as exc:
            raise QuickViewError(f'DLIS parser unavailable: {exc}') from exc

        candidates: list[_DlisFramePackage] = []
        warnings: list[str] = []
        well_name = 'Not supplied'
        with NamedTemporaryFile(suffix='.dlis') as temporary:
            temporary.write(content)
            temporary.flush()
            try:
                with dlis.load(temporary.name) as physical:
                    for logical_index, logical_file in enumerate(physical):
                        origins = list(getattr(logical_file, 'origins', ()) or ())
                        if origins:
                            supplied = getattr(origins[0], 'well_name', None)
                            if supplied and str(supplied).strip():
                                well_name = str(supplied).strip()
                        for frame_index, frame in enumerate(getattr(logical_file, 'frames', ()) or ()):
                            candidate = self._parse_dlis_frame(
                                frame=frame,
                                logical_index=logical_index,
                                frame_index=frame_index,
                            )
                            if candidate is not None:
                                candidates.append(candidate)
            except Exception as exc:
                raise QuickViewError(f'DLIS could not be decoded: {exc}') from exc

        if not candidates:
            raise QuickViewError('DLIS contains no renderable depth-indexed scalar curves.')

        # Quick View is a simple display utility: select the renderable frame
        # carrying the largest scalar curve inventory, then the densest index.
        selected = max(candidates, key=lambda item: (len(item.curves), len(item.depths)))
        if len(candidates) > 1:
            warnings.append(
                f'Selected DLIS frame {selected.frame_name} with {len(selected.curves)} renderable scalar curves.'
            )
        if selected.warning:
            warnings.append(selected.warning)

        selected_curves = list(selected.curves)
        counts = _curve_counts(len(selected_curves), selected_curves, [curve.source_unit for curve in selected_curves])
        recognition = _recognition_summary(selected_curves)
        scaling = _scaling_summary(selected_curves)
        qaqc_flags: list[QuickViewQaqcFlag] = []
        if len(candidates) > 1:
            qaqc_flags.append(QuickViewQaqcFlag(
                code='dlis_multiple_frames',
                severity='info',
                message=f'Selected DLIS frame {selected.frame_name} with {len(selected.curves)} renderable scalar curves.',
                count=len(candidates),
            ))
        if selected.warning:
            qaqc_flags.append(QuickViewQaqcFlag(
                code='unresolved_index_unit',
                severity='warning',
                message=selected.warning,
                source=f'DLIS.frame.{selected.frame_name}',
            ))
        if counts.curves_missing_units:
            qaqc_flags.append(QuickViewQaqcFlag(
                code='missing_curve_units',
                severity='warning',
                message=f'{counts.curves_missing_units} curves have no source unit.',
                count=counts.curves_missing_units,
            ))
        if recognition.unknown:
            qaqc_flags.append(QuickViewQaqcFlag(
                code='unknown_curve_mnemonics',
                severity='info',
                message=f'{recognition.unknown} curves were not recognized by KR or unit domain.',
                count=recognition.unknown,
            ))
        if scaling.unit_mismatch:
            qaqc_flags.append(QuickViewQaqcFlag(
                code='unit_mismatch',
                severity='warning',
                message=f'{scaling.unit_mismatch} curves have source units incompatible with KR policy.',
                count=scaling.unit_mismatch,
            ))
        step = _median_step(list(selected.depths))
        regular = _is_regular_index(list(selected.depths), step)
        if regular is False:
            qaqc_flags.append(QuickViewQaqcFlag(
                code='irregular_index_sampling',
                severity='warning',
                message='Depth/index sampling is irregular.',
            ))
        well_info = _not_supplied_well_info().model_copy(update={
            'well_name': _meta_value(well_name if well_name != 'Not supplied' else None, source='DLIS.origin.well_name'),
        })
        index_info = QuickViewIndexInfo(
            source_mnemonic=_meta_value(selected.index_mnemonic, source=f'DLIS.frame.{selected.frame_name}.index'),
            source_unit=_meta_value(selected.source_index_unit, source=f'DLIS.frame.{selected.frame_name}.index.units'),
            resolved_unit=_meta_value(selected.depth_unit_label, source='QuickView.depth_unit_resolver', confidence='derived' if selected.depth_unit_label else 'unresolved'),
            start=_derived_meta(min(selected.depths), unit=selected.depth_unit_label, source=f'DLIS.frame.{selected.frame_name}'),
            stop=_derived_meta(max(selected.depths), unit=selected.depth_unit_label, source=f'DLIS.frame.{selected.frame_name}'),
            step=_derived_meta(step, unit=selected.depth_unit_label, source=f'DLIS.frame.{selected.frame_name}'),
            sample_count=_derived_meta(len(selected.depths), source=f'DLIS.frame.{selected.frame_name}'),
            is_regular=_derived_meta(regular, source=f'DLIS.frame.{selected.frame_name}'),
        )
        metadata = _quick_view_metadata(
            filename=filename,
            source_format='DLIS',
            content=content,
            format_version=None,
            parser_name='dlis_quick_view_parser',
            parser_status='parsed_with_warnings' if any(flag.severity in {'warning', 'error'} for flag in qaqc_flags) else 'parsed',
            well_info=well_info,
            index_info=index_info,
            curve_counts=counts,
            recognition_summary=recognition,
            scaling_summary=scaling,
            qaqc_flags=qaqc_flags,
        )
        return QuickViewPackage(
            filename=Path(filename).name,
            source_format='DLIS',
            fingerprint=hashlib.sha256(content).hexdigest(),
            well_name=well_name,
            depth_min=min(selected.depths),
            depth_max=max(selected.depths),
            depth_unit_label=selected.depth_unit_label,
            tracks=_group(selected_curves),
            warnings=tuple(warnings),
            quick_view_metadata=metadata,
        )
