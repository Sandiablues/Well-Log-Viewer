import { useEffect, useState } from 'react';
import { Trash2, Edit3, Database, Info, X, Upload } from 'lucide-react';
import type { Volume } from '../services/zarrService';
import SourceIntakeWorkflowPanel from "./SourceIntakeWorkflowPanel";
import ManagedDataPanel from './ManagedDataPanel';
import VolumeInfoModal from "./VolumeInfoModal";
import { useManagedDataSelection } from "../hooks/useManagedDataSelection";
import { useManagedVolumeActions } from "../hooks/useManagedVolumeActions";
import { useManagedDeleteAction } from "../hooks/useManagedDeleteAction";
import { useManagedInfoModal } from "../hooks/useManagedInfoModal";

interface DataManagerProps {
  pageMode?: 'source-intake' | 'managed';
  volumes: Volume[];
  selectedVolume: Volume | null;
  selectedLoadMode?: 'preview' | 'optimized_cache';
  activeDataTab?: '3d' | '2d';
  onActiveDataTabChange?: (tab: '3d' | '2d') => void;
  onSelectVolume: (volume: Volume, options?: { loadMode?: 'preview' | 'optimized_cache' }) => void;
  onRefreshVolumes: () => Promise<void>;
  onUploadSegy: (e: React.ChangeEvent<HTMLInputElement>) => Promise<void>;
  isUploading: boolean;
  onClearSelectedVolume: () => void;
  onViewIndexedPreview?: (viewerSource: any) => void;
  onOpenSourcesPage?: () => void;
}

function getDisplayName(volume: Volume): string {
  return volume.display_name || volume.filename || volume.id;
}

function getShape(volume: Volume): string {
  const shape = volume.metadata?.shape || volume.metadata?.zarr?.shape;
  return Array.isArray(shape) ? shape.join(' × ') : 'Unknown';
}

function getGeometrySource(volume: Volume): string {
  return volume.metadata?.geometry_source || volume.metadata?.zarr?.geometry_source || 'Unknown';
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
      return 'Unknown';
  }
}

function isDisplayable3D(volume: Volume): boolean {
  const is3d = volume.metadata?.is_3d;
  const shape = volume.metadata?.shape || volume.metadata?.zarr?.shape;
  return is3d !== false && Array.isArray(shape) && shape.length === 3;
}

function isDisplayableDataset(volume: Volume): boolean {
  const shape = volume.metadata?.shape || volume.metadata?.zarr?.shape;

  if (volume.dataset_type === '3d_volume') {
    return Array.isArray(shape) && shape.length === 3;
  }

  if (volume.dataset_type === '2d_line') {
    return Array.isArray(shape) && shape.length === 2;
  }

  if (volume.dataset_type === '2d_survey') {
    return true;
  }

  return isDisplayable3D(volume);
}


function hasAvailableOptimizedCache(volume: Volume): boolean {
  const cache = (volume as any).optimized_cache;
  return Boolean(
    cache &&
    cache.status === 'available' &&
    cache.validated === true &&
    typeof cache.zarr_url === 'string' &&
    cache.zarr_url.length > 0
  );
}

function getOptimizedAvailabilityLabel(volume: Volume): string {
  const cache = (volume as any).optimized_cache;
  const status = String((volume as any).optimized_cache_status || cache?.status || 'not_started');

  if (status === 'available' && cache?.validated === true) return 'Fully Converted';
  if (status === 'available') return 'Fully Converted';
  if (status === 'converting' || status === 'queued' || status === 'reading_index') return 'Converting';
  if (status === 'failed') return 'Conversion Failed';
  if (status === 'cancelled') return 'Cancelled';
  return 'Not Converted';
}

