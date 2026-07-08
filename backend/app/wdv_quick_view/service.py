from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from .models import QuickViewCurve, QuickViewPackage, QuickViewSample, QuickViewTrack
from app.inventory.models import ManagedProductGroupItem
from app.wdv_display.kr_family_policy_resolver import ManagedKrFamilyDisplayPolicyResolver
from app.knowledge.curve_knowledge import CURVE_DEFINITIONS, resolve_curve_definition


class QuickViewError(ValueError):
    pass


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

        well = sections.get('WELL') or sections.get('W') or []
        curves_section = sections.get('CURVE') or sections.get('C') or []
        ascii_section = sections.get('ASCII') or sections.get('A') or []
        headers = []
        for line in curves_section:
            left, _, description = line.partition(':')
            match = re.match(r'^\s*([^\.\s]+)\s*\.\s*([^\s]*)\s*(.*)$', left)
            if match:
                headers.append((match.group(1).strip(), match.group(2).strip() or None, description.strip() or None))

        rows = []
        for line in ascii_section:
            try:
                row = [float(value) for value in line.replace(',', ' ').split()]
            except ValueError:
                continue
            if len(row) >= len(headers):
                rows.append(row)
        if not headers or not rows:
            raise QuickViewError('LAS has no renderable curve table.')

        null = -999.25
        well_name = None
        depth_unit = headers[0][1]
        for line in well:
            left, _, _ = line.partition(':')
            match = re.match(r'^\s*([^\.\s]+)\s*\.\s*([^\s]*)\s*(.*)$', left)
            if not match:
                continue
            key = match.group(1).upper()
            value = ' '.join(part for part in [match.group(2), match.group(3)] if part).strip()
            if key == 'NULL':
                try:
                    null = float(value)
                except ValueError:
                    pass
            if key in {'WELL', 'WEL', 'WELLNAME'} and value:
                well_name = value

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
        warnings = () if transform.resolved else ('LAS index unit unresolved; displaying raw index without a unit.',)
        return QuickViewPackage(
            filename=Path(filename).name,
            source_format='LAS',
            fingerprint=hashlib.sha256(content).hexdigest(),
            well_name=well_name or 'Not supplied',
            depth_min=min(depths),
            depth_max=max(depths),
            depth_unit_label=transform.unit_label,
            tracks=_group(output),
            warnings=warnings,
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

        return QuickViewPackage(
            filename=Path(filename).name,
            source_format='DLIS',
            fingerprint=hashlib.sha256(content).hexdigest(),
            well_name=well_name,
            depth_min=min(selected.depths),
            depth_max=max(selected.depths),
            depth_unit_label=selected.depth_unit_label,
            tracks=_group(list(selected.curves)),
            warnings=tuple(warnings),
        )
