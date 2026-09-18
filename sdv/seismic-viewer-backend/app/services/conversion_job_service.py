import json
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict

import zarr

from app.services.seismic_service import SeismicService
from app.services.job_service import JobService
from app.services.metadata_agent_service import build_normalized_metadata
from app.storage.service import storage_service


class ConversionJobService:
    def __init__(
        self,
        job_service: JobService,
        volumes_json: str = "./data/volumes.json",
    ):
        self.job_service = job_service
        self.volumes_json = Path(volumes_json)
        self.volumes_json.parent.mkdir(parents=True, exist_ok=True)

    def _load_volumes(self) -> Dict[str, Any]:
        if self.volumes_json.exists():
            with open(self.volumes_json, "r") as f:
                return json.load(f)
        return {}

    def _save_volumes(self, volumes: Dict[str, Any]) -> None:
        tmp_path = self.volumes_json.with_suffix(".json.tmp")

        with open(tmp_path, "w") as f:
            json.dump(volumes, f, indent=2)

        tmp_path.replace(self.volumes_json)

    def _validate_zarr_dataset(self, zarr_path: str, expected_dataset_type: str) -> Dict[str, Any]:
        arr = zarr.open(zarr_path, mode="r")

        shape = list(arr.shape)
        chunks = list(arr.chunks)

        if expected_dataset_type == "3d_volume" and len(shape) != 3:
            raise ValueError(
                f"Converted Zarr is not a 3D cube. Shape is {shape}."
            )

        if expected_dataset_type == "2d_line" and len(shape) != 2:
            raise ValueError(
                f"Converted Zarr is not a 2D line section. Shape is {shape}."
            )

        return {
            "shape": shape,
            "chunks": chunks,
            "dtype": str(arr.dtype),
        }

    def _make_3d_zarr_progress_callback(self, job_id: str):
        """
        Create a throttled progress callback for 3D SEG-Y -> Zarr conversion.

        Progress is mapped as:
          0–10%   setup/metadata/geometry
          10–90%  actual 3D Zarr writing by inline batches
          90–100% validation, promotion, registration

        The callback is intentionally throttled to avoid writing job JSON inside
        every trace operation.
        """
        state = {"last_time": 0.0, "last_percent": None}

        def callback(update: Dict[str, Any]) -> None:
            try:
                processed_inlines = int(update.get("processed_inlines") or 0)
                total_inlines = int(update.get("total_inlines") or 0)
                processed_traces = int(update.get("processed_traces") or 0)
                total_traces = int(update.get("total_traces") or 0)
                batch_writes = int(update.get("batch_writes") or 0)

                if total_inlines > 0:
                    work_fraction = max(0.0, min(1.0, processed_inlines / total_inlines))
                elif total_traces > 0:
                    work_fraction = max(0.0, min(1.0, processed_traces / total_traces))
                else:
                    work_fraction = 0.0

                percent = max(10.0, min(90.0, 10.0 + (80.0 * work_fraction)))
                now = time.monotonic()
                last_percent = state["last_percent"]

                should_write = (
                    last_percent is None
                    or percent >= 90.0
                    or percent - float(last_percent) >= 1.0
                    or now - float(state["last_time"] or 0.0) >= 1.0
                )

                if not should_write:
                    return

                state["last_time"] = now
                state["last_percent"] = percent

                detail_parts = []
                if total_inlines > 0:
                    detail_parts.append(f"inlines {processed_inlines}/{total_inlines}")
                if total_traces > 0:
                    detail_parts.append(f"traces {processed_traces}/{total_traces}")
                if batch_writes > 0:
                    detail_parts.append(f"batches {batch_writes}")

                detail = ", ".join(detail_parts) if detail_parts else "writing Zarr batches"

                self.job_service.update_job(
                    job_id,
                    status="converting",
                    message=f"Writing 3D Zarr: {detail}",
                    progress=round(percent, 1),
                    progress_stage="writing_zarr",
                    processed_units=processed_inlines if total_inlines > 0 else processed_traces,
                    total_units=total_inlines if total_inlines > 0 else total_traces,
                    progress_units="inlines" if total_inlines > 0 else "traces",
                    batch_writes=batch_writes,
                )
            except Exception:
                # Progress telemetry must never fail conversion.
                return

        return callback

    def _validate_conversion_contract(
        self,
        *,
        requested_dataset_type: str,
        zarr_url: str,
        storage_uri: str,
        metadata: Dict[str, Any],
        zarr_info: Dict[str, Any],
        staged_rebuild: bool = False,
    ) -> None:
        requested = (requested_dataset_type or "").strip().lower()
        if requested not in {"2d_line", "3d_volume"}:
            raise ValueError(f"Unsupported conversion contract target: {requested_dataset_type!r}")

        shape = list(zarr_info.get("shape") or [])
        axis_order = list(zarr_info.get("axis_order") or [])
        zarr_is_3d = zarr_info.get("is_3d")
        metadata_is_3d = metadata.get("is_3d")

        zarr_url_text = str(zarr_url or "")
        storage_uri_text = str(storage_uri or "")

        def has_2d_target(text: str) -> bool:
            if staged_rebuild:
                return (
                    "/staging/conversion_jobs/rebuild/2d/" in text
                    or text.startswith("endrepo://staging/conversion_jobs/rebuild/2d/")
                    or "/managed/zarr/2d/" in text
                    or text.startswith("endrepo://managed/zarr/2d/")
                )
            return "/managed/zarr/2d/" in text or text.startswith("endrepo://managed/zarr/2d/")

        def has_3d_target(text: str) -> bool:
            if staged_rebuild:
                return (
                    "/staging/conversion_jobs/rebuild/3d/" in text
                    or text.startswith("endrepo://staging/conversion_jobs/rebuild/3d/")
                    or "/managed/zarr/3d/" in text
                    or text.startswith("endrepo://managed/zarr/3d/")
                )
            return "/managed/zarr/3d/" in text or text.startswith("endrepo://managed/zarr/3d/")

        if requested == "2d_line":
            if len(shape) != 2 or zarr_is_3d is True or metadata_is_3d is True:
                raise ValueError(
                    "2D conversion contract violated: "
                    f"shape={shape}, zarr_is_3d={zarr_is_3d}, metadata_is_3d={metadata_is_3d}"
                )
            if axis_order and axis_order != ["trace", "sample"]:
                raise ValueError(f"2D conversion contract violated: axis_order={axis_order}")
            if has_3d_target(zarr_url_text) or has_3d_target(storage_uri_text):
                raise ValueError(
                    "2D conversion contract violated: output target points to 3D storage. "
                    f"zarr_url={zarr_url}, storage_uri={storage_uri}"
                )
            return

        if requested == "3d_volume":
            if len(shape) != 3 or zarr_is_3d is not True or metadata_is_3d is not True:
                raise ValueError(
                    "3D conversion contract violated: "
                    f"shape={shape}, zarr_is_3d={zarr_is_3d}, metadata_is_3d={metadata_is_3d}"
                )
            if axis_order and axis_order != ["inline", "crossline", "sample"]:
                raise ValueError(f"3D conversion contract violated: axis_order={axis_order}")
            if has_2d_target(zarr_url_text) or has_2d_target(storage_uri_text):
                raise ValueError(
                    "3D conversion contract violated: output target points to 2D storage. "
                    f"zarr_url={zarr_url}, storage_uri={storage_uri}"
                )

    def run(self, job_id: str) -> None:
        job = self.job_service.get_job(job_id)

        if not job:
            return

        file_id = job["file_id"]
        filename = job["filename"]
        input_path = job["input_path"]
        output_path = job["output_path"]
        temp_output_path = job["temp_output_path"]
        expected_dataset_type = (job.get("expected_dataset_type") or "").strip().lower() or None
        if expected_dataset_type not in {None, "2d_line", "3d_volume"}:
            raise ValueError(f"Unsupported expected_dataset_type on job: {expected_dataset_type!r}")
        geometry_qaqc = job.get("geometry_qaqc") if isinstance(job.get("geometry_qaqc"), dict) else None
        geometry_override = job.get("geometry_override") if isinstance(job.get("geometry_override"), dict) else None
        rebuild_context = job.get("rebuild_context") if isinstance(job.get("rebuild_context"), dict) else None
        staged_rebuild = bool(job.get("staged_rebuild"))


        try:
            self.job_service.update_job(
                job_id,
                status="reading_metadata",
                message="Reading SEG-Y metadata...",
                progress=5,
                progress_stage="reading_metadata",
            )

            metadata = SeismicService.get_segy_metadata(
                input_path,
                expected_dataset_type=expected_dataset_type,
                geometry_override=geometry_override,
            )

            is_3d = metadata.get("is_3d")
            shape = metadata.get("shape")

            if expected_dataset_type:
                dataset_type = expected_dataset_type
            elif is_3d is True and shape and len(shape) == 3:
                dataset_type = "3d_volume"
            elif is_3d is False and shape and len(shape) == 2:
                dataset_type = "2d_line"
            else:
                self.job_service.update_job(
                    job_id,
                    status="failed",
                    message="SEG-Y was read, but its geometry is not currently supported.",
                    error=(
                        f"Detected shape: {shape}, is_3d={is_3d}. "
                        "Supported dataset types are 3D volume and 2D line."
                    ),
                )
                return

            dimension = "3d" if dataset_type == "3d_volume" else "2d"
            if staged_rebuild:
                output_path = str(job.get("output_path") or output_path)
                zarr_url = str(job.get("zarr_url") or "")
                storage_uri = str(job.get("storage_uri") or "")
                if not output_path or not storage_uri:
                    raise ValueError("Staged rebuild job is missing output_path or storage_uri.")
            else:
                target = storage_service().managed_zarr_target(file_id, dimension)
                output_path = str(target["local_path"])
                zarr_url = str(target["zarr_url"])
                storage_uri = str(target["storage_uri"])

            self.job_service.update_job(
                job_id,
                status="converting",
                message="Preparing temporary Zarr output...",
                progress=10,
                progress_stage="preparing_zarr",
                output_path=output_path,
                zarr_url=zarr_url,
                storage_uri=storage_uri,
            )

            temp_path = Path(temp_output_path)
            final_path = Path(output_path)

            if temp_path.exists():
                shutil.rmtree(temp_path)

            if final_path.exists():
                shutil.rmtree(final_path)

            temp_path.parent.mkdir(parents=True, exist_ok=True)
            final_path.parent.mkdir(parents=True, exist_ok=True)

            conversion_info = SeismicService.convert_to_zarr(
                input_path,
                temp_output_path,
                expected_dataset_type=expected_dataset_type,
                progress_callback=(
                    self._make_3d_zarr_progress_callback(job_id)
                    if dataset_type == "3d_volume"
                    else None
                ),
                geometry_override=geometry_override,
            )

            self.job_service.update_job(
                job_id,
                status="validating_zarr",
                message="Validating converted Zarr dataset...",
                progress=92,
                progress_stage="validating_zarr",
            )

            zarr_info = self._validate_zarr_dataset(temp_output_path, dataset_type)

            if isinstance(conversion_info, dict):
                zarr_info = {
                    **conversion_info,
                    **zarr_info,
                }

            if dataset_type == "2d_line":
                if zarr_info.get("is_3d") is True or len(zarr_info.get("shape") or []) != 2:
                    raise ValueError(
                        "2D managed-line conversion contract violated: "
                        f"zarr_info={zarr_info}"
                    )
                zarr_info["is_3d"] = False
                zarr_info["axis_order"] = ["trace", "sample"]

            if dataset_type == "3d_volume":
                if zarr_info.get("is_3d") is False or len(zarr_info.get("shape") or []) != 3:
                    raise ValueError(
                        "3D managed-volume conversion contract violated: "
                        f"zarr_info={zarr_info}"
                    )
                zarr_info["is_3d"] = True
                zarr_info.setdefault("axis_order", ["inline", "crossline", "sample"])

            self._validate_conversion_contract(
                requested_dataset_type=dataset_type,
                zarr_url=zarr_url,
                storage_uri=storage_uri,
                metadata=metadata,
                zarr_info=zarr_info,
                staged_rebuild=staged_rebuild,
            )

            self.job_service.update_job(
                job_id,
                status="promoting_output",
                message="Promoting temporary Zarr to final output...",
                progress=96,
                progress_stage="promoting_output",
            )

            os.replace(temp_output_path, output_path)

            # Promote any sidecar metadata/header files created next to the temp Zarr.
            # Example:
            #   data/zarr_tmp/<id>.zarr.segy_text_header.txt
            # should become:
            #   data/zarr/<id>.zarr.segy_text_header.txt
            temp_base = Path(temp_output_path)
            final_base = Path(output_path)

            # Some sidecar files are created using the final .zarr basename
            # even though they are still written into data/zarr_tmp.
            # Handle both patterns:
            #   <id>.zarr.tmp.*
            #   <id>.zarr.*
            sidecar_patterns = [
                temp_base.name + ".*",
                final_base.name + ".*",
            ]

            for pattern in sidecar_patterns:
                for sidecar in temp_base.parent.glob(pattern):
                    final_sidecar_name = sidecar.name

                    if final_sidecar_name.startswith(temp_base.name):
                        final_sidecar_name = final_sidecar_name.replace(
                            temp_base.name,
                            final_base.name,
                            1,
                        )

                    final_sidecar = final_base.parent / final_sidecar_name

                    if final_sidecar.exists():
                        final_sidecar.unlink()

                    sidecar.replace(final_sidecar)

            volume_record = {
                "dataset_type": dataset_type,
                "id": file_id,
                "filename": filename,
                "display_name": filename,
                "hidden": True,
                "metadata": {
                    **metadata,
                    "zarr": zarr_info,
                    "geometry_qaqc": geometry_qaqc,
                },
                "geometry_qaqc": geometry_qaqc,
                "zarr_url": zarr_url,
                "storage_uri": storage_uri,
            }

            if staged_rebuild:
                staged_payload = {
                    "job_id": job_id,
                    "artifact_id": file_id,
                    "dataset_type": dataset_type,
                    "source_candidate_id": (rebuild_context or {}).get("candidate_id"),
                    "source_volume_id": (rebuild_context or {}).get("prior_volume_id"),
                    "output_path": output_path,
                    "zarr_url": zarr_url,
                    "storage_uri": storage_uri,
                    "metadata": volume_record.get("metadata"),
                    "volume": volume_record,
                    "promotion_required": True,
                    "promotion_options": ["overwrite_existing", "save_as_new", "discard"],
                }
                self.job_service.update_job(
                    job_id,
                    status="complete",
                    message="SEG-Y staged rebuild complete. Choose overwrite, save-as, or discard in the next workflow step.",
                    progress=100,
                    progress_stage="staged_rebuild_complete",
                    volume=volume_record,
                    staged_rebuild=staged_payload,
                    error=None,
                )
                return

            self.job_service.update_job(
                job_id,
                status="registering_dataset",
                message="Registering converted dataset...",
                progress=98,
                progress_stage="registering_dataset",
            )

            volumes = self._load_volumes()
            volumes[file_id] = volume_record
            self._save_volumes(volumes)

            # Build normalized metadata automatically after registration.
            # This is intentionally non-fatal: the SEG-Y conversion remains successful
            # even if metadata enrichment fails.
            try:
                normalized_metadata = build_normalized_metadata(file_id)
                volume_record["normalized_metadata_available"] = True
                volume_record["normalized_metadata"] = normalized_metadata
            except Exception as metadata_error:
                volume_record["normalized_metadata_available"] = False
                volume_record["normalized_metadata_error"] = str(metadata_error)
                print(
                    f"WARNING: normalized metadata enrichment failed for "
                    f"{file_id}: {metadata_error}"
                )

            self.job_service.update_job(
                job_id,
                status="complete",
                message="SEG-Y conversion complete.",
                progress=100,
                volume=volume_record,
                error=None,
            )

        except Exception as e:
            try:
                if Path(temp_output_path).exists():
                    shutil.rmtree(temp_output_path)
            except Exception:
                pass

            self.job_service.update_job(
                job_id,
                status="failed",
                message="SEG-Y conversion failed.",
                error=str(e),
            )
