import axios from 'axios';
import type { Volume } from './zarrService';

type ManagedDataQueryResponse = {
  rows?: unknown[];
  total_count?: number;
  returned_count?: number;
  has_more?: boolean;
  limit?: number;
  offset?: number;
};

export type SeismicDataInfoViewerMode = '2d' | '3d';

export type SeismicDataInformationCatalogPage = {
  rows: Volume[];
  totalCount: number;
  returnedCount: number;
  hasMore: boolean;
  limit: number;
  offset: number;
};

function isSeismicManagedRow(value: any): value is Volume {
  if (!value || typeof value !== 'object') return false;

  const representationId = String(
    value.msi_representation_id || value.representation_id || value.id || ''
  ).trim();
  const viewerMode = String(value.viewer_mode || value.metadata?.representation?.viewer_mode || '').trim();
  const datasetType = String(value.dataset_type || '').trim();

  return (
    representationId.startsWith('msi_repr:') &&
    (viewerMode === '2d' || viewerMode === '3d') &&
    (datasetType === '2d_line' || datasetType === '2d_survey' || datasetType === '3d_volume' || datasetType === 'unknown')
  );
}

function normalizeManagedRow(row: any): Volume {
  return {
    ...row,
    id: String(row.msi_representation_id || row.id),
    msi_representation_id: String(row.msi_representation_id || row.id),
    filename: row.filename || row.display_name || row.name || String(row.id),
    display_name: row.display_name || row.name || row.filename || String(row.id),
    metadata: row.metadata || {},
    hidden: !Boolean(row.is_loaded),
    loaded_from_msi: Boolean(row.is_loaded),
  } as Volume;
}

export async function querySeismicDataInformationCatalog(
  searchText = '',
  viewerMode: SeismicDataInfoViewerMode,
  limit = 50,
  offset = 0,
): Promise<SeismicDataInformationCatalogPage> {
  const q = String(searchText || '').trim();
  const response = await axios.get<ManagedDataQueryResponse>('/api/managed-data/query', {
    params: {
      q: q || undefined,
      viewer_mode: viewerMode,
      limit,
      offset,
      sort_by: viewerMode === '2d' ? 'line_name' : 'volume_name',
      sort_dir: 'asc',
    },
  });

  const rawRows = Array.isArray(response.data?.rows) ? response.data.rows : [];
  const rows = rawRows.filter(isSeismicManagedRow).map(normalizeManagedRow);

  return {
    rows,
    totalCount: Number(response.data?.total_count ?? rows.length),
    returnedCount: Number(response.data?.returned_count ?? rows.length),
    hasMore: Boolean(response.data?.has_more),
    limit: Number(response.data?.limit ?? limit),
    offset: Number(response.data?.offset ?? offset),
  };
}
