/**
 * MultiViewer Well Log Viewer — Shell Viewer Component
 * WL-BUILD-001 scaffold
 *
 * This component:
 * - Receives a backend-owned WellMultitrackV1 viewer package as a prop
 * - Passes it through the equinorWellLogAdapter
 * - Renders via @equinor/videx-wellog (wired in a later sprint)
 *
 * Architecture rules:
 * - Does not parse LAS.
 * - Does not infer QAQC.
 * - Does not own lifecycle state.
 * - Only renders what the backend provides.
 * - ViDEx integration is behind the adapter — not called directly here.
 */

import React from 'react';
import { adaptToViDEx } from '../adapters/equinorWellLogAdapter';
import type { WellMultitrackV1 } from '../types';

interface MultiViewerWellLogViewerProps {
  /** Backend-owned viewer package. Fetched by the page component; passed in as prop. */
  viewerPackage: WellMultitrackV1;
  /** Display height in pixels. Defaults to 600. */
  height?: number;
}

/**
 * MultiViewerWellLogViewer
 *
 * Shell component that renders a well_multitrack_v1 viewer package via the
 * Equinor ViDEx adapter.
 *
 * WL-BUILD-001: renders a placeholder panel with contract metadata.
 * Full ViDEx rendering wired in a later sprint.
 */
export const MultiViewerWellLogViewer: React.FC<MultiViewerWellLogViewerProps> = ({
  viewerPackage,
  height = 600,
}) => {
  // Translate backend contract to ViDEx-facing props via adapter.
  // ViDEx is never called with the raw WellMultitrackV1 directly.
  const viDExProps = adaptToViDEx(viewerPackage);

  // WL-BUILD-001: ViDEx component not yet wired.
  // Render contract metadata as a scaffold placeholder.
  return (
    <div
      className="multiviewer-well-log-viewer"
      style={{ height, overflow: 'hidden', position: 'relative' }}
      data-testid="multiviewer-well-log-viewer"
      data-dataset-id={viewerPackage.dataset_id}
      data-representation-id={viewerPackage.representation_id}
    >
      {/* Scaffold placeholder — replaced by ViDEx renderer in WL-BUILD-002+ */}
      <div className="multiviewer-well-log-viewer__scaffold-notice">
        <p>
          <strong>Well Log Viewer</strong> — scaffold placeholder (WL-BUILD-001)
        </p>
        <ul>
          <li>Package version: {viewerPackage.viewer_package_version}</li>
          <li>Well: {viewerPackage.well_id} / {viewerPackage.wellbore_id}</li>
          <li>Domain: {viewerPackage.display_domain} ({viewerPackage.depth_unit})</li>
          <li>
            Depth range: {viewerPackage.depth_range.min}–{viewerPackage.depth_range.max}{' '}
            {viewerPackage.depth_unit}
          </li>
          <li>Tracks: {viewerPackage.tracks.length}</li>
          <li>QAQC findings: {viewerPackage.qaqc_findings.length}</li>
          <li>Adapter primary axis: {viDExProps.primaryAxis}</li>
        </ul>
        <p className="multiviewer-well-log-viewer__scaffold-notice--subtext">
          ViDEx rendering will be wired in WL-BUILD-002.
        </p>
      </div>
    </div>
  );
};

export default MultiViewerWellLogViewer;
