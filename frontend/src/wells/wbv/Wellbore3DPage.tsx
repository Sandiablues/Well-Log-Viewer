import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { fetchWlvJson } from "../../api/wlvBackendClient";
import "./Wellbore3DPage.css";
import {
  WellboreTrajectoryRenderer,
  type WbvViewPreset,
} from "./WellboreTrajectoryRenderer";

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
  well_id?: string | null;
  well_name?: string | null;
  viewer_state?: WbvViewerState;
  coordinate_mode?: string;
  source_session?: WbvSourceSession | null;
  available_layers?: WbvAvailableLayers;
  warnings?: WbvWarning[];
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

type WbvManagerTab = "track_layout" | WbvDisplayLayerKey;

type WbvDisplayLayerKey =
  | "formation_tops"
  | "lithology_intervals"
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
  };
  curve_settings: WbvCurveItemConfig[];
};

type WbvManagerRect = { left: number; top: number; width: number; height: number };

type WbvDisplayLayerConfigurationContract = {
  managed_well_id: string;
  track_spacing: number;
  tracks: WbvTrackConfig[];
  layers: WbvLayerConfig[];
};

type WbvDepthUnit = "ft" | "m";


type WbvInteractionState = {
  managed_well_id: string;
  selection_mode: "none" | "point" | "interval";
  selected_point_visible: boolean;
  interval_visible: boolean;
  selected_point: WbvRenderPoint | null;
  interval_draft_start: WbvRenderPoint | null;
  saved_interval: { interval_id: string; start: WbvRenderPoint; end: WbvRenderPoint; top_md: number; base_md: number; depth_unit: string } | null;
};
type WbvLoadState = {
  session: WbvSessionContract | null;
  viewerPackage: WbvViewerPackageContract | null;
  loading: boolean;
  error: string | null;
};

