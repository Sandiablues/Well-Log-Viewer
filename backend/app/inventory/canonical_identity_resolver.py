"""Canonical UUIDv7 inventory resolution for WDV and WBV consumers.

This module is the single backend-owned lookup boundary between canonical
managed identities and persisted inventory records. Legacy identifiers are
reported as aliases but are never accepted as canonical lookup keys.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.identity import LegacyIdentityAlias, parse_uuid7

from .models import ManagedProductGroupItem, ManagedSourceReference, ManagedWellRecord
from .repository import ManagedWellInventoryRepository, ManagedWellNotFoundError


class CanonicalIdentityResolutionError(ValueError):
    """Raised when canonical inventory identity is absent, invalid, or ambiguous."""


@dataclass(frozen=True)
class ResolvedManagedCurve:
    well: ManagedWellRecord
    product: ManagedProductGroupItem
    source: ManagedSourceReference

    @property
    def managed_well_uid(self) -> str:
        return _required_uuid7(self.well.managed_well_uid, "managed_well_uid")

    @property
    def managed_curve_uid(self) -> str:
        return _required_uuid7(self.product.managed_curve_uid, "managed_curve_uid")

    @property
    def managed_product_uid(self) -> str:
        return _required_uuid7(self.product.managed_product_uid, "managed_product_uid")

    @property
    def managed_source_uid(self) -> str:
        return _required_uuid7(self.product.managed_source_uid, "managed_source_uid")

    @property
    def managed_wellbore_uid(self) -> str | None:
        value = self.product.managed_wellbore_uid or self.well.managed_wellbore_uid
        return str(parse_uuid7(str(value))) if value is not None else None

    def legacy_ids(self) -> tuple[LegacyIdentityAlias, ...]:
        values: list[LegacyIdentityAlias] = []
        values.extend(self.well.legacy_ids)
        values.extend(self.product.legacy_ids)
        if self.well.managed_well_id:
            values.append(LegacyIdentityAlias(scheme="managed_well_id", value=self.well.managed_well_id))
        if self.product.product_id:
            values.append(LegacyIdentityAlias(scheme="product_id", value=self.product.product_id))
        if self.product.curve_uid:
            values.append(LegacyIdentityAlias(scheme="curve_uid", value=self.product.curve_uid))
        if self.product.curve_name:
            values.append(LegacyIdentityAlias(scheme="curve_id", value=self.product.curve_name))
        return _dedupe_aliases(values)


@dataclass(frozen=True)
class CanonicalIdentityReadinessIssue:
    code: str
    entity: str
    legacy_key: str
    message: str


@dataclass(frozen=True)
class CanonicalIdentityReadinessReport:
    wells_checked: int
    products_checked: int
    sources_checked: int
    issues: tuple[CanonicalIdentityReadinessIssue, ...]

    @property
    def ready(self) -> bool:
        return not self.issues

    def as_dict(self) -> dict[str, object]:
        return {
            "ready": self.ready,
            "wells_checked": self.wells_checked,
            "products_checked": self.products_checked,
            "sources_checked": self.sources_checked,
            "issues": [issue.__dict__ for issue in self.issues],
        }


class CanonicalInventoryIdentityResolver:
    """Resolve canonical inventory identities without legacy fallback."""

    def __init__(self, repository: ManagedWellInventoryRepository | None = None) -> None:
        self.repository = repository or ManagedWellInventoryRepository()

    def resolve_well(self, managed_well_uid: str) -> ManagedWellRecord:
        canonical = str(parse_uuid7(managed_well_uid))
        matches = [
            record for record in self.repository.list_records()
            if record.managed_well_uid is not None and str(record.managed_well_uid) == canonical
        ]
        return _exactly_one(matches, "managed_well_uid", canonical)

    def resolve_curve(self, managed_well_uid: str, managed_curve_uid: str) -> ResolvedManagedCurve:
        well = self.resolve_well(managed_well_uid)
        curve_uid = str(parse_uuid7(managed_curve_uid))
        matches: list[ManagedProductGroupItem] = []
        for group in well.product_groups:
            for item in group.items:
                if item.managed_curve_uid is not None and str(item.managed_curve_uid) == curve_uid:
                    matches.append(item)
        product = _exactly_one(matches, "managed_curve_uid", curve_uid)
        source_uid = _required_uuid7(product.managed_source_uid, "managed_source_uid")
        source_matches = [
            source for source in well.source_references
            if source.managed_source_uid is not None and str(source.managed_source_uid) == source_uid
        ]
        source = _exactly_one(source_matches, "managed_source_uid", source_uid)
        return ResolvedManagedCurve(well=well, product=product, source=source)

    def readiness_report(self) -> CanonicalIdentityReadinessReport:
        issues: list[CanonicalIdentityReadinessIssue] = []
        wells = self.repository.list_records()
        seen_wells: dict[str, str] = {}
        seen_products: dict[str, str] = {}
        seen_curves: dict[str, str] = {}
        seen_sources: dict[str, str] = {}
        product_count = 0
        source_count = 0

        for well in wells:
            well_key = well.managed_well_id
            _check_uid(issues, seen_wells, well.managed_well_uid, "managed_well", well_key)

            for source in well.source_references:
                source_count += 1
                _check_uid(issues, seen_sources, source.managed_source_uid, "managed_source", source.source_id)

            for group in well.product_groups:
                for item in group.items:
                    product_count += 1
                    _check_uid(issues, seen_products, item.managed_product_uid, "managed_product", item.product_id)
                    _check_uid(issues, seen_curves, item.managed_curve_uid, "managed_curve", item.product_id)
                    if item.managed_source_uid is None:
                        issues.append(CanonicalIdentityReadinessIssue(
                            code="missing_managed_source_uid",
                            entity="managed_curve",
                            legacy_key=item.product_id,
                            message="Curve occurrence is not linked to a canonical managed source",
                        ))
                    if well.managed_well_uid is not None and item.well_uid not in (None, str(well.managed_well_uid)):
                        issues.append(CanonicalIdentityReadinessIssue(
                            code="legacy_well_uid_disagrees",
                            entity="managed_curve",
                            legacy_key=item.product_id,
                            message="Legacy well_uid disagrees with canonical managed_well_uid",
                        ))

        return CanonicalIdentityReadinessReport(
            wells_checked=len(wells),
            products_checked=product_count,
            sources_checked=source_count,
            issues=tuple(issues),
        )


def _required_uuid7(value: object | None, field_name: str) -> str:
    if value is None:
        raise CanonicalIdentityResolutionError(f"Missing canonical {field_name}")
    try:
        return str(parse_uuid7(str(value)))
    except ValueError as exc:
        raise CanonicalIdentityResolutionError(f"Invalid canonical {field_name}: {value}") from exc


def _exactly_one(matches: list[object], field_name: str, value: str):
    if not matches:
        raise ManagedWellNotFoundError(value)
    if len(matches) > 1:
        raise CanonicalIdentityResolutionError(f"Ambiguous {field_name}: {value}")
    return matches[0]


def _check_uid(
    issues: list[CanonicalIdentityReadinessIssue],
    seen: dict[str, str],
    value: object | None,
    entity: str,
    legacy_key: str,
) -> None:
    field = f"{entity}_uid"
    if value is None:
        issues.append(CanonicalIdentityReadinessIssue(
            code=f"missing_{field}", entity=entity, legacy_key=legacy_key,
            message=f"{entity} has no canonical UUIDv7 identity",
        ))
        return
    try:
        canonical = str(parse_uuid7(str(value)))
    except ValueError:
        issues.append(CanonicalIdentityReadinessIssue(
            code=f"invalid_{field}", entity=entity, legacy_key=legacy_key,
            message=f"{entity} canonical identity is not UUIDv7",
        ))
        return
    prior = seen.get(canonical)
    if prior is not None and prior != legacy_key:
        issues.append(CanonicalIdentityReadinessIssue(
            code=f"duplicate_{field}", entity=entity, legacy_key=legacy_key,
            message=f"Canonical identity is already assigned to {prior}",
        ))
    else:
        seen[canonical] = legacy_key


def _dedupe_aliases(values: Iterable[LegacyIdentityAlias]) -> tuple[LegacyIdentityAlias, ...]:
    output: list[LegacyIdentityAlias] = []
    seen: set[tuple[str, str]] = set()
    for value in values:
        key = (value.scheme, value.value)
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
    return tuple(output)
