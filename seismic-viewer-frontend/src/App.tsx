import { useState, useEffect } from 'react'
import './App.css'
import { Seismic3DViewer } from './components/Seismic3DViewer'
import { Seismic2DViewer } from './components/Seismic2DViewer'
import { Seismic2DSurveyViewer } from './components/Seismic2DSurveyViewer'
import { DataManager } from './components/DataManager'
import { VolumeInfoPanel } from './components/VolumeInfoPanel'
import { SettingsDrawer } from './components/SettingsDrawer'
import { ToolboxPanel } from './components/ToolboxPanel'
import { LayoutGrid, Box, Image as ImageIcon, Settings, Database, ChevronLeft, ChevronRight, Wrench, Upload } from 'lucide-react'
import { getBackendSliceCacheInfo, getVolumes } from './services/zarrService'; import type { Volume } from './services/zarrService'
import axios from 'axios'
import { getDatasetShape, is3DVolume, is2DLine, is2DSurvey, is2DDataset, isDisplayableDataset } from './utils/datasetTypes'

function App() {
  const getInitialDataContext = (): '3d' | '2d' => {
    try {
      const stored = window.localStorage.getItem('multiviewer:last-data-context');
      return stored === '3d' ? '3d' : '2d';
    } catch {
      return '2d';
    }
  };

  const [viewMode, setViewMode] = useState<'3d' | '2d' | 'sources' | 'data' | 'info' | 'toolbox'>('data');
  const [lastDataManagerTab, setLastDataManagerTab] = useState<'3d' | '2d'>(getInitialDataContext);
  const [volumes, setVolumes] = useState<Volume[]>([]);
  const [selectedVolume, setSelectedVolume] = useState<Volume | null>(null);
  const [selectedLoadMode, setSelectedLoadMode] = useState<'preview' | 'optimized_cache'>('preview');
  const [lastSelected2DVolumeId, setLastSelected2DVolumeId] = useState<string | null>(null);
  const [lastSelected3DVolumeId, setLastSelected3DVolumeId] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState<string>('');
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);
  const [settingsTab, setSettingsTab] = useState<'frontend' | 'backend' | 'cache' | 'jobs' | 'settings'>('frontend');
  const [diagnosticsTab, setDiagnosticsTab] = useState<'diagnostics' | 'backend' | 'frontend' | 'cache' | 'jobs' | 'settings'>('diagnostics');
  const [backendCacheInfo, setBackendCacheInfo] = useState<any>(null);
  const [diagnosticsStatus, setDiagnosticsStatus] = useState<string>('Not run yet');
  const [diagnosticsCheckedAt, setDiagnosticsCheckedAt] = useState<string>('');
  const [diagnosticsHealth, setDiagnosticsHealth] = useState<any>({
    overall: 'Not run yet',
    backendApi: 'Not run yet',
    registry: 'Not run yet',
    selectedDataset: 'Not run yet',
    backendCache: 'Not run yet',
    jobs: 'Not run yet',
    counts: {
      total: 0,
      volumes3d: 0,
      lines2d: 0,
      surveys2d: 0,
      unknown: 0,
    },
  });

  const setDataContext = (mode: '3d' | '2d') => {
    setLastDataManagerTab(mode);
    try {
      window.localStorage.setItem('multiviewer:last-data-context', mode);
    } catch {
      // Ignore persistence errors; in-memory context still works.
    }
  };

  const getViewerModeForVolume = (volume: any): '3d' | '2d' | null => {
    if (!volume) return null;

    const datasetType = String(volume.dataset_type || volume.metadata?.dataset_type || '').trim();
    const viewerMode = String(volume.viewer_mode || volume.metadata?.viewer_mode || '').trim();
    const representationType = String(volume.representation_type || volume.metadata?.representation_type || '').trim();
    const is3dFlag = volume.metadata?.is_3d;
    const shape = getDatasetShape(volume);

    // Managed Data route decisions must not depend only on shape.
    // MSI rows may carry authoritative dataset_type/viewer_mode while the
    // shape is only present in the hydrated viewer catalog row.
    if (datasetType === '2d_line' || datasetType === '2d_survey' || viewerMode === '2d' || is3dFlag === false) {
      return '2d';
    }

    if (datasetType === '3d_volume' || viewerMode === '3d' || is3dFlag === true) {
      return '3d';
    }

    if (representationType.includes('2d')) return '2d';
    if (representationType.includes('3d')) return '3d';

    if (Array.isArray(shape)) {
      if (shape.length === 2) return '2d';
      if (shape.length === 3) return '3d';
    }

    return null;
  };

  const getViewerModeOrDefault = (volume: any): '3d' | '2d' => {
    return getViewerModeForVolume(volume) || '3d';
  };


  const mergeVolumesWithManagedDocumentContext = async (rawVolumes: Volume[]): Promise<Volume[]> => {
    try {
      const response = await axios.get('/api/managed-data/loaded');
      const managedRows = Array.isArray(response.data)
        ? response.data
        : Array.isArray(response.data?.rows)
          ? response.data.rows
          : Array.isArray(response.data?.items)
            ? response.data.items
            : [];

      if (!managedRows.length) return rawVolumes;

      const managedByKey = new Map<string, any>();
      const normalizeDocMergeKey = (key: unknown) => String(key || '')
        .trim()
        .toLowerCase()
        .replace(/^.*\//, '')
        .replace(/^.*\\/, '')
        .replace(/[^a-z0-9]+/g, '');
      const addKey = (key: unknown, row: any) => {
        const value = String(key || '').trim();
        if (value) managedByKey.set(value, row);
        const normalized = normalizeDocMergeKey(value);
        if (normalized) managedByKey.set(`norm:${normalized}`, row);
      };
      const addNameKeys = (row: any) => {
        addKey(row.display_name, row);
        addKey(row.filename, row);
        addKey(row.name, row);
        addKey(row.relative_path, row);
        addKey(row.source_relative_path, row);
        addKey(row.zarr_url, row);
        addKey(row.storage_uri, row);
      };

      managedRows.forEach((row: any) => {
        addKey(row.id, row);
        addKey(row.volume_id, row);
        addKey(row.dataset_id, row);
        addKey(row.physical_volume_id, row);
        addKey(row.source_candidate_id, row);
        addKey(row.source_segy_file_id, row);
        addNameKeys(row);
      });

      return rawVolumes.map((volume: any) => {
        const keys = [
          volume.id,
          volume.volume_id,
          volume.dataset_id,
          volume.physical_volume_id,
          volume.source_candidate_id,
          volume.source_segy_file_id,
          volume.display_name,
          volume.filename,
          volume.name,
          volume.relative_path,
          volume.source_relative_path,
          volume.zarr_url,
          volume.storage_uri,
        ]
          .map((value) => String(value || '').trim())
          .filter(Boolean);

        const managed = keys
          .map((key) => managedByKey.get(key) || managedByKey.get(`norm:${normalizeDocMergeKey(key)}`))
          .find(Boolean);
        if (!managed) return volume;

        const supportingDocuments = managed.supporting_documents || managed.document_context?.supporting_documents || [];
        const documentCount = managed.document_count ?? managed.document_context?.document_count ?? supportingDocuments.length ?? 0;

        return {
          ...volume,
          source_candidate_id: volume.source_candidate_id || managed.source_candidate_id,
          source_segy_file_id: volume.source_segy_file_id || managed.source_segy_file_id,
          repository_id: volume.repository_id || managed.repository_id,
          package_id: volume.package_id || managed.package_id,
          line_id: volume.line_id || managed.line_id,
          document_count: documentCount,
          supporting_document_count: managed.supporting_document_count ?? managed.document_context?.supporting_document_count ?? documentCount,
          supporting_documents: supportingDocuments,
          document_context: managed.document_context || volume.document_context,
          metadata: {
            ...(volume.metadata || {}),
            document_count: documentCount,
            supporting_document_count: managed.supporting_document_count ?? managed.document_context?.supporting_document_count ?? documentCount,
            supporting_documents: supportingDocuments,
            document_context: managed.document_context || volume.metadata?.document_context,
          },
        };
      });
    } catch (err) {
      console.warn('Managed document context merge failed', err);
      return rawVolumes;
    }
  };

  useEffect(() => {
    refreshVolumes({ autoSelectIfNone: false, autoSelectReplacement: false });
  }, []);

  const refreshDiagnostics = async () => {
    setDiagnosticsStatus('Checking...');

    const nextHealth: any = {
      overall: 'Checking',
      backendApi: 'Checking',
      registry: 'Checking',
      selectedDataset: 'Checking',
      backendCache: 'Checking',
      jobs: isUploading ? 'Upload/conversion active' : 'Idle',
      counts: {
        total: 0,
        volumes3d: 0,
        lines2d: 0,
        surveys2d: 0,
        unknown: 0,
      },
    };

    try {
      const currentVolumes = await mergeVolumesWithManagedDocumentContext(await getVolumes());

      nextHealth.backendApi = 'OK';
      nextHealth.registry = `OK · ${currentVolumes.length} datasets`;

      nextHealth.counts = {
        total: currentVolumes.length,
        volumes3d: currentVolumes.filter(v => v.dataset_type === '3d_volume').length,
        lines2d: currentVolumes.filter(v => v.dataset_type === '2d_line').length,
        surveys2d: currentVolumes.filter(v => v.dataset_type === '2d_survey').length,
        unknown: currentVolumes.filter(v => !v.dataset_type || v.dataset_type === 'unknown').length,
      };

      if (!selectedVolume) {
        nextHealth.selectedDataset = 'None selected';
      } else {
        const exists = currentVolumes.some(v => v.id === selectedVolume.id);
        const hasZarr = Boolean(selectedVolume.zarr_url) || selectedVolume.dataset_type === '2d_survey';

        if (!exists) {
          nextHealth.selectedDataset = 'Selected dataset missing from registry';
        } else if (!hasZarr) {
          nextHealth.selectedDataset = 'Selected dataset has no Zarr URL';
        } else {
          nextHealth.selectedDataset = `OK · ${selectedVolume.dataset_type || 'unknown'}`;
        }
      }

      try {
        const cacheInfo = await getBackendSliceCacheInfo();
        setBackendCacheInfo(cacheInfo);
        nextHealth.backendCache = cacheInfo
          ? `OK · ${cacheInfo.entries} entries · ${(cacheInfo.bytes / 1048576).toFixed(1)} MB`
          : 'Unavailable';
      } catch {
        setBackendCacheInfo(null);
        nextHealth.backendCache = 'Unavailable';
      }

      const hasFailure =
        nextHealth.backendApi !== 'OK' ||
        String(nextHealth.registry).startsWith('Failed') ||
        String(nextHealth.selectedDataset).includes('missing') ||
        String(nextHealth.selectedDataset).includes('no Zarr');

      nextHealth.overall = hasFailure ? 'Partial' : 'Healthy';

      setDiagnosticsStatus(nextHealth.overall);
      setDiagnosticsHealth(nextHealth);
      setDiagnosticsCheckedAt(new Date().toLocaleTimeString());
    } catch (err) {
      console.error('Diagnostics check failed', err);

      nextHealth.overall = 'Backend unreachable';
      nextHealth.backendApi = 'Failed';
      nextHealth.registry = 'Failed';
      nextHealth.selectedDataset = selectedVolume ? 'Not checked' : 'None selected';
      nextHealth.backendCache = 'Not checked';

      setBackendCacheInfo(null);
      setDiagnosticsStatus(nextHealth.overall);
      setDiagnosticsHealth(nextHealth);
      setDiagnosticsCheckedAt(new Date().toLocaleTimeString());
    }
  };

  const refreshVolumes = async (
    options: { autoSelectIfNone?: boolean; autoSelectReplacement?: boolean } = {}
  ) => {
    const { autoSelectIfNone = false, autoSelectReplacement = false } = options;

    try {
      const v = await mergeVolumesWithManagedDocumentContext(await getVolumes());
      setVolumes(v);

      if (selectedVolume) {
        const refreshedSelected = v.find((volume: any) => (
          volume.id === selectedVolume.id ||
          volume.volume_id === (selectedVolume as any).volume_id ||
          volume.physical_volume_id === (selectedVolume as any).physical_volume_id ||
          volume.source_candidate_id === (selectedVolume as any).source_candidate_id
        ));
        if (refreshedSelected) {
          setSelectedVolume(refreshedSelected);
        }
      }
      const displayableVolumes = v.filter((volume) => {
        if (viewMode === '2d') return is2DDataset(volume);
        if (viewMode === '3d') return is3DVolume(volume);
        return isDisplayableDataset(volume);
      });

      if (displayableVolumes.length > 0 && !selectedVolume && autoSelectIfNone) {
        setSelectedVolume(displayableVolumes[0]);
      }

      if (selectedVolume && !displayableVolumes.some((volume) => volume.id === selectedVolume.id)) {
        setSelectedVolume(autoSelectReplacement ? (displayableVolumes[0] || null) : null);
      }
    } catch (e) {
      console.error("Failed to fetch volumes", e);
    }
  };

  useEffect(() => {
    const shouldReopenSettings = sessionStorage.getItem('seismicViewerReopenSettings');

    if (shouldReopenSettings === '1') {
      sessionStorage.removeItem('seismicViewerReopenSettings');
      setDiagnosticsOpen(true);
    }
  }, []);

  const isSurveyChildLineForCatalog = (volume: Volume) => {
    const metadata: any = volume.metadata || {};

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

  const isValidViewerVolumeForMode = (volume: Volume, mode: '3d' | '2d') => {
    if (volume.hidden) {
      return false;
    }

    if (isSurveyChildLineForCatalog(volume)) {
      return false;
    }

    return getViewerModeForVolume(volume) === mode;
  };

  const rememberSelectedVolumeForMode = (volume: Volume | null) => {
    if (!volume) {
      return;
    }

    const viewerMode = getViewerModeForVolume(volume);

    if (viewerMode === '2d') {
      setLastSelected2DVolumeId(volume.id);
      setDataContext('2d');
      return;
    }

    if (viewerMode === '3d') {
      setLastSelected3DVolumeId(volume.id);
      setDataContext('3d');
    }
  };

  const viewerCatalogVolumes = volumes.filter((volume) =>
    viewMode === '3d' || viewMode === '2d'
      ? isValidViewerVolumeForMode(volume, viewMode)
      : false
  );

  const isIndexedPreviewVolume = (volume: Volume | null) => {
    return Boolean(
      volume &&
      (
        (volume as any).representation_type === "indexed_preview" ||
        (volume as any).metadata?.representation_type === "indexed_preview" ||
        String((volume as any).zarr_url || "").startsWith("indexed-segy://") ||
        String((volume as any).metadata?.read_mode || "") === "indexed_segy"
      )
    );
  };


  const activeSelectedVolume = (() => {
    if (!selectedVolume) return null;

    if (isIndexedPreviewVolume(selectedVolume)) {
      return selectedVolume;
    }

    if (selectedVolume.hidden) {
      return null;
    }

    const selectedViewerMode = getViewerModeForVolume(selectedVolume);
    if (selectedViewerMode !== viewMode) {
      return null;
    }

    const sameManagedViewerIdentity = (candidate: any) => {
      const selectedKeys = [
        (selectedVolume as any).id,
        (selectedVolume as any).volume_id,
        (selectedVolume as any).msi_representation_id,
        (selectedVolume as any).physical_volume_id,
      ]
        .map((value) => String(value || '').trim())
        .filter(Boolean);

      const candidateKeys = [
        candidate?.id,
        candidate?.volume_id,
        candidate?.msi_representation_id,
        candidate?.physical_volume_id,
      ]
        .map((value) => String(value || '').trim())
        .filter(Boolean);

      return candidateKeys.some((key) => selectedKeys.includes(key));
    };

    if (viewerCatalogVolumes.some((volume) => sameManagedViewerIdentity(volume))) {
      return selectedVolume;
    }

    // A Managed Data eye click can hand App a freshly loaded MSI row before
    // the viewer catalog refresh has reconciled the same row as visible.
    // Allow the selected row to render if it has a valid viewer mode and path.
    if ((selectedVolume as any).is_loaded || Boolean(selectedVolume.zarr_url) || selectedViewerMode === '2d') {
      return selectedVolume;
    }

    return null;
  })();

  const activeZarrPath =
    activeSelectedVolume &&
    selectedLoadMode === 'optimized_cache' &&
    activeSelectedVolume.optimized_cache?.status === 'available' &&
    activeSelectedVolume.optimized_cache?.validated === true &&
    activeSelectedVolume.optimized_cache?.zarr_url
      ? activeSelectedVolume.optimized_cache.zarr_url
      : activeSelectedVolume?.zarr_url;

  const activeViewerDatasetIndex = activeSelectedVolume
    ? viewerCatalogVolumes.findIndex((volume) => volume.id === activeSelectedVolume.id)
    : -1;

  const canPageViewerDataset = viewMode === '2d' || viewMode === '3d';
  const canSelectPreviousDataset = canPageViewerDataset && activeViewerDatasetIndex > 0;
  const canSelectNextDataset =
    canPageViewerDataset &&
    activeViewerDatasetIndex >= 0 &&
    activeViewerDatasetIndex < viewerCatalogVolumes.length - 1;

  const selectViewerDatasetAtIndex = (index: number) => {
    if (!canPageViewerDataset || index < 0 || index >= viewerCatalogVolumes.length) {
      return;
    }

    const volume = viewerCatalogVolumes[index];
    setSelectedVolume(volume);
    setSelectedLoadMode('preview');
    rememberSelectedVolumeForMode(volume);
    setViewMode(getViewerModeOrDefault(volume));
  };

  const selectPreviousViewerDataset = () => {
    selectViewerDatasetAtIndex(activeViewerDatasetIndex - 1);
  };

  const selectNextViewerDataset = () => {
    selectViewerDatasetAtIndex(activeViewerDatasetIndex + 1);
  };

  const openIndexedPreviewVolume = (viewerSource: any) => {
    const datasetId = String(viewerSource?.dataset_id || "").trim();
    if (!datasetId) {
      window.alert("Indexed preview viewer source is missing dataset_id.");
      return;
    }

    const indexedPreviewVolume: Volume = {
      id: `indexed-preview:${datasetId}`,
      filename: viewerSource.display_name || `Indexed Preview ${datasetId}`,
      display_name: viewerSource.display_name || `Indexed Preview ${datasetId}`,
      dataset_type: "3d_volume",
      viewer_mode: "3d",
      representation_type: "indexed_preview",
      zarr_url: `indexed-segy://${datasetId}`,
      hidden: false,
      metadata: {
        ...(viewerSource || {}),
        is_3d: true,
        read_mode: "indexed_segy",
        geometry_source: viewerSource.geometry_source || "indexed_segy_headers",
        shape: viewerSource.shape,
        zarr: {
          shape: viewerSource.shape,
          dtype: viewerSource.data_type || "float32",
          axis_order: viewerSource.axis_order || ["inline", "crossline", "sample"],
          is_3d: true,
          read_mode: "indexed_segy",
          geometry_source: viewerSource.geometry_source || "indexed_segy_headers",
        },
      },
    } as Volume;

    setSelectedVolume(indexedPreviewVolume);
    setSelectedLoadMode("preview");
    setDataContext("3d");
    setViewMode("3d");
  };

  const openDataManager = () => {
    setViewMode('data');

    setSelectedVolume((current) => {
      if (isIndexedPreviewVolume(current)) {
        return null;
      }
      return current;
    });

    setSelectedLoadMode('preview');
  };

  const switchViewerMode = (mode: '3d' | '2d') => {
    const candidates = volumes.filter((volume) => isValidViewerVolumeForMode(volume, mode));
    const rememberedId = mode === '2d' ? lastSelected2DVolumeId : lastSelected3DVolumeId;
    const rememberedVolume = rememberedId
      ? candidates.find((volume) => volume.id === rememberedId)
      : null;

    setDataContext(mode);
    setViewMode(mode);

    setSelectedVolume((current) => {
      if (current && isValidViewerVolumeForMode(current, mode)) {
        rememberSelectedVolumeForMode(current);
        return current;
      }

      return rememberedVolume || null;
    });
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;

    const file = e.target.files[0];
    const formData = new FormData();
    formData.append('file', file);

    const selectedVolumeBeforeUpload = selectedVolume;

    setIsUploading(true);
    setUploadMessage('Uploading SEG-Y file...');

    try {
      const uploadResponse = await axios.post('/api/upload', formData);
      const jobId = uploadResponse.data.job_id;

      if (!jobId) {
        throw new Error('Upload response did not include a job_id.');
      }

      setUploadMessage('SEG-Y upload accepted. Conversion queued.');

      const pollIntervalMs = 1000;
      const maxPolls = 600; // 10 minutes at 1 second intervals
      let pollCount = 0;

      await new Promise<void>((resolve, reject) => {
        const interval = window.setInterval(async () => {
          pollCount += 1;

          try {
            const jobResponse = await axios.get(`/api/jobs/${jobId}`);
            const job = jobResponse.data;

            setUploadMessage(job.message || `Job status: ${job.status}`);

            if (job.status === 'complete') {
              window.clearInterval(interval);

              // Fetch the updated registry directly without triggering refreshVolumes auto-selection.
              // Upload should add the volume to Data Manager/dropdown, but not open it.
              const updatedVolumes = await mergeVolumesWithManagedDocumentContext(await getVolumes());
              setVolumes(updatedVolumes);

              // Do not auto-load anything after upload.
              // The Data Manager "Load" button is the explicit open action.
              setSelectedVolume(null);
              setViewMode('data');

              resolve();
              return;
            }

            if (job.status === 'failed') {
              window.clearInterval(interval);
              reject(new Error(job.error || 'SEG-Y conversion failed.'));
              return;
            }

            if (pollCount >= maxPolls) {
              window.clearInterval(interval);
              reject(new Error('SEG-Y conversion timed out while waiting for job completion.'));
            }
          } catch (err) {
            window.clearInterval(interval);
            reject(err);
          }
        }, pollIntervalMs);
      });
    } catch (e) {
      console.error("Upload/conversion failed", e);
      const message = e instanceof Error ? e.message : "Upload failed. Check console for details.";
      alert(message);
    } finally {
      setIsUploading(false);
      setUploadMessage('');
      e.target.value = '';
    }
  };


  const renderViewerArea = () => {
    if (viewMode === 'sources' || viewMode === 'data') {
      return (
        <DataManager
          pageMode={viewMode === 'sources' ? 'source-intake' : 'managed'}
          volumes={volumes}
          selectedVolume={selectedVolume}
          selectedLoadMode={selectedLoadMode}
          activeDataTab={lastDataManagerTab}
          onActiveDataTabChange={setDataContext}
          onSelectVolume={(volume, options) => {
            if (volume.hidden) {
              setSelectedVolume((current) => current?.id === volume.id ? null : current);
              setSelectedLoadMode('preview');
              return;
            }

            const nextLoadMode = options?.loadMode || 'preview';

            // Managed Data viewer handoff repair:
            // The eye action may pass a loaded MSI row while the parent viewer
            // catalog still contains the same representation as hidden/unloaded.
            // Reconcile the selected row locally for immediate render; backend
            // load state remains authoritative.
            const viewerVolume = {
              ...volume,
              hidden: false,
              is_loaded: (volume as any).is_loaded ?? true,
              loaded_from_msi:
                (volume as any).loaded_from_msi ??
                Boolean((volume as any).msi_representation_id),
            } as Volume;

            setVolumes((currentVolumes) => {
              let matched = false;

              const selectedKeys = [
                (viewerVolume as any).id,
                (viewerVolume as any).volume_id,
                (viewerVolume as any).msi_representation_id,
                (viewerVolume as any).physical_volume_id,
              ]
                .map((value) => String(value || '').trim())
                .filter(Boolean);

              const reconciled = currentVolumes.map((candidate) => {
                const candidateKeys = [
                  (candidate as any).id,
                  (candidate as any).volume_id,
                  (candidate as any).msi_representation_id,
                  (candidate as any).physical_volume_id,
                ]
                  .map((value) => String(value || '').trim())
                  .filter(Boolean);

                const sameIdentity = candidateKeys.some((key) => selectedKeys.includes(key));
                if (!sameIdentity) return candidate;

                matched = true;
                return {
                  ...candidate,
                  ...viewerVolume,
                  hidden: false,
                  metadata: {
                    ...((candidate as any).metadata || {}),
                    ...((viewerVolume as any).metadata || {}),
                  },
                };
              });

              return matched ? reconciled : [...currentVolumes, viewerVolume];
            });

            setSelectedVolume(viewerVolume);
            setSelectedLoadMode(nextLoadMode);
            rememberSelectedVolumeForMode(viewerVolume);
            setViewMode(getViewerModeOrDefault(viewerVolume));
          }}
          onRefreshVolumes={() => refreshVolumes({ autoSelectIfNone: false, autoSelectReplacement: false })}
          onUploadSegy={handleUpload}
          isUploading={isUploading}
          onClearSelectedVolume={() => {
            setSelectedVolume(null);
            setSelectedLoadMode('preview');
            setViewMode('data');
          }}
          onViewIndexedPreview={openIndexedPreviewVolume}
          onOpenSourcesPage={() => setViewMode('sources')}
        />
      );
    }

    if (viewMode === 'toolbox') {
      return <ToolboxPanel />;
    }

    if (viewMode === 'info') {
      return <VolumeInfoPanel volume={selectedVolume} />;
    }

    if (!activeSelectedVolume) {
      return (
        <div className="no-data">
          {isUploading ? (uploadMessage || 'Processing SEG-Y...') : 'No volumes found. Please upload a SEG-Y file.'}
        </div>
      );
    }

    if (viewMode === '3d' && getViewerModeForVolume(activeSelectedVolume) === '3d') {
      return (
        <Seismic3DViewer
          zarrPath={activeZarrPath || activeSelectedVolume.zarr_url}
          volume={activeSelectedVolume}
          key={`3d-${activeSelectedVolume.id}`}
        />
      );
    }

    if (viewMode === '2d' && getViewerModeForVolume(activeSelectedVolume) === '2d' && !is2DSurvey(activeSelectedVolume)) {
      return (
        <Seismic2DViewer
          zarrPath={activeZarrPath || activeSelectedVolume.zarr_url}
          dim={0}
          lineInfo={activeSelectedVolume}
          defaultShowLineInfo={true}
          key={`2d-${activeSelectedVolume.id}`}
        />
      );
    }

    if (viewMode === '2d' && is2DSurvey(activeSelectedVolume)) {
      return (
        <Seismic2DSurveyViewer
          surveyId={activeSelectedVolume.id}
          surveyName={activeSelectedVolume.display_name || activeSelectedVolume.filename}
          key={`survey-${activeSelectedVolume.id}`}
        />
      );
    }

    if (viewMode === '3d') {
      return <div className="no-data">No 3D dataset selected. Choose a 3D volume from the dropdown or Data Manager.</div>;
    }

    if (viewMode === '2d') {
      return <div className="no-data">No 2D dataset selected. Choose a 2D line or survey from the dropdown or Data Manager.</div>;
    }

    return <div className="no-data">Selected dataset type is not supported by this viewer.</div>;
  };


  return (
    <div className="app-container">
      <nav className="sidebar">
        <div className="logo">Seismic Viewer</div>
        <button 
          className={viewMode === '3d' ? 'active' : ''} 
          onClick={() => switchViewerMode('3d')}
          title="3D View"
        >
          <Box size={24} />
          <span>3D View</span>
        </button>
        <button 
          className={viewMode === '2d' ? 'active' : ''} 
          onClick={() => switchViewerMode('2d')}
          title="2D View"
        >
          <ImageIcon size={24} />
          <span>2D View</span>
        </button>


        <button 
          className={viewMode === 'data' ? 'active' : ''} 
          onClick={openDataManager}
          title="Data"
        >
          <Database size={24} />
          <span>Data</span>
        </button>

        <button 
          className={viewMode === 'info' ? 'active' : ''} 
          onClick={() => setViewMode('info')}
          title="Selected Volume Info"
        >
          <LayoutGrid size={24} />
          <span>Info</span>
        </button>
        
        <div className="spacer"></div>
        

        <button
          className={viewMode === 'sources' ? 'active' : ''}
          onClick={() => setViewMode('sources')}
          title="Sources"
        >
          <Upload size={24} />
          <span>Sources</span>
        </button>

        <button
          className={viewMode === 'toolbox' ? 'active' : ''}
          onClick={() => setViewMode('toolbox')}
          title="Toolbox"
        >
          <Wrench size={24} />
          <span>Toolbox</span>
        </button>

        <button
          className={diagnosticsOpen ? 'active' : ''}
          title="Settings"
          onClick={() => setDiagnosticsOpen(true)}
        >
          <Settings size={24} />
          <span>Settings</span>
        </button>
      </nav>

      <SettingsDrawer
        open={diagnosticsOpen}
        onClose={() => setDiagnosticsOpen(false)}
        viewMode={viewMode}
        selectedVolume={selectedVolume}
        volumes={volumes}
        isUploading={isUploading}
        uploadMessage={uploadMessage}
      />

      <main className="content">
        <header className="top-bar">
          <div className="title">
            {viewMode === '3d' ? '3D Cube Visualization' : viewMode === '2d' ? '2D Section Viewer' : viewMode === 'sources' ? 'Sources' : viewMode === 'data' ? 'Data' : viewMode === 'toolbox' ? 'Toolbox' : 'Volume Information'}
          </div>
          
          {viewMode !== 'sources' && viewMode !== 'data' && viewMode !== 'toolbox' && (
          <div className="controls">
            <Database size={16} />
            <button
              type="button"
              className="dataset-nav-button"
              onClick={selectPreviousViewerDataset}
              disabled={!canSelectPreviousDataset}
              title="Previous loaded dataset"
              aria-label="Previous loaded dataset"
            >
              <ChevronLeft size={16} />
            </button>
            <button
              type="button"
              className="dataset-nav-button"
              onClick={selectNextViewerDataset}
              disabled={!canSelectNextDataset}
              title="Next loaded dataset"
              aria-label="Next loaded dataset"
            >
              <ChevronRight size={16} />
            </button>
            <select
              value={activeSelectedVolume?.id || ''}
              onChange={(e) => {
                const vol = viewerCatalogVolumes.find(v => v.id === e.target.value);

                if (vol) {
                  setSelectedVolume(vol);
                  rememberSelectedVolumeForMode(vol);
                  setViewMode(getViewerModeOrDefault(vol));
                }
              }}
              className="volume-select"
            >
              <option value="" disabled>Select Data</option>
              {viewerCatalogVolumes.map((v) => (
                <option key={v.id} value={v.id}>{v.display_name || v.filename}</option>
              ))}
            </select>
          </div>
          )}

        </header>

        {isUploading && (
          <div className="upload-status-bar">
            <span className="upload-status-dot"></span>
            <span>{uploadMessage || 'Processing SEG-Y...'}</span>
          </div>
        )}

        <div className="viewer-area">
          {renderViewerArea()}
        </div>
      </main>
    </div>
  )
}

export default App
