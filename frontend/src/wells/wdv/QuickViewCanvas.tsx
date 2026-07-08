import { useMemo, useRef, useState } from 'react';
import type { DepthViewRange } from './WdvPresentationPrimitives';
import type { QuickViewCurve, QuickViewPackage, QuickViewSample } from './quickViewWorkflow';


const WDV_QV_SHARED_HEADER_TEXT_STYLE = {
  color: '#dfe6f1',
  fontSize: 11,
  fontWeight: 720,
  letterSpacing: '0.115em',
  lineHeight: 1,
  textTransform: 'uppercase' as const,
};

export const QUICK_VIEW_SINGLE_TRACK_WIDTH = 156;
export const QUICK_VIEW_MULTI_TRACK_WIDTH = 168;
export const QUICK_VIEW_DENSE_TRACK_WIDTH = 180;
const VIEW_HEIGHT = 900;
const HEADER_HEIGHT = 64;
const PLOT_PADDING = 12;
const SCALE_HEADROOM = 0.08;
const MAJOR_DEPTH_DIVISIONS = 10;
const MINOR_DEPTH_SUBDIVISIONS = 5;
const MAJOR_VERTICAL_DIVISIONS = 4;

const CURVE_COLORS = [
  '#7CFC00',
  '#45D6FF',
  '#FF4FD8',
  '#FFD84D',
  '#FF9F43',
  '#C084FC',
  '#7EE7C1',
  '#FF7A7A',
  '#5EA2FF',
  '#B9E769',
] as const;

export function quickViewTrackWidth(curveCount: number): number {
  if (curveCount <= 1) return QUICK_VIEW_SINGLE_TRACK_WIDTH;
  if (curveCount <= 3) return QUICK_VIEW_MULTI_TRACK_WIDTH;
  return QUICK_VIEW_DENSE_TRACK_WIDTH;
}

export function quickViewDisplayBounds(curve: Pick<QuickViewCurve, 'scale_min' | 'scale_max' | 'scale_type'>): [number, number] {
  let low = Number(curve.scale_min);
  let high = Number(curve.scale_max);
  if (!Number.isFinite(low) || !Number.isFinite(high)) return [0, 1];
  if (high < low) [low, high] = [high, low];

  if (curve.scale_type === 'logarithmic') {
    const positiveLow = Math.max(low, 1e-12);
    const positiveHigh = Math.max(high, positiveLow * 1.000001);
    const logLow = Math.log10(positiveLow);
    const logHigh = Math.log10(positiveHigh);
    const logSpan = Math.max(logHigh - logLow, 0.001);
    return [
      10 ** (logLow - logSpan * SCALE_HEADROOM),
      10 ** (logHigh + logSpan * SCALE_HEADROOM),
    ];
  }

  const span = high - low;
  if (span <= 0) {
    const pad = Math.max(Math.abs(low) * 0.05, 1);
    return [low - pad, high + pad];
  }
  const pad = span * SCALE_HEADROOM;
  return [low - pad, high + pad];
}

function curveX(curve: QuickViewCurve, value: number, trackWidth: number): number {
  const [low, high] = quickViewDisplayBounds(curve);
  let ratio: number;

  if (curve.scale_type === 'logarithmic') {
    const safeLow = Math.max(low, 1e-12);
    const safeHigh = Math.max(high, safeLow * 1.000001);
    const safeValue = Math.max(value, safeLow);
    ratio = (Math.log10(safeValue) - Math.log10(safeLow)) /
      (Math.log10(safeHigh) - Math.log10(safeLow));
  } else {
    ratio = (value - low) / (high - low || 1);
  }

  if (curve.scale_direction === 'reverse') ratio = 1 - ratio;
  const bounded = Math.max(0, Math.min(1, ratio));
  const plotRight = trackWidth - PLOT_PADDING;
  return PLOT_PADDING + bounded * (plotRight - PLOT_PADDING);
}

function formatRange(value: number): string {
  if (!Number.isFinite(value)) return '';
  const magnitude = Math.abs(value);
  if (magnitude !== 0 && (magnitude >= 10000 || magnitude < 0.01)) {
    return value.toExponential(2).replace(/\.00e/, 'e');
  }
  return Number(value.toPrecision(3)).toString();
}

