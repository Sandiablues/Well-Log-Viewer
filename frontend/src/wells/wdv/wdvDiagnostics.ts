export type WdvDiagnosticData = Record<string, unknown>;

type WdvDiagnosticEvent = {
  sequence: number;
  timestampIso: string;
  performanceTimeMs: number;
  category: string;
  name: string;
  data: WdvDiagnosticData;
};

const MAX_EVENTS = 5000;
const events: WdvDiagnosticEvent[] = [];
let sequence = 0;
let hooksInstalled = false;

function safeData(data: WdvDiagnosticData | undefined): WdvDiagnosticData {
  if (!data) return {};
  try {
    return JSON.parse(JSON.stringify(data)) as WdvDiagnosticData;
  } catch {
    return { serializationError: true, keys: Object.keys(data) };
  }
}

export function recordWdvDiagnosticEvent(category: string, name: string, data: WdvDiagnosticData = {}): void {
  const event: WdvDiagnosticEvent = {
    sequence: ++sequence,
    timestampIso: new Date().toISOString(),
    performanceTimeMs: typeof performance === 'undefined' ? 0 : performance.now(),
    category,
    name,
    data: safeData(data),
  };
  events.push(event);
  if (events.length > MAX_EVENTS) events.splice(0, events.length - MAX_EVENTS);
}

export function beginWdvDiagnosticOperation(category: string, name: string, data: WdvDiagnosticData = {}): {
  id: string;
  end: (result?: WdvDiagnosticData) => void;
} {
  const id = `${Date.now()}-${sequence + 1}`;
  const startedAt = typeof performance === 'undefined' ? 0 : performance.now();
  recordWdvDiagnosticEvent(category, `${name}:start`, { operationId: id, ...data });
  let ended = false;
  return {
    id,
    end: (result = {}) => {
      if (ended) return;
      ended = true;
      const endedAt = typeof performance === 'undefined' ? startedAt : performance.now();
      recordWdvDiagnosticEvent(category, `${name}:end`, {
        operationId: id,
        durationMs: endedAt - startedAt,
        ...result,
      });
    },
  };
}

export function clearWdvDiagnostics(): void {
  events.splice(0, events.length);
  sequence = 0;
  recordWdvDiagnosticEvent('diagnostics', 'cleared');
}

export function exportWdvDiagnostics(context: WdvDiagnosticData = {}): void {
  recordWdvDiagnosticEvent('diagnostics', 'export', context);
  const payload = {
    schema: 'wlv.wdv.curve-selection-diagnostics.v1',
    exportedAt: new Date().toISOString(),
    userAgent: typeof navigator === 'undefined' ? null : navigator.userAgent,
    location: typeof window === 'undefined' ? null : window.location.href,
    context: safeData(context),
    eventCount: events.length,
    events: [...events],
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  anchor.href = url;
  anchor.download = `WDV_CURVE_SELECTION_DIAGNOSTICS_${stamp}.json`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function installWdvDiagnosticErrorHooks(): () => void {
  if (hooksInstalled || typeof window === 'undefined') return () => undefined;
  hooksInstalled = true;
  const onError = (event: ErrorEvent) => {
    recordWdvDiagnosticEvent('window', 'error', {
      message: event.message,
      filename: event.filename,
      line: event.lineno,
      column: event.colno,
      stack: event.error instanceof Error ? event.error.stack : null,
    });
  };
  const onUnhandledRejection = (event: PromiseRejectionEvent) => {
    const reason = event.reason;
    recordWdvDiagnosticEvent('window', 'unhandled-rejection', {
      reason: reason instanceof Error ? reason.message : String(reason),
      stack: reason instanceof Error ? reason.stack : null,
    });
  };
  window.addEventListener('error', onError);
  window.addEventListener('unhandledrejection', onUnhandledRejection);
  recordWdvDiagnosticEvent('diagnostics', 'hooks-installed');
  return () => {
    window.removeEventListener('error', onError);
    window.removeEventListener('unhandledrejection', onUnhandledRejection);
    hooksInstalled = false;
  };
}