type Wellbore3DPageProps = {
  onOpenLogViewer: () => void;
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

const viewPresetLabels: Record<WbvViewPreset, string> = {
  reset: "Reset View",
  fit: "Fit Well",
  top: "Top View",
  side: "Side View",
};

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

type WbvViewerControls = {
  boundingBox: boolean;
  depthLabels: boolean;
  surveyStations: boolean;
  groundPlane: boolean;
  bottomGrid: boolean;
  topGrid: boolean;
  axes: boolean;
  surfaceLighting: boolean;
};

type WbvDisplayLayerControls = {
  trajectory: boolean;
};

const initialViewerControls: WbvViewerControls = {
  boundingBox: true,
  depthLabels: true,
  surveyStations: true,
  groundPlane: false,
  bottomGrid: false,
  topGrid: false,
  axes: false,
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

export function Wellbore3DPage({
  onOpenLogViewer,
}: Wellbore3DPageProps) {
  const [state, setState] = useState<WbvLoadState>(initialState);
  const [viewPreset, setViewPreset] = useState<WbvViewPreset>("fit");
  const [viewCommandId, setViewCommandId] = useState(0);
  const [selectedPoint, setSelectedPoint] = useState<WbvRenderPoint | null>(null);
  const [interaction, setInteraction] = useState<WbvInteractionState | null>(null);
  const [interactionSaving, setInteractionSaving] = useState(false);
  const [interactionError, setInteractionError] = useState<string | null>(null);
  const [trackValuesAlongWellbore, setTrackValuesAlongWellbore] = useState(false);
  const [depthUnitSaving, setDepthUnitSaving] = useState(false);
  const [viewerControls, setViewerControls] = useState<WbvViewerControls>(initialViewerControls);
  const [displayLayers, setDisplayLayers] = useState<WbvDisplayLayerControls>({ trajectory: true });
  const [displayLayerFiles, setDisplayLayerFiles] = useState<WbvDisplayLayerFilesContract | null>(null);
  const [, setSelectedDisplayLayerFiles] = useState<Partial<Record<WbvDisplayLayerKey, string>>>({});
  const [curveOverlayProducts, setCurveOverlayProducts] = useState<WbvCurveOverlayProductsContract | null>(null);
  const [, setSelectedCurveOverlayProductId] = useState("");
  const [, setSelectedCurveProductIds] = useState<string[]>([]);
  const [, setCurveOverlayNormalization] = useState<WbvCurveOverlayNormalizationContract | null>(null);
  const [curveOverlayRenderPackage, setCurveOverlayRenderPackage] = useState<WbvCurveOverlayRenderContract | null>(null);
  const [layerManagerOpen, setLayerManagerOpen] = useState(false);
  const [activeLayerTab, setActiveLayerTab] = useState<WbvManagerTab>("curve_overlays");
  const [curveSelectorSearch, setCurveSelectorSearch] = useState("");
  const [draftLayerConfigs, setDraftLayerConfigs] = useState<WbvLayerConfig[]>([]);
  const [appliedLayerConfigs, setAppliedLayerConfigs] = useState<WbvLayerConfig[]>([]);
  const [appliedTracks, setAppliedTracks] = useState<WbvTrackConfig[]>([]);
  const [draftTracks, setDraftTracks] = useState<WbvTrackConfig[]>([]);
  const [trackSpacing, setTrackSpacing] = useState(0.05);
  const [draftTrackSpacing, setDraftTrackSpacing] = useState(0.05);
  const [selectedTrackId, setSelectedTrackId] = useState<string | null>(null);
  const [layerManagerSaving, setLayerManagerSaving] = useState(false);
  const [selectedCurveForEditing, setSelectedCurveForEditing] = useState<string | null>(null);
  const [layerManagerExpanded, setLayerManagerExpanded] = useState(false);
  const [layerManagerRect, setLayerManagerRect] = useState<WbvManagerRect>({ left: 180, top: 110, width: 1120, height: 760 });
  const [layerManagerRestoreRect, setLayerManagerRestoreRect] = useState<WbvManagerRect | null>(null);
  const layerManagerRef = useRef<HTMLElement | null>(null);

  const requestViewPreset = (preset: WbvViewPreset) => {
    setViewPreset(preset);
    setViewCommandId((current) => current + 1);
  };

  const loadWbvSession = useCallback(async () => {
    setState((current) => ({ ...current, loading: true, error: null }));
    try {
      const session = await fetchWlvJson<WbvSessionContract>(
        "/api/wlv/wbv/session",
      );
      // The backend-owned WBV session is the sole active-well authority.
      const managedWellId = session.active_managed_well_id;
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
      const nextCurveOverlayRenderPackage = managedWellId
        ? await fetchWlvJson<WbvCurveOverlayRenderContract>(
            `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/curve-overlays/render-package`,
          )
        : null;
      const nextInteraction = managedWellId
        ? await fetchWlvJson<WbvInteractionState>(`/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/interaction`)
        : null;
      if (managedWellId) {
        const contracts = [
          viewerPackage,
          nextDisplayLayerFiles,
          nextCurveOverlayProducts,
          nextLayerConfiguration,
          nextCurveOverlayRenderPackage,
        ];
        contracts.forEach((contract) => {
          if (contract && contract.managed_well_id !== managedWellId) {
            throw new Error("WBV rejected mixed managed-well contracts from the backend.");
          }
        });
      }
      setCurveOverlayRenderPackage(nextCurveOverlayRenderPackage);
      setInteraction(nextInteraction);
      setSelectedPoint(nextInteraction?.selected_point ?? null);
      setAppliedLayerConfigs(nextLayerConfiguration?.layers ?? []);
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
    } catch (caught) {
      setDisplayLayerFiles(null);
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

  const putInteraction = async (path: string, method: string, body?: object) => {
    const managedWellId = state.viewerPackage?.managed_well_id;
    if (!managedWellId) return null;
    setInteractionSaving(true);
    setInteractionError(null);
    try {
      const next = await fetchWlvJson<WbvInteractionState>(
        `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/interaction/${path}`,
        { method, headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined },
      );
      setInteraction(next);
      setSelectedPoint(next.selected_point ?? null);
      return next;
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "WBV interaction command failed.";
      setInteractionError(message);
      return null;
    } finally {
      setInteractionSaving(false);
    }
  };

  const setSelectionMode = async (mode: "none" | "point" | "interval") => {
    await putInteraction("mode", "PUT", { mode });
  };

  const handleTrajectoryPick = async (point: WbvRenderPoint) => {
    if (interaction?.selection_mode === "point" && interaction.selected_point_visible) {
      await putInteraction("point", "PUT", { point });
    } else if (interaction?.selection_mode === "interval" && interaction.interval_visible) {
      await putInteraction("interval/pick", "PUT", { point });
    }
  };

  const sendIntervalToLogViewer = async () => {
    const managedWellId = state.viewerPackage?.managed_well_id;
    if (!managedWellId) return;
    setInteractionSaving(true);
    setInteractionError(null);
    try {
      await fetchWlvJson(
        `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/interaction/interval/send-to-wdv`,
        { method: "POST" },
      );
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
  }, [loadWbvSession]);

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

  const defaultCurveItemConfig = (curveProductId: string, displayOrder: number): WbvCurveItemConfig => ({
    curve_product_id: curveProductId,
    display_order: displayOrder,
    scale: {
      source: "backend_default",
      minimum: null,
      maximum: null,
      scale_type: "linear",
      direction: "normal",
      direction_source: "governed",
      clamp_outliers: true,
      show_clipping: true,
    },
    appearance: {
      color: ["#58d39b", "#f0b35a", "#65a7ff", "#df78da", "#e86f6f", "#9ad65b"][displayOrder % 6],
      line_width: 1.5,
      opacity: 1,
      display_mode: "line",
      radial_lane: 0,
      track_id: appliedTracks[0]?.track_id ?? "curve-track-0",
      radial_width: 1,
      show_label: true,
      label_position: "top",
      show_clipped_markers: true,
      fill_mode: "none",
      fill_target_curve_product_id: null,
      fill_side: "positive",
      fill_color: ["#58d39b", "#f0b35a", "#65a7ff", "#df78da", "#e86f6f", "#9ad65b"][displayOrder % 6],
      fill_opacity: 0.35,
      fill_baseline_source: "governed",
      fill_baseline_value: null,
      fill_outline: true,
    },
  });

  const defaultLayerConfig = (layerType: WbvDisplayLayerKey): WbvLayerConfig => ({
    layer_type: layerType,
    visible: false,
    selected_item_ids: [],
    source_type: "wmd",
    source_product_id: null,
    scale: { mode: "backend_default", minimum: null, maximum: null, scale_type: "linear", direction: "normal" },
    appearance: { color: null, opacity: 1, line_width: 1, display_mode: "line", show_labels: true },
    curve_settings: [],
  });

  const layerConfigFor = (configs: WbvLayerConfig[], layerType: WbvDisplayLayerKey): WbvLayerConfig =>
    configs.find((item) => item.layer_type === layerType) ?? defaultLayerConfig(layerType);

  const openLayerManager = (tab: WbvManagerTab) => {
    const allTabs: WbvDisplayLayerKey[] = ["formation_tops", "lithology_intervals", "casing_hole_sections", "completions", "curve_overlays", "borehole_imagery"];
    const drafts = allTabs.map((key) => {
      const applied = layerConfigFor(appliedLayerConfigs, key);
      return {
        ...applied,
        selected_item_ids: [...applied.selected_item_ids],
        curve_settings: (applied.curve_settings ?? []).map((item) => ({
          ...item,
          scale: { ...item.scale },
          appearance: { ...item.appearance },
        })),
      };
    });
    const nextTracks: WbvTrackConfig[] = appliedTracks.length > 0 ? appliedTracks.map((track) => ({ ...track })) : [{ track_id: "curve-track-0", display_name: "Track 1", track_type: "curve", display_order: 0, side: "right", width: 1, background_mode: "transparent", background_color: "#000000", background_opacity: 0, border_visible: false, border_color: "#5f6d73", wellbore_offset: 0.15, previous_track_gap: 0.05 }];
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
    setDraftTracks(nextTracks);
    setDraftTrackSpacing(trackSpacing);
    setSelectedTrackId(nextTracks[0]?.track_id ?? null);
    const curveDraft = layerConfigFor(synchronizedDrafts, "curve_overlays");
    setSelectedCurveForEditing(curveDraft.selected_item_ids[0] ?? null);
    setActiveLayerTab(tab);
    setCurveSelectorSearch("");
    const width = Math.min(1180, Math.max(920, window.innerWidth - 180));
    const height = Math.min(820, Math.max(650, window.innerHeight - 140));
    setLayerManagerRect({
      left: Math.max(24, (window.innerWidth - width) / 2),
      top: Math.max(72, (window.innerHeight - height) / 2),
      width,
      height,
    });
    setLayerManagerExpanded(false);
    setLayerManagerOpen(true);
  };

  const updateDraftLayer = (layerType: WbvDisplayLayerKey, updater: (current: WbvLayerConfig) => WbvLayerConfig) => {
    setDraftLayerConfigs((current) => {
      const existing = layerConfigFor(current, layerType);
      const next = updater(existing);
      return [...current.filter((item) => item.layer_type !== layerType), next];
    });
  };

  const curveSettingFor = (config: WbvLayerConfig, curveId: string): WbvCurveItemConfig =>
    config.curve_settings.find((item) => item.curve_product_id === curveId)
      ?? defaultCurveItemConfig(curveId, config.selected_item_ids.indexOf(curveId));

  const updateDraftCurveSetting = (curveId: string, updater: (current: WbvCurveItemConfig) => WbvCurveItemConfig) => {
    updateDraftLayer("curve_overlays", (current) => {
      const existing = curveSettingFor(current, curveId);
      const nextSettings = [
        ...current.curve_settings.filter((item) => item.curve_product_id !== curveId),
        updater(existing),
      ].sort((a, b) => a.display_order - b.display_order);
      return { ...current, curve_settings: nextSettings };
    });
  };

  const toggleDraftCurve = (curveId: string, selected: boolean) => {
    updateDraftLayer("curve_overlays", (current) => {
      if (selected) {
        if (current.selected_item_ids.includes(curveId)) return current;
        const selectedIds = [...current.selected_item_ids, curveId];
        return {
          ...current,
          selected_item_ids: selectedIds,
          curve_settings: [
            ...current.curve_settings,
            (() => {
              const setting = defaultCurveItemConfig(curveId, selectedIds.length - 1);
              const orderedCurveTracks = [...draftTracks].filter((track) => track.track_type === "curve").sort((a, b) => a.display_order - b.display_order);
              const activeCurveTrack = orderedCurveTracks.find((track) => track.track_id === selectedTrackId) ?? orderedCurveTracks[0];
              const activeTrackIndex = activeCurveTrack ? orderedCurveTracks.findIndex((track) => track.track_id === activeCurveTrack.track_id) : -1;
              return activeCurveTrack ? {
                ...setting,
                appearance: { ...setting.appearance, track_id: activeCurveTrack.track_id, radial_lane: Math.max(0, activeTrackIndex) },
              } : setting;
            })(),
          ],
        };
      }
      const selectedIds = current.selected_item_ids.filter((id) => id !== curveId);
      return {
        ...current,
        selected_item_ids: selectedIds,
        curve_settings: current.curve_settings
          .filter((item) => item.curve_product_id !== curveId)
          .map((item, index) => ({
            ...item,
            display_order: index,
            appearance: item.appearance.fill_target_curve_product_id === curveId
              ? { ...item.appearance, fill_target_curve_product_id: null }
              : item.appearance,
          })),
      };
    });
    setSelectedCurveForEditing((current) => selected ? curveId : current === curveId ? null : current);
  };

  const moveDraftCurve = (curveId: string, direction: -1 | 1) => {
    updateDraftLayer("curve_overlays", (current) => {
      const currentSetting = curveSettingFor(current, curveId);
      const trackId = currentSetting.appearance.track_id;
      const trackCurveIds = current.selected_item_ids
        .filter((id) => curveSettingFor(current, id).appearance.track_id === trackId)
        .sort((a, b) => curveSettingFor(current, a).display_order - curveSettingFor(current, b).display_order);
      const index = trackCurveIds.indexOf(curveId);
      const target = index + direction;
      if (index < 0 || target < 0 || target >= trackCurveIds.length) return current;
      [trackCurveIds[index], trackCurveIds[target]] = [trackCurveIds[target], trackCurveIds[index]];
      const trackOrder = new Map(trackCurveIds.map((id, order) => [id, order]));
      return {
        ...current,
        curve_settings: current.curve_settings.map((item) =>
          trackOrder.has(item.curve_product_id)
            ? { ...item, display_order: trackOrder.get(item.curve_product_id) ?? item.display_order }
            : item,
        ),
      };
    });
  };

  const setDraftCurveTrack = (curveId: string, trackId: string) => {
    const orderedCurveTracks = draftTracks
      .filter((track) => track.track_type === "curve")
      .sort((a, b) => a.display_order - b.display_order);
    const targetTrackIndex = orderedCurveTracks.findIndex((track) => track.track_id === trackId);
    if (targetTrackIndex < 0) return;
    updateDraftLayer("curve_overlays", (current) => ({
      ...current,
      curve_settings: current.curve_settings.map((item) => {
        if (item.curve_product_id === curveId) {
          return {
            ...item,
            display_order: current.selected_item_ids.filter((id) => curveSettingFor(current, id).appearance.track_id === trackId).length,
            appearance: {
              ...item.appearance,
              track_id: trackId,
              radial_lane: targetTrackIndex,
              fill_target_curve_product_id: null,
            },
          };
        }
        if (item.appearance.fill_target_curve_product_id === curveId) {
          return { ...item, appearance: { ...item.appearance, fill_target_curve_product_id: null } };
        }
        return item;
      }),
    }));
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

  const applyLayerManager = async () => {
    const managedWellId = state.viewerPackage?.managed_well_id;
    if (!managedWellId) return;
    setLayerManagerSaving(true);
    try {
      const saved = await fetchWlvJson<WbvDisplayLayerConfigurationContract>(
        `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/display-layer-configuration`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            track_spacing: draftTrackSpacing,
            tracks: draftTracks,
            layers: draftLayerConfigs.map((layer) => layer.layer_type !== "curve_overlays" ? layer : {
              ...layer,
              curve_settings: layer.curve_settings.map((setting) => {
                const trackIndex = Math.max(0, draftTracks.findIndex((track) => track.track_id === setting.appearance.track_id));
                return { ...setting, appearance: { ...setting.appearance, radial_lane: trackIndex } };
              }),
            }),
          }),
        },
      );
      setAppliedLayerConfigs(saved.layers);
      setAppliedTracks(saved.tracks ?? []);
      setTrackSpacing(saved.track_spacing ?? 0.05);
      const curveConfig = layerConfigFor(saved.layers, "curve_overlays");
      setSelectedCurveOverlayProductId(curveConfig.source_product_id ?? "");
      await normalizeSelectedCurves(curveConfig.selected_item_ids);
      const renderPackage = await fetchWlvJson<WbvCurveOverlayRenderContract>(
        `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/curve-overlays/render-package`,
      );
      setCurveOverlayRenderPackage(renderPackage);
      setLayerManagerOpen(false);
    } catch (caught) {
      setState((current) => ({ ...current, error: caught instanceof Error ? caught.message : "Unable to save WBV display layers" }));
    } finally { setLayerManagerSaving(false); }
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

  const session = state.session;
  const viewerPackage = state.viewerPackage;
  const trajectory = viewerPackage?.trajectory;
  const surveyQaqc = viewerPackage?.survey_qaqc;
  const renderPoints = trajectory?.render_points ?? [];
  const viewerState =
    viewerPackage?.viewer_state ?? session?.viewer_state ?? "not_loaded";
  const layers = viewerPackage?.available_layers ?? session?.available_layers;
  const hasTrajectory = renderPoints.length > 0;
  const depthUnit = viewerPackage?.depth_unit ?? "ft";
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

  return (
    <section className="wlv-wbv-page" aria-label="3D Wellbore Viewer">
      <header className="wlv-wbv-header">
        <div>
          <span className="wlv-page-kicker">3D Wellbore</span>
          <h1>3D Wellbore Viewer</h1>
          <p>
            Inspect the managed well trajectory, survey quality, depth
            relationships, and source provenance in three dimensions.
          </p>
        </div>
        <div
          className="wlv-wbv-header-actions"
          aria-label="3D Wellbore Viewer actions"
        >
          <span
            className={`wlv-wbv-state-pill wlv-wbv-state-pill--${viewerState}`}
          >
            {stateLabel(viewerState)}
          </span>
          <button type="button" onClick={() => void loadWbvSession()}>
            Refresh
          </button>
          <button type="button" onClick={onOpenLogViewer}>
            Open WDV
          </button>
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
                ["axes", "Axes"],
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
                ["formation_tops", "Formation tops"], ["lithology_intervals", "Lithology intervals"], ["casing_hole_sections", "Casing / hole sections"],
                ["completions", "Completions"], ["curve_overlays", "Curve overlays"], ["borehole_imagery", "Borehole imagery"],
              ] as Array<[WbvDisplayLayerKey, string]>).map(([key, label]) => {
                const config = layerConfigFor(appliedLayerConfigs, key);
                const configured = config.selected_item_ids.length > 0 || Boolean(config.source_product_id);
                return <label key={key} className={!configured ? "is-disabled" : ""} onClick={() => setActiveLayerTab(key)}>
                  <input type="checkbox" checked={configured && config.visible} disabled={!configured} onChange={(event) => {
                    event.stopPropagation();
                    const next = appliedLayerConfigs.map((item) => item.layer_type === key ? { ...item, visible: event.target.checked } : item);
                    setAppliedLayerConfigs(next);
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

          <div className="wlv-wbv-control-group" aria-label="WBV view controls">
            {(Object.keys(viewPresetLabels) as WbvViewPreset[]).map(
              (preset) => (
                <button
                  type="button"
                  key={preset}
                  className={viewPreset === preset ? "is-active" : ""}
                  disabled={!hasTrajectory}
                  onClick={() => requestViewPreset(preset)}
                >
                  {viewPresetLabels[preset]}
                </button>
              ),
            )}
          </div>
        </aside>

        <main className="wlv-wbv-scene-shell" aria-label="WBV 3D scene shell">
          <div
            className={`wlv-wbv-scene-frame ${hasTrajectory ? "has-trajectory-package" : ""}`}
          >
            {viewerControls.axes ? (
              <>
                <div className="wlv-wbv-axis-label wlv-wbv-axis-label--x">X</div>
                <div className="wlv-wbv-axis-label wlv-wbv-axis-label--y">Y</div>
                <div className="wlv-wbv-axis-label wlv-wbv-axis-label--z">Z / TVD</div>
              </>
            ) : null}

            {hasTrajectory ? (
              <WellboreTrajectoryRenderer
                renderPoints={renderPoints}
                boundingBox={viewerPackage?.bounding_box}
                depthUnit={depthUnit}
                viewerState={viewerState}
                viewPreset={viewPreset}
                viewCommandId={viewCommandId}
                onPointSelect={handleTrajectoryPick}
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
                showAxes={viewerControls.axes}
                useSurfaceLighting={viewerControls.surfaceLighting}
                curveOverlays={curveOverlayRenderPackage?.curves ?? []}
                curveTracks={curveOverlayRenderPackage?.tracks ?? appliedTracks}
                curveTrackSpacing={curveOverlayRenderPackage?.track_spacing ?? trackSpacing}
                showCurveOverlays={layerConfigFor(appliedLayerConfigs, "curve_overlays").visible}
              />
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
            <strong>Well &amp; Trajectory</strong>
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

          <section className="wlv-wbv-information-section" aria-label="Interval selection">
            <div className="wlv-wbv-section-heading-row"><h2>Interval Selection</h2><input aria-label="Enable Interval Selection" type="checkbox" checked={interaction?.selection_mode === "interval"} disabled={interactionSaving} onChange={(event) => setSelectionMode(event.target.checked ? "interval" : "none")} /></div>
            {interaction?.saved_interval ? <div className="wlv-wbv-selected-point-table">
              <div className="wlv-wbv-selected-point-row"><span>Start MD</span><strong>{formatNumber(interaction.saved_interval.start.md, 1)} {depthUnit}</strong></div>
              <div className="wlv-wbv-selected-point-row"><span>End MD</span><strong>{formatNumber(interaction.saved_interval.end.md, 1)} {depthUnit}</strong></div>
              <div className="wlv-wbv-selected-point-row"><span>Length</span><strong>{formatNumber(interaction.saved_interval.base_md - interaction.saved_interval.top_md, 1)} {depthUnit}</strong></div>
            </div> : <p className="wlv-wbv-information-empty">{interaction?.interval_draft_start ? "Select the interval end." : "Select the interval start, then the end."}</p>}
            <div className="wlv-wbv-inline-action-row">
              <button type="button" className="wlv-wbv-control-button wlv-wbv-control-button--compact" disabled={!interaction?.saved_interval || interactionSaving} onClick={sendIntervalToLogViewer}>Send to Log Viewer as AOI</button>
              <button type="button" className="wlv-wbv-control-button wlv-wbv-control-button--compact" disabled={(!interaction?.saved_interval && !interaction?.interval_draft_start) || interactionSaving} onClick={()=>putInteraction("interval","DELETE")}>Clear</button>
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

      {layerManagerOpen ? (
        <div className="wlv-wbv-modal-backdrop wlv-wbv-modal-backdrop--floating" role="presentation">
          <section
            ref={layerManagerRef}
            className={["wlv-wbv-layer-manager-modal", layerManagerExpanded ? "is-expanded" : ""].filter(Boolean).join(" ")}
            role="dialog"
            aria-modal="false"
            aria-labelledby="wbv-layer-manager-title"
            style={{ left: layerManagerRect.left, top: layerManagerRect.top, width: layerManagerRect.width, height: layerManagerRect.height }}
          >
            <header className="wlv-wbv-layer-manager-header" onPointerDown={beginLayerManagerDrag}>
              <div><span className="wlv-wbv-eyebrow">DISPLAY LAYERS</span><h2 id="wbv-layer-manager-title">Manage Display Layers</h2></div>
              <div className="wlv-wbv-layer-manager-header-actions">
                <button type="button" className="wlv-wbv-control-button" onClick={toggleLayerManagerExpanded}>{layerManagerExpanded ? "Restore" : "Expand"}</button>
                <button type="button" className="wlv-wbv-icon-button" aria-label="Close display-layer manager" onClick={() => setLayerManagerOpen(false)}>×</button>
              </div>
            </header>
            <nav className="wlv-wbv-layer-tabs" aria-label="Display layer tabs">
              {([
                ["track_layout", "Track Layout"], ["formation_tops", "Formation Tops"], ["lithology_intervals", "Lithology"], ["casing_hole_sections", "Casing / Hole"],
                ["completions", "Completions"], ["curve_overlays", "Curve Overlays"], ["borehole_imagery", "Borehole Imagery"],
              ] as Array<[WbvManagerTab, string]>).map(([key,label]) => <button type="button" key={key} className={activeLayerTab===key?"is-active":""} onClick={() => setActiveLayerTab(key)}>{label}</button>)}
            </nav>
            <div className={["wlv-wbv-layer-manager-body", activeLayerTab === "track_layout" ? "is-track-layout" : ""].filter(Boolean).join(" ")}>
              {(() => {
                if (activeLayerTab === "track_layout") {
                  const selectedTrack = draftTracks.find((track) => track.track_id === selectedTrackId) ?? draftTracks[0] ?? null;
                  const sameSideTracks = selectedTrack
                    ? [...draftTracks].filter((track) => track.side === selectedTrack.side).sort((a, b) => a.display_order - b.display_order)
                    : [];
                  const selectedTrackSideIndex = selectedTrack
                    ? sameSideTracks.findIndex((track) => track.track_id === selectedTrack.track_id)
                    : -1;
                  const selectedTrackUsesWellboreOffset = selectedTrack?.side !== "center" && selectedTrackSideIndex === 0;
                  const selectedTrackGapLabel = selectedTrack?.side === "right"
                    ? "Gap from track on the left"
                    : selectedTrack?.side === "left"
                      ? "Gap from track on the right"
                      : "Offset from wellbore";
                  const updateTrack = (trackId: string, updater: (track: WbvTrackConfig) => WbvTrackConfig) => setDraftTracks((current) => current.map((track) => track.track_id === trackId ? updater(track) : track));
                  const addTrack = () => { const index = draftTracks.length; const track: WbvTrackConfig = { track_id: `curve-track-${Date.now()}`, display_name: `Track ${index + 1}`, track_type: "curve", display_order: index, side: "right", width: 1, background_mode: "transparent", background_color: "#000000", background_opacity: 0, border_visible: false, border_color: "#5f6d73", wellbore_offset: 0.15, previous_track_gap: draftTrackSpacing }; setDraftTracks((current) => [...current, track]); setSelectedTrackId(track.track_id); };
                  const moveTrack = (direction: -1 | 1) => { if (!selectedTrack) return; setDraftTracks((current) => { const ordered=[...current].sort((a,b)=>a.display_order-b.display_order); const index=ordered.findIndex((track)=>track.track_id===selectedTrack.track_id); const target=index+direction; if(target<0||target>=ordered.length)return current; [ordered[index],ordered[target]]=[ordered[target],ordered[index]]; return ordered.map((track,display_order)=>({...track,display_order})); }); };
                  return <><section className="wlv-wbv-manager-inventory-panel wlv-wbv-track-layout-list"><div className="wlv-wbv-manager-panel-title"><div><h3>Tracks</h3><span>{draftTracks.length} configured</span></div></div><div className="wlv-wbv-track-list">{[...draftTracks].sort((a,b)=>a.display_order-b.display_order).map((track)=><button type="button" key={track.track_id} className={track.track_id===selectedTrack?.track_id?"is-current":""} onClick={()=>setSelectedTrackId(track.track_id)}><span>{track.display_order+1}</span><strong>{track.display_name}</strong><small>{track.side === "center" ? "center" : track.side} · {track.width.toFixed(2)}</small></button>)}</div><div className="wlv-wbv-track-actions"><button type="button" className="wlv-wbv-control-button" onClick={addTrack}>Add Track</button><button type="button" className="wlv-wbv-control-button" disabled={!selectedTrack} onClick={()=>moveTrack(-1)}>Up</button><button type="button" className="wlv-wbv-control-button" disabled={!selectedTrack} onClick={()=>moveTrack(1)}>Down</button><button type="button" className="wlv-wbv-control-button" disabled={!selectedTrack||draftTracks.length===1||layerConfigFor(draftLayerConfigs,"curve_overlays").selected_item_ids.some((curveId)=>curveSettingFor(layerConfigFor(draftLayerConfigs,"curve_overlays"),curveId).appearance.track_id===selectedTrack.track_id)} title={selectedTrack&&layerConfigFor(draftLayerConfigs,"curve_overlays").selected_item_ids.some((curveId)=>curveSettingFor(layerConfigFor(draftLayerConfigs,"curve_overlays"),curveId).appearance.track_id===selectedTrack.track_id)?"Reassign curves before removing this track":undefined} onClick={()=>{if(!selectedTrack)return; setDraftTracks((current)=>current.filter((track)=>track.track_id!==selectedTrack.track_id).map((track,index)=>({...track,display_order:index}))); setSelectedTrackId(draftTracks.find((track)=>track.track_id!==selectedTrack.track_id)?.track_id??null);}}>Remove</button></div></section><section className="wlv-wbv-manager-selected-panel"><div className="wlv-wbv-manager-panel-title"><div><h3>Layout Defaults</h3><span>Global track geometry</span></div></div><label className="wlv-wbv-field">Default gap for new tracks<input type="number" min="0" max="20" step="0.01" value={draftTrackSpacing} onChange={(event)=>setDraftTrackSpacing(Number(event.target.value))}/></label><p>Track order is measured outward from the wellbore on each side.</p></section><section className="wlv-wbv-manager-properties-panel"><div className="wlv-wbv-manager-panel-title"><div><h3>Track Properties</h3><span>{selectedTrack?.display_name??"Select a track"}</span></div></div>{selectedTrack?<div className="wlv-wbv-properties-scroll"><label className="wlv-wbv-field">Name<input value={selectedTrack.display_name} onChange={(event)=>updateTrack(selectedTrack.track_id,(track)=>({...track,display_name:event.target.value}))}/></label><div className="wlv-wbv-inline-fields"><label className="wlv-wbv-field">Type<select value={selectedTrack.track_type} onChange={(event)=>updateTrack(selectedTrack.track_id,(track)=>({...track,track_type:event.target.value as WbvTrackConfig["track_type"]}))}><option value="curve">Curve Track</option><option value="reference">Reference Track</option><option value="image">Image Track</option><option value="interval">Interval Track</option></select></label><label className="wlv-wbv-field">Position<select value={selectedTrack.side} onChange={(event)=>{const position=event.target.value as WbvTrackConfig["side"]; updateTrack(selectedTrack.track_id,(track)=>({...track,side:position,wellbore_offset:position==="center"?0:track.wellbore_offset}));}}><option value="left">Left</option><option value="center">Center — over wellbore</option><option value="right">Right</option></select></label></div><div className="wlv-wbv-inline-fields"><label className="wlv-wbv-field">Width<input type="number" min="0.1" max="20" step="0.1" value={selectedTrack.width} onChange={(event)=>updateTrack(selectedTrack.track_id,(track)=>({...track,width:Number(event.target.value)}))}/></label><label className="wlv-wbv-field">{selectedTrack.side === "center" || selectedTrackUsesWellboreOffset ? "Offset from wellbore" : selectedTrackGapLabel}<input type="number" min="0" max="20" step="0.01" disabled={selectedTrack.side === "center"} value={selectedTrack.side === "center" ? 0 : selectedTrackUsesWellboreOffset ? selectedTrack.wellbore_offset : selectedTrack.previous_track_gap ?? draftTrackSpacing} onChange={(event)=>updateTrack(selectedTrack.track_id,(track)=>selectedTrackUsesWellboreOffset ? {...track,wellbore_offset:Number(event.target.value)} : {...track,previous_track_gap:Number(event.target.value)})}/></label></div><label className="wlv-wbv-field">Background<select value={selectedTrack.background_mode} onChange={(event)=>updateTrack(selectedTrack.track_id,(track)=>({...track,background_mode:event.target.value as WbvTrackConfig["background_mode"]}))}><option value="transparent">Transparent</option><option value="black">Black</option><option value="white">White</option><option value="custom">Custom</option></select></label>{selectedTrack.background_mode==="custom"?<label className="wlv-wbv-field">Background colour<input type="color" value={selectedTrack.background_color} onChange={(event)=>updateTrack(selectedTrack.track_id,(track)=>({...track,background_color:event.target.value}))}/></label>:null}<label className="wlv-wbv-field">Background opacity<input type="number" min="0" max="1" step="0.05" value={selectedTrack.background_opacity} onChange={(event)=>updateTrack(selectedTrack.track_id,(track)=>({...track,background_opacity:Number(event.target.value)}))}/></label><label className="wlv-wbv-check-row"><input type="checkbox" checked={selectedTrack.border_visible} onChange={(event)=>updateTrack(selectedTrack.track_id,(track)=>({...track,border_visible:event.target.checked}))}/><span>Show track border</span></label></div>:<div className="wlv-wbv-empty-state">Select a track.</div>}</section></>;
                }
                const config = layerConfigFor(draftLayerConfigs, activeLayerTab);
                if (activeLayerTab === "curve_overlays") {
                  const products = curveOverlayProducts?.products ?? [];
                  const product = products.find((item) => item.curve_product_id === config.source_product_id) ?? null;
                  const curves = product?.curves ?? [];
                  const curveById = new Map(curves.map((curve) => [curve.curve_product_id, curve]));
                  const query = curveSelectorSearch.trim().toLowerCase();
                  const filtered = curves.filter((curve) => !query || [curve.mnemonic, curve.display_name, curve.description ?? "", curve.unit ?? "", curve.curve_family ?? ""].some((value) => value.toLowerCase().includes(query)));
                  const grouped = filtered.reduce<Record<string, WbvCurveOverlayCurve[]>>((acc, curve) => {
                    const family = (curve.curve_family || "Unclassified").trim().toUpperCase();
                    (acc[family] ??= []).push(curve);
                    return acc;
                  }, {});
                  const selectedCurve = selectedCurveForEditing ? curveById.get(selectedCurveForEditing) ?? null : null;
                  const selectedSetting = selectedCurveForEditing ? curveSettingFor(config, selectedCurveForEditing) : null;
                  const coverage = (curve: WbvCurveOverlayCurve) => {
                    const managedInterval = curve.run_interval?.trim();
                    if (managedInterval) return managedInterval;
                    if (curve.depth_start == null && curve.depth_end == null) return "";
                    const unit = curve.depth_units ?? "";
                    return `${curve.depth_start ?? "—"}–${curve.depth_end ?? "—"} ${unit}`.trim();
                  };
                  const curveMetadataTitle = (curve: WbvCurveOverlayCurve) => [
                    curve.description || curve.display_name,
                    coverage(curve),
                    curve.run_number ? `Run ${curve.run_number}` : "",
                    curve.run_date ?? "",
                    curve.curve_family ?? "",
                    curve.classification_source ?? "",
                    curve.classification_confidence ?? "",
                    curve.review_required ? "Review required" : "",
                    curve.unit ?? "",
                  ].filter(Boolean).join(" · ");
                  return <>
                    <section className="wlv-wbv-manager-inventory-panel">
                      <div className="wlv-wbv-manager-panel-title"><div><h3>Curve Inventory</h3><span>{curves.length} available · {config.selected_item_ids.length} selected</span></div></div>
                      <label className="wlv-wbv-field">Source product<select value={config.source_product_id ?? ""} onChange={(event) => updateDraftLayer(activeLayerTab, (current) => ({...current, source_product_id:event.target.value||null, selected_item_ids:[], curve_settings:[]}))}><option value="">Select registered curve product</option>{products.map((item)=><option key={item.curve_product_id} value={item.curve_product_id}>{item.display_name} ({item.curve_count})</option>)}</select></label>
                      <div className="wlv-wbv-curve-inventory-toolbar"><input type="search" value={curveSelectorSearch} onChange={(event)=>setCurveSelectorSearch(event.target.value)} placeholder="Filter curves"/><button type="button" className="wlv-wbv-control-button" onClick={()=>updateDraftLayer(activeLayerTab,(current)=>({...current,selected_item_ids:curves.map((curve)=>curve.curve_product_id),curve_settings:curves.map((curve,index)=>current.curve_settings.find((item)=>item.curve_product_id===curve.curve_product_id) ?? defaultCurveItemConfig(curve.curve_product_id,index))}))}>Select all</button><button type="button" className="wlv-wbv-control-button" onClick={()=>{updateDraftLayer(activeLayerTab,(current)=>({...current,selected_item_ids:[],curve_settings:[]}));setSelectedCurveForEditing(null);}}>Clear all</button></div>
                      <div className="wlv-wbv-wdv-curve-inventory">
                        {Object.entries(grouped).sort(([a],[b])=>a.localeCompare(b)).map(([family, familyCurves]) => <section key={family} className="wlv-wbv-curve-family-group"><h4>{family}</h4>{familyCurves.map((curve) => {
                          const isSelected = config.selected_item_ids.includes(curve.curve_product_id);
                          return <label key={curve.curve_product_id} className={["wlv-wbv-wdv-curve-row", selectedCurveForEditing===curve.curve_product_id?"is-current":""].filter(Boolean).join(" ")} onClick={()=>isSelected&&setSelectedCurveForEditing(curve.curve_product_id)} title={curveMetadataTitle(curve)}><input type="checkbox" checked={isSelected} onChange={(event)=>toggleDraftCurve(curve.curve_product_id,event.target.checked)}/><strong>{curve.mnemonic}</strong><span>{curve.description || curve.display_name}{coverage(curve)?` · ${coverage(curve)}`:""}{curve.run_number?` · Run ${curve.run_number}`:""}</span><em>{curve.unit??"—"}</em></label>;
                        })}</section>)}
                        {filtered.length===0?<div className="wlv-wbv-empty-state">No curves match this filter.</div>:null}
                      </div>
                    </section>
                    <section className="wlv-wbv-manager-selected-panel">
                      <div className="wlv-wbv-manager-panel-title"><div><h3>Curves by Track</h3><span>Assignments follow Track Layout</span></div></div>
                      <div className="wlv-wbv-selected-curve-list">{draftTracks.filter((track)=>track.track_type==="curve").sort((a,b)=>a.display_order-b.display_order).map((track)=>{const trackCurveIds=config.selected_item_ids.filter((curveId)=>curveSettingFor(config,curveId).appearance.track_id===track.track_id).sort((a,b)=>curveSettingFor(config,a).display_order-curveSettingFor(config,b).display_order);const selectedCurveTrackId=selectedCurveForEditing?curveSettingFor(config,selectedCurveForEditing).appearance.track_id:null;return <section className={["wlv-wbv-lane-group",selectedTrackId===track.track_id?"is-target":""].filter(Boolean).join(" ")} key={track.track_id}><header onClick={()=>setSelectedTrackId(track.track_id)}><strong>{track.display_name}</strong><div className="wlv-wbv-track-group-tools"><span>{trackCurveIds.length} curve{trackCurveIds.length===1?"":"s"}</span><button type="button" disabled={!selectedCurveForEditing||selectedCurveTrackId===track.track_id} onClick={(event)=>{event.stopPropagation();if(selectedCurveForEditing)setDraftCurveTrack(selectedCurveForEditing,track.track_id);}}>Move selected here</button></div></header>{trackCurveIds.length===0?<div className="wlv-wbv-empty-track">No curves assigned. Select a curve in another track, then choose “Move selected here”.</div>:trackCurveIds.map((curveId,index)=>{const curve=curveById.get(curveId);return <div role="button" tabIndex={0} key={curveId} className={selectedCurveForEditing===curveId?"is-current":""} onClick={()=>setSelectedCurveForEditing(curveId)} onKeyDown={(event)=>{if(event.key==="Enter"||event.key===" "){event.preventDefault();setSelectedCurveForEditing(curveId);}}}><span className="wlv-wbv-lane-order">{index+1}</span><strong>{curve?.mnemonic??curveId}</strong><small>{curve?.unit??"—"}</small><select className="wlv-wbv-curve-track-select" aria-label={`Assign ${curve?.mnemonic??curveId} to track`} value={track.track_id} onClick={(event)=>event.stopPropagation()} onChange={(event)=>{event.stopPropagation();setDraftCurveTrack(curveId,event.target.value);}}>{draftTracks.filter((candidate)=>candidate.track_type==="curve").sort((a,b)=>a.display_order-b.display_order).map((candidate)=><option key={candidate.track_id} value={candidate.track_id}>{candidate.display_name}</option>)}</select><span className="wlv-wbv-selected-curve-actions"><button type="button" aria-label="Move curve up in track" disabled={index===0} onClick={(event)=>{event.stopPropagation();moveDraftCurve(curveId,-1);}}>↑</button><button type="button" aria-label="Move curve down in track" disabled={index===trackCurveIds.length-1} onClick={(event)=>{event.stopPropagation();moveDraftCurve(curveId,1);}}>↓</button><button type="button" aria-label="Remove curve" onClick={(event)=>{event.stopPropagation();toggleDraftCurve(curveId,false);}}>×</button></span></div>})}</section>})}{draftTracks.filter((track)=>track.track_type==="curve").length===0?<div className="wlv-wbv-empty-state">Create a Curve Track in Track Layout before assigning curves.</div>:null}{config.selected_item_ids.length===0?<div className="wlv-wbv-empty-state">Select a destination track, then select curves from the inventory.</div>:null}</div>
                    </section>
                    <section className="wlv-wbv-manager-properties-panel">
                      <div className="wlv-wbv-manager-panel-title"><div><h3>Properties</h3><span>{selectedCurve ? `${selectedCurve.mnemonic} · ${selectedCurve.unit??"—"}` : "Select a curve to edit"}</span></div></div>
                      {selectedCurve && selectedSetting ? <div className="wlv-wbv-curve-properties">
                        <fieldset><legend>Scale</legend>
                          <label className="wlv-wbv-field">Range source<select value={selectedSetting.scale.source} onChange={(event)=>updateDraftCurveSetting(selectedCurve.curve_product_id,(current)=>({...current,scale:{...current.scale,source:event.target.value as WbvCurveScaleSource}}))}><option value="backend_default">Backend / KR governed</option><option value="kr_curve">KR curve rule</option><option value="kr_family">KR family rule</option><option value="robust_p5_p95">Robust P5–P95</option><option value="manual">Manual</option></select></label>
                          <div className="wlv-wbv-inline-fields"><label className="wlv-wbv-field">Minimum<input type="number" step="any" disabled={selectedSetting.scale.source!=="manual"} value={selectedSetting.scale.minimum??""} onChange={(event)=>updateDraftCurveSetting(selectedCurve.curve_product_id,(current)=>({...current,scale:{...current.scale,minimum:event.target.value===""?null:Number(event.target.value)}}))}/></label><label className="wlv-wbv-field">Maximum<input type="number" step="any" disabled={selectedSetting.scale.source!=="manual"} value={selectedSetting.scale.maximum??""} onChange={(event)=>updateDraftCurveSetting(selectedCurve.curve_product_id,(current)=>({...current,scale:{...current.scale,maximum:event.target.value===""?null:Number(event.target.value)}}))}/></label></div>
                          <div className="wlv-wbv-inline-fields"><label className="wlv-wbv-field">Scale type<select value={selectedSetting.scale.scale_type} onChange={(event)=>updateDraftCurveSetting(selectedCurve.curve_product_id,(current)=>({...current,scale:{...current.scale,scale_type:event.target.value as "linear"|"logarithmic"}}))}><option value="linear">Linear</option><option value="logarithmic">Logarithmic</option></select></label><label className="wlv-wbv-field">Direction<select value={selectedSetting.scale.direction} onChange={(event)=>updateDraftCurveSetting(selectedCurve.curve_product_id,(current)=>({...current,scale:{...current.scale,direction:event.target.value as "normal"|"reversed",direction_source:"manual"}}))}><option value="normal">Normal</option><option value="reversed">Reverse</option></select></label></div>
                          <label className="wlv-wbv-check-row"><input type="checkbox" checked={selectedSetting.scale.clamp_outliers} onChange={(event)=>updateDraftCurveSetting(selectedCurve.curve_product_id,(current)=>({...current,scale:{...current.scale,clamp_outliers:event.target.checked}}))}/><span>Clamp outliers to display envelope</span></label>
                          <label className="wlv-wbv-check-row"><input type="checkbox" checked={selectedSetting.scale.show_clipping} onChange={(event)=>updateDraftCurveSetting(selectedCurve.curve_product_id,(current)=>({...current,scale:{...current.scale,show_clipping:event.target.checked}}))}/><span>Show clipped-value indicators</span></label>
                        </fieldset>
                        <fieldset><legend>Appearance</legend>
                          <label className="wlv-wbv-field">Colour<input type="color" value={selectedSetting.appearance.color} onChange={(event)=>updateDraftCurveSetting(selectedCurve.curve_product_id,(current)=>({...current,appearance:{...current.appearance,color:event.target.value}}))}/></label>
                          <div className="wlv-wbv-inline-fields"><label className="wlv-wbv-field">Line width<input type="number" min="0.1" max="20" step="0.1" value={selectedSetting.appearance.line_width} onChange={(event)=>updateDraftCurveSetting(selectedCurve.curve_product_id,(current)=>({...current,appearance:{...current.appearance,line_width:Number(event.target.value)}}))}/></label><label className="wlv-wbv-field">Opacity<input type="number" min="0" max="1" step="0.05" value={selectedSetting.appearance.opacity} onChange={(event)=>updateDraftCurveSetting(selectedCurve.curve_product_id,(current)=>({...current,appearance:{...current.appearance,opacity:Number(event.target.value)}}))}/></label></div>
                          <div className="wlv-wbv-inline-fields"><label className="wlv-wbv-field">Display mode<select value={selectedSetting.appearance.display_mode} onChange={(event)=>updateDraftCurveSetting(selectedCurve.curve_product_id,(current)=>({...current,appearance:{...current.appearance,display_mode:event.target.value as "line"|"ribbon"}}))}><option value="line">Line</option><option value="ribbon">Ribbon</option></select></label><label className="wlv-wbv-field">Track<select value={selectedSetting.appearance.track_id ?? ""} onChange={(event)=>setDraftCurveTrack(selectedCurve.curve_product_id,event.target.value)}>{draftTracks.filter((track)=>track.track_type==="curve").sort((a,b)=>a.display_order-b.display_order).map((track)=><option key={track.track_id} value={track.track_id}>{track.display_name}</option>)}</select></label></div>
                          <label className="wlv-wbv-field">Radial width<input type="number" min="0.1" max="10" step="0.1" value={selectedSetting.appearance.radial_width} onChange={(event)=>updateDraftCurveSetting(selectedCurve.curve_product_id,(current)=>({...current,appearance:{...current.appearance,radial_width:Number(event.target.value)}}))}/></label>
                          <label className="wlv-wbv-field">Label position<select value={selectedSetting.appearance.label_position} onChange={(event)=>updateDraftCurveSetting(selectedCurve.curve_product_id,(current)=>({...current,appearance:{...current.appearance,label_position:event.target.value as "top"|"base"|"both"|"none",show_label:event.target.value!=="none"}}))}><option value="top">Top</option><option value="base">Base</option><option value="both">Top and base</option><option value="none">Hidden</option></select></label>
                          <label className="wlv-wbv-check-row"><input type="checkbox" checked={selectedSetting.appearance.show_clipped_markers} onChange={(event)=>updateDraftCurveSetting(selectedCurve.curve_product_id,(current)=>({...current,appearance:{...current.appearance,show_clipped_markers:event.target.checked}}))}/><span>Show clipped-value markers</span></label>
                          <div className="wlv-wbv-inline-fields"><label className="wlv-wbv-field">Fill<select value={selectedSetting.appearance.fill_mode} onChange={(event)=>updateDraftCurveSetting(selectedCurve.curve_product_id,(current)=>({...current,appearance:{...current.appearance,fill_mode:event.target.value as "none"|"to_baseline"|"between_curves",fill_target_curve_product_id:null}}))}><option value="none">None</option><option value="to_baseline">To baseline</option><option value="between_curves">Between curves</option></select></label>{selectedSetting.appearance.fill_mode==="between_curves"?<label className="wlv-wbv-field">Fill to curve<select value={selectedSetting.appearance.fill_target_curve_product_id??""} onChange={(event)=>updateDraftCurveSetting(selectedCurve.curve_product_id,(current)=>({...current,appearance:{...current.appearance,fill_target_curve_product_id:event.target.value||null}}))}><option value="">Choose curve</option>{config.selected_item_ids.filter((curveId)=>curveId!==selectedCurve.curve_product_id&&curveSettingFor(config,curveId).appearance.track_id===selectedSetting.appearance.track_id).map((curveId)=><option key={curveId} value={curveId}>{curveById.get(curveId)?.mnemonic??curveId}</option>)}</select></label>:<label className="wlv-wbv-field">Fill side<select disabled={selectedSetting.appearance.fill_mode!=="to_baseline"} value={selectedSetting.appearance.fill_side} onChange={(event)=>updateDraftCurveSetting(selectedCurve.curve_product_id,(current)=>({...current,appearance:{...current.appearance,fill_side:event.target.value as "positive"|"negative"}}))}><option value="positive">Positive</option><option value="negative">Negative</option></select></label>}</div>
                          <div className="wlv-wbv-inline-fields"><label className="wlv-wbv-field">Fill colour<input type="color" disabled={selectedSetting.appearance.fill_mode==="none"} value={selectedSetting.appearance.fill_color} onChange={(event)=>updateDraftCurveSetting(selectedCurve.curve_product_id,(current)=>({...current,appearance:{...current.appearance,fill_color:event.target.value}}))}/></label><label className="wlv-wbv-field">Fill opacity<input type="number" min="0" max="1" step="0.05" disabled={selectedSetting.appearance.fill_mode==="none"} value={selectedSetting.appearance.fill_opacity} onChange={(event)=>updateDraftCurveSetting(selectedCurve.curve_product_id,(current)=>({...current,appearance:{...current.appearance,fill_opacity:Number(event.target.value)}}))}/></label></div>
                          <div className="wlv-wbv-inline-fields"><label className="wlv-wbv-field">Baseline<select disabled={selectedSetting.appearance.fill_mode!=="to_baseline"} value={selectedSetting.appearance.fill_baseline_source} onChange={(event)=>updateDraftCurveSetting(selectedCurve.curve_product_id,(current)=>({...current,appearance:{...current.appearance,fill_baseline_source:event.target.value as "governed"|"manual"}}))}><option value="governed">Governed default</option><option value="manual">Manual</option></select></label><label className="wlv-wbv-field">Baseline value<input type="number" step="any" disabled={selectedSetting.appearance.fill_mode!=="to_baseline"||selectedSetting.appearance.fill_baseline_source!=="manual"} value={selectedSetting.appearance.fill_baseline_value??""} onChange={(event)=>updateDraftCurveSetting(selectedCurve.curve_product_id,(current)=>({...current,appearance:{...current.appearance,fill_baseline_value:event.target.value===""?null:Number(event.target.value)}}))}/></label></div>
                          <label className="wlv-wbv-check-row"><input type="checkbox" disabled={selectedSetting.appearance.fill_mode==="none"} checked={selectedSetting.appearance.fill_outline} onChange={(event)=>updateDraftCurveSetting(selectedCurve.curve_product_id,(current)=>({...current,appearance:{...current.appearance,fill_outline:event.target.checked}}))}/><span>Show fill outline</span></label>
                        </fieldset>
                      </div>:<div className="wlv-wbv-empty-state">Choose a selected curve to configure its scale and appearance.</div>}
                    </section>
                  </>;
                }
                const files = displayLayerFiles?.layers[activeLayerTab] ?? [];
                return <>
                  <section className="wlv-wbv-manager-inventory-panel"><div className="wlv-wbv-manager-panel-title"><div><h3>Items</h3><span>Registered WMD products</span></div></div><label className="wlv-wbv-field">Registered item<select value={config.selected_item_ids[0] ?? ""} onChange={(event)=>updateDraftLayer(activeLayerTab,(current)=>({...current,selected_item_ids:event.target.value?[event.target.value]:[]}))}><option value="">{files.length?"Select registered file":"No registered files"}</option>{files.map((file)=><option key={file.product_id} value={file.product_id}>{file.display_name}</option>)}</select></label></section>
                  <section className="wlv-wbv-manager-selected-panel"><div className="wlv-wbv-manager-panel-title"><div><h3>Selected Items</h3><span>{config.selected_item_ids.length} selected</span></div></div><p>Selection is retained when the layer is hidden.</p></section>
                  <section className="wlv-wbv-manager-properties-panel"><div className="wlv-wbv-manager-panel-title"><div><h3>Properties</h3><span>Renderer not yet implemented</span></div></div><p>Scale and appearance controls will become available with this layer renderer.</p></section>
                </>;
              })()}
            </div>
            <footer className="wlv-wbv-layer-manager-footer"><button type="button" className="wlv-wbv-control-button" onClick={() => { if(activeLayerTab==="track_layout"){setDraftTracks(appliedTracks.map((track)=>({...track})));setDraftTrackSpacing(trackSpacing);}else{setDraftLayerConfigs((current)=>current.map((item)=>item.layer_type===activeLayerTab?defaultLayerConfig(activeLayerTab):item));} }}>Reset Tab</button><div><button type="button" className="wlv-wbv-control-button" onClick={()=>setLayerManagerOpen(false)}>Cancel</button><button type="button" className="wlv-wbv-control-button is-primary" disabled={layerManagerSaving} onClick={()=>void applyLayerManager()}>{layerManagerSaving?"Applying…":"Apply"}</button></div></footer>
          </section>
        </div>
      ) : null}
    </section>
  );
}
