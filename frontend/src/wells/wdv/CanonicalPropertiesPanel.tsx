import { useEffect, useMemo, useState } from 'react';
import type { CanonicalSessionCommandV21, CanonicalViewerSessionV21 } from '../prototype/canonicalViewerPackageV21';
import type { CurveAssignmentV21, CurveCatalogItemV21, CurveTrackV21 } from '../prototype/trackLayoutModelV21';
import { curveByManagedUidV21 } from '../prototype/trackLayoutModelV21';
import type { CanonicalWdvSelection } from './canonicalSelection';
import { removeCurveFillCommand, updateAssignmentCommand, updateTrackCommand, upsertCurveFillCommand } from './canonicalCommandBuilders';
import { loadCurveFillCapabilities } from './curveFillApi';
import type { CurveFillCapabilities, CurveFillMode } from './curveFillApi';

export interface CanonicalPropertiesPanelProps {
  session: CanonicalViewerSessionV21;
  curves: readonly CurveCatalogItemV21[];
  selection: CanonicalWdvSelection;
  depthUnit: string;
  onCommand: (command: CanonicalSessionCommandV21) => void;
}

function EmptyProperties() {
  return <aside className="wlv-canonical-properties"><header className="wlv-canonical-panel-header"><div><strong>Properties</strong><span>No selection</span></div></header><div className="wlv-canonical-properties-empty">Select a track or an assigned curve to edit its display properties.</div></aside>;
}

function CurveFillControls({session,track,assignment,curve,curves,depthUnit,onCommand}:{session:CanonicalViewerSessionV21;track:CurveTrackV21;assignment:CurveAssignmentV21;curve:CurveCatalogItemV21;curves:readonly CurveCatalogItemV21[];depthUnit:string;onCommand:(command:CanonicalSessionCommandV21)=>void}) {
  const persistedFill=(session.curveFills ?? []).find((item)=>item.ownerAssignmentUid===assignment.assignmentUid) ?? null;
  const [capabilities,setCapabilities]=useState<CurveFillCapabilities|null>(null);
  const [capabilityError,setCapabilityError]=useState<string|null>(null);
  const [mode,setMode]=useState<CurveFillMode>(persistedFill?.fillMode ?? assignment.fillSide);
  const [comparisonCurveUid,setComparisonCurveUid]=useState<string>(persistedFill?.operandBCurveUid ?? assignment.pairedManagedCurveUid ?? '');
  const [condition,setCondition]=useState<'a_greater_than_b'|'a_less_than_b'>(persistedFill?.condition ?? 'a_greater_than_b');
  const [fillColor,setFillColor]=useState(persistedFill?.fill ?? assignment.fillColor);
  const [opacity,setOpacity]=useState(persistedFill?.opacity ?? assignment.fillOpacity/100);
  const [deadband,setDeadband]=useState<number|null>(persistedFill?.deadband ?? null);
  const [minimumInterval,setMinimumInterval]=useState<number|null>(persistedFill?.minimumInterval ?? null);

  useEffect(()=>{ let cancelled=false; setCapabilities(null); setCapabilityError(null); void loadCurveFillCapabilities(session.managedWellUid,track.trackUid,assignment.assignmentUid).then((value)=>{if(!cancelled)setCapabilities(value);}).catch((error:unknown)=>{if(!cancelled)setCapabilityError(error instanceof Error?error.message:String(error));}); return()=>{cancelled=true;}; },[session.managedWellUid,session.revision,track.trackUid,assignment.assignmentUid]);
  const eligibleOperands=useMemo(()=>capabilities?.operands.filter((item)=>item.available && item.eligibleFillModes.includes(mode as 'between'|'conditional'|'crossover')) ?? [],[capabilities,mode]);
  useEffect(()=>{ if(eligibleOperands.some((item)=>item.identity===comparisonCurveUid))return; setComparisonCurveUid(eligibleOperands[0]?.identity ?? ''); },[eligibleOperands,comparisonCurveUid]);

  const applyFill=()=>{
    if(mode==='none'||mode==='left'||mode==='right'||mode==='between'){
      if(persistedFill){ onCommand(removeCurveFillCommand(session.revision,persistedFill.fillUid)); return; }
      onCommand(updateAssignmentCommand(session.revision,assignment.assignmentUid,{fillSide:mode,fillColor,fillOpacity:Math.round(opacity*100),pairedManagedCurveUid:mode==='between'&&comparisonCurveUid?comparisonCurveUid as typeof assignment.managedCurveUid:null})); return;
    }
    const operand=capabilities?.operands.find((item)=>item.identity===comparisonCurveUid);
    const comparisonCurve=curves.find((item)=>item.managedCurveUid===comparisonCurveUid);
    if(!operand||!comparisonCurve)return;
    const preset=capabilities?.presets.find((item)=>item.available&&item.fillMode===mode&&operand.presetIds.includes(item.presetId));
    onCommand(upsertCurveFillCommand({revision:session.revision,fillUid:persistedFill?.fillUid,trackUid:track.trackUid,ownerAssignmentUid:assignment.assignmentUid,ownerCurveUid:assignment.managedCurveUid,comparisonCurveUid,managedWellUid:session.managedWellUid,ownerUnit:curve.unit,comparisonUnit:comparisonCurve.unit,fillMode:mode,condition:mode==='conditional'?condition:null,overlayPolicyId:mode==='crossover'?preset?.overlayPolicyId??null:null,overlayPolicyRevision:mode==='crossover'?preset?.overlayPolicyRevision??null:null,fill:fillColor,opacity,deadband,minimumInterval,depthUnit}));
  };

  return <fieldset className="wlv-canonical-fill-controls"><legend>Curve Fill</legend>
    <label><span>Fill mode</span><select value={mode} onChange={(event)=>setMode(event.target.value as CurveFillMode)}>{(capabilities?.modes ?? []).map((item)=><option key={item.mode} value={item.mode} disabled={!item.available}>{item.label}{item.available?'':` — ${item.reason?.message ?? 'Unavailable'}`}</option>)}</select></label>
    {capabilityError?<div className="wlv-canonical-action-error" role="alert">{capabilityError}</div>:null}
    {(mode==='between'||mode==='conditional'||mode==='crossover')?<label><span>{mode==='crossover'?'Comparison curve':'Against'}</span><select value={comparisonCurveUid} onChange={(event)=>setComparisonCurveUid(event.target.value)}>{eligibleOperands.map((item)=><option key={item.identity} value={item.identity}>{item.displayName}{item.unit?` (${item.unit})`:''}</option>)}</select></label>:null}
    {mode==='conditional'?<label><span>Condition</span><select value={condition} onChange={(event)=>setCondition(event.target.value as typeof condition)}><option value="a_greater_than_b">{curve.displayName} greater than selected operand</option><option value="a_less_than_b">{curve.displayName} less than selected operand</option></select></label>:null}
    {mode!=='none'?<><label><span>Fill color</span><input type="color" value={fillColor} onChange={(event)=>setFillColor(event.target.value)}/></label><label><span>Opacity</span><input type="number" min={0} max={1} step={0.05} value={opacity} onChange={(event)=>setOpacity(Number(event.target.value))}/></label></>:null}
    {(mode==='conditional'||mode==='crossover')?<><label><span>Deadband</span><input type="number" min={0} step="any" value={deadband??''} onChange={(event)=>setDeadband(event.target.value===''?null:Number(event.target.value))}/></label><label><span>Minimum interval ({depthUnit})</span><input type="number" min={0} step="any" value={minimumInterval??''} onChange={(event)=>setMinimumInterval(event.target.value===''?null:Number(event.target.value))}/></label></>:null}
    <button type="button" disabled={(mode==='between'||mode==='conditional'||mode==='crossover')&&!comparisonCurveUid} onClick={applyFill}>Apply Fill</button>
  </fieldset>;
}

