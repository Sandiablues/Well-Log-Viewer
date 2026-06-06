const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

import axios from 'axios';
import { normalizedMetadataUrlForVolumeId, metadataSummaryUrlForVolumeId, isMsiRepresentationId } from './metadataRouteService';
import * as zarr from 'zarrita';

export interface Volume {
  id: string;
  filename: string;
  display_name?: string;
  survey_name?: string | null;
  line_name?: string | null;
  volume_name?: string | null;
  processing_stage?: string | null;
  processing_version?: string | null;
  hidden?: boolean;
  description?: string;
  metadata: any;
  zarr_url: string;
  dataset_type?: '3d_volume' | '2d_line' | '2d_survey' | 'unknown';
  read_mode?: 'zarr' | 'indexed_segy' | 'optimized_zarr_cache';
  optimized_cache_status?: string;
  optimized_cache?: {
    status?: string;
    zarr_url?: string;
    path?: string;
    cache_id?: string;
    validated?: boolean;
    worker?: string;
    zarr?: any;
    sidecars?: Record<string, string>;
    [key: string]: any;
  };
  source?: string;
  registry_source?: string;
  msi_dataset_id?: string;
  msi_representation_id?: string;
  physical_volume_id?: string;
  viewer_mode?: '2d' | '3d' | 'none' | string;
  representation_type?: string;
  storage_uri?: string;
  is_loaded?: boolean;
  loaded_from_msi?: boolean;
}

const BACKEND_BASE_URL = 'http://localhost:8000';
const INDEXED_SEGY_SCHEME = 'indexed-segy://';

function isIndexedSegyPath(path: string): boolean {
  return typeof path === 'string' && path.startsWith(INDEXED_SEGY_SCHEME);
}

function indexedSegyDatasetId(path: string): string {
  if (!isIndexedSegyPath(path)) {
    throw new Error(`Not an indexed SEG-Y path: ${path}`);
  }

  const datasetId = path.slice(INDEXED_SEGY_SCHEME.length).trim();

  if (!datasetId) {
    throw new Error('Indexed SEG-Y path is missing dataset id');
  }

  return datasetId;
}

function indexedSegyDatasetIdFromVolumeId(volumeId: string): string | null {
  const prefix = 'indexed-segy-';

  if (!volumeId || !volumeId.startsWith(prefix)) {
    return null;
  }

  const datasetId = volumeId.slice(prefix.length).trim();
  return datasetId || null;
}


function isMsiVolume(volume: Volume): boolean {
  const id = String(volume.id || '').trim();
  return (
    id.startsWith('msi_repr:') ||
    volume.source === 'msi' ||
    volume.registry_source === 'msi' ||
    Boolean(volume.msi_representation_id)
  );
}

export async function resolveMsiRepresentationVolume(representationId: string): Promise<any> {
  const encoded = encodeURIComponent(representationId);
  const response = await axios.get(`/api/msi/representations/${encoded}/resolved-volume`);
  return response.data;
}

