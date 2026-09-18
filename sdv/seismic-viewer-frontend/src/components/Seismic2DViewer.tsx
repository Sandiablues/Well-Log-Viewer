import React, { useEffect, useRef, useState } from 'react';
import { fetchSection2D, fetchSection2DWindow, fetchSlice, getZarrMetadata } from '../services/zarrService';
import { formatAxisLabel, getVerticalAxis } from '../utils/axisInfo';
import {
  clampNormalizedAmplitude,
  computeRasterColorValue,
  computeSymmetricClipAbs,
  computeTraceStep,
  computeWiggleRenderStyle,
  computeWiggleScale,
  formatDisplayModeLabel,
  formatDisplayPresetLabel,
  formatRasterColorMapLabel,
  build2DProcessingChain,
  type DisplayMode,
  type DisplayPresetId,
  type RasterColorMap,
} from './seismic2dDisplay';
import Seismic2DControlsPanel from './Seismic2DControlsPanel';


function format2DTickValue(value: number, discrete = false): string {
  if (!Number.isFinite(value)) return '—';

  if (discrete) {
    return String(Math.round(value));
  }

  if (Math.abs(value) >= 1000) {
    return Number.isInteger(value) ? value.toFixed(0) : value.toFixed(1);
  }

  if (Number.isInteger(value)) {
    return value.toFixed(0);
  }

  return Number(value.toFixed(3)).toString();
}

function get2DShape(lineInfo: any): number[] {
  const shape = lineInfo?.metadata?.shape || lineInfo?.metadata?.zarr?.shape || lineInfo?.shape;
  return Array.isArray(shape) ? shape : [];
}

function get2DAxisDisplayInfo(lineInfo: any) {
  const metadata = lineInfo?.metadata || {};
  const shape = get2DShape(lineInfo);

  const traceCount =
    Number(metadata.trace_count || metadata.zarr?.trace_count || lineInfo?.trace_count || shape?.[0] || 0);

  const sampleCount =
    Number(metadata.sample_count || metadata.zarr?.sample_count || lineInfo?.sample_count || shape?.[1] || 0);

  const verticalAxis = getVerticalAxis(lineInfo);

  const verticalMin =
    verticalAxis?.min !== null && verticalAxis?.min !== undefined
      ? Number(verticalAxis.min)
      : 0;

  const verticalMax =
    verticalAxis?.max !== null && verticalAxis?.max !== undefined
      ? Number(verticalAxis.max)
      : Math.max(0, sampleCount - 1);

  const verticalLabel = verticalAxis ? formatAxisLabel(verticalAxis) : 'Sample';
  const verticalUnit = verticalAxis?.unit && !['index', 'number', 'sample'].includes(String(verticalAxis.unit))
    ? String(verticalAxis.unit)
    : '';

  return {
    horizontal: {
      label: 'Trace',
      min: 0,
      max: Math.max(0, traceCount - 1),
      discrete: true,
    },
    vertical: {
      label: verticalUnit ? `${verticalLabel} (${verticalUnit})` : verticalLabel,
      min: Number.isFinite(verticalMin) ? verticalMin : 0,
      max: Number.isFinite(verticalMax) ? verticalMax : Math.max(0, sampleCount - 1),
      discrete: !verticalAxis,
    },
  };
}

interface Seismic2DViewerProps {
  zarrPath: string;
  dim: number;
  lineInfo?: any;
  surveyName?: string;
  defaultShowLineInfo?: boolean;
  controlledShowLineInfo?: boolean;
  showLineInfoControl?: boolean;
  emptyState?: boolean;
  emptyStateMessage?: string;
  canvasBackground?: string;
}

type ProcessingMode = 'raw' | 'demean' | 'trace_rms' | 'agc';

type SourceWindow2D = {
  traceStart: number;
  traceEnd: number;
  sampleStart: number;
  sampleEnd: number;
};

type PanDrag2D = {
  active: boolean;
  startXCanvas: number;
  startYCanvas: number;
  currentXCanvas: number;
  currentYCanvas: number;
  startWindow: SourceWindow2D;
};

const MIN_WINDOW_TRACES = 8;
const MIN_WINDOW_SAMPLES = 16;
const STEP_ZOOM_FACTOR = 1.35;
const WINDOW_RENDER_MIN_WIDTH = 800;
const WINDOW_RENDER_MIN_HEIGHT = 600;
const WINDOW_RENDER_MAX_WIDTH = 2400;
const WINDOW_RENDER_MAX_HEIGHT = 1800;

function clampNumber(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function clampWindowRange(start: number, end: number, minSize: number, maxCount: number): [number, number] {
  const safeMax = Math.max(1, Math.floor(maxCount));
  const safeMinSize = Math.max(1, Math.min(Math.floor(minSize), safeMax));

  let s = Math.floor(clampNumber(Math.min(start, end), 0, safeMax - 1));
  let e = Math.ceil(clampNumber(Math.max(start, end), s + 1, safeMax));

  if (e - s < safeMinSize) {
    const center = (s + e) / 2;
    s = Math.floor(center - safeMinSize / 2);
    e = s + safeMinSize;

    if (s < 0) {
      s = 0;
      e = safeMinSize;
    }

    if (e > safeMax) {
      e = safeMax;
      s = Math.max(0, e - safeMinSize);
    }
  }

  return [s, e];
}

function shiftWindowRange(start: number, end: number, shift: number, maxCount: number): [number, number] {
  const safeMax = Math.max(1, Math.floor(maxCount));
  const width = Math.max(1, Math.min(safeMax, Math.round(end - start)));

  let nextStart = Math.round(start + shift);
  let nextEnd = nextStart + width;

  if (nextStart < 0) {
    nextStart = 0;
    nextEnd = width;
  }

  if (nextEnd > safeMax) {
    nextEnd = safeMax;
    nextStart = Math.max(0, safeMax - width);
  }

  return [nextStart, nextEnd];
}

function centeredWindowRange(center: number, size: number, minSize: number, maxCount: number): [number, number] {
  const safeMax = Math.max(1, Math.floor(maxCount));
  const safeMinSize = Math.max(1, Math.min(Math.floor(minSize), safeMax));
  const safeSize = Math.max(safeMinSize, Math.min(safeMax, Math.round(size)));

  let start = Math.round(center - safeSize / 2);
  let end = start + safeSize;

  if (start < 0) {
    start = 0;
    end = safeSize;
  }

  if (end > safeMax) {
    end = safeMax;
    start = Math.max(0, end - safeSize);
  }

  return [start, end];
}

function readSourceWindow(windowInfo: any, sourceShape: number[] | undefined): SourceWindow2D {
  const sourceTraceCount = Math.max(1, Number(sourceShape?.[0] || 1));
  const sourceSampleCount = Math.max(1, Number(sourceShape?.[1] || 1));

  return {
    traceStart: Number(windowInfo?.trace_start ?? windowInfo?.traceStart ?? 0),
    traceEnd: Number(windowInfo?.trace_end ?? windowInfo?.traceEnd ?? sourceTraceCount),
    sampleStart: Number(windowInfo?.sample_start ?? windowInfo?.sampleStart ?? 0),
    sampleEnd: Number(windowInfo?.sample_end ?? windowInfo?.sampleEnd ?? sourceSampleCount),
  };
}


function formatRenderMs(value: any): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  if (n >= 1000) return `${(n / 1000).toFixed(2)} s`;
  return `${Math.round(n)} ms`;
}

