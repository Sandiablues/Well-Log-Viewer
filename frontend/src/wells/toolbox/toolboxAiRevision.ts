import { useCallback, useEffect, useMemo, useState } from 'react';
import { wlvApiBaseUrl } from '../../api/wlvBackendClient';

export type ToolboxAiRevisionTool = 'WME' | 'FTM' | 'CDM' | 'LCM' | 'DSM' | 'CIM_JOIN' | 'CIM_AIQC';
export type ToolboxAiRevisionMetadata = { number:number; label:string; previous_revision:number|null; iteration_type:'initial_discovery'|'supplemental_evidence'; tool:ToolboxAiRevisionTool; well_scoped:true };
type BackendStream={tool:string;authority_key:string;current_revision:number;managed_well_id?:string|null;well_name?:string|null;history?:Array<Record<string,unknown>>};
const LEGACY_STORAGE_PREFIX='wlv.toolbox.aiRevision.v1.';
const normalize=(value:unknown)=>String(value??'').replace(/\s+/g,' ').trim();
export const toolboxAiRevisionLabel=(revision:number)=>`REV_${String(Math.max(1,Math.trunc(revision))).padStart(2,'0')}`;
export const toolboxAiSafeToken=(value:unknown)=>normalize(value).replace(/[^A-Za-z0-9._-]+/g,'_').replace(/^_+|_+$/g,'')||'UNKNOWN_WELL';
const legacyStorageKey=(tool:ToolboxAiRevisionTool,key:string)=>`${LEGACY_STORAGE_PREFIX}${tool}.${encodeURIComponent(normalize(key))}`;
const endpoint=(path:string)=>`${wlvApiBaseUrl()}${path}`;

