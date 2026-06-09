# WLV Backend Runtime Operations

## Purpose

This document defines the backend runtime operations foundation for the
MultiViewer Well Log Viewer. The goal is to align WLV backend operation with
the Seismic Data Viewer style: first-class backend service, repeatable
start/stop/restart/status/validate scripts, deterministic health/status
contracts, and a clear path to enterprise/container deployment.

## Runtime defaults

- Host: `127.0.0.1`
- Port: `8010`
- Environment variables:
  - `WLV_PROJECT`
  - `WLV_BACKEND_HOST`
  - `WLV_BACKEND_PORT`
  - `WLV_BACKEND_ENV`

The local desktop runtime is treated as a single-node deployment profile, not
as a local-only design.

## Scripts

- `scripts/wlv_backend_start.sh`
- `scripts/wlv_backend_stop.sh`
- `scripts/wlv_backend_restart.sh`
- `scripts/wlv_backend_status.sh`
- `scripts/wlv_backend_validate.sh`

These scripts are non-destructive. They do not modify well data, viewer data,
LAS files, curve inventories, or interval records.

## Health and status endpoints

- `/health`
- `/api/wlv/health`
- `/api/wlv/system/status`

`/api/wlv/system/status` is the operational status contract for service checks,
runtime validation, and future enterprise health probes.

## Maintenance policy

BE-002 creates runtime/ops structure only. Destructive maintenance actions are
not implemented in this block. Future maintenance functions must remain
backend-owned, explicit, test-covered, and non-ambiguous.
