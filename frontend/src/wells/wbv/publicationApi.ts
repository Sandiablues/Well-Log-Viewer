import { fetchWlvJson } from '../../api/wlvBackendClient';
import { createCanonicalCommandId } from '../wdv/canonicalCommandId';

export type WbvPublishPreview = {
  managed_well_uid: string;
  source_session_uid: string;
  source_revision: number;
  track_count: number;
  assignment_count: number;
  fill_rule_count: number;
  warnings: string[];
  publishable: boolean;
};

export type WbvTrackPresentationOverride = {
  track_uid: string;
  destination_track_uid: string | null;
  visible: boolean;
  geometry_type: 'camera_ribbon' | 'radial_panel';
  radial_lane: number | null;
  radial_offset: number | null;
  angular_position_deg: number | null;
  radial_width: number | null;
  thickness: number | null;
  orientation_mode: 'follow_trajectory' | 'camera_facing';
  opacity: number | null;
  label_visible: boolean | null;
};

export type WbvCurvePresentationOverride = {
  assignment_uid: string;
  visible: boolean | null;
  color: string | null;
  opacity: number | null;
  line_width: number | null;
  radial_exaggeration: number | null;
  label_visible: boolean | null;
  label_content: 'mnemonic' | 'mnemonic_value' | 'scale' | 'mnemonic_scale' | null;
  label_anchor: 'top' | 'base' | 'custom_md' | null;
  label_custom_md: number | null;
  label_size: number | null;
  label_weight: number | null;
  label_alignment: 'left' | 'center' | 'right' | null;
  label_position: 'on_track' | 'left' | 'right' | 'center' | null;
  label_horizontal_adjustment: number | null;
  label_vertical_adjustment: number | null;
  scale_color: string | null;
  scale_opacity: number | null; // deprecated compatibility field; scale is always opaque
  scale_line_width: number | null;
  scale_size: number | null;
};

export type WbvPresentationOverrides = {
  package_visible: boolean;
  track_spacing: number | null;
  depth_clip_min: number | null;
  depth_clip_max: number | null;
  tracks: WbvTrackPresentationOverride[];
  curves: WbvCurvePresentationOverride[];
};

export type WbvPublishedAssignment = {
  assignment_uid: string;
  observed_mnemonic: string;
  display_name: string;
  unit: string | null;
  visible: boolean;
  line_width: number;
  line_opacity: number;
};

export type WbvPublishedTrack = {
  track_uid: string;
  track_name: string;
  track_number: number;
  track_type: string;
  visible: boolean;
  assignments: WbvPublishedAssignment[];
};

export type WbvPublishedSnapshot = {
  revision: number;
  tracks: WbvPublishedTrack[];
  curve_fills: Array<{ rule_uid: string }>;
};

export type WbvOverlayPackage = {
  package_uid: string;
  managed_well_uid: string;
  package_name: string;
  package_revision: number;
  status: 'active' | 'inactive' | 'archived';
  source_wdv_session_uid: string;
  source_wdv_revision: number;
  created_at: string;
  updated_at: string;
  published_snapshot: WbvPublishedSnapshot;
  wbv_overrides: WbvPresentationOverrides;
};

export type WbvOverlayPackageList = {
  managed_well_uid: string;
  packages: WbvOverlayPackage[];
};

export type WbvPackageChangeSummary = {
  source_revision_from: number;
  source_revision_to: number;
  tracks_added: string[];
  tracks_removed: string[];
  tracks_changed: string[];
  assignments_added: string[];
  assignments_removed: string[];
  assignments_changed: string[];
  fills_added: string[];
  fills_removed: string[];
  fills_changed: string[];
  retained_track_override_count: number;
  dropped_track_override_count: number;
  retained_curve_override_count: number;
  dropped_curve_override_count: number;
};

export type WbvUpdatePreview = {
  managed_well_uid: string;
  package_uid: string;
  package_revision: number;
  source_session_uid: string;
  source_revision: number;
  update_available: boolean;
  publishable: boolean;
  warnings: string[];
  changes: WbvPackageChangeSummary;
};

export type WbvUpdateExistingResult = {
  package: WbvOverlayPackage;
  changes: WbvPackageChangeSummary;
};

function wellBase(managedWellUid: string): string {
  return `/api/wlv/wbv/publications/wells/${encodeURIComponent(managedWellUid)}`;
}

export async function previewWdvPublication(managedWellUid: string, packageName: string): Promise<WbvPublishPreview> {
  return fetchWlvJson<WbvPublishPreview>(`${wellBase(managedWellUid)}/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ package_name: packageName, published_by: 'local_user' }),
  });
}

export async function publishWdvAsNewWbvPackage(managedWellUid: string, packageName: string): Promise<WbvOverlayPackage> {
  return fetchWlvJson<WbvOverlayPackage>(`${wellBase(managedWellUid)}/packages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      package_name: packageName,
      published_by: 'local_user',
      command_uid: createCanonicalCommandId(),
      activate: true,
    }),
  });
}


export async function previewWbvPackageUpdate(managedWellUid: string, packageUid: string): Promise<WbvUpdatePreview> {
  return fetchWlvJson<WbvUpdatePreview>(
    `${wellBase(managedWellUid)}/packages/${encodeURIComponent(packageUid)}/update-preview`,
    { method: 'POST' },
  );
}

