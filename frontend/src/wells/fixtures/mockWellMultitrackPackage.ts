import type { WellMultitrackV1 } from '../types';

export const mockCurveSamples: Record<string, [number, number | null][]> = {};

export const mockWellMultitrackPackage = {
  viewer_package_version: 'well_multitrack_v1',
  dataset_id: '',
  representation_id: '',
  well_id: '',
  wellbore_id: '',
  display_domain: 'MD',
  depth_unit: 'm',
  depth_range: { min: 0, max: 1 },
  tracks: [],
  qaqc_findings: [],
} as WellMultitrackV1;
