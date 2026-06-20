import {
  useMemo,
  useState,
} from 'react';
import type {
  ManagedCurveUid,
} from '../identity/wdvIdentityV21';
import type {
  CurveCatalogItemV21,
} from '../prototype/trackLayoutModelV21';

export interface CanonicalCurveInventoryProps {
  curves: readonly CurveCatalogItemV21[];
  assignedManagedCurveUids: ReadonlySet<ManagedCurveUid>;
  selectedManagedCurveUid: ManagedCurveUid | null;
  onSelect: (managedCurveUid: ManagedCurveUid) => void;
}

function occurrenceLabels(
  curves: readonly CurveCatalogItemV21[],
): ReadonlyMap<ManagedCurveUid, string> {
  const totals = new Map<string, number>();
  const positions = new Map<string, number>();
  const labels = new Map<ManagedCurveUid, string>();

  for (const curve of curves) {
    const key = curve.observedMnemonic.trim().toUpperCase();
    totals.set(key, (totals.get(key) ?? 0) + 1);
  }

  for (const curve of curves) {
    const key = curve.observedMnemonic.trim().toUpperCase();
    const position = (positions.get(key) ?? 0) + 1;
    positions.set(key, position);
    labels.set(
      curve.managedCurveUid,
      (totals.get(key) ?? 0) > 1
        ? `${curve.observedMnemonic} · ${position}`
        : curve.observedMnemonic,
    );
  }

  return labels;
}

export function CanonicalCurveInventory({
  curves,
  assignedManagedCurveUids,
  selectedManagedCurveUid,
  onSelect,
}: CanonicalCurveInventoryProps) {
  const [query, setQuery] = useState('');
  const labels = useMemo(() => occurrenceLabels(curves), [curves]);
  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return curves;
    return curves.filter((curve) => (
      curve.observedMnemonic.toLowerCase().includes(normalized)
      || curve.displayName.toLowerCase().includes(normalized)
      || (curve.unit ?? '').toLowerCase().includes(normalized)
      || curve.curveClass.toLowerCase().includes(normalized)
    ));
  }, [curves, query]);

  return (
    <section className="wlv-canonical-inventory" aria-label="Loaded curves">
      <header className="wlv-canonical-panel-header">
        <div>
          <strong>Loaded Curves</strong>
          <span>{curves.length} available</span>
        </div>
        <input
          aria-label="Filter loaded curves"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Filter curves"
        />
      </header>

      <div className="wlv-canonical-inventory-column-headings">
        <span>Curve</span>
        <span>Unit</span>
        <span>State</span>
      </div>

      <div className="wlv-canonical-inventory-list">
        {filtered.map((curve) => {
          const assigned = assignedManagedCurveUids.has(curve.managedCurveUid);
          const selected = curve.managedCurveUid === selectedManagedCurveUid;
          return (
            <button
              key={curve.managedCurveUid}
              type="button"
              className={[
                'wlv-canonical-inventory-row',
                selected ? 'is-selected' : '',
              ].filter(Boolean).join(' ')}
              onClick={() => onSelect(curve.managedCurveUid)}
              aria-pressed={selected}
              title={[
                curve.displayName,
                curve.unit ?? 'No unit',
                curve.curveClass,
              ].join(' · ')}
            >
              <span className="wlv-canonical-inventory-curve">
                <strong>
                  {labels.get(curve.managedCurveUid)
                    ?? curve.observedMnemonic}
                </strong>
                <small>{curve.displayName}</small>
              </span>
              <span className="wlv-canonical-inventory-unit">
                {curve.unit ?? '—'}
              </span>
              <span
                className={[
                  'wlv-canonical-state-pill',
                  assigned ? 'is-assigned' : '',
                ].filter(Boolean).join(' ')}
              >
                {assigned ? 'Assigned' : 'Loaded'}
              </span>
            </button>
          );
        })}
        {filtered.length === 0 ? (
          <div className="wlv-canonical-inventory-empty">
            No curves match this filter.
          </div>
        ) : null}
      </div>
    </section>
  );
}
