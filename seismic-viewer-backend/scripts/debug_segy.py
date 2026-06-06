import segyio
import sys

file_path = "/home/team/shared/data/small.sgy"

print(f"Trying to open {file_path} with ignore_geometry=False")
try:
    with segyio.open(file_path, "r", ignore_geometry=False) as f:
        print("Success with ignore_geometry=False")
        print(f"Traces: {f.tracecount}")
except Exception as e:
    print(f"Failed with ignore_geometry=False: {e}")

print(f"\nTrying to open {file_path} with ignore_geometry=True")
try:
    with segyio.open(file_path, "r", ignore_geometry=True) as f:
        print("Success with ignore_geometry=True")
        print(f"Traces: {f.tracecount}")
        print(f"Samples: {len(f.samples)}")
except Exception as e:
    print(f"Failed with ignore_geometry=True: {e}")
