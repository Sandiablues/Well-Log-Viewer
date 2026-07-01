import { fetchWlvApi } from '../api/wlvApiClient';
import type { ManagedCurveUid, ManagedWellUid } from '../identity/wdvIdentityV21';
import type { CanonicalViewerSessionV21 } from '../prototype/canonicalViewerPackageV21';
import { parseCanonicalViewerSessionV21 } from '../prototype/canonicalViewerPackageV21';
import type { CurveCatalogItemV21 } from '../prototype/trackLayoutModelV21';

export type CurveFillMode = 'none' | 'left' | 'right' | 'between' | 'conditional' | 'crossover';
export type ConditionalOperator = 'a_greater_than_b' | 'a_less_than_b';

export interface CurveFillReason { code: string; message: string }
export interface CurveFillModeCapability { mode: CurveFillMode; label: string; available: boolean; reason: CurveFillReason | null }
export interface CurveFillOperandCapability {
  operandType: 'curve' | 'constant_reference' | 'stepped_reference' | 'derived_reference';
  identity: string;
  displayName: string;
  unit: string | null;
  managedWellUid: string;
  trackUid: string;
  available: boolean;
  eligibleFillModes: Array<'between' | 'conditional' | 'crossover'>;
  presetIds: string[];
  reason: CurveFillReason | null;
}
export interface CurveFillPresetCapability {
  presetId: string;
  presetRevision: string;
  label: string;
  fillMode: 'conditional' | 'crossover';
  available: boolean;
  defaultCondition: ConditionalOperator | null;
  overlayPolicyId: string | null;
  overlayPolicyRevision: string | null;
  defaultFill: string;
  defaultOpacity: number;
  deadband: number | null;
  minimumInterval: number | null;
  reason: CurveFillReason | null;
}
export interface CurveFillCapabilities {
  contractVersion: 'curve_fill_capabilities_v1';
  managedWellUid: string;
  sessionUid: string;
  sessionRevision: number;
  trackUid: string;
  ownerAssignmentUid: string;
  modes: CurveFillModeCapability[];
  operands: CurveFillOperandCapability[];
  presets: CurveFillPresetCapability[];
}

function record(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(`${label} must be an object`);
  return value as Record<string, unknown>;
}
function text(value: unknown, label: string): string {
  if (typeof value !== 'string' || !value.trim()) throw new Error(`${label} must be a non-blank string`);
  return value.trim();
}
function optionalText(value: unknown): string | null { return value == null ? null : text(value, 'optional string'); }
function reason(value: unknown): CurveFillReason | null {
  if (value == null) return null;
  const r=record(value,'reason'); return { code:text(r.code,'reason.code'), message:text(r.message,'reason.message') };
}
function stringArray(value: unknown, label: string): string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== 'string')) throw new Error(`${label} must be a string array`);
  return [...value] as string[];
}
export function parseCurveFillCapabilities(value: unknown): CurveFillCapabilities {
  const r=record(value,'curve fill capabilities');
  if (r.contract_version !== 'curve_fill_capabilities_v1') throw new Error('Unsupported curve fill capability contract');
  if (!Array.isArray(r.modes) || !Array.isArray(r.operands) || !Array.isArray(r.presets)) throw new Error('Capability collections must be arrays');
  return {
    contractVersion:'curve_fill_capabilities_v1', managedWellUid:text(r.managed_well_uid,'managed_well_uid'), sessionUid:text(r.session_uid,'session_uid'),
    sessionRevision:Number(r.session_revision), trackUid:text(r.track_uid,'track_uid'), ownerAssignmentUid:text(r.owner_assignment_uid,'owner_assignment_uid'),
    modes:r.modes.map((v) => { const x=record(v,'mode'); return { mode:text(x.mode,'mode.mode') as CurveFillMode, label:text(x.label,'mode.label'), available:x.available===true, reason:reason(x.reason) }; }),
    operands:r.operands.map((v) => { const x=record(v,'operand'); return { operandType:text(x.operand_type,'operand_type') as CurveFillOperandCapability['operandType'], identity:text(x.identity,'identity'), displayName:text(x.display_name,'display_name'), unit:optionalText(x.unit), managedWellUid:text(x.managed_well_uid,'managed_well_uid'), trackUid:text(x.track_uid,'track_uid'), available:x.available!==false, eligibleFillModes:stringArray(x.eligible_fill_modes,'eligible_fill_modes') as CurveFillOperandCapability['eligibleFillModes'], presetIds:stringArray(x.preset_ids,'preset_ids'), reason:reason(x.reason) }; }),
    presets:r.presets.map((v) => { const x=record(v,'preset'); return { presetId:text(x.preset_id,'preset_id'), presetRevision:text(x.preset_revision,'preset_revision'), label:text(x.label,'label'), fillMode:text(x.fill_mode,'fill_mode') as 'conditional'|'crossover', available:x.available===true, defaultCondition:optionalText(x.default_condition) as ConditionalOperator|null, overlayPolicyId:optionalText(x.overlay_policy_id), overlayPolicyRevision:optionalText(x.overlay_policy_revision), defaultFill:text(x.default_fill,'default_fill'), defaultOpacity:Number(x.default_opacity), deadband:x.deadband==null?null:Number(x.deadband), minimumInterval:x.minimum_interval==null?null:Number(x.minimum_interval), reason:reason(x.reason) }; }),
  };
}

