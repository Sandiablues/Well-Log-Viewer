"""Backend-owned WDV curve display policy."""

from __future__ import annotations

import hashlib
import json
import math
import re
import threading
from typing import Any

from app.inventory.models import ManagedProductGroupItem
from app.wdv_display.kr_family_policy_resolver import ManagedKrFamilyDisplayPolicyResolver

# ---------------------------------------------------------------------------
# Display-policy cache identity constants
# ---------------------------------------------------------------------------

# Schema version of the display-policy fields written into wdv_load_session_contract.
# Increment when the structure of those fields changes (new required keys, etc.).
WDV_DISPLAY_POLICY_CONTRACT_VERSION: str = "wdv_display_policy_contract_v1"

# Algorithm version of the display-policy resolver (policy_service + kr_family_policy_resolver).
# Bump when resolver logic changes independently of KR content — i.e. when a new
# block modifies resolution paths, fallback order, or guard conditions in a way
# that changes resolved output for existing KR records.
WDV_DISPLAY_POLICY_RESOLVER_VERSION: str = "wdv_display_policy_resolver_v1"

# Unit-normalization contract version.  Included in the revision hash so that
# future unit-handling changes affecting display policy automatically invalidate
# cached contracts.  Increment when unit normalization rules change.
WDV_DISPLAY_POLICY_UNIT_CONTRACT_VERSION: str = "wdv_display_units_v1"


# ---------------------------------------------------------------------------
# Display-policy revision — content-based, deterministic
# ---------------------------------------------------------------------------

_revision_cache_lock: threading.RLock = threading.RLock()
# (path_str, mtime_ns, file_size_bytes) → sha256_hex
# mtime and size are used ONLY as fast-path cache invalidation hints.
# They do not enter the revision hash itself.
_revision_cache: dict[tuple[str, int, int], str] = {}


def _stable_float(v: Any) -> "str | None":
    """Canonical string for a numeric policy field.

    Uses :.15g — up to 15 significant digits, no trailing zeros.
    Deterministic across Python versions and platforms for all finite
    IEEE 754 double-precision values.  Returns None for absent, non-numeric,
    or non-finite inputs.
    """
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return f"{f:.15g}"


def _display_policy_canonical_payload(records: list) -> dict:
    """Build the canonical policy payload dict from a list of managed records.

    Filters to approved, runtime-eligible records that influence display-policy
    resolution.  Excludes volatile metadata (timestamps, audit history, notes,
    evidence refs, actor fields) that does not affect resolution output.

    Record types included:
      template_scale_default — family-level governed scale defaults
      display_rule           — exact curve-level rendering rules
      alias                  — mnemonic → canonical curve ID mappings
      curve_definition       — canonical curve ID → family/subgroup mappings
    """
    from app.knowledge.governance import GovernanceStatus

    template_scale_defaults: list[dict] = []
    display_rules: list[dict] = []
    aliases: list[dict] = []
    curve_definitions: list[dict] = []

    for record in records:
        if getattr(record, "status", None) is not GovernanceStatus.APPROVED:
            continue
        if getattr(record, "runtime_eligible", True) is False:
            continue

        rt = getattr(record, "record_type", None)
        record_id = str(getattr(record, "record_id", "") or "")

        if rt == "template_scale_default":
            # GenericManagedRecord: schema-driven fields live in extra_fields,
            # accessed via __getattr__.
            template_scale_defaults.append({
                "record_id":         record_id,
                "curve_family":      str(getattr(record, "curve_family", "") or ""),
                "scale_type":        str(getattr(record, "scale_type", "") or ""),
                "scale_min":         _stable_float(getattr(record, "scale_min", None)),
                "scale_max":         _stable_float(getattr(record, "scale_max", None)),
                "display_direction": str(getattr(record, "display_direction", "") or ""),
            })

        elif rt == "display_rule":
            # DisplayRuleRecord uses display_min/display_max and reverse_scale (bool),
            # not scale_min/scale_max or display_direction.
            display_rules.append({
                "record_id":          record_id,
                "canonical_curve_id": str(getattr(record, "canonical_curve_id", "") or ""),
                "scale_type":         str(getattr(record, "scale_type", "") or ""),
                "display_min":        _stable_float(getattr(record, "display_min", None)),
                "display_max":        _stable_float(getattr(record, "display_max", None)),
                "reverse_scale":      bool(getattr(record, "reverse_scale", False)),
            })

        elif rt == "alias":
            # AliasRecord: alias → canonical_curve_id mapping used for mnemonic lookup.
            # context_hint excluded — resolver uses normalized alias only, not context.
            aliases.append({
                "record_id":          record_id,
                "alias":              str(getattr(record, "alias", "") or ""),
                "canonical_curve_id": str(getattr(record, "canonical_curve_id", "") or ""),
            })

        elif rt == "curve_definition":
            # CurveDefinitionRecord: canonical ID → family/subgroup used to resolve
            # curve family from KR curve type ID or alias lookup.
            curve_definitions.append({
                "record_id":          record_id,
                "canonical_curve_id": str(getattr(record, "canonical_curve_id", "") or ""),
                "family":             str(getattr(record, "family", "") or ""),
                "product_subgroup":   str(getattr(record, "product_subgroup", "") or ""),
                "default_unit":       str(getattr(record, "default_unit", "") or ""),
            })

    # Sort each section by record_id for stable ordering independent of KR file order.
    for lst in (template_scale_defaults, display_rules, aliases, curve_definitions):
        lst.sort(key=lambda r: r["record_id"])

    return {
        "display_policy_resolver_version":      WDV_DISPLAY_POLICY_RESOLVER_VERSION,
        "display_policy_unit_contract_version": WDV_DISPLAY_POLICY_UNIT_CONTRACT_VERSION,
        "template_scale_defaults":              template_scale_defaults,
        "display_rules":                        display_rules,
        "aliases":                              aliases,
        "curve_definitions":                    curve_definitions,
    }


