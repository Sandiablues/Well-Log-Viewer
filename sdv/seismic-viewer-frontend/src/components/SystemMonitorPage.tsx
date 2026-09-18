import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'

type MonitorPayload = {
  backend?: {
    status?: string
    timestamp?: string
    data_dir?: string
    zarr_dir?: string
    zarr_tmp_dir?: string
    zarr_tmp_size_bytes?: number
    zarr_tmp_file_count?: number
  }
  conversion_jobs?: Array<{
    job_id?: string
    filename?: string
    status?: string
    message?: string
    progress?: number | null
    input_path?: string
    output_path?: string
    temp_output_path?: string
    temp_exists?: boolean
    temp_size_bytes?: number
    temp_file_count?: number
    seconds_since_last_write?: number | null
    health?: string
    health_reason?: string
    error?: string | null
  }>
  repositories?: Array<{
    repository_id?: string
    name?: string
    status?: string
    last_scanned_at?: string
    package_count?: number
    line_count?: number
    segy_file_count?: number
    document_count?: number
  }>
  warnings?: Array<{
    level?: string
    type?: string
    message?: string
    volume_id?: string
    filename?: string
    sidecar?: string
    sample_interval_us?: number
  }>
}

type Snapshot = {
  size?: number
  files?: number
}

function bytes(value?: number, signed = false): string {
  if (value === undefined || value === null || Number.isNaN(value)) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let n = value
  let i = 0

  while (Math.abs(n) >= 1024 && i < units.length - 1) {
    n /= 1024
    i += 1
  }

  const prefix = signed && value > 0 ? '+' : ''
  return `${prefix}${n.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

function isActive(job: NonNullable<MonitorPayload['conversion_jobs']>[number]) {
  const status = (job.status || '').toLowerCase()
  const health = (job.health || '').toLowerCase()

  return ['queued', 'running', 'converting', 'processing'].includes(status) ||
    ['running', 'possibly_stalled'].includes(health)
}

function badge(value?: string): React.CSSProperties {
  const base: React.CSSProperties = {
    display: 'inline-block',
    padding: '1px 5px',
    borderRadius: 999,
    fontSize: 9,
    fontWeight: 700,
    border: '1px solid #d1d5db',
    whiteSpace: 'nowrap',
  }

  switch ((value || '').toLowerCase()) {
    case 'online':
    case 'running':
    case 'available':
      return { ...base, background: '#dcfce7', color: '#14532d', borderColor: '#86efac' }
    case 'possibly_stalled':
    case 'warning':
    case 'queued':
      return { ...base, background: '#fef3c7', color: '#713f12', borderColor: '#facc15' }
    case 'failed':
    case 'error':
      return { ...base, background: '#fee2e2', color: '#7f1d1d', borderColor: '#fca5a5' }
    case 'complete':
    case 'completed':
    case 'converted':
    case 'ready':
      return { ...base, background: '#dbeafe', color: '#1e3a8a', borderColor: '#93c5fd' }
    default:
      return { ...base, background: '#f3f4f6', color: '#374151' }
  }
}

function kv(label: string, value: React.ReactNode) {
  return (
    <div style={kvRow}>
      <div className="mv-system-monitor__kv-label">{label}</div>
      <div className="mv-system-monitor__kv-value">{value || '—'}</div>
    </div>
  )
}

export default function SystemMonitorPage() {
  const [payload, setPayload] = useState<MonitorPayload | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [lastRefresh, setLastRefresh] = useState('—')
  const [deltas, setDeltas] = useState<Record<string, { size?: number; files?: number }>>({})
  const previous = useRef<Record<string, Snapshot>>({})

  const refresh = useCallback(async () => {
    try {
      const res = await fetch('/api/system/monitor', { cache: 'no-store' })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)

      const data = (await res.json()) as MonitorPayload
      const nextDeltas: Record<string, { size?: number; files?: number }> = {}
      const nextSnapshots: Record<string, Snapshot> = {}

      for (const job of data.conversion_jobs || []) {
        if (!job.job_id) continue

        const prev = previous.current[job.job_id]
        const current = {
          size: job.temp_size_bytes,
          files: job.temp_file_count,
        }

        if (prev) {
          nextDeltas[job.job_id] = {
            size: prev.size !== undefined && current.size !== undefined ? current.size - prev.size : undefined,
            files: prev.files !== undefined && current.files !== undefined ? current.files - prev.files : undefined,
          }
        }

        nextSnapshots[job.job_id] = current
      }

      previous.current = { ...previous.current, ...nextSnapshots }
      setDeltas(nextDeltas)
      setPayload(data)
      setError(null)
      setLastRefresh(new Date().toLocaleTimeString())
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setLastRefresh(new Date().toLocaleTimeString())
    }
  }, [])

  useEffect(() => {
    refresh()
    const timer = window.setInterval(refresh, 5000)
    return () => window.clearInterval(timer)
  }, [refresh])

  const jobs = useMemo(() => {
    return [...(payload?.conversion_jobs || [])].sort((a, b) => Number(isActive(b)) - Number(isActive(a)))
  }, [payload])

  return (
    <div className="mv-system-monitor" style={page}>
      <header className="mv-system-monitor__header" style={header}>
        <div>
          <div className="mv-type-page-title">System Monitor</div>
          <div className="mv-type-meta">Live backend, conversion jobs, repositories, and warnings · refreshes every 5 seconds</div>
        </div>

        <div style={{ display: 'flex', gap: 5 }}>
          <button onClick={refresh} className="mv-button mv-button--compact mv-button--secondary" style={button}>Refresh</button>
          <button onClick={() => navigator.clipboard.writeText(JSON.stringify(payload || { error }, null, 2))} className="mv-button mv-button--compact mv-button--secondary" style={button}>Copy</button>
          <button onClick={() => window.close()} className="mv-button mv-button--compact mv-button--secondary" style={button}>Close</button>
        </div>
      </header>

      <section style={topGrid}>
        <div className="mv-system-monitor__card" style={card}>
          <div className="mv-system-monitor__title">Backend</div>
          {kv('Status', <span style={badge(error ? 'error' : payload?.backend?.status)}>{error ? 'error' : payload?.backend?.status || 'unknown'}</span>)}
          {kv('Refresh', lastRefresh)}
          {kv('Timestamp', payload?.backend?.timestamp)}
          {kv('Tmp size', bytes(payload?.backend?.zarr_tmp_size_bytes))}
          {kv('Tmp files', payload?.backend?.zarr_tmp_file_count)}
          {error && kv('Error', <span style={{ color: '#b91c1c' }}>{error}</span>)}
        </div>

        <div className="mv-system-monitor__card" style={card}>
          <div className="mv-system-monitor__title">Repositories</div>
          {(payload?.repositories || []).length === 0 && <div className="mv-system-monitor__muted">No repositories loaded.</div>}
          {(payload?.repositories || []).map((repo) => (
            <div key={repo.repository_id || repo.name} className="mv-system-monitor__mini-card" style={miniCard}>
              <div style={compactHeader}>
                <strong>{repo.name || repo.repository_id || 'Repository'}</strong>
                <span style={badge(repo.status)}>{repo.status || 'unknown'}</span>
              </div>
              <div className="mv-system-monitor__counts" style={repoCounts}>
                <span>Pkg {repo.package_count ?? '—'}</span>
                <span>Lines {repo.line_count ?? '—'}</span>
                <span>SEG-Y {repo.segy_file_count ?? '—'}</span>
                <span>Docs {repo.document_count ?? '—'}</span>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="mv-system-monitor__card" style={card}>
        <div className="mv-system-monitor__title">Conversions</div>
        {jobs.length === 0 && <div className="mv-system-monitor__muted">No conversion jobs found.</div>}

        {jobs.slice(0, 18).map((job) => {
          const delta = job.job_id ? deltas[job.job_id] : undefined
          const active = isActive(job)

          return (
            <div className="mv-system-monitor__job-card" key={job.job_id || job.filename} style={{ ...jobCard, borderColor: active ? '#16a34a' : '#d1d5db' }}>
              <div style={compactHeader}>
                <div className="mv-system-monitor__job-name">{job.filename || 'Unnamed job'}</div>
                <span style={badge(job.health || job.status)}>{job.health || job.status || 'unknown'}</span>
              </div>

              <div style={jobGrid}>
                {kv('Status', job.status)}
                {kv('Message', job.message)}
                {kv('Tmp size', bytes(job.temp_size_bytes))}
                {kv('Tmp files', job.temp_file_count)}
                {kv('Last write', job.seconds_since_last_write === undefined || job.seconds_since_last_write === null ? '—' : `${job.seconds_since_last_write}s`)}
                {kv('Growth', `${delta?.size === undefined ? '—' : bytes(delta.size, true)} / ${delta?.files === undefined ? '—' : `${delta.files >= 0 ? '+' : ''}${delta.files} files`}`)}
              </div>

              {job.error && <div style={errorText}>{job.error}</div>}

              <details style={{ marginTop: 3 }}>
                <summary className="mv-system-monitor__summary">Paths</summary>
                {kv('Input', job.input_path)}
                {kv('Output', job.output_path)}
                {kv('Tmp', job.temp_output_path)}
              </details>
            </div>
          )
        })}
      </section>

      <section className="mv-system-monitor__card" style={card}>
        <div className="mv-system-monitor__title">Warnings</div>
        {(payload?.warnings || []).length === 0 && <div className="mv-system-monitor__muted">No warnings reported.</div>}
        {(payload?.warnings || []).slice(0, 80).map((warning, index) => (
          <div key={`${warning.type}-${warning.volume_id}-${index}`} className="mv-system-monitor__mini-card" style={miniCard}>
            <div style={compactHeader}>
              <strong>{warning.type || 'warning'}</strong>
              <span style={badge(warning.level)}>{warning.level || 'warning'}</span>
            </div>
            <div style={{ fontSize: 9, marginTop: 2 }}>{warning.message || '—'}</div>
            <div className="mv-system-monitor__path">{warning.filename || warning.volume_id || warning.sidecar || ''}</div>
          </div>
        ))}
      </section>
    </div>
  )
}

const page: React.CSSProperties = {
  minHeight: '100vh',
  padding: 8,
  boxSizing: 'border-box',
}

const header: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  gap: 6,
  alignItems: 'center',
  marginBottom: 6,
  paddingBottom: 6,
}

const topGrid: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
  gap: 6,
  marginBottom: 6,
}

const card: React.CSSProperties = {
  padding: 6,
  marginBottom: 6,
}

const miniCard: React.CSSProperties = {
  padding: 5,
  marginTop: 4,
}

const jobCard: React.CSSProperties = {
  padding: 5,
  marginTop: 4,
}

const compactHeader: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  gap: 6,
  alignItems: 'flex-start',
}

const jobName: React.CSSProperties = {
  wordBreak: 'break-word',
}

const jobGrid: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))',
  gap: '0 6px',
  marginTop: 3,
}

const kvRow: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '62px 1fr',
  gap: 4,
  marginBottom: 1,
}

const kvLabel: React.CSSProperties = {
}

const kvValue: React.CSSProperties = {
  wordBreak: 'break-word',
}

const repoCounts: React.CSSProperties = {
  display: 'flex',
  gap: 6,
  flexWrap: 'wrap',
  marginTop: 2,
}

const title: React.CSSProperties = {
  marginBottom: 4,
}

const muted: React.CSSProperties = {
}

const button: React.CSSProperties = {
  padding: '3px 6px',
  cursor: 'pointer',
}

const summary: React.CSSProperties = {
  cursor: 'pointer',
}

const errorText: React.CSSProperties = {
  color: '#b91c1c',
  fontSize: 9,
  marginTop: 2,
}

const smallPath: React.CSSProperties = {
  marginTop: 2,
  wordBreak: 'break-word',
}
