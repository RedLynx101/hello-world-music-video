"""Merge transcription + forced alignment into per-line word timings; derive bar grid and drum hits."""
import json, os, re, sys
import numpy as np

# Project root: HELLO_WORLD_ROOT if set, otherwise the folder above scripts/.
ROOT = os.environ.get('HELLO_WORLD_ROOT') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AN = os.path.join(ROOT, 'analysis')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import LYRICS


def norm(w):
    return re.sub(r"[^a-z0-9']", '', w.lower().replace('’', "'"))


al = json.load(open(os.path.join(AN, 'align_words.json'), encoding='utf-8'))
tr = json.load(open(os.path.join(AN, 'transcribe_words.json'), encoding='utf-8'))
music = json.load(open(os.path.join(AN, 'music.json')))

# 1) aligned words follow the lyric text in order; snap to transcript words when they agree
tr_n = [(s, e, norm(w)) for s, e, w, p in tr]
used = set()
merged = []
for s, e, w, p in al:
    n = norm(w)
    best = None
    for j, (ts, te, tn) in enumerate(tr_n):
        if j in used or tn != n:
            continue
        if abs(ts - s) < 1.6 and (best is None or abs(ts - s) < abs(tr_n[best][0] - s)):
            best = j
    if best is not None:
        used.add(best)
        merged.append([tr_n[best][0], tr_n[best][1], w, 'tr'])
    else:
        merged.append([s, e, w, 'al'])

# 2) split into lyric lines
lines = [l for l in LYRICS.split('\n') if l.strip()]
out_lines = []
k = 0
for i, line in enumerate(lines):
    toks = [t for t in line.split() if norm(t)]
    ws = merged[k:k + len(toks)]
    k += len(toks)
    out_lines.append(dict(i=i, text=line, start=round(ws[0][0], 3), end=round(ws[-1][1], 3),
                          words=[[x[2], round(x[0], 3), round(x[1], 3), x[3]] for x in ws]))
assert k == len(merged), (k, len(merged))

# 3) beat grid: librosa eighths -> quarter beats; choose downbeat phase by percussive energy
beats = np.array(music['beats'])
fr = music['frames']
onset = np.array(fr['onset'])
low = np.array(fr['low'])
fps = music['fps']


def val(arr, t):
    i = int(round(t * fps))
    lo, hi = max(0, i - 1), min(len(arr), i + 2)
    return float(arr[lo:hi].max()) if hi > lo else 0.0


best = None
for qp in (0, 1):
    q = beats[qp::2]
    for bp in range(4):
        d = q[bp::4]
        score = np.mean([val(low, t) + val(onset, t) for t in d])
        if best is None or score > best[0]:
            best = (score, qp, bp)
_, qp, bp = best
quarters = beats[qp::2]
downbeats = quarters[bp::4]
# strong drum hits for glitch triggers
hits = [h for h in music['hits'] if h[1] > np.percentile([x[1] for x in music['hits']], 70)]

json.dump(dict(lines=out_lines, quarters=[round(float(x), 3) for x in quarters],
               downbeats=[round(float(x), 3) for x in downbeats], hits=hits, duration=music['duration']),
          open(os.path.join(AN, 'timing.json'), 'w'), indent=0)
for l in out_lines:
    print(f"{l['i']:2d} {l['start']:7.2f} {l['end']:7.2f}  {l['text']}")
print('quarter ibi', np.median(np.diff(quarters)), 'first downbeats', [round(float(x), 2) for x in downbeats[:8]])
print('downbeats near sections', [round(float(x), 2) for x in downbeats if 50 < x < 60 or 120 < x < 130 or 190 < x < 200])
print('hits', len(hits))
