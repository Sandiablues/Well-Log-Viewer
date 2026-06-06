import segyio
import numpy as np
import os

def create_dummy_segy(filename, n_inlines=10, n_crosslines=10, n_samples=100):
    spec = segyio.spec()
    spec.ilines = np.arange(1, n_inlines + 1)
    spec.xlines = np.arange(1, n_crosslines + 1)
    spec.samples = np.arange(n_samples) * 4 # 4ms sample rate
    spec.format = 1 # IBM Float
    spec.sorting = 2 # Inline sorting
    
    with segyio.create(filename, spec) as f:
        # Create some synthetic data (e.g., a simple sine wave)
        for i in range(n_inlines):
            for j in range(n_crosslines):
                trace = np.sin(np.linspace(0, 4 * np.pi, n_samples)) + np.random.normal(0, 0.1, n_samples)
                f.trace[i * n_crosslines + j] = trace.astype('f4')
                
                # Set trace headers
                f.header[i * n_crosslines + j] = {
                    segyio.TraceField.INLINE_3D: i + 1,
                    segyio.TraceField.CROSSLINE_3D: j + 1,
                    segyio.TraceField.CDP_X: (i + 1) * 100,
                    segyio.TraceField.CDP_Y: (j + 1) * 100,
                }

if __name__ == "__main__":
    output_path = "/home/team/shared/seismic-viewer-backend/data/uploads/dummy.sgy"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    create_dummy_segy(output_path)
    print(f"Created dummy SEG-Y at {output_path}")
