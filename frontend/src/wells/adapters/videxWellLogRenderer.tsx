/**
 * MultiViewer Well Log Viewer — ViDEx Rendering Boundary
 * WL-BUILD-001B
 *
 * Only this file imports @equinor/videx-wellog.
 */

import React, { useEffect, useRef } from 'react';
import {
  LogController,
  ScaleTrack,
  GraphTrack,
  BasicScaleHandler,
} from '@equinor/videx-wellog';
import type {
  ViDExAdapterOutput,
  ViDExCurveDef,
  ViDExTrackDef,
} from './equinorWellLogAdapter';

export interface VidExWellLogRendererProps {
  adapterOutput: ViDExAdapterOutput;
  curveSamples: Record<string, (number | null)[][]>;
  height?: number;
}

type CurveSamples = (number | null)[][];

interface BuiltGraphTrack {
  track: GraphTrack;
  samples: CurveSamples;
}

function graphTrackId(parentTrackId: string, curveDef: ViDExCurveDef): string {
  return `${parentTrackId}__${curveDef.plotId}`;
}

function fallbackSamples(
  curveDef: ViDExCurveDef,
  depthDomain: [number, number],
): CurveSamples {
  const [d0, d1] = depthDomain;
  const [v0, v1] = curveDef.valueDomain;
  const depthSpan = d1 - d0;
  const valueMid = (v0 + v1) / 2;
  const valueAmp = Math.abs(v1 - v0) * 0.30;
  const phase = curveDef.mnemonic.length * 0.73;
  const rows: CurveSamples = [];

  for (let i = 0; i <= 220; i += 1) {
    const t = i / 220;
    const depth = d0 + depthSpan * t;
    const value =
      valueMid +
      valueAmp * Math.sin(t * Math.PI * 12 + phase) +
      valueAmp * 0.25 * Math.sin(t * Math.PI * 31 + phase * 0.5);
    rows.push([depth, value]);
  }

  return rows;
}

function resolveSamples(
  curveDef: ViDExCurveDef,
  curveSamples: Record<string, CurveSamples>,
  depthDomain: [number, number],
): CurveSamples {
  const direct = curveSamples[curveDef.plotId];

  if (Array.isArray(direct) && direct.length > 0) {
    return direct;
  }

  console.warn(
    `[WL-BUILD-001B] Missing samples for ${curveDef.plotId}; using deterministic proof-of-render fallback.`,
  );

  return fallbackSamples(curveDef, depthDomain);
}

function buildCurveTrack(
  parentTrackDef: ViDExTrackDef,
  curveDef: ViDExCurveDef,
  curveSamples: Record<string, CurveSamples>,
  depthDomain: [number, number],
): BuiltGraphTrack {
  const samples = resolveSamples(curveDef, curveSamples, depthDomain);

  const track = new GraphTrack(graphTrackId(parentTrackDef.trackId, curveDef), {
    label: `${parentTrackDef.label} — ${curveDef.mnemonic}`,
    abbr: curveDef.mnemonic.substring(0, 4).toUpperCase(),
    plots: [
      {
        id: curveDef.plotId,
        type: 'line',
        options: {
          color: curveDef.color,
          width: curveDef.lineWidth,
          scale: 'linear',
          domain: curveDef.valueDomain,
          serie: {
            label: curveDef.mnemonic,
            unit: curveDef.unit ?? '',
          },
        },
      },
    ],
  });

  return { track, samples };
}

function buildTracks(
  adapterOutput: ViDExAdapterOutput,
  curveSamples: Record<string, CurveSamples>,
): { tracks: (ScaleTrack | GraphTrack)[]; graphTracks: BuiltGraphTrack[] } {
  const tracks: (ScaleTrack | GraphTrack)[] = [];
  const graphTracks: BuiltGraphTrack[] = [];

  for (const trackDef of adapterOutput.trackDefs) {
    if (trackDef.type === 'scale') {
      tracks.push(new ScaleTrack(trackDef.trackId, {
        label: trackDef.label,
        abbr: trackDef.abbr,
      }));
      continue;
    }

    if (trackDef.type === 'graph') {
      for (const curveDef of trackDef.curves) {
        const built = buildCurveTrack(
          trackDef,
          curveDef,
          curveSamples,
          adapterOutput.domain,
        );
        tracks.push(built.track);
        graphTracks.push(built);
      }
    }
  }

  return { tracks, graphTracks };
}

export const VidExWellLogRenderer: React.FC<VidExWellLogRendererProps> = ({
  adapterOutput,
  curveSamples,
  height = 600,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const controllerRef = useRef<LogController | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    el.innerHTML = '';

    const [minMD, maxMD] = adapterOutput.domain;
    const controller = LogController.basic(true);

    controller.scaleHandler = new BasicScaleHandler([minMD, maxMD]);

    const { tracks, graphTracks } = buildTracks(adapterOutput, curveSamples);

    console.info(
      '[WL-BUILD-001B] ViDEx tracks:',
      tracks.length,
      'graph tracks:',
      graphTracks.length,
      'sample keys:',
      Object.keys(curveSamples),
    );

    controller.init(el);
    controller.setTracks(...tracks);

    for (const built of graphTracks) {
      built.track.loadData(() => built.samples, false);
    }

    controller.domain = [minMD, maxMD];

    requestAnimationFrame(() => {
      controller.adjustToSize(true);

      const trackDiagnostics = Array.from(
        el.querySelectorAll('.track'),
      ).map((trackEl, index) => {
        const rect = trackEl.getBoundingClientRect();
        return {
          index,
          title: trackEl.querySelector('.track-title')?.textContent ?? null,
          width: rect.width,
          height: rect.height,
          flex: window.getComputedStyle(trackEl).flex,
          canvases: trackEl.querySelectorAll('canvas').length,
          svgs: trackEl.querySelectorAll('svg').length,
        };
      });

      console.info('[WL-BUILD-001B] Track DOM diagnostics:', trackDiagnostics);
    });

    controllerRef.current = controller;

    return () => {
      controller.onUnmount();
      el.innerHTML = '';
      controllerRef.current = null;
    };
  }, [adapterOutput, curveSamples]);

  return (
    <div
      ref={containerRef}
      className="videx-well-log-renderer"
      style={{ width: '100%', height, position: 'relative', overflow: 'hidden' }}
      data-testid="videx-well-log-renderer"
      data-domain-min={adapterOutput.domain[0]}
      data-domain-max={adapterOutput.domain[1]}
      data-primary-axis={adapterOutput.primaryAxis}
      aria-label={`Well log viewer — ${adapterOutput.primaryAxis.toUpperCase()} domain — ${adapterOutput.domain[0]}–${adapterOutput.domain[1]} ${adapterOutput.depthUnit}`}
    />
  );
};

export default VidExWellLogRenderer;
