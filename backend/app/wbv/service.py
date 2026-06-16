"""3D Wellbore Viewer backend service boundary.

WBV consumes Managed Well Inventory state and WDV load-session contracts. It does
not read raw DLIS/LIS files in the live viewer path and it must never fabricate a
3D well path when no backend-owned trajectory package exists.
"""

from __future__ import annotations

from typing import Any

from app.inventory.models import ManagedProductGroupItem, ManagedWdvState, ManagedWmdpState, ManagedWellRecord, utc_now_iso
from app.inventory.repository import ManagedWellInventoryRepository

from .trajectory_seed_registry import resolve_seed_trajectory_package

from .models import (
    WbvAvailableLayers,
    WbvCoordinateMode,
    WbvManagedTrajectoryRecord,
    WbvManagedTrajectoryStatus,
    WbvSessionContract,
    WbvSourceSession,
    WbvSetActiveTrajectoryResponse,
    WbvTrajectoryListContract,
    WbvTrajectoryPackage,
    WbvViewerPackageContract,
    WbvViewerState,
    WbvWarning,
)


_VERTICAL_TRAJECTORY_CLASS = "vertical_trajectory_candidate"
_TRAJECTORY_RECORDS_KEY = "wbv_trajectory_records"
_ACTIVE_TRAJECTORY_ID_KEY = "active_trajectory_id"


