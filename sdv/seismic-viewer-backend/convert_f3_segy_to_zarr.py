import sys
from pathlib import Path
import numpy as np
import segyio
import zarr
import numcodecs

if len(sys.argv) < 3:
    print("Usage: python convert_f3_segy_to_zarr.py /path/to/Seismic_data.sgy /path/to/output.zarr")
    sys.exit(1)

segy_path = Path(sys.argv[1])
out_path = Path(sys.argv[2])

if not segy_path.exists():
    raise FileNotFoundError(segy_path)

if out_path.exists():
    raise RuntimeError(f"Output already exists: {out_path}\nDelete it first if you want to rebuild it.")

print(f"Reading SEG-Y: {segy_path}")
print(f"Writing Zarr:  {out_path}")

with segyio.open(str(segy_path), "r", ignore_geometry=True) as f:
    trace_count = f.tracecount
    samples = np.asarray(f.samples, dtype=np.float32)
    sample_count = len(samples)

    inlines = np.asarray(f.attributes(segyio.TraceField.INLINE_3D)[:], dtype=np.int32)
    xlines = np.asarray(f.attributes(segyio.TraceField.CROSSLINE_3D)[:], dtype=np.int32)

    il_min, il_max = int(inlines.min()), int(inlines.max())
    xl_min, xl_max = int(xlines.min()), int(xlines.max())

    n_il = il_max - il_min + 1
    n_xl = xl_max - xl_min + 1
    n_samp = sample_count

    print("\nDetected geometry")
    print("-----------------")
    print(f"Trace count:      {trace_count}")
    print(f"Inline range:     {il_min}-{il_max} ({n_il})")
    print(f"Crossline range:  {xl_min}-{xl_max} ({n_xl})")
    print(f"Samples:          {n_samp}")
    print(f"Sample start:     {samples[0]}")
    print(f"Sample end:       {samples[-1]}")
    print(f"Sample interval:  {samples[1] - samples[0] if n_samp > 1 else 'n/a'}")

    expected_traces = n_il * n_xl
    print(f"Full grid traces: {expected_traces}")
    print(f"Missing traces:   {expected_traces - trace_count}")

    chunks = (16, 16, 128)

    compressor = numcodecs.Blosc(
        cname="zstd",
        clevel=3,
        shuffle=numcodecs.Blosc.BITSHUFFLE,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)

    arr = zarr.open_array(
        str(out_path),
        mode="w",
        shape=(n_il, n_xl, n_samp),
        chunks=chunks,
        dtype="float32",
        compressor=compressor,
        fill_value=0.0,
        zarr_format=2,
    )

    arr.attrs["axis_order"] = ["inline", "crossline", "sample"]
    arr.attrs["inline_min"] = il_min
    arr.attrs["inline_max"] = il_max
    arr.attrs["crossline_min"] = xl_min
    arr.attrs["crossline_max"] = xl_max
    arr.attrs["sample_start"] = float(samples[0])
    arr.attrs["sample_end"] = float(samples[-1])
    arr.attrs["sample_interval"] = float(samples[1] - samples[0]) if n_samp > 1 else None
    arr.attrs["source_file"] = str(segy_path)
    arr.attrs["missing_trace_fill"] = 0.0

    print("\nConverting traces...")
    print("--------------------")

    current_il = None
    current_il_idx = None
    line_buffer = None
    written_lines = 0

    def flush_line():
        global_placeholder = None
        return global_placeholder

    for trace_idx in range(trace_count):
        il = int(inlines[trace_idx])
        xl = int(xlines[trace_idx])

        il_idx = il - il_min
        xl_idx = xl - xl_min

        if current_il is None:
            current_il = il
            current_il_idx = il_idx
            line_buffer = np.zeros((n_xl, n_samp), dtype=np.float32)

        if il != current_il:
            arr[current_il_idx, :, :] = line_buffer
            written_lines += 1
            if written_lines % 25 == 0:
                print(f"Written inline {written_lines}/{n_il}")

            current_il = il
            current_il_idx = il_idx
            line_buffer = np.zeros((n_xl, n_samp), dtype=np.float32)

        line_buffer[xl_idx, :] = f.trace[trace_idx].astype(np.float32, copy=False)

    if line_buffer is not None and current_il_idx is not None:
        arr[current_il_idx, :, :] = line_buffer
        written_lines += 1

    print(f"Written inline {written_lines}/{n_il}")

print("\nDone.")
print(f"Zarr written to: {out_path}")
