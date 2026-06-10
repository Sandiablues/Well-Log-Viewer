/**
 * MultiViewer Well Log Viewer — Inspection Shell
 * WL-BUILD-001B + WLV-SOURCE-INTAKE-7
 *
 * Shell-level entry point for the Well Log Viewer and the WLV Source Intake
 * workbench. Source Intake consumes backend-owned contracts; it does not parse
 * LAS in the frontend, infer lifecycle state, or implement conversion.
 */

import React, { useState } from 'react';
import {
  mockWellMultitrackPackage,
  mockCurveSamples,
} from './fixtures/mockWellMultitrackPackage';
import { SourceIntakeWorkbench } from './source-intake/SourceIntakeWorkbench';
import { WellLogViewerPage } from './WellLogViewerPage';

type ShellView = 'source-intake' | 'well-viewer';

export const InspectionShell: React.FC = () => {
  const [activeView, setActiveView] = useState<ShellView>('source-intake');

  return (
    <div className="mvwlv-inspection-shell">
      <div className="mvwlv-mock-notice" role="alert" aria-label="Development shell notice">
        <span className="mvwlv-mock-notice__icon" aria-hidden="true">⚠</span>
        <span className="mvwlv-mock-notice__label">Development shell</span>
        <span className="mvwlv-mock-notice__detail">
          — Source Intake uses backend contracts · viewer tab still uses inspection data
        </span>
      </div>

      <header className="mvwlv-app-header" role="banner">
        <div className="mvwlv-app-header__brand">
          <span className="mvwlv-app-header__product">MultiViewer</span>
          <span className="mvwlv-app-header__module">Well Log Viewer</span>
        </div>
        <nav className="mvwlv-app-header__nav" aria-label="Well Log Viewer sections">
          <button
            type="button"
            className={activeView === 'source-intake' ? 'is-active' : ''}
            onClick={() => setActiveView('source-intake')}
          >
            Sources
          </button>
          <button
            type="button"
            className={activeView === 'well-viewer' ? 'is-active' : ''}
            onClick={() => setActiveView('well-viewer')}
          >
            Well Viewer
          </button>
        </nav>
        <span className="mvwlv-app-header__sprint">WLV-SOURCE-INTAKE-7</span>
      </header>

      {activeView === 'source-intake' ? (
        <SourceIntakeWorkbench />
      ) : (
        <WellLogViewerPage
          datasetId={mockWellMultitrackPackage.dataset_id}
          representationId={mockWellMultitrackPackage.representation_id}
          inspectionPackage={mockWellMultitrackPackage}
          inspectionSamples={mockCurveSamples}
        />
      )}
    </div>
  );
};

export default InspectionShell;