class WbvService:
    def __init__(self, repository: ManagedWellInventoryRepository | None = None) -> None:
        self.repository = repository or ManagedWellInventoryRepository()

    def get_session(self) -> WbvSessionContract:
        active_records = self._active_loaded_records()
        if not active_records:
            return WbvSessionContract(
                viewer_state=WbvViewerState.NOT_LOADED,
                warnings=[
                    WbvWarning(
                        code="no_loaded_wdv_well",
                        severity="info",
                        message="No managed well is currently loaded to WDV; WBV has no active well context.",
                    )
                ],
            )

        record = active_records[0]
        state, coordinate_mode, warnings = self._viewer_state_for_record(record)
        if len(active_records) > 1:
            warnings.insert(
                0,
                WbvWarning(
                    code="multiple_loaded_wdv_wells",
                    severity="warning",
                    message="Multiple managed wells are marked loaded to WDV. WBV selected the first backend record deterministically.",
                    target="inventory.wdv_state",
                ),
            )

        return WbvSessionContract(
            active_managed_well_id=record.managed_well_id,
            well_id=record.well_id,
            well_name=record.well_name,
            viewer_state=state,
            coordinate_mode=coordinate_mode,
            source_session=self._source_session(record),
            available_layers=self._available_layers(record),
            warnings=warnings,
        )

    def get_viewer_package(self, managed_well_id: str) -> WbvViewerPackageContract:
        record = self.repository.get_record(managed_well_id)
        state, coordinate_mode, warnings = self._viewer_state_for_record(record)
        trajectory = self._trajectory_package(record)
        layers = self._available_layers(record)
        return WbvViewerPackageContract(
            managed_well_id=record.managed_well_id,
            well_id=record.well_id,
            well_name=record.well_name,
            viewer_state=state,
            coordinate_mode=coordinate_mode,
            depth_unit=record.depth_unit or self._trajectory_depth_unit(record) or "ft",
            angle_unit=str(record.metadata.get("angle_unit") or self._raw_trajectory_metadata(record).get("angle_unit") or "deg") if isinstance(record.metadata, dict) else "deg",
            datum=self._datum(record),
            crs=self._crs(record),
            trajectory=trajectory,
            bounding_box=self._bounding_box(record),
            axes=self._dict_metadata(record, "wbv_axes"),
            available_layers=layers,
            markers=self._list_metadata(record, "wbv_markers"),
            intervals=self._list_metadata(record, "wbv_intervals"),
            available_attribute_tracks=self._available_attribute_tracks(record),
            warnings=warnings,
        )

    def list_trajectories(self, managed_well_id: str) -> WbvTrajectoryListContract:
        record = self.repository.get_record(managed_well_id)
        trajectories = self._trajectory_records(record)
        active = self._active_trajectory_record(record, trajectories)
        geometry_status = self._geometry_status(trajectories, active)
        warnings = self._trajectory_list_warnings(trajectories, active)
        return WbvTrajectoryListContract(
            managed_well_id=record.managed_well_id,
            well_id=record.well_id,
            well_name=record.well_name,
            active_trajectory_id=active.trajectory_id if active else None,
            geometry_status=geometry_status,
            wbv_ready=bool(active and active.wbv_eligible),
            trajectories=trajectories,
            warnings=warnings,
        )

    def set_active_trajectory(
        self,
        managed_well_id: str,
        trajectory_id: str,
        *,
        requested_by: str | None = None,
        note: str | None = None,
    ) -> WbvSetActiveTrajectoryResponse:
        record = self.repository.get_record(managed_well_id)
        trajectories = self._trajectory_records(record)
        selected = next((trajectory for trajectory in trajectories if trajectory.trajectory_id == trajectory_id), None)
        if selected is None:
            raise ValueError(f"Trajectory not found for managed well {managed_well_id}: {trajectory_id}")
        if not self._trajectory_selectable(selected):
            raise ValueError(
                "Only approved/synthetic-demo, WBV-eligible trajectories can be set active. "
                f"Trajectory {trajectory_id} has status={selected.status.value!r}, wbv_eligible={selected.wbv_eligible!r}."
            )

        persisted = self._metadata_trajectory_records(record)
        if not persisted:
            persisted = trajectories
        updated: list[WbvManagedTrajectoryRecord] = []
        for trajectory in persisted:
            next_trajectory = trajectory.model_copy(deep=True)
            next_trajectory.is_active = next_trajectory.trajectory_id == trajectory_id
            updated.append(next_trajectory)

        metadata = dict(record.metadata) if isinstance(record.metadata, dict) else {}
        metadata[_TRAJECTORY_RECORDS_KEY] = [trajectory.model_dump(mode="json") for trajectory in updated]
        metadata[_ACTIVE_TRAJECTORY_ID_KEY] = trajectory_id
        if selected.trajectory_package:
            metadata["wbv_trajectory_package"] = selected.trajectory_package
            metadata["wbv_coordinate_mode"] = selected.coordinate_mode.value
        metadata["wellbore_geometry_status"] = "active_trajectory_selected"
        metadata["wellbore_geometry_active_trajectory"] = {
            "trajectory_id": selected.trajectory_id,
            "trajectory_name": selected.trajectory_name,
            "trajectory_type": selected.trajectory_type,
            "status": selected.status.value,
            "is_synthetic": selected.is_synthetic,
            "selected_at": utc_now_iso(),
            "selected_by": requested_by,
            "note": note,
        }

        record.metadata = metadata
        record.updated_at = utc_now_iso()
        record.lifecycle_notes = list(record.lifecycle_notes or [])
        record.lifecycle_notes.append(
            f"Set active WBV trajectory to {selected.trajectory_id} ({selected.trajectory_name})."
        )
        self.repository.upsert_record(record)

        refreshed = self.repository.get_record(managed_well_id)
        next_trajectories = self._trajectory_records(refreshed)
        next_active = self._active_trajectory_record(refreshed, next_trajectories)
        geometry_status = self._geometry_status(next_trajectories, next_active)
        return WbvSetActiveTrajectoryResponse(
            managed_well_id=refreshed.managed_well_id,
            active_trajectory_id=selected.trajectory_id,
            active_trajectory_name=selected.trajectory_name,
            geometry_status=geometry_status,
            wbv_ready=bool(next_active and next_active.wbv_eligible),
            trajectories=next_trajectories,
        )

    def _active_loaded_records(self) -> list[ManagedWellRecord]:
        return [
            record
            for record in self.repository.list_records()
            if record.wmdp_available
            and record.wmdp_state != ManagedWmdpState.REMOVED_FROM_WMDP
            and record.wdv_state == ManagedWdvState.LOADED_TO_WDV
            and self._loaded_wdv_items(record)
        ]

    def _viewer_state_for_record(
        self,
        record: ManagedWellRecord,
    ) -> tuple[WbvViewerState, WbvCoordinateMode, list[WbvWarning]]:
        warnings: list[WbvWarning] = []
        if (
            not record.wmdp_available
            or record.wmdp_state == ManagedWmdpState.REMOVED_FROM_WMDP
            or record.wdv_state != ManagedWdvState.LOADED_TO_WDV
            or not self._loaded_wdv_items(record)
        ):
            return (
                WbvViewerState.NOT_LOADED,
                WbvCoordinateMode.UNAVAILABLE,
                [
                    WbvWarning(
                        code="managed_well_not_loaded_to_wdv",
                        severity="info",
                        message="This managed well is not currently loaded to WDV; WBV is unavailable for it.",
                        target="wdv_state",
                    )
                ],
            )

        if not isinstance(record.metadata.get("wdv_load_session_contract"), dict):
            warnings.append(
                WbvWarning(
                    code="missing_wdv_load_session_contract",
                    severity="warning",
                    message="Managed well is loaded to WDV but has no backend-owned WDV load-session contract.",
                    target="metadata.wdv_load_session_contract",
                )
            )

        trajectory = self._trajectory_package(record)
        if not trajectory.render_points:
            warnings.append(
                WbvWarning(
                    code="missing_deviation_survey",
                    severity="warning",
                    message="No registered deviation survey or backend-owned trajectory package is available for WBV.",
                    target="metadata.wbv_trajectory_package",
                )
            )
            return WbvViewerState.MISSING_SURVEY, WbvCoordinateMode.UNAVAILABLE, warnings

        warnings.extend(self._trajectory_warnings(record))

        coordinate_mode = self._coordinate_mode(record)
        if coordinate_mode == WbvCoordinateMode.UNAVAILABLE:
            return WbvViewerState.NEEDS_REVIEW, coordinate_mode, warnings

        if trajectory.trajectory_class == _VERTICAL_TRAJECTORY_CLASS or trajectory.viewer_state == WbvViewerState.AVAILABLE_VERTICAL.value:
            warnings.append(
                WbvWarning(
                    code="vertical_trajectory_candidate",
                    severity="info",
                    message="A backend-owned trajectory package is available, but this source represents a vertical wellbore section.",
                    target="metadata.wbv_trajectory_package.trajectory_class",
                )
            )
            return WbvViewerState.AVAILABLE_VERTICAL, coordinate_mode, warnings

        if coordinate_mode == WbvCoordinateMode.RELATIVE:
            return WbvViewerState.RELATIVE_ONLY, coordinate_mode, warnings
        return WbvViewerState.AVAILABLE, coordinate_mode, warnings

    def _source_session(self, record: ManagedWellRecord) -> WbvSourceSession | None:
        contract = record.metadata.get("wdv_load_session_contract")
        if not isinstance(contract, dict):
            session = record.metadata.get("wdv_load_session")
            if not isinstance(session, dict):
                return None
            return WbvSourceSession(
                active_viewer_package_id=str(session.get("session_id") or "") or None,
                loaded_product_count=int(session.get("loaded_product_count") or 0),
                source_product_ids=[str(pid) for pid in session.get("source_product_ids", []) if str(pid)],
            )

        return WbvSourceSession(
            active_viewer_package_id=str(contract.get("representation_id") or contract.get("wdv_session_id") or "") or None,
            loaded_product_count=int(contract.get("loaded_product_count") or 0),
            source_product_ids=[str(pid) for pid in contract.get("source_product_ids", []) if str(pid)],
            depth_domain=contract.get("depth_domain") if isinstance(contract.get("depth_domain"), dict) else None,
        )

    def _available_layers(self, record: ManagedWellRecord) -> WbvAvailableLayers:
        trajectory = self._trajectory_package(record)
        loaded_items = self._loaded_wdv_items(record)
        return WbvAvailableLayers(
            trajectory=bool(trajectory.render_points),
            survey_stations=bool(trajectory.stations),
            depth_labels=bool(trajectory.render_points),
            formation_tops=bool(self._list_metadata(record, "formation_tops") or self._list_metadata(record, "tops") or self._list_metadata(record, "wbv_markers")),
            lithology=bool(self._list_metadata(record, "lithology_intervals")),
            casing=bool(self._list_metadata(record, "casing") or self._list_metadata(record, "hole_sections")),
            completions=bool(self._list_metadata(record, "completions") or self._list_metadata(record, "perforations")),
            loaded_curves=bool(loaded_items),
            curve_attributes=bool(loaded_items),
        )

    def _trajectory_package(self, record: ManagedWellRecord) -> WbvTrajectoryPackage:
        raw = self._raw_trajectory_metadata(record)
        if not raw:
            return WbvTrajectoryPackage()

        stations = raw.get("stations", [])
        render_points = raw.get("render_points", [])
        warnings = raw.get("warnings", [])
        return WbvTrajectoryPackage(
            method=str(raw.get("method") or "") or None,
            source=str(raw.get("source") or raw.get("source_type") or "") or None,
            trajectory_class=str(raw.get("trajectory_class") or "") or None,
            viewer_state=str(raw.get("viewer_state") or "") or None,
            station_count=self._optional_int(raw.get("station_count")),
            source_station_count=self._optional_int(raw.get("source_station_count")),
            fixture_sampling=dict(raw.get("fixture_sampling") or {}) if isinstance(raw.get("fixture_sampling"), dict) else {},
            stations=stations if isinstance(stations, list) else [],
            render_points=render_points if isinstance(render_points, list) else [],
            warnings=[item for item in warnings if isinstance(item, dict)] if isinstance(warnings, list) else [],
        )

    def _raw_trajectory_metadata(self, record: ManagedWellRecord) -> dict[str, Any]:
        trajectories = self._metadata_trajectory_records(record)
        active = self._active_trajectory_record(record, trajectories)
        if active is not None and active.trajectory_package:
            return dict(active.trajectory_package)

        legacy = self._legacy_trajectory_metadata(record)
        if legacy:
            return legacy

        seed = resolve_seed_trajectory_package(record)
        return dict(seed) if isinstance(seed, dict) else {}

    def _legacy_trajectory_metadata(self, record: ManagedWellRecord) -> dict[str, Any]:
        if not isinstance(record.metadata, dict):
            return {}
        raw = record.metadata.get("wbv_trajectory_package")
        if not isinstance(raw, dict):
            raw = record.metadata.get("trajectory_package")
        return dict(raw) if isinstance(raw, dict) else {}

    def _metadata_trajectory_records(self, record: ManagedWellRecord) -> list[WbvManagedTrajectoryRecord]:
        if not isinstance(record.metadata, dict):
            return []
        raw_records = record.metadata.get(_TRAJECTORY_RECORDS_KEY)
        if not isinstance(raw_records, list):
            return []
        records: list[WbvManagedTrajectoryRecord] = []
        for index, raw in enumerate(raw_records):
            if not isinstance(raw, dict):
                continue
            try:
                records.append(WbvManagedTrajectoryRecord(**raw))
            except Exception as exc:
                records.append(
                    WbvManagedTrajectoryRecord(
                        trajectory_id=f"invalid-trajectory-record:{index}",
                        trajectory_name=f"Invalid trajectory record {index + 1}",
                        status=WbvManagedTrajectoryStatus.REVIEW_REQUIRED,
                        wbv_eligible=False,
                        qa_flags=["invalid_trajectory_record_contract"],
                        warnings=[{"code": "invalid_trajectory_record_contract", "severity": "error", "message": str(exc)}],
                    )
                )
        active_id = str(record.metadata.get(_ACTIVE_TRAJECTORY_ID_KEY) or "")
        if active_id:
            records = [record.model_copy(update={"is_active": record.is_active or record.trajectory_id == active_id}) for record in records]
        return records

    def _trajectory_records(self, record: ManagedWellRecord) -> list[WbvManagedTrajectoryRecord]:
        records = self._metadata_trajectory_records(record)
        if records:
            return records

        legacy = self._legacy_trajectory_metadata(record)
        if legacy:
            return [self._trajectory_record_from_package("legacy-active-trajectory", "Legacy active trajectory", legacy, active=True)]

        seed = resolve_seed_trajectory_package(record)
        if isinstance(seed, dict) and seed:
            return [self._trajectory_record_from_package("runtime-seed-trajectory", "Runtime seed trajectory", seed, active=True)]
        return []

    def _trajectory_record_from_package(
        self,
        trajectory_id: str,
        trajectory_name: str,
        package: dict[str, Any],
        *,
        active: bool,
    ) -> WbvManagedTrajectoryRecord:
        render_points = package.get("render_points") if isinstance(package.get("render_points"), list) else []
        stations = package.get("stations") if isinstance(package.get("stations"), list) else []
        bounding_box = package.get("bounding_box") if isinstance(package.get("bounding_box"), dict) else {}
        coordinate_mode = str(package.get("coordinate_mode") or ("relative" if render_points else "unavailable"))
        if coordinate_mode not in {mode.value for mode in WbvCoordinateMode}:
            coordinate_mode = WbvCoordinateMode.RELATIVE.value if render_points else WbvCoordinateMode.UNAVAILABLE.value
        md_min, md_max = self._md_range_from_package(package, render_points, bounding_box)
        tvd_min, tvd_max = self._tvd_range_from_package(package, render_points, bounding_box)
        return WbvManagedTrajectoryRecord(
            trajectory_id=trajectory_id,
            trajectory_name=trajectory_name,
            trajectory_type=str(package.get("source") or package.get("source_type") or "deviation_survey"),
            status=WbvManagedTrajectoryStatus.APPROVED if render_points else WbvManagedTrajectoryStatus.REVIEW_REQUIRED,
            wbv_eligible=bool(render_points),
            is_active=active,
            is_canonical=True,
            is_synthetic=False,
            source_label=str(package.get("source") or package.get("source_type") or "trajectory package"),
            station_count=len(render_points) or len(stations) or self._optional_int(package.get("station_count")),
            md_min=md_min,
            md_max=md_max,
            tvd_min=tvd_min,
            tvd_max=tvd_max,
            geometry_class=str(package.get("trajectory_class") or "") or None,
            coordinate_mode=WbvCoordinateMode(coordinate_mode),
            trajectory_package=package,
            warnings=[item for item in package.get("warnings", []) if isinstance(item, dict)] if isinstance(package.get("warnings"), list) else [],
        )

    def _active_trajectory_record(
        self,
        record: ManagedWellRecord,
        trajectories: list[WbvManagedTrajectoryRecord],
    ) -> WbvManagedTrajectoryRecord | None:
        if not trajectories:
            return None
        active_id = str(record.metadata.get(_ACTIVE_TRAJECTORY_ID_KEY) or "") if isinstance(record.metadata, dict) else ""
        if active_id:
            explicit = next((trajectory for trajectory in trajectories if trajectory.trajectory_id == active_id), None)
            if explicit is not None:
                return explicit
        explicit_active = next((trajectory for trajectory in trajectories if trajectory.is_active), None)
        if explicit_active is not None:
            return explicit_active
        selectable = [trajectory for trajectory in trajectories if self._trajectory_selectable(trajectory)]
        if len(selectable) == 1:
            return selectable[0]
        canonical = [trajectory for trajectory in selectable if trajectory.is_canonical]
        if len(canonical) == 1:
            return canonical[0]
        return None

    @staticmethod
    def _trajectory_selectable(trajectory: WbvManagedTrajectoryRecord) -> bool:
        return bool(trajectory.wbv_eligible) and trajectory.status in {
            WbvManagedTrajectoryStatus.APPROVED,
            WbvManagedTrajectoryStatus.SYNTHETIC_DEMO,
        }

    def _geometry_status(
        self,
        trajectories: list[WbvManagedTrajectoryRecord],
        active: WbvManagedTrajectoryRecord | None,
    ) -> str:
        if active is not None and active.wbv_eligible:
            return "active_trajectory_selected"
        if not trajectories:
            return "missing"
        if any(trajectory.status == WbvManagedTrajectoryStatus.REVIEW_REQUIRED for trajectory in trajectories):
            return "review_required"
        selectable = [trajectory for trajectory in trajectories if self._trajectory_selectable(trajectory)]
        if len(selectable) > 1:
            return "multiple_approved_select_active"
        if selectable:
            return "approved_available"
        return "not_wbv_eligible"

    def _trajectory_list_warnings(
        self,
        trajectories: list[WbvManagedTrajectoryRecord],
        active: WbvManagedTrajectoryRecord | None,
    ) -> list[WbvWarning]:
        if not trajectories:
            return [
                WbvWarning(
                    code="no_managed_wellbore_geometry",
                    severity="info",
                    message="No managed wellbore geometry records are registered for this well.",
                    target="metadata.wbv_trajectory_records",
                )
            ]
        selectable = [trajectory for trajectory in trajectories if self._trajectory_selectable(trajectory)]
        if active is None and len(selectable) > 1:
            return [
                WbvWarning(
                    code="multiple_approved_trajectories_require_selection",
                    severity="warning",
                    message="Multiple approved WBV-eligible trajectories exist; select one active trajectory in MDP.",
                    target="metadata.active_trajectory_id",
                )
            ]
        return []

    @staticmethod
    def _md_range_from_package(
        package: dict[str, Any],
        render_points: list[Any],
        bounding_box: dict[str, Any],
    ) -> tuple[float | None, float | None]:
        md_box = bounding_box.get("md") if isinstance(bounding_box.get("md"), dict) else None
        if md_box:
            return WbvService._optional_float(md_box.get("min")), WbvService._optional_float(md_box.get("max"))
        values = [WbvService._optional_float(point.get("md")) for point in render_points if isinstance(point, dict)]
        values = [value for value in values if value is not None]
        return (min(values), max(values)) if values else (None, None)

    @staticmethod
    def _tvd_range_from_package(
        package: dict[str, Any],
        render_points: list[Any],
        bounding_box: dict[str, Any],
    ) -> tuple[float | None, float | None]:
        tvd_box = bounding_box.get("tvd") if isinstance(bounding_box.get("tvd"), dict) else None
        if tvd_box:
            return WbvService._optional_float(tvd_box.get("min")), WbvService._optional_float(tvd_box.get("max"))
        values = [WbvService._optional_float(point.get("tvd")) for point in render_points if isinstance(point, dict)]
        values = [value for value in values if value is not None]
        return (min(values), max(values)) if values else (None, None)

    def _trajectory_warnings(self, record: ManagedWellRecord) -> list[WbvWarning]:
        raw = self._raw_trajectory_metadata(record)
        source_warnings = raw.get("warnings", [])
        warnings: list[WbvWarning] = []
        if not isinstance(source_warnings, list):
            return warnings

        for index, item in enumerate(source_warnings):
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or f"trajectory_warning_{index}")
            severity = str(item.get("severity") or "warning").lower()
            if severity not in {"info", "warning", "error"}:
                severity = "warning"
            message = str(item.get("message") or code)
            target = item.get("target")
            warnings.append(
                WbvWarning(
                    code=code,
                    severity=severity,  # type: ignore[arg-type]
                    message=message,
                    target=str(target) if target is not None else "metadata.wbv_trajectory_package.warnings",
                )
            )
        return warnings

    def _coordinate_mode(self, record: ManagedWellRecord) -> WbvCoordinateMode:
        raw = str(record.metadata.get("wbv_coordinate_mode") or "").strip().lower()
        if raw in {mode.value for mode in WbvCoordinateMode}:
            return WbvCoordinateMode(raw)
        raw_trajectory = self._raw_trajectory_metadata(record)
        trajectory_mode = str(raw_trajectory.get("coordinate_mode") or "").strip().lower()
        if trajectory_mode in {mode.value for mode in WbvCoordinateMode}:
            return WbvCoordinateMode(trajectory_mode)
        trajectory = self._trajectory_package(record)
        if trajectory.render_points:
            return WbvCoordinateMode.RELATIVE
        return WbvCoordinateMode.UNAVAILABLE

    def _trajectory_depth_unit(self, record: ManagedWellRecord) -> str | None:
        raw = self._raw_trajectory_metadata(record)
        unit = raw.get("depth_unit")
        return str(unit) if unit else None

    def _bounding_box(self, record: ManagedWellRecord) -> dict[str, Any]:
        explicit = self._dict_metadata(record, "wbv_bounding_box")
        if explicit:
            return explicit
        raw = self._raw_trajectory_metadata(record)
        bbox = raw.get("bounding_box")
        return dict(bbox) if isinstance(bbox, dict) else {}

    def _loaded_wdv_items(self, record: ManagedWellRecord) -> list[ManagedProductGroupItem]:
        return [
            item
            for group in record.product_groups
            for item in group.items
            if item.wdv_state == ManagedWdvState.LOADED_TO_WDV and self._is_wdv_loadable_product(item)
        ]

    @staticmethod
    def _is_wdv_loadable_product(item: ManagedProductGroupItem) -> bool:
        source_kind = str(item.source_kind or "").lower()
        category = str(item.product_category or "").lower()
        curve_name = str(item.curve_name or "").strip()
        return bool(curve_name) and source_kind not in {"document"} and category not in {"supporting_documents"}

    @staticmethod
    def _list_metadata(record: ManagedWellRecord, key: str) -> list[dict[str, Any]]:
        value = record.metadata.get(key) if isinstance(record.metadata, dict) else None
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        return []

    @staticmethod
    def _dict_metadata(record: ManagedWellRecord, key: str) -> dict[str, Any]:
        value = record.metadata.get(key) if isinstance(record.metadata, dict) else None
        return dict(value) if isinstance(value, dict) else {}

    def _available_attribute_tracks(self, record: ManagedWellRecord) -> list[dict[str, Any]]:
        tracks: list[dict[str, Any]] = []
        for item in self._loaded_wdv_items(record):
            tracks.append(
                {
                    "product_id": item.product_id,
                    "curve_name": item.curve_name,
                    "display_name": item.display_name,
                    "curve_family": item.curve_family,
                    "unit": item.curve_unit,
                    "source_kind": item.source_kind,
                }
            )
        return tracks

    @staticmethod
    def _datum(record: ManagedWellRecord) -> dict[str, Any]:
        datum = record.metadata.get("datum") if isinstance(record.metadata, dict) else None
        return dict(datum) if isinstance(datum, dict) else {}

    @staticmethod
    def _crs(record: ManagedWellRecord) -> dict[str, Any]:
        crs = record.metadata.get("crs") if isinstance(record.metadata, dict) else None
        if isinstance(crs, dict):
            return dict(crs)
        return {"epsg": None, "status": "not_available"}

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        try:
            if value is None:
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None