export async function getVolumeInfoForVolume(volume: Volume): Promise<any> {
  if (isMsiVolume(volume)) {
    const representationId = String(
      (volume as any).msi_representation_id ||
      (volume as any).representation_id ||
      (volume as any).volume_id ||
      volume.id ||
      ''
    ).trim();

    if (representationId) {
      try {
        const encoded = encodeURIComponent(representationId);
        const response = await axios.get(`/api/msi/representations/${encoded}/info-page`);
        return response.data;
      } catch (err) {
        // Fall through to the legacy candidate loop for compatibility only.
        // Components must not resolve physical volume ids themselves.
      }
    }
  }

  const rawCandidates = [
    (volume as any).physical_volume_id,
    (volume as any).physicalVolumeId,
    (volume as any).volume_id,
    (volume as any).volumeId,
    volume.id,
  ];

  const candidates = Array.from(
    new Set(
      rawCandidates
        .map((value) => String(value || '').trim())
        .filter((value) => value.length > 0)
    )
  );

  let firstSuccessfulResponse: any = null;
  let lastError: any = null;

  for (const candidate of candidates) {
    try {
      const response = await axios.get(`/api/volumes/${encodeURIComponent(candidate)}/info`);
      const data = response.data;

      if (!firstSuccessfulResponse) {
        firstSuccessfulResponse = data;
      }

      const docs =
        data?.supporting_documents ||
        data?.document_context?.supporting_documents ||
        data?.metadata?.supporting_documents ||
        data?.metadata?.document_context?.supporting_documents ||
        [];

      const documentCount =
        data?.document_count ??
        data?.supporting_document_count ??
        data?.document_context?.document_count ??
        docs.length;

      if ((Array.isArray(docs) && docs.length > 0) || Number(documentCount || 0) > 0) {
        return data;
      }
    } catch (err) {
      lastError = err;
    }
  }

  if (firstSuccessfulResponse) {
    return firstSuccessfulResponse;
  }

  throw lastError || new Error('Failed to load selected dataset information.');
}
export async function fetchNormalizedMetadataForVolume(volume: Volume): Promise<any> {
  if (isMsiVolume(volume) || isMsiRepresentationId(volume.id)) {
    const representationId = String(volume.msi_representation_id || volume.id || '').trim();
    return fetchNormalizedMetadata(representationId);
  }

  return fetchNormalizedMetadata(volume.id);
}
function resolveZarrUrl(zarrPath: string): string {
  if (!zarrPath) {
    throw new Error('Missing Zarr path');
  }

  if (zarrPath.startsWith('http://') || zarrPath.startsWith('https://')) {
    return zarrPath;
  }

  const normalizedPath = zarrPath.startsWith('/') ? zarrPath : `/${zarrPath}`;
  return `${BACKEND_BASE_URL}${normalizedPath}`;
}

function parseShapeHeader(shapeHeader: unknown): number[] {
  if (typeof shapeHeader !== 'string' || !shapeHeader.trim()) {
    throw new Error(`Missing or invalid X-Slice-Shape header: ${String(shapeHeader)}`);
  }

  return shapeHeader
    .split(',')
    .map((v) => Number.parseInt(v.trim(), 10))
    .filter((v) => Number.isFinite(v));
}


function normalizeMsiCompatibleVolume(record: any): Volume | null {
  if (!record || typeof record !== 'object') return null;

  const id = String(record.id || record.volume_id || '').trim();
  const zarrUrl = String(record.zarr_url || '').trim();
  const representationId = String(record.msi_representation_id || '').trim();

  if (!id || !zarrUrl || !representationId) return null;

  const isLoaded = Boolean(record.is_loaded);

  return {
    ...record,
    id,
    filename: record.filename || record.display_name || record.name || id,
    display_name: record.display_name || record.name || record.filename || id,
    metadata: record.metadata || {},
    zarr_url: zarrUrl,
    dataset_type: record.dataset_type || 'unknown',
    source: 'msi',
    registry_source: record.registry_source || 'msi',
    msi_representation_id: representationId,
    is_loaded: isLoaded,
    loaded_from_msi: Boolean(record.loaded_from_msi || isLoaded),
    read_mode: record.read_mode || 'zarr',
  };
}

async function loadMsiCompatibleLoadedVolumes(): Promise<Volume[]> {
  try {
    const response = await axios.get('/api/managed-data/loaded');
    const rows = Array.isArray(response.data) ? response.data : [];

    return rows
      .map(normalizeMsiCompatibleVolume)
      .filter((volume): volume is Volume => Boolean(volume))
      .map((volume) => ({
        ...volume,
        hidden: false,
        is_loaded: true,
        loaded_from_msi: true,
      }));
  } catch (err) {
    console.warn('Failed to load MSI-compatible loaded volumes', err);
    return [];
  }
}

