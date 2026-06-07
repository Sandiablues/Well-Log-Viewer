/**
 * MultiViewer Well Log Viewer — Page Component
 * WL-BUILD-001 scaffold
 *
 * Page-level component for the Well Log Viewer / Wellbore Data QAQC module.
 *
 * Responsibilities:
 * - Fetch the backend-owned well_multitrack_v1 viewer package via API
 * - Pass the package down to MultiViewerWellLogViewer and WellQaqcPanel
 * - Render loading/error states
 *
 * Architecture rules:
 * - Does not parse LAS.
 * - Does not infer QAQC.
 * - Does not own MSI lifecycle state.
 * - All data comes from backend API calls.
 */

import React, { useEffect, useState } from 'react';
import { MultiViewerWellLogViewer } from './components/MultiViewerWellLogViewer';
import { WellQaqcPanel } from './components/WellQaqcPanel';
import { WellTrackToolbar } from './components/WellTrackToolbar';
import type { ViewerPackageResponse, WellMultitrackV1 } from './types';

interface WellLogViewerPageProps {
  datasetId: string;
  representationId: string;
}

/**
 * WellLogViewerPage
 *
 * Page-level entry point for the Well Log Viewer module.
 *
 * WL-BUILD-001: scaffold with API fetch stub and layout placeholder.
 * Full API integration wired in WL-BUILD-002.
 */
export const WellLogViewerPage: React.FC<WellLogViewerPageProps> = ({
  datasetId,
  representationId,
}) => {
  const [response, setResponse] = useState<ViewerPackageResponse>({
    data: null,
    loading: false,
    error: null,
  });

  useEffect(() => {
    // WL-BUILD-001: API call stubbed — endpoint returns 501 in scaffold state.
    // Full fetch wired in WL-BUILD-002.
    setResponse({ data: null, loading: false, error: 'WL-BUILD-001 scaffold — API not yet implemented.' });

    // TODO (WL-BUILD-002+):
    // const url = `/api/wells/${datasetId}/representations/${representationId}/viewer-package`;
    // setResponse(prev => ({ ...prev, loading: true }));
    // fetch(url)
    //   .then(res => res.json())
    //   .then((data: WellMultitrackV1) => setResponse({ data, loading: false, error: null }))
    //   .catch(err => setResponse({ data: null, loading: false, error: String(err) }));
  }, [datasetId, representationId]);

  const { data: viewerPackage, loading, error } = response;

  if (loading) {
    return (
      <div className="well-log-viewer-page well-log-viewer-page--loading" data-testid="well-log-viewer-page">
        <span>Loading well log viewer…</span>
      </div>
    );
  }

  if (error || !viewerPackage) {
    return (
      <div className="well-log-viewer-page well-log-viewer-page--error" data-testid="well-log-viewer-page">
        <div className="well-log-viewer-page__error-notice">
          <p>Well Log Viewer — scaffold placeholder (WL-BUILD-001)</p>
          <p>{error ?? 'No viewer package available.'}</p>
          <p>Dataset: {datasetId} / Representation: {representationId}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="well-log-viewer-page" data-testid="well-log-viewer-page">
      {/* Toolbar */}
      {/* Domain is fixed to MD in WL-BUILD-001; displayDomain not passed to toolbar. */}
      <WellTrackToolbar
        wellId={viewerPackage.well_id}
        wellboreId={viewerPackage.wellbore_id}
        depthUnit={viewerPackage.depth_unit}
        trackCount={viewerPackage.tracks.length}
      />

      {/* Main layout: viewer + QAQC panel */}
      <div className="well-log-viewer-page__layout">
        <div className="well-log-viewer-page__viewer-pane">
          <MultiViewerWellLogViewer viewerPackage={viewerPackage} height={700} />
        </div>
        <div className="well-log-viewer-page__qaqc-pane">
          <WellQaqcPanel findings={viewerPackage.qaqc_findings} />
        </div>
      </div>
    </div>
  );
};

export default WellLogViewerPage;
