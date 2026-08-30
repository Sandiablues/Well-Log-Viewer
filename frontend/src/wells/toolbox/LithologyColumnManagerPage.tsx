import { useEffect, useMemo, useRef, useState } from 'react';
import * as XLSX from 'xlsx';
import { strFromU8, unzipSync } from 'fflate';
import { fetchWlvJson, wlvApiBaseUrl } from '../../api/wlvBackendClient';
import { toolboxAiExpectedResponseRevision, toolboxAiPackageFilename, toolboxAiPackageRevision, useToolboxAiRevision } from './toolboxAiRevision';
import { fetchToolboxAiRules } from './toolboxAiRulesClient';
import {
  type DeterministicFailureChoice,
  type DeterministicFailureDecision,
  type DeterministicFailurePrompt,
  type EvidencePreparationResponse,
  type EvidencePreparationSummary,
  type GraphicsExportChoice,
  type PreparedEvidenceFile,
  type SkippedArchiveMember,
  type SupportingFile,
  type SupportingFileAuditResult,
  type SupportingFilePreScanResult,
  downloadCompressedJsonPackage,
  downloadText,
  expandZipSupportingFile,
  filePayload,
} from './toolboxAiIntakeExport';

type ManagedWellRecord = {
  managed_well_id: string; managed_well_uid?: string | null; well_id: string; uwi?: string | null;
  well_name?: string | null; display_name?: string | null; wellbore_id?: string | null;
  wellbore_name?: string | null; depth_unit?: string | null; top_depth?: number | null;
  base_depth?: number | null; status?: string | null;
  product_groups?: Array<{ items?: Array<{ product_subgroup_key?: string | null; provenance?: { lithology_intervals?: Array<Record<string, unknown>> } | null }> }>;
};
type ReviewState = 'unreviewed' | 'confirmed' | 'edited' | 'rejected' | 'existing';
type LithologyEntry = { id: string; fgdcCode?: number; name?: string; label?: string; formalName?: string; description?: string; category?: string; subcategory?: string; aliases?: string[]; colors?: { defaultBackground?: string; defaultPattern?: string } };
type LithologyCatalogue = { entries?: LithologyEntry[] };
type Candidate = {
  id:string; state:ReviewState; lithology:string; canonicalLithology:string;
  topMd:string; baseMd:string; topTvd:string; baseTvd:string; topTvdss:string; baseTvdss:string;
  unit:string; depthReference:string; patternId:string; backgroundColor:string; patternColor:string;
  description:string; source:string; evidence:string; confidence:string; notes:string;
  original: Omit<Candidate,'original'> | null;
};
type PersistedSession={selectedWellId:string;candidates:Candidate[];supportingFiles:SupportingFile[];savedAt:string};
const STORAGE_PREFIX='wlv.lcm.review.v1.'; const ACTIVE_KEY='wlv.lcm.activeSession.v1';
const normalize=(v:unknown)=>String(v??'').replace(/\s+/g,' ').trim();
const key=(v:unknown)=>normalize(v).toLowerCase().replace(/[^a-z0-9]+/g,'');
const idFor=(seed:string)=>`${Date.now()}-${Math.random().toString(36).slice(2)}-${seed}`;
function clone(c:Candidate):Omit<Candidate,'original'>{const{original:_o,...rest}=c;return{...rest}}
function emptyCandidate(unit='m', topMd=''):Candidate{const c:Candidate={id:idFor('manual'),state:'unreviewed',lithology:'',canonicalLithology:'',topMd,baseMd:'',topTvd:'',baseTvd:'',topTvdss:'',baseTvdss:'',unit,depthReference:'RT',patternId:'',backgroundColor:'',patternColor:'',description:'',source:'Manual entry',evidence:'',confidence:'',notes:'',original:null};c.original=clone(c);return c}
const valueFrom=(row:Record<string,unknown>,...names:string[])=>{for(const name of names){if(normalize(row[name]))return normalize(row[name]);const found=Object.keys(row).find(k=>key(k)===key(name));if(found&&normalize(row[found]))return normalize(row[found])}return''};
function fromRecord(row:Record<string,unknown>,index:number,source:string,unit:string):Candidate{
 const c:Candidate={id:idFor(`${source}-${index}`),state:'unreviewed',
 lithology:valueFrom(row,'Lithology','lithology','Rock Type','Rock','Facies','Description'),canonicalLithology:valueFrom(row,'Canonical Lithology','canonical_lithology','Lithology Class'),
 topMd:valueFrom(row,'Top MD','top_md','From MD','From','Start MD','Top','MD From'),baseMd:valueFrom(row,'Base MD','base_md','To MD','To','End MD','Base','MD To'),
 topTvd:valueFrom(row,'Top TVD','top_tvd','TVD From'),baseTvd:valueFrom(row,'Base TVD','base_tvd','TVD To'),topTvdss:valueFrom(row,'Top TVDSS','top_tvdss','TVDSS From'),baseTvdss:valueFrom(row,'Base TVDSS','base_tvdss','TVDSS To'),
 unit:valueFrom(row,'Unit','Depth Unit','depth_unit')||unit||'m',depthReference:valueFrom(row,'Depth Reference','Reference','depth_reference')||'RT',patternId:valueFrom(row,'Pattern','Pattern ID','pattern_id'),
 backgroundColor:valueFrom(row,'Background Colour','Background Color','Colour','Color','background_color'),patternColor:valueFrom(row,'Pattern Colour','Pattern Color','pattern_color'),
 description:valueFrom(row,'Original Description','Description','Remarks','description'),source:valueFrom(row,'Source','Source Document','source_document')||source,evidence:valueFrom(row,'Evidence','Source Reference','Page','source_reference'),confidence:valueFrom(row,'Confidence','confidence'),notes:valueFrom(row,'Notes','notes'),original:null};c.original=clone(c);return c;
}
function catalogueEntryText(entry:LithologyEntry){return [entry.name,entry.label,entry.formalName,...(entry.aliases??[])].map(normalize).filter(Boolean)}
function representativeCatalogueEntry(entries:LithologyEntry[],candidate:Candidate):LithologyEntry|null{
 const direct=entries.find(entry=>entry.id===candidate.canonicalLithology);
 if(direct)return direct;
 const lithology=normalize(candidate.lithology);
 if(!lithology)return null;
 const exact=(term:string)=>{const target=key(term);return entries.find(entry=>catalogueEntryText(entry).some(text=>key(text)===target))??null};
 const exactFull=exact(lithology);if(exactFull)return exactFull;
 const components=lithology.split(/\s+(?:and|with|plus|&)\s+|\s*[/,;]\s*/i).map(normalize).filter(Boolean);
 for(const component of components){const matched=exact(component);if(matched)return matched}
 const terms=components.length?components:[lithology];
 for(const term of terms){
  const token=normalize(term).toLowerCase();
  if(!token)continue;
  const escaped=token.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  const rx=new RegExp(`(^|[^a-z0-9])${escaped}([^a-z0-9]|$)`,'i');
  const matches=entries.filter(entry=>catalogueEntryText(entry).some(text=>rx.test(text.toLowerCase())));
  if(matches.length){
   return [...matches].sort((a,b)=>{
    const aLen=Math.min(...catalogueEntryText(a).map(text=>text.length));
    const bLen=Math.min(...catalogueEntryText(b).map(text=>text.length));
    return aLen-bLen||String(a.name??a.label??a.id).localeCompare(String(b.name??b.label??b.id));
   })[0];
  }
 }
 return null;
}
function reconcileRoundtripCandidate(candidate:Candidate,entries:LithologyEntry[]):Candidate{
 const entry=representativeCatalogueEntry(entries,candidate);
 if(!entry){
  if(candidate.canonicalLithology&&!entries.some(item=>item.id===candidate.canonicalLithology)){const cleared={...candidate,canonicalLithology:'',patternId:'',backgroundColor:'',patternColor:''};cleared.original=clone(cleared);return cleared;}
  return candidate;
 }
 const reconciled={...candidate,canonicalLithology:entry.id,patternId:entry.id,backgroundColor:candidate.backgroundColor||entry.colors?.defaultBackground||'',patternColor:candidate.patternColor||entry.colors?.defaultPattern||''};
 reconciled.original=clone(reconciled);
 return reconciled;
}
function readActive():PersistedSession|null{try{const raw=sessionStorage.getItem(ACTIVE_KEY);return raw?JSON.parse(raw) as PersistedSession:null}catch{sessionStorage.removeItem(ACTIVE_KEY);return null}}
const numberOrNull=(v:string)=>normalize(v)===''?null:Number(v);

