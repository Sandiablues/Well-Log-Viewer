/**
 * MultiViewer Well Log Viewer — Page Component
 * WL-BUILD-001B
 *
 * Page-level component for the Well Log Viewer / Wellbore Data QAQC module.
 *
 * Responsibilities:
 * - Fetch the backend-owned well_multitrack_v1 viewer package via API
 * - Fetch curve samples from each curve's samples_url (WL-BUILD-002+)
 * - Pass both down to MultiViewerWellLogViewer and WellQaqcPanel
 * - Render loading/error states
 *
 * Architecture rules:
 * - Does not parse LAS.
 * - Does not infer QAQC.
 * - Does not own MSI lifecycle state.
 * - All production data comes from backend API calls.
 *
 * Inspection props (WL-BUILD-001B):
 * - inspectionPackage: pre-assembled WellMultitrackV1 fixture
 * - inspectionSamples: pre-assembled curve samples per curve_id
 * These bypass the API fetch for visual proof-of-render inspection.
 * Must only be used by InspectionShell — not in production paths.
 */

import React, { useEffect, useState } from 'react';
import { MultiViewerWellLogViewer } from './components/MultiViewerWellLogViewer';
import { WellQaqcPanel } from './components/WellQaqcPanel';
import { WellTrackToolbar } from './components/WellTrackToolbar';
import type { ViewerPackageResponse, WellMultitrackV1 } from './types';

interface WellLogViewerPageProps {
  datasetId: string;
  representationId: string;
  /**
   * Inspection only: pre-assembled viewer package.
   * When set, the API fetch is skipped.
   * Must only be supplied by InspectionShell.
   */
  inspectionPackage?: WellMultitrackV1;
  /**
   * Inspection only: pre-assembled curve samples per curve_id.
   * In production, samples are fetched from each curve's samples_url.
   * Must only be supplied by InspectionShell.
   */
  inspectionSamples?: Record<string, (number | null)[][]>;
}

export const WellLogViewerPage: React.FC<WellLogViewerPageProps> = ({
  datasetId,
  representationId,
  inspectionPackage,
  inspectionSamples,
}) => {
  const [response, setResponse] = useState<ViewerPackageResponse>({
    data: null,
    loading: false,
    error: null,
  });

  // curveSamples state: in production populated by fetching samples_url per curve.
  // In inspection mode, populated from inspectionSamples prop.
  const [curveSamples, setCurveSamples] = useState<Record<string, (number | null)[][]>>(
    inspectionSamples ?? {}
  );

  useEffect(() => {
    if (inspectionPackage) {
      // Inspection path: use fixture directly. No API call.
      setResponse({ data: inspectionPackage, loading: false, error: null });
      setCurveSamples(inspectionSamples ?? {});
      return;
    }

    // Production path (WL-BUILD-001 scaffold state): API returns 501.
    // TODO (WL-BUILD-002+): fetch viewer package + curve samples from backend.
    setResponse({
      data: null,
      loading: false,
      error: 'WL-BUILD-001 scaffold — API not yet implemented.',
    });

    // TODO (WL-BUILD-002+):
    // const url = `/api/wells/${datasetId}/representations/${representationId}/viewer-package`;
    // setResponse(prev => ({ ...prev, loading: true }));
    // fetch(url)
    //   .then(res => res.json())
    //   .then((data: WellMultitrackV1) => {
    //     setResponse({ data, loading: false, error: null });
    //     // Then fetch samples for each curve in parallel:
    //     return fetchAllCurveSamples(data.tracks);
    //   })
    //   .then(samples => setCurveSamples(samples))
    //   .catch(err => setResponse({ data: null, loading: false, error: String(err) }));
  }, [datasetId, representationId, inspectionPackage, inspectionSamples]);

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
      {/* Toolbar — domain fixed to MD in WL-BUILD-001 */}
      <WellTrackToolbar
        wellId={viewerPackage.well_id}
        wellboreId={viewerPackage.wellbore_id}
        depthUnit={viewerPackage.depth_unit}
        trackCount={viewerPackage.tracks.length}
      />

      {/* Main layout: viewer + QAQC panel */}
      <div className="well-log-viewer-page__layout">
        <div className="well-log-viewer-page__viewer-pane">
          <MultiViewerWellLogViewer
            viewerPackage={viewerPackage}
            curveSamples={curveSamples}
            height={680}
          />
        </div>
        <div className="well-log-viewer-page__qaqc-pane">
          <WellQaqcPanel findings={viewerPackage.qaqc_findings} />
        </div>
      </div>
    </div>
  );
};

export default WellLogViewerPage;
