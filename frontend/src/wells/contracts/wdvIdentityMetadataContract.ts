export interface WdvMetadataValue {
  key: string;
  label: string;
  value: string | number | null;
  unit: string | null;
  source?: string | null;
}

export interface WdvMetadataSection {
  key: string;
  label: string;
  values: readonly WdvMetadataValue[];
}

export interface WdvIdentityMetadataContract {
  contract_kind: 'wdv_metadata';
  contract_version: 'wdv_metadata_v1';
  managed_well_uid: string;
  source_format: string | null;
  sections: readonly WdvMetadataSection[];
}

export function parseWdvIdentityMetadataContract(
  payload: unknown,
  managedWellUid: string,
): WdvIdentityMetadataContract {
  if (!payload || typeof payload !== 'object') {
    throw new Error('Backend WDV metadata contract is not an object');
  }
  const contract = payload as Partial<WdvIdentityMetadataContract>;
  if (
    contract.contract_kind !== 'wdv_metadata'
    || contract.contract_version !== 'wdv_metadata_v1'
    || contract.managed_well_uid !== managedWellUid
    || !Array.isArray(contract.sections)
  ) {
    throw new Error('Invalid backend WDV identity/metadata contract');
  }
  return contract as WdvIdentityMetadataContract;
}

export function metadataSection(
  contract: WdvIdentityMetadataContract | null,
  key: string,
): WdvMetadataSection | null {
  return contract?.sections.find((section) => section.key === key) ?? null;
}
