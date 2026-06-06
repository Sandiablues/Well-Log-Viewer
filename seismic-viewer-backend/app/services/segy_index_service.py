from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import segyio

from app.services.segy_text_header_decoder import write_textual_header_sidecars


DATA_DIR = Path(__file__).resolve().parents[2] / "data"
SEGY_INDEX_DIR = DATA_DIR / "segy_index"


@dataclass
class SegyIndexResult:
    dataset_id: str
    index_dir: str
    source_path: str
    trace_count: int
    sample_count: int
    sample_interval_us: Optional[int]
    inline_count: int
    crossline_count: int
    shape: list[int]
    is_3d: bool


class SegyIndexService:
    """
    Fast SEG-Y index builder.

    This does not convert sample amplitudes to Zarr.
    It scans trace headers, records inline/crossline geometry, stores compact
    NumPy sidecars, and makes the file available for indexed SEG-Y reads.

    Output package:
      data/segy_index/<dataset_id>/
        segy_index.json
        trace_inlines.npy
        trace_crosslines.npy
        trace_numbers.npy
        unique_inlines.npy
        unique_crosslines.npy
        inline_sort_order.npy
        crossline_sort_order.npy
        segy_text_header.txt
        segy_binary_header.json

    Later viewer endpoints can use this package to read inline/crossline slices
    directly from the source SEG-Y while optimized Zarr conversion runs in the
    background.
    """

    @staticmethod
    def make_dataset_id(segy_path: str) -> str:
        path = Path(segy_path).expanduser().resolve()
        stat = path.stat()
        payload = f"{path}|{stat.st_size}|{int(stat.st_mtime)}"
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _safe_int(value: Any) -> Optional[int]:
        try:
            return int(value)
        except Exception:
            return None

    @staticmethod
    def build_index(
        segy_path: str,
        dataset_id: Optional[str] = None,
        inline_byte: Optional[int] = None,
        crossline_byte: Optional[int] = None,
        geometry_qaqc: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        source = Path(segy_path).expanduser().resolve()

        if not source.exists():
            raise FileNotFoundError(f"SEG-Y file not found: {source}")

        if dataset_id is None:
            dataset_id = SegyIndexService.make_dataset_id(str(source))

        inline_header_byte = int(inline_byte) if inline_byte is not None else int(segyio.TraceField.INLINE_3D)
        crossline_header_byte = int(crossline_byte) if crossline_byte is not None else int(segyio.TraceField.CROSSLINE_3D)

        index_dir = SEGY_INDEX_DIR / dataset_id
        index_dir.mkdir(parents=True, exist_ok=True)

        with segyio.open(str(source), "r", ignore_geometry=True) as f:
            trace_count = int(f.tracecount)
            sample_count = int(len(f.samples))
            sample_interval_us = SegyIndexService._safe_int(f.bin[segyio.BinField.Interval])

            trace_inlines = np.empty(trace_count, dtype=np.int32)
            trace_crosslines = np.empty(trace_count, dtype=np.int32)
            trace_numbers = np.arange(trace_count, dtype=np.int64)

            for trace_idx in range(trace_count):
                header = f.header[trace_idx]

                inline = SegyIndexService._safe_int(header[inline_header_byte])
                crossline = SegyIndexService._safe_int(header[crossline_header_byte])

                trace_inlines[trace_idx] = inline if inline is not None else -2147483648
                trace_crosslines[trace_idx] = crossline if crossline is not None else -2147483648

            valid_mask = (
                (trace_inlines != -2147483648)
                & (trace_crosslines != -2147483648)
            )

            valid_inlines = trace_inlines[valid_mask]
            valid_crosslines = trace_crosslines[valid_mask]

            unique_inlines = np.unique(valid_inlines).astype(np.int32)
            unique_crosslines = np.unique(valid_crosslines).astype(np.int32)

            inline_sort_order = np.lexsort((trace_crosslines, trace_inlines)).astype(np.int64)
            crossline_sort_order = np.lexsort((trace_inlines, trace_crosslines)).astype(np.int64)

            is_3d = bool(unique_inlines.size > 1 and unique_crosslines.size > 1)
            shape = [int(unique_inlines.size), int(unique_crosslines.size), int(sample_count)]

            try:
                text_decode = write_textual_header_sidecars(index_dir, bytes(f.text[0]))
                text_header = text_decode.get("text", "")
                text_header_decode = {k: v for k, v in text_decode.items() if k != "text"}
            except Exception:
                text_header = ""
                text_header_decode = {
                    "selected_encoding": None,
                    "confidence": "failed",
                    "warnings": ["Failed to decode textual header."],
                }

            binary_header = {
                "sample_interval_us": sample_interval_us,
                "samples_per_trace": SegyIndexService._safe_int(f.bin[segyio.BinField.Samples]),
                "data_sample_format_code": SegyIndexService._safe_int(f.bin[segyio.BinField.Format]),
                "trace_sorting_code": SegyIndexService._safe_int(f.bin[segyio.BinField.SortingCode]),
                "measurement_system": SegyIndexService._safe_int(f.bin[segyio.BinField.MeasurementSystem]),
                "segy_revision": SegyIndexService._safe_int(f.bin[segyio.BinField.SEGYRevision]),
            }

        np.save(index_dir / "trace_inlines.npy", trace_inlines)
        np.save(index_dir / "trace_crosslines.npy", trace_crosslines)
        np.save(index_dir / "trace_numbers.npy", trace_numbers)
        np.save(index_dir / "unique_inlines.npy", unique_inlines)
        np.save(index_dir / "unique_crosslines.npy", unique_crosslines)
        np.save(index_dir / "inline_sort_order.npy", inline_sort_order)
        np.save(index_dir / "crossline_sort_order.npy", crossline_sort_order)

        (index_dir / "segy_text_header.txt").write_text(text_header, encoding="utf-8")
        (index_dir / "segy_binary_header.json").write_text(
            json.dumps(binary_header, indent=2),
            encoding="utf-8",
        )

        summary = {
            "dataset_id": dataset_id,
            "source_path": str(source),
            "index_dir": str(index_dir),
            "source_file_name": source.name,
            "source_size_bytes": source.stat().st_size,
            "trace_count": int(trace_count),
            "sample_count": int(sample_count),
            "sample_interval_us": sample_interval_us,
            "sample_interval_ms": (sample_interval_us / 1000.0) if sample_interval_us else None,
            "inline_header_byte": int(inline_header_byte),
            "crossline_header_byte": int(crossline_header_byte),
            "geometry_source": "source_intake_geometry_qaqc" if geometry_qaqc else "segy_trace_headers_default",
            "geometry_qaqc": geometry_qaqc,
            "inline_count": int(unique_inlines.size),
            "crossline_count": int(unique_crosslines.size),
            "shape": shape,
            "is_3d": is_3d,
            "axis_order": ["inline", "crossline", "sample"],
            "inline_min": int(unique_inlines.min()) if unique_inlines.size else None,
            "inline_max": int(unique_inlines.max()) if unique_inlines.size else None,
            "crossline_min": int(unique_crosslines.min()) if unique_crosslines.size else None,
            "crossline_max": int(unique_crosslines.max()) if unique_crosslines.size else None,
            "valid_trace_header_count": int(valid_mask.sum()),
            "invalid_trace_header_count": int((~valid_mask).sum()),
            "status": "indexed",
            "optimized_cache_status": "not_started",
            "read_mode": "indexed_segy",
            "text_header_encoding": text_header_decode.get("selected_encoding"),
            "text_header_confidence": text_header_decode.get("confidence"),
            "text_header_decode": text_header_decode,
        }

        (index_dir / "segy_index.json").write_text(
            json.dumps(summary, indent=2),
            encoding="utf-8",
        )

        return summary

    @staticmethod
    def load_index(dataset_id: str) -> Dict[str, Any]:
        index_path = SEGY_INDEX_DIR / dataset_id / "segy_index.json"

        if not index_path.exists():
            raise FileNotFoundError(f"SEG-Y index not found: {index_path}")

        return json.loads(index_path.read_text(encoding="utf-8"))

    @staticmethod
    def update_index(dataset_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Safely update an indexed SEG-Y record.

        This method belongs in SegyIndexService because segy_index.json is
        the canonical persistence record for indexed SEG-Y state, including
        attached optimized-cache status.
        """
        clean_id = str(dataset_id).replace("indexed-segy-", "", 1)
        index_path = SEGY_INDEX_DIR / clean_id / "segy_index.json"

        if not index_path.exists():
            raise FileNotFoundError(f"SEG-Y index not found: {index_path}")

        current = json.loads(index_path.read_text(encoding="utf-8"))
        if not isinstance(current, dict):
            raise ValueError(f"SEG-Y index is not a JSON object: {index_path}")

        current.update(updates)

        tmp_path = index_path.with_suffix(".json.tmp")
        tmp_path.write_text(
            json.dumps(current, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(index_path)

        return current

