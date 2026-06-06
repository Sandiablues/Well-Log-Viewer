import React, { useMemo } from "react";

type Props = {
  report?: any;
  result?: any;
  row?: any;
  onDismiss?: () => void;
  onClose?: () => void;
};

function asObject(value: any): any {
  if (value && typeof value === "object" && !Array.isArray(value)) return value;
  return {};
}

function unwrapReport(value: any): any {
  const root = asObject(value);
  if (root.payload && typeof root.payload === "object") return root.payload;
  if (root.result && typeof root.result === "object") return root.result;
  if (root.report && typeof root.report === "object") return root.report;
  return root;
}

function firstDefined(...values: any[]): any {
  for (const value of values) {
    if (value !== undefined && value !== null && value !== "") return value;
  }
  return undefined;
}

function titleCase(value: any): string {
  const text = String(value ?? "").trim();
  if (!text) return "";
  return text.charAt(0).toUpperCase() + text.slice(1).replace(/_/g, " ");
}

function formatPercent(value: any): string | null {
  if (value === undefined || value === null || value === "") return null;
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  if (n <= 1) return `${Math.round(n * 100)}%`;
  return `${Math.round(n)}%`;
}

function formatNumber(value: any): string | null {
  if (value === undefined || value === null || value === "") return null;
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  return n.toLocaleString();
}

function formatRange(minValue: any, maxValue: any): string | null {
  const minText = formatNumber(minValue);
  const maxText = formatNumber(maxValue);
  if (!minText || !maxText) return null;
  return `${minText}–${maxText}`;
}

function Metric({ label, value }: { label: string; value?: any }) {
  if (value === undefined || value === null || value === "") return null;
  return (
    <div className="si-qaqc-metric">
      <div className="si-qaqc-metric-label">{label}</div>
      <div className="si-qaqc-metric-value">{value}</div>
    </div>
  );
}

function DetailsBlock({ title, value }: { title: string; value: any }) {
  if (value === undefined || value === null) return null;
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  if (!text || text === "{}" || text === "[]") return null;
  return (
    <details className="si-qaqc-details">
      <summary>{title}</summary>
      <pre>{text}</pre>
    </details>
  );
}

export function SourceIntakeGeometryQaqcLegacyReport({ report, result, row, onDismiss, onClose }: Props) {
  const payload = useMemo(() => unwrapReport(report ?? result), [report, result]);
  const selected = asObject(firstDefined(payload.selected_candidate, payload.selected_geometry, payload.recommended_geometry));
  const segy = asObject(payload.segy);
  const source = asObject(payload.source);

  const status = titleCase(firstDefined(payload.status, payload.result_status, "result"));
  const summary = firstDefined(payload.summary, payload.message, payload.detail);
  const score = formatPercent(firstDefined(selected.score, payload.score, payload.confidence_score));
  const confidence = titleCase(firstDefined(selected.confidence, payload.confidence));

  const inlineByte = firstDefined(selected.inline_byte, selected.inlineByte, payload.inline_byte);
  const crosslineByte = firstDefined(selected.crossline_byte, selected.crosslineByte, payload.crossline_byte);

  const inlineObj = asObject(selected.inline);
  const crosslineObj = asObject(selected.crossline);
  const inlineCount = formatNumber(firstDefined(inlineObj.unique, inlineObj.count, selected.inline_count, payload.inline_count));
  const crosslineCount = formatNumber(firstDefined(crosslineObj.unique, crosslineObj.count, selected.crossline_count, payload.crossline_count));
  const inlineRange = formatRange(firstDefined(inlineObj.min, selected.inline_min), firstDefined(inlineObj.max, selected.inline_max));
  const crosslineRange = formatRange(firstDefined(crosslineObj.min, selected.crossline_min), firstDefined(crosslineObj.max, selected.crossline_max));

  const traceCount = formatNumber(firstDefined(segy.trace_count, payload.trace_count, selected.trace_count));
  const sampleCount = formatNumber(firstDefined(segy.sample_count, payload.sample_count, selected.sample_count));
  const sampleRange = formatRange(firstDefined(segy.sample_min, payload.sample_min), firstDefined(segy.sample_max, payload.sample_max));
  const expectedPositions = formatNumber(firstDefined(selected.expected_positions, payload.expected_positions));

  const warnings = Array.isArray(payload.warnings) ? payload.warnings : [];
  const errors = Array.isArray(payload.errors) ? payload.errors : [];
  const candidateRankings = firstDefined(payload.candidate_rankings, payload.candidates, payload.rankings);

  const dismiss = onDismiss ?? onClose;

  return (
    <section className="si-qaqc-report si-qaqc-report-compact">
      <div className="si-qaqc-report-header">
        <div>
          <div className="si-qaqc-eyebrow">Geometry QAQC</div>
          <h3>{status ? `Geometry QAQC: ${status}` : "Geometry QAQC"}</h3>
          {summary ? <p className="si-qaqc-summary">{summary}</p> : null}
          {source.filename ? <p className="si-qaqc-file">{source.filename}</p> : null}
        </div>
        {dismiss ? (
          <button type="button" className="si-btn si-btn-secondary" onClick={dismiss}>
            Dismiss
          </button>
        ) : null}
      </div>

      <div className="si-qaqc-section">
        <div className="si-qaqc-section-title">Recommended geometry</div>
        <div className="si-qaqc-metric-grid compact">
          <Metric label="Inline byte" value={inlineByte} />
          <Metric label="Crossline byte" value={crosslineByte} />
          <Metric label="Confidence" value={confidence} />
          <Metric label="Score" value={score} />
        </div>
      </div>

      <div className="si-qaqc-section">
        <div className="si-qaqc-section-title">SEG-Y basis</div>
        <div className="si-qaqc-metric-grid compact">
          <Metric label="Trace count" value={traceCount} />
          <Metric label="Sample count" value={sampleCount} />
          <Metric label="Sample range" value={sampleRange} />
          <Metric label="Expected positions" value={expectedPositions} />
        </div>
      </div>

      {(inlineCount || crosslineCount || inlineRange || crosslineRange) ? (
        <div className="si-qaqc-section">
          <div className="si-qaqc-section-title">Candidate range</div>
          <div className="si-qaqc-metric-grid compact">
            <Metric label="Inline count" value={inlineCount} />
            <Metric label="Crossline count" value={crosslineCount} />
            <Metric label="Inline range" value={inlineRange} />
            <Metric label="Crossline range" value={crosslineRange} />
          </div>
        </div>
      ) : null}

      {warnings.length || errors.length ? (
        <div className="si-qaqc-section">
          <div className="si-qaqc-section-title">Warnings / errors</div>
          <ul className="si-qaqc-list">
            {errors.map((item: any, idx: number) => <li key={`e-${idx}`}>{String(item)}</li>)}
            {warnings.map((item: any, idx: number) => <li key={`w-${idx}`}>{String(item)}</li>)}
          </ul>
        </div>
      ) : null}

      <div className="si-qaqc-advanced">
        <DetailsBlock title="Candidate rankings" value={candidateRankings} />
        <DetailsBlock title="Raw backend JSON report" value={payload} />
      </div>
    </section>
  );
}

export default SourceIntakeGeometryQaqcLegacyReport;
