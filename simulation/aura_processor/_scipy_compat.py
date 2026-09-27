"""Minimal numpy-only fallbacks when scipy is unavailable (CI / lightweight sim)."""

from __future__ import annotations

import numpy as np


def _lfilter(b: np.ndarray, a: np.ndarray, x: np.ndarray) -> np.ndarray:
    y = np.zeros_like(x, dtype=float)
    b = np.asarray(b, dtype=float)
    a = np.asarray(a, dtype=float)
    if len(a) == 0 or abs(a[0]) < 1e-12:
        return x.astype(float)
    a = a / a[0]
    b = b / a[0]
    na = len(a)
    nb = len(b)
    z = np.zeros(max(na, nb) - 1, dtype=float)
    for i, xi in enumerate(x.astype(float)):
        y[i] = b[0] * xi + z[0] if len(z) else b[0] * xi
        for j in range(1, nb):
            if j < len(z):
                y[i] += b[j] * (x[i - j] if i - j >= 0 else 0.0)
        for j in range(1, na):
            if j < len(z):
                y[i] -= a[j] * z[j - 1]
        if len(z):
            z = np.roll(z, 1)
            z[0] = xi
    return y


def butter(order: int, Wn, btype: str = "low", analog: bool = False, output: str = "ba", fs=None):
    """Simplified Butterworth — sufficient for vitals bandpass in sim."""
    if fs is not None:
        Wn = np.asarray(Wn, dtype=float) / (fs / 2.0)
    Wn = np.atleast_1d(Wn).astype(float)
    if btype == "band" and len(Wn) == 2:
        low, high = float(Wn[0]), float(Wn[1])
        mid = np.sqrt(low * high)
        bw = max(high - low, 1e-3)
        q = mid / bw
        w0 = 2 * np.pi * mid
        alpha = np.sin(w0) / (2 * q)
        b0 = alpha
        b1 = 0.0
        b2 = -alpha
        a0 = 1 + alpha
        a1 = -2 * np.cos(w0)
        a2 = 1 - alpha
        b = np.array([b0, b1, b2]) / a0
        a = np.array([1.0, a1 / a0, a2 / a0])
        return b, a
    wc = float(Wn[0]) if len(Wn) else 0.1
    c = 1.0 / np.tan(np.pi * wc / 2.0)
    b = np.array([1.0, 2.0, 1.0]) / (1 + c)
    a = np.array([1.0, 2 * (1 - c) / (1 + c), (1 - c) / (1 + c)])
    return b, a