function TrackGrid({ depthY, trackWidth }: { depthY: (fraction: number) => number; trackWidth: number }) {
  const minorDepthLines = Array.from(
    { length: MAJOR_DEPTH_DIVISIONS * MINOR_DEPTH_SUBDIVISIONS + 1 },
    (_, index) => index / (MAJOR_DEPTH_DIVISIONS * MINOR_DEPTH_SUBDIVISIONS),
  );
  const verticalLines = Array.from(
    { length: MAJOR_VERTICAL_DIVISIONS * 2 + 1 },
    (_, index) => index / (MAJOR_VERTICAL_DIVISIONS * 2),
  );
  const plotRight = trackWidth - PLOT_PADDING;

  return <g aria-hidden="true">
    {minorDepthLines.map((fraction, index) => {
      const major = index % MINOR_DEPTH_SUBDIVISIONS === 0;
      return <line
        key={`h-${index}`}
        x1={0}
        x2={trackWidth}
        y1={depthY(fraction)}
        y2={depthY(fraction)}
        className={major ? 'wlv-qv-grid-major' : 'wlv-qv-grid-minor'}
      />;
    })}
    {verticalLines.map((fraction, index) => {
      const major = index % 2 === 0;
      const x = PLOT_PADDING + fraction * (plotRight - PLOT_PADDING);
      return <line
        key={`v-${index}`}
        x1={x}
        x2={x}
        y1={HEADER_HEIGHT}
        y2={VIEW_HEIGHT}
        className={major ? 'wlv-qv-grid-major' : 'wlv-qv-grid-minor'}
      />;
    })}
  </g>;
}


function curveSegments(curve: QuickViewCurve): string[][] {
  if (curve.samples.length < 2) return [];
  const steps = curve.samples
    .slice(1)
    .map((sample, index) => Math.abs(sample.depth - curve.samples[index].depth))
    .filter((step) => Number.isFinite(step) && step > 0)
    .sort((a, b) => a - b);
  const medianStep = steps.length ? steps[Math.floor(steps.length / 2)] : 0;
  const gapLimit = medianStep > 0 ? medianStep * 1.75 : Number.POSITIVE_INFINITY;
  const segments: QuickViewSample[][] = [];
  let current: QuickViewSample[] = [];
  curve.samples.forEach((sample, index) => {
    const previous = curve.samples[index - 1];
    if (previous && Math.abs(sample.depth - previous.depth) > gapLimit) {
      if (current.length > 1) segments.push(current);
      current = [];
    }
    current.push(sample);
  });
  if (current.length > 1) segments.push(current);
  return segments.map((segment) => segment.map((sample) => `${sample.depth}:${sample.value}`));
}

