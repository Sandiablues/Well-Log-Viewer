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