export function CanonicalPropertiesPanel({session,curves,selection,depthUnit,onCommand}:CanonicalPropertiesPanelProps){
  if(selection.kind==='none')return <EmptyProperties/>;
  const track=session.tracks.find((item)=>item.trackUid===selection.trackUid); if(!track)return <EmptyProperties/>;
  if(selection.kind==='track'||track.trackType!=='curve')return <aside className="wlv-canonical-properties"><header className="wlv-canonical-panel-header"><div><strong>Track Properties</strong><span>{track.title}</span></div></header><div className="wlv-canonical-properties-form"><label><span>Track title</span><input value={track.title} onChange={(event)=>onCommand(updateTrackCommand(session.revision,track.trackUid,{title:event.target.value}))}/></label><label><span>Width</span><input type="number" min={80} max={600} value={track.widthPx} onChange={(event)=>onCommand(updateTrackCommand(session.revision,track.trackUid,{widthPx:Number(event.target.value)}))}/></label></div></aside>;
  const assignment=track.curves.find((item)=>item.assignmentUid===selection.assignmentUid); if(!assignment)return <EmptyProperties/>;
  const curve=curveByManagedUidV21(curves,assignment.managedCurveUid);
  return <aside className="wlv-canonical-properties"><header className="wlv-canonical-panel-header"><div><strong>Curve Properties</strong><span>{curve.observedMnemonic} · {curve.unit??'No unit'}</span></div></header><div className="wlv-canonical-properties-summary"><strong>{curve.displayName}</strong><span>{track.title}</span></div><div className="wlv-canonical-properties-form">
    <label><span>Scale minimum</span><input type="number" value={assignment.scaleMin??''} onChange={(event)=>{const value=Number(event.target.value);if(Number.isFinite(value)&&assignment.scaleMax!==null)onCommand(updateAssignmentCommand(session.revision,assignment.assignmentUid,{scaleMin:value,scaleMax:assignment.scaleMax}));}}/></label>
    <label><span>Scale maximum</span><input type="number" value={assignment.scaleMax??''} onChange={(event)=>{const value=Number(event.target.value);if(Number.isFinite(value)&&assignment.scaleMin!==null)onCommand(updateAssignmentCommand(session.revision,assignment.assignmentUid,{scaleMin:assignment.scaleMin,scaleMax:value}));}}/></label>
    <label><span>Line color</span><input type="color" value={assignment.color} onChange={(event)=>onCommand(updateAssignmentCommand(session.revision,assignment.assignmentUid,{color:event.target.value}))}/></label>
    <CurveFillControls session={session} track={track} assignment={assignment} curve={curve} curves={curves} depthUnit={depthUnit} onCommand={onCommand}/>
    <label className="wlv-canonical-checkbox-label"><span>Visible</span><input type="checkbox" checked={assignment.visible} onChange={(event)=>onCommand(updateAssignmentCommand(session.revision,assignment.assignmentUid,{visible:event.target.checked}))}/></label>
  </div></aside>;
}
