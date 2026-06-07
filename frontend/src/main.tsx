/**
 * MultiViewer Well Log Viewer — Application Entry Point
 * WL-BUILD-001 scaffold
 *
 * Minimal entry point. The WellLogViewerPage will be mounted here
 * when routing is wired in a later sprint.
 */

import React from 'react';
import ReactDOM from 'react-dom/client';

// Scaffold placeholder — full routing wired in WL-BUILD-002+
const ScaffoldRoot: React.FC = () => (
  <div style={{ padding: '2rem', fontFamily: 'sans-serif' }}>
    <h1>MultiViewer Well Log Viewer</h1>
    <p>WL-BUILD-001 scaffold — application entry point placeholder.</p>
    <p>
      Routing and page mounting will be wired in WL-BUILD-002.
      The <code>WellLogViewerPage</code> component is available at{' '}
      <code>src/wells/WellLogViewerPage.tsx</code>.
    </p>
  </div>
);

const rootElement = document.getElementById('root');
if (!rootElement) {
  throw new Error('Root element #root not found.');
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <ScaffoldRoot />
  </React.StrictMode>,
);
