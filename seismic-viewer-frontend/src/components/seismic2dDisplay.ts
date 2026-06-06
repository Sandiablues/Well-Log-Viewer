export type DisplayMode = 'raster' | 'wiggle' | 'raster_wiggle';

export type RasterColorMap =
  | 'gray_balanced'
  | 'gray_high_contrast'
  | 'reverse_gray'
  | 'seismic_rwb'
  | 'seismic_bwr'
  | 'black_white_black'
  | 'brown_white_blue'
  | 'blue_white_brown';

export type Normalized2DDisplayMode = 'raster' | 'wiggle' | 'raster-wiggle';

export type TraceStepMode = 'auto' | string | number;

export type DisplayPresetId =
  | 'standard_interpretation'
  | 'high_contrast_dip'
  | 'polarity_qc'
  | 'wiggle_qc'
  | 'image_wiggle'
  | 'soft_regional';

export type TraceStepResult = {
  decimation: number;
  drawnTraceCount: number;
  baseTraceSpacing: number;
};

export type WiggleScaleResult = {
  traceSpacingFactor: number;
  nominalTraceSpacing: number;
  userScale: number;
  ampScale: number;
  maxExcursion: number;
  lineWidth: number;
};

export type Rgb = {
  r: number;
  g: number;
  b: number;
};

export function clampNumber(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min;
  return Math.max(min, Math.min(max, value));
}

export function clampNormalizedAmplitude(value: number, limit = 1): number {
  const safeLimit = Math.max(1e-12, Math.abs(limit));
  return clampNumber(value, -safeLimit, safeLimit);
}

export function computeSymmetricClipAbs(rawClipAbs: unknown, fallback = 1): number {
  const clipAbs = Math.abs(Number(rawClipAbs));
  const fallbackAbs = Math.abs(Number(fallback));

  if (Number.isFinite(clipAbs) && clipAbs > 1e-12) return clipAbs;
  if (Number.isFinite(fallbackAbs) && fallbackAbs > 1e-12) return fallbackAbs;

  return 1;
}

export function normalize2DDisplayMode(mode: DisplayMode): Normalized2DDisplayMode {
  if (mode === 'wiggle') return 'wiggle';
  if (mode === 'raster_wiggle') return 'raster-wiggle';
  return 'raster';
}

function interpolateChannel(a: number, b: number, fraction: number): number {
  return Math.round(clampNumber(a + (b - a) * fraction, 0, 255));
}

function interpolateRgb(a: Rgb, b: Rgb, fraction: number): Rgb {
  const t = clampNumber(fraction, 0, 1);
  return {
    r: interpolateChannel(a.r, b.r, t),
    g: interpolateChannel(a.g, b.g, t),
    b: interpolateChannel(a.b, b.b, t),
  };
}

function divergingColor(norm: number, negative: Rgb, zero: Rgb, positive: Rgb): Rgb {
  const value = clampNormalizedAmplitude(norm, 1);
  if (value < 0) return interpolateRgb(zero, negative, Math.abs(value));
  return interpolateRgb(zero, positive, value);
}

function signPreservingGamma(norm: number, gamma: number): number {
  const value = clampNormalizedAmplitude(norm, 1);
  return Math.sign(value) * Math.pow(Math.abs(value), Math.max(0.05, gamma));
}

export function computeGrayValue(normalizedAmplitude: number): number {
  const norm = clampNormalizedAmplitude(normalizedAmplitude, 1);
  return Math.round(clampNumber(128 + norm * 127, 0, 255));
}

export function computeColorValue(normalizedAmplitude: number): Rgb {
  return computeRasterColorValue(normalizedAmplitude, 'seismic_bwr');
}

