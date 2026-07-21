export type WbvSelectionTrajectoryPoint = Readonly<{
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
}>;

export type WbvProjectedTrajectoryStation = Readonly<{
  point: WbvSelectionTrajectoryPoint;
  sceneX: number;
  sceneY: number;
  sceneZ: number;
  screenX: number;
  screenY: number;
}>;

export type WbvFrontendSelectedPoint = Readonly<{
  point: WbvSelectionTrajectoryPoint;
  md: number | null;
  tvd: number | null;
  tvdss: number | null;
  x: number | null;
  y: number | null;
  z: number | null;
  inclination: number | null;
  azimuth: number | null;
  doglegSeverity: number | null;
  eastDeparture: number | null;
  northDeparture: number | null;
  segmentIndex: number;
  segmentRatio: number;
  sceneX: number;
  sceneY: number;
  sceneZ: number;
  screenX: number;
  screenY: number;
  screenDistancePx: number;
}>;

export type WbvScreenPointer = Readonly<{ x: number; y: number }>;

const clamp = (value: number, minimum: number, maximum: number): number =>
  Math.max(minimum, Math.min(maximum, value));

const lerp = (start: number, end: number, ratio: number): number =>
  start + (end - start) * ratio;

function finiteOrNull(value: number | null | undefined): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function interpolateNullable(
  start: number | null | undefined,
  end: number | null | undefined,
  ratio: number,
): number | null {
  const first = finiteOrNull(start);
  const second = finiteOrNull(end);
  if (first !== null && second !== null) return lerp(first, second, ratio);
  if (ratio <= 0 && first !== null) return first;
  if (ratio >= 1 && second !== null) return second;
  return null;
}

function interpolatePoint(
  start: WbvSelectionTrajectoryPoint,
  end: WbvSelectionTrajectoryPoint,
  ratio: number,
): WbvSelectionTrajectoryPoint {
  return {
    station_index: ratio < 0.5 ? start.station_index : end.station_index,
    md: interpolateNullable(start.md, end.md, ratio),
    tvd: interpolateNullable(start.tvd, end.tvd, ratio),
    tvdss: interpolateNullable(start.tvdss, end.tvdss, ratio),
    x: interpolateNullable(start.x, end.x, ratio),
    y: interpolateNullable(start.y, end.y, ratio),
    z: interpolateNullable(start.z, end.z, ratio),
    inclination: interpolateNullable(start.inclination, end.inclination, ratio),
    azimuth: interpolateNullable(start.azimuth, end.azimuth, ratio),
    dogleg_severity: interpolateNullable(start.dogleg_severity, end.dogleg_severity, ratio),
    east_departure: interpolateNullable(start.east_departure, end.east_departure, ratio),
    north_departure: interpolateNullable(start.north_departure, end.north_departure, ratio),
  };
}

/**
 * Statelessly projects a screen-space pointer onto the nearest projected
 * wellbore segment. It has no UI, backend, lifecycle, smoothing, continuity,
 * or persistence responsibilities.
 */
