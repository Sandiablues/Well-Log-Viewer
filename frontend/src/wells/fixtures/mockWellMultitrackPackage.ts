/**
 * MultiViewer Well Log Viewer — Mock well_multitrack_v1 Fixture
 * WL-BUILD-001B
 *
 * Two exports:
 *   mockWellMultitrackPackage — conforms to WellMultitrackV1 contract exactly.
 *   mockCurveSamples          — synthetic curve sample data for inspection rendering.
 *                               NOT part of the WellMultitrackV1 contract.
 *                               In production, samples come from each curve's samples_url.
 *
 * Architecture note:
 *   mockCurveSamples is used ONLY by InspectionShell → WellLogViewerPage →
 *   MultiViewerWellLogViewer → VidExWellLogRenderer for proof-of-render.
 *   It must not appear in production data paths.
 *   The WellMultitrackV1 object remains contract-compliant; it carries only
 *   samples_url pointers, not embedded data.
 *
 * Sample data is deterministic (no Math.random).
 * GR/RHOB/NPHI/CALI curves are synthetic but geologically plausible.
 * Well: 34/10-23 SA, Norwegian North Sea.
 */

import type { WellMultitrackV1 } from '../types';

// ── Deterministic curve data generators ───────────────────────────────────

/** Generate a depth array at even spacing. */
function depthArray(minMD: number, maxMD: number, count: number): number[] {
  const step = (maxMD - minMD) / (count - 1);
  return Array.from({ length: count }, (_, i) => minMD + i * step);
}

/**
 * GR (Gamma Ray) — API units, 0–150 range.
 * Oscillates between clean sands (~25 API) and shale (~100 API).
 */
function generateGR(depths: number[]): [number, number][] {
  return depths.map((d, i) => {
    const v = 65 + 42 * Math.sin(i * 0.58 + 0.4)
                 + 18 * Math.sin(i * 2.1 - 0.7)
                 +  8 * Math.sin(i * 4.3 + 1.1);
    return [d, Math.round(Math.max(5, Math.min(145, v)) * 10) / 10];
  });
}

/**
 * RHOB (Bulk Density) — g/cm³, 1.95–2.95 range.
 * Shorter interval: 2340–4210 m (QAQC finding: range mismatch).
 */
function generateRHOB(depths: number[]): [number, number][] {
  return depths.map((d, i) => {
    const v = 2.48 + 0.22 * Math.sin(i * 0.72 + 1.2)
                   + 0.07 * Math.sin(i * 3.1 - 0.3)
                   + 0.03 * Math.sin(i * 5.6 + 0.9);
    return [d, Math.round(Math.max(1.95, Math.min(2.95, v)) * 1000) / 1000];
  });
}

/**
 * NPHI (Neutron Porosity) — v/v, −0.15–0.45 range.
 * Nulls in 2800–3104 m (QAQC finding: excessive null).
 */
function generateNPHI(depths: number[]): [number, number | null][] {
  return depths.map((d, i) => {
    // Null zone per QAQC finding
    if (d >= 2800 && d <= 3104) return [d, null];
    const v = 0.20 + 0.13 * Math.sin(i * 0.68 + 2.1)
                   + 0.04 * Math.sin(i * 2.8 - 0.5)
                   + 0.02 * Math.sin(i * 5.1 + 1.3);
    return [d, Math.round(Math.max(-0.15, Math.min(0.45, v)) * 10000) / 10000];
  });
}

/**
 * CALI (Caliper) — inches, 6–20 range.
 * Mostly near bit size (12.25 in) with washouts.
 */
function generateCALI(depths: number[]): [number, number][] {
  return depths.map((d, i) => {
    const v = 12.25 + 1.8 * Math.sin(i * 0.51 + 0.8)
                    + 0.6 * Math.sin(i * 1.9 - 1.1)
                    + 0.3 * Math.sin(i * 4.2 + 0.4);
    return [d, Math.round(Math.max(6, Math.min(20, v)) * 100) / 100];
  });
}

// ── Depth domains ─────────────────────────────────────────────────────────

const WELL_MIN_MD  = 2340.0;
const WELL_MAX_MD  = 4582.5;
const RHOB_MAX_MD  = 4210.0; // shorter per QAQC finding

const SAMPLE_COUNT = 60;     // enough for smooth curve rendering

const allDepths  = depthArray(WELL_MIN_MD, WELL_MAX_MD, SAMPLE_COUNT);
const rhobDepths = depthArray(WELL_MIN_MD, RHOB_MAX_MD, Math.round(SAMPLE_COUNT * 0.81));

// ── Mock curve samples (proof-of-render only) ─────────────────────────────