function LithologySwatchPicker({
  entries,
  selectedId,
  backgroundColor,
  patternColor,
  onSelect,
}: {
  entries: LithologyEntry[];
  selectedId: string;
  backgroundColor: string;
  patternColor: string;
  onSelect: (entry: LithologyEntry | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const selected = entries.find((entry) => entry.id === selectedId) ?? null;
  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return entries;
    return entries.filter((entry) =>
      [
        entry.name,
        entry.label,
        entry.formalName,
        entry.description,
        entry.fgdcCode,
        ...(entry.aliases ?? []),
      ].some((value) => normalize(value).toLowerCase().includes(query)),
    );
  }, [entries, search]);
  const patternUrl = (entry: LithologyEntry) => {
    const background = backgroundColor || entry.colors?.defaultBackground || '#ffffff';
    const foreground = patternColor || entry.colors?.defaultPattern || '#000000';
    return `${wlvApiBaseUrl()}/api/wlv/knowledge/lithology/entries/${encodeURIComponent(entry.id)}/pattern.svg?background=${encodeURIComponent(background)}&foreground=${encodeURIComponent(foreground)}`;
  };
  return (
    <div className="wlv-lcm-swatch-picker">
      <button
        type="button"
        className="wlv-lcm-swatch-picker__trigger"
        onClick={(event) => {
          event.stopPropagation();
          setOpen((current) => !current);
        }}
      >
        {selected ? (
          <>
            <img src={patternUrl(selected)} alt="" />
            <span>
              <strong>{selected.name || selected.label || selected.id}</strong>
              <small>{selected.fgdcCode ? `FGDC ${selected.fgdcCode}` : selected.id}</small>
            </span>
          </>
        ) : (
          <span><strong>Catalogue match…</strong><small>Choose by pattern and colour</small></span>
        )}
      </button>
      {open ? (
        <div className="wlv-lcm-swatch-picker__popover" onClick={(event) => event.stopPropagation()}>
          <div className="wlv-lcm-swatch-picker__toolbar">
            <input
              autoFocus
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search lithology, alias or FGDC code…"
            />
            <button type="button" onClick={() => setOpen(false)}>Close</button>
          </div>
          <button
            type="button"
            className="wlv-lcm-swatch-picker__none"
            onClick={() => {
              onSelect(null);
              setOpen(false);
            }}
          >
            No catalogue match
          </button>
          <div className="wlv-lcm-swatch-picker__grid">
            {filtered.map((entry) => (
              <button
                type="button"
                key={entry.id}
                className={entry.id === selectedId ? 'is-selected' : ''}
                onClick={() => {
                  onSelect(entry);
                  setOpen(false);
                }}
              >
                <img src={patternUrl(entry)} alt="" />
                <span>
                  <strong>{entry.name || entry.label || entry.id}</strong>
                  <small>{entry.fgdcCode ? `FGDC ${entry.fgdcCode}` : entry.id}</small>
                </span>
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}


export function LithologyColumnManagerPage({onBack}:{onBack:()=>void}){
 const activeRef=useRef<PersistedSession|null>(readActive());
 const [wells,setWells]=useState<ManagedWellRecord[]>([]); const [selectedWellId,setSelectedWellId]=useState(activeRef.current?.selectedWellId??'');
 const [wellSearch,setWellSearch]=useState(''); const [candidates,setCandidates]=useState<Candidate[]>(activeRef.current?.candidates??[]);
 const [supportingFiles,setSupportingFiles]=useState<SupportingFile[]>(activeRef.current?.supportingFiles??[]); const [fileObjects,setFileObjects]=useState<File[]>([]);
 const fileObjectsRef=useRef<File[]>([]);
 const [selectedSupportingFileIndexes,setSelectedSupportingFileIndexes]=useState<Set<number>>(()=>new Set());
 const [deterministicSupportingFileIndexes,setDeterministicSupportingFileIndexes]=useState<Set<number>>(()=>new Set());
 const [skippedArchiveMembers,setSkippedArchiveMembers]=useState<SkippedArchiveMember[]>([]);
 const [supportingFilePreScanResults,setSupportingFilePreScanResults]=useState<Record<number,SupportingFilePreScanResult>>({});
 const [supportingFileAuditResults,setSupportingFileAuditResults]=useState<Record<string,SupportingFileAuditResult>>({});
 const [activeSupportingFileAudit,setActiveSupportingFileAudit]=useState<SupportingFileAuditResult|null>(null);
 const [supportingManifestCollapsed,setSupportingManifestCollapsed]=useState(false);
 const [preScanRunning,setPreScanRunning]=useState(false);
 const [graphicsChoiceFiles,setGraphicsChoiceFiles]=useState<string[]|null>(null);
 const graphicsChoiceResolverRef=useRef<((choice:GraphicsExportChoice)=>void)|null>(null);
 const [deterministicFailurePrompt,setDeterministicFailurePrompt]=useState<DeterministicFailurePrompt|null>(null);
 const deterministicFailureResolverRef=useRef<((decision:DeterministicFailureDecision)=>void)|null>(null);
 const [rememberDeterministicFailureChoice,setRememberDeterministicFailureChoice]=useState(false);
 const [catalogue,setCatalogue]=useState<LithologyEntry[]>([]); const [loadingWells,setLoadingWells]=useState(true); const [status,setStatus]=useState('Select a managed well to begin.');
 const [error,setError]=useState<string|null>(null); const [activeEditId,setActiveEditId]=useState<string|null>(null);
const [selectedCandidateIds, setSelectedCandidateIds] = useState<Set<string>>(() => new Set());
 const fileRef=useRef<HTMLInputElement|null>(null); const aiRef=useRef<HTMLInputElement|null>(null);
 const selectedWell=useMemo(()=>wells.find(w=>w.managed_well_id===selectedWellId)??null,[wells,selectedWellId]);
 useEffect(()=>{fileObjectsRef.current=fileObjects},[fileObjects]);
 const aiRevision=useToolboxAiRevision('LCM',selectedWellId,candidates.map(c=>c.id));
 const filteredWells=useMemo(()=>{const q=wellSearch.trim().toLowerCase();return q?wells.filter(w=>[w.display_name,w.well_name,w.wellbore_name,w.uwi,w.managed_well_id].some(v=>normalize(v).toLowerCase().includes(q))):wells},[wells,wellSearch]);
 const summary=useMemo(()=>({total:candidates.length,approved:candidates.filter(c=>c.state==='confirmed'||c.state==='edited').length,rejected:candidates.filter(c=>c.state==='rejected').length,unreviewed:candidates.filter(c=>c.state==='unreviewed').length}),[candidates]);
 useEffect(()=>{let cancelled=false;Promise.all([fetchWlvJson<ManagedWellRecord[]>('/api/wlv/inventory/wells'),fetchWlvJson<LithologyCatalogue>('/api/wlv/knowledge/lithology/catalogue')]).then(([records,cat])=>{if(cancelled)return;setWells(records);setCatalogue(cat.entries??[]);setStatus(records.length?'Select a managed well to begin.':'No managed wells are available.')}).catch(e=>!cancelled&&setError(e instanceof Error?e.message:'Unable to load LCM data')).finally(()=>!cancelled&&setLoadingWells(false));return()=>{cancelled=true}},[]);
 useEffect(()=>{if(loadingWells)return;if(!selectedWellId){setCandidates([]);setSupportingFiles([]);setFileObjects([]);return}const active=activeRef.current;if(active?.selectedWellId===selectedWellId){setCandidates(active.candidates??[]);setSupportingFiles(active.supportingFiles??[]);activeRef.current=null;setStatus('Restored active Lithology Column Manager session.');return}const raw=localStorage.getItem(`${STORAGE_PREFIX}${selectedWellId}`);if(raw){try{const p=JSON.parse(raw) as PersistedSession;setCandidates(p.candidates??[]);setSupportingFiles(p.supportingFiles??[]);setStatus('Restored saved lithology review.');return}catch{localStorage.removeItem(`${STORAGE_PREFIX}${selectedWellId}`)}}const existing:Candidate[]=[];for(const group of selectedWell?.product_groups??[])for(const item of group.items??[])if(item.product_subgroup_key==='lithology_intervals')for(const [i,row] of (item.provenance?.lithology_intervals??[]).entries()){const c=fromRecord(row,i,'Existing Lithology Column dataset',selectedWell?.depth_unit||'m');c.state='existing';existing.push(c)}setCandidates(existing);setSupportingFiles([]);setFileObjects([]);setStatus(`Loaded ${existing.length} existing lithology interval(s).`)},[selectedWellId,selectedWell,loadingWells]);
 useEffect(()=>{if(!selectedWellId){sessionStorage.removeItem(ACTIVE_KEY);return}const p:PersistedSession={selectedWellId,candidates,supportingFiles,savedAt:new Date().toISOString()};const s=JSON.stringify(p);sessionStorage.setItem(ACTIVE_KEY,s);localStorage.setItem(`${STORAGE_PREFIX}${selectedWellId}`,s)},[selectedWellId,candidates,supportingFiles]);
 const saveReview=()=>{if(!selectedWellId){setError('Select a managed well before saving.');return}localStorage.setItem(`${STORAGE_PREFIX}${selectedWellId}`,JSON.stringify({selectedWellId,candidates,supportingFiles,savedAt:new Date().toISOString()}));setStatus('Lithology review saved.');setError(null)};
 const candidateHasRecognizedContent=(candidate:Candidate)=>Boolean(
  normalize(candidate.lithology)
  || normalize(candidate.topMd)
  || normalize(candidate.baseMd)
  || normalize(candidate.canonicalLithology)
  || normalize(candidate.description)
 );
 const candidatesFromRows=(rows:Record<string,unknown>[],sourceName:string)=>rows
  .map((row,index)=>reconcileRoundtripCandidate(fromRecord(row,index,sourceName,selectedWell?.depth_unit||'m'),catalogue))
  .filter(candidateHasRecognizedContent);
 const rowsFromJsonPayload=(payload:unknown):Record<string,unknown>[]=>{
  if(Array.isArray(payload))return payload.filter((row):row is Record<string,unknown>=>!!row&&typeof row==='object');
  if(!payload||typeof payload!=='object')return[];
  const record=payload as Record<string,unknown>;
  for(const keyName of ['candidates','rows','intervals','lithology_intervals','data']){
   const value=record[keyName];
   if(Array.isArray(value))return value.filter((row):row is Record<string,unknown>=>!!row&&typeof row==='object');
  }
  return[];
 };
 const importRows=async(file:File):Promise<Candidate[]>=>{
  const ext=file.name.split('.').pop()?.toLowerCase();
  let rows:Record<string,unknown>[]=[];
  if(ext==='json'){
   rows=rowsFromJsonPayload(JSON.parse(await file.text()) as unknown);
  }else if(['csv','xlsx','xls'].includes(ext||'')){
   const wb=XLSX.read(await file.arrayBuffer(),{type:'array'});
   const sheet=wb.Sheets[wb.SheetNames[0]];
   if(sheet)rows=XLSX.utils.sheet_to_json<Record<string,unknown>>(sheet,{defval:''});
  }else{
   throw new Error(`Unsupported external review file type: ${ext||'unknown'}. Use CSV, XLSX, XLS, JSON, or ZIP.`);
  }
  const imported=candidatesFromRows(rows,file.name);
  if(!imported.length)throw new Error(`No recognizable lithology review rows were found in ${file.name}. Expected fields such as Lithology, Top MD, Base MD, Canonical Lithology, or Description.`);
  return imported;
 };
 const importExternalZipRows=async(file:File):Promise<Candidate[]>=>{
  let archive:Record<string,Uint8Array>;
  try{archive=unzipSync(new Uint8Array(await file.arrayBuffer()))}catch{throw new Error('Unable to open the external ZIP package.')}
  const imported:Candidate[]=[];
  const supported=Object.entries(archive)
   .filter(([name])=>/\.(csv|xlsx|xls|json)$/i.test(name)&&!name.endsWith('/'))
   .sort(([a],[b])=>a.localeCompare(b));
  for(const [name,bytes] of supported){
   const ext=name.split('.').pop()?.toLowerCase();
   try{
    let rows:Record<string,unknown>[]=[];
    if(ext==='json'){
     rows=rowsFromJsonPayload(JSON.parse(strFromU8(bytes)) as unknown);
    }else{
     const wb=XLSX.read(bytes,{type:'array'});
     const sheet=wb.Sheets[wb.SheetNames[0]];
     if(sheet)rows=XLSX.utils.sheet_to_json<Record<string,unknown>>(sheet,{defval:''});
    }
    imported.push(...candidatesFromRows(rows,`${file.name}:${name}`));
   }catch{
    // A generic external bundle may contain unrelated tabular/JSON artifacts.
    // Ignore members that are not valid lithology review tables.
   }
  }
  if(!imported.length)throw new Error('This ZIP is not an MWD round-trip package and contains no recognizable external lithology review CSV, Excel, or JSON rows.');
  return imported;
 };
 const importMwdRoundtripRows=async(file:File):Promise<Candidate[]>=>{
  if(!selectedWell)throw new Error('Select the managed well that this MWD round-trip package belongs to before importing it.');
  let archive:Record<string,Uint8Array>;
  try{archive=unzipSync(new Uint8Array(await file.arrayBuffer()))}catch{throw new Error('Unable to open the MWD round-trip ZIP package.')}
  const manifestBytes=archive['manifest.json'];
  if(!manifestBytes)throw new Error('This ZIP is not an MWD round-trip package: manifest.json is missing.');
  let manifest:Record<string,unknown>;
  try{manifest=JSON.parse(strFromU8(manifestBytes)) as Record<string,unknown>}catch{throw new Error('The MWD round-trip manifest.json is invalid.')}
  if(manifest.schema!=='multiviewer.mwd.export.v1')throw new Error(`Unsupported MWD package schema: ${normalize(manifest.schema)||'missing'}.`);
  if(manifest.export_profile!=='multiviewer_roundtrip')throw new Error(`This package is not a MultiViewer round-trip export (profile: ${normalize(manifest.export_profile)||'missing'}).`);
  const items=Array.isArray(manifest.items)?manifest.items.filter((value):value is Record<string,unknown>=>!!value&&typeof value==='object'):[];
  const lithologyItem=items.find(item=>normalize(item.product_subtype)==='lithology_intervals');
  if(!lithologyItem)throw new Error('The MWD round-trip package does not contain a lithology_intervals product.');
  const wells=Array.isArray(manifest.wells)?manifest.wells.filter((value):value is Record<string,unknown>=>!!value&&typeof value==='object'):[];
  const packageWellId=normalize(lithologyItem.managed_well_id)||normalize(wells[0]?.managed_well_id);
  if(!packageWellId)throw new Error('The MWD round-trip package does not identify its managed well.');
  if(packageWellId!==selectedWell.managed_well_id)throw new Error(`Managed well mismatch. Package: ${packageWellId}. Selected LCM well: ${selectedWell.managed_well_id}.`);
  const exportFiles=Array.isArray(lithologyItem.export_files)?lithologyItem.export_files.filter((value):value is Record<string,unknown>=>!!value&&typeof value==='object'):[];
  const derivative=exportFiles.find(entry=>normalize(entry.role)==='editable_derivative'&&normalize(entry.format).toLowerCase()==='csv');
  let rows:Record<string,unknown>[]=[];
  const derivativePath=normalize(derivative?.path);
  if(derivativePath&&archive[derivativePath]){
   const wb=XLSX.read(strFromU8(archive[derivativePath]),{type:'string'});
   rows=XLSX.utils.sheet_to_json<Record<string,unknown>>(wb.Sheets[wb.SheetNames[0]],{defval:''});
  }
  if(!rows.length){
   const metadataEntry=exportFiles.find(entry=>normalize(entry.role)==='metadata'&&normalize(entry.format).toLowerCase()==='json');
   const metadataPath=normalize(metadataEntry?.path);
   if(metadataPath&&archive[metadataPath]){
    try{
     const metadata=JSON.parse(strFromU8(archive[metadataPath])) as {product?:{provenance?:{lithology_intervals?:unknown[]}}};
     const fallback=metadata.product?.provenance?.lithology_intervals;
     if(Array.isArray(fallback))rows=fallback.filter((value):value is Record<string,unknown>=>!!value&&typeof value==='object');
    }catch{throw new Error('The lithology product metadata in the MWD round-trip package is invalid.')}
   }
  }
  if(!rows.length)throw new Error('The MWD round-trip lithology product contains no editable lithology interval rows.');
  return rows.map((row,index)=>reconcileRoundtripCandidate(fromRecord(row,index,file.name,selectedWell.depth_unit||'m'),catalogue));
 };
  const toggleAllSupportingFiles = () => {
    if (selectedSupportingFileIndexes.size === fileObjects.length && fileObjects.length > 0) {
      setSelectedSupportingFileIndexes(new Set());
      return;
    }
    setSelectedSupportingFileIndexes(new Set(fileObjects.map((_, index) => index)));
  };

  const toggleSupportingFile = (index: number) => {
    setSelectedSupportingFileIndexes((current) => {
      const next = new Set(current);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  };

  const invalidatePreScanForIndexes = (indexes: number[]) => {
    if (!indexes.length) return;
    setSupportingFilePreScanResults((current) => {
      const next = { ...current };
      indexes.forEach((index) => { delete next[index]; });
      return next;
    });
    setSupportingFileAuditResults((current) => {
      const next = { ...current };
      indexes.forEach((index) => {
        const file = fileObjects[index];
        if (file) delete next[file.name];
      });
      return next;
    });
    if (
      activeSupportingFileAudit
      && indexes.some((index) => fileObjects[index]?.name === activeSupportingFileAudit.fileName)
    ) setActiveSupportingFileAudit(null);
  };

  const toggleAllDeterministicSupportingFiles = () => {
    const selectedIndexes = Array.from(selectedSupportingFileIndexes);
    const allSelectedAreScreened = selectedIndexes.length > 0
      && selectedIndexes.every((index) => deterministicSupportingFileIndexes.has(index));

    invalidatePreScanForIndexes(selectedIndexes);
    setDeterministicSupportingFileIndexes(allSelectedAreScreened ? new Set() : new Set(selectedIndexes));
  };

  const toggleDeterministicSupportingFile = (index: number) => {
    invalidatePreScanForIndexes([index]);
    setDeterministicSupportingFileIndexes((current) => {
      const next = new Set(current);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  };

  const handleFiles = async (files: FileList | File[]) => {
    if (!selectedWellId) {
      setError('Select a managed well before adding supporting files.');
      return;
    }

    setError(null);
    const rawIncoming = Array.from(files);
    const incoming: File[] = [];
    const newlySkippedArchiveMembers: SkippedArchiveMember[] = [];

    for (const file of rawIncoming) {
      const extension = file.name.split('.').pop()?.toLowerCase() || '';
      if (extension !== 'zip') {
        incoming.push(file);
        continue;
      }

      setStatus(`Expanding supporting archive ${file.name}…`);
      try {
        const expanded = await expandZipSupportingFile(file);
        incoming.push(...expanded.files);
        newlySkippedArchiveMembers.push(...expanded.skipped.map((item) => ({
          archive: file.name,
          member: item.member,
          reason: item.reason,
        })));
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : `Could not expand ${file.name}.`);
        setStatus(`ZIP expansion failed for ${file.name}. No archive members were attached.`);
        return;
      }
    }

    if (!incoming.length) {
      setError('No supported supporting files were found.');
      setStatus('No supporting files attached.');
      return;
    }

    const existingCount = fileObjects.length;
    const nextObjects = [...fileObjects, ...incoming];
    fileObjectsRef.current = nextObjects;
    setFileObjects(nextObjects);
    setSupportingFiles((current) => [
      ...current,
      ...incoming.map((file) => ({ name: file.name, type: file.type, size: file.size })),
    ]);
    setSupportingFileAuditResults({});
    setSupportingFilePreScanResults({});
    setActiveSupportingFileAudit(null);
    setSupportingManifestCollapsed(false);
    setSelectedSupportingFileIndexes((current) => {
      const next = new Set(current);
      incoming.forEach((_, offset) => next.add(existingCount + offset));
      return next;
    });
    setDeterministicSupportingFileIndexes((current) => {
      const next = new Set(current);
      incoming.forEach((_, offset) => next.add(existingCount + offset));
      return next;
    });
    if (newlySkippedArchiveMembers.length) {
      setSkippedArchiveMembers((current) => [...current, ...newlySkippedArchiveMembers]);
    }

    const imported: Candidate[] = [];
    for (const stagedFile of incoming) {
      try { imported.push(...await importRows(stagedFile)); } catch { /* supporting evidence may not be tabular */ }
    }
    if (imported.length) setCandidates((current) => [...current, ...imported]);

    const zipCount = rawIncoming.filter((file) => file.name.toLowerCase().endsWith('.zip')).length;
    const skipSuffix = newlySkippedArchiveMembers.length
      ? ` ${newlySkippedArchiveMembers.length} unsupported/nested archive member(s) were reported and skipped.`
      : '';
    setStatus(
      `Staged ${incoming.length} supporting file(s)${zipCount ? ` from ${zipCount} ZIP archive(s)` : ''}. `
      + `Select files and screening mode, then Run Pre-Scan.${skipSuffix}`,
    );
  };

  const clearSupportingFiles = () => {
    setSupportingFiles([]);
    fileObjectsRef.current = [];
    setFileObjects([]);
    setSelectedSupportingFileIndexes(new Set());
    setDeterministicSupportingFileIndexes(new Set());
    setSkippedArchiveMembers([]);
    setSupportingFileAuditResults({});
    setSupportingFilePreScanResults({});
    setActiveSupportingFileAudit(null);
    setSupportingManifestCollapsed(false);
    if (fileRef.current) fileRef.current.value = '';
    setStatus('Supporting files cleared. Lithology candidates and review state were preserved.');
    setError(null);
  };

  const requestGraphicsExportChoice = (files: string[]): Promise<GraphicsExportChoice> => new Promise((resolve) => {
    graphicsChoiceResolverRef.current = resolve;
    setGraphicsChoiceFiles(files);
  });

  const resolveGraphicsExportChoice = (choice: GraphicsExportChoice) => {
    const resolve = graphicsChoiceResolverRef.current;
    graphicsChoiceResolverRef.current = null;
    setGraphicsChoiceFiles(null);
    resolve?.(choice);
  };

  const requestDeterministicFailureChoice = (
    fileName: string,
    detail: string,
  ): Promise<DeterministicFailureDecision> => new Promise((resolve) => {
    deterministicFailureResolverRef.current = resolve;
    setRememberDeterministicFailureChoice(false);
    setDeterministicFailurePrompt({
      fileName,
      detail,
      canBypassScoring: /minimum direct score/i.test(detail),
    });
  });

  const resolveDeterministicFailureChoice = (choice: DeterministicFailureChoice) => {
    const resolve = deterministicFailureResolverRef.current;
    deterministicFailureResolverRef.current = null;
    setDeterministicFailurePrompt(null);
    resolve?.({ choice, remember: rememberDeterministicFailureChoice });
    setRememberDeterministicFailureChoice(false);
  };

  const runSupportingFilePreScan = async () => {
    if (!selectedWell) {
      setError('Select a managed well before running document pre-scan.');
      return;
    }
    if (!fileObjects.length) {
      setError(
        supportingFiles.length
          ? 'Reload the remembered supporting files before running pre-scan.'
          : 'Add one or more supporting files before running pre-scan.',
      );
      return;
    }

    const selectedIndexes = Array.from(selectedSupportingFileIndexes).sort((a, b) => a - b);
    if (!selectedIndexes.length) {
      setError('Select at least one supporting file for pre-scan.');
      return;
    }

    setError(null);
    setPreScanRunning(true);
    setActiveSupportingFileAudit(null);
    let rememberedFailureChoice: DeterministicFailureChoice | null = null;

    try {
      const managedAiRules = await fetchToolboxAiRules('LCM');
      const combinedRules = { ...managedAiRules.rules } as Record<string, unknown>;
      const deterministicProfile = (
        combinedRules.deterministic_screening
        && typeof combinedRules.deterministic_screening === 'object'
        && !Array.isArray(combinedRules.deterministic_screening)
      ) ? combinedRules.deterministic_screening as Record<string, unknown> : {};
      const deterministicProfileSignature = JSON.stringify(deterministicProfile);

      const nextResults = { ...supportingFilePreScanResults };
      const nextAudit = { ...supportingFileAuditResults };

      for (const sourceIndex of selectedIndexes) {
        const file = fileObjects[sourceIndex];
        if (!file) continue;

        const payload = await filePayload(file);
        const deterministicRequested = deterministicSupportingFileIndexes.has(sourceIndex);
        const cached = nextResults[sourceIndex];
        if (
          cached
          && cached.sourceName === file.name
          && cached.sourceSha256 === payload.sha256
          && cached.deterministicRequested === deterministicRequested
          && cached.standardVersion === managedAiRules.active_version
          && cached.deterministicProfileSignature === deterministicProfileSignature
        ) continue;

        setStatus(`Pre-scanning ${file.name}…`);

        if (!deterministicRequested) {
          const preparedEvidence: PreparedEvidenceFile = {
            name: file.name,
            mime_type: file.type || 'application/octet-stream',
            size: file.size,
            content_base64: payload.content_base64,
            preprocessed_from_pdf: false,
            deterministic_screening: false,
            selected_pdf_pages_preserved: file.type === 'application/pdf',
          };
          nextResults[sourceIndex] = {
            sourceIndex,
            sourceName: file.name,
            sourceSha256: payload.sha256,
            deterministicRequested: false,
            standardVersion: managedAiRules.active_version,
            deterministicProfileSignature,
            preparedEvidence,
            evidencePreparation: {
              name: file.name,
              mode: 'full_original',
              original_size: file.size,
              prepared_size: file.size,
            },
            estimatedEvidenceTokens: 0,
          };
          nextAudit[file.name] = {
            fileName: file.name,
            requestedMode: 'full_original',
            completionStatus: 'full_original',
            payloadBytes: file.size,
            selectedPageCount: 0,
            totalPages: null,
            reason: 'Full original selected by operator before pre-scan.',
          };
          continue;
        }

        const makePrepareRequest = async (profile: Record<string, unknown>) => fetch(
          `${wlvApiBaseUrl()}/api/toolbox/ai-revisions/qualification/prepare`,
          {
            method: 'POST',
            headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
            body: JSON.stringify({
              candidate_package: {
                deterministic_screening_enabled: true,
                deterministic_screening_profile: profile,
              },
              evidence_files: [{
                name: file.name,
                mime_type: file.type || 'application/octet-stream',
                size: file.size,
                content_base64: payload.content_base64,
              }],
            }),
          },
        );

        let prepareResponse = await makePrepareRequest(deterministicProfile);
        if (!prepareResponse.ok) {
          let failureDetail = `Deterministic pre-screen returned ${prepareResponse.status}`;
          try {
            const failureBody = await prepareResponse.json() as { detail?: unknown };
            if (failureBody?.detail) failureDetail = String(failureBody.detail);
          } catch {
            const failureText = await prepareResponse.text().catch(() => '');
            if (failureText) failureDetail = failureText;
          }

          const rememberedChoiceUsable = rememberedFailureChoice !== 'bypass_scoring'
            || /minimum direct score/i.test(failureDetail);
          const decision: DeterministicFailureDecision = rememberedFailureChoice && rememberedChoiceUsable
            ? { choice: rememberedFailureChoice, remember: true }
            : await requestDeterministicFailureChoice(file.name, failureDetail);
          if (decision.remember) rememberedFailureChoice = decision.choice;

          if (decision.choice === 'cancel') {
            delete nextResults[sourceIndex];
            nextAudit[file.name] = {
              fileName: file.name,
              requestedMode: 'deterministic',
              completionStatus: 'pending',
              payloadBytes: 0,
              selectedPageCount: 0,
              totalPages: null,
              reason: `${failureDetail} Full-original fallback was not authorized.`,
            };
            continue;
          }

          if (decision.choice === 'full_original') {
            const preparedEvidence: PreparedEvidenceFile = {
              name: file.name,
              mime_type: file.type || 'application/octet-stream',
              size: file.size,
              content_base64: payload.content_base64,
              preprocessed_from_pdf: false,
              deterministic_screening: false,
              selected_pdf_pages_preserved: file.type === 'application/pdf',
            };
            nextResults[sourceIndex] = {
              sourceIndex,
              sourceName: file.name,
              sourceSha256: payload.sha256,
              deterministicRequested: true,
              standardVersion: managedAiRules.active_version,
              deterministicProfileSignature,
              preparedEvidence,
              evidencePreparation: {
                name: file.name,
                mode: 'full_original_fallback_after_deterministic_failure',
                original_size: file.size,
                prepared_size: file.size,
              },
              estimatedEvidenceTokens: 0,
            };
            nextAudit[file.name] = {
              fileName: file.name,
              requestedMode: 'deterministic',
              completionStatus: 'full_scan_fallback',
              payloadBytes: file.size,
              selectedPageCount: 0,
              totalPages: null,
              reason: failureDetail,
            };
            continue;
          }

          prepareResponse = await makePrepareRequest({
            ...deterministicProfile,
            bypass_min_direct_score: true,
          });
          if (!prepareResponse.ok) {
            const bypassText = await prepareResponse.text().catch(() => '');
            delete nextResults[sourceIndex];
            nextAudit[file.name] = {
              fileName: file.name,
              requestedMode: 'deterministic',
              completionStatus: 'pending',
              payloadBytes: 0,
              selectedPageCount: 0,
              totalPages: null,
              reason: `${failureDetail} Bypass scoring retry failed: ${bypassText || prepareResponse.status}.`,
            };
            continue;
          }
        }

        const prepared = await prepareResponse.json() as EvidencePreparationResponse;
        if (!Array.isArray(prepared.prepared_evidence) || prepared.prepared_evidence.length !== 1) {
          throw new Error(`Deterministic pre-screen did not return one prepared payload for ${file.name}.`);
        }

        let preparedEvidence = prepared.prepared_evidence[0];
        let evidencePreparation = Array.isArray(prepared.evidence_preparation)
          ? (prepared.evidence_preparation.find((item) => item.name === file.name) ?? prepared.evidence_preparation[0] ?? null)
          : null;

        if (String(evidencePreparation?.graphics_audit?.risk_level || '') === 'high') {
          const choice = await requestGraphicsExportChoice([file.name]);
          if (choice === 'cancel') {
            delete nextResults[sourceIndex];
            nextAudit[file.name] = {
              fileName: file.name,
              requestedMode: 'deterministic',
              completionStatus: 'pending',
              payloadBytes: 0,
              selectedPageCount: 0,
              totalPages: Number(evidencePreparation?.total_pages || 0) || null,
              reason: 'High graphics risk was detected and no payload choice was authorized.',
            };
            continue;
          }
          if (choice === 'full_original') {
            preparedEvidence = {
              name: file.name,
              mime_type: file.type || 'application/octet-stream',
              size: file.size,
              content_base64: payload.content_base64,
              preprocessed_from_pdf: false,
              deterministic_screening: false,
              selected_pdf_pages_preserved: file.type === 'application/pdf',
            };
            evidencePreparation = {
              ...(evidencePreparation ?? {
                name: file.name,
                mode: 'full_original_graphics_override',
                original_size: file.size,
              }),
              mode: 'full_original_graphics_override',
              prepared_size: file.size,
            };
          }
        }

        const payloadBytes = Math.max(
          0,
          Math.floor((String(preparedEvidence.content_base64 || '').length * 3) / 4),
        );
        const selectedPageCount = Number(
          evidencePreparation?.selected_page_count || preparedEvidence.source_pages?.length || 0,
        );
        const totalPagesValue = Number(evidencePreparation?.total_pages);
        const totalPages = Number.isFinite(totalPagesValue) && totalPagesValue > 0 ? totalPagesValue : null;
        const completionStatus: SupportingFileAuditResult['completionStatus'] =
          evidencePreparation?.mode === 'full_original_graphics_override'
            ? 'full_scan_graphics'
            : 'screened';

        nextResults[sourceIndex] = {
          sourceIndex,
          sourceName: file.name,
          sourceSha256: payload.sha256,
          deterministicRequested: true,
          standardVersion: managedAiRules.active_version,
          deterministicProfileSignature,
          preparedEvidence,
          evidencePreparation,
          estimatedEvidenceTokens: Number(prepared.estimated_evidence_tokens || 0),
        };
        nextAudit[file.name] = {
          fileName: file.name,
          requestedMode: 'deterministic',
          completionStatus,
          payloadBytes,
          selectedPageCount,
          totalPages,
          reason: evidencePreparation?.mode === 'full_original_graphics_override'
            ? 'Operator selected full original after high graphics-risk warning.'
            : 'Deterministic pre-scan completed.',
        };
      }

      setSupportingFilePreScanResults(nextResults);
      setSupportingFileAuditResults(nextAudit);

      const unresolved = selectedIndexes.filter((index) => !nextResults[index]).length;
      setStatus(
        unresolved
          ? `Document pre-scan completed with ${unresolved} unresolved selected file(s).`
          : `Document pre-scan completed for ${selectedIndexes.length} selected file(s). Review the manifest, then export.`,
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Document pre-scan failed.');
    } finally {
      setPreScanRunning(false);
    }
  };


 const exportAiPackage=async()=>{
  if(!selectedWell){setError('Select a managed well first.');return}
  const selectedIndexes=Array.from(selectedSupportingFileIndexes).sort((a,b)=>a-b);
  if(!selectedIndexes.length){setError('Select at least one supporting source file.');return}
  try{
   const managedAiRules=await fetchToolboxAiRules('LCM');
   const combinedRules={...managedAiRules.rules} as Record<string,unknown>;
   const deterministicProfile=(combinedRules.deterministic_screening&&typeof combinedRules.deterministic_screening==='object'&&!Array.isArray(combinedRules.deterministic_screening))?combinedRules.deterministic_screening as Record<string,unknown>:{};
   delete combinedRules.deterministic_screening;
   const signature=JSON.stringify(deterministicProfile);
   const selectedResults=selectedIndexes.map(index=>{
    const file=fileObjects[index];const result=supportingFilePreScanResults[index];
    if(!file||!result)throw new Error('All selected files must be resolved by Run Pre-Scan before export.');
    if(result.sourceName!==file.name||result.deterministicRequested!==deterministicSupportingFileIndexes.has(index)||result.standardVersion!==managedAiRules.active_version||result.deterministicProfileSignature!==signature)throw new Error(`${file.name}: pre-scan result is stale. Run Pre-Scan again.`);
    return result
   });
   const sourceFiles=selectedResults.map(result=>({name:result.sourceName,type:result.preparedEvidence.mime_type||'application/octet-stream',size:fileObjects[result.sourceIndex]?.size??result.preparedEvidence.size,sha256:result.sourceSha256}));
   const preparedEvidence=selectedResults.map(result=>result.preparedEvidence);
   const evidencePreparation=selectedResults.map(result=>result.evidencePreparation).filter((item):item is EvidencePreparationSummary=>Boolean(item));
   const estimatedEvidenceTokens=selectedResults.reduce((sum,result)=>sum+Number(result.estimatedEvidenceTokens||0),0);
   const deterministicPreScreen=selectedResults.some(result=>result.deterministicRequested);
   const embeddedCount=selectedResults.length;
   const packageRevision=await aiRevision.allocateExport();
   const payload={
    package_type:'lithology_column_manager_ai_package',
    managed_ai_rules:combinedRules,
    deterministic_screening:{
     enabled:deterministicPreScreen,
     execution:deterministicPreScreen?'application_side_completed_before_export':'disabled',
     profile:deterministicProfile,
     standard_version:managedAiRules.active_version,
     authority:'AI Standards Manager',
     evidence_preparation:evidencePreparation,
     estimated_evidence_tokens:estimatedEvidenceTokens,
     provider_payload_policy:deterministicPreScreen
      ?'Only application-selected original PDF pages are embedded in supporting_files. Their graphics and layout are preserved for LLM review; the full original PDF is excluded unless screening is disabled.'
      :'Full original supporting files are embedded because deterministic screening is disabled.'
    },
    managed_ai_rules_version:managedAiRules.active_version,
    managed_ai_rules_updated_at:managedAiRules.updated_at,
    managed_ai_rules_are_authoritative_overrides:true,
    revision:toolboxAiPackageRevision('LCM',packageRevision),
    schema_version:'1.2.0',
    created_at:new Date().toISOString(),
    managed_well:{managed_well_id:selectedWell.managed_well_id,well_id:selectedWell.well_id,well_name:selectedWell.well_name??selectedWell.display_name,wellbore_name:selectedWell.wellbore_name,uwi:selectedWell.uwi,depth_unit:selectedWell.depth_unit,top_depth:selectedWell.top_depth,base_depth:selectedWell.base_depth},
    multi_document_execution_contract:{
     architecture:'independent_document_extraction_then_non_destructive_union',
     independent_extraction_required:true,
     combined_context_extraction_is_not_a_valid_substitute:true,
     each_supporting_document_is_an_independent_work_unit:true,
     deterministic_screening_budget_scope:'per_document',
     max_selected_pages_per_document:Number(deterministicProfile.max_selected_pages??50),
     no_shared_cross_document_page_budget:true,
     existing_candidates_are_reconciliation_context_only:true,
     existing_candidates_must_not_suppress_new_document_discoveries:true,
     reconciliation_rules:{
      preserve_union_of_all_valid_per_document_candidates:true,
      identical_intervals_may_consolidate_only_when_lithology_and_boundaries_are_materially_equivalent:true,
      consolidated_candidates_must_retain_evidence_from_every_supporting_source:true,
      materially_different_boundaries_or_lithology_interpretations_must_remain_separate_conflicts_or_alternatives:true,
      do_not_deduplicate_by_lithology_name_alone:true
     }
    },
    document_work_units:sourceFiles.map((file,index)=>({
     work_unit_id:`document-${index+1}`,
     source_document:file.name,
     source_mime_type:file.type,
     source_size:file.size,
     sha256:file.sha256,
     deterministic_screening:{
      enabled:deterministicPreScreen,
      executed_in_application:deterministicPreScreen,
      max_selected_pages:Number(deterministicProfile.max_selected_pages??50),
      budget_scope:'this_document_only',
      preparation:evidencePreparation[index]??null
     },
     instruction:'Screen and extract this document independently. Return every defensible selected-well lithology interval and secondary lithology observation from this document before cross-document reconciliation.'
    })),
    extraction_contract:{
     contract_revision:'lithology-discovery-1.0.4',
     role:'Act as a cold-start geological data-extraction model. Use only evidence contained in this package. Do not rely on outside geological knowledge. Other wells contained in the package may be used only as explicitly labelled analogue or correlation evidence, never as direct selected-well evidence.',
     task:'Find defensible, non-overlapping primary lithology intervals for the selected managed well and identify relevant secondary lithology observations in the embedded supporting files. Preserve direct evidence, graphical interpretation, analogue correlation, and regional context as separate evidence classes.',
     required_workflow:[
      'Decode and inspect every supporting file according to its declared MIME type.',
      'Identify every well and sidetrack referenced by each relevant page, table, section, legend, image, or graphical column.',
      'Classify each relevant source section as direct_selected_well, selected_well_graphical, selected_well_stratigraphic_only, analogue_well, field_or_regional, planning_or_prognosis, or not_applicable.',
      'Validate that the evidence applies explicitly to managed_well before extracting a primary candidate.',
      'Extract only direct selected-well evidence into candidates.',
      'Use another well only as explicitly labelled analogue or correlation evidence when selected-well evidence is absent or incomplete. Never present analogue evidence as direct selected-well evidence.',
      'Inspect searchable text, tables, headings, legends, prose, images, and graphical lithology columns. Do not rely only on keyword search when visual layout carries meaning.',
      'After completing textual extraction, inspect every selected-well appendix, CPI plot, composite log, graphical lithology column, image-based log, and flagged track for secondary observations. Do not stop merely because a complete textual lithology table has already been found.',
      'Separate formation-scale primary intervals from secondary observations such as coal stringers, carbonate-cemented streaks, pyrite, glauconite, minor lithologies, trace components, and isolated log flags.',
      'Return zero candidates when no defensible selected-well primary lithology interval is supported.'
     ],
     evidence_hierarchy:[
      'Selected-well core descriptions.',
      'Selected-well cuttings, mudlog, wellsite, or completion-report lithology descriptions.',
      'Selected-well interpreted composite logs, CPI outputs, or graphical lithology tracks.',
      'Selected-well formation descriptions tied to explicit depth intervals.',
      'Correlated evidence from another well in the same field or report.',
      'Field-wide, regional, planning, or prognosed lithology descriptions.',
      'Higher-ranked evidence overrides lower-ranked evidence when they conflict.'
     ],
     source_classification_rules:[
      'A document title alone does not determine source applicability. Classify the specific page, table, section, figure, or track containing the evidence.',
      'direct_selected_well means explicit lithology evidence tied to the managed well.',
      'selected_well_graphical means a selected-well graphical log or flag with an explicit legend and readable depth context.',
      'selected_well_stratigraphic_only means selected-well formation tops or names without rock-type evidence.',
      'analogue_well means lithology evidence from another named well used only for comparison or correlation.',
      'field_or_regional means a field-wide or regional description not demonstrated to be specific to the managed well.',
      'planning_or_prognosis means predicted geology, drilling-program geology, or pre-drill expectations.',
      'not_applicable means the source does not provide usable evidence for the managed well.',
      'For every source, separately determine whether it contains content concerning the managed well and whether its specific evidence is eligible to support primary candidates.',
      'A source may contain managed-well content while remaining ineligible for primary candidates because it is planning, prognosis, stratigraphy-only, graphical-only, analogue, field-wide, regional, or otherwise non-direct.',
      'Because the current response schema has one appliesToManagedWell boolean, use appliesToManagedWell to mean that the source contains managed-well content. In source_validation.notes, explicitly state primaryCandidateEligible=true or primaryCandidateEligible=false.',
      'Record sourceClass=<classification>, primaryCandidateEligible=<true|false>, and the reason in source_validation.notes.'
     ],
     well_identity_rules:[
      'The selected well is identified by managed_well. Treat well-name and sidetrack identity as a mandatory extraction gate.',
      'A document title alone does not prove that every page applies to the selected well.',
      'Where a document contains multiple wells or sidetracks, use only the section explicitly belonging to the selected well for primary candidates.',
      'Do not treat a field-wide table as well-specific merely because it appears in a document bearing the selected well name.',
      'Treat well names in planning, proposal, feasibility, and amendment documents as potentially historical concepts rather than automatically identical to the final drilled well.',
      'Compare document date, parent-well and sidetrack relationship, planned versus drilled role, target segment, trajectory, KOP, TD, coordinates, and explicit well-name reassignment statements.',
      'When an earlier document uses the same well name for a materially different planned concept, classify that material as planning_or_prognosis or not_applicable and document the historical naming discontinuity.',
      'Record source-well mismatches or uncertain applicability in packageNotes. Do not create a candidate when selected-well identity is uncertain.'
     ],
     stratigraphy_rules:[
      'Formation names, group names, member names, reservoir names, and other stratigraphic-unit names are not lithologies.',
      'Do not populate lithology from a formation-top table unless the same source separately states the rock type associated with that formation or interval.',
      'A formation boundary may provide an interval boundary only when explicit selected-well evidence identifies the lithology of that interval.',
      'Do not use general geological knowledge to assign a lithology to a named formation.',
      'Other wells may be used only to compare or interpret a named unit when the correlation is explicit or strongly supported within the package.',
      'Where direct selected-well evidence conflicts with analogue, regional, planning, or prognosed descriptions, retain the direct selected-well description and document the conflict.',
      'A graphical flag supports only what the flag or legend states.',
      'COAL_FLAG supports coal occurrence but does not prove continuous coal across the enclosing range.',
      'CARB_FLAG or CCARB supports carbonate-bearing or carbonate-cemented material but does not by itself prove limestone.'
     ],
     depth_rules:[
      'Populate topMd and baseMd only when the source explicitly identifies the values as MD or Measured Depth, or when the enclosing table, track, or section unambiguously defines the depth scale as MD.',
      'Do not place TVD, TVDSS, subsea depth, or an unspecified depth into an MD field.',
      'Do not calculate TVD, TVDSS, datum conversions, or deviation-derived depths.',
      'Treat managed_well.top_depth and managed_well.base_depth as validation bounds. Flag credible source values outside those bounds in notes; do not silently alter or discard them.',
      'Where explicit lithology change depths are reported, use each change depth as a proposed Top MD and the next explicit change depth as the preceding proposed Base MD.',
      'When Base MD is derived from the next explicit lithology or formation boundary rather than directly stated, explain this in notes and use no higher than medium confidence.',
      'Graphically estimated boundaries must be identified in notes as visual estimates with approximate boundary precision.',
      'Do not create a continuous interval by using the shallowest and deepest occurrence of several isolated graphical features.',
      'Leave the final Base MD empty when the source does not provide or support an ending boundary.'
     ],
     primary_candidate_rules:[
      'Use candidates only for non-overlapping primary selected-well lithology intervals.',
      'A primary candidate must apply explicitly to the selected well, have a defensible top and base, represent the dominant or explicitly mixed lithology, and avoid overlap with other primary candidates.',
      'Primary candidates should form a non-overlapping lithology column. Report gaps rather than fabricating continuity.',
      'Accept explicit ranges, From/To tables, dash ranges, and lithology change-point sequences.',
      'Remove exact duplicates.',
      'Do not merge materially conflicting direct interpretations; return them separately and explain the conflict.',
      'Every candidate must include an exact source filename and traceable page, table, section, heading, track, or graphical-column reference in evidence.',
      'Never publish, approve, or describe a candidate as reviewed.'
     ],
     secondary_observation_rules:[
      'Do not place isolated or subordinate features into candidates when they overlap a defensible primary interval.',
      'Secondary features include coal stringers, carbonate-cemented streaks, pyrite traces, glauconite traces, minor limestone, minor claystone, local grading, isolated graphical flags, and other non-dominant occurrences.',
      'Record secondary observations in packageNotes using the prefix SECONDARY_OBSERVATION.',
      'Each secondary observation must state the host interval, feature, approximate or explicit depth, continuity as continuous, intermittent, discrete, or unknown, source, evidence location, confidence, and boundary precision.',
      'Graphical completion review is mandatory even when textual evidence already defines a complete primary column.',
      'Do not allow a broad graphical observation envelope to replace or split a direct primary interval unless exact selected-well boundaries are available.'
     ],
     lithology_matching_rules:[
      'Preserve the original source wording in lithology and description.',
      'Use the lithology field for the dominant lithology when the source identifies one. Preserve minor and trace components in description and notes.',
      'When several lithologies occur within one interval and no internal boundaries are stated, preserve one mixed interval and do not invent subdivisions.',
      'Assign a canonicalLithology and representative swatch whenever a catalogue entry defensibly represents the dominant lithology family or the best-supported representative family for the interval.',
      'An exact word-for-word match is not required. Use catalogue names, aliases, alternative terms, and recognised parent lithology families supplied in catalogue_entries.',
      'Read compound catalogue labels according to their stated alternatives. For example, a catalogue class named Calcareous Shale Or Marl may be selected for explicit marl evidence; the source does not also have to state calcareous shale.',
      'For a mixed interval, map to the explicitly dominant component. When dominance is not stated, select the catalogue family that best represents the interval as a whole or its principal recurring component, and state representative mapping in notes.',
      'A mixed interval does not require a blank swatch merely because one pattern cannot depict every minor or trace component. Preserve all components in description and identify the swatch as representative.',
      'Descriptor-specific entries such as crossbedded, ripple-bedded, calcareous, carbonaceous, dolomitic, fossiliferous, sandy, silty, or cherty require support when that descriptor narrows the selected catalogue class. Do not require unrelated descriptors that appear only as an alternative in the catalogue label.',
      'Prefer a broad defensible family entry over leaving canonicalLithology and patternId empty.',
      'Leave canonicalLithology and patternId empty only when no catalogue entry reasonably represents the lithology, or when two materially incompatible families are equally supported and no dominant or representative family can be selected.',
      'Do not force an incorrect narrow subtype merely to display a swatch.',
      'When canonicalLithology is assigned and the catalogue entry provides a pattern, set patternId to that catalogue entry id so the LCM renders the swatch.',
      'Treat canonicalLithology as the interpreted catalogue class and patternId as its rendering pattern. Keep both fields consistent with catalogue_entries.',
      'Explain representative, broad-family, mixed-interval, or unresolved mapping decisions in notes.'
     ],
     confidence_definitions:{
      high:'Lithology, Top MD, and Base MD are explicitly reported for the selected well and supported by traceable direct evidence.',
      medium:'Selected-well lithology is explicit but one boundary is defensibly derived, or graphical evidence is clear and accurately depth-tied.',
      low:'The interpretation depends on visually estimated boundaries, analogue correlation, regional context, incomplete depth context, broad indicator-based interpretation, or another material ambiguity. Do not use low confidence when well identity is uncertain; omit the candidate instead.'
     },
     required_for_publish:['topMd','baseMd','lithology'],
     quality_control_rules:[
      'Validate selected-well identity, historical well-name continuity, source classification, primary-candidate eligibility, evidence class, JSON types, candidate ordering, non-overlap, depth bounds, catalogue identifiers, and pattern identifiers.',
      'Verify that all selected-well appendices and graphical log pages have been inspected after textual extraction.',
      'Use native JSON booleans true and false.',
      'The preferred result is not the result with the greatest number of candidates.',
      'The preferred result captures all supported evidence, preserves geological detail, separates direct evidence from interpretation, avoids false continuity, avoids unsupported catalogue mapping, and produces a valid non-overlapping primary lithology column.'
     ],
     response_rules:[
      'Return one valid JSON object only.',
      'Do not include Markdown, code fences, introductory text, or commentary outside the JSON.',
      'Use empty strings for unavailable optional text or numeric values to remain compatible with the LCM importer.',
      'Use candidates only for primary non-overlapping intervals.',
      'Record secondary observations in packageNotes using the SECONDARY_OBSERVATION prefix.',
      'Every source_validation.notes value must begin with sourceClass=<classification>; primaryCandidateEligible=<true|false>; followed by the applicability reason.',
      'Evidence references must identify PDF page number and printed report page number when both are available, followed by section and table, figure, appendix, or track. Use the form: PDF page X of Y; printed page Z; Section A; Table/Figure/Appendix/Track B.',
      'When only one pagination convention is available, identify it explicitly as PDF page or printed page. Do not provide an unqualified page number where pagination may be ambiguous.',
      'A candidates array with zero entries is valid and preferable to unsupported extraction.'
     ]
    },
    expected_response:{
     package_type:'lithology_column_manager_ai_response',
     schema_version:'1.0.1',
     revision:toolboxAiExpectedResponseRevision(packageRevision),
     managed_well_id:'copy managed_well.managed_well_id exactly',
     source_validation:[{source:'exact filename',identifiedWells:['well names found in source'],appliesToManagedWell:true,notes:'begin with sourceClass=<classification>; primaryCandidateEligible=<true|false>; then state why the source contains or does not contain managed-well content and why its evidence is or is not eligible for primary candidates'}],
     packageNotes:[
      'Coverage gaps, source mismatches, historical well-name discontinuities, extraction limitations, conflicts, analogue or regional comparisons, graphical-review limitations, or empty-result explanation.',
      'SECONDARY_OBSERVATION | hostInterval=<MD range or candidate reference> | feature=<feature> | depth=<explicit or approximate depth> | continuity=<continuous|intermittent|discrete|unknown> | source=<exact filename> | evidence=<page/section/track> | confidence=<high|medium|low> | boundaryPrecision=<explicit|derived|approximate>'
     ],
     candidates:[{
      lithology:'original lithology wording',canonicalLithology:'catalogue entry id or empty',topMd:'number or empty',baseMd:'number or empty',topTvd:'number or empty',baseTvd:'number or empty',topTvdss:'number or empty',baseTvdss:'number or empty',unit:'reported depth unit or empty',depthReference:'reported datum or reference or empty',patternId:'catalogue pattern id or empty',description:'original description with dominant, minor, and trace components preserved',source:'exact source filename',evidence:'page number plus table, section, heading, track, or graphical-column location',confidence:'high | medium | low',notes:'state whether boundaries are explicit, derived, or visually estimated; include ambiguity, overlap, gap, evidence class, and catalogue-match limitations'
     }]
    },
    catalogue_entries:catalogue.map(e=>({id:e.id,name:e.name??e.label,aliases:e.aliases??[]})),
    existing_candidates:candidates.map(({original:_o,...c})=>c),
    source_files:sourceFiles,
    source_payload_policy:deterministicPreScreen
     ?'resolved_per_document_pre_scan_payloads_embedded'
     :'original_binary_embedded_in_supporting_files',
    supporting_files:preparedEvidence.map((file,index)=>({
     name:file.name,
     type:file.mime_type||'text/plain',
     size:file.size,
     content_base64:file.content_base64,
     preprocessed_from_pdf:Boolean(file.preprocessed_from_pdf),
     source_pages:file.source_pages??[],
     deterministic_screening:Boolean(file.deterministic_screening),
     source_sha256:sourceFiles[index]?.sha256??'',
     original_source_size:sourceFiles[index]?.size??0
    }))
   };
   const packageFilename=toolboxAiPackageFilename('LCM_AI_PACKAGE',selectedWell.well_name||selectedWell.display_name||selectedWell.managed_well_id,packageRevision);
   const compressedPackageFilename=await downloadCompressedJsonPackage(packageFilename,JSON.stringify(payload,null,2));
   const totalSelectedPages=evidencePreparation.reduce((sum,item)=>sum+Number(item.selected_page_count||0),0);
   setStatus(`${compressedPackageFilename} exported from ${embeddedCount} resolved selected document(s)${totalSelectedPages?` · ${totalSelectedPages} selected PDF page(s)`:''}.`);
   setError(null)
  }catch(e){setError(e instanceof Error?e.message:'Unable to build AI package')}
 };
 const semanticCandidateKey=(candidate:Candidate)=>{
  const top=Number.parseFloat(candidate.topMd);
  const base=Number.parseFloat(candidate.baseMd);
  if(!Number.isFinite(top)||!Number.isFinite(base))return null;
  const canonical=normalize(candidate.canonicalLithology);
  const lithology=normalize(candidate.lithology);
  const identity=canonical||lithology;
  if(!identity)return null;
  return `${top.toFixed(6)}|${base.toFixed(6)}|${identity}`;
 };
 const mergeCandidatesByTopMd=(current:Candidate[],imported:Candidate[])=>{
  const seen=new Set<string>();
  const merged:Candidate[]=[];
  for(const candidate of current){
   merged.push(candidate);
   const key=semanticCandidateKey(candidate);
   if(key)seen.add(key);
  }
  for(const candidate of imported){
   const key=semanticCandidateKey(candidate);
   if(key&&seen.has(key))continue;
   merged.push(candidate);
   if(key)seen.add(key);
  }
  return merged
   .map((candidate,index)=>({candidate,index,top:Number.parseFloat(candidate.topMd)}))
   .sort((a,b)=>{
    const aValid=Number.isFinite(a.top);
    const bValid=Number.isFinite(b.top);
    if(aValid&&bValid){
     if(a.top!==b.top)return a.top-b.top;
     if(a.candidate.state==='existing'&&b.candidate.state!=='existing')return -1;
     if(b.candidate.state==='existing'&&a.candidate.state!=='existing')return 1;
    }else if(aValid!==bValid){
     return aValid?-1:1;
    }
    return a.index-b.index;
   })
   .map(({candidate})=>candidate);
 };
 const importAi=async(file:File)=>{
  try{
   const lowerName=file.name.toLowerCase();
   if(lowerName.endsWith('.zip')){
    let isMwdRoundtrip=false;
    try{
     const archive=unzipSync(new Uint8Array(await file.arrayBuffer()));
     const manifestBytes=archive['manifest.json'];
     if(manifestBytes){
      const manifest=JSON.parse(strFromU8(manifestBytes)) as Record<string,unknown>;
      isMwdRoundtrip=manifest.schema==='multiviewer.mwd.export.v1'&&manifest.export_profile==='multiviewer_roundtrip';
     }
    }catch{
     // The dedicated importer below will provide the useful error for an unreadable ZIP.
    }
    if(isMwdRoundtrip){
     const imported=await importMwdRoundtripRows(file);
     setCandidates(imported);
     setSelectedCandidateIds(new Set());
     setActiveEditId(null);
     setStatus(`Imported ${imported.length} MWD round-trip lithology interval(s) for review. This complete returned dataset replaces the current review table only; approve the rows before publishing to MWD.`);
     setError(null);
     return;
    }
    const imported=await importExternalZipRows(file);
    setCandidates(current=>mergeCandidatesByTopMd(current,imported));
    setStatus(`Imported ${imported.length} external lithology review row(s) from ${file.name}.`);
    setError(null);
    return;
   }
   const imported=await importRows(file);
   setCandidates(current=>mergeCandidatesByTopMd(current,imported));
   setStatus(`Imported ${imported.length} external lithology review row(s) from ${file.name}.`);
   setError(null);
   // AI revision bookkeeping is best-effort metadata only; it must never gate
   // or redefine ordinary external data intake.
   if(lowerName.endsWith('.json')){
    try{void aiRevision.syncImportedArtifact(file.name,JSON.parse(await file.text()))}catch{}
   }
  }catch(e){
   setError(e instanceof Error?e.message:'Unable to import review package');
  }
 };
 const update=(id:string,field:keyof Candidate,value:string)=>setCandidates(v=>v.map(c=>{if(c.id!==id)return c;const n={...c,[field]:value};if(field!=='state'&&c.state!=='existing'&&c.state!=='rejected')n.state='edited';if(field==='canonicalLithology'){const entry=catalogue.find(e=>e.id===value);if(entry){n.patternId=entry.id;n.backgroundColor=entry.colors?.defaultBackground??n.backgroundColor;n.patternColor=entry.colors?.defaultPattern??n.patternColor;if(!n.lithology)n.lithology=entry.name??entry.label??entry.id}}return n}));
 const confirm=(id:string)=>{setCandidates(v=>v.map(c=>c.id===id?{...c,state:c.state==='edited'?'edited':'confirmed'}:c));setActiveEditId(null)};const toggleCandidateSelection = (id: string) => {
  setSelectedCandidateIds((current) => {
    const next = new Set(current);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
  });
};

const selectAllCandidates = () => {
  setSelectedCandidateIds(new Set(candidates.map((candidate) => candidate.id)));
};

const clearCandidateSelection = () => {
  setSelectedCandidateIds(new Set());
};

const acceptSelectedCandidates = () => {
  selectedCandidateIds.forEach((id) => confirm(id));
  setSelectedCandidateIds(new Set());
};

const reject=(id:string)=>{setCandidates(v=>v.map(c=>c.id===id?{...c,state:'rejected'}:c));setActiveEditId(null)};
 const addRow=()=>{const previous=[...candidates].reverse().find(c=>normalize(c.baseMd));setCandidates(v=>[...v,emptyCandidate(selectedWell?.depth_unit||'m',previous?.baseMd||'')])};
 const publish=async()=>{if(!selectedWell){setError('Select a managed well first.');return}const approved=candidates.filter(c=>c.state==='confirmed'||c.state==='edited');if(!approved.length){setError('No approved intervals are available.');return}for(const [i,c] of approved.entries()){const top=Number(c.topMd),base=Number(c.baseMd);if(!normalize(c.lithology)||!Number.isFinite(top)||!Number.isFinite(base)){setError(`Row ${i+1} requires Top MD, Base MD and Lithology.`);return}if(base<=top){setError(`Row ${i+1} Base MD must be deeper than Top MD.`);return}}const payload={dataset_type:'lithology_intervals',dataset_status:'reviewed',source:'Lithology Column Manager',managed_well_id:selectedWell.managed_well_id,lithology_intervals:approved.map(c=>({lithology:c.lithology,canonical_lithology:c.canonicalLithology||null,top_md:numberOrNull(c.topMd),base_md:numberOrNull(c.baseMd),top_tvd:numberOrNull(c.topTvd),base_tvd:numberOrNull(c.baseTvd),top_tvdss:numberOrNull(c.topTvdss),base_tvdss:numberOrNull(c.baseTvdss),depth_unit:c.unit,depth_reference:c.depthReference,pattern_id:c.patternId||null,background_color:c.backgroundColor||null,pattern_color:c.patternColor||null,description:c.description||null,source_document:c.source||null,source_reference:c.evidence||null,confidence:c.confidence||null,notes:c.notes||null}))};try{const r=await fetch(`${wlvApiBaseUrl()}/api/wlv/inventory/wells/${encodeURIComponent(selectedWell.managed_well_id)}/lithology-intervals`,{method:'POST',headers:{Accept:'application/json','Content-Type':'application/json'},body:JSON.stringify(payload)});if(!r.ok)throw new Error(await r.text()||`Publication returned ${r.status}`);await r.json() as {published_count?:number};saveReview();const wellName=selectedWell.display_name||selectedWell.well_name||selectedWell.well_id;setStatus(`Lithology saved to ${wellName} in the MWD.`);setError(null)}catch(e){setError(e instanceof Error?e.message:'Direct MWD publication failed.')}};
 const exportCsv=()=>{if(!candidates.length)return;const cols=['Lithology','Canonical Lithology','Top MD','Base MD','Top TVD','Base TVD','Top TVDSS','Base TVDSS','Unit','Reference','Pattern ID','Background Colour','Pattern Colour','Description','Source','Evidence','Confidence','Review Status','Notes'];const esc=(v:unknown)=>/[",\n]/.test(String(v??''))?`"${String(v??'').replace(/"/g,'""')}"`:String(v??'');const lines=[cols.join(','),...candidates.map(c=>[c.lithology,c.canonicalLithology,c.topMd,c.baseMd,c.topTvd,c.baseTvd,c.topTvdss,c.baseTvdss,c.unit,c.depthReference,c.patternId,c.backgroundColor,c.patternColor,c.description,c.source,c.evidence,c.confidence,c.state,c.notes].map(esc).join(','))];downloadText('LCM_LITHOLOGY_INTERVALS.csv',lines.join('\n'),'text/csv;charset=utf-8')};
 const clear=()=>{if(!selectedWellId&&!wellSearch&&!candidates.length&&!supportingFiles.length&&!fileObjects.length)return;if(selectedWellId)localStorage.removeItem(`${STORAGE_PREFIX}${selectedWellId}`);sessionStorage.removeItem(ACTIVE_KEY);setSelectedWellId('');setWellSearch('');setCandidates([]);setSupportingFiles([]);setFileObjects([]);fileObjectsRef.current=[];setSelectedSupportingFileIndexes(new Set());setDeterministicSupportingFileIndexes(new Set());setSkippedArchiveMembers([]);setSupportingFilePreScanResults({});setSupportingFileAuditResults({});setActiveSupportingFileAudit(null);setSupportingManifestCollapsed(false);setPreScanRunning(false);setDeterministicFailurePrompt(null);deterministicFailureResolverRef.current=null;setGraphicsChoiceFiles(null);graphicsChoiceResolverRef.current=null;setActiveEditId(null);if(fileRef.current)fileRef.current.value='';if(aiRef.current)aiRef.current.value='';setStatus('Lithology Column Manager cleared. Published lithology was not removed.');setError(null)};
 return <section className="wlv-metadata-tool wlv-ftm-tool wlv-lcm-tool">
      {activeSupportingFileAudit ? <div
        role="dialog"
        aria-modal="true"
        aria-label="Supporting file audit"
        style={{ position: 'fixed', inset: 0, zIndex: 12000, background: 'rgba(0,0,0,0.6)', display: 'grid', placeItems: 'center' }}
      >
        <div style={{ width: 'min(640px, calc(100vw - 40px))', background: '#151b21', border: '1px solid #465466', borderRadius: '6px', padding: '16px', color: '#dbe3eb' }}>
          <strong style={{ display: 'block', marginBottom: '8px' }}>{activeSupportingFileAudit.fileName}</strong>
          <div style={{ fontSize: '11px', lineHeight: 1.55, whiteSpace: 'pre-wrap' }}>
            Requested mode: {activeSupportingFileAudit.requestedMode}{'\n'}
            Completion status: {activeSupportingFileAudit.completionStatus}{'\n'}
            Payload: {activeSupportingFileAudit.payloadBytes.toLocaleString()} bytes{'\n'}
            Pages: {activeSupportingFileAudit.selectedPageCount}{activeSupportingFileAudit.totalPages ? ` / ${activeSupportingFileAudit.totalPages}` : ''}{'\n'}
            Reason: {activeSupportingFileAudit.reason}
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '14px' }}>
            <button type="button" onClick={() => setActiveSupportingFileAudit(null)}>Close</button>
          </div>
        </div>
      </div> : null}

      {deterministicFailurePrompt ? <div
        role="dialog"
        aria-modal="true"
        aria-label="Deterministic screening unavailable for this document"
        style={{ position: 'fixed', inset: 0, zIndex: 12000, background: 'rgba(0,0,0,0.6)', display: 'grid', placeItems: 'center' }}
      >
        <div style={{ width: 'min(700px, calc(100vw - 40px))', background: '#151b21', border: '1px solid #465466', borderRadius: '6px', padding: '16px', color: '#dbe3eb' }}>
          <strong style={{ display: 'block', marginBottom: '6px' }}>Deterministic screening unavailable for this document</strong>
          <div style={{ fontSize: '11px', color: '#aeb9c5', marginBottom: '8px' }}>{deterministicFailurePrompt.fileName}</div>
          <div style={{ fontSize: '11px', lineHeight: 1.45, whiteSpace: 'pre-wrap' }}>{deterministicFailurePrompt.detail}</div>
          <label style={{ display: 'inline-flex', alignItems: 'center', gap: '7px', marginTop: '12px', fontSize: '10px' }}>
            <input
              type="checkbox"
              checked={rememberDeterministicFailureChoice}
              onChange={(event) => setRememberDeterministicFailureChoice(event.target.checked)}
            />
            Remember this answer for the rest of this pre-scan
          </label>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '14px' }}>
            <button type="button" onClick={() => resolveDeterministicFailureChoice('cancel')}>Leave unresolved</button>
            <button type="button" onClick={() => resolveDeterministicFailureChoice('full_original')}>Use full original</button>
            {deterministicFailurePrompt.canBypassScoring ? (
              <button type="button" onClick={() => resolveDeterministicFailureChoice('bypass_scoring')}>Bypass scoring</button>
            ) : null}
          </div>
        </div>
      </div> : null}

      {graphicsChoiceFiles ? <div
        role="dialog"
        aria-modal="true"
        aria-label="High graphical-content risk"
        style={{ position: 'fixed', inset: 0, zIndex: 12000, background: 'rgba(0,0,0,0.6)', display: 'grid', placeItems: 'center' }}
      >
        <div style={{ width: 'min(700px, calc(100vw - 40px))', background: '#151b21', border: '1px solid #465466', borderRadius: '6px', padding: '16px', color: '#dbe3eb' }}>
          <strong style={{ display: 'block', marginBottom: '8px' }}>High graphical-content risk</strong>
          <div style={{ fontSize: '11px', lineHeight: 1.45 }}>
            {graphicsChoiceFiles.join(', ')} may contain visually important evidence outside the deterministic text-selected pages.
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '14px' }}>
            <button type="button" onClick={() => resolveGraphicsExportChoice('cancel')}>Leave unresolved</button>
            <button type="button" onClick={() => resolveGraphicsExportChoice('full_original')}>Use full original document</button>
            <button type="button" onClick={() => resolveGraphicsExportChoice('selected_pages')}>Use deterministic selected pages</button>
          </div>
        </div>
      </div> : null}
<header className="wlv-metadata-tool__header"><button type="button" className="wlv-metadata-tool__back" onClick={onBack}>‹ Toolbox</button><div className="wlv-metadata-tool__title"><h1>Lithology Column Manager</h1><p>Prepare external AI packages, review lithology intervals, and publish approved rows.</p></div><div className="wlv-metadata-tool__window-actions"><button type="button" onClick={clear} disabled={!selectedWellId&&!wellSearch&&candidates.length===0&&supportingFiles.length===0&&fileObjects.length===0} title="Clear the entire Lithology Column Manager workspace">Clear</button><button type="button" className="wlv-metadata-tool__close" aria-label="Close Lithology Column Manager" onClick={onBack}>×</button></div></header>
 <div className="wlv-metadata-tool__input-grid" style={{gridTemplateColumns:'repeat(3,minmax(0,1fr))'}}><section className="wlv-metadata-tool__drop-panel wlv-ftm-tool__well-panel"><div className="wlv-metadata-tool__drop-copy"><strong>Managed Well</strong><span>{selectedWell?(selectedWell.display_name||selectedWell.well_name||selectedWell.well_id):(loadingWells?'Loading wells from the Managed Well Directory…':'Select a managed well')}</span></div><div className="wlv-ftm-tool__well-controls"><input value={wellSearch} onChange={e=>setWellSearch(e.target.value)} placeholder="Search MWD"/><select value={selectedWellId} onChange={e=>{setSelectedWellId(e.target.value);setError(null)}}><option value="">Select a well…</option>{filteredWells.map(w=><option key={w.managed_well_id} value={w.managed_well_id}>{w.display_name||w.well_name||w.well_id}{w.wellbore_name?` — ${w.wellbore_name}`:''}{w.uwi?` (${w.uwi})`:''}</option>)}</select></div></section>
 <section className={`wlv-metadata-tool__drop-panel ${!selectedWellId?'is-disabled':''}`} onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();if(selectedWellId)void handleFiles(e.dataTransfer.files)}}><div className="wlv-metadata-tool__drop-copy"><strong>Supporting Files</strong><span>{fileObjects.length?`${fileObjects.length} staged · ${selectedSupportingFileIndexes.size} selected`:supportingFiles.length?`${supportingFiles.length} file reference(s) remembered · reload required`:(selectedWellId?'Drop PDF, XLSX, CSV, TXT, JSON, image or ZIP bundle here':'Select a managed well first')}</span></div><div style={{display:'flex',alignItems:'center',gap:'6px'}}><button type="button" disabled={!selectedWellId} onClick={()=>fileRef.current?.click()}>Browse</button><button type="button" disabled={!selectedWellId||supportingFiles.length===0} onClick={clearSupportingFiles}>Clear</button></div><input ref={fileRef} type="file" multiple accept=".pdf,.csv,.xlsx,.xls,.txt,.json,.zip,image/*" hidden onChange={e=>{if(e.target.files)void handleFiles(e.target.files);e.currentTarget.value=''}}/></section>
 <section className={`wlv-metadata-tool__drop-panel ${!selectedWellId?'is-disabled':''}`} onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();const f=e.dataTransfer.files?.[0];if(selectedWellId&&f)void importAi(f)}}><div className="wlv-metadata-tool__drop-copy"><strong>Import and Review</strong><span>{selectedWellId?'Drop external CSV, Excel, JSON, ZIP, or MWD round-trip package here':'Select a managed well first'}</span></div><button type="button" disabled={!selectedWellId} onClick={()=>aiRef.current?.click()}>Browse</button><input ref={aiRef} type="file" accept=".zip,.json,.csv,.xlsx,.xls" hidden onChange={e=>{const f=e.target.files?.[0];if(f)void importAi(f);e.currentTarget.value=''}}/></section></div>

      {(fileObjects.length > 0 || skippedArchiveMembers.length > 0) && (
        <section style={{ width: 'calc(100% - 24px)', maxWidth: '1136px', margin: '0 auto 12px', border: '1px solid #34414f', borderRadius: '5px', overflow: 'hidden', background: '#151b21' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', padding: '9px 12px', borderBottom: supportingManifestCollapsed ? undefined : '1px solid #34414f' }}>
            <div style={{ minWidth: 0 }}>
              <strong style={{ display: 'block', fontSize: '11px', color: '#e2e8ef' }}>Supporting file manifest</strong>
              <span style={{ fontSize: '10px', color: '#93a1b0' }}>
                {supportingManifestCollapsed
                  ? `${selectedSupportingFileIndexes.size} selected file${selectedSupportingFileIndexes.size === 1 ? '' : 's'}`
                  : 'Phase 1: select files and screening mode, then Run Pre-Scan. Review Completion Status, Payload and Audit. Phase 2: refine selection and Export AI package.'}
              </span>
            </div>
            <button
              type="button"
              onClick={() => setSupportingManifestCollapsed((current) => !current)}
              aria-expanded={!supportingManifestCollapsed}
              aria-controls="lcm-supporting-file-manifest-body"
              title={supportingManifestCollapsed ? 'Expand supporting file manifest' : 'Collapse supporting file manifest'}
              style={{ flex: '0 0 auto', minWidth: '34px', padding: '4px 8px' }}
            >
              {supportingManifestCollapsed ? '▸' : '▾'}
            </button>
          </div>

          <div id="lcm-supporting-file-manifest-body" hidden={supportingManifestCollapsed}>
            {fileObjects.length > 0 && (
              <div style={{ maxHeight: '280px', overflow: 'auto' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '112px minmax(0,1fr) 82px 128px 132px 92px 42px', alignItems: 'center', minHeight: '32px', color: '#93a1b0', background: '#11171d', borderBottom: '1px solid #293440', fontSize: '10px', fontWeight: 600 }}>
                  <label style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', padding: '7px 14px' }}>
                    <input
                      type="checkbox"
                      checked={fileObjects.length > 0 && selectedSupportingFileIndexes.size === fileObjects.length}
                      onChange={toggleAllSupportingFiles}
                    />
                    SELECT FILES
                  </label>
                  <div style={{ padding: '7px 10px' }}>FILE / ZIP MEMBER</div>
                  <div style={{ padding: '7px 10px' }}>SIZE</div>
                  <label style={{ display: 'inline-flex', alignItems: 'center', gap: '7px', padding: '7px 10px' }}>
                    <input
                      type="checkbox"
                      checked={selectedSupportingFileIndexes.size > 0 && Array.from(selectedSupportingFileIndexes).every((index) => deterministicSupportingFileIndexes.has(index))}
                      disabled={selectedSupportingFileIndexes.size === 0}
                      onChange={toggleAllDeterministicSupportingFiles}
                    />
                    DETERMINISTIC
                  </label>
                  <div style={{ padding: '7px 8px' }}>COMPLETION STATUS</div>
                  <div style={{ padding: '7px 8px' }}>PAYLOAD</div>
                  <div style={{ padding: '7px 4px', textAlign: 'center' }}>AUDIT</div>
                </div>

                {fileObjects.map((file, index) => {
                  const checked = selectedSupportingFileIndexes.has(index);
                  const deterministic = deterministicSupportingFileIndexes.has(index);
                  const audit = supportingFileAuditResults[file.name];
                  const statusLabel = !audit
                    ? 'Pending'
                    : audit.completionStatus === 'screened'
                      ? 'Screened'
                      : audit.completionStatus === 'full_original'
                        ? 'Full original'
                        : audit.completionStatus === 'full_scan_fallback'
                          ? 'Full scan fallback'
                          : audit.completionStatus === 'full_scan_graphics'
                            ? 'Full scan · graphics'
                            : audit.completionStatus === 'excluded'
                              ? 'Excluded'
                              : 'Pending';
                  const payloadLabel = audit?.payloadBytes
                    ? audit.payloadBytes >= 1024 * 1024
                      ? `${(audit.payloadBytes / 1024 / 1024).toFixed(2)} MB`
                      : `${(audit.payloadBytes / 1024).toFixed(1)} KB`
                    : '—';
                  return (
                    <div key={`${file.name}-${index}`} style={{ display: 'grid', gridTemplateColumns: '112px minmax(0,1fr) 82px 128px 132px 92px 42px', alignItems: 'center', minHeight: '34px', borderTop: index ? '1px solid #293440' : undefined, color: '#d6dde5', fontSize: '10px' }}>
                      <div style={{ padding: '7px 14px' }}>
                        <input type="checkbox" checked={checked} onChange={() => toggleSupportingFile(index)} aria-label={`Include ${file.name}`} />
                      </div>
                      <div style={{ padding: '7px 10px', minWidth: 0, overflowWrap: 'anywhere' }}>{file.name}</div>
                      <div style={{ padding: '7px 10px', whiteSpace: 'nowrap', color: '#aeb9c5' }}>
                        {file.size >= 1024 * 1024 ? `${(file.size / 1024 / 1024).toFixed(2)} MB` : `${(file.size / 1024).toFixed(1)} KB`}
                      </div>
                      <div style={{ padding: '7px 10px' }}>
                        <label style={{ display: 'inline-flex', alignItems: 'center', gap: '7px', color: checked ? '#cdd6df' : '#6f7b87' }}>
                          <input type="checkbox" checked={deterministic} disabled={!checked} onChange={() => toggleDeterministicSupportingFile(index)} />
                          {deterministic ? 'Screen' : 'Full'}
                        </label>
                      </div>
                      <div style={{ padding: '7px 8px', whiteSpace: 'nowrap', color: audit ? '#c8d2dc' : '#768493' }}>{statusLabel}</div>
                      <div style={{ padding: '7px 8px', whiteSpace: 'nowrap', color: '#aeb9c5' }}>{payloadLabel}</div>
                      <div style={{ padding: '5px 4px', textAlign: 'center' }}>
                        <button type="button" disabled={!audit} onClick={() => audit && setActiveSupportingFileAudit(audit)} title={audit ? `View audit for ${file.name}` : 'Audit available after pre-scan'}>ⓘ</button>
                      </div>
                    </div>
                  );
                })}

                <div aria-label="Export totals" style={{ display: 'grid', gridTemplateColumns: '112px minmax(0,1fr) 82px 128px 132px 92px 42px', alignItems: 'center', minHeight: '40px', borderTop: '1px solid #4a5968', background: '#11171d', color: '#dbe4ee', fontSize: '10px', fontWeight: 700 }}>
                  <div style={{ padding: '8px 14px', whiteSpace: 'nowrap' }}>EXPORT TOTALS</div>
                  <div style={{ padding: '8px 10px', color: '#aeb9c5', fontWeight: 600 }}>{selectedSupportingFileIndexes.size} selected file{selectedSupportingFileIndexes.size === 1 ? '' : 's'}</div>
                  <div style={{ padding: '8px 10px', whiteSpace: 'nowrap' }}>
                    {(Array.from(selectedSupportingFileIndexes).reduce((sum, index) => sum + Number(fileObjects[index]?.size || 0), 0) / 1024 / 1024).toFixed(2)} MB
                  </div>
                  <div style={{ padding: '8px 10px', color: '#7f8d9b', fontWeight: 600 }}>
                    {Array.from(selectedSupportingFileIndexes).filter((index) => !supportingFilePreScanResults[index]).length
                      ? `${Array.from(selectedSupportingFileIndexes).filter((index) => !supportingFilePreScanResults[index]).length} pending`
                      : 'Ready'}
                  </div>
                  <div style={{ padding: '8px 8px', color: '#aeb9c5', fontWeight: 600 }}>
                    {Array.from(selectedSupportingFileIndexes).every((index) => Boolean(supportingFilePreScanResults[index])) ? 'Ready for export' : 'Selection total'}
                  </div>
                  <div style={{ padding: '8px 8px', whiteSpace: 'nowrap' }}>
                    {(Array.from(selectedSupportingFileIndexes).reduce((sum, index) => sum + Number(supportingFileAuditResults[fileObjects[index]?.name]?.payloadBytes || 0), 0) / 1024 / 1024).toFixed(2)} MB
                  </div>
                  <div />
                </div>
              </div>
            )}

            {skippedArchiveMembers.length > 0 && (
              <details style={{ borderTop: fileObjects.length ? '1px solid #34414f' : undefined }}>
                <summary style={{ cursor: 'pointer', padding: '8px 12px', color: '#c0cad5', fontSize: '10px', fontWeight: 600 }}>
                  Skipped archive members ({skippedArchiveMembers.length})
                </summary>
                <div style={{ maxHeight: '180px', overflow: 'auto', borderTop: '1px solid #293440' }}>
                  {skippedArchiveMembers.map((item, index) => (
                    <div key={`${item.archive}-${item.member}-${index}`} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', padding: '6px 12px', borderTop: index ? '1px solid #242f39' : undefined, fontSize: '9px' }}>
                      <span style={{ color: '#abb7c3', wordBreak: 'break-word' }}>{item.archive}::{item.member}</span>
                      <span style={{ color: '#8e9ba8' }}>{item.reason}</span>
                    </div>
                  ))}
                </div>
              </details>
            )}
          </div>
        </section>
      )}

 <div className="wlv-metadata-tool__action-row"><button type="button" onClick={()=>void runSupportingFilePreScan()} disabled={preScanRunning||!selectedWellId||(supportingFiles.length>0&&fileObjects.length===0)||selectedSupportingFileIndexes.size===0}>{preScanRunning?'Pre-Scanning…':'Run Pre-Scan'}</button><button type="button" onClick={()=>void exportAiPackage()} disabled={preScanRunning||!selectedWellId||selectedSupportingFileIndexes.size===0||!Array.from(selectedSupportingFileIndexes).every(index=>{const result=supportingFilePreScanResults[index];return Boolean(result)&&result.deterministicRequested===deterministicSupportingFileIndexes.has(index)})} title="All currently selected files must have resolved current pre-scan results before AI export.">Export AI package</button><span className="wlv-toolbox-ai-revision" style={{color:'#9ca9b7',fontSize:'10px',fontWeight:600,whiteSpace:'nowrap'}}>{selectedWellId?`AI Review Cycle: ${aiRevision.currentLabel} · Next export: ${aiRevision.nextLabel}`:'AI Review Cycle: —'}</span><button type="button" onClick={()=>void publish()} disabled={!selectedWellId||summary.approved===0}>Publish approved lithology</button><button type="button" onClick={saveReview} disabled={!selectedWellId}>Save review</button><button type="button" onClick={exportCsv} disabled={!candidates.length}>Export CSV</button><button type="button" onClick={addRow} disabled={!selectedWellId}>Add row</button><span className="wlv-metadata-tool__session-summary">{selectedWell?(selectedWell.display_name||selectedWell.well_name||selectedWell.well_id):'No well selected'}{candidates.length?` · ${candidates.length} interval(s)`:''}{summary.approved?` · ${summary.approved} approved`:''}</span></div>
 <div className="wlv-metadata-tool__message" role="status"><span>{error||status}</span><span className="wlv-ftm-tool__counts">{summary.unreviewed} unreviewed · {summary.approved} approved · {summary.rejected} rejected</span></div>
 <section className="wlv-metadata-tool__review"><header>
  <h2>Lithology interval candidates</h2>
  <div
    className="wlv-lcm-tool__bulk-selection"
    style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '6px', marginLeft: 'auto', fontSize: '10px', fontWeight: 600 }}
  >
    <span>{candidates.length || 0}</span>
    <button type="button" onClick={selectAllCandidates} disabled={candidates.length === 0} style={{ fontSize: '10px', fontWeight: 600 }}>Select All</button>
    <button type="button" onClick={clearCandidateSelection} disabled={selectedCandidateIds.size === 0} style={{ fontSize: '10px', fontWeight: 600 }}>Select None</button>
    <button type="button" onClick={acceptSelectedCandidates} disabled={selectedCandidateIds.size === 0} style={{ fontSize: '10px', fontWeight: 600 }}>Accept</button>
  </div>
</header><div className="wlv-metadata-tool__table-wrap wlv-ftm-tool__table-wrap"><table className="wlv-ftm-tool__table wlv-lcm-tool__table"><thead><tr><th>Lithology</th><th>Depth / classification</th><th style={{ paddingRight: '4px' }}>Confidence</th><th style={{ paddingLeft: '4px', paddingRight: '4px' }}>Source</th><th style={{ paddingLeft: '4px' }}>Action</th></tr></thead><tbody>{!candidates.length?<tr><td colSpan={5} className="is-empty">{selectedWellId?'Load supporting files, import a response, or add a row.':'Select a managed well.'}</td></tr>:candidates.map(c=>{const editing=activeEditId===c.id;return <tr key={c.id} className={`is-populated is-${c.state}`}><td className="wlv-metadata-tool__editable-value" onClick={()=>{if(!editing)setActiveEditId(c.id)}}>{editing?<div className="wlv-ftm-tool__edit-stack"><input autoFocus value={c.lithology} placeholder="Lithology" onChange={e=>update(c.id,'lithology',e.target.value)}/><LithologySwatchPicker
  entries={catalogue}
  selectedId={c.canonicalLithology}
  backgroundColor={c.backgroundColor}
  patternColor={c.patternColor}
  onSelect={(entry) => {
    update(c.id,'canonicalLithology',entry?.id||'');
    update(c.id,'patternId',entry?.id||'');
    update(c.id,'backgroundColor',entry?.colors?.defaultBackground||'');
    update(c.id,'patternColor',entry?.colors?.defaultPattern||'');
  }}
/><textarea value={c.description} placeholder="Original description (optional)" onChange={e=>update(c.id,'description',e.target.value)}/></div>:<div className="wlv-lcm-lithology-display">{c.canonicalLithology&&catalogue.find(x=>x.id===c.canonicalLithology)?<img src={`${wlvApiBaseUrl()}/api/wlv/knowledge/lithology/entries/${encodeURIComponent(c.canonicalLithology)}/pattern.svg?background=${encodeURIComponent(c.backgroundColor||catalogue.find(x=>x.id===c.canonicalLithology)?.colors?.defaultBackground||'#ffffff')}&foreground=${encodeURIComponent(c.patternColor||catalogue.find(x=>x.id===c.canonicalLithology)?.colors?.defaultPattern||'#000000')}`} alt=""/>:null}<span><strong>{c.lithology||'—'}</strong>{c.canonicalLithology?<small>{catalogue.find(x=>x.id===c.canonicalLithology)?.name||c.canonicalLithology}</small>:null}</span></div>}</td><td className="wlv-metadata-tool__editable-value" onClick={()=>{if(!editing)setActiveEditId(c.id)}}>{editing?<div className="wlv-ftm-tool__edit-stack"><div className="wlv-ftm-tool__inline-fields"><input value={c.topMd} placeholder="Top MD" onChange={e=>update(c.id,'topMd',e.target.value)}/><input value={c.baseMd} placeholder="Base MD" onChange={e=>update(c.id,'baseMd',e.target.value)}/><input value={c.unit} placeholder="Unit" onChange={e=>update(c.id,'unit',e.target.value)}/><input value={c.depthReference} placeholder="Reference" onChange={e=>update(c.id,'depthReference',e.target.value)}/></div><details className="wlv-lcm-secondary-depths" onClick={e=>e.stopPropagation()}>
  <summary>Additional depth details</summary>
  <div className="wlv-ftm-tool__inline-fields">
    <input value={c.topTvd} placeholder="Top TVD" onChange={e=>update(c.id,'topTvd',e.target.value)}/>
    <input value={c.baseTvd} placeholder="Base TVD" onChange={e=>update(c.id,'baseTvd',e.target.value)}/>
    <input value={c.topTvdss} placeholder="Top TVDSS" onChange={e=>update(c.id,'topTvdss',e.target.value)}/>
    <input value={c.baseTvdss} placeholder="Base TVDSS" onChange={e=>update(c.id,'baseTvdss',e.target.value)}/>
  </div>
</details></div>:<><strong>MD {c.topMd||'—'}–{c.baseMd||'—'} {c.unit}</strong><small>{c.depthReference}{c.topTvd||c.baseTvd?` · TVD ${c.topTvd||'—'}–${c.baseTvd||'—'}`:''}{c.topTvdss||c.baseTvdss?` · TVDSS ${c.topTvdss||'—'}–${c.baseTvdss||'—'}`:''}</small></>}</td><td className="wlv-metadata-tool__editable-value wlv-lcm-tool__confidence" onClick={()=>{if(!editing)setActiveEditId(c.id)}}>{editing?<select value={c.confidence} onChange={e=>update(c.id,'confidence',e.target.value)}><option value="">Select…</option><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></select>:<span className={`wlv-lcm-confidence is-${normalize(c.confidence)||'unset'}`}>{normalize(c.confidence)||'—'}</span>}</td><td className="wlv-metadata-tool__editable-value" onClick={()=>{if(!editing)setActiveEditId(c.id)}}>{editing?<div className="wlv-ftm-tool__edit-stack"><input value={c.source} placeholder="Source" onChange={e=>update(c.id,'source',e.target.value)}/><input value={c.evidence} placeholder="Evidence (optional)" onChange={e=>update(c.id,'evidence',e.target.value)}/><textarea value={c.notes} placeholder="Notes (optional)" onChange={e=>update(c.id,'notes',e.target.value)}/></div>:<><strong>{c.source||'—'}</strong><small>{c.evidence||c.notes||'No supporting detail'}</small></>}</td><td>{c.state==='unreviewed'||c.state==='conflict'||editing?<div className="wlv-metadata-tool__actions"><label style={{ display: 'inline-flex', alignItems: 'center', marginRight: '6px' }} onClick={(event) => event.stopPropagation()} title="Select candidate"><input type="checkbox" checked={selectedCandidateIds.has(c.id)} onChange={() => toggleCandidateSelection(c.id)} aria-label={`Select ${c.lithology || 'interval'}`} style={{ width: '13px', height: '13px', margin: 0 }} /></label><button type="button" onClick={()=>confirm(c.id)}>Approve</button><button type="button" onClick={()=>reject(c.id)}>Reject</button></div>:<span className="wlv-metadata-tool__loaded">{c.state==='rejected'?'Rejected':'Approved'}</span>}</td></tr>})}</tbody></table></div></section></section>
}
export default LithologyColumnManagerPage;
