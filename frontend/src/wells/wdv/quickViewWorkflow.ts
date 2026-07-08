import { wlvApiBaseUrl } from './WdvPresentationPrimitives';
export type QuickViewSample={depth:number;value:number};
export type QuickViewCurve={curve_id:string;mnemonic:string;description?:string|null;unit_label?:string|null;scale_type:'linear'|'logarithmic';scale_direction:'normal'|'reverse';scale_min:number;scale_max:number;review_required:boolean;scale_source?:string|null;catalogue_status?:string|null;scale_decision?:string|null;source_mnemonic?:string|null;source_description?:string|null;source_unit?:string|null;kr_catalogue_status?:string|null;kr_canonical_curve?:string|null;kr_family?:string|null;kr_unit_status?:string|null;display_unit?:string|null;display_transform?:string|null;scale_reason?:string|null;samples:QuickViewSample[]};
export type QuickViewTrack={track_id:string;title:string;scale_type:'linear'|'logarithmic';curves:QuickViewCurve[]};
export type QuickViewPackage={contract_kind:'wdv_quick_view';filename:string;source_format:'LAS'|'DLIS';fingerprint:string;well_name:string;depth_min:number;depth_max:number;depth_unit_label?:string|null;tracks:QuickViewTrack[];warnings:string[]};
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
