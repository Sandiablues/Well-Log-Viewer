import React, { useEffect, useState } from 'react';
import type { Volume } from '../services/zarrService';
import { getVolumeInfoForVolume, fetchNormalizedMetadataForVolume } from '../services/zarrService';
import { MetadataSummaryPanel } from './MetadataSummaryPanel';
import { MetadataCompletenessPanel } from './MetadataCompletenessPanel';
import { MetadataScoreHeaderLink } from './MetadataScoreHeaderLink';


function getSupportingDocumentsForInfo(volume: any, infoData?: any): any[] {
  const volumeMetadata = volume?.metadata || {};
  const infoMetadata = infoData?.metadata || {};
  const docs =
    infoData?.supporting_documents ||
    infoData?.document_context?.supporting_documents ||
    infoMetadata?.supporting_documents ||
    infoMetadata?.document_context?.supporting_documents ||
    volume?.supporting_documents ||
    volume?.document_context?.supporting_documents ||
    volumeMetadata?.supporting_documents ||
    volumeMetadata?.document_context?.supporting_documents ||
    [];
  return Array.isArray(docs) ? docs : [];
}

function openSupportingDocument(doc: any) {
  const url = doc?.open_url || doc?.view_url || doc?.download_url;
  if (!url) return;
  window.open(url, "_blank", "noopener,noreferrer");
}