def compute_display_policy_revision(
    storage: "ManagedStorage | None" = None,
) -> str:
    """Return the content-based display-policy revision for the current KR state.

    The revision is a SHA-256 of the canonical governed-record payload:
    approved, runtime-eligible template_scale_default, display_rule, alias,
    and curve_definition records, plus the resolver and unit contract versions.

    File mtime and size are used only to determine whether the process-local
    cache needs recomputation — they do not enter the revision hash.

    Contract:
    - Deterministic: same governed content → same revision, regardless of
      file timestamps, deployment instance, or process lifetime.
    - Stable: second call with unchanged KR returns the cached revision
      without re-reading the file.
    - Content-sensitive: any change to a policy-semantic field in an approved,
      runtime-eligible record changes the revision.
    - Timestamp-insensitive: timestamp-only changes (file mtime, updated_at,
      approved_at, etc.) with identical governed content do not change the revision.
    - Bump-sensitive: incrementing WDV_DISPLAY_POLICY_RESOLVER_VERSION or
      WDV_DISPLAY_POLICY_UNIT_CONTRACT_VERSION changes the revision for all KR states.
    """
    from pathlib import Path
    from app.knowledge.managed_storage import ManagedStorage as _ManagedStorage

    storage = storage or _ManagedStorage()
    path = Path(storage.path)

    try:
        stat = path.stat()
        cache_key: tuple[str, int, int] = (str(path), stat.st_mtime_ns, stat.st_size)
    except OSError:
        # KR file absent (first run, test isolation, missing data directory).
        cache_key = (str(path), 0, 0)

    with _revision_cache_lock:
        cached = _revision_cache.get(cache_key)
    if cached is not None:
        return cached

    # Slow path: load records and compute content-based hash.
    records, _ = storage.load()
    payload = _display_policy_canonical_payload(records)
    canonical_json = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    revision = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    with _revision_cache_lock:
        # Replace the entire cache: only one active KR path per process in practice.
        _revision_cache.clear()
        _revision_cache[cache_key] = revision

    return revision


def _clear_display_policy_revision_cache_for_tests() -> None:
    """Clear the in-process revision cache.

    For test isolation only.  Mirrors ManagedKrFamilyDisplayPolicyResolver.clear_cache_for_tests().
    """
    with _revision_cache_lock:
        _revision_cache.clear()


