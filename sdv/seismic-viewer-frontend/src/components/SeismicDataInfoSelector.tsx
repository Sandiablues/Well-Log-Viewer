import { useEffect, useMemo, useRef, useState } from 'react';
import type { Volume } from '../services/zarrService';
import {
  querySeismicDataInformationCatalog,
  type SeismicDataInfoViewerMode,
} from '../services/seismicDataInfoService';
import './SeismicDataInfoSelector.css';

type SeismicDataInfoSelectorProps = {
  selectedVolume: Volume | null;
  onSelect: (volume: Volume) => void;
};

const PAGE_SIZE = 50;

function viewerMode(volume: Volume | null): SeismicDataInfoViewerMode | null {
  if (!volume) return null;
  const mode = String(volume.viewer_mode || volume.metadata?.representation?.viewer_mode || '').trim();
  if (mode === '2d' || volume.dataset_type === '2d_line' || volume.dataset_type === '2d_survey') return '2d';
  if (mode === '3d' || volume.dataset_type === '3d_volume') return '3d';
  return null;
}

function displayName(volume: Volume): string {
  return String(volume.display_name || volume.filename || volume.id || '').trim();
}

function secondaryLabel(volume: Volume): string {
  const survey = String((volume as any).survey_name || volume.metadata?.survey_name || '').trim();
  const identity = String((volume as any).line_name || (volume as any).volume_name || '').trim();
  const status = (volume as any).is_loaded ? 'Loaded' : 'Managed';
  return [survey, identity && identity !== displayName(volume) ? identity : '', status].filter(Boolean).join(' · ');
}

export function SeismicDataInfoSelector({ selectedVolume, onSelect }: SeismicDataInfoSelectorProps) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<SeismicDataInfoViewerMode>(() => viewerMode(selectedVolume) || '3d');
  const [searchText, setSearchText] = useState('');
  const [rows, setRows] = useState<Volume[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const selectedMode = viewerMode(selectedVolume);
    if (selectedMode) setMode(selectedMode);
  }, [selectedVolume?.id]);

  useEffect(() => {
    setOffset(0);
  }, [mode, searchText]);

  useEffect(() => {
    if (!open) return;

    let cancelled = false;
    const timer = window.setTimeout(async () => {
      setLoading(true);
      setError('');
      try {
        const page = await querySeismicDataInformationCatalog(searchText, mode, PAGE_SIZE, offset);
        if (cancelled) return;
        setRows(page.rows);
        setTotalCount(page.totalCount);
        setHasMore(page.hasMore);
      } catch (err) {
        console.error('Failed to query Seismic Data Information catalog', err);
        if (!cancelled) {
          setRows([]);
          setTotalCount(0);
          setHasMore(false);
          setError('Managed Data search unavailable');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 180);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [open, searchText, mode, offset]);

  useEffect(() => {
    if (!open) return;
    const handlePointerDown = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, [open]);

  const selectedLabel = useMemo(
    () => selectedVolume ? `${viewerMode(selectedVolume)?.toUpperCase() || ''} · ${displayName(selectedVolume)}` : 'Select Data',
    [selectedVolume],
  );

  const firstResult = totalCount === 0 || rows.length === 0 ? 0 : offset + 1;
  const lastResult = totalCount === 0 || rows.length === 0 ? 0 : offset + rows.length;

  return (
    <div className="sdv-info-selector" ref={rootRef}>
      <button
        type="button"
        className="volume-select sdv-info-selector-trigger"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="dialog"
        aria-expanded={open}
        title="Select any viewer-ready 2D or 3D dataset from Managed Data"
      >
        <span className="sdv-info-selector-trigger-text">{selectedLabel}</span>
        <span aria-hidden="true">▾</span>
      </button>

      {open && (
        <div className="sdv-info-selector-popover" role="dialog" aria-label="Select seismic data from Managed Data">
          <div className="sdv-info-selector-mode" role="group" aria-label="Seismic data type">
            <button
              type="button"
              className={mode === '2d' ? 'active' : ''}
              onClick={() => setMode('2d')}
              aria-pressed={mode === '2d'}
            >
              2D
            </button>
            <button
              type="button"
              className={mode === '3d' ? 'active' : ''}
              onClick={() => setMode('3d')}
              aria-pressed={mode === '3d'}
            >
              3D
            </button>
          </div>

          <input
            type="search"
            value={searchText}
            onChange={(event) => setSearchText(event.currentTarget.value)}
            className="sdv-info-selector-search"
            placeholder={mode === '2d' ? 'Search 2D line, survey, or dataset…' : 'Search 3D volume, survey, or dataset…'}
            aria-label={mode === '2d' ? 'Search 2D Managed Data' : 'Search 3D Managed Data'}
            autoFocus
          />

          <div className="sdv-info-selector-summary">
            <span>{loading ? 'Searching…' : `${totalCount.toLocaleString()} ${mode.toUpperCase()} dataset${totalCount === 1 ? '' : 's'}`}</span>
            {!loading && totalCount > 0 && <span>{firstResult}–{lastResult}</span>}
          </div>

          <div className="sdv-info-selector-results" role="listbox">
            {error && <div className="sdv-info-selector-message error">{error}</div>}
            {!error && !loading && rows.length === 0 && (
              <div className="sdv-info-selector-message">No matching {mode.toUpperCase()} datasets.</div>
            )}
            {rows.map((volume) => {
              const isSelected = selectedVolume?.id === volume.id;
              return (
                <button
                  key={volume.id}
                  type="button"
                  className={`sdv-info-selector-result${isSelected ? ' selected' : ''}`}
                  onClick={() => {
                    onSelect(volume);
                    setOpen(false);
                  }}
                  role="option"
                  aria-selected={isSelected}
                  title={String((volume as any).msi_representation_id || volume.id)}
                >
                  <span className="sdv-info-selector-result-name">{displayName(volume)}</span>
                  <span className="sdv-info-selector-result-meta">{secondaryLabel(volume)}</span>
                </button>
              );
            })}
          </div>

          <div className="sdv-info-selector-pagination">
            <button
              type="button"
              onClick={() => setOffset((value) => Math.max(0, value - PAGE_SIZE))}
              disabled={offset <= 0 || loading}
            >
              Previous
            </button>
            <button
              type="button"
              onClick={() => setOffset((value) => value + PAGE_SIZE)}
              disabled={!hasMore || loading}
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
