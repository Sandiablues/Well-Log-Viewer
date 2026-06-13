import { useEffect, useState } from 'react';
import { fetchWlvJson } from '../../api/wlvBackendClient';

type WbvViewerState =
  | 'not_loaded'
  | 'missing_survey'
  | 'invalid_survey'
  | 'relative_only'
  | 'available'
  | 'needs_review'
  | 'unavailable';

type WbvWarning = {
  code?: string;
  severity?: 'info' | 'warning' | 'error' | string;
  message?: string;
  target?: string | null;
};

type WbvAvailableLayers = {
  trajectory?: boolean;
  survey_stations?: boolean;
  depth_labels?: boolean;
  formation_tops?: boolean;
  lithology?: boolean;
  casing?: boolean;
  completions?: boolean;
  loaded_curves?: boolean;
  curve_attributes?: boolean;
};

type WbvSourceSession = {
  contract_kind?: string;
  active_viewer_package_id?: string | null;
  loaded_product_count?: number;
  source_product_ids?: string[];
};

type WbvSessionContract = {
  contract_kind?: string;
  contract_version?: string;
  viewer?: 'WBV';
  active_managed_well_id?: string | null;
  well_id?: string | null;
  well_name?: string | null;
  viewer_state?: WbvViewerState;
  coordinate_mode?: string;
  source_session?: WbvSourceSession | null;
  available_layers?: WbvAvailableLayers;
  warnings?: WbvWarning[];
};

type WbvViewerPackageContract = {
  contract_kind?: string;
  contract_version?: string;
  viewer?: 'WBV';
  managed_well_id?: string;
  well_id?: string;
  well_name?: string;
  viewer_state?: WbvViewerState;
  coordinate_mode?: string;
  depth_unit?: string;
  angle_unit?: string;
  trajectory?: {
    method?: string | null;
    source?: string | null;
    stations?: unknown[];
    render_points?: unknown[];
  };
  available_layers?: WbvAvailableLayers;
  available_attribute_tracks?: Array<{
    product_id?: string;
    curve_name?: string | null;
    display_name?: string | null;
    curve_family?: string | null;
    unit?: string | null;
  }>;
  warnings?: WbvWarning[];
};

type WbvLoadState = {
  session: WbvSessionContract | null;
  viewerPackage: WbvViewerPackageContract | null;
  loading: boolean;
  error: string | null;
};

type Wellbore3DPageProps = {
  activeManagedWellId: string | null;
  onOpenLogViewer: () => void;
};

const initialState: WbvLoadState = {
  session: null,
  viewerPackage: null,
  loading: true,
  error: null,
};

function stateLabel(value: string | null | undefined): string {
  if (!value) return 'unknown';
  return value.replace(/_/g, ' ');
}

function layerRows(layers: WbvAvailableLayers | undefined): Array<[string, boolean]> {
  return [
    ['Trajectory', Boolean(layers?.trajectory)],
    ['Survey stations', Boolean(layers?.survey_stations)],
    ['Depth labels', Boolean(layers?.depth_labels)],
    ['Formation tops', Boolean(layers?.formation_tops)],
    ['Lithology intervals', Boolean(layers?.lithology)],
    ['Casing / hole sections', Boolean(layers?.casing)],
    ['Completions', Boolean(layers?.completions)],
    ['Loaded curve attributes', Boolean(layers?.curve_attributes)],
  ];
}

function warningRows(
  session: WbvSessionContract | null,
  viewerPackage: WbvViewerPackageContract | null,
): WbvWarning[] {
  return [
    ...(session?.warnings ?? []),
    ...(viewerPackage?.warnings ?? []),
  ];
}

