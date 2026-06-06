import type { ChangeEvent } from "react";

type ManagedDataBulkToolbarProps = {
  searchText: string;
  onSearchTextChange: (value: string) => void;
  totalCount: number;
  visibleCount: number;
  selectedCount: number;
  bulkDeleteBusy: boolean;
  bulkDeleteMessage: string | null;
  queryLoading: boolean;
  queryError: string | null;
  pageOffset: number;
  pageLimit: number;
  hasNextPage: boolean;
  onPreviousPage: () => void;
  onNextPage: () => void;
  onPageLimitChange: (limit: number) => void;
  selectedAction: string;
  onSelectedActionChange: (value: string) => void;
  onApplySelectedAction: () => void;
};

function cleanText(value: unknown): string {
  return String(value ?? "").trim();
}

export function getManagedDataRowId(volume: any): string {
  return cleanText(volume?.msi_representation_id || volume?.id || volume?.volume_id);
}

export function managedDataRowMatchesSearch(
  volume: any,
  query: string,
  getDisplayName: (volume: any) => string,
): boolean {
  const normalizedQuery = cleanText(query).toLowerCase();
  if (!normalizedQuery) return true;

  const metadata = volume?.metadata || {};
  const normalizedMetadata = volume?.normalized_metadata || {};
  const sourceReference = volume?.source_reference || metadata?.source_reference || {};

  const searchable = [
    getDisplayName(volume),
    volume?.display_name,
    volume?.name,
    volume?.filename,
    volume?.dataset_type,
    volume?.viewer_mode,
    volume?.representation_type,
    volume?.survey_name,
    volume?.line_name,
    volume?.volume_name,
    volume?.processing_stage,
    volume?.processing_version,
    volume?.source_repository_name,
    volume?.source_repository_id,
    volume?.id,
    volume?.volume_id,
    volume?.msi_dataset_id,
    volume?.msi_representation_id,
    volume?.physical_volume_id,
    normalizedMetadata?.identity?.survey_name,
    sourceReference?.repository_id,
    sourceReference?.package_id,
    sourceReference?.line_id,
    sourceReference?.source_segy_file_id,
    sourceReference?.filename,
    sourceReference?.relative_path,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();

  return searchable.includes(normalizedQuery);
}

const toolbarControlStyle = {
  background: "transparent",
  border: "1px solid #64748b",
  borderRadius: 6,
  color: "#cbd5e1",
  padding: "5px 8px",
  fontSize: 12,
  fontWeight: 700,
} as const;

export default function ManagedDataBulkToolbar({
  searchText,
  onSearchTextChange,
  totalCount,
  visibleCount,
  selectedCount,
  bulkDeleteBusy,
  bulkDeleteMessage,
  queryLoading,
  queryError,
  pageOffset,
  pageLimit,
  hasNextPage,
  onPreviousPage,
  onNextPage,
  onPageLimitChange,
  selectedAction,
  onSelectedActionChange,
  onApplySelectedAction,
}: ManagedDataBulkToolbarProps) {
  const handleSearchChange = (event: ChangeEvent<HTMLInputElement>) => {
    onSearchTextChange(event.currentTarget.value);
  };

  const firstVisible = totalCount === 0 || visibleCount === 0 ? 0 : pageOffset + 1;
  const lastVisible = totalCount === 0 || visibleCount === 0 ? 0 : pageOffset + visibleCount;

  return (
    <div
      className="managed-data-bulk-toolbar"
      style={{
        border: "1px solid #334155",
        borderRadius: 8,
        padding: 10,
        marginBottom: 10,
        background: "rgba(15,23,42,0.42)",
      }}
    >
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: 8,
          alignItems: "center",
        }}
      >
        <input
          type="search"
          value={searchText}
          onChange={handleSearchChange}
          placeholder="Search MSI Managed Data..."
          aria-label="Search MSI Managed Data"
          className="md-control-input"
          style={{
            width: 476,
            maxWidth: "55.5vw",
            minWidth: 180,
            flex: "0 1 476px",
          }}
        />

        <label style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12 }}>
          <span>Page size</span>
          <select
            value={pageLimit}
            onChange={(event) => onPageLimitChange(Number(event.currentTarget.value))}
            disabled={bulkDeleteBusy || queryLoading}
            className="md-control-select" style={toolbarControlStyle}
          >
            <option value={50}>50</option>
            <option value={100}>100</option>
            <option value={250}>250</option>
            <option value={500}>500</option>
          </select>
        </label>

        <button
          type="button"
          className="md-control-select" style={toolbarControlStyle}
          onClick={onPreviousPage}
          disabled={pageOffset <= 0 || bulkDeleteBusy || queryLoading}
          title="Previous Managed Data page"
        >
          Previous
        </button>

        <button
          type="button"
          className="md-control-select" style={toolbarControlStyle}
          onClick={onNextPage}
          disabled={!hasNextPage || bulkDeleteBusy || queryLoading}
          title="Next Managed Data page"
        >
          Next
        </button>

        <span style={{ fontSize: 12, opacity: 0.82 }}>
          Showing {firstVisible}–{lastVisible} of {totalCount}
        </span>

        {queryLoading && <span style={{ fontSize: 12, opacity: 0.82 }}>Loading query...</span>}
        {queryError && <span style={{ color: "#fca5a5", fontSize: 12 }}>Query error: {queryError}</span>}
      </div>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          width: 476,
          maxWidth: "55.5vw",
          minWidth: 180,
          marginTop: 8,
        }}
      >
        <span style={{ fontSize: 12, opacity: 0.86, whiteSpace: "nowrap" }}>
          Selected {selectedCount}
        </span>

        <div
          style={{
            display: "inline-flex",
            flexWrap: "nowrap",
            gap: 8,
            alignItems: "center",
            justifyContent: "flex-end",
            marginLeft: "auto",
          }}
        >
          <label style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12 }}>
            <span>Action</span>
            <select
              value={selectedAction}
              onChange={(event) => onSelectedActionChange(event.currentTarget.value)}
              disabled={bulkDeleteBusy || queryLoading}
              className="md-control-select" style={{ ...toolbarControlStyle, minWidth: 220 }}
            >
              <option value="load">Load selected to Viewer</option>
              <option value="unload">Unload selected from Viewer</option>
              <option value="add_documents">Add Documents</option>
              <option value="delete">Delete selected records/artifacts</option>
            </select>
          </label>

          <button
            type="button"
            className={`md-control-button md-apply-button md-action-${selectedAction}`}
            onClick={onApplySelectedAction}
            disabled={!selectedCount || bulkDeleteBusy || queryLoading}
            title="Apply selected Managed Data action"
          >
            {bulkDeleteBusy ? "Applying..." : `Apply (${selectedCount})`}
          </button>
        </div>
      </div>

      {bulkDeleteMessage && (
        <div
          style={{
            marginTop: 8,
            border: "1px solid #64748b",
            borderRadius: 6,
            padding: "6px 8px",
            fontSize: 12,
            opacity: 0.9,
          }}
        >
          {bulkDeleteMessage}
        </div>
      )}
    </div>
  );
}
