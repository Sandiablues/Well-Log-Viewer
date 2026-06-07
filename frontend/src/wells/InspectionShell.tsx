/**
 * MultiViewer Well Log Viewer — Inspection Shell
 * WL-BUILD-001B
 *
 * Visual inspection wrapper for proving real ViDEx rendering with mock
 * backend-owned well_multitrack_v1 data.
 *
 * Renders:
 * - Mock data banner (amber, always visible)
 * - Application header with sprint label
 * - WellLogViewerPage with inspectionPackage + inspectionSamples props
 *
 * The viewer area is a real ViDEx LogController render — not fake cards.
 *
 * Rules:
 * - Does not parse LAS.
 * - Does not infer QAQC.
 * - Does not introduce lifecycle state.
 * - ViDEx is behind the VidExWellLogRenderer boundary.
 * - This component must not be used in production data paths.
 */

import React from 'react';
import {
  mockWellMultitrackPackage,
  mockCurveSamples,
} from './fixtures/mockWellMultitrackPackage';
import { WellLogViewerPage } from './WellLogViewerPage';

/**
 * InspectionShell
 *
 * Mounts the Well Log Viewer with mock backend-owned data for
 * visual review and proof-of-render of the WL-BUILD-001B implementation.
 */
export const InspectionShell: React.FC = () => (
  <div className="mvwlv-inspection-shell">

    {/* Mock data notice */}
    <div className="mvwlv-mock-notice" role="alert" aria-label="Mock inspection data notice">
      <span className="mvwlv-mock-notice__icon" aria-hidden="true">⚠</span>
      <span className="mvwlv-mock-notice__label">Mock inspection data only</span>
      <span className="mvwlv-mock-notice__detail">
        — well_multitrack_v1 fixture · real ViDEx rendering · WL-BUILD-001B proof-of-render
      </span>
    </div>

    {/* Application header */}
    <header className="mvwlv-app-header" role="banner">
      <div className="mvwlv-app-header__brand">
        <span className="mvwlv-app-header__product">MultiViewer</span>
        <span className="mvwlv-app-header__module">Well Log Viewer</span>
      </div>
      <span className="mvwlv-app-header__sprint">WL-BUILD-001B</span>
    </header>

    {/* Well Log Viewer via inspection prop path */}
    <WellLogViewerPage
      datasetId={mockWellMultitrackPackage.dataset_id}
      representationId={mockWellMultitrackPackage.representation_id}
      inspectionPackage={mockWellMultitrackPackage}
      inspectionSamples={mockCurveSamples}
    />

  </div>
);

export default InspectionShell;