class WdvCurveDisplayPolicyService:
    """Single backend authority for default curve display behaviour."""

    _COLORS = {
        "gamma": "#2f80ed",
        "borehole": "#27ae60",
        "resistivity": "#eb5757",
        "density": "#9b51e0",
        "neutron": "#00a6a6",
        "sonic": "#f2994a",
        "porosity": "#f2c94c",
        "generic": "#2f80ed",
    }

    @classmethod
    def resolve(
        cls,
        item: ManagedProductGroupItem,
        sample_stats: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        stats = sample_stats or {}
        key = (
            f"{item.curve_name} {item.curve_family} {item.curve_type} "
            f"{item.curve_description} {item.curve_unit}"
        ).lower()
        warnings: list[str] = []
        if int(stats.get("rejected_sample_count") or 0) > 0:
            warnings.append("invalid_samples_rejected")

        observed_min = cls._float_or_none(
            stats.get("robust_observed_min", stats.get("observed_min"))
        )
        observed_max = cls._float_or_none(
            stats.get("robust_observed_max", stats.get("observed_max"))
        )
        observed_p05 = cls._float_or_none(stats.get("observed_p05"))
        observed_p95 = cls._float_or_none(stats.get("observed_p95"))
        has_stats = (
            observed_min is not None
            and observed_max is not None
            and observed_max > observed_min
        )
        is_derived = cls._is_derived_or_correction_curve(item)
        curve_class = cls._curve_class(key)

        def finalize(scale: dict[str, Any]) -> dict[str, Any]:
            enriched = cls._add_visual_variation_diagnostics(
                scale,
                observed_min,
                observed_max,
                observed_p05,
                observed_p95,
            )
            enriched["curve_class"] = curve_class
            enriched["default_color"] = cls._COLORS[curve_class]
            enriched["lattice"] = (
                "logarithmic" if enriched.get("type") == "log" else "linear"
            )
            return enriched

        try:
            managed_kr_policy = ManagedKrFamilyDisplayPolicyResolver.resolve(item)
        except (OSError, ValueError, TypeError):
            managed_kr_policy = None
            warnings.append("managed_knowledge_policy_unavailable")

        if managed_kr_policy is not None:
            managed_kr_policy["warnings"] = [
                *warnings,
                *list(managed_kr_policy.get("warnings") or []),
            ]
            return finalize(managed_kr_policy)

        if "resist" in key or "ohmm" in key or "ohm" in key:
            if has_stats and observed_min is not None and observed_min <= 0:
                warnings.append("non_positive_values_for_log_scale")
            return finalize({
                "type": "log",
                "min": 0.2,
                "max": 2000.0,
                "direction": "normal",
                "source": "internal_fallback",
                "warnings": warnings,
            })

        if "gamma" in key or "gapi" in key or re.search(r"\bapi\b", key):
            return finalize({
                "type": "linear",
                "min": 0.0,
                "max": 200.0,
                "direction": "normal",
                "source": "internal_fallback",
                "warnings": warnings,
            })

        if "density" in key or "g/c" in key or "g/cc" in key:
            if is_derived and has_stats:
                low, high = cls._padded_observed_domain(
                    float(observed_min), float(observed_max)
                )
                warnings.append("suspected_correction_or_delta_curve")
                return finalize({
                    "type": "linear",
                    "min": low,
                    "max": high,
                    "direction": "normal",
                    "source": "observed_statistics",
                    "warnings": warnings,
                })
            if has_stats and not cls._domain_overlaps(
                float(observed_min), float(observed_max), 1.0, 4.0
            ):
                low, high = cls._padded_observed_domain(
                    float(observed_min), float(observed_max)
                )
                warnings.append("density_default_not_supported_by_observed_values")
                return finalize({
                    "type": "linear",
                    "min": low,
                    "max": high,
                    "direction": "normal",
                    "source": "observed_statistics",
                    "warnings": warnings,
                })
            return finalize({
                "type": "linear",
                "min": 1.95,
                "max": 2.95,
                "direction": "normal",
                "source": "internal_fallback",
                "warnings": warnings,
            })

        if (
            "neutron" in key
            or "porosity" in key
            or "cfcf" in key
            or "v/v" in key
        ):
            if is_derived and has_stats:
                low, high = cls._padded_observed_domain(
                    float(observed_min), float(observed_max)
                )
                warnings.append("suspected_correction_or_delta_curve")
                return finalize({
                    "type": "linear",
                    "min": high,
                    "max": low,
                    "direction": "reversed",
                    "source": "observed_statistics",
                    "warnings": warnings,
                })
            if has_stats and not cls._domain_overlaps(
                float(observed_min), float(observed_max), -0.25, 0.75
            ):
                low, high = cls._padded_observed_domain(
                    float(observed_min), float(observed_max)
                )
                warnings.append("neutron_default_not_supported_by_observed_values")
                return finalize({
                    "type": "linear",
                    "min": high,
                    "max": low,
                    "direction": "reversed",
                    "source": "observed_statistics",
                    "warnings": warnings,
                })
            return finalize({
                "type": "linear",
                "min": 0.45,
                "max": -0.15,
                "direction": "reversed",
                "source": "internal_fallback",
                "warnings": warnings,
            })

        if "sonic" in key or "delta-t" in key or "us/f" in key or "us/ft" in key:
            return finalize({
                "type": "linear",
                "min": 140.0,
                "max": 40.0,
                "direction": "reversed",
                "source": "internal_fallback",
                "warnings": warnings,
            })

        if "caliper" in key or " in" in key:
            return finalize({
                "type": "linear",
                "min": 6.0,
                "max": 16.0,
                "direction": "normal",
                "source": "internal_fallback",
                "warnings": warnings,
            })

        if "pressure" in key or "psi" in key:
            return finalize({
                "type": "linear",
                "min": 0.0,
                "max": 10000.0,
                "direction": "normal",
                "source": "internal_fallback",
                "warnings": warnings,
            })

        if "temperature" in key or "deg" in key:
            return finalize({
                "type": "linear",
                "min": 0.0,
                "max": 500.0,
                "direction": "normal",
                "source": "internal_fallback",
                "warnings": warnings,
            })

        if has_stats:
            low, high = cls._padded_observed_domain(
                float(observed_min), float(observed_max)
            )
            return finalize({
                "type": "linear",
                "min": low,
                "max": high,
                "direction": "normal",
                "source": "observed_statistics",
                "warnings": warnings,
            })

        return finalize({
            "type": "linear",
            "min": 0.0,
            "max": 150.0,
            "direction": "normal",
            "source": "internal_fallback",
            "warnings": warnings,
        })

    @staticmethod
    def _curve_class(key: str) -> str:
        if "gamma" in key or "gapi" in key or re.search(r"\bapi\b", key):
            return "gamma"
        if "caliper" in key or "borehole" in key:
            return "borehole"
        if "resist" in key or "ohm" in key:
            return "resistivity"
        if "density" in key or "g/cc" in key:
            return "density"
        if "neutron" in key:
            return "neutron"
        if "sonic" in key or "delta-t" in key or "us/ft" in key:
            return "sonic"
        if "porosity" in key or "cfcf" in key or "v/v" in key:
            return "porosity"
        return "generic"

    @staticmethod
    def _is_derived_or_correction_curve(item: ManagedProductGroupItem) -> bool:
        key = (
            f"{item.curve_name} {item.curve_family} {item.curve_type} "
            f"{item.curve_description} {item.display_name}"
        ).lower()
        return any(
            token in key
            for token in (
                "correction",
                "difference",
                "delta",
                "standoff",
                "stand-off",
                "stand off",
                "apparent",
                "ratio",
                "from back scatter",
                "back scatter",
                "inversion",
            )
        )

    @staticmethod
    def _float_or_none(value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    @staticmethod
    def _domain_overlaps(
        low: float,
        high: float,
        reference_low: float,
        reference_high: float,
    ) -> bool:
        return max(low, reference_low) <= min(high, reference_high)

    @staticmethod
    def _padded_observed_domain(low: float, high: float) -> tuple[float, float]:
        if high < low:
            low, high = high, low
        span = high - low
        if span <= 0:
            pad = max(abs(low) * 0.05, 0.1)
            return low - pad, high + pad
        pad = max(span * 0.08, 0.05)
        return low - pad, high + pad

    @classmethod
    def _add_visual_variation_diagnostics(
        cls,
        scale: dict[str, Any],
        observed_min: float | None,
        observed_max: float | None,
        observed_p05: float | None,
        observed_p95: float | None,
    ) -> dict[str, Any]:
        scale.setdefault("display_mode", scale.get("source") or "template_default")
        scale.setdefault(
            "recommended_display_mode",
            scale.get("display_mode"),
        )
        scale.setdefault("standard_type", scale.get("type"))
        scale.setdefault("standard_min", scale.get("min"))
        scale.setdefault("standard_max", scale.get("max"))
        scale.setdefault("standard_direction", scale.get("direction"))

        def set_render_semantics(
            prefix: str,
            left: Any,
            right: Any,
            direction: str,
        ) -> None:
            left_value = cls._float_or_none(left)
            right_value = cls._float_or_none(right)
            if left_value is None or right_value is None:
                return
            numeric_low = min(left_value, right_value)
            numeric_high = max(left_value, right_value)
            if prefix:
                scale[f"{prefix}_display_left_value"] = left_value
                scale[f"{prefix}_display_right_value"] = right_value
                scale[f"{prefix}_numeric_min"] = numeric_low
                scale[f"{prefix}_numeric_max"] = numeric_high
            else:
                scale["display_left_value"] = left_value
                scale["display_right_value"] = right_value
                scale["numeric_min"] = numeric_low
                scale["numeric_max"] = numeric_high
            if direction in {"reverse", "reversed"} and left_value < right_value:
                if prefix:
                    scale[f"{prefix}_display_left_value"] = right_value
                    scale[f"{prefix}_display_right_value"] = left_value
                else:
                    scale["display_left_value"] = right_value
                    scale["display_right_value"] = left_value

        direction = str(scale.get("direction") or "normal")
        set_render_semantics(
            "standard",
            scale.get("standard_min"),
            scale.get("standard_max"),
            str(scale.get("standard_direction") or direction),
        )

        if (
            observed_min is not None
            and observed_max is not None
            and observed_max > observed_min
        ):
            use_p_domain = (
                observed_p05 is not None
                and observed_p95 is not None
                and observed_p95 > observed_p05
            )
            if use_p_domain:
                low, high = cls._padded_observed_domain(
                    float(observed_p05), float(observed_p95)
                )
                scale["robust_observed_domain_source"] = "p05_p95"
            else:
                low, high = cls._padded_observed_domain(
                    float(observed_min), float(observed_max)
                )
                scale["robust_observed_domain_source"] = "observed_min_max"
            scale["robust_observed_numeric_min"] = low
            scale["robust_observed_numeric_max"] = high
            if direction in {"reverse", "reversed"}:
                scale["robust_observed_min"] = high
                scale["robust_observed_max"] = low
                scale["robust_observed_display_left_value"] = high
                scale["robust_observed_display_right_value"] = low
                scale["robust_observed_direction"] = "reversed"
            else:
                scale["robust_observed_min"] = low
                scale["robust_observed_max"] = high
                scale["robust_observed_display_left_value"] = low
                scale["robust_observed_display_right_value"] = high
                scale["robust_observed_direction"] = "normal"
            scale["robust_observed_type"] = scale.get("type") or "linear"

        try:
            display_span = abs(
                float(scale.get("standard_max", scale.get("max")))
                - float(scale.get("standard_min", scale.get("min")))
            )
        except (TypeError, ValueError):
            set_render_semantics("", scale.get("min"), scale.get("max"), direction)
            return scale
        if display_span <= 0 or observed_p05 is None or observed_p95 is None:
            set_render_semantics("", scale.get("min"), scale.get("max"), direction)
            return scale

        observed_span = abs(float(observed_p95) - float(observed_p05))
        ratio = observed_span / display_span if display_span else None
        scale["visual_span_ratio"] = ratio
        if (
            ratio is not None
            and ratio < 0.08
            and scale.get("source") == "managed_knowledge_curve_rule"
            # Log-scale governed ranges (e.g. resistivity 0.2–2000) must never be
            # replaced by observed statistics.  The linear visual_span_ratio is
            # semantically invalid for log data, and any override risks producing a
            # non-positive scale_min that breaks logarithmic rendering entirely.
            and scale.get("type") != "log"
        ):
            warnings = list(scale.get("warnings") or [])
            if "low_visual_variation_on_standard_scale" not in warnings:
                warnings.append("low_visual_variation_on_standard_scale")
            scale["warnings"] = warnings

            robust_left = scale.get(
                "robust_observed_display_left_value",
                scale.get("robust_observed_min"),
            )
            robust_right = scale.get(
                "robust_observed_display_right_value",
                scale.get("robust_observed_max"),
            )
            if (
                robust_left is not None
                and robust_right is not None
                and robust_left != robust_right
            ):
                scale["min"] = robust_left
                scale["max"] = robust_right
                scale["source"] = "robust_observed_statistics"
                scale["display_mode"] = "robust_observed"
                scale["recommended_display_mode"] = "robust_observed"
                scale["mode_reason"] = "low_visual_variation_on_standard_scale"

        set_render_semantics("", scale.get("min"), scale.get("max"), direction)
        return scale