function Import2DSurveyPanel({ onImported }: { onImported: () => void }) {
  const [sourceFolder, setSourceFolder] = useState('/Users/donarcher/Desktop/Seismic_Viewer/Test_Data/Rhode_Island_Sound_2D');
  const [surveyName, setSurveyName] = useState('Rhode_Island_Sound_2D');
  const [replaceExisting, setReplaceExisting] = useState(true);
  const [isImporting, setIsImporting] = useState(false);
  const [message, setMessage] = useState('');

  const importSurvey = async () => {
    if (!sourceFolder.trim()) {
      setMessage('Source folder is required.');
      return;
    }

    if (!surveyName.trim()) {
      setMessage('Survey name is required.');
      return;
    }

    setIsImporting(true);
    setMessage('Importing 2D survey. This may take several minutes...');

    try {
      const response = await fetch('/api/2d-surveys/import-folder', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_folder: sourceFolder.trim(),
          survey_name: surveyName.trim(),
          replace_existing_survey: replaceExisting,
        }),
      });

      const result = await response.json();

      if (!result.ok) {
        setMessage(result.message || '2D survey import failed.');
        console.error('2D survey import failed', result);
        return;
      }

      setMessage(result.message || '2D survey imported.');
      onImported();
    } catch (err) {
      console.error('2D survey import request failed', err);
      setMessage('2D survey import request failed. Check backend log.');
    } finally {
      setIsImporting(false);
    }
  };

  return (
    <div
      style={{
        border: '1px solid #333',
        background: '#1f1f1f',
        borderRadius: 8,
        padding: 12,
        marginBottom: 14,
        color: 'white',
      }}
    >

      <div style={{ fontWeight: 400, marginBottom: 8 }}>Import 2D Survey from Folder</div>

      <div style={{ display: 'grid', gridTemplateColumns: '130px 1fr', gap: '8px 10px', alignItems: 'center' }}>
        <label style={{ fontSize: 13, opacity: 0.8 }}>Survey name</label>
        <input
          value={surveyName}
          onChange={(e) => setSurveyName(e.target.value)}
          disabled={isImporting}
          style={{
            background: '#2b2b2b',
            color: 'white',
            border: '1px solid #555',
            borderRadius: 4,
            padding: '7px 8px',
          }}
        />

        <label style={{ fontSize: 13, opacity: 0.8 }}>Source folder</label>
        <input
          value={sourceFolder}
          onChange={(e) => setSourceFolder(e.target.value)}
          disabled={isImporting}
          placeholder="/path/to/master/survey/folder"
          style={{
            background: '#2b2b2b',
            color: 'white',
            border: '1px solid #555',
            borderRadius: 4,
            padding: '7px 8px',
          }}
        />
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginTop: 10 }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
          <input
            type="checkbox"
            checked={replaceExisting}
            onChange={(e) => setReplaceExisting(e.target.checked)}
            disabled={isImporting}
          />
          Replace existing survey
        </label>

        <button
          onClick={importSurvey}
          disabled={isImporting}
          style={{
          border: isUploading || !selectedFile ? "1px solid #52525b" : "1px solid #60a5fa",
          borderRadius: 6,
          background: "transparent",
          color: isUploading || !selectedFile ? "#71717a" : "#60a5fa",
          padding: "6px 10px",
          fontSize: 12,
          fontWeight: 800,
          cursor: isUploading || !selectedFile ? "not-allowed" : "pointer",
        }}
        >
          {isImporting ? 'Importing...' : 'Import Survey'}
        </button>
      </div>

      {message && (
        <div style={{ marginTop: 10, fontSize: 13, opacity: 0.85 }}>
          {message}
        </div>
      )}

      <div style={{ marginTop: 8, fontSize: 12, opacity: 0.6 }}>
        The folder is scanned recursively for .sgy and .segy files. Use the master survey folder, not an individual line folder.
      </div>
    </div>
  );
}


function SegyUploadPanel({
  mode,
  isUploading,
  onUploadSegy,
  disabled = false,
  disabledReason,
}: {
  mode: '3d' | '2d';
  isUploading: boolean;
  onUploadSegy: (e: React.ChangeEvent<HTMLInputElement>) => Promise<void>;
  disabled?: boolean;
  disabledReason?: string;
}) {
  const inputId = mode === '3d' ? 'segy-upload-3d' : 'segy-upload-2d';
  const importDisabled = isUploading || disabled;
  const title = 'Manually Upload SEG-Y';
  const description =
    mode === '3d'
      ? 'Fallback import for a standalone 3D SEG-Y outside the source repository workflow.'
      : 'Fallback import for a standalone 2D SEG-Y line outside the source repository workflow.';

  return (
    <div
      style={{
        border: '1px solid #333',
        background: '#1f1f1f',
        borderRadius: 8,
        padding: 12,
        marginBottom: 14,
        color: 'white',
        display: 'flex',
        justifyContent: 'space-between',
        gap: 12,
        alignItems: 'center',
      }}
    >
      <div>
        <div style={{ fontWeight: 700, fontSize: 16, color: "#f8fafc", lineHeight: 1.25 }}>{title}</div>
        <div style={{ fontSize: 12, color: "#94a3b8", marginTop: 4, lineHeight: 1.4 }}>{description}</div>
      </div>

      <label
        htmlFor={inputId}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 7,
          background: 'transparent',
          color: importDisabled ? '#71717a' : '#60a5fa',
          border: importDisabled ? '1px solid #52525b' : '1px solid #60a5fa',
          borderRadius: 6,
          padding: '7px 11px',
          cursor: importDisabled ? 'not-allowed' : 'pointer',
          whiteSpace: 'nowrap',
          fontSize: 13,
          fontWeight: 650,
          lineHeight: 1.2,
          minHeight: 34,
          opacity: importDisabled ? 0.65 : 1,
        }}
      >
        <Upload size={15} />
        {isUploading ? 'Importing...' : disabled ? 'Import SEG-Y Disabled' : 'Import SEG-Y'}
        <input
          id={inputId}
          type="file"
          accept=".sgy,.segy"
          onChange={onUploadSegy}
          disabled={importDisabled}
          style={{ display: 'none' }}
        />
      </label>
      {disabled && disabledReason && (
        <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 6 }}>
          {disabledReason}
        </div>
      )}
    </div>
  );
}