function SupportingDocumentsInfoSection({ volume, infoData }: { volume: any; infoData?: any }) {
  const docs = getSupportingDocumentsForInfo(volume, infoData);
  return (
    <section className="info-section source-intake-supporting-documents">
      <h3>Supporting Documents</h3>
      {docs.length === 0 ? (
        <p className="muted">No assigned supporting documents.</p>
      ) : (
        <div className="supporting-documents-info-list">
          {docs.map((doc: any, index: number) => (
            <div className="supporting-documents-info-row" key={doc?.document_id || doc?.filename || index}>
              <button
                type="button"
                className="link-button supporting-document-info-link"
                onClick={() => openSupportingDocument(doc)}
                disabled={!(doc?.open_url || doc?.view_url || doc?.download_url)}
              >
                {doc?.filename || doc?.relative_path || doc?.document_id || "Supporting document"}
              </button>
              <div className="supporting-document-info-meta">
                {[doc?.document_type, doc?.suggested_scope, doc?.match_confidence]
                  .filter(Boolean)
                  .join(" · ") || "Assigned document"}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}


interface VolumeInfoPanelProps {
  volume: Volume | null;
}

function getDisplayName(volume: Volume): string {
  return volume.display_name || volume.filename || volume.id;
}

function formatValue(value: any): string {
  if (value === null || value === undefined || value === '') return '—';
  if (Array.isArray(value)) return value.join(' × ');
  if (typeof value === 'number') {
    return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(4)));
  }
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function firstNonEmptyValue(...values: any[]): string | null {
  for (const value of values) {
    if (value === null || value === undefined) continue;
    const text = String(value).trim();
    if (text) return text;
  }
  return null;
}

function formatRange(value: any, unit?: string): string {
  if (!Array.isArray(value) || value.length < 2) return formatValue(value);
  const left = formatValue(value[0]);
  const right = formatValue(value[1]);
  const suffix = unit ? ` ${unit}` : '';
  return `${left} – ${right}${suffix}`;
}

function getShape(volume: Volume): any {
  return volume.metadata?.shape || volume.metadata?.zarr?.shape;
}

function getDatasetTypeLabel(volume: Volume): string {
  switch (volume.dataset_type) {
    case '3d_volume':
      return '3D Volume';
    case '2d_line':
      return '2D Line';
    case '2d_survey':
      return '2D Survey';
    default:
      return volume.metadata?.is_3d === false ? '2D Line' : 'Unknown';
  }
}

function getReadyStatus(volume: Volume): string {
  switch (volume.dataset_type) {
    case '3d_volume':
      return 'Ready 3D';
    case '2d_line':
      return 'Ready 2D';
    case '2d_survey':
      return 'Ready Survey';
    default:
      return volume.metadata?.is_3d === false ? 'Ready 2D' : 'Ready 3D';
  }
}

function getGeometrySource(volume: Volume): string {
  return volume.metadata?.geometry_source || volume.metadata?.zarr?.geometry_source || 'Unknown';
}

function InfoGrid({ children }: { children: React.ReactNode }) {
  return <div className="info-grid">{children}</div>;
}

function InfoRow({ label, value }: { label: string; value: any }) {
  return (
    <div>
      <strong>{label}</strong>
      <span>{formatValue(value)}</span>
    </div>
  );
}

function InfoDisplayRow({ label, value }: { label: string; value: any }) {
  return (
    <div>
      <strong>{label}</strong>
      <span>{value === null || value === undefined || value === '' ? '—' : String(value)}</span>
    </div>
  );
}

function TextHeaderDecodeBadge({ decode }: { decode: any }) {
  if (!decode) return null;

  const selectedEncoding = decode.selected_encoding || decode.encoding;
  const confidence = decode.confidence;
  const warnings = Array.isArray(decode.warnings) ? decode.warnings : [];

  if (!selectedEncoding && !confidence && !warnings.length) return null;

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      gap: 4,
      margin: '8px 0 10px 0',
      fontSize: 12,
      color: '#cbd5e1',
    }}>
      <div>
        <strong>Textual header decode</strong>
        <span style={{ marginLeft: 8 }}>
          {selectedEncoding ? `Encoding: ${selectedEncoding}` : 'Encoding: —'}
          {confidence ? ` · confidence: ${confidence}` : ''}
        </span>
      </div>
      {warnings.length ? (
        <div style={{ color: '#fbbf24' }}>
          {warnings.join(' · ')}
        </div>
      ) : null}
    </div>
  );
}


function formatAxisRange(axis: any): string {
  const min = axis?.min;
  const max = axis?.max;
  const unit = axis?.unit;

  if (min === null || min === undefined || max === null || max === undefined) {
    return 'Unavailable';
  }

  const range = `${min} – ${max}`;

  if (!unit || unit === 'number' || unit === 'index') {
    return range;
  }

  return `${range} ${unit}`;
}

function getFieldValue(field: any): any {
  if (!field || typeof field !== 'object' || !('value' in field)) return field;
  return field.value;
}

function getFieldMeta(field: any): string {
  if (!field || typeof field !== 'object' || !('value' in field)) return '';

  const parts = [];

  if (field.source && field.source !== 'unknown') parts.push(field.source);
  if (field.confidence !== null && field.confidence !== undefined && field.confidence > 0) {
    parts.push(`conf. ${field.confidence}`);
  }
  if (field.status && field.status !== 'missing') parts.push(field.status);

  return parts.length ? parts.join(' · ') : '';
}

function NormalizedInfoRow({ label, field, unit }: { label: string; field: any; unit?: string }) {
  const value = getFieldValue(field);
  const meta = getFieldMeta(field);
  const displayValue = formatValue(value);

  return (
    <div>
      <strong>{label}</strong>
      <span>
        {displayValue}{displayValue !== '—' && unit ? ` ${unit}` : ''}
        {meta ? <small className="field-provenance"> · {meta}</small> : null}
      </span>
    </div>
  );
}

function MainInfoSupportingDocumentsSection({ volume, infoData }: { volume: any; infoData?: any }) {
  const supportingDocs = getSupportingDocumentsForInfo(volume, infoData);

  return (
    <section className="main-info-supporting-documents-section">
      <h3>Supporting Documents</h3>
      <InfoGrid>
        <InfoRow label="Supporting Documents" value={supportingDocs.length} />
      </InfoGrid>

      {supportingDocs.length > 0 ? (
        <ul className="main-info-supporting-document-list">
          {supportingDocs.map((doc: any, index: number) => {
            const filename =
              doc?.filename ||
              doc?.relative_path ||
              doc?.display_name ||
              doc?.document_id ||
              `Supporting document ${index + 1}`;
            const url = doc?.open_url || doc?.view_url || doc?.download_url || "";
            const meta = [
              doc?.document_type,
              doc?.suggested_scope,
              doc?.match_confidence,
            ].filter(Boolean).join(" · ");

            return (
              <li className="main-info-supporting-document-item" key={`${doc?.document_id || filename}-${index}`}>
                {url ? (
                  <a href={url} target="_blank" rel="noreferrer">
                    {filename}
                  </a>
                ) : (
                  <span>{filename}</span>
                )}
                {meta ? <small className="field-provenance"> · {meta}</small> : null}
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="muted">No assigned supporting documents.</p>
      )}
    </section>
  );
}

function NormalizedMetadataSection({
  normalized,
  loading,
  error,
  volume,
  infoData,
}: {
  normalized: any;
  loading?: boolean;
  error?: string;
  volume?: any;
  infoData?: any;
}) {
  if (loading) {
    return (
      <section>
        <h3>Normalized Metadata Overview</h3>
        <p>Loading normalized metadata...</p>
      </section>
    );
  }

  if (error) {
    return (
      <section>
        <h3>Normalized Metadata Overview</h3>
        <p>{error}</p>
      </section>
    );
  }

  if (!normalized) {
    return (
      <section>
        <h3>Normalized Metadata Overview</h3>
        <p>No normalized metadata available. Use Data Manager → Enrich metadata first.</p>
      </section>
    );
  }

  const identity = normalized.identity || {};
  const managedDisplayName = volume?.display_name || volume?.filename || volume?.id;
  const originalSourceName = getFieldValue(identity.source_file_name) || getFieldValue(identity.display_name);
  const selectedDatasetType = String(volume?.dataset_type || '').trim().toLowerCase();
  const selectedIs2DLine =
    selectedDatasetType === '2d_line' || volume?.metadata?.is_3d === false;
  const selectedIs3DVolume =
    selectedDatasetType === '3d_volume' || volume?.metadata?.is_3d === true;
  const geometry = normalized.geometry || {};
  const coordinateCrs = normalized.coordinate_crs || {};
  const conversion = normalized.conversion || {};
  const quality = normalized.quality || {};
  const warnings = quality.warnings || [];

  return (
    <section>
      <h3>Normalized Metadata Overview</h3>

      <h4>Identity</h4>
      <InfoGrid>
        <InfoRow label="Schema Version" value={normalized.schema_version} />
        <InfoRow label="Managed Display Name" value={managedDisplayName} />
        <InfoRow label="Original / Source Name" value={originalSourceName} />
        <NormalizedInfoRow label="Dataset Type" field={identity.dataset_type} />
        <NormalizedInfoRow label="Source File" field={identity.source_file_name} />
        <NormalizedInfoRow label="Survey Name" field={identity.survey_name} />

        {selectedIs2DLine ? (
          <NormalizedInfoRow
            label="Line Name"
            field={identity.line_name?.value ? identity.line_name : identity.display_name}
          />
        ) : null}

        {selectedIs3DVolume ? (
          <NormalizedInfoRow
            label="Volume Name"
            field={identity.volume_name?.value ? identity.volume_name : identity.display_name}
          />
        ) : null}
      </InfoGrid>

      <h4>Geometry</h4>
      <InfoGrid>
        <NormalizedInfoRow label="Zarr Shape" field={geometry.zarr_shape} />
        <NormalizedInfoRow label="Trace Count" field={geometry.trace_count} />
        <NormalizedInfoRow label="Inline Count" field={geometry.inline_count} />
        <NormalizedInfoRow label="Crossline Count" field={geometry.crossline_count} />
        <NormalizedInfoRow label="Sample Count" field={geometry.sample_count} />
        <NormalizedInfoRow label="Sample Interval" field={geometry.sample_interval_ms} unit="ms" />
        <NormalizedInfoRow label="Record Length" field={geometry.record_length_ms} unit="ms" />
        <NormalizedInfoRow label="Vertical Domain" field={geometry.vertical_domain} />
      </InfoGrid>

      <h4>Coordinate / CRS</h4>
      <InfoGrid>
        <NormalizedInfoRow label="X Min" field={geometry.x_min} />
        <NormalizedInfoRow label="X Max" field={geometry.x_max} />
        <NormalizedInfoRow label="Y Min" field={geometry.y_min} />
        <NormalizedInfoRow label="Y Max" field={geometry.y_max} />
        <NormalizedInfoRow label="CRS Name" field={coordinateCrs.crs_name} />
        <NormalizedInfoRow label="EPSG Code" field={coordinateCrs.epsg_code} />
        <NormalizedInfoRow label="CRS Confidence" field={coordinateCrs.crs_confidence} />
      </InfoGrid>

      <h4>Conversion</h4>
      <InfoGrid>
        <NormalizedInfoRow label="Source Format" field={conversion.source_format} />
        <NormalizedInfoRow label="Target Format" field={conversion.target_format} />
        <NormalizedInfoRow label="Zarr Chunks" field={conversion.zarr_chunks} />
        <NormalizedInfoRow label="Geometry Source" field={conversion.geometry_source} />
      </InfoGrid>

      <h4>Quality</h4>
      <InfoGrid>
      </InfoGrid>

      {warnings.length ? (
        <>
          <h4>Warnings</h4>
          <ul>
            {warnings.map((warning: string, index: number) => (
              <li key={`${warning}-${index}`} style={{ fontSize: "12px", lineHeight: 1.3, margin: "2px 0" }}>{warning}</li>
            ))}
          </ul>
        </>
      ) : (
        <p>No normalized metadata warnings.</p>
      )}
    </section>
  );
}

function looksLikeBadTextHeader(value: any): boolean {
  if (!value || typeof value !== 'string') return true;

  const sample = value.slice(0, 600);
  const replacementCount = (sample.match(/\uFFFD/g) || []).length;
  const atCount = (sample.match(/@/g) || []).length;
  const letterCount = (sample.match(/[A-Za-z]/g) || []).length;

  if (replacementCount > 5) return true;
  if (atCount > 80 && letterCount < 40) return true;

  return false;
}

function getReadableTextHeader(infoData: any, metadata: any): string | null {
  const primary = infoData?.text_header;

  if (!looksLikeBadTextHeader(primary)) {
    return primary;
  }

  return (
    metadata?.decoded_text_header ||
    metadata?.normalized?.segy_info?.text_header ||
    metadata?.textual_header ||
    metadata?.ebcdic_header ||
    null
  );
}

function SurveyInfo({ volume, normalizedMetadata, normalizedLoading, normalizedError, metadataAuthorityId }: { volume: Volume; normalizedMetadata: any; normalizedLoading?: boolean; normalizedError?: string; metadataAuthorityId: string }) {
  const metadata = volume.metadata || {};
  const lines = volume.lines || metadata.lines || [];

  return (
    <>
      <section>
        <h3>Survey Summary</h3>
        <InfoGrid>
          <InfoRow label="Dataset Type" value={getDatasetTypeLabel(volume)} />
          <InfoRow label="Ready Status" value={getReadyStatus(volume)} />
          <InfoRow label="Survey ID" value={volume.id} />
          <InfoRow label="Survey Name" value={metadata.survey_name || getDisplayName(volume)} />
          <InfoRow label="Line Count" value={metadata.line_count || lines.length} />
          <InfoRow label="Source" value={metadata.source} />
          <InfoRow label="Source Folder" value={metadata.source_folder} />
        </InfoGrid>
      </section>

      <section>
        <h3>Survey Lines</h3>
        {lines.length ? (
          <div style={{ overflowX: 'auto' }}>
            <table className="info-table">
              <thead>
                <tr>
                  <th>Line</th>
                  <th>File</th>
                  <th>Shape</th>
                  <th>Traces</th>
                  <th>Samples</th>
                  <th>Sample Rate</th>
                  <th>Axis Order</th>
                </tr>
              </thead>
              <tbody>
                {lines.map((line: any) => (
                  <tr key={line.line_id || line.zarr_url}>
                    <td>{line.line_name || line.line_id}</td>
                    <td>{line.filename || '—'}</td>
                    <td>{formatValue(line.shape)}</td>
                    <td>{formatValue(line.trace_count || line.shape?.[0])}</td>
                    <td>{formatValue(line.sample_count || line.shape?.[1])}</td>
                    <td>{formatValue(line.sample_rate)}</td>
                    <td>{formatValue(line.axis_order)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p>No survey lines registered.</p>
        )}
      </section>

      <NormalizedMetadataSection normalized={normalizedMetadata} loading={normalizedLoading} error={normalizedError} volume={volume} />
      <MetadataCompletenessPanel volumeId={metadataAuthorityId} />
</>
  );
}

function LineInfo({ volume, infoData, normalizedMetadata, normalizedLoading, normalizedError, metadataAuthorityId }: { volume: Volume; infoData: any; normalizedMetadata: any; normalizedLoading?: boolean; normalizedError?: string; metadataAuthorityId: string }) {
  const metadata = volume.metadata || {};
  const infoVolumeMetadata = infoData?.volume?.metadata || {};
  const textHeaderMetadata = Object.keys(infoVolumeMetadata).length ? infoVolumeMetadata : metadata;
  const zarrMetadata = metadata.zarr || {};
  const shape = getShape(volume);

  const displaySampleInterval =
    metadata.sample_interval_ms ||
    metadata.sample_rate ||
    zarrMetadata.sample_interval_ms ||
    zarrMetadata.sample_rate ||
    infoVolumeMetadata.sample_interval_ms ||
    infoVolumeMetadata.sample_rate;

  const displayDataType =
    zarrMetadata.dtype ||
    metadata.dtype ||
    infoVolumeMetadata.dtype ||
    infoData?.dtype ||
    null;

  const normalizedIdentity = normalizedMetadata?.identity || {};
  const displaySurveyName = firstNonEmptyValue(
    (volume as any)?.survey_name,
    metadata.survey_name,
    infoVolumeMetadata.survey_name,
    getFieldValue(normalizedIdentity.survey_name),
  );
  const displayLineName = firstNonEmptyValue(
    (volume as any)?.line_name,
    metadata.line_name,
    infoVolumeMetadata.line_name,
    getFieldValue(normalizedIdentity.line_name),
    getDisplayName(volume),
  );

  return (
    <>
      <section>
        <h3>2D Line Summary</h3>
        <InfoGrid>
          <InfoRow label="Dataset Type" value={getDatasetTypeLabel(volume)} />
          <InfoRow label="Ready Status" value={getReadyStatus(volume)} />
          <InfoRow label="Line ID" value={volume.id} />
          <InfoRow label="Line Name" value={displayLineName} />
          <InfoRow label="Survey Name" value={displaySurveyName} />
          <InfoRow label="Source SEG-Y" value={volume.filename} />
          <InfoRow label="Source Relative Path" value={metadata.source_relative_path} />
          <InfoRow label="Shape" value={shape} />
          <InfoRow label="Trace Count" value={metadata.trace_count || zarrMetadata.trace_count || shape?.[0]} />
          <InfoRow label="Sample Count" value={shape?.[1]} />
          <InfoDisplayRow label="Sample Interval" value={displaySampleInterval ? `${displaySampleInterval} ms` : null} />
          <InfoRow label="Axis Order" value={zarrMetadata.axis_order || metadata.axis_order || ['trace', 'sample']} />
          <InfoRow label="Zarr URL" value={volume.zarr_url} />
        </InfoGrid>
      </section>

      <section>
        <h3>Zarr / Display Metadata</h3>
        <InfoGrid>
          <InfoRow label="Chunks" value={zarrMetadata.chunks} />
          <InfoRow label="Data Type" value={displayDataType} />
          <InfoRow label="Geometry Source" value={getGeometrySource(volume)} />
          <InfoRow label="Survey Import Source" value={metadata.survey_import_source} />
        </InfoGrid>
      </section>

      <section>
        <h3>SEG-Y Textual Header</h3>
        <TextHeaderDecodeBadge decode={infoData?.text_header_decode || infoData?.indexed_segy?.text_header_decode} />
        <pre className="text-header">{getReadableTextHeader(infoData, textHeaderMetadata) || 'Textual header not available for this line.'}</pre>
      </section>

      <section>
        <h3>SEG-Y Binary Header</h3>
        <pre className="json-block">{infoData?.binary_header ? JSON.stringify(infoData.binary_header, null, 2) : 'Binary header not available for this line.'}</pre>
      </section>

      <section>
        <h3>Trace Header Summary</h3>
        <pre className="json-block">{infoData?.trace_header_summary ? JSON.stringify(infoData.trace_header_summary, null, 2) : 'Trace header summary not available for this line.'}</pre>
      </section>

      <NormalizedMetadataSection normalized={normalizedMetadata} loading={normalizedLoading} error={normalizedError} volume={volume} infoData={infoData} />
      <MetadataCompletenessPanel volumeId={metadataAuthorityId} />
</>
  );
}

function Volume3DInfo({ volume, infoData, normalizedMetadata, normalizedLoading, normalizedError, metadataAuthorityId }: { volume: Volume; infoData: any; normalizedMetadata: any; normalizedLoading?: boolean; normalizedError?: string; metadataAuthorityId: string }) {
  const metadata = infoData?.metadata || infoData?.volume?.metadata || volume.metadata || {};
  const zarrMetadata = metadata.zarr || {};
  const normalizedGeometry = normalizedMetadata?.geometry || {};
  const normalizedConversion = normalizedMetadata?.conversion || {};
  const conversionInfo = infoData?.conversion_info || metadata.conversion_info || normalizedConversion || {};
  const viewerMetadata = infoData?.viewer_metadata;
  const isIndexedSegy =
    String(volume.zarr_url || '').startsWith('indexed-segy://') ||
    String((volume as any).read_mode || '').toLowerCase() === 'indexed_segy' ||
    String(volume.metadata?.read_mode || '').toLowerCase() === 'indexed_segy';

  const displayDataType =
    zarrMetadata.dtype ||
    metadata.dtype ||
    normalizedConversion.dtype ||
    (isIndexedSegy ? 'float32 preview' : null);

  const displayGeometrySource =
    metadata.geometry_source ||
    zarrMetadata.geometry_source ||
    normalizedGeometry.geometry_source ||
    normalizedConversion.geometry_source ||
    getGeometrySource(volume);

  const displayInlineRange =
    metadata.inline_range ||
    normalizedGeometry.inline_range ||
    (metadata.inline_min !== undefined && metadata.inline_max !== undefined ? [metadata.inline_min, metadata.inline_max] : null) ||
    (metadata.inlines ? [metadata.inlines[0], metadata.inlines[metadata.inlines.length - 1]] : null);

  const displayCrosslineRange =
    metadata.crossline_range ||
    normalizedGeometry.crossline_range ||
    (metadata.crossline_min !== undefined && metadata.crossline_max !== undefined ? [metadata.crossline_min, metadata.crossline_max] : null) ||
    (metadata.crosslines ? [metadata.crosslines[0], metadata.crosslines[metadata.crosslines.length - 1]] : null);

  const displaySampleIndexRange =
    normalizedGeometry.sample_index_range ||
    (metadata.sample_count !== undefined
      ? [0, Number(metadata.sample_count) - 1]
      : metadata.sample_range_ms || (metadata.sample_min !== undefined && metadata.sample_max !== undefined ? [metadata.sample_min, metadata.sample_max - 1] : (metadata.samples ? [metadata.samples[0], metadata.samples[metadata.samples.length - 1]] : null)));

  const displayTimeRange =
    normalizedGeometry.time_range_ms ||
    ((metadata.sample_count !== undefined && (metadata.sample_interval_ms || metadata.sample_rate))
      ? `0 – ${(Number(metadata.sample_count) - 1) * Number(metadata.sample_interval_ms || metadata.sample_rate)} ms`
      : null);

  const displaySampleInterval =
    metadata.sample_interval_ms ||
    metadata.sample_rate ||
    normalizedGeometry.sample_interval_ms;

  const displayAxisOrder =
    zarrMetadata.axis_order ||
    metadata.axis_order ||
    normalizedGeometry.axis_order;

  const normalizedIdentity = normalizedMetadata?.identity || {};
  const displaySurveyName = firstNonEmptyValue(
    (volume as any)?.survey_name,
    metadata.survey_name,
    getFieldValue(normalizedIdentity.survey_name),
  );
  const displayVolumeName = firstNonEmptyValue(
    (volume as any)?.volume_name,
    metadata.volume_name,
    getFieldValue(normalizedIdentity.volume_name),
    getDisplayName(volume),
  );

  return (
    <>
      <section>
        <h3>Volume Summary</h3>
        <InfoGrid>
          <InfoRow label="Dataset Type" value={getDatasetTypeLabel(volume)} />
          <InfoRow label="Ready Status" value={getReadyStatus(volume)} />
          <InfoRow label="Volume ID" value={volume.id} />
          <InfoRow label="Volume Name" value={displayVolumeName} />
          <InfoRow label="Survey Name" value={displaySurveyName} />
          <InfoRow label="Shape" value={getShape(volume)} />
          <InfoRow label="Zarr URL" value={volume.zarr_url} />
          <InfoRow label="Data Type" value={zarrMetadata.dtype} />
          <InfoRow label="Chunks" value={zarrMetadata.chunks} />
        </InfoGrid>
      </section>

      <section>
        <h3>Geometry</h3>
        <InfoGrid>
          <InfoRow label="Geometry Source" value={displayGeometrySource} />
          <InfoDisplayRow label="Inline Range" value={formatRange(displayInlineRange)} />
          <InfoDisplayRow label="Crossline Range" value={formatRange(displayCrosslineRange)} />
          <InfoDisplayRow label="Sample Index Range" value={formatRange(displaySampleIndexRange)} />
          <InfoDisplayRow label="Time Range" value={formatRange(displayTimeRange, "ms")} />
          <InfoRow label="Sample Rate" value={(metadata.sample_rate || metadata.sample_interval_ms) ? `${metadata.sample_rate || metadata.sample_interval_ms} ms` : null} />
          <InfoRow label="Axis Order" value={displayAxisOrder} />
        </InfoGrid>
      </section>

      <section>
        <h3>Conversion / Completeness</h3>
        <InfoGrid>
          <InfoRow label="Input Trace Count" value={metadata.trace_count || zarrMetadata.trace_count} />
          <InfoRow label="Written Traces" value={zarrMetadata.written_traces} />
          <InfoRow label="Skipped Traces" value={zarrMetadata.skipped_traces} />
          <InfoRow label="Expected Trace Positions" value={zarrMetadata.expected_trace_positions} />
          <InfoRow label="Missing Trace Positions" value={zarrMetadata.missing_trace_positions} />
          <InfoRow label="Missing Trace Fill" value={zarrMetadata.missing_trace_fill} />
          <InfoRow label="Batch Size" value={zarrMetadata.batch_size_inlines ? `${zarrMetadata.batch_size_inlines} inlines` : null} />
          <InfoRow label="Batch Writes" value={zarrMetadata.batch_writes} />
        </InfoGrid>
      </section>

      {viewerMetadata && (
        <section>
          <h3>Viewer Metadata</h3>
          <pre className="json-block">{JSON.stringify(viewerMetadata, null, 2)}</pre>
        </section>
      )}

      <section>
        <h3>SEG-Y Textual Header</h3>
        <TextHeaderDecodeBadge decode={infoData?.text_header_decode || infoData?.indexed_segy?.text_header_decode} />
        <pre className="text-header">{getReadableTextHeader(infoData, metadata) || 'Textual header not available for this volume.'}</pre>
      </section>

      <section>
        <h3>SEG-Y Binary Header</h3>
        <pre className="json-block">{infoData?.binary_header ? JSON.stringify(infoData.binary_header, null, 2) : 'Binary header not available for this volume.'}</pre>
      </section>

      <section>
        <h3>Trace Header Summary</h3>
        <pre className="json-block">{infoData?.trace_header_summary ? JSON.stringify(infoData.trace_header_summary, null, 2) : 'Trace header summary not available for this volume.'}</pre>
      </section>

      <NormalizedMetadataSection normalized={normalizedMetadata} loading={normalizedLoading} error={normalizedError} volume={volume} infoData={infoData} />
      <MetadataCompletenessPanel volumeId={metadataAuthorityId} />
</>
  );
}



function formatSummaryValue(value: any): string {
  if (value === null || value === undefined || value === '') return '—';
  if (Array.isArray(value)) return value.join(' × ');
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function MetadataSummarySection({ summary }: { summary: any }) {
  if (!summary) {
    return (
      <section className="info-section">
        <h3>Metadata Summary</h3>
        <p>Metadata summary not available.</p>
      </section>
    );
  }

  const source = summary.source || {};
  const geometry = summary.geometry || {};
  const headers = summary.headers || {};
  const documents = summary.documents || {};
  const warnings = summary.warnings || [];
  const supportingDocs = documents.supporting_documents || [];

  return (
    <section className="info-section">
      <h3>Metadata Summary</h3>

      <h4>Dataset Identity</h4>
      <InfoGrid>
        <InfoRow label="Display Name" value={summary.display_name} />
        <InfoRow label="Dataset Type" value={summary.dataset_type} />
        <InfoRow label="Resolution: Name" value={summary.resolution_status?.name} />
        <InfoRow label="Resolution: Geometry" value={summary.resolution_status?.geometry} />
      </InfoGrid>

      <h4>Source Provenance</h4>
      <InfoGrid>
        <InfoRow label="Source Type" value={source.source_type} />
        <InfoRow label="Repository ID" value={source.repository_id} />
        <InfoRow label="Package" value={source.package_display_name || source.package_id} />
        <InfoRow label="Line" value={source.line_display_name || source.line_id} />
        <InfoRow label="SEG-Y File" value={source.filename} />
        <InfoRow label="Relative Path" value={source.relative_path} />
      </InfoGrid>

      <h4>Geometry</h4>
      <InfoGrid>
        <InfoRow label="Shape" value={geometry.shape} />
        <InfoRow label="Axis Order" value={geometry.axis_order} />
        <InfoRow label="Sample Interval" value={geometry.sample_interval_ms != null ? `${geometry.sample_interval_ms} ms` : null} />
        <InfoRow label="Trace Count" value={geometry.trace_count} />
        <InfoRow label="Sample Count" value={geometry.sample_count} />
        <InfoRow label="Inline Range" value={geometry.inline_range} />
        <InfoRow label="Crossline Range" value={geometry.crossline_range} />
        <InfoRow label="Time Range" value={geometry.time_range_ms ? `${formatSummaryValue(geometry.time_range_ms)} ms` : null} />
        <InfoRow label="Geometry Status" value={geometry.geometry_status} />
      </InfoGrid>

      <h4>Evidence Availability</h4>
      <InfoGrid>
        <InfoRow label="Viewer Metadata" value={headers.viewer_metadata_available} />
        <InfoRow label="Text Header" value={headers.text_header_available} />
        <InfoRow label="Text Header Readable" value={headers.text_header_readable} />
        <InfoRow label="Binary Header" value={headers.binary_header_available} />
        <InfoRow label="Trace Header Summary" value={headers.trace_header_summary_available} />
        <InfoRow label="Normalized Metadata" value={headers.normalized_metadata_available} />
        <InfoRow label="Supporting Documents" value={supportingDocs.length} />
      </InfoGrid>

      {warnings.length > 0 && (
        <>
          <h4>Warnings</h4>
          <ul className="metadata-warning-list">
            {warnings.map((warning: string, index: number) => (
              <li key={`${warning}-${index}`} style={{ fontSize: "12px", lineHeight: 1.3, margin: "2px 0" }}>{warning}</li>
            ))}
          </ul>
        </>
      )}

      {supportingDocs.length > 0 && (
        <>
          <h4>Supporting Documents</h4>
          <ul className="metadata-document-list">
            {supportingDocs.map((doc: any) => (
              <li key={doc.document_id || doc.relative_path || doc.filename}>
                <strong>{doc.filename || 'Unnamed document'}</strong>
                {doc.document_type ? ` — ${doc.document_type}` : ''}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

function resolveMetadataAuthorityId(volume: Volume, infoData?: any): string {
  const fromInfo = String(
    infoData?.msi_representation_id ||
    infoData?.representation_id ||
    infoData?.metadata?.msi_representation_id ||
    ''
  ).trim();

  if (fromInfo) return fromInfo;

  const fromVolume = String(
    (volume as any)?.msi_representation_id ||
    (volume as any)?.representation_id ||
    ''
  ).trim();

  if (fromVolume) return fromVolume;

  const id = String(volume?.id || '').trim();
  return id;
}

export function VolumeInfoPanel({ volume }: VolumeInfoPanelProps) {
  const [infoData, setInfoData] = useState<any>(null);
  const [normalizedMetadata, setNormalizedMetadata] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [normalizedLoading, setNormalizedLoading] = useState(false);
  const [error, setError] = useState('');
  const [normalizedError, setNormalizedError] = useState('');

  useEffect(() => {
    let cancelled = false;

    async function loadInfo() {
      if (!volume?.id || volume.dataset_type === '2d_survey') {
        setInfoData(null);
        setNormalizedMetadata(null);
        setError('');
        setNormalizedError('');
        return;
      }

      setLoading(true);
      setNormalizedLoading(true);
      setError('');
      setNormalizedError('');

      try {
        const data = await getVolumeInfoForVolume(volume);
        if (!cancelled) setInfoData(data);
      } catch (err) {
        console.error('Failed to load selected dataset info', err);
        if (!cancelled) {
          setError('Failed to load selected dataset information.');
          setInfoData(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }

      try {
        const normalizedResponse = await fetchNormalizedMetadataForVolume(volume);
        if (!cancelled) {
          setNormalizedMetadata(normalizedResponse?.normalized_metadata || null);
        }
      } catch (err) {
        console.error('Failed to load normalized metadata', err);
        if (!cancelled) {
          setNormalizedError('Normalized metadata not available. Use Data Manager → Enrich metadata first.');
          setNormalizedMetadata(null);
        }
      } finally {
        if (!cancelled) setNormalizedLoading(false);
      }
    }

    loadInfo();

    return () => {
      cancelled = true;
    };
  }, [volume?.id, volume?.dataset_type]);

  if (!volume) {
    return (
      <div className="volume-info-panel empty-info">
        <h2>Dataset Information</h2>
        <p>No managed dataset selected. Search or select a 2D or 3D dataset from the top ribbon.</p>
      </div>
    );
  }

  const metadataAuthorityId = volume ? resolveMetadataAuthorityId(volume, infoData) : '';

  return (
    <div className="volume-info-panel">
      <div className="volume-info-header volume-info-header-with-score">
        <div className="volume-info-title-block">
          <h2>{getDisplayName(volume)}</h2>
          <p>{getDatasetTypeLabel(volume)}</p>
        </div>
        <MetadataScoreHeaderLink volumeId={metadataAuthorityId} />
      </div>

      {loading && <div className="info-loading">Loading dataset information...</div>}
      {error && <div className="info-error">{error}</div>}


      <div className="volume-info-content">
        <MetadataSummaryPanel volumeId={metadataAuthorityId} />
        {volume.dataset_type === '2d_survey' ? (
          <SurveyInfo volume={volume} normalizedMetadata={normalizedMetadata} normalizedLoading={normalizedLoading} normalizedError={normalizedError} metadataAuthorityId={metadataAuthorityId} />
        ) : volume.dataset_type === '2d_line' || volume.metadata?.is_3d === false ? (
          <LineInfo volume={volume} infoData={infoData} normalizedMetadata={normalizedMetadata} normalizedLoading={normalizedLoading} normalizedError={normalizedError} metadataAuthorityId={metadataAuthorityId} />
        ) : (
          <Volume3DInfo volume={volume} infoData={infoData} normalizedMetadata={normalizedMetadata} normalizedLoading={normalizedLoading} normalizedError={normalizedError} metadataAuthorityId={metadataAuthorityId} />
        )}
      </div>

      <div className="supporting-documents-placeholder">
        <MainInfoSupportingDocumentsSection volume={volume} infoData={infoData} />

        <h3>Supporting Links</h3>
        <p>Reserved for links to external linked resources.</p>
      </div>

</div>
  );
}
