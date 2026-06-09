# WLV Managed Well Inventory

This block adds the backend-owned Managed Well Inventory foundation for the
MultiViewer Well Log Viewer.

The inventory layer is the WLV equivalent of the Seismic Data Viewer MSI
boundary. It is responsible for managed well records, source-file references,
viewer-package references, and durable persistence behind a repository/service
contract.

## Current scope

- Local JSON persistence for the single-node desktop/runtime profile.
- Thin API routes under `/api/wlv/inventory`.
- Repository and service layers separated from route handlers.
- Seed registration for the current Forge 21-31 prototype well.
- Non-destructive list/detail/status/viewer-package endpoints.

## API endpoints

- `GET /api/wlv/inventory/health`
- `GET /api/wlv/inventory/status`
- `GET /api/wlv/inventory/wells`
- `GET /api/wlv/inventory/wells/{managed_well_id}`
- `POST /api/wlv/inventory/wells/register-seed`
- `GET /api/wlv/inventory/viewer-packages`

## Storage

Default local storage path:

```text
backend/data/managed_inventory/managed_wells.json
```

Override with:

```text
WLV_MANAGED_INVENTORY_PATH=/path/to/managed_wells.json
```

The JSON repository is intentionally replaceable. Future enterprise deployment
can replace it with SQLite/Postgres/object-catalog persistence without changing
the API contract.

## Rules preserved

- Backend owns inventory truth.
- Frontend does not infer or mutate inventory state.
- No frontend migration in this block.
- No destructive delete/cleanup action in this block.
- No LAS upload/import workflow in this block.
- No launcher changes in this block.

## BE-005 persistence and lifecycle hardening

The Managed Well Inventory now treats lifecycle state as a first-class backend
contract. Each managed well record carries both the legacy `status` field and
the explicit `lifecycle_state` field. They should remain aligned until a later
migration removes the legacy status naming from downstream consumers.

Current lifecycle states:

- `registered` — known to the inventory but not yet checked for availability.
- `available` — source references are present and the record can be used by
  backend workflows.
- `viewer_ready` — at least one backend viewer-package reference is registered.
- `stale` — record requires refresh because source or derived state changed.
- `invalid` — record failed integrity checks or cannot be trusted.
- `archived` — retained but not normally active.
- `review_required` — record requires manual review before use.
- `error` — operational error state.

The local JSON repository remains the single-node persistence implementation,
but it is isolated behind `ManagedWellInventoryRepository` so it can later be
replaced by SQLite, Postgres, or object/catalog storage without changing the
API contract.

Non-destructive maintenance endpoints:

- `GET /api/wlv/inventory/validate` validates inventory integrity without
  mutating records.
- `GET /api/wlv/inventory/maintenance/status` reports maintenance readiness and
  explicitly states that destructive actions are disabled.

Validation checks include duplicate managed ids, duplicate well ids, duplicate
viewer-package ids, missing required identifiers, invalid depth ranges, source
reference gaps, viewer-ready records without viewer packages, and status /
lifecycle mismatches.

No delete, remove, archive, or destructive repair endpoint is enabled in this
block.
