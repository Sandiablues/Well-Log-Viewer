export type Active3DSliceAxis = 'inline' | 'crossline' | 'time';

export type Active3DColorMode = 'grayscale' | 'color';

export type Active3DQualityMode = 'preview' | 'balanced' | 'high';

export type Active3DSourceAxis = 'inline' | 'crossline' | 'sample';

export type Active3DSourceBounds = {
  xStart: number;
  xEnd: number;
  yStart: number;
  yEnd: number;
};

export type Active3DOutputShape = {
  width: number;
  height: number;
};

export type Active3DSliceWindowRequest = {
  representationId: string;
  axis: Active3DSliceAxis;
  sliceIndex: number;
  sourceBounds: Active3DSourceBounds;
  outputShape: Active3DOutputShape;
  clipPercentile: number;
  gain: number;
  reversePolarity: boolean;
  colorMode: Active3DColorMode;
  quality: Active3DQualityMode;
};

export type Active3DAxisMapping = {
  fixedAxis: Active3DSourceAxis;
  sourceXAxis: Active3DSourceAxis;
  sourceYAxis: Active3DSourceAxis;
};

export const ACTIVE_3D_AXIS_MAPPING: Record<Active3DSliceAxis, Active3DAxisMapping> = {
  inline: {
    fixedAxis: 'inline',
    sourceXAxis: 'crossline' as Active3DSourceAxis,
    sourceYAxis: 'sample',
  },
  crossline: {
    fixedAxis: 'crossline' as Active3DSourceAxis,
    sourceXAxis: 'inline',
    sourceYAxis: 'sample',
  },
  time: {
    fixedAxis: 'sample',
    sourceXAxis: 'inline',
    sourceYAxis: 'crossline' as Active3DSourceAxis,
  },
};

export function clampActive3DNumber(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min;
  return Math.max(min, Math.min(max, value));
}

export function normalizeActive3DSourceBounds(bounds: Active3DSourceBounds): Active3DSourceBounds {
  const xStart = Math.min(bounds.xStart, bounds.xEnd);
  const xEnd = Math.max(bounds.xStart, bounds.xEnd);
  const yStart = Math.min(bounds.yStart, bounds.yEnd);
  const yEnd = Math.max(bounds.yStart, bounds.yEnd);

  return {
    xStart,
    xEnd,
    yStart,
    yEnd,
  };
}

export function buildActive3DSliceWindowCacheKey(request: Active3DSliceWindowRequest): string {
  const bounds = normalizeActive3DSourceBounds(request.sourceBounds);
  return [
    request.representationId,
    request.axis,
    String(request.sliceIndex),
    bounds.xStart.toFixed(3),
    bounds.xEnd.toFixed(3),
    bounds.yStart.toFixed(3),
    bounds.yEnd.toFixed(3),
    String(request.outputShape.width),
    String(request.outputShape.height),
    String(request.clipPercentile),
    String(request.gain),
    request.reversePolarity ? 'reverse' : 'normal',
    request.colorMode,
    request.quality,
  ].join('|');
}

export function buildActive3DSliceWindowQuery(request: Active3DSliceWindowRequest): URLSearchParams {
  const bounds = normalizeActive3DSourceBounds(request.sourceBounds);
  const params = new URLSearchParams();

  params.set('axis', request.axis);
  params.set('slice_index', String(request.sliceIndex));
  params.set('source_x_start', String(bounds.xStart));
  params.set('source_x_end', String(bounds.xEnd));
  params.set('source_y_start', String(bounds.yStart));
  params.set('source_y_end', String(bounds.yEnd));
  params.set('output_width', String(request.outputShape.width));
  params.set('output_height', String(request.outputShape.height));
  params.set('clip_percentile', String(request.clipPercentile));
  params.set('gain', String(request.gain));
  params.set('reverse_polarity', request.reversePolarity ? 'true' : 'false');
  params.set('color_mode', request.colorMode);
  params.set('quality', request.quality);

  return params;
}


export type Active3DSourceShape = {
  inlineCount: number;
  crosslineCount: number;
  sampleCount: number;
};

export type Active3DSliceIndices = {
  inline: number;
  crossline: number;
  time: number;
};

export function getActive3DSliceIndex(axis: Active3DSliceAxis, indices: Active3DSliceIndices): number {
  if (axis === 'inline') return indices.inline;
  if (axis === 'crossline') return indices.crossline;
  return indices.time;
}

export function getActive3DSourceAxisCount(axis: Active3DSourceAxis, shape: Active3DSourceShape): number {
  if (axis === 'inline') return Math.max(1, Math.floor(shape.inlineCount));
  if (axis === 'crossline') return Math.max(1, Math.floor(shape.crosslineCount));
  return Math.max(1, Math.floor(shape.sampleCount));
}

export function buildWholeSliceSourceBoundsForAxis(
  axis: Active3DSliceAxis,
  shape: Active3DSourceShape,
): Active3DSourceBounds {
  const mapping = ACTIVE_3D_AXIS_MAPPING[axis];
  const xCount = getActive3DSourceAxisCount(mapping.sourceXAxis, shape);
  const yCount = getActive3DSourceAxisCount(mapping.sourceYAxis, shape);

  return {
    xStart: 0,
    xEnd: Math.max(0, xCount - 1),
    yStart: 0,
    yEnd: Math.max(0, yCount - 1),
  };
}

export function formatActive3DSourceBounds(bounds: Active3DSourceBounds): string {
  const normalized = normalizeActive3DSourceBounds(bounds);
  return `x ${normalized.xStart.toFixed(0)}-${normalized.xEnd.toFixed(0)}, y ${normalized.yStart.toFixed(0)}-${normalized.yEnd.toFixed(0)}`;
}