async function loadMsiCompatibleManagedVolumes(): Promise<Volume[]> {
  try {
    const response = await axios.get('/api/managed-data');
    const rows = Array.isArray(response.data) ? response.data : [];

    return rows
      .map(normalizeMsiCompatibleVolume)
      .filter((volume): volume is Volume => Boolean(volume))
      .map((volume) => ({
        ...volume,
        hidden: !Boolean(volume.is_loaded),
        loaded_from_msi: Boolean(volume.is_loaded),
      }));
  } catch (err) {
    console.warn('Failed to load MSI-compatible managed volumes', err);
    return [];
  }
}


function artifactIdentityKeys(volume: Volume): string[] {
  const keys = new Set<string>();

  const physicalVolumeId = String((volume as any).physical_volume_id || '').trim();
  const id = String(volume.id || '').trim();
  const zarrUrl = String((volume as any).zarr_url || '').trim();

  if (physicalVolumeId) keys.add(`physical:${physicalVolumeId}`);
  if (zarrUrl) keys.add(`zarr:${zarrUrl}`);

  // Legacy /api/volumes rows commonly use the physical Zarr id as `id`.
  // MSI rows use the representation id as `id` and carry the physical id separately.
  if (id && !id.startsWith('msi_repr:')) {
    keys.add(`physical:${id}`);
  }

  return Array.from(keys);
}

function suppressLegacyRowsManagedByMsi(base: Volume[], msiVolumes: Volume[]): Volume[] {
  const msiArtifactKeys = new Set<string>();

  for (const volume of msiVolumes) {
    for (const key of artifactIdentityKeys(volume)) {
      msiArtifactKeys.add(key);
    }
  }

  if (!msiArtifactKeys.size) {
    return base;
  }

  return base.filter((volume) => {
    const isMsi = volume.source === 'msi' || volume.registry_source === 'msi' || Boolean((volume as any).msi_representation_id);
    if (isMsi) return true;

    const keys = artifactIdentityKeys(volume);
    return !keys.some((key) => msiArtifactKeys.has(key));
  });
}


function upsertVolumesById(base: Volume[], incoming: Volume[]): Volume[] {
  const merged = [...base];

  for (const volume of incoming) {
    const existingIndex = merged.findIndex((item) => item.id === volume.id);

    if (existingIndex >= 0) {
      merged[existingIndex] = {
        ...merged[existingIndex],
        ...volume,
        metadata: {
          ...(merged[existingIndex].metadata || {}),
          ...(volume.metadata || {}),
        },
      };
    } else {
      merged.push(volume);
    }
  }

  return merged;
}


function isFullZarrManagedArtifact(volume: Volume): boolean {
  const readMode = String(volume.read_mode || '').trim().toLowerCase();
  const datasetType = String(volume.dataset_type || '').trim().toLowerCase();
  const zarrUrl = String(volume.zarr_url || '').trim();

  if (readMode === 'indexed_segy' || readMode === 'optimized_zarr_cache') {
    return false;
  }

  return (
    Boolean(zarrUrl) &&
    !zarrUrl.startsWith('indexed-segy://') &&
    (datasetType === '3d_volume' || datasetType === '2d_line' || datasetType === '2d_survey')
  );
}

function isMsiManagedVolume(volume: Volume): boolean {
  return (
    volume.source === 'msi' ||
    volume.registry_source === 'msi' ||
    Boolean((volume as any).msi_representation_id)
  );
}

function filterLegacyFullZarrRows(legacyVolumes: Volume[], msiManagedVolumes: Volume[]): Volume[] {
  const msiArtifactKeys = new Set<string>();

  for (const volume of msiManagedVolumes) {
    for (const key of artifactIdentityKeys(volume)) {
      msiArtifactKeys.add(key);
    }
  }

  return legacyVolumes.filter((volume) => {
    if (isMsiManagedVolume(volume)) {
      return true;
    }

    const keys = artifactIdentityKeys(volume);
    const isMsiOwnedDuplicate = keys.some((key) => msiArtifactKeys.has(key));

    if (isMsiOwnedDuplicate) {
      return false;
    }

    // Critical transition rule:
    // Legacy /api/volumes must no longer supply converted full-Zarr Managed Data rows.
    // Those rows must come through MSI. Legacy rows that are not full-Zarr artifacts
    // may remain temporarily for backward compatibility during migration.
    if (isFullZarrManagedArtifact(volume)) {
      return false;
    }

    return true;
  });
}


