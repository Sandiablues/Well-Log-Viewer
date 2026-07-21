import { useEffect, useMemo, useRef, useState } from 'react';
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

export type WbvViewPreset = 'reset' | 'fit' | 'top' | 'side';

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
  fill_mode: 'none' | 'to_baseline' | 'between_curves' | 'crossover';
  fill_target_curve_product_id?: string | null;
  fill_side: 'positive' | 'negative';
  fill_color: string;
  fill_opacity: number;
  fill_outline: boolean;
  baseline_normalized: number;
  samples: WbvCurveOverlayRenderSample[];
};

type WbvTrajectoryRendererProps = {
  renderPoints: WbvTrajectoryRenderPoint[];
  boundingBox?: WbvBoundingBox;
  depthUnit: string;
  viewerState: string;
  viewPreset?: WbvViewPreset;
  viewCommandId?: number;
  onInteractionCommand?: (command: {
    kind: "observe" | "track-start" | "track-update" | "track-commit" | "track-cancel";
    observation?: WbvScreenObservationV2;
    sessionId?: string;
    sequence: number;
  }) => Promise<WbvInteractionStateV2 | null>;
  onLocalSelectedPoint?: (point: WbvTrajectoryRenderPoint) => void;
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
  showAxes?: boolean;
  useSurfaceLighting?: boolean;
  curveOverlays?: WbvCurveOverlayRenderCurve[];
  curveTracks?: WbvCurveTrack[];
  depthTracks?: WbvDepthTrack[];
  curveTrackSpacing?: number;
  showCurveOverlays?: boolean;
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

    let innerOffset: number;
    let outerOffset: number;
    if (track.position === 'center') {
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
        color: '#b9f3ff',
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

function addCurveOverlays(
  group: THREE.Group,
  overlays: WbvCurveOverlayRenderCurve[],
  renderPoints: WbvTrajectoryRenderPoint[],
  positions: THREE.Vector3[],
  tracks: WbvCurveTrack[],
  trackSpacing: number,
): CurveOverlayRuntime {
  const bindings: ViewRelativeGeometryBinding[] = [];
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
    if (track.geometry_type !== 'legacy_planar') {
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
    const excursion = excursionSign * widthScale * Math.min(curve.radial_width, track.width);
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

  if (preset === 'side') {
    return {
      position: center.clone().add(new THREE.Vector3(distance, 0, 0.01)),
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
    const materialHolder = child as THREE.Object3D & { material?: THREE.Material | THREE.Material[] };
    const geometryHolder = child as THREE.Object3D & { geometry?: THREE.BufferGeometry };

    geometryHolder.geometry?.dispose();

    materialList(materialHolder.material).forEach((material) => {
      const maybeMapped = material as THREE.Material & { map?: THREE.Texture };
      maybeMapped.map?.dispose();
      material.dispose();
    });
  });
}

export function WellboreTrajectoryRenderer({
  renderPoints,
  boundingBox: _boundingBox,
  depthUnit,
  viewerState,
  viewPreset = 'reset',
  viewCommandId = 0,
  onInteractionCommand,
  onLocalSelectedPoint,
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
  showAxes = false,
  useSurfaceLighting = true,
  curveOverlays = [],
  curveTracks = [],
  depthTracks = [],
  curveTrackSpacing = 0.05,
  showCurveOverlays = true,
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
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
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
  onLocalSelectedPointRef.current = onLocalSelectedPoint;
  const selectedPointRef = useRef<WbvTrajectoryRenderPoint | null>(selectedPoint);
  selectedPointRef.current = selectedPoint;
  const selectionModeRef = useRef(selectionMode);
  selectionModeRef.current = selectionMode;
  const intervalDraftStartRef = useRef<WbvTrajectoryRenderPoint | null>(intervalDraftStart);
  intervalDraftStartRef.current = intervalDraftStart;
  const savedIntervalRef = useRef(savedInterval);
  savedIntervalRef.current = savedInterval;
  const [status, setStatus] = useState<RendererStatus>('idle');
  const runtimeRef = useRef<{
    applyPreset: (preset: WbvViewPreset) => void;
    syncInteraction: () => void;
  } | null>(null);
  const cameraViewRef = useRef<CameraViewSnapshot | null>(null);
  const curveOverlayGroupRef = useRef<THREE.Group | null>(null);

  useEffect(() => {
    trackValuesRef.current = trackValuesAlongWellbore;
  }, [trackValuesAlongWellbore]);

  useEffect(() => {
    if (curveOverlayGroupRef.current) {
      curveOverlayGroupRef.current.visible = showCurveOverlays;
    }
  }, [showCurveOverlays]);

  const scenePoints = useMemo(() => scenePointsFromBackend(renderPoints), [renderPoints]);
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
      const normalizedPoints = createNormalizedPoints(scenePoints);
      const box = sceneBoxFor(normalizedPoints);
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
      controls.mouseButtons = {
        LEFT: THREE.MOUSE.ROTATE,
        MIDDLE: THREE.MOUSE.DOLLY,
        RIGHT: THREE.MOUSE.PAN,
      };
      controls.touches = {
        ONE: THREE.TOUCH.ROTATE,
        TWO: THREE.TOUCH.DOLLY_PAN,
      };
      if (interactionLifecycleRef.current.trackingPointerId !== null) {
        controls.enabled = false;
      }

      if (showBoundingBox) {
        group.add(createTrajectoryBoundingBox(box));
      }

      if (showGroundPlane) {
        const plane = new THREE.Mesh(
          new THREE.PlaneGeometry(Math.max(3.2, box.maxX - box.minX + 1.2), Math.max(3.2, box.maxZ - box.minZ + 1.2)),
          new THREE.MeshStandardMaterial({ color: 0x182129, transparent: true, opacity: 0.62, roughness: 0.92 }),
        );
        plane.rotation.x = -Math.PI / 2;
        plane.position.y = box.minY;
        group.add(plane);
      }

      const gridSize = Math.max(3.2, box.maxX - box.minX + 1.2, box.maxZ - box.minZ + 1.2);
      const gridCenterX = (box.minX + box.maxX) / 2;
      const gridCenterZ = (box.minZ + box.maxZ) / 2;

      if (showBottomGrid) {
        const bottomGrid = new THREE.GridHelper(gridSize, 12, 0x526878, 0x2b3944);
        bottomGrid.position.set(gridCenterX, box.minY + 0.002, gridCenterZ);
        group.add(bottomGrid);
      }

      if (showTopGrid) {
        const topGrid = new THREE.GridHelper(gridSize, 12, 0x526878, 0x2b3944);
        topGrid.position.set(gridCenterX, box.maxY - 0.002, gridCenterZ);
        group.add(topGrid);
      }

      if (showAxes) {
        const axes = new THREE.AxesHelper(0.82);
        axes.position.set(box.minX, box.minY, box.minZ);
        group.add(axes);
      }

      if (useSurfaceLighting) {
        scene.add(new THREE.HemisphereLight(0xdff6ff, 0x17202a, 1.1));
        const keyLight = new THREE.DirectionalLight(0xffffff, 1.15);
        keyLight.position.set(3, 5, 4);
        scene.add(keyLight);
      }

      const zoomScaledTextSprites: THREE.Sprite[] = [];

      if (showDepthLabels) {
        const depthTickPoints: THREE.Vector3[] = [];
        const tickLength = Math.max(
          0.06,
          Math.min(0.11, Math.abs(box.maxX - box.minX) * 0.06),
        );

        depthTicks.forEach((tick) => {
          const y = sceneYForMeasuredDepth(renderPoints, normalizedPoints, tick.md, tick.pointIndex);
          const label = createTextSprite(`MD ${tick.label}`, {
            color: '#b9f3ff',
            background: 'rgba(3, 8, 12, 0.58)',
            scale: 0.18,
          });
          label.position.set(box.minX - 0.52, y, box.maxZ + 0.09);
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

      let surveyStationMaterial: THREE.PointsMaterial | null = null;
      if (showSurveyStations) {
        const stationGeometry = new THREE.BufferGeometry().setFromPoints(normalizedPoints);
        surveyStationMaterial = new THREE.PointsMaterial({
          color: 0x2f9bff,
          size: surveyStationPointSizeForZoom(camera.zoom),
          sizeAttenuation: false,
          transparent: true,
          opacity: 1,
          depthTest: false,
          depthWrite: false,
        });
        const surveyStations = new THREE.Points(stationGeometry, surveyStationMaterial);
        surveyStations.renderOrder = 120;
        group.add(surveyStations);
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

      const curve = new THREE.CatmullRomCurve3(normalizedPoints, false, 'catmullrom', 0.02);
      const displayTrajectory = buildUniformCurveDisplayTrajectory(
        renderPoints,
        normalizedPoints,
        curve,
        interpolateTransientPoint,
        0.25,
      );
      const displayTrajectoryPositions = displayTrajectory.map((sample) => sample.position);
      const guideGeometry = new THREE.TubeGeometry(
        curve,
        Math.max(80, Math.min(1200, displayTrajectoryPositions.length)),
        0.008,
        8,
        false,
      );
      const guideMaterial = useSurfaceLighting
        ? new THREE.MeshStandardMaterial({
            color: 0x67d599,
            emissive: 0x2c7a52,
            emissiveIntensity: 0.90,
            roughness: 0.42,
            transparent: true,
            opacity: 0.96,
          })
        : new THREE.MeshBasicMaterial({
            color: 0x67d599,
            transparent: true,
            opacity: 0.96,
          });
      const trajectoryMesh = new THREE.Mesh(guideGeometry, guideMaterial);
      trajectoryMesh.visible = showTrajectory;
      trajectoryMesh.renderOrder = 35;
      guideMaterial.depthTest = false;
      guideMaterial.depthWrite = false;
      group.add(trajectoryMesh);

      const lineGeometry = new THREE.BufferGeometry().setFromPoints(displayTrajectoryPositions);
      const lineMaterial = new THREE.LineBasicMaterial({
        color: 0xe7fbff,
        transparent: true,
        opacity: 0.76,
      });
      const trajectoryLine = new THREE.Line(lineGeometry, lineMaterial);
      trajectoryLine.visible = showTrajectory;
      trajectoryLine.renderOrder = 36;
      lineMaterial.depthTest = false;
      lineMaterial.depthWrite = false;
      group.add(trajectoryLine);

      const depthTrackGroup = new THREE.Group();
      group.add(depthTrackGroup);
      const depthTrackRuntime = addDepthTracks(
        depthTrackGroup,
        depthTracks,
        renderPoints,
        normalizedPoints,
        depthUnit,
      );

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
        const geometry = new THREE.SphereGeometry(0.028, 20, 14);
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

      const pointAtMd = (md: number): THREE.Vector3 | null => {
        for (let index = 0; index < renderPoints.length - 1; index += 1) {
          const firstMd = renderPoints[index].md;
          const secondMd = renderPoints[index + 1].md;
          if (typeof firstMd !== 'number' || !Number.isFinite(firstMd) || typeof secondMd !== 'number' || !Number.isFinite(secondMd)) continue;
          if (md < Math.min(firstMd, secondMd) || md > Math.max(firstMd, secondMd)) continue;
          const ratio = secondMd === firstMd ? 0 : THREE.MathUtils.clamp((md - firstMd) / (secondMd - firstMd), 0, 1);
          return normalizedPoints[index].clone().lerp(normalizedPoints[index + 1], ratio);
        }
        return null;
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
        return createWbvScreenObservation(event, renderer.domElement, camera, 20);
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
        return createWbvScreenObservation(synthetic, renderer.domElement, camera, 20);
      };

      const commitLocalProjection = async (projection: WbvFrontendSelectedPoint): Promise<void> => {
        const observation = exactObservationForProjection(projection);
        if (!observation) return;
        await sendCommand({ kind: 'observe', observation, sequence: 0 });
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

      const handlePointerDown = (event: PointerEvent) => {
        if (!renderer || event.button !== 0 || selectionModeRef.current === 'none') return;
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
        if (localTrackingPointerId === event.pointerId) {
          void endLocalTracking(event, true);
          return;
        }
        const pointerDown = interactionLifecycle.ordinaryPointerDown;
        interactionLifecycle.ordinaryPointerDown = null;
        if (!pointerDown || pointerDown.pointerId !== event.pointerId || pointerDown.moved) return;

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

      const topMarker = new THREE.Mesh(
        new THREE.SphereGeometry(0.026, 16, 16),
        new THREE.MeshBasicMaterial({ color: 0xc6f6ff }),
      );
      topMarker.position.copy(normalizedPoints[0]);
      group.add(topMarker);

      const baseMarker = new THREE.Mesh(
        new THREE.SphereGeometry(0.026, 16, 16),
        new THREE.MeshBasicMaterial({ color: 0x67d599 }),
      );
      baseMarker.position.copy(normalizedPoints[normalizedPoints.length - 1]);
      group.add(baseMarker);

      const topLabel = createTextSprite(`Top ${formatDepth(renderPoints[0]?.md ?? renderPoints[0]?.tvd, depthUnit)}`, {
        color: '#e7fbff',
        background: 'rgba(3, 8, 12, 0.62)',
        scale: 0.18,
      });
      topLabel.position.set(box.maxX + 0.5, normalizedPoints[0].y, box.maxZ + 0.1);
      zoomScaledTextSprites.push(topLabel);
      group.add(topLabel);

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

      const applyPreset = (preset: WbvViewPreset) => {
        if (!controls) return;
        const { aspect } = resizeRenderer();
        const plan = cameraPlanFor(preset, box, aspect);
        applyCameraPlan(camera, controls, plan, aspect);
      };

      const resizeAndPreserveView = () => {
        const { aspect } = resizeRenderer();
        const currentViewHeight = Math.abs(camera.top - camera.bottom) || cameraPlanFor(viewPreset, box, aspect).viewHeight;
        applyCameraProjection(camera, currentViewHeight, aspect);
      };

      runtimeRef.current = { applyPreset, syncInteraction };
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
        controls.update();
      } else {
        applyPreset(viewPreset);
      }

      depthTrackRuntime.update(camera);
      curveOverlayRuntime.update(camera);
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
          const span = Math.max(1, currentOverviewRange.endIndex - currentOverviewRange.startIndex);
          const halfBefore = Math.floor(span / 2);
          const halfAfter = span - halfBefore;
          const sourceIndex = Math.max(halfBefore, Math.min(normalizedPoints.length - 1 - halfAfter, requestedIndex));
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
          curveOverlayRuntime.update(camera);
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
          [intervalStartMarker, intervalEndMarker].forEach((marker) => {
            marker.scale.setScalar(0.105 * markerScale);
          });
          if (surveyStationMaterial) {
            surveyStationMaterial.size = surveyStationPointSizeForZoom(camera.zoom);
          }
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
        cameraViewRef.current = {
          position: camera.position.clone(),
          up: camera.up.clone(),
          quaternion: camera.quaternion.clone(),
          target: controls?.target.clone() ?? new THREE.Vector3(),
          zoom: camera.zoom,
          viewHeight: Math.abs(camera.top - camera.bottom),
        };
        runtimeRef.current = null;
        overviewRuntimeRef.current = null;
        if (curveOverlayGroupRef.current === curveOverlayGroup) {
          curveOverlayGroupRef.current = null;
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
        window.removeEventListener('pointermove', handlePointerMove, true);
        window.removeEventListener('pointerup', handlePointerUp, true);
        window.removeEventListener('pointercancel', handlePointerCancel, true);
        clearTransientContinuity();
        controls?.dispose();
        disposeObject(scene);
        renderer?.dispose();
      };
    } catch (error) {
      console.error('WBV trajectory renderer failed', error);
      runtimeRef.current = null;
      overviewRuntimeRef.current = null;
      curveOverlayGroupRef.current = null;
      setStatus('error');
      controls?.dispose();
      renderer?.dispose();
      return undefined;
    }
  }, [
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
    useSurfaceLighting,
  ]);

  useEffect(() => {
    runtimeRef.current?.syncInteraction();
  }, [selectionMode, selectedPoint, intervalDraftStart, savedInterval]);

  useEffect(() => {
    runtimeRef.current?.applyPreset(viewPreset);
  }, [viewPreset, viewCommandId]);

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

  const pointCount = renderPoints.length.toLocaleString();

  return (
    <div
      className="wlv-wbv-trajectory-renderer"
      ref={hostRef}
      aria-label="Backend-owned 3D wellbore trajectory renderer"
      data-renderer-status={status}
      data-viewer-state={viewerState}
    >
      <canvas ref={canvasRef} aria-hidden="true" />
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
      <div className="wlv-wbv-renderer-readout" aria-live="polite">
        <strong>{status === 'rendered' ? '3D trajectory rendered' : `3D trajectory renderer: ${status}`}</strong>
        <span>{pointCount} survey points · {depthUnit} · {viewPreset} view · click a point to inspect</span>
      </div>
    </div>
  );
}
