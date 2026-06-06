from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    representation_info = (ROOT / "seismic-viewer-backend/app/msi/representation_info_service.py").read_text(encoding="utf-8")
    volumes_api = (ROOT / "seismic-viewer-backend/app/api/volumes.py").read_text(encoding="utf-8")
    zarr_service = (ROOT / "seismic-viewer-frontend/src/services/zarrService.ts").read_text(encoding="utf-8")

    require('"info_contract": "msi_representation_info_v1"' in representation_info, "MSI info contract marker missing")
    require('volume_metadata = volume_payload.get("metadata")' in representation_info, "MSI info does not expose resolved physical volume metadata")
    require('"metadata": metadata' in representation_info, "MSI info does not return top-level metadata")

    require('enriched.get("metadata") or volume_metadata or {}' in volumes_api, "legacy MSI bridge does not preserve resolved physical metadata")
    require('metadata["requested_volume_id"] = requested_volume_id' in volumes_api, "legacy MSI bridge requested id marker missing")

    require('/api/msi/representations/${encoded}/info' in zarr_service, "frontend service does not call MSI-native info endpoint")
    require('if (isMsiVolume(volume))' in zarr_service, "frontend info helper does not detect MSI rows at service boundary")

    print("PASS MSI 3D info contract static test")


if __name__ == "__main__":
    main()
