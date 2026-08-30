import { wlvApiBaseUrl } from '../../api/wlvBackendClient';
import type { ToolboxAiRevisionTool } from './toolboxAiRevision';

export type ToolboxAiStandardVersionSummary = {
  version: number;
  created_at: string;
  created_by: string;
  change_note: string;
};

export type ToolboxAiStandardActive = {
  tool: ToolboxAiRevisionTool;
  active_version: number;
  rules: Record<string, unknown>;
  updated_at: string;
  updated_by: string;
  change_note: string;
  versions: ToolboxAiStandardVersionSummary[];
};

export type ToolboxAiStandardVersion = {
  tool: ToolboxAiRevisionTool;
  active_version: number;
  version: number;
  created_at: string;
  created_by: string;
  change_note: string;
  rules: Record<string, unknown>;
  migrated_previous_rules?: Record<string, unknown> | null;
};

const endpoint = (path: string) => `${wlvApiBaseUrl()}${path}`;

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(endpoint(path), init);
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `AI standards API ${response.status}`);
  }
  return await response.json() as T;
}

export const fetchToolboxAiRules = (tool: ToolboxAiRevisionTool) =>
  requestJson<ToolboxAiStandardActive>(`/api/toolbox/ai-revisions/standards/${tool}`);

export const fetchToolboxAiStandardVersion = (tool: ToolboxAiRevisionTool, version: number) =>
  requestJson<ToolboxAiStandardVersion>(`/api/toolbox/ai-revisions/standards/${tool}/versions/${version}`);

export const saveNewToolboxAiStandardVersion = (
  tool: ToolboxAiRevisionTool,
  rules: Record<string, unknown>,
  changeNote: string,
) => requestJson<ToolboxAiStandardActive>(`/api/toolbox/ai-revisions/standards/${tool}/versions`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ rules, created_by: 'operator', change_note: changeNote }),
});

export const restoreToolboxAiStandardAsNewVersion = (
  tool: ToolboxAiRevisionTool,
  sourceVersion: number,
  changeNote: string,
) => requestJson<ToolboxAiStandardActive>(`/api/toolbox/ai-revisions/standards/${tool}/restore`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ source_version: sourceVersion, created_by: 'operator', change_note: changeNote }),
});


export const deleteToolboxAiStandardVersion = (
  tool: ToolboxAiRevisionTool,
  version: number,
) => requestJson<ToolboxAiStandardActive>(
  `/api/toolbox/ai-revisions/standards/${tool}/versions/${version}`,
  { method: 'DELETE' },
);
