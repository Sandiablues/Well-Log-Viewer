import { useEffect, useState } from 'react';
import { metadataScoreReportUrlForVolumeId, metadataCompletenessUrlForVolumeId } from '../services/metadataRouteService';

interface MetadataCompletenessPanelProps {
  volumeId: string;
}

function formatStatus(value: any): string {
  const raw = String(value || '').trim();

  const labels: Record<string, string> = {
    complete: 'Complete',
    mostly_complete: 'Mostly complete',
    partial: 'Partial',
    weak: 'Weak',
    indexed_provisional: 'Indexed provisional',
    available: 'Available',
    missing: 'Missing',
    not_started: 'Not started',
    headers_only: 'Headers only',
    provisional: 'Provisional',
  };

  return labels[raw] || raw || '—';
}

function formatPercent(value: any): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  if (n <= 1) return `${Math.round(n * 100)}%`;
  return `${Math.round(n)}%`;
}

function cleanFieldName(value: string): string {
  return String(value || '')
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function MetadataCompletenessPanel({ volumeId }: MetadataCompletenessPanelProps) {
  const [payload, setPayload] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!volumeId) return;

    let cancelled = false;

    async function loadCompleteness() {
      setPayload(null);
      setError(null);

      try {
        const response = await fetch(metadataCompletenessUrlForVolumeId(volumeId));
        if (!response.ok) {
          throw new Error(`Metadata completeness request failed: ${response.status}`);
        }

        const data = await response.json();

        if (!cancelled) {
          setPayload(data);
        }
      } catch (err: any) {
        console.warn('Metadata completeness panel failed', err);
        if (!cancelled) {
          setError('Metadata completeness unavailable.');
        }
      }
    }

    loadCompleteness();

    return () => {
      cancelled = true;
    };
  }, [volumeId]);

  if (error) {
    return (
      <section id="metadata-scoring-table" className="info-section metadata-completeness-panel">
        <h3>Metadata Completeness</h3>
        <p>{error}</p>
      </section>
    );
  }

  if (!payload) {
    return null;
  }

  // Converted-Zarr legacy shape:
  //   payload.metadata_quality.completeness
  // Indexed canonical shape:
  //   payload.completeness
  const quality = payload.metadata_quality || payload;
  const completeness = quality.completeness || {};
  const categories = completeness.categories || {};

  const identity = categories.identity;
  const geometry = categories.geometry;
  const evidence = categories.evidence || categories.headers;
  const documents = categories.documents;
  const optimizedCache = categories.optimized_cache;

  const evidenceStrength = quality.evidence_strength;
  const consistency = quality.consistency;
  const metadataStatus = quality.metadata_status || {
    status: payload.metadata_status,
    summary: payload.summary,
  };

  const missingFields = completeness.missing_fields || [];
  const derivedFields = completeness.derived_fields || [];

  return (
    <section id="metadata-scoring-table" className="info-section metadata-completeness-panel">
      <div className="metadata-completeness-header">
        <div>
          <h3>Metadata Completeness</h3>
          <p className="metadata-completeness-subtitle">
            Viewer-required metadata coverage based on geometry, headers, conversion state, and evidence.
          </p>
        </div>

        <div className="metadata-completeness-score-block">
          <div className="metadata-completeness-score-line">
            <strong>{completeness.percent ?? '—'}%</strong>
            <a
              className="metadata-score-learn-more-link"
              href={metadataScoreReportUrlForVolumeId(volumeId)}
              target="_blank"
              rel="noopener noreferrer"
              title="Open detailed metadata scoring report"
            >
              Learn more
            </a>
          </div>
          <span>{formatStatus(completeness.status || payload.metadata_status)}</span>
        </div>
      </div>

      <div className="metadata-completeness-category-grid">
        {identity && (
          <div>
            <strong>Identity</strong>
            <span>{formatPercent(identity.score)} — {formatStatus(identity.status)}</span>
          </div>
        )}

        {geometry && (
          <div>
            <strong>Geometry</strong>
            <span>{formatPercent(geometry.score)} — {formatStatus(geometry.status)}</span>
          </div>
        )}

        {evidence && (
          <div>
            <strong>Headers / Evidence</strong>
            <span>{formatPercent(evidence.score)} — {formatStatus(evidence.status)}</span>
          </div>
        )}

        {documents && (
          <div>
            <strong>Documents</strong>
            <span>{formatPercent(documents.score)} — {formatStatus(documents.status)}</span>
          </div>
        )}

        {optimizedCache && (
          <div>
            <strong>Optimized Cache</strong>
            <span>{formatPercent(optimizedCache.score)} — {formatStatus(optimizedCache.status)}</span>
          </div>
        )}

        {evidenceStrength && (
          <div>
            <strong>Evidence Strength</strong>
            <span>{formatStatus(evidenceStrength.status)}</span>
          </div>
        )}

        {consistency && (
          <div>
            <strong>Consistency</strong>
            <span>
              {formatStatus(consistency.status)} — {consistency.checks_passed ?? 0} passed, {consistency.checks_failed ?? 0} failed
            </span>
          </div>
        )}

        {metadataStatus && (
          <div>
            <strong>Metadata Status</strong>
            <span>{formatStatus(metadataStatus.status || payload.metadata_status)}</span>
          </div>
        )}
      </div>

      {metadataStatus?.summary && (
        <p className="metadata-completeness-status-summary">{metadataStatus.summary}</p>
      )}

      {missingFields.length > 0 && (
        <div className="metadata-completeness-detail">
          <strong>Missing</strong>
          <ul>
            {missingFields.map((field: string) => (
              <li key={field} style={{ fontSize: '12px', lineHeight: 1.3, margin: '2px 0' }}>
                {cleanFieldName(field)}
              </li>
            ))}
          </ul>
        </div>
      )}

      {derivedFields.length > 0 && (
        <div className="metadata-completeness-detail">
          <strong>Derived</strong>
          <ul>
            {derivedFields.map((field: string) => (
              <li key={field} style={{ fontSize: '12px', lineHeight: 1.3, margin: '2px 0' }}>
                {cleanFieldName(field)}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