export function Wellbore3DPage({ activeManagedWellId, onOpenLogViewer }: Wellbore3DPageProps) {
  const [state, setState] = useState<WbvLoadState>(initialState);

  const loadWbvSession = async () => {
    setState((current) => ({ ...current, loading: true, error: null }));
    try {
      const session = await fetchWlvJson<WbvSessionContract>('/api/wlv/wbv/session');
      const managedWellId = session.active_managed_well_id ?? activeManagedWellId;
      const viewerPackage = managedWellId
        ? await fetchWlvJson<WbvViewerPackageContract>(`/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/viewer-package`)
        : null;
      setState({ session, viewerPackage, loading: false, error: null });
    } catch (caught) {
      setState({
        session: null,
        viewerPackage: null,
        loading: false,
        error: caught instanceof Error ? caught.message : 'Unable to load WBV session',
      });
    }
  };

  useEffect(() => {
    void loadWbvSession();
  }, [activeManagedWellId]);

  const session = state.session;
  const viewerPackage = state.viewerPackage;
  const viewerState = viewerPackage?.viewer_state ?? session?.viewer_state ?? 'not_loaded';
  const layers = viewerPackage?.available_layers ?? session?.available_layers;
  const warnings = warningRows(session, viewerPackage);
  const hasTrajectory = Boolean(viewerPackage?.trajectory?.render_points?.length);
  const loadedCurveCount = session?.source_session?.loaded_product_count ?? viewerPackage?.available_attribute_tracks?.length ?? 0;

  return (
    <section className="wlv-wbv-page" aria-label="3D Wellbore Viewer">
      <header className="wlv-wbv-header">
        <div>
          <span className="wlv-page-kicker">3D Wellbore</span>
          <h1>3D Wellbore Viewer</h1>
          <p>
            Backend-owned WBV page shell. Trajectory rendering remains unavailable until a deviation survey package is registered.
          </p>
        </div>
        <div className="wlv-wbv-header-actions" aria-label="3D Wellbore Viewer actions">
          <span className={`wlv-wbv-state-pill wlv-wbv-state-pill--${viewerState}`}>{stateLabel(viewerState)}</span>
          <button type="button" onClick={() => void loadWbvSession()}>Refresh</button>
          <button type="button" onClick={onOpenLogViewer}>Open WDV</button>
        </div>
      </header>

      <div className="wlv-wbv-layout">
        <aside className="wlv-wbv-panel wlv-wbv-panel--left" aria-label="WBV display controls">
          <div className="wlv-wbv-panel-heading">
            <span>Display Layers</span>
            <strong>WBV Controls</strong>
          </div>
          <div className="wlv-wbv-control-list">
            {layerRows(layers).map(([label, available]) => (
              <label className={!available ? 'is-disabled' : ''} key={label}>
                <input type="checkbox" checked={available} disabled readOnly />
                <span>{label}</span>
              </label>
            ))}
          </div>
          <div className="wlv-wbv-control-group" aria-label="Reserved view controls">
            <button type="button" disabled>Reset View</button>
            <button type="button" disabled>Fit Well</button>
            <button type="button" disabled>Top View</button>
            <button type="button" disabled>Side View</button>
          </div>
        </aside>

        <main className="wlv-wbv-scene-shell" aria-label="WBV 3D scene shell">
          <div className="wlv-wbv-scene-frame">
            <div className="wlv-wbv-axis-label wlv-wbv-axis-label--x">X</div>
            <div className="wlv-wbv-axis-label wlv-wbv-axis-label--y">Y</div>
            <div className="wlv-wbv-axis-label wlv-wbv-axis-label--z">Z / TVD</div>
            <div className="wlv-wbv-bounding-box" aria-hidden="true">
              <div className="wlv-wbv-bounding-box__top" />
              <div className="wlv-wbv-bounding-box__front" />
              <div className="wlv-wbv-bounding-box__side" />
            </div>
            <div className="wlv-wbv-scene-message">
              {state.loading ? (
                <>
                  <h2>Loading WBV session…</h2>
                  <p>Fetching backend-owned WBV availability state.</p>
                </>
              ) : state.error ? (
                <>
                  <h2>WBV session unavailable</h2>
                  <p>{state.error}</p>
                </>
              ) : !hasTrajectory ? (
                <>
                  <h2>Trajectory package not available</h2>
                  <p>No backend-owned deviation survey / trajectory package is available yet. WBV will not fabricate a 3D well path.</p>
                </>
              ) : (
                <>
                  <h2>Trajectory package detected</h2>
                  <p>The render package is available. Actual 3D rendering is reserved for the next WBV block.</p>
                </>
              )}
            </div>
          </div>
        </main>

        <aside className="wlv-wbv-panel wlv-wbv-panel--right" aria-label="WBV inspection panel">
          <div className="wlv-wbv-panel-heading">
            <span>Inspection</span>
            <strong>Session State</strong>
          </div>
          <dl className="wlv-wbv-session-list">
            <dt>Well</dt>
            <dd>{viewerPackage?.well_name ?? session?.well_name ?? 'Not loaded'}</dd>
            <dt>Managed ID</dt>
            <dd>{viewerPackage?.managed_well_id ?? session?.active_managed_well_id ?? 'None'}</dd>
            <dt>Viewer state</dt>
            <dd>{stateLabel(viewerState)}</dd>
            <dt>Coordinate mode</dt>
            <dd>{viewerPackage?.coordinate_mode ?? session?.coordinate_mode ?? 'unavailable'}</dd>
            <dt>Loaded curves</dt>
            <dd>{loadedCurveCount}</dd>
            <dt>Trajectory pts</dt>
            <dd>{viewerPackage?.trajectory?.render_points?.length ?? 0}</dd>
          </dl>

          <div className="wlv-wbv-warning-list">
            <h2>Warnings</h2>
            {warnings.length === 0 ? (
              <p>No WBV warnings reported.</p>
            ) : warnings.map((warning, index) => (
              <div className="wlv-wbv-warning-card" key={`${warning.code ?? 'warning'}-${index}`}>
                <strong>{warning.code ?? 'warning'}</strong>
                <span>{warning.severity ?? 'warning'}</span>
                <p>{warning.message ?? 'No warning detail provided.'}</p>
              </div>
            ))}
          </div>
        </aside>
      </div>
    </section>
  );
}