export function computeRasterColorValue(
  normalizedAmplitude: number,
  colorMap: RasterColorMap = 'gray_balanced'
): Rgb {
  const norm = clampNormalizedAmplitude(normalizedAmplitude, 1);

  switch (colorMap) {
    case 'gray_high_contrast': {
      const enhanced = signPreservingGamma(norm, 0.72);
      const gray = Math.round(clampNumber(128 + enhanced * 127, 0, 255));
      return { r: gray, g: gray, b: gray };
    }

    case 'reverse_gray': {
      const gray = Math.round(clampNumber(128 - norm * 127, 0, 255));
      return { r: gray, g: gray, b: gray };
    }

    case 'seismic_rwb':
      return divergingColor(
        norm,
        { r: 180, g: 0, b: 0 },
        { r: 255, g: 255, b: 255 },
        { r: 0, g: 65, b: 190 }
      );

    case 'seismic_bwr':
      return divergingColor(
        norm,
        { r: 0, g: 65, b: 190 },
        { r: 255, g: 255, b: 255 },
        { r: 180, g: 0, b: 0 }
      );

    case 'black_white_black': {
      const gray = Math.round((1 - clampNumber(Math.abs(norm), 0, 1)) * 255);
      return { r: gray, g: gray, b: gray };
    }

    case 'brown_white_blue':
      return divergingColor(
        norm,
        { r: 150, g: 95, b: 45 },
        { r: 255, g: 255, b: 255 },
        { r: 50, g: 90, b: 210 }
      );

    case 'blue_white_brown':
      return divergingColor(
        norm,
        { r: 50, g: 90, b: 210 },
        { r: 255, g: 255, b: 255 },
        { r: 150, g: 95, b: 45 }
      );

    case 'gray_balanced':
    default: {
      const gray = computeGrayValue(norm);
      return { r: gray, g: gray, b: gray };
    }
  }
}

export function computeTraceStep(
  traceCount: number,
  traceDecimation: TraceStepMode,
  targetAutoTraces = 95
): TraceStepResult {
  const safeTraceCount = Math.max(1, Math.floor(Number(traceCount) || 1));
  const safeTarget = Math.max(1, Math.floor(Number(targetAutoTraces) || 95));

  const decimation =
    traceDecimation === 'auto'
      ? Math.max(1, Math.ceil(safeTraceCount / safeTarget))
      : Math.max(1, Math.floor(Number(traceDecimation) || 1));

  const drawnTraceCount = Math.max(1, Math.ceil(safeTraceCount / decimation));
  const baseTraceSpacing = safeTraceCount / Math.max(1, drawnTraceCount);

  return { decimation, drawnTraceCount, baseTraceSpacing };
}

export function computeWiggleScale(
  baseTraceSpacing: number,
  wiggleTraceSpacing: number,
  wiggleScale: number
): WiggleScaleResult {
  const safeBaseTraceSpacing = Math.max(1e-6, Number(baseTraceSpacing) || 1);
  const traceSpacingFactor = clampNumber(Number(wiggleTraceSpacing) || 1, 0.5, 3.0);
  const nominalTraceSpacing = safeBaseTraceSpacing * traceSpacingFactor;
  const userScale = clampNumber(Number(wiggleScale) || 1, 0.1, 5.0);
  const ampScale = nominalTraceSpacing * 0.62 * userScale;
  const maxExcursion = nominalTraceSpacing * 0.85;
  const lineWidth = nominalTraceSpacing >= 10 ? 0.85 : 0.65;

  return {
    traceSpacingFactor,
    nominalTraceSpacing,
    userScale,
    ampScale,
    maxExcursion,
    lineWidth,
  };
}

export type WiggleRenderStyle = {
  positiveFillStyle: string;
  negativeFillStyle: string;
  traceStrokeStyle: string;
  traceLineWidth: number;
  zeroLineStrokeStyle: string;
  zeroLineWidth: number;
  zeroLineDash: number[];
};

