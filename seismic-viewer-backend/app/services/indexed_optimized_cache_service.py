from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import segyio
import zarr

from app.services.job_service import JobService
from app.services.segy_index_service import SegyIndexService, SEGY_INDEX_DIR


BACKEND_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND_ROOT / "data"

ZARR_DIR = Path(os.environ.get("ZARR_DIR", str(DATA_DIR / "zarr")))
ZARR_TMP_DIR = Path(os.environ.get("ZARR_TMP_DIR", str(DATA_DIR / "zarr_tmp")))


ACTIVE_CACHE_STATUSES = {
    "queued",
    "reading_index",
    "converting",
    "validating_zarr",
    "promoting_output",
}


DEFAULT_INLINE_BATCH_SIZE = 16
DEFAULT_CROSSLINE_CHUNK = 64
DEFAULT_SAMPLE_CHUNK = 256
HEARTBEAT_SECONDS = 3.0
HEARTBEAT_TRACE_INTERVAL = 5000


class IndexedOptimizedCacheService:
    """
    Builds an optimized Zarr cache for an already-indexed SEG-Y dataset.

    Architectural boundary:
      - Dataset API handles HTTP only.
      - This service coordinates indexed-cache build jobs.
      - SegyIndexService owns indexed-record persistence.
      - This service uses existing SEG-Y index arrays instead of re-inferring geometry.
      - No external repository registry mutation.
      - No viewer/rendering mutation.
      - No report mutation.
    """

    def __init__(self, job_service: JobService):
        self.job_service = job_service

    def _clean_dataset_id(self, dataset_id: str) -> str:
        return str(dataset_id).replace("indexed-segy-", "", 1)

    def _index_dir(self, dataset_id: str) -> Path:
        return SEGY_INDEX_DIR / self._clean_dataset_id(dataset_id)

    def _load_index_arrays(self, dataset_id: str) -> Dict[str, np.ndarray]:
        index_dir = self._index_dir(dataset_id)

        required = {
            "trace_inlines": "trace_inlines.npy",
            "trace_crosslines": "trace_crosslines.npy",
            "trace_numbers": "trace_numbers.npy",
            "unique_inlines": "unique_inlines.npy",
            "unique_crosslines": "unique_crosslines.npy",
            "inline_sort_order": "inline_sort_order.npy",
        }

        arrays: Dict[str, np.ndarray] = {}

        for key, filename in required.items():
            path = index_dir / filename
            if not path.exists():
                raise FileNotFoundError(f"Required SEG-Y index array missing: {path}")
            arrays[key] = np.load(path)

        return arrays

    def _validate_index_arrays(
        self,
        index: Dict[str, Any],
        arrays: Dict[str, np.ndarray],
    ) -> None:
        trace_count = int(index.get("trace_count") or 0)
        inline_count = int(index.get("inline_count") or 0)
        crossline_count = int(index.get("crossline_count") or 0)

        trace_inlines = arrays["trace_inlines"]
        trace_crosslines = arrays["trace_crosslines"]
        trace_numbers = arrays["trace_numbers"]
        unique_inlines = arrays["unique_inlines"]
        unique_crosslines = arrays["unique_crosslines"]
        inline_sort_order = arrays["inline_sort_order"]

        if not (
            len(trace_inlines)
            == len(trace_crosslines)
            == len(trace_numbers)
            == trace_count
        ):
            raise ValueError(
                "Indexed trace arrays are not aligned with trace_count. "
                f"trace_count={trace_count}, "
                f"trace_inlines={len(trace_inlines)}, "
                f"trace_crosslines={len(trace_crosslines)}, "
                f"trace_numbers={len(trace_numbers)}"
            )

        if len(unique_inlines) != inline_count:
            raise ValueError(
                f"unique_inlines count mismatch. "
                f"Expected {inline_count}, got {len(unique_inlines)}."
            )

        if len(unique_crosslines) != crossline_count:
            raise ValueError(
                f"unique_crosslines count mismatch. "
                f"Expected {crossline_count}, got {len(unique_crosslines)}."
            )

        if len(inline_sort_order) != trace_count:
            raise ValueError(
                f"inline_sort_order length mismatch. "
                f"Expected {trace_count}, got {len(inline_sort_order)}."
            )

    def _validate_zarr_cache(
        self,
        zarr_path: Path,
        expected_shape: list[int],
    ) -> Dict[str, Any]:
        arr = zarr.open(str(zarr_path), mode="r")

        shape = list(arr.shape)
        chunks = list(arr.chunks)
        dtype = str(arr.dtype)

        if len(shape) != 3:
            raise ValueError(f"Optimized Zarr cache is not a 3D cube. Shape is {shape}.")

        if expected_shape and list(expected_shape) != shape:
            raise ValueError(
                f"Optimized Zarr cache shape mismatch. "
                f"Expected {expected_shape}, got {shape}."
            )

        if dtype not in {"float32", "float32"}:
            raise ValueError(f"Unexpected optimized Zarr dtype: {dtype}")

        return {
            "shape": shape,
            "chunks": chunks,
            "dtype": dtype,
        }

    def _current_cache_with_status(
        self,
        index: Dict[str, Any],
        status: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        cache = dict(index.get("optimized_cache") or {})
        cache["status"] = status
        if extra:
            cache.update(extra)
        return cache

    def _set_phase(
        self,
        dataset_id: str,
        job_id: str,
        status: str,
        message: str,
        progress: Optional[float] = None,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> None:
        index = SegyIndexService.load_index(dataset_id)
        cache = self._current_cache_with_status(
            index,
            status,
            {
                "last_message": message,
                "last_heartbeat_at": self.job_service.utc_now(),
                "metrics": metrics or {},
            },
        )

        SegyIndexService.update_index(dataset_id, {
            "optimized_cache_status": status,
            "optimized_cache": cache,
            "optimized_cache_error": None,
        })

        updates: Dict[str, Any] = {
            "status": status,
            "message": message,
            "optimized_cache": cache,
            "error": None,
        }

        if progress is not None:
            updates["progress"] = progress

        if metrics is not None:
            updates["metrics"] = metrics

        self.job_service.update_job(job_id, **updates)

    def _write_index_sidecars(
        self,
        dataset_id: str,
        output_path: Path,
        index: Dict[str, Any],
        zarr_info: Dict[str, Any],
    ) -> Dict[str, str]:
        index_dir = self._index_dir(dataset_id)
        output_dir = output_path.parent
        base_name = output_path.name[:-5] if output_path.name.endswith(".zarr") else output_path.stem

        sidecars: Dict[str, str] = {}

        text_src = index_dir / "segy_text_header.txt"
        if text_src.exists():
            text_dst = output_dir / f"{base_name}.segy_text_header.txt"
            shutil.copy2(text_src, text_dst)
            sidecars["text_header"] = str(text_dst)

        binary_src = index_dir / "segy_binary_header.json"
        if binary_src.exists():
            binary_dst = output_dir / f"{base_name}.segy_binary_header.json"
            shutil.copy2(binary_src, binary_dst)
            sidecars["binary_header"] = str(binary_dst)

        trace_summary = {
            "trace_count": index.get("trace_count"),
            "inline_count": index.get("inline_count"),
            "crossline_count": index.get("crossline_count"),
            "sample_count": index.get("sample_count"),
            "inline_min": index.get("inline_min"),
            "inline_max": index.get("inline_max"),
            "crossline_min": index.get("crossline_min"),
            "crossline_max": index.get("crossline_max"),
            "valid_trace_header_count": index.get("valid_trace_header_count"),
            "invalid_trace_header_count": index.get("invalid_trace_header_count"),
            "sample_interval_ms": index.get("sample_interval_ms"),
            "geometry_source": "indexed_segy_headers",
        }

        trace_dst = output_dir / f"{base_name}.trace_header_summary.json"
        trace_dst.write_text(json.dumps(trace_summary, indent=2), encoding="utf-8")
        sidecars["trace_header_summary"] = str(trace_dst)

        viewer_metadata = {
            "dataset_id": dataset_id,
            "source_file_name": index.get("source_file_name"),
            "source_path": index.get("source_path"),
            "source_format": "SEG-Y",
            "read_mode": "optimized_zarr_cache",
            "optimized_cache_status": "available",
            "shape": zarr_info.get("shape"),
            "chunks": zarr_info.get("chunks"),
            "dtype": zarr_info.get("dtype"),
            "axis_order": ["inline", "crossline", "sample"],
            "sample_interval_ms": index.get("sample_interval_ms"),
            "trace_count": index.get("trace_count"),
            "inline_count": index.get("inline_count"),
            "crossline_count": index.get("crossline_count"),
            "sample_count": index.get("sample_count"),
            "inline_range": [index.get("inline_min"), index.get("inline_max")],
            "crossline_range": [index.get("crossline_min"), index.get("crossline_max")],
            "geometry_source": "indexed_segy_headers",
            "conversion_info": zarr_info,
            "sidecars": sidecars,
        }

        viewer_dst = output_dir / f"{base_name}.viewer_metadata.json"
        viewer_dst.write_text(json.dumps(viewer_metadata, indent=2), encoding="utf-8")
        sidecars["viewer_metadata"] = str(viewer_dst)

        return sidecars

    def queue_build(self, dataset_id: str) -> Dict[str, Any]:
        clean_id = self._clean_dataset_id(dataset_id)
        index = SegyIndexService.load_index(clean_id)

        current_status = index.get("optimized_cache_status", "not_started")
        current_cache = index.get("optimized_cache") or {}

        if current_status in ACTIVE_CACHE_STATUSES:
            job_id = current_cache.get("job_id") or index.get("optimized_cache_job_id")
            job = self.job_service.get_job(job_id) if job_id else None
            return {
                "status": current_status,
                "message": "Optimized Zarr cache build is already queued or running.",
                "dataset_id": clean_id,
                "job_id": job_id,
                "job": job,
                "optimized_cache": current_cache,
            }

        source_path = Path(index.get("source_path", "")).expanduser()

        if not source_path.exists() or not source_path.is_file():
            SegyIndexService.update_index(clean_id, {
                "optimized_cache_status": "failed",
                "optimized_cache_error": f"Source SEG-Y file missing: {source_path}",
            })
            raise FileNotFoundError(f"Source SEG-Y file missing: {source_path}")

        cache_id = f"{clean_id}-optimized-{uuid.uuid4().hex[:8]}"
        job_id = str(uuid.uuid4())

        ZARR_DIR.mkdir(parents=True, exist_ok=True)
        ZARR_TMP_DIR.mkdir(parents=True, exist_ok=True)

        output_path = ZARR_DIR / f"{cache_id}.zarr"
        temp_output_path = ZARR_TMP_DIR / f"{cache_id}.zarr.tmp"
        zarr_url = f"/data/zarr/{cache_id}.zarr"

        self.job_service.create_job(
            job_id=job_id,
            file_id=cache_id,
            filename=index.get("source_file_name") or source_path.name,
            input_path=str(source_path),
            output_path=str(output_path),
            temp_output_path=str(temp_output_path),
        )

        optimized_cache = {
            "status": "queued",
            "job_id": job_id,
            "cache_id": cache_id,
            "zarr_url": zarr_url,
            "path": str(output_path),
            "temp_path": str(temp_output_path),
            "source_dataset_id": clean_id,
            "worker": "indexed_cache_worker",
        }

        updated = SegyIndexService.update_index(clean_id, {
            "optimized_cache_status": "queued",
            "optimized_cache_job_id": job_id,
            "optimized_cache": optimized_cache,
            "optimized_cache_error": None,
        })

        return {
            "status": "queued",
            "message": "Indexed optimized Zarr cache build queued.",
            "dataset_id": clean_id,
            "job_id": job_id,
            "cache_id": cache_id,
            "zarr_url": zarr_url,
            "optimized_cache": optimized_cache,
            "index": updated,
        }

    def _write_indexed_zarr_cache(
        self,
        dataset_id: str,
        job_id: str,
        input_path: Path,
        temp_output_path: Path,
    ) -> Dict[str, Any]:
        index = SegyIndexService.load_index(dataset_id)
        arrays = self._load_index_arrays(dataset_id)
        self._validate_index_arrays(index, arrays)

        shape = [int(v) for v in index["shape"]]
        n_inline, n_crossline, n_samples = shape
        trace_count = int(index["trace_count"])

        inline_batch_size = min(DEFAULT_INLINE_BATCH_SIZE, n_inline)
        chunks = (
            inline_batch_size,
            min(DEFAULT_CROSSLINE_CHUNK, n_crossline),
            min(DEFAULT_SAMPLE_CHUNK, n_samples),
        )

        trace_inlines = arrays["trace_inlines"]
        trace_crosslines = arrays["trace_crosslines"]
        trace_numbers = arrays["trace_numbers"]
        unique_inlines = arrays["unique_inlines"]
        unique_crosslines = arrays["unique_crosslines"]
        inline_sort_order = arrays["inline_sort_order"]

        inline_index = {int(value): idx for idx, value in enumerate(unique_inlines.tolist())}
        crossline_index = {int(value): idx for idx, value in enumerate(unique_crosslines.tolist())}

        if temp_output_path.exists():
            shutil.rmtree(temp_output_path)

        temp_output_path.parent.mkdir(parents=True, exist_ok=True)

        z = zarr.open(
            str(temp_output_path),
            mode="w",
            shape=tuple(shape),
            chunks=chunks,
            dtype="f4",
            fill_value=0.0,
        )

        current_batch_start: Optional[int] = None
        current_batch_end: Optional[int] = None
        current_block: Optional[np.ndarray] = None
        current_block_has_data = False

        written_traces = 0
        skipped_traces = 0
        batch_writes = 0
        last_heartbeat_time = time.monotonic()

        def flush_current_block() -> None:
            nonlocal current_batch_start
            nonlocal current_batch_end
            nonlocal current_block
            nonlocal current_block_has_data
            nonlocal batch_writes

            if (
                current_block is not None
                and current_batch_start is not None
                and current_batch_end is not None
                and current_block_has_data
            ):
                z[current_batch_start:current_batch_end, :, :] = current_block
                batch_writes += 1

            current_batch_start = None
            current_batch_end = None
            current_block = None
            current_block_has_data = False

        def maybe_heartbeat(force: bool = False) -> None:
            nonlocal last_heartbeat_time

            now = time.monotonic()
            if (
                force
                or written_traces % HEARTBEAT_TRACE_INTERVAL == 0
                or (now - last_heartbeat_time) >= HEARTBEAT_SECONDS
            ):
                progress = round((written_traces / trace_count) * 100.0, 2) if trace_count else None
                metrics = {
                    "worker": "indexed_cache_worker",
                    "written_traces": written_traces,
                    "skipped_traces": skipped_traces,
                    "total_traces": trace_count,
                    "batch_writes": batch_writes,
                    "shape": shape,
                    "chunks": list(chunks),
                    "temp_output_path": str(temp_output_path),
                }
                self._set_phase(
                    dataset_id=dataset_id,
                    job_id=job_id,
                    status="converting",
                    message=(
                        f"Writing optimized Zarr cache from indexed SEG-Y "
                        f"({written_traces}/{trace_count} traces)..."
                    ),
                    progress=progress,
                    metrics=metrics,
                )
                last_heartbeat_time = now

        with segyio.open(str(input_path), "r", ignore_geometry=True) as f:
            for order_pos, array_pos in enumerate(inline_sort_order):
                array_pos_int = int(array_pos)
                trace_no = int(trace_numbers[array_pos_int])
                inline = int(trace_inlines[array_pos_int])
                crossline = int(trace_crosslines[array_pos_int])

                i_idx = inline_index.get(inline)
                x_idx = crossline_index.get(crossline)

                if i_idx is None or x_idx is None:
                    skipped_traces += 1
                    continue

                desired_batch_start = (i_idx // inline_batch_size) * inline_batch_size
                desired_batch_end = min(desired_batch_start + inline_batch_size, n_inline)

                if (
                    current_batch_start is None
                    or i_idx < current_batch_start
                    or i_idx >= current_batch_end
                ):
                    flush_current_block()

                    current_batch_start = desired_batch_start
                    current_batch_end = desired_batch_end
                    current_block = np.zeros(
                        (
                            current_batch_end - current_batch_start,
                            n_crossline,
                            n_samples,
                        ),
                        dtype=np.float32,
                    )
                    current_block_has_data = False

                local_i = i_idx - current_batch_start
                current_block[local_i, x_idx, :] = f.trace[trace_no]
                current_block_has_data = True
                written_traces += 1

                maybe_heartbeat()

            flush_current_block()
            maybe_heartbeat(force=True)

        expected_trace_positions = n_inline * n_crossline

        return {
            "shape": shape,
            "chunks": list(chunks),
            "dtype": "float32",
            "axis_order": ["inline", "crossline", "sample"],
            "is_3d": True,
            "trace_count": trace_count,
            "geometry_source": "indexed_segy_headers",
            "missing_trace_fill": 0.0,
            "written_traces": written_traces,
            "skipped_traces": skipped_traces,
            "batch_size_inlines": inline_batch_size,
            "batch_writes": batch_writes,
            "expected_trace_positions": expected_trace_positions,
            "missing_trace_positions": expected_trace_positions - written_traces,
            "sample_interval_ms": index.get("sample_interval_ms"),
            "worker": "indexed_cache_worker",
        }

    def run(self, job_id: str) -> None:
        job = self.job_service.get_job(job_id)
        if not job:
            return

        cache_id = job["file_id"]
        input_path = Path(job["input_path"])
        output_path = Path(job["output_path"])
        temp_output_path = Path(job["temp_output_path"])
        dataset_id = cache_id.split("-optimized-", 1)[0]

        try:
            index = SegyIndexService.load_index(dataset_id)
            expected_shape = [int(v) for v in index["shape"]]

            self._set_phase(
                dataset_id=dataset_id,
                job_id=job_id,
                status="reading_index",
                message="Reading indexed SEG-Y arrays before optimized cache build...",
                progress=0,
                metrics={"worker": "indexed_cache_worker"},
            )

            if output_path.exists():
                shutil.rmtree(output_path)

            zarr_info = self._write_indexed_zarr_cache(
                dataset_id=dataset_id,
                job_id=job_id,
                input_path=input_path,
                temp_output_path=temp_output_path,
            )

            self._set_phase(
                dataset_id=dataset_id,
                job_id=job_id,
                status="validating_zarr",
                message="Validating optimized Zarr cache...",
                progress=98,
                metrics=zarr_info,
            )

            validation_info = self._validate_zarr_cache(temp_output_path, expected_shape)
            zarr_info = {**zarr_info, **validation_info}

            self._set_phase(
                dataset_id=dataset_id,
                job_id=job_id,
                status="promoting_output",
                message="Promoting optimized Zarr cache to stable cache path...",
                progress=99,
                metrics=zarr_info,
            )

            output_path.parent.mkdir(parents=True, exist_ok=True)
            os.replace(str(temp_output_path), str(output_path))

            sidecars = self._write_index_sidecars(
                dataset_id=dataset_id,
                output_path=output_path,
                index=index,
                zarr_info=zarr_info,
            )

            zarr_url = f"/data/zarr/{output_path.name}"

            optimized_cache = {
                "status": "available",
                "job_id": job_id,
                "cache_id": cache_id,
                "zarr_url": zarr_url,
                "path": str(output_path),
                "source_dataset_id": dataset_id,
                "zarr": zarr_info,
                "sidecars": sidecars,
                "validated": True,
                "validated_at": self.job_service.utc_now(),
                "worker": "indexed_cache_worker",
            }

            updated_index = SegyIndexService.update_index(dataset_id, {
                "optimized_cache_status": "available",
                "optimized_cache": optimized_cache,
                "optimized_cache_error": None,
            })

            self.job_service.update_job(
                job_id,
                status="complete",
                message="Optimized Zarr cache build complete.",
                progress=100,
                volume=None,
                optimized_cache=optimized_cache,
                index=updated_index,
                metrics=zarr_info,
                error=None,
            )

        except Exception as exc:
            try:
                if temp_output_path.exists():
                    shutil.rmtree(temp_output_path)
            except Exception:
                pass

            try:
                index = SegyIndexService.load_index(dataset_id)
                cache = self._current_cache_with_status(
                    index,
                    "failed",
                    {
                        "failed_at": self.job_service.utc_now(),
                        "error": str(exc),
                    },
                )
                SegyIndexService.update_index(dataset_id, {
                    "optimized_cache_status": "failed",
                    "optimized_cache": cache,
                    "optimized_cache_error": str(exc),
                })
            except Exception:
                pass

            self.job_service.update_job(
                job_id,
                status="failed",
                message="Optimized Zarr cache build failed.",
                error=str(exc),
            )

    def get_status(self, dataset_id: str) -> Dict[str, Any]:
        clean_id = self._clean_dataset_id(dataset_id)
        index = SegyIndexService.load_index(clean_id)

        cache = index.get("optimized_cache") or {}
        job_id = cache.get("job_id") or index.get("optimized_cache_job_id")
        job = self.job_service.get_job(job_id) if job_id else None

        return {
            "dataset_id": clean_id,
            "optimized_cache_status": index.get("optimized_cache_status", "not_started"),
            "optimized_cache": cache,
            "job_id": job_id,
            "job": job,
            "error": index.get("optimized_cache_error"),
        }
