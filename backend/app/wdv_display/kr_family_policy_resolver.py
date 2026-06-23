"""Managed-KR family display-policy resolver for WDV.

Block 3A intentionally resolves only approved ``template_scale_default``
records. Exact curve-level ``display_rule`` resolution is deferred to a later
bounded block because exact rules currently contain mixed unit conventions
(for example percentage versus fraction porosity scales).
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.inventory.models import ManagedProductGroupItem
from app.knowledge.governance import GovernanceStatus
from app.knowledge.managed_models import DisplayRuleRecord, GenericManagedRecord
from app.knowledge.managed_storage import ManagedStorage


@dataclass(frozen=True)
class _FamilyPolicyIndex:
    storage_path: Path
    file_mtime_ns: int
    file_size: int
    family_defaults: dict[str, GenericManagedRecord]
    # Exact curve-level display rules — approved, runtime_eligible=True only.
    # Keyed by canonical_curve_id.  Populated from display_rule records.
    curve_display_rules: dict[str, DisplayRuleRecord]
    alias_to_canonical: dict[str, str]
    curve_definitions: dict[str, Any]


class ManagedKrFamilyDisplayPolicyResolver:
    """Resolve governed WDV family defaults from the canonical Managed KR."""

    _lock = threading.RLock()
    _cached_index: _FamilyPolicyIndex | None = None

    _FAMILY_ALIASES: dict[str, str] = {
        "gamma": "gamma_ray",
        "gamma_ray": "gamma_ray",
        "gamma_ray_sp": "spectral_gamma_ray",
        "spectral_gamma": "spectral_gamma_ray",
        "spectral_gamma_ray": "spectral_gamma_ray",
        "sp": "spontaneous_potential",
        "spontaneous_potential": "spontaneous_potential",
        "caliper": "caliper",
        "borehole_caliper": "caliper",
        "bit_size": "bit_size",
        "resistivity": "resistivity",
        "resistivity_array": "resistivity",
        "array_resistivity": "resistivity",
        "induction_resistivity": "resistivity",
        "laterolog_resistivity": "resistivity",
        "density": "density",
        "bulk_density": "density",
        "density_correction": "density_correction",
        "neutron": "neutron_porosity",
        "neutron_porosity": "neutron_porosity",
        "sonic": "sonic_slowness",
        "sonic_slowness": "sonic_slowness",
        "compressional_sonic": "sonic_slowness",
        "photoelectric": "photoelectric_factor",
        "photoelectric_factor": "photoelectric_factor",
        "porosity": "porosity",
        "water_saturation": "water_saturation",
        "shale_volume": "shale_volume",
        "permeability": "permeability",
        "pressure": "pressure",
        "temperature": "temperature",
        "spinner_flow": "spinner_flow",
        "collar_locator": "collar_locator",
        "variable_density_log": "variable_density_log",
        "borehole_image": "borehole_image",
        "dip_azimuth": "dip_azimuth",
    }

    @classmethod
    def resolve(
        cls,
        item: ManagedProductGroupItem,
        *,
        storage: ManagedStorage | None = None,
    ) -> dict[str, Any] | None:
        """Resolve an approved WDV curve or family display policy.

        UNIT-1 deliberately preserves the established runtime contract:
        a resolved policy dictionary is returned when an approved rule exists,
        otherwise ``None``.  The new policy-unit contract is dormant until the
        governed KR migration is complete and strict activation is performed in
        a later bounded block.
        """
        storage = storage or ManagedStorage()
        index = cls._index(storage)

        exact = cls._resolve_exact_curve_rule(item, index)
        if exact is not None:
            return exact

        family = cls._resolve_family(item, index)
        if family is None:
            return None

        record = index.family_defaults.get(family)
        if record is None:
            return None

        scale_type = str(getattr(record, "scale_type", "") or "").strip()
        scale_min = getattr(record, "scale_min", None)
        scale_max = getattr(record, "scale_max", None)
        direction = str(
            getattr(record, "display_direction", "normal") or "normal"
        ).strip()

        if scale_type in {"event_track", "waveform_track", "image_track", "tadpole_track"}:
            return None
        if scale_min is None or scale_max is None:
            return None
        if scale_type == "log" and (
            float(scale_min) <= 0 or float(scale_max) <= float(scale_min)
        ):
            return None

        return {
            "type": scale_type,
            "min": float(scale_min),
            "max": float(scale_max),
            "direction": direction,
            "source": "managed_knowledge_family_default",
            "policy_record_id": record.record_id,
            "policy_record_version": record.version,
            "curve_family": family,
            "warnings": [],
        }

    @classmethod
    def _resolve_exact_curve_rule(
        cls,
        item: ManagedProductGroupItem,
        index: "_FamilyPolicyIndex",
    ) -> "dict[str, Any] | None":
        """Return a policy dict from an exact approved display_rule, or None.

        Resolution order for canonical_curve_id:
          1. item.kr_curve_type_id (direct canonical ID from import)
          2. alias_to_canonical lookup on observed_mnemonic, normalized_mnemonic, curve_name
          3. No further fallback — item.curve_family is a family, not a canonical curve ID

        Only display_rule records with runtime_eligible is True are used.
        """
        canonical_id = cls._resolve_canonical_curve_id(item, index)
        if canonical_id is None:
            return None

        rule = index.curve_display_rules.get(canonical_id)
        if rule is None:
            return None

        scale_type = str(getattr(rule, "scale_type", "") or "").strip() or "linear"
        display_min = getattr(rule, "display_min", None)
        display_max = getattr(rule, "display_max", None)
        reverse_scale = bool(getattr(rule, "reverse_scale", False))

        if display_min is None or display_max is None:
            return None
        if scale_type == "log" and (
            float(display_min) <= 0 or float(display_max) <= float(display_min)
        ):
            return None

        direction = "reversed" if reverse_scale else "normal"
        return {
            "type": scale_type,
            "min": float(display_min),
            "max": float(display_max),
            "direction": direction,
            "source": "managed_knowledge_curve_rule",
            "policy_record_id": rule.record_id,
            "policy_record_version": rule.version,
            "canonical_curve_id": canonical_id,
            "warnings": [],
        }

    @classmethod
    def _resolve_canonical_curve_id(
        cls,
        item: ManagedProductGroupItem,
        index: "_FamilyPolicyIndex",
    ) -> "str | None":
        """Resolve a canonical_curve_id from item identity fields.

        Uses kr_curve_type_id first (direct canonical reference), then
        alias lookup on observed/normalized mnemonic and curve_name.
        Does NOT use curve_family — that is a family key, not a curve ID.
        """
        if item.kr_curve_type_id:
            canonical = str(item.kr_curve_type_id).strip()
            if canonical in index.curve_display_rules:
                return canonical

        for raw in (item.observed_mnemonic, item.normalized_mnemonic, item.curve_name):
            alias = cls._normalize_alias(str(raw or ""))
            canonical = index.alias_to_canonical.get(alias)
            if canonical and canonical in index.curve_display_rules:
                return canonical

        return None

    @classmethod
    def _index(cls, storage: ManagedStorage) -> _FamilyPolicyIndex:
        path = Path(storage.path)
        stat = path.stat()
        with cls._lock:
            cached = cls._cached_index
            if (
                cached is not None
                and cached.storage_path == path
                and cached.file_mtime_ns == stat.st_mtime_ns
                and cached.file_size == stat.st_size
            ):
                return cached

            records, _ = storage.load()
            family_defaults: dict[str, GenericManagedRecord] = {}
            # Only runtime_eligible=True display rules are authoritative for
            # exact curve resolution.  runtime_eligible=None records (e.g. the
            # bulk PWLS import set) are not yet curated for runtime use and are
            # excluded here.  They remain in the C1 semantic revision hash under
            # the existing is-False filter — that filter is unchanged by C2.
            curve_display_rules: dict[str, DisplayRuleRecord] = {}
            alias_to_canonical: dict[str, str] = {}
            curve_definitions: dict[str, Any] = {}

            for record in records:
                if getattr(record, "status", None) is not GovernanceStatus.APPROVED:
                    continue
                record_type = getattr(record, "record_type", None)

                if record_type == "display_rule":
                    # Strict runtime_eligible filter for exact rule resolution.
                    if getattr(record, "runtime_eligible", None) is not True:
                        continue
                    canonical = str(
                        getattr(record, "canonical_curve_id", "") or ""
                    ).strip()
                    if canonical:
                        curve_display_rules[canonical] = record
                else:
                    # Family defaults, aliases, curve definitions use the
                    # existing lenient filter (not-False includes None).
                    if getattr(record, "runtime_eligible", True) is False:
                        continue

                    if record_type == "template_scale_default":
                        family = cls._normalize(
                            str(getattr(record, "curve_family", "") or "")
                        )
                        if family:
                            family_defaults[family] = record
                    elif record_type == "alias":
                        alias = cls._normalize_alias(
                            str(getattr(record, "alias", "") or "")
                        )
                        canonical = str(
                            getattr(record, "canonical_curve_id", "") or ""
                        ).strip()
                        if alias and canonical:
                            alias_to_canonical[alias] = canonical
                    elif record_type == "curve_definition":
                        canonical = str(
                            getattr(record, "canonical_curve_id", "") or ""
                        ).strip()
                        if canonical:
                            curve_definitions[canonical] = record

            built = _FamilyPolicyIndex(
                storage_path=path,
                file_mtime_ns=stat.st_mtime_ns,
                file_size=stat.st_size,
                family_defaults=family_defaults,
                curve_display_rules=curve_display_rules,
                alias_to_canonical=alias_to_canonical,
                curve_definitions=curve_definitions,
            )
            cls._cached_index = built
            return built

    @classmethod
    def _resolve_family(
        cls,
        item: ManagedProductGroupItem,
        index: _FamilyPolicyIndex,
    ) -> str | None:
        canonical_candidates: list[str] = []

        if item.kr_curve_type_id:
            canonical_candidates.append(str(item.kr_curve_type_id).strip())

        for raw in (
            item.observed_mnemonic,
            item.normalized_mnemonic,
            item.curve_name,
        ):
            alias = cls._normalize_alias(str(raw or ""))
            canonical = index.alias_to_canonical.get(alias)
            if canonical:
                canonical_candidates.append(canonical)

        for canonical in canonical_candidates:
            definition = index.curve_definitions.get(canonical)
            if definition is None:
                continue
            for raw_family in (
                getattr(definition, "family", None),
                getattr(definition, "product_subgroup", None),
            ):
                resolved = cls._family_key(raw_family, index)
                if resolved:
                    return resolved

        for raw_family in (
            item.curve_family,
            item.product_subgroup_key,
            item.curve_type,
        ):
            resolved = cls._family_key(raw_family, index)
            if resolved:
                return resolved

        return None

    @classmethod
    def _family_key(
        cls,
        raw: Any,
        index: _FamilyPolicyIndex,
    ) -> str | None:
        normalized = cls._normalize(str(raw or ""))
        if not normalized:
            return None
        if normalized in index.family_defaults:
            return normalized
        mapped = cls._FAMILY_ALIASES.get(normalized)
        if mapped in index.family_defaults:
            return mapped

        # Conservative token fallback for broad, well-established families.
        token_map = (
            ("resist", "resistivity"),
            ("gamma", "gamma_ray"),
            ("neutron", "neutron_porosity"),
            ("density_correction", "density_correction"),
            ("density", "density"),
            ("sonic", "sonic_slowness"),
            ("caliper", "caliper"),
            ("pressure", "pressure"),
            ("temperature", "temperature"),
            ("permeab", "permeability"),
        )
        for token, family in token_map:
            if token in normalized and family in index.family_defaults:
                return family
        return None

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", value.lower())).strip("_")

    @staticmethod
    def _normalize_alias(value: str) -> str:
        return re.sub(r"[^A-Z0-9]+", "", value.upper())

    @classmethod
    def clear_cache_for_tests(cls) -> None:
        with cls._lock:
            cls._cached_index = None
