/* Auto-added slice scroll telemetry.
   Purpose: expose 3D volume slice fetch behavior during scroll stress testing.
   Toggle overlay: Ctrl+Shift+C
*/

type SliceTelemetryRecord = {
  id: number;
  url: string;
  axis: string;
  index: string;
  durationMs: number;
  status: number | string;
  ok: boolean;
  startedAt: number;
  finishedAt: number;
};

declare global {
  interface Window {
    __sliceScrollTelemetryInstalled?: boolean;
    __sliceScrollTelemetry?: {
      records: SliceTelemetryRecord[];
      inflight: number;
      totalRequests: number;
      last: SliceTelemetryRecord | null;
      visible: boolean;
      reset: () => void;
    };
  }
}

function safeUrl(input: RequestInfo | URL): string {
  try {
    if (typeof input === "string") return input;
    if (input instanceof URL) return input.toString();
    if (input instanceof Request) return input.url;
    return String(input);
  } catch {
    return "";
  }
}

function getQueryValue(urlText: string, keys: string[]): string {
  try {
    const url = new URL(urlText, window.location.origin);
    for (const key of keys) {
      const value = url.searchParams.get(key);
      if (value !== null && value !== "") return value;
    }
  } catch {
    // ignore
  }
  return "";
}

function inferAxis(urlText: string): string {
  const q = getQueryValue(urlText, ["axis", "plane", "direction", "view", "slice_axis"]);
  if (q) return q;

  const lower = urlText.toLowerCase();

  if (lower.includes("crossline") || lower.includes("xline")) return "crossline";
  if (lower.includes("inline") || lower.includes("iline")) return "inline";
  if (lower.includes("timeslice") || lower.includes("time-slice")) return "time";
  if (lower.includes("time")) return "time";

  return "unknown";
}

function inferIndex(urlText: string): string {
  const q = getQueryValue(urlText, [
    "slice",
    "slice_index",
    "index",
    "idx",
    "inline",
    "iline",
    "crossline",
    "xline",
    "time",
    "sample",
  ]);
  return q || "unknown";
}

function isLikelySliceFetch(urlText: string): boolean {
  const lower = urlText.toLowerCase();

  const sliceTerms =
    lower.includes("slice") ||
    lower.includes("inline") ||
    lower.includes("crossline") ||
    lower.includes("xline") ||
    lower.includes("iline") ||
    lower.includes("timeslice") ||
    lower.includes("time-slice");

  const dataTerms =
    lower.includes("/api/") ||
    lower.includes("/data/") ||
    lower.includes("volume") ||
    lower.includes("zarr") ||
    lower.includes("seismic");

  return sliceTerms && dataTerms;
}

function estimateMemory(): string {
  const perfAny = performance as any;
  const memory = perfAny && perfAny.memory;
  if (!memory || typeof memory.usedJSHeapSize !== "number") return "n/a";

  const used = memory.usedJSHeapSize / 1024 / 1024;
  const limit = memory.jsHeapSizeLimit / 1024 / 1024;
  return `${used.toFixed(0)} / ${limit.toFixed(0)} MB`;
}

function percentile(values: number[], p: number): number {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const i = Math.min(sorted.length - 1, Math.max(0, Math.floor((p / 100) * sorted.length)));
  return sorted[i];
}