export function computeWiggleRenderStyle(
  mode: DisplayMode,
  nominalTraceSpacing: number,
  baseLineWidth: number
): WiggleRenderStyle {
  const overlayOnImage = mode === 'raster_wiggle';
  const safeSpacing = Math.max(1e-6, Number(nominalTraceSpacing) || 1);
  const safeBaseLineWidth = clampNumber(Number(baseLineWidth) || 0.65, 0.35, 1.4);

  return {
    positiveFillStyle: overlayOnImage ? 'rgba(0,0,0,0.24)' : 'rgba(0,0,0,0.52)',
    negativeFillStyle: overlayOnImage ? 'rgba(60,60,60,0.16)' : 'rgba(60,60,60,0.34)',
    traceStrokeStyle: overlayOnImage ? 'rgba(0,0,0,0.88)' : '#000000',
    traceLineWidth: overlayOnImage
      ? clampNumber(safeBaseLineWidth * 0.9, 0.45, 0.9)
      : safeBaseLineWidth,
    zeroLineStrokeStyle: overlayOnImage ? 'rgba(0,0,0,0.62)' : 'rgba(30,30,30,0.78)',
    zeroLineWidth: overlayOnImage
      ? clampNumber(safeSpacing * 0.075, 0.75, 1.35)
      : clampNumber(safeSpacing * 0.085, 0.85, 1.45),
    zeroLineDash: [],
  };
}

export function formatDisplayModeLabel(mode: DisplayMode): string {
  switch (mode) {
    case 'raster':
      return 'Raster';
    case 'wiggle':
      return 'Wiggle';
    case 'raster_wiggle':
      return 'Raster + Wiggle';
    default:
      return String(mode || '—');
  }
}

export function formatRasterColorMapLabel(colorMap: RasterColorMap): string {
  switch (colorMap) {
    case 'gray_balanced':
      return 'Gray balanced';
    case 'gray_high_contrast':
      return 'Gray high contrast';
    case 'reverse_gray':
      return 'Reverse gray';
    case 'seismic_rwb':
      return 'Seismic R-W-B';
    case 'seismic_bwr':
      return 'Seismic B-W-R';
    case 'black_white_black':
      return 'Black-white-black';
    case 'brown_white_blue':
      return 'Brown-white-blue';
    case 'blue_white_brown':
      return 'Blue-white-brown';
    default:
      return String(colorMap || '—');
  }
}

export function formatDisplayPresetLabel(presetId: DisplayPresetId): string {
  switch (presetId) {
    case 'standard_interpretation':
      return 'Standard interpretation';
    case 'high_contrast_dip':
      return 'High-contrast dip';
    case 'polarity_qc':
      return 'Polarity QC';
    case 'wiggle_qc':
      return 'Wiggle QC';
    case 'image_wiggle':
      return 'Raster + Wiggle';
    case 'soft_regional':
      return 'Soft regional';
    default:
      return String(presetId || '—');
  }
}

export type ProcessingChainInput = {
  processingMode: 'raw' | 'demean' | 'trace_rms' | 'agc' | string;
  frequencyFilter: 'none' | 'bandpass' | string;
  agcWindowSec: number;
  clipPercentile: number;
  gain: number;
  reversePolarity: boolean;
  rasterColorMap: RasterColorMap;
  displayMode: DisplayMode;
};

export function build2DProcessingChain(input: ProcessingChainInput): string {
  const processLabel = (() => {
    switch (input.processingMode) {
      case 'raw':
        return 'Raw';
      case 'demean':
        return 'Demean';
      case 'trace_rms':
        return 'Trace RMS';
      case 'agc':
        return `AGC ${Number(input.agcWindowSec || 0).toFixed(1)}s`;
      default:
        return String(input.processingMode || 'Unknown');
    }
  })();

  const filterLabel =
    input.frequencyFilter === 'bandpass'
      ? 'Bandpass 8/12/80/100 Hz'
      : 'Filter off';

  const clip = Number(input.clipPercentile);
  const clipLabel = Number.isFinite(clip) ? `Clip P${clip}` : 'Clip —';

  const gain = Number(input.gain);
  const gainLabel = Number.isFinite(gain) ? `Gain ${gain.toFixed(1)}×` : 'Gain —';

  const polarityLabel = input.reversePolarity ? 'Reverse polarity' : 'Normal polarity';

  return [
    processLabel,
    filterLabel,
    clipLabel,
    gainLabel,
    polarityLabel,
  ].join(' → ');
}