function isIndexedPreviewCatalogRow(volume: any): boolean {
  const zarrUrl = String(
    volume?.zarr_url ||
    volume?.metadata?.zarr_url ||
    volume?.metadata?.zarr?.zarr_url ||
    ""
  ).trim();

  const representationType = String(
    volume?.representation_type ||
    volume?.metadata?.representation_type ||
    ""
  ).trim().toLowerCase();

  const readMode = String(
    volume?.read_mode ||
    volume?.metadata?.read_mode ||
    volume?.metadata?.zarr?.read_mode ||
    ""
  ).trim().toLowerCase();

  const id = String(volume?.id || "").trim().toLowerCase();
  const source = String(volume?.source || volume?.registry_source || "").trim().toLowerCase();

  return (
    zarrUrl.startsWith(INDEXED_SEGY_SCHEME) ||
    representationType === "indexed_preview" ||
    readMode === "indexed_segy" ||
    id.startsWith("indexed-preview:") ||
    id.startsWith("indexed-segy") ||
    source === "indexed_segy"
  );
}

function filterIndexedPreviewCatalogRows(volumes: Volume[]): Volume[] {
  return volumes.filter((volume) => !isIndexedPreviewCatalogRow(volume));
}

async function getVolumesRaw(): Promise<Volume[]> {
  // MSI-owned Managed Data:
  // - full-Zarr managed artifacts come from MSI only.
  // - /api/volumes is no longer a frontend authority for converted full-Zarr rows.
  // - legacy /api/volumes is retained only for temporary non-full-Zarr compatibility rows.
  // - indexed SEG-Y preview/cache rows still come from /api/datasets.
  // - loaded MSI rows merge last so viewer dropdown/catalog state wins.
  const msiManagedVolumes = await loadMsiCompatibleManagedVolumes();
  let volumes: Volume[] = [...msiManagedVolumes];

  try {
    const response = await axios.get('/api/volumes');
    const legacyVolumes: Volume[] = Array.isArray(response.data) ? response.data : [];
    const allowedLegacyRows = filterLegacyFullZarrRows(legacyVolumes, msiManagedVolumes);
    volumes = upsertVolumesById(volumes, allowedLegacyRows);
  } catch (err) {
    console.warn('Failed to load legacy /api/volumes compatibility rows', err);
  }

  // Indexed SEG-Y datasets are not full-Zarr MSI managed artifacts yet.
  // They remain sourced from /api/datasets until indexed/optimized-cache lifecycle
  // is migrated into MSI.
  try {
    const datasetResponse = await axios.get('/api/datasets');
    const datasets = Array.isArray(datasetResponse.data?.datasets)
      ? datasetResponse.data.datasets
      : [];

    for (const dataset of datasets) {
      const datasetId = dataset.dataset_id || dataset.id;
      if (!datasetId) continue;

      const volumeId = dataset.legacy_volume_id || `indexed-segy-${datasetId}`;

      const indexedVolume: Volume = {
        id: volumeId,
        filename: dataset.filename || dataset.source_file_name || datasetId,
        display_name: dataset.display_name || dataset.filename || volumeId,
        description: dataset.description,
        hidden: dataset.hidden,
        zarr_url: dataset.zarr_url || `indexed-segy://${datasetId}`,
        dataset_type: dataset.dataset_type || 'unknown',
        read_mode: dataset.read_mode || 'indexed_segy',
        optimized_cache_status: dataset.optimized_cache_status || 'not_started',
        optimized_cache: dataset.optimized_cache,
        metadata: {
          ...(dataset.metadata || {}),
          dataset_id: datasetId,
          legacy_volume_id: volumeId,
          read_mode: dataset.read_mode || 'indexed_segy',
          optimized_cache_status: dataset.optimized_cache_status || 'not_started',
          optimized_cache: dataset.optimized_cache,
          shape: dataset.shape || dataset.metadata?.geometry?.shape || dataset.metadata?.shape,
          axis_order: dataset.axis_order || dataset.metadata?.geometry?.axis_order,
          sample_interval_ms: dataset.sample_interval_ms || dataset.metadata?.geometry?.sample_interval_ms,
          trace_count: dataset.trace_count || dataset.metadata?.geometry?.trace_count,
          inline_count: dataset.inline_count || dataset.metadata?.geometry?.inline_count,
          crossline_count: dataset.crossline_count || dataset.metadata?.geometry?.crossline_count,
          sample_count: dataset.sample_count || dataset.metadata?.geometry?.sample_count,
          is_3d: dataset.dataset_type === '3d_volume',
        },
      };

      const existingIndex = volumes.findIndex(
        (volume) =>
          volume.id === indexedVolume.id ||
          volume.id === datasetId ||
          volume.id === `indexed-segy-${datasetId}`
      );

      if (existingIndex >= 0) {
        volumes[existingIndex] = {
          ...volumes[existingIndex],
          ...indexedVolume,
          metadata: {
            ...(volumes[existingIndex].metadata || {}),
            ...(indexedVolume.metadata || {}),
          },
        };
      } else {
        volumes.push(indexedVolume);
      }
    }
  } catch (err) {
    console.warn('Failed to load indexed dataset registry records', err);
  }

  const msiLoadedVolumes = await loadMsiCompatibleLoadedVolumes();
  return upsertVolumesById(volumes, msiLoadedVolumes);
}

