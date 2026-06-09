# WLV Source Ingestion Architecture

This block establishes the format-neutral Well Log Source Ingestion foundation
for the MultiViewer Well Log Viewer.

The ingestion service is deliberately not LAS-only. LAS is the first concrete
numeric-curve adapter target, but the backend contract is designed for multiple
wellbore-log source classes:

- LAS: numeric curve logs.
- DLIS: future frame/channel/run logs.
- CGM: future vector/raster log artifacts.
- TIFF/TIF: future raster log or scanned image artifacts.
- PDF: future supporting document or raster log path.
- UNKNOWN: registered/reviewable source that is not importable until classified.

## Layered model

```text
Source file
  -> format detection
  -> adapter boundary
  -> normalized well-log package
  -> QAQC / metadata evidence
  -> Managed Well Inventory
  -> viewer package
```

## Current endpoints

- `GET /api/wlv/ingestion/health`
- `GET /api/wlv/ingestion/supported-formats`
- `POST /api/wlv/ingestion/detect-format`

## Current implementation status

This is an architecture block. It adds deterministic format detection by file
extension and a stable adapter registry. It does not yet parse LAS, DLIS, CGM,
TIFF, or PDF payloads.

## Enterprise path

The service boundary is independent of local files, future object storage,
database-backed inventory, and distributed workers. Later adapters can write
normalized outputs into the Managed Well Inventory without changing the public
format-detection contract.
## BE-007 LAS adapter implementation

The first concrete adapter is LAS, but the ingestion architecture remains
format-neutral. LAS registration now flows through:

```text
/api/wlv/ingestion/sources/register
  -> WellLogSourceIngestionService
  -> LasSourceAdapter
  -> NormalizedWellLogPackage
  -> ManagedWellInventoryService
```

The LAS adapter extracts well metadata, depth range, null value, curve/channel
inventory, source fingerprint, and a normalized ingestion package. The managed
inventory record is registered with lifecycle state `available` because viewer
package generation remains a separate backend boundary. `viewer_ready` remains
reserved for records with backend viewer-package references.

DLIS, CGM, TIFF, PDF, and UNKNOWN remain first-class detection/contract cases.
They are not parsed in this block and must not be forced into a LAS-only model.
