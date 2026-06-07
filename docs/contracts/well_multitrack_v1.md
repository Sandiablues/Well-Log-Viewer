# well_multitrack_v1 Contract

Initial canonical backend-owned viewer package contract for the MultiViewer
Well Log Viewer.

The frontend must render this contract through an adapter. The Equinor ViDEx
viewer must not become the canonical backend API contract.

## Draft shape

{
  "viewer_package_version": "well_multitrack_v1",
  "dataset_id": "string",
  "representation_id": "string",
  "well_id": "string",
  "wellbore_id": "string",
  "display_domain": "MD",
  "depth_unit": "m|ft",
  "depth_range": {
    "min": 0,
    "max": 0
  },
  "tracks": [
    {
      "track_id": "string",
      "track_type": "curve",
      "title": "string",
      "curves": [
        {
          "curve_id": "string",
          "mnemonic": "string",
          "normalized_name": "string|null",
          "unit": "string|null",
          "samples_url": "string",
          "scale": {
            "type": "linear|log",
            "min": 0,
            "max": 150
          }
        }
      ]
    }
  ],
  "qaqc_findings": [
    {
      "finding_id": "string",
      "severity": "info|warning|error",
      "code": "string",
      "object_type": "string",
      "object_id": "string",
      "message": "string"
    }
  ]
}