function installOverlay(state: NonNullable<Window["__sliceScrollTelemetry"]>) {
  const existing = document.getElementById("slice-scroll-telemetry-overlay");
  if (existing) existing.remove();

  const el = document.createElement("div");
  el.id = "slice-scroll-telemetry-overlay";
  el.style.position = "fixed";
  el.style.right = "12px";
  el.style.bottom = "12px";
  el.style.zIndex = "999999";
  el.style.width = "330px";
  el.style.maxWidth = "calc(100vw - 24px)";
  el.style.fontFamily = "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace";
  el.style.fontSize = "12px";
  el.style.lineHeight = "1.35";
  el.style.background = "rgba(10, 10, 10, 0.86)";
  el.style.color = "white";
  el.style.border = "1px solid rgba(255,255,255,0.25)";
  el.style.borderRadius = "8px";
  el.style.padding = "10px";
  el.style.boxShadow = "0 8px 28px rgba(0,0,0,0.35)";
  el.style.pointerEvents = "none";
  el.style.whiteSpace = "pre-wrap";

  document.body.appendChild(el);

  const render = () => {
    if (!state.visible) {
      el.style.display = "none";
      return;
    }

    el.style.display = "block";

    const records = state.records;
    const recent = records.slice(-30);
    const durations = recent.map((r) => r.durationMs);
    const p50 = percentile(durations, 50);
    const p90 = percentile(durations, 90);
    const last = state.last;

    const axisCounts = recent.reduce<Record<string, number>>((acc, r) => {
      acc[r.axis] = (acc[r.axis] || 0) + 1;
      return acc;
    }, {});

    const axisSummary = Object.entries(axisCounts)
      .map(([k, v]) => `${k}:${v}`)
      .join(" ");

    el.textContent =
`Slice scroll telemetry
Requests: ${state.totalRequests}
Inflight: ${state.inflight}
Recent axis: ${axisSummary || "none"}
Last axis: ${last ? last.axis : "none"}
Last index: ${last ? last.index : "none"}
Last fetch: ${last ? last.durationMs.toFixed(1) + " ms" : "none"}
Recent p50: ${p50.toFixed(1)} ms
Recent p90: ${p90.toFixed(1)} ms
JS heap: ${estimateMemory()}
Status: ${last ? String(last.status) : "none"}

Ctrl+Shift+C toggles this overlay.`;
  };

  window.setInterval(render, 250);

  window.addEventListener("keydown", (event) => {
    if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === "c") {
      state.visible = !state.visible;
      render();
    }
  });

  render();
}

export function installSliceScrollTelemetry() {
  if (typeof window === "undefined") return;
  if (window.__sliceScrollTelemetryInstalled) return;

  window.__sliceScrollTelemetryInstalled = true;

  const state = {
    records: [] as SliceTelemetryRecord[],
    inflight: 0,
    totalRequests: 0,
    last: null as SliceTelemetryRecord | null,
    visible: true,
    reset: () => {
      state.records = [];
      state.inflight = 0;
      state.totalRequests = 0;
      state.last = null;
    },
  };

  window.__sliceScrollTelemetry = state;

  const originalFetch = window.fetch.bind(window);
  let seq = 0;

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const urlText = safeUrl(input);

    if (!isLikelySliceFetch(urlText)) {
      return originalFetch(input, init);
    }

    const id = ++seq;
    const startedAt = performance.now();

    state.inflight += 1;
    state.totalRequests += 1;

    try {
      const response = await originalFetch(input, init);
      const finishedAt = performance.now();

      const record: SliceTelemetryRecord = {
        id,
        url: urlText,
        axis: inferAxis(urlText),
        index: inferIndex(urlText),
        durationMs: finishedAt - startedAt,
        status: response.status,
        ok: response.ok,
        startedAt,
        finishedAt,
      };

      state.inflight = Math.max(0, state.inflight - 1);
      state.records.push(record);
      if (state.records.length > 300) state.records.shift();
      state.last = record;

      if (!response.ok || record.durationMs > 250) {
        console.debug("[slice-scroll-telemetry]", record);
      }

      return response;
    } catch (error) {
      const finishedAt = performance.now();

      const record: SliceTelemetryRecord = {
        id,
        url: urlText,
        axis: inferAxis(urlText),
        index: inferIndex(urlText),
        durationMs: finishedAt - startedAt,
        status: "error",
        ok: false,
        startedAt,
        finishedAt,
      };

      state.inflight = Math.max(0, state.inflight - 1);
      state.records.push(record);
      if (state.records.length > 300) state.records.shift();
      state.last = record;

      console.debug("[slice-scroll-telemetry:error]", record, error);
      throw error;
    }
  };

  const start = () => installOverlay(state);

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }

  console.info("[slice-scroll-telemetry] installed");
}