/**
 * Synthetic curve samples for WL-BUILD-001B proof-of-render.
 *
 * Format: [depth_m, value] pairs — matches ViDEx LinePlot data convention.
 * Keyed by curve_id matching the WellMultitrackV1 fixture.
 *
 * In production, samples are fetched from each curve's samples_url.
 * This object must not be used in production paths.
 */
export const mockCurveSamples: Record<string, [number, number | null][]> = {
  'curve-depth-md': allDepths.map((d) => [d, d]),
  'curve-gr':       generateGR(allDepths),
  'curve-rhob':     generateRHOB(rhobDepths),
  'curve-nphi':     generateNPHI(allDepths),
  'curve-cali':     generateCALI(allDepths),
};

// ── Mock well_multitrack_v1 package ───────────────────────────────────────

/**
 * Mock well_multitrack_v1 viewer package — conforms exactly to WellMultitrackV1.
 * All data is synthetic. For visual inspection and proof-of-render only.
 */
export const mockWellMultitrackPackage: WellMultitrackV1 = {
  viewer_package_version: 'well_multitrack_v1',

  dataset_id:        'mock-ds-34-10-23S',
  representation_id: 'mock-rep-lasv2-triple-combo',

  well_id:     '34/10-23 S',
  wellbore_id: '34/10-23 SA',

  display_domain: 'MD',
  depth_unit:     'm',
  depth_range:    { min: WELL_MIN_MD, max: WELL_MAX_MD },

  tracks: [
    {
      track_id:   'track-depth',
      track_type: 'depth',
      title:      'DEPTH',
      curves: [{
        curve_id:        'curve-depth-md',
        mnemonic:        'DEPT',
        normalized_name: 'measured_depth',
        unit:            'm',
        samples_url:     '/api/wells/mock-ds-34-10-23S/representations/mock-rep-lasv2-triple-combo/curves/DEPT/samples',
        scale: { type: 'linear', min: WELL_MIN_MD, max: WELL_MAX_MD },
      }],
    },
    {
      track_id:   'track-gr',
      track_type: 'curve',
      title:      'Gamma Ray',
      curves: [{
        curve_id:        'curve-gr',
        mnemonic:        'GR',
        normalized_name: 'gamma_ray',
        unit:            'API',
        samples_url:     '/api/wells/mock-ds-34-10-23S/representations/mock-rep-lasv2-triple-combo/curves/GR/samples',
        scale: { type: 'linear', min: 0, max: 150 },
      }],
    },
    {
      track_id:   'track-density-neutron',
      track_type: 'curve',
      title:      'Density / Neutron',
      curves: [
        {
          curve_id:        'curve-rhob',
          mnemonic:        'RHOB',
          normalized_name: 'bulk_density',
          unit:            'g/cm3',
          samples_url:     '/api/wells/mock-ds-34-10-23S/representations/mock-rep-lasv2-triple-combo/curves/RHOB/samples',
          scale: { type: 'linear', min: 1.95, max: 2.95 },
        },
        {
          curve_id:        'curve-nphi',
          mnemonic:        'NPHI',
          normalized_name: 'neutron_porosity',
          unit:            'v/v',
          samples_url:     '/api/wells/mock-ds-34-10-23S/representations/mock-rep-lasv2-triple-combo/curves/NPHI/samples',
          scale: { type: 'linear', min: -0.15, max: 0.45 },
        },
      ],
    },
    {
      track_id:   'track-cali',
      track_type: 'curve',
      title:      'Caliper',
      curves: [{
        curve_id:        'curve-cali',
        mnemonic:        'CALI',
        normalized_name: 'borehole_diameter',
        unit:            'in',
        samples_url:     '/api/wells/mock-ds-34-10-23S/representations/mock-rep-lasv2-triple-combo/curves/CALI/samples',
        scale: { type: 'linear', min: 6, max: 20 },
      }],
    },
  ],

  qaqc_findings: [
    {
      finding_id:  'mock-finding-001',
      severity:    'info',
      code:        'CURVE_UNIT_UNRECOGNIZED',
      object_type: 'curve',
      object_id:   'curve-cali',
      message:     "CALI: unit 'in' is not in the normalised unit registry. Curve displayed with raw unit label.",
    },
    {
      finding_id:  'mock-finding-002',
      severity:    'warning',
      code:        'CURVE_EXCESSIVE_NULL',
      object_type: 'curve',
      object_id:   'curve-nphi',
      message:     'NPHI: 34.2% null samples in interval 2800.0–3104.5 m MD. Exceeds 25% null threshold. Check source for splice gap.',
    },
    {
      finding_id:  'mock-finding-003',
      severity:    'error',
      code:        'CURVE_DEPTH_RANGE_MISMATCH',
      object_type: 'curve',
      object_id:   'curve-rhob',
      message:     'RHOB: samples cover 2340.0–4210.0 m but well depth range is 2340.0–4582.5 m. 372.5 m of logged interval has no density data.',
    },
  ],
};
