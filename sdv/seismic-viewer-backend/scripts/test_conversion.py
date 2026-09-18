from app.services.seismic_service import SeismicService
import os

segy_path = "/home/team/shared/seismic-viewer-backend/data/uploads/dummy.sgy"
zarr_path = "/home/team/shared/seismic-viewer-backend/data/zarr/dummy.zarr"

if os.path.exists(zarr_path):
    import shutil
    shutil.rmtree(zarr_path)

print("Getting metadata...")
metadata = SeismicService.get_segy_metadata(segy_path)
print(f"Metadata: {metadata}")

print("Converting to Zarr...")
SeismicService.convert_to_zarr(segy_path, zarr_path)
print(f"Zarr created at {zarr_path}")

import zarr
z = zarr.open(zarr_path, mode='r')
print(f"Zarr shape: {z.shape}")
print(f"Zarr chunks: {z.chunks}")
