/**
 * MultiViewer Well Log Viewer — Shell Viewer Component
 * WL-BUILD-001B
 *
 * This component:
 * - Receives a backend-owned WellMultitrackV1 viewer package as a prop
 * - Passes it through equinorWellLogAdapter.adaptToViDEx()
 * - Renders via VidExWellLogRenderer (the documented ViDEx rendering boundary)
 *
 * Architecture rules:
 * - Does not parse LAS.
 * - Does not infer QAQC.
 * - Does not own lifecycle state.
 * - Only renders what the backend provides.
 * - ViDEx integration is isolated in VidExWellLogRenderer.
 * - This component does NOT import @equinor/videx-wellog directly.
 *
 * WL-BUILD-001B: real ViDEx rendering via LogController.
 * Fake cards and synthetic SVG waveforms from WL-BUILD-001A are removed.
 */

import React from 'react';
import { adaptToViDEx } from '../adapters/equinorWellLogAdapter';
import { VidExWellLogRenderer } from '../adapters/videxWellLogRenderer';
import type { WellMultitrackV1 } from '../types';

interface MultiViewerWellLogViewerProps {
  /** Backend-owned viewer package. Fetched by the page component; passed in as prop. */
  viewerPackage: WellMultitrackV1;
  /**
   * Curve samples keyed by curve_id — [depth, value | null][] per curve.
   *
   * In production: fetched from each curve's samples_url after receiving
   * the viewer package from the backend API.
   * In WL-BUILD-001B: supplied from mockCurveSamples fixture via InspectionShell.
   */
  curveSamples: Record<string, (number | null)[][]>;
  /** Display height in pixels. Defaults to 600. */
  height?: number;
}

/**
 * MultiViewerWellLogViewer
 *
 * Shell component. Translates WellMultitrackV1 → ViDEx config via the adapter,
 * then passes the result to VidExWellLogRenderer for actual rendering.
 *
 * The rendering boundary is VidExWellLogRenderer — not this component.
 * This component does not hold ViDEx state or import ViDEx classes.
 */
export const MultiViewerWellLogViewer: React.FC<MultiViewerWellLogViewerProps> = ({
  viewerPackage,
  curveSamples,
  height = 600,
}) => {
  // Translate backend contract to ViDEx-facing config via the adapter.
  // The adapter does not import @equinor/videx-wellog.
  const adapterOutput = adaptToViDEx(viewerPackage);

  return (
    <div
      className="multiviewer-well-log-viewer"
      style={{ width: '100%', height, overflow: 'hidden', position: 'relative' }}
      data-testid="multiviewer-well-log-viewer"
      data-dataset-id={viewerPackage.dataset_id}
      data-representation-id={viewerPackage.representation_id}
      data-domain={viewerPackage.display_domain}
    >
      <VidExWellLogRenderer
        adapterOutput={adapterOutput}
        curveSamples={curveSamples}
        height={height}
      />
    </div>
  );
};

export default MultiViewerWellLogViewer;
