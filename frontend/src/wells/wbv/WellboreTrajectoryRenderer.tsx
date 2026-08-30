import { useEffect, useMemo, useRef, useState } from 'react';
import type { WbvViewProperties } from './Wellbore3DPage';
import { createWbvScreenObservation, type WbvInteractionStateV2, type WbvScreenObservationV2 } from './interactionDomain';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import {
  TransientContinuityController,
  type TransientScreenPoint,
  type TransientTrajectoryLocation,
  type TransientTrajectoryStation,
} from './selectedPointTracking/transientContinuityController';
import { advanceTransientArcPresentation } from './selectedPointTracking/transientArcPresentation';
import { buildUniformCurveDisplayTrajectory } from './selectedPointTracking/uniformCurveDisplayTrajectory';
import { createContinuousProjectedTracker, projectPointerToWellbore, type WbvContinuousProjectedTracker, type WbvFrontendSelectedPoint } from './selection/projectPointerToWellbore';
import { createWbvTopsideRig } from './WbvTopsideRig';

export type WbvTrajectoryRenderPoint = {
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
  inclination_source?: string | null;
  azimuth_source?: string | null;
  dogleg_severity_source?: string | null;
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

type RendererStatus = 'idle' | 'empty' | 'rendered' | 'error';

export type WbvViewPreset = 'reset' | 'fit' | 'top' | 'north' | 'east' | 'south' | 'west';
export type WbvViewAction =
  | 'fit-selection'
  | 'fit-core'
  | 'fit-core-locator'
  | 'zoom-in'
  | 'zoom-out'
  | 'zoom-reset'
  | 'set-rotation-center'
  | 'reset-rotation-center'
  | 'horizontal-rotate-negative'
  | 'horizontal-rotate-positive'
  | 'vertical-rotate-negative'
  | 'vertical-rotate-positive';

export type WbvCurveOverlayRenderSample = { md: number; value: number; normalized: number };

export type WbvCurveTrack = {
  track_id: string;
  display_name: string;
  track_type: 'curve' | 'depth' | 'reference' | 'image' | 'interval';
  display_order: number;
  side: 'left' | 'right' | 'center';
  geometry_type: 'legacy_planar' | 'camera_ribbon' | 'radial_panel';
  radial_lane: number;
  angular_position_deg: number;
  orientation_mode: 'follow_trajectory' | 'camera_facing';
  thickness: number;
  width: number;
  background_mode: 'transparent' | 'black' | 'white' | 'custom';
  background_color: string;
  background_opacity: number;
  border_visible: boolean;
  border_color: string;
  grid_mode: 'off' | 'linear' | 'logarithmic';
  grid_color: string;
  wellbore_offset: number;
  previous_track_gap?: number;
};

export type WbvDepthTrack = {
  track_uid: string;
  display_name: string;
  track_type: 'depth';
  display_order: number;
  visible: boolean;
  position: 'right' | 'left' | 'center';
  angular_position_deg: number;
  distance_from_wellbore: number;
  previous_track_gap: number;
  width: number;
  opacity: number;
  background_mode: 'transparent' | 'solid';
  background_color: string;
  outline_visible: boolean;
  grid_mode: 'off' | 'linear' | 'logarithmic';
  depth_type: 'MD' | 'TVD' | 'TVDSS';
  depth_increment: number;
  label_increment: number;
  label_size: number;
  show_depth_units: boolean;
};

export type WbvCurveOverlayRenderCurve = {
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
  label_content?: 'mnemonic' | 'mnemonic_value' | 'scale' | 'mnemonic_scale';
  label_anchor?: 'top' | 'base' | 'custom_md';
  label_custom_md?: number | null;
  label_size?: number;
  label_weight?: number;
  label_alignment?: 'left' | 'center' | 'right';
  label_position?: 'on_track' | 'left' | 'right' | 'center';
  label_horizontal_adjustment?: number;
  label_vertical_adjustment?: number;
  scale_color?: string;
  scale_opacity?: number;
  scale_line_width?: number;
  scale_size?: number;
  display_min?: number | null;
  display_max?: number | null;
  scale_type?: 'linear' | 'logarithmic' | null;
  display_direction?: 'normal' | 'reversed' | null;
  fill_mode: 'none' | 'to_baseline' | 'between_curves' | 'crossover';
  fill_target_curve_product_id?: string | null;
  fill_side: 'positive' | 'negative';
  fill_color: string;
  fill_opacity: number;
  fill_outline: boolean;
  baseline_normalized: number;
  samples: WbvCurveOverlayRenderSample[];
};

export type WbvCompletionRenderItem = {
  component_id: string;
  canonical_id: string;
  canonical_component_key: string;
  label: string;
  top_md: number;
  base_md?: number | null;
  diameter?: number | null;
  geometry_class: string;
  geometry_family: string;
  material_family: string;
  annotation_policy: string;
};
export type WbvCompletionAppearance = { color?: string | null; opacity: number; sizeMultiplier?: number; showLabels?: boolean; labelMode?: "name" | "name_md" | "name_tvd" | "name_md_tvd"; labelColor?: string | null; labelSize?: number; labelOffset?: number; labelPosition?: "right" | "left" | "above" | "below"; };

export type WbvContextTrajectory = {
  managedWellId: string;
  wellName: string;
  renderPoints: WbvTrajectoryRenderPoint[];
  color?: string;
  materialMode?: 'color' | 'gray_metallic';
  metallicTone?: 'light_silver' | 'silver' | 'steel' | 'gunmetal' | 'graphite';
  thickness?: number;
  opacity?: number;
  formationTops?: WbvFormationTopRenderItem[];
  formationTopAppearance?: WbvFormationTopAppearance;
  showFormationTops?: boolean;
  lithologyIntervals?: WbvLithologyIntervalRenderItem[];
  lithologyAppearance?: WbvLithologyAppearance;
  showLithologyOverlay?: boolean;
  completionComponents?: WbvCompletionRenderItem[];
  completionAppearance?: WbvCompletionAppearance;
  showCompletions?: boolean;
  curveOverlays?: WbvCurveOverlayRenderCurve[];
  curveTracks?: WbvCurveTrack[];
  curveTrackSpacing?: number;
  showCurveOverlays?: boolean;
  layerFiles?: unknown;
  depthUnit?: string;
};

export type WbvFormationTopRenderItem = { top_id: string; name: string; marker_type: string; md: number; tvd?: number | null; group?: string | null; };
export type WbvFormationTopAppearance = { color?: string | null; opacity: number; line_width: number; show_labels: boolean; marker_style?: "ring" | "disc" | "tick" | "flag"; marker_size?: number; color_mode?: "formation" | "well" | "classification" | "single"; label_mode?: "name" | "name_md" | "name_tvd" | "name_md_tvd"; label_size?: number; label_offset?: number; label_position?: "right" | "left" | "above" | "below"; };

const WBV_FORMATION_TOP_PALETTE = [
  0x58d39b,
  0x5fa8ff,
  0xffc857,
  0xee6c8a,
  0xb98cff,
  0x56cfe1,
  0xf28482,
  0x84a59d,
] as const;

function canonicalFormationTopIdentity(name: string): string {
  return name
    .normalize("NFKC")
    .trim()
    .toLocaleLowerCase()
    .replace(/[_\-–—]+/g, " ")
    .replace(/[()[\]{}.,:;]+/g, " ")
    .replace(/\s+/g, " ")
    .replace(/\s+top$/i, "")
    .trim();
}

function canvasFormationTopColor(name: string): THREE.Color {
  const key = canonicalFormationTopIdentity(name);
  let hash = 2166136261;
  for (let index = 0; index < key.length; index += 1) {
    hash ^= key.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return new THREE.Color(WBV_FORMATION_TOP_PALETTE[(hash >>> 0) % WBV_FORMATION_TOP_PALETTE.length]);
}


export type WbvLithologyIntervalRenderItem = {
  interval_id: string;
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
export type WbvLithologyAppearance = { opacity: number; radiusMultiplier: number; brightness?: number; patternScale?: number; hideUnderlyingWellbore?: boolean; };
export type WbvCoreAppearance = { color?: string | null; brightness?: number; };

export type WbvCoreTrack = {
  track_uid: string;
  display_name: string;
  track_type: 'core';
  display_order: number;
  visible: boolean;
  position: 'right' | 'left' | 'center';
  angular_position_deg: number;
  distance_from_wellbore: number;
  previous_track_gap: number;
  width: number;
  opacity: number;
  background_mode: 'transparent' | 'solid';
  background_color: string;
  outline_visible: boolean;
  grid_mode: 'off' | 'linear' | 'logarithmic';
};

export type WbvCoreRenderChunk = {
  product_id: string;
  chunk_id: string;
  top_md: number;
  base_md: number;
  pixel_width: number;
  pixel_height: number;
  image_url: string;
};

export type WbvCoreLocatorPick = {
  product_id: string;
  md: number;
  top_md: number;
  base_md: number;
};

export type WbvTrackPlacementTrack = {
  track_uid: string;
  track_type: string;
  display_order: number;
  visible: boolean;
  position: 'right' | 'left' | 'center';
  distance_from_wellbore: number;
  previous_track_gap: number;
  width: number;
};

type WbvResolvedTrackPlacement = {
  trackUid: string;
  trackType: string;
  displayOrder: number;
  position: 'right' | 'left' | 'center';
  sideSign: -1 | 0 | 1;
  innerOffset: number;
  outerOffset: number;
  centerOffset: number;
  layoutWidth: number;
};

function resolvedTrackPlacementKey(trackType: string, displayOrder: number, position: string): string {
  return `type:${trackType}:order:${displayOrder}:position:${position}`;
}

function resolveTrackLayoutPlacements(tracks: WbvTrackPlacementTrack[], wellboreRadius: number): Map<string, WbvResolvedTrackPlacement> {
  const placements = new Map<string, WbvResolvedTrackPlacement>();
  const widthScale = wellboreRadius * 5.0;
  const visible = tracks.filter((track) => track.visible).sort((first, second) => first.display_order - second.display_order);
  (['left', 'right'] as const).forEach((position) => {
    const sideSign: -1 | 1 = position === 'left' ? -1 : 1;
    let previousOuterDistance: number | null = null;
    visible.filter((track) => track.position === position).forEach((track) => {
      const layoutWidth = widthScale * Math.max(0.25, track.width);
      const innerDistance = previousOuterDistance === null
        ? wellboreRadius * (2.75 + Math.max(0, track.distance_from_wellbore))
        : previousOuterDistance + wellboreRadius * Math.max(0, track.previous_track_gap);
      const outerDistance = innerDistance + layoutWidth;
      previousOuterDistance = outerDistance;
      const placement: WbvResolvedTrackPlacement = {
        trackUid: track.track_uid, trackType: track.track_type, displayOrder: track.display_order, position, sideSign,
        innerOffset: sideSign * innerDistance, outerOffset: sideSign * outerDistance,
        centerOffset: sideSign * ((innerDistance + outerDistance) / 2), layoutWidth,
      };
      placements.set(track.track_uid, placement);
      placements.set(resolvedTrackPlacementKey(track.track_type, track.display_order, position), placement);
    });
  });
  visible.filter((track) => track.position === 'center').forEach((track) => {
    const layoutWidth = widthScale * Math.max(0.25, track.width);
    const placement: WbvResolvedTrackPlacement = {
      trackUid: track.track_uid, trackType: track.track_type, displayOrder: track.display_order, position: 'center', sideSign: 0,
      innerOffset: -layoutWidth / 2, outerOffset: layoutWidth / 2, centerOffset: 0, layoutWidth,
    };
    placements.set(track.track_uid, placement);
    placements.set(resolvedTrackPlacementKey(track.track_type, track.display_order, 'center'), placement);
  });
  return placements;
}


export type WbvCameraViewState = {
  position: [number, number, number];
  up: [number, number, number];
  quaternion: [number, number, number, number];
  target: [number, number, number];
  zoom: number;
  view_height: number;
};

type WbvTrajectoryRendererProps = {
  renderPoints: WbvTrajectoryRenderPoint[];
  activeManagedWellId?: string | null;
  contextTrajectories?: WbvContextTrajectory[];
  onActivateWell?: (managedWellId: string) => void;
  boundingBox?: WbvBoundingBox;
  depthUnit: string;
  viewerState: string;
  viewPreset?: WbvViewPreset;
  viewCommandId?: number;
  viewAction?: WbvViewAction | null;
  viewActionId?: number;
  horizontalRotationLocked?: boolean;
  verticalRotationLocked?: boolean;
  onZoomPercentChange?: (zoomPercent: number) => void;
  onCameraViewChange?: (view: WbvCameraViewState) => void;
  cameraViewRestore?: WbvCameraViewState | null;
  cameraViewRestoreId?: number;
  onInteractionCommand?: (command: {
    kind: "observe" | "track-start" | "track-update" | "track-commit" | "track-cancel";
    observation?: WbvScreenObservationV2;
    sessionId?: string;
    sequence: number;
    exactLocalPoint?: WbvTrajectoryRenderPoint;
  }) => Promise<WbvInteractionStateV2 | null>;
  onLocalSelectedPoint?: (point: WbvTrajectoryRenderPoint) => void;
  rotationCenterPickArmed?: boolean;
  onRotationCenterEstablished?: (point: WbvTrajectoryRenderPoint) => void;
  selectedPoint?: WbvTrajectoryRenderPoint | null;
  selectionMode?: "none" | "point" | "interval";
  intervalDraftStart?: WbvTrajectoryRenderPoint | null;
  savedInterval?: { start: WbvTrajectoryRenderPoint; end: WbvTrajectoryRenderPoint; top_md: number; base_md: number } | null;
  trackValuesAlongWellbore?: boolean;
  showTrajectory?: boolean;
  showBoundingBox?: boolean;
  showDepthLabels?: boolean;
  showSurveyStations?: boolean;
  showGroundPlane?: boolean;
  showBottomGrid?: boolean;
  showTopGrid?: boolean;
  surfaceDatumLabel?: string | null;
  showAxes?: boolean;
  showNorthArrow?: boolean;
  useSurfaceLighting?: boolean;
  curveOverlays?: WbvCurveOverlayRenderCurve[];
  curveTracks?: WbvCurveTrack[];
  depthTracks?: WbvDepthTrack[];
  curveTrackSpacing?: number;
  showCurveOverlays?: boolean;
  formationTops?: WbvFormationTopRenderItem[];
  formationTopAppearance?: WbvFormationTopAppearance;
  showFormationTops?: boolean;
  lithologyIntervals?: WbvLithologyIntervalRenderItem[];
  lithologyAppearance?: WbvLithologyAppearance;
  showLithologyOverlay?: boolean;
  completionComponents?: WbvCompletionRenderItem[];
  completionAppearance?: WbvCompletionAppearance;
  showCompletions?: boolean;
  coreChunks?: WbvCoreRenderChunk[];
  coreTracks?: WbvCoreTrack[];
  coreAppearance?: WbvCoreAppearance;
  showCoreOverlay?: boolean;
  coreInspectionInterval?: { top_md: number; base_md: number } | null;
  coreLocatorFocusInterval?: { top_md: number; base_md: number } | null;
  coreViewMode?: boolean;
  onCoreLocatorPick?: (pick: WbvCoreLocatorPick) => void;
  trackLayoutTracks?: WbvTrackPlacementTrack[];
  viewProperties?: WbvViewProperties;
};

type ScenePoint = {
  x: number;
  y: number;
  z: number;
  md?: number | null;
  tvd?: number | null;
};

type SceneBox = {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
  minZ: number;
  maxZ: number;
};

type CameraPlan = {
  position: THREE.Vector3;
  up: THREE.Vector3;
  target: THREE.Vector3;
  viewHeight: number;
};

type CameraViewSnapshot = {
  position: THREE.Vector3;
  up: THREE.Vector3;
  quaternion: THREE.Quaternion;
  target: THREE.Vector3;
  zoom: number;
  viewHeight: number;
};



type OverviewPoint = { x: number; y: number; sourceIndex: number };
type OverviewRange = { startIndex: number; endIndex: number };
type OverviewRuntime = {
  panToSourceIndex: (sourceIndex: number) => void;
};

const OVERVIEW_WIDTH = 160;
const OVERVIEW_HEIGHT = 220;
const OVERVIEW_PADDING = 14;
const OVERVIEW_ENVELOPE_HALF_WIDTH = 7;
const OVERVIEW_MAX_POINTS = 700;

function sampledIndices(length: number, maximum = OVERVIEW_MAX_POINTS): number[] {
  if (length <= 0) return [];
  if (length <= maximum) return Array.from({ length }, (_, index) => index);
  const result: number[] = [];
  const step = (length - 1) / (maximum - 1);
  for (let index = 0; index < maximum; index += 1) {
    result.push(Math.min(length - 1, Math.round(index * step)));
  }
  return result;
}

export function buildOverviewProjection(points: THREE.Vector3[]): OverviewPoint[] {
  const indices = sampledIndices(points.length);
  if (indices.length === 0) return [];

  let meanX = 0;
  let meanZ = 0;
  for (const index of indices) {
    meanX += finiteNumber(points[index]?.x, 0);
    meanZ += finiteNumber(points[index]?.z, 0);
  }
  meanX /= indices.length;
  meanZ /= indices.length;

  let xx = 0;
  let xz = 0;
  let zz = 0;
  for (const index of indices) {
    const point = points[index];
    const dx = finiteNumber(point?.x, 0) - meanX;
    const dz = finiteNumber(point?.z, 0) - meanZ;
    xx += dx * dx;
    xz += dx * dz;
    zz += dz * dz;
  }

  const angle = 0.5 * Math.atan2(2 * xz, xx - zz);
  const axisX = Math.cos(angle);
  const axisZ = Math.sin(angle);
  const raw = indices.map((sourceIndex) => {
    const point = points[sourceIndex];
    return {
      x: (finiteNumber(point?.x, 0) - meanX) * axisX + (finiteNumber(point?.z, 0) - meanZ) * axisZ,
      y: finiteNumber(point?.y, 0),
      sourceIndex,
    };
  });

  let minX = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;
  for (const point of raw) {
    minX = Math.min(minX, point.x);
    maxX = Math.max(maxX, point.x);
    minY = Math.min(minY, point.y);
    maxY = Math.max(maxY, point.y);
  }

  const spanX = Math.max(0.001, maxX - minX);
  const spanY = Math.max(0.001, maxY - minY);
  const availableWidth = OVERVIEW_WIDTH - OVERVIEW_PADDING * 2;
  const availableHeight = OVERVIEW_HEIGHT - OVERVIEW_PADDING * 2;
  const scale = Math.min(availableWidth / spanX, availableHeight / spanY);
  const offsetX = (OVERVIEW_WIDTH - spanX * scale) / 2;
  const offsetY = (OVERVIEW_HEIGHT - spanY * scale) / 2;

  return raw.map((point) => ({
    x: offsetX + (point.x - minX) * scale,
    y: OVERVIEW_HEIGHT - (offsetY + (point.y - minY) * scale),
    sourceIndex: point.sourceIndex,
  }));
}

function overviewPath(points: OverviewPoint[]): string {
  let path = '';
  for (let index = 0; index < points.length; index += 1) {
    const point = points[index];
    path += `${index === 0 ? 'M' : ' L'} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`;
  }
  return path;
}

function overviewEnvelope(points: OverviewPoint[], halfWidth = OVERVIEW_ENVELOPE_HALF_WIDTH): string {
  if (points.length < 2) return '';
  const left: OverviewPoint[] = [];
  const right: OverviewPoint[] = [];
  for (let index = 0; index < points.length; index += 1) {
    const point = points[index];
    const previous = points[Math.max(0, index - 1)];
    const next = points[Math.min(points.length - 1, index + 1)];
    const dx = next.x - previous.x;
    const dy = next.y - previous.y;
    const length = Math.max(0.001, Math.hypot(dx, dy));
    const nx = -dy / length;
    const ny = dx / length;
    left.push({ x: point.x + nx * halfWidth, y: point.y + ny * halfWidth, sourceIndex: point.sourceIndex });
    right.push({ x: point.x - nx * halfWidth, y: point.y - ny * halfWidth, sourceIndex: point.sourceIndex });
  }
  return `${overviewPath([...left, ...right.reverse()])} Z`;
}

function visibleTrajectoryRange(camera: THREE.Camera, points: THREE.Vector3[]): OverviewRange {
  const indices = sampledIndices(points.length);
  if (indices.length < 2) return { startIndex: 0, endIndex: Math.max(0, points.length - 1) };
  let firstVisible = -1;
  let lastVisible = -1;
  let nearestIndex = indices[0];
  let nearestDistance = Number.POSITIVE_INFINITY;
  for (const sourceIndex of indices) {
    const projected = points[sourceIndex].clone().project(camera);
    const distance = Math.hypot(projected.x, projected.y);
    if (distance < nearestDistance) {
      nearestDistance = distance;
      nearestIndex = sourceIndex;
    }
    if (projected.x >= -1 && projected.x <= 1 && projected.y >= -1 && projected.y <= 1 && projected.z >= -1 && projected.z <= 1) {
      if (firstVisible < 0) firstVisible = sourceIndex;
      lastVisible = sourceIndex;
    }
  }
  if (firstVisible >= 0) {
    const margin = Math.max(1, Math.ceil(points.length / OVERVIEW_MAX_POINTS));
    return {
      startIndex: Math.max(0, firstVisible - margin),
      endIndex: Math.min(points.length - 1, lastVisible + margin),
    };
  }
  const halfWindow = Math.max(1, Math.round(points.length * 0.04));
  return {
    startIndex: Math.max(0, nearestIndex - halfWindow),
    endIndex: Math.min(points.length - 1, nearestIndex + halfWindow),
  };
}

function nearestOverviewSourceIndex(points: OverviewPoint[], x: number, y: number): number {
  let nearestSourceIndex = points[0]?.sourceIndex ?? 0;
  let nearestDistance = Number.POSITIVE_INFINITY;
  for (const point of points) {
    const distance = Math.hypot(point.x - x, point.y - y);
    if (distance < nearestDistance) {
      nearestDistance = distance;
      nearestSourceIndex = point.sourceIndex;
    }
  }
  return nearestSourceIndex;
}

const TARGET_WELL_HEIGHT = 5.35;
const MIN_DISPLAY_LATERAL_HALF_SPAN = 0.92;
const MAX_DISPLAY_LATERAL_HALF_SPAN = 1.35;

function finiteNumber(value: number | null | undefined, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

function firstFinite(...values: Array<number | null | undefined>): number | null {
  for (const value of values) {
    if (typeof value === 'number' && Number.isFinite(value)) return value;
  }
  return null;
}

function scenePointsFromBackend(points: WbvTrajectoryRenderPoint[]): ScenePoint[] {
  return points.map((point) => {
    const east = finiteNumber(point.x ?? point.east_departure, 0);
    const north = finiteNumber(point.y ?? point.north_departure, 0);
    const depth = firstFinite(
      point.tvd,
      point.md,
      point.z !== undefined && point.z !== null ? Math.abs(point.z) : null,
    ) ?? 0;

    return {
      x: east,
      y: -depth,
      z: north,
      md: point.md,
      tvd: point.tvd,
    };
  });
}

function sceneBoxCenter(box: SceneBox): THREE.Vector3 {
  return new THREE.Vector3(
    (box.minX + box.maxX) / 2,
    (box.minY + box.maxY) / 2,
    (box.minZ + box.maxZ) / 2,
  );
}

function sceneBoxSpan(box: SceneBox): { x: number; y: number; z: number; max: number } {
  const x = Math.abs(box.maxX - box.minX);
  const y = Math.abs(box.maxY - box.minY);
  const z = Math.abs(box.maxZ - box.minZ);
  return { x, y, z, max: Math.max(x, y, z) };
}

function createNormalizedPoints(points: ScenePoint[]): THREE.Vector3[] {
  const minX = Math.min(...points.map((point) => point.x));
  const maxX = Math.max(...points.map((point) => point.x));
  const minY = Math.min(...points.map((point) => point.y));
  const maxY = Math.max(...points.map((point) => point.y));
  const minZ = Math.min(...points.map((point) => point.z));
  const maxZ = Math.max(...points.map((point) => point.z));

  const centerX = (minX + maxX) / 2;
  const centerY = (minY + maxY) / 2;
  const centerZ = (minZ + maxZ) / 2;
  const verticalSpan = Math.max(1, Math.abs(maxY - minY));
  const scale = TARGET_WELL_HEIGHT / verticalSpan;

  return points.map((point) => new THREE.Vector3(
    (point.x - centerX) * scale,
    (point.y - centerY) * scale,
    (point.z - centerZ) * scale,
  ));
}

function sceneBoxFor(points: THREE.Vector3[]): SceneBox {
  const minX = Math.min(...points.map((point) => point.x));
  const maxX = Math.max(...points.map((point) => point.x));
  const minY = Math.min(...points.map((point) => point.y));
  const maxY = Math.max(...points.map((point) => point.y));
  const minZ = Math.min(...points.map((point) => point.z));
  const maxZ = Math.max(...points.map((point) => point.z));

  const xSpan = Math.abs(maxX - minX);
  const ySpan = Math.abs(maxY - minY);
  const zSpan = Math.abs(maxZ - minZ);
  const verticalPad = Math.max(0.38, ySpan * 0.075);
  const lateralHalfSpan = Math.max(
    MIN_DISPLAY_LATERAL_HALF_SPAN,
    Math.min(MAX_DISPLAY_LATERAL_HALF_SPAN, ySpan * 0.22),
  );

  return {
    minX: xSpan < 0.05 ? -lateralHalfSpan : minX - lateralHalfSpan * 0.24,
    maxX: xSpan < 0.05 ? lateralHalfSpan : maxX + lateralHalfSpan * 0.24,
    minY: minY - verticalPad,
    maxY: maxY + verticalPad,
    minZ: zSpan < 0.05 ? -lateralHalfSpan : minZ - lateralHalfSpan * 0.24,
    maxZ: zSpan < 0.05 ? lateralHalfSpan : maxZ + lateralHalfSpan * 0.24,
  };
}

function createTrajectoryBoundingBox(box: SceneBox): THREE.LineSegments {
  const width = Math.max(0.001, box.maxX - box.minX);
  const height = Math.max(0.001, box.maxY - box.minY);
  const depth = Math.max(0.001, box.maxZ - box.minZ);
  const geometry = new THREE.EdgesGeometry(new THREE.BoxGeometry(width, height, depth));
  const material = new THREE.LineBasicMaterial({
    color: 0x45606f,
    transparent: true,
    opacity: 0.46,
  });
  const boundingBox = new THREE.LineSegments(geometry, material);
  boundingBox.position.set(
    (box.minX + box.maxX) / 2,
    (box.minY + box.maxY) / 2,
    (box.minZ + box.maxZ) / 2,
  );
  return boundingBox;
}

function createTextSprite(
  text: string,
  options?: {
    color?: string;
    background?: string;
    scale?: number;
    fontWeight?: number;
    shadowBlur?: number;
    shadowColor?: string;
  },
): THREE.Sprite {
  const canvas = document.createElement('canvas');
  canvas.width = 640;
  canvas.height = 160;
  const context = canvas.getContext('2d');

  if (context) {
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.font = `${options?.fontWeight ?? 800} 32px Inter, Arial, sans-serif`;
    context.textBaseline = 'middle';
    context.textAlign = 'center';

    if (options?.background) {
      context.fillStyle = options.background;
      const x = 34;
      const y = 44;
      const width = 572;
      const height = 72;
      const radius = 18;
      context.beginPath();
      context.moveTo(x + radius, y);
      context.lineTo(x + width - radius, y);
      context.quadraticCurveTo(x + width, y, x + width, y + radius);
      context.lineTo(x + width, y + height - radius);
      context.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
      context.lineTo(x + radius, y + height);
      context.quadraticCurveTo(x, y + height, x, y + height - radius);
      context.lineTo(x, y + radius);
      context.quadraticCurveTo(x, y, x + radius, y);
      context.closePath();
      context.fill();
    }

    context.shadowColor = options?.shadowColor ?? 'rgba(111, 211, 255, 0.48)';
    context.shadowBlur = options?.shadowBlur ?? 8;
    context.fillStyle = options?.color ?? '#b9f3ff';
    context.fillText(text, canvas.width / 2, canvas.height / 2);
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.needsUpdate = true;

  const material = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    depthTest: false,
    depthWrite: false,
  });

  const sprite = new THREE.Sprite(material);
  const scale = options?.scale ?? 0.27;
  sprite.scale.set(scale * 4.0, scale, 1);
  sprite.userData.baseTextScale = new THREE.Vector3(scale * 4.0, scale, 1);
  return sprite;
}

function formatDepth(value: number | null | undefined, unit: string): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return `— ${unit}`;
  return `${Math.round(value).toLocaleString()} ${unit}`;
}

type RepresentativeDepthTick = {
  label: string;
  md: number | null;
  pointIndex: number;
};

function representativeTicks(points: WbvTrajectoryRenderPoint[], depthUnit: string): RepresentativeDepthTick[] {
  if (points.length === 0) return [];

  const indices = Array.from(new Set([
    0,
    Math.floor((points.length - 1) * 0.25),
    Math.floor((points.length - 1) * 0.5),
    Math.floor((points.length - 1) * 0.75),
    points.length - 1,
  ])).filter((index) => index >= 0 && index < points.length);

  return indices.map((index) => {
    const md = firstFinite(points[index].md, points[index].tvd);
    return {
      label: formatDepth(md, depthUnit),
      md,
      pointIndex: index,
    };
  });
}

function sceneYForMeasuredDepth(
  points: WbvTrajectoryRenderPoint[],
  scenePositions: THREE.Vector3[],
  targetMd: number | null,
  fallbackPointIndex: number,
): number {
  const fallback = scenePositions[Math.max(0, Math.min(scenePositions.length - 1, fallbackPointIndex))]?.y ?? 0;
  if (targetMd === null || !Number.isFinite(targetMd) || points.length !== scenePositions.length) return fallback;

  for (let index = 0; index < points.length - 1; index += 1) {
    const firstMd = points[index].md;
    const secondMd = points[index + 1].md;
    if (
      typeof firstMd !== 'number' || !Number.isFinite(firstMd)
      || typeof secondMd !== 'number' || !Number.isFinite(secondMd)
    ) {
      continue;
    }

    const minMd = Math.min(firstMd, secondMd);
    const maxMd = Math.max(firstMd, secondMd);
    if (targetMd < minMd || targetMd > maxMd) continue;

    const denominator = secondMd - firstMd;
    const ratio = denominator === 0 ? 0 : Math.max(0, Math.min(1, (targetMd - firstMd) / denominator));
    return scenePositions[index].y + (scenePositions[index + 1].y - scenePositions[index].y) * ratio;
  }

  let nearestIndex = fallbackPointIndex;
  let nearestDistance = Number.POSITIVE_INFINITY;
  points.forEach((point, index) => {
    const md = point.md;
    if (typeof md !== 'number' || !Number.isFinite(md)) return;
    const distance = Math.abs(md - targetMd);
    if (distance < nearestDistance) {
      nearestDistance = distance;
      nearestIndex = index;
    }
  });

  return scenePositions[Math.max(0, Math.min(scenePositions.length - 1, nearestIndex))]?.y ?? fallback;
}

function trajectoryTangents(points: THREE.Vector3[]): THREE.Vector3[] {
  return points.map((_, index) => {
    const previous = points[Math.max(0, index - 1)];
    const next = points[Math.min(points.length - 1, index + 1)];
    return next.clone().sub(previous).normalize();
  });
}

type TrajectoryBasis = {
  position: THREE.Vector3;
  tangent: THREE.Vector3;
  framePosition: number;
};

function interpolateTrajectoryScalarAtMd(
  renderPoints: WbvTrajectoryRenderPoint[],
  md: number,
  selector: (point: WbvTrajectoryRenderPoint) => number | null | undefined,
): number | null {
  for (let index = 0; index < renderPoints.length - 1; index += 1) {
    const firstMd = renderPoints[index].md;
    const secondMd = renderPoints[index + 1].md;
    if (typeof firstMd !== 'number' || typeof secondMd !== 'number' || !Number.isFinite(firstMd) || !Number.isFinite(secondMd)) continue;
    const minimum = Math.min(firstMd, secondMd);
    const maximum = Math.max(firstMd, secondMd);
    if (md < minimum || md > maximum) continue;
    const firstValue = selector(renderPoints[index]);
    const secondValue = selector(renderPoints[index + 1]);
    if (typeof firstValue !== 'number' || !Number.isFinite(firstValue)) return null;
    if (typeof secondValue !== 'number' || !Number.isFinite(secondValue)) return firstValue;
    const ratio = secondMd === firstMd ? 0 : THREE.MathUtils.clamp((md - firstMd) / (secondMd - firstMd), 0, 1);
    return THREE.MathUtils.lerp(firstValue, secondValue, ratio);
  }
  return null;
}

function interpolateTrajectoryBasisAtMd(
  renderPoints: WbvTrajectoryRenderPoint[],
  positions: THREE.Vector3[],
  tangents: THREE.Vector3[],
  md: number,
): TrajectoryBasis | null {
  for (let index = 0; index < renderPoints.length - 1; index += 1) {
    const firstMd = renderPoints[index].md;
    const secondMd = renderPoints[index + 1].md;
    if (typeof firstMd !== 'number' || typeof secondMd !== 'number' || !Number.isFinite(firstMd) || !Number.isFinite(secondMd)) continue;
    const minimum = Math.min(firstMd, secondMd);
    const maximum = Math.max(firstMd, secondMd);
    if (md < minimum || md > maximum) continue;
    const ratio = secondMd === firstMd ? 0 : THREE.MathUtils.clamp((md - firstMd) / (secondMd - firstMd), 0, 1);
    return {
      position: positions[index].clone().lerp(positions[index + 1], ratio),
      tangent: tangents[index].clone().lerp(tangents[index + 1], ratio).normalize(),
      framePosition: index + ratio,
    };
  }
  return null;
}

type PreparedOverlayPoint = {
  md: number;
  value: number;
  normalized: number;
  basis: TrajectoryBasis;
  baselineOffset: number;
  traceOffset: number;
};

function preparedOverlaySegments(
  curve: WbvCurveOverlayRenderCurve,
  renderPoints: WbvTrajectoryRenderPoint[],
  positions: THREE.Vector3[],
  tangents: THREE.Vector3[],
  baselineOffset: number,
  excursion: number,
): PreparedOverlayPoint[][] {
  const byMd = new Map<number, WbvCurveOverlayRenderSample>();
  curve.samples.forEach((sample) => {
    if (!Number.isFinite(sample.md) || !Number.isFinite(sample.normalized)) return;
    byMd.set(sample.md, sample);
  });
  const ordered = [...byMd.values()].sort((first, second) => first.md - second.md);
  if (ordered.length < 2) return [];

  const positiveGaps = ordered
    .slice(1)
    .map((sample, index) => sample.md - ordered[index].md)
    .filter((gap) => Number.isFinite(gap) && gap > 0)
    .sort((first, second) => first - second);
  const medianGap = positiveGaps.length > 0
    ? positiveGaps[Math.floor(positiveGaps.length / 2)]
    : Number.POSITIVE_INFINITY;
  const trajectoryMds = renderPoints
    .map((point) => point.md)
    .filter((md): md is number => typeof md === 'number' && Number.isFinite(md));
  const trajectorySpan = trajectoryMds.length > 1 ? Math.max(...trajectoryMds) - Math.min(...trajectoryMds) : 0;
  const gapThreshold = Number.isFinite(medianGap)
    ? Math.max(medianGap * 8, trajectorySpan * 0.0025)
    : Number.POSITIVE_INFINITY;

  const segments: PreparedOverlayPoint[][] = [];
  let current: PreparedOverlayPoint[] = [];
  let previousMd: number | null = null;

  ordered.forEach((sample) => {
    if (previousMd !== null && sample.md - previousMd > gapThreshold && current.length > 0) {
      if (current.length >= 2) segments.push(current);
      current = [];
    }
    previousMd = sample.md;
    const basis = interpolateTrajectoryBasisAtMd(renderPoints, positions, tangents, sample.md);
    if (!basis) {
      if (current.length >= 2) segments.push(current);
      current = [];
      return;
    }
    const displacement = (sample.normalized - curve.baseline_normalized) * excursion;
    current.push({
      md: sample.md,
      value: sample.value,
      normalized: sample.normalized,
      basis,
      baselineOffset,
      traceOffset: baselineOffset + displacement,
    });
  });
  if (current.length >= 2) segments.push(current);
  return segments;
}

function interpolatePreparedPoint(segment: PreparedOverlayPoint[], md: number): PreparedOverlayPoint | null {
  for (let index = 0; index < segment.length - 1; index += 1) {
    const first = segment[index];
    const second = segment[index + 1];
    if (md < first.md || md > second.md) continue;
    const ratio = second.md === first.md ? 0 : THREE.MathUtils.clamp((md - first.md) / (second.md - first.md), 0, 1);
    return {
      md,
      value: THREE.MathUtils.lerp(first.value, second.value, ratio),
      normalized: THREE.MathUtils.lerp(first.normalized, second.normalized, ratio),
      basis: {
        position: first.basis.position.clone().lerp(second.basis.position, ratio),
        tangent: first.basis.tangent.clone().lerp(second.basis.tangent, ratio).normalize(),
        framePosition: THREE.MathUtils.lerp(first.basis.framePosition, second.basis.framePosition, ratio),
      },
      baselineOffset: THREE.MathUtils.lerp(first.baselineOffset, second.baselineOffset, ratio),
      traceOffset: THREE.MathUtils.lerp(first.traceOffset, second.traceOffset, ratio),
    };
  }
  const exact = segment.find((point) => point.md === md);
  return exact ? {
    ...exact,
    basis: {
      position: exact.basis.position.clone(),
      tangent: exact.basis.tangent.clone(),
      framePosition: exact.basis.framePosition,
    },
  } : null;
}

function pairedOverlaySegments(
  firstSegments: PreparedOverlayPoint[][],
  secondSegments: PreparedOverlayPoint[][],
): Array<Array<{ first: PreparedOverlayPoint; second: PreparedOverlayPoint }>> {
  const paired: Array<Array<{ first: PreparedOverlayPoint; second: PreparedOverlayPoint }>> = [];
  firstSegments.forEach((firstSegment) => {
    secondSegments.forEach((secondSegment) => {
      const start = Math.max(firstSegment[0].md, secondSegment[0].md);
      const end = Math.min(firstSegment[firstSegment.length - 1].md, secondSegment[secondSegment.length - 1].md);
      if (!(end > start)) return;
      const mds = [...new Set([
        start,
        end,
        ...firstSegment.map((point) => point.md).filter((md) => md > start && md < end),
        ...secondSegment.map((point) => point.md).filter((md) => md > start && md < end),
      ])].sort((a, b) => a - b);
      const current: Array<{ first: PreparedOverlayPoint; second: PreparedOverlayPoint }> = [];
      mds.forEach((md) => {
        const first = interpolatePreparedPoint(firstSegment, md);
        const second = interpolatePreparedPoint(secondSegment, md);
        if (!first || !second) return;
        const prior = current[current.length - 1];
        if (prior) {
          const priorDelta = prior.first.normalized - prior.second.normalized;
          const delta = first.normalized - second.normalized;
          if (priorDelta !== 0 && delta !== 0 && Math.sign(priorDelta) !== Math.sign(delta)) {
            const ratio = Math.abs(priorDelta) / (Math.abs(priorDelta) + Math.abs(delta));
            const crossingMd = THREE.MathUtils.lerp(prior.first.md, first.md, ratio);
            const firstCross = interpolatePreparedPoint(firstSegment, crossingMd);
            const secondCross = interpolatePreparedPoint(secondSegment, crossingMd);
            if (firstCross && secondCross) current.push({ first: firstCross, second: secondCross });
          }
        }
        current.push({ first, second });
      });
      if (current.length >= 2) paired.push(current);
    });
  });
  return paired;
}

type ViewRelativeVertex = {
  position: THREE.Vector3;
  tangent: THREE.Vector3;
  framePosition: number;
  offset: number;
};

type ViewRelativeGeometryBinding = {
  attribute: THREE.BufferAttribute;
  vertices: ViewRelativeVertex[];
  trackId: string;
};

type CurveLabelBinding = {
  sprite: THREE.Sprite;
  trackId: string;
  vertex: ViewRelativeVertex;
  horizontalWorldOffset: number;
  verticalWorldOffset: number;
};

type CurveScaleSpriteBinding = {
  sprite: THREE.Sprite;
  trackId: string;
  anchorPosition: THREE.Vector3;
  framePosition: number;
  baselineOffset: number;
  signedExcursion: number;
  horizontalWorldOffset: number;
  verticalWorldOffset: number;
};

type CurveOverlayRuntime = {
  update(camera: THREE.Camera): void;
};

function sharedViewAxes(
  tangents: THREE.Vector3[],
  cameraRight: THREE.Vector3,
): THREE.Vector3[] {
  const viewRight = cameraRight.clone().normalize();
  return tangents.map(() => viewRight.clone());
}

function trajectoryRadialAxes(
  tangents: THREE.Vector3[],
  angleDeg: number,
): THREE.Vector3[] {
  const angle = THREE.MathUtils.degToRad(angleDeg);
  let previous: THREE.Vector3 | null = null;
  return tangents.map((tangent) => {
    const t = tangent.clone().normalize();
    const reference = Math.abs(t.dot(new THREE.Vector3(0, 1, 0))) > 0.92
      ? new THREE.Vector3(1, 0, 0)
      : new THREE.Vector3(0, 1, 0);
    let axis = new THREE.Vector3().crossVectors(reference, t).normalize();
    if (previous && previous.dot(axis) < 0) axis.negate();
    axis.applyAxisAngle(t, angle).normalize();
    previous = axis.clone();
    return axis;
  });
}

function axesForTrack(
  track: WbvCurveTrack | undefined,
  tangents: THREE.Vector3[],
  cameraRight: THREE.Vector3,
): THREE.Vector3[] {
  if (!track || track.geometry_type === 'legacy_planar') return sharedViewAxes(tangents, cameraRight);
  if (track.geometry_type === 'camera_ribbon' || track.orientation_mode === 'camera_facing') {
    return sharedViewAxes(tangents, cameraRight);
  }
  return trajectoryRadialAxes(tangents, track.angular_position_deg);
}

function axisAtFramePosition(axes: THREE.Vector3[], framePosition: number): THREE.Vector3 {
  if (axes.length === 0) return new THREE.Vector3(1, 0, 0);
  const clamped = THREE.MathUtils.clamp(framePosition, 0, axes.length - 1);
  const firstIndex = Math.floor(clamped);
  const secondIndex = Math.min(axes.length - 1, firstIndex + 1);
  const ratio = clamped - firstIndex;
  const first = axes[firstIndex];
  const second = axes[secondIndex];
  const alignedSecond = first.dot(second) < 0 ? second.clone().negate() : second;
  return first.clone().lerp(alignedSecond, ratio).normalize();
}

function updateViewRelativeBinding(
  binding: ViewRelativeGeometryBinding,
  axes: THREE.Vector3[],
): void {
  binding.vertices.forEach((vertex, index) => {
    const axis = axisAtFramePosition(axes, vertex.framePosition);
    const point = vertex.position.clone().add(axis.multiplyScalar(vertex.offset));
    binding.attribute.setXYZ(index, point.x, point.y, point.z);
  });
  binding.attribute.needsUpdate = true;
}

function dynamicGeometry(vertices: ViewRelativeVertex[], indices: number[] | undefined, trackId: string): {
  geometry: THREE.BufferGeometry;
  binding: ViewRelativeGeometryBinding;
} {
  const attribute = new THREE.Float32BufferAttribute(new Float32Array(vertices.length * 3), 3);
  attribute.setUsage(THREE.DynamicDrawUsage);
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', attribute);
  if (indices) geometry.setIndex(indices);
  return { geometry, binding: { attribute, vertices, trackId } };
}

function viewVerticesFromPoints(points: PreparedOverlayPoint[], offset: 'traceOffset' | 'baselineOffset'): ViewRelativeVertex[] {
  return points.map((point) => ({
    position: point.basis.position,
    tangent: point.basis.tangent,
    framePosition: point.basis.framePosition,
    offset: point[offset],
  }));
}


type DepthTrackRuntime = {
  update(camera: THREE.Camera): void;
};

type DepthSpriteBinding = {
  sprite: THREE.Sprite;
  trackId: string;
  position: THREE.Vector3;
  framePosition: number;
  offset: number;
};

function governedDepthValue(
  point: WbvTrajectoryRenderPoint,
  depthType: WbvDepthTrack['depth_type'],
): number | null {
  if (depthType === 'MD') {
    return typeof point.md === 'number' && Number.isFinite(point.md) ? point.md : null;
  }
  if (depthType === 'TVD') {
    return typeof point.tvd === 'number' && Number.isFinite(point.tvd) ? point.tvd : null;
  }
  if (typeof point.tvdss === 'number' && Number.isFinite(point.tvdss)) return point.tvdss;
  // Agreed provisional contract: without a resolved surface datum, TVDSS is equivalent to TVD.
  return typeof point.tvd === 'number' && Number.isFinite(point.tvd) ? point.tvd : null;
}

function measuredDepthAtGovernedDepth(
  renderPoints: WbvTrajectoryRenderPoint[],
  depthType: WbvDepthTrack['depth_type'],
  targetDepth: number,
): number | null {
  for (let index = 0; index < renderPoints.length - 1; index += 1) {
    const first = renderPoints[index];
    const second = renderPoints[index + 1];
    const firstDepth = governedDepthValue(first, depthType);
    const secondDepth = governedDepthValue(second, depthType);
    const firstMd = first.md;
    const secondMd = second.md;
    if (
      firstDepth === null ||
      secondDepth === null ||
      typeof firstMd !== 'number' ||
      typeof secondMd !== 'number' ||
      !Number.isFinite(firstMd) ||
      !Number.isFinite(secondMd)
    ) continue;
    const minimum = Math.min(firstDepth, secondDepth);
    const maximum = Math.max(firstDepth, secondDepth);
    if (targetDepth < minimum || targetDepth > maximum) continue;
    const span = secondDepth - firstDepth;
    const ratio = Math.abs(span) < 1e-12
      ? 0
      : THREE.MathUtils.clamp((targetDepth - firstDepth) / span, 0, 1);
    return THREE.MathUtils.lerp(firstMd, secondMd, ratio);
  }
  return null;
}

function depthTrackPositions(
  renderPoints: WbvTrajectoryRenderPoint[],
  track: WbvDepthTrack,
  increment: number,
): Array<{ depth: number; md: number }> {
  const values = renderPoints
    .map((point) => governedDepthValue(point, track.depth_type))
    .filter((value): value is number => value !== null && Number.isFinite(value));
  if (values.length < 2) return [];

  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const governedIncrement = Math.max(Number.EPSILON, increment);
  const firstValue = Math.ceil(minimum / governedIncrement) * governedIncrement;
  const positions: Array<{ depth: number; md: number }> = [];

  for (
    let depth = firstValue, count = 0;
    depth <= maximum + governedIncrement * 1e-6 && count < 5000;
    depth += governedIncrement, count += 1
  ) {
    const md = measuredDepthAtGovernedDepth(renderPoints, track.depth_type, depth);
    if (md !== null) positions.push({ depth, md });
  }

  return positions;
}

function depthTrackAsCurveTrack(track: WbvDepthTrack): WbvCurveTrack {
  return {
    track_id: track.track_uid,
    display_name: track.display_name,
    track_type: 'depth',
    display_order: track.display_order,
    side: track.position,
    geometry_type: 'camera_ribbon',
    radial_lane: track.display_order,
    angular_position_deg: track.angular_position_deg,
    orientation_mode: 'camera_facing',
    thickness: 0.05,
    width: track.width,
    background_mode: track.background_mode === 'solid' ? 'custom' : 'transparent',
    background_color: track.background_color,
    background_opacity: track.background_mode === 'solid' ? track.opacity : 0,
    border_visible: track.outline_visible,
    border_color: '#8799a3',
    grid_mode: 'off',
    grid_color: '#8799a3',
    wellbore_offset: track.distance_from_wellbore,
    previous_track_gap: track.previous_track_gap,
  };
}

function addDepthTracks(
  group: THREE.Group,
  tracks: WbvDepthTrack[],
  renderPoints: WbvTrajectoryRenderPoint[],
  positions: THREE.Vector3[],
  depthUnit: string,
  viewProperties?: WbvViewProperties,
  trackPlacements?: Map<string, WbvResolvedTrackPlacement>,
): DepthTrackRuntime {
  const bindings: ViewRelativeGeometryBinding[] = [];
  const spriteBindings: DepthSpriteBinding[] = [];
  const tangents = trajectoryTangents(positions);
  const trackById = new Map<string, WbvCurveTrack>();

  const update = (camera: THREE.Camera) => {
    const cameraRight = new THREE.Vector3(1, 0, 0).applyQuaternion(camera.quaternion).normalize();
    const axesCache = new Map<string, THREE.Vector3[]>();
    const axesForTrackId = (trackId: string) => {
      let axes = axesCache.get(trackId);
      if (!axes) {
        axes = axesForTrack(trackById.get(trackId), tangents, cameraRight);
        axesCache.set(trackId, axes);
      }
      return axes;
    };

    bindings.forEach((binding) => {
      updateViewRelativeBinding(binding, axesForTrackId(binding.trackId));
    });

    spriteBindings.forEach((binding) => {
      const axis = axisAtFramePosition(axesForTrackId(binding.trackId), binding.framePosition);
      binding.sprite.position.copy(binding.position).add(axis.multiplyScalar(binding.offset));
    });
  };

  if (tracks.length === 0 || positions.length < 2) return { update };

  const wellboreRadius = 0.008;
  const widthScale = wellboreRadius * 5.0;
  const sortedTracks = tracks
    .filter((track) => track.visible && track.track_type === 'depth')
    .sort((first, second) => first.display_order - second.display_order);

  sortedTracks.forEach((track) => {
    const renderTrack = depthTrackAsCurveTrack(track);
    trackById.set(track.track_uid, renderTrack);

    const sideSign = track.position === 'left' ? -1 : track.position === 'center' ? 0 : 1;
    const radialDistance = wellboreRadius * (2.75 + Math.max(0, track.distance_from_wellbore));
    const trackWidth = widthScale * Math.max(0.25, track.width);
    const resolvedPlacement = trackPlacements?.get(track.track_uid) ?? trackPlacements?.get(resolvedTrackPlacementKey('depth', track.display_order, track.position));

    let innerOffset: number;
    let outerOffset: number;
    if (resolvedPlacement) {
      innerOffset = resolvedPlacement.innerOffset;
      outerOffset = resolvedPlacement.outerOffset;
    } else if (track.position === 'center') {
      innerOffset = -trackWidth / 2;
      outerOffset = trackWidth / 2;
    } else {
      innerOffset = sideSign * radialDistance;
      outerOffset = innerOffset + sideSign * trackWidth;
    }
    const centerOffset = (innerOffset + outerOffset) / 2;

    // WLV-WBV-DEPTH-TRACK-FULL-BODY-LABEL-WEIGHT-EXACT-FIX
    // Complete camera-facing track body using the same inner/outer edge model
    // as the existing Curve track renderer.
    const innerVertices: ViewRelativeVertex[] = positions.map((position, index) => ({
      position,
      tangent: tangents[index],
      framePosition: index,
      offset: innerOffset,
    }));
    const outerVertices: ViewRelativeVertex[] = positions.map((position, index) => ({
      position,
      tangent: tangents[index],
      framePosition: index,
      offset: outerOffset,
    }));

    if (track.background_mode === 'solid' && track.opacity > 0) {
      const ribbonVertices: ViewRelativeVertex[] = [];
      positions.forEach((_, index) => {
        ribbonVertices.push(innerVertices[index], outerVertices[index]);
      });
      const ribbonIndices: number[] = [];
      for (let index = 0; index < positions.length - 1; index += 1) {
        const base = index * 2;
        ribbonIndices.push(base, base + 1, base + 2, base + 1, base + 3, base + 2);
      }
      const ribbonDynamic = dynamicGeometry(ribbonVertices, ribbonIndices, track.track_uid);
      const ribbonMaterial = new THREE.MeshBasicMaterial({
        color: new THREE.Color(track.background_color),
        transparent: true,
        opacity: track.opacity,
        side: THREE.DoubleSide,
        depthTest: false,
        depthWrite: false,
      });
      const ribbon = new THREE.Mesh(ribbonDynamic.geometry, ribbonMaterial);
      ribbon.renderOrder = 49;
      group.add(ribbon);
      bindings.push(ribbonDynamic.binding);
    }

    if (track.outline_visible) {
      [innerVertices, outerVertices].forEach((boundaryVertices) => {
        const boundaryDynamic = dynamicGeometry(boundaryVertices, undefined, track.track_uid);
        const boundaryMaterial = new THREE.LineBasicMaterial({
          color: 0xb9f3ff,
          transparent: true,
          opacity: track.opacity,
        });
        boundaryMaterial.depthTest = false;
        boundaryMaterial.depthWrite = false;
        const boundary = new THREE.Line(boundaryDynamic.geometry, boundaryMaterial);
        boundary.renderOrder = 50;
        group.add(boundary);
        bindings.push(boundaryDynamic.binding);
      });
    }

    // WLV-WBV-DEPTH-TRACK-STAGE3-REPAIR
    // Tick and label schedules are independent. The ruler is two-sided.
    depthTrackPositions(renderPoints, track, track.depth_increment).forEach((tick) => {
      const basis = interpolateTrajectoryBasisAtMd(renderPoints, positions, tangents, tick.md);
      if (!basis) return;

      const tickVertices: ViewRelativeVertex[] = [
        {
          position: basis.position,
          tangent: basis.tangent,
          framePosition: basis.framePosition,
          offset: innerOffset,
        },
        {
          position: basis.position,
          tangent: basis.tangent,
          framePosition: basis.framePosition,
          offset: outerOffset,
        },
      ];
      const tickDynamic = dynamicGeometry(tickVertices, undefined, track.track_uid);
      const tickMaterial = new THREE.LineBasicMaterial({
        color: 0xb9f3ff,
        transparent: true,
        opacity: track.opacity,
      });
      tickMaterial.depthTest = false;
      tickMaterial.depthWrite = false;
      const tickLine = new THREE.Line(tickDynamic.geometry, tickMaterial);
      tickLine.renderOrder = 51;
      group.add(tickLine);
      bindings.push(tickDynamic.binding);
    });

    depthTrackPositions(renderPoints, track, track.label_increment).forEach((labelPoint) => {
      const basis = interpolateTrajectoryBasisAtMd(renderPoints, positions, tangents, labelPoint.md);
      if (!basis) return;

      const unitSuffix = track.show_depth_units ? ` ${depthUnit}` : '';
      const formattedDepth = labelPoint.depth.toLocaleString(undefined, { maximumFractionDigits: 2 });
      const label = createTextSprite(`${formattedDepth}${unitSuffix}`, {
        color: viewProperties?.depthLabels.color ?? '#b9f3ff',
        // WLV-WBV-DEPTH-TRACK-TRANSPARENT-LABEL-BACKGROUND-FIX
        background: track.background_mode === 'solid' ? track.background_color : 'rgba(0, 0, 0, 0)',
        scale: 0.15 * track.label_size,
        fontWeight: 500,
        shadowBlur: 2,
        shadowColor: 'rgba(111, 211, 255, 0.18)',
      });
      label.material.opacity = track.opacity;
      label.renderOrder = 53;
      group.add(label);

      spriteBindings.push({
        sprite: label,
        trackId: track.track_uid,
        position: basis.position.clone(),
        framePosition: basis.framePosition,
        offset: centerOffset,
      });
    });
  });

  return { update };
}

// WLV-WBV-DEPTH-TRACK-STAGE2-RENDERER

function formatCurveScaleValue(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—';
  const magnitude = Math.abs(value);
  const maximumFractionDigits = magnitude >= 100 ? 0 : magnitude >= 10 ? 1 : 3;
  return value.toLocaleString(undefined, { maximumFractionDigits });
}

function curveScaleTicks(curve: WbvCurveOverlayRenderCurve): Array<{ position: number; value: number }> {
  const minimum = curve.display_min;
  const maximum = curve.display_max;
  if (typeof minimum !== 'number' || typeof maximum !== 'number' || !Number.isFinite(minimum) || !Number.isFinite(maximum) || minimum === maximum) return [];
  const reversed = curve.display_direction === 'reversed';
  const logarithmic = curve.scale_type === 'logarithmic' && minimum > 0 && maximum > 0;
  const fractions = logarithmic ? [0, 0.25, 0.5, 0.75, 1] : [0, 1 / 3, 2 / 3, 1];
  const low = Math.min(minimum, maximum);
  const high = Math.max(minimum, maximum);
  const logLow = logarithmic ? Math.log10(low) : 0;
  const logHigh = logarithmic ? Math.log10(high) : 0;
  return fractions.map((fraction) => ({
    position: reversed ? 1 - fraction : fraction,
    value: logarithmic ? 10 ** (logLow + (logHigh - logLow) * fraction) : low + (high - low) * fraction,
  }));
}

function createCurveTextLabelSprite(curve: WbvCurveOverlayRenderCurve, point: PreparedOverlayPoint): THREE.Sprite {
  const includeValue = (curve.label_content ?? 'mnemonic') === 'mnemonic_value';
  const canvas = document.createElement('canvas');
  canvas.width = 560;
  canvas.height = includeValue ? 230 : 150;
  const context = canvas.getContext('2d');
  if (context) {
    const size = THREE.MathUtils.clamp(curve.label_size ?? 1, 0.5, 2.5);
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.textAlign = 'center';
    context.textBaseline = 'middle';
    context.font = `${THREE.MathUtils.clamp(curve.label_weight ?? 800, 400, 900)} ${Math.round(48 * size)}px Inter, Arial, sans-serif`;
    context.fillStyle = curve.color;
    context.fillText(curve.mnemonic || 'CURVE', canvas.width / 2, includeValue ? 72 : canvas.height / 2);
    if (includeValue) {
      const unit = curve.unit ? ` ${curve.unit}` : '';
      context.font = `700 ${Math.round(34 * size)}px Inter, Arial, sans-serif`;
      context.fillStyle = '#dbe5ec';
      context.fillText(`${formatCurveScaleValue(point.value)}${unit}`, canvas.width / 2, 158);
    }
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.needsUpdate = true;
  const material = new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: false, depthWrite: false });
  const sprite = new THREE.Sprite(material);
  const baseHeight = includeValue ? 0.078 : 0.055;
  const aspect = canvas.width / canvas.height;
  sprite.scale.set(baseHeight * aspect, baseHeight, 1);
  sprite.userData.baseTextScale = sprite.scale.clone();
  return sprite;
}

function createCurveScaleSprite(
  curve: WbvCurveOverlayRenderCurve,
  curveWorldWidth: number,
): THREE.Sprite {
  const includeMnemonic = curve.label_content === 'mnemonic_scale';
  const canvas = document.createElement('canvas');
  canvas.width = 1200;
  canvas.height = includeMnemonic ? 300 : 230;
  const context = canvas.getContext('2d');
  const axisStart = 90;
  const axisEnd = 1110;
  if (context) {
    const scaleSize = THREE.MathUtils.clamp(curve.scale_size ?? 1, 0.5, 2);
    const scaleWeight = THREE.MathUtils.clamp(curve.scale_line_width ?? 1, 0.5, 4);
    const scaleColor = curve.scale_color ?? '#b7c5d0';
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.globalAlpha = 1;

    if (includeMnemonic) {
      const alignment = curve.label_alignment ?? 'center';
      context.textAlign = alignment;
      context.textBaseline = 'middle';
      context.fillStyle = curve.color;
      context.font = `${THREE.MathUtils.clamp(curve.label_weight ?? 800, 400, 900)} ${Math.round(56 * THREE.MathUtils.clamp(curve.label_size ?? 1, 0.5, 2.5))}px Inter, Arial, sans-serif`;
      const x = alignment === 'left' ? axisStart : alignment === 'right' ? axisEnd : (axisStart + axisEnd) / 2;
      context.fillText(curve.mnemonic || 'CURVE', x, 68);
    }

    const axisY = includeMnemonic ? 155 : 90;
    context.strokeStyle = scaleColor;
    context.fillStyle = scaleColor;
    context.lineWidth = Math.max(1, scaleWeight * 2);
    context.beginPath();
    context.moveTo(axisStart, axisY);
    context.lineTo(axisEnd, axisY);
    context.stroke();

    const tickLength = 22 * scaleSize;
    context.font = `700 ${Math.round(30 * scaleSize)}px Inter, Arial, sans-serif`;
    context.textAlign = 'center';
    context.textBaseline = 'top';
    curveScaleTicks(curve).forEach((tick) => {
      const x = axisStart + (axisEnd - axisStart) * tick.position;
      context.beginPath();
      context.moveTo(x, axisY - tickLength / 2);
      context.lineTo(x, axisY + tickLength / 2);
      context.stroke();
      context.fillText(formatCurveScaleValue(tick.value), x, axisY + tickLength / 2 + 10);
    });

    if (curve.unit) {
      context.textAlign = 'right';
      context.font = `700 ${Math.round(25 * scaleSize)}px Inter, Arial, sans-serif`;
      context.fillText(curve.unit, axisEnd, axisY - tickLength / 2 - 34);
    }
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.needsUpdate = true;
  const material = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    opacity: THREE.MathUtils.clamp(curve.scale_opacity ?? 1, 0, 1),
    depthTest: false,
    depthWrite: false,
    sizeAttenuation: true,
  });
  const sprite = new THREE.Sprite(material);
  const axisFraction = 1020 / 1200;
  const governedWidth = Math.max(0.0001, curveWorldWidth / axisFraction);
  const governedHeight = 0.075 * THREE.MathUtils.clamp(curve.scale_size ?? 1, 0.5, 2);
  sprite.scale.set(governedWidth, governedHeight, 1);
  sprite.renderOrder = 48 + curve.display_order;
  sprite.frustumCulled = false;
  return sprite;
}