export function QuickViewCanvas({
  pkg,
  onClose,
  onElevate,
  elevatePending = false,
  elevateMessage,
  viewDepthRange,
  displayDepthUnit,
  selectedDepth,
  intervalZoomActive,
  onIntervalSelected,
}: {
  pkg: QuickViewPackage;
  onClose: () => void;
  onElevate: () => void;
  elevatePending?: boolean;
  elevateMessage?: string | null;
  viewDepthRange: DepthViewRange;
  displayDepthUnit: 'm' | 'ft';
  selectedDepth?: number | null;
  intervalZoomActive: boolean;
  onIntervalSelected: (range: DepthViewRange) => void;
}) {
  const sourceUnit = pkg.depth_unit_label?.toLowerCase() === 'ft' ? 'ft'
    : pkg.depth_unit_label?.toLowerCase() === 'm' ? 'm'
    : null;
  const convertDepth = (value: number): number => {
    if (!sourceUnit || sourceUnit === displayDepthUnit) return value;
    return sourceUnit === 'm' ? value * 3.280839895013123 : value / 3.280839895013123;
  };
  const visibleSpan = viewDepthRange.max - viewDepthRange.min || 1;
  const y = (sourceDepth: number) => HEADER_HEIGHT + ((convertDepth(sourceDepth) - viewDepthRange.min) / visibleSpan) * (VIEW_HEIGHT - HEADER_HEIGHT);
  const depthY = (fraction: number) => HEADER_HEIGHT + fraction * (VIEW_HEIGHT - HEADER_HEIGHT);
  const [dragStartY, setDragStartY] = useState<number | null>(null);
  const [dragCurrentY, setDragCurrentY] = useState<number | null>(null);
  const plotRef = useRef<HTMLDivElement | null>(null);
  let paletteIndex = 0;

  const depthAtClientY = (clientY: number): number => {
    const rect = plotRef.current?.getBoundingClientRect();
    if (!rect) return viewDepthRange.min;
    const local = Math.max(HEADER_HEIGHT, Math.min(VIEW_HEIGHT, clientY - rect.top));
    const ratio = (local - HEADER_HEIGHT) / (VIEW_HEIGHT - HEADER_HEIGHT);
    return viewDepthRange.min + ratio * visibleSpan;
  };

  const dragSelection = useMemo(() => {
    if (dragStartY === null || dragCurrentY === null) return null;
    return {
      top: Math.min(dragStartY, dragCurrentY),
      height: Math.abs(dragCurrentY - dragStartY),
    };
  }, [dragStartY, dragCurrentY]);

  return <section className="wlv-qv-canvas" aria-label="Direct Quick View">
    <div className="wlv-qv-toolbar" style={{ minHeight: 42, display: 'flex', alignItems: 'center' }}>
      <span
        className="wlv-qv-toolbar-title"
        style={{
          minWidth: 0,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          color: '#cbd4e1',
          fontSize: 11,
          fontWeight: 400,
          lineHeight: 1,
        }}
      >
        <span className="wlv-qv-shared-header-text" style={WDV_QV_SHARED_HEADER_TEXT_STYLE}>QUICK VIEW:</span>{' '}
        <span style={{ color: '#cbd4e1', fontSize: 11, fontWeight: 400, letterSpacing: 0, lineHeight: 1 }}>{pkg.filename}</span>
      </span>
      <div className="wlv-qv-toolbar-actions"><button type="button" onClick={onElevate} disabled={elevatePending}>{elevatePending ? 'Sending…' : 'Send Quick View to Sources'}</button><button type="button" onClick={onClose}>Close Quick View</button>{elevateMessage ? <small>{elevateMessage}</small> : null}</div>
    </div>

    <div
      ref={plotRef}
      className={`wlv-qv-scroll ${intervalZoomActive ? 'wlv-qv-interval-active' : ''}`}
      onPointerDown={(event) => {
        if (!intervalZoomActive) return;
        event.currentTarget.setPointerCapture(event.pointerId);
        const rect = event.currentTarget.getBoundingClientRect();
        const local = Math.max(HEADER_HEIGHT, Math.min(VIEW_HEIGHT, event.clientY - rect.top));
        setDragStartY(local);
        setDragCurrentY(local);
      }}
      onPointerMove={(event) => {
        if (!intervalZoomActive || dragStartY === null) return;
        const rect = event.currentTarget.getBoundingClientRect();
        setDragCurrentY(Math.max(HEADER_HEIGHT, Math.min(VIEW_HEIGHT, event.clientY - rect.top)));
      }}
      onPointerUp={(event) => {
        if (!intervalZoomActive || dragStartY === null) return;
        const startDepth = depthAtClientY((plotRef.current?.getBoundingClientRect().top ?? 0) + dragStartY);
        const endDepth = depthAtClientY(event.clientY);
        setDragStartY(null);
        setDragCurrentY(null);
        if (Math.abs(endDepth - startDepth) > Math.max(visibleSpan * 0.002, 0.001)) {
          onIntervalSelected({ min: Math.min(startDepth, endDepth), max: Math.max(startDepth, endDepth) });
        }
      }}
      onPointerCancel={() => { setDragStartY(null); setDragCurrentY(null); }}
    >
      <div className="wlv-qv-depth" style={{ height: VIEW_HEIGHT }}>
        <header>
          <b>MD</b>
          <small>{sourceUnit ? displayDepthUnit : ''}</small>
        </header>
        {Array.from({ length: MAJOR_DEPTH_DIVISIONS + 1 }, (_, index) => {
          const depth = viewDepthRange.min + visibleSpan * index / MAJOR_DEPTH_DIVISIONS;
          return <span key={index} style={{ top: `${depthY(index / MAJOR_DEPTH_DIVISIONS)}px` }}>
            {depth.toFixed(0)}
          </span>;
        })}
      </div>

      {pkg.tracks.map((track) => {
        const curves = track.curves.map((curve) => ({
          curve,
          color: CURVE_COLORS[(paletteIndex++) % CURVE_COLORS.length],
        }));
        const trackWidth = quickViewTrackWidth(curves.length);

        return <div className="wlv-qv-track" key={track.track_id} style={{ width: trackWidth, height: VIEW_HEIGHT }}>
          <header>
            <b>{track.title}</b>
            <div className="wlv-qv-curve-legend">
              {curves.map(({ curve, color }) => <small key={curve.curve_id}>
                <i style={{ backgroundColor: color }} />
                <span>{curve.mnemonic}{curve.unit_label ? `  ${curve.unit_label}` : ''}</span>
                <em>{formatRange(curve.scale_min)} — {formatRange(curve.scale_max)}</em>
              </small>)}
            </div>
          </header>

          <svg width={trackWidth} height={VIEW_HEIGHT} role="img" aria-label={`${track.title} curves`}>
            <TrackGrid depthY={depthY} trackWidth={trackWidth} />
            {curves.flatMap(({ curve, color }) => {
              const segments = curveSegments(curve);
              return segments.map((segment, segmentIndex) => {
                const points = segment.map((token) => {
                  const [depth, value] = token.split(':').map(Number);
                  return `${curveX(curve, value, trackWidth)},${y(depth)}`;
                }).join(' ');
                return <polyline key={`${curve.curve_id}-${segmentIndex}`} points={points} fill="none" stroke={color} strokeWidth="1.2" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />;
              });
            })}
          </svg>
        </div>;
      })}
      {selectedDepth !== null && selectedDepth !== undefined && selectedDepth >= viewDepthRange.min && selectedDepth <= viewDepthRange.max ? <div className="wlv-qv-selected-depth-line" style={{ top: y(selectedDepth) }} aria-label={`Selected MD ${selectedDepth}`} /> : null}
      {dragSelection ? <div className="wlv-qv-drag-selection" style={{ top: dragSelection.top, height: dragSelection.height }} /> : null}
    </div>
  </section>;
}

