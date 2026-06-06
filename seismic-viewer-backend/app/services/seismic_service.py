import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import segyio
import zarr
import numpy as np


class SeismicService:
    @staticmethod
    def _clean_expected_dataset_type(expected_dataset_type: Optional[str]) -> Optional[str]:
        clean = (expected_dataset_type or "").strip().lower() or None
        if clean not in {None, "2d_line", "3d_volume"}:
            raise ValueError(f"Unsupported expected_dataset_type: {expected_dataset_type!r}")
        return clean

    @staticmethod
    def _assert_metadata_matches_expected(metadata: Dict[str, Any], expected_dataset_type: Optional[str]) -> None:
        clean = SeismicService._clean_expected_dataset_type(expected_dataset_type)
        shape = list(metadata.get("shape") or [])
        is_3d = metadata.get("is_3d")
        if clean == "2d_line":
            if is_3d is True or len(shape) != 2:
                raise ValueError(
                    "2D conversion contract violated during metadata read: "
                    f"is_3d={is_3d}, shape={shape}"
                )
        if clean == "3d_volume":
            if is_3d is not True or len(shape) != 3:
                raise ValueError(
                    "3D conversion contract violated during metadata read: "
                    f"is_3d={is_3d}, shape={shape}"
                )

    @staticmethod
    def _infer_manual_3d_geometry(
        file_path: str,
        inline_byte: Optional[int] = None,
        crossline_byte: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Infer regular 3D geometry from SEG-Y trace headers without relying on
        segyio automatic geometry detection.

        When inline_byte/crossline_byte are supplied, they come from the
        backend Geometry QAQC gate and are treated as the authoritative
        conversion geometry for this job. Otherwise the legacy standard
        INLINE_3D/CROSSLINE_3D fields are used as a fallback.
        """
        resolved_inline_byte = int(inline_byte) if inline_byte is not None else int(segyio.TraceField.INLINE_3D)
        resolved_crossline_byte = int(crossline_byte) if crossline_byte is not None else int(segyio.TraceField.CROSSLINE_3D)
        geometry_source = "geometry_qaqc_trace_headers" if inline_byte is not None and crossline_byte is not None else "manual_trace_headers"

        with segyio.open(file_path, "r", ignore_geometry=True) as f:
            inline_values = []
            crossline_values = []

            for i in range(f.tracecount):
                header = f.header[i]
                inline = int(header[resolved_inline_byte])
                crossline = int(header[resolved_crossline_byte])

                if inline != 0 and crossline != 0:
                    inline_values.append(inline)
                    crossline_values.append(crossline)

            if not inline_values or not crossline_values:
                return None

            unique_inlines = sorted(set(inline_values))
            unique_crosslines = sorted(set(crossline_values))

            if len(unique_inlines) <= 1 or len(unique_crosslines) <= 1:
                return None

            return {
                "inlines": unique_inlines,
                "crosslines": unique_crosslines,
                "samples": f.samples.tolist(),
                "sample_rate": f.bin[segyio.BinField.Interval] / 1000.0,
                "trace_count": f.tracecount,
                "is_3d": True,
                "shape": (
                    len(unique_inlines),
                    len(unique_crosslines),
                    len(f.samples),
                ),
                "geometry_source": geometry_source,
                "inline_byte": resolved_inline_byte,
                "crossline_byte": resolved_crossline_byte,
                "missing_trace_fill": 0.0,
            }

    @staticmethod
    def get_segy_metadata(
        file_path: str,
        expected_dataset_type: Optional[str] = None,
        geometry_override: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        clean_expected_dataset_type = SeismicService._clean_expected_dataset_type(expected_dataset_type)
        if clean_expected_dataset_type == "2d_line":
            metadata = SeismicService._get_trace_sample_metadata(file_path)
            SeismicService._assert_metadata_matches_expected(metadata, clean_expected_dataset_type)
            return metadata

        if clean_expected_dataset_type == "3d_volume" and isinstance(geometry_override, dict):
            inline_byte = geometry_override.get("inline_byte")
            crossline_byte = geometry_override.get("crossline_byte")
            if inline_byte is not None and crossline_byte is not None:
                metadata = SeismicService._infer_manual_3d_geometry(
                    file_path,
                    inline_byte=int(inline_byte),
                    crossline_byte=int(crossline_byte),
                )
                if not metadata:
                    raise ValueError(
                        "Geometry QAQC override did not resolve valid 3D geometry: "
                        f"inline_byte={inline_byte}, crossline_byte={crossline_byte}"
                    )
                metadata["geometry_qaqc_selected"] = geometry_override
                SeismicService._assert_metadata_matches_expected(metadata, clean_expected_dataset_type)
                return metadata

        # First try segyio's automatic geometry handling.
        try:
            with segyio.open(file_path, "r", ignore_geometry=False) as f:
                is_3d = (
                    hasattr(f, "ilines")
                    and hasattr(f, "xlines")
                    and len(f.ilines) > 1
                    and len(f.xlines) > 1
                )

                if is_3d:
                    metadata = {
                        "inlines": f.ilines.tolist(),
                        "crosslines": f.xlines.tolist(),
                        "samples": f.samples.tolist(),
                        "sample_rate": f.bin[segyio.BinField.Interval] / 1000.0,
                        "trace_count": f.tracecount,
                        "is_3d": True,
                        "shape": (len(f.ilines), len(f.xlines), len(f.samples)),
                        "geometry_source": "segyio",
                        "missing_trace_fill": 0.0,
                    }
                    SeismicService._assert_metadata_matches_expected(metadata, clean_expected_dataset_type)
                    return metadata
        except Exception:
            pass

        # If segyio cannot infer geometry, try manual inline/crossline headers.
        manual_geometry = SeismicService._infer_manual_3d_geometry(file_path)
        if manual_geometry:
            SeismicService._assert_metadata_matches_expected(manual_geometry, clean_expected_dataset_type)
            return manual_geometry

        # Final fallback: valid SEG-Y but not displayable as a 3D cube.
        metadata = SeismicService._get_trace_sample_metadata(file_path)
        SeismicService._assert_metadata_matches_expected(metadata, clean_expected_dataset_type)
        return metadata

    @staticmethod
    def _get_trace_sample_metadata(file_path: str) -> Dict[str, Any]:
        try:
            with segyio.open(file_path, "r", ignore_geometry=True) as f:
                sample_interval_us = int(f.bin[segyio.BinField.Interval] or 0)
                sample_interval_ms = sample_interval_us / 1000.0 if sample_interval_us else None
                sample_interval_sec = sample_interval_us / 1000000.0 if sample_interval_us else None
                return {
                    "inlines": [],
                    "crosslines": [],
                    "samples": f.samples.tolist(),
                    "sample_rate": sample_interval_ms,
                    "sample_interval_us": sample_interval_us or None,
                    "sample_interval_ms": sample_interval_ms,
                    "sample_interval_sec": sample_interval_sec,
                    "trace_count": f.tracecount,
                    "is_3d": False,
                    "shape": (f.tracecount, len(f.samples)),
                    "geometry_source": "trace_sample_fallback",
                }
        except Exception as e:
            raise ValueError(f"Failed to parse SEG-Y file: {str(e)}")

    @staticmethod
    def _convert_manual_3d_to_zarr(
        segy_path: str,
        zarr_path: str,
        metadata: Dict[str, Any],
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """
        Fast manual SEG-Y -> 3D Zarr conversion using inline-batched writes.

        Instead of writing one trace at a time to Zarr, this accumulates
        multiple inline panels in memory and writes each block as:

            z[inline_start:inline_end, :, :] = block

        This is much faster for large sparse 3D SEG-Y volumes.
        Missing trace positions are filled with 0.0.
        """
        inlines = metadata["inlines"]
        crosslines = metadata["crosslines"]
        shape = tuple(metadata["shape"])

        n_inline, n_crossline, n_samples = shape

        inline_index = {inline: idx for idx, inline in enumerate(inlines)}
        crossline_index = {crossline: idx for idx, crossline in enumerate(crosslines)}

        # Chunking chosen for viewer-friendly slicing and efficient block writes.
        chunks = (
            min(16, n_inline),
            min(64, n_crossline),
            min(128, n_samples),
        )

        z = zarr.open(
            zarr_path,
            mode="w",
            shape=shape,
            chunks=chunks,
            dtype="f4",
            fill_value=0.0,
        )

        batch_size = min(16, n_inline)

        current_batch_start = None
        current_batch_end = None
        current_block = None
        current_block_has_data = False

        written_traces = 0
        skipped_traces = 0
        batch_writes = 0

        def emit_progress(processed_inlines: int) -> None:
            if progress_callback is None:
                return
            try:
                progress_callback({
                    "stage": "writing_zarr",
                    "processed_inlines": max(0, min(int(processed_inlines), int(n_inline))),
                    "total_inlines": int(n_inline),
                    "processed_traces": int(written_traces),
                    "total_traces": int(metadata.get("trace_count") or 0),
                    "batch_writes": int(batch_writes),
                    "batch_size_inlines": int(batch_size),
                    "shape": list(shape),
                })
            except Exception:
                # Progress telemetry must never fail conversion.
                pass

        def flush_current_block():
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
                emit_progress(current_batch_end)

            current_batch_start = None
            current_batch_end = None
            current_block = None
            current_block_has_data = False

        with segyio.open(segy_path, "r", ignore_geometry=True) as f:
            for trace_idx in range(f.tracecount):
                header = f.header[trace_idx]
                inline_byte = int(metadata.get("inline_byte") or int(segyio.TraceField.INLINE_3D))
                crossline_byte = int(metadata.get("crossline_byte") or int(segyio.TraceField.CROSSLINE_3D))
                inline = int(header[inline_byte])
                crossline = int(header[crossline_byte])

                i_idx = inline_index.get(inline)
                x_idx = crossline_index.get(crossline)

                if i_idx is None or x_idx is None:
                    skipped_traces += 1
                    continue

                desired_batch_start = (i_idx // batch_size) * batch_size
                desired_batch_end = min(desired_batch_start + batch_size, n_inline)

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
                current_block[local_i, x_idx, :] = f.trace[trace_idx]
                current_block_has_data = True
                written_traces += 1

            flush_current_block()

        return {
            "shape": list(shape),
            "chunks": list(chunks),
            "dtype": "float32",
            "axis_order": ["inline", "crossline", "sample"],
            "is_3d": True,
            "trace_count": metadata.get("trace_count"),
            "geometry_source": metadata.get("geometry_source", "manual_trace_headers"),
            "missing_trace_fill": 0.0,
            "written_traces": written_traces,
            "skipped_traces": skipped_traces,
            "batch_size_inlines": batch_size,
            "batch_writes": batch_writes,
            "expected_trace_positions": shape[0] * shape[1],
            "missing_trace_positions": (shape[0] * shape[1]) - written_traces,
        }

    @staticmethod
    def convert_to_zarr(
        segy_path: str,
        zarr_path: str,
        expected_dataset_type: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        geometry_override: Optional[Dict[str, Any]] = None,
    ):
        clean_expected_dataset_type = SeismicService._clean_expected_dataset_type(expected_dataset_type)
        metadata = SeismicService.get_segy_metadata(
            segy_path,
            expected_dataset_type=clean_expected_dataset_type,
            geometry_override=geometry_override,
        )
        SeismicService._assert_metadata_matches_expected(metadata, clean_expected_dataset_type)

        if clean_expected_dataset_type == "2d_line":
            metadata = SeismicService._get_trace_sample_metadata(segy_path)
            SeismicService._assert_metadata_matches_expected(metadata, clean_expected_dataset_type)

        if clean_expected_dataset_type == "3d_volume" and metadata.get("is_3d") is not True:
            raise ValueError("3D conversion request did not resolve to valid 3D geometry.")

        if metadata.get("is_3d") is True:
            conversion_info = SeismicService._convert_manual_3d_to_zarr(
                segy_path=segy_path,
                zarr_path=zarr_path,
                metadata=metadata,
                progress_callback=progress_callback,
            )

            SeismicService.write_segy_header_sidecars(
                segy_path=segy_path,
                zarr_path=zarr_path,
                conversion_info=conversion_info,
            )
            return conversion_info

        # Non-3D fallback: preserve a 2D trace × sample Zarr for inspection,
        # but the job layer should reject this for the current 3D viewer.
        with segyio.open(segy_path, "r", ignore_geometry=True) as f:
            shape = (f.tracecount, len(f.samples))
            chunks = (
                (1000, 512)
                if shape[0] >= 1000 and shape[1] >= 512
                else None
            )

            z = zarr.open(
                zarr_path,
                mode="w",
                shape=shape,
                chunks=chunks,
                dtype="f4",
            )

            for i in range(f.tracecount):
                z[i] = f.trace[i]

            sample_interval_us = int(f.bin[segyio.BinField.Interval] or 0)
            sample_interval_ms = sample_interval_us / 1000.0 if sample_interval_us else None
            sample_interval_sec = sample_interval_us / 1000000.0 if sample_interval_us else None

            conversion_info = {
                "shape": list(shape),
                "chunks": list(chunks) if chunks else None,
                "dtype": "float32",
                "axis_order": ["trace", "sample"],
                "is_3d": False,
                "trace_count": f.tracecount,
                "geometry_fallback": True,
                "sample_interval_us": sample_interval_us or None,
                "sample_interval_ms": sample_interval_ms,
                "sample_interval_sec": sample_interval_sec,
                "sample_rate": sample_interval_ms,
            }

        SeismicService.write_segy_header_sidecars(
            segy_path=segy_path,
            zarr_path=zarr_path,
            conversion_info=conversion_info,
        )
        return conversion_info

    @staticmethod
    def write_segy_header_sidecars(
        segy_path: str,
        zarr_path: str,
        conversion_info: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        """
        Preserve source SEG-Y header information beside the generated Zarr store.

        Output layout:
          <name>.zarr
          <name>.viewer_metadata.json
          <name>.segy_text_header.txt
          <name>.segy_binary_header.json
          <name>.trace_header_summary.json
        """
        conversion_info = conversion_info or {}

        zarr_file = Path(zarr_path)
        output_dir = zarr_file.parent
        base_name = zarr_file.name[:-5] if zarr_file.name.endswith(".zarr") else zarr_file.stem

        text_header_file = output_dir / f"{base_name}.segy_text_header.txt"
        binary_header_file = output_dir / f"{base_name}.segy_binary_header.json"
        trace_summary_file = output_dir / f"{base_name}.trace_header_summary.json"
        viewer_metadata_file = output_dir / f"{base_name}.viewer_metadata.json"

        output_dir.mkdir(parents=True, exist_ok=True)

        text_header, text_encoding = SeismicService._extract_textual_header(segy_path)
        text_header_file.write_text(text_header, encoding="utf-8")

        binary_header = SeismicService._extract_binary_header(segy_path)
        binary_header_file.write_text(
            json.dumps(binary_header, indent=2),
            encoding="utf-8",
        )

        trace_summary = SeismicService._extract_trace_header_summary(segy_path)
        trace_summary_file.write_text(
            json.dumps(trace_summary, indent=2),
            encoding="utf-8",
        )

        sample_interval_us = (
            conversion_info.get("sample_interval_us")
            or binary_header.get("sample_interval_us")
        )
        sample_interval_ms = (
            conversion_info.get("sample_interval_ms")
            or (sample_interval_us / 1000.0 if sample_interval_us else None)
        )
        sample_interval_sec = (
            conversion_info.get("sample_interval_sec")
            or (sample_interval_us / 1000000.0 if sample_interval_us else None)
        )

        viewer_metadata = {
            "source": {
                "filename": os.path.basename(segy_path),
                "converted_at": datetime.now(timezone.utc).isoformat(),
                "converter_version": "0.1",
            },
            "volume": {
                "zarr_path": f"/data/zarr/{zarr_file.name}",
                "shape": conversion_info.get("shape"),
                "chunks": conversion_info.get("chunks"),
                "dtype": conversion_info.get("dtype", "float32"),
                "axis_order": conversion_info.get("axis_order"),
                "is_3d": conversion_info.get("is_3d"),
                "trace_count": conversion_info.get("trace_count"),
                "geometry_fallback": conversion_info.get("geometry_fallback", False),
            },
            "segy_headers": {
                "text_encoding": text_encoding,
                "text_header_file": text_header_file.name,
                "binary_header_file": binary_header_file.name,
                "trace_header_summary_file": trace_summary_file.name,
            },
        }

        viewer_metadata_file.write_text(
            json.dumps(viewer_metadata, indent=2),
            encoding="utf-8",
        )

        return {
            "viewer_metadata": str(viewer_metadata_file),
            "text_header": str(text_header_file),
            "binary_header": str(binary_header_file),
            "trace_header_summary": str(trace_summary_file),
        }

    @staticmethod
    def _extract_textual_header(segy_path: str) -> tuple[str, str]:
        with open(segy_path, "rb") as f:
            raw = f.read(3200)

        candidates = [
            ("ebcdic", "cp500"),
            ("ascii", "ascii"),
        ]

        best_text = ""
        best_encoding = "unknown"
        best_score = -1

        for label, codec_name in candidates:
            decoded = raw.decode(codec_name, errors="replace")

            printable_count = sum(
                1 for ch in decoded if ch.isprintable() or ch in "\r\n\t"
            )

            if printable_count > best_score:
                best_score = printable_count
                best_text = decoded
                best_encoding = label

        lines = [
            best_text[i : i + 80].rstrip()
            for i in range(0, min(len(best_text), 3200), 80)
        ]

        while len(lines) < 40:
            lines.append("")

        return "\n".join(lines[:40]) + "\n", best_encoding

    @staticmethod
    def _extract_binary_header(segy_path: str) -> Dict[str, Any]:
        with segyio.open(segy_path, "r", ignore_geometry=True) as f:
            binary = f.bin

            def read_bin(field) -> Any:
                try:
                    return int(binary[field])
                except Exception:
                    return None

            return {
                "sample_interval_us": read_bin(segyio.BinField.Interval),
                "samples_per_trace": read_bin(segyio.BinField.Samples),
                "data_sample_format_code": read_bin(segyio.BinField.Format),
                "trace_sorting_code": read_bin(segyio.BinField.SortingCode),
                "measurement_system": read_bin(segyio.BinField.MeasurementSystem),
                "ensemble_fold": read_bin(segyio.BinField.EnsembleFold),
                "segy_revision": read_bin(segyio.BinField.SEGYRevision),
            }

    @staticmethod
    def _extract_trace_header_summary(segy_path: str) -> Dict[str, Any]:
        with segyio.open(segy_path, "r", ignore_geometry=True) as f:
            trace_count = int(f.tracecount)

            def read_trace_header(trace_index: int) -> Dict[str, Any]:
                header = f.header[trace_index]

                def read_field(field) -> Any:
                    try:
                        return int(header[field])
                    except Exception:
                        return None

                return {
                    "trace_index": trace_index,
                    "inline_189": read_field(segyio.TraceField.INLINE_3D),
                    "crossline_193": read_field(segyio.TraceField.CROSSLINE_3D),
                    "cdp_x": read_field(segyio.TraceField.CDP_X),
                    "cdp_y": read_field(segyio.TraceField.CDP_Y),
                    "source_x": read_field(segyio.TraceField.SourceX),
                    "source_y": read_field(segyio.TraceField.SourceY),
                    "group_x": read_field(segyio.TraceField.GroupX),
                    "group_y": read_field(segyio.TraceField.GroupY),
                    "coordinate_scalar": read_field(segyio.TraceField.SourceGroupScalar),
                    "sample_interval_us": read_field(segyio.TraceField.TRACE_SAMPLE_INTERVAL),
                    "samples_in_trace": read_field(segyio.TraceField.TRACE_SAMPLE_COUNT),
                }

            first_trace_header = read_trace_header(0) if trace_count > 0 else {}

            sample_indices = sorted(
                set(
                    i
                    for i in [
                        0,
                        trace_count // 4,
                        trace_count // 2,
                        (trace_count * 3) // 4,
                        trace_count - 1,
                    ]
                    if 0 <= i < trace_count
                )
            )

            sampled_trace_headers = [read_trace_header(i) for i in sample_indices]

            inline_values = [
                h["inline_189"]
                for h in sampled_trace_headers
                if h.get("inline_189") not in (None, 0)
            ]
            crossline_values = [
                h["crossline_193"]
                for h in sampled_trace_headers
                if h.get("crossline_193") not in (None, 0)
            ]
            cdp_x_values = [
                h["cdp_x"]
                for h in sampled_trace_headers
                if h.get("cdp_x") not in (None, 0)
            ]
            cdp_y_values = [
                h["cdp_y"]
                for h in sampled_trace_headers
                if h.get("cdp_y") not in (None, 0)
            ]

            return {
                "trace_count": trace_count,
                "first_trace_header": first_trace_header,
                "sampled_trace_headers": sampled_trace_headers,
                "detected_or_assumed_inline_byte_location": 189,
                "detected_or_assumed_crossline_byte_location": 193,
                "inline_min_sampled": min(inline_values) if inline_values else None,
                "inline_max_sampled": max(inline_values) if inline_values else None,
                "crossline_min_sampled": min(crossline_values) if crossline_values else None,
                "crossline_max_sampled": max(crossline_values) if crossline_values else None,
                "cdp_x_min_sampled": min(cdp_x_values) if cdp_x_values else None,
                "cdp_x_max_sampled": max(cdp_x_values) if cdp_x_values else None,
                "cdp_y_min_sampled": min(cdp_y_values) if cdp_y_values else None,
                "cdp_y_max_sampled": max(cdp_y_values) if cdp_y_values else None,
                "note": (
                    "Trace header ranges are sampled, not full-volume scanned. "
                    "Inline and crossline byte locations vary between SEG-Y files."
                ),
            }