export function projectPointerToWellbore(
  pointer: WbvScreenPointer,
  stations: readonly WbvProjectedTrajectoryStation[],
  hitTolerancePx = 20,
): WbvFrontendSelectedPoint | null {
  if (
    stations.length < 2 ||
    !Number.isFinite(pointer.x) ||
    !Number.isFinite(pointer.y) ||
    !Number.isFinite(hitTolerancePx) ||
    hitTolerancePx < 0
  ) {
    return null;
  }

  let best:
    | {
        segmentIndex: number;
        ratio: number;
        screenX: number;
        screenY: number;
        distancePx: number;
      }
    | null = null;

  for (let segmentIndex = 0; segmentIndex < stations.length - 1; segmentIndex += 1) {
    const start = stations[segmentIndex];
    const end = stations[segmentIndex + 1];
    const dx = end.screenX - start.screenX;
    const dy = end.screenY - start.screenY;
    const lengthSquared = dx * dx + dy * dy;
    const ratio = lengthSquared > 0
      ? clamp(
          ((pointer.x - start.screenX) * dx + (pointer.y - start.screenY) * dy) / lengthSquared,
          0,
          1,
        )
      : 0;
    const screenX = lerp(start.screenX, end.screenX, ratio);
    const screenY = lerp(start.screenY, end.screenY, ratio);
    const distancePx = Math.hypot(pointer.x - screenX, pointer.y - screenY);

    if (!best || distancePx < best.distancePx) {
      best = { segmentIndex, ratio, screenX, screenY, distancePx };
    }
  }

  if (!best || best.distancePx > hitTolerancePx) return null;

  const start = stations[best.segmentIndex];
  const end = stations[best.segmentIndex + 1];
  const point = interpolatePoint(start.point, end.point, best.ratio);

  return {
    point,
    md: finiteOrNull(point.md),
    tvd: finiteOrNull(point.tvd),
    tvdss: finiteOrNull(point.tvdss),
    x: finiteOrNull(point.x),
    y: finiteOrNull(point.y),
    z: finiteOrNull(point.z),
    inclination: finiteOrNull(point.inclination),
    azimuth: finiteOrNull(point.azimuth),
    doglegSeverity: finiteOrNull(point.dogleg_severity),
    eastDeparture: finiteOrNull(point.east_departure),
    northDeparture: finiteOrNull(point.north_departure),
    segmentIndex: best.segmentIndex,
    segmentRatio: best.ratio,
    sceneX: lerp(start.sceneX, end.sceneX, best.ratio),
    sceneY: lerp(start.sceneY, end.sceneY, best.ratio),
    sceneZ: lerp(start.sceneZ, end.sceneZ, best.ratio),
    screenX: best.screenX,
    screenY: best.screenY,
    screenDistancePx: best.distancePx,
  };
}


export type WbvContinuousProjectedTracker = {
  update(pointer: WbvScreenPointer, stations: readonly WbvProjectedTrajectoryStation[]): WbvFrontendSelectedPoint | null;
};

type ContinuousCandidate = WbvFrontendSelectedPoint & Readonly<{ pathPx: number }>;

function cumulativePath(stations: readonly WbvProjectedTrajectoryStation[]): number[] {
  const path = new Array<number>(stations.length).fill(0);
  for (let index = 1; index < stations.length; index += 1) {
    path[index] = path[index - 1] + Math.hypot(
      stations[index].screenX - stations[index - 1].screenX,
      stations[index].screenY - stations[index - 1].screenY,
    );
  }
  return path;
}

function candidateForSegment(
  pointer: WbvScreenPointer,
  stations: readonly WbvProjectedTrajectoryStation[],
  path: readonly number[],
  segmentIndex: number,
): ContinuousCandidate | null {
  if (segmentIndex < 0 || segmentIndex >= stations.length - 1) return null;
  const start = stations[segmentIndex];
  const end = stations[segmentIndex + 1];
  const dx = end.screenX - start.screenX;
  const dy = end.screenY - start.screenY;
  const lengthSquared = dx * dx + dy * dy;
  const ratio = lengthSquared > 0
    ? clamp(((pointer.x - start.screenX) * dx + (pointer.y - start.screenY) * dy) / lengthSquared, 0, 1)
    : 0;
  const screenX = lerp(start.screenX, end.screenX, ratio);
  const screenY = lerp(start.screenY, end.screenY, ratio);
  const point = interpolatePoint(start.point, end.point, ratio);
  return {
    point,
    md: finiteOrNull(point.md), tvd: finiteOrNull(point.tvd), tvdss: finiteOrNull(point.tvdss),
    x: finiteOrNull(point.x), y: finiteOrNull(point.y), z: finiteOrNull(point.z),
    inclination: finiteOrNull(point.inclination), azimuth: finiteOrNull(point.azimuth),
    doglegSeverity: finiteOrNull(point.dogleg_severity), eastDeparture: finiteOrNull(point.east_departure),
    northDeparture: finiteOrNull(point.north_departure), segmentIndex, segmentRatio: ratio,
    sceneX: lerp(start.sceneX, end.sceneX, ratio), sceneY: lerp(start.sceneY, end.sceneY, ratio),
    sceneZ: lerp(start.sceneZ, end.sceneZ, ratio), screenX, screenY,
    screenDistancePx: Math.hypot(pointer.x - screenX, pointer.y - screenY),
    pathPx: path[segmentIndex] + Math.sqrt(lengthSquared) * ratio,
  };
}

