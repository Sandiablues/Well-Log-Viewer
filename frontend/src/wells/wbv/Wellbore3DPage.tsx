import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { createWbvInteractionCommandAuthority, wbvInteractionApiV2, type WbvInteractionCommandAuthority, type WbvInteractionStateV2, type WbvScreenObservationV2 } from './interactionDomain';
import { fetchWlvJson } from "../../api/wlvBackendClient";
import { changeWbvOverlayPackageLifecycle, commandWbvTrackLayout, deleteWbvOverlayPackage, getWbvTrackLayout, listWbvOverlayPackages, publishedWbvRenderPackageUrl, setWbvOverlayPackageActive, updateWbvPresentationOverrides, type WbvLayoutCommand, type WbvLayoutTrack, type WbvOverlayPackage, type WbvPresentationOverrides, type WbvTrackLayout } from "./publicationApi";
import "./Wellbore3DPage.css";
import { SavedCanvasToolbarControl, type SavedCanvasToolbarItem } from "../wdv/SavedCanvasToolbarControl";
import { ExternalWindowPortal } from "./ExternalWindowPortal";
import {
  WellboreTrajectoryRenderer,
  type WbvViewPreset,
  type WbvViewAction,
  type WbvCurveTrack,
  type WbvCoreTrack,
  type WbvCoreRenderChunk,
  type WbvCoreLocatorPick,
  type WbvTrackPlacementTrack,
  type WbvCameraViewState,
} from "./WellboreTrajectoryRenderer";

const WBV_NAVIGATION_CAMERA_VIEW_STORAGE_KEY = "wlv:wbv:navigation-camera-view:v1";

function isFiniteCameraTuple(values: readonly number[], expectedLength: number): boolean {
  return values.length === expectedLength && values.every((value) => Number.isFinite(value));
}

function validWbvCameraViewState(value: unknown): value is WbvCameraViewState {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<WbvCameraViewState>;
  return Array.isArray(candidate.position)
    && isFiniteCameraTuple(candidate.position, 3)
    && Array.isArray(candidate.up)
    && isFiniteCameraTuple(candidate.up, 3)
    && Array.isArray(candidate.quaternion)
    && isFiniteCameraTuple(candidate.quaternion, 4)
    && Array.isArray(candidate.target)
    && isFiniteCameraTuple(candidate.target, 3)
    && typeof candidate.zoom === "number"
    && Number.isFinite(candidate.zoom)
    && candidate.zoom > 0
    && typeof candidate.view_height === "number"
    && Number.isFinite(candidate.view_height)
    && candidate.view_height > 0;
}

