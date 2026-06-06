import React from 'react';
import { type DisplayMode, type DisplayPresetId, type RasterColorMap } from './seismic2dDisplay';

type ProcessingMode = 'raw' | 'demean' | 'trace_rms' | 'agc';
type FrequencyFilter = 'none' | 'bandpass';
type WiggleStyle = 'line' | 'variable_area';
type WiggleFill = 'none' | 'positive' | 'negative' | 'both';

type Props = {
  displayControlsOpen: boolean;
  setDisplayControlsOpen: React.Dispatch<React.SetStateAction<boolean>>;
  displayMode: DisplayMode;
  setDisplayMode: React.Dispatch<React.SetStateAction<DisplayMode>>;
  rasterColorMap: RasterColorMap;
  setRasterColorMap: React.Dispatch<React.SetStateAction<RasterColorMap>>;
  displayPreset: DisplayPresetId;
  applyDisplayPreset: (presetId: DisplayPresetId) => void;
  fitToWidth: boolean;
  setFitToWidth: React.Dispatch<React.SetStateAction<boolean>>;
  reverseDirection: boolean;
  setReverseDirection: React.Dispatch<React.SetStateAction<boolean>>;

  amplitudeControlsOpen: boolean;
  setAmplitudeControlsOpen: React.Dispatch<React.SetStateAction<boolean>>;
  processingMode: ProcessingMode;
  setProcessingMode: React.Dispatch<React.SetStateAction<ProcessingMode>>;
  agcWindowSec: number;
  setAgcWindowSec: React.Dispatch<React.SetStateAction<number>>;
  frequencyFilter: FrequencyFilter;
  setFrequencyFilter: React.Dispatch<React.SetStateAction<FrequencyFilter>>;
  clipPercentile: number;
  setClipPercentile: React.Dispatch<React.SetStateAction<number>>;
  gain: number;
  setGain: React.Dispatch<React.SetStateAction<number>>;
  reversePolarity: boolean;
  setReversePolarity: React.Dispatch<React.SetStateAction<boolean>>;

  wiggleControlsOpen: boolean;
  setWiggleControlsOpen: React.Dispatch<React.SetStateAction<boolean>>;
  wiggleStyle: WiggleStyle;
  setWiggleStyle: React.Dispatch<React.SetStateAction<WiggleStyle>>;
  wiggleFill: WiggleFill;
  setWiggleFill: React.Dispatch<React.SetStateAction<WiggleFill>>;
  wiggleScale: number;
  setWiggleScale: React.Dispatch<React.SetStateAction<number>>;
  wiggleTraceSpacing: number;
  setWiggleTraceSpacing: React.Dispatch<React.SetStateAction<number>>;
  traceDecimation: string;
  setTraceDecimation: React.Dispatch<React.SetStateAction<string>>;
  showWiggleZeroLine: boolean;
  setShowWiggleZeroLine: React.Dispatch<React.SetStateAction<boolean>>;

  gridAxisControlsOpen: boolean;
  setGridAxisControlsOpen: React.Dispatch<React.SetStateAction<boolean>>;
  showTimelines: boolean;
  setShowTimelines: React.Dispatch<React.SetStateAction<boolean>>;
  timelineIntervalMs: number;
  setTimelineIntervalMs: React.Dispatch<React.SetStateAction<number>>;
  showAxisLabels: boolean;
  setShowAxisLabels: React.Dispatch<React.SetStateAction<boolean>>;

  zoomControlsOpen: boolean;
  setZoomControlsOpen: React.Dispatch<React.SetStateAction<boolean>>;
  boxZoomEnabled: boolean;
  setBoxZoomEnabled: React.Dispatch<React.SetStateAction<boolean>>;
  resetZoom: () => void;
  resetView: () => void;
  zoomLevel: number;
  canStepZoomOut: boolean;
  canResetZoom: boolean;
  applyStepZoom: (direction: 'in' | 'out') => void;
};

const sectionStyle: React.CSSProperties = {
  borderTop: '1px solid #444',
  paddingTop: 12,
  marginTop: 12,
};

const sectionTitleStyle: React.CSSProperties = {
  fontSize: 12,
  fontWeight: 700,
  textTransform: 'uppercase',
  color: '#cbd5e1',
};

const rowStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '90px 1fr',
  gap: 8,
  alignItems: 'center',
  marginBottom: 8,
  fontSize: 12,
};

const selectStyle: React.CSSProperties = {
  width: '100%',
  background: '#111',
  color: 'white',
  border: '1px solid #555',
  padding: '4px 6px',
  fontSize: 12,
};

const checkboxRowStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  fontSize: 12,
  marginBottom: 8,
};

const valueStyle: React.CSSProperties = {
  color: '#9ca3af',
  fontSize: 11,
  marginTop: 2,
};

const sectionButtonStyle: React.CSSProperties = {
  ...sectionTitleStyle,
  width: '100%',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  background: 'transparent',
  border: 'none',
  color: '#cbd5e1',
  cursor: 'pointer',
  padding: '0 0 8px 0',
  textAlign: 'left',
};

function SectionButton({ open, label, onClick }: { open: boolean; label: string; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} style={sectionButtonStyle}>
      <span>{open ? '▾' : '▸'} {label}</span>
    </button>
  );
}

export default function Seismic2DControlsPanel(props: Props) {
  return (
    <>
      <div style={sectionStyle}>
        <SectionButton open={props.displayControlsOpen} label="Display" onClick={() => props.setDisplayControlsOpen((value) => !value)} />
        {props.displayControlsOpen && (
          <>
            <div style={rowStyle}>
              <label>Mode</label>
              <select value={props.displayMode} onChange={(e) => props.setDisplayMode(e.target.value as DisplayMode)} style={selectStyle}>
                <option value="raster">Raster</option>
                <option value="wiggle">Wiggle</option>
                <option value="raster_wiggle">Raster + Wiggle</option>
              </select>
            </div>
            <div style={rowStyle}>
              <label>Raster map</label>
              <select value={props.rasterColorMap} onChange={(e) => props.setRasterColorMap(e.target.value as RasterColorMap)} style={selectStyle}>
                <option value="gray_balanced">Gray balanced</option>
                <option value="gray_high_contrast">Gray high contrast</option>
                <option value="reverse_gray">Reverse gray</option>
                <option value="seismic_rwb">Seismic R-W-B</option>
                <option value="seismic_bwr">Seismic B-W-R</option>
                <option value="black_white_black">Black-white-black</option>
                <option value="brown_white_blue">Brown-white-blue</option>
                <option value="blue_white_brown">Blue-white-brown</option>
              </select>
            </div>
            <div style={rowStyle}>
              <label>Preset</label>
              <select value={props.displayPreset} onChange={(e) => props.applyDisplayPreset(e.target.value as DisplayPresetId)} style={selectStyle}>
                <option value="standard_interpretation">Standard interpretation</option>
                <option value="high_contrast_dip">High-contrast dip</option>
                <option value="polarity_qc">Polarity QC</option>
                <option value="wiggle_qc">Wiggle QC</option>
                <option value="image_wiggle">Raster + Wiggle</option>
                <option value="soft_regional">Soft regional</option>
              </select>
            </div>
            <label style={checkboxRowStyle}>
              <input type="checkbox" checked={props.fitToWidth} onChange={(e) => props.setFitToWidth(e.target.checked)} />
              Fit width
            </label>
            <label style={checkboxRowStyle}>
              <input type="checkbox" checked={props.reverseDirection} onChange={(e) => props.setReverseDirection(e.target.checked)} />
              Reverse direction
            </label>
          </>
        )}
      </div>

      <div style={sectionStyle}>
        <SectionButton open={props.amplitudeControlsOpen} label="Amplitude" onClick={() => props.setAmplitudeControlsOpen((value) => !value)} />
        {props.amplitudeControlsOpen && (
          <>
            <div style={rowStyle}>
              <label>Process</label>
              <select value={props.processingMode} onChange={(e) => props.setProcessingMode(e.target.value as ProcessingMode)} style={selectStyle}>
                <option value="raw">Raw</option>
                <option value="demean">Demean</option>
                <option value="trace_rms">Trace RMS</option>
                <option value="agc">AGC</option>
              </select>
            </div>
            {props.processingMode === 'agc' && (
              <div style={rowStyle}>
                <label>AGC window</label>
                <select value={props.agcWindowSec} onChange={(e) => props.setAgcWindowSec(parseFloat(e.target.value))} style={selectStyle}>
                  <option value={0.2}>0.2 sec</option>
                  <option value={0.5}>0.5 sec</option>
                  <option value={1.0}>1.0 sec</option>
                </select>
              </div>
            )}
            <div style={rowStyle}>
              <label>Filter</label>
              <select value={props.frequencyFilter} onChange={(e) => props.setFrequencyFilter(e.target.value as FrequencyFilter)} style={selectStyle}>
                <option value="none">None</option>
                <option value="bandpass">Bandpass</option>
              </select>
            </div>
            {props.frequencyFilter === 'bandpass' && (
              <div style={rowStyle}>
                <label>Bandpass</label>
                <div style={valueStyle}>8 / 12 / 80 / 100 Hz</div>
              </div>
            )}
            <div style={rowStyle}>
              <label>Clip</label>
              <select value={props.clipPercentile} onChange={(e) => props.setClipPercentile(parseFloat(e.target.value))} style={selectStyle}>
                <option value={95}>P95</option>
                <option value={98}>P98</option>
                <option value={99}>P99</option>
                <option value={99.5}>P99.5</option>
                <option value={99.9}>P99.9</option>
              </select>
            </div>
            <div style={rowStyle}>
              <label>Gain</label>
              <div>
                <input type="range" min={0.1} max={10} step={0.1} value={props.gain} onChange={(e) => props.setGain(parseFloat(e.target.value))} style={{ width: '100%' }} />
                <div style={valueStyle}>{props.gain.toFixed(1)}×</div>
              </div>
            </div>
            <label style={checkboxRowStyle}>
              <input type="checkbox" checked={props.reversePolarity} onChange={(e) => props.setReversePolarity(e.target.checked)} />
              Reverse polarity
            </label>
          </>
        )}
      </div>

      <div style={sectionStyle}>
        <SectionButton open={props.wiggleControlsOpen} label="Wiggle" onClick={() => props.setWiggleControlsOpen((value) => !value)} />
        {props.wiggleControlsOpen && (
          <>
            <div style={rowStyle}>
              <label>Style</label>
              <select value={props.wiggleStyle} onChange={(e) => props.setWiggleStyle(e.target.value as WiggleStyle)} style={selectStyle}>
                <option value="line">Line only</option>
                <option value="variable_area">Variable area</option>
              </select>
            </div>
            <div style={rowStyle}>
              <label>Fill</label>
              <select value={props.wiggleFill} onChange={(e) => props.setWiggleFill(e.target.value as WiggleFill)} style={selectStyle}>
                <option value="none">None</option>
                <option value="positive">Positive</option>
                <option value="negative">Negative</option>
                <option value="both">Both</option>
              </select>
            </div>
            <div style={rowStyle}>
              <label>Scale</label>
              <div>
                <input type="range" min={0.2} max={5} step={0.1} value={props.wiggleScale} onChange={(e) => props.setWiggleScale(parseFloat(e.target.value))} style={{ width: '100%' }} />
                <div style={valueStyle}>{props.wiggleScale.toFixed(1)}×</div>
              </div>
            </div>
            <div style={rowStyle}>
              <label>Trace spacing</label>
              <div>
                <input type="range" min={0.5} max={3} step={0.1} value={props.wiggleTraceSpacing} onChange={(e) => props.setWiggleTraceSpacing(parseFloat(e.target.value))} style={{ width: '100%' }} />
                <div style={valueStyle}>{props.wiggleTraceSpacing.toFixed(1)}×</div>
              </div>
            </div>
            <div style={rowStyle}>
              <label>Trace step</label>
              <select value={props.traceDecimation} onChange={(e) => props.setTraceDecimation(e.target.value)} style={selectStyle}>
                <option value="auto">Auto</option>
                <option value="1">1</option>
                <option value="2">2</option>
                <option value="4">4</option>
                <option value="8">8</option>
                <option value="16">16</option>
                <option value="32">32</option>
                <option value="64">64</option>
              </select>
            </div>
            <div style={rowStyle}>
              <label>Zero line</label>
              <select value={props.showWiggleZeroLine ? 'on' : 'off'} onChange={(e) => props.setShowWiggleZeroLine(e.target.value === 'on')} style={selectStyle}>
                <option value="on">On</option>
                <option value="off">Off</option>
              </select>
            </div>
          </>
        )}
      </div>

      <div style={sectionStyle}>
        <SectionButton open={props.gridAxisControlsOpen} label="Grid / Axis" onClick={() => props.setGridAxisControlsOpen((value) => !value)} />
        {props.gridAxisControlsOpen && (
          <>
            <label style={checkboxRowStyle}>
              <input type="checkbox" checked={props.showTimelines} onChange={(e) => props.setShowTimelines(e.target.checked)} />
              Time grid
            </label>
            {props.showTimelines && (
              <div style={rowStyle}>
                <label>Interval</label>
                <select value={props.timelineIntervalMs} onChange={(e) => props.setTimelineIntervalMs(parseInt(e.target.value, 10))} style={selectStyle}>
                  <option value={100}>100 ms</option>
                  <option value={250}>250 ms</option>
                  <option value={500}>500 ms</option>
                  <option value={1000}>1000 ms</option>
                </select>
              </div>
            )}
            <label style={checkboxRowStyle}>
              <input type="checkbox" checked={props.showAxisLabels} onChange={(e) => props.setShowAxisLabels(e.target.checked)} />
              Axis labels
            </label>
          </>
        )}
      </div>

      <div style={sectionStyle}>
        <SectionButton open={props.zoomControlsOpen} label="Zoom" onClick={() => props.setZoomControlsOpen((value) => !value)} />
        {props.zoomControlsOpen && (
          <>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '32px 32px 1fr',
                gap: 8,
                alignItems: 'center',
                marginBottom: 8,
              }}
            >
              <button
                type="button"
                onClick={() => props.applyStepZoom('in')}
                title="Increase the current 2D zoom level without redrawing the zoom box"
                style={{
                  height: 28,
                  width: 32,
                  border: '1px solid #666',
                  background: 'transparent',
                  color: '#eee',
                  cursor: 'pointer',
                  fontSize: 18,
                  lineHeight: 1,
                }}
              >
                +
              </button>
              <button
                type="button"
                onClick={() => props.applyStepZoom('out')}
                disabled={!props.canStepZoomOut}
                title="Decrease the current 2D zoom level without redrawing the zoom box"
                style={{
                  height: 28,
                  width: 32,
                  border: '1px solid #666',
                  background: 'transparent',
                  color: props.canStepZoomOut ? '#eee' : '#777',
                  cursor: props.canStepZoomOut ? 'pointer' : 'not-allowed',
                  fontSize: 18,
                  lineHeight: 1,
                }}
              >
                −
              </button>
              <div
                style={{
                  color: '#cfcfcf',
                  fontSize: 12,
                  fontVariantNumeric: 'tabular-nums',
                  textAlign: 'right',
                }}
              >
                Zoom: {Number(props.zoomLevel || 1).toFixed(2)}x
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
              <label style={{ ...checkboxRowStyle, margin: 0, flex: 1 }}>
                <input type="checkbox" checked={props.boxZoomEnabled} onChange={(e) => props.setBoxZoomEnabled(e.target.checked)} />
                Box zoom
              </label>
              <button
                type="button"
                onClick={props.resetZoom}
                disabled={!props.canResetZoom}
                title="Reset zoom scale only"
                style={{
                  padding: '4px 8px',
                  background: 'transparent',
                  color: props.canResetZoom ? '#eee' : '#777',
                  border: '1px solid #666',
                  cursor: props.canResetZoom ? 'pointer' : 'not-allowed',
                  whiteSpace: 'nowrap',
                  fontSize: 12,
                }}
              >
                Reset zoom
              </button>
            </div>
            <button
              type="button"
              onClick={props.resetView}
              title="Reset the current 2D line to its original loaded view"
              style={{
                width: '100%',
                padding: '6px 8px',
                background: 'transparent',
                color: '#eee',
                border: '1px solid #666',
                cursor: 'pointer',
                marginTop: 8,
              }}
            >
              Reset view
            </button>
          </>
        )}
      </div>
    </>
  );
}
