export type WbvInteractionMode = 'none' | 'point' | 'interval';

export type WbvScreenObservationV2 = {
  pointer_x_px: number;
  pointer_y_px: number;
  viewport_width_px: number;
  viewport_height_px: number;
  view_projection_matrix: number[];
  activation_tolerance_px: number;
};

export type WbvAuthoritativePointV2 = {
  md: number;
  tvd: number;
  tvdss: number | null;
  inclination: number | null;
  azimuth: number | null;
  dogleg_severity: number | null;
  x: number;
  y: number;
  z: number;
  segment_index: number;
  segment_ratio: number;
  screen_distance_px: number;
};

export type WbvSavedIntervalV2 = {
  interval_id: string;
  managed_well_id: string;
  trajectory_id: string | null;
  trajectory_revision_uid: string | null;
  start: WbvAuthoritativePointV2;
  end: WbvAuthoritativePointV2;
  top_md: number;
  base_md: number;
  depth_unit: string;
  created_at: string;
  updated_at: string;
};

export type WbvInteractionStateV2 = {
  contract_kind: 'wbv_interaction_state';
  contract_version: 'wbv_interaction_state_v2';
  managed_well_id: string;
  revision: number;
  selection_mode: WbvInteractionMode;
  selected_point_visible: boolean;
  interval_visible: boolean;
  selected_point: WbvAuthoritativePointV2 | null;
  interval_draft_start: WbvAuthoritativePointV2 | null;
  saved_interval: WbvSavedIntervalV2 | null;
  active_tracking_session_id: string | null;
  tracking_status: 'idle' | 'tracking' | 'committed' | 'cancelled' | 'expired';
  fallback_status: 'none' | 'backend_unavailable' | 'trajectory_unavailable' | 'stale_command';
  updated_at: string;
};

export type WbvObservationCommandV2 = {
  observation: WbvScreenObservationV2;
  expected_revision?: number;
};

export type WbvTrackCommandV2 = {
  session_id?: string;
  sequence: number;
  observation?: WbvScreenObservationV2;
  expected_revision?: number;
};
