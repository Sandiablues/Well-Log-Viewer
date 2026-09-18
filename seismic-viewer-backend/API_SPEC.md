# Seismic Viewer Backend API Specification

The backend is built with FastAPI and provides endpoints for seismic data ingestion and metadata retrieval. It serves processed data in Zarr format.

## Base URL
`http://0.0.0.0:8000`

## Endpoints

### 1. Ingestion

#### `POST /api/upload`
Uploads a SEG-Y file for processing. The file is parsed and converted to Zarr format.

**Request:**
- Content-Type: `multipart/form-data`
- Body: `file` (binary)

**Response (200 OK):**
```json
{
  "id": "uuid-string",
  "filename": "original_filename.sgy",
  "metadata": {
    "inlines": [1, 2, ...],
    "crosslines": [1, 2, ...],
    "samples": [0.0, 4.0, ...],
    "sample_rate": 4.0,
    "trace_count": 1000,
    "is_3d": true,
    "shape": [10, 10, 100]
  },
  "zarr_url": "/data/zarr/uuid-string.zarr"
}
```

### 2. Volume Management

#### `GET /api/volumes`
Lists all processed seismic volumes.

**Response (200 OK):**
```json
[
  {
    "id": "uuid-string",
    "filename": "name.sgy",
    "metadata": { ... },
    "zarr_url": "/data/zarr/uuid-string.zarr"
  }
]
```

#### `GET /api/volumes/{volume_id}/metadata`
Retrieves metadata for a specific volume.

**Response (200 OK):**
Metadata object (see above).

### 3. Data Access (Zarr)

#### `GET /data/zarr/{volume_id}.zarr/{path}`
Directly access Zarr V3 chunks and metadata. This endpoint supports HTTP Range requests for efficient chunk retrieval.

**Example paths:**
- `zarr.json`: Zarr V3 metadata (root)
- `c/0/0/0`: Data chunk for coordinates (0,0,0) - structure depends on chunking configuration.

## Frontend Integration Note
The data is stored in **Zarr V3** format. Ensure you use a compatible library (like `zarrita.js` or `zarr-js` with V3 support).

Default chunking for 3D data: `(64, 64, 64)`.
Default chunking for 2D data: `(1000, 512)`.
