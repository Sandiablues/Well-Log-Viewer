"""3D Wellbore Viewer backend service boundary.

WBV consumes Managed Well Inventory state and WDV load-session contracts. It does
not read raw DLIS/LIS files in the live viewer path and it must never fabricate a
3D well path when no backend-owned trajectory package exists.
"""

from __future__ import annotations

from typing import Any
import math

from app.inventory.models import ManagedProductGroupItem, ManagedWdvState, ManagedWmdpState, ManagedWellRecord, utc_now_iso
from app.inventory.repository import ManagedWellInventoryRepository
from app.inventory.wdv_workspace import WdvWorkspaceService
from app.inventory.curve_sample_service import CurveSampleService
from app.curve_display.contract_service import (
    BackendCurveDisplayContractService,
    BackendCurveDisplayIntent,
)

from .trajectory_seed_registry import resolve_seed_trajectory_package

from .models import (
    WbvAvailableLayers,
    WbvCoordinateMode,
    WbvDisplayLayerFile,
    WbvDisplayLayerFilesContract,
    WbvDisplayLayerConfiguration,
    WbvDisplayLayerConfigurationContract,
    WbvCurveOverlayCurve,
    WbvCurveOverlayNormalizationContract,
    WbvCurveOverlayNormalizationItem,
    WbvCurveOverlayProduct,
    WbvCurveOverlayProductsContract,
    WbvCurveOverlayRenderContract,
    WbvCurveOverlayRenderCurve,
    WbvCurveOverlayRenderSample,
    WbvDisplaySettingsContract,
    WbvManagedTrajectoryRecord,
    WbvManagedTrajectoryStatus,
    WbvSessionContract,
    WbvSurveyQaqcContract,
    WbvSurveyQaqcFinding,
    WbvSurveyQaqcSummary,
    WbvSourceSession,
    WbvSetActiveTrajectoryResponse,
    WbvTrajectoryListContract,
    WbvTrackConfiguration,
    WbvTrajectoryPackage,
    WbvViewerPackageContract,
    WbvViewerState,
    WbvWarning,
)


_VERTICAL_TRAJECTORY_CLASS = "vertical_trajectory_candidate"
_TRAJECTORY_RECORDS_KEY = "wbv_trajectory_records"
_ACTIVE_TRAJECTORY_ID_KEY = "active_trajectory_id"
_ACTIVE_TRAJECTORY_UID_KEY = "active_trajectory_uid"
_WBV_DEPTH_UNIT_KEY = "wbv_depth_unit"
_WBV_DISPLAY_LAYER_CONFIG_KEY = "wbv_display_layer_configuration_v1"


