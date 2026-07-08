import { wlvApiBaseUrl } from './WdvPresentationPrimitives';
export type QuickViewSample={depth:number;value:number};
export type QuickViewCurve={curve_id:string;mnemonic:string;description?:string|null;unit_label?:string|null;scale_type:'linear'|'logarithmic';scale_direction:'normal'|'reverse';scale_min:number;scale_max:number;review_required:boolean;scale_source?:string|null;catalogue_status?:string|null;scale_decision?:string|null;source_mnemonic?:string|null;source_description?:string|null;source_unit?:string|null;kr_catalogue_status?:string|null;kr_canonical_curve?:string|null;kr_family?:string|null;kr_unit_status?:string|null;display_unit?:string|null;display_transform?:string|null;scale_reason?:string|null;samples:QuickViewSample[]};
export type QuickViewTrack={track_id:string;title:string;scale_type:'linear'|'logarithmic';curves:QuickViewCurve[]};
export type QuickViewMetadataValue={value:string|number|boolean|null;unit?:string|null;source?:string|null;confidence:'explicit'|'derived'|'not_supplied'|'unresolved'};
export type QuickViewFileInfo={source_file_name:QuickViewMetadataValue;file_type:QuickViewMetadataValue;format_version:QuickViewMetadataValue;file_size_bytes:QuickViewMetadataValue;content_fingerprint:QuickViewMetadataValue;parser_name:QuickViewMetadataValue;parser_status:QuickViewMetadataValue;temporary_only:QuickViewMetadataValue};
export type QuickViewWellInfo={well_name:QuickViewMetadataValue;well_id:QuickViewMetadataValue;uwi:QuickViewMetadataValue;api:QuickViewMetadataValue;field:QuickViewMetadataValue;operator:QuickViewMetadataValue;country:QuickViewMetadataValue;state_province:QuickViewMetadataValue;county_area:QuickViewMetadataValue;latitude:QuickViewMetadataValue;longitude:QuickViewMetadataValue;x:QuickViewMetadataValue;y:QuickViewMetadataValue;datum:QuickViewMetadataValue};
export type QuickViewIndexInfo={source_mnemonic:QuickViewMetadataValue;source_unit:QuickViewMetadataValue;resolved_unit:QuickViewMetadataValue;start:QuickViewMetadataValue;stop:QuickViewMetadataValue;step:QuickViewMetadataValue;sample_count:QuickViewMetadataValue;is_regular:QuickViewMetadataValue};
export type QuickViewCurveCounts={total_curves:number;renderable_curves:number;non_renderable_curves:number;curves_with_units:number;curves_missing_units:number};
export type QuickViewRecognitionSummary={kr_exact:number;kr_alias:number;kr_family:number;unit_domain:number;unknown:number;review_required:number};
export type QuickViewScalingSummary={governed:number;kr_known_fallback:number;unit_domain_fallback:number;generic_fallback:number;unit_mismatch:number};
export type QuickViewCurveInfo={index:QuickViewIndexInfo;curve_counts:QuickViewCurveCounts;recognition_summary:QuickViewRecognitionSummary;scaling_summary:QuickViewScalingSummary};
export type QuickViewQaqcFlag={code:string;severity:'info'|'warning'|'error';message:string;count?:number|null;source?:string|null;visible_by_default:boolean};
export type QuickViewEarlyQaqc={severity:'ok'|'info'|'warning'|'error';flags:QuickViewQaqcFlag[]};
export type QuickViewMetadata={file_info:QuickViewFileInfo;well_info:QuickViewWellInfo;curve_info:QuickViewCurveInfo;early_qaqc:QuickViewEarlyQaqc};
export type QuickViewPackage={contract_kind:'wdv_quick_view';filename:string;source_format:'LAS'|'DLIS';fingerprint:string;well_name:string;depth_min:number;depth_max:number;depth_unit_label?:string|null;tracks:QuickViewTrack[];warnings:string[];quick_view_metadata?:QuickViewMetadata|null};
export const isQuickViewFile=(file:File)=>/\.(las|dlis)$/i.test(file.name);
export async function openQuickViewFile(file:File):Promise<QuickViewPackage>{
 const body=new FormData();body.append('file',file);
 const response=await fetch(`${wlvApiBaseUrl()}/api/wlv/v2/wdv/quick-view`,{method:'POST',body});
 if(!response.ok){let detail=`Quick View failed (${response.status})`;try{const p=await response.json() as {detail?:string};detail=p.detail??detail;}catch{}throw new Error(detail)}
 return response.json() as Promise<QuickViewPackage>;
}


export type QuickViewWsiHandoffResult = {
  candidateCount: number;
  message: string;
};

export async function sendQuickViewFileToWsi(file: File): Promise<QuickViewWsiHandoffResult> {
  const body = new FormData();
  body.append('files', file);
  const response = await fetch(`${wlvApiBaseUrl()}/api/wlv/source-intake/ingest-files`, {
    method: 'POST',
    body,
  });
  if (!response.ok) {
    let detail = `WSI handoff failed (${response.status})`;
    try {
      const payload = await response.json() as { detail?: string };
      detail = payload.detail ?? detail;
    } catch {}
    throw new Error(detail);
  }
  const payload = await response.json() as { candidates?: unknown[] };
  const candidateCount = Array.isArray(payload.candidates) ? payload.candidates.length : 0;
  return {
    candidateCount,
    message: candidateCount === 1 ? 'Sent to WSI' : `Sent ${candidateCount} candidates to WSI`,
  };
}