export async function getVolumes(): Promise<Volume[]> {
  const volumes = await getVolumesRaw();
  return filterIndexedPreviewCatalogRows(volumes);
}



export async function loadMsiRepresentation(representationId: string): Promise<any> {
  const response = await axios.post(`/api/managed-data/${encodeURIComponent(representationId)}/load`);
  return response.data;
}

export async function unloadMsiRepresentation(representationId: string): Promise<any> {
  const response = await axios.post(`/api/managed-data/${encodeURIComponent(representationId)}/unload`);
  return response.data;
}


export async function deleteMsiRepresentation(representationId: string): Promise<any> {
  const response = await axios.delete(`/api/managed-data/${encodeURIComponent(representationId)}`);
  return response.data;
}

export async function updateMsiRepresentationDisplayName(
  representationId: string,
  displayName: string
): Promise<any> {
  const cleanRepresentationId = String(representationId || '').trim();
  const cleanDisplayName = String(displayName || '').trim();

  if (!cleanRepresentationId) {
    throw new Error('MSI representation id is required for display-name update');
  }

  if (!cleanDisplayName) {
    throw new Error('Display name is required');
  }

  const response = await axios.post(
    `/api/msi/representations/${encodeURIComponent(cleanRepresentationId)}/display-name`,
    { display_name: cleanDisplayName }
  );

  return response.data;
}

export type MsiDatasetMetadataUpdates = {
  survey_name?: string | null;
  line_name?: string | null;
  volume_name?: string | null;
  processing_stage?: string | null;
  processing_version?: string | null;
};

