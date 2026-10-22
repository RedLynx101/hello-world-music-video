"""Shared image ops: EXR read, bloom, tonemap, grain. Float32 RGB arrays (H, W, 3)."""
import os
os.environ.setdefault('OPENCV_IO_ENABLE_OPENEXR', '1')
import cv2
import numpy as np


def read_exr(path):
    im = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if im is None:
        raise FileNotFoundError(path)
    im = im[..., :3][..., ::-1].astype(np.float32)
    return np.nan_to_num(im, nan=0.0, posinf=50.0, neginf=0.0)


def gblur(a, sigma):
    """Gaussian blur that downsamples for big radii."""
    if sigma <= 6:
        return cv2.GaussianBlur(a, (0, 0), sigma)
    k = int(max(2, sigma // 4))
    h, w = a.shape[:2]
    small = cv2.resize(a, (max(1, w // k), max(1, h // k)), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), sigma / k)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)


def bloom(img, thr=1.2, levels=((3, 0.25), (10, 0.20), (28, 0.14), (70, 0.09), (170, 0.05)), gain=1.0, scale=1.0):
    lum = img.max(axis=2, keepdims=True)
    b = img * np.clip((lum - thr) / np.maximum(lum, 1e-4), 0, 1)
    out = np.zeros_like(img)
    for s, w in levels:
        out += gblur(b, s * scale) * w
    return img + out * gain


def aces(x):
    a, b, c, d, e = 2.51, 0.03, 2.43, 0.59, 0.14
    return np.clip((x * (a * x + b)) / (x * (c * x + d) + e), 0, 1)


_LUT_N = 16384
_l = np.linspace(0, 1, _LUT_N, dtype=np.float64)
_SRGB_LUT = np.where(_l <= 0.0031308, _l * 12.92, 1.055 * np.power(_l, 1 / 2.4) - 0.055).astype(np.float32)


def to_srgb(x):
    """Linear -> sRGB via a 16k-entry table (error far below one 8-bit step)."""
    idx = (np.clip(x, 0, 1) * (_LUT_N - 1) + 0.5).astype(np.int32)
    return _SRGB_LUT[idx]


def finish(img, exposure=1.0, bloom_gain=1.0, thr=1.2, scale=1.0):
    img = img * exposure
    img = bloom(img, thr=thr, gain=bloom_gain, scale=scale)
    return to_srgb(aces(img))


_VIG = {}


def grain_vignette(img, rng, grain=0.018, vignette=0.32):
    h, w = img.shape[:2]
    key = (h, w, vignette)
    if key not in _VIG:
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        x = (xx / w - 0.5) * 2
        y = (yy / h - 0.5) * 2
        v = 1 - vignette * np.clip((x * x * 0.6 + y * y * 0.9) - 0.15, 0, None)
        _VIG[key] = np.clip(v, 0, 1)[..., None].astype(np.float32)
    img = img * _VIG[key]
    if grain > 0:
        img += rng.standard_normal((h, w, 1), dtype=np.float32) * np.float32(grain)
    return np.clip(img, 0, 1, out=img)
