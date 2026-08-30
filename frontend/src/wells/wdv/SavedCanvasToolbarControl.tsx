import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

export type SavedCanvasToolbarItem = {
    saved_canvas_uid: string;
    workspace_id: string;
    name: string;
    created_at: string;
    schema_version: number;
    is_active?: boolean;
};

type Props = {
    items: SavedCanvasToolbarItem[];
    disabled?: boolean;
    busySavedCanvasUid?: string | null;
    saving?: boolean;
    error?: string | null;
    onSave: (name: string) => void | Promise<void>;
    onSaveChanges: (savedCanvasUid: string) => void | Promise<void>;
    onLoad: (savedCanvasUid: string) => void | Promise<void>;
    onDelete: (savedCanvasUid: string) => void | Promise<void>;
};

const MENU_WIDTH = 400;
const CONTROL_HEIGHT = 28;

const neutralButtonStyle = (width: number, primary = false) => ({
    all: 'unset' as const,
    boxSizing: 'border-box' as const,
    width,
    height: CONTROL_HEIGHT,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 4,
    border: primary ? '1px solid #16a34a' : '1px solid #64748b',
    background: primary ? '#10261a' : '#182234',
    color: primary ? '#4ade80' : '#e5e7eb',
    fontSize: 12,
    fontWeight: 500,
    lineHeight: '1',
    cursor: 'pointer',
    userSelect: 'none' as const,
    whiteSpace: 'nowrap' as const,
});

