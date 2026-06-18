export type InventoryActionWellReference = {
  managed_well_uid?: string | null;
  managed_well_id: string;
};

export type InventoryActionProductReference = {
  managed_product_uid?: string | null;
  product_id: string;
};

type InventoryActionPayload = {
  managed_well_uid?: string;
  managed_well_id?: string;
  managed_product_uids?: string[];
  product_ids?: string[];
};

type InventoryRemovalPayload = {
  managed_well_uids?: string[];
  managed_well_ids?: string[];
  managed_product_uids?: string[];
  product_ids?: string[];
};

function nonEmpty(value: string | null | undefined): string | null {
  const normalized = value?.trim() ?? '';
  return normalized.length > 0 ? normalized : null;
}

function productReferences(products: InventoryActionProductReference[]): {
  managed_product_uids: string[];
  product_ids: string[];
} {
  const managedProductUids: string[] = [];
  const legacyProductIds: string[] = [];

  products.forEach((product) => {
    const managedProductUid = nonEmpty(product.managed_product_uid);
    if (managedProductUid) {
      managedProductUids.push(managedProductUid);
      return;
    }

    const productId = nonEmpty(product.product_id);
    if (productId) legacyProductIds.push(productId);
  });

  return {
    managed_product_uids: [...new Set(managedProductUids)],
    product_ids: [...new Set(legacyProductIds)],
  };
}

export function buildInventoryActionPayload(
  well: InventoryActionWellReference,
  products: InventoryActionProductReference[],
): InventoryActionPayload {
  const managedWellUid = nonEmpty(well.managed_well_uid);
  const managedWellId = nonEmpty(well.managed_well_id);
  const productPayload = productReferences(products);

  if (!managedWellUid && !managedWellId) {
    throw new Error('Inventory action requires a managed well identity.');
  }

  return {
    ...(managedWellUid
      ? { managed_well_uid: managedWellUid }
      : { managed_well_id: managedWellId as string }),
    ...(productPayload.managed_product_uids.length > 0
      ? { managed_product_uids: productPayload.managed_product_uids }
      : {}),
    ...(productPayload.product_ids.length > 0
      ? { product_ids: productPayload.product_ids }
      : {}),
  };
}

export function buildInventoryRemovalPayload(
  wells: InventoryActionWellReference[],
  products: InventoryActionProductReference[],
): InventoryRemovalPayload {
  const managedWellUids: string[] = [];
  const legacyWellIds: string[] = [];

  wells.forEach((well) => {
    const managedWellUid = nonEmpty(well.managed_well_uid);
    if (managedWellUid) {
      managedWellUids.push(managedWellUid);
      return;
    }

    const managedWellId = nonEmpty(well.managed_well_id);
    if (managedWellId) legacyWellIds.push(managedWellId);
  });

  const productPayload = productReferences(products);

  return {
    ...(managedWellUids.length > 0
      ? { managed_well_uids: [...new Set(managedWellUids)] }
      : {}),
    ...(legacyWellIds.length > 0
      ? { managed_well_ids: [...new Set(legacyWellIds)] }
      : {}),
    ...(productPayload.managed_product_uids.length > 0
      ? { managed_product_uids: productPayload.managed_product_uids }
      : {}),
    ...(productPayload.product_ids.length > 0
      ? { product_ids: productPayload.product_ids }
      : {}),
  };
}