export async function updateMsiRepresentationDatasetMetadata(
  representationId: string,
  updates: MsiDatasetMetadataUpdates
): Promise<any> {
  const cleanRepresentationId = String(representationId || '').trim();

  if (!cleanRepresentationId) {
    throw new Error('MSI representation id is required for dataset metadata update');
  }

  const payload: MsiDatasetMetadataUpdates = {};

  for (const field of ['survey_name', 'line_name', 'volume_name', 'processing_stage', 'processing_version'] as const) {
    if (Object.prototype.hasOwnProperty.call(updates, field)) {
      const value = updates[field];
      payload[field] = value === null || value === undefined ? null : String(value).trim() || null;
    }
  }

  if (Object.keys(payload).length === 0) {
    throw new Error('At least one MSI dataset metadata field is required');
  }

  const response = await axios.post(
    `/api/msi/representations/${encodeURIComponent(cleanRepresentationId)}/metadata`,
    payload
  );

  return response.data;
}

export async function updateVolume(
  volumeId: string,
  updates: Partial<Pick<Volume, 'display_name' | 'hidden' | 'description'>>
): Promise<Volume> {
  const indexedDatasetId = indexedSegyDatasetIdFromVolumeId(volumeId);

  if (indexedDatasetId) {
    const response = await axios.patch(`/api/datasets/${indexedDatasetId}`, updates);
    const dataset = response.data;

    return {
      id: dataset.legacy_volume_id || `indexed-segy-${dataset.dataset_id || indexedDatasetId}`,
      filename: dataset.filename || dataset.source_file_name || indexedDatasetId,
      display_name: dataset.display_name || dataset.filename || indexedDatasetId,
      description: dataset.description,
      hidden: dataset.hidden,
      zarr_url: dataset.zarr_url || `indexed-segy://${indexedDatasetId}`,
      dataset_type: dataset.dataset_type || 'unknown',
      read_mode: dataset.read_mode || 'indexed_segy',
      optimized_cache_status: dataset.optimized_cache_status || 'not_started',
      optimized_cache: dataset.optimized_cache,
      metadata: {
        ...(dataset.metadata || {}),
        dataset_id: dataset.dataset_id || indexedDatasetId,
        legacy_volume_id: dataset.legacy_volume_id || `indexed-segy-${indexedDatasetId}`,
        read_mode: dataset.read_mode || 'indexed_segy',
        optimized_cache_status: dataset.optimized_cache_status || 'not_started',
        optimized_cache: dataset.optimized_cache,
        shape: dataset.shape || dataset.metadata?.geometry?.shape || dataset.metadata?.shape,
        axis_order: dataset.axis_order || dataset.metadata?.geometry?.axis_order,
        sample_interval_ms: dataset.sample_interval_ms || dataset.metadata?.geometry?.sample_interval_ms,
        trace_count: dataset.trace_count || dataset.metadata?.geometry?.trace_count,
        inline_count: dataset.inline_count || dataset.metadata?.geometry?.inline_count,
        crossline_count: dataset.crossline_count || dataset.metadata?.geometry?.crossline_count,
        sample_count: dataset.sample_count || dataset.metadata?.geometry?.sample_count,
        is_3d: dataset.dataset_type === '3d_volume',
      },
    };
  }

  const response = await axios.patch(`/api/volumes/${volumeId}`, updates);
  return response.data;
}

export async function deleteVolume(volumeId: string): Promise<any> {
  const response = await axios.delete(`/api/volumes/${volumeId}`);
  return response.data;
}

export async function fetchSection2D(
  zarrPath: string,
  maxWidth = 1600,
  maxHeight = 900,
  clipPercentile = 99.0,
  processingMode = "demean",
  agcWindowSec = 0.5,
  filterType = "none",
  f1 = 8,
  f2 = 12,
  f3 = 80,
  f4 = 100
) {
  const response = await axios.get('/api/section2d', {
    params: {
      zarr_path: zarrPath,
      max_width: maxWidth,
      max_height: maxHeight,
      clip_percentile: clipPercentile,
      processing_mode: processingMode,
      agc_window_sec: agcWindowSec,
      filter_type: filterType,
      f1,
      f2,
      f3,
      f4,
    },
  });

  return response.data;
}

