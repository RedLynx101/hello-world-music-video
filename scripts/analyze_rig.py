"""Audio features for the orb's sound rig, one value per video frame (24 fps).

Writes analysis/rig.json (vocal envelope, kick envelope + onsets, energy, bass) and
analysis/rig_spec.png (vocal spectrum: width = bins, height = frames, row f = frame f+1).
"""
import os, json
import numpy as np
import soundfile as sf
import librosa
import cv2

# Project root: HELLO_WORLD_ROOT if set, otherwise the folder above scripts/.
ROOT = os.environ.get('HELLO_WORLD_ROOT') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AN = os.path.join(ROOT, 'analysis')
SEP = os.path.join(AN, 'sep', 'htdemucs', 'hello_world')
FPS = 24
BINS = 40


def load(path):
    y, sr = sf.read(path, dtype='float32')
    if y.ndim > 1:
        y = y.mean(axis=1)
    return y, sr


def frame_rms(y, sr, n):
    out = np.zeros(n, np.float32)
    for f in range(n):
        a, b = int(round(f * sr / FPS)), int(round((f + 1) * sr / FPS))
        seg = y[a:b]
        out[f] = np.sqrt(np.mean(seg ** 2)) if len(seg) else 0.0
    return out


def resample_frames(M, sr, hop, n):
    """Columns of an STFT (hop samples apart) -> one column per video frame (nearest, centered)."""
    idx = np.clip(np.round((np.arange(n) + 0.5) * sr / FPS / hop).astype(int), 0, M.shape[-1] - 1)
    return M[..., idx]


def follow(x, att, rel):
    """Envelope follower: per-frame attack/release coefficients (0..1, higher = faster)."""
    out = np.zeros_like(x)
    v = 0.0
    for i, s in enumerate(x):
        v += (s - v) * (att if s > v else rel)
        out[i] = v
    return out


def norm(x, lo_pct=5, hi_pct=97):
    lo, hi = np.percentile(x, lo_pct), np.percentile(x, hi_pct)
    return np.clip((x - lo) / max(1e-9, hi - lo), 0, 1)


def main():
    voc, sr = load(os.path.join(SEP, 'vocals.wav'))
    acc, sra = load(os.path.join(SEP, 'no_vocals.wav'))
    mix, srm = load(os.path.join(ROOT, 'audio', 'hello_world.wav'))
    n = int(np.ceil(len(mix) / srm * FPS))
    hop = 512

    # vocal envelope (dB-ish, gated so breaths and bleed stay quiet)
    vr = frame_rms(voc, sr, n)
    vdb = 20 * np.log10(vr + 1e-6)
    venv = np.clip((vdb - (-42.0)) / 26.0, 0, 1)
    venv = follow(venv, 0.65, 0.18)

    # vocal spectrum: log-spaced bands 120 Hz - 7 kHz
    S = np.abs(librosa.stft(voc, n_fft=4096, hop_length=hop, center=True)) ** 2
    freqs = librosa.fft_frequencies(sr=sr, n_fft=4096)
    edges = np.geomspace(120, 7000, BINS + 1)
    bands = np.zeros((BINS, S.shape[1]), np.float32)
    for b in range(BINS):
        sel = (freqs >= edges[b]) & (freqs < edges[b + 1])
        bands[b] = S[sel].mean(axis=0) if sel.any() else 0
    bands = 10 * np.log10(bands + 1e-10)
    bands = resample_frames(bands, sr, hop, n)
    spec = np.zeros_like(bands)
    for b in range(BINS):
        spec[b] = norm(bands[b], 20, 99)
    spec = spec * venv[None, :] ** 0.5          # silence the ring between phrases
    for b in range(BINS):
        spec[b] = follow(spec[b], 0.8, 0.30)
    spec_img = (np.clip(spec.T, 0, 1) * 255 + 0.5).astype(np.uint8)   # (n, BINS)
    cv2.imwrite(os.path.join(AN, 'rig_spec.png'), spec_img)

    # pulses: the beat grid (quarters), weighted by how much low end the accompaniment has on each beat
    Sa = np.abs(librosa.stft(acc, n_fft=2048, hop_length=hop)) ** 2
    fa = librosa.fft_frequencies(sr=sra, n_fft=2048)
    low = resample_frames(Sa[(fa >= 35) & (fa <= 160)].sum(axis=0), sra, hop, n)
    ldb = 10 * np.log10(low + 1e-10)
    lnorm = norm(ldb, 10, 99)
    timing = json.load(open(os.path.join(AN, 'timing.json')))
    downs = set(round(d, 2) for d in timing['downbeats'])
    kicks = []
    for q in timing['quarters']:
        f0 = int(round(q * FPS))
        if f0 >= n:
            continue
        lv = float(lnorm[max(0, f0 - 1):f0 + 3].max())
        if lv < 0.35:
            continue
        down = any(abs(q - d) < 0.06 for d in downs)
        kicks.append([round(q, 4), round(min(1.0, lv * (1.0 if down else 0.75)), 3), 1 if down else 0])
    kenv = np.zeros(n, np.float32)
    for t, s, _d in kicks:
        f0 = int(round(t * FPS))
        for k in range(0, 18):
            if f0 + k < n:
                kenv[f0 + k] = max(kenv[f0 + k], s * np.exp(-k / 4.0))

    # overall energy and bass of the full mix
    mr = frame_rms(mix, sr, n)
    energy = follow(norm(20 * np.log10(mr + 1e-6), 10, 99), 0.3, 0.05)
    bass = follow(norm(ldb, 10, 99), 0.5, 0.15)

    out = dict(fps=FPS, n=n, bins=BINS, vocal=np.round(venv, 4).tolist(), kick=np.round(kenv, 4).tolist(),
               energy=np.round(energy, 4).tolist(), bass=np.round(bass, 4).tolist(), kicks=kicks,
               spec_png='analysis/rig_spec.png')
    json.dump(out, open(os.path.join(AN, 'rig.json'), 'w'))
    print('RIG frames', n, 'kicks', len(kicks), 'vocal mean', round(float(venv.mean()), 3),
          'spec', spec_img.shape, 'energy mean', round(float(energy.mean()), 3))
    # coarse report per 10 s
    for s in range(0, int(n / FPS), 10):
        a, b = s * FPS, min(n, (s + 10) * FPS)
        kc = sum(1 for t, _, _d in kicks if s <= t < s + 10)
        print(f'{s:4d}s voc {venv[a:b].mean():.2f} energy {energy[a:b].mean():.2f} kicks {kc}')


if __name__ == '__main__':
    main()
