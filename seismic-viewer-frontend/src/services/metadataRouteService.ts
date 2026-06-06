const INDEXED_SEGY_PREFIX = 'indexed-segy-';

export function isMsiRepresentationId(value: string | undefined | null): boolean {
  return String(value || '').trim().startsWith('msi_repr:');
}

export function datasetIdFromIndexedVolumeId(volumeId: string | undefined | null): string | null {
  const text = String(volumeId || '').trim();
  if (!text.startsWith(INDEXED_SEGY_PREFIX)) return null;
  const datasetId = text.slice(INDEXED_SEGY_PREFIX.length).trim();
  return datasetId || null;
}

function encodedMsiRepresentationId(volumeId: string): string {
  return encodeURIComponent(String(volumeId || '').trim());
}

export function metadataSummaryUrlForVolumeId(volumeId: string): string {
  const indexedDatasetId = datasetIdFromIndexedVolumeId(volumeId);

  if (indexedDatasetId) {
    return `/api/datasets/${indexedDatasetId}/metadata-summary`;
  }

  if (isMsiRepresentationId(volumeId)) {
    return `/api/msi/representations/${encodedMsiRepresentationId(volumeId)}/metadata-summary`;
  }

  return `/api/volumes/${volumeId}/metadata-summary`;
}

export function metadataCompletenessUrlForVolumeId(volumeId: string): string {
  const indexedDatasetId = datasetIdFromIndexedVolumeId(volumeId);

  if (indexedDatasetId) {
    return `/api/datasets/${indexedDatasetId}/metadata-completeness`;
  }

  // MSI currently exposes completeness through the metadata-summary payload,
  // matching the existing physical-volume behavior.
  if (isMsiRepresentationId(volumeId)) {
    return `/api/msi/representations/${encodedMsiRepresentationId(volumeId)}/metadata-summary`;
  }

  return `/api/volumes/${volumeId}/metadata-summary`;
}

export function metadataScoreReportUrlForVolumeId(volumeId: string): string {
  const indexedDatasetId = datasetIdFromIndexedVolumeId(volumeId);

  if (indexedDatasetId) {
    return `/api/datasets/${indexedDatasetId}/metadata-score-report`;
  }

  if (isMsiRepresentationId(volumeId)) {
    return `/api/msi/representations/${encodedMsiRepresentationId(volumeId)}/metadata-score-report`;
  }

  return `/api/volumes/${volumeId}/metadata-score-report`;
}

export function normalizedMetadataUrlForVolumeId(volumeId: string): string {
  const indexedDatasetId = datasetIdFromIndexedVolumeId(volumeId);

  if (indexedDatasetId) {
    return `/api/datasets/${indexedDatasetId}/metadata/normalized`;
  }

  if (isMsiRepresentationId(volumeId)) {
    return `/api/msi/representations/${encodedMsiRepresentationId(volumeId)}/metadata/normalized`;
  }

  return `/api/volumes/${volumeId}/metadata/normalized`;
}