function curveLabelAnchorPoint(
  segments: PreparedOverlayPoint[][],
  anchor: 'top' | 'base' | 'custom_md',
  customMd: number | null | undefined,
): PreparedOverlayPoint | null {
  const populated = segments.filter((segment) => segment.length > 0);
  if (populated.length === 0) return null;
  if (anchor === 'base') return populated[populated.length - 1][populated[populated.length - 1].length - 1];
  if (anchor !== 'custom_md' || typeof customMd !== 'number' || !Number.isFinite(customMd)) return populated[0][0];
  for (const segment of populated) {
    const interpolated = interpolatePreparedPoint(segment, customMd);
    if (interpolated) return interpolated;
  }
  let nearest: PreparedOverlayPoint | null = null;
  let nearestDistance = Number.POSITIVE_INFINITY;
  populated.forEach((segment) => {
    segment.forEach((point) => {
      const distance = Math.abs(point.md - customMd);
      if (distance < nearestDistance) { nearestDistance = distance; nearest = point; }
    });
  });
  return nearest;
}

function addCurveOverlays(
  group: THREE.Group,
  overlays: WbvCurveOverlayRenderCurve[],
  renderPoints: WbvTrajectoryRenderPoint[],
  positions: THREE.Vector3[],
  tracks: WbvCurveTrack[],
  trackSpacing: number,
  trackPlacements?: Map<string, WbvResolvedTrackPlacement>,
): CurveOverlayRuntime {
  const bindings: ViewRelativeGeometryBinding[] = [];
  const labelBindings: CurveLabelBinding[] = [];
  const scaleSpriteBindings: CurveScaleSpriteBinding[] = [];
  const tangents = trajectoryTangents(positions);
  const trackById = new Map(tracks.map((track) => [track.track_id, track]));
  const update = (camera: THREE.Camera) => {
    const cameraRight = new THREE.Vector3(1, 0, 0).applyQuaternion(camera.quaternion).normalize();
    const axesCache = new Map<string, THREE.Vector3[]>();
    bindings.forEach((binding) => {
      let axes = axesCache.get(binding.trackId);
      if (!axes) {
        axes = axesForTrack(trackById.get(binding.trackId), tangents, cameraRight);
        axesCache.set(binding.trackId, axes);
      }
      updateViewRelativeBinding(binding, axes);
    });
    labelBindings.forEach((binding) => {
      let axes = axesCache.get(binding.trackId);
      if (!axes) {
        axes = axesForTrack(trackById.get(binding.trackId), tangents, cameraRight);
        axesCache.set(binding.trackId, axes);
      }
      const axis = axisAtFramePosition(axes, binding.vertex.framePosition);
      const cameraUp = new THREE.Vector3(0, 1, 0).applyQuaternion(camera.quaternion).normalize();
      const point = binding.vertex.position.clone().add(axis.multiplyScalar(binding.vertex.offset));
      point.add(cameraRight.clone().multiplyScalar(binding.horizontalWorldOffset));
      point.add(cameraUp.multiplyScalar(binding.verticalWorldOffset));
      binding.sprite.position.copy(point);
    });

    scaleSpriteBindings.forEach((binding) => {
      let axes = axesCache.get(binding.trackId);
      if (!axes) {
        axes = axesForTrack(trackById.get(binding.trackId), tangents, cameraRight);
        axesCache.set(binding.trackId, axes);
      }
      const axis = axisAtFramePosition(axes, binding.framePosition);
      const cameraUp = new THREE.Vector3(0, 1, 0).applyQuaternion(camera.quaternion).normalize();
      const centerOffset = binding.baselineOffset + binding.signedExcursion / 2;
      const point = binding.anchorPosition.clone().add(axis.clone().multiplyScalar(centerOffset));
      point.add(cameraRight.clone().multiplyScalar(binding.horizontalWorldOffset));
      point.add(cameraUp.multiplyScalar(binding.verticalWorldOffset));
      binding.sprite.position.copy(point);
    });
  };
  if (overlays.length === 0 || positions.length < 2) return { update };

  const wellboreRadius = 0.008;
  const innerClearance = wellboreRadius * 2.75;
  const widthScale = wellboreRadius * 5.0;
  const effectiveTracks = tracks.length > 0 ? [...tracks].sort((a, b) => a.display_order - b.display_order) : [{ track_id: 'curve-track-0', display_name: 'Track 1', track_type: 'curve' as const, display_order: 0, side: 'right' as const, geometry_type: 'legacy_planar' as const, radial_lane: 0, angular_position_deg: 0, orientation_mode: 'camera_facing' as const, thickness: 0.05, width: 1, background_mode: 'transparent' as const, background_color: '#000000', background_opacity: 0, border_visible: false, border_color: '#5f6d73', grid_mode: 'off' as const, grid_color: '#44545d', wellbore_offset: 0.15, previous_track_gap: trackSpacing }];
  const trackOffsets = new Map<string, number>();
  const sideOuterEdge: { left: number | null; right: number | null; center: number } = { left: null, right: null, center: 0 };
  effectiveTracks.forEach((track) => {
    const side = track.side;
    const trackWidth = widthScale * track.width;
    let baselineOffset: number;
    let outerOffset: number;
    const resolvedPlacement = trackPlacements?.get(track.track_id) ?? trackPlacements?.get(resolvedTrackPlacementKey('curve', track.display_order, side));
    if (resolvedPlacement) {
      baselineOffset = resolvedPlacement.innerOffset;
      outerOffset = resolvedPlacement.outerOffset;
      if (side !== 'center') sideOuterEdge[side] = Math.max(Math.abs(resolvedPlacement.innerOffset), Math.abs(resolvedPlacement.outerOffset));
    } else if (track.geometry_type !== 'legacy_planar') {
      const radialDistance = wellboreRadius * (2.75 + Math.max(0, track.wellbore_offset));
      if (track.side === 'left') {
        baselineOffset = -radialDistance;
        outerOffset = baselineOffset - trackWidth;
      } else if (track.side === 'center') {
        baselineOffset = -trackWidth / 2;
        outerOffset = trackWidth / 2;
      } else {
        baselineOffset = radialDistance;
        outerOffset = baselineOffset + trackWidth;
      }
    } else if (side === 'center') {
      const centerSpacing = sideOuterEdge.center;
      baselineOffset = -trackWidth / 2 - centerSpacing;
      outerOffset = trackWidth / 2 + centerSpacing;
      sideOuterEdge.center += wellboreRadius * Math.max(0, trackSpacing);
    } else {
      const previousOuterEdge = sideOuterEdge[side];
      const innerDistance = previousOuterEdge === null
        ? wellboreRadius * (2.75 + Math.max(0, track.wellbore_offset))
        : previousOuterEdge + wellboreRadius * Math.max(0, track.previous_track_gap ?? trackSpacing);
      const outerDistance = innerDistance + trackWidth;
      sideOuterEdge[side] = outerDistance;
      const sign = side === 'left' ? -1 : 1;
      baselineOffset = sign * innerDistance;
      outerOffset = sign * outerDistance;
    }
    trackOffsets.set(track.track_id, baselineOffset);

    const innerVertices: ViewRelativeVertex[] = positions.map((position, index) => ({ position, tangent: tangents[index], framePosition: index, offset: baselineOffset }));
    const outerVertices: ViewRelativeVertex[] = positions.map((position, index) => ({ position, tangent: tangents[index], framePosition: index, offset: outerOffset }));

    if (track.background_mode !== 'transparent' && track.background_opacity > 0) {
      const vertices: ViewRelativeVertex[] = [];
      positions.forEach((_, index) => vertices.push(innerVertices[index], outerVertices[index]));
      const indices: number[] = [];
      for (let index = 0; index < positions.length - 1; index += 1) {
        const base = index * 2;
        indices.push(base, base + 1, base + 2, base + 1, base + 3, base + 2);
      }
      const { geometry, binding } = dynamicGeometry(vertices, indices, track.track_id);
      bindings.push(binding);
      const color = track.background_mode === 'white' ? '#ffffff' : track.background_mode === 'black' ? '#000000' : track.background_color;
      const material = new THREE.MeshBasicMaterial({
        color: new THREE.Color(color),
        transparent: true,
        opacity: track.background_opacity,
        side: THREE.DoubleSide,
        depthTest: false,
        depthWrite: false,
      });
      const mesh = new THREE.Mesh(geometry, material);
      mesh.renderOrder = 20 + track.display_order;
      group.add(mesh);
    }

    if (track.grid_mode !== 'off') {
      const gridFractions = track.grid_mode === 'linear'
        ? [0.25, 0.5, 0.75]
        : [2, 3, 4, 5, 6, 7, 8, 9].map((value) => Math.log10(value));
      gridFractions.forEach((fraction) => {
        const offset = baselineOffset + (outerOffset - baselineOffset) * fraction;
        const vertices: ViewRelativeVertex[] = positions.map((position, index) => ({
          position,
          tangent: tangents[index],
          framePosition: index,
          offset,
        }));
        const { geometry, binding } = dynamicGeometry(vertices, undefined, track.track_id);
        bindings.push(binding);
        const line = new THREE.Line(geometry, new THREE.LineBasicMaterial({
          color: new THREE.Color(track.grid_color),
          transparent: true,
          opacity: 0.42,
          depthTest: false,
          depthWrite: false,
        }));
        line.renderOrder = 23 + track.display_order;
        group.add(line);
      });
    }

    if (track.border_visible) {
      [innerVertices, outerVertices].forEach((vertices) => {
        const { geometry, binding } = dynamicGeometry(vertices, undefined, track.track_id);
        bindings.push(binding);
        const line = new THREE.Line(geometry, new THREE.LineBasicMaterial({
          color: new THREE.Color(track.border_color),
          transparent: true,
          opacity: 0.75,
          depthTest: false,
          depthWrite: false,
        }));
        line.renderOrder = 24 + track.display_order;
        group.add(line);
      });
    }
  });

  const preparedByCurve = new Map<string, PreparedOverlayPoint[][]>();
  overlays.forEach((curve) => {
    const fallbackTrack = effectiveTracks[Math.min(curve.radial_lane, effectiveTracks.length - 1)];
    const track = trackById.get(curve.track_id ?? '') ?? fallbackTrack;
    const baselineOffset = trackOffsets.get(track.track_id) ?? innerClearance;
    const excursionSign = track.side === 'left' ? -1 : 1;
    // WBV lateral exaggeration is a direct multiplier on curve excursion:
    // 0.25 = 25%, 1.0 = normal, 3.0 = 300%.
    // Clamp here as a renderer safety gate so malformed/stale values cannot
    // exceed the supported presentation range.
    const exaggeration = Math.min(3, Math.max(0.25, curve.radial_width));
    const excursion = excursionSign * widthScale * track.width * exaggeration;
    preparedByCurve.set(curve.curve_product_id, preparedOverlaySegments(
      curve,
      renderPoints,
      positions,
      tangents,
      baselineOffset,
      excursion,
    ));
  });

  overlays.forEach((curve) => {
    const fallbackTrack = effectiveTracks[Math.min(curve.radial_lane, effectiveTracks.length - 1)];
    const track = trackById.get(curve.track_id ?? '') ?? fallbackTrack;
    const segments = preparedByCurve.get(curve.curve_product_id) ?? [];

    if ((curve.fill_mode === 'between_curves' || curve.fill_mode === 'crossover') && curve.fill_target_curve_product_id) {
      const target = overlays.find((candidate) => candidate.curve_product_id === curve.fill_target_curve_product_id);
      const targetSegments = preparedByCurve.get(curve.fill_target_curve_product_id) ?? [];
      if (target && (target.track_id ?? String(target.radial_lane)) === (curve.track_id ?? String(curve.radial_lane))) {
        pairedOverlaySegments(segments, targetSegments).forEach((segment) => {
          const vertices: ViewRelativeVertex[] = [];
          segment.forEach((point) => {
            vertices.push(
              { position: point.first.basis.position, tangent: point.first.basis.tangent, framePosition: point.first.basis.framePosition, offset: point.first.traceOffset },
              { position: point.second.basis.position, tangent: point.second.basis.tangent, framePosition: point.second.basis.framePosition, offset: point.second.traceOffset },
            );
          });
          const indices: number[] = [];
          for (let index = 0; index < segment.length - 1; index += 1) {
            const firstPair = segment[index];
            const secondPair = segment[index + 1];
            if (curve.fill_mode === 'crossover') {
              const firstDelta = firstPair.first.traceOffset - firstPair.second.traceOffset;
              const secondDelta = secondPair.first.traceOffset - secondPair.second.traceOffset;
              if (firstDelta < 0 || secondDelta < 0) continue;
            }
            const base = index * 2;
            indices.push(base, base + 1, base + 2, base + 1, base + 3, base + 2);
          }
          if (indices.length > 0) {
            const { geometry, binding } = dynamicGeometry(vertices, indices, track.track_id);
            bindings.push(binding);
            const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({
              color: new THREE.Color(curve.fill_color),
              transparent: true,
              opacity: curve.fill_opacity,
              side: THREE.DoubleSide,
              depthTest: false,
              depthWrite: false,
            }));
            mesh.renderOrder = 30 + curve.display_order;
            group.add(mesh);
          }
        });
      }
    }

    segments.forEach((segment) => {
      if (curve.fill_mode === 'to_baseline') {
        const vertices: ViewRelativeVertex[] = [];
        const indices: number[] = [];
        segment.forEach((point) => {
          vertices.push(
            { position: point.basis.position, tangent: point.basis.tangent, framePosition: point.basis.framePosition, offset: point.traceOffset },
            { position: point.basis.position, tangent: point.basis.tangent, framePosition: point.basis.framePosition, offset: point.baselineOffset },
          );
        });
        for (let index = 0; index < segment.length - 1; index += 1) {
          const first = segment[index];
          const second = segment[index + 1];
          const firstEnabled = curve.fill_side === 'positive'
            ? first.normalized >= curve.baseline_normalized
            : first.normalized <= curve.baseline_normalized;
          const secondEnabled = curve.fill_side === 'positive'
            ? second.normalized >= curve.baseline_normalized
            : second.normalized <= curve.baseline_normalized;
          if (!firstEnabled || !secondEnabled) continue;
          const base = index * 2;
          indices.push(base, base + 1, base + 2, base + 1, base + 3, base + 2);
        }
        if (indices.length > 0) {
          const { geometry, binding } = dynamicGeometry(vertices, indices, track.track_id);
          bindings.push(binding);
          const fillMesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({
            color: new THREE.Color(curve.fill_color),
            transparent: true,
            opacity: curve.fill_opacity,
            side: THREE.DoubleSide,
            depthTest: false,
            depthWrite: false,
          }));
          fillMesh.renderOrder = 30 + curve.display_order;
          group.add(fillMesh);
        }
      }

      const { geometry, binding } = dynamicGeometry(viewVerticesFromPoints(segment, 'traceOffset'), undefined, track.track_id);
      bindings.push(binding);
      const line = new THREE.Line(geometry, new THREE.LineBasicMaterial({
        color: new THREE.Color(curve.color),
        transparent: true,
        opacity: curve.opacity,
        linewidth: curve.line_width,
        depthTest: false,
        depthWrite: false,
      }));
      line.renderOrder = 40 + curve.display_order;
      group.add(line);
    });

    if (curve.label_visible) {
      const labelPoint = curveLabelAnchorPoint(segments, curve.label_anchor ?? 'top', curve.label_custom_md);
      if (labelPoint) {
        const content = curve.label_content ?? 'mnemonic';
        const scaleMode = content === 'scale' || content === 'mnemonic_scale';
        const legacyPosition = curve.label_position === 'center' ? 'on_track' : curve.label_position;
        const placement = legacyPosition ?? 'on_track';
        const signedExcursion = (track.side === 'left' ? -1 : 1) * widthScale * track.width * Math.min(3, Math.max(0.25, curve.radial_width));
        const curveWorldWidth = Math.abs(signedExcursion);
        const fineHorizontal = THREE.MathUtils.clamp(curve.label_horizontal_adjustment ?? 0, -4, 4) * widthScale;
        const fineVertical = THREE.MathUtils.clamp(curve.label_vertical_adjustment ?? 0, -4, 4) * widthScale;
        const placementGap = widthScale * 0.28;
        const placementShift = placement === 'left'
          ? -(curveWorldWidth + placementGap)
          : placement === 'right'
            ? curveWorldWidth + placementGap
            : 0;
        if (scaleMode) {
          const sprite = createCurveScaleSprite(curve, curveWorldWidth);
          group.add(sprite);
          scaleSpriteBindings.push({
            sprite,
            trackId: track.track_id,
            anchorPosition: labelPoint.basis.position.clone(),
            framePosition: labelPoint.basis.framePosition,
            baselineOffset: labelPoint.baselineOffset,
            signedExcursion,
            horizontalWorldOffset: placementShift + fineHorizontal,
            verticalWorldOffset: fineVertical,
          });
        } else {
          const sprite = createCurveTextLabelSprite(curve, labelPoint);
          sprite.material.opacity = Math.max(0.45, curve.opacity);
          sprite.renderOrder = 48 + curve.display_order;
          group.add(sprite);
          labelBindings.push({
            sprite,
            trackId: track.track_id,
            vertex: {
              position: labelPoint.basis.position,
              tangent: labelPoint.basis.tangent,
              framePosition: labelPoint.basis.framePosition,
              offset: labelPoint.traceOffset,
            },
            horizontalWorldOffset: placementShift + fineHorizontal,
            verticalWorldOffset: fineVertical,
          });
        }
      }
    }
  });

  return { update };
}