export async function fetchSection2DWindow(
  zarrPath: string,
  traceStart: number,
  traceEnd: number,
  sampleStart: number,
  sampleEnd: number,
  outputWidth = 1600,
  outputHeight = 900,
  clipPercentile = 99.0,
  processingMode = "demean",
  agcWindowSec = 0.5,
  filterType = "none",
  f1 = 8,
  f2 = 12,
  f3 = 80,
  f4 = 100
) {
  const response = await axios.get('/api/section2d/window', {
    params: {
      zarr_path: zarrPath,
      trace_start: Math.max(0, Math.floor(traceStart)),
      trace_end: Math.max(0, Math.ceil(traceEnd)),
      sample_start: Math.max(0, Math.floor(sampleStart)),
      sample_end: Math.max(0, Math.ceil(sampleEnd)),
      output_width: outputWidth,
      output_height: outputHeight,
      clip_percentile: clipPercentile,
      processing_mode: processingMode,
      agc_window_sec: agcWindowSec,
      filter_type: filterType,
      f1,
      f2,
      f3,
      f4,
    },
  });

  return response.data;
}


export async function fetchSlice(zarrPath: string, dim: number, index: number) {
  // Indexed SEG-Y read mode.
  // Inline/crossline slices are served directly from the source SEG-Y index.
  // Time/depth slices are deferred until optimized cache exists.
  if (isIndexedSegyPath(zarrPath)) {
    if (dim === 2) {
      throw new Error('Indexed SEG-Y mode supports inline/crossline preview only. Time slices require optimized cache.');
    }

    const datasetId = indexedSegyDatasetId(zarrPath);

    const response = await axios.get(`/api/segy-index/${datasetId}/slice`, {
      params: {
        dim,
        index,
        format: 'binary',
      },
      responseType: 'arraybuffer',
    });

    const rawShape = response.headers['x-shape'];
    const shape = typeof rawShape === 'string'
      ? JSON.parse(rawShape)
      : rawShape;

    const arrayBuffer = response.data as ArrayBuffer;
    const data = new Float32Array(arrayBuffer);

    const expectedLength = shape.reduce((acc: number, v: number) => acc * v, 1);
    if (data.length !== expectedLength) {
      throw new Error(
        `Indexed SEG-Y slice payload length mismatch. Expected ${expectedLength} float32 values from shape [${shape.join(
          ', '
        )}], got ${data.length}.`
      );
    }

    return { data, shape };
  }

  // Backend-assisted Zarr slice loading.
  const response = await axios.get('/api/slice', {
    params: {
      zarr_path: zarrPath,
      dim,
      index,
    },
    responseType: 'arraybuffer',
  });

  const shape = parseShapeHeader(response.headers['x-slice-shape']);
  const arrayBuffer = response.data as ArrayBuffer;
  const data = new Float32Array(arrayBuffer);

  const expectedLength = shape.reduce((acc, v) => acc * v, 1);
  if (data.length !== expectedLength) {
    throw new Error(
      `Slice payload length mismatch. Expected ${expectedLength} float32 values from shape [${shape.join(
        ', '
      )}], got ${data.length}.`
    );
  }

  return { data, shape };
}

export async function getZarrMetadata(zarrPath: string) {
  if (isIndexedSegyPath(zarrPath)) {
    const datasetId = indexedSegyDatasetId(zarrPath);
    const response = await axios.get(`/api/segy-index/${datasetId}`);
    const index = response.data;

    return {
      shape: index.shape,
      chunks: null,
      dtype: 'float32',
      read_mode: 'indexed_segy',
      optimized_cache_status: index.optimized_cache_status || 'not_started',
      sample_interval_ms: index.sample_interval_ms,
      sample_rate: index.sample_interval_ms,
      trace_count: index.trace_count,
      inline_count: index.inline_count,
      crossline_count: index.crossline_count,
      source_file_name: index.source_file_name,
    };
  }

  // Keep metadata loading direct for Zarr.
  console.log('Fetching metadata for:', zarrPath);

  const zarrUrl = resolveZarrUrl(zarrPath);
  console.log('Resolved Zarr URL:', zarrUrl);

  try {
    const store = new zarr.FetchStore(zarrUrl);
    console.log('Store created, opening array...');
    const arr = await zarr.open(store, { kind: 'array' });
    console.log('Array opened:', arr);
    return {
      shape: arr.shape,
      chunks: arr.chunks,
      dtype: arr.dtype,
    };
  } catch (err) {
    console.error('Error in getZarrMetadata:', err);
    throw err;
  }
}


