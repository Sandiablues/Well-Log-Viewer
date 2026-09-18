import sys
from pathlib import Path
import segyio
import numpy as np

if len(sys.argv) < 2:
    print("Usage: python inspect_segy.py /path/to/Seismic_data.sgy")
    sys.exit(1)

path = Path(sys.argv[1])

if not path.exists():
    print(f"File not found: {path}")
    sys.exit(1)

print(f"Inspecting: {path}")
print(f"Size: {path.stat().st_size / (1024**2):.1f} MB")

with segyio.open(str(path), "r", ignore_geometry=True) as f:
    trace_count = f.tracecount
    sample_count = len(f.samples)

    print("\nBasic SEG-Y info")
    print("----------------")
    print(f"Trace count:   {trace_count}")
    print(f"Sample count:  {sample_count}")
    print(f"First sample:  {f.samples[0]}")
    print(f"Last sample:   {f.samples[-1]}")
    if sample_count > 1:
        print(f"Sample step:   {f.samples[1] - f.samples[0]}")

    print("\nTesting likely inline/crossline header fields")
    print("--------------------------------------------")

    candidates = {
        "INLINE_3D": segyio.TraceField.INLINE_3D,
        "CROSSLINE_3D": segyio.TraceField.CROSSLINE_3D,
        "FieldRecord": segyio.TraceField.FieldRecord,
        "TraceNumber": segyio.TraceField.TraceNumber,
        "CDP": segyio.TraceField.CDP,
        "CDP_TRACE": segyio.TraceField.CDP_TRACE,
    }

    for name, field in candidates.items():
        try:
            vals = np.array(f.attributes(field)[:])
            unique = np.unique(vals)
            print(f"{name:15s} byte={int(field):4d}  unique={len(unique):6d}  min={unique.min()}  max={unique.max()}")
        except Exception as e:
            print(f"{name:15s} failed: {e}")

    print("\nFirst 10 trace headers for likely fields")
    print("----------------------------------------")
    for i in range(min(10, trace_count)):
        h = f.header[i]
        try:
            il = h[segyio.TraceField.INLINE_3D]
            xl = h[segyio.TraceField.CROSSLINE_3D]
            cdp = h[segyio.TraceField.CDP]
            tr = h[segyio.TraceField.TraceNumber]
            print(f"trace {i:4d}: INLINE_3D={il}, CROSSLINE_3D={xl}, CDP={cdp}, TraceNumber={tr}")
        except Exception as e:
            print(f"trace {i:4d}: header read failed: {e}")
