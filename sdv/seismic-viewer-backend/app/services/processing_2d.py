"""
2D seismic preview processing.

This module replaces the earlier inline endpoint-only display conditioning.

Design intent:
- Preserve stored Zarr data unchanged.
- Process only the preview array returned to the viewer.
- Keep operations explicit and testable.
- Follow Seismic Unix behavior where practical:
  - sugain-style demean, RMS balance, AGC windowing, percentile clip
  - sufilter-style zero-phase sine-squared tapered frequency filters
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np


_EPS = 1.0e-12


FilterType = Literal["none", "bandpass", "lowpass", "highpass"]


@dataclass
class Processing2DInfo:
    processing_mode: str
    demean: bool
    rms_balance: bool
    agc: bool
    agc_window_sec: float
    agc_window_samples: int
    filter_type: str
    f1: float | None
    f2: float | None
    f3: float | None
    f4: float | None
    sample_interval_sec: float
    nyquist_hz: float
    clip_percentile: float
    clip_abs: float


def _as_float32_2d(data: np.ndarray) -> np.ndarray:
    arr = np.asarray(data, dtype=np.float32)
    if arr.ndim != 2:
        raise ValueError(f"Expected 2D array [trace, sample], got shape {arr.shape}")
    return arr.copy()


def demean_traces(data: np.ndarray) -> np.ndarray:
    """Subtract per-trace mean. Equivalent to a simple SU mbal-style debias."""
    return data - np.mean(data, axis=1, keepdims=True, dtype=np.float64).astype(np.float32)


def rms_balance_traces(data: np.ndarray) -> np.ndarray:
    """Divide each trace by its RMS amplitude. Similar purpose to sugain pbal."""
    rms = np.sqrt(np.mean(data * data, axis=1, keepdims=True, dtype=np.float64)).astype(np.float32)
    rms = np.where(rms > _EPS, rms, 1.0).astype(np.float32)
    return data / rms


def percentile_clip_value(data: np.ndarray, clip_percentile: float = 99.0) -> float:
    """Return absolute clip value from non-zero amplitudes."""
    pct = float(np.clip(clip_percentile, 50.0, 99.99))
    abs_values = np.abs(data)
    nonzero = abs_values[abs_values > 0]
    if nonzero.size == 0:
        return 1.0
    value = float(np.percentile(nonzero, pct))
    if not np.isfinite(value) or value <= 0:
        return 1.0
    return value


def clip_by_abs_value(data: np.ndarray, clip_abs: float) -> np.ndarray:
    """Hard clip amplitudes by absolute value."""
    if clip_abs <= 0 or not np.isfinite(clip_abs):
        return data
    return np.clip(data, -clip_abs, clip_abs).astype(np.float32)


def agc_traces(data: np.ndarray, sample_interval_sec: float, agc_window_sec: float = 0.5) -> tuple[np.ndarray, int]:
    """
    Sliding RMS AGC.

    SU exposes wagc in seconds. This implementation computes a centered moving
    RMS envelope per trace and divides by it. It is intentionally simple,
    deterministic, and suitable for preview processing.
    """
    dt = float(sample_interval_sec)
    if dt <= 0 or not np.isfinite(dt):
        dt = 0.004

    window_sec = float(agc_window_sec)
    if window_sec <= 0 or not np.isfinite(window_sec):
        window_sec = 0.5

    window_samples = max(3, int(round(window_sec / dt)))
    if window_samples % 2 == 0:
        window_samples += 1

    # Avoid a nonsensical AGC window longer than the displayed trace.
    n_samples = data.shape[1]
    window_samples = min(window_samples, max(3, n_samples if n_samples % 2 == 1 else n_samples - 1))
    if window_samples < 3:
        return data.astype(np.float32), window_samples

    kernel = np.ones(window_samples, dtype=np.float32) / float(window_samples)

    out = np.empty_like(data, dtype=np.float32)

    for i in range(data.shape[0]):
        trace = data[i].astype(np.float32, copy=False)
        power = trace * trace
        local_power = np.convolve(power, kernel, mode="same")
        envelope = np.sqrt(np.maximum(local_power, _EPS)).astype(np.float32)
        out[i] = trace / envelope

    return out, window_samples


def _sine_squared_ramp(x: np.ndarray) -> np.ndarray:
    """0..1 smooth ramp using sine squared."""
    x = np.clip(x, 0.0, 1.0)
    return np.sin(0.5 * np.pi * x) ** 2


def _build_taper_response(
    freqs: np.ndarray,
    filter_type: FilterType,
    f1: float | None,
    f2: float | None,
    f3: float | None,
    f4: float | None,
    nyquist_hz: float,
) -> np.ndarray:
    """
    Build a zero-phase amplitude response using sine-squared tapers.

    Bandpass uses f1,f2,f3,f4:
      0 below f1
      sine^2 ramp f1->f2
      1 from f2->f3
      sine^2 ramp down f3->f4
      0 above f4

    Lowpass uses f3,f4 as pass-to-stop transition.
    Highpass uses f1,f2 as stop-to-pass transition.
    """
    response = np.ones_like(freqs, dtype=np.float32)

    if filter_type == "none":
        return response

    nyq = float(nyquist_hz)
    if nyq <= 0:
        return response

    def clean(v: float | None, default: float) -> float:
        if v is None:
            return default
        try:
            fv = float(v)
        except Exception:
            return default
        if not np.isfinite(fv):
            return default
        return float(np.clip(fv, 0.0, nyq))

    if filter_type == "bandpass":
        a = clean(f1, 0.10 * nyq)
        b = clean(f2, 0.15 * nyq)
        c = clean(f3, 0.45 * nyq)
        d = clean(f4, 0.50 * nyq)
        a, b, c, d = sorted([a, b, c, d])

        response[:] = 0.0
        if b > a:
            up = (freqs >= a) & (freqs < b)
            response[up] = _sine_squared_ramp((freqs[up] - a) / (b - a))
        response[(freqs >= b) & (freqs <= c)] = 1.0
        if d > c:
            down = (freqs > c) & (freqs <= d)
            response[down] = _sine_squared_ramp((d - freqs[down]) / (d - c))
        response[freqs > d] = 0.0
        return response.astype(np.float32)

    if filter_type == "lowpass":
        c = clean(f3, 0.45 * nyq)
        d = clean(f4, 0.50 * nyq)
        c, d = sorted([c, d])

        response[:] = 1.0
        if d > c:
            down = (freqs > c) & (freqs <= d)
            response[down] = _sine_squared_ramp((d - freqs[down]) / (d - c))
        response[freqs > d] = 0.0
        return response.astype(np.float32)

    if filter_type == "highpass":
        a = clean(f1, 0.10 * nyq)
        b = clean(f2, 0.15 * nyq)
        a, b = sorted([a, b])

        response[:] = 0.0
        if b > a:
            up = (freqs >= a) & (freqs < b)
            response[up] = _sine_squared_ramp((freqs[up] - a) / (b - a))
        response[freqs >= b] = 1.0
        return response.astype(np.float32)

    return response


def frequency_filter_traces(
    data: np.ndarray,
    sample_interval_sec: float,
    filter_type: FilterType = "none",
    f1: float | None = None,
    f2: float | None = None,
    f3: float | None = None,
    f4: float | None = None,
) -> tuple[np.ndarray, float]:
    """
    Apply zero-phase FFT-domain sine-squared tapered filter trace-by-trace.

    This is the NumPy equivalent of the SU sufilter idea, not a direct C port.
    """
    ft = (filter_type or "none").lower().strip()
    if ft not in ("none", "bandpass", "lowpass", "highpass"):
        raise ValueError("filter_type must be one of: none, bandpass, lowpass, highpass")

    if ft == "none":
        dt = sample_interval_sec if sample_interval_sec > 0 else 0.004
        return data.astype(np.float32), 0.5 / dt

    dt = float(sample_interval_sec)
    if dt <= 0 or not np.isfinite(dt):
        dt = 0.004

    n_samples = data.shape[1]
    if n_samples < 4:
        return data.astype(np.float32), 0.5 / dt

    freqs = np.fft.rfftfreq(n_samples, d=dt)
    nyquist = float(0.5 / dt)
    response = _build_taper_response(freqs, ft, f1, f2, f3, f4, nyquist)

    spectrum = np.fft.rfft(data, axis=1)
    spectrum *= response[None, :]
    filtered = np.fft.irfft(spectrum, n=n_samples, axis=1)

    return filtered.astype(np.float32), nyquist


def process_2d_section(
    data: np.ndarray,
    *,
    sample_interval_sec: float = 0.004,
    processing_mode: str = "raw",
    clip_percentile: float = 99.0,
    agc_window_sec: float = 0.5,
    filter_type: FilterType = "none",
    f1: float | None = None,
    f2: float | None = None,
    f3: float | None = None,
    f4: float | None = None,
) -> tuple[np.ndarray, Processing2DInfo]:
    """
    Process a 2D preview section.

    Backward-compatible processing modes:
      raw       -> no amplitude conditioning
      demean    -> per-trace mean removal
      trace_rms -> demean + per-trace RMS balance
      agc       -> demean + sliding RMS AGC

    Filter can be applied in addition to the mode.
    """
    mode = (processing_mode or "raw").lower().strip()
    if mode not in ("raw", "demean", "trace_rms", "agc"):
        raise ValueError("processing_mode must be one of: raw, demean, trace_rms, agc")

    arr = _as_float32_2d(data)

    dt = float(sample_interval_sec)
    if dt <= 0 or not np.isfinite(dt):
        dt = 0.004

    ft = (filter_type or "none").lower().strip()
    if ft not in ("none", "bandpass", "lowpass", "highpass"):
        raise ValueError("filter_type must be one of: none, bandpass, lowpass, highpass")

    # First apply frequency filtering to the preview traces.
    arr, nyquist_hz = frequency_filter_traces(
        arr,
        sample_interval_sec=dt,
        filter_type=ft,  # type: ignore[arg-type]
        f1=f1,
        f2=f2,
        f3=f3,
        f4=f4,
    )

    did_demean = False
    did_rms = False
    did_agc = False
    agc_samples = 0

    if mode in ("demean", "trace_rms", "agc"):
        arr = demean_traces(arr)
        did_demean = True

    if mode == "trace_rms":
        arr = rms_balance_traces(arr)
        did_rms = True

    if mode == "agc":
        arr, agc_samples = agc_traces(arr, sample_interval_sec=dt, agc_window_sec=agc_window_sec)
        did_agc = True

    clip_abs = percentile_clip_value(arr, clip_percentile=clip_percentile)

    info = Processing2DInfo(
        processing_mode=mode,
        demean=did_demean,
        rms_balance=did_rms,
        agc=did_agc,
        agc_window_sec=float(agc_window_sec),
        agc_window_samples=int(agc_samples),
        filter_type=ft,
        f1=f1,
        f2=f2,
        f3=f3,
        f4=f4,
        sample_interval_sec=dt,
        nyquist_hz=float(nyquist_hz),
        clip_percentile=float(clip_percentile),
        clip_abs=float(clip_abs),
    )

    return arr.astype(np.float32), info
