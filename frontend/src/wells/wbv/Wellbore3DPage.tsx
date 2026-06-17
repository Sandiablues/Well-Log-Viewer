import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchWlvJson } from '../../api/wlvBackendClient';
import { WellboreTrajectoryRenderer, type WbvViewPreset } from './WellboreTrajectoryRenderer';

type WbvViewerState =
  | 'not_loaded'
  | 'missing_survey'
  | 'invalid_survey'
  | 'relative_only'
  | 'available'
  | 'available_vertical'
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
  depth_domain?: Record<string, unknown> | null;
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

type WbvRenderPoint = {
  station_index?: number;
  md?: number | null;
  tvd?: number | null;
  tvdss?: number | null;
  x?: number | null;
  y?: number | null;
  z?: number | null;
  inclination?: number | null;
  azimuth?: number | null;
  dogleg_severity?: number | null;
  east_departure?: number | null;
  north_departure?: number | null;
  source?: Record<string, unknown>;
};

type WbvTrajectoryPackage = {
  method?: string | null;
  source?: string | null;
  trajectory_class?: string | null;
  viewer_state?: string | null;
  station_count?: number | null;
  source_station_count?: number | null;
  fixture_sampling?: Record<string, unknown>;
  stations?: unknown[];
  render_points?: WbvRenderPoint[];
  warnings?: WbvWarning[];
};

type WbvAxisRange = {
  min?: number | null;
  max?: number | null;
};

