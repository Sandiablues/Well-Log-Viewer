export type ManagedWellUid = string & { readonly __brand: 'ManagedWellUid' };
export type ManagedWellboreUid = string & { readonly __brand: 'ManagedWellboreUid' };
export type ManagedCurveUid = string & { readonly __brand: 'ManagedCurveUid' };
export type ManagedProductUid = string & { readonly __brand: 'ManagedProductUid' };
export type ManagedSourceUid = string & { readonly __brand: 'ManagedSourceUid' };
export type AssignmentUid = string & { readonly __brand: 'AssignmentUid' };
export type SessionUid = string & { readonly __brand: 'SessionUid' };
export type TrackUid = string & { readonly __brand: 'TrackUid' };

const UUIDV7_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export class WdvIdentityContractError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'WdvIdentityContractError';
  }
}

function requireRecord(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new WdvIdentityContractError(`${label} must be an object`);
  }
  return value as Record<string, unknown>;
}

function requireString(value: unknown, field: string): string {
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw new WdvIdentityContractError(`${field} must be a non-blank string`);
  }
  return value.trim();
}

function optionalString(value: unknown, field: string): string | null {
  if (value === null || typeof value === 'undefined') return null;
  if (typeof value !== 'string') {
    throw new WdvIdentityContractError(`${field} must be a string or null`);
  }
  const normalized = value.trim();
  return normalized.length > 0 ? normalized : null;
}

function requireUuid7<T extends string>(value: unknown, field: string): T {
  const normalized = requireString(value, field);
  if (!UUIDV7_PATTERN.test(normalized)) {
    throw new WdvIdentityContractError(`${field} must be a UUIDv7`);
  }
  return normalized as T;
}

export function asManagedWellUid(value: unknown): ManagedWellUid {
  return requireUuid7<ManagedWellUid>(value, 'managed_well_uid');
}

export function asManagedWellboreUid(value: unknown): ManagedWellboreUid {
  return requireUuid7<ManagedWellboreUid>(value, 'managed_wellbore_uid');
}

export function asManagedCurveUid(value: unknown): ManagedCurveUid {
  return requireUuid7<ManagedCurveUid>(value, 'managed_curve_uid');
}

export function asManagedProductUid(value: unknown): ManagedProductUid {
  return requireUuid7<ManagedProductUid>(value, 'managed_product_uid');
}

export function asManagedSourceUid(value: unknown): ManagedSourceUid {
  return requireUuid7<ManagedSourceUid>(value, 'managed_source_uid');
}

export function asAssignmentUid(value: unknown): AssignmentUid {
  return requireUuid7<AssignmentUid>(value, 'assignment_uid');
}

export function asSessionUid(value: unknown): SessionUid {
  return requireUuid7<SessionUid>(value, 'session_uid');
}

export function asTrackUid(value: unknown): TrackUid {
  return requireUuid7<TrackUid>(value, 'track_uid');
}

export interface CanonicalCurveCatalogItemV21 {
  managedCurveUid: ManagedCurveUid;
  managedProductUid: ManagedProductUid;
  managedWellUid: ManagedWellUid;
  managedWellboreUid: ManagedWellboreUid | null;
  managedSourceUid: ManagedSourceUid;
  krCurveTypeId: string | null;
  observedMnemonic: string;
  normalizedMnemonic: string | null;
  displayName: string;
  unit: string | null;
  curveFamily: string | null;
  description: string | null;
}

export interface CanonicalCurveAssignmentIdentityV21 {
  assignmentUid: AssignmentUid;
  managedCurveUid: ManagedCurveUid;
  managedProductUid: ManagedProductUid;
  managedWellUid: ManagedWellUid;
  managedWellboreUid: ManagedWellboreUid | null;
  managedSourceUid: ManagedSourceUid;
  trackUid: TrackUid;
}

const FORBIDDEN_ACTIVE_IDENTITY_FIELDS = [
  'curve_id',
  'curve_uid',
  'product_id',
  'display_curve_id',
  'canonical_curve_id',
  'mnemonic',
] as const;

