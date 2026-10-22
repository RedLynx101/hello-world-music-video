"""Render every shot's first/last frames plus every 24th frame (both formats where plates exist) to catch crashes."""
import os, sys, traceback
sys.path.insert(0, os.path.dirname(__file__))
from multiprocessing import Pool


def job(args):
    f, fmt = args
    import comp
    try:
        comp.render_seq([f], fmt)
        return None
    except Exception:
        return (f, fmt, traceback.format_exc().splitlines()[-3:])


if __name__ == '__main__':
    import comp, shots
    n = int(shots.DURATION * comp.FPS) + 1
    frames = set(range(1, n + 1, 24))
    for s in shots.SHOTS:
        a, b = int(round(s['t0'] * comp.FPS)) + 1, int(round(s['t1'] * comp.FPS))
        for f in (a - 1, a, a + 1, a + 2, b - 1, b, b + 1):
            if 1 <= f <= n:
                frames.add(f)
    jobs = [(f, '169') for f in sorted(frames)]
    short_frames = set()
    for segs in shots.SHORTS.values():
        for a, b in segs:
            fa, fb = int(round(a * comp.FPS)) + 1, int(round(b * comp.FPS))
            short_frames |= {f for f in frames if fa <= f <= fb} | {fa, fa + 1, fb}
    jobs += [(f, '916') for f in sorted(short_frames)]
    print('SMOKE', len(jobs), 'frames', flush=True)
    with Pool(int(os.environ.get('COMP_WORKERS', '12'))) as pool:
        bad = [r for r in pool.imap_unordered(job, jobs, chunksize=4) if r]
    for r in bad:
        print('FAIL', r)
    print('SMOKE_DONE failures:', len(bad))