function materialList(material: THREE.Material | THREE.Material[] | undefined): THREE.Material[] {
  if (!material) return [];
  return Array.isArray(material) ? material : [material];
}

function cameraPlanFor(preset: WbvViewPreset, box: SceneBox, aspect: number): CameraPlan {
  const center = sceneBoxCenter(box);
  const span = sceneBoxSpan(box);
  const lateralSpan = Math.max(span.x, span.z, 1);
  const fitHeight = Math.max(span.y * 1.34, lateralSpan * 1.38, 7.55);
  const distance = Math.max(18, span.max * 3.5);

  if (preset === 'top') {
    return {
      position: center.clone().add(new THREE.Vector3(0, distance, 0.01)),
      up: new THREE.Vector3(0, 0, -1),
      target: center,
      viewHeight: Math.max(lateralSpan * 1.65, 3.9),
    };
  }

  if (preset === 'north') {
    return {
      position: center.clone().add(new THREE.Vector3(0.01, 0, distance)),
      up: new THREE.Vector3(0, 1, 0),
      target: center,
      viewHeight: Math.max(span.y * 1.24, 7.05),
    };
  }

  if (preset === 'east') {
    return {
      position: center.clone().add(new THREE.Vector3(distance, 0, 0.01)),
      up: new THREE.Vector3(0, 1, 0),
      target: center,
      viewHeight: Math.max(span.y * 1.24, 7.05),
    };
  }

  if (preset === 'south') {
    return {
      position: center.clone().add(new THREE.Vector3(0.01, 0, -distance)),
      up: new THREE.Vector3(0, 1, 0),
      target: center,
      viewHeight: Math.max(span.y * 1.24, 7.05),
    };
  }

  if (preset === 'west') {
    return {
      position: center.clone().add(new THREE.Vector3(-distance, 0, 0.01)),
      up: new THREE.Vector3(0, 1, 0),
      target: center,
      viewHeight: Math.max(span.y * 1.24, 7.05),
    };
  }

  if (preset === 'fit') {
    return {
      position: center.clone().add(new THREE.Vector3(distance * 0.55, distance * 0.24, distance * 0.86)),
      up: new THREE.Vector3(0, 1, 0),
      target: center,
      viewHeight: Math.max(fitHeight, 7.9 / Math.max(0.8, aspect)),
    };
  }

  return {
    position: center.clone().add(new THREE.Vector3(distance * 0.6, distance * 0.32, distance * 0.92)),
    up: new THREE.Vector3(0, 1, 0),
    target: center,
    viewHeight: Math.max(fitHeight * 1.06, 8.1 / Math.max(0.8, aspect)),
  };
}

function applyCameraProjection(camera: THREE.OrthographicCamera, viewHeight: number, aspect: number): void {
  camera.left = -viewHeight * aspect * 0.5;
  camera.right = viewHeight * aspect * 0.5;
  camera.top = viewHeight * 0.5;
  camera.bottom = -viewHeight * 0.5;
  camera.near = 0.1;
  camera.far = 1000;
  camera.updateProjectionMatrix();
}

function applyCameraPlan(
  camera: THREE.OrthographicCamera,
  controls: OrbitControls,
  plan: CameraPlan,
  aspect: number,
): void {
  camera.position.copy(plan.position);
  camera.up.copy(plan.up);
  camera.zoom = 1;
  applyCameraProjection(camera, plan.viewHeight, aspect);
  controls.target.copy(plan.target);
  camera.lookAt(plan.target);
  controls.update();
}


export function nearestSegmentOnScreen(
  event: PointerEvent,
  canvas: HTMLCanvasElement,
  camera: THREE.Camera,
  points: THREE.Vector3[],
): { segmentIndex: number; ratio: number; distance: number } | null {
  const rect = canvas.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0 || points.length < 2) return null;
  const px = event.clientX - rect.left;
  const py = event.clientY - rect.top;
  let best: { segmentIndex: number; ratio: number; distance: number } | null = null;
  const projected = points.map((point) => {
    const p = point.clone().project(camera);
    return { x: (p.x * 0.5 + 0.5) * rect.width, y: (-p.y * 0.5 + 0.5) * rect.height };
  });
  for (let index = 0; index < projected.length - 1; index += 1) {
    const a = projected[index];
    const b = projected[index + 1];
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const lengthSquared = dx * dx + dy * dy;
    const ratio = lengthSquared > 0 ? Math.max(0, Math.min(1, ((px - a.x) * dx + (py - a.y) * dy) / lengthSquared)) : 0;
    const nx = a.x + ratio * dx;
    const ny = a.y + ratio * dy;
    const distance = Math.hypot(px - nx, py - ny);
    if (!best || distance < best.distance) best = { segmentIndex: index, ratio, distance };
  }
  return best;
}

export function cameraFacingMarkerPosition(
  basePosition: THREE.Vector3,
  cameraDirection: THREE.Vector3,
  offset = 0.028,
): THREE.Vector3 {
  return basePosition.clone().addScaledVector(cameraDirection, -Math.max(0, offset));
}


export function markerScaleForZoom(zoom: number): number {
  const safeZoom = Math.max(0.25, Number.isFinite(zoom) ? zoom : 1);
  return THREE.MathUtils.clamp(Math.pow(safeZoom, -1.1), 0.12, 1.25);
}

export function selectionMarkerScaleForZoom(zoom: number): number {
  const safeZoom = Math.max(0.1, Number.isFinite(zoom) ? zoom : 1);
  // The selected-point marker should remain easy to find at overview scale, then
  // become progressively smaller relative to the wellbore as the camera zooms in.
  // A shallow inverse curve avoids both failure modes seen in testing:
  //   - fixed world size: too dominant at high zoom;
  //   - generic markerScaleForZoom(): collapses to a pinprick.
  return THREE.MathUtils.clamp(Math.pow(safeZoom, -0.35), 0.38, 1.6);
}

export function surveyStationPointSizeForZoom(zoom: number): number {
  const safeZoom = Math.max(0.25, Number.isFinite(zoom) ? zoom : 1);
  return THREE.MathUtils.clamp(4.2 * Math.pow(safeZoom, -0.2), 2.0, 4.8);
}

export function textSpriteScaleForZoom(zoom: number): number {
  const safeZoom = Math.max(0.25, Number.isFinite(zoom) ? zoom : 1);
  return THREE.MathUtils.clamp(Math.pow(safeZoom, -0.82), 0.08, 1.18);
}

export function markerSmoothingAlpha(deltaMs: number, zoom: number): number {
  const safeDelta = THREE.MathUtils.clamp(Number.isFinite(deltaMs) ? deltaMs : 16.67, 0, 100);
  const safeZoom = Math.max(1, Number.isFinite(zoom) ? zoom : 1);
  const timeConstantMs = THREE.MathUtils.clamp(48 + Math.log2(safeZoom) * 12, 48, 110);
  return 1 - Math.exp(-safeDelta / timeConstantMs);
}

export function interpolateCurveValueAtMd(
  samples: WbvCurveOverlayRenderSample[],
  md: number,
): number | null {
  const ordered = samples
    .filter((sample) => Number.isFinite(sample.md) && Number.isFinite(sample.value))
    .slice()
    .sort((a, b) => a.md - b.md);
  if (ordered.length === 0 || md < ordered[0].md || md > ordered[ordered.length - 1].md) return null;
  for (let index = 0; index < ordered.length - 1; index += 1) {
    const first = ordered[index];
    const second = ordered[index + 1];
    if (md < first.md || md > second.md) continue;
    const ratio = second.md === first.md ? 0 : THREE.MathUtils.clamp((md - first.md) / (second.md - first.md), 0, 1);
    return first.value + (second.value - first.value) * ratio;
  }
  return ordered[ordered.length - 1].value;
}

function disposeObject(object: THREE.Object3D): void {
  object.traverse((child: THREE.Object3D) => {
    child.userData.wbvDisposed = true;
    const materialHolder = child as THREE.Object3D & { material?: THREE.Material | THREE.Material[] };
    const geometryHolder = child as THREE.Object3D & { geometry?: THREE.BufferGeometry };

    geometryHolder.geometry?.dispose();

    materialList(materialHolder.material).forEach((material) => {
      const maybeMapped = material as THREE.Material & { map?: THREE.Texture | null; emissiveMap?: THREE.Texture | null };
      const textures = new Set<THREE.Texture>();
      if (maybeMapped.map) textures.add(maybeMapped.map);
      if (maybeMapped.emissiveMap) textures.add(maybeMapped.emissiveMap);
      textures.forEach((texture) => texture.dispose());
      material.dispose();
    });
  });
}

type WbvKrLithologyEntry = {
  id?: string;
  pattern?: { asset?: string; defaultScale?: number };
  colors?: { defaultBackground?: string; defaultPattern?: string };
};


type CoreTrackPick = {
  product_id: string;
  md: number;
  top_md: number;
  base_md: number;
};

type CoreTrackRuntime = {
  update(camera: THREE.Camera): void;
  setFocusInterval(interval: { top_md: number; base_md: number } | null): void;
  pick(pointerNdc: THREE.Vector2, viewportWidth: number, viewportHeight: number): CoreTrackPick | null;
};

function addCoreImageTracks(
  group: THREE.Group,
  chunks: WbvCoreRenderChunk[],
  tracks: WbvCoreTrack[],
  renderPoints: WbvTrajectoryRenderPoint[],
  positions: THREE.Vector3[],
  inspectionInterval: { top_md: number; base_md: number } | null,
  focusInterval: { top_md: number; base_md: number } | null,
  appearance?: WbvCoreAppearance,
  trackPlacements?: Map<string, WbvResolvedTrackPlacement>,
): CoreTrackRuntime {
  const tangents = trajectoryTangents(positions);
  const ribbonBindings: Array<{
    attribute: THREE.BufferAttribute;
    vertices: ViewRelativeVertex[];
  }> = [];
  const locatorBindings: Array<{
    mesh: THREE.Mesh;
    hitMesh: THREE.Mesh;
    productId: string;
    topMd: number;
    baseMd: number;
    startCap: THREE.Mesh;
    endCap: THREE.Mesh;
  }> = [];

  const visibleTracks = tracks
    .filter((track) => track.visible && track.track_type === 'core')
    .sort((first, second) => first.display_order - second.display_order);
  const track = visibleTracks[0];

  if (!track || chunks.length === 0 || positions.length < 2) {
    return { update: () => undefined, setFocusInterval: () => undefined, pick: () => null };
  }

  const wellboreRadius = 0.008;
  const sideSign = track.position === 'left' ? -1 : track.position === 'center' ? 0 : 1;
  const radialDistance = wellboreRadius * (2.75 + Math.max(0, track.distance_from_wellbore));
  const widthMultiplier = Math.max(0.05, track.width);
  const locatorRadius = wellboreRadius * 0.36 * Math.max(0.5, widthMultiplier);
  const resolvedPlacement = trackPlacements?.get(track.track_uid) ?? trackPlacements?.get(resolvedTrackPlacementKey('core', track.display_order, track.position));
  const resolvedCenterOffset = resolvedPlacement?.centerOffset ?? (track.position === 'center' ? 0 : sideSign * (radialDistance + locatorRadius));

  const median = (values: number[]) => {
    const ordered = [...values].sort((left, right) => left - right);
    const middle = Math.floor(ordered.length / 2);
    return ordered.length % 2 === 0
      ? (ordered[middle - 1] + ordered[middle]) / 2
      : ordered[middle];
  };

  const productGeometry = new Map<string, { nativeWidth: number; nativePixelsPerMd: number }>();
  const groupedGeometry = new Map<string, Array<{ width: number; pixelsPerMd: number }>>();

  chunks.forEach((chunk) => {
    const nativeWidth = Number(chunk.pixel_width);
    const nativeHeight = Number(chunk.pixel_height);
    const mdSpan = Math.abs(Number(chunk.base_md) - Number(chunk.top_md));
    if (
      !Number.isFinite(nativeWidth)
      || !Number.isFinite(nativeHeight)
      || !Number.isFinite(mdSpan)
      || nativeWidth <= 0
      || nativeHeight <= 0
      || mdSpan <= 0
    ) return;

    const samples = groupedGeometry.get(chunk.product_id) ?? [];
    samples.push({ width: nativeWidth, pixelsPerMd: nativeHeight / mdSpan });
    groupedGeometry.set(chunk.product_id, samples);
  });

  groupedGeometry.forEach((samples, productId) => {
    productGeometry.set(productId, {
      nativeWidth: median(samples.map((sample) => sample.width)),
      nativePixelsPerMd: median(samples.map((sample) => sample.pixelsPerMd)),
    });
  });

  const inspectionTop = inspectionInterval
    ? Math.min(inspectionInterval.top_md, inspectionInterval.base_md)
    : null;
  const inspectionBase = inspectionInterval
    ? Math.max(inspectionInterval.top_md, inspectionInterval.base_md)
    : null;

  const addInspectionRibbon = (chunk: WbvCoreRenderChunk) => {
    const topMd = Math.min(chunk.top_md, chunk.base_md);
    const baseMd = Math.max(chunk.top_md, chunk.base_md);
    if (!Number.isFinite(topMd) || !Number.isFinite(baseMd) || baseMd <= topMd) return;

    const nativeWidth = Number(chunk.pixel_width);
    const nativeHeight = Number(chunk.pixel_height);
    const mdSpan = baseMd - topMd;
    const nativePixelsPerMd =
      Number.isFinite(nativeHeight) && nativeHeight > 0 && mdSpan > 0
        ? nativeHeight / mdSpan
        : 0;
    const referenceGeometry = productGeometry.get(chunk.product_id);
    const geometryConsistent =
      Number.isFinite(nativeWidth)
      && Number.isFinite(nativeHeight)
      && nativeWidth > 0
      && nativeHeight > 0
      && referenceGeometry !== undefined
      && referenceGeometry.nativeWidth > 0
      && referenceGeometry.nativePixelsPerMd > 0
      && Math.abs(nativeWidth / referenceGeometry.nativeWidth - 1) <= 0.05
      && Math.abs(nativePixelsPerMd / referenceGeometry.nativePixelsPerMd - 1) <= 0.05;

    if (!geometryConsistent) {
      console.warn('WBV Core inspection geometry rejected: invalid or inconsistent native raster geometry', {
        productId: chunk.product_id,
        chunkId: chunk.chunk_id,
        pixelWidth: nativeWidth,
        pixelHeight: nativeHeight,
        nativePixelsPerMd,
        referenceGeometry,
      });
      return;
    }

    const rowCount = Math.max(4, Math.min(160, Math.ceil(mdSpan / 1.5) + 1));
    const rows: TrajectoryBasis[] = [];
    for (let row = 0; row < rowCount; row += 1) {
      const basis = interpolateTrajectoryBasisAtMd(
        renderPoints,
        positions,
        tangents,
        THREE.MathUtils.lerp(topMd, baseMd, row / (rowCount - 1)),
      );
      if (basis) rows.push(basis);
    }
    if (rows.length < 2) return;

    let alongHoleSceneLength = 0;
    for (let row = 1; row < rows.length; row += 1) {
      alongHoleSceneLength += rows[row].position.distanceTo(rows[row - 1].position);
    }
    if (!Number.isFinite(alongHoleSceneLength) || alongHoleSceneLength <= 0) return;

    const naturalCoreWidth = alongHoleSceneLength * (nativeWidth / nativeHeight);
    const renderedCoreWidth = naturalCoreWidth * widthMultiplier;
    if (!Number.isFinite(renderedCoreWidth) || renderedCoreWidth <= 0) return;

    let innerOffset: number;
    let outerOffset: number;
    if (track.position === 'center') {
      innerOffset = -renderedCoreWidth / 2;
      outerOffset = renderedCoreWidth / 2;
    } else if (resolvedPlacement) {
      innerOffset = resolvedCenterOffset - sideSign * (renderedCoreWidth / 2);
      outerOffset = resolvedCenterOffset + sideSign * (renderedCoreWidth / 2);
    } else {
      innerOffset = sideSign * radialDistance;
      outerOffset = innerOffset + sideSign * renderedCoreWidth;
    }

    const vertices: ViewRelativeVertex[] = [];
    const uvs: number[] = [];
    rows.forEach((basis, rowIndex) => {
      const v = rowIndex / (rows.length - 1);
      vertices.push({ position: basis.position.clone(), tangent: basis.tangent.clone(), framePosition: basis.framePosition, offset: innerOffset });
      vertices.push({ position: basis.position.clone(), tangent: basis.tangent.clone(), framePosition: basis.framePosition, offset: outerOffset });
      uvs.push(0, 1 - v, 1, 1 - v);
    });

    const indices: number[] = [];
    for (let row = 0; row < rows.length - 1; row += 1) {
      const a = row * 2;
      indices.push(a, a + 2, a + 1, a + 1, a + 2, a + 3);
    }

    const geometry = new THREE.BufferGeometry();
    const positionAttribute = new THREE.BufferAttribute(new Float32Array(vertices.length * 3), 3);
    geometry.setAttribute('position', positionAttribute);
    geometry.setAttribute('uv', new THREE.BufferAttribute(new Float32Array(uvs), 2));
    geometry.setIndex(indices);

    const material = new THREE.MeshBasicMaterial({
      color: 0xffffff,
      transparent: track.opacity < 0.999,
      opacity: THREE.MathUtils.clamp(track.opacity, 0, 1),
      side: THREE.DoubleSide,
      depthTest: true,
      depthWrite: track.opacity >= 0.999,
    });
    const texture = new THREE.TextureLoader().load(chunk.image_url);
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.minFilter = THREE.LinearFilter;
    texture.magFilter = THREE.LinearFilter;
    material.map = texture;
    material.needsUpdate = true;

    const mesh = new THREE.Mesh(geometry, material);
    mesh.name = `wbv-core-${chunk.product_id}-${chunk.chunk_id}`;
    mesh.renderOrder = 45;
    mesh.userData = {
      kind: 'core_image_chunk',
      productId: chunk.product_id,
      chunkId: chunk.chunk_id,
      topMd,
      baseMd,
      displayMode: 'inspection_photo',
    };
    group.add(mesh);
    ribbonBindings.push({ attribute: positionAttribute, vertices });
  };

  /*
   * OVERVIEW CORE RUN CONTRACT
   *
   * Runtime evidence shows CIM display chunks are raster subdivisions, not
   * semantic Core intervals. Therefore overview locator runs are derived only
   * from exact MD continuity:
   *
   *   next.top_md <= current.base_md + epsilon  => same run
   *   next.top_md >  current.base_md + epsilon  => genuine Core gap
   *
   * No guessed merge tolerance is used. Every positive MD gap is preserved.
   */
  const overviewIntervalsByProduct = new Map<string, Array<{ topMd: number; baseMd: number }>>();
  chunks.forEach((chunk) => {
    const topMd = Math.min(chunk.top_md, chunk.base_md);
    const baseMd = Math.max(chunk.top_md, chunk.base_md);
    if (!Number.isFinite(topMd) || !Number.isFinite(baseMd) || baseMd <= topMd) return;

    const inspectionActiveForChunk =
      inspectionTop !== null
      && inspectionBase !== null
      && baseMd >= inspectionTop
      && topMd <= inspectionBase;

    if (inspectionActiveForChunk) {
      addInspectionRibbon(chunk);
      return;
    }

    /*
     * Inspection isolation:
     * while any Core inspection interval is active, do not construct
     * overview locator runs from the non-inspected chunks. The inspection
     * photograph must stand alone without the larger Core locator behind it.
     */
    if (inspectionInterval !== null) return;

    const intervals = overviewIntervalsByProduct.get(chunk.product_id) ?? [];
    intervals.push({ topMd, baseMd });
    overviewIntervalsByProduct.set(chunk.product_id, intervals);
  });

  const locatorBrightness = THREE.MathUtils.clamp(appearance?.brightness ?? 1.35, 0.75, 2.5);
  const locatorBrightnessScale = locatorBrightness / 1.35;
  const locatorBaseColor = new THREE.Color(appearance?.color ?? '#7b838a');
  const locatorDisplayColor = locatorBaseColor.clone();
  locatorDisplayColor.r = THREE.MathUtils.clamp(locatorDisplayColor.r * locatorBrightnessScale, 0, 1);
  locatorDisplayColor.g = THREE.MathUtils.clamp(locatorDisplayColor.g * locatorBrightnessScale, 0, 1);
  locatorDisplayColor.b = THREE.MathUtils.clamp(locatorDisplayColor.b * locatorBrightnessScale, 0, 1);
  const locatorEmissive = locatorBaseColor.clone().multiplyScalar(0.075 * locatorBrightnessScale);

  const locatorMaterial = new THREE.MeshStandardMaterial({
    color: locatorDisplayColor,
    metalness: 0.05,
    roughness: 0.72,
    emissive: locatorEmissive,
    emissiveIntensity: 0.18,
    transparent: track.opacity < 0.999,
    opacity: THREE.MathUtils.clamp(track.opacity, 0, 1),
    depthTest: true,
    depthWrite: track.opacity >= 0.999,
    side: THREE.FrontSide,
  });
  const capGeometry = new THREE.SphereGeometry(locatorRadius, 14, 10);
  let activeFocusInterval = focusInterval;

  // WDV edge_arrows: two independent fixed-size orange markers on the
  // locator's outer side, both pointing inward toward the locator.
  const focusArrowPoints = new THREE.Points(
    new THREE.BufferGeometry(),
    (() => {
      const textureSize = 96;
      const canvas = document.createElement('canvas');
      canvas.width = textureSize;
      canvas.height = textureSize;
      const context = canvas.getContext('2d');
      if (!context) {
        return new THREE.PointsMaterial({
          color: 0xf59e0b,
          size: 12,
          sizeAttenuation: false,
          transparent: true,
          opacity: 0.98,
          depthTest: false,
          depthWrite: false,
        });
      }

      context.clearRect(0, 0, textureSize, textureSize);
      context.fillStyle = '#f59e0b';
      context.beginPath();

      // Render the same WDV inward-facing triangle at high resolution and
      // let linear filtering/downsampling provide anti-aliased edges.
      const pointsLeft = sideSign >= 0;
      if (pointsLeft) {
        context.moveTo(textureSize * 0.18, textureSize * 0.50);
        context.lineTo(textureSize * 0.82, textureSize * 0.18);
        context.lineTo(textureSize * 0.82, textureSize * 0.82);
      } else {
        context.moveTo(textureSize * 0.82, textureSize * 0.50);
        context.lineTo(textureSize * 0.18, textureSize * 0.18);
        context.lineTo(textureSize * 0.18, textureSize * 0.82);
      }
      context.closePath();
      context.fill();

      const texture = new THREE.CanvasTexture(canvas);
      texture.needsUpdate = true;
      texture.magFilter = THREE.LinearFilter;
      texture.minFilter = THREE.LinearFilter;
      texture.generateMipmaps = false;

      return new THREE.PointsMaterial({
        size: 12,
        sizeAttenuation: false,
        map: texture,
        transparent: true,
        alphaTest: 0.01,
        depthTest: false,
        depthWrite: false,
      });
    })(),
  );
  focusArrowPoints.name = 'wbv-core-locator-focus-bracket';
  focusArrowPoints.renderOrder = 60;
  focusArrowPoints.userData = {
    kind: 'core_locator_focus_bracket',
    style: 'wdv_edge_arrows_antialiased',
  };
  focusArrowPoints.visible = false;
  focusArrowPoints.frustumCulled = false;
  group.add(focusArrowPoints);

  overviewIntervalsByProduct.forEach((intervals, productId) => {
    const ordered = [...intervals].sort((left, right) => left.topMd - right.topMd);
    const runs: Array<{ topMd: number; baseMd: number }> = [];
    const continuityEpsilonMd = 1e-6;

    ordered.forEach((interval) => {
      const previous = runs[runs.length - 1];
      if (!previous) {
        runs.push({ ...interval });
      } else if (interval.topMd <= previous.baseMd + continuityEpsilonMd) {
        previous.baseMd = Math.max(previous.baseMd, interval.baseMd);
      } else {
        runs.push({ ...interval });
      }
    });

    runs.forEach((run, runIndex) => {
      const mesh = new THREE.Mesh(new THREE.BufferGeometry(), locatorMaterial.clone());
      mesh.name = `wbv-core-locator-run-${productId}-${runIndex}`;
      mesh.renderOrder = 44;
      mesh.userData = {
        kind: 'core_locator_run',
        productId,
        runIndex,
        topMd: run.topMd,
        baseMd: run.baseMd,
        displayMode: 'overview_locator_tube',
      };
      const hitMaterial = new THREE.MeshBasicMaterial({
        transparent: true,
        opacity: 0,
        depthWrite: false,
        depthTest: false,
        side: THREE.DoubleSide,
      });
      const hitMesh = new THREE.Mesh(new THREE.BufferGeometry(), hitMaterial);
      hitMesh.name = `wbv-core-locator-hit-run-${productId}-${runIndex}`;
      hitMesh.renderOrder = 43;
      hitMesh.userData = {
        kind: 'core_locator_hit',
        productId,
        runIndex,
        topMd: run.topMd,
        baseMd: run.baseMd,
      };
      const startCap = new THREE.Mesh(capGeometry.clone(), locatorMaterial.clone());
      const endCap = new THREE.Mesh(capGeometry.clone(), locatorMaterial.clone());
      startCap.renderOrder = 44;
      endCap.renderOrder = 44;
      group.add(mesh, hitMesh, startCap, endCap);
      locatorBindings.push({
        mesh,
        hitMesh,
        productId,
        topMd: run.topMd,
        baseMd: run.baseMd,
        startCap,
        endCap,
      });
    });
  });

  let lastLocatorCameraQuaternion = new THREE.Quaternion(Number.NaN, Number.NaN, Number.NaN, Number.NaN);

  const rebuildLocatorTubes = (camera: THREE.Camera) => {
    if (locatorBindings.length === 0) return;
    if (lastLocatorCameraQuaternion.angleTo(camera.quaternion) < 1e-5) return;
    lastLocatorCameraQuaternion.copy(camera.quaternion);

    const cameraRight = new THREE.Vector3(1, 0, 0).applyQuaternion(camera.quaternion).normalize();
    const axes = sharedViewAxes(tangents, cameraRight);
    const centerOffset = resolvedCenterOffset;

    locatorBindings.forEach((binding) => {
      const span = binding.baseMd - binding.topMd;
      const sampleCount = Math.max(4, Math.min(96, Math.ceil(span / 1.5) + 1));
      const samples: THREE.Vector3[] = [];

      for (let index = 0; index < sampleCount; index += 1) {
        const basis = interpolateTrajectoryBasisAtMd(
          renderPoints,
          positions,
          tangents,
          THREE.MathUtils.lerp(binding.topMd, binding.baseMd, index / (sampleCount - 1)),
        );
        if (!basis) continue;
        const axis = axisAtFramePosition(axes, basis.framePosition);
        samples.push(basis.position.clone().add(axis.multiplyScalar(centerOffset)));
      }

      if (samples.length < 2) {
        binding.mesh.visible = false;
        binding.hitMesh.visible = false;
        binding.startCap.visible = false;
        binding.endCap.visible = false;
        return;
      }

      const curve = new THREE.CatmullRomCurve3(samples, false, 'catmullrom', 0.02);
      const geometry = new THREE.TubeGeometry(
        curve,
        Math.max(12, Math.min(180, samples.length * 4)),
        locatorRadius,
        14,
        false,
      );
      binding.mesh.geometry.dispose();
      binding.mesh.geometry = geometry;
      binding.mesh.visible = true;

      const hitGeometry = new THREE.TubeGeometry(
        curve,
        Math.max(12, Math.min(180, samples.length * 4)),
        Math.max(locatorRadius * 3.4, locatorRadius + 0.18),
        12,
        false,
      );
      binding.hitMesh.geometry.dispose();
      binding.hitMesh.geometry = hitGeometry;
      binding.hitMesh.visible = true;

      binding.startCap.position.copy(samples[0]);
      binding.endCap.position.copy(samples[samples.length - 1]);
      binding.startCap.visible = true;
      binding.endCap.visible = true;
    });

    if (activeFocusInterval) {
      const topMd = Math.min(activeFocusInterval.top_md, activeFocusInterval.base_md);
      const baseMd = Math.max(activeFocusInterval.top_md, activeFocusInterval.base_md);
      const topBasis = interpolateTrajectoryBasisAtMd(renderPoints, positions, tangents, topMd);
      const baseBasis = interpolateTrajectoryBasisAtMd(renderPoints, positions, tangents, baseMd);
      if (topBasis && baseBasis) {
        const side = sideSign === 0 ? 1 : sideSign;
        const topAxis = axisAtFramePosition(axes, topBasis.framePosition);
        const baseAxis = axisAtFramePosition(axes, baseBasis.framePosition);

        // WDV side semantics:
        // right edge => arrow points left into target
        // left edge  => arrow points right into target
        const markerOffset = resolvedCenterOffset + side * locatorRadius * 2.25;
        const topMarker = topBasis.position.clone().add(topAxis.multiplyScalar(markerOffset));
        const baseMarker = baseBasis.position.clone().add(baseAxis.multiplyScalar(markerOffset));

        focusArrowPoints.geometry.dispose();
        focusArrowPoints.geometry = new THREE.BufferGeometry().setFromPoints([
          topMarker,
          baseMarker,
        ]);
        focusArrowPoints.visible = true;
      } else {
        focusArrowPoints.visible = false;
      }
    } else {
      focusArrowPoints.visible = false;
    }
  };

  let lastCoreCamera: THREE.Camera | null = null;

  const update = (camera: THREE.Camera) => {
    lastCoreCamera = camera;
    const cameraRight = new THREE.Vector3(1, 0, 0).applyQuaternion(camera.quaternion).normalize();
    const axes = sharedViewAxes(tangents, cameraRight);
    ribbonBindings.forEach((binding) => {
      binding.vertices.forEach((vertex, index) => {
        const axis = axisAtFramePosition(axes, vertex.framePosition);
        const point = vertex.position.clone().add(axis.multiplyScalar(vertex.offset));
        binding.attribute.setXYZ(index, point.x, point.y, point.z);
      });
      binding.attribute.needsUpdate = true;
    });
    rebuildLocatorTubes(camera);
  };

  const setFocusInterval = (interval: { top_md: number; base_md: number } | null) => {
    activeFocusInterval = interval;
    if (!lastCoreCamera) return;
    lastLocatorCameraQuaternion.set(Number.NaN, Number.NaN, Number.NaN, Number.NaN);
    rebuildLocatorTubes(lastCoreCamera);
  };

  const pick = (
    pointerNdc: THREE.Vector2,
    viewportWidth: number,
    viewportHeight: number,
  ): CoreTrackPick | null => {
    const pickCamera = lastCoreCamera;
    if (!pickCamera || locatorBindings.length === 0 || viewportWidth <= 0 || viewportHeight <= 0) {
      return null;
    }

    const cameraRight = new THREE.Vector3(1, 0, 0)
      .applyQuaternion(pickCamera.quaternion)
      .normalize();
    const axes = sharedViewAxes(tangents, cameraRight);
    const pointerPx = new THREE.Vector2(
      (pointerNdc.x * 0.5 + 0.5) * viewportWidth,
      (-pointerNdc.y * 0.5 + 0.5) * viewportHeight,
    );
    const hitRadiusSq = 30 * 30;
    let bestDistanceSq = Number.POSITIVE_INFINITY;
    let bestPick: CoreTrackPick | null = null;

    for (const binding of locatorBindings) {
      const span = binding.baseMd - binding.topMd;
      if (!Number.isFinite(span) || span <= 0) continue;

      const sampleCount = Math.max(32, Math.min(360, Math.ceil(span / 0.25) + 1));
      let previousMd: number | null = null;
      let previousPx: THREE.Vector2 | null = null;

      for (let index = 0; index < sampleCount; index += 1) {
        const ratio = index / (sampleCount - 1);
        const md = THREE.MathUtils.lerp(binding.topMd, binding.baseMd, ratio);
        const basis = interpolateTrajectoryBasisAtMd(renderPoints, positions, tangents, md);
        if (!basis) continue;

        const axis = axisAtFramePosition(axes, basis.framePosition);
        const world = basis.position.clone().add(axis.multiplyScalar(resolvedCenterOffset));
        const projected = world.project(pickCamera);
        const currentPx = new THREE.Vector2(
          (projected.x * 0.5 + 0.5) * viewportWidth,
          (-projected.y * 0.5 + 0.5) * viewportHeight,
        );

        if (previousMd != null && previousPx) {
          const segment = currentPx.clone().sub(previousPx);
          const lengthSq = segment.lengthSq();
          const fraction = lengthSq <= 1e-9
            ? 0
            : THREE.MathUtils.clamp(
                pointerPx.clone().sub(previousPx).dot(segment) / lengthSq,
                0,
                1,
              );
          const closest = previousPx.clone().add(segment.multiplyScalar(fraction));
          const distanceSq = closest.distanceToSquared(pointerPx);

          if (distanceSq <= hitRadiusSq && distanceSq < bestDistanceSq) {
            bestDistanceSq = distanceSq;
            bestPick = {
              product_id: binding.productId,
              md: THREE.MathUtils.lerp(previousMd, md, fraction),
              top_md: binding.topMd,
              base_md: binding.baseMd,
            };
          }
        }

        previousMd = md;
        previousPx = currentPx;
      }
    }

    return bestPick;
  };

  return { update, setFocusInterval, pick };
}
const krLithologyEntryCache = new Map<string, Promise<WbvKrLithologyEntry>>();
const krLithologySvgDataUrlCache = new Map<string, Promise<string>>();