function rejectForbiddenIdentityFields(record: Record<string, unknown>, label: string): void {
  const present = FORBIDDEN_ACTIVE_IDENTITY_FIELDS.filter((field) => (
    Object.prototype.hasOwnProperty.call(record, field)
  ));
  if (present.length > 0) {
    throw new WdvIdentityContractError(
      `${label} contains forbidden active identity fields: ${present.join(', ')}`,
    );
  }
}

export function parseCanonicalCurveCatalogItemV21(
  value: unknown,
): CanonicalCurveCatalogItemV21 {
  const record = requireRecord(value, 'WDV curve');

  if (record.contract_version !== 'wdv_identity_v2_1') {
    throw new WdvIdentityContractError(
      'WDV curve contract_version must be wdv_identity_v2_1',
    );
  }
  rejectForbiddenIdentityFields(record, 'WDV curve');

  return {
    managedCurveUid: asManagedCurveUid(record.managed_curve_uid),
    managedProductUid: asManagedProductUid(record.managed_product_uid),
    managedWellUid: asManagedWellUid(record.managed_well_uid),
    managedWellboreUid:
      record.managed_wellbore_uid === null || typeof record.managed_wellbore_uid === 'undefined'
        ? null
        : asManagedWellboreUid(record.managed_wellbore_uid),
    managedSourceUid: asManagedSourceUid(record.managed_source_uid),
    krCurveTypeId: optionalString(record.kr_curve_type_id, 'kr_curve_type_id'),
    observedMnemonic: requireString(record.observed_mnemonic, 'observed_mnemonic'),
    normalizedMnemonic: optionalString(record.normalized_mnemonic, 'normalized_mnemonic'),
    displayName: requireString(record.display_name, 'display_name'),
    unit: optionalString(record.unit, 'unit'),
    curveFamily: optionalString(record.curve_family, 'curve_family'),
    description: optionalString(record.description, 'description'),
  };
}

export function parseCanonicalAssignmentIdentityV21(
  value: unknown,
): CanonicalCurveAssignmentIdentityV21 {
  const record = requireRecord(value, 'WDV assignment');
  rejectForbiddenIdentityFields(record, 'WDV assignment');

  return {
    assignmentUid: asAssignmentUid(record.assignment_uid),
    managedCurveUid: asManagedCurveUid(record.managed_curve_uid),
    managedProductUid: asManagedProductUid(record.managed_product_uid),
    managedWellUid: asManagedWellUid(record.managed_well_uid),
    managedWellboreUid:
      record.managed_wellbore_uid === null || typeof record.managed_wellbore_uid === 'undefined'
        ? null
        : asManagedWellboreUid(record.managed_wellbore_uid),
    managedSourceUid: asManagedSourceUid(record.managed_source_uid),
    trackUid: asTrackUid(record.track_uid),
  };
}

export function indexCanonicalCurvesByUid(
  curves: readonly CanonicalCurveCatalogItemV21[],
): ReadonlyMap<ManagedCurveUid, CanonicalCurveCatalogItemV21> {
  const index = new Map<ManagedCurveUid, CanonicalCurveCatalogItemV21>();
  for (const curve of curves) {
    if (index.has(curve.managedCurveUid)) {
      throw new WdvIdentityContractError(
        `Duplicate managed_curve_uid: ${curve.managedCurveUid}`,
      );
    }
    index.set(curve.managedCurveUid, curve);
  }
  return index;
}

export function canonicalCurveByUid(
  curves: readonly CanonicalCurveCatalogItemV21[],
  managedCurveUid: ManagedCurveUid,
): CanonicalCurveCatalogItemV21 {
  const curve = curves.find((item) => item.managedCurveUid === managedCurveUid);
  if (!curve) {
    throw new WdvIdentityContractError(
      `Unknown managed_curve_uid: ${managedCurveUid}`,
    );
  }
  return curve;
}
