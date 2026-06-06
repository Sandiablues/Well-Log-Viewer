import { useEffect, useState } from 'react';
import {
  Wrench,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  TerminalSquare,
  FileSearch,
  PlayCircle,
} from 'lucide-react';

type SegySakStatus = {
  ok?: boolean;
  tool?: string;
  installed?: boolean;
  executable?: boolean;
  path?: string;
  repo_path?: string;
  repo_exists?: boolean;
  version?: string | null;
  help_available?: boolean;
  help_excerpt?: string;
  message?: string;
  integration_mode?: string;
  license_note?: string;
  commands?: string[];
};

type SegySakScanResult = {
  ok?: boolean;
  timed_out?: boolean;
  return_code?: number | null;
  elapsed_seconds?: number;
  command?: string[];
  path?: string;
  stdout?: string;
  stderr?: string;
  detail?: string;
};

const defaultSegyPath = () => {
  try {
    return window.localStorage.getItem('multiviewer:toolbox:segysak:last-path') || '';
  } catch {
    return '';
  }
};

export function ToolboxPanel() {
  const [status, setStatus] = useState<SegySakStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');

  const [scanPath, setScanPath] = useState<string>(defaultSegyPath);
  const [maxTraces, setMaxTraces] = useState<number>(20000);
  const [scanLoading, setScanLoading] = useState(false);
  const [scanError, setScanError] = useState<string>('');
  const [scanResult, setScanResult] = useState<SegySakScanResult | null>(null);

  const loadStatus = async () => {
    setLoading(true);
    setError('');

    try {
      const response = await fetch('/api/toolbox/segysak/status');
      if (!response.ok) {
        const body = await response.text();
        throw new Error(`SEGY-SAK status failed (${response.status}): ${body || response.statusText}`);
      }

      const payload = await response.json();
      setStatus(payload);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message);
      setStatus(null);
    } finally {
      setLoading(false);
    }
  };

  const runScan = async () => {
    const cleanPath = scanPath.trim();
    if (!cleanPath) {
      setScanError('Enter a local SEG-Y path before running a scan.');
      return;
    }

    setScanLoading(true);
    setScanError('');
    setScanResult(null);

    try {
      try {
        window.localStorage.setItem('multiviewer:toolbox:segysak:last-path', cleanPath);
      } catch {
        // non-critical
      }

      const response = await fetch('/api/toolbox/segysak/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          path: cleanPath,
          max_traces: maxTraces,
          timeout_seconds: 180,
        }),
      });

      const payload = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(payload?.detail || `SEGY-SAK scan failed (${response.status})`);
      }

      setScanResult(payload);
      if (!payload?.ok) {
        setScanError(payload?.stderr || 'SEGY-SAK scan returned a non-zero exit code.');
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setScanError(message);
    } finally {
      setScanLoading(false);
    }
  };

  useEffect(() => {
    void loadStatus();
  }, []);

  const ok = Boolean(status?.ok);
  const canRunScan = ok && !scanLoading && Boolean(scanPath.trim());

  return (
    <div className="toolbox-page">
      <div className="toolbox-header">
        <div>
          <div className="toolbox-eyebrow">Toolbox</div>
          <h2>SEG-Y Tools</h2>
          <p>
            External and diagnostic utilities staged outside the main viewer runtime.
          </p>
        </div>
        <button
          type="button"
          className="toolbox-refresh-button"
          onClick={() => void loadStatus()}
          disabled={loading}
        >
          <RefreshCw size={16} />
          {loading ? 'Checking…' : 'Refresh'}
        </button>
      </div>

      <section className="toolbox-card">
        <div className="toolbox-card-title-row">
          <div className="toolbox-tool-icon">
            <Wrench size={22} />
          </div>
          <div>
            <h3>SEGY-SAK</h3>
            <p>Isolated SEG-Y diagnostic sandbox.</p>
          </div>
          <div className={`toolbox-status-pill ${ok ? 'ok' : 'warn'}`}>
            {ok ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />}
            {ok ? 'Available' : 'Unavailable'}
          </div>
        </div>

        {error && <div className="toolbox-error">{error}</div>}

        <div className="toolbox-grid">
          <div className="toolbox-field">
            <span>Executable</span>
            <strong>{status?.executable ? 'Found' : 'Not found'}</strong>
          </div>
          <div className="toolbox-field">
            <span>Version</span>
            <strong>{status?.version || '—'}</strong>
          </div>
          <div className="toolbox-field">
            <span>Integration</span>
            <strong>{status?.integration_mode || '—'}</strong>
          </div>
          <div className="toolbox-field">
            <span>Repo staged</span>
            <strong>{status?.repo_exists ? 'Yes' : 'No'}</strong>
          </div>
        </div>

        <div className="toolbox-path-block">
          <span>Path</span>
          <code>{status?.path || 'SEGY-SAK status has not loaded yet.'}</code>
        </div>

        <div className="toolbox-path-block">
          <span>Repository</span>
          <code>{status?.repo_path || '—'}</code>
        </div>

        <div className="toolbox-note">
          {status?.license_note || 'SEGY-SAK is treated as an external diagnostic tool.'}
        </div>

        <div className="toolbox-command-list">
          <div className="toolbox-command-title">
            <TerminalSquare size={16} />
            Available command families
          </div>
          <div className="toolbox-command-pills">
            {(status?.commands || ['scan', 'ebcidc', 'scrape']).map((command) => (
              <span key={command}>{command}</span>
            ))}
          </div>
        </div>

        {status?.help_excerpt && (
          <pre className="toolbox-help">{status.help_excerpt}</pre>
        )}
      </section>

      <section className="toolbox-card">
        <div className="toolbox-card-title-row">
          <div className="toolbox-tool-icon">
            <FileSearch size={22} />
          </div>
          <div>
            <h3>SEGY-SAK Scan</h3>
            <p>Read-only trace-header scan run through the isolated sandbox.</p>
          </div>
        </div>

        <div className="toolbox-path-block">
          <span>Local SEG-Y path</span>
          <input
            value={scanPath}
            onChange={(event) => setScanPath(event.target.value)}
            placeholder="/path/to/file.sgy"
            style={{
              width: '100%',
              boxSizing: 'border-box',
              border: '1px solid rgba(148, 163, 184, 0.55)',
              borderRadius: 10,
              background: 'rgba(15, 23, 42, 0.55)',
              color: '#e5e7eb',
              padding: '10px 12px',
              fontSize: 13,
            }}
          />
        </div>

        <div className="toolbox-grid">
          <div className="toolbox-field">
            <span>Max traces</span>
            <input
              type="number"
              value={maxTraces}
              min={1}
              max={500000}
              onChange={(event) => setMaxTraces(Number(event.target.value || 20000))}
              style={{
                width: '100%',
                boxSizing: 'border-box',
                border: '1px solid rgba(148, 163, 184, 0.55)',
                borderRadius: 10,
                background: 'rgba(15, 23, 42, 0.55)',
                color: '#e5e7eb',
                padding: '8px 10px',
                fontSize: 13,
              }}
            />
          </div>
          <div className="toolbox-field">
            <span>Status</span>
            <strong>
              {scanLoading ? 'Running scan…' : scanResult ? (scanResult.ok ? 'Scan complete' : 'Scan returned error') : 'Not run'}
            </strong>
          </div>
          <div className="toolbox-field">
            <span>Elapsed</span>
            <strong>{scanResult?.elapsed_seconds != null ? `${scanResult.elapsed_seconds}s` : '—'}</strong>
          </div>
          <div className="toolbox-field">
            <span>Return code</span>
            <strong>{scanResult?.return_code ?? '—'}</strong>
          </div>
        </div>

        <button
          type="button"
          className="toolbox-refresh-button"
          disabled={!canRunScan}
          onClick={() => void runScan()}
        >
          <PlayCircle size={16} />
          {scanLoading ? 'Running scan…' : 'Run SEGY-SAK Scan'}
        </button>

        {scanError && <div className="toolbox-error">{scanError}</div>}

        {scanResult?.command && (
          <div className="toolbox-path-block">
            <span>Command</span>
            <code>{scanResult.command.join(' ')}</code>
          </div>
        )}

        {scanResult?.stdout && (
          <pre className="toolbox-help">{scanResult.stdout}</pre>
        )}

        {scanResult?.stderr && (
          <pre className="toolbox-help">{scanResult.stderr}</pre>
        )}
      </section>

      <section className="toolbox-card muted">
        <h3>Integration boundary</h3>
        <p>
          This scan runner is read-only. It does not register data, mutate Source Intake,
          create Managed Data, or decide geometry. Its output is diagnostic evidence for
          the future Source Intake QAQC workflow.
        </p>
      </section>
    </div>
  );
}
