import type { CurveAssignment, CurveCatalogItem } from '../prototype/trackLayoutModel';

export class CurveIdentityContractError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'CurveIdentityContractError';
  }
}

export type CurveIdentityIndex = Readonly<{
  canonicalByAlias: ReadonlyMap<string, string>;
  curveByCanonical: ReadonlyMap<string, CurveCatalogItem>;
  ambiguousAliases: ReadonlySet<string>;
}>;

function normalizeIdentity(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const normalized = value.trim();
  return normalized.length > 0 ? normalized : null;
}

export function canonicalCurveKey(curve: CurveCatalogItem): string {
  const key = normalizeIdentity(curve.curveUid) ?? normalizeIdentity(curve.curveId);
  if (!key) throw new CurveIdentityContractError('Curve catalog item has no usable identity');
  return key;
}

export function buildCurveIdentityIndex(curves: readonly CurveCatalogItem[]): CurveIdentityIndex {
  const canonicalByAlias = new Map<string, string>();
  const curveByCanonical = new Map<string, CurveCatalogItem>();
  const ambiguousAliases = new Set<string>();

  for (const curve of curves) {
    const canonical = canonicalCurveKey(curve);
    if (curveByCanonical.has(canonical)) {
      throw new CurveIdentityContractError(`Duplicate canonical curve identity: ${canonical}`);
    }
    curveByCanonical.set(canonical, curve);

    const aliases = new Set<string>();
    [canonical, curve.curveUid, curve.curveId, ...(curve.identityAliases ?? [])].forEach((value) => {
      const alias = normalizeIdentity(value);
      if (alias) aliases.add(alias);
    });

    for (const alias of aliases) {
      if (ambiguousAliases.has(alias)) continue;
      const existing = canonicalByAlias.get(alias);
      if (existing && existing !== canonical) {
        canonicalByAlias.delete(alias);
        ambiguousAliases.add(alias);
      } else {
        canonicalByAlias.set(alias, canonical);
      }
    }
  }

  return { canonicalByAlias, curveByCanonical, ambiguousAliases };
}

export function resolveCanonicalCurveKey(
  index: CurveIdentityIndex,
  ...identityCandidates: readonly unknown[]
): string | null {
  for (const candidate of identityCandidates) {
    const alias = normalizeIdentity(candidate);
    if (!alias || index.ambiguousAliases.has(alias)) continue;
    const canonical = index.canonicalByAlias.get(alias);
    if (canonical) return canonical;
  }
  return null;
}

export function resolveAssignmentCanonicalCurveKey(
  index: CurveIdentityIndex,
  assignment: Pick<CurveAssignment, 'curveUid' | 'curveId'>,
): string | null {
  return resolveCanonicalCurveKey(index, assignment.curveUid, assignment.curveId);
}

export function canonicalizeCurveIdentitySet(
  index: CurveIdentityIndex,
  identities: Iterable<string>,
): Set<string> {
  const result = new Set<string>();
  for (const identity of identities) {
    const canonical = resolveCanonicalCurveKey(index, identity);
    if (canonical) result.add(canonical);
  }
  return result;
}

export function canonicalizeCurveUsageCounts(
  index: CurveIdentityIndex,
  counts: ReadonlyMap<string, number>,
): Map<string, number> {
  const result = new Map<string, number>();
  for (const [identity, count] of counts.entries()) {
    const canonical = resolveCanonicalCurveKey(index, identity);
    if (!canonical) continue;
    result.set(canonical, (result.get(canonical) ?? 0) + count);
  }
  return result;
}