function candidateAtPath(
  pointer: WbvScreenPointer,
  stations: readonly WbvProjectedTrajectoryStation[],
  path: readonly number[],
  targetPathPx: number,
): ContinuousCandidate | null {
  for (let segmentIndex = 0; segmentIndex < stations.length - 1; segmentIndex += 1) {
    if (targetPathPx < path[segmentIndex] || targetPathPx > path[segmentIndex + 1]) continue;
    const span = Math.max(0.0001, path[segmentIndex + 1] - path[segmentIndex]);
    const ratio = clamp((targetPathPx - path[segmentIndex]) / span, 0, 1);
    const start = stations[segmentIndex];
    const end = stations[segmentIndex + 1];
    const screenX = lerp(start.screenX, end.screenX, ratio);
    const screenY = lerp(start.screenY, end.screenY, ratio);
    const point = interpolatePoint(start.point, end.point, ratio);
    return {
      point,
      md: finiteOrNull(point.md), tvd: finiteOrNull(point.tvd), tvdss: finiteOrNull(point.tvdss),
      x: finiteOrNull(point.x), y: finiteOrNull(point.y), z: finiteOrNull(point.z),
      inclination: finiteOrNull(point.inclination), azimuth: finiteOrNull(point.azimuth),
      doglegSeverity: finiteOrNull(point.dogleg_severity), eastDeparture: finiteOrNull(point.east_departure),
      northDeparture: finiteOrNull(point.north_departure), segmentIndex, segmentRatio: ratio,
      sceneX: lerp(start.sceneX, end.sceneX, ratio), sceneY: lerp(start.sceneY, end.sceneY, ratio),
      sceneZ: lerp(start.sceneZ, end.sceneZ, ratio), screenX, screenY,
      screenDistancePx: Math.hypot(pointer.x - screenX, pointer.y - screenY), pathPx: targetPathPx,
    };
  }
  return null;
}

function stationAtPathIndex(
  path: readonly number[],
  targetPathPx: number,
): number {
  let low = 0;
  let high = path.length - 1;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (path[middle] < targetPathPx) low = middle + 1;
    else high = middle;
  }
  return Math.max(0, Math.min(path.length - 1, low));
}

function pointAtPath(
  stations: readonly WbvProjectedTrajectoryStation[],
  path: readonly number[],
  targetPathPx: number,
): WbvScreenPointer {
  const total = path[path.length - 1] ?? 0;
  const target = clamp(targetPathPx, 0, total);
  const upper = stationAtPathIndex(path, target);
  if (upper <= 0) return { x: stations[0].screenX, y: stations[0].screenY };
  const lower = upper - 1;
  const span = Math.max(0.0001, path[upper] - path[lower]);
  const ratio = clamp((target - path[lower]) / span, 0, 1);
  return {
    x: lerp(stations[lower].screenX, stations[upper].screenX, ratio),
    y: lerp(stations[lower].screenY, stations[upper].screenY, ratio),
  };
}

function normalizedAngleDelta(first: number, second: number): number {
  let delta = second - first;
  while (delta > Math.PI) delta -= Math.PI * 2;
  while (delta < -Math.PI) delta += Math.PI * 2;
  return delta;
}

/**
 * Measures distributed screen-space curvature around a path location.  The
 * window is defined in pixels rather than survey rows or MD, so it remains
 * applicable to wells with different survey spacing, zoom levels and shapes.
 */
function cumulativeTurnAngleDeg(
  stations: readonly WbvProjectedTrajectoryStation[],
  path: readonly number[],
  centerPathPx: number,
  radiusPx: number,
): number {
  const total = path[path.length - 1] ?? 0;
  if (stations.length < 3 || total <= 0) return 0;
  const start = clamp(centerPathPx - radiusPx, 0, total);
  const end = clamp(centerPathPx + radiusPx, 0, total);
  if (end - start < 4) return 0;
  const samples = 6;
  let previous = pointAtPath(stations, path, start);
  let previousHeading: number | null = null;
  let accumulated = 0;
  for (let index = 1; index <= samples; index += 1) {
    const current = pointAtPath(stations, path, lerp(start, end, index / samples));
    const dx = current.x - previous.x;
    const dy = current.y - previous.y;
    const length = Math.hypot(dx, dy);
    if (length > 0.25) {
      const heading = Math.atan2(dy, dx);
      if (previousHeading !== null) accumulated += Math.abs(normalizedAngleDelta(previousHeading, heading));
      previousHeading = heading;
    }
    previous = current;
  }
  return accumulated * 180 / Math.PI;
}

