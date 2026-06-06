import { X } from "lucide-react";
import type { Volume } from "../types";

type DetailRecord = Record<string, unknown>;

function firstNonEmpty(...values: unknown[]): string | null {
  for (const value of values) {
    if (value === null || value === undefined) continue;
    const text = String(value).trim();
    if (text) return text;
  }
  return null;
}

function cleanDetails(record: DetailRecord): Array<[string, string]> {
  return Object.entries(record)
    .map(([key, value]) => {
      if (value === null || value === undefined) return null;
      const text = String(value).trim();
      if (!text) return null;
      return [key, text] as [string, string];
    })
    .filter((entry): entry is [string, string] => Boolean(entry));
}

function labelize(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function renderDetailGrid(title: string, details: DetailRecord) {
  const rows = cleanDetails(details);
  if (!rows.length) return null;

  return (
    <section>
      <h4>{title}</h4>
      <div className="info-grid">
        {rows.map(([key, value]) => (
          <div key={key}>
            <strong>{labelize(key)}</strong>
            <span>{value}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function getSourceReference(infoVolume: any): DetailRecord {
  const metadata = infoVolume?.metadata || {};
  return (
    infoVolume?.source_reference ||
    metadata?.source_reference ||
    metadata?.source ||
    {}
  );
}

function buildDatasetIdentityDetails(infoVolume: any): DetailRecord {
  const metadata = infoVolume?.metadata || {};
  const sourceReference = getSourceReference(infoVolume);
  const managedIdentity = metadata?.managed_data_info?.dataset_identity || {};
  const directDetails = infoVolume?.dataset_identity_details || {};
  const identity = metadata?.identity || {};

  return {
    survey_name: firstNonEmpty(
      directDetails.survey_name,
      managedIdentity.survey_name,
      infoVolume?.survey_name,
      metadata?.survey_name,
      sourceReference.survey_name,
      identity.survey_name,
      "—",
    ),
    line_name: firstNonEmpty(
      directDetails.line_name,
      managedIdentity.line_name,
      infoVolume?.line_name,
      metadata?.line_name,
      sourceReference.line_name,
      identity.line_name,
    ),
    volume_name: firstNonEmpty(
      directDetails.volume_name,
      managedIdentity.volume_name,
      infoVolume?.volume_name,
      metadata?.volume_name,
      sourceReference.volume_name,
      identity.volume_name,
    ),
  };
}

function buildSourceDetails(infoVolume: any): DetailRecord {
  const metadata = infoVolume?.metadata || {};
  const sourceReference = getSourceReference(infoVolume);
  const managedInfoSource = metadata?.managed_data_info?.source_file || {};
  const directSourceDetails = infoVolume?.source_file_details || {};

  return {
    source_filename: firstNonEmpty(
      directSourceDetails.source_filename,
      managedInfoSource.source_filename,
      sourceReference.filename,
      sourceReference.source_filename,
      infoVolume?.source_filename,
      infoVolume?.source_file,
      infoVolume?.filename,
    ),
    source_repository_id: firstNonEmpty(
      directSourceDetails.source_repository_id,
      managedInfoSource.source_repository_id,
      sourceReference.repository_id,
      infoVolume?.repository_id,
      metadata?.repository_id,
    ),
    source_package_id: firstNonEmpty(
      directSourceDetails.source_package_id,
      managedInfoSource.source_package_id,
      sourceReference.package_id,
      infoVolume?.package_id,
      metadata?.package_id,
    ),
    source_line_id: firstNonEmpty(
      directSourceDetails.source_line_id,
      managedInfoSource.source_line_id,
      sourceReference.line_id,
      infoVolume?.line_id,
      metadata?.line_id,
    ),
    source_segy_file_id: firstNonEmpty(
      directSourceDetails.source_segy_file_id,
      managedInfoSource.source_segy_file_id,
      sourceReference.source_segy_file_id,
      sourceReference.segy_file_id,
      infoVolume?.source_segy_file_id,
      metadata?.source_segy_file_id,
    ),
    source_relative_path: firstNonEmpty(
      directSourceDetails.source_relative_path,
      managedInfoSource.source_relative_path,
      sourceReference.relative_path,
      sourceReference.source_relative_path,
      infoVolume?.relative_path,
      metadata?.source_relative_path,
    ),
    source_path: firstNonEmpty(
      directSourceDetails.source_path,
      managedInfoSource.source_path,
      sourceReference.source_path,
      sourceReference.input_path,
      infoVolume?.source_path,
      metadata?.source_path,
    ),
    source_system: firstNonEmpty(
      directSourceDetails.source_system,
      managedInfoSource.source_system,
      sourceReference.source_system,
      infoVolume?.source,
      infoVolume?.registry_source,
    ),
    conversion_job_id: firstNonEmpty(
      sourceReference.job_id,
      infoVolume?.job_id,
      metadata?.job_id,
    ),
  };
}

function buildManagedRepresentationDetails(infoVolume: any): DetailRecord {
  const metadata = infoVolume?.metadata || {};
  const sourceReference = getSourceReference(infoVolume);
  const managedInfo = metadata?.managed_data_info?.managed_representation || {};
  const directDetails = infoVolume?.managed_representation_details || {};

  return {
    msi_dataset_id: firstNonEmpty(
      directDetails.msi_dataset_id,
      managedInfo.msi_dataset_id,
      infoVolume?.msi_dataset_id,
      sourceReference.msi_dataset_id,
    ),
    msi_representation_id: firstNonEmpty(
      directDetails.msi_representation_id,
      managedInfo.msi_representation_id,
      infoVolume?.msi_representation_id,
      sourceReference.msi_representation_id,
    ),
    physical_volume_id: firstNonEmpty(
      directDetails.physical_volume_id,
      managedInfo.physical_volume_id,
      infoVolume?.physical_volume_id,
      sourceReference.volume_id,
      infoVolume?.id,
    ),
    dataset_type: firstNonEmpty(
      directDetails.dataset_type,
      managedInfo.dataset_type,
      infoVolume?.dataset_type,
      metadata?.dataset_type,
    ),
    representation_type: firstNonEmpty(
      directDetails.representation_type,
      managedInfo.representation_type,
      infoVolume?.representation_type,
      metadata?.representation?.representation_type,
    ),
    viewer_mode: firstNonEmpty(
      directDetails.viewer_mode,
      managedInfo.viewer_mode,
      infoVolume?.viewer_mode,
      metadata?.representation?.viewer_mode,
    ),
    loaded_state: firstNonEmpty(
      directDetails.loaded_state,
      managedInfo.loaded_state,
      Boolean(infoVolume?.is_loaded) ? "loaded" : "unloaded",
    ),
    storage_uri: firstNonEmpty(
      directDetails.storage_uri,
      managedInfo.storage_uri,
      infoVolume?.storage_uri,
      sourceReference.storage_uri,
      metadata?.storage_uri,
    ),
    zarr_url: firstNonEmpty(
      directDetails.zarr_url,
      managedInfo.zarr_url,
      infoVolume?.zarr_url,
      sourceReference.zarr_url,
      metadata?.zarr_url,
    ),
  };
}

type VolumeInfoModalProps = {
  infoVolume: Volume;
  infoData: any;
  infoLoading: boolean;
  infoError: string | null;
  onClose: () => void;
  getDisplayName: (volume: Volume) => string;
  getShape: (volume: Volume) => string;
  getGeometrySource: (volume: Volume) => string;
};

export default function VolumeInfoModal({
  infoVolume,
  infoData,
  infoLoading,
  infoError,
  onClose,
  getDisplayName,
  getShape,
  getGeometrySource,
}: VolumeInfoModalProps) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="info-modal" onClick={(event) => event.stopPropagation()}>
        <div className="info-modal-header">
          <div>
            <h3>{getDisplayName(infoVolume)}</h3>
            <p>{infoVolume.filename}</p>
          </div>

          <button className="modal-close" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        {infoLoading && <div className="info-loading">Loading volume info...</div>}

        {infoError && <div className="info-error">{infoError}</div>}

        {infoData && (
          <div className="info-modal-body">
            {renderDetailGrid("Dataset Identity", buildDatasetIdentityDetails(infoVolume))}
            {renderDetailGrid("Source File", buildSourceDetails(infoVolume))}

            <section>
              <h4>Conversion / Volume</h4>
              <div className="info-grid">
                <div><strong>Shape</strong><span>{getShape(infoVolume)}</span></div>
                <div><strong>Geometry</strong><span>{getGeometrySource(infoVolume)}</span></div>
                <div><strong>Zarr URL</strong><span>{infoVolume.zarr_url}</span></div>
                <div><strong>Trace Count</strong><span>{infoVolume.metadata?.trace_count ?? "—"}</span></div>
                <div><strong>Sample Rate</strong><span>{infoVolume.metadata?.sample_rate ?? "—"}</span></div>
                <div><strong>Chunks</strong><span>{infoVolume.metadata?.zarr?.chunks?.join(" × ") ?? "—"}</span></div>
              </div>
            </section>

            {renderDetailGrid("Managed Representation", buildManagedRepresentationDetails(infoVolume))}

            <section>
              <h4>Sidecar Files</h4>
              <div className="sidecar-list">
                {Object.entries(infoData.sidecars || {}).map(([key, value]: any) => (
                  <div key={key}>
                    <strong>{key}</strong>
                    <span>{value.exists ? value.filename : "Not available"}</span>
                  </div>
                ))}
              </div>
            </section>

            <section>
              <h4>SEG-Y Text Header</h4>
              <pre className="text-header">{infoData.text_header || "Text header not available."}</pre>
            </section>

            <section>
              <h4>Binary Header</h4>
              <pre className="json-block">{JSON.stringify(infoData.binary_header, null, 2)}</pre>
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