export function readToolboxAiRevision(tool:ToolboxAiRevisionTool,key:string){
  if(!key||typeof window==='undefined')return 0;
  const n=Number(window.localStorage.getItem(legacyStorageKey(tool,key)));
  return Number.isFinite(n)&&n>0?Math.trunc(n):0;
}
export function writeToolboxAiRevision(tool:ToolboxAiRevisionTool,key:string,revision:number){
  if(!key||typeof window==='undefined')return 0;
  const next=Math.max(readToolboxAiRevision(tool,key),Math.max(0,Math.trunc(revision)));
  if(next>0)window.localStorage.setItem(legacyStorageKey(tool,key),String(next));
  return next;
}
export function inferToolboxAiRevision(artifacts:string[]){
  let highest=0,legacy=false;
  for(const raw of artifacts){
    const value=normalize(raw);if(!value)continue;
    const match=value.match(/_REV_(\d{1,4})/i);
    if(match)highest=Math.max(highest,Number(match[1])||0);
    if(/(?:AI_PACKAGE|AI_RESPONSE)/i.test(value))legacy=true;
  }
  return highest||(legacy?1:0);
}
export function toolboxAiRevisionFromPayload(fileName:string,payload:unknown){
  let highest=inferToolboxAiRevision([fileName]);
  if(payload&&typeof payload==='object'){
    const revision=(payload as Record<string,unknown>).revision;
    if(revision&&typeof revision==='object'){
      const r=revision as Record<string,unknown>;
      for(const value of [r.responds_to_revision,r.number]){
        const n=Number(value);
        if(Number.isFinite(n)&&n>0)highest=Math.max(highest,Math.trunc(n));
      }
    }
  }
  return highest;
}
export function toolboxAiPackageRevision(tool:ToolboxAiRevisionTool,revision:number):ToolboxAiRevisionMetadata{
  const number=Math.max(1,Math.trunc(revision));
  return{number,label:toolboxAiRevisionLabel(number),previous_revision:number>1?number-1:null,iteration_type:number>1?'supplemental_evidence':'initial_discovery',tool,well_scoped:true};
}
export function toolboxAiExpectedResponseRevision(revision:number){
  const number=Math.max(1,Math.trunc(revision));
  return{number,label:toolboxAiRevisionLabel(number),responds_to_revision:number};
}
export function toolboxAiPackageFilename(prefix:string,wellName:unknown,revision:number,extension:'json'|'zip'='json'){
  return`${prefix}_${toolboxAiSafeToken(wellName)}_${toolboxAiRevisionLabel(revision)}.${extension}`;
}
async function backendJson(path:string,init?:RequestInit):Promise<BackendStream>{
  const response=await fetch(endpoint(path),init);
  if(!response.ok)throw new Error(`Toolbox AI revision API ${response.status}`);
  return await response.json() as BackendStream;
}
async function backendMutation(path:string,payload:Record<string,unknown>):Promise<BackendStream>{
  return backendJson(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
}

export function useToolboxAiRevision(tool:ToolboxAiRevisionTool,authorityKey:string,legacyArtifacts:string[]=[]){
  const legacyKey=legacyArtifacts.join('\u0001');
  const[lastRevision,setLastRevision]=useState(0);
  const[ready,setReady]=useState(false);
  const[error,setError]=useState<string|null>(null);

  const refresh=useCallback(async()=>{
    if(!authorityKey){setLastRevision(0);setReady(false);setError(null);return 0}
    setReady(false);
    try{
      const query=new URLSearchParams({tool,authority_key:authorityKey});
      let stream=await backendJson(`/api/toolbox/ai-revisions/stream?${query.toString()}`);
      const legacyRevision=Math.max(readToolboxAiRevision(tool,authorityKey),inferToolboxAiRevision(legacyArtifacts));
      if(legacyRevision>Number(stream.current_revision||0)){
        stream=await backendMutation('/api/toolbox/ai-revisions/synchronize',{
          tool,authority_key:authorityKey,revision:legacyRevision,reason:'one-time frontend legacy migration',actor:'frontend-migration'
        });
      }
      const revision=Math.max(0,Math.trunc(Number(stream.current_revision)||0));
      setLastRevision(revision);
      setReady(true);
      setError(null);
      return revision;
    }catch(err){
      setError(err instanceof Error?err.message:String(err));
      setReady(false);
      return 0;
    }
  },[tool,authorityKey,legacyKey]);

  useEffect(()=>{void refresh()},[refresh]);

  const allocateExport=useCallback(async(options?:{artifactName?:string;wellName?:string;managedWellId?:string})=>{
    if(!authorityKey)throw new Error('AI revision authority key is unavailable');
    const stream=await backendMutation('/api/toolbox/ai-revisions/allocate',{
      tool,authority_key:authorityKey,well_name:options?.wellName||null,managed_well_id:options?.managedWellId||null,
      artifact_name:options?.artifactName||null,reason:'AI package export',actor:'frontend'
    });
    const revision=Math.max(1,Math.trunc(Number(stream.current_revision)||1));
    setLastRevision(revision);setReady(true);setError(null);
    return revision;
  },[tool,authorityKey]);

  const syncImportedArtifact=useCallback(async(fileName:string,payload?:unknown)=>{
    if(!authorityKey)return lastRevision;
    const revision=toolboxAiRevisionFromPayload(fileName,payload);
    if(revision<=0)return lastRevision;
    const stream=await backendMutation('/api/toolbox/ai-revisions/synchronize',{
      tool,authority_key:authorityKey,revision,artifact_name:fileName,reason:'AI response import',actor:'frontend'
    });
    const committed=Math.max(0,Math.trunc(Number(stream.current_revision)||0));
    setLastRevision(committed);setReady(true);setError(null);
    return committed;
  },[tool,authorityKey,lastRevision]);

  const nextRevision=lastRevision+1;
  return useMemo(()=>({
    lastRevision,nextRevision,currentLabel:lastRevision>0?`Rev ${lastRevision}`:'Not started',nextLabel:`Rev ${nextRevision}`,
    ready,error,refresh,allocateExport,syncImportedArtifact
  }),[lastRevision,nextRevision,ready,error,refresh,allocateExport,syncImportedArtifact]);
}