function formatPixelCount(value: any): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  if (n >= 1000000) return `${(n / 1000000).toFixed(2)} MP`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)} kpx`;
  return `${Math.round(n)} px`;
}

function formatLineInfoValue(value: any): string {
  if (value === null || value === undefined || value === '') return '—';
  if (Array.isArray(value)) return value.join(' × ');
  return String(value);
}

function LineInfoRow({ label, value }: { label: string; value: any }) {
  return (
    <>
      <div className="mv-sdv3d-metadata-label">{label}</div>
      <div className="mv-type-property-value">{formatLineInfoValue(value)}</div>
    </>
  );
}


type Seismic2DOptionPanelOpenState = {
  display: boolean;
  amplitude: boolean;
  wiggle: boolean;
  gridAxis: boolean;
  zoom: boolean;
};

const seismic2DOptionPanelOpenState: Seismic2DOptionPanelOpenState = {
  display: true,
  amplitude: true,
  wiggle: false,
  gridAxis: false,
  zoom: false,
};

export const Seismic2DViewer: React.FC<Seismic2DViewerProps> = ({
  zarrPath,
  dim,
  lineInfo,
  surveyName,
  defaultShowLineInfo = true,
  controlledShowLineInfo,
  showLineInfoControl = true,
  canvasBackground = '#000',
  emptyState = false,
  emptyStateMessage = 'No data loaded',
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const renderRequestSeqRef = useRef(0);

  const [index, setIndex] = useState(0);
  const [metadata, setMetadata] = useState<any>(emptyState ? { shape: [0, 0] } : null);
  const [gain, setGain] = useState(1.0);
  const [clipPercentile, setClipPercentile] = useState(99.0);
  const [processingMode, setProcessingMode] = useState<ProcessingMode>('demean');
  const [displayMode, setDisplayMode] = useState<DisplayMode>('raster');
  const [rasterColorMap, setRasterColorMap] = useState<RasterColorMap>('gray_balanced');
  const [displayPreset, setDisplayPreset] = useState<DisplayPresetId>('standard_interpretation');
  const [fitToWidth, setFitToWidth] = useState(true);
  const [reversePolarity, setReversePolarity] = useState(false);
  const [reverseDirection, setReverseDirection] = useState(false);
  const [xScale, setXScale] = useState(1.0);
  const [yScale, setYScale] = useState(1.0);
  const [wiggleScale, setWiggleScale] = useState(1.0);
  const [traceDecimation, setTraceDecimation] = useState('auto');
  const [wiggleStyle, setWiggleStyle] = useState<'line' | 'variable_area'>('variable_area');
  const [wiggleFill, setWiggleFill] = useState<'none' | 'positive' | 'negative' | 'both'>('positive');
  const [wiggleTraceSpacing, setWiggleTraceSpacing] = useState(1.0);
  const [showWiggleZeroLine, setShowWiggleZeroLine] = useState(true);
  const [showTimelines, setShowTimelines] = useState(false);
  const [showAxisLabels, setShowAxisLabels] = useState(true);
  const [menuCollapsed, setMenuCollapsed] = useState(false);
  const [displayControlsOpen, setDisplayControlsOpen] = useState(() => seismic2DOptionPanelOpenState.display);
  const [amplitudeControlsOpen, setAmplitudeControlsOpen] = useState(() => seismic2DOptionPanelOpenState.amplitude);
  const [wiggleControlsOpen, setWiggleControlsOpen] = useState(() => seismic2DOptionPanelOpenState.wiggle);
  const [gridAxisControlsOpen, setGridAxisControlsOpen] = useState(() => seismic2DOptionPanelOpenState.gridAxis);
  const [zoomControlsOpen, setZoomControlsOpen] = useState(() => seismic2DOptionPanelOpenState.zoom);
  const [timelineIntervalMs, setTimelineIntervalMs] = useState(250);
  const [sectionInfo, setSectionInfo] = useState<any>(null);
  const [cursorInfo, setCursorInfo] = useState<any>(null);
  const [showLineInfoDrawer, setShowLineInfoDrawer] = useState(defaultShowLineInfo);
  const effectiveShowLineInfoDrawer = controlledShowLineInfo ?? showLineInfoDrawer;
  const [lineInfoCollapsed, setLineInfoCollapsed] = useState(false);
  const [zoomDrag, setZoomDrag] = useState<any>(null);
  const [panDrag, setPanDrag] = useState<PanDrag2D | null>(null);
  const [sourceWindow, setSourceWindow] = useState<SourceWindow2D | null>(null);
  const [renderError, setRenderError] = useState<string | null>(null);
  const [boxZoomEnabled, setBoxZoomEnabled] = useState(false);
  const [agcWindowSec, setAgcWindowSec] = useState(0.5);
  const [frequencyFilter, setFrequencyFilter] = useState<'none' | 'bandpass'>('none');

  useEffect(() => {
    seismic2DOptionPanelOpenState.display = displayControlsOpen;
    seismic2DOptionPanelOpenState.amplitude = amplitudeControlsOpen;
    seismic2DOptionPanelOpenState.wiggle = wiggleControlsOpen;
    seismic2DOptionPanelOpenState.gridAxis = gridAxisControlsOpen;
    seismic2DOptionPanelOpenState.zoom = zoomControlsOpen;
  }, [
    displayControlsOpen,
    amplitudeControlsOpen,
    wiggleControlsOpen,
    gridAxisControlsOpen,
    zoomControlsOpen,
  ]);

  useEffect(() => {
    setSourceWindow(null);
    setPanDrag(null);
    setZoomDrag(null);
    setBoxZoomEnabled(false);
    setRenderError(null);

    if (emptyState || !zarrPath) {
      setMetadata({ shape: [0, 0] });
      setSectionInfo(null);
      setCursorInfo(null);
      return;
    }

    getZarrMetadata(zarrPath).then(setMetadata);
  }, [zarrPath, emptyState]);

  useEffect(() => {
    async function renderSection() {
      if (emptyState || !canvasRef.current || !metadata) return;

      const renderRequestId = ++renderRequestSeqRef.current;

      const isTrue2DLine = metadata.shape?.length === 2;

      const sourceShape = Array.isArray(metadata?.shape) ? metadata.shape : [];
      const renderTarget = (() => {
        if (!sourceWindow) return { width: 1600, height: 900 };

        const viewport = viewportRef.current;
        const viewportWidth = Math.max(1, Number(viewport?.clientWidth || 1600));
        const viewportHeight = Math.max(1, Number(viewport?.clientHeight || 900));
        const axisWidthAllowance = showAxisLabels ? 96 : 24;
        const axisHeightAllowance = showAxisLabels ? 72 : 24;

        return {
          width: Math.round(clampNumber(viewportWidth - axisWidthAllowance, WINDOW_RENDER_MIN_WIDTH, WINDOW_RENDER_MAX_WIDTH)),
          height: Math.round(clampNumber(viewportHeight - axisHeightAllowance, WINDOW_RENDER_MIN_HEIGHT, WINDOW_RENDER_MAX_HEIGHT)),
        };
      })();

      const requestStartedAt = typeof performance !== 'undefined' ? performance.now() : Date.now();

      const slice = isTrue2DLine
        ? sourceWindow
          ? await fetchSection2DWindow(
              zarrPath,
              sourceWindow.traceStart,
              sourceWindow.traceEnd,
              sourceWindow.sampleStart,
              sourceWindow.sampleEnd,
              renderTarget.width,
              renderTarget.height,
              clipPercentile,
              processingMode,
              agcWindowSec,
              frequencyFilter,
              8,
              12,
              80,
              100
            )
          : await fetchSection2D(
              zarrPath,
              1600,
              900,
              clipPercentile,
              processingMode,
              agcWindowSec,
              frequencyFilter,
              8,
              12,
              80,
              100
            )
        : await fetchSlice(zarrPath, dim, index);

      if (renderRequestId !== renderRequestSeqRef.current) return;

      const requestFinishedAt = typeof performance !== 'undefined' ? performance.now() : Date.now();
      const requestElapsedMs = Math.max(0, requestFinishedAt - requestStartedAt);
      const renderMode = Boolean(slice.windowed) ? 'window' : 'preview';

      setSectionInfo({
        sourceShape: slice.source_shape || slice.shape,
        previewShape: slice.shape,
        traceStride: slice.trace_stride || 1,
        sampleStride: slice.sample_stride || 1,
        sampleIntervalMs:
          Number(metadata?.sample_interval_ms || 0) ||
          Number(metadata?.sample_rate || 0) ||
          Number(metadata?.volume?.sample_interval_ms || 0) ||
          Number(metadata?.zarr?.sample_interval_ms || 0) ||
          Number(metadata?.sample_interval_us || 0) / 1000 ||
          Number(metadata?.volume?.sample_interval_us || 0) / 1000 ||
          Number(metadata?.zarr?.sample_interval_us || 0) / 1000 ||
          Number(slice.sample_interval_ms || 0) ||
          Number(slice.processing?.sample_interval_sec || 0) * 1000,
        clipAbs: slice.clip_abs,
        clipPercentile: slice.clip_percentile,
        processingMode: slice.processing_mode,
        processing: slice.processing,
        agcWindowSec,
        frequencyFilter,
        filterLabel: frequencyFilter === 'bandpass' ? 'Bandpass 8/12/80/100 Hz' : 'None',
        preview: slice.preview,
        windowed: Boolean(slice.windowed),
        renderMode,
        sourceWindow: slice.source_window || null,
        renderTarget,
        requestElapsedMs,
        backendRenderMs: slice.render_time_ms ?? null,
        sourceWindowPixelCount: slice.source_window_pixel_count ?? null,
        outputPixelCount: slice.output_pixel_count ?? (Array.isArray(slice.shape) ? Number(slice.shape[0] || 0) * Number(slice.shape[1] || 0) : null),
      });

      setRenderError(null);

      const data = Array.isArray(slice.data) ? slice.data : Array.from(slice.data as any);
      const [traceCountRaw, sampleCountRaw] = slice.shape;

      const traceCount = isTrue2DLine ? traceCountRaw : sampleCountRaw;
      const sampleCount = isTrue2DLine ? sampleCountRaw : traceCountRaw;

      const canvas = canvasRef.current;
      canvas.width = traceCount;
      canvas.height = sampleCount;

      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      const clipAbs = computeSymmetricClipAbs(slice.clip_abs);
      const polarity = reversePolarity ? -1 : 1;

      const getRawValue = (trace: number, sample: number) => {
        if (isTrue2DLine) {
          const actualTrace = reverseDirection ? traceCount - 1 - trace : trace;
          return Number(data[actualTrace * sampleCount + sample]) || 0;
        }

        return Number(data[sample * traceCount + trace]) || 0;
      };

      const getNormValue = (trace: number, sample: number) => {
        const val = getRawValue(trace, sample) * polarity * gain / clipAbs;
        return clampNormalizedAmplitude(val, 1);
      };

      const drawTimelines = () => {
        if (!showTimelines) return;

        const sampleStride = Number(slice.sample_stride || 1);
        const sectionSampleIntervalMs =
          Number(metadata?.sample_interval_ms || 0) ||
          Number(metadata?.sample_rate || 0) ||
          Number(metadata?.volume?.sample_interval_ms || 0) ||
          Number(metadata?.zarr?.sample_interval_ms || 0) ||
          Number(metadata?.sample_interval_us || 0) / 1000 ||
          Number(metadata?.volume?.sample_interval_us || 0) / 1000 ||
          Number(metadata?.zarr?.sample_interval_us || 0) / 1000 ||
          Number(slice.sample_interval_ms || 0) ||
          Number(slice.processing?.sample_interval_sec || 0) * 1000;

        if (!sectionSampleIntervalMs || !timelineIntervalMs) return;

        const previewSampleIntervalMs = sectionSampleIntervalMs * sampleStride;
        // Exact requested time-grid interval.
        // Do not thin or multiply this value; 100 ms must mean 100 ms.
        const lineStep = Math.max(1, Math.round(timelineIntervalMs / previewSampleIntervalMs));

        ctx.save();
        ctx.strokeStyle =
          displayMode === 'raster' || displayMode === 'raster_wiggle'
            ? 'rgba(0,0,0,0.18)'
            : 'rgba(0,0,0,0.20)';
        ctx.lineWidth = 1;

        for (let y = lineStep; y < sampleCount; y += lineStep) {
          ctx.beginPath();
          ctx.moveTo(0, y + 0.5);
          ctx.lineTo(traceCount, y + 0.5);
          ctx.stroke();
        }

        ctx.restore();
      };

      const renderRaster = () => {
        const imageData = ctx.createImageData(traceCount, sampleCount);

        for (let y = 0; y < sampleCount; y++) {
          for (let x = 0; x < traceCount; x++) {
            const pixelIndex = y * traceCount + x;
            const norm = getNormValue(x, y);

            const color = computeRasterColorValue(norm, rasterColorMap);
            imageData.data[pixelIndex * 4] = color.r;
            imageData.data[pixelIndex * 4 + 1] = color.g;
            imageData.data[pixelIndex * 4 + 2] = color.b;

            imageData.data[pixelIndex * 4 + 3] = 255;
          }
        }

        ctx.putImageData(imageData, 0, 0);
        drawTimelines();
      };

      const renderWiggle = () => {
        ctx.save();

        // Pure wiggle mode uses a paper-style background. Image + Wiggle keeps
        // the raster image already drawn by renderRaster().
        if (displayMode === 'wiggle') {
          ctx.fillStyle = '#ffffff';
          ctx.fillRect(0, 0, traceCount, sampleCount);
        }

        drawTimelines();

        /*
          Robust SU-style wiggle renderer.

          This is not copied SU/X11 code. It is a canvas implementation of the
          same display idea:
            - draw a sparse set of traces
            - center each trace on a baseline
            - scale amplitude relative to display clip
            - clamp excursions to avoid trace smearing
            - optionally fill positive or negative lobes
            - smooth only for display, not data
        */

        const { decimation, baseTraceSpacing } = computeTraceStep(traceCount, traceDecimation, 95);

        // Conservative default. Scale slider still works, but cannot destroy the plot.
        const { nominalTraceSpacing, ampScale, maxExcursion, lineWidth } = computeWiggleScale(
          baseTraceSpacing,
          wiggleTraceSpacing,
          wiggleScale
        );

        const wiggleRenderStyle = computeWiggleRenderStyle(
          displayMode,
          nominalTraceSpacing,
          lineWidth
        );

        const shouldFillPositive =
          wiggleStyle === 'variable_area' &&
          (wiggleFill === 'positive' || wiggleFill === 'both');

        const shouldFillNegative =
          wiggleStyle === 'variable_area' &&
          (wiggleFill === 'negative' || wiggleFill === 'both');

        const clipNorm = (v: number) => Math.max(-1.75, Math.min(1.75, v));

        const wiggleX = (baseline: number, norm: number) => {
          const excursion = Math.max(
            -maxExcursion,
            Math.min(maxExcursion, clipNorm(norm) * ampScale)
          );
          return baseline + excursion;
        };

        const buildSmoothedNorms = (trace: number) => {
          const raw = new Float32Array(sampleCount);

          for (let sample = 0; sample < sampleCount; sample++) {
            raw[sample] = clipNorm(getNormValue(trace, sample));
          }

          // Light display-only smoothing. This reduces jagged canvas scratch
          // without changing backend data or suppressing real events.
          if (sampleCount < 7) return raw;

          const smooth = new Float32Array(sampleCount);

          smooth[0] = raw[0];
          smooth[1] = raw[1];

          for (let i = 2; i < sampleCount - 2; i++) {
            smooth[i] =
              (raw[i - 2] +
                2 * raw[i - 1] +
                3 * raw[i] +
                2 * raw[i + 1] +
                raw[i + 2]) /
              9;
          }

          smooth[sampleCount - 2] = raw[sampleCount - 2];
          smooth[sampleCount - 1] = raw[sampleCount - 1];

          return smooth;
        };

        const drawFilledLobes = (
          baseline: number,
          norms: Float32Array,
          fillPositive: boolean
        ) => {
          const hasWantedSign = (v: number) =>
            fillPositive ? v > 0 : v < 0;

          const interpolateZeroCrossing = (sampleA: number, sampleB: number) => {
            const a = norms[sampleA];
            const b = norms[sampleB];
            const denom = Math.abs(a) + Math.abs(b);

            if (!Number.isFinite(denom) || denom <= 1e-12) return sampleA;

            return sampleA + Math.abs(a) / denom;
          };

          let lobeStart: number | null = null;
          let lobeStartY = 0;

          for (let sample = 0; sample <= sampleCount; sample++) {
            const active = sample < sampleCount && hasWantedSign(norms[sample]);

            if (active && lobeStart === null) {
              lobeStart = sample;
              lobeStartY =
                sample > 0 && !hasWantedSign(norms[sample - 1])
                  ? interpolateZeroCrossing(sample - 1, sample)
                  : sample;
            }

            if (!active && lobeStart !== null) {
              const lobeEnd = sample - 1;
              const lobeEndY =
                sample < sampleCount && lobeEnd >= 0
                  ? interpolateZeroCrossing(lobeEnd, sample)
                  : lobeEnd;

              if (lobeEnd >= lobeStart) {
                ctx.beginPath();

                // Baseline side of the variable-area lobe.
                ctx.moveTo(baseline, lobeStartY);
                ctx.lineTo(baseline, lobeEndY);

                // Wiggle-curve side of the lobe, including single-sample lobes.
                for (let s = lobeEnd; s >= lobeStart; s--) {
                  ctx.lineTo(wiggleX(baseline, norms[s]), s);
                }

                ctx.closePath();
                ctx.fill();
              }

              lobeStart = null;
            }
          }
        };

        ctx.lineCap = 'round';
        ctx.lineJoin = 'round';

        for (let trace = 0; trace < traceCount; trace += decimation) {
          const baseline = trace;
          const norms = buildSmoothedNorms(trace);

          if (shouldFillPositive) {
            ctx.fillStyle = wiggleRenderStyle.positiveFillStyle;
            drawFilledLobes(baseline, norms, true);
          }

          if (shouldFillNegative) {
            ctx.fillStyle = wiggleRenderStyle.negativeFillStyle;
            drawFilledLobes(baseline, norms, false);
          }

          ctx.beginPath();

          for (let sample = 0; sample < sampleCount; sample++) {
            const x = wiggleX(baseline, norms[sample]);

            if (sample === 0) {
              ctx.moveTo(x, sample);
            } else {
              ctx.lineTo(x, sample);
            }
          }

          ctx.strokeStyle = wiggleRenderStyle.traceStrokeStyle;
          ctx.lineWidth = wiggleRenderStyle.traceLineWidth;
          ctx.stroke();

          // Optional trace zero-amplitude baseline.
          // Deliberately visible for testing. If this proves useful, we can tone it down later.
          if (showWiggleZeroLine) {
            ctx.save();
            ctx.beginPath();
            ctx.moveTo(baseline, 0);
            ctx.lineTo(baseline, sampleCount - 1);
            ctx.strokeStyle = wiggleRenderStyle.zeroLineStrokeStyle;
            ctx.lineWidth = wiggleRenderStyle.zeroLineWidth;
            ctx.setLineDash([]);
            ctx.stroke();
            ctx.setLineDash([]);
            ctx.restore();
          }
        }

        ctx.restore();
      };

      if (displayMode === 'raster' || displayMode === 'raster_wiggle') {
        renderRaster();
      }

      if (displayMode === 'wiggle' || displayMode === 'raster_wiggle') {
        renderWiggle();
      }
    }

    renderSection().catch((err) => {
      console.error('Failed to render 2D section', err);
      setRenderError(err instanceof Error ? err.message : String(err));
    });
  }, [
    zarrPath,
    dim,
    index,
    metadata,
    gain,
    clipPercentile,
    processingMode,
    displayMode,
    rasterColorMap,
    agcWindowSec,
    frequencyFilter,
    wiggleScale,
    traceDecimation,
    wiggleStyle,
    wiggleFill,
    wiggleTraceSpacing,
    showWiggleZeroLine,
    reversePolarity,
    reverseDirection,
    showTimelines,
    timelineIntervalMs,
    sourceWindow,
    showAxisLabels,
  ]);

  if (!metadata) return <div>Loading...</div>;

  const maxIndex = metadata.shape?.length === 2 ? 0 : metadata.shape[dim] - 1;

  const getCanvasPoint = (event: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return null;

    const rect = canvas.getBoundingClientRect();

    return {
      canvas,
      rect,
      xCss: event.clientX - rect.left,
      yCss: event.clientY - rect.top,
      xCanvas: Math.max(0, Math.min(canvas.width, ((event.clientX - rect.left) / rect.width) * canvas.width)),
      yCanvas: Math.max(0, Math.min(canvas.height, ((event.clientY - rect.top) / rect.height) * canvas.height)),
    };
  };

  const handleCanvasMouseMove = (event: React.MouseEvent<HTMLCanvasElement>) => {
    const point = getCanvasPoint(event);
    if (!point || !metadata?.shape) return;

    if (zoomDrag?.active) {
      setZoomDrag({
        ...zoomDrag,
        currentXCss: point.xCss,
        currentYCss: point.yCss,
        currentXCanvas: point.xCanvas,
        currentYCanvas: point.yCanvas,
      });
    }

    if (panDrag?.active && !boxZoomEnabled) {
      setPanDrag({
        ...panDrag,
        currentXCanvas: point.xCanvas,
        currentYCanvas: point.yCanvas,
      });
    }

    const canvas = point.canvas;
    const previewTrace = Math.max(0, Math.min(canvas.width - 1, Math.floor(point.xCanvas)));
    const previewSample = Math.max(0, Math.min(canvas.height - 1, Math.floor(point.yCanvas)));

    const activeSourceWindow = readSourceWindow(sectionInfo?.sourceWindow, sectionInfo?.sourceShape || metadata.shape);
    const traceSpan = Math.max(1, activeSourceWindow.traceEnd - activeSourceWindow.traceStart);
    const sampleSpan = Math.max(1, activeSourceWindow.sampleEnd - activeSourceWindow.sampleStart);
    const traceFraction = canvas.width <= 1 ? 0 : previewTrace / Math.max(1, canvas.width - 1);
    const sampleFraction = canvas.height <= 1 ? 0 : previewSample / Math.max(1, canvas.height - 1);

    const sourceTrace = reverseDirection
      ? activeSourceWindow.traceEnd - 1 - traceFraction * Math.max(0, traceSpan - 1)
      : activeSourceWindow.traceStart + traceFraction * Math.max(0, traceSpan - 1);

    const sourceSample = activeSourceWindow.sampleStart + sampleFraction * Math.max(0, sampleSpan - 1);
    const sampleRate =
      Number(metadata.sample_rate || metadata.sample_interval_ms || 0) ||
      Number(sectionInfo?.sampleIntervalMs || 0);
    const timeMs = sampleRate ? sourceSample * sampleRate : null;

    setCursorInfo({
      trace: sourceTrace,
      sample: sourceSample,
      timeMs,
    });
  };

  const handleCanvasMouseDown = (event: React.MouseEvent<HTMLCanvasElement>) => {
    if (event.button !== 0) return;

    const point = getCanvasPoint(event);
    if (!point) return;

    if (boxZoomEnabled) {
      setPanDrag(null);
      setZoomDrag({
        active: true,
        startXCss: point.xCss,
        startYCss: point.yCss,
        currentXCss: point.xCss,
        currentYCss: point.yCss,
        startXCanvas: point.xCanvas,
        startYCanvas: point.yCanvas,
        currentXCanvas: point.xCanvas,
        currentYCanvas: point.yCanvas,
      });
      return;
    }

    if (sourceWindow) {
      setZoomDrag(null);
      setPanDrag({
        active: true,
        startXCanvas: point.xCanvas,
        startYCanvas: point.yCanvas,
        currentXCanvas: point.xCanvas,
        currentYCanvas: point.yCanvas,
        startWindow: { ...sourceWindow },
      });
    }
  };

  const handleCanvasMouseUp = () => {
    const viewport = viewportRef.current;
    const canvas = canvasRef.current;

    if (panDrag?.active && !boxZoomEnabled) {
      if (!canvas) {
        setPanDrag(null);
        return;
      }

      const sourceShape = sectionInfo?.sourceShape || metadata?.shape || [];
      const sourceTraceCount = Math.max(1, Number(sourceShape?.[0] || 1));
      const sourceSampleCount = Math.max(1, Number(sourceShape?.[1] || 1));
      const startWindow = panDrag.startWindow;
      const traceSpan = Math.max(1, startWindow.traceEnd - startWindow.traceStart);
      const sampleSpan = Math.max(1, startWindow.sampleEnd - startWindow.sampleStart);
      const deltaX = panDrag.currentXCanvas - panDrag.startXCanvas;
      const deltaY = panDrag.currentYCanvas - panDrag.startYCanvas;
      const traceShift = -(deltaX / Math.max(1, canvas.width)) * traceSpan;
      const sampleShift = -(deltaY / Math.max(1, canvas.height)) * sampleSpan;

      setPanDrag(null);

      if (Math.abs(deltaX) < 3 && Math.abs(deltaY) < 3) return;

      const [nextTraceStart, nextTraceEnd] = shiftWindowRange(
        startWindow.traceStart,
        startWindow.traceEnd,
        traceShift,
        sourceTraceCount
      );
      const [nextSampleStart, nextSampleEnd] = shiftWindowRange(
        startWindow.sampleStart,
        startWindow.sampleEnd,
        sampleShift,
        sourceSampleCount
      );

      setSourceWindow({
        traceStart: nextTraceStart,
        traceEnd: nextTraceEnd,
        sampleStart: nextSampleStart,
        sampleEnd: nextSampleEnd,
      });

      return;
    }

    if (!boxZoomEnabled) return;
    if (!zoomDrag?.active) return;

    if (!viewport || !canvas) {
      setZoomDrag(null);
      return;
    }

    const x1 = Math.min(zoomDrag.startXCanvas, zoomDrag.currentXCanvas);
    const x2 = Math.max(zoomDrag.startXCanvas, zoomDrag.currentXCanvas);
    const y1 = Math.min(zoomDrag.startYCanvas, zoomDrag.currentYCanvas);
    const y2 = Math.max(zoomDrag.startYCanvas, zoomDrag.currentYCanvas);

    const boxWidth = x2 - x1;
    const boxHeight = y2 - y1;

    setZoomDrag(null);

    if (boxWidth < 10 || boxHeight < 10) return;

    const activeSourceWindow = readSourceWindow(sectionInfo?.sourceWindow, sectionInfo?.sourceShape || metadata.shape);
    const traceSpan = Math.max(1, activeSourceWindow.traceEnd - activeSourceWindow.traceStart);
    const sampleSpan = Math.max(1, activeSourceWindow.sampleEnd - activeSourceWindow.sampleStart);

    const canvasXToSourceTrace = (x: number) => {
      const fraction = clampNumber(x / Math.max(1, canvas.width), 0, 1);
      return reverseDirection
        ? activeSourceWindow.traceEnd - fraction * traceSpan
        : activeSourceWindow.traceStart + fraction * traceSpan;
    };

    const canvasYToSourceSample = (y: number) => {
      const fraction = clampNumber(y / Math.max(1, canvas.height), 0, 1);
      return activeSourceWindow.sampleStart + fraction * sampleSpan;
    };

    const mappedTrace1 = canvasXToSourceTrace(x1);
    const mappedTrace2 = canvasXToSourceTrace(x2);
    const mappedSample1 = canvasYToSourceSample(y1);
    const mappedSample2 = canvasYToSourceSample(y2);

    const sourceTraceCount = Math.max(1, Number((sectionInfo?.sourceShape || metadata.shape)?.[0] || 1));
    const sourceSampleCount = Math.max(1, Number((sectionInfo?.sourceShape || metadata.shape)?.[1] || 1));

    const [nextTraceStart, nextTraceEnd] = clampWindowRange(
      mappedTrace1,
      mappedTrace2,
      MIN_WINDOW_TRACES,
      sourceTraceCount
    );
    const [nextSampleStart, nextSampleEnd] = clampWindowRange(
      mappedSample1,
      mappedSample2,
      MIN_WINDOW_SAMPLES,
      sourceSampleCount
    );

    setSourceWindow({
      traceStart: nextTraceStart,
      traceEnd: nextTraceEnd,
      sampleStart: nextSampleStart,
      sampleEnd: nextSampleEnd,
    });
    setBoxZoomEnabled(false);

    setFitToWidth(true);
    setXScale(1.0);
    setYScale(1.0);

    window.setTimeout(() => {
      viewport.scrollLeft = 0;
      viewport.scrollTop = 0;
    }, 0);
  };

  const handleCanvasDoubleClick = () => {
    setXScale(1.0);
    setYScale(1.0);
    setFitToWidth(true);
    setZoomDrag(null);
    setPanDrag(null);
    setBoxZoomEnabled(false);
    setSourceWindow(null);

    const viewport = viewportRef.current;
    if (viewport) {
      viewport.scrollLeft = 0;
      viewport.scrollTop = 0;
    }
  };

  const applyDisplayPreset = (presetId: DisplayPresetId) => {
    setDisplayPreset(presetId);

    switch (presetId) {
      case 'standard_interpretation':
        setDisplayMode('raster');
        setRasterColorMap('gray_balanced');
        setProcessingMode('demean');
        setFrequencyFilter('none');
        setClipPercentile(99.0);
        setGain(1.0);
        setReversePolarity(false);
        return;

      case 'high_contrast_dip':
        setDisplayMode('raster');
        setRasterColorMap('gray_high_contrast');
        setProcessingMode('demean');
        setFrequencyFilter('none');
        setClipPercentile(98.0);
        setGain(1.2);
        setReversePolarity(false);
        return;

      case 'polarity_qc':
        setDisplayMode('raster');
        setRasterColorMap('seismic_rwb');
        setProcessingMode('demean');
        setFrequencyFilter('none');
        setClipPercentile(99.0);
        setGain(1.0);
        setReversePolarity(false);
        return;

      case 'wiggle_qc':
        setDisplayMode('wiggle');
        setRasterColorMap('gray_balanced');
        setProcessingMode('demean');
        setFrequencyFilter('none');
        setClipPercentile(99.0);
        setGain(1.0);
        setWiggleStyle('variable_area');
        setWiggleFill('positive');
        setTraceDecimation('auto');
        setWiggleScale(1.0);
        setWiggleTraceSpacing(1.0);
        setShowWiggleZeroLine(true);
        return;

      case 'image_wiggle':
        setDisplayMode('raster_wiggle');
        setRasterColorMap('gray_balanced');
        setProcessingMode('demean');
        setFrequencyFilter('none');
        setClipPercentile(99.0);
        setGain(1.0);
        setWiggleStyle('variable_area');
        setWiggleFill('positive');
        setTraceDecimation('auto');
        setWiggleScale(1.0);
        setWiggleTraceSpacing(1.0);
        setShowWiggleZeroLine(true);
        return;

      case 'soft_regional':
        setDisplayMode('raster');
        setRasterColorMap('gray_balanced');
        setProcessingMode('demean');
        setFrequencyFilter('none');
        setClipPercentile(99.5);
        setGain(0.8);
        setReversePolarity(false);
        return;

      default:
        return;
    }
  };

  const getActiveSourceShape = (): number[] => {
    const shape = sectionInfo?.sourceShape || metadata?.shape || [];
    return Array.isArray(shape) ? shape : [];
  };

  const getActiveSourceCounts = () => {
    const shape = getActiveSourceShape();
    return {
      traceCount: Math.max(1, Number(shape?.[0] || 1)),
      sampleCount: Math.max(1, Number(shape?.[1] || 1)),
    };
  };

  const getActiveWindow = (): SourceWindow2D => {
    return sourceWindow || readSourceWindow(sectionInfo?.sourceWindow, getActiveSourceShape());
  };

  const getZoomLevel = (): number => {
    const { traceCount, sampleCount } = getActiveSourceCounts();
    const activeWindow = getActiveWindow();
    const traceSpan = Math.max(1, activeWindow.traceEnd - activeWindow.traceStart);
    const sampleSpan = Math.max(1, activeWindow.sampleEnd - activeWindow.sampleStart);

    return Math.max(traceCount / traceSpan, sampleCount / sampleSpan);
  };

  const applyStepZoom = (direction: 'in' | 'out') => {
    if (!metadata?.shape || metadata.shape.length !== 2) return;

    const activeWindow = getActiveWindow();
    const { traceCount, sampleCount } = getActiveSourceCounts();
    const currentTraceSpan = Math.max(1, activeWindow.traceEnd - activeWindow.traceStart);
    const currentSampleSpan = Math.max(1, activeWindow.sampleEnd - activeWindow.sampleStart);
    const scale = direction === 'in' ? 1 / STEP_ZOOM_FACTOR : STEP_ZOOM_FACTOR;

    const nextTraceSpan = currentTraceSpan * scale;
    const nextSampleSpan = currentSampleSpan * scale;

    const traceCenter = (activeWindow.traceStart + activeWindow.traceEnd) / 2;
    const sampleCenter = (activeWindow.sampleStart + activeWindow.sampleEnd) / 2;

    const [nextTraceStart, nextTraceEnd] = centeredWindowRange(
      traceCenter,
      nextTraceSpan,
      MIN_WINDOW_TRACES,
      traceCount
    );
    const [nextSampleStart, nextSampleEnd] = centeredWindowRange(
      sampleCenter,
      nextSampleSpan,
      MIN_WINDOW_SAMPLES,
      sampleCount
    );

    const isFullWindow = nextTraceStart === 0 && nextTraceEnd === traceCount && nextSampleStart === 0 && nextSampleEnd === sampleCount;

    setZoomDrag(null);
    setPanDrag(null);
    setBoxZoomEnabled(false);
    setFitToWidth(true);
    setXScale(1.0);
    setYScale(1.0);
    setSourceWindow(isFullWindow ? null : {
      traceStart: nextTraceStart,
      traceEnd: nextTraceEnd,
      sampleStart: nextSampleStart,
      sampleEnd: nextSampleEnd,
    });

    const viewport = viewportRef.current;
    if (viewport) {
      window.setTimeout(() => {
        viewport.scrollLeft = 0;
        viewport.scrollTop = 0;
      }, 0);
    }
  };

  const zoomLevel = getZoomLevel();
  const canStepZoomOut = Boolean(sourceWindow);

  const resetZoom = () => {
    // Reset zoom/viewport only.
    // Does not change display mode, amplitude, wiggle, grid, or selected data.
    setFitToWidth(true);
    setXScale(1.0);
    setYScale(1.0);
    setZoomDrag(null);
    setPanDrag(null);
    setBoxZoomEnabled(false);
    setSourceWindow(null);

    const viewport = viewportRef.current;
    if (viewport) {
      viewport.scrollLeft = 0;
      viewport.scrollTop = 0;
    }
  };

  const resetView = () => {
    // Restore the currently loaded 2D section to its original loaded/default view.
    // This does not unload data or change the selected line.
    setGain(1.0);
    setClipPercentile(99.0);
    setProcessingMode('demean');
    setAgcWindowSec(0.5);
    setFrequencyFilter('none');
    setDisplayMode('raster');
    setRasterColorMap('gray_balanced');
    setDisplayPreset('standard_interpretation');
    setReversePolarity(false);
    setReverseDirection(false);

    setXScale(1.0);
    setYScale(1.0);
    setFitToWidth(true);
    setBoxZoomEnabled(false);
    setZoomDrag(null);
    setPanDrag(null);
    setSourceWindow(null);

    setWiggleScale(1.0);
    setTraceDecimation('auto');
    setWiggleStyle('variable_area');
    setWiggleFill('positive');
    setWiggleTraceSpacing(1.0);
    setShowWiggleZeroLine(true);

    setShowTimelines(false);
    setTimelineIntervalMs(250);
    setShowAxisLabels(true);

    setDisplayControlsOpen(true);
    setAmplitudeControlsOpen(true);
    setWiggleControlsOpen(false);
    setGridAxisControlsOpen(false);
    setZoomControlsOpen(false);

    const viewport = viewportRef.current;
    if (viewport) {
      viewport.scrollLeft = 0;
      viewport.scrollTop = 0;
    }
  };

  const resetDisplay = () => {
    setGain(1.0);
    setClipPercentile(99.0);
    setProcessingMode('demean');
    setDisplayMode('raster');
    setRasterColorMap('gray_balanced');
    setReversePolarity(false);
    setReverseDirection(false);
    setXScale(1.0);
    setYScale(1.0);
    setWiggleScale(1.0);
    setTraceDecimation('auto');
    setWiggleStyle('variable_area');
    setWiggleFill('positive');
    setWiggleTraceSpacing(1.0);
    setShowWiggleZeroLine(true);
    setShowTimelines(false);
    setTimelineIntervalMs(100);
    setFitToWidth(true);
    setZoomDrag(null);
    setPanDrag(null);
    setSourceWindow(null);
  };

  const panelStyle: React.CSSProperties = {
    width: '270px',
    minWidth: '270px',
    padding: '12px',
    borderRight: '1px solid #27343e',
    background: '#0d1116',
    overflowY: 'auto',
    boxSizing: 'border-box',
  };

  const sectionStyle: React.CSSProperties = {
    marginBottom: '16px',
    paddingBottom: '12px',
    borderBottom: '1px solid #27343e',
  };

  const sectionTitleStyle: React.CSSProperties = {
    fontSize: '12px',
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
    opacity: 0.65,
    marginBottom: '8px',
  };

  const rowStyle: React.CSSProperties = {
    display: 'grid',
    gridTemplateColumns: '88px 1fr',
    alignItems: 'center',
    gap: '8px',
    marginBottom: '8px',
    fontSize: '13px',
  };

  const selectStyle: React.CSSProperties = {
    background: '#091118',
    color: '#e3e8ec',
    border: '1px solid #354452',
    borderRadius: '4px',
    padding: '4px 6px',
    width: '100%',
  };

  const buttonStyle: React.CSSProperties = {
    background: '#091118',
    color: '#e3e8ec',
    border: '1px solid #354452',
    borderRadius: '4px',
    padding: '6px 8px',
    cursor: 'pointer',
    width: '100%',
  };

  const checkboxRowStyle: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    marginBottom: '8px',
    fontSize: '13px',
  };

  const valueStyle: React.CSSProperties = {
    fontSize: '12px',
    opacity: 0.75,
    textAlign: 'right',
  };

  return (
    <div
      style={{
        display: 'flex',
        position: 'relative',
        height: '100%',
        background: '#0d1116',
        color: '#e3e8ec',
        boxSizing: 'border-box',
        minHeight: 0,
      }}
    >
      <aside
        className="mv-viewer-controls-panel mv-viewer-controls-panel--info-parity mv-sdv2d-wbv-controls-panel"
        style={{
          ...panelStyle,
          position: 'absolute',
          top: 0,
          left: 0,
          zIndex: 5,
          transform: menuCollapsed ? 'translateX(calc(-100% - 10px))' : 'translateX(0)',
          transition: 'transform 180ms ease',
          pointerEvents: menuCollapsed ? 'none' : 'auto',
          width: panelStyle.width,
          minWidth: panelStyle.minWidth,
          height: '100%',
          padding: panelStyle.padding,
          overflow: panelStyle.overflow,
        }}
      >
        
        <button
          className="mv-viewer-compact-button"
          onClick={() => setMenuCollapsed((value) => !value)}
          title={menuCollapsed ? 'Expand 2D View Controls' : 'Collapse 2D View Controls'}
          aria-label={menuCollapsed ? 'Expand 2D View Controls' : 'Collapse 2D View Controls'}
        >
          {menuCollapsed ? '▶' : '◀'}
        </button>

        <h3 className="mv-viewer-controls-title" style={{ margin: 0 }}>
          2D View Controls
        </h3>

        {!menuCollapsed && (
          <Seismic2DControlsPanel
            displayControlsOpen={displayControlsOpen}
            setDisplayControlsOpen={setDisplayControlsOpen}
            displayMode={displayMode}
            setDisplayMode={setDisplayMode}
            rasterColorMap={rasterColorMap}
            setRasterColorMap={setRasterColorMap}
            displayPreset={displayPreset}
            applyDisplayPreset={applyDisplayPreset}
            fitToWidth={fitToWidth}
            setFitToWidth={setFitToWidth}
            reverseDirection={reverseDirection}
            setReverseDirection={setReverseDirection}
            amplitudeControlsOpen={amplitudeControlsOpen}
            setAmplitudeControlsOpen={setAmplitudeControlsOpen}
            processingMode={processingMode}
            setProcessingMode={setProcessingMode}
            agcWindowSec={agcWindowSec}
            setAgcWindowSec={setAgcWindowSec}
            frequencyFilter={frequencyFilter}
            setFrequencyFilter={setFrequencyFilter}
            clipPercentile={clipPercentile}
            setClipPercentile={setClipPercentile}
            gain={gain}
            setGain={setGain}
            reversePolarity={reversePolarity}
            setReversePolarity={setReversePolarity}
            wiggleControlsOpen={wiggleControlsOpen}
            setWiggleControlsOpen={setWiggleControlsOpen}
            wiggleStyle={wiggleStyle}
            setWiggleStyle={setWiggleStyle}
            wiggleFill={wiggleFill}
            setWiggleFill={setWiggleFill}
            wiggleScale={wiggleScale}
            setWiggleScale={setWiggleScale}
            wiggleTraceSpacing={wiggleTraceSpacing}
            setWiggleTraceSpacing={setWiggleTraceSpacing}
            traceDecimation={traceDecimation}
            setTraceDecimation={setTraceDecimation}
            showWiggleZeroLine={showWiggleZeroLine}
            setShowWiggleZeroLine={setShowWiggleZeroLine}
            gridAxisControlsOpen={gridAxisControlsOpen}
            setGridAxisControlsOpen={setGridAxisControlsOpen}
            showTimelines={showTimelines}
            setShowTimelines={setShowTimelines}
            timelineIntervalMs={timelineIntervalMs}
            setTimelineIntervalMs={setTimelineIntervalMs}
            showAxisLabels={showAxisLabels}
            setShowAxisLabels={setShowAxisLabels}
            zoomControlsOpen={zoomControlsOpen}
            setZoomControlsOpen={setZoomControlsOpen}
            boxZoomEnabled={boxZoomEnabled}
            setBoxZoomEnabled={setBoxZoomEnabled}
            resetZoom={resetZoom}
            resetView={resetView}
            zoomLevel={zoomLevel}
            canStepZoomOut={canStepZoomOut}
            canResetZoom={Boolean(sourceWindow)}
            applyStepZoom={applyStepZoom}
          />
        )}
      </aside>

      <section
        style={{
          position: 'relative',
          flex: 1,
          marginLeft: menuCollapsed ? 0 : panelStyle.width,
          marginRight: lineInfoCollapsed ? 0 : 330,
          minWidth: 0,
          minHeight: 0,
          display: 'flex',
          flexDirection: 'column',
        }}
      >



        {!emptyState && metadata.shape?.length !== 2 && (
          <div className="mv-sdv-2d-slice-index-row" style={{ padding: '8px 12px' }}>
            <label>Slice Index: </label>
            <input
              type="range"
              min={0}
              max={maxIndex}
              value={index}
              onChange={(e) => setIndex(parseInt(e.target.value, 10))}
            />
            <span> {index}</span>
          </div>
        )}



        <div
          ref={viewportRef}
          style={{
                padding: showAxisLabels ? '12px 12px 44px 78px' : '12px',
                boxSizing: 'border-box',
            flex: 1,
            overflow: 'auto',
            background: canvasBackground,
            minHeight: 0,
            padding: '12px',
            boxSizing: 'border-box',
            border: '1px solid rgb(155, 168, 179)',
            borderRadius: 0,
            boxShadow: 'rgb(167, 178, 188) 0 0 0 1px inset',
          }}
        >
          <div
            style={{
              position: 'relative',
              width: emptyState ? '100%' : (fitToWidth ? `${100 * xScale}%` : `${(canvasRef.current?.width || 100) * xScale}px`),
              height: emptyState ? '100%' : `${(canvasRef.current?.height || 100) * yScale}px`,
              minHeight: emptyState ? '240px' : undefined,
              margin: '0 auto',
            }}
          >
            {emptyState && (
              <div
                className="mv-sdv2d-empty-canvas-state"
                role="status"
                aria-live="polite"
                style={{
                  position: 'absolute',
                  inset: 0,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  zIndex: 2,
                  pointerEvents: 'none',
                }}
              >
                <div
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    padding: '10px 16px',
                    border: '1px solid var(--mv-border-strong)',
                    borderRadius: 6,
                    background: 'color-mix(in srgb, var(--mv-surface-1) 92%, transparent)',
                    color: 'var(--mv-text-primary)',
                    fontFamily: 'var(--mv-font-ui)',
                    fontSize: '0.82rem',
                    fontWeight: 600,
                    lineHeight: 1.2,
                    textAlign: 'center',
                    boxSizing: 'border-box',
                  }}
                >
                  {emptyStateMessage}
                </div>
              </div>
            )}
            <canvas
              ref={canvasRef}
              onMouseDown={handleCanvasMouseDown}
              onMouseMove={handleCanvasMouseMove}
              onMouseUp={handleCanvasMouseUp}
              onDoubleClick={handleCanvasDoubleClick}
              onMouseLeave={() => {
                setCursorInfo(null);
                if (zoomDrag?.active) setZoomDrag(null);
                if (panDrag?.active) setPanDrag(null);
              }}
              style={{
                imageRendering: 'auto',
                width: '100%',
                height: '100%',
                display: emptyState ? 'none' : 'block',
                background: canvasBackground,
                cursor: boxZoomEnabled ? 'crosshair' : sourceWindow ? (panDrag?.active ? 'grabbing' : 'grab') : 'default',
              }}
            />

            {!emptyState && showAxisLabels && (() => {
              const axisInfo = get2DAxisDisplayInfo(lineInfo);

              const leftGutter = 78;
              const bottomGutter = 44;

              const tickStyle: React.CSSProperties = {
                position: 'absolute',
                color: '#f5f7fb',
                background: 'rgba(12, 16, 24, 0.44)',
                border: '1px solid rgba(255,255,255,0.10)',
                borderRadius: 4,
                padding: '1px 4px',
                fontSize: 9,
                fontWeight: 600,
                pointerEvents: 'none',
                zIndex: 20,
                opacity: 0.78,
                whiteSpace: 'nowrap',
              };

              const titleStyle: React.CSSProperties = {
                position: 'absolute',
                color: '#f5f7fb',
                background: 'rgba(12, 16, 24, 0.34)',
                border: '1px solid rgba(255,255,255,0.08)',
                borderRadius: 4,
                padding: '1px 5px',
                fontSize: 9,
                fontWeight: 700,
                pointerEvents: 'none',
                zIndex: 20,
                opacity: 0.72,
                whiteSpace: 'nowrap',
              };

              return (
                <>
                  {/* X axis: bottom gutter, outside seismic pixels */}
                  <div
                    style={{
                      ...tickStyle,
                      left: leftGutter,
                      bottom: 22,
                    }}
                  >
                    {format2DTickValue(axisInfo.horizontal.min, true)}
                  </div>

                  <div
                    style={{
                      ...tickStyle,
                      right: 12,
                      bottom: 22,
                    }}
                  >
                    {format2DTickValue(axisInfo.horizontal.max, true)}
                  </div>

                  <div
                    style={{
                      ...titleStyle,
                      left: `calc(${leftGutter}px + (100% - ${leftGutter}px) / 2)`,
                      bottom: 6,
                      transform: 'translateX(-50%)',
                    }}
                  >
                    {axisInfo.horizontal.label}
                  </div>

                  {/* Y axis: left gutter, outside seismic pixels */}
                  <div
                    style={{
                      ...tickStyle,
                      left: 28,
                      top: 12,
                    }}
                  >
                    {format2DTickValue(axisInfo.vertical.min, axisInfo.vertical.discrete)}
                  </div>

                  <div
                    style={{
                      ...tickStyle,
                      left: 28,
                      bottom: bottomGutter + 4,
                    }}
                  >
                    {format2DTickValue(axisInfo.vertical.max, axisInfo.vertical.discrete)}
                  </div>

                  <div
                    style={{
                      ...titleStyle,
                      left: 4,
                      top: `calc(50% - ${bottomGutter / 2}px)`,
                      transform: 'translateY(-50%) rotate(-90deg)',
                      transformOrigin: 'center center',
                    }}
                  >
                    {axisInfo.vertical.label}
                  </div>
                </>
              );
            })()}

            {!emptyState && boxZoomEnabled && zoomDrag?.active && (
              <div
                style={{
                  position: 'absolute',
                  pointerEvents: 'none',
                  left: `${Math.min(zoomDrag.startXCss, zoomDrag.currentXCss)}px`,
                  top: `${Math.min(zoomDrag.startYCss, zoomDrag.currentYCss)}px`,
                  width: `${Math.abs(zoomDrag.currentXCss - zoomDrag.startXCss)}px`,
                  height: `${Math.abs(zoomDrag.currentYCss - zoomDrag.startYCss)}px`,
                  border: '2px solid #4aa3ff',
                  background: 'rgba(74, 163, 255, 0.15)',
                  boxSizing: 'border-box',
                }}
              />
            )}
          </div>
        </div>
      </section>

      <aside
        className="mv-viewer-info-stack mv-sdv2d-wbv-info-panel"
        style={{
          position: 'absolute',
          top: 0,
          right: 0,
          zIndex: 5,
          transform: lineInfoCollapsed ? 'translateX(calc(100% + 10px))' : 'translateX(0)',
          transition: 'transform 180ms ease',
          pointerEvents: lineInfoCollapsed ? 'none' : 'auto',
          width: '330px',
          minWidth: '330px',
          height: '100%',
          overflowY: 'auto',
          boxSizing: 'border-box',
        }}
      >
        
        <button
          className="mv-viewer-compact-button mv-viewer-info-collapse-button"
          onClick={() => setLineInfoCollapsed((value) => !value)}
          title={lineInfoCollapsed ? 'Expand Line Info' : 'Collapse Line Info'}
          aria-label={lineInfoCollapsed ? 'Expand Line Info' : 'Collapse Line Info'}
        >
          {lineInfoCollapsed ? '◀' : '▶'}
        </button>

        <h3
          className="mv-viewer-controls-title mv-viewer-info-primary-heading"
          style={{ margin: 0 }}
        >
          Line Info
        </h3>

        {!lineInfoCollapsed && (
          <div
            style={{
              overflowY: 'auto',
              height: 'calc(100vh - 92px)',
              maxHeight: 'calc(100vh - 92px)',
              display: 'flex',
              flexDirection: 'column',
              gap: 8,
              overscrollBehavior: 'contain',
              scrollbarGutter: 'stable',
            }}
          >
          <aside
            className="mv-viewer-info-card"
            style={{
              boxSizing: 'border-box',
            }}
          >
            <div className="mv-type-property-grid mv-sdv3d-metadata-grid" style={{ display: 'grid' }}>
            <LineInfoRow label="Survey" value={surveyName} />
            <LineInfoRow label="Line" value={lineInfo?.line_name || lineInfo?.display_name || lineInfo?.filename || lineInfo?.id} />
            <LineInfoRow label="Rel Path" value={lineInfo?.source_relative_path || lineInfo?.metadata?.source_relative_path} />
            <LineInfoRow label="Shape" value={emptyState ? undefined : (lineInfo?.shape || metadata?.shape)} />
            <LineInfoRow label="Traces" value={emptyState ? undefined : (lineInfo?.trace_count || lineInfo?.shape?.[0] || metadata?.shape?.[0])} />
            <LineInfoRow label="Samples" value={emptyState ? undefined : (lineInfo?.sample_count || lineInfo?.shape?.[1] || metadata?.shape?.[1])} />
            <LineInfoRow
              label="Sample Rate"
              value={
                sectionInfo?.sampleIntervalMs
                  ? `${Number(sectionInfo.sampleIntervalMs).toFixed(3)} ms`
                  : "—"
              }
            />
            <LineInfoRow
              label="Record Length"
              value={
                sectionInfo?.sampleIntervalMs && sectionInfo?.sourceShape?.[1]
                  ? `${((Number(sectionInfo.sampleIntervalMs) * Number(sectionInfo.sourceShape[1])) / 1000).toFixed(3)} s`
                  : "—"
              }
            />
            <LineInfoRow label="Axis" value={lineInfo?.axis_order || metadata?.zarr?.axis_order || ['trace', 'sample']} />
            </div>
          </aside>

          <aside
            className="mv-viewer-info-card"
            style={{
              boxSizing: 'border-box',
            }}
          >
            <div className="mv-type-section-heading" style={{ marginBottom: 8 }}>
              Display Info
            </div>

            <div className="mv-type-property-grid mv-sdv3d-metadata-grid" style={{ display: 'grid' }}>

            <LineInfoRow label="Preset" value={formatDisplayPresetLabel(displayPreset)} />
            <LineInfoRow label="Display" value={formatDisplayModeLabel(displayMode)} />
            <LineInfoRow label="Raster map" value={formatRasterColorMapLabel(rasterColorMap)} />
            <LineInfoRow
              label="Chain"
              value={build2DProcessingChain({
                processingMode,
                frequencyFilter,
                agcWindowSec,
                clipPercentile: sectionInfo?.clipPercentile ?? clipPercentile,
                gain,
                reversePolarity,
                rasterColorMap,
                displayMode,
              })}
            />
            <LineInfoRow label="Render mode" value={sectionInfo?.windowed ? 'Windowed native source render' : 'Full-line preview render'} />
            <LineInfoRow label="Backend" value={formatRenderMs(sectionInfo?.backendRenderMs)} />
            <LineInfoRow label="Request" value={formatRenderMs(sectionInfo?.requestElapsedMs)} />
            <LineInfoRow label="Output" value={formatPixelCount(sectionInfo?.outputPixelCount)} />
            <LineInfoRow label="Clip Abs" value={sectionInfo?.clipAbs ? Number(sectionInfo.clipAbs).toFixed(1) : null} />
            <LineInfoRow label="Preview" value={sectionInfo?.previewShape} />
            <LineInfoRow label="Stride" value={sectionInfo?.traceStride ? `${sectionInfo.traceStride} × ${sectionInfo.sampleStride}` : null} />
            </div>
          </aside>

          <div className="mv-type-helper">
            Full SEG-Y headers and supporting-document links remain in the main Info tab.
          </div>
          </div>
        )}
      </aside>

      {lineInfoCollapsed && (
        <button
          onClick={() => setLineInfoCollapsed(false)}
          style={{
            position: 'absolute',
            top: 18,
            right: 0,
            zIndex: 10,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 8,
            minHeight: 136,
            padding: '10px 6px',
            background: 'var(--mv-surface-1)',
            color: 'var(--mv-text-primary)',
            border: '1px solid var(--mv-border-strong)',
            borderRight: 'none',
            borderRadius: '8px 0 0 8px',
            cursor: 'pointer',
            boxSizing: 'border-box',
          }}
          title="Expand information panel"
          aria-label="Expand information panel"
        >
          <span style={{ fontSize: 16, lineHeight: 1 }}>◀</span>
          <span
            style={{
              writingMode: 'vertical-rl',
              transform: 'rotate(180deg)',
              letterSpacing: 1,
              lineHeight: 1,
            }}
          >
            Info
          </span>
        </button>
      )}

      {menuCollapsed && (
        <button
          onClick={() => setMenuCollapsed(false)}
          style={{
            position: 'absolute',
            top: 18,
            left: 0,
            zIndex: 10,
            writingMode: 'vertical-rl',
            transform: 'rotate(180deg)',
            background: 'var(--mv-surface-1)',
            color: 'var(--mv-text-primary)',
            border: '1px solid var(--mv-border-strong)',
            borderLeft: 'none',
            borderRadius: '0 8px 8px 0',
            padding: '10px 6px',
            cursor: 'pointer',
            letterSpacing: 1,
          }}
          title="Expand controls"
          aria-label="Expand controls"
        >
          Controls ▶
        </button>
      )}
    </div>
  );
};