export async function updateExistingWbvPackage(
  managedWellUid: string,
  packageUid: string,
  expectedPackageRevision: number,
): Promise<WbvUpdateExistingResult> {
  return fetchWlvJson<WbvUpdateExistingResult>(
    `${wellBase(managedWellUid)}/packages/${encodeURIComponent(packageUid)}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        command_uid: createCanonicalCommandId(),
        expected_package_revision: expectedPackageRevision,
        published_by: 'local_user',
        activate: true,
      }),
    },
  );
}

export async function listWbvOverlayPackages(
  managedWellUid: string,
  includeArchived = true,
): Promise<WbvOverlayPackageList> {
  return fetchWlvJson<WbvOverlayPackageList>(
    `${wellBase(managedWellUid)}/packages?include_archived=${includeArchived ? 'true' : 'false'}`,
  );
}

export async function changeWbvOverlayPackageLifecycle(
  managedWellUid: string,
  packageUid: string,
  expectedPackageRevision: number,
  action: 'archive' | 'restore',
): Promise<WbvOverlayPackage> {
  return fetchWlvJson<WbvOverlayPackage>(
    `${wellBase(managedWellUid)}/packages/${encodeURIComponent(packageUid)}/lifecycle`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        expected_package_revision: expectedPackageRevision,
        action,
      }),
    },
  );
}

export async function deleteWbvOverlayPackage(
  managedWellUid: string,
  packageUid: string,
  expectedPackageRevision: number,
): Promise<void> {
  await fetchWlvJson<unknown>(
    `${wellBase(managedWellUid)}/packages/${encodeURIComponent(packageUid)}?expected_package_revision=${expectedPackageRevision}`,
    { method: 'DELETE' },
  );
}

export function publishedWbvRenderPackageUrl(managedWellUid: string, packageUid: string): string {
  return `${wellBase(managedWellUid)}/packages/${encodeURIComponent(packageUid)}/render-package`;
}


export async function setWbvOverlayPackageActive(
  managedWellUid: string,
  packageUid: string,
  active: boolean,
): Promise<WbvOverlayPackage> {
  return fetchWlvJson<WbvOverlayPackage>(
    `${wellBase(managedWellUid)}/packages/${encodeURIComponent(packageUid)}/active`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ active }),
    },
  );
}

export async function updateWbvPresentationOverrides(
  managedWellUid: string,
  packageUid: string,
  expectedPackageRevision: number,
  overrides: WbvPresentationOverrides,
): Promise<WbvOverlayPackage> {
  return fetchWlvJson<WbvOverlayPackage>(
    `${wellBase(managedWellUid)}/packages/${encodeURIComponent(packageUid)}/presentation`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        expected_package_revision: expectedPackageRevision,
        overrides,
      }),
    },
  );
}

export type WbvLayoutTrackType = 'curve' | 'depth' | 'formation_tops' | 'lithology' | 'core' | 'casing_hole' | 'completions' | 'borehole_imagery';
export type WbvTrackPosition = 'right' | 'left' | 'center';
export type WbvLayoutTrack = {
  track_uid: string; display_name: string; track_type: WbvLayoutTrackType; display_order: number; visible: boolean;
  position: WbvTrackPosition; angular_position_deg: number; distance_from_wellbore: number; previous_track_gap: number;
  width: number; opacity: number; background_mode: 'transparent' | 'solid'; background_color: string;
  outline_visible: boolean; grid_mode: 'off' | 'linear' | 'logarithmic';
  depth_type: 'MD' | 'TVD' | 'TVDSS'; depth_increment: number; label_increment: number; label_size: number; show_depth_units: boolean;
};
export type WbvTrackLayout = { contract_version: 'wbv_track_layout_v1'; managed_well_uid: string; revision: number; tracks: WbvLayoutTrack[] };
export type WbvLayoutCommand = {
  expected_revision: number; command: 'add_track'|'update_track'|'delete_track'|'duplicate_track'|'move_up'|'move_down';
  track_uid?: string; display_name?: string; track_type?: WbvLayoutTrackType; position?: WbvTrackPosition;
  distance_from_wellbore?: number; previous_track_gap?: number; width?: number; opacity?: number;
  background_mode?: 'transparent' | 'solid'; background_color?: string;
  outline_visible?: boolean; grid_mode?: 'off' | 'linear' | 'logarithmic'; visible?: boolean;
  depth_type?: 'MD' | 'TVD' | 'TVDSS'; depth_increment?: number; label_increment?: number; label_size?: number; show_depth_units?: boolean;
};

export async function getWbvTrackLayout(managedWellUid: string): Promise<WbvTrackLayout> {
  return fetchWlvJson<WbvTrackLayout>(`/api/wlv/wbv/layouts/wells/${encodeURIComponent(managedWellUid)}`);
}
export async function commandWbvTrackLayout(managedWellUid: string, command: WbvLayoutCommand): Promise<WbvTrackLayout> {
  return fetchWlvJson<WbvTrackLayout>(`/api/wlv/wbv/layouts/wells/${encodeURIComponent(managedWellUid)}/commands`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(command),
  });
}