type WbvBoundingBox = {
  x?: WbvAxisRange;
  y?: WbvAxisRange;
  z?: WbvAxisRange;
  md?: WbvAxisRange;
  tvd?: WbvAxisRange;
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
  trajectory?: WbvTrajectoryPackage;
  bounding_box?: WbvBoundingBox;
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

type NumericRange = {
  min: number | null;
  max: number | null;
};

const initialState: WbvLoadState = {
  session: null,
  viewerPackage: null,
  loading: true,
  error: null,
};

const viewPresetLabels: Record<WbvViewPreset, string> = {
  reset: 'Reset View',
  fit: 'Fit Well',
  top: 'Top View',
  side: 'Side View',
};

function stateLabel(value: string | null | undefined): string {
  if (!value) return 'unknown';
  return value.replace(/_/g, ' ');
}

function fieldLabel(value: string | null | undefined): string {
  if (!value) return 'None';
  return value.replace(/_/g, ' ');
}

function formatNumber(value: number | null | undefined, digits = 1): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—';
  return value.toLocaleString(undefined, {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
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
    ...(viewerPackage?.trajectory?.warnings ?? []),
  ];
}

function numericRange(values: Array<number | null | undefined>): NumericRange {
  const clean = values.filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
  if (clean.length === 0) return { min: null, max: null };
  return { min: Math.min(...clean), max: Math.max(...clean) };
}

function rangeFromBoundingBox(
  boundingBox: WbvBoundingBox | undefined,
  key: keyof WbvBoundingBox,
): NumericRange | null {
  const value = boundingBox?.[key];
  if (!value) return null;
  const min = typeof value.min === 'number' && Number.isFinite(value.min) ? value.min : null;
  const max = typeof value.max === 'number' && Number.isFinite(value.max) ? value.max : null;
  if (min === null && max === null) return null;
  return { min, max };
}

function rangeText(range: NumericRange | null, unit = '', digits = 1): string {
  if (!range || (range.min === null && range.max === null)) return '—';
  const suffix = unit ? ` ${unit}` : '';
  return `${formatNumber(range.min, digits)}–${formatNumber(range.max, digits)}${suffix}`;
}

function firstLastPoint(points: WbvRenderPoint[]): { first: WbvRenderPoint | null; last: WbvRenderPoint | null } {
  return {
    first: points.length > 0 ? points[0] : null,
    last: points.length > 0 ? points[points.length - 1] : null,
  };
}

function isVerticalTrajectory(points: WbvRenderPoint[], trajectoryClass: string | null | undefined): boolean {
  if (trajectoryClass === 'vertical_trajectory_candidate') return true;
  if (points.length === 0) return false;
  return points.every((point) => {
    const inclination = point.inclination ?? 0;
    const x = point.x ?? point.east_departure ?? 0;
    const y = point.y ?? point.north_departure ?? 0;
    return Math.abs(inclination) < 1e-9 && Math.abs(x) < 1e-9 && Math.abs(y) < 1e-9;
  });
}

function sampleRenderPoints(points: WbvRenderPoint[]): WbvRenderPoint[] {
  if (points.length <= 5) return points;
  const indices = [0, Math.floor(points.length * 0.25), Math.floor(points.length * 0.5), Math.floor(points.length * 0.75), points.length - 1];
  return Array.from(new Set(indices)).map((index) => points[index]).filter(Boolean);
}

export function Wellbore3DPage({ activeManagedWellId, onOpenLogViewer }: Wellbore3DPageProps) {
  const [state, setState] = useState<WbvLoadState>(initialState);
  const [viewPreset, setViewPreset] = useState<WbvViewPreset>('fit');
  const [viewCommandId, setViewCommandId] = useState(0);

  const requestViewPreset = (preset: WbvViewPreset) => {
    setViewPreset(preset);
    setViewCommandId((current) => current + 1);
  };

  const loadWbvSession = useCallback(async () => {
    setState((current) => ({ ...current, loading: true, error: null }));
    try {
      const session = await fetchWlvJson<WbvSessionContract>('/api/wlv/wbv/session');
      // An explicit managed-well context from the application shell is authoritative.
      // The session fallback is used only when WBV is opened without a selected well.
      const managedWellId = activeManagedWellId ?? session.active_managed_well_id;
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
  }, [activeManagedWellId]);

  useEffect(() => {
    void loadWbvSession();
  }, [loadWbvSession]);

  useEffect(() => {
    const refreshFromBackend = () => {
      void loadWbvSession();
    };
    const refreshWhenVisible = () => {
      if (document.visibilityState === 'visible') {
        refreshFromBackend();
      }
    };

    window.addEventListener('focus', refreshFromBackend);
    document.addEventListener('visibilitychange', refreshWhenVisible);

    return () => {
      window.removeEventListener('focus', refreshFromBackend);
      document.removeEventListener('visibilitychange', refreshWhenVisible);
    };
  }, [loadWbvSession]);

  const session = state.session;
  const viewerPackage = state.viewerPackage;
  const trajectory = viewerPackage?.trajectory;
  const renderPoints = trajectory?.render_points ?? [];
  const viewerState = viewerPackage?.viewer_state ?? session?.viewer_state ?? 'not_loaded';
  const layers = viewerPackage?.available_layers ?? session?.available_layers;
  const warnings = warningRows(session, viewerPackage);
  const hasTrajectory = renderPoints.length > 0;
  const depthUnit = viewerPackage?.depth_unit ?? 'ft';
  const angleUnit = viewerPackage?.angle_unit ?? 'deg';
  const loadedCurveCount = session?.source_session?.loaded_product_count ?? viewerPackage?.available_attribute_tracks?.length ?? 0;
  const verticalTrajectory = isVerticalTrajectory(renderPoints, trajectory?.trajectory_class ?? null);
  const sampledPoints = useMemo(() => sampleRenderPoints(renderPoints), [renderPoints]);
  const endpoints = firstLastPoint(renderPoints);
  const mdRange = rangeFromBoundingBox(viewerPackage?.bounding_box, 'md') ?? numericRange(renderPoints.map((point) => point.md));
  const tvdRange = rangeFromBoundingBox(viewerPackage?.bounding_box, 'tvd') ?? numericRange(renderPoints.map((point) => point.tvd));
  const xRange = rangeFromBoundingBox(viewerPackage?.bounding_box, 'x') ?? numericRange(renderPoints.map((point) => point.x ?? point.east_departure));
  const yRange = rangeFromBoundingBox(viewerPackage?.bounding_box, 'y') ?? numericRange(renderPoints.map((point) => point.y ?? point.north_departure));
  const zRange = rangeFromBoundingBox(viewerPackage?.bounding_box, 'z') ?? numericRange(renderPoints.map((point) => point.z));

  return (
    <section className="wlv-wbv-page" aria-label="3D Wellbore Viewer">
      <header className="wlv-wbv-header">
        <div>
          <span className="wlv-page-kicker">3D Wellbore</span>
          <h1>3D Wellbore Viewer</h1>
          <p>
            Backend-owned WBV page shell. This view now consumes the WBV trajectory package contract and reports real package state before 3D renderer work starts.
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

          <div className="wlv-wbv-package-card" aria-label="Trajectory package summary">
            <span>Trajectory Package</span>
            <strong>{hasTrajectory ? 'Detected' : 'Not available'}</strong>
            <dl>
              <dt>Class</dt>
              <dd>{fieldLabel(trajectory?.trajectory_class)}</dd>
              <dt>Method</dt>
              <dd>{fieldLabel(trajectory?.method)}</dd>
              <dt>Source</dt>
              <dd>{fieldLabel(trajectory?.source)}</dd>
              <dt>Render pts</dt>
              <dd>{renderPoints.length.toLocaleString()}</dd>
              <dt>Stations</dt>
              <dd>{(trajectory?.station_count ?? trajectory?.source_station_count ?? renderPoints.length).toLocaleString()}</dd>
            </dl>
          </div>

          <div className="wlv-wbv-control-group" aria-label="WBV view controls">
            {(Object.keys(viewPresetLabels) as WbvViewPreset[]).map((preset) => (
              <button
                type="button"
                key={preset}
                className={viewPreset === preset ? 'is-active' : ''}
                disabled={!hasTrajectory}
                onClick={() => requestViewPreset(preset)}
              >
                {viewPresetLabels[preset]}
              </button>
            ))}
          </div>
        </aside>

        <main className="wlv-wbv-scene-shell" aria-label="WBV 3D scene shell">
          <div className={`wlv-wbv-scene-frame ${hasTrajectory ? 'has-trajectory-package' : ''}`}>
            <div className="wlv-wbv-axis-label wlv-wbv-axis-label--x">X</div>
            <div className="wlv-wbv-axis-label wlv-wbv-axis-label--y">Y</div>
            <div className="wlv-wbv-axis-label wlv-wbv-axis-label--z">Z / TVD</div>
            <div className="wlv-wbv-bounding-box" aria-hidden="true">
              <div className="wlv-wbv-bounding-box__top" />
              <div className="wlv-wbv-bounding-box__front" />
              <div className="wlv-wbv-bounding-box__side" />
            </div>

            {hasTrajectory ? (
              <WellboreTrajectoryRenderer
                renderPoints={renderPoints}
                boundingBox={viewerPackage?.bounding_box}
                depthUnit={depthUnit}
                viewerState={viewerState}
                viewPreset={viewPreset}
                viewCommandId={viewCommandId}
              />
            ) : null}

            <div className={`wlv-wbv-scene-message ${hasTrajectory ? 'wlv-wbv-scene-message--package' : ''}`}>
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
                  <h2>{verticalTrajectory ? 'Vertical trajectory package loaded' : 'Trajectory package loaded'}</h2>
                  <p>
                    {renderPoints.length.toLocaleString()} backend-owned render points are rendered from the WBV trajectory package. The scene framing, labels, and bounding box are frontend display elements only.
                  </p>
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
            <dt>Depth unit</dt>
            <dd>{depthUnit}</dd>
            <dt>Angle unit</dt>
            <dd>{angleUnit}</dd>
            <dt>Loaded curves</dt>
            <dd>{loadedCurveCount}</dd>
            <dt>Trajectory pts</dt>
            <dd>{renderPoints.length.toLocaleString()}</dd>
          </dl>

          <div className="wlv-wbv-inspection-card" aria-label="Trajectory ranges">
            <h2>Trajectory Ranges</h2>
            <dl className="wlv-wbv-session-list">
              <dt>MD</dt>
              <dd>{rangeText(mdRange, depthUnit)}</dd>
              <dt>TVD</dt>
              <dd>{rangeText(tvdRange, depthUnit)}</dd>
              <dt>X</dt>
              <dd>{rangeText(xRange, depthUnit)}</dd>
              <dt>Y</dt>
              <dd>{rangeText(yRange, depthUnit)}</dd>
              <dt>Z</dt>
              <dd>{rangeText(zRange, depthUnit)}</dd>
            </dl>
          </div>

          {hasTrajectory ? (
            <div className="wlv-wbv-inspection-card" aria-label="Trajectory endpoints">
              <h2>Trajectory Endpoints</h2>
              <dl className="wlv-wbv-session-list">
                <dt>Top MD</dt>
                <dd>{formatNumber(endpoints.first?.md, 1)} {depthUnit}</dd>
                <dt>Base MD</dt>
                <dd>{formatNumber(endpoints.last?.md, 1)} {depthUnit}</dd>
                <dt>Top TVD</dt>
                <dd>{formatNumber(endpoints.first?.tvd, 1)} {depthUnit}</dd>
                <dt>Base TVD</dt>
                <dd>{formatNumber(endpoints.last?.tvd, 1)} {depthUnit}</dd>
                <dt>Inclination</dt>
                <dd>{formatNumber(endpoints.last?.inclination, 2)} {angleUnit}</dd>
                <dt>Azimuth</dt>
                <dd>{formatNumber(endpoints.last?.azimuth, 2)} {angleUnit}</dd>
              </dl>
            </div>
          ) : null}

          {hasTrajectory ? (
            <div className="wlv-wbv-inspection-card" aria-label="Sample render points">
              <h2>Sample Points</h2>
              <div className="wlv-wbv-sample-points">
                {sampledPoints.map((point, index) => (
                  <div className="wlv-wbv-sample-point" key={`${point.station_index ?? index}-${point.md ?? index}`}>
                    <strong>MD {formatNumber(point.md, 1)} {depthUnit}</strong>
                    <span>TVD {formatNumber(point.tvd, 1)} {depthUnit}</span>
                    <span>INC {formatNumber(point.inclination, 2)} {angleUnit}</span>
                    <span>AZI {formatNumber(point.azimuth, 2)} {angleUnit}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

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