class WbvService:
    def __init__(self, repository: ManagedWellInventoryRepository | None = None) -> None:
        self.repository = repository or ManagedWellInventoryRepository()
        self.curve_sample_service = CurveSampleService(self.repository)
        self.curve_display_contract_service = BackendCurveDisplayContractService()
        self._workspace_service: WdvWorkspaceService | None = None

    def _workspace(self) -> WdvWorkspaceService:
        """Resolve the workspace boundary only for WBV session commands.

        Curve-overlay and rendering services are also exercised with narrow test
        repositories that intentionally do not expose filesystem storage. Those
        paths must not construct workspace persistence they do not use.
        """
        if self._workspace_service is None:
            self._workspace_service = WdvWorkspaceService(self.repository)
        return self._workspace_service

    def get_session(self) -> WbvSessionContract:
        """Return the WBV session for the backend-owned active WDV workspace well.

        WBV never selects a well independently and never falls back to repository
        ordering. The WDV workspace is the single authority for active managed-well
        identity across WDV and WBV.
        """
        workspace = self._workspace().get_workspace()
        managed_well_id = workspace.active_managed_well_id
        if not managed_well_id:
            return WbvSessionContract(
                viewer_state=WbvViewerState.NOT_LOADED,
                warnings=[
                    WbvWarning(
                        code="no_active_wdv_workspace_well",
                        severity="info",
                        message="The backend-owned WDV workspace has no active managed well; WBV has no active well context.",
                        target="wdv_workspace.active_managed_well_id",
                    )
                ],
            )

        record = self.repository.get_record(managed_well_id)
        state, coordinate_mode, warnings = self._viewer_state_for_record(record)
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

    def set_active_well(self, managed_well_id: str) -> WbvSessionContract:
        """Explicitly command the backend workspace to change WBV/WDV active well."""
        workspace = self._workspace().set_active_well(managed_well_id)
        if workspace.active_managed_well_id != managed_well_id:
            raise ValueError("Backend WDV workspace did not confirm the requested active managed well.")
        return self.get_session()

    def get_viewer_package(self, managed_well_id: str) -> WbvViewerPackageContract:
        record = self.repository.get_record(managed_well_id)
        state, coordinate_mode, warnings = self._viewer_state_for_record(record)
        source_unit = self._source_depth_unit(record)
        display_unit = self._display_depth_unit(record, source_unit)
        trajectory = self._convert_trajectory_package(
            self._trajectory_package(record), source_unit, display_unit
        )
        layers = self._available_layers(record)
        return WbvViewerPackageContract(
            managed_well_id=record.managed_well_id,
            well_id=record.well_id,
            well_name=record.well_name,
            viewer_state=state,
            coordinate_mode=coordinate_mode,
            depth_unit=display_unit,
            angle_unit=str(record.metadata.get("angle_unit") or self._raw_trajectory_metadata(record).get("angle_unit") or "deg") if isinstance(record.metadata, dict) else "deg",
            datum=self._datum(record),
            crs=self._crs(record),
            trajectory=trajectory,
            survey_qaqc=self._convert_survey_qaqc(
                self._survey_qaqc_summary(self._trajectory_package(record)),
                source_unit, display_unit,
            ),
            bounding_box=self._convert_bounding_box(
                self._bounding_box(record), source_unit, display_unit
            ),
            axes=self._dict_metadata(record, "wbv_axes"),
            available_layers=layers,
            markers=self._list_metadata(record, "wbv_markers"),
            intervals=self._list_metadata(record, "wbv_intervals"),
            available_attribute_tracks=self._available_attribute_tracks(record),
            warnings=warnings,
        )

    def set_display_depth_unit(
        self, managed_well_id: str, depth_unit: str
    ) -> WbvDisplaySettingsContract:
        normalized = self._normalize_depth_unit(depth_unit)
        if normalized not in {"ft", "m"}:
            raise ValueError("WBV depth_unit must be 'ft' or 'm'.")
        record = self.repository.get_record(managed_well_id)
        metadata = dict(record.metadata) if isinstance(record.metadata, dict) else {}
        metadata[_WBV_DEPTH_UNIT_KEY] = normalized
        record.metadata = metadata
        record.updated_at = utc_now_iso()
        self.repository.upsert_record(record)
        return WbvDisplaySettingsContract(
            managed_well_id=record.managed_well_id, depth_unit=normalized
        )

    def get_display_layer_files(self, managed_well_id: str) -> WbvDisplayLayerFilesContract:
        record = self.repository.get_record(managed_well_id)
        layer_keys = (
            "formation_tops",
            "lithology_intervals",
            "casing_hole_sections",
            "completions",
            "curve_overlays",
            "borehole_imagery",
        )
        grouped: dict[str, list[WbvDisplayLayerFile]] = {key: [] for key in layer_keys}
        for group in record.product_groups:
            for item in group.items:
                layer_type = str(item.display_layer_type or "").strip()
                if layer_type not in grouped:
                    continue
                if item.wmdp_state != ManagedWmdpState.STAGED_IN_WMDP:
                    continue
                depth_reference = str(item.depth_reference or "").strip()
                depth_units = str(item.depth_units or "").strip()
                if not depth_reference or not depth_units:
                    continue
                grouped[layer_type].append(
                    WbvDisplayLayerFile(
                        product_id=item.product_id,
                        display_name=item.display_name,
                        display_layer_type=layer_type,
                        depth_reference=depth_reference,
                        depth_units=depth_units,
                        depth_start=item.depth_start,
                        depth_end=item.depth_end,
                    )
                )
        for values in grouped.values():
            values.sort(key=lambda value: (value.display_name.casefold(), value.product_id))
        return WbvDisplayLayerFilesContract(
            managed_well_id=record.managed_well_id,
            layers=grouped,
        )

    def get_curve_overlay_products(self, managed_well_id: str) -> WbvCurveOverlayProductsContract:
        record = self.repository.get_record(managed_well_id)
        source_names = {source.source_id: source.display_name for source in record.source_references}
        managed_items = [
            item
            for group in record.product_groups
            for item in group.items
            if item.wmdp_state == ManagedWmdpState.STAGED_IN_WMDP
        ]

        excluded_product_keys = {
            self._curve_overlay_product_key(item)
            for item in managed_items
            if self._is_trajectory_or_geometry_item(item)
        }

        grouped: dict[str, list[ManagedProductGroupItem]] = {}
        labels: dict[str, str] = {}
        for item in managed_items:
            product_key = self._curve_overlay_product_key(item)
            if product_key in excluded_product_keys:
                continue
            if not item.selectable or not (item.curve_name or item.display_name):
                continue
            grouped.setdefault(product_key, []).append(item)
            labels[product_key] = source_names.get(product_key) or item.source_id or "Managed curve product"

        products: list[WbvCurveOverlayProduct] = []
        for product_key, items in grouped.items():
            curves = [
                WbvCurveOverlayCurve(
                    curve_product_id=item.product_id,
                    managed_curve_uid=item.managed_curve_uid,
                    display_name=item.display_name,
                    mnemonic=item.curve_name or item.display_name,
                    description=item.curve_description,
                    unit=item.curve_unit,
                    curve_family=item.curve_family,
                    depth_start=item.depth_start,
                    depth_end=item.depth_end,
                    depth_units=item.depth_units,
                    run_interval=item.run_interval if item.run_interval and item.run_interval != "—" else None,
                    run_number=item.run_number if item.run_number and item.run_number != "—" else None,
                    run_date=item.run_date if item.run_date and item.run_date != "—" else None,
                    curve_type=item.curve_type or None,
                    classification_source=item.classification_source or None,
                    classification_confidence=item.classification_confidence or None,
                    review_required=bool(item.review_required),
                    source_display_name=source_names.get(product_key) or "Managed curve product",
                )
                for item in sorted(items, key=lambda value: ((value.curve_name or value.display_name).casefold(), value.product_id))
            ]
            products.append(WbvCurveOverlayProduct(
                curve_product_id=product_key,
                display_name=labels[product_key],
                curve_count=len(curves),
                curves=curves,
            ))
        products.sort(key=lambda value: (value.display_name.casefold(), value.curve_product_id))
        return WbvCurveOverlayProductsContract(managed_well_id=record.managed_well_id, products=products)

    @staticmethod
    def _curve_overlay_product_key(item: ManagedProductGroupItem) -> str:
        return str(
            item.source_id
            or item.source_intake_candidate_id
            or item.viewer_package_id
            or "managed-curves"
        ).strip()

    @staticmethod
    def _is_trajectory_or_geometry_item(item: ManagedProductGroupItem) -> bool:
        excluded_types = {
            "trajectory",
            "deviation_survey",
            "directional_survey",
            "wellbore_geometry",
            "wellbore_geometry_candidate",
        }
        classifications = {
            str(item.display_layer_type or "").strip().lower(),
            str(item.source_kind or "").strip().lower(),
            str(item.product_category or "").strip().lower(),
            str(item.curve_type or "").strip().lower(),
        }
        return bool(classifications & excluded_types)

    def normalize_curve_overlays(
        self, managed_well_id: str, curve_product_ids: list[str]
    ) -> WbvCurveOverlayNormalizationContract:
        record = self.repository.get_record(managed_well_id)
        config = self.get_display_layer_configuration(managed_well_id)
        curve_layer = next(
            (layer for layer in config.layers if layer.layer_type == "curve_overlays"),
            None,
        )
        setting_index = {
            setting.curve_product_id: setting
            for setting in (curve_layer.curve_settings if curve_layer is not None else [])
        }
        item_index = {
            item.product_id: item
            for group in record.product_groups
            for item in group.items
            if item.wmdp_state == ManagedWmdpState.STAGED_IN_WMDP
        }
        results: list[WbvCurveOverlayNormalizationItem] = []
        for curve_product_id in dict.fromkeys(curve_product_ids):
            item = item_index.get(curve_product_id)
            if item is None:
                raise ValueError(f"Curve product is not available in WMD for this well: {curve_product_id}")
            samples = self.curve_sample_service.get_curve_samples(
                managed_well_id=managed_well_id,
                product_id=curve_product_id,
                max_samples=100000,
            )
            setting = setting_index.get(curve_product_id)
            scale = setting.scale if setting is not None else None
            intent = self._curve_display_intent(scale)
            contract = self.curve_display_contract_service.resolve(
                record=record,
                item=item,
                statistics={
                    "observed_min": samples.get("value_min"),
                    "observed_max": samples.get("value_max"),
                    "robust_observed_min": samples.get("robust_value_min"),
                    "robust_observed_max": samples.get("robust_value_max"),
                    "observed_p05": samples.get("value_p05"),
                    "observed_p95": samples.get("value_p95"),
                    "rejected_sample_count": samples.get("rejected_sample_count", 0),
                },
                intent=intent,
            )
            low, high = contract.minimum, contract.maximum
            values = [
                float(pair[1])
                for pair in samples.get("samples", [])
                if isinstance(pair, (list, tuple)) and len(pair) >= 2
            ]
            below = sum(1 for value in values if value < low)
            above = sum(1 for value in values if value > high)
            count = len(values)
            display_min, display_max = (
                (high, low) if contract.direction == "reversed" else (low, high)
            )
            results.append(WbvCurveOverlayNormalizationItem(
                curve_product_id=curve_product_id,
                managed_curve_uid=item.managed_curve_uid,
                display_name=item.display_name,
                mnemonic=item.curve_name or item.display_name,
                unit=samples.get("value_unit") or item.curve_unit,
                display_min=display_min,
                display_max=display_max,
                scale_type=contract.scale_type,
                display_direction=contract.direction,
                range_source=contract.range_source,
                policy_revision=contract.policy_revision,
                provenance=contract.provenance,
                clamp=contract.clamp,
                requires_review=contract.requires_review,
                sample_count=int(samples.get("sample_count") or count),
                below_range_count=below,
                above_range_count=above,
                clipped_fraction=((below + above) / count) if count else 0.0,
            ))
        return WbvCurveOverlayNormalizationContract(
            managed_well_id=record.managed_well_id,
            curves=results,
        )

    @staticmethod
    def _curve_display_intent(scale: Any | None) -> BackendCurveDisplayIntent | None:
        if scale is None:
            return None
        source = str(scale.source or "backend_default")
        range_mode = source if source in {"robust_p5_p95", "manual"} else "governed"
        direction_override = (
            scale.direction if scale.direction_source == "manual" else None
        )
        return BackendCurveDisplayIntent(
            range_mode=range_mode,
            minimum=scale.minimum,
            maximum=scale.maximum,
            scale_type=scale.scale_type if range_mode == "manual" else None,
            direction_override=direction_override,
            clamp=bool(scale.clamp_outliers),
            intent_source="wbv_backend_display_layer_configuration",
        )

    def get_curve_overlay_render_package(self, managed_well_id: str) -> WbvCurveOverlayRenderContract:
        record = self.repository.get_record(managed_well_id)
        config = self.get_display_layer_configuration(managed_well_id)
        layer = next((item for item in config.layers if item.layer_type == "curve_overlays"), None)
        if layer is None or not layer.visible or not layer.selected_item_ids:
            return WbvCurveOverlayRenderContract(
                managed_well_id=record.managed_well_id,
                track_spacing=config.track_spacing,
                tracks=config.tracks,
            )

        item_index = {
            item.product_id: item
            for group in record.product_groups
            for item in group.items
            if item.wmdp_state == ManagedWmdpState.STAGED_IN_WMDP
        }
        setting_index = {item.curve_product_id: item for item in layer.curve_settings}
        normalized_index = {
            item.curve_product_id: item
            for item in self.normalize_curve_overlays(managed_well_id, layer.selected_item_ids).curves
        }
        curves: list[WbvCurveOverlayRenderCurve] = []
        for curve_id in layer.selected_item_ids:
            managed_item = item_index.get(curve_id)
            normalization = normalized_index.get(curve_id)
            if managed_item is None or normalization is None:
                continue
            setting = setting_index.get(curve_id)
            appearance = setting.appearance if setting is not None else None
            low = min(normalization.display_min, normalization.display_max)
            high = max(normalization.display_min, normalization.display_max)
            reverse = normalization.display_direction == "reversed"
            logarithmic = normalization.scale_type == "logarithmic"
            raw = self.curve_sample_service.get_curve_samples(
                managed_well_id=managed_well_id, product_id=curve_id, max_samples=12000
            )
            render_samples: list[WbvCurveOverlayRenderSample] = []
            for pair in raw.get("samples", []):
                if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                    continue
                md = self._finite_number(pair[0]); value = self._finite_number(pair[1])
                if md is None or value is None:
                    continue
                if logarithmic:
                    if value <= 0 or low <= 0 or high <= 0:
                        continue
                    ratio = (math.log10(value) - math.log10(low)) / (math.log10(high) - math.log10(low))
                else:
                    ratio = (value - low) / (high - low)
                ratio = max(0.0, min(1.0, ratio))
                if reverse:
                    ratio = 1.0 - ratio
                render_samples.append(WbvCurveOverlayRenderSample(md=md, value=value, normalized=ratio))
            baseline = 0.0
            if appearance and appearance.fill_baseline_source == "manual" and appearance.fill_baseline_value is not None:
                baseline_value = float(appearance.fill_baseline_value)
                if logarithmic:
                    if baseline_value > 0 and low > 0 and high > 0:
                        baseline = (math.log10(baseline_value) - math.log10(low)) / (math.log10(high) - math.log10(low))
                else:
                    baseline = (baseline_value - low) / (high - low)
                baseline = max(0.0, min(1.0, baseline))
                if reverse:
                    baseline = 1.0 - baseline
            curves.append(WbvCurveOverlayRenderCurve(
                curve_product_id=curve_id,
                display_name=managed_item.display_name,
                mnemonic=managed_item.curve_name or managed_item.display_name,
                unit=managed_item.curve_unit,
                display_order=setting.display_order if setting else 0,
                radial_lane=appearance.radial_lane if appearance else 0,
                track_id=appearance.track_id if appearance else None,
                radial_width=appearance.radial_width if appearance else 1.0,
                color=appearance.color if appearance else "#58d39b",
                line_width=appearance.line_width if appearance else 1.5,
                opacity=appearance.opacity if appearance else 1.0,
                fill_mode=appearance.fill_mode if appearance else "none",
                fill_target_curve_product_id=appearance.fill_target_curve_product_id if appearance else None,
                fill_side=appearance.fill_side if appearance else "positive",
                fill_color=appearance.fill_color if appearance else "#58d39b",
                fill_opacity=appearance.fill_opacity if appearance else 0.35,
                fill_outline=appearance.fill_outline if appearance else True,
                baseline_normalized=baseline,
                display_min=(high if reverse else low),
                display_max=(low if reverse else high),
                scale_type="logarithmic" if logarithmic else "linear",
                display_direction="reversed" if reverse else "normal",
                range_source=normalization.range_source,
                policy_revision=normalization.policy_revision,
                provenance=normalization.provenance,
                samples=render_samples,
            ))
        track_order = {track.track_id: track.display_order for track in config.tracks}
        curves.sort(key=lambda item: (track_order.get(item.track_id or "", item.radial_lane), item.display_order, item.mnemonic.casefold()))
        return WbvCurveOverlayRenderContract(
            managed_well_id=record.managed_well_id,
            track_spacing=config.track_spacing,
            tracks=config.tracks,
            curves=curves,
        )

    @staticmethod
    def _finite_number(value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    def get_display_layer_configuration(self, managed_well_id: str) -> WbvDisplayLayerConfigurationContract:
        record = self.repository.get_record(managed_well_id)
        raw = record.metadata.get(_WBV_DISPLAY_LAYER_CONFIG_KEY, [])
        layers: list[WbvDisplayLayerConfiguration] = []
        tracks: list[WbvTrackConfiguration] = []
        track_spacing = 0.05
        raw_layers = raw
        if isinstance(raw, dict):
            raw_layers = raw.get("layers", [])
            track_spacing = float(raw.get("track_spacing", 0.05) or 0.05)
            for item in raw.get("tracks", []):
                try:
                    tracks.append(WbvTrackConfiguration.model_validate(item))
                except Exception:
                    continue
        if isinstance(raw_layers, list):
            for item in raw_layers:
                try:
                    layers.append(WbvDisplayLayerConfiguration.model_validate(item))
                except Exception:
                    continue
        if not tracks:
            curve_layer = next((item for item in layers if item.layer_type == "curve_overlays"), None)
            lane_ids = sorted({setting.appearance.radial_lane for setting in (curve_layer.curve_settings if curve_layer else [])}) or [0]
            tracks = [WbvTrackConfiguration(track_id=f"curve-track-{lane}", display_name=f"Track {index + 1}", display_order=index) for index, lane in enumerate(lane_ids)]
        return WbvDisplayLayerConfigurationContract(
            managed_well_id=record.managed_well_id,
            track_spacing=track_spacing,
            tracks=sorted(tracks, key=lambda item: item.display_order),
            layers=layers,
        )

    def set_display_layer_configuration(
        self,
        managed_well_id: str,
        layers: list[WbvDisplayLayerConfiguration],
        tracks: list[WbvTrackConfiguration] | None = None,
        track_spacing: float = 0.05,
    ) -> WbvDisplayLayerConfigurationContract:
        record = self.repository.get_record(managed_well_id)
        tracks = list(tracks or [])
        if not tracks:
            tracks = [WbvTrackConfiguration(track_id="curve-track-0", display_name="Track 1", display_order=0)]
        track_ids = [item.track_id for item in tracks]
        if len(track_ids) != len(set(track_ids)):
            raise ValueError("Duplicate WBV track identity.")
        tracks.sort(key=lambda item: item.display_order)
        for index, track in enumerate(tracks):
            track.display_order = index
        allowed = {
            "formation_tops",
            "lithology_intervals",
            "casing_hole_sections",
            "completions",
            "curve_overlays",
            "borehole_imagery",
        }
        seen: set[str] = set()
        validated: list[WbvDisplayLayerConfiguration] = []
        for layer in layers:
            if layer.layer_type not in allowed:
                raise ValueError(f"Unsupported WBV display layer: {layer.layer_type}")
            if layer.layer_type in seen:
                raise ValueError(f"Duplicate WBV display layer configuration: {layer.layer_type}")
            seen.add(layer.layer_type)
            if layer.layer_type == "curve_overlays":
                selected_ids = set(layer.selected_item_ids)
                setting_ids = [item.curve_product_id for item in layer.curve_settings]
                if len(setting_ids) != len(set(setting_ids)):
                    raise ValueError("Duplicate WBV curve overlay item configuration.")
                unknown = set(setting_ids) - selected_ids
                if unknown:
                    raise ValueError(
                        "WBV curve settings reference unselected curves: "
                        + ", ".join(sorted(unknown))
                    )
                setting_by_id = {item.curve_product_id: item for item in layer.curve_settings}
                valid_track_ids = set(track_ids)
                curve_track_ids = {track.track_id for track in tracks if track.track_type == "curve"}

                # Normalize every legacy radial-lane assignment before validating
                # relationships between curves. Pair validation must not depend on
                # the order in which curve settings happen to be supplied.
                for setting in layer.curve_settings:
                    appearance = setting.appearance
                    if not appearance.track_id:
                        legacy_index = min(appearance.radial_lane, len(tracks) - 1)
                        appearance.track_id = tracks[legacy_index].track_id
                    if appearance.track_id not in valid_track_ids:
                        raise ValueError(f"Unknown WBV track for curve {setting.curve_product_id}: {appearance.track_id}")
                    if appearance.track_id not in curve_track_ids:
                        raise ValueError(
                            f"WBV curve {setting.curve_product_id} must be assigned to a curve track: {appearance.track_id}"
                        )
                    appearance.radial_lane = track_ids.index(appearance.track_id)

                per_track_order: dict[str, int] = {}
                for setting in sorted(layer.curve_settings, key=lambda item: (track_ids.index(item.appearance.track_id or track_ids[0]), item.display_order)):
                    track_id = setting.appearance.track_id or track_ids[0]
                    setting.display_order = per_track_order.get(track_id, 0)
                    per_track_order[track_id] = setting.display_order + 1

                for setting in layer.curve_settings:
                    appearance = setting.appearance
                    if appearance.fill_mode != "between_curves":
                        continue
                    target_id = str(appearance.fill_target_curve_product_id or "").strip()
                    if not target_id:
                        raise ValueError(
                            f"Between-curves fill requires a target curve: {setting.curve_product_id}"
                        )
                    if target_id == setting.curve_product_id:
                        raise ValueError("A curve cannot fill to itself.")
                    if target_id not in selected_ids:
                        raise ValueError(
                            f"Between-curves fill target is not selected: {target_id}"
                        )
                    target = setting_by_id.get(target_id)
                    if target is None:
                        raise ValueError(
                            f"Between-curves fill target has no curve settings: {target_id}"
                        )
                    if target.appearance.track_id != appearance.track_id:
                        raise ValueError(
                            "Between-curves fill requires both curves to share a track."
                        )
                layer.curve_settings.sort(key=lambda item: item.display_order)
            elif layer.curve_settings:
                raise ValueError(
                    f"curve_settings are only valid for curve_overlays, not {layer.layer_type}."
                )
            validated.append(layer)
        record.metadata[_WBV_DISPLAY_LAYER_CONFIG_KEY] = {
            "track_spacing": track_spacing,
            "tracks": [track.model_dump(mode="json") for track in tracks],
            "layers": [layer.model_dump(mode="json") for layer in validated],
        }
        record.updated_at = utc_now_iso()
        self.repository.upsert_record(record)
        return WbvDisplayLayerConfigurationContract(
            managed_well_id=record.managed_well_id,
            track_spacing=track_spacing,
            tracks=tracks,
            layers=validated,
        )

    def get_survey_qaqc(self, managed_well_id: str) -> WbvSurveyQaqcContract:
        record = self.repository.get_record(managed_well_id)
        trajectory = self._trajectory_package(record)
        trajectories = self._trajectory_records(record)
        active = self._active_trajectory_record(record, trajectories)
        return WbvSurveyQaqcContract(
            managed_well_id=record.managed_well_id,
            well_id=record.well_id,
            well_name=record.well_name,
            trajectory_id=active.trajectory_id if active else None,
            trajectory_uid=active.managed_trajectory_uid if active else None,
            depth_unit=self._display_depth_unit(record, self._source_depth_unit(record)),
            angle_unit=str(record.metadata.get("angle_unit") or self._raw_trajectory_metadata(record).get("angle_unit") or "deg") if isinstance(record.metadata, dict) else "deg",
            summary=self._convert_survey_qaqc(
                self._survey_qaqc_summary(trajectory),
                self._source_depth_unit(record),
                self._display_depth_unit(record, self._source_depth_unit(record)),
            ),
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
            active_trajectory_uid=active.managed_trajectory_uid if active else None,
            geometry_status=geometry_status,
            wbv_ready=bool(active and active.wbv_eligible),
            trajectories=trajectories,
            warnings=warnings,
        )

    def set_active_trajectory(
        self,
        managed_well_id: str,
        trajectory_reference: str,
        *,
        requested_by: str | None = None,
        note: str | None = None,
    ) -> WbvSetActiveTrajectoryResponse:
        record = self.repository.get_record(managed_well_id)
        trajectories = self._trajectory_records(record)
        selected = self._resolve_trajectory_reference(
            trajectories,
            trajectory_reference,
        )
        if selected is None:
            raise ValueError(
                f"Trajectory not found for managed well {managed_well_id}: "
                f"{trajectory_reference}"
            )
        if not self._trajectory_selectable(selected):
            raise ValueError(
                "Only approved/synthetic-demo, WBV-eligible trajectories can be set active. "
                f"Trajectory {trajectory_reference} has status={selected.status.value!r}, "
                f"wbv_eligible={selected.wbv_eligible!r}."
            )

        persisted = self._metadata_trajectory_records(record)
        if not persisted:
            persisted = trajectories
        updated: list[WbvManagedTrajectoryRecord] = []
        for trajectory in persisted:
            next_trajectory = trajectory.model_copy(deep=True)
            next_trajectory.is_active = (
                next_trajectory.trajectory_id == selected.trajectory_id
                or (
                    selected.managed_trajectory_uid is not None
                    and next_trajectory.managed_trajectory_uid == selected.managed_trajectory_uid
                )
            )
            updated.append(next_trajectory)

        metadata = dict(record.metadata) if isinstance(record.metadata, dict) else {}
        metadata[_TRAJECTORY_RECORDS_KEY] = [trajectory.model_dump(mode="json") for trajectory in updated]
        metadata[_ACTIVE_TRAJECTORY_ID_KEY] = selected.trajectory_id
        if selected.managed_trajectory_uid:
            metadata[_ACTIVE_TRAJECTORY_UID_KEY] = selected.managed_trajectory_uid
        if selected.trajectory_package:
            metadata["wbv_trajectory_package"] = selected.trajectory_package
            metadata["wbv_coordinate_mode"] = selected.coordinate_mode.value
        metadata["wellbore_geometry_status"] = "active_trajectory_selected"
        metadata["wellbore_geometry_active_trajectory"] = {
            "trajectory_id": selected.trajectory_id,
            "managed_trajectory_uid": str(selected.managed_trajectory_uid) if selected.managed_trajectory_uid else None,
            "trajectory_revision_uid": str(selected.trajectory_revision_uid) if selected.trajectory_revision_uid else None,
            "representation_uid": str(selected.representation_uid) if selected.representation_uid else None,
            "source_occurrence_uid": str(selected.source_occurrence_uid) if selected.source_occurrence_uid else None,
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
            active_trajectory_uid=selected.managed_trajectory_uid,
            active_trajectory_name=selected.trajectory_name,
            geometry_status=geometry_status,
            wbv_ready=bool(next_active and next_active.wbv_eligible),
            trajectories=next_trajectories,
        )

    @staticmethod
    def _resolve_trajectory_reference(
        trajectories: list[WbvManagedTrajectoryRecord],
        reference: str,
    ) -> WbvManagedTrajectoryRecord | None:
        normalized = str(reference or "").strip()
        if not normalized:
            return None

        # Canonical managed trajectory UUIDv7 is authoritative. Legacy
        # trajectory_id remains accepted only as a request-boundary alias.
        canonical = next(
            (
                trajectory
                for trajectory in trajectories
                if str(trajectory.managed_trajectory_uid or "") == normalized
            ),
            None,
        )
        if canonical is not None:
            return canonical

        return next(
            (
                trajectory
                for trajectory in trajectories
                if trajectory.trajectory_id == normalized
            ),
            None,
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
        clean_points = [dict(point) for point in render_points if isinstance(point, dict)] if isinstance(render_points, list) else []
        enriched_points, value_sources, directional_status = self._enrich_directional_values(clean_points)
        provenance = {
            "source_type": raw.get("source_type"),
            "source_relative_path": raw.get("source_relative_path"),
            "source_fixture": raw.get("source_fixture"),
            "frame": raw.get("frame"),
            "classification_message": raw.get("classification_message"),
            "coordinate_mode": raw.get("coordinate_mode"),
            "canonical_depth_resolution": raw.get("canonical_depth_resolution"),
        }
        return WbvTrajectoryPackage(
            method=str(raw.get("method") or "") or None,
            source=str(raw.get("source") or raw.get("source_type") or "") or None,
            trajectory_class=str(raw.get("trajectory_class") or "") or None,
            viewer_state=str(raw.get("viewer_state") or "") or None,
            station_count=self._optional_int(raw.get("station_count")),
            source_station_count=self._optional_int(raw.get("source_station_count")),
            fixture_sampling=dict(raw.get("fixture_sampling") or {}) if isinstance(raw.get("fixture_sampling"), dict) else {},
            stations=stations if isinstance(stations, list) else [],
            render_points=enriched_points,
            warnings=[item for item in warnings if isinstance(item, dict)] if isinstance(warnings, list) else [],
            provenance={key: value for key, value in provenance.items() if value not in (None, "", {}, [])},
            directional_values_status=directional_status,
            point_value_sources=value_sources,
        )

    @staticmethod
    def _enrich_directional_values(points: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str], str]:
        if not points:
            return points, {}, "not_available"
        source_counts = {"inclination": 0, "azimuth": 0, "dogleg_severity": 0}
        derived_counts = {"inclination": 0, "azimuth": 0, "dogleg_severity": 0}
        previous_direction: tuple[float, float] | None = None
        previous_md: float | None = None
        for index, point in enumerate(points):
            for key in source_counts:
                if WbvService._optional_float(point.get(key)) is not None:
                    source_counts[key] += 1
                    point[f"{key}_source"] = "source"
            if index == 0:
                continue
            previous = points[index - 1]
            east0 = WbvService._optional_float(previous.get("x") if previous.get("x") is not None else previous.get("east_departure"))
            east1 = WbvService._optional_float(point.get("x") if point.get("x") is not None else point.get("east_departure"))
            north0 = WbvService._optional_float(previous.get("y") if previous.get("y") is not None else previous.get("north_departure"))
            north1 = WbvService._optional_float(point.get("y") if point.get("y") is not None else point.get("north_departure"))
            tvd0 = WbvService._optional_float(previous.get("tvd"))
            tvd1 = WbvService._optional_float(point.get("tvd"))
            md = WbvService._optional_float(point.get("md"))
            if None in (east0, east1, north0, north1, tvd0, tvd1):
                continue
            de, dn, dv = east1-east0, north1-north0, tvd1-tvd0
            horizontal = math.hypot(de, dn)
            inclination = math.degrees(math.atan2(horizontal, abs(dv))) if (horizontal or dv) else 0.0
            azimuth = (math.degrees(math.atan2(de, dn)) + 360.0) % 360.0 if horizontal else 0.0
            if WbvService._optional_float(point.get("inclination")) is None:
                point["inclination"] = inclination
                point["inclination_source"] = "derived_from_relative_geometry"
                derived_counts["inclination"] += 1
            if WbvService._optional_float(point.get("azimuth")) is None:
                point["azimuth"] = azimuth
                point["azimuth_source"] = "derived_from_relative_geometry"
                derived_counts["azimuth"] += 1
            if WbvService._optional_float(point.get("dogleg_severity")) is None and previous_direction is not None and md is not None and previous_md is not None and md > previous_md:
                inc0, azi0 = map(math.radians, previous_direction)
                inc1, azi1 = map(math.radians, (inclination, azimuth))
                cosine = math.cos(inc0)*math.cos(inc1)+math.sin(inc0)*math.sin(inc1)*math.cos(azi1-azi0)
                dogleg = math.degrees(math.acos(max(-1.0, min(1.0, cosine))))
                point["dogleg_severity"] = dogleg * 100.0 / (md-previous_md)
                point["dogleg_severity_source"] = "derived_deg_per_100_depth_units"
                derived_counts["dogleg_severity"] += 1
            previous_direction = (inclination, azimuth)
            previous_md = md
        sources = {}
        for key in source_counts:
            if source_counts[key] and derived_counts[key]: sources[key] = "mixed_source_and_derived"
            elif source_counts[key]: sources[key] = "source"
            elif derived_counts[key]: sources[key] = "derived_from_relative_geometry"
            else: sources[key] = "not_available"
        status = "source" if all(v == "source" for v in sources.values()) else ("derived_or_mixed" if any(v != "not_available" for v in sources.values()) else "not_available")
        return points, sources, status

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
        active_uid = str(record.metadata.get(_ACTIVE_TRAJECTORY_UID_KEY) or "") if isinstance(record.metadata, dict) else ""
        if active_uid:
            explicit = next((trajectory for trajectory in trajectories if trajectory.managed_trajectory_uid == active_uid), None)
            if explicit is not None:
                return explicit
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

    @staticmethod
    def _survey_qaqc_summary(trajectory: WbvTrajectoryPackage) -> WbvSurveyQaqcSummary:
        points = [point for point in trajectory.render_points if isinstance(point, dict)]
        findings: list[WbvSurveyQaqcFinding] = []
        duplicate_md_count = 0
        reversed_md_count = 0
        zero_length_interval_count = 0
        invalid_inclination_count = 0
        invalid_azimuth_count = 0
        missing_inclination_count = 0
        missing_azimuth_count = 0
        derived_inclination_count = 0
        derived_azimuth_count = 0
        md_gaps: list[float] = []
        doglegs: list[float] = []
        valid_points = 0
        previous_md: float | None = None
        previous_tvd: float | None = None
        tvd_monotonic = True

        for index, point in enumerate(points):
            md = WbvService._optional_float(point.get("md"))
            tvd = WbvService._optional_float(point.get("tvd"))
            inclination = WbvService._optional_float(point.get("inclination"))
            azimuth = WbvService._optional_float(point.get("azimuth"))
            dogleg = WbvService._optional_float(point.get("dogleg_severity"))
            station_index = WbvService._optional_int(point.get("station_index"))

            if md is None:
                findings.append(WbvSurveyQaqcFinding(
                    code="missing_md", severity="error",
                    message="Trajectory render point has no valid measured depth.",
                    station_index=station_index if station_index is not None else index,
                    target=f"trajectory.render_points[{index}].md",
                ))
                continue

            valid_points += 1
            if previous_md is not None:
                delta = md - previous_md
                if delta < 0:
                    reversed_md_count += 1
                    findings.append(WbvSurveyQaqcFinding(
                        code="reversed_md", severity="error",
                        message="Measured depth decreases between adjacent trajectory points.",
                        station_index=station_index if station_index is not None else index,
                        md_start=previous_md, md_end=md,
                        target=f"trajectory.render_points[{index}].md",
                    ))
                elif delta == 0:
                    duplicate_md_count += 1
                    zero_length_interval_count += 1
                    findings.append(WbvSurveyQaqcFinding(
                        code="duplicate_md", severity="warning",
                        message="Adjacent trajectory points have the same measured depth.",
                        station_index=station_index if station_index is not None else index,
                        md_start=previous_md, md_end=md,
                        target=f"trajectory.render_points[{index}].md",
                    ))
                else:
                    md_gaps.append(delta)

            if tvd is not None and previous_tvd is not None and tvd < previous_tvd:
                tvd_monotonic = False
                findings.append(WbvSurveyQaqcFinding(
                    code="reversed_tvd", severity="warning",
                    message="True vertical depth decreases between adjacent trajectory points.",
                    station_index=station_index if station_index is not None else index,
                    md_start=previous_md, md_end=md,
                    target=f"trajectory.render_points[{index}].tvd",
                ))

            if inclination is None:
                missing_inclination_count += 1
            elif point.get("inclination_source") != "source":
                derived_inclination_count += 1
            if azimuth is None:
                missing_azimuth_count += 1
            elif point.get("azimuth_source") != "source":
                derived_azimuth_count += 1

            if inclination is not None and not (0.0 <= inclination <= 180.0):
                invalid_inclination_count += 1
                findings.append(WbvSurveyQaqcFinding(
                    code="invalid_inclination", severity="error",
                    message="Inclination is outside the valid 0–180 degree range.",
                    station_index=station_index if station_index is not None else index,
                    md_start=md, md_end=md,
                    target=f"trajectory.render_points[{index}].inclination",
                ))

            if azimuth is not None and not (0.0 <= azimuth < 360.0):
                invalid_azimuth_count += 1
                findings.append(WbvSurveyQaqcFinding(
                    code="invalid_azimuth", severity="error",
                    message="Azimuth is outside the valid 0–360 degree range.",
                    station_index=station_index if station_index is not None else index,
                    md_start=md, md_end=md,
                    target=f"trajectory.render_points[{index}].azimuth",
                ))

            if dogleg is not None:
                doglegs.append(dogleg)
            previous_md = md
            if tvd is not None:
                previous_tvd = tvd

        return WbvSurveyQaqcSummary(
            station_count=trajectory.station_count or len(points),
            source_station_count=trajectory.source_station_count,
            valid_point_count=valid_points,
            md_monotonic=reversed_md_count == 0,
            tvd_monotonic=tvd_monotonic,
            duplicate_md_count=duplicate_md_count,
            reversed_md_count=reversed_md_count,
            zero_length_interval_count=zero_length_interval_count,
            invalid_inclination_count=invalid_inclination_count,
            invalid_azimuth_count=invalid_azimuth_count,
            missing_inclination_count=missing_inclination_count,
            missing_azimuth_count=missing_azimuth_count,
            derived_inclination_count=derived_inclination_count,
            derived_azimuth_count=derived_azimuth_count,
            overall_state="error" if any(f.severity == "error" for f in findings) else ("warning" if findings or derived_inclination_count or derived_azimuth_count else "pass"),
            max_station_gap=max(md_gaps) if md_gaps else None,
            max_dogleg_severity=max(doglegs) if doglegs else None,
            finding_count=len(findings),
            findings=findings,
        )

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


    @staticmethod
    def _normalize_depth_unit(value: Any) -> str:
        normalized = str(value or "").strip().lower()
        if normalized in {"ft", "feet", "foot"}:
            return "ft"
        if normalized in {"m", "meter", "meters", "metre", "metres"}:
            return "m"
        return normalized

    def _source_depth_unit(self, record: ManagedWellRecord) -> str:
        return self._normalize_depth_unit(
            record.depth_unit or self._trajectory_depth_unit(record) or "ft"
        ) or "ft"

    def _display_depth_unit(self, record: ManagedWellRecord, source_unit: str) -> str:
        metadata = record.metadata if isinstance(record.metadata, dict) else {}
        requested = self._normalize_depth_unit(metadata.get(_WBV_DEPTH_UNIT_KEY))
        return requested if requested in {"ft", "m"} else source_unit

    @staticmethod
    def _distance_factor(source_unit: str, target_unit: str) -> float:
        if source_unit == target_unit:
            return 1.0
        if source_unit == "ft" and target_unit == "m":
            return 0.3048
        if source_unit == "m" and target_unit == "ft":
            return 1.0 / 0.3048
        raise ValueError(f"Unsupported WBV depth-unit conversion: {source_unit} to {target_unit}")

    @staticmethod
    def _convert_optional(value: Any, factor: float) -> Any:
        return value * factor if isinstance(value, (int, float)) and math.isfinite(value) else value

    @classmethod
    def _convert_trajectory_package(cls, trajectory: WbvTrajectoryPackage, source_unit: str, target_unit: str) -> WbvTrajectoryPackage:
        if source_unit == target_unit:
            return trajectory
        factor = cls._distance_factor(source_unit, target_unit)
        dls_factor = (30.0 / 30.48) if source_unit == "ft" else (30.48 / 30.0)
        converted = trajectory.model_copy(deep=True)
        distance_keys = {"md", "tvd", "tvdss", "x", "y", "z", "east_departure", "north_departure"}
        for collection_name in ("render_points", "stations"):
            collection = getattr(converted, collection_name)
            for point in collection:
                for key in distance_keys:
                    if key in point:
                        point[key] = cls._convert_optional(point.get(key), factor)
                if "dogleg_severity" in point:
                    point["dogleg_severity"] = cls._convert_optional(point.get("dogleg_severity"), dls_factor)
        return converted

    @classmethod
    def _convert_bounding_box(cls, bounding_box: dict[str, Any], source_unit: str, target_unit: str) -> dict[str, Any]:
        if source_unit == target_unit:
            return dict(bounding_box)
        factor = cls._distance_factor(source_unit, target_unit)
        result = dict(bounding_box)
        for key in ("md", "tvd", "x", "y", "z"):
            axis = result.get(key)
            if isinstance(axis, dict):
                axis = dict(axis)
                axis["min"] = cls._convert_optional(axis.get("min"), factor)
                axis["max"] = cls._convert_optional(axis.get("max"), factor)
                result[key] = axis
        return result

    @classmethod
    def _convert_survey_qaqc(cls, summary: WbvSurveyQaqcSummary, source_unit: str, target_unit: str) -> WbvSurveyQaqcSummary:
        if source_unit == target_unit:
            return summary
        factor = cls._distance_factor(source_unit, target_unit)
        dls_factor = (30.0 / 30.48) if source_unit == "ft" else (30.48 / 30.0)
        converted = summary.model_copy(deep=True)
        converted.max_station_gap = cls._convert_optional(converted.max_station_gap, factor)
        converted.max_dogleg_severity = cls._convert_optional(converted.max_dogleg_severity, dls_factor)
        for finding in converted.findings:
            finding.md_start = cls._convert_optional(finding.md_start, factor)
            finding.md_end = cls._convert_optional(finding.md_end, factor)
        return converted

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