async function json(response: Response): Promise<unknown> {
  const payload=await response.json().catch(() => null);
  if (!response.ok) { const r=payload && typeof payload==='object' ? payload as Record<string,unknown> : {}; throw new Error(typeof r.detail==='string' ? r.detail : `Curve Fill request failed (${response.status})`); }
  return payload;
}

export async function loadCurveFillCapabilities(managedWellUid: ManagedWellUid, trackUid: string, ownerAssignmentUid: string, fetchImpl: typeof fetch=fetch): Promise<CurveFillCapabilities> {
  const q=new URLSearchParams({track_uid:trackUid, owner_assignment_uid:ownerAssignmentUid});
  const response=await fetchWlvApi(`/api/wlv/v2/wdv/curve-fill-capabilities/${encodeURIComponent(managedWellUid)}?${q.toString()}`,{headers:{Accept:'application/json'}},fetchImpl);
  return parseCurveFillCapabilities(await json(response));
}

export interface UpsertCurveFillInput {
  fillUid?: string | null; trackUid:string; ownerAssignmentUid:string; ownerCurveUid:ManagedCurveUid; comparisonCurveUid:ManagedCurveUid;
  fillMode:'conditional'|'crossover'; condition:ConditionalOperator|null; overlayPolicyId:string|null; overlayPolicyRevision:string|null;
  fill:string; opacity:number; deadband:number|null; minimumInterval:number|null; depthUnit:string;
}
export async function upsertCurveFill(managedWellUid: ManagedWellUid, revision:number, input:UpsertCurveFillInput, curves:readonly CurveCatalogItemV21[], fetchImpl:typeof fetch=fetch):Promise<CanonicalViewerSessionV21> {
  const depthDomainUid=`md:${managedWellUid}`;
  const operand=(curveUid:ManagedCurveUid) => ({type:'curve',managed_well_uid:managedWellUid,curve_uid:curveUid,depth_domain_uid:depthDomainUid,unit:curves.find((c)=>c.managedCurveUid===curveUid)?.unit ?? null});
  const response=await fetchWlvApi(`/api/wlv/v2/wdv/session-commands/${encodeURIComponent(managedWellUid)}/curve-fills/upsert`,{method:'POST',headers:{Accept:'application/json','Content-Type':'application/json'},body:JSON.stringify({expected_revision:revision,fill_uid:input.fillUid??null,track_uid:input.trackUid,owner_assignment_uid:input.ownerAssignmentUid,fill_mode:input.fillMode,operand_a:operand(input.ownerCurveUid),operand_b:operand(input.comparisonCurveUid),condition:input.fillMode==='conditional'?input.condition:null,comparison_basis:input.fillMode==='conditional'?'engineering_value':'normalized_track_position',overlay_policy_id:input.fillMode==='crossover'?input.overlayPolicyId:null,overlay_policy_revision:input.fillMode==='crossover'?input.overlayPolicyRevision:null,style:{fill:input.fill,opacity:input.opacity},deadband:input.deadband,minimum_interval:input.minimumInterval,depth_unit:input.depthUnit,enabled:true})},fetchImpl);
  return parseCanonicalViewerSessionV21(await json(response),curves);
}
export async function removeCurveFill(managedWellUid:ManagedWellUid,revision:number,fillUid:string,curves:readonly CurveCatalogItemV21[],fetchImpl:typeof fetch=fetch):Promise<CanonicalViewerSessionV21>{
  const response=await fetchWlvApi(`/api/wlv/v2/wdv/session-commands/${encodeURIComponent(managedWellUid)}/curve-fills/remove`,{method:'POST',headers:{Accept:'application/json','Content-Type':'application/json'},body:JSON.stringify({expected_revision:revision,fill_uid:fillUid})},fetchImpl);
  return parseCanonicalViewerSessionV21(await json(response),curves);
}