function readWbvNavigationCameraView(): WbvCameraViewState | null {
  try {
    const raw = window.localStorage.getItem(WBV_NAVIGATION_CAMERA_VIEW_STORAGE_KEY)
      ?? window.sessionStorage.getItem(WBV_NAVIGATION_CAMERA_VIEW_STORAGE_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (!validWbvCameraViewState(parsed)) {
      window.localStorage.removeItem(WBV_NAVIGATION_CAMERA_VIEW_STORAGE_KEY);
      window.sessionStorage.removeItem(WBV_NAVIGATION_CAMERA_VIEW_STORAGE_KEY);
      return null;
    }
    // One-time migration from the former session-only store.
    window.localStorage.setItem(WBV_NAVIGATION_CAMERA_VIEW_STORAGE_KEY, JSON.stringify(parsed));
    return structuredClone(parsed);
  } catch {
    return null;
  }
}

function writeWbvNavigationCameraView(view: WbvCameraViewState): void {
  try {
    window.localStorage.setItem(WBV_NAVIGATION_CAMERA_VIEW_STORAGE_KEY, JSON.stringify(view));
  } catch {
    // Navigation persistence is best-effort and must never interrupt WBV interaction.
  }
}

function wbvApiBaseUrl(): string {
  const runtimeConfig = window as unknown as { __WLV_API_BASE_URL__?: string };
  if (runtimeConfig.__WLV_API_BASE_URL__) {
    return runtimeConfig.__WLV_API_BASE_URL__.replace(/\/$/, "");
  }
  const protocol = window.location.protocol || "http:";
  const hostname = window.location.hostname || "127.0.0.1";
  const port = window.location.port;
  if (port === "8001") return "";
  if (port === "5173" || port === "5174" || port === "5175") {
    return `${protocol}//${hostname}:8001`;
  }
  return "http://127.0.0.1:8001";
}

function lithologyKrPatternUrl(interval: WbvLithologyIntervalItem): string | null {
  const canonicalId = interval.canonical_lithology?.trim();
  if (!canonicalId) return null;
  // Do not override the KR catalogue colours with LCM interval colours here.
  // The KR SVG endpoint already applies the canonical defaultBackground/defaultPattern
  // for the lithology entry (e.g. yellow sands, green limestones). Supplying the
  // interval publication colours was forcing many otherwise-correct KR symbols to
  // render gray/pink.
  return `${wbvApiBaseUrl()}/api/wlv/knowledge/lithology/entries/${encodeURIComponent(canonicalId)}/pattern.svg`;
}

function lithologyKrEntryUrl(interval: WbvLithologyIntervalItem): string | null {
  const canonicalId = interval.canonical_lithology?.trim();
  if (!canonicalId) return null;
  return `${wbvApiBaseUrl()}/api/wlv/knowledge/lithology/entries/${encodeURIComponent(canonicalId)}`;
}

function lithologyRendererInterval(interval: WbvLithologyIntervalItem) {
  return {
    ...interval,
    kr_entry_url: lithologyKrEntryUrl(interval),
    kr_pattern_url: lithologyKrPatternUrl(interval),
  };
}

type WbvCoreInspectionInterval = { top_md: number; base_md: number };
function orderedCoreChunks(chunks: WbvCoreRenderChunk[]): WbvCoreRenderChunk[] {
  return [...chunks].sort((first, second) => {
    const firstTop = Math.min(first.top_md, first.base_md);
    const secondTop = Math.min(second.top_md, second.base_md);
    if (firstTop !== secondTop) return firstTop - secondTop;
    const firstBase = Math.max(first.top_md, first.base_md);
    const secondBase = Math.max(second.top_md, second.base_md);
    return firstBase - secondBase;
  });
}

type WbvViewerState =
  | "not_loaded"
  | "missing_survey"
  | "invalid_survey"
  | "relative_only"
  | "available"
  | "available_vertical"
  | "needs_review"
  | "unavailable";

type WbvWarning = {
  code?: string;
  severity?: "info" | "warning" | "error" | string;
  message?: string;
  target?: string | null;
};

type WbvAvailableLayers = {
  trajectory?: boolean;
  survey_stations?: boolean;
  depth_labels?: boolean;
  formation_tops?: boolean;
  lithology?: boolean;
  core?: boolean;
  casing?: boolean;
  completions?: boolean;
  loaded_curves?: boolean;
  curve_attributes?: boolean;
};

type WbvSourceSession = {
  contract_kind?: string;
  active_viewer_package_id?: string | null;
  loaded_product_count?: number;
  source_product_ids?: string[];
  depth_domain?: Record<string, unknown> | null;
};

type WbvSessionContract = {
  contract_kind?: string;
  contract_version?: string;
  viewer?: "WBV";
  active_managed_well_id?: string | null;
  active_managed_well_uid?: string | null;
  well_id?: string | null;
  well_name?: string | null;
  viewer_state?: WbvViewerState;
  coordinate_mode?: string;
  source_session?: WbvSourceSession | null;
  available_layers?: WbvAvailableLayers;
  warnings?: WbvWarning[];
};

type ManagedWellSummary = { managed_well_id: string; well_name: string };
type WdvWorkspaceSummary = {
  active_managed_well_id?: string | null;
  loaded_wells?: Array<{ managed_well_id: string; well_name?: string }>;
};
type WbvWellSelectorItem = {
  managedWellId: string;
  wellName: string;
  viewerState: WbvViewerState;
  hasSurvey: boolean;
  loadedInWdv: boolean;
  activeInWdv: boolean;
};

type WbvRenderPoint = {
  station_index?: number;
  md?: number | null;
  tvd?: number | null;
  tvdss?: number | null;
  x?: number | null;
  y?: number | null;
  z?: number | null;
  inclination?: number | null;
  azimuth?: number | null;
  dogleg_severity?: number | null;
  east_departure?: number | null;
  north_departure?: number | null;
  source?: Record<string, unknown>;
  inclination_source?: string | null;
  azimuth_source?: string | null;
  dogleg_severity_source?: string | null;
};

type WbvTrajectoryPackage = {
  method?: string | null;
  source?: string | null;
  trajectory_class?: string | null;
  viewer_state?: string | null;
  station_count?: number | null;
  source_station_count?: number | null;
  fixture_sampling?: Record<string, unknown>;
  stations?: unknown[];
  render_points?: WbvRenderPoint[];
  warnings?: WbvWarning[];
  provenance?: Record<string, unknown>;
  directional_values_status?: string;
  point_value_sources?: Record<string, string>;
};

type WbvAxisRange = {
  min?: number | null;
  max?: number | null;
};

type WbvBoundingBox = {
  x?: WbvAxisRange;
  y?: WbvAxisRange;
  z?: WbvAxisRange;
  md?: WbvAxisRange;
  tvd?: WbvAxisRange;
};

type WbvSurveyQaqcFinding = {
  code?: string;
  severity?: "info" | "warning" | "error" | string;
  message?: string;
  station_index?: number | null;
  md_start?: number | null;
  md_end?: number | null;
};

type WbvSurveyQaqcSummary = {
  station_count?: number;
  source_station_count?: number | null;
  valid_point_count?: number;
  md_monotonic?: boolean;
  tvd_monotonic?: boolean;
  duplicate_md_count?: number;
  reversed_md_count?: number;
  zero_length_interval_count?: number;
  invalid_inclination_count?: number;
  invalid_azimuth_count?: number;
  missing_inclination_count?: number;
  missing_azimuth_count?: number;
  derived_inclination_count?: number;
  derived_azimuth_count?: number;
  overall_state?: "pass" | "warning" | "error";
  max_station_gap?: number | null;
  max_dogleg_severity?: number | null;
  finding_count?: number;
  findings?: WbvSurveyQaqcFinding[];
};

type WbvViewerPackageContract = {
  contract_kind?: string;
  contract_version?: string;
  viewer?: "WBV";
  managed_well_id?: string;
  well_id?: string;
  well_name?: string;
  viewer_state?: WbvViewerState;
  coordinate_mode?: string;
  depth_unit?: string;
  angle_unit?: string;
  trajectory?: WbvTrajectoryPackage;
  survey_qaqc?: WbvSurveyQaqcSummary;
  bounding_box?: WbvBoundingBox;
  available_layers?: WbvAvailableLayers;
  available_attribute_tracks?: Array<{
    product_id?: string;
    curve_name?: string | null;
    display_name?: string | null;
    curve_family?: string | null;
    unit?: string | null;
  }>;
  warnings?: WbvWarning[];
};

type WbvDisplayLayerFile = {
  product_id: string;
  display_name: string;
  display_layer_type: string;
  depth_reference: string;
  depth_units: string;
  depth_start?: number | null;
  depth_end?: number | null;
};

type WbvDisplayLayerFilesContract = {
  managed_well_id: string;
  layers: Record<string, WbvDisplayLayerFile[]>;
};

type WbvFormationTopItem = { top_id: string; product_id?: string | null; name: string; marker_type: string; group?: string | null; md: number; tvd?: number | null; tvdss?: number | null; uncertainty?: number | null; pick_status?: string | null; source_document?: string | null; source_page?: number | null; };
type WbvFormationTopProduct = { product_id: string; display_name: string; tops: WbvFormationTopItem[]; };
type WbvFormationTopProductsContract = { managed_well_id: string; products: WbvFormationTopProduct[]; };
type WbvLithologyIntervalItem = {
  interval_id: string;
  product_id?: string | null;
  lithology: string;
  canonical_lithology?: string | null;
  top_md: number;
  base_md: number;
  pattern_id?: string | null;
  background_color?: string | null;
  pattern_color?: string | null;
  kr_entry_url?: string | null;
  kr_pattern_url?: string | null;
};
type WbvLithologyProduct = { product_id: string; display_name: string; intervals: WbvLithologyIntervalItem[]; };
type WbvLithologyProductsContract = { managed_well_id: string; products: WbvLithologyProduct[]; };

type WbvCompletionComponentItem = {
  component_id: string;
  product_id?: string | null;
  canonical_id: string;
  canonical_component_key: string;
  label: string;
  top_md: number;
  base_md?: number | null;
  depth_unit: string;
  diameter?: number | null;
  status?: string | null;
  confidence?: string | null;
  geometry_class: string;
  geometry_family: string;
  material_family: string;
  annotation_policy: string;
};
type WbvCompletionProduct = { product_id: string; display_name: string; components: WbvCompletionComponentItem[]; };
type WbvCompletionProductsContract = { managed_well_id: string; products: WbvCompletionProduct[]; };

type WbvCurveOverlayCurve = {
  curve_product_id: string;
  managed_curve_uid?: string | null;
  display_name: string;
  mnemonic: string;
  description?: string | null;
  unit?: string | null;
  curve_family?: string | null;
  depth_start?: number | null;
  depth_end?: number | null;
  depth_units?: string | null;
  run_interval?: string | null;
  run_number?: string | null;
  run_date?: string | null;
  curve_type?: string | null;
  classification_source?: string | null;
  classification_confidence?: string | null;
  review_required?: boolean;
  source_display_name?: string | null;
};

type WbvCurveOverlayProduct = {
  curve_product_id: string;
  display_name: string;
  curve_count: number;
  curves: WbvCurveOverlayCurve[];
};

type WbvCurveOverlayProductsContract = {
  managed_well_id: string;
  products: WbvCurveOverlayProduct[];
};


type WbvCoreDisplayChunkManifestItem = {
  chunk_id: string;
  sequence_index?: number;
  top_depth: number;
  base_depth: number;
  depth_unit?: string;
  pixel_width?: number;
  pixel_height?: number;
};

type WbvCoreDisplayChunksContract = {
  product_id: string;
  segment_id?: string | null;
  segment_name?: string | null;
  top_depth?: number | null;
  base_depth?: number | null;
  depth_unit?: string | null;
  chunks: WbvCoreDisplayChunkManifestItem[];
};

type WbvCoreDescriptionItem = {
  description_id: string;
  product_id: string;
  top_md: number;
  base_md: number;
  text: string;
  category: string;
};

type WbvCoreManagedWellRecord = {
  product_groups?: Array<{
    items?: Array<{
      product_id?: string | null;
      product_subgroup_key?: string | null;
      provenance?: {
        description_intervals?: Array<Record<string, unknown>> | null;
      } | null;
    }>;
  }>;
};

type WbvCurveOverlayNormalizationItem = {
  curve_product_id: string;
  display_name: string;
  mnemonic: string;
  unit?: string | null;
  display_min: number;
  display_max: number;
  scale_type: "linear" | "logarithmic";
  display_direction: "normal" | "reversed";
  range_source: string;
  requires_review: boolean;
  sample_count: number;
  below_range_count: number;
  above_range_count: number;
  clipped_fraction: number;
};

type WbvCurveOverlayNormalizationContract = {
  managed_well_id: string;
  curves: WbvCurveOverlayNormalizationItem[];
};

type WbvCurveOverlayRenderSample = { md: number; value: number; normalized: number };

type WbvTrackConfig = {
  track_id: string;
  display_name: string;
  track_type: "curve" | "reference" | "image" | "interval";
  display_order: number;
  side: "left" | "right" | "center";
  geometry_type: "legacy_planar" | "camera_ribbon" | "radial_panel";
  radial_lane: number;
  angular_position_deg: number;
  orientation_mode: "follow_trajectory" | "camera_facing";
  thickness: number;
  width: number;
  background_mode: "transparent" | "black" | "white" | "custom";
  background_color: string;
  background_opacity: number;
  border_visible: boolean;
  border_color: string;
  wellbore_offset: number;
  previous_track_gap: number;
};

type WbvCurveOverlayRenderCurve = {
  assignment_uid?: string | null;
  curve_product_id: string;
  display_name: string;
  mnemonic: string;
  unit?: string | null;
  display_order: number;
  radial_lane: number;
  track_id?: string | null;
  radial_width: number;
  color: string;
  line_width: number;
  opacity: number;
  label_visible?: boolean;
  label_content?: "mnemonic" | "mnemonic_value" | "scale" | "mnemonic_scale";
  label_anchor?: "top" | "base" | "custom_md";
  label_custom_md?: number | null;
  label_size?: number;
  label_weight?: number;
  label_alignment?: "left" | "center" | "right";
  label_position?: "on_track" | "left" | "right" | "center";
  label_horizontal_adjustment?: number;
  label_vertical_adjustment?: number;
  scale_color?: string;
  scale_opacity?: number;
  scale_line_width?: number;
  scale_size?: number;
  display_min?: number | null;
  display_max?: number | null;
  scale_type?: "linear" | "logarithmic" | null;
  display_direction?: "normal" | "reversed" | null;
  fill_mode: "none" | "to_baseline" | "between_curves";
  fill_target_curve_product_id?: string | null;
  fill_side: "positive" | "negative";
  fill_color: string;
  fill_opacity: number;
  fill_outline: boolean;
  baseline_normalized: number;
  samples: WbvCurveOverlayRenderSample[];
};

type WbvCurveOverlayRenderContract = {
  managed_well_id: string;
  track_spacing: number;
  tracks: WbvTrackConfig[];
  curves: WbvCurveOverlayRenderCurve[];
};

type WbvManagerTab = "view_properties" | "track_layout" | WbvDisplayLayerKey;

type WbvDisplayLayerKey =
  | "formation_tops"
  | "lithology_intervals"
  | "core_images"
  | "casing_hole_sections"
  | "completions"
  | "curve_overlays"
  | "borehole_imagery";

type WbvCurveScaleSource = "backend_default" | "kr_curve" | "kr_family" | "robust_p5_p95" | "manual";

type WbvCurveItemConfig = {
  curve_product_id: string;
  display_order: number;
  scale: {
    source: WbvCurveScaleSource;
    minimum?: number | null;
    maximum?: number | null;
    scale_type: "linear" | "logarithmic";
    direction: "normal" | "reversed";
    direction_source: "governed" | "manual";
    clamp_outliers: boolean;
    show_clipping: boolean;
  };
  appearance: {
    color: string;
    line_width: number;
    opacity: number;
    display_mode: "line" | "ribbon";
    radial_lane: number;
    track_id?: string | null;
    radial_width: number;
    show_label: boolean;
    label_position: "top" | "base" | "both" | "none";
    show_clipped_markers: boolean;
    fill_mode: "none" | "to_baseline" | "between_curves";
    fill_target_curve_product_id?: string | null;
    fill_side: "positive" | "negative";
    fill_color: string;
    fill_opacity: number;
    fill_baseline_source: "governed" | "manual";
    fill_baseline_value?: number | null;
    fill_outline: boolean;
  };
};

type WbvLayerConfig = {
  layer_type: WbvDisplayLayerKey;
  visible: boolean;
  selected_item_ids: string[];
  source_type: "wmd" | "wdv_template";
  source_product_id?: string | null;
  scale: {
    mode: "backend_default" | "manual";
    minimum?: number | null;
    maximum?: number | null;
    scale_type: "linear" | "logarithmic";
    direction: "normal" | "reversed";
  };
  appearance: {
    color?: string | null;
    opacity: number;
    line_width: number;
    display_mode?: string | null;
    show_labels: boolean;
    marker_style?: "ring" | "disc" | "tick" | "flag";
    marker_size?: number;
    color_mode?: "formation" | "well" | "classification" | "single";
    label_mode?: "name" | "name_md" | "name_tvd" | "name_md_tvd";
    label_size?: number;
    label_offset?: number;
    label_position?: "right" | "left" | "above" | "below";
    selected_top_ids?: string[] | null;
    selected_interval_ids?: string[] | null;
    selected_component_ids?: string[] | null;
    label_color?: string | null;
    brightness?: number;
    pattern_scale?: number;
    hide_underlay?: boolean;
  };
  curve_settings: WbvCurveItemConfig[];
};

type WbvManagerRect = { left: number; top: number; width: number; height: number };
type WbvCoreModalSize = { width: number; height: number };

type WbvCoreRestartRecoveryState = {
  schema_version: 1;
  managed_well_id: string | null;
  core_view_mode: boolean;
  core_modal: {
    open: boolean;
    chunk_id: string;
    target_md: number | null;
    visible_interval: WbvCoreInspectionInterval | null;
    zoom: number;
    zoom_locked: boolean;
    expanded: boolean;
    position: { x: number; y: number } | null;
    size: WbvCoreModalSize | null;
  };
  core_layout: {
    lattice_side: "off" | "left" | "right";
    lattice_offset: number;
    description_side: "off" | "left" | "right";
    description_offset: number;
    description_width: number;
    description_font_size: number;
    description_show_md: boolean;
  };
  display_modal: {
    rect: WbvManagerRect;
    expanded: boolean;
    popped_out: boolean;
    active_tab: WbvManagerTab;
    selected_view_property: keyof WbvViewProperties;
  };
};

type WbvRecoveryStateRecord = {
  schema_version: 1;
  updated_at?: string | null;
  state: Partial<WbvCoreRestartRecoveryState>;
};

type WbvDisplayLayerConfigurationContract = {
  managed_well_id: string;
  track_spacing: number;
  tracks: WbvTrackConfig[];
  layers: WbvLayerConfig[];
};

type WbvDepthUnit = "ft" | "m";

/* WBV_SAVE_CANVAS_V1_0_0 */
type WbvSavedCanvasSnapshot = {
  schema_version: 1;
  core_recovery_state?: WbvCoreRestartRecoveryState | null;
  displayed_well_ids: string[];
  active_managed_well_id: string | null;
  view_properties_by_well: Record<string, WbvViewProperties>;
  viewer_controls: WbvViewerControls;
  display_layers: WbvDisplayLayerControls;
  track_values_along_wellbore: boolean;
  view_preset: WbvViewPreset;
  zoom_percent: number;
  camera_view?: WbvCameraViewState | null;
  horizontal_rotation_locked: boolean;
  vertical_rotation_locked: boolean;
  layer_configurations_by_well: Record<string, WbvDisplayLayerConfigurationContract>;
};
type WbvSavedCanvasRecord = SavedCanvasToolbarItem & { snapshot: WbvSavedCanvasSnapshot };


type WbvInteractionState = WbvInteractionStateV2;
type WbvLoadState = {
  session: WbvSessionContract | null;
  viewerPackage: WbvViewerPackageContract | null;
  loading: boolean;
  error: string | null;
};

type WbvDisplayedWellLayerBundle = {
  files: WbvDisplayLayerFilesContract | null;
  configuration: WbvDisplayLayerConfigurationContract | null;
  formationTops: WbvFormationTopProductsContract | null;
  lithologyProducts: WbvLithologyProductsContract | null;
  completionProducts: WbvCompletionProductsContract | null;
  curveProducts: WbvCurveOverlayProductsContract | null;
  curveRenderPackage: WbvCurveOverlayRenderContract | null;
};

type WbvDisplayedWellPackage = {
  managedWellId: string;
  wellName: string;
  viewerPackage: WbvViewerPackageContract;
  layers: WbvDisplayedWellLayerBundle;
};


type WbvWellInfoDatumValue = {
  value?: string;
  unit?: string;
};

type WbvWellInfoMetadata = Record<string, WbvWellInfoDatumValue>;

type Wellbore3DPageProps = {
  onOpenLogViewer: () => void;
  supplementalWellInfoMetadataByWell?: Record<string, WbvWellInfoMetadata>;
};

type NumericRange = {
  min: number | null;
  max: number | null;
};

const initialState: WbvLoadState = {
  session: null,
  viewerPackage: null,
  loading: true,
  error: null,
};

const orientationLabels: Record<Extract<WbvViewPreset, "north" | "east" | "south" | "west" | "top">, string> = {
  north: "F",
  east: "R",
  south: "L",
  west: "Bk",
  top: "T",
};

const orientationPresetOrder: Array<"north" | "east" | "south" | "west" | "top"> = [
  "north",
  "east",
  "south",
  "west",
  "top",
];


function stateLabel(value: string | null | undefined): string {
  if (!value) return "unknown";
  return value.replace(/_/g, " ");
}

function fieldLabel(value: string | null | undefined): string {
  if (!value) return "None";
  return value.replace(/_/g, " ");
}

function formatNumber(value: number | null | undefined, digits = 1): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return value.toLocaleString(undefined, {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}


export type WbvViewProperties = {
  trajectory: { color: string; materialMode?: "color" | "gray_metallic"; metallicTone?: "light_silver" | "silver" | "steel" | "gunmetal" | "graphite"; thickness: number; opacity: number };
  boundingBox: { color: string; thickness: number; opacity: number };
  depthLabels: { color: string; size: number; interval: number; offset: number };
  surveyStations: { color: string; size: number; shape: "circle" | "square" | "diamond" | "cross"; orientation: "along" | "across"; opacity: number };
  groundPlane: { color: string; opacity: number; size: number };
  grids: { color: string; thickness: number; spacing: number; opacity: number };
  shading: { intensity: number; ambient: number; directional: number };
};

const defaultViewProperties: WbvViewProperties = {
  trajectory: { color: "#67d599", materialMode: "color", metallicTone: "silver", thickness: 1, opacity: 1 },
  boundingBox: { color: "#587080", thickness: 1, opacity: 0.72 },
  depthLabels: { color: "#b9f3ff", size: 1, interval: 0, offset: 0.52 },
  surveyStations: { color: "#2f9bff", size: 1, shape: "circle", orientation: "along", opacity: 1 },
  groundPlane: { color: "#182129", opacity: 0.62, size: 1 },
  grids: { color: "#526878", thickness: 1, spacing: 12, opacity: 0.8 },
  shading: { intensity: 1, ambient: 1.1, directional: 1.15 },
};

type WbvViewerControls = {
  boundingBox: boolean;
  depthLabels: boolean;
  surveyStations: boolean;
  groundPlane: boolean;
  bottomGrid: boolean;
  topGrid: boolean;
  northArrow: boolean;
  surfaceLighting: boolean;
};

type WbvDisplayLayerControls = {
  trajectory: boolean;
};

const initialViewerControls: WbvViewerControls = {
  boundingBox: true,
  depthLabels: true,
  surveyStations: false,
  groundPlane: false,
  bottomGrid: false,
  topGrid: false,
  northArrow: true,
  surfaceLighting: true,
};

function numericRange(values: Array<number | null | undefined>): NumericRange {
  const clean = values.filter(
    (value): value is number =>
      typeof value === "number" && Number.isFinite(value),
  );
  if (clean.length === 0) return { min: null, max: null };
  return { min: Math.min(...clean), max: Math.max(...clean) };
}

function interpolateOptionalValue(
  first: number | null | undefined,
  second: number | null | undefined,
  ratio: number,
): number | null {
  if (typeof first === "number" && Number.isFinite(first) && typeof second === "number" && Number.isFinite(second)) {
    return first + (second - first) * ratio;
  }
  if (typeof first === "number" && Number.isFinite(first)) return first;
  if (typeof second === "number" && Number.isFinite(second)) return second;
  return null;
}

function interpolateAzimuthValue(
  first: number | null | undefined,
  second: number | null | undefined,
  ratio: number,
): number | null {
  if (typeof first !== "number" || !Number.isFinite(first)) {
    return typeof second === "number" && Number.isFinite(second) ? second : null;
  }
  if (typeof second !== "number" || !Number.isFinite(second)) return first;
  const delta = ((second - first + 540) % 360) - 180;
  return (first + delta * ratio + 360) % 360;
}

function interpolateRenderPointValue(
  first: WbvRenderPoint,
  second: WbvRenderPoint,
  ratio: number,
): WbvRenderPoint {
  return {
    station_index: interpolateOptionalValue(first.station_index, second.station_index, ratio) ?? undefined,
    md: interpolateOptionalValue(first.md, second.md, ratio),
    tvd: interpolateOptionalValue(first.tvd, second.tvd, ratio),
    tvdss: interpolateOptionalValue(first.tvdss, second.tvdss, ratio),
    x: interpolateOptionalValue(first.x, second.x, ratio),
    y: interpolateOptionalValue(first.y, second.y, ratio),
    z: interpolateOptionalValue(first.z, second.z, ratio),
    inclination: interpolateOptionalValue(first.inclination, second.inclination, ratio),
    azimuth: interpolateAzimuthValue(first.azimuth, second.azimuth, ratio),
    dogleg_severity: interpolateOptionalValue(first.dogleg_severity, second.dogleg_severity, ratio),
    east_departure: interpolateOptionalValue(first.east_departure, second.east_departure, ratio),
    north_departure: interpolateOptionalValue(first.north_departure, second.north_departure, ratio),
    inclination_source: ratio === 0 ? first.inclination_source : "interpolated_along_trajectory",
    azimuth_source: ratio === 0 ? first.azimuth_source : "interpolated_along_trajectory",
    dogleg_severity_source: ratio === 0 ? first.dogleg_severity_source : "interpolated_along_trajectory",
  };
}

function remapSelectedPointAcrossPackages(
  selectedPoint: WbvRenderPoint | null,
  currentPoints: WbvRenderPoint[],
  nextPoints: WbvRenderPoint[],
): WbvRenderPoint | null {
  if (!selectedPoint || currentPoints.length === 0 || nextPoints.length !== currentPoints.length) {
    return selectedPoint;
  }

  const selectedMd = selectedPoint.md;
  if (typeof selectedMd !== "number" || !Number.isFinite(selectedMd)) return selectedPoint;

  for (let index = 0; index < currentPoints.length - 1; index += 1) {
    const firstMd = currentPoints[index].md;
    const secondMd = currentPoints[index + 1].md;
    if (typeof firstMd !== "number" || !Number.isFinite(firstMd) || typeof secondMd !== "number" || !Number.isFinite(secondMd)) {
      continue;
    }
    const minMd = Math.min(firstMd, secondMd);
    const maxMd = Math.max(firstMd, secondMd);
    if (selectedMd < minMd || selectedMd > maxMd) continue;
    const denominator = secondMd - firstMd;
    const ratio = denominator === 0 ? 0 : Math.max(0, Math.min(1, (selectedMd - firstMd) / denominator));
    return interpolateRenderPointValue(nextPoints[index], nextPoints[index + 1], ratio);
  }

  const nearestIndex = currentPoints.reduce((bestIndex, point, index) => {
    const md = point.md;
    const bestMd = currentPoints[bestIndex]?.md;
    if (typeof md !== "number" || !Number.isFinite(md)) return bestIndex;
    if (typeof bestMd !== "number" || !Number.isFinite(bestMd)) return index;
    return Math.abs(md - selectedMd) < Math.abs(bestMd - selectedMd) ? index : bestIndex;
  }, 0);
  return nextPoints[nearestIndex] ?? selectedPoint;
}

function rangeFromBoundingBox(
  boundingBox: WbvBoundingBox | undefined,
  key: keyof WbvBoundingBox,
): NumericRange | null {
  const value = boundingBox?.[key];
  if (!value) return null;
  const min =
    typeof value.min === "number" && Number.isFinite(value.min)
      ? value.min
      : null;
  const max =
    typeof value.max === "number" && Number.isFinite(value.max)
      ? value.max
      : null;
  if (min === null && max === null) return null;
  return { min, max };
}


function firstLastPoint(points: WbvRenderPoint[]): {
  first: WbvRenderPoint | null;
  last: WbvRenderPoint | null;
} {
  return {
    first: points.length > 0 ? points[0] : null,
    last: points.length > 0 ? points[points.length - 1] : null,
  };
}

function isVerticalTrajectory(
  points: WbvRenderPoint[],
  trajectoryClass: string | null | undefined,
): boolean {
  if (trajectoryClass === "vertical_trajectory_candidate") return true;
  if (points.length === 0) return false;
  return points.every((point) => {
    const inclination = point.inclination ?? 0;
    const x = point.x ?? point.east_departure ?? 0;
    const y = point.y ?? point.north_departure ?? 0;
    return (
      Math.abs(inclination) < 1e-9 && Math.abs(x) < 1e-9 && Math.abs(y) < 1e-9
    );
  });
}


function selectionRecordFromDisplayedPackages(packages: Record<string, WbvDisplayedWellPackage>): Record<string, boolean> {
  const next: Record<string, boolean> = {};
  Object.keys(packages).forEach((managedWellId) => {
    next[managedWellId] = true;
  });
  return next;
}

function pendingSelectionMatchesDisplayed(
  selection: Record<string, boolean>,
  displayedPackages: Record<string, WbvDisplayedWellPackage>,
): boolean {
  const selectedIds = Object.keys(selection).filter((managedWellId) => selection[managedWellId]);
  const displayedIds = Object.keys(displayedPackages);
  return selectedIds.length === displayedIds.length && selectedIds.every((managedWellId) => Boolean(displayedPackages[managedWellId]));
}
export function Wellbore3DPage({
  onOpenLogViewer: _onOpenLogViewer,
  supplementalWellInfoMetadataByWell = {},
}: Wellbore3DPageProps) {
  const [state, setState] = useState<WbvLoadState>(initialState);
  const [wellSelectorItems, setWellSelectorItems] = useState<WbvWellSelectorItem[]>([]);
  const [wellSelectorLoading, setWellSelectorLoading] = useState(false);
  const [wellSelectorMessage, setWellSelectorMessage] = useState<string | null>(null);
  const [selectedUnavailableWellId, setSelectedUnavailableWellId] = useState<string | null>(null);
  const [displayedWellPackages, setDisplayedWellPackages] = useState<Record<string, WbvDisplayedWellPackage>>({});
  const [pendingDisplayedWellIds, setPendingDisplayedWellIds] = useState<Record<string, boolean>>({});
  const [prefetchedWellPackages, setPrefetchedWellPackages] = useState<Record<string, WbvDisplayedWellPackage>>({});
  const [loadingDisplayedWellIds, setLoadingDisplayedWellIds] = useState<Record<string, boolean>>({});
  const [wellSelectorOpen, setWellSelectorOpen] = useState(false);
  const [wbvSavedCanvases, setWbvSavedCanvases] = useState<SavedCanvasToolbarItem[]>([]);
  const [wbvSavedCanvasSaving, setWbvSavedCanvasSaving] = useState(false);
  const [wbvSavedCanvasBusyUid, setWbvSavedCanvasBusyUid] = useState<string | null>(null);
  const [wbvSavedCanvasError, setWbvSavedCanvasError] = useState<string | null>(null);
  const [layerEditorWellId, setLayerEditorWellId] = useState<string | null>(null);
  const [viewPropertiesByWell, setViewPropertiesByWell] = useState<Record<string, WbvViewProperties>>({});
  const [viewPreset, setViewPreset] = useState<WbvViewPreset>("fit");
  const [viewCommandId, setViewCommandId] = useState(0);
  const [viewAction, setViewAction] = useState<WbvViewAction | null>(null);
  const [viewActionId, setViewActionId] = useState(0);
  const initialNavigationCameraViewRef = useRef<WbvCameraViewState | null>(readWbvNavigationCameraView());
  const [zoomPercent, setZoomPercent] = useState(() => Math.round((initialNavigationCameraViewRef.current?.zoom ?? 1) * 100));
  const wbvCameraViewRef = useRef<WbvCameraViewState | null>(initialNavigationCameraViewRef.current ? structuredClone(initialNavigationCameraViewRef.current) : null);
  const [wbvCameraViewRestore, setWbvCameraViewRestore] = useState<WbvCameraViewState | null>(() => initialNavigationCameraViewRef.current ? structuredClone(initialNavigationCameraViewRef.current) : null);
  const [wbvCameraViewRestoreId, setWbvCameraViewRestoreId] = useState(() => initialNavigationCameraViewRef.current ? 1 : 0);
  const acceptWbvCameraView = useCallback((view: WbvCameraViewState) => {
    const captured = structuredClone(view);
    wbvCameraViewRef.current = captured;
    writeWbvNavigationCameraView(captured);
  }, []);
  const [rotationCenterActive, setRotationCenterActive] = useState(false);
  const [rotationCenterPickArmed, setRotationCenterPickArmed] = useState(false);
  const [horizontalRotationLocked, setHorizontalRotationLocked] = useState(false);
  const [verticalRotationLocked, setVerticalRotationLocked] = useState(false);
  const horizontalRotationHoldRef = useRef<{ delay: number | null; repeat: number | null; held: boolean }>({ delay: null, repeat: null, held: false });
  const verticalRotationHoldRef = useRef<{ delay: number | null; repeat: number | null; held: boolean }>({ delay: null, repeat: null, held: false });
  const [selectedPoint, setSelectedPoint] = useState<WbvRenderPoint | null>(null);
  const [interaction, setInteraction] = useState<WbvInteractionState | null>(null);
  const [interactionSaving, setInteractionSaving] = useState(false);
  const [interactionError, setInteractionError] = useState<string | null>(null);
  // A point projected by the live renderer is the authoritative presentation value.
  // Keep it pending while the backend records the observation so a resampled response
  // cannot visibly replace the exact MD selected by the user.
  const pendingExactSelectedPointRef = useRef<{ managedWellId: string; point: WbvRenderPoint } | null>(null);
  const interactionAuthorityRef = useRef<WbvInteractionCommandAuthority | null>(null);
  if (!interactionAuthorityRef.current) {
    interactionAuthorityRef.current = createWbvInteractionCommandAuthority({
      applyState: (next) => {
        setInteraction(next);
        const pendingExactPoint = pendingExactSelectedPointRef.current;
        if (pendingExactPoint && pendingExactPoint.managedWellId !== next.managed_well_id) {
          pendingExactSelectedPointRef.current = null;
        }
        setSelectedPoint(
          pendingExactPoint?.managedWellId === next.managed_well_id
            ? pendingExactPoint.point
            : next.selected_point ?? null,
        );
      },
      applyError: setInteractionError,
    });
  }
  const [trackValuesAlongWellbore, setTrackValuesAlongWellbore] = useState(false);
  const [depthUnitSaving, setDepthUnitSaving] = useState(false);
  const [viewerControls, setViewerControls] = useState<WbvViewerControls>(initialViewerControls);
  const [viewProperties, setViewProperties] = useState<WbvViewProperties>(defaultViewProperties);
  const [draftViewProperties, setDraftViewProperties] = useState<WbvViewProperties>(defaultViewProperties);
  const [selectedViewProperty, setSelectedViewProperty] = useState<keyof WbvViewProperties>("trajectory");
  const [displayLayers, setDisplayLayers] = useState<WbvDisplayLayerControls>({ trajectory: true });
  const [displayLayerFiles, setDisplayLayerFiles] = useState<WbvDisplayLayerFilesContract | null>(null);
  const [formationTopProducts, setFormationTopProducts] = useState<WbvFormationTopProductsContract | null>(null);
  const [lithologyProducts, setLithologyProducts] = useState<WbvLithologyProductsContract | null>(null);
  const [completionProducts, setCompletionProducts] = useState<WbvCompletionProductsContract | null>(null);
  const [coreRenderChunks, setCoreRenderChunks] = useState<WbvCoreRenderChunk[]>([]);
  const [coreInspectionInterval, setCoreInspectionInterval] = useState<WbvCoreInspectionInterval | null>(null);
  const [coreViewMode, setCoreViewMode] = useState(false);
  const [coreLocatorFocusInterval, setCoreLocatorFocusInterval] = useState<WbvCoreInspectionInterval | null>(null);
  const [coreModalOpen, setCoreModalOpen] = useState(false);
  const [coreModalChunkId, setCoreModalChunkId] = useState("");
  const [coreLatticeSide, setCoreLatticeSide] = useState<"off" | "left" | "right">("left");
  const [coreLatticeOffset, setCoreLatticeOffset] = useState(4);
  const [coreDescriptions, setCoreDescriptions] = useState<WbvCoreDescriptionItem[]>([]);
  const [coreDescriptionSide, setCoreDescriptionSide] = useState<"off" | "left" | "right">("off");
  const coreDescriptionSideTouchedRef = useRef(false);
  const [coreDescriptionFontSize, setCoreDescriptionFontSize] = useState(12);
  const [coreDescriptionPanelWidth, setCoreDescriptionPanelWidth] = useState(230);
  const [coreDescriptionOffset, setCoreDescriptionOffset] = useState(6);
  const [coreDescriptionShowMd, setCoreDescriptionShowMd] = useState(true);
  const [coreModalZoom, setCoreModalZoom] = useState(1);
  const [coreModalZoomLocked, setCoreModalZoomLocked] = useState(false);
  const [coreModalExpanded, setCoreModalExpanded] = useState(false);
  const [coreModalPosition, setCoreModalPosition] = useState<{ x: number; y: number } | null>(null);
  const [coreModalSize, setCoreModalSize] = useState<WbvCoreModalSize | null>(null);
  const coreModalWindowRef = useRef<HTMLElement | null>(null);
  const coreRecoveryHydratedRef = useRef(false);
  const coreRecoverySaveTimerRef = useRef<number | null>(null);
  const pendingCoreModalRecoveryRef = useRef<WbvCoreRestartRecoveryState | null>(null);
  const layerManagerRectRecoveredRef = useRef(false);
  const [coreModalDragging, setCoreModalDragging] = useState<{
    startX: number;
    startY: number;
    originX: number;
    originY: number;
  } | null>(null);
  const [coreModalResizing, setCoreModalResizing] = useState<{
    pointerId: number;
    corner: "top-right" | "bottom-right";
    startX: number;
    startY: number;
    originLeft: number;
    originTop: number;
    originWidth: number;
    originHeight: number;
  } | null>(null);
  const [coreModalTargetMd, setCoreModalTargetMd] = useState<number | null>(null);
  const coreModalViewportRef = useRef<HTMLDivElement | null>(null);
  const coreModalFocusRafRef = useRef<number | null>(null);
  const coreModalPanRef = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    scrollLeft: number;
    scrollTop: number;
  } | null>(null);
  const [layerEditorFormationTopProducts, setLayerEditorFormationTopProducts] = useState<WbvFormationTopProductsContract | null>(null);
  const [layerEditorLithologyProducts, setLayerEditorLithologyProducts] = useState<WbvLithologyProductsContract | null>(null);
  const [layerEditorCompletionProducts, setLayerEditorCompletionProducts] = useState<WbvCompletionProductsContract | null>(null);
  const [layerEditorDisplayLayerFiles, setLayerEditorDisplayLayerFiles] = useState<WbvDisplayLayerFilesContract | null>(null);
  const [, setLayerEditorCurveProducts] = useState<WbvCurveOverlayProductsContract | null>(null);
  const [layerEditorWellLoading, setLayerEditorWellLoading] = useState(false);
  const [, setSelectedDisplayLayerFiles] = useState<Partial<Record<WbvDisplayLayerKey, string>>>({});
  const [curveOverlayProducts, setCurveOverlayProducts] = useState<WbvCurveOverlayProductsContract | null>(null);
  const [, setSelectedCurveOverlayProductId] = useState("");
  const [, setSelectedCurveProductIds] = useState<string[]>([]);
  const [, setCurveOverlayNormalization] = useState<WbvCurveOverlayNormalizationContract | null>(null);
  const [curveOverlayRenderPackage, setCurveOverlayRenderPackage] = useState<WbvCurveOverlayRenderContract | null>(null);
  const [publishedOverlayPackages, setPublishedOverlayPackages] = useState<WbvOverlayPackage[]>([]);
  const [selectedPublishedPackageUid, setSelectedPublishedPackageUid] = useState<string | null>(null);
  const [publishedPresentationDraft, setPublishedPresentationDraft] = useState<WbvPresentationOverrides | null>(null);
  const [publishedPresentationSaving, setPublishedPresentationSaving] = useState(false);
  const [curveLabelEditorAssignmentUid, setCurveLabelEditorAssignmentUid] = useState<string | null>(null);
  const [publishedPackageView, setPublishedPackageView] = useState<"available" | "archived">("available");
  const [pendingPackageAction, setPendingPackageAction] = useState<"archive" | "delete" | null>(null);
  const [packageLifecycleError, setPackageLifecycleError] = useState<string | null>(null);
  const [wbvTrackLayout, setWbvTrackLayout] = useState<WbvTrackLayout | null>(null);
  const [selectedLayoutTrackUid, setSelectedLayoutTrackUid] = useState<string | null>(null);
  const [layoutCommandSaving, setLayoutCommandSaving] = useState(false);
  const [newLayoutTrackType, setNewLayoutTrackType] = useState<WbvLayoutTrack["track_type"]>("curve");
  const [layerManagerOpen, setLayerManagerOpen] = useState(false);
  const [layerManagerPoppedOut, setLayerManagerPoppedOut] = useState(true);
  const [activeLayerTab, setActiveLayerTab] = useState<WbvManagerTab>("curve_overlays");
  const [, setCurveSelectorSearch] = useState("");
  const [draftLayerConfigs, setDraftLayerConfigs] = useState<WbvLayerConfig[]>([]);
  const [appliedLayerConfigs, setAppliedLayerConfigs] = useState<WbvLayerConfig[]>([]);
  const [appliedTracks, setAppliedTracks] = useState<WbvTrackConfig[]>([]);
  const [draftTracks, setDraftTracks] = useState<WbvTrackConfig[]>([]);
  const [trackSpacing, setTrackSpacing] = useState(0.05);
  const [draftTrackSpacing, setDraftTrackSpacing] = useState(0.05);
  const [, setSelectedTrackId] = useState<string | null>(null);
  const [layerManagerSaving, setLayerManagerSaving] = useState(false);
  const [layerManagerApplyFlash, setLayerManagerApplyFlash] = useState(false);
  const layerManagerApplyFlashTimerRef = useRef<number | null>(null);
  useEffect(() => () => {
    if (layerManagerApplyFlashTimerRef.current !== null) window.clearTimeout(layerManagerApplyFlashTimerRef.current);
  }, []);
  useEffect(() => () => {
    if (coreRecoverySaveTimerRef.current !== null) window.clearTimeout(coreRecoverySaveTimerRef.current);
  }, []);

  // WBV_MANAGE_DISPLAY_LAYERS_APPLY_ACKNOWLEDGEMENT_V1_0_0

  const [, setSelectedCurveForEditing] = useState<string | null>(null);
  const [layerManagerExpanded, setLayerManagerExpanded] = useState(false);
  const [layerManagerRect, setLayerManagerRect] = useState<WbvManagerRect>({ left: 180, top: 110, width: 1120, height: 760 });
  const [layerManagerRestoreRect, setLayerManagerRestoreRect] = useState<WbvManagerRect | null>(null);
  const layerManagerRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    setRotationCenterActive(false);
    setRotationCenterPickArmed(false);
    setHorizontalRotationLocked(false);
    setVerticalRotationLocked(false);
    clearHorizontalRotationHold();
    clearVerticalRotationHold();
  }, [state.session?.active_managed_well_uid]);

  const selectedPublishedPackage = publishedOverlayPackages.find(
    (item) => item.package_uid === selectedPublishedPackageUid,
  ) ?? null;

  // Keep renderer lifecycle inputs referentially stable while selected-point
  // interaction state changes. A new filtered array on every page render was
  // retriggering the Three.js construction effect for every tracking update.
  const depthTrackRenderLayout = useMemo(
    () => (wbvTrackLayout?.tracks ?? []).filter(
      (track): track is WbvLayoutTrack & { track_type: "depth" } => track.track_type === "depth",
    ),
    [wbvTrackLayout?.tracks],
  );

  const coreTrackRenderLayout = useMemo(
    () => (wbvTrackLayout?.tracks ?? []).filter(
      (track): track is WbvLayoutTrack & { track_type: "core" } => track.track_type === "core",
    ) as unknown as WbvCoreTrack[],
    [wbvTrackLayout?.tracks],
  );

  const trackPlacementRenderLayout = useMemo<WbvTrackPlacementTrack[]>(
    () => (wbvTrackLayout?.tracks ?? []).map((track) => ({ track_uid: track.track_uid, track_type: track.track_type, display_order: track.display_order, visible: track.visible, position: track.position, distance_from_wellbore: track.distance_from_wellbore, previous_track_gap: track.previous_track_gap, width: track.width })),
    [wbvTrackLayout?.tracks],
  );

  useEffect(() => {
    setPublishedPresentationDraft(
      selectedPublishedPackage ? structuredClone(selectedPublishedPackage.wbv_overrides) : null,
    );
  }, [selectedPublishedPackage]);

  const refreshPublishedPackages = useCallback(async (managedWellId: string, preferredUid?: string) => {
    const response = await listWbvOverlayPackages(managedWellId);
    setPublishedOverlayPackages(response.packages);
    setSelectedPublishedPackageUid((current) => {
      if (preferredUid && response.packages.some((item) => item.package_uid === preferredUid)) return preferredUid;
      if (current && response.packages.some((item) => item.package_uid === current)) return current;
      return response.packages.find((item) => item.status === "active")?.package_uid ?? response.packages[0]?.package_uid ?? null;
    });
  }, []);

  const runLayoutCommand = async (command: Omit<WbvLayoutCommand, "expected_revision">) => {
    const managedWellUid = state.session?.active_managed_well_uid;
    if (!managedWellUid || !wbvTrackLayout) return;
    setLayoutCommandSaving(true);
    try {
      const saved = await commandWbvTrackLayout(managedWellUid, { ...command, expected_revision: wbvTrackLayout.revision });
      setWbvTrackLayout(saved);
      setSelectedLayoutTrackUid((current) => current && saved.tracks.some((track) => track.track_uid === current) ? current : saved.tracks[0]?.track_uid ?? null);
      const activePackage = publishedOverlayPackages.find((item) => item.status === "active");
      if (activePackage) setCurveOverlayRenderPackage(await fetchWlvJson<WbvCurveOverlayRenderContract>(publishedWbvRenderPackageUrl(managedWellUid, activePackage.package_uid)));
    } finally { setLayoutCommandSaving(false); }
  };

  const activatePublishedPackage = async (packageUid: string) => {
    const managedWellUid = state.session?.active_managed_well_uid;
    if (!managedWellUid) return;
    setPublishedPresentationSaving(true);
    try {
      await setWbvOverlayPackageActive(managedWellUid, packageUid, true);
      await refreshPublishedPackages(managedWellUid, packageUid);
      const nextRenderPackage = await fetchWlvJson<WbvCurveOverlayRenderContract>(
        publishedWbvRenderPackageUrl(managedWellUid, packageUid),
      );
      setCurveOverlayRenderPackage(nextRenderPackage);
      const activeManagedWellId = state.viewerPackage?.managed_well_id;
      if (activeManagedWellId) {
        setDisplayedWellPackages((current) => {
          const existing = current[activeManagedWellId];
          if (!existing) return current;
          return {
            ...current,
            [activeManagedWellId]: {
              ...existing,
              layers: { ...existing.layers, curveRenderPackage: nextRenderPackage },
            },
          };
        });
      }
    } finally {
      setPublishedPresentationSaving(false);
    }
  };

  const changePublishedPackageLifecycle = async (
    packageItem: WbvOverlayPackage,
    action: "archive" | "restore",
  ) => {
    const managedWellUid = state.session?.active_managed_well_uid;
    if (!managedWellUid) return;
    setPublishedPresentationSaving(true);
    setPackageLifecycleError(null);
    try {
      const saved = await changeWbvOverlayPackageLifecycle(
        managedWellUid,
        packageItem.package_uid,
        packageItem.package_revision,
        action,
      );
      await refreshPublishedPackages(managedWellUid, saved.package_uid);
      if (action === "archive") {
        if (packageItem.status === "active") setCurveOverlayRenderPackage(null);
        setPublishedPackageView("archived");
      } else {
        setPublishedPackageView("available");
      }
      setPendingPackageAction(null);
    } catch (caught) {
      setPackageLifecycleError(caught instanceof Error ? caught.message : "Unable to update the package.");
    } finally {
      setPublishedPresentationSaving(false);
    }
  };

  const deletePublishedPackage = async (packageItem: WbvOverlayPackage) => {
    const managedWellUid = state.session?.active_managed_well_uid;
    if (!managedWellUid) return;
    setPublishedPresentationSaving(true);
    setPackageLifecycleError(null);
    try {
      await deleteWbvOverlayPackage(
        managedWellUid,
        packageItem.package_uid,
        packageItem.package_revision,
      );
      setPublishedOverlayPackages((current) =>
        current.filter((item) => item.package_uid !== packageItem.package_uid),
      );
      setSelectedPublishedPackageUid((current) =>
        current === packageItem.package_uid ? null : current,
      );
      if (packageItem.status === "active") setCurveOverlayRenderPackage(null);
      setPendingPackageAction(null);
      await refreshPublishedPackages(managedWellUid);
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "Unable to delete the package.";
      if (message.startsWith("404 Not Found:")) {
        setPublishedOverlayPackages((current) =>
          current.filter((item) => item.package_uid !== packageItem.package_uid),
        );
        setSelectedPublishedPackageUid((current) =>
          current === packageItem.package_uid ? null : current,
        );
        if (packageItem.status === "active") setCurveOverlayRenderPackage(null);
        setPendingPackageAction(null);
        await refreshPublishedPackages(managedWellUid);
      } else {
        setPackageLifecycleError(message);
      }
    } finally {
      setPublishedPresentationSaving(false);
    }
  };

  const savePublishedPresentation = async () => {
    const managedWellUid = state.session?.active_managed_well_uid;
    if (!managedWellUid || !selectedPublishedPackage || !publishedPresentationDraft) return;
    setPublishedPresentationSaving(true);
    try {
      const saved = await updateWbvPresentationOverrides(
        managedWellUid,
        selectedPublishedPackage.package_uid,
        selectedPublishedPackage.package_revision,
        publishedPresentationDraft,
      );

      // The presentation PUT response is the committed package authority. Install it
      // locally immediately instead of round-tripping through the package-list GET,
      // which can otherwise rehydrate an older package revision before modal close.
      setPublishedOverlayPackages((current) => {
        const found = current.some((item) => item.package_uid === saved.package_uid);
        return found
          ? current.map((item) => item.package_uid === saved.package_uid ? saved : item)
          : [...current, saved];
      });
      setSelectedPublishedPackageUid(saved.package_uid);
      setPublishedPresentationDraft(structuredClone(saved.wbv_overrides));

      if (saved.status === "active") {
        // Render-package URL is revision-qualified and explicitly no-store so draft
        // preview can hand authority back to the newly committed render package
        // without a stale browser-cached GET restoring the previous presentation.
        const committedRenderPackage = await fetchWlvJson<WbvCurveOverlayRenderContract>(
          `${publishedWbvRenderPackageUrl(managedWellUid, saved.package_uid)}?package_revision=${encodeURIComponent(String(saved.package_revision))}`,
          { cache: "no-store" },
        );
        setCurveOverlayRenderPackage(committedRenderPackage);

        const activeManagedWellId = state.viewerPackage?.managed_well_id;
        if (activeManagedWellId) {
          setDisplayedWellPackages((current) => {
            const existing = current[activeManagedWellId];
            if (!existing) return current;
            return {
              ...current,
              [activeManagedWellId]: {
                ...existing,
                layers: {
                  ...existing.layers,
                  curveRenderPackage: committedRenderPackage,
                },
              },
            };
          });
        }
      }
    } finally {
      setPublishedPresentationSaving(false);
    }
  };

  const clearHorizontalRotationHold = () => {
    const hold = horizontalRotationHoldRef.current;
    if (hold.delay !== null) window.clearTimeout(hold.delay);
    if (hold.repeat !== null) window.clearInterval(hold.repeat);
    hold.delay = null;
    hold.repeat = null;
    hold.held = false;
  };

  const beginHorizontalRotationHold = (
    direction: "negative" | "positive",
    event: ReactPointerEvent<HTMLButtonElement>,
  ) => {
    if (!horizontalRotationLocked || !hasTrajectory) return;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    clearHorizontalRotationHold();
    const hold = horizontalRotationHoldRef.current;
    hold.held = false;
    hold.delay = window.setTimeout(() => {
      hold.held = true;
      requestViewAction(direction === "negative" ? "horizontal-rotate-negative" : "horizontal-rotate-positive");
      hold.repeat = window.setInterval(() => {
        requestViewAction(direction === "negative" ? "horizontal-rotate-negative" : "horizontal-rotate-positive");
      }, 24);
    }, 280);
  };

  const endHorizontalRotationHold = (
    direction: "negative" | "positive",
  ) => {
    const wasHeld = horizontalRotationHoldRef.current.held;
    clearHorizontalRotationHold();
    if (!wasHeld && horizontalRotationLocked && hasTrajectory) {
      requestViewAction(direction === "negative" ? "horizontal-rotate-negative" : "horizontal-rotate-positive");
    }
  };

  const clearVerticalRotationHold = () => {
    const hold = verticalRotationHoldRef.current;
    if (hold.delay !== null) window.clearTimeout(hold.delay);
    if (hold.repeat !== null) window.clearInterval(hold.repeat);
    hold.delay = null;
    hold.repeat = null;
    hold.held = false;
  };

  const beginVerticalRotationHold = (
    direction: "negative" | "positive",
    event: ReactPointerEvent<HTMLButtonElement>,
  ) => {
    if (!verticalRotationLocked || !hasTrajectory) return;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    clearVerticalRotationHold();
    const hold = verticalRotationHoldRef.current;
    hold.held = false;
    hold.delay = window.setTimeout(() => {
      hold.held = true;
      requestViewAction(direction === "negative" ? "vertical-rotate-negative" : "vertical-rotate-positive");
      hold.repeat = window.setInterval(() => {
        requestViewAction(direction === "negative" ? "vertical-rotate-negative" : "vertical-rotate-positive");
      }, 24);
    }, 280);
  };

  const endVerticalRotationHold = (
    direction: "negative" | "positive",
  ) => {
    const wasHeld = verticalRotationHoldRef.current.held;
    clearVerticalRotationHold();
    if (!wasHeld && verticalRotationLocked && hasTrajectory) {
      requestViewAction(direction === "negative" ? "vertical-rotate-negative" : "vertical-rotate-positive");
    }
  };

  const requestViewPreset = (preset: WbvViewPreset) => {
    setRotationCenterActive(false);
    setRotationCenterPickArmed(false);
    setCoreInspectionInterval(null);
    setViewPreset(preset);
    setViewCommandId((current) => current + 1);
  };

  const requestViewAction = (action: WbvViewAction) => {
    if (action === "fit-selection") setCoreInspectionInterval(null);
    if (action === "reset-rotation-center" || action === "fit-selection" || action === "fit-core") {
      setRotationCenterActive(false);
      setRotationCenterPickArmed(false);
    }
    setViewAction(action);
    setViewActionId((current) => current + 1);
  };

  const handleRotationCenterButton = () => {
    if (rotationCenterActive) {
      setRotationCenterPickArmed(false);
      requestViewAction("reset-rotation-center");
      return;
    }
    setRotationCenterPickArmed(true);
  };

  const handleRotationCenterEstablished = useCallback((_point: WbvRenderPoint) => {
    setRotationCenterPickArmed(false);
    setRotationCenterActive(true);
  }, []);

  const loadWellSelectorItems = useCallback(async () => {
    setWellSelectorLoading(true);
    try {
      const [wells, workspace] = await Promise.all([
        fetchWlvJson<ManagedWellSummary[]>("/api/wlv/inventory/wells"),
        fetchWlvJson<WdvWorkspaceSummary>("/api/wlv/inventory/wdv-workspace"),
      ]);
      const loadedIds = new Set((workspace.loaded_wells ?? []).map((item) => item.managed_well_id));
      const packages = await Promise.all(wells.map(async (well) => {
        try {
          return await fetchWlvJson<WbvViewerPackageContract>(`/api/wlv/wbv/wells/${encodeURIComponent(well.managed_well_id)}/viewer-package`);
        } catch {
          return null;
        }
      }));
      setWellSelectorItems(wells.map((well, index): WbvWellSelectorItem => {
        const viewerPackage = packages[index];
        const viewerState = viewerPackage?.viewer_state ?? "unavailable";
        const trajectory = viewerPackage?.trajectory;
        const resolvedTrajectoryPointCount = Math.max(
          trajectory?.render_points?.length ?? 0,
          trajectory?.station_count ?? 0,
          trajectory?.source_station_count ?? 0,
        );
        const hasResolvedTrajectory = resolvedTrajectoryPointCount > 1;
        return {
          managedWellId: well.managed_well_id,
          wellName: well.well_name,
          viewerState,
          hasSurvey:
            hasResolvedTrajectory ||
            !["not_loaded", "missing_survey", "unavailable"].includes(viewerState),
          loadedInWdv: loadedIds.has(well.managed_well_id),
          activeInWdv: workspace.active_managed_well_id === well.managed_well_id,
        };
      }).sort((a, b) => a.wellName.localeCompare(b.wellName)));
    } catch (caught) {
      setWellSelectorMessage(caught instanceof Error ? caught.message : "Unable to load managed wells.");
    } finally {
      setWellSelectorLoading(false);
    }
  }, []);

  useEffect(() => {
    if (wellSelectorOpen) return;
    setPendingDisplayedWellIds(selectionRecordFromDisplayedPackages(displayedWellPackages));
  }, [displayedWellPackages, wellSelectorOpen]);

  const loadWbvSession = useCallback(async () => {
    setState((current) => ({ ...current, loading: true, error: null }));
    try {
      const session = await fetchWlvJson<WbvSessionContract>(
        "/api/wlv/wbv/session",
      );
      // The backend-owned WBV session is independent; WDV is only its initial default and synchronization peer.
      const managedWellId = session.active_managed_well_id;
      const managedWellUid = session.active_managed_well_uid;
      const viewerPackage = managedWellId
        ? await fetchWlvJson<WbvViewerPackageContract>(
            `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/viewer-package`,
          )
        : null;
      const nextDisplayLayerFiles = managedWellId
        ? await fetchWlvJson<WbvDisplayLayerFilesContract>(
            `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/display-layer-files`,
          )
        : null;
      const nextFormationTopProducts = managedWellId
        ? await fetchWlvJson<WbvFormationTopProductsContract>(
            `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/formation-top-products`,
          )
        : null;
      const nextLithologyProducts = managedWellId
        ? await fetchWlvJson<WbvLithologyProductsContract>(
            `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/lithology-products`,
          )
        : null;
      const nextCompletionProducts = managedWellId
        ? await fetchWlvJson<WbvCompletionProductsContract>(
            `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/completion-products`,
          )
        : null;
      const nextCurveOverlayProducts = managedWellId
        ? await fetchWlvJson<WbvCurveOverlayProductsContract>(
            `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/curve-overlay-products`,
          )
        : null;
      const nextLayerConfiguration = managedWellId
        ? await fetchWlvJson<WbvDisplayLayerConfigurationContract>(
            `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/display-layer-configuration`,
          )
        : null;
      const nextPublishedPackages = managedWellUid
        ? await listWbvOverlayPackages(managedWellUid)
        : null;
      const nextWbvTrackLayout = managedWellUid ? await getWbvTrackLayout(managedWellUid) : null;
      setWbvTrackLayout(nextWbvTrackLayout);
      setSelectedLayoutTrackUid((current) => current && nextWbvTrackLayout?.tracks.some((track) => track.track_uid === current) ? current : nextWbvTrackLayout?.tracks[0]?.track_uid ?? null);
      const activePublishedPackage = nextPublishedPackages?.packages.find((item) => item.status === "active") ?? null;
      const packageItems = nextPublishedPackages?.packages ?? [];
      setPublishedOverlayPackages(packageItems);
      setSelectedPublishedPackageUid((current) => {
        if (current && packageItems.some((item) => item.package_uid === current)) return current;
        return packageItems.find((item) => item.status === "active")?.package_uid ?? packageItems[0]?.package_uid ?? null;
      });
      const nextCurveOverlayRenderPackage =
        managedWellUid && activePublishedPackage
          ? await fetchWlvJson<WbvCurveOverlayRenderContract>(
              publishedWbvRenderPackageUrl(
                managedWellUid,
                activePublishedPackage.package_uid,
              ),
            )
          : null;
      const nextInteraction = managedWellId
        ? await wbvInteractionApiV2.get(managedWellId)
        : null;
      if (managedWellId) {
        const legacyContracts = [
          viewerPackage,
          nextDisplayLayerFiles,
          nextFormationTopProducts,
          nextLithologyProducts,
          nextCompletionProducts,
          nextCurveOverlayProducts,
          nextLayerConfiguration,
        ];
        legacyContracts.forEach((contract) => {
          if (contract && contract.managed_well_id !== managedWellId) {
            throw new Error("WBV rejected mixed legacy managed-well contracts from the backend.");
          }
        });
      }
      if (nextCurveOverlayRenderPackage) {
        const expectedRenderWellIdentity = activePublishedPackage ? managedWellUid : managedWellId;
        if (
          expectedRenderWellIdentity
          && nextCurveOverlayRenderPackage.managed_well_id !== expectedRenderWellIdentity
        ) {
          throw new Error("WBV rejected a curve-overlay render contract for another managed well.");
        }
      }
      setCurveOverlayRenderPackage(nextCurveOverlayRenderPackage);
      interactionAuthorityRef.current?.seed(nextInteraction);
      const loadedLayerConfigs = nextLayerConfiguration?.layers ?? [];
      const hasVisibleDepthTrack = Boolean(
        nextWbvTrackLayout?.tracks.some((track) => track.track_type === "depth" && track.visible),
      );
      setAppliedLayerConfigs((current) => {
        if (!hasVisibleDepthTrack) return loadedLayerConfigs;
        const currentCurveVisibility = current.find((item) => item.layer_type === "curve_overlays")?.visible;
        const loadedCurveIndex = loadedLayerConfigs.findIndex((item) => item.layer_type === "curve_overlays");
        if (loadedCurveIndex >= 0) {
          return loadedLayerConfigs.map((item, index) => index !== loadedCurveIndex ? item : {
            ...item,
            visible: currentCurveVisibility ?? (item.selected_item_ids.length > 0 || Boolean(item.source_product_id) ? item.visible : true),
          });
        }
        return [
          ...loadedLayerConfigs,
          {
            layer_type: "curve_overlays",
            visible: currentCurveVisibility ?? true,
            selected_item_ids: [],
            source_type: "wmd",
            source_product_id: null,
            scale: { mode: "backend_default", minimum: null, maximum: null, scale_type: "linear", direction: "normal" },
            appearance: { color: null, opacity: 1, line_width: 1, display_mode: "line", show_labels: true, marker_style: "ring", marker_size: 1, color_mode: "formation", label_mode: "name_md", label_size: 1, label_offset: 1, label_position: "right", selected_top_ids: null, selected_interval_ids: null, selected_component_ids: null, label_color: null, brightness: 1.35, pattern_scale: 1.5, hide_underlay: false },
            curve_settings: [],
          },
        ];
      });
      setAppliedTracks(nextLayerConfiguration?.tracks ?? []);
      setTrackSpacing(nextLayerConfiguration?.track_spacing ?? 0.05);
      setCurveOverlayProducts(nextCurveOverlayProducts);
      setSelectedCurveOverlayProductId((current) =>
        nextCurveOverlayProducts?.products.some((product) => product.curve_product_id === current)
          ? current
          : nextCurveOverlayProducts?.products.length === 1
            ? nextCurveOverlayProducts.products[0].curve_product_id
            : "",
      );
      setSelectedCurveProductIds((current) => {
        const valid = new Set(
          nextCurveOverlayProducts?.products.flatMap((product) => product.curves.map((curve) => curve.curve_product_id)) ?? [],
        );
        return current.filter((curveId) => valid.has(curveId));
      });
      setDisplayLayerFiles(nextDisplayLayerFiles);
      setFormationTopProducts(nextFormationTopProducts);
      setLithologyProducts(nextLithologyProducts);
      setCompletionProducts(nextCompletionProducts);
      setSelectedDisplayLayerFiles((current) => {
        const next: Partial<Record<WbvDisplayLayerKey, string>> = {};
        if (!nextDisplayLayerFiles) return next;
        (Object.keys(nextDisplayLayerFiles.layers) as WbvDisplayLayerKey[]).forEach((key) => {
          const files = nextDisplayLayerFiles.layers[key] ?? [];
          if (files.some((file) => file.product_id === current[key])) {
            next[key] = current[key];
          } else if (files.length === 1) {
            next[key] = files[0].product_id;
          }
        });
        return next;
      });
      setState({ session, viewerPackage, loading: false, error: null });
      if (managedWellId && viewerPackage) {
        const name = viewerPackage.well_name?.trim() || managedWellId;
        setDisplayedWellPackages((current) => ({
          ...current,
          [managedWellId]: {
            managedWellId,
            wellName: name,
            viewerPackage,
            layers: {
              files: nextDisplayLayerFiles,
              configuration: nextLayerConfiguration,
              formationTops: nextFormationTopProducts,
              lithologyProducts: nextLithologyProducts,
              completionProducts: nextCompletionProducts,
              curveProducts: nextCurveOverlayProducts,
              curveRenderPackage: nextCurveOverlayRenderPackage,
            },
          },
        }));
        setLayerEditorWellId((current) => current ?? managedWellId);
      }
    } catch (caught) {
      setDisplayLayerFiles(null);
      setFormationTopProducts(null);
      setLithologyProducts(null);
      setCompletionProducts(null);
      setCurveOverlayProducts(null);
      setCurveOverlayNormalization(null);
      setCurveOverlayRenderPackage(null);
      setState({
        session: null,
        viewerPackage: null,
        loading: false,
        error:
          caught instanceof Error
            ? caught.message
            : "Unable to load WBV session",
      });
    }
  }, []);

  const selectWbvWell = useCallback(async (managedWellId: string) => {
    if (!managedWellId) return;
    const item = wellSelectorItems.find((candidate) => candidate.managedWellId === managedWellId);
    if (!item) return;
    setWellSelectorMessage(null);
    if (!item.hasSurvey) {
      setSelectedUnavailableWellId(managedWellId);
      setSelectedPoint(null);
      setInteraction(null);
      return;
    }
    setSelectedUnavailableWellId(null);
    const outgoingActiveWellId = state.session?.active_managed_well_id ?? null;
    const switchingWell = outgoingActiveWellId !== managedWellId;
    if (switchingWell) {
      // Changing active well transfers standard WBV control focus only.
      // Preserve the outgoing well's local presentation before focus moves.
      if (outgoingActiveWellId) {
        const outgoingViewProperties = structuredClone(viewProperties);
        setViewPropertiesByWell((current) => ({
          ...current,
          [outgoingActiveWellId]: outgoingViewProperties,
        }));
      }
      pendingExactSelectedPointRef.current = null;
      setSelectedPoint(null);
      setInteraction(null);
    }
    try {
      // Selecting an unavailable inventory well does not change the backend WBV session.
      // When the operator returns to the well already active in that session, simply
      // restore it; do not PUT the same active well again and provoke a false 422.
      if (state.session?.active_managed_well_id !== managedWellId) {
        await fetchWlvJson<WbvSessionContract>("/api/wlv/wbv/session/active-well", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ managed_well_id: managedWellId }),
        });
      }
      await loadWbvSession();
      await loadWellSelectorItems();
      if (switchingWell) {
        const incomingViewProperties = viewPropertiesByWell[managedWellId] ?? defaultViewProperties;
        setViewProperties(structuredClone(incomingViewProperties));
      }
    } catch (caught) {
      setWellSelectorMessage(caught instanceof Error ? caught.message : "Unable to select well.");
    }
  }, [
    wellSelectorItems,
    loadWbvSession,
    loadWellSelectorItems,
    state.session?.active_managed_well_id,
    viewProperties,
    viewPropertiesByWell,
  ]);

  const prefetchDisplayedWellPackage = useCallback(async (managedWellId: string) => {
    if (displayedWellPackages[managedWellId] || prefetchedWellPackages[managedWellId] || loadingDisplayedWellIds[managedWellId]) return;
    const item = wellSelectorItems.find((candidate) => candidate.managedWellId === managedWellId);
    if (!item?.hasSurvey) return;
    setLoadingDisplayedWellIds((current) => ({ ...current, [managedWellId]: true }));
    try {
      const [
        viewerPackage,
        displayLayerFilesForWell,
        formationTopProductsForWell,
        lithologyProductsForWell,
        completionProductsForWell,
        curveProductsForWell,
        displayLayerConfigurationForWell,
        curveRenderPackageForWell,
      ] = await Promise.all([
        fetchWlvJson<WbvViewerPackageContract>(
          `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/viewer-package`,
        ),
        fetchWlvJson<WbvDisplayLayerFilesContract>(
          `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/display-layer-files`,
        ),
        fetchWlvJson<WbvFormationTopProductsContract>(
          `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/formation-top-products`,
        ),
        fetchWlvJson<WbvLithologyProductsContract>(
          `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/lithology-products`,
        ),
        fetchWlvJson<WbvCompletionProductsContract>(
          `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/completion-products`,
        ),
        fetchWlvJson<WbvCurveOverlayProductsContract>(
          `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/curve-overlay-products`,
        ),
        fetchWlvJson<WbvDisplayLayerConfigurationContract>(
          `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/display-layer-configuration`,
        ),
        fetchWlvJson<WbvCurveOverlayRenderContract>(
          `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/curve-overlays/render-package`,
        ).catch(() => null),
      ]);
      setPrefetchedWellPackages((current) => ({
        ...current,
        [managedWellId]: {
          managedWellId,
          wellName: item.wellName,
          viewerPackage,
          layers: {
            files: displayLayerFilesForWell,
            configuration: displayLayerConfigurationForWell,
            formationTops: formationTopProductsForWell,
            lithologyProducts: lithologyProductsForWell,
            completionProducts: completionProductsForWell,
            curveProducts: curveProductsForWell,
            curveRenderPackage: curveRenderPackageForWell,
          },
        },
      }));
    } catch (caught) {
      setWellSelectorMessage(caught instanceof Error ? caught.message : "Unable to prepare selected well.");
    } finally {
      setLoadingDisplayedWellIds((current) => {
        const next = { ...current };
        delete next[managedWellId];
        return next;
      });
    }
  }, [displayedWellPackages, loadingDisplayedWellIds, prefetchedWellPackages, wellSelectorItems]);

  const togglePendingDisplayedWell = useCallback((managedWellId: string, checked: boolean) => {
    const item = wellSelectorItems.find((candidate) => candidate.managedWellId === managedWellId);
    if (!item?.hasSurvey) return;
    setPendingDisplayedWellIds((current) => {
      const next = { ...current };
      if (checked) next[managedWellId] = true;
      else delete next[managedWellId];
      return next;
    });
    if (checked) void prefetchDisplayedWellPackage(managedWellId);
  }, [prefetchDisplayedWellPackage, wellSelectorItems]);

  const applyDisplayedWellSelection = useCallback(async () => {
    const targetIds = Object.keys(pendingDisplayedWellIds).filter((managedWellId) => pendingDisplayedWellIds[managedWellId]);
    if (targetIds.length === 0) {
      setWellSelectorMessage("Select at least one qualified well to display.");
      return;
    }
    setWellSelectorMessage(null);
    setWellSelectorOpen(false);

    const retainedPackages: Record<string, WbvDisplayedWellPackage> = {};
    targetIds.forEach((managedWellId) => {
      const available = displayedWellPackages[managedWellId] ?? prefetchedWellPackages[managedWellId];
      if (available) retainedPackages[managedWellId] = available;
    });
    setDisplayedWellPackages(retainedPackages);

    const nextActiveWellId = targetIds.includes(state.session?.active_managed_well_id ?? "")
      ? (state.session?.active_managed_well_id ?? null)
      : targetIds[0] ?? null;
    setLayerEditorWellId((current) => {
      if (current && targetIds.includes(current)) return current;
      return nextActiveWellId;
    });
    if (nextActiveWellId && nextActiveWellId !== state.session?.active_managed_well_id) {
      void selectWbvWell(nextActiveWellId);
    }

    const missingIds = targetIds.filter((managedWellId) => !retainedPackages[managedWellId]);
    if (missingIds.length > 0) {
      setWellSelectorMessage(`Loading ${missingIds.length} selected well${missingIds.length === 1 ? "" : "s"}…`);
      await Promise.allSettled(
        missingIds.map(async (managedWellId) => {
          const item = wellSelectorItems.find((candidate) => candidate.managedWellId === managedWellId);
          if (!item?.hasSurvey) return;
          setLoadingDisplayedWellIds((current) => ({ ...current, [managedWellId]: true }));
          try {
            const [
              viewerPackage,
              displayLayerFilesForWell,
              formationTopProductsForWell,
              lithologyProductsForWell,
              completionProductsForWell,
              curveProductsForWell,
              displayLayerConfigurationForWell,
              curveRenderPackageForWell,
            ] = await Promise.all([
              fetchWlvJson<WbvViewerPackageContract>(
                `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/viewer-package`,
              ),
              fetchWlvJson<WbvDisplayLayerFilesContract>(
                `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/display-layer-files`,
              ),
              fetchWlvJson<WbvFormationTopProductsContract>(
                `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/formation-top-products`,
              ),
              fetchWlvJson<WbvLithologyProductsContract>(
                `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/lithology-products`,
              ),
              fetchWlvJson<WbvCompletionProductsContract>(
                `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/completion-products`,
              ),
              fetchWlvJson<WbvCurveOverlayProductsContract>(
                `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/curve-overlay-products`,
              ),
              fetchWlvJson<WbvDisplayLayerConfigurationContract>(
                `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/display-layer-configuration`,
              ),
              fetchWlvJson<WbvCurveOverlayRenderContract>(
                `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/curve-overlays/render-package`,
              ).catch(() => null),
            ]);
            const entry = {
              managedWellId,
              wellName: item.wellName,
              viewerPackage,
              layers: {
                files: displayLayerFilesForWell,
                configuration: displayLayerConfigurationForWell,
                formationTops: formationTopProductsForWell,
                lithologyProducts: lithologyProductsForWell,
                completionProducts: completionProductsForWell,
                curveProducts: curveProductsForWell,
                curveRenderPackage: curveRenderPackageForWell,
              },
            } satisfies WbvDisplayedWellPackage;
            setPrefetchedWellPackages((current) => ({ ...current, [managedWellId]: entry }));
            setDisplayedWellPackages((current) => ({ ...current, [managedWellId]: entry }));
          } finally {
            setLoadingDisplayedWellIds((current) => {
              const next = { ...current };
              delete next[managedWellId];
              return next;
            });
          }
        }),
      );
    }
    setWellSelectorMessage(null);
  }, [displayedWellPackages, pendingDisplayedWellIds, prefetchedWellPackages, selectWbvWell, state.session?.active_managed_well_id, wellSelectorItems]);

  const setSelectionMode = async (mode: "none" | "point" | "interval") => {
    if (mode !== "point") pendingExactSelectedPointRef.current = null;
    const managedWellId = layerEditorWellId ?? state.viewerPackage?.managed_well_id;
    if (!managedWellId) return;
    setInteractionSaving(true);
    try {
      await interactionAuthorityRef.current?.runRevisioned((expectedRevision) =>
        wbvInteractionApiV2.setMode(managedWellId, mode, expectedRevision),
      );
    } finally {
      setInteractionSaving(false);
    }
  };

  const acceptExactLocalSelectedPoint = useCallback((point: WbvRenderPoint) => {
    const managedWellId = state.viewerPackage?.managed_well_id;
    if (!managedWellId) return;
    pendingExactSelectedPointRef.current = { managedWellId, point };
    setSelectedPoint(point);
  }, [state.viewerPackage?.managed_well_id]);

  const handleInteractionCommand = async (command: {
    kind: "observe" | "track-start" | "track-update" | "track-commit" | "track-cancel";
    observation?: WbvScreenObservationV2;
    sessionId?: string;
    sequence: number;
    exactLocalPoint?: WbvRenderPoint;
  }) => {
    const managedWellId = state.viewerPackage?.managed_well_id;
    const authority = interactionAuthorityRef.current;
    if (!managedWellId || !authority) return null;
    if (command.kind === "observe" && command.observation) {
      if (command.exactLocalPoint) {
        pendingExactSelectedPointRef.current = { managedWellId, point: command.exactLocalPoint };
        setSelectedPoint(command.exactLocalPoint);
      } else {
        pendingExactSelectedPointRef.current = null;
      }
      return authority.runRevisioned((expectedRevision) => wbvInteractionApiV2.observe(managedWellId, {
        observation: command.observation!, expected_revision: expectedRevision,
      }));
    }
    if (command.kind === "track-start" && command.observation) {
      return authority.runRevisioned((expectedRevision) => wbvInteractionApiV2.startTracking(managedWellId, {
        sequence: command.sequence, observation: command.observation!, expected_revision: expectedRevision,
      }));
    }
    if (command.kind === "track-update" && command.observation && command.sessionId) {
      return authority.runSession(() => wbvInteractionApiV2.updateTracking(managedWellId, {
        session_id: command.sessionId, sequence: command.sequence, observation: command.observation!,
      }));
    }
    if (command.kind === "track-commit" && command.sessionId) {
      return authority.runSession(() => wbvInteractionApiV2.commitTracking(managedWellId, {
        session_id: command.sessionId, sequence: command.sequence, observation: command.observation,
      }));
    }
    if (command.kind === "track-cancel" && command.sessionId) {
      return authority.runSession(() => wbvInteractionApiV2.cancelTracking(managedWellId, {
        session_id: command.sessionId, sequence: command.sequence,
      }));
    }
    return null;
  };

  const sendIntervalToLogViewer = async () => {
    const managedWellId = state.viewerPackage?.managed_well_id;
    if (!managedWellId) return;
    setInteractionSaving(true);
    setInteractionError(null);
    try {
      await wbvInteractionApiV2.sendIntervalToWdv(managedWellId);
    } catch (caught) {
      setInteractionError(caught instanceof Error ? caught.message : "Unable to send the AOI to Log Viewer.");
    } finally {
      setInteractionSaving(false);
    }
  };

  const changeDepthUnit = async (nextUnit: WbvDepthUnit) => {
    const managedWellId = state.viewerPackage?.managed_well_id;
    if (!managedWellId || nextUnit === state.viewerPackage?.depth_unit) return;

    setDepthUnitSaving(true);
    setState((current) => ({ ...current, error: null }));
    try {
      const settings = await fetchWlvJson<{
        managed_well_id?: string;
        depth_unit?: WbvDepthUnit;
      }>(
        `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/display-settings`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ depth_unit: nextUnit }),
        },
      );
      if (settings.depth_unit !== nextUnit) {
        throw new Error("WBV backend did not confirm the selected depth unit.");
      }

      const viewerPackage = await fetchWlvJson<WbvViewerPackageContract>(
        `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/viewer-package`,
      );
      if (viewerPackage.depth_unit !== nextUnit) {
        throw new Error("WBV viewer package did not return converted depth values.");
      }

      const currentPoints = state.viewerPackage?.trajectory?.render_points ?? [];
      const nextPoints = viewerPackage.trajectory?.render_points ?? [];
      setSelectedPoint((currentSelectedPoint) =>
        remapSelectedPointAcrossPackages(
          currentSelectedPoint,
          currentPoints,
          nextPoints,
        ),
      );
      setState((current) => ({
        ...current,
        viewerPackage,
        loading: false,
        error: null,
      }));
    } catch (caught) {
      setState((current) => ({
        ...current,
        error:
          caught instanceof Error
            ? caught.message
            : "Unable to change WBV depth units",
      }));
    } finally {
      setDepthUnitSaving(false);
    }
  };

  useEffect(() => {
    setSelectedPoint(null);
    void loadWbvSession();
    void loadWellSelectorItems();
  }, [loadWbvSession, loadWellSelectorItems]);

  useEffect(() => {
    const refreshFromBackend = () => {
      void loadWbvSession();
    };
    const refreshWhenVisible = () => {
      if (document.visibilityState === "visible") {
        refreshFromBackend();
      }
    };

    window.addEventListener("focus", refreshFromBackend);
    document.addEventListener("visibilitychange", refreshWhenVisible);

    return () => {
      window.removeEventListener("focus", refreshFromBackend);
      document.removeEventListener("visibilitychange", refreshWhenVisible);
    };
  }, [loadWbvSession]);

  const defaultLayerConfig = (layerType: WbvDisplayLayerKey): WbvLayerConfig => ({
    layer_type: layerType,
    visible: false,
    selected_item_ids: [],
    source_type: "wmd",
    source_product_id: null,
    scale: { mode: "backend_default", minimum: null, maximum: null, scale_type: "linear", direction: "normal" },
    appearance: { color: null, opacity: 1, line_width: 1, display_mode: "line", show_labels: true, marker_style: "ring", marker_size: 1, color_mode: "formation", label_mode: "name_md", label_size: 1, label_offset: 1, label_position: "right", brightness: 1.35, pattern_scale: 1.5, hide_underlay: false },
    curve_settings: [],
  });

  const layerConfigFor = (configs: WbvLayerConfig[], layerType: WbvDisplayLayerKey): WbvLayerConfig =>
    configs.find((item) => item.layer_type === layerType) ?? defaultLayerConfig(layerType);

  const loadLayerEditorWell = async (managedWellId: string) => {
    setLayerEditorWellLoading(true);
    try {
      const [
        nextDisplayLayerFiles,
        nextFormationTopProducts,
        nextLithologyProducts,
        nextCompletionProducts,
        nextCurveProducts,
        nextLayerConfiguration,
      ] = await Promise.all([
        fetchWlvJson<WbvDisplayLayerFilesContract>(
          `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/display-layer-files`,
        ),
        fetchWlvJson<WbvFormationTopProductsContract>(
          `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/formation-top-products`,
        ),
        fetchWlvJson<WbvLithologyProductsContract>(
          `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/lithology-products`,
        ),
        fetchWlvJson<WbvCompletionProductsContract>(
          `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/completion-products`,
        ),
        fetchWlvJson<WbvCurveOverlayProductsContract>(
          `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/curve-overlay-products`,
        ),
        fetchWlvJson<WbvDisplayLayerConfigurationContract>(
          `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/display-layer-configuration`,
        ),
      ]);
      const editorContracts = [nextDisplayLayerFiles, nextFormationTopProducts, nextLithologyProducts, nextCompletionProducts, nextCurveProducts, nextLayerConfiguration];
      if (editorContracts.some((contract) => contract.managed_well_id !== managedWellId)) {
        throw new Error("WBV rejected mixed managed-well layer-editor contracts.");
      }

      setLayerEditorWellId(managedWellId);
      setLayerEditorDisplayLayerFiles(nextDisplayLayerFiles);
      setLayerEditorFormationTopProducts(nextFormationTopProducts);
      setLayerEditorLithologyProducts(nextLithologyProducts);
      setLayerEditorCompletionProducts(nextCompletionProducts);
      setLayerEditorCurveProducts(nextCurveProducts);

      const loaded = nextLayerConfiguration.layers;
      const allTabs: WbvDisplayLayerKey[] = ["formation_tops", "lithology_intervals", "core_images", "casing_hole_sections", "completions", "curve_overlays", "borehole_imagery"];
      setDraftLayerConfigs(allTabs.map((key) => {
        const layer = layerConfigFor(loaded, key);
        return {
          ...layer,
          selected_item_ids: [...layer.selected_item_ids],
          appearance: {
            ...layer.appearance,
            selected_top_ids: layer.appearance.selected_top_ids == null ? null : [...layer.appearance.selected_top_ids],
            selected_interval_ids: layer.appearance.selected_interval_ids == null ? null : [...layer.appearance.selected_interval_ids],
          },
          curve_settings: (layer.curve_settings ?? []).map((item) => ({
            ...item,
            scale: { ...item.scale },
            appearance: { ...item.appearance },
          })),
        };
      }));
      setDraftTracks((nextLayerConfiguration.tracks ?? []).map((track) => ({ ...track })));
      setDraftTrackSpacing(nextLayerConfiguration.track_spacing ?? 0.05);

      const stored = viewPropertiesByWell[managedWellId];
      setDraftViewProperties(structuredClone(stored ?? defaultViewProperties));
    } finally {
      setLayerEditorWellLoading(false);
    }
  };

  const openLayerManager = (tab: WbvManagerTab) => {
    const allTabs: WbvDisplayLayerKey[] = ["formation_tops", "lithology_intervals", "core_images", "casing_hole_sections", "completions", "curve_overlays", "borehole_imagery"];
    const drafts = allTabs.map((key) => {
      const applied = layerConfigFor(appliedLayerConfigs, key);
      return {
        ...applied,
        selected_item_ids: [...applied.selected_item_ids],
        appearance: {
          ...applied.appearance,
          selected_top_ids: applied.appearance.selected_top_ids == null ? null : [...applied.appearance.selected_top_ids],
          selected_interval_ids: applied.appearance.selected_interval_ids == null ? null : [...applied.appearance.selected_interval_ids],
        },
        curve_settings: (applied.curve_settings ?? []).map((item) => ({
          ...item,
          scale: { ...item.scale },
          appearance: { ...item.appearance },
        })),
      };
    });
    const nextTracks: WbvTrackConfig[] = appliedTracks.length > 0 ? appliedTracks.map((track) => ({ ...track })) : [{
      track_id: "curve-track-0",
      display_name: "Track 1",
      track_type: "curve",
      display_order: 0,
      side: "right",
      geometry_type: "legacy_planar",
      radial_lane: 0,
      angular_position_deg: 0,
      orientation_mode: "follow_trajectory",
      thickness: 0.05,
      width: 1,
      background_mode: "transparent",
      background_color: "#000000",
      background_opacity: 0,
      border_visible: false,
      border_color: "#5f6d73",
      wellbore_offset: 0.15,
      previous_track_gap: 0.05,
    }];
    const orderedCurveTracks = nextTracks.filter((track) => track.track_type === "curve").sort((a, b) => a.display_order - b.display_order);
    const synchronizedDrafts = drafts.map((layer) => layer.layer_type !== "curve_overlays" ? layer : {
      ...layer,
      curve_settings: layer.curve_settings.map((setting) => {
        const fallbackTrack = orderedCurveTracks[Math.min(setting.appearance.radial_lane, Math.max(0, orderedCurveTracks.length - 1))] ?? orderedCurveTracks[0];
        const assignedTrack = orderedCurveTracks.find((track) => track.track_id === setting.appearance.track_id) ?? fallbackTrack;
        return assignedTrack ? {
          ...setting,
          appearance: {
            ...setting.appearance,
            track_id: assignedTrack.track_id,
            radial_lane: orderedCurveTracks.findIndex((track) => track.track_id === assignedTrack.track_id),
          },
        } : setting;
      }),
    });
    setDraftLayerConfigs(synchronizedDrafts);
    setLayerEditorWellId(activeManagedWellId ?? null);
    setLayerEditorDisplayLayerFiles(displayLayerFiles);
    setLayerEditorFormationTopProducts(formationTopProducts);
    setLayerEditorLithologyProducts(lithologyProducts);
    setLayerEditorCompletionProducts(completionProducts);
    setLayerEditorCurveProducts(curveOverlayProducts ?? null);
    setDraftViewProperties(JSON.parse(JSON.stringify(viewProperties)) as WbvViewProperties);
    setDraftTracks(nextTracks);
    setDraftTrackSpacing(trackSpacing);
    setSelectedTrackId(nextTracks[0]?.track_id ?? null);
    const curveDraft = layerConfigFor(synchronizedDrafts, "curve_overlays");
    setSelectedCurveForEditing(curveDraft.selected_item_ids[0] ?? null);
    setActiveLayerTab(tab);
    setCurveSelectorSearch("");
    if (!layerManagerRectRecoveredRef.current) {
      const width = Math.min(1180, Math.max(920, window.innerWidth - 180));
      const height = Math.min(820, Math.max(650, window.innerHeight - 140));
      setLayerManagerRect({
        left: Math.max(24, (window.innerWidth - width) / 2),
        top: Math.max(72, (window.innerHeight - height) / 2),
        width,
        height,
      });
      setLayerManagerExpanded(false);
    }
    // Accepted WBV contract: Manage Display Layers is external-only.
    // Never let recovered in-app state suppress creation of the pop-out window.
    setLayerManagerPoppedOut(true);
    setLayerManagerOpen(true);
  };

  const updateDraftLayer = (layerType: WbvDisplayLayerKey, updater: (current: WbvLayerConfig) => WbvLayerConfig) => {
    setDraftLayerConfigs((current) => {
      const existing = layerConfigFor(current, layerType);
      const next = updater(existing);
      return [...current.filter((item) => item.layer_type !== layerType), next];
    });
  };

  const beginLayerManagerDrag = (event: ReactPointerEvent<HTMLElement>) => {
    if (layerManagerExpanded || (event.target as HTMLElement).closest("button, input, select")) return;
    event.preventDefault();
    const start = { x: event.clientX, y: event.clientY, ...layerManagerRect };
    const move = (moveEvent: PointerEvent) => {
      setLayerManagerRect((current) => ({
        ...current,
        left: Math.max(8, Math.min(window.innerWidth - 220, start.left + moveEvent.clientX - start.x)),
        top: Math.max(52, Math.min(window.innerHeight - 100, start.top + moveEvent.clientY - start.y)),
      }));
    };
    const stop = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
  };

  const toggleLayerManagerExpanded = () => {
    if (layerManagerExpanded) {
      if (layerManagerRestoreRect) setLayerManagerRect(layerManagerRestoreRect);
      setLayerManagerExpanded(false);
      return;
    }
    const bounds = layerManagerRef.current?.getBoundingClientRect();
    setLayerManagerRestoreRect(bounds ? { left: bounds.left, top: bounds.top, width: bounds.width, height: bounds.height } : layerManagerRect);
    setLayerManagerRect({ left: 92, top: 72, width: Math.max(760, window.innerWidth - 116), height: Math.max(620, window.innerHeight - 96) });
    setLayerManagerExpanded(true);
  };

  const flashLayerManagerApply = () => {
    if (layerManagerApplyFlashTimerRef.current !== null) {
      window.clearTimeout(layerManagerApplyFlashTimerRef.current);
    }
    setLayerManagerApplyFlash(true);
    layerManagerApplyFlashTimerRef.current = window.setTimeout(() => {
      setLayerManagerApplyFlash(false);
      layerManagerApplyFlashTimerRef.current = null;
    }, 420);
  };

  const applyLayerManager = async () => {
    if (activeLayerTab === "view_properties") {
      const targetWellId = layerEditorWellId ?? activeManagedWellId;
      if (targetWellId) {
        const cloned = JSON.parse(JSON.stringify(draftViewProperties)) as WbvViewProperties;
        setViewPropertiesByWell((current) => ({ ...current, [targetWellId]: cloned }));
        if (targetWellId === activeManagedWellId) setViewProperties(cloned);
      }
      // Apply commits the current draft but deliberately keeps the manager open.
      // Closing is reserved for X or Cancel; subsequent edits remain live-preview drafts.
      flashLayerManagerApply();
      return;
    }
    const managedWellId = layerEditorWellId ?? state.viewerPackage?.managed_well_id;
    if (!managedWellId) return;
    setLayerManagerSaving(true);
    try {
      if (activeLayerTab === "curve_overlays") {
        await savePublishedPresentation();
      }

      const layersForApply = draftLayerConfigs.map((layer) => {
        const isCurrentLayer = layer.layer_type === activeLayerTab;
        const hasConfiguredContent =
          layer.selected_item_ids.length > 0
          || Boolean(layer.source_product_id)
          || (layer.layer_type === "curve_overlays" && draftTracks.length > 0);
        const normalizedLayer = layer.layer_type !== "curve_overlays" ? layer : {
          ...layer,
          curve_settings: layer.curve_settings.map((setting) => {
            const trackIndex = Math.max(0, draftTracks.findIndex((track) => track.track_id === setting.appearance.track_id));
            return { ...setting, appearance: { ...setting.appearance, radial_lane: trackIndex } };
          }),
        };
        // Applying a configured layer makes that layer visible for the selected well.
        // Hiding it remains an explicit action in WBV Controls.
        return isCurrentLayer && hasConfiguredContent
          ? { ...normalizedLayer, visible: true }
          : normalizedLayer;
      });
      const saved = await fetchWlvJson<WbvDisplayLayerConfigurationContract>(
        `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/display-layer-configuration`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            track_spacing: draftTrackSpacing,
            tracks: draftTracks,
            layers: layersForApply,
          }),
        },
      );
      const applyingToActiveWell = managedWellId === activeManagedWellId;
      if (applyingToActiveWell) {
        setAppliedLayerConfigs(saved.layers);
        setAppliedTracks(saved.tracks ?? []);
        setTrackSpacing(saved.track_spacing ?? 0.05);
      }
      const refreshedCurveRenderPackage = await fetchWlvJson<WbvCurveOverlayRenderContract>(
        `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/curve-overlays/render-package`,
        { cache: "no-store" },
      ).catch(() => null);
      setDisplayedWellPackages((current) => {
        const existing = current[managedWellId];
        if (!existing) return current;
        return {
          ...current,
          [managedWellId]: {
            ...existing,
            layers: {
              ...existing.layers,
              configuration: saved,
              curveRenderPackage: refreshedCurveRenderPackage ?? existing.layers.curveRenderPackage,
            },
          },
        };
      });
      setPrefetchedWellPackages((current) => {
        const existing = current[managedWellId];
        if (!existing) return current;
        return {
          ...current,
          [managedWellId]: {
            ...existing,
            layers: {
              ...existing.layers,
              configuration: saved,
              curveRenderPackage: refreshedCurveRenderPackage ?? existing.layers.curveRenderPackage,
            },
          },
        };
      });
      // The backend response is now the committed baseline for the editor well. Keep the modal open
      // and continue previewing from that normalized committed state.
      setDraftLayerConfigs(saved.layers.map((layer) => ({
        ...layer,
        selected_item_ids: [...layer.selected_item_ids],
        appearance: {
          ...layer.appearance,
          selected_top_ids: layer.appearance.selected_top_ids == null
            ? null
            : [...layer.appearance.selected_top_ids],
          selected_interval_ids: layer.appearance.selected_interval_ids == null
            ? null
            : [...layer.appearance.selected_interval_ids],
        },
        curve_settings: (layer.curve_settings ?? []).map((item) => ({
          ...item,
          scale: { ...item.scale },
          appearance: { ...item.appearance },
        })),
      })));
      setDraftTracks((saved.tracks ?? []).map((track) => ({ ...track })));
      setDraftTrackSpacing(saved.track_spacing ?? 0.05);
      if (applyingToActiveWell) {
        const curveConfig = layerConfigFor(saved.layers, "curve_overlays");
        setSelectedCurveOverlayProductId(curveConfig.source_product_id ?? "");
        await normalizeSelectedCurves(curveConfig.selected_item_ids);
        const managedWellUid = state.session?.active_managed_well_uid;
        const activePublishedPackage = publishedOverlayPackages.find(
          (item) => item.status === "active",
        );
        if (managedWellUid && activePublishedPackage) {
          const renderPackage = await fetchWlvJson<WbvCurveOverlayRenderContract>(
            publishedWbvRenderPackageUrl(
              managedWellUid,
              activePublishedPackage.package_uid,
            ),
            { cache: "no-store" },
          );
          setCurveOverlayRenderPackage(renderPackage);
        } else {
          setCurveOverlayRenderPackage(null);
        }
      }
      flashLayerManagerApply();
      // Apply commits without closing. X/Cancel are the only close actions.
    } catch (caught) {
      setState((current) => ({ ...current, error: caught instanceof Error ? caught.message : "Unable to save WBV display layers" }));
    } finally { setLayerManagerSaving(false); }
  };

  const setActiveWellLayerVisibility = (layerType: WbvDisplayLayerKey, visible: boolean) => {
    const managedWellId = activeManagedWellId;
    if (!managedWellId) return;

    const previousLayers = appliedLayerConfigs;
    const updatedLayers = (() => {
      const existing = previousLayers.find((item) => item.layer_type === layerType);
      if (existing) {
        return previousLayers.map((item) =>
          item.layer_type === layerType ? { ...item, visible } : item
        );
      }
      return [...previousLayers, { ...defaultLayerConfig(layerType), visible }];
    })();

    const previousBundle = displayedWellPackages[managedWellId] ?? prefetchedWellPackages[managedWellId];
    const previousConfiguration = previousBundle?.layers.configuration ?? null;
    const nextConfiguration: WbvDisplayLayerConfigurationContract = previousConfiguration
      ? {
          ...previousConfiguration,
          layers: updatedLayers,
          tracks: appliedTracks,
          track_spacing: trackSpacing,
        }
      : {
          managed_well_id: managedWellId,
          layers: updatedLayers,
          tracks: appliedTracks,
          track_spacing: trackSpacing,
        };

    const updateBundle = (
      current: Record<string, WbvDisplayedWellPackage>,
      configuration: WbvDisplayLayerConfigurationContract,
    ) => {
      const existing = current[managedWellId];
      if (!existing) return current;
      return {
        ...current,
        [managedWellId]: {
          ...existing,
          layers: { ...existing.layers, configuration },
        },
      };
    };

    // One optimistic state update feeds both the active renderer/sidebar and the
    // displayed-well bundle used if this well later becomes a context well.
    setAppliedLayerConfigs(updatedLayers);
    setDisplayedWellPackages((current) => updateBundle(current, nextConfiguration));
    setPrefetchedWellPackages((current) => updateBundle(current, nextConfiguration));

    void fetchWlvJson<WbvDisplayLayerConfigurationContract>(
      `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/display-layer-configuration`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          track_spacing: trackSpacing,
          tracks: appliedTracks,
          layers: updatedLayers,
        }),
      },
    ).then((saved) => {
      setAppliedLayerConfigs(saved.layers);
      setAppliedTracks(saved.tracks ?? appliedTracks);
      setTrackSpacing(saved.track_spacing ?? trackSpacing);
      setDisplayedWellPackages((current) => updateBundle(current, saved));
      setPrefetchedWellPackages((current) => updateBundle(current, saved));
    }).catch((caught) => {
      // Restore the exact pre-toggle local authority if persistence fails.
      setAppliedLayerConfigs(previousLayers);
      if (previousConfiguration) {
        setDisplayedWellPackages((current) => updateBundle(current, previousConfiguration));
        setPrefetchedWellPackages((current) => updateBundle(current, previousConfiguration));
      }
      setState((current) => ({
        ...current,
        error: caught instanceof Error ? caught.message : "Unable to persist WBV layer visibility",
      }));
    });
  };

  const normalizeSelectedCurves = async (curveIds: string[]) => {
    const managedWellId = state.viewerPackage?.managed_well_id;
    setSelectedCurveProductIds(curveIds);
    if (!managedWellId || curveIds.length === 0) {
      setCurveOverlayNormalization(null);
      return;
    }
    try {
      const normalized = await fetchWlvJson<WbvCurveOverlayNormalizationContract>(
        `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/curve-overlays/normalize`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ curve_product_ids: curveIds }),
        },
      );
      setCurveOverlayNormalization(normalized);
    } catch (caught) {
      setCurveOverlayNormalization(null);
      setState((current) => ({
        ...current,
        error: caught instanceof Error ? caught.message : "Unable to normalize selected curves",
      }));
    }
  };

  const displayedManagedWellId = selectedUnavailableWellId ?? state.session?.active_managed_well_id ?? "";
  const selectedWellItem = wellSelectorItems.find((item) => item.managedWellId === displayedManagedWellId) ?? null;
  const session = selectedUnavailableWellId ? null : state.session;
  const viewerPackage = selectedUnavailableWellId ? null : state.viewerPackage;
  const trajectory = viewerPackage?.trajectory;
  const surveyQaqc = viewerPackage?.survey_qaqc;
  const renderPoints = trajectory?.render_points ?? [];
  // Keep renderer collection props referentially stable while zoom percentage
  // updates rerender this page. Fresh fallback arrays here previously caused the
  // Three.js construction effect to dispose and rebuild the entire scene on
  // successive zoom frames.
  const rendererCurveOverlays = useMemo(() => {
    const baseCurves = curveOverlayRenderPackage?.curves ?? [];
    const activeManagedWellUid = state.session?.active_managed_well_uid ?? null;
    const editingPublishedCurves =
      layerManagerOpen
      && activeLayerTab === "curve_overlays"
      && Boolean(publishedPresentationDraft)
      && selectedPublishedPackage?.status === "active"
      && selectedPublishedPackage.managed_well_uid === activeManagedWellUid;

    if (!editingPublishedCurves || !publishedPresentationDraft) return baseCurves;
    if (!publishedPresentationDraft.package_visible) return [];

    const overrides = new Map(
      publishedPresentationDraft.curves.map((item) => [item.assignment_uid, item]),
    );
    const depthMin = publishedPresentationDraft.depth_clip_min;
    const depthMax = publishedPresentationDraft.depth_clip_max;

    return baseCurves.flatMap((curve) => {
      const override = curve.assignment_uid
        ? overrides.get(curve.assignment_uid)
        : undefined;
      if (override?.visible === false) return [];

      const samples =
        depthMin == null && depthMax == null
          ? curve.samples
          : curve.samples.filter(
              (sample) =>
                (depthMin == null || sample.md >= depthMin)
                && (depthMax == null || sample.md <= depthMax),
            );

      return [{
        ...curve,
        color: override?.color ?? curve.color,
        line_width: override?.line_width ?? curve.line_width,
        opacity: override?.opacity ?? curve.opacity,
        radial_width: override?.radial_exaggeration ?? curve.radial_width,
        label_visible: override?.label_visible ?? curve.label_visible ?? false,
        label_content: override?.label_content ?? curve.label_content ?? "mnemonic",
        label_anchor: override?.label_anchor ?? curve.label_anchor ?? "top",
        label_custom_md: override?.label_custom_md ?? curve.label_custom_md ?? null,
        label_size: override?.label_size ?? curve.label_size ?? 1,
        label_weight: override?.label_weight ?? curve.label_weight ?? 800,
        label_alignment: override?.label_alignment ?? curve.label_alignment ?? "center",
        label_position: override?.label_position ?? curve.label_position ?? "on_track",
        label_horizontal_adjustment: override?.label_horizontal_adjustment ?? curve.label_horizontal_adjustment ?? 0,
        label_vertical_adjustment: override?.label_vertical_adjustment ?? curve.label_vertical_adjustment ?? 0,
        scale_color: override?.scale_color ?? curve.scale_color ?? "#b7c5d0",
        scale_opacity: override?.scale_opacity ?? curve.scale_opacity ?? 1,
        scale_line_width: override?.scale_line_width ?? curve.scale_line_width ?? 1,
        scale_size: override?.scale_size ?? curve.scale_size ?? 1,
        samples,
      }];
    });
  }, [
    curveOverlayRenderPackage?.curves,
    layerManagerOpen,
    activeLayerTab,
    publishedPresentationDraft,
    selectedPublishedPackage,
    state.session?.active_managed_well_uid,
  ]);
  const rendererCurveTracks = useMemo<WbvCurveTrack[]>(
    () =>
      (curveOverlayRenderPackage?.tracks ?? appliedTracks).map((track) => ({
        ...track,
        track_type: track.track_type,
        grid_mode: "off",
        grid_color: "#5f7384",
      })),
    [curveOverlayRenderPackage?.tracks, appliedTracks],
  );
  const activeManagedWellId = state.session?.active_managed_well_id ?? null;

  useEffect(() => {
    let cancelled = false;
    void fetchWlvJson<WbvRecoveryStateRecord>("/api/wlv/wbv/saved-canvases/recovery-state")
      .then((record) => {
        if (cancelled) return;
        const recovered = record.state;
        if (!recovered || recovered.schema_version !== 1) {
          coreRecoveryHydratedRef.current = true;
          return;
        }

        setCoreViewMode(Boolean(recovered.core_view_mode));

        const layout = recovered.core_layout;
        if (layout) {
          if (layout.lattice_side === "off" || layout.lattice_side === "left" || layout.lattice_side === "right") setCoreLatticeSide(layout.lattice_side);
          if (Number.isFinite(layout.lattice_offset)) setCoreLatticeOffset(Math.max(0, Math.min(80, Number(layout.lattice_offset))));
          if (layout.description_side === "off" || layout.description_side === "left" || layout.description_side === "right") {
            coreDescriptionSideTouchedRef.current = true;
            setCoreDescriptionSide(layout.description_side);
          }
          if (Number.isFinite(layout.description_offset)) setCoreDescriptionOffset(Math.max(0, Math.min(80, Number(layout.description_offset))));
          if (Number.isFinite(layout.description_width)) setCoreDescriptionPanelWidth(Math.max(140, Math.min(420, Number(layout.description_width))));
          if (Number.isFinite(layout.description_font_size)) setCoreDescriptionFontSize(Math.max(8, Math.min(24, Number(layout.description_font_size))));
          if (typeof layout.description_show_md === "boolean") setCoreDescriptionShowMd(layout.description_show_md);
        }

        const modal = recovered.core_modal;
        if (modal) {
          if (modal.position && Number.isFinite(modal.position.x) && Number.isFinite(modal.position.y)) setCoreModalPosition({ x: modal.position.x, y: modal.position.y });
          if (modal.size && Number.isFinite(modal.size.width) && Number.isFinite(modal.size.height)) {
            setCoreModalSize({
              width: Math.max(620, Number(modal.size.width)),
              height: Math.max(480, Number(modal.size.height)),
            });
          }
          if (Number.isFinite(modal.zoom)) setCoreModalZoom(Math.max(.5, Math.min(8, Number(modal.zoom))));
          if (typeof modal.zoom_locked === "boolean") setCoreModalZoomLocked(modal.zoom_locked);
          if (typeof modal.expanded === "boolean") setCoreModalExpanded(false);
        }

        const displayModal = recovered.display_modal;
        if (displayModal) {
          const rect = displayModal.rect;
          if (rect && [rect.left, rect.top, rect.width, rect.height].every(Number.isFinite)) {
            setLayerManagerRect({
              left: Number(rect.left),
              top: Number(rect.top),
              width: Math.max(760, Number(rect.width)),
              height: Math.max(620, Number(rect.height)),
            });
            layerManagerRectRecoveredRef.current = true;
          }
          if (typeof displayModal.expanded === "boolean") setLayerManagerExpanded(displayModal.expanded);
          if (typeof displayModal.popped_out === "boolean") {
            // Preserve schema compatibility but enforce the accepted external-only contract.
            setLayerManagerPoppedOut(true);
          }
          if (displayModal.active_tab) setActiveLayerTab(displayModal.active_tab);
          if (displayModal.selected_view_property) setSelectedViewProperty(displayModal.selected_view_property);
        }

        if (modal?.open && recovered.managed_well_id) {
          pendingCoreModalRecoveryRef.current = recovered as WbvCoreRestartRecoveryState;
        } else {
          coreRecoveryHydratedRef.current = true;
        }
      })
      .catch((error) => {
        console.error("WBV Core recovery-state load failed", error);
        if (!cancelled) coreRecoveryHydratedRef.current = true;
      });
    return () => { cancelled = true; };
  }, []);

  // Live preview is deliberately scoped to renderer inputs that can be updated
  // safely without a backend normalization/rebuild. Formation Tops and View
  // Properties are fully local presentation state, so their drafts can render
  // immediately while Manage Display Layers remains open.
  const editingActiveLayerWell = (layerEditorWellId ?? activeManagedWellId) === activeManagedWellId;
  const previewFormationTopConfig = layerConfigFor(
    layerManagerOpen && editingActiveLayerWell ? draftLayerConfigs : appliedLayerConfigs,
    "formation_tops",
  );
  const previewFormationTopProducts =
    layerManagerOpen && editingActiveLayerWell
      ? (layerEditorFormationTopProducts ?? formationTopProducts)
      : formationTopProducts;
  const previewViewProperties =
    layerManagerOpen && activeLayerTab === "view_properties"
      ? draftViewProperties
      : viewProperties;
  const previewLithologyConfig = layerConfigFor(
    layerManagerOpen && editingActiveLayerWell ? draftLayerConfigs : appliedLayerConfigs,
    "lithology_intervals",
  );
  const previewLithologyProducts =
    layerManagerOpen && editingActiveLayerWell
      ? (layerEditorLithologyProducts ?? lithologyProducts)
      : lithologyProducts;
  const previewCompletionConfig = layerConfigFor(
    layerManagerOpen && editingActiveLayerWell ? draftLayerConfigs : appliedLayerConfigs,
    "completions",
  );
  const previewCompletionProducts = layerManagerOpen && editingActiveLayerWell
    ? (layerEditorCompletionProducts ?? completionProducts)
    : completionProducts;
  const previewCompletionComponents = (previewCompletionProducts?.products ?? [])
    .filter((product) => previewCompletionConfig.selected_item_ids.includes(product.product_id))
    .flatMap((product) => {
      const selectedComponentIds = previewCompletionConfig.appearance.selected_component_ids;
      return selectedComponentIds == null
        ? product.components
        : product.components.filter((component) => selectedComponentIds.includes(component.component_id));
    });

  const previewCoreConfig = layerConfigFor(
    layerManagerOpen && editingActiveLayerWell ? draftLayerConfigs : appliedLayerConfigs,
    "core_images",
  );

  useEffect(() => {
    let cancelled = false;
    const managedWellId = activeManagedWellId;
    const productIds = previewCoreConfig.selected_item_ids;
    if (!managedWellId || !previewCoreConfig.visible || productIds.length === 0) {
      setCoreRenderChunks([]);
      return () => { cancelled = true; };
    }

    void Promise.all(productIds.map(async (productId) => {
      const manifest = await fetchWlvJson<WbvCoreDisplayChunksContract>(
        `/api/wlv/inventory/wells/${encodeURIComponent(managedWellId)}/core-segment-display-chunks?product_id=${encodeURIComponent(productId)}`,
      );
      return (manifest.chunks ?? []).map((chunk): WbvCoreRenderChunk => ({
        product_id: productId,
        chunk_id: chunk.chunk_id,
        top_md: Number(chunk.top_depth),
        base_md: Number(chunk.base_depth),
        pixel_width: Number(chunk.pixel_width),
        pixel_height: Number(chunk.pixel_height),
        image_url: `${wbvApiBaseUrl()}/api/wlv/inventory/wells/${encodeURIComponent(managedWellId)}/core-segment-display-chunk?product_id=${encodeURIComponent(productId)}&chunk_id=${encodeURIComponent(chunk.chunk_id)}`,
      })).filter((chunk) => Number.isFinite(chunk.top_md) && Number.isFinite(chunk.base_md));
    })).then((groups) => {
      if (!cancelled) setCoreRenderChunks(groups.flat());
    }).catch((error) => {
      console.error("WBV Core display-chunk load failed", error);
      if (!cancelled) setCoreRenderChunks([]);
    });

    return () => { cancelled = true; };
  }, [
    activeManagedWellId,
    previewCoreConfig.visible,
    previewCoreConfig.selected_item_ids.join("|"),
  ]);

  useEffect(() => {
    let cancelled = false;
    const managedWellId = activeManagedWellId;
    const selectedProductIds = new Set(previewCoreConfig.selected_item_ids);

    if (!managedWellId || !previewCoreConfig.visible || selectedProductIds.size === 0) {
      setCoreDescriptions([]);
      return () => { cancelled = true; };
    }

    void fetchWlvJson<WbvCoreManagedWellRecord>(
      `/api/wlv/inventory/wells/${encodeURIComponent(managedWellId)}`,
    ).then((record) => {
      if (cancelled) return;
      const descriptions: WbvCoreDescriptionItem[] = [];

      for (const group of record.product_groups ?? []) {
        for (const item of group.items ?? []) {
          const productId = String(item.product_id ?? "");
          if (
            item.product_subgroup_key !== "compound_core_segment"
            || !productId
            || !selectedProductIds.has(productId)
          ) continue;

          for (const [index, raw] of (item.provenance?.description_intervals ?? []).entries()) {
            if (!raw || typeof raw !== "object") continue;
            const topMd = Number(raw.top_depth ?? raw.top_md ?? raw.depth_md);
            const baseCandidate = raw.base_depth ?? raw.base_md;
            const baseMd = baseCandidate == null ? topMd : Number(baseCandidate);
            const text = String(raw.text ?? "").trim();
            if (!Number.isFinite(topMd) || !Number.isFinite(baseMd) || !text) continue;

            descriptions.push({
              description_id: String(raw.description_id ?? `${productId}:description:${index}`),
              product_id: productId,
              top_md: Math.min(topMd, baseMd),
              base_md: Math.max(topMd, baseMd),
              text,
              category: String(raw.category ?? "core_description"),
            });
          }
        }
      }

      descriptions.sort((first, second) =>
        first.top_md - second.top_md
        || first.base_md - second.base_md
        || first.description_id.localeCompare(second.description_id)
      );
      setCoreDescriptions(descriptions);
      if (descriptions.length > 0 && !coreDescriptionSideTouchedRef.current) {
        setCoreDescriptionSide("right");
      }
    }).catch((error) => {
      console.error("WBV Core description load failed", error);
      if (!cancelled) setCoreDescriptions([]);
    });

    return () => { cancelled = true; };
  }, [
    activeManagedWellId,
    previewCoreConfig.visible,
    previewCoreConfig.selected_item_ids.join("|"),
  ]);

  useEffect(() => {
    setCoreInspectionInterval(null);
    setCoreLocatorFocusInterval(null);
    setCoreModalOpen(false);
    setCoreModalChunkId("");
    coreDescriptionSideTouchedRef.current = false;
  }, [
    activeManagedWellId,
    previewCoreConfig.selected_item_ids.join("|"),
  ]);

  const sortedCoreRenderChunks = useMemo(
    () => orderedCoreChunks(coreRenderChunks),
    [coreRenderChunks],
  );

  useEffect(() => {
    const recovered = pendingCoreModalRecoveryRef.current;
    if (!recovered || !activeManagedWellId || recovered.managed_well_id !== activeManagedWellId || sortedCoreRenderChunks.length === 0) return;

    const modal = recovered.core_modal;
    const requestedChunk = sortedCoreRenderChunks.find((chunk) => chunk.chunk_id === modal.chunk_id);
    const targetMd = Number.isFinite(modal.target_md)
      ? Number(modal.target_md)
      : modal.visible_interval
        ? (modal.visible_interval.top_md + modal.visible_interval.base_md) / 2
        : null;
    const nearestChunk = requestedChunk ?? (targetMd == null
      ? sortedCoreRenderChunks[0]
      : [...sortedCoreRenderChunks].sort((first, second) => {
          const firstCenter = (first.top_md + first.base_md) / 2;
          const secondCenter = (second.top_md + second.base_md) / 2;
          return Math.abs(firstCenter - targetMd) - Math.abs(secondCenter - targetMd);
        })[0]);

    if (nearestChunk) setCoreModalChunkId(nearestChunk.chunk_id);
    if (targetMd != null) setCoreModalTargetMd(targetMd);
    if (modal.visible_interval) setCoreLocatorFocusInterval(structuredClone(modal.visible_interval));
    setCoreModalOpen(Boolean(modal.open));

    pendingCoreModalRecoveryRef.current = null;
    coreRecoveryHydratedRef.current = true;
  }, [activeManagedWellId, sortedCoreRenderChunks]);

  const coreModalProductId = useMemo(() => {
    if (!coreModalChunkId) return "";
    return sortedCoreRenderChunks.find((chunk) => chunk.chunk_id === coreModalChunkId)?.product_id ?? "";
  }, [sortedCoreRenderChunks, coreModalChunkId]);
  const coreModalChunks = useMemo(
    () => sortedCoreRenderChunks.filter((chunk) => !coreModalProductId || chunk.product_id === coreModalProductId),
    [sortedCoreRenderChunks, coreModalProductId],
  );
  const coreModalTopMd = useMemo(
    () => coreModalChunks.length
      ? Math.min(...coreModalChunks.map((chunk) => Math.min(chunk.top_md, chunk.base_md)))
      : 0,
    [coreModalChunks],
  );
  const coreModalBaseMd = useMemo(
    () => coreModalChunks.length
      ? Math.max(...coreModalChunks.map((chunk) => Math.max(chunk.top_md, chunk.base_md)))
      : 0,
    [coreModalChunks],
  );
  const coreModalPixelsPerMd = 120 * coreModalZoom;
  const coreModalContentHeight = Math.max(
    620,
    Math.max(0.001, coreModalBaseMd - coreModalTopMd) * coreModalPixelsPerMd,
  );
  const coreModalDepthTicks = useMemo(() => {
    if (!coreModalChunks.length) return [];
    const rawStep = coreModalZoom >= 2.5 ? 0.5 : coreModalZoom >= 1.25 ? 1 : 2;
    const first = Math.ceil(coreModalTopMd / rawStep) * rawStep;
    const ticks: number[] = [];
    for (let md = first; md <= coreModalBaseMd + 1e-6; md += rawStep) {
      ticks.push(Number(md.toFixed(3)));
    }
    return ticks;
  }, [coreModalChunks.length, coreModalTopMd, coreModalBaseMd, coreModalZoom]);
  const coreModalDescriptions = useMemo(
    () => coreDescriptions.filter((item) =>
      (!coreModalProductId || item.product_id === coreModalProductId)
      && item.base_md >= coreModalTopMd
      && item.top_md <= coreModalBaseMd
    ),
    [coreDescriptions, coreModalProductId, coreModalTopMd, coreModalBaseMd],
  );
  const coreModalImageLaneWidth = useMemo(() => {
    if (!coreModalChunks.length) return 80;
    const widths = coreModalChunks.map((chunk) => {
      const pixelWidth = Number(chunk.pixel_width);
      const pixelHeight = Number(chunk.pixel_height);
      const mdHeight = Math.max(1, Math.abs(chunk.base_md - chunk.top_md) * coreModalPixelsPerMd);
      if (!Number.isFinite(pixelWidth) || !Number.isFinite(pixelHeight) || pixelWidth <= 0 || pixelHeight <= 0) {
        return 80;
      }
      return mdHeight * (pixelWidth / pixelHeight);
    });
    return Math.max(48, Math.min(720, Math.ceil(Math.max(...widths))));
  }, [coreModalChunks, coreModalPixelsPerMd]);

  const updateCoreModalVisibleInterval = () => {
    if (coreModalFocusRafRef.current != null) return;
    coreModalFocusRafRef.current = requestAnimationFrame(() => {
      coreModalFocusRafRef.current = null;
      const viewport = coreModalViewportRef.current;
      if (!viewport || coreModalPixelsPerMd <= 0 || !coreModalChunks.length) return;
      const topMd = coreModalTopMd + viewport.scrollTop / coreModalPixelsPerMd;
      const baseMd = coreModalTopMd + (viewport.scrollTop + viewport.clientHeight) / coreModalPixelsPerMd;
      setCoreLocatorFocusInterval({
        top_md: Math.max(coreModalTopMd, Math.min(coreModalBaseMd, topMd)),
        base_md: Math.max(coreModalTopMd, Math.min(coreModalBaseMd, baseMd)),
      });
    });
  };

  const selectCoreModalChunk = (chunk: WbvCoreRenderChunk | null, targetMd?: number) => {
    if (!chunk) return;
    setCoreModalChunkId(chunk.chunk_id);
    setCoreModalTargetMd(targetMd ?? (chunk.top_md + chunk.base_md) / 2);
    setCoreModalOpen(true);
  };

  const handleCoreLocatorPick = (pick: WbvCoreLocatorPick) => {
    const matching = sortedCoreRenderChunks
      .filter((chunk) => chunk.product_id === pick.product_id)
      .find((chunk) => {
        const top = Math.min(chunk.top_md, chunk.base_md);
        const base = Math.max(chunk.top_md, chunk.base_md);
        return pick.md >= top && pick.md <= base;
      });
    const nearest = matching ?? sortedCoreRenderChunks
      .filter((chunk) => chunk.product_id === pick.product_id)
      .sort((first, second) => {
        const firstCenter = (first.top_md + first.base_md) / 2;
        const secondCenter = (second.top_md + second.base_md) / 2;
        return Math.abs(firstCenter - pick.md) - Math.abs(secondCenter - pick.md);
      })[0] ?? null;
    selectCoreModalChunk(nearest, pick.md);
  };

  useEffect(() => {
    if (!coreModalOpen || coreModalTargetMd == null || !coreModalChunks.length) return;
    const frame = requestAnimationFrame(() => {
      const viewport = coreModalViewportRef.current;
      if (!viewport) return;
      viewport.scrollTop = Math.max(
        0,
        (coreModalTargetMd - coreModalTopMd) * coreModalPixelsPerMd - viewport.clientHeight / 2,
      );
      updateCoreModalVisibleInterval();
    });
    return () => cancelAnimationFrame(frame);
  }, [coreModalOpen, coreModalTargetMd, coreModalChunkId]);

  useEffect(() => {
    if (!coreModalOpen) return;
    const element = coreModalWindowRef.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;

      // Persist the OUTER border-box size. contentRect is the inner content
      // box; feeding it back into CSS width/height causes a 2px shrink cycle
      // on every observer notification because the modal has a 1px border.
      const borderBox = Array.isArray(entry.borderBoxSize)
        ? entry.borderBoxSize[0]
        : entry.borderBoxSize;
      const measured = borderBox
        ? { width: borderBox.inlineSize, height: borderBox.blockSize }
        : (() => {
            const rect = element.getBoundingClientRect();
            return { width: rect.width, height: rect.height };
          })();

      if (measured.width < 1 || measured.height < 1) return;
      const nextSize = {
        width: Math.max(620, Math.round(measured.width)),
        height: Math.max(480, Math.round(measured.height)),
      };
      setCoreModalSize((current) => (
        current
        && current.width === nextSize.width
        && current.height === nextSize.height
          ? current
          : nextSize
      ));
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [coreModalOpen]);

  const zoomToCoreImage = () => {
    if (sortedCoreRenderChunks.length === 0) return;
    /*
     * Return to symbolic 3D locator mode before fitting the locator itself.
     * This intentionally does not activate any photographic Core interval.
     */
    setCoreInspectionInterval(null);
    requestViewAction("fit-core-locator");
  };

  const viewerState =
    viewerPackage?.viewer_state ?? session?.viewer_state ?? "not_loaded";
  const layers = viewerPackage?.available_layers ?? session?.available_layers;
  const hasTrajectory = renderPoints.length > 0;
  const depthUnit = viewerPackage?.depth_unit ?? "ft";

  // WBV_WELL_INFORMATION_DATUM_BINDING_V1_0_1
  // Well Information is the canonical user-facing datum authority.
  const activeWellInfoMetadata = activeManagedWellId
    ? supplementalWellInfoMetadataByWell[activeManagedWellId] ?? {}
    : {};
  const wellInfoDepthReference = activeWellInfoMetadata.depth_reference?.value?.trim() || '';
  const wellInfoReferenceElevation = activeWellInfoMetadata.reference_elevation?.value?.trim() || '';
  const wellInfoReferenceElevationUnit = activeWellInfoMetadata.reference_elevation?.unit?.trim() || depthUnit;
  const wellInfoElevationHasEmbeddedUnit = /[A-Za-z]/.test(wellInfoReferenceElevation);
  const wellInfoSurfaceDatumLabel = wellInfoDepthReference && wellInfoReferenceElevation
    ? `${wellInfoReferenceElevation}${wellInfoElevationHasEmbeddedUnit || !wellInfoReferenceElevationUnit ? '' : ` ${wellInfoReferenceElevationUnit}`} ${wellInfoDepthReference}`
    : null;
  const angleUnit = viewerPackage?.angle_unit ?? "deg";
  const verticalTrajectory = isVerticalTrajectory(
    renderPoints,
    trajectory?.trajectory_class ?? null,
  );
  const endpoints = firstLastPoint(renderPoints);
  const xRange =
    rangeFromBoundingBox(viewerPackage?.bounding_box, "x") ??
    numericRange(renderPoints.map((point) => point.x ?? point.east_departure));
  const yRange =
    rangeFromBoundingBox(viewerPackage?.bounding_box, "y") ??
    numericRange(renderPoints.map((point) => point.y ?? point.north_departure));
  const zRange =
    rangeFromBoundingBox(viewerPackage?.bounding_box, "z") ??
    numericRange(renderPoints.map((point) => point.z));
  const qaqcFindingCount =
    surveyQaqc?.finding_count ?? surveyQaqc?.findings?.length ?? 0;
  const qaqcDisplayState =
    qaqcFindingCount === 0 ? "Pass" : fieldLabel(surveyQaqc?.overall_state);
  const primaryQaqcFinding = surveyQaqc?.findings?.[0]?.message ?? null;
  const trajectoryPointCount =
    trajectory?.station_count ??
    trajectory?.source_station_count ??
    renderPoints.length;
  const displayedWellList = useMemo(
    () => Object.values(displayedWellPackages),
    [displayedWellPackages],
  );
  const activateWellFromScene = useCallback((managedWellId: string) => {
    if (!managedWellId || managedWellId === activeManagedWellId) return;

    // Scene click changes standard WBV control authority. An open modal with
    // its own well selector keeps its explicit target independently.
    const explicitModalTarget = layerManagerOpen ? layerEditorWellId : null;
    void selectWbvWell(managedWellId).finally(() => {
      if (explicitModalTarget) {
        setLayerEditorWellId(explicitModalTarget);
      } else if (!layerManagerOpen) {
        setLayerEditorWellId(managedWellId);
      }
    });
  }, [
    activeManagedWellId,
    layerManagerOpen,
    layerEditorWellId,
    selectWbvWell,
  ]);

  const contextTrajectories = useMemo(
    () => displayedWellList
      .filter((entry) => entry.managedWellId !== activeManagedWellId)
      .map((entry) => {
        const editingThisWell = layerManagerOpen && layerEditorWellId === entry.managedWellId;
        const persistedLayers = entry.layers.configuration?.layers ?? [];
        const persistedFormationConfig = layerConfigFor(persistedLayers, "formation_tops");
        const formationConfig = editingThisWell
          ? layerConfigFor(draftLayerConfigs, "formation_tops")
          : persistedFormationConfig;
        const products = editingThisWell
          ? (layerEditorFormationTopProducts ?? entry.layers.formationTops)
          : entry.layers.formationTops;
        const curveConfig = editingThisWell
          ? layerConfigFor(draftLayerConfigs, "curve_overlays")
          : layerConfigFor(persistedLayers, "curve_overlays");
        const lithologyConfig = editingThisWell
          ? layerConfigFor(draftLayerConfigs, "lithology_intervals")
          : layerConfigFor(persistedLayers, "lithology_intervals");
        const lithologyProductsForWell = editingThisWell
          ? (layerEditorLithologyProducts ?? entry.layers.lithologyProducts)
          : entry.layers.lithologyProducts;
        const completionConfig = editingThisWell
          ? layerConfigFor(draftLayerConfigs, "completions")
          : layerConfigFor(persistedLayers, "completions");
        const completionProductsForWell = editingThisWell
          ? (layerEditorCompletionProducts ?? entry.layers.completionProducts)
          : entry.layers.completionProducts;
        const formationTopsForWell = (products?.products ?? [])
          .filter((product) => formationConfig.selected_item_ids.includes(product.product_id))
          .flatMap((product) => {
            const selectedTopIds = formationConfig.appearance.selected_top_ids;
            return selectedTopIds == null
              ? product.tops
              : product.tops.filter((top) => selectedTopIds.includes(top.top_id));
          });

        return {
          managedWellId: entry.managedWellId,
          wellName: entry.wellName,
          renderPoints: entry.viewerPackage.trajectory?.render_points ?? [],
          color: viewPropertiesByWell[entry.managedWellId]?.trajectory.color ?? "#67d599",
          materialMode: viewPropertiesByWell[entry.managedWellId]?.trajectory.materialMode ?? "color",
          metallicTone: viewPropertiesByWell[entry.managedWellId]?.trajectory.metallicTone ?? "silver",
          thickness: viewPropertiesByWell[entry.managedWellId]?.trajectory.thickness ?? 1,
          opacity: viewPropertiesByWell[entry.managedWellId]?.trajectory.opacity ?? 1,
          formationTops: formationTopsForWell,
          formationTopAppearance: formationConfig.appearance,
          showFormationTops: formationConfig.visible,
          lithologyIntervals: (lithologyProductsForWell?.products ?? [])
            .filter((product) => lithologyConfig.selected_item_ids.includes(product.product_id))
            .flatMap((product) => {
              const selectedIntervalIds = lithologyConfig.appearance.selected_interval_ids;
              const selectedIntervals = selectedIntervalIds == null
                ? product.intervals
                : product.intervals.filter((interval) => selectedIntervalIds.includes(interval.interval_id));
              return selectedIntervals.map(lithologyRendererInterval);
            }),
          lithologyAppearance: {
            opacity: lithologyConfig.appearance.opacity,
            radiusMultiplier: lithologyConfig.appearance.line_width,
            brightness: lithologyConfig.appearance.brightness ?? 1.35,
            patternScale: lithologyConfig.appearance.pattern_scale ?? 1.5,
            hideUnderlyingWellbore: lithologyConfig.appearance.hide_underlay ?? false,
          },
          showLithologyOverlay: lithologyConfig.visible,
          completionComponents: (completionProductsForWell?.products ?? [])
            .filter((product) => completionConfig.selected_item_ids.includes(product.product_id))
            .flatMap((product) => {
              const selectedComponentIds = completionConfig.appearance.selected_component_ids;
              return selectedComponentIds == null
                ? product.components
                : product.components.filter((component) => selectedComponentIds.includes(component.component_id));
            }),
          completionAppearance: {
            color: completionConfig.appearance.color,
            opacity: completionConfig.appearance.opacity,
            sizeMultiplier: completionConfig.appearance.line_width,
            showLabels: completionConfig.appearance.show_labels,
            labelMode: completionConfig.appearance.label_mode ?? "name_md",
            labelColor: completionConfig.appearance.label_color ?? "#dce7ef",
            labelSize: completionConfig.appearance.label_size ?? 1,
            labelOffset: completionConfig.appearance.label_offset ?? 1,
            labelPosition: completionConfig.appearance.label_position ?? "right",
          },
          showCompletions: completionConfig.visible,
          curveOverlays: curveConfig.visible ? (entry.layers.curveRenderPackage?.curves ?? []) : [],
          curveTracks: (entry.layers.curveRenderPackage?.tracks ?? []).map((track) => ({
            ...track,
            track_type: track.track_type,
            grid_mode: "off" as const,
            grid_color: "#5f7384",
          })),
          curveTrackSpacing: entry.layers.curveRenderPackage?.track_spacing ?? entry.layers.configuration?.track_spacing ?? 0.05,
          showCurveOverlays: curveConfig.visible,
          layerFiles: entry.layers.files,
          depthUnit: entry.viewerPackage.depth_unit ?? depthUnit,
        };
      })
      .filter((entry) => entry.renderPoints.length > 1),
    [
      activeManagedWellId,
      displayedWellList,
      viewPropertiesByWell,
      layerManagerOpen,
      layerEditorWellId,
      draftLayerConfigs,
      layerEditorFormationTopProducts,
      layerEditorLithologyProducts,
      layerEditorCompletionProducts,
      depthUnit,
    ],
  );
  useEffect(() => {
    if (!coreRecoveryHydratedRef.current) return;
    if (coreRecoverySaveTimerRef.current !== null) window.clearTimeout(coreRecoverySaveTimerRef.current);

    coreRecoverySaveTimerRef.current = window.setTimeout(() => {
      const recoveryState: WbvCoreRestartRecoveryState = {
        schema_version: 1,
        managed_well_id: activeManagedWellId,
        core_view_mode: coreViewMode,
        core_modal: {
          open: coreModalOpen,
          chunk_id: coreModalChunkId,
          target_md: coreLocatorFocusInterval
            ? (coreLocatorFocusInterval.top_md + coreLocatorFocusInterval.base_md) / 2
            : coreModalTargetMd,
          visible_interval: coreLocatorFocusInterval ? structuredClone(coreLocatorFocusInterval) : null,
          zoom: coreModalZoom,
          zoom_locked: coreModalZoomLocked,
          expanded: coreModalExpanded,
          position: coreModalPosition ? { ...coreModalPosition } : null,
          size: coreModalSize ? { ...coreModalSize } : null,
        },
        core_layout: {
          lattice_side: coreLatticeSide,
          lattice_offset: coreLatticeOffset,
          description_side: coreDescriptionSide,
          description_offset: coreDescriptionOffset,
          description_width: coreDescriptionPanelWidth,
          description_font_size: coreDescriptionFontSize,
          description_show_md: coreDescriptionShowMd,
        },
        display_modal: {
          rect: { ...layerManagerRect },
          expanded: layerManagerExpanded,
          popped_out: true,
          active_tab: activeLayerTab,
          selected_view_property: selectedViewProperty,
        },
      };

      void fetchWlvJson("/api/wlv/wbv/saved-canvases/recovery-state", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ state: recoveryState }),
      }).catch((error) => {
        console.error("WBV Core recovery-state save failed", error);
      });
      coreRecoverySaveTimerRef.current = null;
    }, 250);

    return () => {
      if (coreRecoverySaveTimerRef.current !== null) {
        window.clearTimeout(coreRecoverySaveTimerRef.current);
        coreRecoverySaveTimerRef.current = null;
      }
    };
  }, [
    activeLayerTab,
    activeManagedWellId,
    coreDescriptionFontSize,
    coreDescriptionOffset,
    coreDescriptionPanelWidth,
    coreDescriptionShowMd,
    coreDescriptionSide,
    coreLatticeOffset,
    coreLatticeSide,
    coreLocatorFocusInterval,
    coreModalChunkId,
    coreModalExpanded,
    coreModalOpen,
    coreModalPosition,
    coreModalSize,
    coreModalTargetMd,
    coreModalZoom,
    coreModalZoomLocked,
    coreViewMode,
    layerManagerExpanded,
    layerManagerPoppedOut,
    layerManagerRect,
    selectedViewProperty,
  ]);

  const refreshWbvSavedCanvases = useCallback(async () => {
    try {
      const items = await fetchWlvJson<SavedCanvasToolbarItem[]>("/api/wlv/wbv/saved-canvases");
      setWbvSavedCanvases(items);
      setWbvSavedCanvasError(null);
    } catch (error) {
      setWbvSavedCanvasError(error instanceof Error ? error.message : "Unable to list WBV Saved Canvases");
    }
  }, []);

  useEffect(() => { void refreshWbvSavedCanvases(); }, [refreshWbvSavedCanvases]);

  const buildWbvSavedCanvasSnapshot = useCallback((): WbvSavedCanvasSnapshot => {
    const activeManagedWellIdForSave = state.session?.active_managed_well_id ?? null;
    const effectiveViewPropertiesByWell = structuredClone(viewPropertiesByWell);
    if (activeManagedWellIdForSave) effectiveViewPropertiesByWell[activeManagedWellIdForSave] = structuredClone(viewProperties);
    const layerConfigurationsByWell: Record<string, WbvDisplayLayerConfigurationContract> = {};
    Object.entries(displayedWellPackages).forEach(([managedWellId, entry]) => {
      const configuration = managedWellId === activeManagedWellIdForSave
        ? { managed_well_id: managedWellId, track_spacing: trackSpacing, tracks: structuredClone(appliedTracks), layers: structuredClone(appliedLayerConfigs) }
        : entry.layers.configuration;
      if (configuration) layerConfigurationsByWell[managedWellId] = structuredClone(configuration);
    });
    return {
      schema_version: 1,
      core_recovery_state: {
        schema_version: 1,
        managed_well_id: activeManagedWellIdForSave,
        core_view_mode: coreViewMode,
        core_modal: {
          open: coreModalOpen,
          chunk_id: coreModalChunkId,
          target_md: coreLocatorFocusInterval
            ? (coreLocatorFocusInterval.top_md + coreLocatorFocusInterval.base_md) / 2
            : coreModalTargetMd,
          visible_interval: coreLocatorFocusInterval ? structuredClone(coreLocatorFocusInterval) : null,
          zoom: coreModalZoom,
          zoom_locked: coreModalZoomLocked,
          expanded: coreModalExpanded,
          position: coreModalPosition ? { ...coreModalPosition } : null,
          size: coreModalSize ? { ...coreModalSize } : null,
        },
        core_layout: {
          lattice_side: coreLatticeSide,
          lattice_offset: coreLatticeOffset,
          description_side: coreDescriptionSide,
          description_offset: coreDescriptionOffset,
          description_width: coreDescriptionPanelWidth,
          description_font_size: coreDescriptionFontSize,
          description_show_md: coreDescriptionShowMd,
        },
        display_modal: {
          rect: { ...layerManagerRect },
          expanded: layerManagerExpanded,
          popped_out: true,
          active_tab: activeLayerTab,
          selected_view_property: selectedViewProperty,
        },
      },
      displayed_well_ids: Object.keys(displayedWellPackages),
      active_managed_well_id: activeManagedWellIdForSave,
      view_properties_by_well: effectiveViewPropertiesByWell,
      viewer_controls: structuredClone(viewerControls),
      display_layers: structuredClone(displayLayers),
      track_values_along_wellbore: trackValuesAlongWellbore,
      view_preset: viewPreset,
      zoom_percent: zoomPercent,
      camera_view: wbvCameraViewRef.current ? structuredClone(wbvCameraViewRef.current) : null,
      horizontal_rotation_locked: horizontalRotationLocked,
      vertical_rotation_locked: verticalRotationLocked,
      layer_configurations_by_well: layerConfigurationsByWell,
    };
  }, [activeLayerTab, appliedLayerConfigs, appliedTracks, coreDescriptionFontSize, coreDescriptionOffset, coreDescriptionPanelWidth, coreDescriptionShowMd, coreDescriptionSide, coreLatticeOffset, coreLatticeSide, coreLocatorFocusInterval, coreModalChunkId, coreModalExpanded, coreModalOpen, coreModalPosition, coreModalSize, coreModalTargetMd, coreModalZoom, coreModalZoomLocked, coreViewMode, displayLayers, displayedWellPackages, horizontalRotationLocked, layerManagerExpanded, layerManagerPoppedOut, layerManagerRect, selectedViewProperty, state.session?.active_managed_well_id, trackSpacing, trackValuesAlongWellbore, verticalRotationLocked, viewPreset, viewProperties, viewPropertiesByWell, viewerControls, zoomPercent]);

  const saveWbvCanvas = useCallback(async (name: string) => {
    setWbvSavedCanvasSaving(true); setWbvSavedCanvasError(null);
    try {
      await fetchWlvJson("/api/wlv/wbv/saved-canvases", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({name,snapshot:buildWbvSavedCanvasSnapshot()}) });
      await refreshWbvSavedCanvases();
    } catch (error) { setWbvSavedCanvasError(error instanceof Error ? error.message : "Unable to save WBV canvas"); }
    finally { setWbvSavedCanvasSaving(false); }
  }, [buildWbvSavedCanvasSnapshot, refreshWbvSavedCanvases]);

  const saveActiveWbvCanvas = useCallback(async (uid: string) => {
    setWbvSavedCanvasSaving(true); setWbvSavedCanvasError(null);
    try {
      await fetchWlvJson(`/api/wlv/wbv/saved-canvases/${encodeURIComponent(uid)}`, { method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify({snapshot:buildWbvSavedCanvasSnapshot()}) });
      await refreshWbvSavedCanvases();
    } catch (error) { setWbvSavedCanvasError(error instanceof Error ? error.message : "Unable to save WBV canvas changes"); }
    finally { setWbvSavedCanvasSaving(false); }
  }, [buildWbvSavedCanvasSnapshot, refreshWbvSavedCanvases]);

  const fetchSavedCanvasWellPackage = useCallback(async (managedWellId: string): Promise<WbvDisplayedWellPackage> => {
    const item = wellSelectorItems.find((candidate) => candidate.managedWellId === managedWellId);
    if (!item?.hasSurvey) throw new Error(`Saved Canvas references unavailable well ${managedWellId}`);
    const [viewerPackage, files, formationTops, lithologyProductsForWell, completionProductsForWell, curveProducts, configuration, curveRenderPackage] = await Promise.all([
      fetchWlvJson<WbvViewerPackageContract>(`/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/viewer-package`),
      fetchWlvJson<WbvDisplayLayerFilesContract>(`/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/display-layer-files`),
      fetchWlvJson<WbvFormationTopProductsContract>(`/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/formation-top-products`),
      fetchWlvJson<WbvLithologyProductsContract>(`/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/lithology-products`),
      fetchWlvJson<WbvCompletionProductsContract>(`/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/completion-products`),
      fetchWlvJson<WbvCurveOverlayProductsContract>(`/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/curve-overlay-products`),
      fetchWlvJson<WbvDisplayLayerConfigurationContract>(`/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/display-layer-configuration`),
      fetchWlvJson<WbvCurveOverlayRenderContract>(`/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/curve-overlays/render-package`).catch(() => null),
    ]);
    return { managedWellId, wellName:item.wellName, viewerPackage, layers:{files,configuration,formationTops,lithologyProducts:lithologyProductsForWell,completionProducts:completionProductsForWell,curveProducts,curveRenderPackage} };
  }, [wellSelectorItems]);

  const loadWbvSavedCanvas = useCallback(async (uid: string) => {
    if (wbvSavedCanvasBusyUid) return;
    setWbvSavedCanvasBusyUid(uid); setWbvSavedCanvasError(null); setLayerManagerOpen(false);
    try {
      const record = await fetchWlvJson<WbvSavedCanvasRecord>(`/api/wlv/wbv/saved-canvases/${encodeURIComponent(uid)}/restore`, {method:"POST"});
      const snapshot = record.snapshot;
      if (!snapshot || snapshot.schema_version !== 1) throw new Error("Unsupported WBV Saved Canvas schema");
      for (const managedWellId of snapshot.displayed_well_ids) {
        const item = wellSelectorItems.find((candidate) => candidate.managedWellId === managedWellId);
        if (!item?.hasSurvey) throw new Error(`Cannot load ${record.name}: ${managedWellId} is not displayable`);
      }
      const previous: Record<string,WbvDisplayLayerConfigurationContract> = {};
      for (const managedWellId of Object.keys(snapshot.layer_configurations_by_well)) {
        previous[managedWellId] = await fetchWlvJson<WbvDisplayLayerConfigurationContract>(`/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/display-layer-configuration`);
      }
      try {
        for (const [managedWellId,configuration] of Object.entries(snapshot.layer_configurations_by_well)) {
          await fetchWlvJson(`/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/display-layer-configuration`, {method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({track_spacing:configuration.track_spacing,tracks:configuration.tracks,layers:configuration.layers})});
        }
      } catch (restoreError) {
        await Promise.allSettled(Object.entries(previous).map(([managedWellId,configuration]) => fetchWlvJson(`/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/display-layer-configuration`, {method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({track_spacing:configuration.track_spacing,tracks:configuration.tracks,layers:configuration.layers})})));
        throw restoreError;
      }
      const packages=await Promise.all(snapshot.displayed_well_ids.map(fetchSavedCanvasWellPackage));
      const packageMap=Object.fromEntries(packages.map((entry)=>[entry.managedWellId,entry]));
      setDisplayedWellPackages(packageMap); setPrefetchedWellPackages((current)=>({...current,...packageMap}));
      setPendingDisplayedWellIds(Object.fromEntries(snapshot.displayed_well_ids.map((managedWellId)=>[managedWellId,true])));
      setViewPropertiesByWell(structuredClone(snapshot.view_properties_by_well));
      setViewerControls(structuredClone(snapshot.viewer_controls)); setDisplayLayers(structuredClone(snapshot.display_layers));
      setTrackValuesAlongWellbore(snapshot.track_values_along_wellbore); setViewPreset(snapshot.view_preset);
      setHorizontalRotationLocked(snapshot.horizontal_rotation_locked); setVerticalRotationLocked(snapshot.vertical_rotation_locked);
      if (snapshot.core_recovery_state) {
        const recovered = snapshot.core_recovery_state;
        setCoreViewMode(recovered.core_view_mode);
        setCoreLatticeSide(recovered.core_layout.lattice_side);
        setCoreLatticeOffset(recovered.core_layout.lattice_offset);
        coreDescriptionSideTouchedRef.current = true;
        setCoreDescriptionSide(recovered.core_layout.description_side);
        setCoreDescriptionOffset(recovered.core_layout.description_offset);
        setCoreDescriptionPanelWidth(recovered.core_layout.description_width);
        setCoreDescriptionFontSize(recovered.core_layout.description_font_size);
        setCoreDescriptionShowMd(recovered.core_layout.description_show_md);
        setCoreModalZoom(recovered.core_modal.zoom);
        setCoreModalZoomLocked(recovered.core_modal.zoom_locked);
        setCoreModalExpanded(false);
        setCoreModalPosition(recovered.core_modal.position);
        setCoreModalSize(recovered.core_modal.size);
        setLayerManagerRect(recovered.display_modal.rect);
        layerManagerRectRecoveredRef.current = true;
        setLayerManagerExpanded(recovered.display_modal.expanded);
        // Saved Canvas may contain historical in-app state; Manage Display Layers
        // is now governed as external-only.
        setLayerManagerPoppedOut(true);
        setActiveLayerTab(recovered.display_modal.active_tab);
        setSelectedViewProperty(recovered.display_modal.selected_view_property);
        if (recovered.core_modal.open) pendingCoreModalRecoveryRef.current = recovered;
      }
      if (snapshot.active_managed_well_id) { setViewProperties(structuredClone(snapshot.view_properties_by_well[snapshot.active_managed_well_id] ?? defaultViewProperties)); await selectWbvWell(snapshot.active_managed_well_id); }
      if (snapshot.camera_view) {
        const restoredCameraView = structuredClone(snapshot.camera_view);
        wbvCameraViewRef.current = restoredCameraView;
        writeWbvNavigationCameraView(restoredCameraView);
        setWbvCameraViewRestore(restoredCameraView);
        setWbvCameraViewRestoreId((current) => current + 1);
        setZoomPercent(Math.round(restoredCameraView.zoom * 100));
      } else {
        setWbvCameraViewRestore(null);
        setZoomPercent(snapshot.zoom_percent);
      }
      await refreshWbvSavedCanvases();
    } catch (error) { setWbvSavedCanvasError(error instanceof Error ? error.message : "Unable to load WBV Saved Canvas"); }
    finally { setWbvSavedCanvasBusyUid(null); }
  }, [fetchSavedCanvasWellPackage, refreshWbvSavedCanvases, selectWbvWell, wbvSavedCanvasBusyUid, wellSelectorItems]);

  const deleteWbvSavedCanvas = useCallback(async (uid: string) => {
    if (wbvSavedCanvasBusyUid) return;
    setWbvSavedCanvasBusyUid(uid); setWbvSavedCanvasError(null);
    try { await fetchWlvJson(`/api/wlv/wbv/saved-canvases/${encodeURIComponent(uid)}`,{method:"DELETE"}); await refreshWbvSavedCanvases(); }
    catch (error) { setWbvSavedCanvasError(error instanceof Error ? error.message : "Unable to delete WBV Saved Canvas"); }
    finally { setWbvSavedCanvasBusyUid(null); }
  }, [refreshWbvSavedCanvases, wbvSavedCanvasBusyUid]);

  const wellSelectionDirty = !pendingSelectionMatchesDisplayed(pendingDisplayedWellIds, displayedWellPackages);
  const pendingDisplayedWellList = wellSelectorItems.filter((item) => pendingDisplayedWellIds[item.managedWellId]);
  const selectorSummaryItems = wellSelectionDirty ? pendingDisplayedWellList : displayedWellList;
  const displayedWellSummary = selectorSummaryItems.length === 0
    ? "Select wells"
    : selectorSummaryItems.length === 1
      ? selectorSummaryItems[0].wellName
      : `${selectorSummaryItems.length} wells displayed`;

  return (
    <section className="wlv-wbv-page" aria-label="3D Wellbore Viewer">
      <header className="wlv-wbv-header">
        <div>
          <span className="wlv-page-kicker">3D Wellbore</span>
          <h1>3D Wellbore Viewer</h1>
        </div>
        <div className="wlv-wbv-header-tools">
          <div className="wlv-wbv-save-canvas-field" aria-label="WBV Save Canvas">
            <span className="wlv-wbv-save-canvas-title">Save Canvas</span>
            <div className="wlv-toolbar-group wlv-toolbar-group-saved-canvas wlv-wbv-save-canvas-slot" data-toolbar-group="saved-canvas" aria-label="Saved Canvases">
              <div className="wlv-toolbar-actions">
                <SavedCanvasToolbarControl items={wbvSavedCanvases} disabled={state.loading} saving={wbvSavedCanvasSaving} busySavedCanvasUid={wbvSavedCanvasBusyUid} error={wbvSavedCanvasError} onSave={saveWbvCanvas} onSaveChanges={saveActiveWbvCanvas} onLoad={loadWbvSavedCanvas} onDelete={deleteWbvSavedCanvas} />
              </div>
            </div>
          </div>
          <div className="wlv-wbv-well-selector" aria-label="Select managed wells for display">
          <button
            type="button"
            className={`wlv-wbv-well-selector__label-button ${wellSelectionDirty ? "is-pending" : "is-ready"}`}
            disabled={wellSelectorLoading || !wellSelectionDirty}
            onClick={() => void applyDisplayedWellSelection()}
          >
            Well Selection
          </button>
          <div className={`wlv-wbv-multiwell-select ${wellSelectorOpen ? "is-open" : ""}`}>
            <button
              id="wbv-managed-well-select"
              type="button"
              className="wlv-wbv-multiwell-select__trigger"
              disabled={wellSelectorLoading}
              aria-expanded={wellSelectorOpen}
              onClick={() => {
                setWellSelectorOpen((open) => {
                  if (!open) setPendingDisplayedWellIds(selectionRecordFromDisplayedPackages(displayedWellPackages));
                  return !open;
                });
              }}
            >
              <span>{wellSelectorLoading ? "Loading wells…" : displayedWellSummary}</span>
              <span aria-hidden="true">⌄</span>
            </button>
            {wellSelectorOpen ? (
              <div className="wlv-wbv-multiwell-select__menu" role="listbox" aria-multiselectable="true">
                {wellSelectorItems.map((item) => {
                  const checked = Boolean(pendingDisplayedWellIds[item.managedWellId]);
                  const active = activeManagedWellId === item.managedWellId;
                  return (
                    <label key={item.managedWellId} className={`wlv-wbv-multiwell-select__option ${!item.hasSurvey ? "is-unavailable" : ""} ${active ? "is-active" : ""}`}>
                      <input type="checkbox" checked={checked} disabled={!item.hasSurvey} onChange={(event) => togglePendingDisplayedWell(item.managedWellId, event.target.checked)} />
                      <span className="wlv-wbv-multiwell-select__name">{item.wellName}</span>
                      {loadingDisplayedWellIds[item.managedWellId] ? <span className="wlv-wbv-multiwell-select__badge is-loading">LOADING</span> : active ? <span className="wlv-wbv-multiwell-select__badge">ACTIVE</span> : item.activeInWdv ? <span className="wlv-wbv-multiwell-select__badge">WDV</span> : null}
                    </label>
                  );
                })}
              </div>
            ) : null}
          </div>
          {selectedWellItem && !selectedWellItem.hasSurvey ? (
            <p className="wlv-wbv-well-selector__warning">No deviation survey is connected. This well cannot be displayed in the Wellbore Viewer.</p>
          ) : selectedWellItem?.activeInWdv ? (
            <p className="wlv-wbv-well-selector__active">Active in the Well Data Viewer. Linked data exchange is available.</p>
          ) : selectedWellItem?.hasSurvey ? (
            <p className="wlv-wbv-well-selector__notice">Deviation survey available. This well can be displayed independently in WBV; load and activate it in WDV only to enable linked curve data and data exchange.</p>
          ) : null}
          {wellSelectionDirty ? <p className="wlv-wbv-well-selector__pending">Selection changed. Click the Well Selection header to activate the updated display set.</p> : null}
          {wellSelectorMessage && !selectedWellItem ? <p className="wlv-wbv-well-selector__error">{wellSelectorMessage}</p> : null}
          </div>
        </div>
      </header>

      <div className="wlv-wbv-layout">
        <aside
          className="wlv-wbv-panel wlv-wbv-panel--left"
          aria-label="WBV display controls"
        >
          <div className="wlv-wbv-panel-heading">
            <span>Display</span>
            <strong>WBV Controls</strong>
          </div>
          {activeManagedWellId ? (
            <div className="wlv-wbv-active-control-well" title="All standard WBV controls apply to this active well">
              Active well: {selectedWellItem?.wellName ?? activeManagedWellId}
            </div>
          ) : null}

          <section className="wlv-wbv-left-section" aria-labelledby="wbv-viewer-controls-heading">
            <h2 id="wbv-viewer-controls-heading">Viewer</h2>
            <div className="wlv-wbv-control-list">
              {([
                ["boundingBox", "Bounding box"],
                ["depthLabels", "Depth labels"],
                ["surveyStations", "Survey stations"],
                ["groundPlane", "Ground plane"],
                ["bottomGrid", "Bottom grid"],
                ["topGrid", "Top grid"],
                ["northArrow", "Compass"],
                ["surfaceLighting", "3D shading"],
              ] as Array<[keyof WbvViewerControls, string]>).map(([key, label]) => (
                <label key={key}>
                  <input
                    type="checkbox"
                    checked={viewerControls[key]}
                    onChange={(event) =>
                      setViewerControls((current) => ({ ...current, [key]: event.target.checked }))
                    }
                  />
                  <span>{label}</span>
                </label>
              ))}
            </div>
          </section>

          <section className="wlv-wbv-left-section" aria-labelledby="wbv-display-layers-heading">
            <div className="wlv-wbv-section-heading-row">
              <h2 id="wbv-display-layers-heading">Display Layers</h2>
              <button type="button" className="wlv-wbv-manage-layers-button" onClick={() => openLayerManager(activeLayerTab)}>Manage</button>
            </div>
            <div className="wlv-wbv-control-list">
              <label className={!layers?.trajectory ? "is-disabled" : ""}>
                <input type="checkbox" checked={displayLayers.trajectory && Boolean(layers?.trajectory)} disabled={!layers?.trajectory} onChange={(event) => setDisplayLayers({ trajectory: event.target.checked })} />
                <span>Trajectory</span>
              </label>
              {([
                ["formation_tops", "Formation tops"], ["lithology_intervals", "Lithology intervals"], ["core_images", "Core"], ["casing_hole_sections", "Casing / hole sections"],
                ["completions", "Completions"], ["curve_overlays", "Curve overlays"], ["borehole_imagery", "Borehole imagery"],
              ] as Array<[WbvDisplayLayerKey, string]>).map(([key, label]) => {
                const config = layerConfigFor(appliedLayerConfigs, key);
                const hasRenderableCurveContent = key === "curve_overlays"
                  && rendererCurveOverlays.length > 0;
                const configured = config.selected_item_ids.length > 0 || Boolean(config.source_product_id) || hasRenderableCurveContent;
                return <label key={key} className={!configured ? "is-disabled" : ""} onClick={() => setActiveLayerTab(key)}>
                  <input type="checkbox" checked={configured && config.visible} disabled={!configured} onChange={(event) => {
                    event.stopPropagation();
                    setActiveWellLayerVisibility(key, event.target.checked);
                  }} />
                  <span>{label}</span>
                </label>;
              })}
            </div>
          </section>

          {appliedLayerConfigs.some((item) => item.selected_item_ids.length > 0 || item.source_product_id) ? (
            <section className="wlv-wbv-left-section" aria-label="Active layers">
              <h2>Active Layers</h2>
              <div className="wlv-wbv-active-layer-list">
                {appliedLayerConfigs.filter((item) => item.selected_item_ids.length > 0 || item.source_product_id).map((item) => (
                  <div key={item.layer_type}><strong>{fieldLabel(item.layer_type)}</strong><span>{item.layer_type === "curve_overlays" ? `${item.selected_item_ids.length} curves` : `${item.selected_item_ids.length || 1} item`}</span></div>
                ))}
              </div>
            </section>
          ) : null}

          <section className="wlv-wbv-view-controls" aria-label="WBV view controls">
            <h2>View</h2>

            <div className="wlv-wbv-view-control-block">
              <h3>Framing</h3>
              <div className="wlv-wbv-view-control-grid wlv-wbv-view-control-grid--two">
                <button type="button" disabled={!hasTrajectory} onClick={() => requestViewPreset("fit")}>Fit Well</button>
                <button type="button" disabled={!hasTrajectory || !interaction?.saved_interval} onClick={() => requestViewAction("fit-selection")}>Fit Selection</button>
              </div>
            </div>

            <div className="wlv-wbv-view-control-block">
              <h3>Orientation</h3>
              <div className="wlv-wbv-view-control-grid wlv-wbv-view-control-grid--five">
                {orientationPresetOrder.map((preset) => (
                  <button type="button" key={preset} className={viewPreset === preset ? "is-active" : ""} disabled={!hasTrajectory} onClick={() => requestViewPreset(preset)}>
                    {orientationLabels[preset]}
                  </button>
                ))}
              </div>
            </div>

            <div className="wlv-wbv-view-control-block">
              <h3>Zoom</h3>
              <div className="wlv-wbv-zoom-controls">
                <button type="button" aria-label="Zoom out" disabled={!hasTrajectory || zoomPercent <= 25} onClick={() => requestViewAction("zoom-out")}>−</button>
                <button type="button" className="wlv-wbv-zoom-value" disabled={!hasTrajectory} title="Reset zoom to 100%" onClick={() => requestViewAction("zoom-reset")}>{zoomPercent}%</button>
                <button type="button" aria-label="Zoom in" disabled={!hasTrajectory || zoomPercent >= 800} onClick={() => requestViewAction("zoom-in")}>+</button>
              </div>
            </div>

            <div className="wlv-wbv-view-control-block wlv-wbv-rotation-center-controls">
              <h3>Rotation</h3>
              <div className="wlv-wbv-rotation-center-row">
                <button
                  type="button"
                  className={rotationCenterActive ? "is-active" : ""}
                  disabled={!hasTrajectory}
                  aria-pressed={rotationCenterActive}
                  aria-label={rotationCenterActive ? "Clear rotation center" : "Set rotation center"}
                  onClick={handleRotationCenterButton}
                >
                  Set Rotation Center
                </button>
              </div>
              <div className="wlv-wbv-horizontal-rotation-controls">
                <button
                  type="button"
                  aria-label="Rotate horizontally negative"
                  disabled={!hasTrajectory || !horizontalRotationLocked}
                  onPointerDown={(event) => beginHorizontalRotationHold("negative", event)}
                  onPointerUp={() => endHorizontalRotationHold("negative")}
                  onPointerCancel={clearHorizontalRotationHold}
                  onPointerLeave={() => {
                    if (horizontalRotationHoldRef.current.held) clearHorizontalRotationHold();
                  }}
                >−</button>
                <button
                  type="button"
                  className={horizontalRotationLocked ? "is-active" : ""}
                  disabled={!hasTrajectory}
                  onClick={() => {
                    clearHorizontalRotationHold();
                    clearVerticalRotationHold();
                    setHorizontalRotationLocked((current) => {
                      const next = !current;
                      if (next) setVerticalRotationLocked(false);
                      return next;
                    });
                  }}
                >
                  Horizontal
                </button>
                <button
                  type="button"
                  aria-label="Rotate horizontally positive"
                  disabled={!hasTrajectory || !horizontalRotationLocked}
                  onPointerDown={(event) => beginHorizontalRotationHold("positive", event)}
                  onPointerUp={() => endHorizontalRotationHold("positive")}
                  onPointerCancel={clearHorizontalRotationHold}
                  onPointerLeave={() => {
                    if (horizontalRotationHoldRef.current.held) clearHorizontalRotationHold();
                  }}
                >+</button>
              </div>
              <div className="wlv-wbv-vertical-rotation-controls">
                <button
                  type="button"
                  aria-label="Rotate vertically negative"
                  disabled={!hasTrajectory || !verticalRotationLocked}
                  onPointerDown={(event) => beginVerticalRotationHold("negative", event)}
                  onPointerUp={() => endVerticalRotationHold("negative")}
                  onPointerCancel={clearVerticalRotationHold}
                  onPointerLeave={() => {
                    if (verticalRotationHoldRef.current.held) clearVerticalRotationHold();
                  }}
                >−</button>
                <button
                  type="button"
                  className={verticalRotationLocked ? "is-active" : ""}
                  disabled={!hasTrajectory}
                  onClick={() => {
                    clearHorizontalRotationHold();
                    clearVerticalRotationHold();
                    setVerticalRotationLocked((current) => {
                      const next = !current;
                      if (next) setHorizontalRotationLocked(false);
                      return next;
                    });
                  }}
                >
                  Vertical
                </button>
                <button
                  type="button"
                  aria-label="Rotate vertically positive"
                  disabled={!hasTrajectory || !verticalRotationLocked}
                  onPointerDown={(event) => beginVerticalRotationHold("positive", event)}
                  onPointerUp={() => endVerticalRotationHold("positive")}
                  onPointerCancel={clearVerticalRotationHold}
                  onPointerLeave={() => {
                    if (verticalRotationHoldRef.current.held) clearVerticalRotationHold();
                  }}
                >+</button>
              </div>
            </div>
          </section>
        </aside>

        <main className="wlv-wbv-scene-shell" aria-label="WBV 3D scene shell">
          <div
            className={`wlv-wbv-scene-frame ${hasTrajectory ? "has-trajectory-package" : ""}`}
          >
            {hasTrajectory ? (
              <>
              <WellboreTrajectoryRenderer
                renderPoints={renderPoints}
                activeManagedWellId={activeManagedWellId}
                contextTrajectories={contextTrajectories}
                onActivateWell={activateWellFromScene}
                boundingBox={viewerPackage?.bounding_box}
                depthUnit={depthUnit}
                viewerState={viewerState}
                viewPreset={viewPreset}
                viewCommandId={viewCommandId}
                viewAction={viewAction}
                viewActionId={viewActionId}
                horizontalRotationLocked={horizontalRotationLocked}
                verticalRotationLocked={verticalRotationLocked}
                onZoomPercentChange={setZoomPercent}
                onCameraViewChange={acceptWbvCameraView}
                cameraViewRestore={wbvCameraViewRestore}
                cameraViewRestoreId={wbvCameraViewRestoreId}
                onInteractionCommand={handleInteractionCommand}
                onLocalSelectedPoint={acceptExactLocalSelectedPoint}
                rotationCenterPickArmed={rotationCenterPickArmed}
                onRotationCenterEstablished={handleRotationCenterEstablished}
                selectedPoint={interaction?.selected_point_visible ? selectedPoint : null}
                selectionMode={interaction?.selection_mode ?? "none"}
                intervalDraftStart={interaction?.interval_visible ? interaction.interval_draft_start : null}
                savedInterval={interaction?.interval_visible ? interaction.saved_interval : null}
                trackValuesAlongWellbore={trackValuesAlongWellbore}
                showTrajectory={displayLayers.trajectory}
                showBoundingBox={viewerControls.boundingBox}
                showDepthLabels={viewerControls.depthLabels}
                showSurveyStations={viewerControls.surveyStations}
                showGroundPlane={viewerControls.groundPlane}
                showBottomGrid={viewerControls.bottomGrid}
                showTopGrid={viewerControls.topGrid}
                surfaceDatumLabel={wellInfoSurfaceDatumLabel}
                showAxes={false}
                showNorthArrow={viewerControls.northArrow}
                useSurfaceLighting={viewerControls.surfaceLighting}
                curveOverlays={rendererCurveOverlays}
                curveTracks={rendererCurveTracks}
                depthTracks={depthTrackRenderLayout}
                curveTrackSpacing={curveOverlayRenderPackage?.track_spacing ?? trackSpacing}
                showCurveOverlays={(() => {
                  const curveConfig = layerConfigFor(appliedLayerConfigs, "curve_overlays");
                  const curveLayerConfigured =
                    curveConfig.selected_item_ids.length > 0
                    || Boolean(curveConfig.source_product_id)
                    || rendererCurveOverlays.length > 0;
                  return curveLayerConfigured && curveConfig.visible;
                })()}
                formationTops={(previewFormationTopProducts?.products ?? []).filter((product) => previewFormationTopConfig.selected_item_ids.includes(product.product_id)).flatMap((product) => { const selectedTopIds = previewFormationTopConfig.appearance.selected_top_ids; return selectedTopIds == null ? product.tops : product.tops.filter((top) => selectedTopIds.includes(top.top_id)); })}
                formationTopAppearance={previewFormationTopConfig.appearance}
                showFormationTops={previewFormationTopConfig.visible}
                lithologyIntervals={(previewLithologyProducts?.products ?? []).filter((product) => previewLithologyConfig.selected_item_ids.includes(product.product_id)).flatMap((product) => { const selectedIntervalIds=previewLithologyConfig.appearance.selected_interval_ids; const selectedIntervals=selectedIntervalIds == null ? product.intervals : product.intervals.filter((interval)=>selectedIntervalIds.includes(interval.interval_id)); return selectedIntervals.map(lithologyRendererInterval); })}
                lithologyAppearance={{ opacity: previewLithologyConfig.appearance.opacity, radiusMultiplier: previewLithologyConfig.appearance.line_width, brightness: previewLithologyConfig.appearance.brightness ?? 1.35, patternScale: previewLithologyConfig.appearance.pattern_scale ?? 1.5, hideUnderlyingWellbore: previewLithologyConfig.appearance.hide_underlay ?? false }}
                showLithologyOverlay={previewLithologyConfig.visible}
                completionComponents={previewCompletionComponents}
                completionAppearance={{ color: previewCompletionConfig.appearance.color, opacity: previewCompletionConfig.appearance.opacity, sizeMultiplier: previewCompletionConfig.appearance.line_width, showLabels: previewCompletionConfig.appearance.show_labels, labelMode: previewCompletionConfig.appearance.label_mode ?? "name_md", labelColor: previewCompletionConfig.appearance.label_color ?? "#dce7ef", labelSize: previewCompletionConfig.appearance.label_size ?? 1, labelOffset: previewCompletionConfig.appearance.label_offset ?? 1, labelPosition: previewCompletionConfig.appearance.label_position ?? "right" }}
                showCompletions={previewCompletionConfig.visible}
                coreChunks={coreRenderChunks}
                coreTracks={coreTrackRenderLayout}
                trackLayoutTracks={trackPlacementRenderLayout}
                coreAppearance={{ color: previewCoreConfig.appearance.color ?? "#7b838a", brightness: previewCoreConfig.appearance.brightness ?? 1.35 }}
                showCoreOverlay={previewCoreConfig.visible}
                coreInspectionInterval={coreInspectionInterval}
                coreLocatorFocusInterval={coreLocatorFocusInterval}
                coreViewMode={coreViewMode}
                onCoreLocatorPick={handleCoreLocatorPick}
                viewProperties={previewViewProperties}
              />
              </>
            ) : null}

            <div
              className={`wlv-wbv-scene-message ${hasTrajectory ? "wlv-wbv-scene-message--package" : ""}`}
            >
              {state.loading ? (
                <>
                  <h2>Loading WBV session…</h2>
                  <p>Fetching backend-owned WBV availability state.</p>
                </>
              ) : state.error ? (
                <>
                  <h2>WBV session unavailable</h2>
                  <p>{state.error}</p>
                </>
              ) : !hasTrajectory ? (
                <>
                  <h2>Trajectory package not available</h2>
                  <p>
                    No backend-owned deviation survey / trajectory package is
                    available yet. WBV will not fabricate a 3D well path.
                  </p>
                </>
              ) : (
                <>
                  <h2>
                    {verticalTrajectory
                      ? "Vertical managed trajectory"
                      : "Managed trajectory loaded"}
                  </h2>
                  <p>
                    {renderPoints.length.toLocaleString()} managed trajectory
                    points are rendered. Click a survey point to inspect MD,
                    TVD, direction values, and provenance.
                  </p>
                </>
              )}
            </div>
          </div>
        </main>

        <aside
          className="wlv-wbv-panel wlv-wbv-panel--right"
          aria-label="WBV information panel"
        >
          <div className="wlv-wbv-panel-heading">
            <span>Inspection</span>
            <strong>Well &amp; Trajectory</strong><span className="wlv-wbv-active-well-label">ACTIVE WELLBORE: {selectedWellItem?.wellName ?? "None"}</span>
          </div>

          <section
            className="wlv-wbv-information-section wlv-wbv-information-section--well"
            aria-label="Well and trajectory information"
          >
            <div className="wlv-wbv-well-summary">
              <div className="wlv-wbv-well-summary__row">
                <span>Name</span>
                <strong>{viewerPackage?.well_name ?? session?.well_name ?? "Not loaded"}</strong>
              </div>
              <div className="wlv-wbv-well-summary__row">
                <span>Coordinate mode</span>
                <strong>{viewerPackage?.coordinate_mode ?? session?.coordinate_mode ?? "unavailable"}</strong>
              </div>
              <div className="wlv-wbv-well-summary__row">
                <span>Depth units</span>
                <div className="wlv-wbv-depth-unit-toggle" role="group" aria-label="Depth units">
                  {(["ft", "m"] as WbvDepthUnit[]).map((unit) => (
                    <button
                      type="button"
                      key={unit}
                      className={depthUnit === unit ? "is-active" : ""}
                      aria-pressed={depthUnit === unit}
                      disabled={depthUnitSaving || !viewerPackage?.managed_well_id}
                      onClick={() => void changeDepthUnit(unit)}
                    >
                      {unit}
                    </button>
                  ))}
                </div>
              </div>
              <div className="wlv-wbv-well-summary__row">
                <span>Angle units</span>
                <strong>{angleUnit}</strong>
              </div>
              <div className="wlv-wbv-well-summary__row">
                <span>Trajectory points</span>
                <strong>{trajectoryPointCount.toLocaleString()}</strong>
              </div>
            </div>

            <div className="wlv-wbv-trajectory-list" aria-label="Trajectory geometry">
              {[
                [
                  "Measured depth (MD)",
                  typeof endpoints.first?.md === "number" &&
                  typeof endpoints.last?.md === "number"
                    ? `${formatNumber(endpoints.first.md, 1)}–${formatNumber(endpoints.last.md, 1)} ${depthUnit}`
                    : "—",
                ],
                [
                  "True vertical depth (TVD)",
                  typeof endpoints.first?.tvd === "number" &&
                  typeof endpoints.last?.tvd === "number"
                    ? `${formatNumber(endpoints.first.tvd, 1)}–${formatNumber(endpoints.last.tvd, 1)} ${depthUnit}`
                    : "—",
                ],
                [
                  "X displacement",
                  typeof xRange.min === "number" && typeof xRange.max === "number"
                    ? `${formatNumber(xRange.min, 1)}–${formatNumber(xRange.max, 1)} ${depthUnit}`
                    : "—",
                ],
                [
                  "Y displacement",
                  typeof yRange.min === "number" && typeof yRange.max === "number"
                    ? `${formatNumber(yRange.min, 1)}–${formatNumber(yRange.max, 1)} ${depthUnit}`
                    : "—",
                ],
                [
                  "Vertical coordinate (Z)",
                  typeof zRange.min === "number" && typeof zRange.max === "number"
                    ? `${formatNumber(zRange.min, 1)}–${formatNumber(zRange.max, 1)} ${depthUnit}`
                    : "—",
                ],
                [
                  "Inclination",
                  typeof endpoints.last?.inclination === "number"
                    ? `${formatNumber(endpoints.last.inclination, 2)} ${angleUnit}`
                    : "—",
                ],
                [
                  "Azimuth",
                  typeof endpoints.last?.azimuth === "number"
                    ? `${formatNumber(endpoints.last.azimuth, 2)} ${angleUnit}`
                    : "—",
                ],
              ].map(([label, value]) => (
                <div className="wlv-wbv-trajectory-list__row" key={label}>
                  <span>{label}</span>
                  <strong>{value}</strong>
                </div>
              ))}
            </div>
          </section>

          <section
            className="wlv-wbv-information-section"
            aria-label="Selected trajectory point"
          >
            <div className="wlv-wbv-section-heading-row"><h2>Selected Point</h2><input aria-label="Show Selected Point selector" type="checkbox" checked={interaction?.selection_mode === "point"} disabled={interactionSaving} onChange={(event) => setSelectionMode(event.target.checked ? "point" : "none")} /></div>
            {interactionError ? <p className="wlv-wbv-interaction-error" role="alert">{interactionError}</p> : null}
            {selectedPoint ? (
              <div
                className="wlv-wbv-selected-point-table"
                role="table"
                aria-label="Selected point values"
              >
                <div className="wlv-wbv-selected-point-row wlv-wbv-selected-point-row--paired" role="row">
                  <span className="wlv-wbv-selected-point-label" role="rowheader">MD</span>
                  <span className="wlv-wbv-selected-point-value" role="cell">
                    {formatNumber(selectedPoint.md, 1)} {depthUnit}
                  </span>
                  <span className="wlv-wbv-selected-point-label" role="rowheader">TVD</span>
                  <span className="wlv-wbv-selected-point-value" role="cell">
                    {formatNumber(selectedPoint.tvd, 1)} {depthUnit}
                  </span>
                </div>
                <div className="wlv-wbv-selected-point-row" role="row">
                  <span className="wlv-wbv-selected-point-label" role="rowheader">Inclination</span>
                  <span className="wlv-wbv-selected-point-value" role="cell">
                    {formatNumber(selectedPoint.inclination, 2)} {angleUnit}
                  </span>
                </div>
                <div className="wlv-wbv-selected-point-row" role="row">
                  <span className="wlv-wbv-selected-point-label" role="rowheader">Azimuth</span>
                  <span className="wlv-wbv-selected-point-value" role="cell">
                    {formatNumber(selectedPoint.azimuth, 2)} {angleUnit}
                  </span>
                </div>
                <div className="wlv-wbv-selected-point-row" role="row">
                  <span className="wlv-wbv-selected-point-label" role="rowheader">Dogleg</span>
                  <span className="wlv-wbv-selected-point-value" role="cell">
                    {formatNumber(selectedPoint.dogleg_severity, 2)} {depthUnit === "m" ? "°/30 m" : "°/100 ft"}
                  </span>
                </div>
              </div>
            ) : (
              <p className="wlv-wbv-information-empty">
                Click the trajectory to inspect a point.
              </p>
            )}
            <label className="wlv-wbv-track-values-control">
              <input
                type="checkbox"
                checked={trackValuesAlongWellbore}
                onChange={(event) => setTrackValuesAlongWellbore(event.target.checked)}
                disabled={!selectedPoint}
              />
              <span>Track values along wellbore</span>
            </label>
          </section>

          <section className="wlv-wbv-information-section wlv-wbv-interval-section" aria-label="Interval selection">
            <div className="wlv-wbv-section-heading-row"><h2>Interval Selection</h2><input aria-label="Enable Interval Selection" type="checkbox" checked={interaction?.selection_mode === "interval"} disabled={interactionSaving} onChange={(event) => setSelectionMode(event.target.checked ? "interval" : "none")} /></div>
            {interaction?.saved_interval ? <div className="wlv-wbv-selected-point-table wlv-wbv-interval-table">
              <div className="wlv-wbv-selected-point-row"><span className="wlv-wbv-selected-point-label">Start MD</span><strong className="wlv-wbv-selected-point-value">{formatNumber(interaction.saved_interval.start.md, 1)} {depthUnit}</strong></div>
              <div className="wlv-wbv-selected-point-row"><span className="wlv-wbv-selected-point-label">End MD</span><strong className="wlv-wbv-selected-point-value">{formatNumber(interaction.saved_interval.end.md, 1)} {depthUnit}</strong></div>
              <div className="wlv-wbv-selected-point-row"><span className="wlv-wbv-selected-point-label">Length</span><strong className="wlv-wbv-selected-point-value">{formatNumber(interaction.saved_interval.base_md - interaction.saved_interval.top_md, 1)} {depthUnit}</strong></div>
            </div> : <p className="wlv-wbv-information-empty">{interaction?.interval_draft_start ? "Select the interval end." : "Select the interval start, then the end."}</p>}
            <div className="wlv-wbv-inline-action-row">
              <button type="button" className="wlv-wbv-control-button wlv-wbv-control-button--compact" disabled={!interaction?.saved_interval || interactionSaving} onClick={sendIntervalToLogViewer}>Send to Log Viewer as AOI</button>
              <button type="button" className="wlv-wbv-control-button wlv-wbv-control-button--compact" disabled={(!interaction?.saved_interval && !interaction?.interval_draft_start) || interactionSaving} onClick={() => { const id = state.viewerPackage?.managed_well_id; if (id) void interactionAuthorityRef.current?.runRevisioned((expectedRevision) => wbvInteractionApiV2.clearInterval(id, expectedRevision)); }}>Clear</button>
            </div>
          </section>

          <section
            className="wlv-wbv-information-section"
            aria-label="Survey QAQC summary"
          >
            <h2>Survey QAQC</h2>
            <div className="wlv-wbv-qaqc-summary">
              <strong>{qaqcDisplayState}</strong>
              <span>
                {qaqcFindingCount}{" "}
                {qaqcFindingCount === 1 ? "finding" : "findings"}
              </span>
            </div>
            {primaryQaqcFinding ? <p>{primaryQaqcFinding}</p> : null}
          </section>

        </aside>
      </div>

      {pendingPackageAction && selectedPublishedPackage ? (
        <div className="wlv-wbv-confirm-backdrop" role="presentation">
          <section className="wlv-wbv-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="wbv-package-action-title">
            <h2 id="wbv-package-action-title">{pendingPackageAction === "delete" ? "Delete this package permanently?" : "Archive this package?"}</h2>
            <p>{pendingPackageAction === "delete"
              ? "This permanently deletes the selected WBV package record and cannot be undone."
              : "This stops rendering the package, clears its WBV track assignments, and retains the published snapshot in Archived."}</p>
            {packageLifecycleError ? <p className="wlv-wbv-package-action-error" role="alert">{packageLifecycleError}</p> : null}
            <div>
              <button type="button" className="wlv-wbv-control-button" onClick={()=>{setPendingPackageAction(null);setPackageLifecycleError(null);}}>Cancel</button>
              <button
                type="button"
                className="wlv-wbv-control-button is-danger"
                disabled={publishedPresentationSaving}
                onClick={()=>void (pendingPackageAction === "delete"
                  ? deletePublishedPackage(selectedPublishedPackage)
                  : changePublishedPackageLifecycle(selectedPublishedPackage,"archive"))}
              >
                {publishedPresentationSaving ? "Working…" : pendingPackageAction === "delete" ? "Delete Permanently" : "Archive Package"}
              </button>
            </div>
          </section>
        </div>
      ) : null}

      <ExternalWindowPortal
          enabled={layerManagerOpen && layerManagerPoppedOut}
          windowName="multiviewer-wbv-manage-display-layers"
          title="MultiViewer — Manage Display Layers"
          storageKey="multiviewer.wbv.manageDisplayLayers.windowBounds.v1"
          defaultWidth={1180}
          defaultHeight={820}
          onExternalClose={() => {
            setLayerManagerPoppedOut(true);
            setLayerManagerOpen(false);
          }}
          onPopupBlocked={() => {
            setLayerManagerPoppedOut(true);
            setLayerManagerOpen(false);
          }}
        >
        {layerManagerOpen ? (
        <div className="wlv-wbv-modal-backdrop wlv-wbv-modal-backdrop--floating" role="presentation">
          <section
            ref={layerManagerRef}
            className={["wlv-wbv-layer-manager-modal", layerManagerExpanded ? "is-expanded" : ""].filter(Boolean).join(" ")}
            role="dialog"
            aria-modal="false"
            aria-labelledby="wbv-layer-manager-title"
            style={layerManagerPoppedOut
              ? { left: 8, top: 8, width: "calc(100vw - 16px)", height: "calc(100vh - 16px)", maxHeight: "calc(100vh - 16px)", resize: "none" }
              : { left: layerManagerRect.left, top: layerManagerRect.top, width: layerManagerRect.width, height: layerManagerRect.height }}
          >
            <header className="wlv-wbv-layer-manager-header" onPointerDown={layerManagerPoppedOut ? undefined : beginLayerManagerDrag}>
              <div><h2 id="wbv-layer-manager-title">Manage Display Layers</h2></div>
                <label className="wlv-wbv-layer-well-selector">
                  <span>Edit display layers for</span>
                  <select disabled={layerEditorWellLoading} value={layerEditorWellId ?? activeManagedWellId ?? ""} onChange={(event) => {
                    const id = event.target.value;
                    void loadLayerEditorWell(id);
                  }}>
                    {displayedWellList.map((entry) => <option key={entry.managedWellId} value={entry.managedWellId}>{entry.wellName}</option>)}
                  </select>
                </label>
              <div className="wlv-wbv-layer-manager-header-actions">
                {!layerManagerPoppedOut ? <button type="button" className="wlv-wbv-control-button" onClick={toggleLayerManagerExpanded}>{layerManagerExpanded ? "Restore" : "Expand"}</button> : null}
                <button type="button" className="wlv-wbv-icon-button" aria-label="Close display-layer manager" onClick={() => setLayerManagerOpen(false)}>×</button>
              </div>
            </header>
            <nav className="wlv-wbv-layer-tabs" aria-label="Display layer tabs">
              {([
                ["view_properties", "View Properties"], ["track_layout", "Track Layout"], ["formation_tops", "Formation Tops"], ["lithology_intervals", "Lithology"], ["core_images", "Core"], ["casing_hole_sections", "Casing / Hole"],
                ["completions", "Completions"], ["curve_overlays", "Curve Overlays"], ["borehole_imagery", "Borehole Imagery"],
              ] as Array<[WbvManagerTab, string]>).map(([key,label]) => <button type="button" key={key} className={activeLayerTab===key?"is-active":""} onClick={() => setActiveLayerTab(key)}>{label}</button>)}
            </nav>
            <div
              className={["wlv-wbv-layer-manager-body", activeLayerTab === "track_layout" ? "is-track-layout" : "", activeLayerTab === "curve_overlays" ? "is-curve-overlays" : "", activeLayerTab === "formation_tops" ? "is-formation-tops" : "", activeLayerTab === "lithology_intervals" ? "is-lithology" : "", activeLayerTab === "core_images" ? "is-core-images" : "", activeLayerTab === "completions" ? "is-completions" : ""].filter(Boolean).join(" ")}
              style={activeLayerTab === "completions" ? { gridTemplateColumns: "250px 560px 390px", justifyContent: "start", alignItems: "stretch" } : undefined}
            >
              {(() => {
                if (activeLayerTab === "view_properties") {
                  const updateSection = <K extends keyof WbvViewProperties>(section: K, patch: Partial<WbvViewProperties[K]>) => setDraftViewProperties((current) => ({ ...current, [section]: { ...current[section], ...patch } }));
                  const propertyLabels: Array<[keyof WbvViewProperties, string]> = [["trajectory","Trajectory"],["boundingBox","Bounding Box"],["depthLabels","Depth Labels"],["surveyStations","Survey Stations"],["groundPlane","Ground Plane"],["grids","Bottom / Top Grids"],["shading","3D Shading"]];
                  return <>
                    <aside className="wlv-wbv-view-properties-rail" aria-label="View property categories">
                      <div className="wlv-wbv-view-properties-rail-heading">View Properties</div>
                      <div className="wlv-wbv-view-properties-nav">
                        {propertyLabels.map(([key,label]) => (
                          <button
                            type="button"
                            key={key}
                            className={selectedViewProperty===key?"is-current":""}
                            onClick={()=>setSelectedViewProperty(key)}
                          >
                            <span>{label}</span>
                          </button>
                        ))}
                      </div>
                    </aside>
                    <section className="wlv-wbv-view-properties-editor">
                      <header className="wlv-wbv-view-properties-header">
                        <div>
                          <h3>{propertyLabels.find(([key])=>key===selectedViewProperty)?.[1]}</h3>
                          <p>Appearance and display settings</p>
                        </div>
                      </header>
                      <div className="wlv-wbv-view-properties-content">
                        {selectedViewProperty==="trajectory"?<div className="wlv-wbv-property-card"><h4>Appearance</h4><div className="wlv-wbv-property-grid" style={{gridTemplateColumns:"minmax(220px,1fr) minmax(340px,1.55fr) minmax(140px,.7fr) minmax(140px,.7fr)"}}><label className="wlv-wbv-field"><span>Color</span><div style={{display:"flex",alignItems:"center",gap:8}}><button type="button" aria-label="Use custom wellbore color" aria-pressed={(draftViewProperties.trajectory.materialMode ?? "color")==="color"} title="Use selected wellbore color" onClick={()=>updateSection("trajectory",{materialMode:"color"})} style={{width:42,height:42,padding:4,borderRadius:6,border:(draftViewProperties.trajectory.materialMode ?? "color")==="color"?"2px solid #67d599":"1px solid #53616b",background:"#10171c",cursor:"pointer"}}><span aria-hidden="true" style={{display:"block",width:"100%",height:"100%",borderRadius:3,background:draftViewProperties.trajectory.color}}/></button><input type="color" aria-label="Wellbore custom color" value={draftViewProperties.trajectory.color} onChange={e=>updateSection("trajectory",{color:e.target.value,materialMode:"color"})}/></div></label><div className="wlv-wbv-field"><span>Gray Metallic</span><div style={{display:"flex",alignItems:"center",gap:8,flexWrap:"wrap"}}><button type="button" aria-label="Use light silver metallic wellbore" aria-pressed={(draftViewProperties.trajectory.materialMode ?? "color")==="gray_metallic"&&(draftViewProperties.trajectory.metallicTone ?? "silver")==="light_silver"} title="Light Silver" onClick={()=>updateSection("trajectory",{materialMode:"gray_metallic",metallicTone:"light_silver"})} style={{width:42,height:42,padding:4,borderRadius:6,border:(draftViewProperties.trajectory.materialMode ?? "color")==="gray_metallic"&&(draftViewProperties.trajectory.metallicTone ?? "silver")==="light_silver"?"2px solid #67d599":"1px solid #53616b",background:"#10171c",cursor:"pointer"}}><span aria-hidden="true" style={{display:"block",width:"100%",height:"100%",borderRadius:3,background:"linear-gradient(90deg,#ffffff 0%,#d7dde0 25%,#f7f9fa 52%,#aab3b8 78%,#e6ecef 100%)"}}/></button><button type="button" aria-label="Use silver metallic wellbore" aria-pressed={(draftViewProperties.trajectory.materialMode ?? "color")==="gray_metallic"&&(draftViewProperties.trajectory.metallicTone ?? "silver")==="silver"} title="Silver" onClick={()=>updateSection("trajectory",{materialMode:"gray_metallic",metallicTone:"silver"})} style={{width:42,height:42,padding:4,borderRadius:6,border:(draftViewProperties.trajectory.materialMode ?? "color")==="gray_metallic"&&(draftViewProperties.trajectory.metallicTone ?? "silver")==="silver"?"2px solid #67d599":"1px solid #53616b",background:"#10171c",cursor:"pointer"}}><span aria-hidden="true" style={{display:"block",width:"100%",height:"100%",borderRadius:3,background:"linear-gradient(90deg,#eef2f4 0%,#9ca7ad 40%,#e7ecef 70%,#7e898f 100%)"}}/></button><button type="button" aria-label="Use steel metallic wellbore" aria-pressed={(draftViewProperties.trajectory.materialMode ?? "color")==="gray_metallic"&&(draftViewProperties.trajectory.metallicTone ?? "silver")==="steel"} title="Steel" onClick={()=>updateSection("trajectory",{materialMode:"gray_metallic",metallicTone:"steel"})} style={{width:42,height:42,padding:4,borderRadius:6,border:(draftViewProperties.trajectory.materialMode ?? "color")==="gray_metallic"&&(draftViewProperties.trajectory.metallicTone ?? "silver")==="steel"?"2px solid #67d599":"1px solid #53616b",background:"#10171c",cursor:"pointer"}}><span aria-hidden="true" style={{display:"block",width:"100%",height:"100%",borderRadius:3,background:"linear-gradient(90deg,#c5cdd1 0%,#7f898f 38%,#b6c0c5 68%,#667078 100%)"}}/></button><button type="button" aria-label="Use gunmetal metallic wellbore" aria-pressed={(draftViewProperties.trajectory.materialMode ?? "color")==="gray_metallic"&&(draftViewProperties.trajectory.metallicTone ?? "silver")==="gunmetal"} title="Gunmetal" onClick={()=>updateSection("trajectory",{materialMode:"gray_metallic",metallicTone:"gunmetal"})} style={{width:42,height:42,padding:4,borderRadius:6,border:(draftViewProperties.trajectory.materialMode ?? "color")==="gray_metallic"&&(draftViewProperties.trajectory.metallicTone ?? "silver")==="gunmetal"?"2px solid #67d599":"1px solid #53616b",background:"#10171c",cursor:"pointer"}}><span aria-hidden="true" style={{display:"block",width:"100%",height:"100%",borderRadius:3,background:"linear-gradient(90deg,#899299 0%,#4e565c 38%,#7a848a 68%,#394046 100%)"}}/></button><button type="button" aria-label="Use graphite metallic wellbore" aria-pressed={(draftViewProperties.trajectory.materialMode ?? "color")==="gray_metallic"&&(draftViewProperties.trajectory.metallicTone ?? "silver")==="graphite"} title="Graphite" onClick={()=>updateSection("trajectory",{materialMode:"gray_metallic",metallicTone:"graphite"})} style={{width:42,height:42,padding:4,borderRadius:6,border:(draftViewProperties.trajectory.materialMode ?? "color")==="gray_metallic"&&(draftViewProperties.trajectory.metallicTone ?? "silver")==="graphite"?"2px solid #67d599":"1px solid #53616b",background:"#10171c",cursor:"pointer"}}><span aria-hidden="true" style={{display:"block",width:"100%",height:"100%",borderRadius:3,background:"linear-gradient(90deg,#666d72 0%,#2f3438 38%,#555c61 68%,#202428 100%)"}}/></button></div></div><label className="wlv-wbv-field"><span>Thickness</span><input type="number" min="0.25" max="6" step="0.25" value={draftViewProperties.trajectory.thickness} onChange={e=>updateSection("trajectory",{thickness:Number(e.target.value)})}/></label><label className="wlv-wbv-field"><span>Opacity</span><input type="number" min="0" max="1" step="0.05" value={draftViewProperties.trajectory.opacity} onChange={e=>updateSection("trajectory",{opacity:Number(e.target.value)})}/></label></div><span style={{display:"none"}}>{/* WBV_TRAJECTORY_METALLIC_SHADE_PALETTE_V1_0_0 */}</span></div>:null}
                        {selectedViewProperty==="boundingBox"?<div className="wlv-wbv-property-card"><h4>Lines</h4><div className="wlv-wbv-property-grid is-three"><label className="wlv-wbv-field">Line color<input type="color" value={draftViewProperties.boundingBox.color} onChange={e=>updateSection("boundingBox",{color:e.target.value})}/></label><label className="wlv-wbv-field">Line thickness<input type="number" min="0.5" max="5" step="0.5" value={draftViewProperties.boundingBox.thickness} onChange={e=>updateSection("boundingBox",{thickness:Number(e.target.value)})}/></label><label className="wlv-wbv-field">Opacity<input type="number" min="0" max="1" step="0.05" value={draftViewProperties.boundingBox.opacity} onChange={e=>updateSection("boundingBox",{opacity:Number(e.target.value)})}/></label></div></div>:null}
                        {selectedViewProperty==="depthLabels"?<div className="wlv-wbv-property-card"><h4>Labels</h4><div className="wlv-wbv-property-grid"><label className="wlv-wbv-field">Text color<input type="color" value={draftViewProperties.depthLabels.color} onChange={e=>updateSection("depthLabels",{color:e.target.value})}/></label><label className="wlv-wbv-field">Label size<input type="number" min="0.5" max="3" step="0.1" value={draftViewProperties.depthLabels.size} onChange={e=>updateSection("depthLabels",{size:Number(e.target.value)})}/></label><label className="wlv-wbv-field">Label interval <small>0 = automatic</small><input type="number" min="0" step="10" value={draftViewProperties.depthLabels.interval} onChange={e=>updateSection("depthLabels",{interval:Number(e.target.value)})}/></label><label className="wlv-wbv-field">Offset from trajectory<input type="number" min="0" max="2" step="0.05" value={draftViewProperties.depthLabels.offset} onChange={e=>updateSection("depthLabels",{offset:Number(e.target.value)})}/></label></div></div>:null}
                        {selectedViewProperty==="surveyStations"?<><div className="wlv-wbv-property-card"><h4>Marker</h4><div className="wlv-wbv-property-grid"><label className="wlv-wbv-field">Shape<select value={draftViewProperties.surveyStations.shape} onChange={e=>updateSection("surveyStations",{shape:e.target.value as WbvViewProperties["surveyStations"]["shape"]})}><option value="circle">Circle</option><option value="square">Square</option><option value="diamond">Diamond</option><option value="cross">Cross</option></select></label><label className="wlv-wbv-field">Size<input type="number" min="0.25" max="8" step="0.25" value={draftViewProperties.surveyStations.size} onChange={e=>updateSection("surveyStations",{size:Number(e.target.value)})}/></label><label className="wlv-wbv-field">Color<input type="color" value={draftViewProperties.surveyStations.color} onChange={e=>updateSection("surveyStations",{color:e.target.value})}/></label><label className="wlv-wbv-field">Opacity<input type="number" min="0" max="1" step="0.05" value={draftViewProperties.surveyStations.opacity} onChange={e=>updateSection("surveyStations",{opacity:Number(e.target.value)})}/></label></div></div><div className="wlv-wbv-property-card"><h4>Orientation</h4><div className="wlv-wbv-segmented-control" role="group" aria-label="Survey station orientation"><button type="button" className={draftViewProperties.surveyStations.orientation==="along"?"is-active":""} onClick={()=>updateSection("surveyStations",{orientation:"along"})}>Along wellbore</button><button type="button" className={draftViewProperties.surveyStations.orientation==="across"?"is-active":""} onClick={()=>updateSection("surveyStations",{orientation:"across"})}>Across wellbore</button></div></div></>:null}
                        
                        {selectedViewProperty==="groundPlane"?<div className="wlv-wbv-property-card"><h4>Surface</h4><div className="wlv-wbv-property-grid is-three"><label className="wlv-wbv-field">Color<input type="color" value={draftViewProperties.groundPlane.color} onChange={e=>updateSection("groundPlane",{color:e.target.value})}/></label><label className="wlv-wbv-field">Size<input type="number" min="0.5" max="3" step="0.1" value={draftViewProperties.groundPlane.size} onChange={e=>updateSection("groundPlane",{size:Number(e.target.value)})}/></label><label className="wlv-wbv-field">Opacity<input type="number" min="0" max="1" step="0.05" value={draftViewProperties.groundPlane.opacity} onChange={e=>updateSection("groundPlane",{opacity:Number(e.target.value)})}/></label></div></div>:null}
                        {selectedViewProperty==="grids"?<div className="wlv-wbv-property-card"><h4>Grid lines</h4><div className="wlv-wbv-property-grid"><label className="wlv-wbv-field">Grid color<input type="color" value={draftViewProperties.grids.color} onChange={e=>updateSection("grids",{color:e.target.value})}/></label><label className="wlv-wbv-field">Line thickness<input type="number" min="0.5" max="5" step="0.5" value={draftViewProperties.grids.thickness} onChange={e=>updateSection("grids",{thickness:Number(e.target.value)})}/></label><label className="wlv-wbv-field">Grid divisions<input type="number" min="2" max="40" step="1" value={draftViewProperties.grids.spacing} onChange={e=>updateSection("grids",{spacing:Number(e.target.value)})}/></label><label className="wlv-wbv-field">Opacity<input type="number" min="0" max="1" step="0.05" value={draftViewProperties.grids.opacity} onChange={e=>updateSection("grids",{opacity:Number(e.target.value)})}/></label></div></div>:null}
                        {selectedViewProperty==="shading"?<div className="wlv-wbv-property-card"><h4>Lighting</h4><div className="wlv-wbv-property-grid is-three"><label className="wlv-wbv-field">Shading intensity<input type="number" min="0" max="2" step="0.05" value={draftViewProperties.shading.intensity} onChange={e=>updateSection("shading",{intensity:Number(e.target.value)})}/></label><label className="wlv-wbv-field">Ambient light<input type="number" min="0" max="3" step="0.05" value={draftViewProperties.shading.ambient} onChange={e=>updateSection("shading",{ambient:Number(e.target.value)})}/></label><label className="wlv-wbv-field">Directional light<input type="number" min="0" max="3" step="0.05" value={draftViewProperties.shading.directional} onChange={e=>updateSection("shading",{directional:Number(e.target.value)})}/></label></div></div>:null}
                      </div>
                    </section>
                  </>;
                }
                if (activeLayerTab === "track_layout") {
                  const tracks = [...(wbvTrackLayout?.tracks ?? [])].sort((first, second) => first.display_order - second.display_order);
                  const selectedTrack = tracks.find((track) => track.track_uid === selectedLayoutTrackUid) ?? tracks[0] ?? null;
                  const updateSelected = (patch: Partial<WbvLayoutTrack>) => {
                    if (!selectedTrack) return;
                    void runLayoutCommand({ command: "update_track", track_uid: selectedTrack.track_uid, ...patch });
                  };
                  const samePositionTracks = selectedTrack
                    ? tracks.filter((track) => track.position === selectedTrack.position).sort((first, second) => first.display_order - second.display_order)
                    : [];
                  const isClosestToWellbore = selectedTrack
                    ? samePositionTracks[0]?.track_uid === selectedTrack.track_uid
                    : false;
                  return <>
                    <section className="wlv-wbv-manager-inventory-panel wlv-wbv-track-layout-list">
                      <div className="wlv-wbv-manager-panel-title"><div><h3>WBV Tracks</h3><span>{tracks.length} tracks</span></div></div>
                      <div className="wlv-wbv-track-toolbar">
                        <select value={newLayoutTrackType} onChange={(event)=>setNewLayoutTrackType(event.target.value as WbvLayoutTrack["track_type"])}><option value="curve">Curve</option><option value="depth">Depth</option><option value="formation_tops">Formation Tops</option><option value="lithology">Lithology</option><option value="core">Core</option><option value="casing_hole">Casing / Hole</option><option value="completions">Completions</option><option value="borehole_imagery">Borehole Imagery</option></select>
                        <button type="button" className="wlv-wbv-control-button is-primary" disabled={layoutCommandSaving} onClick={()=>void runLayoutCommand({command:"add_track",track_type:newLayoutTrackType})}>+ Add Track</button>
                      </div>
                      <div className="wlv-wbv-track-list">{tracks.map((track)=><button type="button" key={track.track_uid} className={track.track_uid===selectedTrack?.track_uid?"is-current":""} onClick={()=>setSelectedLayoutTrackUid(track.track_uid)}><span>{track.display_order+1}</span><strong>{track.display_name}</strong><small>{track.track_type.replace(/_/g, " ")} · {track.position}</small></button>)}</div>
                    </section>
                    <section className="wlv-wbv-manager-properties-panel wlv-wbv-simple-track-properties">
                      <div className="wlv-wbv-manager-panel-title"><div><h3>Track Settings</h3><span>{selectedTrack?.display_name ?? "Select a track"}</span></div></div>
                      {selectedTrack?<div className="wlv-wbv-properties-scroll">
                        <label className="wlv-wbv-check-row"><input type="checkbox" checked={selectedTrack.visible} onChange={(e)=>updateSelected({visible:e.target.checked})}/><span>Show track</span></label>
                        <label className="wlv-wbv-field">Track name<input key={`${selectedTrack.track_uid}-name-${selectedTrack.display_name}`} defaultValue={selectedTrack.display_name} onBlur={(e)=>{const value=e.target.value.trim();if(value&&value!==selectedTrack.display_name)updateSelected({display_name:value});}}/></label>
                        <div className="wlv-wbv-inline-fields"><label className="wlv-wbv-field">Track type<select value={selectedTrack.track_type} onChange={(e)=>updateSelected({track_type:e.target.value as WbvLayoutTrack["track_type"]})}><option value="curve">Curve</option><option value="depth">Depth</option><option value="formation_tops">Formation Tops</option><option value="lithology">Lithology</option><option value="core">Core</option><option value="casing_hole">Casing / Hole</option><option value="completions">Completions</option><option value="borehole_imagery">Borehole Imagery</option></select></label><label className="wlv-wbv-field">Position<select value={selectedTrack.position} onChange={(e)=>updateSelected({position:e.target.value as WbvLayoutTrack["position"]})}><option value="right">Right</option><option value="left">Left</option><option value="center">Center</option></select></label></div>
                        <div className="wlv-wbv-inline-fields">{isClosestToWellbore?<label className="wlv-wbv-field">Distance from wellbore<input key={`${selectedTrack.track_uid}-distance-${selectedTrack.distance_from_wellbore}`} type="number" min="0" step="0.05" defaultValue={selectedTrack.distance_from_wellbore} onBlur={(e)=>updateSelected({distance_from_wellbore:Number(e.target.value)})}/></label>:<label className="wlv-wbv-field">Gap from previous track<input key={`${selectedTrack.track_uid}-gap-${selectedTrack.previous_track_gap}`} type="number" min="0" step="0.05" defaultValue={selectedTrack.previous_track_gap} onBlur={(e)=>updateSelected({previous_track_gap:Number(e.target.value)})}/></label>}<label className="wlv-wbv-field">Width<input key={`${selectedTrack.track_uid}-width-${selectedTrack.width}`} type="number" min="0.1" step="0.05" defaultValue={selectedTrack.width} onBlur={(e)=>updateSelected({width:Number(e.target.value)})}/></label></div>
                        <div className="wlv-wbv-inline-fields">
                          <label className="wlv-wbv-field">Track background<select value={selectedTrack.background_mode} onChange={(e)=>updateSelected({background_mode:e.target.value as WbvLayoutTrack["background_mode"]})}><option value="transparent">Transparent</option><option value="solid">Solid</option></select></label>
                          <label className="wlv-wbv-field">Background color<input type="color" value={selectedTrack.background_color} disabled={selectedTrack.background_mode==="transparent"} onChange={(e)=>updateSelected({background_color:e.target.value})}/></label>
                        </div>
                        <label className="wlv-wbv-check-row"><input type="checkbox" checked={selectedTrack.outline_visible} onChange={(e)=>updateSelected({outline_visible:e.target.checked})}/><span>Track outline</span></label>
                        {selectedTrack.track_type==="depth"?<>
                          <div className="wlv-wbv-inline-fields">
                            <label className="wlv-wbv-field">Depth type<select value={selectedTrack.depth_type} onChange={(e)=>updateSelected({depth_type:e.target.value as WbvLayoutTrack["depth_type"]})}><option value="MD">MD</option><option value="TVD">TVD</option><option value="TVDSS">TVDSS</option></select></label>
                            <label className="wlv-wbv-field">Depth increment<input key={`${selectedTrack.track_uid}-depth-increment-${selectedTrack.depth_increment}`} type="number" min="0.000001" step="10" defaultValue={selectedTrack.depth_increment} onBlur={(e)=>updateSelected({depth_increment:Number(e.target.value)})}/></label>
                          </div>
                          <div className="wlv-wbv-inline-fields">
                            <label className="wlv-wbv-field">Label increment<input key={`${selectedTrack.track_uid}-label-increment-${selectedTrack.label_increment}`} type="number" min="0.000001" step="10" defaultValue={selectedTrack.label_increment} onBlur={(e)=>updateSelected({label_increment:Number(e.target.value)})}/></label>
                            <label className="wlv-wbv-field">Label size<input key={`${selectedTrack.track_uid}-label-size-${selectedTrack.label_size}`} type="number" min="0.1" step="0.1" defaultValue={selectedTrack.label_size} onBlur={(e)=>updateSelected({label_size:Number(e.target.value)})}/></label>
                          </div>
                          <label className="wlv-wbv-check-row"><input type="checkbox" checked={selectedTrack.show_depth_units} onChange={(e)=>updateSelected({show_depth_units:e.target.checked})}/><span>Show units</span></label>
                          {selectedTrack.depth_type==="TVDSS"?<div className="wlv-wbv-warning-inline">Precise surface elevation/datum is not available. TVDSS is currently referenced to TVD.</div>:null}
                        </>:<label className="wlv-wbv-field">Track grid<select value={selectedTrack.grid_mode} onChange={(e)=>updateSelected({grid_mode:e.target.value as WbvLayoutTrack["grid_mode"]})}><option value="off">Off</option><option value="linear">Linear</option><option value="logarithmic">Logarithmic</option></select></label>}
                        <label className="wlv-wbv-field">Track opacity<input key={`${selectedTrack.track_uid}-opacity-${selectedTrack.opacity}`} type="number" min="0" max="1" step="0.05" defaultValue={selectedTrack.opacity} onBlur={(e)=>updateSelected({opacity:Number(e.target.value)})}/></label>
                        <div className="wlv-wbv-inline-action-row"><button type="button" className="wlv-wbv-control-button" disabled={layoutCommandSaving||selectedTrack.display_order===0} onClick={()=>void runLayoutCommand({command:"move_up",track_uid:selectedTrack.track_uid})}>Move Up</button><button type="button" className="wlv-wbv-control-button" disabled={layoutCommandSaving||selectedTrack.display_order===tracks.length-1} onClick={()=>void runLayoutCommand({command:"move_down",track_uid:selectedTrack.track_uid})}>Move Down</button><button type="button" className="wlv-wbv-control-button" disabled={layoutCommandSaving} onClick={()=>void runLayoutCommand({command:"duplicate_track",track_uid:selectedTrack.track_uid})}>Duplicate</button><button type="button" className="wlv-wbv-control-button is-danger" disabled={layoutCommandSaving} onClick={()=>void runLayoutCommand({command:"delete_track",track_uid:selectedTrack.track_uid})}>Delete</button></div>
                      </div>:<div className="wlv-wbv-empty-state">Add a track.</div>}
                    </section>
                  </>;
                }
                const config = layerConfigFor(draftLayerConfigs, activeLayerTab);
                if (activeLayerTab === "curve_overlays") {
                  const selectedPackage = selectedPublishedPackage;
                  const presentation = publishedPresentationDraft;
                  const tracks = (selectedPackage?.published_snapshot.tracks ?? []).filter((track) => track.assignments.length > 0);
                  const curveDestinations = (wbvTrackLayout?.tracks ?? []).filter((item) => item.track_type === "curve");
                  const visiblePackages = publishedOverlayPackages.filter((item) =>
                    publishedPackageView === "archived" ? item.status === "archived" : item.status !== "archived",
                  );
                  const trackOverride = (trackUid: string) =>
                    presentation?.tracks.find((item) => item.track_uid === trackUid) ?? {
                      track_uid: trackUid,
                      destination_track_uid: null,
                      visible: true,
                      geometry_type: "radial_panel",
                      radial_lane: null,
                      radial_offset: null,
                      angular_position_deg: null,
                      radial_width: null,
                      thickness: null,
                      orientation_mode: "follow_trajectory",
                      opacity: null,
                      label_visible: null,
                    };
                  const curveOverride = (assignmentUid: string) =>
                    presentation?.curves.find((item) => item.assignment_uid === assignmentUid) ?? {
                      assignment_uid: assignmentUid,
                      visible: null,
                      color: null,
                      opacity: null,
                      line_width: null,
                      radial_exaggeration: null,
                      label_visible: null,
                      label_content: null,
                      label_anchor: null,
                      label_custom_md: null,
                      label_size: null,
                      label_weight: null,
                      label_alignment: null,
                      label_position: null,
                      label_horizontal_adjustment: null,
                      label_vertical_adjustment: null,
                      scale_color: null,
                      scale_opacity: null,
                      scale_line_width: null,
                      scale_size: null,
                    };
                  const updateTrackOverride = (trackUid: string, patch: Partial<ReturnType<typeof trackOverride>>) => {
                    if (!presentation) return;
                    const existing = trackOverride(trackUid);
                    setPublishedPresentationDraft({
                      ...presentation,
                      tracks: [...presentation.tracks.filter((item) => item.track_uid !== trackUid), { ...existing, ...patch }],
                    });
                  };
                  const updateCurveOverride = (assignmentUid: string, patch: Partial<ReturnType<typeof curveOverride>>) => {
                    if (!presentation) return;
                    const existing = curveOverride(assignmentUid);
                    setPublishedPresentationDraft({
                      ...presentation,
                      curves: [...presentation.curves.filter((item) => item.assignment_uid !== assignmentUid), { ...existing, ...patch }],
                    });
                  };
                  const allPublishedCurves = tracks.flatMap((track) => track.assignments);
                  const selectedLabelCurve = allPublishedCurves.find((curve) => curve.assignment_uid === curveLabelEditorAssignmentUid) ?? null;
                  const selectedLabelOverride = selectedLabelCurve ? curveOverride(selectedLabelCurve.assignment_uid) : null;
                  const selectedLabelRenderedCurve = selectedLabelCurve ? curveOverlayRenderPackage?.curves.find((curve) => curve.assignment_uid === selectedLabelCurve.assignment_uid) ?? null : null;
                  const packageDisplayName = (item: WbvOverlayPackage) => {
                    const packageTracks = item.published_snapshot.tracks.filter((track) => track.assignments.length > 0);
                    const mnemonics = packageTracks.flatMap((track) => track.assignments.map((curve) => curve.observed_mnemonic)).slice(0, 4);
                    const wellName = viewerPackage?.well_name ?? session?.well_name ?? "Published curves";
                    return `${wellName} — ${mnemonics.length ? mnemonics.join(" / ") : "Curve package"}`;
                  };
                  const availableDestinations = (trackUid: string) => {
                    const currentDestination = trackOverride(trackUid).destination_track_uid;
                    const usedByOtherTracks = new Set(
                      tracks
                        .filter((track) => track.track_uid !== trackUid)
                        .map((track) => trackOverride(track.track_uid).destination_track_uid)
                        .filter((uid): uid is string => Boolean(uid)),
                    );
                    return curveDestinations.filter(
                      (destination) => destination.track_uid === currentDestination || !usedByOtherTracks.has(destination.track_uid),
                    );
                  };
                  return <>
                    <section className="wlv-wbv-manager-inventory-panel wlv-wbv-published-package-panel">
                      <div className="wlv-wbv-manager-panel-title"><div><h3>Published Curve Packages</h3><span>{visiblePackages.length} shown</span></div><div className="wlv-wbv-package-filters"><button type="button" className={publishedPackageView==="available"?"is-active":""} onClick={()=>setPublishedPackageView("available")}>Available</button><button type="button" className={publishedPackageView==="archived"?"is-active":""} onClick={()=>setPublishedPackageView("archived")}>Archived</button></div></div>
                      <div className="wlv-wbv-published-package-cards">
                        {visiblePackages.map((item) => {
                          const itemTracks = item.published_snapshot.tracks.filter((track) => track.assignments.length > 0);
                          const itemCurveCount = itemTracks.reduce((total, track) => total + track.assignments.length, 0);
                          const isSelected = item.package_uid === selectedPublishedPackageUid;
                          return <article key={item.package_uid} className={isSelected ? "is-current" : ""}>
                            <button type="button" className="wlv-wbv-package-card-heading" onClick={()=>setSelectedPublishedPackageUid(item.package_uid)}>
                              <span className="wlv-wbv-package-status">{item.status}</span>
                              <strong>{packageDisplayName(item)}</strong>
                              <small>{itemTracks.length} curve tracks · {itemCurveCount} curves · WDV revision {item.source_wdv_revision}</small>
                            </button>
                          </article>;
                        })}
                        {visiblePackages.length===0?<div className="wlv-wbv-empty-state">{publishedPackageView==="archived"?"No archived packages.":"No WDV curve package has been published to this well."}</div>:null}
                      </div>
                    </section>
                    <section className="wlv-wbv-manager-properties-panel wlv-wbv-published-post-panel">
                      <div className="wlv-wbv-manager-panel-title"><div><h3>WBV Post-production</h3><span>{selectedPackage ? packageDisplayName(selectedPackage) : "Select a package"}</span></div></div>
                      {selectedPackage && presentation ? <div className="wlv-wbv-properties-scroll">
                        <div className="wlv-wbv-post-package-controls">
                          <label className="wlv-wbv-check-row"><input type="checkbox" checked={presentation.package_visible} onChange={(event)=>setPublishedPresentationDraft({...presentation,package_visible:event.target.checked})}/><span>Show published package</span></label>
                          <div className="wlv-wbv-inline-fields">
                            <label className="wlv-wbv-field">Depth clip minimum<input type="number" step="any" value={presentation.depth_clip_min ?? ""} onChange={(event)=>setPublishedPresentationDraft({...presentation,depth_clip_min:event.target.value===""?null:Number(event.target.value)})}/></label>
                            <label className="wlv-wbv-field">Depth clip maximum<input type="number" step="any" value={presentation.depth_clip_max ?? ""} onChange={(event)=>setPublishedPresentationDraft({...presentation,depth_clip_max:event.target.value===""?null:Number(event.target.value)})}/></label>
                          </div>
                        </div>
                        <div className="wlv-wbv-post-track-list">
                          {tracks.map((track) => {
                            const destinationUid = trackOverride(track.track_uid).destination_track_uid;
                            const destination = curveDestinations.find((item)=>item.track_uid===destinationUid);
                            return <fieldset className="wlv-wbv-combined-curve-track-card" key={track.track_uid}>
                              <legend>{track.track_name || "Curve track"}</legend>
                              <div className="wlv-wbv-combined-track-header">
                                <div><strong>{track.assignments.map((curve)=>curve.observed_mnemonic).join(" · ")}</strong><span>{destination ? `Displayed in ${destination.display_name}` : "Not assigned"}</span></div>
                                <label>Display in<select value={destinationUid ?? ""} onChange={(event)=>updateTrackOverride(track.track_uid,{destination_track_uid:event.target.value||null})}><option value="">Not displayed</option>{availableDestinations(track.track_uid).map((item)=><option key={item.track_uid} value={item.track_uid}>{item.display_name} · {item.position}</option>)}</select></label>
                              </div>
                              {track.assignments.map((curve) => {
                                const curveEdit = curveOverride(curve.assignment_uid);
                                const renderedCurve = curveOverlayRenderPackage?.curves.find(
                                  (item) => item.assignment_uid === curve.assignment_uid,
                                );
                                const effectiveColor = curveEdit.color ?? renderedCurve?.color ?? "#58d39b";
                                const effectiveWidth = curveEdit.line_width ?? renderedCurve?.line_width ?? curve.line_width ?? 1.5;
                                const effectiveOpacity = curveEdit.opacity ?? renderedCurve?.opacity ?? (curve.line_opacity / 100);
                                const effectiveExaggeration = curveEdit.radial_exaggeration ?? renderedCurve?.radial_width ?? 1;
                                return <div className="wlv-wbv-published-curve-edit" key={curve.assignment_uid}>
                                  <strong>{curve.observed_mnemonic}</strong>
                                  <label className="wlv-wbv-field wlv-wbv-curve-compact-toggle"><span>Visible</span><input type="checkbox" checked={curveEdit.visible ?? true} onChange={(event)=>updateCurveOverride(curve.assignment_uid,{visible:event.target.checked})}/></label>
                                  <label className="wlv-wbv-field wlv-wbv-colour-field"><span>Curve Color</span><input type="color" value={effectiveColor} onChange={(event)=>updateCurveOverride(curve.assignment_uid,{color:event.target.value})}/></label>
                                  <label className="wlv-wbv-field wlv-wbv-curve-number-compact"><span>Width</span><input type="number" min="0.1" step="0.1" value={effectiveWidth} onChange={(event)=>updateCurveOverride(curve.assignment_uid,{line_width:Number(event.target.value)})}/></label>
                                  <label className="wlv-wbv-field wlv-wbv-curve-number-compact"><span>Opacity</span><input type="number" min="0" max="1" step="0.05" value={effectiveOpacity} onChange={(event)=>updateCurveOverride(curve.assignment_uid,{opacity:Number(event.target.value)})}/></label>
                                  <label className="wlv-wbv-field wlv-wbv-curve-number-standard"><span>Lateral Exaggeration</span><input type="number" min="0.25" max="3" step="0.25" value={effectiveExaggeration} onChange={(event)=>updateCurveOverride(curve.assignment_uid,{radial_exaggeration:Math.min(3,Math.max(0.25,Number(event.target.value)))})}/></label>
                                  <div className="wlv-wbv-curve-label-summary">
                                    <label className="wlv-wbv-curve-label-toggle"><span>Show Label</span><input type="checkbox" checked={curveEdit.label_visible ?? renderedCurve?.label_visible ?? false} onChange={(event)=>updateCurveOverride(curve.assignment_uid,{label_visible:event.target.checked})}/></label>
                                    <button type="button" className="wlv-wbv-control-button" onClick={()=>setCurveLabelEditorAssignmentUid(curve.assignment_uid)}>Edit Label</button>
                                  </div>
                                </div>;
                              })}
                            </fieldset>;
                          })}
                        </div>
                        {selectedLabelCurve && selectedLabelOverride ? <section className="wlv-wbv-curve-label-editor" aria-label={`Edit label for ${selectedLabelCurve.observed_mnemonic}`}>
                          <header className="wlv-wbv-curve-label-editor-header">
                            <div><strong>Edit Label · {selectedLabelCurve.observed_mnemonic}</strong><span>Scene-attached curve annotation</span></div>
                            <button type="button" className="wlv-wbv-icon-button" aria-label="Close curve label editor" onClick={()=>setCurveLabelEditorAssignmentUid(null)}>×</button>
                          </header>
                          <div className="wlv-wbv-curve-label-editor-grid">
                            <fieldset className="wlv-wbv-curve-label-section is-content"><legend>Content</legend>
                              <label className="wlv-wbv-field">Type<select value={selectedLabelOverride.label_content ?? selectedLabelRenderedCurve?.label_content ?? "mnemonic"} onChange={(event)=>updateCurveOverride(selectedLabelCurve.assignment_uid,{label_content:event.target.value as "mnemonic"|"mnemonic_value"|"scale"|"mnemonic_scale"})}><option value="mnemonic">Mnemonic</option><option value="mnemonic_value">Mnemonic + Value</option><option value="scale">Scale</option><option value="mnemonic_scale">Mnemonic + Scale</option></select></label>
                            </fieldset>
                            <fieldset className="wlv-wbv-curve-label-section is-anchor"><legend>Anchor</legend>
                              <label className="wlv-wbv-field">Depth<select value={selectedLabelOverride.label_anchor ?? selectedLabelRenderedCurve?.label_anchor ?? "top"} onChange={(event)=>updateCurveOverride(selectedLabelCurve.assignment_uid,{label_anchor:event.target.value as "top"|"base"|"custom_md"})}><option value="top">Top of curve</option><option value="base">Base of curve</option><option value="custom_md">Custom MD</option></select></label>
                              {(selectedLabelOverride.label_anchor ?? selectedLabelRenderedCurve?.label_anchor ?? "top")==="custom_md"?<label className="wlv-wbv-field">Custom MD<input type="number" step="any" value={selectedLabelOverride.label_custom_md ?? selectedLabelRenderedCurve?.label_custom_md ?? ""} onChange={(event)=>updateCurveOverride(selectedLabelCurve.assignment_uid,{label_custom_md:event.target.value===""?null:Number(event.target.value)})}/></label>:null}
                              <label className="wlv-wbv-field">Placement<select value={(selectedLabelOverride.label_position ?? selectedLabelRenderedCurve?.label_position ?? "on_track")==="center"?"on_track":(selectedLabelOverride.label_position ?? selectedLabelRenderedCurve?.label_position ?? "on_track")} onChange={(event)=>updateCurveOverride(selectedLabelCurve.assignment_uid,{label_position:event.target.value as "on_track"|"left"|"right"})}><option value="on_track">On track</option><option value="left">Left of track</option><option value="right">Right of track</option></select></label>
                            </fieldset>
                            {(selectedLabelOverride.label_content ?? selectedLabelRenderedCurve?.label_content ?? "mnemonic")!=="scale"?<fieldset className="wlv-wbv-curve-label-section is-mnemonic"><legend>Mnemonic</legend>
                              <label className="wlv-wbv-field wlv-wbv-range-field"><span>Size</span><input type="range" min="0.5" max="2.5" step="0.1" value={selectedLabelOverride.label_size ?? selectedLabelRenderedCurve?.label_size ?? 1} onChange={(event)=>updateCurveOverride(selectedLabelCurve.assignment_uid,{label_size:Number(event.target.value)})}/><span className="wlv-wbv-range-number-box"><input className="wlv-wbv-range-number" type="number" min="0.5" max="2.5" step="0.1" value={selectedLabelOverride.label_size ?? selectedLabelRenderedCurve?.label_size ?? 1} onChange={(event)=>updateCurveOverride(selectedLabelCurve.assignment_uid,{label_size:Math.min(2.5,Math.max(0.5,Number(event.target.value)))})}/><span>×</span></span></label>
                              <label className="wlv-wbv-field wlv-wbv-range-field"><span>Weight</span><input type="range" min="400" max="900" step="100" value={selectedLabelOverride.label_weight ?? selectedLabelRenderedCurve?.label_weight ?? 800} onChange={(event)=>updateCurveOverride(selectedLabelCurve.assignment_uid,{label_weight:Number(event.target.value)})}/><span className="wlv-wbv-range-number-box"><input className="wlv-wbv-range-number" type="number" min="400" max="900" step="100" value={selectedLabelOverride.label_weight ?? selectedLabelRenderedCurve?.label_weight ?? 800} onChange={(event)=>updateCurveOverride(selectedLabelCurve.assignment_uid,{label_weight:Math.min(900,Math.max(400,Math.round(Number(event.target.value)/100)*100))})}/></span></label>
                              {(selectedLabelOverride.label_content ?? selectedLabelRenderedCurve?.label_content ?? "mnemonic")==="mnemonic_scale"?<label className="wlv-wbv-field">Alignment<select value={selectedLabelOverride.label_alignment ?? selectedLabelRenderedCurve?.label_alignment ?? "center"} onChange={(event)=>updateCurveOverride(selectedLabelCurve.assignment_uid,{label_alignment:event.target.value as "left"|"center"|"right"})}><option value="left">Left</option><option value="center">Center</option><option value="right">Right</option></select></label>:null}
                            </fieldset>:null}
                            {((selectedLabelOverride.label_content ?? selectedLabelRenderedCurve?.label_content ?? "mnemonic")==="scale" || (selectedLabelOverride.label_content ?? selectedLabelRenderedCurve?.label_content ?? "mnemonic")==="mnemonic_scale")?<fieldset className="wlv-wbv-curve-label-section is-scale"><legend>Scale Appearance</legend>
                              <label className="wlv-wbv-field wlv-wbv-colour-field"><span>Color</span><input type="color" value={selectedLabelOverride.scale_color ?? selectedLabelRenderedCurve?.scale_color ?? "#b7c5d0"} onChange={(event)=>updateCurveOverride(selectedLabelCurve.assignment_uid,{scale_color:event.target.value})}/></label>
                              <label className="wlv-wbv-field wlv-wbv-range-field"><span>Opacity</span><input type="range" min="0" max="1" step="0.05" value={selectedLabelOverride.scale_opacity ?? selectedLabelRenderedCurve?.scale_opacity ?? 1} onChange={(event)=>updateCurveOverride(selectedLabelCurve.assignment_uid,{scale_opacity:Number(event.target.value)})}/><span className="wlv-wbv-range-number-box"><input className="wlv-wbv-range-number" type="number" min="0" max="1" step="0.05" value={selectedLabelOverride.scale_opacity ?? selectedLabelRenderedCurve?.scale_opacity ?? 1} onChange={(event)=>updateCurveOverride(selectedLabelCurve.assignment_uid,{scale_opacity:Math.min(1,Math.max(0,Number(event.target.value)))})}/><span>×</span></span></label>
                              <label className="wlv-wbv-field wlv-wbv-range-field"><span>Weight</span><input type="range" min="0.5" max="4" step="0.25" value={selectedLabelOverride.scale_line_width ?? selectedLabelRenderedCurve?.scale_line_width ?? 1} onChange={(event)=>updateCurveOverride(selectedLabelCurve.assignment_uid,{scale_line_width:Number(event.target.value)})}/><span className="wlv-wbv-range-number-box"><input className="wlv-wbv-range-number" type="number" min="0.5" max="4" step="0.25" value={selectedLabelOverride.scale_line_width ?? selectedLabelRenderedCurve?.scale_line_width ?? 1} onChange={(event)=>updateCurveOverride(selectedLabelCurve.assignment_uid,{scale_line_width:Math.min(4,Math.max(0.5,Number(event.target.value)))})}/><span>px</span></span></label>
                              <label className="wlv-wbv-field wlv-wbv-range-field"><span>Size</span><input type="range" min="0.5" max="2" step="0.1" value={selectedLabelOverride.scale_size ?? selectedLabelRenderedCurve?.scale_size ?? 1} onChange={(event)=>updateCurveOverride(selectedLabelCurve.assignment_uid,{scale_size:Number(event.target.value)})}/><span className="wlv-wbv-range-number-box"><input className="wlv-wbv-range-number" type="number" min="0.5" max="2" step="0.1" value={selectedLabelOverride.scale_size ?? selectedLabelRenderedCurve?.scale_size ?? 1} onChange={(event)=>updateCurveOverride(selectedLabelCurve.assignment_uid,{scale_size:Math.min(2,Math.max(0.5,Number(event.target.value)))})}/><span>×</span></span></label>
                            </fieldset>:null}
                            <fieldset className="wlv-wbv-curve-label-section is-position"><legend>Position</legend>
                              <label className="wlv-wbv-field wlv-wbv-range-field"><span>Horizontal</span><input type="range" min="-4" max="4" step="0.25" value={selectedLabelOverride.label_horizontal_adjustment ?? selectedLabelRenderedCurve?.label_horizontal_adjustment ?? 0} onChange={(event)=>updateCurveOverride(selectedLabelCurve.assignment_uid,{label_horizontal_adjustment:Number(event.target.value)})}/><span className="wlv-wbv-range-number-box"><input className="wlv-wbv-range-number" type="number" min="-4" max="4" step="0.25" value={selectedLabelOverride.label_horizontal_adjustment ?? selectedLabelRenderedCurve?.label_horizontal_adjustment ?? 0} onChange={(event)=>updateCurveOverride(selectedLabelCurve.assignment_uid,{label_horizontal_adjustment:Math.min(4,Math.max(-4,Number(event.target.value)))})}/><span>×</span></span></label>
                              <label className="wlv-wbv-field wlv-wbv-range-field"><span>Vertical</span><input type="range" min="-4" max="4" step="0.25" value={selectedLabelOverride.label_vertical_adjustment ?? selectedLabelRenderedCurve?.label_vertical_adjustment ?? 0} onChange={(event)=>updateCurveOverride(selectedLabelCurve.assignment_uid,{label_vertical_adjustment:Number(event.target.value)})}/><span className="wlv-wbv-range-number-box"><input className="wlv-wbv-range-number" type="number" min="-4" max="4" step="0.25" value={selectedLabelOverride.label_vertical_adjustment ?? selectedLabelRenderedCurve?.label_vertical_adjustment ?? 0} onChange={(event)=>updateCurveOverride(selectedLabelCurve.assignment_uid,{label_vertical_adjustment:Math.min(4,Math.max(-4,Number(event.target.value)))})}/><span>×</span></span></label>
                            </fieldset>
                          </div>
                        </section>:null}
                      </div>:<div className="wlv-wbv-empty-state">Select a retained publication package.</div>}
                    </section>
                  </>;
                }
                const files = activeLayerTab === "formation_tops"
                  ? (layerEditorFormationTopProducts?.products ?? []).map((product) => ({ product_id: product.product_id, display_name: product.display_name }))
                  : activeLayerTab === "completions"
                    ? (layerEditorCompletionProducts?.products ?? []).map((product) => ({ product_id: product.product_id, display_name: product.display_name }))
                    : (layerEditorDisplayLayerFiles?.layers[activeLayerTab] ?? []);
                return <>
                  <section className="wlv-wbv-manager-inventory-panel"><div className="wlv-wbv-manager-panel-title"><div><h3>Items</h3><span>Registered WMD products</span></div></div><label className="wlv-wbv-field">Registered item<select style={activeLayerTab==="completions"?{width:"100%",minWidth:0}:undefined} title={files.find((file)=>file.product_id===config.selected_item_ids[0])?.display_name ?? ""} value={config.selected_item_ids[0] ?? ""} onChange={(event)=>updateDraftLayer(activeLayerTab,(current)=>({...current,selected_item_ids:event.target.value?[event.target.value]:[],appearance:{...current.appearance,selected_top_ids:activeLayerTab==="formation_tops"?null:current.appearance.selected_top_ids,selected_interval_ids:activeLayerTab==="lithology_intervals"?null:current.appearance.selected_interval_ids,selected_component_ids:activeLayerTab==="completions"?null:current.appearance.selected_component_ids}}))}><option value="">{files.length?"Select registered file":"No registered files"}</option>{files.map((file)=><option key={file.product_id} value={file.product_id}>{file.display_name}</option>)}</select></label>{activeLayerTab==="completions"&&config.selected_item_ids[0]?<div className="wlv-wbv-property-note" style={{marginTop:8,whiteSpace:"normal",overflowWrap:"anywhere"}}>{files.find((file)=>file.product_id===config.selected_item_ids[0])?.display_name}</div>:null}</section>
                  <section className="wlv-wbv-manager-selected-panel">{activeLayerTab === "formation_tops" ? (()=>{
                    const availableTops=(layerEditorFormationTopProducts?.products ?? []).filter((product)=>config.selected_item_ids.includes(product.product_id)).flatMap((product)=>product.tops);
                    const selectedTopIds=config.appearance.selected_top_ids == null ? availableTops.map((top)=>top.top_id) : config.appearance.selected_top_ids.filter((topId)=>availableTops.some((top)=>top.top_id===topId));
                    const selectedTopSet=new Set(selectedTopIds);
                    const setTopSelection=(nextIds:string[])=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,selected_top_ids:nextIds}}));
                    return <>
                      <div className="wlv-wbv-manager-panel-title"><div><h3>Selected Items</h3><span>{selectedTopIds.length} of {availableTops.length} selected</span></div></div>
                      {availableTops.length > 0 ? <>
                        <div className="wlv-wbv-manager-top-actions"><button type="button" className="wlv-wbv-control-button" onClick={()=>setTopSelection(availableTops.map((top)=>top.top_id))}>Select All</button><button type="button" className="wlv-wbv-control-button" onClick={()=>setTopSelection([])}>None</button></div>
                        <div className="wlv-wbv-manager-top-list" role="group" aria-label="Formation tops to display">
                          {availableTops.map((top)=><label key={top.top_id} className="wlv-wbv-manager-top-row"><input type="checkbox" checked={selectedTopSet.has(top.top_id)} onChange={(event)=>{ const next=event.target.checked ? [...selectedTopIds,top.top_id] : selectedTopIds.filter((id)=>id!==top.top_id); setTopSelection(Array.from(new Set(next))); }}/><span className="wlv-wbv-manager-top-name">{top.name}</span><span className="wlv-wbv-manager-top-md">{top.md.toLocaleString(undefined,{maximumFractionDigits:2})} MD</span></label>)}
                        </div>
                      </> : config.selected_item_ids.length > 0 ? <p>No managed formation-top rows are attached to the selected MWD product.</p> : <p>Select a registered Formation Tops product.</p>}
                    </>;
                  })() : activeLayerTab === "lithology_intervals" ? (()=>{
                    const intervals=(layerEditorLithologyProducts?.products ?? []).filter((product)=>config.selected_item_ids.includes(product.product_id)).flatMap((product)=>product.intervals);
                    const selectedIntervalIds=config.appearance.selected_interval_ids == null ? intervals.map((interval)=>interval.interval_id) : config.appearance.selected_interval_ids.filter((intervalId)=>intervals.some((interval)=>interval.interval_id===intervalId));
                    const selectedIntervalSet=new Set(selectedIntervalIds);
                    const setIntervalSelection=(nextIds:string[])=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,selected_interval_ids:nextIds}}));
                    return <>
                      <div className="wlv-wbv-manager-panel-title"><div><h3>Selected Items</h3><span>{selectedIntervalIds.length} of {intervals.length} selected</span></div></div>
                      {intervals.length > 0 ? <>
                        <div className="wlv-wbv-manager-top-actions wlv-wbv-lithology-actions"><button type="button" className="wlv-wbv-control-button" onClick={()=>setIntervalSelection(intervals.map((interval)=>interval.interval_id))}>Select All</button><button type="button" className="wlv-wbv-control-button" onClick={()=>setIntervalSelection([])}>None</button></div>
                        <div className="wlv-wbv-manager-top-list wlv-wbv-lithology-list" role="group" aria-label="Lithology intervals to display">
                          <div className="wlv-wbv-lithology-list-header" aria-hidden="true"><span></span><span>Lithology</span><span>Interval MD</span></div>
                          {intervals.map((interval)=><label key={interval.interval_id} className="wlv-wbv-manager-top-row wlv-wbv-lithology-row"><input type="checkbox" checked={selectedIntervalSet.has(interval.interval_id)} onChange={(event)=>{ const next=event.target.checked?[...selectedIntervalIds,interval.interval_id]:selectedIntervalIds.filter((id)=>id!==interval.interval_id); setIntervalSelection(Array.from(new Set(next))); }}/><span className="wlv-wbv-lithology-name-wrap">{lithologyKrPatternUrl(interval)?<span className="wlv-wbv-lithology-swatch wlv-wbv-lithology-swatch--kr" title={interval.canonical_lithology || interval.lithology}><img src={lithologyKrPatternUrl(interval) ?? undefined} alt="" aria-hidden="true"/></span>:<span className="wlv-wbv-lithology-swatch wlv-wbv-lithology-swatch--fallback" style={{background:interval.background_color || "#6f8f72"}} title="No canonical KR pattern assigned" aria-hidden="true"></span>}<span className="wlv-wbv-manager-top-name wlv-wbv-lithology-name" title={interval.lithology}>{interval.lithology}</span></span><span className="wlv-wbv-manager-top-md wlv-wbv-lithology-md">{interval.top_md.toLocaleString(undefined,{maximumFractionDigits:1})} – {interval.base_md.toLocaleString(undefined,{maximumFractionDigits:1})} MD</span></label>)}
                        </div>
                      </> : config.selected_item_ids.length>0 ? <p>No reviewed lithology intervals are attached to the selected LCM product.</p> : <p>Select a registered Lithology product.</p>}
                    </>;
                  })() : activeLayerTab === "completions" ? (()=>{
                    const components=(layerEditorCompletionProducts?.products ?? []).filter((product)=>config.selected_item_ids.includes(product.product_id)).flatMap((product)=>product.components);
                    const selectedComponentIds=config.appearance.selected_component_ids == null ? components.map((component)=>component.component_id) : config.appearance.selected_component_ids.filter((componentId)=>components.some((component)=>component.component_id===componentId));
                    const selectedComponentSet=new Set(selectedComponentIds);
                    const setComponentSelection=(nextIds:string[])=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,selected_component_ids:nextIds}}));
                    const componentMdLabel=(component:WbvCompletionComponentItem)=>component.base_md!=null&&component.base_md>component.top_md?`${component.top_md.toLocaleString(undefined,{maximumFractionDigits:1})} – ${component.base_md.toLocaleString(undefined,{maximumFractionDigits:1})}`:component.top_md.toLocaleString(undefined,{maximumFractionDigits:1});
                    return <>
                      <div className="wlv-wbv-manager-panel-title"><div><h3>Completion Components</h3><span>{selectedComponentIds.length} of {components.length} shown</span></div></div>
                      {components.length>0? <>
                        <div className="wlv-wbv-manager-top-actions"><button type="button" className="wlv-wbv-control-button" onClick={()=>setComponentSelection(components.map((component)=>component.component_id))}>Select All</button><button type="button" className="wlv-wbv-control-button" onClick={()=>setComponentSelection([])}>None</button></div>
                        <div role="group" aria-label="Completion components to display" style={{padding:"0 8px 12px",overflowY:"auto"}}>
                          <div aria-hidden="true" style={{display:"grid",gridTemplateColumns:"28px minmax(0, 1fr) 138px",gap:10,padding:"7px 8px 6px",borderBottom:"1px solid rgba(132,157,174,0.22)",color:"#9fb0bd",fontSize:11,fontWeight:700,textTransform:"uppercase",letterSpacing:"0.06em"}}><span></span><span>Component</span><span style={{textAlign:"right"}}>MD</span></div>
                          {components.map((component)=><label key={component.component_id} title={component.canonical_id} style={{display:"grid",gridTemplateColumns:"28px minmax(0, 1fr) 138px",gap:10,alignItems:"center",padding:"7px 8px",borderBottom:"1px solid rgba(132,157,174,0.14)",cursor:"pointer"}}><input type="checkbox" checked={selectedComponentSet.has(component.component_id)} onChange={(event)=>{ const next=event.target.checked?[...selectedComponentIds,component.component_id]:selectedComponentIds.filter((id)=>id!==component.component_id); setComponentSelection(Array.from(new Set(next))); }}/><span style={{minWidth:0,color:"#dce7ef",fontWeight:600,fontSize:13.5,lineHeight:1.28,whiteSpace:"normal",overflowWrap:"anywhere"}}>{component.label}</span><span style={{color:"#c7d5df",fontVariantNumeric:"tabular-nums",fontWeight:600,fontSize:13,textAlign:"right",whiteSpace:"nowrap"}}>{componentMdLabel(component)} {component.depth_unit || "MD"}</span></label>)}
                        </div>
                      </> : <p>Select a registered Completion product.</p>}
                    </>;
                  })() : <><div className="wlv-wbv-manager-panel-title"><div><h3>Selected Items</h3><span>{config.selected_item_ids.length} selected</span></div></div><p>Selection is retained when the layer is hidden.</p></>}</section>
                  <section className="wlv-wbv-manager-properties-panel"><div className="wlv-wbv-manager-panel-title"><div><h3>Properties</h3><span>{activeLayerTab === "formation_tops" ? "3D marker appearance" : activeLayerTab === "lithology_intervals" ? "Wellbore overlay" : activeLayerTab === "core_images" ? "Depth-registered Core track" : activeLayerTab === "completions" ? "Trajectory-attached completion geometry" : "Renderer not yet implemented"}</span></div></div>{activeLayerTab === "formation_tops" ? <div className="wlv-wbv-manager-properties-stack wlv-wbv-formation-top-properties">
                    <fieldset className="wlv-wbv-property-group"><legend>Marker</legend>
                      <label className="wlv-wbv-field">Style<select value={config.appearance.marker_style ?? "ring"} onChange={(e)=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,marker_style:e.target.value as WbvLayerConfig["appearance"]["marker_style"]}}))}><option value="ring">Ring</option><option value="disc">Disc</option><option value="tick">Tick</option><option value="flag">Flag</option></select></label>
                      <label className="wlv-wbv-field wlv-wbv-range-field"><span>Size</span><input type="range" min="0.25" max="5" step="0.10" value={config.appearance.marker_size ?? 1} onChange={(e)=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,marker_size:Number(e.target.value)}}))}/><span className="wlv-wbv-range-number-box"><input className="wlv-wbv-range-number" type="number" min="0.25" max="5" step="0.10" value={config.appearance.marker_size ?? 1} onChange={(e)=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,marker_size:Number(e.target.value)}}))}/><span>×</span></span></label>
                      <label className="wlv-wbv-field wlv-wbv-range-field"><span>Opacity</span><input type="range" min="0" max="1" step="0.05" value={config.appearance.opacity} onChange={(e)=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,opacity:Number(e.target.value)}}))}/><span className="wlv-wbv-range-number-box"><input className="wlv-wbv-range-number" type="number" min="0" max="100" step="1" value={Math.round(config.appearance.opacity*100)} onChange={(e)=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,opacity:Math.max(0,Math.min(1,Number(e.target.value)/100))}}))}/><span>%</span></span></label>
                    </fieldset>
                    <fieldset className="wlv-wbv-property-group"><legend>Colour</legend>
                      <label className="wlv-wbv-field">Colour by<select value={config.appearance.color_mode ?? "formation"} onChange={(e)=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,color_mode:e.target.value as WbvLayerConfig["appearance"]["color_mode"]}}))}><option value="formation">Formation</option><option value="well">Well</option><option value="classification">Classification</option><option value="single">Single colour</option></select></label>
                      {(config.appearance.color_mode ?? "formation") === "single" ? <label className="wlv-wbv-field wlv-wbv-colour-field"><span>Colour</span><input type="color" value={config.appearance.color ?? "#58d39b"} onChange={(e)=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,color:e.target.value}}))}/></label> : null}
                    </fieldset>
                    <fieldset className="wlv-wbv-property-group"><legend>Labels</legend>
                      <label className="wlv-wbv-manager-toggle-row"><input type="checkbox" checked={config.appearance.show_labels} onChange={(e)=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,show_labels:e.target.checked}}))}/><span>Show labels</span></label>
                      <label className="wlv-wbv-field">Format<select disabled={!config.appearance.show_labels} value={config.appearance.label_mode ?? "name_md"} onChange={(e)=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,label_mode:e.target.value as WbvLayerConfig["appearance"]["label_mode"]}}))}><option value="name">Name</option><option value="name_md">Name + MD</option><option value="name_tvd">Name + TVD</option><option value="name_md_tvd">Name + MD / TVD</option></select></label>
                      <label className="wlv-wbv-field wlv-wbv-range-field"><span>Size</span><input disabled={!config.appearance.show_labels} type="range" min="0.15" max="3" step="0.05" value={config.appearance.label_size ?? 1} onChange={(e)=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,label_size:Number(e.target.value)}}))}/><span className="wlv-wbv-range-number-box"><input disabled={!config.appearance.show_labels} className="wlv-wbv-range-number" type="number" min="0.15" max="3" step="0.05" value={config.appearance.label_size ?? 1} onChange={(e)=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,label_size:Number(e.target.value)}}))}/><span>×</span></span></label>
                      <label className="wlv-wbv-field">Position<select disabled={!config.appearance.show_labels} value={config.appearance.label_position ?? "right"} onChange={(e)=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,label_position:e.target.value as WbvLayerConfig["appearance"]["label_position"]}}))}><option value="right">Right</option><option value="left">Left</option><option value="above">Above</option><option value="below">Below</option></select></label>
                      <label className="wlv-wbv-field wlv-wbv-range-field"><span>Distance</span><input disabled={!config.appearance.show_labels} type="range" min="0" max="8" step="0.25" value={config.appearance.label_offset ?? 1} onChange={(e)=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,label_offset:Number(e.target.value)}}))}/><span className="wlv-wbv-range-number-box"><input disabled={!config.appearance.show_labels} className="wlv-wbv-range-number" type="number" min="0" max="8" step="0.25" value={config.appearance.label_offset ?? 1} onChange={(e)=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,label_offset:Number(e.target.value)}}))}/><span>×</span></span></label>
                    </fieldset>
                  </div> : activeLayerTab === "lithology_intervals" ? <div className="wlv-wbv-manager-properties-stack wlv-wbv-lithology-properties">
                    <fieldset className="wlv-wbv-property-group"><legend>Wellbore Overlay</legend>
                      <p className="wlv-wbv-property-note">Reviewed intervals come from LCM and the 3D sleeve uses the exact canonical KR SVG pattern, colour and default scale for each interval. Pattern size multiplies the KR default scale; no local WBV lithology pattern mapping is used.</p>
                      <label className="wlv-wbv-field wlv-wbv-range-field"><span>Radius</span><input type="range" min="1.00" max="8.00" step="0.05" value={config.appearance.line_width || 1.35} onChange={(e)=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,line_width:Number(e.target.value),display_mode:"wellbore_overlay"}}))}/><span className="wlv-wbv-range-number-box"><input className="wlv-wbv-range-number" type="number" min="1" max="8" step="0.05" value={config.appearance.line_width || 1.35} onChange={(e)=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,line_width:Number(e.target.value),display_mode:"wellbore_overlay"}}))}/><span>×</span></span></label>
                      <label className="wlv-wbv-field wlv-wbv-range-field"><span>Opacity</span><input type="range" min="0.1" max="1" step="0.05" value={config.appearance.opacity} onChange={(e)=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,opacity:Number(e.target.value),display_mode:"wellbore_overlay"}}))}/><span className="wlv-wbv-range-number-box"><input className="wlv-wbv-range-number" type="number" min="10" max="100" step="1" value={Math.round(config.appearance.opacity*100)} onChange={(e)=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,opacity:Math.max(0.1,Math.min(1,Number(e.target.value)/100)),display_mode:"wellbore_overlay"}}))}/><span>%</span></span></label>
                      <label className="wlv-wbv-field wlv-wbv-range-field"><span>Brightness</span><input type="range" min="0.75" max="2.50" step="0.05" value={config.appearance.brightness ?? 1.35} onChange={(e)=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,brightness:Number(e.target.value),display_mode:"wellbore_overlay"}}))}/><span className="wlv-wbv-range-number-box"><input className="wlv-wbv-range-number" type="number" min="0.75" max="2.5" step="0.05" value={config.appearance.brightness ?? 1.35} onChange={(e)=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,brightness:Number(e.target.value),display_mode:"wellbore_overlay"}}))}/><span>×</span></span></label>
                      <label className="wlv-wbv-field wlv-wbv-range-field"><span>Pattern size</span><input type="range" min="0.75" max="4.00" step="0.05" value={config.appearance.pattern_scale ?? 1.5} onChange={(e)=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,pattern_scale:Number(e.target.value),display_mode:"wellbore_overlay"}}))}/><span className="wlv-wbv-range-number-box"><input className="wlv-wbv-range-number" type="number" min="0.75" max="4" step="0.05" value={config.appearance.pattern_scale ?? 1.5} onChange={(e)=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,pattern_scale:Number(e.target.value),display_mode:"wellbore_overlay"}}))}/><span>×</span></span></label>
                      <label className="wlv-wbv-manager-toggle-row"><input type="checkbox" checked={config.appearance.hide_underlay ?? false} onChange={(e)=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,hide_underlay:e.target.checked,display_mode:"wellbore_overlay"}}))}/><span>Hide underlying wellbore</span></label>
                    </fieldset>
                  </div> : activeLayerTab === "completions" ? <div className="wlv-wbv-manager-properties-stack wlv-wbv-completion-properties">
                    <fieldset className="wlv-wbv-property-group"><legend>Display</legend>
                      <p className="wlv-wbv-property-note">Completion componentry follows the WDV standard by default. The colour swatch remains available as a single-colour override.</p>
                      <div className="wlv-wbv-inline-fields" style={{alignItems:"end",gap:12}}>
                        <label className="wlv-wbv-field wlv-wbv-colour-field"><span>Colour override</span><input type="color" value={config.appearance.color ?? "#d6dde3"} onChange={(e)=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,color:e.target.value}}))}/></label>
                        <button type="button" className="wlv-wbv-control-button" disabled={config.appearance.color == null} onClick={()=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,color:null}}))}>Use WDV standard</button>
                      </div>
                      <label className="wlv-wbv-field wlv-wbv-range-field"><span>Size</span><input type="range" min="0.5" max="4" step="0.1" value={config.appearance.line_width || 1} onChange={(e)=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,line_width:Number(e.target.value)}}))}/><span className="wlv-wbv-range-number-box"><input className="wlv-wbv-range-number" type="number" min="0.5" max="4" step="0.1" value={config.appearance.line_width || 1} onChange={(e)=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,line_width:Math.max(0.5,Math.min(4,Number(e.target.value)))}}))}/><span>×</span></span></label>
                      <label className="wlv-wbv-field wlv-wbv-range-field"><span>Opacity</span><input type="range" min="0.1" max="1" step="0.05" value={config.appearance.opacity} onChange={(e)=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,opacity:Number(e.target.value)}}))}/><span className="wlv-wbv-range-number-box"><input className="wlv-wbv-range-number" type="number" min="10" max="100" step="1" value={Math.round(config.appearance.opacity*100)} onChange={(e)=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,opacity:Math.max(0.1,Math.min(1,Number(e.target.value)/100))}}))}/><span>%</span></span></label>
                    </fieldset>
                    <fieldset className="wlv-wbv-property-group"><legend>Labels</legend>
                      <label className="wlv-wbv-manager-toggle-row"><input type="checkbox" checked={config.appearance.show_labels} onChange={(e)=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,show_labels:e.target.checked}}))}/><span>Show labels</span></label>
                      <label className="wlv-wbv-field wlv-wbv-colour-field"><span>Label colour</span><input disabled={!config.appearance.show_labels} type="color" value={config.appearance.label_color ?? "#dce7ef"} onChange={(e)=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,label_color:e.target.value}}))}/></label>
                      <label className="wlv-wbv-field">Format<select disabled={!config.appearance.show_labels} value={config.appearance.label_mode ?? "name_md"} onChange={(e)=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,label_mode:e.target.value as WbvLayerConfig["appearance"]["label_mode"]}}))}><option value="name">Name</option><option value="name_md">Name + MD</option><option value="name_tvd">Name + TVD</option><option value="name_md_tvd">Name + MD / TVD</option></select></label>
                      <label className="wlv-wbv-field wlv-wbv-range-field"><span>Size</span><input disabled={!config.appearance.show_labels} type="range" min="0.15" max="3" step="0.05" value={config.appearance.label_size ?? 1} onChange={(e)=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,label_size:Number(e.target.value)}}))}/><span className="wlv-wbv-range-number-box"><input disabled={!config.appearance.show_labels} className="wlv-wbv-range-number" type="number" min="0.15" max="3" step="0.05" value={config.appearance.label_size ?? 1} onChange={(e)=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,label_size:Number(e.target.value)}}))}/><span>×</span></span></label>
                      <label className="wlv-wbv-field">Position<select disabled={!config.appearance.show_labels} value={config.appearance.label_position ?? "right"} onChange={(e)=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,label_position:e.target.value as WbvLayerConfig["appearance"]["label_position"]}}))}><option value="right">Right</option><option value="left">Left</option><option value="above">Above</option><option value="below">Below</option></select></label>
                      <label className="wlv-wbv-field wlv-wbv-range-field"><span>Distance</span><input disabled={!config.appearance.show_labels} type="range" min="0" max="8" step="0.25" value={config.appearance.label_offset ?? 1} onChange={(e)=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,label_offset:Number(e.target.value)}}))}/><span className="wlv-wbv-range-number-box"><input disabled={!config.appearance.show_labels} className="wlv-wbv-range-number" type="number" min="0" max="8" step="0.25" value={config.appearance.label_offset ?? 1} onChange={(e)=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,label_offset:Number(e.target.value)}}))}/><span>×</span></span></label>
                    </fieldset>
                    <fieldset className="wlv-wbv-property-group"><legend>Rendering</legend>
                      <p className="wlv-wbv-property-note">Completion geometry is attached to this well's trajectory by measured depth. Published component geometry families remain authoritative.</p>
                    </fieldset>
                  </div> : activeLayerTab === "core_images" ? <div className="wlv-wbv-manager-properties-stack wlv-wbv-core-properties">
                    <fieldset className="wlv-wbv-property-group"><legend>Core Display</legend>
                      <p className="wlv-wbv-property-note">Overview shows the 3D Core locator at exact published MD intervals. Core photographs are shown only in inspection at canonical WDV-derived proportions.</p>
                      <div className="wlv-wbv-property-note">{coreTrackRenderLayout.length > 0 ? `${coreTrackRenderLayout.length} Core track${coreTrackRenderLayout.length===1?"":"s"} available · ${coreRenderChunks.length} image chunk${coreRenderChunks.length===1?"":"s"} loaded` : "Add a Core track in Track Layout."}</div>
                      <div className="wlv-wbv-core-action-row">
                        <button type="button" className="wlv-wbv-control-button is-primary" disabled={!editingActiveLayerWell || coreRenderChunks.length===0} onClick={zoomToCoreImage}>Zoom to Image</button>
                        <button
                          type="button"
                          className={`wlv-wbv-control-button${coreViewMode ? " is-primary is-active" : ""}`}
                          disabled={!editingActiveLayerWell || coreRenderChunks.length===0}
                          onClick={() => {
                            setCoreViewMode((active) => {
                              const next = !active;
                              if (!next) {
                                setCoreModalOpen(false);
                                setCoreModalChunkId("");
                                setCoreLocatorFocusInterval(null);
                              }
                              return next;
                            });
                            setCoreInspectionInterval(null);
                          }}
                        >
                          View Core
                        </button>
                        <button type="button" className="wlv-wbv-control-button" disabled={!editingActiveLayerWell} onClick={()=>{setCoreViewMode(false);setCoreInspectionInterval(null);requestViewPreset("fit");}}>Full Well</button>
                      </div>
                      <div
                        style={{
                          marginTop: 10,
                          padding: "9px 11px",
                          border: "1px solid rgba(128,146,160,.36)",
                          borderRadius: 7,
                          background: "rgba(7,14,21,.34)",
                          minHeight: 48,
                        }}
                        aria-live="polite"
                      >
                        <div style={{fontSize:11,fontWeight:700,letterSpacing:".06em",textTransform:"uppercase",opacity:.7,marginBottom:4}}>Core selection</div>
                        {coreLocatorFocusInterval ? <>
                          <div style={{fontSize:13,fontWeight:600,color:"#dce5ec"}}>Core inspection</div>
                          <div style={{fontSize:12,color:"#aebac5",marginTop:2}}>{`${Math.min(coreLocatorFocusInterval.top_md,coreLocatorFocusInterval.base_md).toLocaleString(undefined,{maximumFractionDigits:2})}–${Math.max(coreLocatorFocusInterval.top_md,coreLocatorFocusInterval.base_md).toLocaleString(undefined,{maximumFractionDigits:2})} MD visible`}</div>
                        </> : <div style={{fontSize:12,opacity:.74}}>{coreViewMode ? "Select a point on the illustrated core." : "No core selected"}</div>}
                      </div>

                      <fieldset className="wlv-wbv-property-group" style={{marginTop:14}}>
                        <legend>Core Inspection Layout</legend>
                        <div style={{display:"grid",gridTemplateColumns:"150px 1fr",columnGap:16,rowGap:12,alignItems:"center"}}>
                          <div style={{fontSize:12,fontWeight:400,color:"#c7d1da"}}>Depth lattice</div>
                          <div style={{display:"flex",gap:6,alignItems:"center",flexWrap:"wrap"}}>
                            <button type="button" className={`wlv-wbv-control-button${coreLatticeSide==="off"?" is-primary":""}`} onClick={()=>setCoreLatticeSide("off")}>Off</button>
                            <button type="button" className={`wlv-wbv-control-button${coreLatticeSide==="left"?" is-primary":""}`} onClick={()=>setCoreLatticeSide("left")}>Left</button>
                            <button type="button" className={`wlv-wbv-control-button${coreLatticeSide==="right"?" is-primary":""}`} onClick={()=>setCoreLatticeSide("right")}>Right</button>
                          </div>

                          <div style={{fontSize:12,fontWeight:400,color:"#c7d1da"}}>Lattice offset</div>
                          <div style={{display:"flex",gap:6,alignItems:"center"}}>
                            <button type="button" className="wlv-wbv-control-button" disabled={coreLatticeSide==="off"} onClick={()=>setCoreLatticeOffset((value)=>Math.max(0,value-2))}>−</button>
                            <span style={{minWidth:48,textAlign:"center",fontSize:12,color:"#d5dee6",fontWeight:400}}>{coreLatticeOffset}px</span>
                            <button type="button" className="wlv-wbv-control-button" disabled={coreLatticeSide==="off"} onClick={()=>setCoreLatticeOffset((value)=>Math.min(80,value+2))}>+</button>
                          </div>

                          <div style={{fontSize:12,fontWeight:400,color:"#c7d1da"}}>Core descriptions</div>
                          <div style={{display:"flex",gap:6,alignItems:"center",flexWrap:"wrap"}}>
                            <button type="button" className={`wlv-wbv-control-button${coreDescriptionSide==="off"?" is-primary":""}`} onClick={()=>{coreDescriptionSideTouchedRef.current=true;setCoreDescriptionSide("off");}}>Off</button>
                            <button type="button" className={`wlv-wbv-control-button${coreDescriptionSide==="left"?" is-primary":""}`} disabled={coreDescriptions.length===0} onClick={()=>{coreDescriptionSideTouchedRef.current=true;setCoreDescriptionSide("left");}}>Left</button>
                            <button type="button" className={`wlv-wbv-control-button${coreDescriptionSide==="right"?" is-primary":""}`} disabled={coreDescriptions.length===0} onClick={()=>{coreDescriptionSideTouchedRef.current=true;setCoreDescriptionSide("right");}}>Right</button>
                            <span style={{fontSize:11,color:"#8f9da9",marginLeft:4,fontWeight:400}}>{coreDescriptions.length>0?`${coreDescriptions.length} published`:"No published descriptions"}</span>
                          </div>

                          <div style={{fontSize:12,fontWeight:400,color:"#c7d1da"}}>Description offset</div>
                          <div style={{display:"flex",gap:6,alignItems:"center"}}>
                            <button type="button" className="wlv-wbv-control-button" disabled={coreDescriptionSide==="off"} onClick={()=>setCoreDescriptionOffset((value)=>Math.max(0,value-2))}>−</button>
                            <span style={{minWidth:48,textAlign:"center",fontSize:12,color:"#d5dee6",fontWeight:400}}>{coreDescriptionOffset}px</span>
                            <button type="button" className="wlv-wbv-control-button" disabled={coreDescriptionSide==="off"} onClick={()=>setCoreDescriptionOffset((value)=>Math.min(80,value+2))}>+</button>
                          </div>

                          <div style={{fontSize:12,fontWeight:400,color:"#c7d1da"}}>Description width</div>
                          <div style={{display:"flex",gap:6,alignItems:"center"}}>
                            <button type="button" className="wlv-wbv-control-button" disabled={coreDescriptionSide==="off"} onClick={()=>setCoreDescriptionPanelWidth((width)=>Math.max(140,width-20))}>−</button>
                            <span style={{minWidth:54,textAlign:"center",fontSize:12,color:"#d5dee6",fontWeight:400}}>{coreDescriptionPanelWidth}px</span>
                            <button type="button" className="wlv-wbv-control-button" disabled={coreDescriptionSide==="off"} onClick={()=>setCoreDescriptionPanelWidth((width)=>Math.min(420,width+20))}>+</button>
                          </div>

                          <div style={{fontSize:12,fontWeight:400,color:"#c7d1da"}}>Description text</div>
                          <div style={{display:"flex",gap:6,alignItems:"center",flexWrap:"wrap"}}>
                            <button type="button" className="wlv-wbv-control-button" disabled={coreDescriptionSide==="off"} onClick={()=>setCoreDescriptionFontSize((size)=>Math.max(8,size-1))}>−</button>
                            <span style={{minWidth:42,textAlign:"center",fontSize:12,color:"#d5dee6",fontWeight:400}}>{coreDescriptionFontSize}px</span>
                            <button type="button" className="wlv-wbv-control-button" disabled={coreDescriptionSide==="off"} onClick={()=>setCoreDescriptionFontSize((size)=>Math.min(24,size+1))}>+</button>
                            <button type="button" className={`wlv-wbv-control-button${coreDescriptionShowMd?" is-primary":""}`} disabled={coreDescriptionSide==="off"} aria-pressed={coreDescriptionShowMd} onClick={()=>setCoreDescriptionShowMd((visible)=>!visible)}>MD labels</button>
                          </div>
                        </div>
                      </fieldset>
                    </fieldset>
                    <fieldset className="wlv-wbv-property-group"><legend>Locator Appearance</legend>
                      <label className="wlv-wbv-field wlv-wbv-colour-field"><span>Color</span><input type="color" value={config.appearance.color ?? "#7b838a"} onChange={(e)=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,color:e.target.value}}))}/></label>
                      <label className="wlv-wbv-field wlv-wbv-range-field"><span>Brightness</span><input type="range" min="0.75" max="2.50" step="0.05" value={config.appearance.brightness ?? 1.35} onChange={(e)=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,brightness:Number(e.target.value)}}))}/><span className="wlv-wbv-range-number-box"><input className="wlv-wbv-range-number" type="number" min="0.75" max="2.5" step="0.05" value={config.appearance.brightness ?? 1.35} onChange={(e)=>updateDraftLayer(activeLayerTab,(current)=>({...current,appearance:{...current.appearance,brightness:Math.max(0.75,Math.min(2.5,Number(e.target.value)))}}))}/><span>×</span></span></label>
                    </fieldset>
                  </div> : <p>Scale and appearance controls will become available with this layer renderer.</p>}</section>
                </>;
              })()}
            </div>
            <footer className="wlv-wbv-layer-manager-footer">
              <div className="wlv-wbv-footer-left">
                <button type="button" className="wlv-wbv-control-button" onClick={() => { if(activeLayerTab==="view_properties"){setDraftViewProperties(JSON.parse(JSON.stringify(defaultViewProperties)) as WbvViewProperties);}else if(activeLayerTab==="track_layout"){setDraftTracks(appliedTracks.map((track)=>({...track})));setDraftTrackSpacing(trackSpacing);}else{setDraftLayerConfigs((current)=>current.map((item)=>item.layer_type===activeLayerTab?defaultLayerConfig(activeLayerTab):item));} }}>Reset Tab</button>
                {activeLayerTab === "curve_overlays" ? <div className="wlv-wbv-package-global-actions" aria-label="Selected package actions">
                  <button type="button" className="wlv-wbv-control-button is-primary" disabled={!selectedPublishedPackage || selectedPublishedPackage.status === "active" || selectedPublishedPackage.status === "archived" || publishedPresentationSaving} onClick={()=>selectedPublishedPackage&&void activatePublishedPackage(selectedPublishedPackage.package_uid)}>Promote</button>
                  <button type="button" className="wlv-wbv-control-button" disabled={!selectedPublishedPackage || selectedPublishedPackage.status === "archived" || publishedPresentationSaving} onClick={()=>{setPackageLifecycleError(null);setPendingPackageAction("archive");}}>Archive</button>
                  <button type="button" className="wlv-wbv-control-button is-danger" disabled={!selectedPublishedPackage || publishedPresentationSaving} onClick={()=>{setPackageLifecycleError(null);setPendingPackageAction("delete");}}>Delete</button>
                </div> : null}
              </div>
              <div><button type="button" className="wlv-wbv-control-button" onClick={()=>setLayerManagerOpen(false)}>Cancel</button><button type="button" className="wlv-wbv-control-button is-primary" disabled={layerManagerSaving} onClick={()=>void applyLayerManager()} aria-label="Apply display layer changes" style={layerManagerApplyFlash?{background:"#d9fbe8",color:"#10231a",borderColor:"#9af0c2",boxShadow:"0 0 0 3px rgba(103,213,153,.32), 0 0 18px rgba(103,213,153,.62)",transition:"background 90ms ease,color 90ms ease,border-color 90ms ease,box-shadow 90ms ease"}:{transition:"background 180ms ease,color 180ms ease,border-color 180ms ease,box-shadow 180ms ease"}}>{layerManagerSaving?"Applying…":"Apply"}</button></div>
            </footer>
          </section>
        </div>
        ) : null}
        </ExternalWindowPortal>

        {coreModalOpen && coreModalChunks.length > 0 ? (
          <div
            role="presentation"
            style={{
              position: "fixed",
              inset: 0,
              zIndex: 2147483000,
              pointerEvents: "none",
            }}
          >
            <section
              ref={coreModalWindowRef}
              role="dialog"
              aria-modal="false"
              aria-label="Core inspection"
              style={{
                position: "absolute",
                left: coreModalPosition?.x ?? "50%",
                top: coreModalPosition?.y ?? "50%",
                transform: coreModalPosition ? "none" : "translate(-50%, -50%)",
                width: coreModalSize?.width ?? "min(980px, 88vw)",
                height: coreModalSize?.height ?? "min(820px, 88vh)",
                minWidth: 620,
                minHeight: 480,
                resize: "none",
                overflow: "hidden",
                boxSizing: "border-box",
                border: "1px solid rgba(128,146,160,.48)",
                borderRadius: 10,
                background: "#111820",
                boxShadow: "0 24px 64px rgba(0,0,0,.46)",
                color: "#e5edf4",
                display: "flex",
                flexDirection: "column",
                pointerEvents: "auto",
              }}
            >
              <header
                style={{
                  display:"flex",
                  alignItems:"center",
                  justifyContent:"space-between",
                  gap:16,
                  padding:"12px 14px",
                  borderBottom:"1px solid rgba(128,146,160,.28)",
                  cursor: coreModalDragging ? "grabbing" : "grab",
                  userSelect:"none",
                  flex:"0 0 auto",
                }}
                onPointerDown={(event) => {
                  const target = event.target as HTMLElement;
                  if (target.closest("button")) return;
                  const rect = event.currentTarget.parentElement?.getBoundingClientRect();
                  if (!rect) return;
                  setCoreModalPosition({ x: rect.left, y: rect.top });
                  setCoreModalDragging({
                    startX: event.clientX,
                    startY: event.clientY,
                    originX: rect.left,
                    originY: rect.top,
                  });
                  event.currentTarget.setPointerCapture(event.pointerId);
                }}
                onPointerMove={(event) => {
                  if (!coreModalDragging) return;
                  setCoreModalPosition({
                    x: Math.max(0, Math.min(window.innerWidth - 160, coreModalDragging.originX + event.clientX - coreModalDragging.startX)),
                    y: Math.max(0, Math.min(window.innerHeight - 80, coreModalDragging.originY + event.clientY - coreModalDragging.startY)),
                  });
                }}
                onPointerUp={(event) => {
                  if (coreModalDragging) {
                    setCoreModalDragging(null);
                    try { event.currentTarget.releasePointerCapture(event.pointerId); } catch {}
                  }
                }}
              >
                <div>
                  <div style={{fontWeight:700}}>Core Inspection</div>
                  <div style={{fontSize:12,opacity:.72,marginTop:2}}>
                    {coreLocatorFocusInterval
                      ? `${Math.min(coreLocatorFocusInterval.top_md,coreLocatorFocusInterval.base_md).toLocaleString(undefined,{maximumFractionDigits:2})}–${Math.max(coreLocatorFocusInterval.top_md,coreLocatorFocusInterval.base_md).toLocaleString(undefined,{maximumFractionDigits:2})} MD visible`
                      : `${coreModalTopMd.toLocaleString(undefined,{maximumFractionDigits:2})}–${coreModalBaseMd.toLocaleString(undefined,{maximumFractionDigits:2})} MD`}
                  </div>
                </div>
                <div style={{display:"flex",gap:6}}>
                  <button
                    type="button"
                    className="wlv-wbv-control-button"
                    style={{fontSize:11,padding:"4px 9px",minHeight:28,lineHeight:"16px"}}
                    onClick={()=>setCoreModalOpen(false)}
                  >
                    Close
                  </button>
                </div>
              </header>

              <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",gap:10,padding:"10px 14px",borderBottom:"1px solid rgba(128,146,160,.18)",flex:"0 0 auto"}}>
                <div style={{fontSize:12,opacity:.72}}>
                  Drag core to pan continuously
                </div>
                <div style={{display:"flex",alignItems:"center",gap:8}}>
                  <span style={{fontSize:12,opacity:.72}}>Zoom</span>
                  <button
                    type="button"
                    className="wlv-wbv-control-button"
                    style={{fontSize:12,padding:"3px 8px",minHeight:28,minWidth:34,lineHeight:"16px"}}
                    onClick={()=>setCoreModalZoom((zoom)=>Math.max(.5, Number((zoom-.25).toFixed(2))))}
                  >
                    −
                  </button>
                  <span style={{fontSize:12,minWidth:42,textAlign:"center"}}>{`${Math.round(coreModalZoom*100)}%`}</span>
                  <button
                    type="button"
                    className="wlv-wbv-control-button"
                    style={{fontSize:12,padding:"3px 8px",minHeight:28,minWidth:34,lineHeight:"16px"}}
                    onClick={()=>setCoreModalZoom((zoom)=>Math.min(8, Number((zoom+.25).toFixed(2))))}
                  >
                    +
                  </button>
                  <button
                    type="button"
                    className={`wlv-wbv-control-button${coreModalZoomLocked ? " is-primary" : ""}`}
                    style={{fontSize:11,padding:"4px 9px",minHeight:28,lineHeight:"16px"}}
                    aria-pressed={coreModalZoomLocked}
                    onClick={()=>setCoreModalZoomLocked((locked)=>!locked)}
                  >
                    {coreModalZoomLocked ? "Locked" : "Lock"}
                  </button>
                </div>
              </div>

              <div
                ref={coreModalViewportRef}
                style={{
                  flex:"1 1 auto",
                  overflow:"auto",
                  padding:14,
                  background:"#0b1117",
                  cursor:"grab",
                  touchAction:"none",
                }}
                onScroll={updateCoreModalVisibleInterval}
                onPointerDown={(event) => {
                  const viewport = coreModalViewportRef.current;
                  if (!viewport || event.button !== 0) return;
                  coreModalPanRef.current = {
                    pointerId: event.pointerId,
                    startX: event.clientX,
                    startY: event.clientY,
                    scrollLeft: viewport.scrollLeft,
                    scrollTop: viewport.scrollTop,
                  };
                  viewport.setPointerCapture(event.pointerId);
                  viewport.style.cursor = "grabbing";
                  event.preventDefault();
                }}
                onPointerMove={(event) => {
                  const viewport = coreModalViewportRef.current;
                  const pan = coreModalPanRef.current;
                  if (!viewport || !pan || pan.pointerId !== event.pointerId) return;
                  viewport.scrollLeft = pan.scrollLeft - (event.clientX - pan.startX);
                  viewport.scrollTop = pan.scrollTop - (event.clientY - pan.startY);
                }}
                onPointerUp={(event) => {
                  const viewport = coreModalViewportRef.current;
                  const pan = coreModalPanRef.current;
                  if (!viewport || !pan || pan.pointerId !== event.pointerId) return;
                  coreModalPanRef.current = null;
                  viewport.style.cursor = "grab";
                  try { viewport.releasePointerCapture(event.pointerId); } catch {}
                  updateCoreModalVisibleInterval();
                }}
                onWheel={(event) => {
                  const viewport = coreModalViewportRef.current;
                  if (!viewport || !coreModalChunks.length) return;
                  event.preventDefault();
                  event.stopPropagation();

                  if (coreModalZoomLocked) {
                    // Locked zoom converts the wheel into vertical Core navigation.
                    viewport.scrollTop += event.deltaY;
                    requestAnimationFrame(updateCoreModalVisibleInterval);
                    return;
                  }

                  // Unlocked wheel changes magnification only. It never pans.
                  const oldZoom = coreModalZoom;
                  const nextZoom = Math.max(
                    .5,
                    Math.min(8, Number((oldZoom + (event.deltaY < 0 ? .25 : -.25)).toFixed(2))),
                  );
                  if (nextZoom === oldZoom) return;
                  setCoreModalZoom(nextZoom);
                  requestAnimationFrame(updateCoreModalVisibleInterval);
                }}
              >
                <div
                  style={{
                    display:"flex",
                    justifyContent:"center",
                    alignItems:"stretch",
                    gap:1,
                    width:"max-content",
                    minWidth:"100%",
                    height:`${coreModalContentHeight}px`,
                    minHeight:"100%",
                    userSelect:"none",
                  }}
                >
                  {coreLatticeSide !== "off" ? (
                  <div
                    aria-label="Measured depth lattice"
                    style={{
                      position:"relative",
                      order:coreLatticeSide==="left"?0:4,
                      flex:"0 0 56px",
                      height:`${coreModalContentHeight}px`,
                      transform:`translateX(${coreLatticeSide==="left"?-coreLatticeOffset:coreLatticeOffset}px)`,
                      borderRight:coreLatticeSide==="left"?"1px solid rgba(185,243,255,.35)":"none",
                      borderLeft:coreLatticeSide==="right"?"1px solid rgba(185,243,255,.35)":"none",
                    }}
                  >
                    {coreModalDepthTicks.map((md,index)=>{
                      const topPct = ((md-coreModalTopMd)/Math.max(.001,coreModalBaseMd-coreModalTopMd))*100;
                      const major = Math.abs(md-Math.round(md)) < 1e-6;
                      return (
                        <div
                          key={`core-depth-tick-${index}-${md}`}
                          style={{
                            position:"absolute",
                            top:`${topPct}%`,
                            left:coreLatticeSide==="left"?0:2,
                            right:coreLatticeSide==="left"?2:0,
                            transform:"translateY(-50%)",
                            display:"flex",
                            alignItems:"center",
                            gap:4,
                            flexDirection:coreLatticeSide==="left"?"row":"row-reverse",
                            fontSize:major?11:10,
                            whiteSpace:"nowrap",
                            color:major?"#d9f4ff":"rgba(207,233,244,.72)",
                          }}
                        >
                          <span>{md.toLocaleString(undefined,{maximumFractionDigits:2})}</span>
                          <span style={{display:"block",height:1,width:major?16:9,background:major?"rgba(185,243,255,.82)":"rgba(185,243,255,.42)"}} />
                        </div>
                      );
                    })}
                  </div>
                  ) : null}


                  {coreDescriptionSide !== "off" ? (
                    <div
                      aria-label="Core descriptions"
                      style={{
                        position:"relative",
                        order:coreDescriptionSide==="left"?1:3,
                        flex:`0 0 ${coreDescriptionPanelWidth}px`,
                        width:coreDescriptionPanelWidth,
                        height:`${coreModalContentHeight}px`,
                        borderRight:coreDescriptionSide==="left"?"1px solid rgba(128,146,160,.32)":"none",
                        borderLeft:coreDescriptionSide==="right"?"1px solid rgba(128,146,160,.32)":"none",
                        background:"rgba(12,19,25,.78)",
                        transform:`translateX(${coreDescriptionSide==="left"?-coreDescriptionOffset:coreDescriptionOffset}px)`,
                        overflow:"hidden",
                      }}
                    >
                      {coreModalDescriptions.map((description) => {
                        const topPx = Math.max(0,(description.top_md-coreModalTopMd)*coreModalPixelsPerMd);
                        return (
                          <div
                            key={description.description_id}
                            style={{
                              position:"absolute",
                              top:topPx,
                              left:0,
                              right:0,
                              padding:"3px 6px",
                              borderTop:"1px solid rgba(185,243,255,.42)",
                              boxSizing:"border-box",
                              fontSize:coreDescriptionFontSize,
                              lineHeight:1.18,
                              color:"#dbe7ed",
                              background:"rgba(17,24,32,.92)",
                              overflowWrap:"anywhere",
                            }}
                          >
                            {coreDescriptionShowMd ? (
                              <div style={{fontSize:Math.max(8,coreDescriptionFontSize-1),fontWeight:600,color:"#b9f3ff",marginBottom:2}}>
                                {`${description.top_md.toLocaleString(undefined,{maximumFractionDigits:2})} MD`}
                              </div>
                            ) : null}
                            <div>{description.text}</div>
                          </div>
                        );
                      })}
                    </div>
                  ) : null}

                  <div
                    style={{
                      position:"relative",
                      order:2,
                      width:`${coreModalImageLaneWidth}px`,
                      height:`${coreModalContentHeight}px`,
                      flex:`0 0 ${coreModalImageLaneWidth}px`,
                      background:"#080c10",
                      overflow:"visible",
                    }}
                  >
                    {coreModalChunks.map((chunk) => {
                      const topMd = Math.min(chunk.top_md,chunk.base_md);
                      const baseMd = Math.max(chunk.top_md,chunk.base_md);
                      const topPx = (topMd-coreModalTopMd)*coreModalPixelsPerMd;
                      const heightPx = Math.max(1,(baseMd-topMd)*coreModalPixelsPerMd);
                      return (
                        <img
                          key={chunk.chunk_id}
                          src={chunk.image_url}
                          alt={`${topMd.toLocaleString(undefined,{maximumFractionDigits:2})}–${baseMd.toLocaleString(undefined,{maximumFractionDigits:2})} MD core`}
                          draggable={false}
                          style={{
                            position:"absolute",
                            top:`${topPx}px`,
                            left:"50%",
                            width:"auto",
                            height:`${heightPx}px`,
                            maxWidth:"none",
                            transform:"translateX(-50%)",
                            objectFit:"contain",
                            display:"block",
                            pointerEvents:"none",
                            background:"#080c10",
                          }}
                        />
                      );
                    })}
                  </div>
                </div>
              </div>

              <footer style={{padding:"8px 14px",borderTop:"1px solid rgba(128,146,160,.18)",fontSize:11,opacity:.68,flex:"0 0 auto"}}>
                Wheel: zoom when unlocked / pan when locked · MB1 drag: pan core · Title bar: move modal · Corner tabs: resize
              </footer>

              {(["top-right","bottom-right"] as const).map((corner) => (
                <div
                  key={`core-modal-resize-${corner}`}
                  role="separator"
                  aria-label={`Resize Core Inspection from ${corner}`}
                  style={{
                    position:"absolute",
                    right:-1,
                    top:corner==="top-right"?-1:undefined,
                    bottom:corner==="bottom-right"?-1:undefined,
                    width:20,
                    height:20,
                    cursor:corner==="top-right"?"nesw-resize":"nwse-resize",
                    zIndex:8,
                    pointerEvents:"auto",
                  }}
                  onPointerDown={(event) => {
                    if (event.button !== 0) return;
                    const rect = coreModalWindowRef.current?.getBoundingClientRect();
                    if (!rect) return;
                    setCoreModalPosition({x:rect.left,y:rect.top});
                    setCoreModalSize({width:rect.width,height:rect.height});
                    setCoreModalResizing({
                      pointerId:event.pointerId,
                      corner,
                      startX:event.clientX,
                      startY:event.clientY,
                      originLeft:rect.left,
                      originTop:rect.top,
                      originWidth:rect.width,
                      originHeight:rect.height,
                    });
                    event.currentTarget.setPointerCapture(event.pointerId);
                    event.preventDefault();
                    event.stopPropagation();
                  }}
                  onPointerMove={(event) => {
                    if (!coreModalResizing || coreModalResizing.pointerId !== event.pointerId || coreModalResizing.corner !== corner) return;

                    const dx = event.clientX-coreModalResizing.startX;
                    const dy = event.clientY-coreModalResizing.startY;
                    const maxWidth = Math.max(620,window.innerWidth-coreModalResizing.originLeft-8);
                    const nextWidth = Math.min(maxWidth,Math.max(620,coreModalResizing.originWidth+dx));

                    if (corner==="bottom-right") {
                      const maxHeight = Math.max(480,window.innerHeight-coreModalResizing.originTop-8);
                      const nextHeight = Math.min(maxHeight,Math.max(480,coreModalResizing.originHeight+dy));
                      setCoreModalSize({width:nextWidth,height:nextHeight});
                    } else {
                      const fixedBottom = coreModalResizing.originTop+coreModalResizing.originHeight;
                      const desiredHeight = Math.max(480,coreModalResizing.originHeight-dy);
                      const nextTop = Math.max(8,fixedBottom-desiredHeight);
                      setCoreModalPosition({x:coreModalResizing.originLeft,y:nextTop});
                      setCoreModalSize({width:nextWidth,height:fixedBottom-nextTop});
                    }

                    event.preventDefault();
                    event.stopPropagation();
                  }}
                  onPointerUp={(event) => {
                    if (!coreModalResizing || coreModalResizing.pointerId !== event.pointerId) return;
                    setCoreModalResizing(null);
                    try { event.currentTarget.releasePointerCapture(event.pointerId); } catch {}
                    event.preventDefault();
                    event.stopPropagation();
                  }}
                >
                  <div
                    style={{
                      position:"absolute",
                      inset:3,
                      borderRight:"2px solid rgba(186,201,212,.76)",
                      borderTop:corner==="top-right"?"2px solid rgba(186,201,212,.76)":"none",
                      borderBottom:corner==="bottom-right"?"2px solid rgba(186,201,212,.76)":"none",
                      borderRadius:corner==="top-right"?"0 6px 0 0":"0 0 6px 0",
                    }}
                  />
                  <div
                    style={{
                      position:"absolute",
                      right:5,
                      top:corner==="top-right"?8:undefined,
                      bottom:corner==="bottom-right"?8:undefined,
                      width:8,
                      height:1,
                      background:"rgba(186,201,212,.62)",
                      transform:corner==="top-right"?"rotate(-45deg)":"rotate(45deg)",
                      transformOrigin:"right center",
                    }}
                  />
                </div>
              ))}
            </section>
          </div>
        ) : null}
    </section>
  );
}
