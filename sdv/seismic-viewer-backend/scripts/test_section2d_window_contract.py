from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import numpy as np
import zarr


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="section2d_window_contract_"))
    try:
        zarr_root = tmp / "zarr"
        zarr_root.mkdir(parents=True, exist_ok=True)
        os.environ["ZARR_DIR"] = str(zarr_root)

        arr_path = zarr_root / "contract_line.zarr"
        data = np.arange(100 * 200, dtype=np.float32).reshape(100, 200)
        arr = zarr.open_array(str(arr_path), mode="w", shape=data.shape, dtype="float32", chunks=(25, 50))
        arr[:] = data

        from app.services.sections2d_service import get_2d_section_preview, get_2d_section_window

        window_payload = get_2d_section_window(
            zarr_path="/data/zarr/contract_line.zarr",
            trace_start=10,
            trace_end=60,
            sample_start=20,
            sample_end=120,
            output_width=25,
            output_height=50,
            clip_percentile=99.0,
            processing_mode="raw",
            sample_interval_sec=0.004,
            agc_window_sec=0.5,
            filter_type="none",
            f1=None,
            f2=None,
            f3=None,
            f4=None,
        )

        require(window_payload["source_shape"] == [100, 200], f"source_shape mismatch: {window_payload.get('source_shape')}")
        require(window_payload["shape"] == [25, 50], f"shape mismatch: {window_payload.get('shape')}")
        require(window_payload["windowed"] is True, "windowed flag must be true")
        require(window_payload["preview"] is True, "preview flag must remain true")
        require(window_payload["source_window"]["trace_start"] == 10, "trace_start mismatch")
        require(window_payload["source_window"]["trace_end"] == 60, "trace_end mismatch")
        require(window_payload["source_window"]["sample_start"] == 20, "sample_start mismatch")
        require(window_payload["source_window"]["sample_end"] == 120, "sample_end mismatch")
        require(abs(float(window_payload["trace_stride"]) - 2.0) < 1e-6, f"trace_stride mismatch: {window_payload.get('trace_stride')}")
        require(abs(float(window_payload["sample_stride"]) - 2.0) < 1e-6, f"sample_stride mismatch: {window_payload.get('sample_stride')}")
        require(len(window_payload["data"]) == 25 * 50, f"data length mismatch: {len(window_payload.get('data', []))}")
        require(float(window_payload["clip_abs"]) > 0.0, "clip_abs must be positive")
        require(float(window_payload["render_time_ms"]) >= 0.0, "window render_time_ms must be present and non-negative")
        require(window_payload["source_window_pixel_count"] == 50 * 100, "window source_window_pixel_count mismatch")
        require(window_payload["output_pixel_count"] == 25 * 50, "window output_pixel_count mismatch")

        preview_payload = get_2d_section_preview(
            zarr_path="/data/zarr/contract_line.zarr",
            max_width=50,
            max_height=80,
            clip_percentile=99.0,
            processing_mode="raw",
            sample_interval_sec=0.004,
            agc_window_sec=0.5,
            filter_type="none",
            f1=None,
            f2=None,
            f3=None,
            f4=None,
        )

        require(preview_payload["source_shape"] == [100, 200], f"preview source_shape mismatch: {preview_payload.get('source_shape')}")
        require(preview_payload["windowed"] is False, "preview windowed flag must be false")
        require(preview_payload["preview"] is True, "preview flag must be true")
        require(len(preview_payload["data"]) == int(preview_payload["shape"][0]) * int(preview_payload["shape"][1]), "preview data length mismatch")
        require(float(preview_payload["render_time_ms"]) >= 0.0, "preview render_time_ms must be present and non-negative")
        require(preview_payload["source_window_pixel_count"] == 100 * 200, "preview source_window_pixel_count mismatch")
        require(preview_payload["output_pixel_count"] == int(preview_payload["shape"][0]) * int(preview_payload["shape"][1]), "preview output_pixel_count mismatch")

        print("PASS section2d window and preview contract")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
