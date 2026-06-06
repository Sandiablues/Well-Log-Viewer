# 3D Active-Slice / Viewport-Window Rendering Design

## Purpose

This design defines the enterprise-ready path for improving 3D seismic slice
quality beyond whole-slice texture scaling.

The current 3D renderer builds whole-slice textures and camera zoom magnifies
those textures. The near-term 2x slice-detail improvement improves still-view
quality, but it still spends texture resolution on areas outside the visible
viewport.

The target model is active-slice viewport-window rendering:

```text
active axis + slice index + camera-visible source bounds
→ requested output texture dimensions
→ display parameters
→ texture/window response
→ cache + LOD behavior
```

## Ownership Boundary

Frontend rendering layer owns:

- active axis and slice selection
- camera and viewport state
- mapping visible screen/camera region to source bounds
- choosing requested output texture dimensions
- local texture cache keys and eviction policy
- low-detail movement preview and high-detail settled render behavior

Backend/service layer owns:

- MSI representation identity
- physical volume resolution
- Zarr/source-data access
- future MSI-native slice-window endpoint
- durable source-window extraction
- server-side cache if promoted beyond local runtime

The frontend must not infer MSI lifecycle, physical artifact truth, or registry
state. MSI representation ID remains the public managed-data identity.

## Slice Axis Mapping

Each active 3D plane maps to two source axes:

| Active slice axis | Fixed coordinate | Texture/source X axis | Texture/source Y axis |
| --- | --- | --- | --- |
| inline | inline index | crossline | sample/time |
| crossline | crossline index | inline | sample/time |
| time | sample/time index | inline | crossline |

This mapping must be centralized in a helper module. It must not be scattered
through Seismic3DViewer.tsx.

## Request Shape

The future backend request should use an MSI-native route pattern:

```text
GET /api/msi/representations/{representation_id}/slice-window
```

Logical parameters:

```text
axis: inline | crossline | time
slice_index: number
source_x_start: number
source_x_end: number
source_y_start: number
source_y_end: number
output_width: number
output_height: number
clip_percentile: number
gain: number
reverse_polarity: boolean
color_mode: grayscale | color
quality: preview | balanced | high
```

The backend response should include:

```text
axis
slice_index
source_bounds
output_shape
source_shape
texture_format
clip/gain/polarity parameters actually used
render_time_ms
cache_status
payload
```

Payload may initially be JSON/numeric for prototype work, but enterprise-scale
transport should move toward binary/tiled payloads rather than large JSON arrays.

## LOD / Movement Behavior

The target behavior is:

```text
while moving camera or slice:
  show existing whole-slice texture or native/1x preview

after movement settles:
  request high-quality visible window

if same request is repeated:
  use texture cache

if cache grows too large:
  evict least-recently used entries
```

High-resolution requests must not fire on every mouse movement.

## Cache Key

A stable cache key must include:

```text
representation_id
axis
slice_index
source bounds
output dimensions
clip_percentile
gain
reverse_polarity
color_mode
quality
```

Cache keys must not depend on incidental UI labels.

## Phased Implementation

### 3D-C1 — Design and Request Model

Add this design document and a typed request-model helper. No runtime behavior
change.

### 3D-C2 — Viewport Bounds Diagnostics

Calculate and display active-plane source bounds in diagnostics. No backend
endpoint and no renderer replacement yet.


### 3D-C2 — Active Bounds Diagnostics

The first runtime diagnostic step should display a conservative active-slice
source-bounds model without replacing rendering behavior. Initially this may
show the whole-slice baseline bounds for the currently active plane, plus the
centralized axis mapping and future request/cache key.

This diagnostic is intentionally not the final camera-visible crop. It verifies
that the viewer can express active plane, slice index, source axes, source
bounds, output dimensions, and cache-key inputs without making the frontend own
MSI or physical-volume truth.

### 3D-C3 — One-Plane Prototype

Prototype active-slice viewport-window rendering for one plane only, preferably
time slice. Keep current whole-slice rendering as fallback.

### 3D-C4 — Cache / Cancellation / Settled Render

Add request cancellation, debounce/settle logic, and bounded texture cache.

### 3D-C5 — Generalize to Inline and Crossline

Extend the one-plane prototype to all active slice planes.

### 3D-C6 — MSI-Native Backend Endpoint

Promote source-window extraction to a backend-owned MSI-native endpoint once the
frontend prototype proves the coordinate mapping and UX.

## Stop Conditions

Stop if implementation requires:

- rewriting Seismic3DViewer.tsx in one block
- frontend resolving physical volume IDs as authority
- scattered axis-specific math in JSX
- high-res requests on every camera event
- unbounded texture cache growth
- backend route identity ambiguity