export function DataManager({
  pageMode,
  volumes,
  selectedVolume,
  selectedLoadMode = 'preview',
  activeDataTab,
  onActiveDataTabChange,
  onSelectVolume,
  onRefreshVolumes,
  onUploadSegy,
  isUploading,
  onClearSelectedVolume,
  onViewIndexedPreview,
  onOpenSourcesPage,
}: DataManagerProps) {

  const [localDataManagerTab, setLocalDataManagerTab] = useState<'3d' | '2d'>('2d');
  const dataManagerTab = activeDataTab || localDataManagerTab;

  const setDataManagerTab = (tab: '3d' | '2d') => {
    setLocalDataManagerTab(tab);
    onActiveDataTabChange?.(tab);
  };
  const [dataWorkflowTab, setDataWorkflowTab] = useState<"source-intake" | "managed">("managed");
  const activeWorkflowTab = pageMode || dataWorkflowTab;
  const [indexedDeleteHelpVolumeId, setIndexedDeleteHelpVolumeId] = useState<string | null>(null);
  const [selected2DSourceRepository, setSelected2DSourceRepository] = useState<any | null>(null);
  const [selected3DSourceRepository, setSelected3DSourceRepository] = useState<any | null>(null);

  const sourceStructureTypes3D = new Set([
    "single_3d_volume",
    "single_3d_volume_with_docs",
    "multi_version_3d_delivery",
  ]);

  const sourceStructureTypes2D = new Set([
    "single_isolated_line",
    "single_line_with_docs",
    "single_line_multi_version",
    "survey_with_line_folders",
    "survey_flat_lines",
  ]);

  const is3DSourceRepository = (repo: any): boolean =>
    Boolean(repo) &&
    (
      repo.intended_use === "3d_segy_intake" ||
      sourceStructureTypes3D.has(String(repo.source_structure_type || ""))
    );

  const is2DSourceRepository = (repo: any): boolean =>
    Boolean(repo) &&
    (
      repo.intended_use === "2d_segy_intake" ||
      sourceStructureTypes2D.has(String(repo.source_structure_type || ""))
    );

  const activeSourceRepository =
    dataManagerTab === "3d" ? selected3DSourceRepository : selected2DSourceRepository;

  const activeSourceRepositoryIsValid =
    dataManagerTab === "3d"
      ? is3DSourceRepository(activeSourceRepository)
      : is2DSourceRepository(activeSourceRepository);

  const selectedSourceRepositoryId =
    activeSourceRepositoryIsValid ? String(activeSourceRepository?.repository_id || "") : "";

  const handleBrowseSourceRepository = (repositoryId: string, repository?: any) => {
    if (!repositoryId) {
      if (dataManagerTab === "3d") {
        setSelected3DSourceRepository(null);
      } else {
        setSelected2DSourceRepository(null);
      }
      return;
    }

    const candidate = {
      ...(repository || {}),
      repository_id: repositoryId,
    };

    if (dataManagerTab === "3d") {
      setSelected3DSourceRepository(is3DSourceRepository(candidate) ? candidate : null);
    } else {
      setSelected2DSourceRepository(is2DSourceRepository(candidate) ? candidate : null);
    }
  };
  const [managedDataCollapsed, setManagedDataCollapsed] = useState(false);
  const [externalRegistryCollapsed, setExternalRegistryCollapsed] = useState(false);

  useEffect(() => {
    const handleManagedDataUpdated = () => {
      void onRefreshVolumes();
    };

    const handleSourceIntakeUpdated = () => {
      void onRefreshVolumes();
    };

    window.addEventListener('multiviewer:managed-data-updated', handleManagedDataUpdated);
    window.addEventListener('multiviewer:source-intake-updated', handleSourceIntakeUpdated);
    return () => {
      window.removeEventListener('multiviewer:managed-data-updated', handleManagedDataUpdated);
      window.removeEventListener('multiviewer:source-intake-updated', handleSourceIntakeUpdated);
    };
  }, [onRefreshVolumes]);

  const managedDataMaxWidth = '100%';
  const externalRegistryMaxWidth = '100%';

  const isManagedDisplayableDataset = (volume: any) => {
    // Managed Data must show and allow Load for hidden/unloaded datasets.
    // `hidden` only excludes a dataset from the viewer dropdown/catalog.
    if (volume.dataset_type === '3d_volume' || volume.metadata?.is_3d === true) {
      return true;
    }

    return (
      volume.dataset_type === '2d_line' ||
      volume.dataset_type === '2d_survey' ||
      volume.metadata?.is_3d === false
    );
  };

  const isSurveyChildLine = (volume: any) => {
    const metadata = volume.metadata || {};

    return (
      volume.dataset_type === '2d_line' &&
      (
        Boolean(metadata.survey_import_source) ||
        Boolean(metadata.source_relative_path) ||
        Boolean(metadata.parent_survey_id) ||
        Boolean(metadata.survey_id)
      )
    );
  };

  const visibleVolumes = volumes.filter((volume) => {
    if (dataManagerTab === '3d') {
      return volume.dataset_type === '3d_volume' || volume.metadata?.is_3d === true;
    }

    if (isSurveyChildLine(volume)) {
      return false;
    }

    return (
      volume.dataset_type === '2d_line' ||
      volume.dataset_type === '2d_survey' ||
      volume.metadata?.is_3d === false
    );
  });

  const threeDCount = volumes.filter((volume) => volume.dataset_type === '3d_volume' || volume.metadata?.is_3d === true).length;

  const twoDCount = volumes.filter((volume) =>
    !isSurveyChildLine(volume) &&
    (
      volume.dataset_type === '2d_line' ||
      volume.dataset_type === '2d_survey' ||
      volume.metadata?.is_3d === false
    )
  ).length;

  const {
    infoVolume,
    infoData,
    infoLoading,
    infoError,
    handleInfo,
    closeInfoModal,
  } = useManagedInfoModal();
  const {
    getSelectedTargets,
    setSelectedTarget,
    clearSelectedTargets,
    countSelectedTargets,
  } = useManagedDataSelection();

  const {
    loadSelectedTargets,
    handleRename,
    unloadFromViewerCatalog,
  } = useManagedVolumeActions({
    selectedVolume,
    onSelectVolume,
    onRefreshVolumes,
    onClearSelectedVolume,
    clearSelectedTargets,
    countSelectedTargets,
    getDisplayName,
  });


  const { handleDelete } = useManagedDeleteAction({
    selectedVolume,
    onRefreshVolumes,
    onClearSelectedVolume,
    getDisplayName,
  });

  const viewLoadedDataset = (volume: Volume) => {
    const isMsiManaged =
      String(volume.id || "").startsWith("msi_repr:") ||
      (volume as any).source === "msi" ||
      (volume as any).registry_source === "msi" ||
      Boolean((volume as any).msi_representation_id);

    const isLoaded = isMsiManaged ? Boolean((volume as any).is_loaded) : !volume.hidden;

    if (!isLoaded) {
      window.alert("Load this dataset before viewing it.");
      return;
    }

    if (!isManagedDisplayableDataset(volume)) {
      window.alert("This managed dataset is not displayable in the viewer.");
      return;
    }

    onSelectVolume({ ...volume, hidden: false }, { loadMode: "preview" });
  };

  const handleManagedPanelWorkflowNavigation = (tab: string) => {
    if (tab === "source-intake" && pageMode === "managed" && onOpenSourcesPage) {
      onOpenSourcesPage();
      return;
    }

    if (tab === "source-intake" || tab === "managed") {
      setDataWorkflowTab(tab);
    }
  };




  return (
    <div className="data-manager">

      {/* Data Manager Tabs */}
      <div
        style={{
          display: 'flex',
          gap: 8,
          marginBottom: 14,
          alignItems: 'center',
        }}
      >
        <button
          onClick={() => {
            setDataManagerTab('3d');
          }}
          style={{
            background: dataManagerTab === '3d' ? '#3f5f85' : '#2b2b2b',
            color: 'white',
            border: dataManagerTab === '3d' ? '1px solid #8fb8e8' : '1px solid #555',
            borderRadius: 6,
            padding: '7px 11px',
            cursor: 'pointer',
            fontWeight: dataManagerTab === '3d' ? 700 : 400,
          }}
        >
          3D Data ({threeDCount})
        </button>

        <button
          onClick={() => {
            setDataManagerTab('2d');
          }}
          style={{
            background: dataManagerTab === '2d' ? '#3f5f85' : '#2b2b2b',
            color: 'white',
            border: dataManagerTab === '2d' ? '1px solid #8fb8e8' : '1px solid #555',
            borderRadius: 6,
            padding: '7px 11px',
            cursor: 'pointer',
            fontWeight: dataManagerTab === '2d' ? 700 : 400,
          }}
        >
          2D Data ({twoDCount})
        </button>
      </div>

      <div style={{ fontSize: 12, opacity: 0.7, marginBottom: 12 }}>
        {dataManagerTab === '3d'
          ? 'Showing 3D volumes only.'
          : 'Showing 2D lines and 2D surveys.'}
      </div>

      {!pageMode && (
        <div
          style={{
            display: 'flex',
            gap: 8,
            margin: '0 0 16px 0',
            flexWrap: 'wrap',
          }}
        >
          {[
            ['source-intake', 'Source Intake'],
            ['managed', 'Managed Data'],
          ].map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => {
                const nextTab = key as 'source-intake' | 'managed';
                setDataWorkflowTab(nextTab);
                if (nextTab === 'managed') {
                  void onRefreshVolumes();
                }
              }}
              style={{
                padding: '7px 12px',
                borderRadius: 7,
                border: dataWorkflowTab === key ? '1px solid #8fb8e8' : '1px solid #555',
                background: dataWorkflowTab === key ? '#3f5f85' : '#2b2b2b',
                color: '#f8fafc',
                fontSize: 13,
                fontWeight: dataWorkflowTab === key ? 700 : 500,
                cursor: 'pointer',
              }}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {activeWorkflowTab === "source-intake" && (
        <SourceIntakeWorkflowPanel
          dataManagerTab={dataManagerTab}
          selectedSourceRepositoryId={selectedSourceRepositoryId}
          onRefreshVolumes={onRefreshVolumes}
          onBrowseRepository={handleBrowseSourceRepository}
          externalRegistryCollapsed={externalRegistryCollapsed}
          externalRegistryMaxWidth={externalRegistryMaxWidth}
          onViewIndexedPreview={onViewIndexedPreview}
        />
      )}
      {activeWorkflowTab === "managed" && (
        <>
      <div className="data-manager-header">
        <div>
          <h2>Managed Data</h2>
          <p>Manage registered datasets and viewer-ready representations.</p>
        </div>
      </div>

      <ManagedDataPanel
        visibleVolumes={visibleVolumes}
        managedDataCollapsed={managedDataCollapsed}
        setManagedDataCollapsed={setManagedDataCollapsed}
        onRefreshVolumes={onRefreshVolumes}
        managedDataMaxWidth={managedDataMaxWidth}
        selectedVolume={selectedVolume}
        selectedLoadMode={selectedLoadMode}
        getDisplayName={getDisplayName}
        isManagedDisplayableDataset={isManagedDisplayableDataset}
        getSelectedTargets={getSelectedTargets}
        setSelectedTarget={setSelectedTarget}
        clearSelectedTargets={clearSelectedTargets}
        loadSelectedTargets={loadSelectedTargets}
        viewLoadedDataset={viewLoadedDataset}
        unloadFromViewerCatalog={unloadFromViewerCatalog}
        handleInfo={handleInfo}
        handleRename={handleRename}
        handleDelete={handleDelete}
        hasAvailableOptimizedCache={hasAvailableOptimizedCache}
        getShape={getShape}
        getDatasetTypeLabel={getDatasetTypeLabel}
        indexedDeleteHelpVolumeId={indexedDeleteHelpVolumeId}
        setIndexedDeleteHelpVolumeId={setIndexedDeleteHelpVolumeId}
        setDataWorkflowTab={handleManagedPanelWorkflowNavigation}
        viewerModeFilter={dataManagerTab}
      />

        </>
      )}


      {infoVolume && (
        <VolumeInfoModal
          infoVolume={infoVolume}
          infoData={infoData}
          infoLoading={infoLoading}
          infoError={infoError}
          onClose={closeInfoModal}
          getDisplayName={getDisplayName}
          getShape={getShape}
          getGeometrySource={getGeometrySource}
        />
      )}
    </div>
  );
}
