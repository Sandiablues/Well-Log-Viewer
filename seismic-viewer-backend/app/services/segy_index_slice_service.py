from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np
import segyio

from app.services.segy_index_service import SEGY_INDEX_DIR


class IndexedSegySliceService:
    """
    Read inline/crossline slices directly from an indexed SEG-Y file.

    This is the fast-preview read path used before optimized Zarr conversion
    is available. It does not rewrite the full volume.
    """

    @staticmethod
    def _load_index_package(dataset_id: str) -> Tuple[Dict[str, Any], Path]:
        index_dir = SEGY_INDEX_DIR / dataset_id
        index_path = index_dir / "segy_index.json"

        if not index_path.exists():
            raise FileNotFoundError(f"Indexed SEG-Y package not found: {index_path}")

        summary = json.loads(index_path.read_text(encoding="utf-8"))
        return summary, index_dir

    @staticmethod
    def read_slice(dataset_id: str, dim: int, index: int) -> Dict[str, Any]:
        summary, index_dir = IndexedSegySliceService._load_index_package(dataset_id)

        source_path = Path(summary["source_path"])
        if not source_path.exists():
            raise FileNotFoundError(f"Source SEG-Y file not found: {source_path}")

        trace_inlines = np.load(index_dir / "trace_inlines.npy", mmap_mode="r")
        trace_crosslines = np.load(index_dir / "trace_crosslines.npy", mmap_mode="r")
        unique_inlines = np.load(index_dir / "unique_inlines.npy", mmap_mode="r")
        unique_crosslines = np.load(index_dir / "unique_crosslines.npy", mmap_mode="r")

        inline_count = int(unique_inlines.size)
        crossline_count = int(unique_crosslines.size)
        sample_count = int(summary["sample_count"])

        if dim == 0:
            if index < 0 or index >= inline_count:
                raise IndexError(f"Inline index out of range: {index}")

            inline_value = int(unique_inlines[index])
            trace_numbers = np.flatnonzero(trace_inlines == inline_value)

            data = np.zeros((crossline_count, sample_count), dtype=np.float32)
            crossline_lookup = {int(value): pos for pos, value in enumerate(unique_crosslines.tolist())}

            with segyio.open(str(source_path), "r", ignore_geometry=True) as f:
                for trace_number in trace_numbers:
                    crossline_value = int(trace_crosslines[int(trace_number)])
                    x_idx = crossline_lookup.get(crossline_value)
                    if x_idx is None:
                        continue
                    data[x_idx, :] = f.trace[int(trace_number)]

            return {
                "dataset_id": dataset_id,
                "read_mode": "indexed_segy",
                "dim": dim,
                "index": index,
                "axis_value": inline_value,
                "shape": list(data.shape),
                "dtype": "float32",
                "data": data,
            }

        if dim == 1:
            if index < 0 or index >= crossline_count:
                raise IndexError(f"Crossline index out of range: {index}")

            crossline_value = int(unique_crosslines[index])
            trace_numbers = np.flatnonzero(trace_crosslines == crossline_value)

            data = np.zeros((inline_count, sample_count), dtype=np.float32)
            inline_lookup = {int(value): pos for pos, value in enumerate(unique_inlines.tolist())}

            with segyio.open(str(source_path), "r", ignore_geometry=True) as f:
                for trace_number in trace_numbers:
                    inline_value = int(trace_inlines[int(trace_number)])
                    i_idx = inline_lookup.get(inline_value)
                    if i_idx is None:
                        continue
                    data[i_idx, :] = f.trace[int(trace_number)]

            return {
                "dataset_id": dataset_id,
                "read_mode": "indexed_segy",
                "dim": dim,
                "index": index,
                "axis_value": crossline_value,
                "shape": list(data.shape),
                "dtype": "float32",
                "data": data,
            }

        if dim == 2:
            raise NotImplementedError(
                "Indexed SEG-Y time/depth slices are intentionally deferred. "
                "Use optimized Zarr/OpenVDS cache for time-slice browsing."
            )

        raise ValueError(f"Unsupported dim: {dim}")