function cachedKrLithologyEntry(url: string): Promise<WbvKrLithologyEntry> {
  const existing = krLithologyEntryCache.get(url);
  if (existing) return existing;
  const pending = fetch(url, { cache: 'no-store' }).then(async (response) => {
    if (!response.ok) throw new Error(`KR lithology entry request failed (${response.status}) for ${url}`);
    return await response.json() as WbvKrLithologyEntry;
  });
  krLithologyEntryCache.set(url, pending);
  pending.catch(() => krLithologyEntryCache.delete(url));
  return pending;
}

function cachedKrLithologySvgDataUrl(url: string): Promise<string> {
  const existing = krLithologySvgDataUrlCache.get(url);
  if (existing) return existing;
  const pending = fetch(url, { cache: 'no-store' }).then(async (response) => {
    if (!response.ok) throw new Error(`KR lithology SVG request failed (${response.status}) for ${url}`);
    const svg = await response.text();
    if (!/<svg\b/i.test(svg)) throw new Error(`KR lithology pattern response is not SVG for ${url}`);
    return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
  });
  krLithologySvgDataUrlCache.set(url, pending);
  pending.catch(() => krLithologySvgDataUrlCache.delete(url));
  return pending;
}

function applyWorldAspectUvScale(geometry: THREE.TubeGeometry, curveLength: number, radius: number): void {
  const uv = geometry.getAttribute('uv');
  if (!(uv instanceof THREE.BufferAttribute)) return;
  const circumference = Math.max(1e-6, Math.PI * 2 * radius);
  const axialRatio = Math.max(0.25, curveLength / circumference);
  for (let index = 0; index < uv.count; index += 1) uv.setX(index, uv.getX(index) * axialRatio);
  uv.needsUpdate = true;
}

function installExactKrTexture(
  intervalGroup: THREE.Group,
  mesh: THREE.Mesh,
  material: THREE.MeshStandardMaterial | THREE.MeshBasicMaterial,
  interval: WbvLithologyIntervalRenderItem,
  appearance: WbvLithologyAppearance,
): void {
  const entryUrl = interval.kr_entry_url?.trim();
  const patternUrl = interval.kr_pattern_url?.trim();
  if (!entryUrl || !patternUrl || !interval.canonical_lithology) {
    intervalGroup.visible = false;
    mesh.userData.krPatternError = 'missing_canonical_kr_reference';
    console.error('WBV lithology interval withheld: canonical KR render reference missing', interval.interval_id);
    return;
  }

  intervalGroup.visible = false;
  Promise.all([cachedKrLithologyEntry(entryUrl), cachedKrLithologySvgDataUrl(patternUrl)])
    .then(([entry, dataUrl]) => {
      if (mesh.userData.wbvDisposed || intervalGroup.userData.wbvDisposed || intervalGroup.parent?.userData.wbvDisposed) return;
      const canonicalDefaultScale = Number(entry.pattern?.defaultScale);
      if (!Number.isFinite(canonicalDefaultScale) || canonicalDefaultScale <= 0) {
        throw new Error(`KR entry ${interval.canonical_lithology} has no valid pattern.defaultScale`);
      }
      const userPatternScale = THREE.MathUtils.clamp(appearance.patternScale ?? 1.5, 0.75, 4.0);
      const effectivePatternScale = canonicalDefaultScale * userPatternScale;
      const repeats = THREE.MathUtils.clamp(4 / effectivePatternScale, 1, 8);
      const texture = new THREE.TextureLoader().load(
        dataUrl,
        (loadedTexture) => {
          if (mesh.userData.wbvDisposed || intervalGroup.userData.wbvDisposed || intervalGroup.parent?.userData.wbvDisposed) {
            loadedTexture.dispose();
            return;
          }
          loadedTexture.colorSpace = THREE.SRGBColorSpace;
          loadedTexture.wrapS = THREE.RepeatWrapping;
          loadedTexture.wrapT = THREE.RepeatWrapping;
          loadedTexture.repeat.set(repeats, repeats);
          loadedTexture.needsUpdate = true;
          material.map = loadedTexture;
          if (material instanceof THREE.MeshStandardMaterial) {
            material.emissiveMap = loadedTexture;
            material.emissive.set(0xffffff);
            material.emissiveIntensity = THREE.MathUtils.clamp((appearance.brightness ?? 1.35) - 0.65, 0, 2.0);
          }
          material.needsUpdate = true;
          intervalGroup.visible = true;
          mesh.userData.krPatternAsset = entry.pattern?.asset ?? null;
          mesh.userData.krDefaultScale = canonicalDefaultScale;
          mesh.userData.krDefaultBackground = entry.colors?.defaultBackground ?? null;
          mesh.userData.krDefaultPattern = entry.colors?.defaultPattern ?? null;
        },
        undefined,
        (error) => {
          intervalGroup.visible = false;
          mesh.userData.krPatternError = 'texture_decode_failed';
          console.error('WBV lithology interval withheld: KR SVG texture decode failed', interval.interval_id, error);
        },
      );
      texture.colorSpace = THREE.SRGBColorSpace;
      texture.wrapS = THREE.RepeatWrapping;
      texture.wrapT = THREE.RepeatWrapping;
      texture.repeat.set(repeats, repeats);
    })
    .catch((error) => {
      if (mesh.userData.wbvDisposed || intervalGroup.userData.wbvDisposed || intervalGroup.parent?.userData.wbvDisposed) return;
      intervalGroup.visible = false;
      mesh.userData.krPatternError = 'kr_fetch_failed';
      console.error('WBV lithology interval withheld: canonical KR data could not be loaded', interval.interval_id, error);
    });
}

function addLithologyWellboreOverlay(
  group: THREE.Group,
  intervals: WbvLithologyIntervalRenderItem[],
  renderPoints: WbvTrajectoryRenderPoint[],
  positions: THREE.Vector3[],
  tangents: THREE.Vector3[],
  baseRadius: number,
  appearance: WbvLithologyAppearance,
  useSurfaceLighting: boolean,
  managedWellId: string | null | undefined,
) {
  const radius=baseRadius*THREE.MathUtils.clamp(appearance.radiusMultiplier || 1.35,1.0,8.0);
  const opacity=THREE.MathUtils.clamp(appearance.opacity,0.05,1);
  const hideUnderlyingWellbore=appearance.hideUnderlyingWellbore ?? false;
  intervals.forEach((interval)=>{
    if(!Number.isFinite(interval.top_md)||!Number.isFinite(interval.base_md)||interval.base_md<=interval.top_md)return;
    const top=interpolateTrajectoryBasisAtMd(renderPoints,positions,tangents,interval.top_md);
    const base=interpolateTrajectoryBasisAtMd(renderPoints,positions,tangents,interval.base_md);
    if(!top||!base)return;
    const frameSpan=Math.max(1,Math.abs(base.framePosition-top.framePosition));
    const sampleCount=Math.max(4,Math.min(64,Math.ceil(frameSpan*2)));
    const samples:THREE.Vector3[]=[];
    for(let i=0;i<=sampleCount;i+=1){
      const md=THREE.MathUtils.lerp(interval.top_md,interval.base_md,i/sampleCount);
      const basis=interpolateTrajectoryBasisAtMd(renderPoints,positions,tangents,md);
      if(basis)samples.push(basis.position);
    }
    if(samples.length<2)return;
    const curve=new THREE.CatmullRomCurve3(samples,false,"catmullrom",0.02);
    const geometry=new THREE.TubeGeometry(curve,Math.max(12,Math.min(180,samples.length*4)),radius,18,false);
    applyWorldAspectUvScale(geometry, curve.getLength(), radius);
    const effectiveOpacity=hideUnderlyingWellbore ? 1 : opacity;
    const material=useSurfaceLighting
      ? new THREE.MeshStandardMaterial({
          color:0xffffff,
          metalness:0,
          roughness:0.52,
          transparent:effectiveOpacity<0.999,
          opacity:effectiveOpacity,
          depthTest:true,
          depthWrite:hideUnderlyingWellbore || effectiveOpacity>=0.999,
          side:THREE.FrontSide,
        })
      : new THREE.MeshBasicMaterial({
          color:0xffffff,
          transparent:effectiveOpacity<0.999,
          opacity:effectiveOpacity,
          depthTest:true,
          depthWrite:hideUnderlyingWellbore || effectiveOpacity>=0.999,
          side:THREE.FrontSide,
        });
    const intervalGroup = new THREE.Group();
    intervalGroup.name = `wbv-lithology-interval-${interval.interval_id}`;
    intervalGroup.visible = false;
    intervalGroup.userData = {
      kind: "lithology_interval_group",
      managedWellId,
      intervalId: interval.interval_id,
      canonicalLithology: interval.canonical_lithology ?? null,
    };

    const mesh=new THREE.Mesh(geometry,material);
    mesh.renderOrder=32;
    mesh.userData={kind:"lithology_interval",managedWellId,intervalId:interval.interval_id,lithology:interval.lithology,topMd:interval.top_md,baseMd:interval.base_md,patternId:interval.pattern_id??null,canonicalLithology:interval.canonical_lithology??null};
    intervalGroup.add(mesh);

    // Thin dark collars at interval boundaries make adjacent lithologies readable
    // even when their colours are similar and at oblique camera angles.
    const collarMaterial=new THREE.MeshBasicMaterial({
      color:new THREE.Color("#182028"),
      transparent:opacity<1,
      opacity:Math.min(1,opacity*0.9),
      depthTest:true,
      depthWrite:true,
    });
    const collarRadius=radius*1.042;
    const collarThickness=Math.max(baseRadius*0.18, radius*0.04);
    [top,base].forEach((basis,index)=>{
      const tangent=basis.tangent.clone().normalize();
      const geometry=new THREE.CylinderGeometry(collarRadius,collarRadius,collarThickness,18,1,false);
      geometry.rotateX(Math.PI/2);
      const collar=new THREE.Mesh(geometry,collarMaterial.clone());
      collar.position.copy(basis.position);
      collar.quaternion.setFromUnitVectors(new THREE.Vector3(0,0,1),tangent);
      collar.renderOrder=33;
      collar.userData={kind:"lithology_boundary",managedWellId,intervalId:interval.interval_id,boundary:index===0?"top":"base"};
      intervalGroup.add(collar);
    });

    group.add(intervalGroup);
    installExactKrTexture(intervalGroup,mesh,material,interval,appearance);
  });
}


function completionMaterialColor(component: WbvCompletionRenderItem, override?: string | null): THREE.Color {
  if (override) return new THREE.Color(override);
  switch (component.canonical_id) {
    case 'completion.perforations': return new THREE.Color('#ffb15c');
    case 'completion.cement_barrier': return new THREE.Color('#9b9a91');
    case 'completion.open_hole': return new THREE.Color('#65594c');
    case 'completion.packer':
    case 'completion.bridge_plug':
    case 'completion.retainer': return new THREE.Color('#30363c');
    case 'completion.safety_valve': return new THREE.Color('#aab5bb');
    case 'completion.downhole_valve': return new THREE.Color('#aab5bb');
    case 'completion.sliding_sleeve': return new THREE.Color('#aab5bb');
    case 'completion.gas_lift': return new THREE.Color('#aab5bb');
    case 'completion.icd_aicd': return new THREE.Color('#4b3a2d');
    case 'completion.screen': return new THREE.Color('#89979e');
    case 'completion.casing':
    case 'completion.liner': return new THREE.Color('#aab5bb');
    case 'completion.tubing': return new THREE.Color('#d8e1e5');
    default: return new THREE.Color('#aab5bb');
  }
}

type WbvTrajectoryMetallicTone = 'light_silver' | 'silver' | 'steel' | 'gunmetal' | 'graphite';

const WBV_TRAJECTORY_METALLIC_TONES: Record<WbvTrajectoryMetallicTone, string> = {
  light_silver: '#eef2f4',
  silver: '#d8e1e5',
  steel: '#aab5bb',
  gunmetal: '#707980',
  graphite: '#454b50',
};

function wbvTrajectoryMetallicColor(tone: WbvTrajectoryMetallicTone = 'silver'): string {
  return WBV_TRAJECTORY_METALLIC_TONES[tone] ?? WBV_TRAJECTORY_METALLIC_TONES.silver;
}

function wdvTubingMaterial(
  useSurfaceLighting: boolean,
  opacity = 1,
  metallicTone: WbvTrajectoryMetallicTone = 'silver',
): THREE.Material {
  const color = wbvTrajectoryMetallicColor(metallicTone);
  if (!useSurfaceLighting) return new THREE.MeshBasicMaterial({ color, transparent: opacity < 0.999, opacity });
  const emissive = new THREE.Color(color).multiplyScalar(metallicTone === 'graphite' ? .08 : .16);
  return new THREE.MeshPhysicalMaterial({
    color,
    emissive,
    emissiveIntensity: metallicTone === 'graphite' ? .08 : .12,
    metalness: .36,
    roughness: .30,
    clearcoat: .68,
    clearcoatRoughness: .16,
    reflectivity: .82,
    transparent: opacity < 0.999,
    opacity,
  });
}

function wbvTrajectoryMaterial(
  useSurfaceLighting: boolean,
  opacity: number,
  color: string,
  materialMode: 'color' | 'gray_metallic',
  metallicTone: WbvTrajectoryMetallicTone = 'silver',
): THREE.Material {
  if (materialMode === 'gray_metallic') return wdvTubingMaterial(useSurfaceLighting, opacity, metallicTone);
  if (!useSurfaceLighting) return new THREE.MeshBasicMaterial({ color, transparent: opacity < 0.999, opacity });
  return new THREE.MeshPhysicalMaterial({
    color,
    emissive: new THREE.Color(color).multiplyScalar(.12),
    emissiveIntensity: .10,
    metalness: .28,
    roughness: .34,
    clearcoat: .54,
    clearcoatRoughness: .18,
    reflectivity: .68,
    transparent: opacity < 0.999,
    opacity,
  });
}

function wdvBrushedMaterial(useSurfaceLighting: boolean, opacity = 1): THREE.Material {
  if (!useSurfaceLighting) return new THREE.MeshBasicMaterial({ color: 0xc5cdd1, transparent: opacity < 0.999, opacity });
  return new THREE.MeshPhysicalMaterial({
    color: 0xc5cdd1,
    emissive: 0x566066,
    emissiveIntensity: .05,
    metalness: .48,
    roughness: .34,
    clearcoat: .36,
    clearcoatRoughness: .24,
    reflectivity: .72,
    transparent: opacity < 0.999,
    opacity,
  });
}

function wdvDarkMetalMaterial(useSurfaceLighting: boolean, opacity = 1): THREE.Material {
  if (!useSurfaceLighting) return new THREE.MeshBasicMaterial({ color: 0x655244, transparent: opacity < 0.999, opacity });
  return new THREE.MeshStandardMaterial({ color: 0x655244, emissive: 0x20160f, emissiveIntensity: .04, metalness: .42, roughness: .46, transparent: opacity < 0.999, opacity });
}

function wdvBronzeMaterial(useSurfaceLighting: boolean, opacity = 1): THREE.Material {
  if (!useSurfaceLighting) return new THREE.MeshBasicMaterial({ color: 0x9b6b32, transparent: opacity < 0.999, opacity });
  return new THREE.MeshPhysicalMaterial({
    color: 0x9b6b32,
    metalness: .88,
    roughness: .23,
    clearcoat: .3,
    clearcoatRoughness: .25,
    transparent: opacity < 0.999,
    opacity,
  });
}

function completionSurfaceMaterial(component: WbvCompletionRenderItem, useSurfaceLighting: boolean, opacity: number, override?: string | null): THREE.Material {
  const color = completionMaterialColor(component, override);
  if (!useSurfaceLighting) return new THREE.MeshBasicMaterial({ color, transparent: opacity < 0.999, opacity, side: THREE.DoubleSide });
  if (component.canonical_id === 'completion.perforations') {
    return new THREE.MeshStandardMaterial({
      color,
      emissive: color.clone().multiplyScalar(.32),
      emissiveIntensity: .85,
      metalness: .24,
      roughness: .35,
      transparent: opacity < .999,
      opacity,
    });
  }
  if (component.canonical_id === 'completion.cement_barrier') {
    return new THREE.MeshPhysicalMaterial({ color, metalness: 0, roughness: .96, transparent: true, opacity: Math.min(.58, opacity), side: THREE.DoubleSide, depthWrite: false });
  }
  if (component.canonical_id === 'completion.open_hole') {
    return new THREE.MeshStandardMaterial({ color, metalness: 0, roughness: 1, transparent: true, opacity: Math.min(.34, opacity), side: THREE.BackSide, depthWrite: false });
  }
  if (component.canonical_id === 'completion.tubing') return wdvTubingMaterial(useSurfaceLighting, opacity);
  if (component.canonical_id === 'completion.packer' || component.canonical_id === 'completion.bridge_plug' || component.canonical_id === 'completion.retainer' || component.canonical_id === 'completion.icd_aicd') return wdvDarkMetalMaterial(useSurfaceLighting, opacity);
  return wdvBrushedMaterial(useSurfaceLighting, opacity);
}

function completionLocalFrame(tangent: THREE.Vector3): { normal: THREE.Vector3; binormal: THREE.Vector3 } {
  const t = tangent.clone().normalize();
  const reference = Math.abs(t.dot(new THREE.Vector3(0, 1, 0))) > .88 ? new THREE.Vector3(1, 0, 0) : new THREE.Vector3(0, 1, 0);
  const normal = new THREE.Vector3().crossVectors(t, reference).normalize();
  const binormal = new THREE.Vector3().crossVectors(t, normal).normalize();
  return { normal, binormal };
}


function sanitizeCompletionLabel(label: string): string {
  return label
    .replace(/â€“|â€”|â€‘|â€’|â€"|â€³|â€¹|â€º|â€š|â€ž|â€¢|â€¦|â€|â€/g, '–')
    .replace(/\s+[âÃ].*$/g, '')
    .replace(/\s+–\s+–/g, ' – ')
    .replace(/\s{2,}/g, ' ')
    .replace(/\s+[–-]$/g, '')
    .trim();
}

function perforationStationCount(intervalLength: number): number {
  if (intervalLength <= 8) return 3;
  if (intervalLength <= 20) return 4;
  if (intervalLength <= 40) return 5;
  return 6;
}

type CompletionOccupancyProfile = {
  blocksPerforationHost: boolean;
  axialLengthScale: number;
  radialScale: number;
};

type CompletionOccupancyEnvelope = {
  componentId: string;
  canonicalId: string;
  center: THREE.Vector3;
  tangent: THREE.Vector3;
  axialHalfLength: number;
  radialRadius: number;
};

const COMPLETION_OCCUPANCY_PROFILES: Record<string, CompletionOccupancyProfile> = {
  'completion.retainer': { blocksPerforationHost: true, axialLengthScale: .96, radialScale: 1.29 },
  'completion.cement_barrier': { blocksPerforationHost: true, axialLengthScale: .98, radialScale: 1.40 },
  'completion.packer': { blocksPerforationHost: true, axialLengthScale: 1.00, radialScale: 1.48 },
  'completion.bridge_plug': { blocksPerforationHost: true, axialLengthScale: 1.00, radialScale: 1.34 },
  'completion.icd_aicd': { blocksPerforationHost: true, axialLengthScale: 1.00, radialScale: 1.24 },
  'completion.downhole_valve': { blocksPerforationHost: true, axialLengthScale: 1.00, radialScale: 1.34 },
  'completion.safety_valve': { blocksPerforationHost: true, axialLengthScale: 1.00, radialScale: 1.34 },
  'completion.sliding_sleeve': { blocksPerforationHost: true, axialLengthScale: 1.00, radialScale: 1.28 },
  'completion.gas_lift': { blocksPerforationHost: true, axialLengthScale: 1.00, radialScale: 1.30 },
};

function completionOccupancyProfile(canonicalId: string): CompletionOccupancyProfile | null {
  return COMPLETION_OCCUPANCY_PROFILES[canonicalId] ?? null;
}

function buildCompletionOccupancyEnvelopes(
  components: WbvCompletionRenderItem[],
  renderPoints: WbvTrajectoryRenderPoint[],
  positions: THREE.Vector3[],
  tangents: THREE.Vector3[],
  pointBodyLength: number,
  baseRadius: number,
  stackOffsets: Map<string, number>,
): CompletionOccupancyEnvelope[] {
  const envelopes: CompletionOccupancyEnvelope[] = [];
  components.forEach((component) => {
    const profile = completionOccupancyProfile(component.canonical_id);
    if (!profile?.blocksPerforationHost || !component.component_id || !Number.isFinite(component.top_md)) return;
    const hasInterval = component.base_md != null && Number.isFinite(component.base_md) && component.base_md > component.top_md;
    if (hasInterval) return;
    const basis = interpolateTrajectoryBasisAtMd(renderPoints, positions, tangents, component.top_md);
    if (!basis) return;
    const tangent = basis.tangent.clone().normalize();
    const center = basis.position.clone().add(tangent.clone().multiplyScalar(stackOffsets.get(component.component_id) ?? 0));
    envelopes.push({
      componentId: component.component_id,
      canonicalId: component.canonical_id,
      center,
      tangent,
      axialHalfLength: pointBodyLength * profile.axialLengthScale * .5,
      radialRadius: baseRadius * profile.radialScale,
    });
  });
  return envelopes;
}

function pointInsideCompletionEnvelope(
  point: THREE.Vector3,
  envelope: CompletionOccupancyEnvelope,
  axialClearance: number,
  radialClearance: number,
): boolean {
  const delta = point.clone().sub(envelope.center);
  const axialDistance = Math.abs(delta.dot(envelope.tangent));
  if (axialDistance > envelope.axialHalfLength + axialClearance) return false;
  const radialVector = delta.sub(envelope.tangent.clone().multiplyScalar(delta.dot(envelope.tangent)));
  return radialVector.length() <= envelope.radialRadius + radialClearance;
}

function perforationHostIsExposed(
  md: number,
  renderPoints: WbvTrajectoryRenderPoint[],
  positions: THREE.Vector3[],
  tangents: THREE.Vector3[],
  envelopes: CompletionOccupancyEnvelope[],
  baseRadius: number,
): boolean {
  const basis = interpolateTrajectoryBasisAtMd(renderPoints, positions, tangents, md);
  if (!basis) return false;
  const axialClearance = baseRadius * .30;
  const radialClearance = baseRadius * .04;
  return !envelopes.some((envelope) => pointInsideCompletionEnvelope(basis.position, envelope, axialClearance, radialClearance));
}

function nearestExposedPerforationMd(
  rawMd: number,
  intervalTopMd: number,
  intervalBaseMd: number,
  renderPoints: WbvTrajectoryRenderPoint[],
  positions: THREE.Vector3[],
  tangents: THREE.Vector3[],
  envelopes: CompletionOccupancyEnvelope[],
  baseRadius: number,
): number | null {
  const clamped = THREE.MathUtils.clamp(rawMd, intervalTopMd, intervalBaseMd);
  if (perforationHostIsExposed(clamped, renderPoints, positions, tangents, envelopes, baseRadius)) return clamped;
  const intervalLength = intervalBaseMd - intervalTopMd;
  if (!(intervalLength > 0)) return null;
  const step = Math.max(.10, Math.min(.50, intervalLength / 80));
  const maxSteps = Math.ceil(intervalLength / step) + 2;
  for (let index = 1; index <= maxSteps; index += 1) {
    const offset = index * step;
    const lower = clamped - offset;
    const upper = clamped + offset;
    if (lower >= intervalTopMd && perforationHostIsExposed(lower, renderPoints, positions, tangents, envelopes, baseRadius)) return lower;
    if (upper <= intervalBaseMd && perforationHostIsExposed(upper, renderPoints, positions, tangents, envelopes, baseRadius)) return upper;
    if (lower < intervalTopMd && upper > intervalBaseMd) break;
  }
  return null;
}

function distributePerforationStations(
  intervalTopMd: number,
  intervalBaseMd: number,
  requestedCount: number,
  renderPoints: WbvTrajectoryRenderPoint[],
  positions: THREE.Vector3[],
  tangents: THREE.Vector3[],
  envelopes: CompletionOccupancyEnvelope[],
  baseRadius: number,
): number[] {
  const intervalLength = intervalBaseMd - intervalTopMd;
  if (!(intervalLength > 0) || requestedCount <= 0) return [];
  const resolved: number[] = [];
  const minimumGap = Math.max(.75, intervalLength / Math.max(requestedCount * 2, 6));
  for (let index = 0; index < requestedCount; index += 1) {
    const ratio = requestedCount <= 1 ? .5 : index / (requestedCount - 1);
    const nominalMd = THREE.MathUtils.lerp(intervalTopMd, intervalBaseMd, ratio);
    const candidateMd = nearestExposedPerforationMd(
      nominalMd,
      intervalTopMd,
      intervalBaseMd,
      renderPoints,
      positions,
      tangents,
      envelopes,
      baseRadius,
    );
    if (candidateMd == null) continue;
    if (resolved.some((existingMd) => Math.abs(existingMd - candidateMd) < minimumGap)) continue;
    resolved.push(candidateMd);
  }
  if (resolved.length === 0) {
    const probeCount = Math.max(24, Math.ceil(intervalLength * 4));
    let longestStart: number | null = null;
    let longestEnd: number | null = null;
    let runStart: number | null = null;
    for (let index = 0; index <= probeCount; index += 1) {
      const md = THREE.MathUtils.lerp(intervalTopMd, intervalBaseMd, index / probeCount);
      const exposed = perforationHostIsExposed(md, renderPoints, positions, tangents, envelopes, baseRadius);
      if (exposed && runStart == null) runStart = md;
      if ((!exposed || index === probeCount) && runStart != null) {
        const runEnd = exposed && index === probeCount ? md : THREE.MathUtils.lerp(intervalTopMd, intervalBaseMd, Math.max(0, index - 1) / probeCount);
        if (longestStart == null || longestEnd == null || runEnd - runStart > longestEnd - longestStart) {
          longestStart = runStart;
          longestEnd = runEnd;
        }
        runStart = null;
      }
    }
    if (longestStart != null && longestEnd != null && longestEnd >= longestStart) resolved.push((longestStart + longestEnd) * .5);
  }
  return resolved.sort((first, second) => first - second);
}

function orientCylinderToTangent(mesh: THREE.Object3D, tangent: THREE.Vector3) {
  mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), tangent.clone().normalize());
}

function syntheticTestGlyphDisplayOffsetMd(component: WbvCompletionRenderItem): number {
  const label = String(component.label ?? '').trim();
  // Temporary visual-review spacing only. These offsets do not alter MWD data,
  // source MD labels, or production completion placement.
  const offsets: Record<string, number> = {
    'TEST - Packer': 0,
    'TEST - Safety Valve': 5,
    'TEST - Downhole Valve': 10,
    'TEST - Sliding Sleeve': 15,
    'TEST - Gas Lift': 20,
    'TEST - ICD / AICD': 25,
    'TEST - Bridge Plug': 30,
  };
  return offsets[label] ?? 0;
}

