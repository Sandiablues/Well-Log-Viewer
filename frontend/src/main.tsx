import React from 'react';
/**
 * WL-PROTOTYPE-001 — Track Layout Editor Working Template
 *
 * Working frontend-only prototype for dbMap-style WLV track layout behavior.
 * No LAS parsing, no backend persistence, and no production ViDEx wiring here.
 */

import ReactDOM from 'react-dom/client';
import { TrackLayoutPrototype } from './wells/prototype/TrackLayoutPrototype';

const rootElement = document.getElementById('root');
if (!rootElement) {
  throw new Error('Root element #root not found.');
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <TrackLayoutPrototype />
  </React.StrictMode>,
);