export async function clearBackendSliceCache() {
  const response = await axios.post('/api/slice/clear-cache');
  return response.data;
}

export async function getBackendSliceCacheInfo() {
  const response = await axios.get('/api/slice/cache-info');
  return response.data;
}

export async function getVolumeInfo(volumeId: string): Promise<any> {
  const indexedDatasetId = indexedSegyDatasetIdFromVolumeId(volumeId);

  if (indexedDatasetId) {
    const response = await axios.get(`/api/datasets/${indexedDatasetId}/info`);
    return response.data;
  }

  const response = await axios.get(`/api/volumes/${volumeId}/info`);
  return response.data;
}


export async function get2DSurveyLines(surveyId: string): Promise<any[]> {
  const response = await axios.get(`/api/2d-surveys/${surveyId}/lines`);
  return response.data;
}


export async function getRecentJobs(limit = 20): Promise<any> {
  const response = await axios.get('/api/jobs', {
    params: { limit },
  });

  return response.data;
}


export async function getBackendLogTail(lines = 80): Promise<any> {
  const response = await axios.get('/api/system/backend-log-tail', {
    params: { lines },
  });

  return response.data;
}


export async function restartBackend(): Promise<any> {
  const response = await axios.post('/api/system/restart-backend');
  return response.data;
}

export async function enrichVolumeMetadata(volumeId: string) {
  const response = await fetch(`${API_BASE_URL}/api/volumes/${volumeId}/metadata/enrich`, {
    method: "POST",
  });

  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new Error(`Failed to enrich metadata: ${response.status} ${response.statusText} ${detail}`);
  }

  return response.json();
}

export async function fetchNormalizedMetadata(volumeId: string) {
  const primaryUrl = normalizedMetadataUrlForVolumeId(volumeId);
  const primaryResponse = await fetch(primaryUrl);

  if (primaryResponse.ok) {
    return primaryResponse.json();
  }

  // Indexed SEG-Y datasets may reach the Info panel either as:
  //   indexed-segy-{dataset_id}
  // or as the raw dataset_id.
  // Keep this fallback here so the UI does not need to know registry internals.
  const indexedDatasetId = indexedSegyDatasetIdFromVolumeId(volumeId) || volumeId;
  const datasetUrl = `${API_BASE_URL}/api/datasets/${indexedDatasetId}/metadata/normalized`;

  if (datasetUrl !== primaryUrl) {
    const datasetResponse = await fetch(datasetUrl);

    if (datasetResponse.ok) {
      return datasetResponse.json();
    }

    const datasetDetail = await datasetResponse.text().catch(() => "");
    const primaryDetail = await primaryResponse.text().catch(() => "");
    throw new Error(
      `Failed to fetch normalized metadata. primary=${primaryResponse.status} ${primaryResponse.statusText} ${primaryDetail}; dataset=${datasetResponse.status} ${datasetResponse.statusText} ${datasetDetail}`
    );
  }

  const detail = await primaryResponse.text().catch(() => "");
  throw new Error(`Failed to fetch normalized metadata: ${primaryResponse.status} ${primaryResponse.statusText} ${detail}`);
}

export async function getMetadataSummary(volumeId: string): Promise<any> {
  const response = await fetch(metadataSummaryUrlForVolumeId(volumeId));
  if (!response.ok) {
    throw new Error(`Failed to fetch metadata summary for volume ${volumeId}`);
  }
  return response.json();
}

