import { useEffect, useState } from 'react';
import { metadataSummaryUrlForVolumeId, metadataCompletenessUrlForVolumeId } from '../services/metadataRouteService';

interface MetadataSummaryPanelProps {
  volumeId: string;
}

function formatValue(value: any): string {
  if (value === null || value === undefined || value === '') return '—';
  if (Array.isArray(value)) return value.join(' × ');
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  return String(value);
}

function formatGeometryStatus(value: any): string {
  const raw = String(value || '').trim();

  const labels: Record<string, string> = {
    manual_trace_headers: 'Parsed trace-header geometry',
    trace_sample_fallback: 'Trace/sample indexed',
    parsed: 'Parsed geometry',
    inferred: 'Inferred geometry',
    fallback: 'Fallback geometry',
    unknown: 'Unknown',
  };

  return labels[raw] || raw || '—';
}

function formatSourceType(value: any): string {
  const raw = String(value || '').trim();

  const labels: Record<string, string> = {
    external_repository: 'External repository',
    manual_upload: 'Manual upload',
  };

  return labels[raw] || raw || '—';
}

function SummaryRow({ label, value }: { label: string; value: any }) {
  return (
    <div className="metadata-summary-row">
      <span className="metadata-summary-label">{label}</span>
      <span className="metadata-summary-value">{formatValue(value)}</span>
    </div>
  );
}

export function MetadataSummaryPanel({ volumeId }: MetadataSummaryPanelProps) {
  const [summary, setSummary] = useState<any>(null);
  const [status, setStatus] = useState<'idle' | 'loading' | 'loaded' | 'failed'>('idle');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!volumeId) {
      setStatus('failed');
      setError('No selected dataset.');
      return;
    }

    let cancelled = false;

    async function loadSummary() {
      setStatus('loading');
      setError(null);
      setSummary(null);

      try {
        const response = await fetch(metadataSummaryUrlForVolumeId(volumeId));
        if (!response.ok) {
          throw new Error(`Metadata summary request failed: ${response.status}`);
        }

        const data = await response.json();

        if (!cancelled) {
          setSummary(data);
          setStatus('loaded');
        }
      } catch (err: any) {
        console.warn('Metadata summary panel failed', err);
        if (!cancelled) {
          setStatus('failed');
          setError('Metadata summary unavailable.');
        }
      }
    }

    loadSummary();

    return () => {
      cancelled = true;
    };
  }, [volumeId]);

  if (status === 'loading') {
    return (
      <section className="info-section metadata-summary-panel">
        <h3>Metadata Summary</h3>
        <p>Loading metadata summary...</p>
      </section>
    );
  }

  if (status === 'failed') {
    return (
      <section className="info-section metadata-summary-panel">
        <h3>Metadata Summary</h3>
        <p>{error || 'Metadata summary unavailable.'}</p>
      </section>
    );
  }

  if (!summary) {
    return null;
  }

  const source = summary.source || {};
  const msi = summary._msi || {};
  const geometry = summary.geometry || {};
  const headers = summary.headers || {};
  const documents = summary.documents || {};
  const warnings = summary.warnings || [];
  const supportingDocuments = documents.supporting_documents || [];
  const sourceLabel = formatSourceType(source.source_type);
  const geometryStatus = formatGeometryStatus(geometry.geometry_status);
  const managedDisplayName = msi.managed_display_name || summary.display_name;
  const originalSourceName = msi.original_source_name || source.filename || summary.display_name;

  return (
    <section className="info-section metadata-summary-panel">
      <div className="metadata-summary-header">
        <div>
          <h3>Metadata Summary</h3>
          <p className="metadata-summary-subtitle">
            Consolidated identity, source, geometry, and evidence status.
          </p>
        </div>
        <div className="metadata-summary-badges">
          <span>{summary.dataset_type || 'unknown'}</span>
          <span>{geometryStatus}</span>
        </div>
      </div>

      <div className="metadata-summary-grid">
        <div className="metadata-summary-card">
          <h4>Identity</h4>
          <SummaryRow label="Managed Display Name" value={managedDisplayName} />
          <SummaryRow label="Original / Source Name" value={originalSourceName} />
          <SummaryRow label="Dataset Type" value={summary.dataset_type} />
          <SummaryRow label="Name Resolution" value={summary.resolution_status?.name} />
        </div>

        <div className="metadata-summary-card">
          <h4>Source</h4>
          <SummaryRow label="Source Type" value={sourceLabel} />
          <SummaryRow label="Package" value={source.package_display_name || source.package_id} />
          <SummaryRow label="Line / Volume" value={source.line_display_name || source.line_id} />
          <SummaryRow label="SEG-Y File" value={source.filename} />
        </div>

        <div className="metadata-summary-card">
          <h4>Geometry</h4>
          <SummaryRow label="Shape" value={geometry.shape} />
          <SummaryRow label="Axis Order" value={geometry.axis_order} />
          <SummaryRow label="Inline Range" value={geometry.inline_range} />
          <SummaryRow label="Crossline Range" value={geometry.crossline_range} />
          <SummaryRow label="Time Range" value={geometry.time_range_ms ? `${formatValue(geometry.time_range_ms)} ms` : null} />
          <SummaryRow label="Sample Interval" value={geometry.sample_interval_ms != null ? `${geometry.sample_interval_ms} ms` : null} />
          <SummaryRow label="Trace Count" value={geometry.trace_count} />
          <SummaryRow label="Sample Count" value={geometry.sample_count} />
        </div>

        <div className="metadata-summary-card">
          <h4>Evidence</h4>
          <SummaryRow label="Viewer Metadata" value={headers.viewer_metadata_available} />
          <SummaryRow label="Text Header" value={headers.text_header_available} />
          <SummaryRow label="Text Header Readable" value={headers.text_header_readable} />
          <SummaryRow label="Binary Header" value={headers.binary_header_available} />
          <SummaryRow label="Trace Header Summary" value={headers.trace_header_summary_available} />
          <SummaryRow label="Normalized Metadata" value={headers.normalized_metadata_available} />
          <SummaryRow label="Supporting Documents" value={supportingDocuments.length} />
        </div>
      </div>

      {warnings.length > 0 && (
        <div className="metadata-summary-warning-block">
          <h4>Warnings</h4>
          <ul className="metadata-warning-list">
            {warnings.map((warning: string, index: number) => (
              <li key={`${warning}-${index}`} style={{ fontSize: "12px", lineHeight: 1.3, margin: "2px 0" }}>{warning}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
