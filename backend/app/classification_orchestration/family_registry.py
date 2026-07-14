"""Canonical backend-owned curve-family identity registry.

The registry composes the complete family vocabulary from two existing backend
sources of truth:
  * deterministic well-log classification vocabulary; and
  * approved runtime KR curve-definition families.

Raw/source nomenclature is retained as aliases. Canonical keys are normalized
lookup identities only. Duplicate nomenclature forms for the same canonical key
are merged; aliases that would point to different canonical keys are rejected.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable, Optional

from app.classification.well_log_vocabulary import (
    CASED_HOLE_CURVE_FAMILIES,
    COMPLETION_INTEGRITY_FAMILIES,
    LITHOLOGY_CORE_MARKER_FAMILIES,
    OPEN_HOLE_CURVE_FAMILIES,
    PRESSURE_PRODUCTION_FLUID_FAMILIES,
)
from app.knowledge.contextual_curve_resolver import governed_contextual_families

_UNCLASSIFIED_KEY = "unclassified"
_UNCLASSIFIED_LABEL = "Unclassified"
_REGISTRY_VERSION = "canonical-curve-family-registry-v3"


def canonical_family_key(value: str | None) -> str:
    words = re.findall(r"[a-z0-9]+", str(value or "").strip().lower())
    return "_".join(words)


def _display_label(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    # Preserve governed acronyms/casing. Only synthesize a label for machine keys.
    if "_" in raw and raw == raw.lower() and " " not in raw:
        return raw.replace("_", " ").title()
    return raw


@dataclass(frozen=True)
class CanonicalCurveFamily:
    family_key: str
    display_label: str
    aliases: tuple[str, ...] = ()
    active: bool = True
    registry_version: str = _REGISTRY_VERSION


class CanonicalCurveFamilyRegistry:
    """Backend-owned family identity registry with collision protection."""

    def __init__(self, families: Iterable[CanonicalCurveFamily] = ()) -> None:
        self._by_key: dict[str, CanonicalCurveFamily] = {}
        self._alias_to_key: dict[str, str] = {}
        self.register(
            CanonicalCurveFamily(
                family_key=_UNCLASSIFIED_KEY,
                display_label=_UNCLASSIFIED_LABEL,
                aliases=("unknown", "other review required"),
            )
        )
        for family in families:
            self.register(family)

    @staticmethod
    def _deterministic_labels() -> set[str]:
        labels: set[str] = set()
        for mapping in (
            OPEN_HOLE_CURVE_FAMILIES,
            CASED_HOLE_CURVE_FAMILIES,
            LITHOLOGY_CORE_MARKER_FAMILIES,
            PRESSURE_PRODUCTION_FLUID_FAMILIES,
            COMPLETION_INTEGRITY_FAMILIES,
        ):
            labels.update(value[0] for value in mapping.values())
        labels.update(governed_contextual_families())
        return labels

    @classmethod
    def from_existing_backend_vocabulary(cls) -> "CanonicalCurveFamilyRegistry":
        registry = cls()
        for label in sorted(cls._deterministic_labels()):
            registry.register_source_family(label)
        return registry

    @classmethod
    def from_authoritative_sources(
        cls,
        runtime_resolver: Any | None = None,
    ) -> "CanonicalCurveFamilyRegistry":
        """Compose deterministic vocabulary plus approved runtime KR families.

        The resolver is intentionally injected. This keeps KR access at the
        backend composition boundary and makes the registry independently testable.
        Only records exposed by the approved runtime resolver are admitted.
        """
        registry = cls.from_existing_backend_vocabulary()
        if runtime_resolver is None:
            return registry
        records = runtime_resolver.list_runtime_records(record_type="curve_definition")
        for record in records:
            family = getattr(record, "family", None)
            if family is not None and str(family).strip():
                registry.register_source_family(str(family))
        return registry

    @classmethod
    def default(cls, runtime_resolver: Any | None = None) -> "CanonicalCurveFamilyRegistry":
        """Compatibility composition entry point used by shadow infrastructure."""
        return cls.from_authoritative_sources(runtime_resolver=runtime_resolver)

    def register_source_family(self, source_family: str) -> None:
        raw = str(source_family or "").strip()
        key = canonical_family_key(raw)
        if not key:
            raise ValueError("Source family must not be blank")
        self.register(
            CanonicalCurveFamily(
                family_key=key,
                display_label=_display_label(raw),
                aliases=(raw, raw.lower(), raw.upper(), key),
            )
        )

    def register(self, family: CanonicalCurveFamily) -> None:
        key = canonical_family_key(family.family_key)
        if not key:
            raise ValueError("Canonical family key must not be blank")

        incoming_label = family.display_label.strip() or key.replace("_", " ").title()
        existing_family = self._by_key.get(key)
        if existing_family is not None:
            # Same canonical identity: merge nomenclature, preserving the first
            # governed display label rather than allowing later source casing to
            # rewrite user-facing presentation.
            merged_aliases = tuple(dict.fromkeys((
                *existing_family.aliases,
                incoming_label,
                *family.aliases,
            )))
            normalized = CanonicalCurveFamily(
                family_key=key,
                display_label=existing_family.display_label,
                aliases=merged_aliases,
                active=existing_family.active and family.active,
                registry_version=_REGISTRY_VERSION,
            )
        else:
            normalized = CanonicalCurveFamily(
                family_key=key,
                display_label=incoming_label,
                aliases=tuple(family.aliases),
                active=family.active,
                registry_version=_REGISTRY_VERSION,
            )

        aliases = {key, normalized.display_label, *normalized.aliases}
        for alias in aliases:
            alias_key = canonical_family_key(alias)
            if not alias_key:
                continue
            other = self._alias_to_key.get(alias_key)
            if other is not None and other != key:
                raise ValueError(
                    f"Canonical family alias collision: {alias!r} -> {other!r}/{key!r}"
                )

        self._by_key[key] = normalized
        for alias in aliases:
            alias_key = canonical_family_key(alias)
            if alias_key:
                self._alias_to_key[alias_key] = key


    def governed_measurement_matches_family(
        self,
        measurement_value: str | None,
        *,
        governed_family_value: str | None,
        runtime_payload: Any | None = None,
    ) -> bool:
        """Return True only for a KR-governed measurement→family relationship.

        This does not create a global alias.  It evaluates one runtime
        classification result and accepts a more-specific measurement label
        only when that same approved KR result explicitly identifies the
        measurement and its broader governed family.
        """
        family = self.resolve(governed_family_value)
        if family is None:
            return False

        measurement_key = canonical_family_key(measurement_value)
        if not measurement_key or measurement_key == family.family_key:
            return False

        payload = runtime_payload if isinstance(runtime_payload, dict) else {}
        governed_measurement_values = (
            payload.get("canonical_curve_id"),
            payload.get("display_name"),
            payload.get("technical_curve_id"),
            payload.get("technical_display_name"),
            payload.get("measurement_family"),
        )
        for value in governed_measurement_values:
            if canonical_family_key(value) == measurement_key:
                return True
        return False

    def resolve(self, value: str | None) -> Optional[CanonicalCurveFamily]:
        alias_key = canonical_family_key(value)
        canonical_key = self._alias_to_key.get(alias_key)
        if canonical_key is None:
            return None
        family = self._by_key[canonical_key]
        return family if family.active else None

    def require(self, value: str | None) -> CanonicalCurveFamily:
        family = self.resolve(value)
        if family is None:
            raise ValueError(f"Unregistered curve family: {value!r}")
        return family

    def unclassified(self) -> CanonicalCurveFamily:
        return self._by_key[_UNCLASSIFIED_KEY]

    def list_active(self) -> tuple[CanonicalCurveFamily, ...]:
        return tuple(sorted(
            (item for item in self._by_key.values() if item.active),
            key=lambda item: item.family_key,
        ))
