import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

export interface TrackBodyGeometryOptions {
  headerHeightPx: number;
  fallbackBodyHeightPx: number;
  minBodyHeightPx: number;
  maxBodyHeightPx: number;
  footerClearancePx: number;
  stripPaddingPx: number;
}

export interface TrackBodyGeometry {
  setContainerRef: (node: HTMLElement | null) => void;
  trackBodyHeightPx: number;
  trackTotalHeightPx: number;
}

function clampValue(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

export function useTrackBodyGeometry(options: TrackBodyGeometryOptions): TrackBodyGeometry {
  const {
    headerHeightPx,
    fallbackBodyHeightPx,
    minBodyHeightPx,
    maxBodyHeightPx,
    footerClearancePx,
    stripPaddingPx,
  } = options;

  const containerRef = useRef<HTMLElement | null>(null);
  const [trackBodyHeightPx, setTrackBodyHeightPx] = useState(fallbackBodyHeightPx);

  const recompute = useCallback(() => {
    const container = containerRef.current;
    if (!container) {
      setTrackBodyHeightPx(fallbackBodyHeightPx);
      return;
    }

    const rect = container.getBoundingClientRect();
    const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
    const availableBodyHeight =
      viewportHeight
      - rect.top
      - headerHeightPx
      - footerClearancePx
      - stripPaddingPx * 2;

    if (!Number.isFinite(availableBodyHeight) || availableBodyHeight <= 0) {
      setTrackBodyHeightPx(fallbackBodyHeightPx);
      return;
    }

    const nextHeight = Math.round(
      clampValue(availableBodyHeight, minBodyHeightPx, maxBodyHeightPx),
    );
    setTrackBodyHeightPx((current) => (current === nextHeight ? current : nextHeight));
  }, [fallbackBodyHeightPx, footerClearancePx, headerHeightPx, maxBodyHeightPx, minBodyHeightPx, stripPaddingPx]);

  const setContainerRef = useCallback((node: HTMLElement | null) => {
    containerRef.current = node;
    recompute();
  }, [recompute]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return undefined;

    recompute();

    const resizeObserver = new ResizeObserver(recompute);
    resizeObserver.observe(container);
    window.addEventListener('resize', recompute);
    window.visualViewport?.addEventListener('resize', recompute);

    return () => {
      resizeObserver.disconnect();
      window.removeEventListener('resize', recompute);
      window.visualViewport?.removeEventListener('resize', recompute);
    };
  }, [recompute]);

  return useMemo(() => ({
    setContainerRef,
    trackBodyHeightPx,
    trackTotalHeightPx: headerHeightPx + trackBodyHeightPx,
  }), [headerHeightPx, setContainerRef, trackBodyHeightPx]);
}