def filtfilt(b: np.ndarray, a: np.ndarray, x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    if len(x) < 8:
        return x - np.mean(x)
    padlen = min(3 * (max(len(a), len(b)) - 1), len(x) - 1)
    if padlen < 1:
        return _lfilter(b, a, x)
    edge = x[0]
    ext = np.concatenate([2 * edge - x[padlen:0:-1], x, 2 * x[-1] - x[-2 : -padlen - 2 : -1]])
    y = _lfilter(b, a, ext)
    y = _lfilter(b, a, y[::-1])[::-1]
    return y[padlen : padlen + len(x)]


def welch(
    x,
    fs: float = 1.0,
    nperseg: int | None = None,
    noverlap: int | None = None,
    nfft: int | None = None,
    **_,
):
    x = np.asarray(x, dtype=float).ravel()
    nperseg = int(nperseg or min(256, len(x)))
    nperseg = max(8, min(nperseg, len(x)))
    noverlap = int(noverlap if noverlap is not None else nperseg // 2)
    hop = max(1, nperseg - noverlap)
    win = np.hanning(nperseg)
    psd_acc = None
    count = 0
    for start in range(0, len(x) - nperseg + 1, hop):
        seg = x[start : start + nperseg] * win
        fft = np.fft.rfft(seg, n=nfft)
        p = np.abs(fft) ** 2
        psd_acc = p if psd_acc is None else psd_acc + p
        count += 1
    if count == 0:
        fft = np.fft.rfft(x * np.hanning(len(x)))
        psd_acc = np.abs(fft) ** 2
        count = 1
    f = np.fft.rfftfreq(nperseg if nfft is None else nfft, d=1.0 / fs)
    return f, psd_acc / count


def detrend(x, type: str = "linear", axis: int = 0, bp: int = 0):
    x = np.asarray(x, dtype=float)
    if type == "constant":
        return x - np.mean(x, axis=axis, keepdims=True)
    if x.ndim == 1:
        t = np.arange(len(x), dtype=float)
        p = np.polyfit(t, x, 1)
        return x - np.polyval(p, t)
    out = np.empty_like(x)
    if axis == 0:
        for i in range(x.shape[1]):
            slc = x[:, i]
            t = np.arange(len(slc), dtype=float)
            p = np.polyfit(t, slc, 1)
            out[:, i] = slc - np.polyval(p, t)
    else:
        for i in range(x.shape[0]):
            slc = x[i, :]
            t = np.arange(len(slc), dtype=float)
            p = np.polyfit(t, slc, 1)
            out[i, :] = slc - np.polyval(p, t)
    return out


def find_peaks(x, height=None, distance=None, prominence=None, **kwargs):
    x = np.asarray(x, dtype=float)
    peaks = []
    for i in range(1, len(x) - 1):
        if x[i] >= x[i - 1] and x[i] > x[i + 1]:
            if height is not None and x[i] < height:
                continue
            peaks.append(i)
    if distance is not None and distance > 1 and peaks:
        filtered = [peaks[0]]
        for p in peaks[1:]:
            if p - filtered[-1] >= distance:
                filtered.append(p)
        peaks = filtered
    props = {"peak_heights": np.array([x[p] for p in peaks]) if peaks else np.array([])}
    return np.array(peaks, dtype=int), props


def stft(x, fs: float = 1.0, nperseg: int = 256, noverlap: int | None = None, **kwargs):
    x = np.asarray(x, dtype=float).ravel()
    nperseg = min(nperseg, len(x)) if len(x) else nperseg
    noverlap = noverlap if noverlap is not None else nperseg // 2
    hop = max(1, nperseg - noverlap)
    win = np.hanning(nperseg)
    cols = []
    for start in range(0, max(len(x) - nperseg + 1, 1), hop):
        seg = x[start : start + nperseg]
        if len(seg) < nperseg:
            seg = np.pad(seg, (0, nperseg - len(seg)))
        cols.append(np.fft.fft(seg * win))
    zxx = np.array(cols).T if cols else np.zeros((nperseg, 0), dtype=complex)
    f = np.fft.fftfreq(nperseg, d=1.0 / fs)
    t = np.arange(zxx.shape[1]) * hop / fs
    return f, t, zxx


def hilbert(x, N: int | None = None, axis: int = -1):
    x = np.asarray(x, dtype=float)
    n = N or x.shape[axis]
    Xf = np.fft.fft(x, n=n, axis=axis)
    h = np.zeros(n)
    if n % 2 == 0:
        h[0] = h[n // 2] = 1
        h[1 : n // 2] = 2
    else:
        h[0] = 1
        h[1 : (n + 1) // 2] = 2
    return np.fft.ifft(Xf * h, axis=axis)


def resample(x, num: int, t=None, axis: int = 0, window=None, domain: str = "time"):
    x = np.asarray(x, dtype=float)
    old_len = x.shape[axis]
    if old_len == num:
        return x
    old_idx = np.linspace(0, 1, old_len)
    new_idx = np.linspace(0, 1, num)
    if x.ndim == 1:
        return np.interp(new_idx, old_idx, x)
    out = np.zeros((num,) + x.shape[1:], dtype=float)
    for i in range(x.shape[1] if axis == 0 else x.shape[0]):
        slc = x[:, i] if axis == 0 else x[i]
        out[:, i] if axis == 0 else out[i]
        if axis == 0:
            out[:, i] = np.interp(new_idx, old_idx, slc)
        else:
            out[i] = np.interp(new_idx, old_idx, slc)
    return out


def uniform_filter1d(x, size: int, axis: int = -1, mode: str = "reflect", origin: int = 0):
    x = np.asarray(x, dtype=float)
    k = np.ones(max(int(size), 1)) / max(int(size), 1)
    if x.ndim == 1:
        return np.convolve(x, k, mode="same")
    out = np.empty_like(x)
    for i in range(x.shape[0]):
        out[i] = np.convolve(x[i], k, mode="same")
    return out


def gaussian_filter1d(x, sigma, axis: int = -1, mode: str = "reflect", order: int = 0, truncate: float = 4.0):
    x = np.asarray(x, dtype=float)
    radius = int(truncate * float(sigma) + 0.5)
    t = np.arange(-radius, radius + 1, dtype=float)
    k = np.exp(-0.5 * (t / max(float(sigma), 1e-6)) ** 2)
    k /= k.sum()
    if x.ndim == 1:
        return np.convolve(x, k, mode="same")
    out = np.empty_like(x)
    for i in range(x.shape[0]):
        out[i] = np.convolve(x[i], k, mode="same")
    return out


def install_scipy_shim() -> None:
    """Register minimal scipy modules in sys.modules if scipy is missing."""
    import sys
    import types

    if "scipy" in sys.modules:
        try:
            import scipy  # noqa: F401
            return
        except ImportError:
            pass

    try:
        import scipy  # noqa: F401
        return
    except ImportError:
        pass

    sig = types.ModuleType("scipy.signal")
    sig.butter = butter
    sig.filtfilt = filtfilt
    sig.welch = welch
    sig.detrend = detrend
    sig.find_peaks = find_peaks
    sig.stft = stft
    sig.hilbert = hilbert
    sig.resample = resample

    ndi = types.ModuleType("scipy.ndimage")
    ndi.uniform_filter1d = uniform_filter1d
    ndi.gaussian_filter1d = gaussian_filter1d

    scipy_mod = types.ModuleType("scipy")
    scipy_mod.signal = sig
    scipy_mod.ndimage = ndi

    sys.modules["scipy"] = scipy_mod
    sys.modules["scipy.signal"] = sig
    sys.modules["scipy.ndimage"] = ndi
