import { FormEvent, useEffect, useMemo, useState } from 'react';

type Entry = {
  id: string;
  fgdcCode: number;
  name: string;
  formalName: string;
  description: string;
  category: string;
  subcategory: string;
  aliases: string[];
  pattern: { asset: string; defaultScale: number };
  colors: { defaultBackground: string; defaultPattern: string };
  source: { standard: string; series?: string; repository?: string };
  status?: 'active' | 'deprecated';
};
type Catalogue = { version: string; description: string; entryCount: number; entries: Entry[] };
type PatternOption = { asset: string; name: string };
type RuntimeWindow = Window & { __WLV_API_BASE_URL__?: string };
type Mode = 'add' | 'edit' | null;
type FormState = {
  id: string; fgdcCode: string; name: string; formalName: string; description: string;
  category: string; subcategory: string; aliases: string; patternAsset: string;
  defaultScale: string; defaultBackground: string; defaultPattern: string;
  sourceStandard: string; sourceSeries: string; sourceRepository: string;
};

function apiBase() {
  const r = window as RuntimeWindow;
  if (r.__WLV_API_BASE_URL__) return r.__WLV_API_BASE_URL__.replace(/\/$/, '');
  const protocol = window.location.protocol || 'http:';
  const hostname = window.location.hostname || '127.0.0.1';
  const port = window.location.port;
  const backendPort = '8001';
  if (port === backendPort) return '';
  if (port === '5173' || port === '5174' || port === '5175') return `${protocol}//${hostname}:${backendPort}`;
  return `http://127.0.0.1:${backendPort}`;
}

const panel: React.CSSProperties = { background: '#181b20', border: '1px solid #363b43', borderRadius: 6, padding: 14 };
const control: React.CSSProperties = { background: '#101216', color: '#fff', border: '1px solid #454b55', borderRadius: 4, padding: '7px 9px', fontSize: 12 };
const button: React.CSSProperties = { ...control, cursor: 'pointer', padding: '6px 10px' };
const emptyForm: FormState = {
  id: 'lithology:custom-', fgdcCode: '', name: '', formalName: '', description: '',
  category: 'custom', subcategory: 'custom', aliases: '', patternAsset: '', defaultScale: '1',
  defaultBackground: '#D9D9D9', defaultPattern: '#111111', sourceStandard: 'CUSTOM',
  sourceSeries: 'custom', sourceRepository: 'MultiViewer',
};

function entryToForm(entry: Entry): FormState {
  return {
    id: entry.id, fgdcCode: String(entry.fgdcCode), name: entry.name, formalName: entry.formalName,
    description: entry.description, category: entry.category, subcategory: entry.subcategory,
    aliases: entry.aliases.join(', '), patternAsset: entry.pattern.asset,
    defaultScale: String(entry.pattern.defaultScale ?? 1), defaultBackground: entry.colors.defaultBackground,
    defaultPattern: entry.colors.defaultPattern, sourceStandard: entry.source.standard,
    sourceSeries: entry.source.series ?? 'custom', sourceRepository: entry.source.repository ?? 'MultiViewer',
  };
}

