"""Lyric caption files (SRT) for the music video and the three Shorts, from the same lyric timing the video uses."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
import shots

FPS = 24
OUT = os.path.join(shots.ROOT, 'out', 'captions')
os.makedirs(OUT, exist_ok=True)
L = shots.LINES


def cues():
    """(start, end, text) per sung line; each ends a beat after the singing, never past the next line."""
    out = []
    for i, ln in enumerate(L):
        s, e = ln['start'], ln['end'] + 0.6
        if i + 1 < len(L):
            e = min(e, L[i + 1]['start'] - 0.05)
        e = max(e, s + 1.0)
        out.append((s, e, ln['text'].strip()))
    return out


def ts(x):
    ms = int(round(max(0.0, x) * 1000))
    return '%02d:%02d:%02d,%03d' % (ms // 3600000, ms // 60000 % 60, ms // 1000 % 60, ms % 1000)


def write(name, items):
    p = os.path.join(OUT, name)
    with open(p, 'w', encoding='utf-8', newline='\r\n') as f:
        for k, (s, e, t) in enumerate(items, 1):
            f.write('%d\n%s --> %s\n%s\n\n' % (k, ts(s), ts(e), t))
    print('SRT', name, len(items), 'cues')


C = cues()
write('Hello World - Music Video - lyrics (EN).srt', C)

titles = {'SH1': 'Short 1', 'SH2': 'Short 2', 'SH3': 'Short 3'}
for key, segs in shots.SHORTS.items():
    items, base = [], 0.0
    for a, b in segs:
        fa, fb = int(round(a * FPS)) / FPS, int(round(b * FPS)) / FPS   # the exact cut points the encoder used
        for s, e, t in C:
            if e <= fa + 0.25 or s >= fb - 0.25:
                continue
            items.append((base + max(s, fa) - fa, base + min(e, fb) - fa, t))
        base += fb - fa
    write('Hello World - %s - lyrics (EN).srt' % titles[key], items)