export function createContinuousProjectedTracker(
  initialPointer: WbvScreenPointer,
  initialStations: readonly WbvProjectedTrajectoryStation[],
  hitTolerancePx = 20,
): WbvContinuousProjectedTracker | null {
  const initial = projectPointerToWellbore(initialPointer, initialStations, hitTolerancePx);
  if (!initial) return null;
  let previousPointer = initialPointer;
  let lastPathPx = cumulativePath(initialStations)[initial.segmentIndex]
    + Math.hypot(
      initialStations[initial.segmentIndex + 1].screenX - initialStations[initial.segmentIndex].screenX,
      initialStations[initial.segmentIndex + 1].screenY - initialStations[initial.segmentIndex].screenY,
    ) * initial.segmentRatio;
  let direction = 0;

  return {
    update(pointer, stations) {
      if (stations.length < 2) return null;
      const path = cumulativePath(stations);
      const totalPathPx = path[path.length - 1];
      const tangentUpper = stationAtPathIndex(path, lastPathPx);
      const tangentSegment = Math.min(stations.length - 2, Math.max(0, tangentUpper - 1));
      const tangentDx = stations[tangentSegment + 1].screenX - stations[tangentSegment].screenX;
      const tangentDy = stations[tangentSegment + 1].screenY - stations[tangentSegment].screenY;
      const tangentLength = Math.hypot(tangentDx, tangentDy) || 1;
      const pointerDx = pointer.x - previousPointer.x;
      const pointerDy = pointer.y - previousPointer.y;
      const along = pointerDx * tangentDx / tangentLength + pointerDy * tangentDy / tangentLength;
      const predicted = clamp(lastPathPx + along, 0, totalPathPx);
      const pointerStep = Math.hypot(pointerDx, pointerDy);
      const windowPx = clamp(55 + pointerStep * 5, 35, 180);
      let best: (ContinuousCandidate & { score: number }) | null = null;
      for (let segmentIndex = 0; segmentIndex < stations.length - 1; segmentIndex += 1) {
        if (path[segmentIndex + 1] < predicted - windowPx || path[segmentIndex] > predicted + windowPx) continue;
        const candidate = candidateForSegment(pointer, stations, path, segmentIndex);
        if (!candidate) continue;
        const reversePenalty = direction !== 0 && (candidate.pathPx - lastPathPx) * direction < 0 ? 18 : 0;
        const score = candidate.screenDistancePx + Math.abs(candidate.pathPx - predicted) * 0.18 + reversePenalty;
        if (!best || score < best.score) best = { ...candidate, score };
      }
      previousPointer = pointer;
      if (!best) return null;
      if (Math.abs(along) > 0.35) direction = Math.sign(along);

      const ordinaryMaxStep = clamp(25 + pointerStep * 5, 20, 120);
      const curvatureRadiusPx = clamp(45 + pointerStep * 2, 40, 90);
      const turnAngleDeg = cumulativeTurnAngleDeg(stations, path, (lastPathPx + best.pathPx) * 0.5, curvatureRadiusPx);
      const curvatureWeight = clamp((turnAngleDeg - 7) / 25, 0, 1);
      const curvedMaxStep = clamp(7 + pointerStep * 1.5, 7, 20);
      const maxStep = lerp(ordinaryMaxStep, curvedMaxStep, curvatureWeight);

      let accepted: ContinuousCandidate = best;
      if (Math.abs(best.pathPx - lastPathPx) > maxStep) {
        const boundedPath = clamp(lastPathPx + Math.sign(best.pathPx - lastPathPx) * maxStep, 0, totalPathPx);
        accepted = candidateAtPath(pointer, stations, path, boundedPath) ?? best;
      }
      lastPathPx = accepted.pathPx;
      return accepted;
    },
  };
}
