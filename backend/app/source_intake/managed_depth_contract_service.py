"""Source Intake → managed inventory depth-contract projection.

This service is generic and UUID-preserving.  It projects current WSI depth
facts into managed-source contracts, then recomputes each managed well's
canonical depth reference without merging unlike numeric units.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.depth_reference import (
    DepthReferenceError,
    build_well_depth_contract,
    canonical_depth_unit,
    make_source_depth_contract,
    source_contract_from_metadata,
)
from app.inventory.models import ManagedInventorySnapshot, ManagedWellRecord
from app.inventory.repository import ManagedWellInventoryRepository

from .models import SourceFileCandidate, SourceIntakeDepthNormalizationStatus


class ManagedDepthContractError(ValueError):
    pass


def source_depth_contract_from_candidate(candidate: SourceFileCandidate) -> dict[str, Any]:
    parsed = candidate.parsed_metadata
    if parsed is None or parsed.log_header is None:
        raise ManagedDepthContractError(
            f"Candidate {candidate.source_file_id} has no parsed log depth header"
        )
    header = parsed.log_header
    if header.start_depth is None or header.stop_depth is None:
        raise ManagedDepthContractError(
            f"Candidate {candidate.source_file_id} has no complete parsed depth range"
        )

    normalization = candidate.depth_normalization
    if normalization is not None and normalization.status == SourceIntakeDepthNormalizationStatus.HUMAN_RESOLVED:
        decision = normalization.decision
        if decision is None or canonical_depth_unit(decision.target_unit) is None:
            raise ManagedDepthContractError(
                f"Candidate {candidate.source_file_id} has an invalid human depth decision"
            )
        return make_source_depth_contract(
            raw_unit=normalization.raw_unit,
            raw_minimum=normalization.raw_start_depth,
            raw_maximum=normalization.raw_stop_depth,
            normalized_unit=decision.target_unit,
            normalized_minimum=header.start_depth,
            normalized_maximum=header.stop_depth,
            basis="human_resolved",
            decision=decision.model_dump(mode="json"),
        )

    native_unit = canonical_depth_unit(header.depth_unit)
    if native_unit is None:
        raise ManagedDepthContractError(
            f"Candidate {candidate.source_file_id} depth unit {header.depth_unit!r} requires a human target decision"
        )
    return make_source_depth_contract(
        raw_unit=header.depth_unit,
        raw_minimum=header.start_depth,
        raw_maximum=header.stop_depth,
        normalized_unit=native_unit,
        normalized_minimum=header.start_depth,
        normalized_maximum=header.stop_depth,
        basis="source_native",
    )


def preferred_well_unit_from_candidate(candidate: SourceFileCandidate) -> str | None:
    normalization = candidate.depth_normalization
    if (
        normalization is not None
        and normalization.status == SourceIntakeDepthNormalizationStatus.HUMAN_RESOLVED
        and normalization.decision is not None
    ):
        return canonical_depth_unit(normalization.decision.target_unit)
    return None


def project_candidate_depth_contract(
    record: ManagedWellRecord,
    candidate: SourceFileCandidate,
) -> ManagedWellRecord:
    """Project one candidate into its exact managed source occurrence.

    Matching is by exact source-intake occurrence id only.  Checksums are not
    identity and are never used for source selection.
    """
    contract = source_depth_contract_from_candidate(candidate)
    matching_sources = [
        source for source in record.source_references
        if source.source_id == candidate.source_file_id
        or source.metadata.get("source_intake_candidate_id") == candidate.source_file_id
    ]
    if len(matching_sources) != 1:
        raise ManagedDepthContractError(
            f"Expected exactly one managed source occurrence for candidate {candidate.source_file_id}; "
            f"found {len(matching_sources)}"
        )
    target_source = matching_sources[0]
    next_sources = []
    for source in record.source_references:
        if source is target_source:
            next_sources.append(source.model_copy(update={
                "metadata": {**source.metadata, "depth_reference": contract},
            }))
        else:
            next_sources.append(source)

    source_uid = str(target_source.managed_source_uid) if target_source.managed_source_uid else None
    next_groups = []
    native = contract["source_native"]
    for group in record.product_groups:
        next_items = []
        for item in group.items:
            owns_source = (
                (source_uid is not None and item.managed_source_uid is not None and str(item.managed_source_uid) == source_uid)
                or item.source_intake_candidate_id == candidate.source_file_id
                or item.source_id == candidate.source_file_id
            )
            if owns_source:
                next_items.append(item.model_copy(update={
                    "depth_units": native["unit"],
                    "depth_start": native["minimum"],
                    "depth_end": native["maximum"],
                    "provenance": {**item.provenance, "depth_reference": contract},
                }))
            else:
                next_items.append(item)
        next_groups.append(group.model_copy(update={"items": next_items}))

    projected = record.model_copy(update={
        "source_references": next_sources,
        "product_groups": next_groups,
    })
    return recompute_managed_well_depth_contract(
        projected,
        preferred_unit=preferred_well_unit_from_candidate(candidate),
    )


def recompute_managed_well_depth_contract(
    record: ManagedWellRecord,
    *,
    preferred_unit: str | None = None,
) -> ManagedWellRecord:
    direct_contracts: list[dict[str, Any]] = []
    for source in record.source_references:
        contract = source_contract_from_metadata(source.metadata)
        if contract is not None:
            direct_contracts.append(contract)
    if not direct_contracts:
        raise ManagedDepthContractError(
            f"Managed well {record.managed_well_uid or record.managed_well_id} has no usable source depth contracts"
        )
    existing = record.metadata.get("depth_reference")
    try:
        initial = build_well_depth_contract(
            existing_contract=existing if isinstance(existing, dict) else None,
            existing_well_unit=record.depth_unit,
            source_contracts=direct_contracts,
            preferred_unit=preferred_unit,
        )
    except DepthReferenceError as exc:
        raise ManagedDepthContractError(str(exc)) from exc

    # Once the managed-well reference is explicit, legacy scaled sources can be
    # projected into that reference without guessing. Persist those contracts so
    # future reads do not depend on migration order or another source.
    next_sources = []
    contract_by_source_uid: dict[str, dict[str, Any]] = {}
    contract_by_source_id: dict[str, dict[str, Any]] = {}
    complete_contracts: list[dict[str, Any]] = []
    for source in record.source_references:
        contract = source_contract_from_metadata(
            source.metadata,
            fallback_target_unit=initial["unit"],
        )
        if contract is None:
            next_sources.append(source)
            continue
        complete_contracts.append(contract)
        next_sources.append(source.model_copy(update={
            "metadata": {**source.metadata, "depth_reference": contract},
        }))
        if source.managed_source_uid is not None:
            contract_by_source_uid[str(source.managed_source_uid)] = contract
        contract_by_source_id[source.source_id] = contract

    if not complete_contracts:
        raise ManagedDepthContractError(
            f"Managed well {record.managed_well_uid or record.managed_well_id} has no complete depth contracts"
        )
    try:
        contract = build_well_depth_contract(
            existing_contract=initial,
            existing_well_unit=initial["unit"],
            source_contracts=complete_contracts,
        )
    except DepthReferenceError as exc:
        raise ManagedDepthContractError(str(exc)) from exc

    next_groups = []
    for group in record.product_groups:
        next_items = []
        for item in group.items:
            source_contract = None
            if item.managed_source_uid is not None:
                source_contract = contract_by_source_uid.get(str(item.managed_source_uid))
            if source_contract is None and item.source_id:
                source_contract = contract_by_source_id.get(item.source_id)
            if source_contract is None:
                next_items.append(item)
                continue
            native = source_contract["source_native"]
            next_items.append(item.model_copy(update={
                "depth_units": native["unit"],
                "depth_start": native["minimum"],
                "depth_end": native["maximum"],
                "provenance": {**item.provenance, "depth_reference": source_contract},
            }))
        next_groups.append(group.model_copy(update={"items": next_items}))

    return record.model_copy(update={
        "depth_unit": contract["unit"],
        "top_depth": contract["minimum"],
        "base_depth": contract["maximum"],
        "source_references": next_sources,
        "product_groups": next_groups,
        "metadata": {**record.metadata, "depth_reference": contract},
    })


class ManagedDepthContractMigrationService:
    """Idempotently backfill current WSI contracts into managed inventory."""

    def __init__(self, repository: ManagedWellInventoryRepository | None = None) -> None:
        self.repository = repository or ManagedWellInventoryRepository()

    def migrate(self, candidates: Iterable[SourceFileCandidate]) -> ManagedInventorySnapshot:
        by_id = {candidate.source_file_id: candidate for candidate in candidates}
        snapshot = self.repository.snapshot()
        records: list[ManagedWellRecord] = []
        for record in snapshot.records:
            next_record = record
            for source in record.source_references:
                candidate_id = source.metadata.get("source_intake_candidate_id") or source.source_id
                candidate = by_id.get(str(candidate_id))
                if candidate is None:
                    continue
                try:
                    next_record = project_candidate_depth_contract(next_record, candidate)
                except ManagedDepthContractError:
                    # Unresolved/unsupported candidates remain untouched and cannot
                    # silently influence the canonical WDV depth contract.
                    continue
            try:
                next_record = recompute_managed_well_depth_contract(next_record)
            except ManagedDepthContractError:
                pass
            records.append(next_record)
        migrated = snapshot.model_copy(update={"records": records})
        self.repository.write_snapshot(migrated)
        return migrated