export function SavedCanvasToolbarControl({
    items, disabled = false, busySavedCanvasUid = null, saving = false, error = null,
    onSave, onSaveChanges, onLoad, onDelete,
}: Props) {
    const buttonRef = useRef<HTMLButtonElement | null>(null);
    const popoverRef = useRef<HTMLDivElement | null>(null);
    const inputRef = useRef<HTMLInputElement | null>(null);
    const [open, setOpen] = useState(false);
    const [creating, setCreating] = useState(false);
    const [name, setName] = useState('');
    const [position, setPosition] = useState({ top: 0, left: 0 });
    const sortedItems = useMemo(() => [...items].sort((a, b) => b.created_at.localeCompare(a.created_at)), [items]);
    const activeItem = useMemo(() => items.find((item) => item.is_active) ?? null, [items]);

    const updatePosition = () => {
        const button = buttonRef.current;
        if (!button) return;
        const rect = button.getBoundingClientRect();
        const left = Math.min(window.innerWidth - MENU_WIDTH - 8, Math.max(8, rect.right - MENU_WIDTH));
        setPosition({ top: rect.bottom + 7, left });
    };

    useEffect(() => {
        if (!open) return undefined;
        updatePosition();
        const close = (event: MouseEvent) => {
            const target = event.target as Node;
            if (buttonRef.current?.contains(target) || popoverRef.current?.contains(target)) return;
            setOpen(false); setCreating(false); setName('');
        };
        window.addEventListener('mousedown', close);
        window.addEventListener('resize', updatePosition);
        window.addEventListener('scroll', updatePosition, true);
        return () => {
            window.removeEventListener('mousedown', close);
            window.removeEventListener('resize', updatePosition);
            window.removeEventListener('scroll', updatePosition, true);
        };
    }, [open]);

    useEffect(() => {
        if (creating) window.requestAnimationFrame(() => inputRef.current?.focus());
    }, [creating]);

    const submitSave = async () => {
        const normalized = name.trim();
        if (!normalized || saving) return;
        await onSave(normalized);
        setName('');
        setCreating(false);
    };

    return (
        <span className="wlv-saved-canvas-control">
            <button
                ref={buttonRef}
                type="button"
                className={open ? 'active' : ''}
                disabled={disabled}
                aria-expanded={open}
                title={activeItem ? `Active Saved Canvas: ${activeItem.name}` : 'Save or restore the complete WDV canvas'}
                onClick={() => { setOpen((value) => !value); setCreating(false); setName(''); window.requestAnimationFrame(updatePosition); }}
            >
                {activeItem ? activeItem.name : 'Save Canvas'} ▾
            </button>

            {open ? createPortal(
                <div
                    ref={popoverRef}
                    role="dialog"
                    aria-label="Saved Canvases"
                    style={{
                        position: 'fixed', zIndex: 10000, top: position.top, left: position.left,
                        width: MENU_WIDTH, maxWidth: 'calc(100vw - 16px)', padding: 10,
                        boxSizing: 'border-box', background: '#111827', border: '1px solid #475569',
                        borderRadius: 8, boxShadow: '0 12px 28px rgba(0,0,0,.42)',
                        color: '#e5e7eb', fontFamily: 'inherit',
                    }}
                    onMouseDown={(event) => event.stopPropagation()}
                    onClick={(event) => event.stopPropagation()}
                >
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 8, alignItems: 'center', paddingBottom: 7, borderBottom: '1px solid #334155' }}>
                        <div style={{ fontSize: 13, fontWeight: 600, lineHeight: '18px' }}>Saved Canvases</div>
                        {!creating ? (
                            <button type="button" disabled={saving || Boolean(busySavedCanvasUid)} onClick={() => setCreating(true)} style={neutralButtonStyle(92, true)}>
                                Save As New
                            </button>
                        ) : null}
                    </div>

                    {activeItem && !creating ? (
                        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 92px', gap: 6, alignItems: 'center', padding: '7px 0', borderBottom: '1px solid #334155' }}>
                            <div style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 11, lineHeight: '16px', color: '#94a3b8' }}>
                                Active: <span style={{ color: '#cbd5e1', fontWeight: 500 }}>{activeItem.name}</span>
                            </div>
                            <button type="button" disabled={saving || Boolean(busySavedCanvasUid)} onClick={() => void onSaveChanges(activeItem.saved_canvas_uid)} style={neutralButtonStyle(92, true)}>
                                {saving ? '…' : 'Save Changes'}
                            </button>
                        </div>
                    ) : null}

                    {creating ? (
                        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 52px 62px', gap: 6, alignItems: 'center', padding: '8px 0', borderBottom: '1px solid #334155' }}>
                            <input
                                ref={inputRef}
                                value={name}
                                maxLength={160}
                                placeholder="Canvas name"
                                aria-label="Saved Canvas name"
                                onChange={(event) => setName(event.target.value)}
                                onKeyDown={(event) => {
                                    if (event.key === 'Enter') void submitSave();
                                    if (event.key === 'Escape') { setName(''); setCreating(false); }
                                }}
                                style={{
                                    all: 'unset', boxSizing: 'border-box', width: '100%', minWidth: 0,
                                    height: CONTROL_HEIGHT, padding: '0 8px', borderRadius: 4,
                                    border: '1px solid #64748b', background: '#0f172a', color: '#f8fafc',
                                    fontSize: 12, lineHeight: `${CONTROL_HEIGHT}px`,
                                }}
                            />
                            <button type="button" disabled={saving || !name.trim()} onClick={() => void submitSave()} style={neutralButtonStyle(52, true)}>{saving ? '…' : 'Save'}</button>
                            <button type="button" disabled={saving} onClick={() => { setName(''); setCreating(false); }} style={neutralButtonStyle(62)}>Cancel</button>
                        </div>
                    ) : null}

                    {error ? <div role="alert" style={{ padding: '7px 0 1px', fontSize: 12, lineHeight: '17px', color: '#fca5a5' }}>{error}</div> : null}

                    <div style={{ maxHeight: 240, overflowY: 'auto', paddingTop: sortedItems.length ? 4 : 0 }}>
                        {sortedItems.length === 0 ? (
                            <div style={{ padding: '9px 2px 3px', fontSize: 12, lineHeight: '18px', color: '#94a3b8' }}>No Saved Canvases</div>
                        ) : sortedItems.map((item) => {
                            const active = Boolean(item.is_active);
                            const busy = busySavedCanvasUid === item.saved_canvas_uid;
                            return (
                                <div key={item.saved_canvas_uid} style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 56px 64px', gap: 6, alignItems: 'center', minHeight: 34, padding: '3px 0' }}>
                                    <div title={item.name} style={{ minWidth: 0, display: 'flex', gap: 6, alignItems: 'center', overflow: 'hidden' }}>
                                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 12, lineHeight: '18px', fontWeight: 500 }}>{item.name}</span>
                                        {active ? <span style={{ flex: '0 0 auto', fontSize: 10, lineHeight: '14px', color: '#86efac', fontWeight: 500 }}>Active</span> : null}
                                    </div>
                                    <button type="button" disabled={saving || Boolean(busySavedCanvasUid) || active} onClick={() => void onLoad(item.saved_canvas_uid)} style={neutralButtonStyle(56)}>
                                        {busy ? '…' : active ? '—' : 'Load'}
                                    </button>
                                    <button
                                        type="button"
                                        disabled={saving || Boolean(busySavedCanvasUid)}
                                        onClick={() => { if (window.confirm(`Delete Saved Canvas "${item.name}"?`)) void onDelete(item.saved_canvas_uid); }}
                                        style={neutralButtonStyle(64)}
                                    >
                                        Delete
                                    </button>
                                </div>
                            );
                        })}
                    </div>
                </div>,
                document.body,
            ) : null}
        </span>
    );
}
