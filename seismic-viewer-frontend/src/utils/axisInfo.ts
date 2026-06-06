export type AxisConfidence = 'high' | 'medium' | 'low' | string;

export interface NormalizedAxis {
  key?: string;
  label?: string;
  min?: number | string | null;
  max?: number | string | null;
  step?: number | string | null;
  unit?: string | null;
  source?: string | null;
  confidence?: AxisConfidence | null;
  domain?: string | null;
}

export interface NormalizedMetadata {
  schema_version?: string;
  dataset_kind?: string;
  axis_info?: {
    axes?: NormalizedAxis[];
  };
  extent_info?: Record<string, any>;
  qc_info?: {
    warnings?: string[];
  };
  viewer_info?: Record<string, any>;
  custom?: Record<string, any>;
}

export function getNormalizedMetadata(volume: any): NormalizedMetadata | null {
  return volume?.metadata?.normalized || null;
}

export function getAxisList(source: any): NormalizedAxis[] {
  const normalized = source?.axis_info ? source : getNormalizedMetadata(source);
  const axes = normalized?.axis_info?.axes;

  return Array.isArray(axes) ? axes : [];
}

export function findAxis(source: any, keys: string[]): NormalizedAxis | null {
  const wanted = new Set(keys.map((key) => key.toLowerCase()));

  return (
    getAxisList(source).find((axis) => {
      const key = String(axis.key || '').toLowerCase();
      const label = String(axis.label || '').toLowerCase();
      return wanted.has(key) || wanted.has(label);
    }) || null
  );
}

export function getVerticalAxis(source: any): NormalizedAxis | null {
  return findAxis(source, ['vertical', 'time', 'depth', 'sample', 'two-way time']);
}

export function getInlineAxis(source: any): NormalizedAxis | null {
  return findAxis(source, ['inline', 'inline index']);
}

export function getCrosslineAxis(source: any): NormalizedAxis | null {
  return findAxis(source, ['crossline', 'crossline index']);
}

export function getHorizontalAxis(source: any): NormalizedAxis | null {
  return findAxis(source, ['horizontal', 'trace', 'trace index', 'shotpoint', 'cdp']);
}

function formatNumberish(value: any): string {
  if (value === null || value === undefined || value === '') {
    return '—';
  }

  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return '—';

    if (Math.abs(value) >= 1000) {
      return Number.isInteger(value) ? value.toFixed(0) : value.toFixed(2);
    }

    return Number.isInteger(value) ? value.toFixed(0) : Number(value.toFixed(4)).toString();
  }

  return String(value);
}

export function formatAxisRange(axis: NormalizedAxis | null | undefined): string {
  if (!axis) return '—';

  const min = axis.min;
  const max = axis.max;
  const unit = axis.unit;

  if (min === null || min === undefined || max === null || max === undefined) {
    return '—';
  }

  const range = `${formatNumberish(min)} – ${formatNumberish(max)}`;

  if (!unit || unit === 'number' || unit === 'index') {
    return range;
  }

  return `${range} ${unit}`;
}

export function formatAxisLabel(axis: NormalizedAxis | null | undefined): string {
  if (!axis) return 'Axis';
  return axis.label || axis.key || 'Axis';
}

export function formatAxisSummary(axis: NormalizedAxis | null | undefined): string {
  if (!axis) return '—';

  const parts = [formatAxisRange(axis)];

  if (axis.step !== null && axis.step !== undefined) {
    parts.push(`step ${formatNumberish(axis.step)}`);
  }

  if (axis.unit) {
    parts.push(`unit ${axis.unit}`);
  }

  if (axis.confidence) {
    parts.push(`${axis.confidence} confidence`);
  }

  if (axis.source) {
    parts.push(`source: ${axis.source}`);
  }

  return parts.filter(Boolean).join(' · ');
}

export function getAxisSummaryLines(source: any): string[] {
  return getAxisList(source).map((axis) => `${formatAxisLabel(axis)}: ${formatAxisSummary(axis)}`);
}
