export type NullableIdentity = string | null | undefined;

export function nonEmptyIdentity(...values: NullableIdentity[]): string | null {
  for (const value of values) {
    const normalized = typeof value === 'string' ? value.trim() : '';
    if (normalized) return normalized;
  }
  return null;
}

export type CurveIdentityContract = {
  managed_curve_uid?: NullableIdentity;
  curve_uid?: NullableIdentity;
  managed_product_uid?: NullableIdentity;
  product_id?: NullableIdentity;
  display_curve_id?: NullableIdentity;
  curve_id?: NullableIdentity;
};

export function canonicalCurveIdentity(
  curve: CurveIdentityContract,
  fallback: string,
): string {
  return nonEmptyIdentity(
    curve.managed_curve_uid,
    curve.curve_uid,
    curve.managed_product_uid,
    curve.product_id,
    curve.display_curve_id,
    curve.curve_id,
    fallback,
  ) ?? fallback;
}

export function canonicalProductIdentity(
  product: Pick<CurveIdentityContract, 'managed_product_uid' | 'product_id'>,
): string | null {
  return nonEmptyIdentity(product.managed_product_uid, product.product_id);
}

export function legacyProductId(
  product: Pick<CurveIdentityContract, 'product_id'>,
  fallback: string,
): string {
  return nonEmptyIdentity(product.product_id, fallback) ?? fallback;
}
