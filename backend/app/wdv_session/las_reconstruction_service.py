"""Complete-LAS reconstruction using managed source and canonical WDV commands."""
from __future__ import annotations

from app.identity import new_uuid7_str, parse_uuid7
from app.identity.wdv_contract_v2 import WdvCanonicalTrack
from app.inventory.models import ManagedSourceKind, ManagedWdvState
from app.inventory.repository import ManagedWellInventoryRepository, ManagedWellNotFoundError
from app.inventory.service import ManagedWellInventoryService
from app.wdv_session.canonical_command_service import CanonicalWdvCommandService
from app.wdv_session.canonical_service import CanonicalSessionRevisionConflict
from app.wdv_session.las_reconstruction_models import (
    LasReconstructionCurve,
    LasReconstructionPlan,
    LasSourceList,
    LasSourceOption,
    LogImageSourceList,
    LogImageSourceOption,
    LoadCompleteLasCommand,
    LoadCompleteLasResponse,
)


class LasReconstructionError(ValueError):
    pass


class LasReconstructionService:
    def __init__(
        self,
        repository: ManagedWellInventoryRepository | None = None,
        inventory_service: ManagedWellInventoryService | None = None,
        command_service: CanonicalWdvCommandService | None = None,
    ) -> None:
        self.repository = repository or ManagedWellInventoryRepository()
        self.inventory_service = inventory_service or ManagedWellInventoryService(repository=self.repository)
        self.command_service = command_service or CanonicalWdvCommandService()

    def list_sources(self, managed_well_uid: str) -> LasSourceList:
        canonical_well_uid = str(parse_uuid7(managed_well_uid))
        matches = [
            record for record in self.repository.list_records()
            if record.managed_well_uid and str(record.managed_well_uid) == canonical_well_uid
        ]
        if len(matches) != 1:
            raise ManagedWellNotFoundError(managed_well_uid)
        record = matches[0]
        curve_counts: dict[str, int] = {}
        for group in record.product_groups:
            for item in group.items:
                if item.source_id:
                    curve_counts[item.source_id] = curve_counts.get(item.source_id, 0) + 1
        sources: list[LasSourceOption] = []
        for source in record.source_references:
            if source.source_kind != ManagedSourceKind.LAS or source.managed_source_uid is None:
                continue
            metadata = source.metadata if isinstance(source.metadata, dict) else {}
            asset = metadata.get("las_asset") if isinstance(metadata.get("las_asset"), dict) else {}
            if not asset:
                provenance = metadata.get("source_intake_provenance")
                if isinstance(provenance, dict) and isinstance(provenance.get("las_asset"), dict):
                    asset = provenance["las_asset"]
            filename = source.file_name or source.display_name or source.source_id
            sources.append(LasSourceOption(
                source_id=source.source_id,
                managed_source_uid=str(source.managed_source_uid),
                label=source.display_name or filename,
                original_filename=filename,
                curve_count=curve_counts.get(source.source_id, 0),
                asset_available=bool(metadata.get("las_asset_id") or asset.get("asset_id")),
                source_fingerprint=source.checksum or (str(asset.get("source_fingerprint")) if asset.get("source_fingerprint") else None),
            ))
        sources.sort(key=lambda item: (item.label.lower(), item.source_id))
        return LasSourceList(managed_well_uid=canonical_well_uid, sources=tuple(sources))

    def list_log_images(self, managed_well_uid: str) -> LogImageSourceList:
        canonical_well_uid = str(parse_uuid7(managed_well_uid))
        matches = [
            record for record in self.repository.list_records()
            if record.managed_well_uid and str(record.managed_well_uid) == canonical_well_uid
        ]
        if len(matches) != 1:
            raise ManagedWellNotFoundError(managed_well_uid)
        record = matches[0]
        sources: list[LogImageSourceOption] = []
        for source in record.source_references:
            if source.source_kind != ManagedSourceKind.RASTER_LOG or source.managed_source_uid is None:
                continue
            filename = source.file_name or source.display_name or source.source_id
            sources.append(LogImageSourceOption(
                source_id=source.source_id,
                managed_source_uid=str(source.managed_source_uid),
                label=source.display_name or filename,
                original_filename=filename,
                file_format=source.file_format,
                source_fingerprint=source.checksum,
            ))
        sources.sort(key=lambda item: (item.label.lower(), item.source_id))
        return LogImageSourceList(managed_well_uid=canonical_well_uid, sources=tuple(sources))

    def build_plan(self, managed_well_uid: str, source_id: str) -> LasReconstructionPlan:
        canonical_well_uid = str(parse_uuid7(managed_well_uid))
        matches = [
            record for record in self.repository.list_records()
            if record.managed_well_uid and str(record.managed_well_uid) == canonical_well_uid
        ]
        if len(matches) != 1:
            raise ManagedWellNotFoundError(managed_well_uid)
        record = matches[0]
        sources = [source for source in record.source_references if source.source_id == source_id]
        if len(sources) != 1:
            raise LasReconstructionError(f"LAS source is missing or ambiguous: {source_id}")
        source = sources[0]
        if source.source_kind != ManagedSourceKind.LAS:
            raise LasReconstructionError(f"Source is not LAS: {source_id}")
        if source.managed_source_uid is None:
            raise LasReconstructionError("LAS source has no canonical managed_source_uid")

        items = [
            item for group in record.product_groups for item in group.items
            if item.source_id == source_id
        ]
        items.sort(key=lambda item: (
            int((item.provenance or {}).get("source_curve_position") or 10**9),
            item.product_id,
        ))
        curves: list[LasReconstructionCurve] = []
        warnings: list[str] = []
        for fallback_index, item in enumerate(items):
            if item.managed_curve_uid is None or item.managed_product_uid is None or item.managed_source_uid is None:
                warnings.append(f"Skipped {item.product_id}: canonical curve/product/source identity is incomplete.")
                continue
            provenance = item.provenance if isinstance(item.provenance, dict) else {}
            index = int(provenance.get("source_curve_index") if provenance.get("source_curve_index") is not None else fallback_index)
            position = int(provenance.get("source_curve_position") or index + 1)
            curves.append(LasReconstructionCurve(
                managed_curve_uid=str(item.managed_curve_uid),
                managed_product_uid=str(item.managed_product_uid),
                managed_source_uid=str(item.managed_source_uid),
                product_id=item.product_id,
                mnemonic=item.curve_name,
                display_name=item.display_name,
                unit=item.curve_unit,
                curve_family=item.curve_family,
                source_curve_index=index,
                source_curve_position=position,
                review_required=item.review_required,
                selectable=item.selectable,
                loaded_to_wdv=item.wdv_state == ManagedWdvState.LOADED_TO_WDV,
            ))

        metadata = source.metadata if isinstance(source.metadata, dict) else {}
        asset = metadata.get("las_asset") if isinstance(metadata.get("las_asset"), dict) else {}
        if not asset:
            provenance = metadata.get("source_intake_provenance")
            if isinstance(provenance, dict) and isinstance(provenance.get("las_asset"), dict):
                asset = provenance["las_asset"]
        eligible = [curve for curve in curves if curve.selectable and not curve.review_required]
        return LasReconstructionPlan(
            managed_well_uid=canonical_well_uid,
            managed_well_id=record.managed_well_id,
            well_name=record.well_name,
            source_id=source_id,
            managed_source_uid=str(source.managed_source_uid),
            original_filename=source.file_name or source.display_name,
            asset_id=str(metadata.get("las_asset_id") or asset.get("asset_id") or "") or None,
            source_fingerprint=source.checksum or (str(asset.get("source_fingerprint")) if asset.get("source_fingerprint") else None),
            curve_count=len(curves),
            eligible_curve_count=len(eligible),
            review_curve_count=sum(1 for curve in curves if curve.review_required),
            curves=tuple(curves),
            warnings=tuple(warnings),
        )

    def load_complete_las(self, managed_well_uid: str, command: LoadCompleteLasCommand) -> LoadCompleteLasResponse:
        plan = self.build_plan(managed_well_uid, command.source_id)
        selected = [
            curve for curve in plan.curves
            if curve.selectable and (command.include_review_required or not curve.review_required)
        ]
        if not selected:
            raise LasReconstructionError("LAS source has no eligible managed curves")

        session = self.command_service.session_service.get_session(managed_well_uid)
        if command.placement == "inventory_only":
            if session.revision != command.expected_revision:
                raise CanonicalSessionRevisionConflict(
                    f"Expected canonical session revision {command.expected_revision}, found {session.revision}"
                )
            load_result = self.inventory_service.load_managed_well_to_wdv(
                plan.managed_well_id,
                product_ids=[curve.product_id for curve in selected],
            )
            return LoadCompleteLasResponse(
                plan=self.build_plan(managed_well_uid, command.source_id),
                loaded_product_ids=tuple(load_result.result.loaded_product_ids),
                session=session,
            )

        existing = {
            assignment.managed_curve_uid
            for track in session.tracks for assignment in track.assignments
        }
        to_add = [curve for curve in selected if not (command.skip_existing_assignments and curve.managed_curve_uid in existing)]
        skipped = [curve.managed_curve_uid for curve in selected if curve.managed_curve_uid not in {item.managed_curve_uid for item in to_add}]

        def mutate(current):
            tracks = list(current.tracks)
            for curve in to_add:
                track_uid = new_uuid7_str()
                assignment = self.command_service.assignment_policy_service.create_assignment(
                    managed_well_uid=managed_well_uid,
                    managed_curve_uid=curve.managed_curve_uid,
                    track_uid=track_uid,
                    stack_index=0,
                    assignment_source="complete_las_backend_reconstruction",
                )
                tracks.append(WdvCanonicalTrack(
                    track_uid=track_uid,
                    managed_well_uid=managed_well_uid,
                    track_key=f"las:{plan.source_id}:{curve.source_curve_position}",
                    track_number=len(tracks),
                    track_name=curve.display_name or curve.mnemonic,
                    track_type="curve",
                    renderer_type="curve",
                    track_role="las_source_curve",
                    width_px=command.track_width_px,
                    lattice=assignment.scale_type or "linear",
                    lattice_source="backend_display_policy",
                    scale_mode="per_curve",
                    assignments=(assignment,),
                ))
            return current.model_copy(update={
                "tracks": tuple(track.model_copy(update={"track_number": index}) for index, track in enumerate(tracks)),
                "selected_track_uid": tracks[-1].track_uid if to_add else current.selected_track_uid,
                "state_status": "active" if tracks else current.state_status,
            })

        payload = command.model_dump(mode="json", exclude={"expected_revision", "command_id"})
        session = self.command_service.transaction_service.execute(
            managed_well_uid,
            expected_revision=command.expected_revision,
            command_name="LoadCompleteLasCommand",
            command_payload=payload,
            command_id=command.command_id,
            mutation=mutate,
        )
        return LoadCompleteLasResponse(
            plan=self.build_plan(managed_well_uid, command.source_id),
            loaded_product_ids=(),
            added_managed_curve_uids=tuple(curve.managed_curve_uid for curve in to_add),
            skipped_existing_managed_curve_uids=tuple(skipped),
            session=session,
        )
