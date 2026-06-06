import React, { useEffect, useMemo, useState } from 'react';
import { get2DSurveyLines } from '../services/zarrService';
import { Seismic2DViewer } from './Seismic2DViewer';

interface Seismic2DSurveyViewerProps {
  surveyId: string;
  surveyName?: string;
}

function formatValue(value: any): string {
  if (value === null || value === undefined || value === '') return '—';
  if (Array.isArray(value)) return value.join(' × ');
  return String(value);
}

function InfoRow({ label, value }: { label: string; value: any }) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '92px 1fr',
        gap: '8px',
        fontSize: '12px',
        padding: '5px 0',
        borderBottom: '1px solid #303030',
      }}
    >
      <div style={{ opacity: 0.65 }}>{label}</div>
      <div style={{ wordBreak: 'break-word' }}>{formatValue(value)}</div>
    </div>
  );
}

export function Seismic2DSurveyViewer({ surveyId, surveyName }: Seismic2DSurveyViewerProps) {
  const [lines, setLines] = useState<any[]>([]);
  const [selectedLineId, setSelectedLineId] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showSurveyInfo, setShowSurveyInfo] = useState(true);
  const [showLineInfo, setShowLineInfo] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function loadLines() {
      setLoading(true);
      setError('');

      try {
        const result = await get2DSurveyLines(surveyId);

        if (cancelled) return;

        setLines(result || []);
        setSelectedLineId(result?.[0]?.line_id || '');
      } catch (err) {
        console.error('Failed to load 2D survey lines', err);
        if (!cancelled) setError('Failed to load 2D survey lines.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    loadLines();

    return () => {
      cancelled = true;
    };
  }, [surveyId]);

  const selectedLine = useMemo(
    () => lines.find((line) => line.line_id === selectedLineId) || null,
    [lines, selectedLineId]
  );

  const selectedIndex = useMemo(
    () => lines.findIndex((line) => line.line_id === selectedLineId),
    [lines, selectedLineId]
  );

  const selectPreviousLine = () => {
    if (!lines.length) return;
    const nextIndex = selectedIndex <= 0 ? lines.length - 1 : selectedIndex - 1;
    setSelectedLineId(lines[nextIndex].line_id);
  };

  const selectNextLine = () => {
    if (!lines.length) return;
    const nextIndex = selectedIndex < 0 || selectedIndex >= lines.length - 1 ? 0 : selectedIndex + 1;
    setSelectedLineId(lines[nextIndex].line_id);
  };

  if (loading) return <div className="no-data">Loading 2D survey lines...</div>;
  if (error) return <div className="no-data">{error}</div>;
  if (!lines.length) return <div className="no-data">This 2D survey has no registered lines.</div>;

  const sourceFolders = Array.from(
    new Set(
      lines
        .map((line) => line.source_relative_path?.split('/')?.[0])
        .filter(Boolean)
    )
  );

  return (
    <div
      style={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        background: '#1f1f1f',
        color: 'white',
        minHeight: 0,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          padding: '10px 14px',
          borderBottom: '1px solid #333',
          flexWrap: 'wrap',
        }}
      >
        <strong>{surveyName || '2D Survey'}</strong>

        <span style={{ fontSize: '12px', opacity: 0.65 }}>
          {lines.length} lines
        </span>

        <button
          onClick={selectPreviousLine}
          style={{ background: '#333', color: 'white', border: '1px solid #555', borderRadius: '4px', padding: '5px 8px' }}
        >
          Previous
        </button>

        <button
          onClick={selectNextLine}
          style={{ background: '#333', color: 'white', border: '1px solid #555', borderRadius: '4px', padding: '5px 8px' }}
        >
          Next
        </button>

        <label style={{ fontSize: '13px', opacity: 0.85 }}>Line:</label>

        <select
          value={selectedLineId}
          onChange={(e) => setSelectedLineId(e.target.value)}
          style={{
            background: '#2b2b2b',
            color: 'white',
            border: '1px solid #555',
            padding: '6px 8px',
            borderRadius: '6px',
            minWidth: '320px',
          }}
        >
          {lines.map((line, index) => (
            <option key={line.line_id} value={line.line_id}>
              {index + 1}. {line.line_name || line.filename || line.line_id}
            </option>
          ))}
        </select>

        {selectedLine && (
          <span style={{ fontSize: '12px', opacity: 0.75 }}>
            {selectedIndex + 1}/{lines.length} · {selectedLine.shape?.[0] ?? selectedLine.trace_count ?? '—'} traces × {selectedLine.shape?.[1] ?? selectedLine.sample_count ?? '—'} samples
          </span>
        )}

        <div
          style={{
            marginLeft: 'auto',
            display: 'flex',
            alignItems: 'center',
            gap: '14px',
            fontSize: '13px',
          }}
        >
          <label style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <input
              type="checkbox"
              checked={showSurveyInfo}
              onChange={(e) => setShowSurveyInfo(e.target.checked)}
            />
            Survey info
          </label>

          <label style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <input
              type="checkbox"
              checked={showLineInfo}
              onChange={(e) => setShowLineInfo(e.target.checked)}
            />
            Line info
          </label>
        </div>
      </div>

      <div style={{ flex: 1, minHeight: 0, display: 'flex' }}>
        <div style={{ flex: 1, minWidth: 0, minHeight: 0 }}>
          {selectedLine?.zarr_url ? (
            <Seismic2DViewer
              zarrPath={selectedLine.zarr_url}
              dim={0}
              lineInfo={selectedLine}
              surveyName={surveyName || '2D Survey'}
              controlledShowLineInfo={showLineInfo}
              showLineInfoControl={false}
              key={`survey-line-${selectedLine.line_id}`}
            />
          ) : (
            <div className="no-data">Selected line has no Zarr URL.</div>
          )}
        </div>

        {showSurveyInfo && (
          <aside
            style={{
              width: '300px',
              minWidth: '300px',
              borderLeft: '1px solid #333',
              background: '#1b1b1b',
              padding: '12px',
              overflowY: 'auto',
              boxSizing: 'border-box',
            }}
          >
            <div style={{ marginBottom: '14px' }}>
              <div
                style={{
                  fontSize: '12px',
                  textTransform: 'uppercase',
                  letterSpacing: '0.06em',
                  opacity: 0.6,
                  marginBottom: '6px',
                }}
              >
                Survey Info
              </div>

              <InfoRow label="Name" value={surveyName || '2D Survey'} />
              <InfoRow label="Survey ID" value={surveyId} />
              <InfoRow label="Line Count" value={lines.length} />
              <InfoRow label="Folders" value={sourceFolders.length ? sourceFolders.join(', ') : null} />
            </div>

            <div style={{ marginBottom: '14px' }}>
              <div
                style={{
                  fontSize: '12px',
                  textTransform: 'uppercase',
                  letterSpacing: '0.06em',
                  opacity: 0.6,
                  marginBottom: '6px',
                }}
              >
                Line List
              </div>

              <div style={{ maxHeight: '420px', overflowY: 'auto', borderTop: '1px solid #303030' }}>
                {lines.map((line, index) => (
                  <button
                    key={line.line_id}
                    onClick={() => setSelectedLineId(line.line_id)}
                    style={{
                      width: '100%',
                      textAlign: 'left',
                      background: line.line_id === selectedLineId ? '#26384d' : 'transparent',
                      color: 'white',
                      border: 'none',
                      borderBottom: '1px solid #303030',
                      padding: '7px 4px',
                      cursor: 'pointer',
                      fontSize: '12px',
                    }}
                  >
                    <div>{index + 1}. {line.line_name || line.filename || line.line_id}</div>
                    <div style={{ opacity: 0.6 }}>
                      {line.shape?.[0] ?? line.trace_count ?? '—'} × {line.shape?.[1] ?? line.sample_count ?? '—'}
                    </div>
                  </button>
                ))}
              </div>
            </div>

            <div style={{ fontSize: '12px', opacity: 0.65, lineHeight: 1.4 }}>
              Full survey metadata and SEG-Y headers are available in the main Info tab.
            </div>
          </aside>
        )}
      </div>
    </div>
  );
}
