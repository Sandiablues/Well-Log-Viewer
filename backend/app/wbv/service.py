"""3D Wellbore Viewer backend service boundary.

WBV consumes Managed Well Inventory state and WDV load-session contracts. It does
not read raw DLIS/LIS files in the live viewer path and it must never fabricate a
3D well path when no backend-owned trajectory package exists.
"""

from __future__ import annotations

from typing import Any

from backend.app.inventory.models import ManagedProductGroupItem, ManagedWdvState, ManagedWmdpState, ManagedWellRecord
from backend.app.inventory.repository import ManagedWellInventoryRepository

from .trajectory_seed_registry import resolve_seed_trajectory_package

from .models import (
    WbvAvailableLayers,
    WbvCoordinateMode,
    WbvSessionContract,
    WbvSourceSession,
    WbvTrajectoryPackage,
    WbvViewerPackageContract,
    WbvViewerState,
    WbvWarning,
)


_VERTICAL_TRAJECTORY_CLASS = "vertical_trajectory_candidate"


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
        raw = record.metadata.get("wbv_trajectory_package") if isinstance(record.metadata, dict) else None
        if not isinstance(raw, dict):
            raw = record.metadata.get("trajectory_package") if isinstance(record.metadata, dict) else None
        if isinstance(raw, dict):
            return dict(raw)

        seed = resolve_seed_trajectory_package(record)
        return dict(seed) if isinstance(seed, dict) else {}
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