function addCompletionWellboreOverlay(
  group: THREE.Group,
  components: WbvCompletionRenderItem[],
  renderPoints: WbvTrajectoryRenderPoint[],
  positions: THREE.Vector3[],
  tangents: THREE.Vector3[],
  baseRadius: number,
  appearance: WbvCompletionAppearance,
  useSurfaceLighting: boolean,
  managedWellId: string | null | undefined,
  depthUnit?: string | null,
  addHtmlLabel?: (args: {
    text: string;
    color: string;
    opacity: number;
    size: number;
    anchor: THREE.Vector3;
    marker: THREE.Object3D;
    position: "right" | "left" | "above" | "below";
    distance: number;
    kind?: "formation_top" | "completion";
  }) => void,
) {
  const opacity = THREE.MathUtils.clamp(appearance.opacity, .05, 1);
  const scale = THREE.MathUtils.clamp(appearance.sizeMultiplier ?? 1, .5, 4);
  const trajectoryMds = renderPoints.map((point) => point.md).filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
  if (trajectoryMds.length < 2) return;
  const trajectoryMinMd = Math.min(...trajectoryMds);
  const trajectoryMaxMd = Math.max(...trajectoryMds);

  // KR preview proportions are bounded around the metallic body. Keep the 3D
  // symbol envelope tied to the local wellbore radius so it cannot explode with
  // viewport scale or interval length.
  const tubularRadius = baseRadius * (.95 + .08 * scale);
  const casingRadius = baseRadius * (1.42 + .08 * scale);
  const linerRadius = baseRadius * (1.24 + .08 * scale);
  const screenRadius = baseRadius * (1.18 + .08 * scale);
  const pointBodyRadius = baseRadius * (1.08 + .06 * scale);
  const pointBodyLength = baseRadius * (2.55 + .20 * scale);
  const pointOuterRadius = baseRadius * (1.34 + .08 * scale);
  const pointComponentStackOffset = new Map<string, number>();
  const pointComponents = components.filter((candidate) => !(candidate.base_md != null && Number.isFinite(candidate.base_md) && candidate.base_md > candidate.top_md));
  pointComponents.forEach((candidate) => {
    if (!candidate.component_id || pointComponentStackOffset.has(candidate.component_id)) return;
    const siblings = pointComponents
      .filter((entry) => Number.isFinite(entry.top_md) && Math.abs(entry.top_md - candidate.top_md) < .35)
      .sort((first, second) => String(first.canonical_id).localeCompare(String(second.canonical_id)) || String(first.component_id).localeCompare(String(second.component_id)));
    const index = siblings.findIndex((entry) => entry.component_id === candidate.component_id);
    if (index >= 0) pointComponentStackOffset.set(candidate.component_id, (index - (siblings.length - 1) / 2) * pointBodyLength * 1.16);
  });
  const completionOccupancyEnvelopes = buildCompletionOccupancyEnvelopes(
    pointComponents,
    renderPoints,
    positions,
    tangents,
    pointBodyLength,
    baseRadius,
    pointComponentStackOffset,
  );

  const labelText = (component: WbvCompletionRenderItem): string => {
    const mode = appearance.labelMode ?? 'name_md';
    const unitSuffix = depthUnit ? ` ${depthUnit}` : '';
    const mdText = component.base_md != null && Number.isFinite(component.base_md) && component.base_md > component.top_md
      ? `${component.top_md.toLocaleString(undefined,{maximumFractionDigits:1})}–${component.base_md.toLocaleString(undefined,{maximumFractionDigits:1})}${unitSuffix} MD`
      : `${component.top_md.toLocaleString(undefined,{maximumFractionDigits:1})}${unitSuffix} MD`;
    const tvdValue = interpolateTrajectoryScalarAtMd(renderPoints, component.top_md, (point) => point.tvd ?? null);
    const tvdText = typeof tvdValue === 'number' && Number.isFinite(tvdValue)
      ? `${tvdValue.toLocaleString(undefined,{maximumFractionDigits:1})}${unitSuffix} TVD`
      : '';
    return mode === 'name'
      ? sanitizeCompletionLabel(component.label)
      : mode === 'name_tvd'
        ? `${sanitizeCompletionLabel(component.label)}${tvdText ? ` · ${tvdText}` : ''}`
        : mode === 'name_md_tvd'
          ? `${sanitizeCompletionLabel(component.label)} · ${mdText}${tvdText ? ` / ${tvdText}` : ''}`
          : `${sanitizeCompletionLabel(component.label)} · ${mdText}`;
  };

  const addLabel = (component: WbvCompletionRenderItem, marker: THREE.Object3D, anchor: THREE.Vector3) => {
    if (!appearance.showLabels) return;
    addHtmlLabel?.({
      text: labelText(component),
      color: appearance.labelColor ?? '#dce7ef',
      opacity,
      size: appearance.labelSize ?? 1,
      anchor,
      marker,
      position: appearance.labelPosition ?? 'right',
      distance: appearance.labelOffset ?? 1,
      kind: 'completion',
    });
  };

  const addIntervalTube = (component: WbvCompletionRenderItem, topMd: number, baseMd: number, radius: number, radialSegments = 24, renderOrder = 38) => {
    const samples: THREE.Vector3[] = [];
    const sampleCount = Math.max(8, Math.min(160, Math.ceil((baseMd - topMd) / 2) + 1));
    for (let index = 0; index < sampleCount; index += 1) {
      const md = THREE.MathUtils.lerp(topMd, baseMd, index / Math.max(1, sampleCount - 1));
      const basis = interpolateTrajectoryBasisAtMd(renderPoints, positions, tangents, md);
      if (basis) samples.push(basis.position);
    }
    if (samples.length < 2) return null;
    const curve = new THREE.CatmullRomCurve3(samples, false, 'catmullrom', .02);
    const mesh = new THREE.Mesh(
      new THREE.TubeGeometry(curve, Math.max(16, Math.min(260, samples.length * 4)), radius, radialSegments, false),
      completionSurfaceMaterial(component, useSurfaceLighting, opacity, appearance.color),
    );
    mesh.renderOrder = renderOrder;
    mesh.userData = { kind: 'completion_component', managedWellId, componentId: component.component_id, canonicalId: component.canonical_id, topMd, baseMd };
    group.add(mesh);
    const midpoint = interpolateTrajectoryBasisAtMd(renderPoints, positions, tangents, (topMd + baseMd) * .5);
    if (midpoint && (component.canonical_id === 'completion.tubing' || component.canonical_id === 'completion.screen')) {
      // TubeGeometry vertices are already expressed in world coordinates while
      // the mesh itself remains at the scene origin. Completion HTML labels use
      // marker.getWorldPosition(), so using the interval mesh as the label marker
      // incorrectly anchors the label at the origin. Use a midpoint proxy for the
      // two synthetic review intervals that require explicit labels.
      const labelProxy = new THREE.Object3D();
      labelProxy.position.copy(midpoint.position);
      group.add(labelProxy);
      addLabel(component, labelProxy, midpoint.position);
    }
    return mesh;
  };

  components.forEach((component) => {
    if (!Number.isFinite(component.top_md) || component.top_md < trajectoryMinMd || component.top_md > trajectoryMaxMd) return;
    const requestedBaseMd = component.base_md != null && Number.isFinite(component.base_md) && component.base_md > component.top_md ? component.base_md : null;
    const displayTopMd = requestedBaseMd == null
      ? component.top_md + syntheticTestGlyphDisplayOffsetMd(component)
      : component.top_md;
    const topBasis = interpolateTrajectoryBasisAtMd(renderPoints, positions, tangents, displayTopMd);
    if (!topBasis) return;
    const baseMd = requestedBaseMd == null ? null : Math.min(requestedBaseMd, trajectoryMaxMd);
    const canonicalId = component.canonical_id;

    if (baseMd !== null && canonicalId === 'completion.tubing') {
      addIntervalTube(component, component.top_md, baseMd, tubularRadius, 24, 40);
      return;
    }
    if (baseMd !== null && canonicalId === 'completion.casing') {
      addIntervalTube(component, component.top_md, baseMd, casingRadius, 30, 36);
      return;
    }
    if (baseMd !== null && canonicalId === 'completion.liner') {
      addIntervalTube(component, component.top_md, baseMd, linerRadius, 28, 37);
      return;
    }
    if (baseMd !== null && canonicalId === 'completion.screen') {
      const mesh = addIntervalTube(component, component.top_md, baseMd, screenRadius, 28, 39);
      if (mesh && mesh.material instanceof THREE.MeshPhysicalMaterial) {
        mesh.material.wireframe = true;
        mesh.material.opacity = Math.min(.88, opacity);
        mesh.material.transparent = true;
      }
      return;
    }
    if (baseMd !== null && canonicalId === 'completion.open_hole') {
      addIntervalTube(component, component.top_md, baseMd, baseRadius * 1.62, 20, 30);
      return;
    }
    if (baseMd !== null && canonicalId === 'completion.cement_barrier') {
      const mesh = addIntervalTube(component, component.top_md, baseMd, baseRadius * 1.48, 28, 38);
      if (mesh) {
        [component.top_md, baseMd].forEach((md) => {
          const basis = interpolateTrajectoryBasisAtMd(renderPoints, positions, tangents, md);
          if (!basis) return;
          const rim = new THREE.Mesh(
            new THREE.TorusGeometry(baseRadius * 1.38, baseRadius * .08, 8, 28),
            new THREE.MeshBasicMaterial({ color: 0x81776b, transparent: true, opacity: .34 }),
          );
          rim.position.copy(basis.position);
          rim.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), basis.tangent.clone().normalize());
          rim.renderOrder = 39;
          group.add(rim);
        });
      }
      return;
    }

    if (baseMd !== null && canonicalId === 'completion.perforations') {
      const intervalLength = baseMd - component.top_md;
      const stationCount = perforationStationCount(intervalLength);
      const shotMaterial = new THREE.MeshPhysicalMaterial({
        color: 0x9a4f21,
        emissive: 0x4e1e08,
        emissiveIntensity: .18,
        metalness: .28,
        roughness: .42,
        clearcoat: .10,
        transparent: opacity < .999,
        opacity,
      });
      const shotLength = baseRadius * 2.05;
      const shotThickness = Math.max(baseRadius * .16, .0012);
      const shotDepth = Math.max(baseRadius * .19, .0014);
      const shotAngle = THREE.MathUtils.degToRad(16);
      const relevantOccupancyEnvelopes = completionOccupancyEnvelopes.filter((envelope) => envelope.componentId !== component.component_id);
      const resolvedMds = distributePerforationStations(
        component.top_md,
        baseMd,
        stationCount,
        renderPoints,
        positions,
        tangents,
        relevantOccupancyEnvelopes,
        baseRadius,
      );
      resolvedMds.forEach((md, index) => {
        const basis = interpolateTrajectoryBasisAtMd(renderPoints, positions, tangents, md);
        if (!basis) return;
        const tangent = basis.tangent.clone().normalize();
        const frame = completionLocalFrame(tangent);
        const side = index % 2 === 0 ? -1 : 1;
        const radial = frame.normal.clone().multiplyScalar(side).normalize();
        const direction = radial.clone().multiplyScalar(Math.cos(shotAngle))
          .add(tangent.clone().multiplyScalar(side * Math.sin(shotAngle)))
          .normalize();
        const shot = new THREE.Mesh(
          new THREE.BoxGeometry(shotLength, shotThickness, shotDepth),
          shotMaterial,
        );
        shot.position.copy(basis.position).add(radial.clone().multiplyScalar(baseRadius * .92 + shotLength * .44));
        shot.quaternion.setFromUnitVectors(new THREE.Vector3(1, 0, 0), direction);
        shot.castShadow = true;
        shot.receiveShadow = true;
        shot.renderOrder = 42;
        shot.userData = { kind: 'completion_component', managedWellId, componentId: component.component_id, canonicalId, topMd: component.top_md, baseMd, stationIndex: index };
        group.add(shot);
      });
      const midpoint = interpolateTrajectoryBasisAtMd(renderPoints, positions, tangents, (component.top_md + baseMd) * .5);
      if (midpoint) {
        const proxy = new THREE.Object3D();
        proxy.position.copy(midpoint.position);
        group.add(proxy);
        addLabel(component, proxy, midpoint.position);
      }
      return;
    }

    const tangent = topBasis.tangent.clone().normalize();
    const frame = completionLocalFrame(tangent);
    const bodyMaterial = completionSurfaceMaterial(component, useSurfaceLighting, opacity, appearance.color);
    const brushed = wdvBrushedMaterial(useSurfaceLighting, opacity);
    const dark = wdvDarkMetalMaterial(useSurfaceLighting, opacity);
    const bronze = wdvBronzeMaterial(useSurfaceLighting, opacity);
    const stackOffset = pointComponentStackOffset.get(component.component_id) ?? 0;
    const bodyCenter = topBasis.position.clone().add(tangent.clone().multiplyScalar(stackOffset));
    const body = new THREE.Mesh(new THREE.CylinderGeometry(pointBodyRadius, pointBodyRadius, pointBodyLength, 28), bodyMaterial);
    body.position.copy(bodyCenter);
    orientCylinderToTangent(body, tangent);
    body.renderOrder = 40;
    body.userData = { kind: 'completion_component', managedWellId, componentId: component.component_id, canonicalId, topMd: component.top_md, baseMd: component.base_md ?? null };
    group.add(body);

    if (canonicalId === 'completion.cement_barrier') {
      body.visible = false;
      const cementMaterial = useSurfaceLighting
        ? new THREE.MeshPhysicalMaterial({
            color: 0xbdb3a4,
            metalness: 0,
            roughness: 1,
            clearcoat: 0,
            transparent: true,
            opacity: Math.min(.78, opacity),
            side: THREE.DoubleSide,
            depthWrite: false,
          })
        : new THREE.MeshBasicMaterial({ color: 0xbdb3a4, transparent: true, opacity: Math.min(.78, opacity), side: THREE.DoubleSide, depthWrite: false });
      const cementEdgeMaterial = new THREE.MeshBasicMaterial({ color: 0x978d81, transparent: true, opacity: Math.min(.34, opacity) });
      const barrierHeight = pointBodyLength * .98;
      const baseCementRadius = baseRadius * 1.40;
      const radiusProfile = [.90, 1.01, .95, 1.03, .88];
      const segmentHeight = barrierHeight / radiusProfile.length;
      radiusProfile.forEach((radiusScale, index) => {
        const sleeve = new THREE.Mesh(
          new THREE.CylinderGeometry(baseCementRadius * radiusScale, baseCementRadius * radiusScale, segmentHeight * 1.18, 28, 1, true),
          cementMaterial,
        );
        sleeve.position.copy(bodyCenter).add(tangent.clone().multiplyScalar(-barrierHeight * .5 + segmentHeight * (index + .5)));
        orientCylinderToTangent(sleeve, tangent);
        sleeve.castShadow = true;
        sleeve.receiveShadow = true;
        sleeve.renderOrder = 39;
        sleeve.userData = { kind: 'completion_component', managedWellId, componentId: component.component_id, canonicalId, topMd: component.top_md, baseMd: component.base_md ?? null };
        group.add(sleeve);
      });
      const cementSpeckMaterial = new THREE.MeshBasicMaterial({ color: 0xd8d0c3, transparent: true, opacity: .78 });
      [
        { radial: frame.normal, along: -.28, size: .085 },
        { radial: frame.binormal, along: -.02, size: .10 },
        { radial: frame.normal.clone().negate(), along: .21, size: .075 },
        { radial: frame.binormal.clone().negate(), along: .34, size: .065 },
      ].forEach((entry) => {
        const speck = new THREE.Mesh(new THREE.SphereGeometry(baseRadius * entry.size, 8, 6), cementSpeckMaterial);
        speck.position.copy(bodyCenter)
          .add(entry.radial.clone().multiplyScalar(baseCementRadius * 1.01))
          .add(tangent.clone().multiplyScalar(barrierHeight * entry.along));
        speck.renderOrder = 40;
        group.add(speck);
      });
      [-1, 1].forEach((direction) => {
        const edge = new THREE.Mesh(
          new THREE.TorusGeometry(baseCementRadius * .90, Math.max(baseRadius * .05, .0007), 8, 24),
          cementEdgeMaterial,
        );
        edge.position.copy(bodyCenter).add(tangent.clone().multiplyScalar(direction * barrierHeight * .49));
        edge.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), tangent);
        edge.renderOrder = 40;
        group.add(edge);
      });
      const labelProxy = new THREE.Object3D();
      labelProxy.position.copy(bodyCenter);
      group.add(labelProxy);
      addLabel(component, labelProxy, bodyCenter);
      return;
    }

    const addSleeve = (radius: number, length: number, material: THREE.Material, offset = 0) => {
      const sleeve = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, length, 28), material);
      sleeve.position.copy(bodyCenter).add(tangent.clone().multiplyScalar(offset));
      orientCylinderToTangent(sleeve, tangent);
      sleeve.renderOrder = 41;
      group.add(sleeve);
      return sleeve;
    };

    const addRadialPlate = (width: number, height: number, thickness: number, material: THREE.Material, radial = frame.normal, radialOffset = pointOuterRadius) => {
      const plate = new THREE.Mesh(new THREE.BoxGeometry(width, height, thickness), material);
      plate.position.copy(bodyCenter).add(radial.clone().normalize().multiplyScalar(radialOffset));
      plate.quaternion.copy(body.quaternion);
      plate.renderOrder = 42;
      group.add(plate);
      return plate;
    };

    if (canonicalId === 'completion.packer') {
      body.material = dark;
      const torusTube = baseRadius * .14;
      [-pointBodyLength * .22, pointBodyLength * .22].forEach((offset) => {
        const torus = new THREE.Mesh(new THREE.TorusGeometry(pointOuterRadius, torusTube, 10, 32), dark);
        torus.position.copy(bodyCenter).add(tangent.clone().multiplyScalar(offset));
        torus.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), tangent);
        torus.renderOrder = 42;
        group.add(torus);
      });
    } else if (canonicalId === 'completion.safety_valve') {
      body.material = brushed;
      addSleeve(pointBodyRadius * 1.14, pointBodyLength * .60, brushed);
      const plate = addRadialPlate(baseRadius * 1.02, baseRadius * 1.02, baseRadius * .20, bronze, frame.normal, pointBodyRadius * 1.20);
      plate.rotateZ(Math.PI / 4);
    } else if (canonicalId === 'completion.downhole_valve') {
      body.material = brushed;
      addSleeve(pointBodyRadius * 1.12, pointBodyLength * .56, brushed);
      const crossWidth = baseRadius * 1.08;
      const crossHeight = baseRadius * .16;
      const first = addRadialPlate(crossWidth, crossHeight, baseRadius * .16, dark, frame.normal, pointBodyRadius * 1.20);
      const second = addRadialPlate(crossWidth, crossHeight, baseRadius * .16, dark, frame.normal, pointBodyRadius * 1.20);
      first.rotateZ(Math.PI / 4);
      second.rotateZ(-Math.PI / 4);
    } else if (canonicalId === 'completion.sliding_sleeve') {
      body.material = brushed;
      addSleeve(pointBodyRadius * 1.20, pointBodyLength * .72, brushed);
      [-.34, .34].forEach((ratio) => addSleeve(pointOuterRadius * .98, baseRadius * .11, dark, pointBodyLength * ratio));
      [-1, 1].forEach((side) => addRadialPlate(baseRadius * .52, baseRadius * .18, baseRadius * .15, bronze, frame.normal.clone().multiplyScalar(side), pointBodyRadius * 1.27));
    } else if (canonicalId === 'completion.gas_lift') {
      body.material = brushed;
      addSleeve(pointBodyRadius * 1.12, pointBodyLength * .55, brushed);
      const pod = addRadialPlate(baseRadius * .68, baseRadius * .92, baseRadius * .44, dark, frame.normal, pointBodyRadius * 1.18);
      pod.scale.set(1, 1, 1.20);
      const port = new THREE.Mesh(new THREE.SphereGeometry(baseRadius * .20, 18, 14), bronze);
      port.position.copy(bodyCenter).add(frame.normal.clone().multiplyScalar(pointBodyRadius * 1.52));
      port.renderOrder = 43;
      group.add(port);
    } else if (canonicalId === 'completion.icd_aicd') {
      body.material = dark;
      addSleeve(pointBodyRadius * 1.16, pointBodyLength * .68, dark);
      [-.34, -.11, .11, .34].forEach((ratio) => addSleeve(pointOuterRadius * .98, baseRadius * .13, brushed, pointBodyLength * ratio));
      [-1, 1].forEach((side) => addRadialPlate(baseRadius * .44, baseRadius * .17, baseRadius * .14, bronze, frame.normal.clone().multiplyScalar(side), pointBodyRadius * 1.28));
    } else if (canonicalId === 'completion.bridge_plug') {
      body.material = dark;
      const a = addRadialPlate(baseRadius * .92, baseRadius * .12, baseRadius * .14, dark);
      const b = addRadialPlate(baseRadius * .92, baseRadius * .12, baseRadius * .14, dark);
      a.rotateZ(Math.PI / 4);
      b.rotateZ(-Math.PI / 4);
    } else if (canonicalId === 'completion.retainer') {
      body.visible = false;
      const retainerHeight = pointBodyLength * .96;
      const retainerRadius = baseRadius * 1.20;
      const retainerBody = new THREE.Mesh(
        new THREE.CylinderGeometry(retainerRadius, retainerRadius, retainerHeight, 30),
        bronze,
      );
      retainerBody.position.copy(bodyCenter);
      orientCylinderToTangent(retainerBody, tangent);
      retainerBody.castShadow = true;
      retainerBody.receiveShadow = true;
      retainerBody.renderOrder = 41;
      retainerBody.userData = { kind: 'completion_component', managedWellId, componentId: component.component_id, canonicalId, topMd: component.top_md, baseMd: component.base_md ?? null };
      group.add(retainerBody);
      [-retainerHeight * .30, 0, retainerHeight * .30].forEach((offset) => {
        const collar = new THREE.Mesh(
          new THREE.CylinderGeometry(baseRadius * 1.29, baseRadius * 1.29, baseRadius * .11, 30),
          dark,
        );
        collar.position.copy(bodyCenter).add(tangent.clone().multiplyScalar(offset));
        orientCylinderToTangent(collar, tangent);
        collar.castShadow = true;
        collar.receiveShadow = true;
        collar.renderOrder = 42;
        group.add(collar);
      });
      addLabel(component, retainerBody, bodyCenter);
      return;
    }
    addLabel(component, body, bodyCenter);
  });
}

