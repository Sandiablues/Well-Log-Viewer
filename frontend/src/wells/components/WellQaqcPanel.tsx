/**
 * MultiViewer Well Log Viewer — QAQC Panel Component
 * WL-BUILD-001 scaffold
 *
 * Displays backend-provided QAQC findings.
 *
 * Architecture rules:
 * - Receives findings as props — does NOT generate or infer them.
 * - Backend (well_qaqc_service) owns all QAQC logic.
 * - Follows MultiViewer UI conventions (no filled colored buttons,
 *   consistent panel/card layout, consistent status states).
 */

import React from 'react';
import type { QaqcFinding, QaqcSeverity } from '../types';

interface WellQaqcPanelProps {
  /** Backend-owned QAQC findings from the well_multitrack_v1 package. */
  findings: QaqcFinding[];
  loading?: boolean;
  error?: string | null;
}

const SEVERITY_LABEL: Record<QaqcSeverity, string> = {
  info: 'Info',
  warning: 'Warning',
  error: 'Error',
};

/**
 * WellQaqcPanel
 *
 * Renders the backend-generated QAQC findings for a well representation.
 *
 * WL-BUILD-001: placeholder layout with severity grouping.
 * Full severity styling and grouping interactions deferred to later sprint.
 */
export const WellQaqcPanel: React.FC<WellQaqcPanelProps> = ({
  findings,
  loading = false,
  error = null,
}) => {
  if (loading) {
    return (
      <div className="well-qaqc-panel well-qaqc-panel--loading" data-testid="well-qaqc-panel">
        <span>Loading QAQC findings…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="well-qaqc-panel well-qaqc-panel--error" data-testid="well-qaqc-panel">
        <span>Error loading QAQC findings: {error}</span>
      </div>
    );
  }

  if (findings.length === 0) {
    return (
      <div className="well-qaqc-panel well-qaqc-panel--empty" data-testid="well-qaqc-panel">
        <span>No QAQC findings.</span>
      </div>
    );
  }

  return (
    <div className="well-qaqc-panel" data-testid="well-qaqc-panel">
      <div className="well-qaqc-panel__header">
        <span className="well-qaqc-panel__title">QAQC Findings</span>
        <span className="well-qaqc-panel__count">{findings.length}</span>
      </div>
      <ul className="well-qaqc-panel__findings-list">
        {findings.map((finding) => (
          <li
            key={finding.finding_id}
            className={`well-qaqc-panel__finding well-qaqc-panel__finding--${finding.severity}`}
            data-finding-id={finding.finding_id}
            data-severity={finding.severity}
          >
            <span className="well-qaqc-panel__finding-severity">
              {SEVERITY_LABEL[finding.severity]}
            </span>
            <span className="well-qaqc-panel__finding-code">{finding.code}</span>
            <span className="well-qaqc-panel__finding-message">{finding.message}</span>
          </li>
        ))}
      </ul>
    </div>
  );
};

export default WellQaqcPanel;