export function LithologyCatalogueWorkbench() {
  const [catalogue, setCatalogue] = useState<Catalogue | null>(null);
  const [patterns, setPatterns] = useState<PatternOption[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('all');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>(null);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [saving, setSaving] = useState(false);

  const loadCatalogue = async (preferredId?: string | null) => {
    const response = await fetch(`${apiBase()}/api/wlv/knowledge/lithology/catalogue`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    const data = await response.json() as Catalogue;
    setCatalogue(data);
    setSelectedId((current) => preferredId && data.entries.some((entry) => entry.id === preferredId)
      ? preferredId
      : current && data.entries.some((entry) => entry.id === current)
        ? current
        : data.entries[0]?.id ?? null);
  };

  useEffect(() => {
    Promise.all([
      loadCatalogue(),
      fetch(`${apiBase()}/api/wlv/knowledge/lithology/patterns`, { cache: 'no-store' })
        .then((response) => { if (!response.ok) throw new Error(`${response.status} ${response.statusText}`); return response.json(); })
        .then((data: { patterns: PatternOption[] }) => setPatterns(data.patterns)),
    ]).catch((caught) => setError(caught instanceof Error ? caught.message : 'Lithology catalogue unavailable'));
  }, []);

  const categories = useMemo(() => Array.from(new Set((catalogue?.entries ?? []).map((entry) => entry.category))).sort(), [catalogue]);
  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    return (catalogue?.entries ?? []).filter((entry) =>
      (category === 'all' || entry.category === category)
      && (!query || [entry.name, entry.formalName, entry.description, String(entry.fgdcCode), ...entry.aliases].join(' ').toLowerCase().includes(query))
    );
  }, [catalogue, category, search]);
  const selected = (catalogue?.entries ?? []).find((entry) => entry.id === selectedId) ?? filtered[0] ?? null;
  const url = (entry: Entry) => `${apiBase()}/api/wlv/knowledge/lithology/entries/${encodeURIComponent(entry.id)}/pattern.svg?background=${encodeURIComponent(entry.colors.defaultBackground)}&foreground=${encodeURIComponent(entry.colors.defaultPattern)}&v=${encodeURIComponent(catalogue?.version ?? '1')}`;

  const openAdd = () => {
    setError(null); setStatusMessage(null);
    setForm({ ...emptyForm, patternAsset: selected?.pattern.asset ?? patterns[0]?.asset ?? '' });
    setMode('add');
  };
  const openEdit = () => {
    if (!selected) return;
    setError(null); setStatusMessage(null); setForm(entryToForm(selected)); setMode('edit');
  };
  const closeModal = () => { if (!saving) setMode(null); };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true); setError(null); setStatusMessage(null);
    try {
      const body = {
        id: form.id.trim(), fgdcCode: Number(form.fgdcCode), name: form.name.trim(), formalName: form.formalName.trim(),
        description: form.description.trim(), category: form.category.trim(), subcategory: form.subcategory.trim(),
        aliases: form.aliases.split(',').map((value) => value.trim()).filter(Boolean),
        pattern: { asset: form.patternAsset, defaultScale: Number(form.defaultScale) },
        defaultBackground: form.defaultBackground, defaultPattern: form.defaultPattern,
        sourceStandard: form.sourceStandard.trim(), sourceSeries: form.sourceSeries.trim(), sourceRepository: form.sourceRepository.trim(),
        status: 'active',
      };
      const endpoint = mode === 'edit' && selected ? `/entries/${encodeURIComponent(selected.id)}` : '/entries';
      const response = await fetch(`${apiBase()}/api/wlv/knowledge/lithology${endpoint}`, {
        method: mode === 'edit' ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => null) as { detail?: string | Array<{ msg?: string }> } | null;
        const message = Array.isArray(detail?.detail) ? detail?.detail.map((item) => item.msg).filter(Boolean).join('; ') : detail?.detail;
        throw new Error(message || `${response.status} ${response.statusText}`);
      }
      const saved = await response.json() as Entry;
      await loadCatalogue(saved.id);
      setMode(null);
      setStatusMessage(mode === 'edit' ? `Updated ${saved.name}.` : `Added ${saved.name}.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Lithology could not be saved');
    } finally { setSaving(false); }
  };

  const deleteSelected = async () => {
    if (!selected) return;
    if (!window.confirm(`Delete ${selected.name} from the lithology catalogue? The SVG pattern asset will be retained.`)) return;
    setSaving(true); setError(null); setStatusMessage(null);
    try {
      const response = await fetch(`${apiBase()}/api/wlv/knowledge/lithology/entries/${encodeURIComponent(selected.id)}`, { method: 'DELETE' });
      if (!response.ok) {
        const detail = await response.json().catch(() => null) as { detail?: string } | null;
        throw new Error(detail?.detail || `${response.status} ${response.statusText}`);
      }
      await loadCatalogue(null);
      setStatusMessage(`Deleted ${selected.name}.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Lithology could not be deleted');
    } finally { setSaving(false); }
  };

  const field = (label: string, key: keyof FormState, options?: { type?: string; required?: boolean }) => (
    <label style={{ display: 'grid', gap: 4, fontSize: 11 }}>
      <span>{label}</span>
      <input style={control} type={options?.type ?? 'text'} required={options?.required ?? true} value={form[key]} onChange={(event) => setForm((current) => ({ ...current, [key]: event.target.value }))} />
    </label>
  );

  return <section style={{ padding: 18, color: '#f4f4f4' }} aria-label="Lithology catalogue">
    <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', gap: 18, marginBottom: 14 }}>
      <div><span style={{ fontSize: 11, color: '#9ca3ad', textTransform: 'uppercase', letterSpacing: '.08em' }}>Knowledge Repository</span><h1 style={{ margin: '3px 0 4px', fontSize: 23 }}>Lithology Catalogue</h1><p style={{ margin: 0, color: '#abb1ba', fontSize: 12 }}>{catalogue?.description ?? 'Loading catalogue…'}</p></div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
        <button type="button" style={button} onClick={openAdd}>Add Lithology</button>
        <button type="button" style={button} onClick={openEdit} disabled={!selected}>Edit Selected</button>
        <button type="button" style={{ ...button, borderColor: '#a94a54', color: '#ffb3bb' }} onClick={deleteSelected} disabled={!selected || saving}>Delete Selected</button>
        <span style={{ fontSize: 12, color: '#aeb4bd', marginLeft: 6 }}>{catalogue ? `${filtered.length} of ${catalogue.entryCount} patterns · v${catalogue.version}` : 'Loading…'}</span>
      </div>
    </header>
    {error ? <p style={{ ...panel, color: '#ff8080', padding: 9 }}>{error}</p> : null}
    {statusMessage ? <p style={{ ...panel, color: '#8fe6a7', padding: 9 }}>{statusMessage}</p> : null}
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 330px', gap: 14 }}>
      <div style={panel}><div style={{ display: 'flex', gap: 8, marginBottom: 12 }}><input style={{ ...control, flex: 1 }} value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search name, description, alias or FGDC code…"/><select style={control} value={category} onChange={(event) => setCategory(event.target.value)}><option value="all">All categories</option>{categories.map((item) => <option key={item} value={item}>{item}</option>)}</select></div><div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(138px,1fr))', gap: 9, maxHeight: 'calc(100vh - 295px)', overflow: 'auto' }}>{filtered.map((entry) => <button key={entry.id} type="button" onClick={() => setSelectedId(entry.id)} style={{ textAlign: 'left', background: selected?.id === entry.id ? '#2c333d' : '#20242a', color: '#fff', border: selected?.id === entry.id ? '1px solid #e0a72f' : '1px solid #3a4049', borderRadius: 5, padding: 7, cursor: 'pointer' }}><img src={url(entry)} alt="" style={{ display: 'block', width: '100%', height: 68, objectFit: 'cover', border: '1px solid #555' }}/><strong style={{ display: 'block', fontSize: 11, marginTop: 6 }}>{entry.name}</strong><span style={{ fontSize: 10, color: '#aeb4bd' }}>FGDC {entry.fgdcCode}</span></button>)}</div></div>
      <aside style={{ ...panel, alignSelf: 'start' }}>{selected ? <><h2 style={{ fontSize: 18, margin: '0 0 10px' }}>{selected.name}</h2><img src={url(selected)} alt={`${selected.name} pattern and default colour`} style={{ width: '100%', height: 150, objectFit: 'cover', border: '1px solid #555' }}/><div style={{ fontSize: 11, color: '#d1a33b', marginTop: 10 }}>FGDC {selected.fgdcCode} · {selected.subcategory}</div><p style={{ fontSize: 12, lineHeight: 1.45, color: '#c4c8cf' }}>{selected.description}</p><dl style={{ display: 'grid', gridTemplateColumns: '105px 1fr', gap: '7px 8px', fontSize: 11 }}><dt>Formal name</dt><dd>{selected.formalName}</dd><dt>Category</dt><dd>{selected.category}</dd><dt>Background</dt><dd>{selected.colors.defaultBackground}</dd><dt>Pattern</dt><dd>{selected.colors.defaultPattern}</dd><dt>Aliases</dt><dd>{selected.aliases.join(', ') || '—'}</dd><dt>Source</dt><dd>{selected.source.standard}</dd></dl></> : <p>No lithology selected.</p>}</aside>
    </div>
    {mode ? <div role="dialog" aria-modal="true" aria-label={mode === 'add' ? 'Add lithology' : 'Edit lithology'} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.68)', display: 'grid', placeItems: 'center', zIndex: 1000, padding: 20 }} onMouseDown={(event) => { if (event.target === event.currentTarget) closeModal(); }}><form onSubmit={submit} style={{ ...panel, width: 'min(760px, 94vw)', maxHeight: '90vh', overflow: 'auto', padding: 18 }}><header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}><h2 style={{ margin: 0, fontSize: 18 }}>{mode === 'add' ? 'Add Lithology' : `Edit ${selected?.name ?? 'Lithology'}`}</h2><button type="button" style={button} onClick={closeModal}>Close</button></header><div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,minmax(0,1fr))', gap: 10 }}>{field('Catalogue ID', 'id')}{field('FGDC or custom code', 'fgdcCode', { type: 'number' })}{field('Name', 'name')}{field('Formal name', 'formalName')}{field('Category', 'category')}{field('Subcategory', 'subcategory')}<label style={{ display: 'grid', gap: 4, fontSize: 11, gridColumn: '1 / -1' }}><span>Description</span><textarea style={{ ...control, minHeight: 72, resize: 'vertical' }} required value={form.description} onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))}/></label><label style={{ display: 'grid', gap: 4, fontSize: 11, gridColumn: '1 / -1' }}><span>Aliases, comma separated</span><input style={control} value={form.aliases} onChange={(event) => setForm((current) => ({ ...current, aliases: event.target.value }))}/></label><label style={{ display: 'grid', gap: 4, fontSize: 11, gridColumn: '1 / -1' }}><span>Pattern asset</span><select style={control} required value={form.patternAsset} onChange={(event) => setForm((current) => ({ ...current, patternAsset: event.target.value }))}><option value="">Select pattern…</option>{patterns.map((option) => <option key={option.asset} value={option.asset}>{option.name}</option>)}</select></label>{field('Pattern scale', 'defaultScale', { type: 'number' })}<label style={{ display: 'grid', gap: 4, fontSize: 11 }}><span>Background colour</span><input style={{ ...control, padding: 3, height: 32 }} type="color" value={form.defaultBackground} onChange={(event) => setForm((current) => ({ ...current, defaultBackground: event.target.value.toUpperCase() }))}/></label><label style={{ display: 'grid', gap: 4, fontSize: 11 }}><span>Pattern colour</span><input style={{ ...control, padding: 3, height: 32 }} type="color" value={form.defaultPattern} onChange={(event) => setForm((current) => ({ ...current, defaultPattern: event.target.value.toUpperCase() }))}/></label>{field('Source standard', 'sourceStandard')}{field('Source series', 'sourceSeries')}{field('Source repository', 'sourceRepository')}</div><footer style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16 }}><button type="button" style={button} onClick={closeModal} disabled={saving}>Cancel</button><button type="submit" style={{ ...button, background: '#78c9ed', color: '#06111a', borderColor: '#78c9ed' }} disabled={saving}>{saving ? 'Saving…' : mode === 'add' ? 'Add Lithology' : 'Save Changes'}</button></footer></form></div> : null}
  </section>;
}