export function WellboreTrajectoryRenderer({
  renderPoints,
  activeManagedWellId = null,
  contextTrajectories = [],
  onActivateWell,
  boundingBox: _boundingBox,
  depthUnit,
  viewerState,
  viewPreset = 'reset',
  viewCommandId = 0,
  viewAction = null,
  viewActionId = 0,
  horizontalRotationLocked = false,
  verticalRotationLocked = false,
  onZoomPercentChange,
  onCameraViewChange,
  cameraViewRestore = null,
  cameraViewRestoreId = 0,
  onInteractionCommand,
  onLocalSelectedPoint,
  rotationCenterPickArmed = false,
  onRotationCenterEstablished,
  selectedPoint = null,
  selectionMode = "none",
  intervalDraftStart = null,
  savedInterval = null,
  trackValuesAlongWellbore = false,
  showTrajectory = true,
  showBoundingBox = true,
  showDepthLabels = true,
  showSurveyStations = false,
  showGroundPlane = false,
  showBottomGrid = false,
  showTopGrid = false,
  surfaceDatumLabel = null,
  showAxes = false,
  showNorthArrow = true,
  useSurfaceLighting = true,
  curveOverlays = [],
  curveTracks = [],
  depthTracks = [],
  curveTrackSpacing = 0.05,
  showCurveOverlays = true,
  formationTops = [],
  formationTopAppearance,
  showFormationTops = false,
  lithologyIntervals = [],
  lithologyAppearance,
  showLithologyOverlay = false,
  completionComponents = [],
  completionAppearance = { opacity: 1, sizeMultiplier: 1, showLabels: true, labelMode: 'name_md', labelColor: '#dce7ef', labelSize: 1, labelOffset: 1, labelPosition: 'right' },
  showCompletions = false,
  coreChunks = [],
  coreTracks = [],
  coreAppearance,
  showCoreOverlay = false,
  coreInspectionInterval = null,
  coreLocatorFocusInterval = null,
  coreViewMode = false,
  onCoreLocatorPick,
  trackLayoutTracks = [],
  viewProperties,
}: WbvTrajectoryRendererProps) {
  const activeTrackingPointerRef = useRef<{ pointerId: number; clientX: number; clientY: number } | null>(null);
  const interactionLifecycleRef = useRef<{
    ordinaryPointerDown: { pointerId: number; x: number; y: number; moved: boolean } | null;
    trackingPointerId: number | null;
    trackingSessionId: string | null;
    trackingSequence: number;
    trackingStartPending: boolean;
    pendingTrackingObservation: WbvScreenObservationV2 | null;
    trackingStartPromise: Promise<WbvInteractionStateV2 | null> | null;
    trackingUpdatePromise: Promise<void> | null;
    trackingFinishing: boolean;
  }>({
    ordinaryPointerDown: null,
    trackingPointerId: null,
    trackingSessionId: null,
    trackingSequence: 0,
    trackingStartPending: false,
    pendingTrackingObservation: null,
    trackingStartPromise: null,
    trackingUpdatePromise: null,
    trackingFinishing: false,
  });

  const hostRef = useRef<HTMLDivElement | null>(null);
  const compassRoseRef = useRef<HTMLDivElement | null>(null);
  const compassAngleRef = useRef<number | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const formationTopLabelOverlayRef = useRef<HTMLDivElement | null>(null);
  const leaderRef = useRef<HTMLDivElement | null>(null);
  const liveReadoutRef = useRef<HTMLDivElement | null>(null);
  const overviewFocusPathRef = useRef<SVGPathElement | null>(null);
  const overviewRuntimeRef = useRef<OverviewRuntime | null>(null);
  const overviewDisabledRef = useRef(false);
  const overviewDragRef = useRef(false);
  const trackValuesRef = useRef(trackValuesAlongWellbore);
  const onInteractionCommandRef = useRef(onInteractionCommand);
  onInteractionCommandRef.current = onInteractionCommand;
  const onLocalSelectedPointRef = useRef(onLocalSelectedPoint);
  const rotationCenterPickArmedRef = useRef(rotationCenterPickArmed);
  rotationCenterPickArmedRef.current = rotationCenterPickArmed;
  const onRotationCenterEstablishedRef = useRef(onRotationCenterEstablished);
  onRotationCenterEstablishedRef.current = onRotationCenterEstablished;
  const onActivateWellRef = useRef(onActivateWell);
  onActivateWellRef.current = onActivateWell;
  const onZoomPercentChangeRef = useRef(onZoomPercentChange);
  onZoomPercentChangeRef.current = onZoomPercentChange;
  const onCameraViewChangeRef = useRef(onCameraViewChange);
  onCameraViewChangeRef.current = onCameraViewChange;
  onLocalSelectedPointRef.current = onLocalSelectedPoint;
  const selectedPointRef = useRef<WbvTrajectoryRenderPoint | null>(selectedPoint);
  selectedPointRef.current = selectedPoint;
  const selectionModeRef = useRef(selectionMode);
  selectionModeRef.current = selectionMode;
  const intervalDraftStartRef = useRef<WbvTrajectoryRenderPoint | null>(intervalDraftStart);
  intervalDraftStartRef.current = intervalDraftStart;
  const savedIntervalRef = useRef(savedInterval);
  savedIntervalRef.current = savedInterval;
  const coreInspectionIntervalRef = useRef(coreInspectionInterval);
  coreInspectionIntervalRef.current = coreInspectionInterval;
  const coreTrackRuntimeRef = useRef<CoreTrackRuntime | null>(null);
  const coreViewModeRef = useRef(coreViewMode);
  coreViewModeRef.current = coreViewMode;
  const onCoreLocatorPickRef = useRef(onCoreLocatorPick);
  onCoreLocatorPickRef.current = onCoreLocatorPick;
  const [status, setStatus] = useState<RendererStatus>('idle');
  const runtimeRef = useRef<{
    applyPreset: (preset: WbvViewPreset) => void;
    applyViewAction: (action: WbvViewAction) => void;
    applyCameraView: (view: WbvCameraViewState) => void;
    syncInteraction: () => void;
    setHorizontalRotationLock: (locked: boolean) => void;
    setVerticalRotationLock: (locked: boolean) => void;
  } | null>(null);
  const cameraViewRef = useRef<CameraViewSnapshot | null>(null);
  const curveOverlayGroupRef = useRef<THREE.Group | null>(null);
  const depthTrackGroupRef = useRef<THREE.Group | null>(null);

  useEffect(() => {
    trackValuesRef.current = trackValuesAlongWellbore;
  }, [trackValuesAlongWellbore]);

  useEffect(() => {
    if (curveOverlayGroupRef.current) {
      curveOverlayGroupRef.current.visible = showCurveOverlays;
    }
    if (depthTrackGroupRef.current) {
      depthTrackGroupRef.current.visible = showCurveOverlays;
    }
  }, [showCurveOverlays]);

  const scenePoints = useMemo(() => scenePointsFromBackend(renderPoints), [renderPoints]);
  const contextSceneTrajectories = useMemo(() => contextTrajectories.map((trajectory) => ({
    ...trajectory,
    scenePoints: scenePointsFromBackend(trajectory.renderPoints),
  })), [contextTrajectories]);
  const overviewPoints = useMemo(() => {
    try {
      return buildOverviewProjection(createNormalizedPoints(scenePoints));
    } catch (error) {
      console.error('WBV overview projection disabled', error);
      return [];
    }
  }, [scenePoints]);
  const overviewFullPath = useMemo(() => overviewPath(overviewPoints), [overviewPoints]);
  const depthTicks = useMemo(() => representativeTicks(renderPoints, depthUnit), [renderPoints, depthUnit]);
  const coreRenderKey = JSON.stringify({
    visible: showCoreOverlay,
    inspectionInterval: coreInspectionInterval,
    appearance: {
      color: coreAppearance?.color ?? null,
      brightness: coreAppearance?.brightness ?? 1.35,
    },
    tracks: coreTracks.map((track) => ({
      track_uid: track.track_uid,
      visible: track.visible,
      position: track.position,
      distance_from_wellbore: track.distance_from_wellbore,
      width: track.width,
      opacity: track.opacity,
    })),
    chunks: coreChunks.map((chunk) => ({
      product_id: chunk.product_id,
      chunk_id: chunk.chunk_id,
      top_md: chunk.top_md,
      base_md: chunk.base_md,
      pixel_width: chunk.pixel_width,
      pixel_height: chunk.pixel_height,
      image_url: chunk.image_url,
    })),
  });
  const trackPlacementRenderKey = JSON.stringify(trackLayoutTracks.map((track) => ({ track_uid: track.track_uid, track_type: track.track_type, display_order: track.display_order, visible: track.visible, position: track.position, distance_from_wellbore: track.distance_from_wellbore, previous_track_gap: track.previous_track_gap, width: track.width })));

  const lithologyRenderKey = JSON.stringify({
    visible: showLithologyOverlay,
    appearance: lithologyAppearance ?? null,
    intervals: lithologyIntervals.map((interval) => ({
      interval_id: interval.interval_id,
      canonical_lithology: interval.canonical_lithology ?? null,
      top_md: interval.top_md,
      base_md: interval.base_md,
      kr_entry_url: interval.kr_entry_url ?? null,
      kr_pattern_url: interval.kr_pattern_url ?? null,
    })),
  });

  const completionRenderKey = JSON.stringify({
    visible: showCompletions,
    appearance: completionAppearance,
    components: completionComponents.map((component) => ({
      component_id: component.component_id,
      canonical_id: component.canonical_id,
      top_md: component.top_md,
      base_md: component.base_md ?? null,
      geometry_family: component.geometry_family,
      material_family: component.material_family,
    })),
  });

  useEffect(() => {
    const host = hostRef.current;
    const canvas = canvasRef.current;

    runtimeRef.current = null;
    overviewRuntimeRef.current = null;
    overviewDisabledRef.current = false;

    if (!host || !canvas) return undefined;

    if (scenePoints.length < 2) {
      setStatus(scenePoints.length === 0 ? 'empty' : 'error');
      return undefined;
    }

    let renderer: THREE.WebGLRenderer | null = null;
    let controls: OrbitControls | null = null;
    let animationFrame: number | null = null;
    let resizeObserver: ResizeObserver | null = null;

    try {
      const allScenePoints = [scenePoints, ...contextSceneTrajectories.map((entry) => entry.scenePoints)].flat();
      const minX = Math.min(...allScenePoints.map((point) => point.x));
      const maxX = Math.max(...allScenePoints.map((point) => point.x));
      const minY = Math.min(...allScenePoints.map((point) => point.y));
      const maxY = Math.max(...allScenePoints.map((point) => point.y));
      const minZ = Math.min(...allScenePoints.map((point) => point.z));
      const maxZ = Math.max(...allScenePoints.map((point) => point.z));
      const centerX = (minX + maxX) / 2;
      const centerY = (minY + maxY) / 2;
      const centerZ = (minZ + maxZ) / 2;
      const sharedScale = TARGET_WELL_HEIGHT / Math.max(1, Math.abs(maxY - minY));
      const normalizeShared = (points: ScenePoint[]) => points.map((point) => new THREE.Vector3(
        (point.x - centerX) * sharedScale,
        (point.y - centerY) * sharedScale,
        (point.z - centerZ) * sharedScale,
      ));
      const normalizedPoints = normalizeShared(scenePoints);
      const normalizedContextTrajectories = contextSceneTrajectories.map((entry) => ({ ...entry, normalizedPoints: normalizeShared(entry.scenePoints) }));
      const activeMinX = Math.min(...scenePoints.map((point) => point.x));
      const activeMaxX = Math.max(...scenePoints.map((point) => point.x));
      const activeMinY = Math.min(...scenePoints.map((point) => point.y));
      const activeMaxY = Math.max(...scenePoints.map((point) => point.y));
      const activeMinZ = Math.min(...scenePoints.map((point) => point.z));
      const activeMaxZ = Math.max(...scenePoints.map((point) => point.z));
      const activeCenterX = (activeMinX + activeMaxX) / 2;
      const activeCenterY = (activeMinY + activeMaxY) / 2;
      const activeCenterZ = (activeMinZ + activeMaxZ) / 2;
      const activeScale = TARGET_WELL_HEIGHT / Math.max(1, Math.abs(activeMaxY - activeMinY));
      const activeToSharedScale = sharedScale / activeScale;
      const governedTrajectoryTransform = new THREE.Matrix4().makeScale(
        activeToSharedScale,
        activeToSharedScale,
        activeToSharedScale,
      );
      governedTrajectoryTransform.setPosition(
        (activeCenterX - centerX) * sharedScale,
        (activeCenterY - centerY) * sharedScale,
        (activeCenterZ - centerZ) * sharedScale,
      );
      const box = sceneBoxFor(allScenePoints.length > 1 ? normalizeShared(allScenePoints) : normalizedPoints);
      const scene = new THREE.Scene();
      const group = new THREE.Group();
      scene.add(group);

      const camera = new THREE.OrthographicCamera(-5, 5, 5, -5, 0.1, 1000);

      renderer = new THREE.WebGLRenderer({
        canvas,
        antialias: true,
        alpha: true,
        powerPreference: 'high-performance',
      });
      renderer.setClearColor(0x000000, 0);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      renderer.domElement.style.cursor = 'default';

      controls = new OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true;
      controls.dampingFactor = 0.08;
      controls.enableRotate = true;
      controls.enableZoom = true;
      controls.enablePan = true;
      controls.screenSpacePanning = true;
      controls.rotateSpeed = 0.72;
      controls.zoomSpeed = 0.82;
      controls.panSpeed = 0.72;
      controls.minZoom = 0.35;
      controls.maxZoom = 40;
      const inspectionPrimaryPan = coreInspectionInterval !== null;
      controls.enableRotate = !inspectionPrimaryPan;
      controls.mouseButtons = {
        LEFT: inspectionPrimaryPan ? THREE.MOUSE.PAN : THREE.MOUSE.ROTATE,
        MIDDLE: THREE.MOUSE.DOLLY,
        RIGHT: THREE.MOUSE.PAN,
      };
      renderer.domElement.style.cursor = inspectionPrimaryPan ? 'grab' : 'default';
      controls.touches = {
        ONE: THREE.TOUCH.ROTATE,
        TWO: THREE.TOUCH.DOLLY_PAN,
      };
      if (interactionLifecycleRef.current.trackingPointerId !== null) {
        controls.enabled = false;
      }

      let targetZoom = camera.zoom;
      let smoothZoomActive = false;
      const smoothZoomMin = controls.minZoom;
      const smoothZoomMax = controls.maxZoom;

      let horizontalLockActive = false;
      const unlockedMinPolarAngle = 0;
      const unlockedMaxPolarAngle = Math.PI;

      // WBV_ROTATION_CENTER_MODEL_SPACE_AXIS_V1_0_2:
      // With a selected rotation center, Horizontal +/- is a MODEL-SPACE turntable.
      // The camera is stationary. The rendered WBV assembly rotates around the local
      // wellbore tangent passing through the exact selected point.
      let rotationCenterWorld: THREE.Vector3 | null = null;
      let rotationCenterAxisWorld: THREE.Vector3 | null = null;
      let rotationCenterMarker: THREE.Mesh | null = null;

      const clearRotationCenterConstraint = () => {
        rotationCenterWorld = null;
        rotationCenterAxisWorld = null;
        if (rotationCenterMarker) rotationCenterMarker.visible = false;
      };

      const applyHorizontalRotationLock = (locked: boolean) => {
        if (!controls) return;
        horizontalLockActive = locked;
        if (locked) {
          const polar = controls.getPolarAngle();
          controls.minPolarAngle = polar;
          controls.maxPolarAngle = polar;
        } else {
          controls.minPolarAngle = unlockedMinPolarAngle;
          controls.maxPolarAngle = unlockedMaxPolarAngle;
        }
        controls.enableRotate = true;
        controls.update();
      };

      const rotateModelHorizontallyAroundSelectedAxis = (degrees: number) => {
        if (!rotationCenterWorld || !rotationCenterAxisWorld || !Number.isFinite(degrees)) return false;

        const axis = rotationCenterAxisWorld.clone().normalize();
        const pivot = rotationCenterWorld;
        const rotation = new THREE.Quaternion().setFromAxisAngle(axis, THREE.MathUtils.degToRad(degrees));

        // Rotate the complete WBV rendered assembly around the fixed world-space hinge.
        // `group` is parent to the active trajectory and its attached 3D overlays.
        group.position.sub(pivot).applyQuaternion(rotation).add(pivot);
        group.quaternion.premultiply(rotation).normalize();
        group.updateMatrixWorld(true);
        return true;
      };

      const rotateHorizontallyByDegrees = (degrees: number) => {
        if (!controls || !horizontalLockActive || !Number.isFinite(degrees)) return;

        // Active center: camera MUST remain completely unchanged.
        if (rotateModelHorizontallyAroundSelectedAxis(degrees)) return;

        // No active center: retain the established generic camera-horizontal behavior.
        const axis = camera.up.clone().normalize();
        const offset = camera.position.clone().sub(controls.target);
        offset.applyAxisAngle(axis, THREE.MathUtils.degToRad(degrees));
        camera.position.copy(controls.target).add(offset);
        camera.lookAt(controls.target);
        camera.updateMatrixWorld();
        controls.update();
      };

      let verticalLockActive = false;
      let verticalDragPointerId: number | null = null;
      let verticalDragLastY = 0;
      let verticalDragMoved = false;

      const rotateVerticallyByDegrees = (degrees: number) => {
        if (!controls || !verticalLockActive || !Number.isFinite(degrees)) return;
        const axis = new THREE.Vector3(1, 0, 0).applyQuaternion(camera.quaternion).normalize();
        const angle = THREE.MathUtils.degToRad(degrees);
        const offset = camera.position.clone().sub(controls.target);
        offset.applyAxisAngle(axis, angle);
        camera.up.applyAxisAngle(axis, angle).normalize();
        camera.position.copy(controls.target).add(offset);
        camera.lookAt(controls.target);
        camera.updateMatrixWorld();
        controls.update();
      };

      const applyVerticalRotationLock = (locked: boolean) => {
        if (!controls) return;
        verticalLockActive = locked;
        verticalDragPointerId = null;
        verticalDragMoved = false;
        controls.enableRotate = !locked;
        controls.update();
      };

      // Wheel input is accumulated as logarithmic zoom velocity and integrated in the
      // animation loop. This keeps motion continuous even when browser wheel events
      // arrive in uneven bursts.
      let wheelZoomVelocity = 0;
      const wheelZoomDecayMs = 110;
      const wheelZoomImpulseScale = 0.00135 / (wheelZoomDecayMs / 1000);
      const wheelZoomVelocityLimit = 3.2;
      const wheelZoomStopThreshold = 0.0008;

      const handleSmoothWheelZoom = (event: WheelEvent) => {
        if (!controls || !controls.enabled || !controls.enableZoom) return;
        event.preventDefault();
        event.stopImmediatePropagation();

        const normalizedDelta = THREE.MathUtils.clamp(event.deltaY, -240, 240);
        wheelZoomVelocity = THREE.MathUtils.clamp(
          wheelZoomVelocity - normalizedDelta * wheelZoomImpulseScale,
          -wheelZoomVelocityLimit,
          wheelZoomVelocityLimit,
        );
        targetZoom = camera.zoom;
        smoothZoomActive = true;
      };
      renderer.domElement.addEventListener('wheel', handleSmoothWheelZoom, { capture: true, passive: false });

      if (showBoundingBox) {
        const boxObject = createTrajectoryBoundingBox(box);
        boxObject.traverse((child) => {
          const material = (child as THREE.LineSegments).material as THREE.LineBasicMaterial | undefined;
          if (material) { material.color.set(viewProperties?.boundingBox.color ?? '#587080'); material.opacity = viewProperties?.boundingBox.opacity ?? 0.72; material.transparent = true; material.linewidth = viewProperties?.boundingBox.thickness ?? 1; }
        });
        group.add(boxObject);
      }

      if (showGroundPlane) {
        const plane = new THREE.Mesh(
          new THREE.PlaneGeometry(Math.max(3.2, box.maxX - box.minX + 1.2) * (viewProperties?.groundPlane.size ?? 1), Math.max(3.2, box.maxZ - box.minZ + 1.2) * (viewProperties?.groundPlane.size ?? 1)),
          new THREE.MeshStandardMaterial({ color: viewProperties?.groundPlane.color ?? '#182129', transparent: true, opacity: viewProperties?.groundPlane.opacity ?? 0.62, roughness: 0.92 }),
        );
        plane.rotation.x = -Math.PI / 2;
        plane.position.y = box.minY;
        group.add(plane);
      }

      const gridSize = Math.max(3.2, box.maxX - box.minX + 1.2, box.maxZ - box.minZ + 1.2);
      const gridCenterX = (box.minX + box.maxX) / 2;
      const gridCenterZ = (box.minZ + box.maxZ) / 2;

      const zoomScaledTextSprites: THREE.Sprite[] = [];

      if (showBottomGrid) {
        const bottomGrid = new THREE.GridHelper(gridSize, Math.max(2, Math.round(viewProperties?.grids.spacing ?? 12)), viewProperties?.grids.color ?? '#526878', viewProperties?.grids.color ?? '#526878');
        bottomGrid.position.set(gridCenterX, box.minY + 0.002, gridCenterZ);
        group.add(bottomGrid);
      }

      if (showTopGrid) {
        const topGrid = new THREE.GridHelper(gridSize, Math.max(2, Math.round(viewProperties?.grids.spacing ?? 12)), viewProperties?.grids.color ?? '#526878', viewProperties?.grids.color ?? '#526878');
        topGrid.position.set(gridCenterX, box.maxY - 0.002, gridCenterZ);
        group.add(topGrid);

        // WBV_TOP_GRID_3D_TOPSIDE_RIG_V1_0_4: brighter rig + honest datum presentation.
        // WBV_WELL_INFORMATION_DATUM_BINDING_V1_0_1: datum supplied from Well Information metadata.
        const wellheadPoint = normalizedPoints[0];
        const rigScale = Math.max(0.34, Math.min(0.52, gridSize * 0.13));
        const topsideRig = createWbvTopsideRig(rigScale, '#e6fcff');
        topsideRig.position.set(wellheadPoint.x, box.maxY, wellheadPoint.z);
        group.add(topsideRig);

        // WBV_TOPSIDE_RIG_LABEL_WELLHEAD_EXTENSION_V1_0_2:
        // Continue the wellbore to the rig base using the same visible diameter
        // and colour family as the wellbore below, without depending on hidden
        // local renderer variables that are out of scope here.
        const wellheadExtensionHeight = Math.max(0, box.maxY - wellheadPoint.y);
        if (wellheadExtensionHeight > 0.0001) {
          const extensionRadius = 0.008 * (viewProperties?.trajectory.thickness ?? 1);
          const extensionGeometry = new THREE.CylinderGeometry(
            extensionRadius,
            extensionRadius,
            wellheadExtensionHeight,
            8,
            1,
            false,
          );
          const extensionMaterial = new THREE.MeshBasicMaterial({
            color: (viewProperties?.trajectory.materialMode ?? 'color') === 'gray_metallic'
              ? wbvTrajectoryMetallicColor(viewProperties?.trajectory.metallicTone ?? 'silver')
              : (viewProperties?.trajectory.color ?? '#67d599'),
            transparent: true,
            opacity: viewProperties?.trajectory.opacity ?? 0.96,
            depthTest: false,
            depthWrite: false,
          });
          const wellheadExtension = new THREE.Mesh(extensionGeometry, extensionMaterial);
          wellheadExtension.name = 'wbv-topside-wellhead-extension';
          wellheadExtension.visible = showTrajectory;
          wellheadExtension.renderOrder = 35;
          wellheadExtension.position.set(
            wellheadPoint.x,
            wellheadPoint.y + (wellheadExtensionHeight / 2),
            wellheadPoint.z,
          );
          group.add(wellheadExtension);
        }

        const datumLabel = createTextSprite(
          surfaceDatumLabel?.trim() || 'Surface datum unavailable',
          {
            color: '#f4feff',
            background: 'rgba(3, 8, 12, 0.84)',
            scale: 0.225,
            shadowBlur: 14,
            shadowColor: 'rgba(181, 244, 255, 0.82)',
          },
        );
        datumLabel.position.set(
          wellheadPoint.x + rigScale * 0.98,
          box.maxY + rigScale * 0.63,
          wellheadPoint.z + rigScale * 0.24,
        );
        zoomScaledTextSprites.push(datumLabel);
        group.add(datumLabel);
      }

      if (showAxes) {
        const axes = new THREE.AxesHelper(0.82);
        axes.position.set(box.minX, box.minY, box.minZ);
        group.add(axes);
      }

      if (useSurfaceLighting) {
        const shadingIntensity = viewProperties?.shading.intensity ?? 1;
        scene.add(new THREE.HemisphereLight(0xeaf7ff, 0x24303a, (viewProperties?.shading.ambient ?? 1.55) * shadingIntensity));
        const keyLight = new THREE.DirectionalLight(0xffffff, (viewProperties?.shading.directional ?? 3.6) * shadingIntensity);
        keyLight.position.set(3, 5, 4);
        scene.add(keyLight);
        const rimLight = new THREE.DirectionalLight(0x8fd8ff, 1.8 * shadingIntensity);
        rimLight.position.set(-4, 3, -3);
        scene.add(rimLight);
        const warmFill = new THREE.DirectionalLight(0xffd8a8, 0.85 * shadingIntensity);
        warmFill.position.set(2, 2, -4);
        scene.add(warmFill);
      }


      if (showDepthLabels) {
        const depthTickPoints: THREE.Vector3[] = [];
        const tickLength = Math.max(
          0.06,
          Math.min(0.11, Math.abs(box.maxX - box.minX) * 0.06),
        );

        depthTicks.forEach((tick) => {
          const y = sceneYForMeasuredDepth(renderPoints, normalizedPoints, tick.md, tick.pointIndex);
          const label = createTextSprite(`MD ${tick.label}`, {
            color: viewProperties?.depthLabels.color ?? '#b9f3ff',
            background: 'rgba(3, 8, 12, 0.58)',
            scale: 0.18 * (viewProperties?.depthLabels.size ?? 1),
          });
          label.position.set(box.minX - (viewProperties?.depthLabels.offset ?? 0.52), y, box.maxZ + 0.09);
          zoomScaledTextSprites.push(label);
          group.add(label);

          const verticalEdges = [
            { x: box.minX, z: box.maxZ, outwardX: -tickLength },
            { x: box.minX, z: box.minZ, outwardX: -tickLength },
            { x: box.maxX, z: box.maxZ, outwardX: tickLength },
            { x: box.maxX, z: box.minZ, outwardX: tickLength },
          ];

          verticalEdges.forEach((edge) => {
            depthTickPoints.push(
              new THREE.Vector3(edge.x, y, edge.z),
              new THREE.Vector3(edge.x + edge.outwardX, y, edge.z),
            );
          });
        });

        if (depthTickPoints.length > 0) {
          const depthTickGeometry = new THREE.BufferGeometry().setFromPoints(depthTickPoints);
          const depthTickMaterial = new THREE.LineBasicMaterial({
            color: 0x9bc8d6,
            transparent: true,
            opacity: 0.86,
            depthTest: false,
            depthWrite: false,
          });
          const depthTickMarks = new THREE.LineSegments(depthTickGeometry, depthTickMaterial);
          depthTickMarks.renderOrder = 18;
          group.add(depthTickMarks);
        }
      }

      if (showSurveyStations) {
        const stationGroup = new THREE.Group();
        const tangents = trajectoryTangents(normalizedPoints);
        const markerSize = 0.018 * (viewProperties?.surveyStations.size ?? 1);
        const markerColor = viewProperties?.surveyStations.color ?? '#2f9bff';
        const markerOpacity = viewProperties?.surveyStations.opacity ?? 1;
        const markerShape = viewProperties?.surveyStations.shape ?? 'circle';
        const markerOrientation = viewProperties?.surveyStations.orientation ?? 'along';
        normalizedPoints.forEach((position, index) => {
          let geometry: THREE.BufferGeometry;
          if (markerShape === 'circle') geometry = new THREE.RingGeometry(markerSize * 0.58, markerSize, 24);
          else if (markerShape === 'square') geometry = new THREE.PlaneGeometry(markerSize * 1.8, markerSize * 1.8);
          else if (markerShape === 'diamond') { geometry = new THREE.PlaneGeometry(markerSize * 1.65, markerSize * 1.65); geometry.rotateZ(Math.PI / 4); }
          else {
            const shape = new THREE.Shape(); const w=markerSize*0.34, l=markerSize;
            shape.moveTo(-w,-l);shape.lineTo(w,-l);shape.lineTo(w,-w);shape.lineTo(l,-w);shape.lineTo(l,w);shape.lineTo(w,w);shape.lineTo(w,l);shape.lineTo(-w,l);shape.lineTo(-w,w);shape.lineTo(-l,w);shape.lineTo(-l,-w);shape.lineTo(-w,-w);shape.closePath();
            geometry = new THREE.ShapeGeometry(shape);
          }
          const material = new THREE.MeshBasicMaterial({ color: markerColor, transparent: true, opacity: markerOpacity, side: THREE.DoubleSide, depthTest: false, depthWrite: false });
          const marker = new THREE.Mesh(geometry, material);
          marker.position.copy(position);
          const tangent = tangents[index] ?? new THREE.Vector3(0,1,0);
          const normal = markerOrientation === 'across' ? tangent : new THREE.Vector3(0,0,1).cross(tangent).normalize();
          if (normal.lengthSq() < 1e-6) normal.set(1,0,0);
          marker.quaternion.setFromUnitVectors(new THREE.Vector3(0,0,1), normal.normalize());
          marker.renderOrder = 120; stationGroup.add(marker);
        });
        group.add(stationGroup);
      }

      const interpolateOptionalNumber = (
        first: number | null | undefined,
        second: number | null | undefined,
        ratio: number,
      ): number | null => {
        if (typeof first === 'number' && Number.isFinite(first) && typeof second === 'number' && Number.isFinite(second)) {
          return THREE.MathUtils.lerp(first, second, ratio);
        }
        if (typeof first === 'number' && Number.isFinite(first)) return first;
        if (typeof second === 'number' && Number.isFinite(second)) return second;
        return null;
      };

      const interpolateTransientPoint = (
        first: WbvTrajectoryRenderPoint,
        second: WbvTrajectoryRenderPoint,
        ratio: number,
      ): WbvTrajectoryRenderPoint => ({
        ...first,
        station_index: ratio <= 0 ? first.station_index : ratio >= 1 ? second.station_index : undefined,
        md: interpolateOptionalNumber(first.md, second.md, ratio),
        tvd: interpolateOptionalNumber(first.tvd, second.tvd, ratio),
        tvdss: interpolateOptionalNumber(first.tvdss, second.tvdss, ratio),
        inclination: interpolateOptionalNumber(first.inclination, second.inclination, ratio),
        azimuth: interpolateOptionalNumber(first.azimuth, second.azimuth, ratio),
        dogleg_severity: interpolateOptionalNumber(first.dogleg_severity, second.dogleg_severity, ratio),
        east_departure: interpolateOptionalNumber(first.east_departure, second.east_departure, ratio),
        north_departure: interpolateOptionalNumber(first.north_departure, second.north_departure, ratio),
        x: interpolateOptionalNumber(first.x, second.x, ratio),
        y: interpolateOptionalNumber(first.y, second.y, ratio),
        z: interpolateOptionalNumber(first.z, second.z, ratio),
      });

      const selectableWellMeshes: THREE.Object3D[] = [];
      const contextCurveOverlayRuntimes: CurveOverlayRuntime[] = [];
      /*
       * Formation Tops text has one presentation authority only: HTML screen space.
       *
       * The 3D marker/ring remains in Three.js and owns the geological anchor.
       * The label itself is NOT a Three.js object. Each frame we project the immutable
       * anchor to the viewport and position a DOM element in pixels. This eliminates
       * sprite billboard transforms, world-space unprojection, camera-dependent label
       * scaling, and the feedback loop that made label orientation unstable.
       */
      const formationTopLabelOverlay = formationTopLabelOverlayRef.current;
      formationTopLabelOverlay?.replaceChildren();
      const formationTopLabelRuntimes: Array<{
        element: HTMLDivElement;
        anchor: THREE.Vector3;
        marker: THREE.Object3D;
        markerBoundaryPoints: THREE.Vector3[];
        position: "right" | "left" | "above" | "below";
        distance: number;
        kind: "formation_top" | "completion";
      }> = [];

      const formationTopMarkerBoundaryPoints = (marker: THREE.Object3D): THREE.Vector3[] => {
        const geometryHolder = marker as THREE.Object3D & { geometry?: THREE.BufferGeometry };
        const positionAttribute = geometryHolder.geometry?.getAttribute('position');
        if (!(positionAttribute instanceof THREE.BufferAttribute) || positionAttribute.count === 0) {
          return [new THREE.Vector3(0, 0, 0)];
        }
        const points: THREE.Vector3[] = [];
        for (let index = 0; index < positionAttribute.count; index += 1) {
          points.push(new THREE.Vector3(
            positionAttribute.getX(index),
            positionAttribute.getY(index),
            positionAttribute.getZ(index),
          ));
        }
        return points;
      };

      const addFormationTopHtmlLabel = (args: {
        text: string;
        color: string;
        opacity: number;
        size: number;
        anchor: THREE.Vector3;
        marker: THREE.Object3D;
        position: "right" | "left" | "above" | "below";
        distance: number;
        kind?: "formation_top" | "completion";
      }) => {
        if (!formationTopLabelOverlay) return;
        const element = document.createElement('div');
        element.textContent = args.text;
        element.style.position = 'absolute';
        element.style.left = '0px';
        element.style.top = '0px';
        element.style.pointerEvents = 'none';
        element.style.userSelect = 'none';
        element.style.whiteSpace = 'nowrap';
        element.style.fontFamily = 'inherit';
        element.style.fontWeight = '700';
        element.style.fontSize = `${THREE.MathUtils.clamp(13 * args.size, 8, 42)}px`;
        element.style.lineHeight = '1';
        element.style.color = args.color;
        element.style.opacity = `${THREE.MathUtils.clamp(args.opacity, 0, 1)}`;
        element.style.textShadow = '0 0 3px rgba(0,0,0,.95), 0 0 7px rgba(0,0,0,.72)';
        element.style.willChange = 'left, top, transform';
        element.style.transformOrigin = 'center center';
        element.hidden = true;
        formationTopLabelOverlay.appendChild(element);
        formationTopLabelRuntimes.push({
          element,
          anchor: args.anchor.clone(),
          marker: args.marker,
          markerBoundaryPoints: formationTopMarkerBoundaryPoints(args.marker),
          position: args.position,
          distance: args.distance,
          kind: args.kind ?? "formation_top",
        });
      };
      normalizedContextTrajectories.forEach((entry) => {
        if (entry.normalizedPoints.length < 2) return;
        const contextCurve = new THREE.CatmullRomCurve3(entry.normalizedPoints, false, 'catmullrom', 0.02);
        const contextGeometry = new THREE.TubeGeometry(
          contextCurve,
          Math.max(64, Math.min(900, entry.normalizedPoints.length * 5)),
          0.0075 * (entry.thickness ?? 1),
          8,
          false,
        );
        const contextOpacity = THREE.MathUtils.clamp(entry.opacity ?? 1, 0, 1);
        const contextIsTransparent = contextOpacity < 0.999;
        const contextMaterial = wbvTrajectoryMaterial(
          useSurfaceLighting,
          contextOpacity,
          entry.color ?? '#67d599',
          entry.materialMode ?? 'color',
          entry.metallicTone ?? 'silver',
        );
        const contextHideLithologyUnderlay = Boolean(
          entry.showLithologyOverlay &&
          entry.lithologyAppearance?.hideUnderlyingWellbore &&
          (entry.lithologyIntervals?.length ?? 0) > 0
        );
        // Wellbore tubes are physical 3D bodies. They must always participate in
        // depth testing so camera rotation cannot make a farther tube draw through
        // a nearer opaque tube. Opaque tubes also write depth; deliberately
        // transparent tubes retain blending behavior without being treated as solid.
        contextMaterial.depthTest = true;
        contextMaterial.depthWrite = !contextIsTransparent || contextHideLithologyUnderlay;
        const mesh = new THREE.Mesh(contextGeometry, contextMaterial);
        mesh.visible = showTrajectory;
        mesh.renderOrder = 30;
        mesh.userData.managedWellId = entry.managedWellId;
        mesh.userData.wellName = entry.wellName;
        selectableWellMeshes.push(mesh);
        group.add(mesh);

        if (entry.showLithologyOverlay && (entry.lithologyIntervals?.length ?? 0) > 0) {
          const contextDisplayTrajectory = buildUniformCurveDisplayTrajectory(entry.renderPoints,entry.normalizedPoints,contextCurve,interpolateTransientPoint,0.25);
          const contextPositions=contextDisplayTrajectory.map((sample)=>sample.position);
          const contextRenderPoints=contextDisplayTrajectory.map((sample)=>sample.point);
          const contextTangents=trajectoryTangents(contextPositions);
          const lithologyGroup=new THREE.Group();
          lithologyGroup.name=`wbv-lithology-overlay-${entry.managedWellId}`;
          addLithologyWellboreOverlay(lithologyGroup,entry.lithologyIntervals??[],contextRenderPoints,contextPositions,contextTangents,0.0075*(entry.thickness??1),entry.lithologyAppearance??{opacity:0.95,radiusMultiplier:1.2},useSurfaceLighting,entry.managedWellId);
          group.add(lithologyGroup);
        }

        if (entry.showCompletions && (entry.completionComponents?.length ?? 0) > 0) {
          const contextDisplayTrajectory = buildUniformCurveDisplayTrajectory(entry.renderPoints, entry.normalizedPoints, contextCurve, interpolateTransientPoint, 0.25);
          const completionGroup = new THREE.Group();
          completionGroup.name = `wbv-completions-${entry.managedWellId}`;
          addCompletionWellboreOverlay(
            completionGroup,
            entry.completionComponents ?? [],
            contextDisplayTrajectory.map((sample) => sample.point),
            contextDisplayTrajectory.map((sample) => sample.position),
            trajectoryTangents(contextDisplayTrajectory.map((sample) => sample.position)),
            0.0075 * (entry.thickness ?? 1),
            entry.completionAppearance ?? { opacity: 1, sizeMultiplier: 1, showLabels: true, labelMode: 'name_md', labelColor: '#dce7ef', labelSize: 1, labelOffset: 1, labelPosition: 'right' },
            useSurfaceLighting,
            entry.managedWellId,
          );
          group.add(completionGroup);
        }

        if (entry.showFormationTops && (entry.formationTops?.length ?? 0) > 0) {
          const contextDisplayTrajectory = buildUniformCurveDisplayTrajectory(
            entry.renderPoints,
            entry.normalizedPoints,
            contextCurve,
            interpolateTransientPoint,
            0.25,
          );
          const contextDisplayPositions = contextDisplayTrajectory.map((sample) => sample.position);
          const contextDisplayRenderPoints = contextDisplayTrajectory.map((sample) => sample.point);
          const contextDisplayTangents = trajectoryTangents(contextDisplayPositions);
          const formationTopGroup = new THREE.Group();
          formationTopGroup.name = `wbv-formation-tops-${entry.managedWellId}`;

          const appearance = entry.formationTopAppearance ?? { opacity: 1, line_width: 1, show_labels: true };
          const size = 0.042 * (appearance.marker_size ?? 1);
          const formationColor = (name: string, markerType: string) => {
            if ((appearance.color_mode ?? "formation") === "single") return new THREE.Color(appearance.color ?? "#58d39b");
            if ((appearance.color_mode ?? "formation") === "well") return new THREE.Color(entry.color ?? "#67d599");
            if ((appearance.color_mode ?? "formation") === "classification") return new THREE.Color(markerType.toLowerCase().includes("base") ? 0xee6c8a : 0x58d39b);
            return canvasFormationTopColor(name);
          };

          entry.formationTops?.forEach((top) => {
            if (!Number.isFinite(top.md)) return;
            const basis = interpolateTrajectoryBasisAtMd(
              contextDisplayRenderPoints,
              contextDisplayPositions,
              contextDisplayTangents,
              top.md,
            );
            if (!basis) return;

            const color = formationColor(top.name, top.marker_type);
            const style = appearance.marker_style ?? "ring";
            let marker: THREE.Object3D;
            if (style === "disc") {
              marker = new THREE.Mesh(
                new THREE.CircleGeometry(size, 32),
                new THREE.MeshBasicMaterial({ color, transparent:true, opacity:appearance.opacity, side:THREE.DoubleSide, depthTest:true, depthWrite:true }),
              );
            } else if (style === "tick") {
              marker = new THREE.Line(
                new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(-size,0,0),new THREE.Vector3(size,0,0)]),
                new THREE.LineBasicMaterial({ color, transparent:true, opacity:appearance.opacity, depthTest:false, depthWrite:false }),
              );
            } else if (style === "flag") {
              const shape = new THREE.Shape();
              shape.moveTo(0,0);
              shape.lineTo(size*1.8,0);
              shape.lineTo(size*1.8,size*0.8);
              shape.lineTo(size*0.7,size*0.8);
              shape.lineTo(size*0.7,size*1.8);
              shape.lineTo(0,size*1.8);
              shape.closePath();
              marker = new THREE.Mesh(
                new THREE.ShapeGeometry(shape),
                new THREE.MeshBasicMaterial({ color, transparent:true, opacity:appearance.opacity, side:THREE.DoubleSide, depthTest:false, depthWrite:false }),
              );
            } else {
              marker = new THREE.Mesh(
                new THREE.RingGeometry(size*0.62,size,32),
                new THREE.MeshBasicMaterial({ color, transparent:true, opacity:appearance.opacity, side:THREE.DoubleSide, depthTest:true, depthWrite:true }),
              );
            }

            marker.position.copy(basis.position);
            marker.quaternion.setFromUnitVectors(new THREE.Vector3(0,0,1), basis.tangent.clone().normalize());
            marker.renderOrder = 29;
            marker.userData = {
              kind:"formation_top",
              managedWellId:entry.managedWellId,
              topId:top.top_id,
              md:top.md,
              name:top.name,
            };
            formationTopGroup.add(marker);

            if (appearance.show_labels) {
              const mode = appearance.label_mode ?? "name_md";
              const unitSuffix = entry.depthUnit ? ` ${entry.depthUnit}` : "";
              const mdText = `${top.md.toLocaleString(undefined,{maximumFractionDigits:2})}${unitSuffix} MD`;
              const tvdText = typeof top.tvd === "number" && Number.isFinite(top.tvd)
                ? `${top.tvd.toLocaleString(undefined,{maximumFractionDigits:2})}${unitSuffix} TVD`
                : "";
              const labelText = mode === "name"
                ? top.name
                : mode === "name_tvd"
                  ? `${top.name}${tvdText ? ` · ${tvdText}` : ""}`
                  : mode === "name_md_tvd"
                    ? `${top.name} · ${mdText}${tvdText ? ` / ${tvdText}` : ""}`
                    : `${top.name} · ${mdText}`;

              addFormationTopHtmlLabel({
                text: labelText,
                color: `#${color.getHexString()}`,
                opacity: appearance.opacity,
                size: appearance.label_size ?? 1,
                anchor: basis.position,
                marker,
                position: appearance.label_position ?? "right",
                distance: appearance.label_offset ?? 1,
              });
            }
          });

          group.add(formationTopGroup);
        }

        if (entry.showCurveOverlays && (entry.curveOverlays?.length ?? 0) > 0) {
          const contextCurveGroup = new THREE.Group();
          contextCurveGroup.name = `wbv-curve-overlays-${entry.managedWellId}`;
          group.add(contextCurveGroup);
          const contextCurveRuntime = addCurveOverlays(
            contextCurveGroup,
            entry.curveOverlays ?? [],
            entry.renderPoints,
            entry.normalizedPoints,
            entry.curveTracks ?? [],
            entry.curveTrackSpacing ?? 0.05,
            undefined,
          );
          contextCurveOverlayRuntimes.push(contextCurveRuntime);
        }
      });

      const curve = new THREE.CatmullRomCurve3(normalizedPoints, false, 'catmullrom', 0.02);
      const displayTrajectory = buildUniformCurveDisplayTrajectory(
        renderPoints,
        normalizedPoints,
        curve,
        interpolateTransientPoint,
        0.25,
      );
      const displayTrajectoryPositions = displayTrajectory.map((sample) => sample.position);
      const displayTrajectoryRenderPoints = displayTrajectory.map((sample) => sample.point);
      const displayTrajectoryTangents = trajectoryTangents(displayTrajectoryPositions);
      const guideGeometry = new THREE.TubeGeometry(
        curve,
        Math.max(80, Math.min(1200, displayTrajectoryPositions.length)),
        0.008 * (viewProperties?.trajectory.thickness ?? 1),
        8,
        false,
      );
      const configuredTrajectoryOpacity = THREE.MathUtils.clamp(
        viewProperties?.trajectory.opacity ?? 1,
        0,
        1,
      );
      // 0.96 was the legacy default, not an intentional transparency choice.
      // Treat that legacy default as solid while preserving explicitly lower
      // user-selected opacity values as transparent rendering.
      const trajectoryOpacity = Math.abs(configuredTrajectoryOpacity - 0.96) < 0.0001
        ? 1
        : configuredTrajectoryOpacity;
      const trajectoryIsTransparent = trajectoryOpacity < 0.999;
      const guideMaterial = wbvTrajectoryMaterial(
        useSurfaceLighting,
        trajectoryOpacity,
        viewProperties?.trajectory.color ?? '#67d599',
        viewProperties?.trajectory.materialMode ?? 'color',
        viewProperties?.trajectory.metallicTone ?? 'silver',
      );
      const activeHideLithologyUnderlay = Boolean(
        showLithologyOverlay &&
        lithologyAppearance?.hideUnderlyingWellbore &&
        lithologyIntervals.length > 0
      );
      const trajectoryMesh = new THREE.Mesh(guideGeometry, guideMaterial);
      trajectoryMesh.visible = showTrajectory;
      trajectoryMesh.renderOrder = 35;
      // Formation Tops and opaque Lithology sleeves are real 3D geometry. When either
      // requires true occlusion, let the base trajectory participate in the depth buffer.
      // This keeps the well visible outside Lithology coverage while preventing it from
      // bleeding through the opaque KR sleeve inside covered MD intervals.
      guideMaterial.depthTest = true;
      guideMaterial.depthWrite = !trajectoryIsTransparent || activeHideLithologyUnderlay;
      trajectoryMesh.userData.managedWellId = activeManagedWellId;
      selectableWellMeshes.push(trajectoryMesh);
      group.add(trajectoryMesh);

      const lineGeometry = new THREE.BufferGeometry().setFromPoints(displayTrajectoryPositions);
      const lineMaterial = new THREE.LineBasicMaterial({
        color: 0xffffff,
        transparent: true,
        opacity: 0.94,
      });
      const trajectoryLine = new THREE.Line(lineGeometry, lineMaterial);
      trajectoryLine.visible = showTrajectory;
      trajectoryLine.renderOrder = 36;
      // The white trajectory accent must obey the same scene depth buffer as
      // the tube; otherwise the accent line itself can appear through nearer wells.
      lineMaterial.depthTest = true;
      lineMaterial.depthWrite = false;
      group.add(trajectoryLine);

      if (showLithologyOverlay && lithologyIntervals.length > 0) {
        const lithologyGroup=new THREE.Group();
        lithologyGroup.name="wbv-lithology-overlay";
        addLithologyWellboreOverlay(lithologyGroup,lithologyIntervals,displayTrajectoryRenderPoints,displayTrajectoryPositions,displayTrajectoryTangents,0.008*(viewProperties?.trajectory.thickness??1),lithologyAppearance??{opacity:0.95,radiusMultiplier:1.2},useSurfaceLighting,activeManagedWellId);
        group.add(lithologyGroup);
      }

      if (showCompletions && completionComponents.length > 0) {
        const completionGroup = new THREE.Group();
        completionGroup.name = "wbv-completions";
        addCompletionWellboreOverlay(
          completionGroup, completionComponents, displayTrajectoryRenderPoints, displayTrajectoryPositions, displayTrajectoryTangents,
          0.008 * (viewProperties?.trajectory.thickness ?? 1), completionAppearance, useSurfaceLighting, activeManagedWellId, depthUnit, addFormationTopHtmlLabel,
        );
        group.add(completionGroup);
      }

      if (showFormationTops && formationTops.length > 0) {
        const formationTopGroup = new THREE.Group();
        formationTopGroup.name = "wbv-formation-tops";
        const appearance = formationTopAppearance ?? { opacity: 1, line_width: 1, show_labels: true };
        const size = 0.042 * (appearance.marker_size ?? 1);
        const formationColor = (name: string, markerType: string) => {
          if ((appearance.color_mode ?? "formation") === "single") return new THREE.Color(appearance.color ?? "#58d39b");
          if ((appearance.color_mode ?? "formation") === "well") return new THREE.Color(viewProperties?.trajectory.color ?? "#67d599");
          if ((appearance.color_mode ?? "formation") === "classification") return new THREE.Color(markerType.toLowerCase().includes("base") ? 0xee6c8a : 0x58d39b);
          return canvasFormationTopColor(name);
        };
        formationTops.forEach((top) => {
          if (!Number.isFinite(top.md)) return;
          // Use the same display-trajectory samples used by the rendered wellbore so
          // formation-top markers sit on the true visible centerline rather than an adjacent
          // source-station interpolation path.
          const basis = interpolateTrajectoryBasisAtMd(displayTrajectoryRenderPoints, displayTrajectoryPositions, displayTrajectoryTangents, top.md);
          if (!basis) return;
          const color = formationColor(top.name, top.marker_type);
          let marker: THREE.Object3D;
          const style = appearance.marker_style ?? "ring";
          if (style === "disc") {
            marker = new THREE.Mesh(new THREE.CircleGeometry(size, 32), new THREE.MeshBasicMaterial({ color, transparent:true, opacity:appearance.opacity, side:THREE.DoubleSide, depthTest:true, depthWrite:true }));
          } else if (style === "tick") {
            marker = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(-size,0,0),new THREE.Vector3(size,0,0)]), new THREE.LineBasicMaterial({ color, transparent:true, opacity:appearance.opacity, depthTest:false, depthWrite:false }));
          } else if (style === "flag") {
            const shape = new THREE.Shape(); shape.moveTo(0,0); shape.lineTo(size*1.8,0); shape.lineTo(size*1.8,size*0.8); shape.lineTo(size*0.7,size*0.8); shape.lineTo(size*0.7,size*1.8); shape.lineTo(0,size*1.8); shape.closePath();
            marker = new THREE.Mesh(new THREE.ShapeGeometry(shape), new THREE.MeshBasicMaterial({ color, transparent:true, opacity:appearance.opacity, side:THREE.DoubleSide, depthTest:false, depthWrite:false }));
          } else {
            marker = new THREE.Mesh(new THREE.RingGeometry(size*0.62,size,32), new THREE.MeshBasicMaterial({ color, transparent:true, opacity:appearance.opacity, side:THREE.DoubleSide, depthTest:true, depthWrite:true }));
          }
          marker.position.copy(basis.position);
          marker.quaternion.setFromUnitVectors(new THREE.Vector3(0,0,1), basis.tangent.clone().normalize());
          // Ring/Disc geometry is centered on the same trajectory point as the wellbore.
          // Depth testing, rather than forced front/back ordering, resolves their intersection.
          marker.renderOrder = 34;
          marker.userData = { kind:"formation_top", topId:top.top_id, md:top.md, name:top.name };
          formationTopGroup.add(marker);

          if (appearance.show_labels) {
            const mode = appearance.label_mode ?? "name_md";
            const unitSuffix = depthUnit ? ` ${depthUnit}` : "";
            const mdText = `${top.md.toLocaleString(undefined,{maximumFractionDigits:2})}${unitSuffix} MD`;
            const tvdText = typeof top.tvd === "number" && Number.isFinite(top.tvd) ? `${top.tvd.toLocaleString(undefined,{maximumFractionDigits:2})}${unitSuffix} TVD` : "";
            const labelText = mode === "name" ? top.name : mode === "name_tvd" ? `${top.name}${tvdText ? ` · ${tvdText}` : ""}` : mode === "name_md_tvd" ? `${top.name} · ${mdText}${tvdText ? ` / ${tvdText}` : ""}` : `${top.name} · ${mdText}`;
            addFormationTopHtmlLabel({
              text: labelText,
              color: `#${color.getHexString()}`,
              opacity: appearance.opacity,
              size: appearance.label_size ?? 1,
              anchor: basis.position,
              marker,
              position: appearance.label_position ?? "right",
              distance: appearance.label_offset ?? 1,
            });
          }
        });
        group.add(formationTopGroup);
      }

      // Depth tracks keep their established scene placement, but share the
      // Curve Overlays visibility state with rendered curve traces.
      const resolvedTrackPlacements = resolveTrackLayoutPlacements(trackLayoutTracks, 0.008);

      const depthTrackGroup = new THREE.Group();
      depthTrackGroup.visible = showCurveOverlays;
      depthTrackGroupRef.current = depthTrackGroup;
      group.add(depthTrackGroup);
      const depthTrackRuntime = addDepthTracks(
        depthTrackGroup,
        depthTracks,
        renderPoints,
        normalizedPoints,
        depthUnit,
        viewProperties,
        resolvedTrackPlacements,
      );

      const coreTrackGroup = new THREE.Group();
      coreTrackGroup.visible = showCoreOverlay;
      group.add(coreTrackGroup);
      const coreTrackRuntime = addCoreImageTracks(
        coreTrackGroup,
        coreChunks,
        coreTracks,
        renderPoints,
        normalizedPoints,
        coreInspectionInterval,
        coreLocatorFocusInterval,
        coreAppearance,
        resolvedTrackPlacements,
      );
      coreTrackRuntimeRef.current = coreTrackRuntime;

      const curveOverlayGroup = new THREE.Group();
      curveOverlayGroup.visible = showCurveOverlays;
      curveOverlayGroupRef.current = curveOverlayGroup;
      group.add(curveOverlayGroup);
      const curveOverlayRuntime = addCurveOverlays(
        curveOverlayGroup,
        curveOverlays,
        renderPoints,
        normalizedPoints,
        curveTracks,
        curveTrackSpacing,
        resolvedTrackPlacements,
      );

      const createBullseye = () => {
        const canvas = document.createElement('canvas');
        canvas.width = 128;
        canvas.height = 128;
        const context = canvas.getContext('2d');
        if (context) {
          const center = 64;
          context.clearRect(0, 0, 128, 128);
          context.beginPath();
          context.arc(center, center, 43, 0, Math.PI * 2);
          context.fillStyle = 'rgba(4, 8, 11, 0.76)';
          context.fill();
          context.strokeStyle = '#e23232';
          context.lineWidth = 6;
          context.beginPath();
          context.arc(center, center, 38, 0, Math.PI * 2);
          context.stroke();
          context.lineWidth = 5;
          context.beginPath();
          context.arc(center, center, 19, 0, Math.PI * 2);
          context.stroke();
          context.beginPath();
          context.arc(center, center, 5, 0, Math.PI * 2);
          context.fillStyle = '#e23232';
          context.fill();
        }
        const texture = new THREE.CanvasTexture(canvas);
        texture.colorSpace = THREE.SRGBColorSpace;
        texture.needsUpdate = true;
        const material = new THREE.SpriteMaterial({
          map: texture,
          transparent: true,
          depthTest: false,
          depthWrite: false,
          sizeAttenuation: true,
        });
        const marker = new THREE.Sprite(material);
        marker.renderOrder = 200;
        marker.frustumCulled = false;
        marker.visible = false;
        marker.userData.basePosition = new THREE.Vector3();
        marker.userData.targetPosition = new THREE.Vector3();
        marker.scale.setScalar(0.105);
        group.add(marker);
        return marker;
      };
      const createDiagnosticSphere = () => {
        const geometry = new THREE.SphereGeometry(0.0115, 20, 14);
        const material = new THREE.MeshBasicMaterial({
          color: 0xe23232,
          depthTest: false,
          depthWrite: false,
        });
        const marker = new THREE.Mesh(geometry, material);
        marker.renderOrder = 201;
        marker.frustumCulled = false;
        marker.visible = false;
        marker.userData.basePosition = new THREE.Vector3();
        marker.userData.targetPosition = new THREE.Vector3();
        group.add(marker);
        return marker;
      };
      const selectionMarker = createDiagnosticSphere();
      selectionMarker.scale.setScalar(selectionMarkerScaleForZoom(camera.zoom));
      const createRotationCenterMarker = () => {
        const geometry = new THREE.SphereGeometry(0.012, 20, 14);
        const material = new THREE.MeshBasicMaterial({
          color: 0x39d353,
          depthTest: false,
          depthWrite: false,
        });
        const marker = new THREE.Mesh(geometry, material);
        marker.renderOrder = 205;
        marker.frustumCulled = false;
        marker.visible = false;
        group.add(marker);
        return marker;
      };
      rotationCenterMarker = createRotationCenterMarker();
      const intervalStartMarker = createBullseye();
      const intervalEndMarker = createBullseye();

      let intervalHighlight: THREE.Line | null = null;
      let selectedRuntimePoint: WbvTrajectoryRenderPoint | null = null;
      let activeTransientPoint: WbvTrajectoryRenderPoint | null = null;
      let transientContinuity: TransientContinuityController<WbvTrajectoryRenderPoint> | null = null;
      let displayedTransientProjectedDistance: number | null = null;
      let targetTransientProjectedDistance: number | null = null;
      let keyboardTraversalProjectedDistance: number | null = null;
      const keyboardTraversalStepPx = 0.75;
      let cachedLiveReadoutText = '';
      const projectedMarkerPosition = new THREE.Vector3();
      const cameraDirection = new THREE.Vector3();
      const liveOverlayOffsetXPx = 144;
      const liveOverlayOffsetYPx = 0;
      const liveOverlayLeaderLengthPx = 128;
      const liveOverlayReadoutWidthPx = 300;
      let viewportWidth = Math.max(1, host.clientWidth);
      let viewportHeight = Math.max(1, host.clientHeight);
      let lastReadoutLayoutKey = '';
      let lastAppliedZoom = Number.NaN;

      const handleKeyboardTraversal = (event: KeyboardEvent) => {
        if (!event.shiftKey || (event.key !== 'ArrowUp' && event.key !== 'ArrowDown')) return;

        event.preventDefault();
        event.stopPropagation();

        if (!transientContinuity) {
          const stations = projectedTransientStations();
          const selectedPoint =
            activeTransientPoint ??
            selectedRuntimePoint ??
            selectedPointRef.current;
          const selectedMd = selectedPoint?.md;

          if (stations.length < 2 || typeof selectedMd !== 'number' || !Number.isFinite(selectedMd)) {
            return;
          }

          transientContinuity = new TransientContinuityController(
            stations,
            interpolateTransientPoint,
          );

          let cumulativeProjectedDistance = 0;
          let seededProjectedDistance = 0;
          let seeded = false;

          for (let index = 0; index < stations.length - 1; index += 1) {
            const first = stations[index];
            const second = stations[index + 1];
            const segmentProjectedLength = Math.hypot(
              second.screenX - first.screenX,
              second.screenY - first.screenY,
            );
            const firstMd = first.point.md;
            const secondMd = second.point.md;

            if (
              typeof firstMd === 'number' &&
              typeof secondMd === 'number' &&
              selectedMd >= Math.min(firstMd, secondMd) &&
              selectedMd <= Math.max(firstMd, secondMd)
            ) {
              const mdSpan = secondMd - firstMd;
              const ratio =
                Math.abs(mdSpan) > Number.EPSILON
                  ? Math.max(0, Math.min(1, (selectedMd - firstMd) / mdSpan))
                  : 0;
              seededProjectedDistance =
                cumulativeProjectedDistance + segmentProjectedLength * ratio;
              seeded = true;
              break;
            }

            cumulativeProjectedDistance += segmentProjectedLength;
          }

          keyboardTraversalProjectedDistance = seeded
            ? seededProjectedDistance
            : 0;
          displayedTransientProjectedDistance = keyboardTraversalProjectedDistance;
          targetTransientProjectedDistance = keyboardTraversalProjectedDistance;
        }

        const currentDistance =
          keyboardTraversalProjectedDistance ??
          displayedTransientProjectedDistance ??
          targetTransientProjectedDistance ??
          0;
        const direction = event.key === 'ArrowUp' ? 1 : -1;
        keyboardTraversalProjectedDistance = Math.max(
          0,
          currentDistance + direction * keyboardTraversalStepPx,
        );

        const location = transientContinuity.locationAtArc(keyboardTraversalProjectedDistance);
        displayedTransientProjectedDistance = keyboardTraversalProjectedDistance;
        targetTransientProjectedDistance = keyboardTraversalProjectedDistance;
        showTransientLocation(location);
      };

      window.addEventListener('keydown', handleKeyboardTraversal);

      const setMarkerBasePosition = (marker: THREE.Object3D, position: THREE.Vector3) => {
        const basePosition = marker.userData.basePosition as THREE.Vector3;
        const targetPosition = marker.userData.targetPosition as THREE.Vector3;
        targetPosition.copy(position);
        if (!marker.visible || !Number.isFinite(basePosition.x + basePosition.y + basePosition.z)) {
          basePosition.copy(position);
          marker.position.copy(position);
        }
      };

      // One authoritative MD -> scene-position mapping for every selected-point render path.
      // Pointer projection already uses displayTrajectory; rebuilding the marker from the coarse
      // renderPoints/normalizedPoints path produces the observed post-selection "scoot".
      const pointAtMd = (md: number): THREE.Vector3 | null => {
        if (!Number.isFinite(md) || displayTrajectory.length === 0) return null;

        for (let index = 0; index < displayTrajectory.length - 1; index += 1) {
          const first = displayTrajectory[index];
          const second = displayTrajectory[index + 1];
          const firstMd = first.point.md;
          const secondMd = second.point.md;
          if (
            typeof firstMd !== 'number' || !Number.isFinite(firstMd) ||
            typeof secondMd !== 'number' || !Number.isFinite(secondMd)
          ) continue;
          if (md < Math.min(firstMd, secondMd) || md > Math.max(firstMd, secondMd)) continue;
          const ratio = secondMd === firstMd
            ? 0
            : THREE.MathUtils.clamp((md - firstMd) / (secondMd - firstMd), 0, 1);
          return first.position.clone().lerp(second.position, ratio);
        }

        let nearestPosition: THREE.Vector3 | null = null;
        let nearestDistance = Number.POSITIVE_INFINITY;
        for (const sample of displayTrajectory) {
          const sampleMd = sample.point.md;
          if (typeof sampleMd !== 'number' || !Number.isFinite(sampleMd)) continue;
          const distance = Math.abs(sampleMd - md);
          if (distance < nearestDistance) {
            nearestDistance = distance;
            nearestPosition = sample.position;
          }
        }
        return nearestPosition?.clone() ?? null;
      };

      const tangentAtMd = (md: number): THREE.Vector3 | null => {
        if (!Number.isFinite(md) || displayTrajectory.length < 2) return null;

        for (let index = 0; index < displayTrajectory.length - 1; index += 1) {
          const first = displayTrajectory[index];
          const second = displayTrajectory[index + 1];
          const firstMd = first.point.md;
          const secondMd = second.point.md;
          if (
            typeof firstMd !== 'number' || !Number.isFinite(firstMd) ||
            typeof secondMd !== 'number' || !Number.isFinite(secondMd)
          ) continue;
          if (md < Math.min(firstMd, secondMd) || md > Math.max(firstMd, secondMd)) continue;
          const direction = second.position.clone().sub(first.position);
          return direction.lengthSq() > Number.EPSILON ? direction.normalize() : null;
        }

        let nearestIndex = -1;
        let nearestDistance = Number.POSITIVE_INFINITY;
        for (let index = 0; index < displayTrajectory.length; index += 1) {
          const sampleMd = displayTrajectory[index]?.point.md;
          if (typeof sampleMd !== 'number' || !Number.isFinite(sampleMd)) continue;
          const distance = Math.abs(sampleMd - md);
          if (distance < nearestDistance) {
            nearestDistance = distance;
            nearestIndex = index;
          }
        }
        if (nearestIndex < 0) return null;

        const prevIndex = Math.max(0, nearestIndex - 1);
        const nextIndex = Math.min(displayTrajectory.length - 1, nearestIndex + 1);
        if (prevIndex === nextIndex) return null;
        const direction = displayTrajectory[nextIndex].position.clone().sub(displayTrajectory[prevIndex].position);
        return direction.lengthSq() > Number.EPSILON ? direction.normalize() : null;
      };

      const clearIntervalHighlight = () => {
        if (!intervalHighlight) return;
        group.remove(intervalHighlight);
        intervalHighlight.geometry.dispose();
        materialList(intervalHighlight.material).forEach((material) => material.dispose());
        intervalHighlight = null;
      };

      const liveReadoutTextFor = (point: WbvTrajectoryRenderPoint): string => {
        const curveValues = typeof point.md === 'number'
          ? curveOverlays
              .map((curve) => {
                const value = interpolateCurveValueAtMd(curve.samples, point.md as number);
                return value === null ? null : `${curve.display_name} ${value.toPrecision(4)}${curve.unit ? ` ${curve.unit}` : ''}`;
              })
              .filter((value): value is string => value !== null)
          : [];
        return [
          `MD ${formatDepth(point.md, depthUnit)} / TVD ${formatDepth(point.tvd, depthUnit)}`,
          ...curveValues,
        ].join('\n');
      };

      const syncInteraction = () => {
        selectionMarker.visible = false;
        intervalStartMarker.visible = false;
        intervalEndMarker.visible = false;
        selectedRuntimePoint = null;
        cachedLiveReadoutText = '';
        lastReadoutLayoutKey = '';
        clearIntervalHighlight();

        if (selectionModeRef.current === 'point') {
          const point = activeTransientPoint ?? selectedPointRef.current;
          if (point && typeof point.md === 'number' && Number.isFinite(point.md)) {
            const position = pointAtMd(point.md);
            if (position) {
              setMarkerBasePosition(selectionMarker, position);
              selectionMarker.visible = true;
              selectedRuntimePoint = point;
              cachedLiveReadoutText = liveReadoutTextFor(point);
              const readoutElement = liveReadoutRef.current;
              if (readoutElement && readoutElement.textContent !== cachedLiveReadoutText) {
                readoutElement.textContent = cachedLiveReadoutText;
              }
            }
          }
          return;
        }

        if (selectionModeRef.current !== 'interval') return;
        const interval = savedIntervalRef.current;
        const start = interval?.start ?? intervalDraftStartRef.current;
        const end = interval?.end ?? null;
        if (typeof start?.md === 'number') {
          const position = pointAtMd(start.md);
          if (position) {
            setMarkerBasePosition(intervalStartMarker, position);
            intervalStartMarker.visible = true;
          }
        }
        if (typeof end?.md === 'number') {
          const position = pointAtMd(end.md);
          if (position) {
            setMarkerBasePosition(intervalEndMarker, position);
            intervalEndMarker.visible = true;
          }
        }
        if (!interval) return;
        const interior = renderPoints
          .map((point, index) => ({ point, index }))
          .filter(({ point }) => typeof point.md === 'number' && point.md >= interval.top_md && point.md <= interval.base_md)
          .map(({ index }) => normalizedPoints[index]);
        const top = pointAtMd(interval.top_md);
        const base = pointAtMd(interval.base_md);
        const points = [...(top ? [top] : []), ...interior, ...(base ? [base] : [])];
        if (points.length >= 2) {
          intervalHighlight = new THREE.Line(
            new THREE.BufferGeometry().setFromPoints(points),
            new THREE.LineBasicMaterial({ color: 0xe23232, linewidth: 3, depthTest: false, depthWrite: false }),
          );
          intervalHighlight.renderOrder = 88;
          group.add(intervalHighlight);
        }
      };

      const observationFor = (event: PointerEvent): WbvScreenObservationV2 | null => {
        if (!renderer) return null;
        return createWbvScreenObservation(event, renderer.domElement, camera, 20, governedTrajectoryTransform);
      };

      const transientPointerFor = (event: PointerEvent): TransientScreenPoint | null => {
        if (!renderer) return null;
        const rect = renderer.domElement.getBoundingClientRect();
        if (rect.width <= 0 || rect.height <= 0) return null;
        return { x: event.clientX - rect.left, y: event.clientY - rect.top };
      };

      const projectedTransientStations = (): readonly TransientTrajectoryStation<WbvTrajectoryRenderPoint>[] => {
        if (!renderer || displayTrajectory.length < 2) return [];
        const rect = renderer.domElement.getBoundingClientRect();
        return displayTrajectory.map((sample) => {
          const projected = sample.position.clone().project(camera);
          return {
            point: sample.point,
            sceneX: sample.position.x,
            sceneY: sample.position.y,
            sceneZ: sample.position.z,
            screenX: (projected.x * 0.5 + 0.5) * rect.width,
            screenY: (-projected.y * 0.5 + 0.5) * rect.height,
          };
        });
      };

      const showTransientLocation = (
        location: TransientTrajectoryLocation<WbvTrajectoryRenderPoint>,
      ) => {
        activeTransientPoint = location.point;
        selectedRuntimePoint = location.point;
        selectionMarker.position.set(location.sceneX, location.sceneY, location.sceneZ);
        selectionMarker.visible = true;
        cachedLiveReadoutText = liveReadoutTextFor(location.point);
        const readoutElement = liveReadoutRef.current;
        if (readoutElement && readoutElement.textContent !== cachedLiveReadoutText) {
          readoutElement.textContent = cachedLiveReadoutText;
        }
      };

      const startTransientContinuityAtPointer = (pointer: TransientScreenPoint): boolean => {
        const stations = projectedTransientStations();
        if (stations.length < 2) return false;
        const controller = new TransientContinuityController(stations, interpolateTransientPoint);
        const location = controller.start(pointer);
        if (!location) return false;
        transientContinuity = controller;
        displayedTransientProjectedDistance = location.projectedDistance;
        targetTransientProjectedDistance = location.projectedDistance;
        keyboardTraversalProjectedDistance = location.projectedDistance;
        showTransientLocation(location);
        return true;
      };


      const startTransientContinuity = (event: PointerEvent): boolean => {
        const pointer = transientPointerFor(event);
        return pointer ? startTransientContinuityAtPointer(pointer) : false;
      };

      const restoreTransientContinuityFromActivePointer = (): boolean => {
        if (!renderer || interactionLifecycleRef.current.trackingPointerId === null) return false;
        const activePointer = activeTrackingPointerRef.current;
        if (!activePointer || activePointer.pointerId !== interactionLifecycleRef.current.trackingPointerId) return false;
        const rect = renderer.domElement.getBoundingClientRect();
        if (rect.width <= 0 || rect.height <= 0) return false;
        return startTransientContinuityAtPointer({
          x: activePointer.clientX - rect.left,
          y: activePointer.clientY - rect.top,
        });
      };


      const updateTransientContinuity = (event: PointerEvent) => {
        const pointer = transientPointerFor(event);
        if (!pointer) return;
        if (!transientContinuity) {
          startTransientContinuityAtPointer(pointer);
          return;
        }
        const location = transientContinuity.update(pointer);
        targetTransientProjectedDistance = location.projectedDistance;
      };

      // Backend-selected-point updates can reconstruct this renderer while a drag is active.
      // Re-seed the local presentation immediately so visible motion never falls back to
      // backend-response cadence alone.
      restoreTransientContinuityFromActivePointer();

      const clearTransientContinuity = () => {
        transientContinuity?.clear();
        transientContinuity = null;
        displayedTransientProjectedDistance = null;
        targetTransientProjectedDistance = null;
        keyboardTraversalProjectedDistance = null;
        activeTransientPoint = null;
      };

      const interactionLifecycle = interactionLifecycleRef.current;
      let localTrackingPointerId: number | null = null;
      let localTrackingProjection: WbvFrontendSelectedPoint | null = null;
      let localContinuousTracker: WbvContinuousProjectedTracker | null = null;

      const sendCommand = async (command: Parameters<NonNullable<WbvTrajectoryRendererProps['onInteractionCommand']>>[0]) => {
        const handler = onInteractionCommandRef.current;
        return handler ? handler(command) : null;
      };

      const localProjectionFor = (event: PointerEvent): WbvFrontendSelectedPoint | null => {
        const pointer = transientPointerFor(event);
        if (!pointer) return null;
        return projectPointerToWellbore(pointer, projectedTransientStations(), 20);
      };

      const establishRotationCenterFromProjection = (projection: WbvFrontendSelectedPoint): boolean => {
        const point = projection.point as WbvTrajectoryRenderPoint;
        const md = point.md;
        if (typeof md !== 'number' || !Number.isFinite(md)) return false;

        const selectedCenterLocal = new THREE.Vector3(
          projection.sceneX,
          projection.sceneY,
          projection.sceneZ,
        );
        const selectedAxisLocal = tangentAtMd(md);
        if (!selectedAxisLocal) return false;

        group.updateMatrixWorld(true);
        rotationCenterWorld = selectedCenterLocal.clone().applyMatrix4(group.matrixWorld);
        rotationCenterAxisWorld = selectedAxisLocal.clone().transformDirection(group.matrixWorld).normalize();

        if (rotationCenterMarker) {
          rotationCenterMarker.position.copy(selectedCenterLocal);
          rotationCenterMarker.visible = true;
        }

        onRotationCenterEstablishedRef.current?.(point);
        return true;
      };

      const showLocalProjection = (
        projection: WbvFrontendSelectedPoint,
        publishPageState: boolean,
      ): void => {
        localTrackingProjection = projection;
        const point = projection.point as WbvTrajectoryRenderPoint;
        activeTransientPoint = point;
        selectedRuntimePoint = point;
        if (publishPageState) onLocalSelectedPointRef.current?.(point);
        const projectedPosition = new THREE.Vector3(
          projection.sceneX,
          projection.sceneY,
          projection.sceneZ,
        );
        const markerBasePosition = selectionMarker.userData.basePosition as THREE.Vector3;
        const markerTargetPosition = selectionMarker.userData.targetPosition as THREE.Vector3;
        markerBasePosition.copy(projectedPosition);
        markerTargetPosition.copy(projectedPosition);
        selectionMarker.position.copy(projectedPosition);
        selectionMarker.visible = true;
        cachedLiveReadoutText = liveReadoutTextFor(point);
        const readoutElement = liveReadoutRef.current;
        if (readoutElement && readoutElement.textContent !== cachedLiveReadoutText) {
          readoutElement.textContent = cachedLiveReadoutText;
        }
      };

      const exactObservationForProjection = (projection: WbvFrontendSelectedPoint): WbvScreenObservationV2 | null => {
        if (!renderer) return null;
        const rect = renderer.domElement.getBoundingClientRect();
        const synthetic = new PointerEvent('pointerup', {
          pointerId: localTrackingPointerId ?? 1,
          pointerType: 'mouse',
          button: 0,
          buttons: 0,
          clientX: rect.left + projection.screenX,
          clientY: rect.top + projection.screenY,
        });
        return createWbvScreenObservation(synthetic, renderer.domElement, camera, 20, governedTrajectoryTransform);
      };

      const commitLocalProjection = async (projection: WbvFrontendSelectedPoint): Promise<void> => {
        const observation = exactObservationForProjection(projection);
        if (!observation) return;
        await sendCommand({
          kind: 'observe',
          observation,
          sequence: 0,
          exactLocalPoint: projection.point as WbvTrajectoryRenderPoint,
        });
      };

      const beginLocalTracking = (event: PointerEvent): boolean => {
        if (!renderer || selectionModeRef.current !== 'point' || localTrackingPointerId !== null) return false;
        localTrackingPointerId = event.pointerId;
        interactionLifecycle.ordinaryPointerDown = null;
        if (controls) controls.enabled = false;
        try {
          renderer.domElement.setPointerCapture(event.pointerId);
        } catch {
          // Pointer capture can fail if the browser has already transferred ownership;
          // window listeners below still keep the gesture alive.
        }
        renderer.domElement.style.setProperty('cursor', 'default');
        const pointer = transientPointerFor(event);
        const stations = projectedTransientStations();
        localContinuousTracker = pointer ? createContinuousProjectedTracker(pointer, stations, 20) : null;
        const projection = pointer ? projectPointerToWellbore(pointer, stations, 20) : null;
        if (projection) showLocalProjection(projection, false);
        return true;
      };

      const endLocalTracking = async (event: PointerEvent, commit: boolean): Promise<void> => {
        if (!renderer || localTrackingPointerId !== event.pointerId) return;
        const finalPointer = transientPointerFor(event);
        const finalProjection = (finalPointer && localContinuousTracker
          ? localContinuousTracker.update(finalPointer, projectedTransientStations())
          : null) ?? localTrackingProjection;
        if (finalProjection) showLocalProjection(finalProjection, false);
        if (renderer.domElement.hasPointerCapture(event.pointerId)) renderer.domElement.releasePointerCapture(event.pointerId);
        if (controls) controls.enabled = true;
        renderer.domElement.style.setProperty('cursor', 'default');
        localTrackingPointerId = null;
        localTrackingProjection = null;
        localContinuousTracker = null;
        if (commit && finalProjection) {
          onLocalSelectedPointRef.current?.(finalProjection.point as WbvTrajectoryRenderPoint);
          await commitLocalProjection(finalProjection);
        }
        event.preventDefault();
        event.stopPropagation();
      };

      const activateWellAtPointer = (event: PointerEvent): boolean => {
        if (!renderer || selectableWellMeshes.length === 0) return false;
        const rect = renderer.domElement.getBoundingClientRect();
        const pointer = new THREE.Vector2(
          ((event.clientX - rect.left) / rect.width) * 2 - 1,
          -((event.clientY - rect.top) / rect.height) * 2 + 1,
        );
        const raycaster = new THREE.Raycaster();
        raycaster.setFromCamera(pointer, camera);
        const hit = raycaster.intersectObjects(selectableWellMeshes, false)[0];
        const managedWellId = hit?.object.userData.managedWellId as string | null | undefined;
        if (!managedWellId || managedWellId === activeManagedWellId) return false;
        onActivateWellRef.current?.(managedWellId);
        return true;
      };

      const pickCoreLocatorAtPointer = (event: PointerEvent): boolean => {
        if (!renderer || !coreViewModeRef.current || !onCoreLocatorPickRef.current) return false;
        const rect = renderer.domElement.getBoundingClientRect();
        if (rect.width <= 0 || rect.height <= 0) return false;
        const pointer = new THREE.Vector2(
          ((event.clientX - rect.left) / rect.width) * 2 - 1,
          -((event.clientY - rect.top) / rect.height) * 2 + 1,
        );

        const projectedPick = coreTrackRuntime.pick(pointer, rect.width, rect.height);
        if (projectedPick) {
          onCoreLocatorPickRef.current(projectedPick);
          return true;
        }

        const raycaster = new THREE.Raycaster();
        raycaster.setFromCamera(pointer, camera);
        const imageHit = raycaster
          .intersectObjects(coreTrackGroup.children, true)
          .find((candidate) => candidate.object.userData.kind === 'core_image_chunk');
        if (!imageHit) return false;

        const object = imageHit.object;
        const topMd = Number(object.userData.topMd);
        const baseMd = Number(object.userData.baseMd);
        const productId = String(object.userData.productId ?? '');
        if (!Number.isFinite(topMd) || !Number.isFinite(baseMd) || !productId) return false;

        const along = THREE.MathUtils.clamp(1 - (imageHit.uv?.y ?? 0.5), 0, 1);
        onCoreLocatorPickRef.current({
          product_id: productId,
          md: THREE.MathUtils.lerp(topMd, baseMd, along),
          top_md: topMd,
          base_md: baseMd,
        });
        return true;
      };

      const handlePointerDown = (event: PointerEvent) => {
        if (!renderer || event.button !== 0) return;

        if (coreViewModeRef.current) {
          if (pickCoreLocatorAtPointer(event)) {
            interactionLifecycle.ordinaryPointerDown = null;
            event.preventDefault();
            event.stopPropagation();
          }
          return;
        }

        if (inspectionPrimaryPan) {
          renderer.domElement.style.cursor = 'grabbing';
        }
        if (verticalLockActive) {
          verticalDragPointerId = event.pointerId;
          verticalDragLastY = event.clientY;
          verticalDragMoved = false;
          try {
            renderer.domElement.setPointerCapture(event.pointerId);
          } catch {
            // Window-level listeners preserve the drag if pointer capture is unavailable.
          }
        }
        if (activateWellAtPointer(event)) {
          event.preventDefault();
          event.stopPropagation();
          return;
        }
        if (rotationCenterPickArmedRef.current) {
          interactionLifecycle.ordinaryPointerDown = {
            pointerId: event.pointerId,
            x: event.clientX,
            y: event.clientY,
            moved: false,
          };
          event.preventDefault();
          event.stopPropagation();
          return;
        }
        if (selectionModeRef.current === 'none') return;
        if (event.detail >= 2) {
          event.preventDefault();
          event.stopPropagation();
          return;
        }
        const shiftTrackingRequested = event.shiftKey || event.getModifierState?.('Shift') === true;
        if (shiftTrackingRequested && selectionModeRef.current === 'point') {
          if (beginLocalTracking(event)) {
            event.preventDefault();
            event.stopPropagation();
          }
          return;
        }
        interactionLifecycle.ordinaryPointerDown = {
          pointerId: event.pointerId,
          x: event.clientX,
          y: event.clientY,
          moved: false,
        };
      };

      const handlePointerMove = (event: PointerEvent) => {
        if (verticalLockActive && verticalDragPointerId === event.pointerId) {
          const deltaY = event.clientY - verticalDragLastY;
          verticalDragLastY = event.clientY;
          if (Math.abs(deltaY) > 0) {
            verticalDragMoved = true;
            rotateVerticallyByDegrees(deltaY * 0.35);
            const ordinaryPointerDown = interactionLifecycle.ordinaryPointerDown;
            if (ordinaryPointerDown?.pointerId === event.pointerId) ordinaryPointerDown.moved = true;
            event.preventDefault();
            event.stopPropagation();
          }
          return;
        }
        if (localTrackingPointerId === event.pointerId) {
          const pointer = transientPointerFor(event);
          const projection = pointer && localContinuousTracker
            ? localContinuousTracker.update(pointer, projectedTransientStations())
            : null;
          if (projection) showLocalProjection(projection, false);
          event.preventDefault();
          event.stopPropagation();
          return;
        }
        const pointerDown = interactionLifecycle.ordinaryPointerDown;
        if (!pointerDown || pointerDown.pointerId !== event.pointerId) return;
        if (Math.hypot(event.clientX - pointerDown.x, event.clientY - pointerDown.y) > 4) {
          pointerDown.moved = true;
        }
      };

      const handlePointerUp = (event: PointerEvent) => {
        if (inspectionPrimaryPan && renderer) {
          renderer.domElement.style.cursor = 'grab';
        }
        if (verticalDragPointerId === event.pointerId) {
          const moved = verticalDragMoved;
          verticalDragPointerId = null;
          verticalDragMoved = false;
          if (renderer?.domElement.hasPointerCapture(event.pointerId)) {
            renderer.domElement.releasePointerCapture(event.pointerId);
          }
          if (moved) {
            interactionLifecycle.ordinaryPointerDown = null;
            event.preventDefault();
            event.stopPropagation();
            return;
          }
        }
        if (localTrackingPointerId === event.pointerId) {
          void endLocalTracking(event, true);
          return;
        }
        const pointerDown = interactionLifecycle.ordinaryPointerDown;
        interactionLifecycle.ordinaryPointerDown = null;
        if (!pointerDown || pointerDown.pointerId !== event.pointerId || pointerDown.moved) return;

        if (rotationCenterPickArmedRef.current) {
          const projection = localProjectionFor(event);
          if (projection && establishRotationCenterFromProjection(projection)) {
            event.preventDefault();
            event.stopPropagation();
          }
          return;
        }

        if (selectionModeRef.current === 'point') {
          const projection = localProjectionFor(event);
          if (!projection) return;
          showLocalProjection(projection, true);
          void commitLocalProjection(projection);
          return;
        }

        const observation = observationFor(event);
        if (observation) void sendCommand({ kind: 'observe', observation, sequence: 0 });
      };

      const handlePointerCancel = (event: PointerEvent) => {
        if (inspectionPrimaryPan && renderer) {
          renderer.domElement.style.cursor = 'grab';
        }
        if (verticalDragPointerId === event.pointerId) {
          verticalDragPointerId = null;
          verticalDragMoved = false;
        }
        interactionLifecycle.ordinaryPointerDown = null;
        if (localTrackingPointerId === event.pointerId) void endLocalTracking(event, false);
      };

      const handleDoubleClick = (event: MouseEvent) => {
        if (selectionModeRef.current === 'none') return;
        event.preventDefault();
        event.stopPropagation();
      };

      renderer.domElement.addEventListener('pointerdown', handlePointerDown, true);
      renderer.domElement.addEventListener('pointermove', handlePointerMove, true);
      renderer.domElement.addEventListener('pointerup', handlePointerUp, true);
      renderer.domElement.addEventListener('pointercancel', handlePointerCancel, true);
      renderer.domElement.addEventListener('dblclick', handleDoubleClick, true);
      window.addEventListener('pointermove', handlePointerMove, true);
      window.addEventListener('pointerup', handlePointerUp, true);
      window.addEventListener('pointercancel', handlePointerCancel, true);
      syncInteraction();

      if (!showTopGrid) {
        const topMarker = new THREE.Mesh(
          new THREE.SphereGeometry(0.026, 16, 16),
          new THREE.MeshBasicMaterial({ color: 0xc6f6ff }),
        );
        topMarker.position.copy(normalizedPoints[0]);
        group.add(topMarker);
      }

      if (!showTopGrid) {
        const topLabel = createTextSprite(`Top ${formatDepth(renderPoints[0]?.md ?? renderPoints[0]?.tvd, depthUnit)}`, {
          color: '#e7fbff',
          background: 'rgba(3, 8, 12, 0.62)',
          scale: 0.18,
        });
        topLabel.position.set(box.maxX + 0.5, normalizedPoints[0].y, box.maxZ + 0.1);
        zoomScaledTextSprites.push(topLabel);
        group.add(topLabel);
      }

      const baseLabel = createTextSprite(`Base ${formatDepth(renderPoints[renderPoints.length - 1]?.md ?? renderPoints[renderPoints.length - 1]?.tvd, depthUnit)}`, {
        color: '#dff8ec',
        background: 'rgba(3, 8, 12, 0.62)',
        scale: 0.18,
      });
      baseLabel.position.set(box.maxX + 0.52, normalizedPoints[normalizedPoints.length - 1].y, box.maxZ + 0.1);
      zoomScaledTextSprites.push(baseLabel);
      group.add(baseLabel);

      const xLabel = createTextSprite('X / EAST', { color: '#80dcff', scale: 0.18 });
      xLabel.position.set(box.maxX + 0.34, box.minY, box.maxZ + 0.08);
      zoomScaledTextSprites.push(xLabel);
      group.add(xLabel);

      const yLabel = createTextSprite('Y / NORTH', { color: '#80dcff', scale: 0.18 });
      yLabel.position.set(box.minX - 0.34, box.minY, box.maxZ + 0.08);
      zoomScaledTextSprites.push(yLabel);
      group.add(yLabel);

      const zLabel = createTextSprite('Z / TVD', { color: '#80dcff', scale: 0.195 });
      zLabel.position.set(box.maxX + 0.38, box.maxY, box.minZ - 0.08);
      zoomScaledTextSprites.push(zLabel);
      group.add(zLabel);

      const resizeRenderer = () => {
        if (!renderer) return { width: 1, height: 1, aspect: 1 };
        const width = Math.max(1, host.clientWidth);
        const height = Math.max(1, host.clientHeight);
        viewportWidth = width;
        viewportHeight = height;
        const aspect = width / height;
        renderer.setSize(width, height, false);
        return { width, height, aspect };
      };

      const captureCameraViewState = (): WbvCameraViewState | null => {
        if (!controls) return null;
        return {
          position: [camera.position.x, camera.position.y, camera.position.z],
          up: [camera.up.x, camera.up.y, camera.up.z],
          quaternion: [camera.quaternion.x, camera.quaternion.y, camera.quaternion.z, camera.quaternion.w],
          target: [controls.target.x, controls.target.y, controls.target.z],
          zoom: camera.zoom,
          view_height: Math.abs(camera.top - camera.bottom),
        };
      };

      const publishZoomPercent = () => {
        onZoomPercentChangeRef.current?.(Math.round(camera.zoom * 100));
        const capturedView = captureCameraViewState();
        if (capturedView) onCameraViewChangeRef.current?.(capturedView);
      };

      const applyPreset = (preset: WbvViewPreset) => {
        if (!controls) return;
        const relockHorizontal = horizontalLockActive;
        if (relockHorizontal) applyHorizontalRotationLock(false);
        const { aspect } = resizeRenderer();
        const plan = cameraPlanFor(preset, box, aspect);
        applyCameraPlan(camera, controls, plan, aspect);
        if (relockHorizontal) applyHorizontalRotationLock(true);
        targetZoom = camera.zoom;
        wheelZoomVelocity = 0;
        smoothZoomActive = false;
        publishZoomPercent();
      };

      const fitMdInterval = (
        interval: { top_md: number; base_md: number },
        minimumViewHeight: number,
        paddingFactor: number,
        coreCenterMode: 'none' | 'photo' | 'locator' = 'none',
      ) => {
        if (!controls) return;
        const topMd = Math.min(interval.top_md, interval.base_md);
        const baseMd = Math.max(interval.top_md, interval.base_md);
        if (!Number.isFinite(topMd) || !Number.isFinite(baseMd) || baseMd <= topMd) return;

        const intervalPoints = renderPoints
          .map((point, index) => ({ point, scenePoint: normalizedPoints[index] }))
          .filter(({ point, scenePoint }) => (
            Boolean(scenePoint)
            && typeof point.md === 'number'
            && Number.isFinite(point.md)
            && point.md >= topMd
            && point.md <= baseMd
          ))
          .map(({ scenePoint }) => scenePoint);
        const topPoint = pointAtMd(topMd);
        const basePoint = pointAtMd(baseMd);
        const fitPoints = [
          ...(topPoint ? [topPoint] : []),
          ...intervalPoints,
          ...(basePoint ? [basePoint] : []),
        ];
        if (fitPoints.length < 2) return;

        const intervalBox = new THREE.Box3().setFromPoints(fitPoints);
        const intervalCenter = intervalBox.getCenter(new THREE.Vector3());
        const intervalSize = intervalBox.getSize(new THREE.Vector3());
        const { aspect } = resizeRenderer();
        const cameraDirection = camera.position.clone().sub(controls.target);
        const cameraDistance = Math.max(cameraDirection.length(), 1);
        cameraDirection.normalize();

        /*
         * Generic interval fits target the well trajectory centerline.
         * Core inspection is different: the photograph lives in a side-car
         * Core track, so the camera target must be shifted to the actual Core
         * track centerline. Otherwise a tight fit zooms into the borehole
         * and leaves the Core photograph off-center or off-screen.
         */
        const fitCenter = intervalCenter.clone();
        if (coreCenterMode !== 'none') {
          const coreTrack = coreTracks
            .filter((track) => track.visible && track.track_type === 'core')
            .sort((first, second) => first.display_order - second.display_order)[0];

          if (coreTrack) {
            const midpointMd = (topMd + baseMd) / 2;
            const fitTangents = trajectoryTangents(normalizedPoints);
            const midpointBasis = interpolateTrajectoryBasisAtMd(
              renderPoints,
              normalizedPoints,
              fitTangents,
              midpointMd,
            );

            if (midpointBasis) {
              const cameraRight = new THREE.Vector3(1, 0, 0)
                .applyQuaternion(camera.quaternion)
                .normalize();
              const axes = sharedViewAxes(fitTangents, cameraRight);
              const coreAxis = axisAtFramePosition(axes, midpointBasis.framePosition);

              const wellboreRadius = 0.008;
              const sideSign =
                coreTrack.position === 'left'
                  ? -1
                  : coreTrack.position === 'center'
                    ? 0
                    : 1;
              const radialDistance =
                wellboreRadius * (2.75 + Math.max(0, coreTrack.distance_from_wellbore));

              const sceneLengthForMdInterval = (startMd: number, endMd: number) => {
                const sampleCount = 32;
                const sampleTangents = fitTangents;
                const samples: THREE.Vector3[] = [];
                for (let index = 0; index < sampleCount; index += 1) {
                  const ratio = index / (sampleCount - 1);
                  const basis = interpolateTrajectoryBasisAtMd(
                    renderPoints,
                    normalizedPoints,
                    sampleTangents,
                    THREE.MathUtils.lerp(startMd, endMd, ratio),
                  );
                  if (basis) samples.push(basis.position);
                }
                let length = 0;
                for (let index = 1; index < samples.length; index += 1) {
                  length += samples[index].distanceTo(samples[index - 1]);
                }
                return length;
              };

              let centerOffset = resolvedTrackPlacements.get(coreTrack.track_uid)?.centerOffset
                ?? resolvedTrackPlacements.get(resolvedTrackPlacementKey('core', coreTrack.display_order, coreTrack.position))?.centerOffset
                ?? 0;

              if (coreTrack.position !== 'center' && centerOffset === 0) {
                if (coreCenterMode === 'locator') {
                  /*
                   * The true 3D overview locator is a TubeGeometry whose center
                   * is offset by radialDistance + locatorRadius.
                   * Match that renderer geometry exactly; do not derive a
                   * camera target from photograph width.
                   */
                  const locatorRadius =
                    wellboreRadius * 0.36 * Math.max(0.5, Math.max(0.05, coreTrack.width));
                  centerOffset = sideSign * (radialDistance + locatorRadius);
                } else {
                  const overlappingChunks = coreChunks.filter((chunk) => {
                    const chunkTop = Math.min(chunk.top_md, chunk.base_md);
                    const chunkBase = Math.max(chunk.top_md, chunk.base_md);
                    return chunkBase >= topMd && chunkTop <= baseMd;
                  });

                  let widestNaturalCore = 0;
                  overlappingChunks.forEach((chunk) => {
                    const nativeWidth = Number(chunk.pixel_width);
                    const nativeHeight = Number(chunk.pixel_height);
                    const chunkTop = Math.max(topMd, Math.min(chunk.top_md, chunk.base_md));
                    const chunkBase = Math.min(baseMd, Math.max(chunk.top_md, chunk.base_md));
                    if (
                      !Number.isFinite(nativeWidth)
                      || !Number.isFinite(nativeHeight)
                      || nativeWidth <= 0
                      || nativeHeight <= 0
                      || chunkBase <= chunkTop
                    ) return;
                    const sceneLength = sceneLengthForMdInterval(chunkTop, chunkBase);
                    const naturalWidth =
                      sceneLength * (nativeWidth / nativeHeight) * Math.max(0.05, coreTrack.width);
                    if (Number.isFinite(naturalWidth)) {
                      widestNaturalCore = Math.max(widestNaturalCore, naturalWidth);
                    }
                  });
                  centerOffset = sideSign * (radialDistance + widestNaturalCore / 2);
                }
              }

              fitCenter.copy(midpointBasis.position)
                .add(coreAxis.multiplyScalar(centerOffset));
            }
          }
        }

        const relockHorizontal = horizontalLockActive;
        if (relockHorizontal) applyHorizontalRotationLock(false);
        controls.target.copy(fitCenter);
        camera.position.copy(fitCenter).addScaledVector(cameraDirection, cameraDistance);

        const verticalSpan = Math.max(intervalSize.y, 0.0001);
        const horizontalSpan = Math.max(intervalSize.x, intervalSize.z, 0.0001);
        const fitViewHeight = Math.max(
          verticalSpan * paddingFactor,
          (horizontalSpan * paddingFactor) / Math.max(aspect, 0.25),
          minimumViewHeight,
        );
        applyCameraProjection(camera, fitViewHeight, aspect);
        camera.zoom = 1;
        camera.lookAt(fitCenter);
        camera.updateProjectionMatrix();
        targetZoom = camera.zoom;
        wheelZoomVelocity = 0;
        smoothZoomActive = false;
        controls.update();
        if (relockHorizontal) applyHorizontalRotationLock(true);
        publishZoomPercent();
      };

      const applyCameraView = (view: WbvCameraViewState) => {
        if (!controls) return;
        const values = [...view.position, ...view.up, ...view.quaternion, ...view.target, view.zoom, view.view_height];
        if (values.some((value) => !Number.isFinite(value)) || view.zoom <= 0 || view.view_height <= 0) return;
        const { aspect } = resizeRenderer();
        const relockHorizontal = horizontalLockActive;
        if (relockHorizontal) applyHorizontalRotationLock(false);
        camera.position.set(view.position[0], view.position[1], view.position[2]);
        camera.up.set(view.up[0], view.up[1], view.up[2]).normalize();
        camera.quaternion.set(view.quaternion[0], view.quaternion[1], view.quaternion[2], view.quaternion[3]).normalize();
        controls.target.set(view.target[0], view.target[1], view.target[2]);
        applyCameraProjection(camera, view.view_height, aspect);
        camera.zoom = THREE.MathUtils.clamp(view.zoom, controls.minZoom, controls.maxZoom);
        camera.updateProjectionMatrix();
        targetZoom = camera.zoom;
        wheelZoomVelocity = 0;
        smoothZoomActive = false;
        controls.update();
        if (relockHorizontal) applyHorizontalRotationLock(true);
        publishZoomPercent();
      };

      const applyViewAction = (action: WbvViewAction) => {
        if (!controls) return;
        if (action === 'set-rotation-center') {
          const selected = selectedPointRef.current;
          if (!selected) return;
          let selectedCenterLocal: THREE.Vector3 | null = null;
          let selectedAxisLocal: THREE.Vector3 | null = null;

          if (typeof selected.md === 'number' && Number.isFinite(selected.md)) {
            selectedCenterLocal = pointAtMd(selected.md);
            selectedAxisLocal = tangentAtMd(selected.md);
          }
          if (!selectedCenterLocal && typeof selected.station_index === 'number' && Number.isInteger(selected.station_index)) {
            selectedCenterLocal = normalizedPoints[selected.station_index]?.clone() ?? null;
            const prevPoint = normalizedPoints[Math.max(0, selected.station_index - 1)] ?? null;
            const nextPoint = normalizedPoints[Math.min(normalizedPoints.length - 1, selected.station_index + 1)] ?? null;
            if (prevPoint && nextPoint && prevPoint !== nextPoint) {
              const fallbackDirection = nextPoint.clone().sub(prevPoint);
              selectedAxisLocal = fallbackDirection.lengthSq() > Number.EPSILON ? fallbackDirection.normalize() : null;
            }
          }
          if (!selectedCenterLocal || !selectedAxisLocal) return;

          group.updateMatrixWorld(true);
          const selectedCenterWorld = selectedCenterLocal.clone().applyMatrix4(group.matrixWorld);
          const selectedAxisWorld = selectedAxisLocal.clone().transformDirection(group.matrixWorld).normalize();

          rotationCenterWorld = selectedCenterWorld;
          rotationCenterAxisWorld = selectedAxisWorld;
          if (rotationCenterMarker) {
            rotationCenterMarker.position.copy(selectedCenterLocal);
            rotationCenterMarker.visible = true;
          }
          onRotationCenterEstablishedRef.current?.(selected);
          return;
        }
        if (action === 'reset-rotation-center') {
          clearRotationCenterConstraint();
          return;
        }
        if (action === 'horizontal-rotate-negative') {
          rotateHorizontallyByDegrees(-1);
          return;
        }
        if (action === 'horizontal-rotate-positive') {
          rotateHorizontallyByDegrees(1);
          return;
        }
        if (action === 'vertical-rotate-negative') {
          rotateVerticallyByDegrees(-1);
          return;
        }
        if (action === 'vertical-rotate-positive') {
          rotateVerticallyByDegrees(1);
          return;
        }
        if (action === 'fit-selection') {
          const interval = savedIntervalRef.current;
          if (!interval) return;
          fitMdInterval(interval, 0.72, 1.35);
          return;
        }
        if (action === 'fit-core') {
          const interval = coreInspectionIntervalRef.current;
          if (!interval) return;
          /*
           * Core inspection deliberately permits a much smaller camera view
           * height than generic interval selection so short Core sections can
           * occupy meaningful screen space without altering MD geometry.
           */
          fitMdInterval(interval, 0.018, 1.55, 'photo');
          return;
        }
        if (action === 'fit-core-locator') {
          if (coreChunks.length === 0) return;
          const topMd = Math.min(...coreChunks.map((chunk) => Math.min(chunk.top_md, chunk.base_md)));
          const baseMd = Math.max(...coreChunks.map((chunk) => Math.max(chunk.top_md, chunk.base_md)));
          if (!Number.isFinite(topMd) || !Number.isFinite(baseMd) || baseMd <= topMd) return;
          /*
           * Overview locator fit:
           * - does not activate inspection photography;
           * - frames the complete published Core extent;
           * - targets the actual true-3D locator tube centerline.
           */
          fitMdInterval({ top_md: topMd, base_md: baseMd }, 0.12, 1.28, 'locator');
          return;
        }
        wheelZoomVelocity = 0;
        const factor = action === 'zoom-in' ? 1.25 : action === 'zoom-out' ? 0.8 : 0;
        targetZoom = action === 'zoom-reset'
          ? 1
          : THREE.MathUtils.clamp(targetZoom * factor, 0.25, 8);
        smoothZoomActive = true;
      };

      const resizeAndPreserveView = () => {
        const { aspect } = resizeRenderer();
        const currentViewHeight = Math.abs(camera.top - camera.bottom) || cameraPlanFor(viewPreset, box, aspect).viewHeight;
        applyCameraProjection(camera, currentViewHeight, aspect);
      };

      runtimeRef.current = {
        applyPreset,
        applyViewAction,
        applyCameraView,
        syncInteraction,
        setHorizontalRotationLock: applyHorizontalRotationLock,
        setVerticalRotationLock: applyVerticalRotationLock,
      };
      controls.addEventListener('change', publishZoomPercent);
      const { aspect } = resizeRenderer();
      const savedView = cameraViewRef.current;
      if (savedView) {
        camera.position.copy(savedView.position);
        camera.up.copy(savedView.up);
        camera.quaternion.copy(savedView.quaternion);
        camera.zoom = savedView.zoom;
        controls.target.copy(savedView.target);
        applyCameraProjection(camera, savedView.viewHeight, aspect);
        camera.updateProjectionMatrix();
        targetZoom = camera.zoom;
        wheelZoomVelocity = 0;
        smoothZoomActive = false;
        controls.update();
        publishZoomPercent();
      } else {
        applyPreset(viewPreset);
      }

      applyHorizontalRotationLock(horizontalRotationLocked);
      applyVerticalRotationLock(verticalRotationLocked);
      depthTrackRuntime.update(camera);
      coreTrackRuntime.update(camera);
      curveOverlayRuntime.update(camera);
      contextCurveOverlayRuntimes.forEach((runtime) => runtime.update(camera));
      const lastOverlayQuaternion = camera.quaternion.clone();
      let lastOverviewUpdate = Number.NEGATIVE_INFINITY;
      let currentOverviewRange: OverviewRange = { startIndex: 0, endIndex: normalizedPoints.length - 1 };

      const updateOverviewFocus = () => {
        if (overviewDisabledRef.current || !overviewFocusPathRef.current) return;
        currentOverviewRange = visibleTrajectoryRange(camera, normalizedPoints);
        const focusedPoints = overviewPoints.filter(
          (point) => point.sourceIndex >= currentOverviewRange.startIndex && point.sourceIndex <= currentOverviewRange.endIndex,
        );
        overviewFocusPathRef.current.setAttribute('d', overviewEnvelope(focusedPoints));
      };

      overviewRuntimeRef.current = {
        panToSourceIndex: (requestedIndex: number) => {
          if (!controls || normalizedPoints.length === 0) return;
          // The overview selects the camera target, not a viewport rectangle constrained
          // to remain inside the trajectory. Clamping by half the visible range made the
          // final survey stations unreachable at zoom: the camera target stopped short
          // of TD and the operator had to pan manually. Permit the target to reach both
          // true trajectory endpoints; the viewport may legitimately extend beyond them.
          const sourceIndex = THREE.MathUtils.clamp(
            Math.round(requestedIndex),
            0,
            normalizedPoints.length - 1,
          );
          const newTarget = normalizedPoints[sourceIndex];
          const translation = newTarget.clone().sub(controls.target);
          controls.target.add(translation);
          camera.position.add(translation);
          controls.update();
        },
      };

      let previousFrameTime = performance.now();
      const renderScene = (frameTime = performance.now()) => {
        if (!renderer || !controls) return;
        const deltaMs = Math.max(0, frameTime - previousFrameTime);
        previousFrameTime = frameTime;
        if (Math.abs(wheelZoomVelocity) > wheelZoomStopThreshold) {
          const decay = Math.exp(-deltaMs / wheelZoomDecayMs);
          const integratedSeconds = (wheelZoomDecayMs / 1000) * (1 - decay);
          const nextLogZoom = Math.log(Math.max(camera.zoom, 1e-6))
            + wheelZoomVelocity * integratedSeconds;
          const nextZoom = THREE.MathUtils.clamp(
            Math.exp(nextLogZoom),
            smoothZoomMin,
            smoothZoomMax,
          );

          camera.zoom = nextZoom;
          wheelZoomVelocity *= decay;
          targetZoom = camera.zoom;
          smoothZoomActive = true;

          if (
            camera.zoom <= smoothZoomMin + 1e-6
            || camera.zoom >= smoothZoomMax - 1e-6
            || Math.abs(wheelZoomVelocity) <= wheelZoomStopThreshold
          ) {
            wheelZoomVelocity = 0;
            smoothZoomActive = false;
          }
          camera.updateProjectionMatrix();
          publishZoomPercent();
        } else if (smoothZoomActive) {
          const zoomAlpha = 1 - Math.exp(-deltaMs / 72);
          const nextZoom = THREE.MathUtils.lerp(camera.zoom, targetZoom, zoomAlpha);
          if (Math.abs(nextZoom - targetZoom) <= 0.0005) {
            camera.zoom = targetZoom;
            smoothZoomActive = false;
          } else {
            camera.zoom = nextZoom;
          }
          camera.updateProjectionMatrix();
          publishZoomPercent();
        } else if (Math.abs(targetZoom - camera.zoom) > 0.0005) {
          // Keep target state aligned with non-wheel zoom sources such as middle-button dolly.
          targetZoom = camera.zoom;
        }
        controls.update();
        if (
          transientContinuity
          && displayedTransientProjectedDistance !== null
          && targetTransientProjectedDistance !== null
        ) {
          displayedTransientProjectedDistance = advanceTransientArcPresentation(
            displayedTransientProjectedDistance,
            targetTransientProjectedDistance,
            deltaMs,
          );
          showTransientLocation(
            transientContinuity.locationAtArc(displayedTransientProjectedDistance),
          );
        }
        if (1 - Math.abs(lastOverlayQuaternion.dot(camera.quaternion)) > 1e-5) {
          lastOverlayQuaternion.copy(camera.quaternion);
          depthTrackRuntime.update(camera);
          coreTrackRuntime.update(camera);
          curveOverlayRuntime.update(camera);
          contextCurveOverlayRuntimes.forEach((runtime) => runtime.update(camera));
        }
        const leaderElement = leaderRef.current;
        const readoutElement = liveReadoutRef.current;
        if (leaderElement && readoutElement) {
          leaderElement.style.width = `${liveOverlayLeaderLengthPx}px`;
          leaderElement.style.transformOrigin = 'left center';
          leaderElement.style.willChange = 'transform';
          readoutElement.style.width = `${liveOverlayReadoutWidthPx}px`;
          readoutElement.style.minWidth = `${liveOverlayReadoutWidthPx}px`;
          readoutElement.style.maxWidth = `${liveOverlayReadoutWidthPx}px`;
          readoutElement.style.textAlign = 'left';
          readoutElement.style.fontVariantNumeric = 'tabular-nums';
          readoutElement.style.whiteSpace = 'pre';
          readoutElement.style.willChange = 'transform';

          const showLive = trackValuesRef.current && selectionMarker.visible && selectedRuntimePoint !== null;
          if (showLive) {
            projectedMarkerPosition.copy(selectionMarker.position).project(camera);
            const markerX = Math.round((projectedMarkerPosition.x * 0.5 + 0.5) * viewportWidth);
            const markerY = Math.round((-projectedMarkerPosition.y * 0.5 + 0.5) * viewportHeight);
            const leaderLeft = markerX;
            const leaderTop = markerY;
            const readoutLeft = markerX + liveOverlayOffsetXPx;
            const readoutTop = markerY + liveOverlayOffsetYPx;
            const layoutKey = `${leaderLeft}:${leaderTop}:${readoutLeft}:${readoutTop}`;
            leaderElement.hidden = false;
            readoutElement.hidden = false;
            if (layoutKey !== lastReadoutLayoutKey) {
              lastReadoutLayoutKey = layoutKey;
              leaderElement.style.transform = `translate3d(${leaderLeft}px, ${leaderTop}px, 0)`;
              readoutElement.style.transform = `translate3d(${readoutLeft}px, ${readoutTop}px, 0)`;
            }
            if (readoutElement.textContent !== cachedLiveReadoutText) {
              readoutElement.textContent = cachedLiveReadoutText;
            }
          } else {
            leaderElement.hidden = true;
            readoutElement.hidden = true;
            lastReadoutLayoutKey = '';
          }
        }
        if (camera.zoom !== lastAppliedZoom) {
          lastAppliedZoom = camera.zoom;
          const textScale = textSpriteScaleForZoom(camera.zoom);
          zoomScaledTextSprites.forEach((sprite) => {
            const baseScale = sprite.userData.baseTextScale as THREE.Vector3 | undefined;
            if (baseScale) sprite.scale.copy(baseScale).multiplyScalar(textScale);
          });
          const markerScale = markerScaleForZoom(camera.zoom);
          selectionMarker.scale.setScalar(selectionMarkerScaleForZoom(camera.zoom));
          [intervalStartMarker, intervalEndMarker].forEach((marker) => {
            marker.scale.setScalar(0.105 * markerScale);
          });
          if (rotationCenterMarker) rotationCenterMarker.scale.setScalar(markerScale);
        }
        const smoothingAlpha = markerSmoothingAlpha(deltaMs, camera.zoom);
        camera.getWorldDirection(cameraDirection);
        [selectionMarker, intervalStartMarker, intervalEndMarker].forEach((marker) => {
          if (!marker.visible) return;
          if (marker === selectionMarker && transientContinuity) return;
          const basePosition = marker.userData.basePosition as THREE.Vector3;
          const targetPosition = marker.userData.targetPosition as THREE.Vector3;
          if (marker === selectionMarker) {
            basePosition.copy(targetPosition);
            marker.position.copy(basePosition);
          } else {
            basePosition.lerp(targetPosition, smoothingAlpha);
            marker.position.copy(cameraFacingMarkerPosition(basePosition, cameraDirection, 0.045));
          }
        });
        const compassRose = compassRoseRef.current;
        if (compassRose) {
          // Drive the dial from camera yaw only. Projecting world North onto the
          // screen plane becomes singular during oblique rotations and can reverse
          // the result by 180 degrees. Horizontal heading remains stable regardless
          // of camera pitch, roll, or perspective.
          camera.getWorldDirection(cameraDirection);
          const horizontalMagnitude = Math.hypot(cameraDirection.x, cameraDirection.z);

          if (horizontalMagnitude > 0.04) {
            const viewHeadingDeg = Math.atan2(cameraDirection.x, cameraDirection.z) * 180 / Math.PI;

            // The eye is on the near (viewer-facing) rim. Rotating the rose by the
            // negative viewing heading places the camera-side cardinal direction
            // beneath that fixed eye: facing north shows S at the near rim, etc.
            const rawRoseAngleDeg = -viewHeadingDeg;
            const previousAngle = compassAngleRef.current;
            let continuousAngle = rawRoseAngleDeg;

            if (previousAngle !== null) {
              while (continuousAngle - previousAngle > 180) continuousAngle -= 360;
              while (continuousAngle - previousAngle < -180) continuousAngle += 360;

              const smoothing = 1 - Math.exp(-Math.max(deltaMs, 1) / 90);
              continuousAngle = previousAngle + (continuousAngle - previousAngle) * smoothing;
            }

            compassAngleRef.current = continuousAngle;
            compassRose.style.transform = `rotate(${continuousAngle.toFixed(3)}deg)`;
            compassRose.dataset.edgeOn = 'false';
          } else {
            // Heading is undefined only when looking almost exactly vertically.
            // Retain the last valid horizontal bearing instead of reversing it.
            compassRose.dataset.edgeOn = 'true';
          }
        }

        if (formationTopLabelRuntimes.length > 0) {
          const viewportWidth = Math.max(renderer.domElement.clientWidth, 1);
          const viewportHeight = Math.max(renderer.domElement.clientHeight, 1);

          formationTopLabelRuntimes.forEach((runtime) => {
            runtime.marker.updateWorldMatrix(true, false);
            const projectedAnchor = runtime.marker.getWorldPosition(new THREE.Vector3()).project(camera);
            const visible = Number.isFinite(projectedAnchor.x)
              && Number.isFinite(projectedAnchor.y)
              && Number.isFinite(projectedAnchor.z)
              && projectedAnchor.z >= -1
              && projectedAnchor.z <= 1;

            runtime.element.hidden = !visible;
            if (!visible) return;

            let minX = Number.POSITIVE_INFINITY;
            let maxX = Number.NEGATIVE_INFINITY;
            let minY = Number.POSITIVE_INFINITY;
            let maxY = Number.NEGATIVE_INFINITY;
            let projectedBoundaryCount = 0;

            runtime.markerBoundaryPoints.forEach((localPoint) => {
              const projectedPoint = localPoint.clone()
                .applyMatrix4(runtime.marker.matrixWorld)
                .project(camera);
              if (!Number.isFinite(projectedPoint.x) || !Number.isFinite(projectedPoint.y) || !Number.isFinite(projectedPoint.z)) return;
              const x = (projectedPoint.x * 0.5 + 0.5) * viewportWidth;
              const y = (-projectedPoint.y * 0.5 + 0.5) * viewportHeight;
              minX = Math.min(minX, x);
              maxX = Math.max(maxX, x);
              minY = Math.min(minY, y);
              maxY = Math.max(maxY, y);
              projectedBoundaryCount += 1;
            });

            const centerX = (projectedAnchor.x * 0.5 + 0.5) * viewportWidth;
            const centerY = (-projectedAnchor.y * 0.5 + 0.5) * viewportHeight;
            if (projectedBoundaryCount === 0) {
              minX = maxX = centerX;
              minY = maxY = centerY;
            }

            const edgeGapPixels = 6 + THREE.MathUtils.clamp(runtime.distance, 0, 8) * 8;

            if (runtime.position === 'left') {
              runtime.element.style.left = `${(minX - edgeGapPixels).toFixed(2)}px`;
              runtime.element.style.top = `${centerY.toFixed(2)}px`;
              runtime.element.style.transform = 'translate(-100%, -50%)';
            } else if (runtime.position === 'above') {
              runtime.element.style.left = `${centerX.toFixed(2)}px`;
              runtime.element.style.top = `${(minY - edgeGapPixels).toFixed(2)}px`;
              runtime.element.style.transform = 'translate(-50%, -100%)';
            } else if (runtime.position === 'below') {
              runtime.element.style.left = `${centerX.toFixed(2)}px`;
              runtime.element.style.top = `${(maxY + edgeGapPixels).toFixed(2)}px`;
              runtime.element.style.transform = 'translate(-50%, 0)';
            } else {
              runtime.element.style.left = `${(maxX + edgeGapPixels).toFixed(2)}px`;
              runtime.element.style.top = `${centerY.toFixed(2)}px`;
              runtime.element.style.transform = 'translate(0, -50%)';
            }
          });

          // Completion labels use the KR conditional-leader policy. Keep their
          // requested side/anchor, but separate overlapping labels vertically so
          // dense completion assemblies remain readable instead of overposting.
          const completionLabels = formationTopLabelRuntimes
            .filter((runtime) => runtime.kind === 'completion' && !runtime.element.hidden)
            .sort((first, second) => first.element.getBoundingClientRect().top - second.element.getBoundingClientRect().top);
          let previousBottom = Number.NEGATIVE_INFINITY;
          let collisionIndex = 0;
          completionLabels.forEach((runtime) => {
            const rect = runtime.element.getBoundingClientRect();
            if (rect.top < previousBottom + 18) {
              const shift = previousBottom + 18 - rect.top;
              const top = Number.parseFloat(runtime.element.style.top || '0');
              runtime.element.style.top = `${(top + shift).toFixed(2)}px`;
              if (runtime.position === 'right' || runtime.position === 'left') {
                const left = Number.parseFloat(runtime.element.style.left || '0');
                const horizontalShift = collisionIndex % 2 === 0 ? 0 : 24;
                runtime.element.style.left = `${(left + horizontalShift).toFixed(2)}px`;
              }
              collisionIndex += 1;
            }
            previousBottom = runtime.element.getBoundingClientRect().bottom;
          });
        }

        renderer.render(scene, camera);
        animationFrame = window.requestAnimationFrame(renderScene);
        if (!overviewDisabledRef.current && frameTime - lastOverviewUpdate >= 100) {
          try {
            updateOverviewFocus();
          } catch (error) {
            overviewDisabledRef.current = true;
            console.error('WBV overview disabled after isolated update failure', error);
          }
          lastOverviewUpdate = frameTime;
        }
      };

      resizeObserver = new ResizeObserver(resizeAndPreserveView);
      resizeObserver.observe(host);
      renderScene();
      setStatus('rendered');

      return () => {
        const finalCameraView = captureCameraViewState();
        if (finalCameraView) onCameraViewChangeRef.current?.(finalCameraView);
        cameraViewRef.current = {
          position: camera.position.clone(),
          up: camera.up.clone(),
          quaternion: camera.quaternion.clone(),
          target: controls?.target.clone() ?? new THREE.Vector3(),
          zoom: camera.zoom,
          viewHeight: Math.abs(camera.top - camera.bottom),
        };
        controls?.removeEventListener('change', publishZoomPercent);
        runtimeRef.current = null;
        overviewRuntimeRef.current = null;
        if (curveOverlayGroupRef.current === curveOverlayGroup) {
          curveOverlayGroupRef.current = null;
        }
        if (depthTrackGroupRef.current === depthTrackGroup) {
          depthTrackGroupRef.current = null;
        }
        if (coreTrackRuntimeRef.current === coreTrackRuntime) {
          coreTrackRuntimeRef.current = null;
        }
        if (animationFrame !== null) {
          window.cancelAnimationFrame(animationFrame);
        }
        resizeObserver?.disconnect();
        window.removeEventListener('keydown', handleKeyboardTraversal);
        renderer?.domElement.removeEventListener('pointerdown', handlePointerDown, true);
        renderer?.domElement.removeEventListener('pointermove', handlePointerMove, true);
        renderer?.domElement.removeEventListener('pointerup', handlePointerUp, true);
        renderer?.domElement.removeEventListener('pointercancel', handlePointerCancel, true);
        renderer?.domElement.removeEventListener('dblclick', handleDoubleClick, true);
        renderer?.domElement.removeEventListener('wheel', handleSmoothWheelZoom, true);
        window.removeEventListener('pointermove', handlePointerMove, true);
        window.removeEventListener('pointerup', handlePointerUp, true);
        window.removeEventListener('pointercancel', handlePointerCancel, true);
        clearTransientContinuity();
        formationTopLabelOverlay?.replaceChildren();
        controls?.dispose();
        disposeObject(scene);
        renderer?.dispose();
      };
    } catch (error) {
      console.error('WBV trajectory renderer failed', error);
      formationTopLabelOverlayRef.current?.replaceChildren();
      runtimeRef.current = null;
      overviewRuntimeRef.current = null;
      curveOverlayGroupRef.current = null;
      depthTrackGroupRef.current = null;
      setStatus('error');
      controls?.dispose();
      renderer?.dispose();
      return undefined;
    }
  }, [
    activeManagedWellId,
    contextSceneTrajectories,
    curveOverlays,
    curveTracks,
    depthTracks,
    curveTrackSpacing,
    depthTicks,
    depthUnit,
    renderPoints,
    scenePoints,
    showAxes,
    showBoundingBox,
    showDepthLabels,
    showBottomGrid,
    showTopGrid,
    showGroundPlane,
    showSurveyStations,
    showTrajectory,
    lithologyRenderKey,
    completionRenderKey,
    coreRenderKey,
    trackPlacementRenderKey,
    useSurfaceLighting,
    viewProperties,
  ]);

  useEffect(() => {
    coreTrackRuntimeRef.current?.setFocusInterval(coreLocatorFocusInterval);
  }, [coreLocatorFocusInterval]);

  useEffect(() => {
    runtimeRef.current?.syncInteraction();
  }, [selectionMode, selectedPoint, intervalDraftStart, savedInterval]);

  useEffect(() => {
    runtimeRef.current?.applyPreset(viewPreset);
  }, [viewPreset, viewCommandId]);

  useEffect(() => {
    if (viewAction) runtimeRef.current?.applyViewAction(viewAction);
  }, [viewAction, viewActionId]);

  useEffect(() => {
    if (cameraViewRestore && cameraViewRestoreId > 0) runtimeRef.current?.applyCameraView(cameraViewRestore);
  }, [cameraViewRestore, cameraViewRestoreId]);

  useEffect(() => {
    runtimeRef.current?.setHorizontalRotationLock(horizontalRotationLocked);
  }, [horizontalRotationLocked]);

  useEffect(() => {
    runtimeRef.current?.setVerticalRotationLock(verticalRotationLocked);
  }, [verticalRotationLocked]);

  const overviewPointerPosition = (event: React.PointerEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return null;
    return {
      x: ((event.clientX - rect.left) / rect.width) * OVERVIEW_WIDTH,
      y: ((event.clientY - rect.top) / rect.height) * OVERVIEW_HEIGHT,
    };
  };

  const panOverviewFromPointer = (event: React.PointerEvent<SVGSVGElement>) => {
    const position = overviewPointerPosition(event);
    if (!position || overviewPoints.length === 0) return;
    const sourceIndex = nearestOverviewSourceIndex(overviewPoints, position.x, position.y);
    overviewRuntimeRef.current?.panToSourceIndex(sourceIndex);
  };

  const handleOverviewPointerDown = (event: React.PointerEvent<SVGSVGElement>) => {
    if (event.button !== 0) return;
    overviewDragRef.current = true;
    event.currentTarget.setPointerCapture(event.pointerId);
    event.preventDefault();
    event.stopPropagation();
    panOverviewFromPointer(event);
  };

  const handleOverviewPointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    if (!overviewDragRef.current) return;
    event.preventDefault();
    event.stopPropagation();
    panOverviewFromPointer(event);
  };

  const handleOverviewPointerEnd = (event: React.PointerEvent<SVGSVGElement>) => {
    overviewDragRef.current = false;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    event.preventDefault();
    event.stopPropagation();
  };

  const directionalReferenceKnown = renderPoints.some((point) =>
    [point.x, point.y, point.east_departure, point.north_departure].some(
      (value) => typeof value === 'number' && Number.isFinite(value),
    ),
  );

  return (
    <div
      className="wlv-wbv-trajectory-renderer"
      ref={hostRef}
      aria-label="Backend-owned 3D wellbore trajectory renderer"
      data-renderer-status={status}
      data-viewer-state={viewerState}
    >
      <canvas ref={canvasRef} aria-hidden="true" />
      <div
        ref={formationTopLabelOverlayRef}
        className="wlv-wbv-formation-top-label-overlay"
        aria-hidden="true"
        style={{
          position: 'absolute',
          inset: 0,
          zIndex: 11,
          overflow: 'hidden',
          pointerEvents: 'none',
        }}
      />
      {status === 'rendered' && overviewPoints.length >= 2 ? (
        <div className="wlv-wbv-overview" aria-label="Wellbore overview and draggable zoom focus">
          <span className="wlv-wbv-overview__title">Overview</span>
          <svg
            className="wlv-wbv-overview__svg"
            viewBox={`0 0 ${OVERVIEW_WIDTH} ${OVERVIEW_HEIGHT}`}
            role="application"
            aria-label="Drag the highlighted focus polygon to pan the wellbore view"
            onPointerDown={handleOverviewPointerDown}
            onPointerMove={handleOverviewPointerMove}
            onPointerUp={handleOverviewPointerEnd}
            onPointerCancel={handleOverviewPointerEnd}
          >
            <path className="wlv-wbv-overview__trajectory" d={overviewFullPath} />
            <path ref={overviewFocusPathRef} className="wlv-wbv-overview__focus" />
          </svg>
        </div>
      ) : null}
      <div ref={leaderRef} className="wlv-wbv-live-track-line" hidden aria-hidden="true" />
      <div ref={liveReadoutRef} className="wlv-wbv-live-track-readout" hidden aria-live="polite" />
      {status === 'rendered' && showNorthArrow && directionalReferenceKnown ? (
        <div className="wlv-wbv-compass-dial" aria-label="Viewer orientation compass">
          <div className="wlv-wbv-compass-dial__bezel" aria-hidden="true">
            <span className="wlv-wbv-compass-dial__viewer-eye">
              <svg viewBox="0 0 24 16" focusable="false" aria-hidden="true">
                <path d="M1.5 8C4.3 3.7 7.8 1.5 12 1.5S19.7 3.7 22.5 8C19.7 12.3 16.2 14.5 12 14.5S4.3 12.3 1.5 8Z" />
                <circle cx="12" cy="8" r="3.15" />
                <circle className="wlv-wbv-compass-dial__viewer-eye-highlight" cx="13" cy="7" r="0.75" />
              </svg>
            </span>
            <div ref={compassRoseRef} className="wlv-wbv-compass-dial__rose">
              <span className="wlv-wbv-compass-dial__cardinal is-north">N</span>
              <span className="wlv-wbv-compass-dial__cardinal is-east">E</span>
              <span className="wlv-wbv-compass-dial__cardinal is-south">S</span>
              <span className="wlv-wbv-compass-dial__cardinal is-west">W</span>
              <span className="wlv-wbv-compass-dial__center" />
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
