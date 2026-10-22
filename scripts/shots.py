"""Shot timeline for Hello, World. Pure Python: imported by Blender (3D state) and by the compositor (overlays).

Times are seconds into the song. Compositions are fractions of the frame (x from left, y from top, r = eye
radius / frame height). The eye is a physical object of radius R metres placed from a composition.
"""
import json, math, os

# Project root: HELLO_WORLD_ROOT if set, otherwise the folder above scripts/.
ROOT = os.environ.get('HELLO_WORLD_ROOT') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TIMING = json.load(open(os.path.join(ROOT, 'analysis', 'timing.json')))
DURATION = TIMING['duration']
LINES = TIMING['lines']
FPS = 24
LONE_AZ = 4.85  # degrees right of +Y; sits at x~0.70 in S14

# small manual fixes to the merged lyric timings
def _even(i, t0, t1):
    ws = LINES[i]['words']
    n = len(ws)
    for k, w in enumerate(ws):
        w[1] = round(t0 + (t1 - t0) * k / n, 3)
        w[2] = round(t0 + (t1 - t0) * (k + 1) / n, 3)
    LINES[i]['start'], LINES[i]['end'] = t0, t1


LINES[12]['words'][-1][1:3] = [53.9, 54.3]
LINES[12]['end'] = 54.3
_even(21, 86.03, 89.30)
_even(55, 212.26, 214.04)
LINES[59]['words'][-1][1:3] = [230.40, 231.30]
LINES[59]['end'] = 231.3


def _span(i, k0, k1, t0, t1):
    """Spread words k0..k1 (inclusive) of line i evenly over t0..t1."""
    ws = LINES[i]['words']
    n = k1 - k0 + 1
    for j, k in enumerate(range(k0, k1 + 1)):
        ws[k][1] = round(t0 + (t1 - t0) * j / n, 3)
        ws[k][2] = round(t0 + (t1 - t0) * (j + 1) / n, 3)
    LINES[i]['start'] = ws[0][1]


# verse 2 opening: "But" pickup, breath, then the line; "I found" sits just before "the strangest thing"
LINES[21]['words'][0][1:3] = [86.03, 86.40]
_span(21, 1, 6, 86.95, 89.45)
LINES[21]['start'], LINES[21]['end'] = 86.03, 89.45
_span(22, 0, 1, 89.60, 90.70)
_span(38, 1, 2, 141.90, 142.62)
# the aligner glues the gap before a line onto its first word; pull those onsets in
for _i in (17, 19, 37, 39, 54):
    _w = LINES[_i]['words'][0]
    if _w[2] - _w[1] > 1.2:
        _w[1] = round(_w[2] - 0.5, 3)
        LINES[_i]['start'] = _w[1]


def W(line, word=0, which=1):
    """Time of a word in a lyric line (which=1 start, 2 end). Negative word index counts from the end."""
    return LINES[line]['words'][word][which]


# ------------------------------------------------------------------ easing / interpolation
def smooth(u):
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


def lerp(a, b, u):
    return a + (b - a) * u


def keyed(keys, t):
    """keys: [(time, value), ...] absolute seconds, smoothstep between keys."""
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t <= t1:
            return lerp(v0, v1, smooth((t - t0) / max(1e-6, t1 - t0)))
    return keys[-1][1]


def val(spec, t, u):
    if isinstance(spec, tuple):
        return lerp(spec[0], spec[1], u)
    if isinstance(spec, list):
        return keyed(spec, t)
    return spec


# ------------------------------------------------------------------ shots
D16 = dict(h=4.0, yh=0.72, lens=50.0, yaw=0.0, roll=0.0, x=0.0, y=0.0)
PROPS = dict(eye_gold=0.0, eye_ember=0.0, eye_int=1.0, eye_core=1.0, eye_rings=1.0, sky_pre=0.0, sky_dawn=0.0,
             sky_glow=0.18, sky_bright=1.0, lights=1.0, fire=0.0, lone=0.0, sea_chop=1.4, sea_rough=0.09, sea_lines=1.0,
             ap=1.0, bezel_rot=0.0, iris_rot=0.0)
COVER = dict(x=0.5, y=0.40, r=0.21)
VDEF = dict(y=0.30, rw=0.36, hz=0.56)

SHOTS = [
    dict(id='S01', t0=0.0, t1=9.10, plate=False, cam={}, eye=COVER),
    dict(id='S02', t0=9.10, t1=15.65, cam=dict(h=4, aim=8.0, lens=(300, 330), roll=(2.5, 0.0)),
         eye=dict(x=0.5, y=0.5, r=0.95), props=dict(bezel_rot=[(9.1, -40.0), (15.4, 0.0)], iris_rot=[(9.1, 12.0), (15.4, 0.0)],
                                                     ap=[(9.1, 0.84), (15.3, 0.9), (15.65, 0.93)], sky_glow=0.0),
         v=dict(aim=True, rw=0.95)),
    dict(id='S03', t0=15.65, t1=22.90, cam=dict(h=4, yh=0.72, lens=(80, 50)), eye=COVER, anchor='end'),
    dict(id='S04', t0=22.90, t1=29.50, cam=dict(h=(1.4, 1.0), yh=0.44, lens=28, y=(0.0, 28.0)),
         eye=dict(x=0.5, y=0.25, r=0.075), props=dict(sea_chop=1.2)),
    dict(id='S05', t0=29.50, t1=35.60, cam=dict(h=6, yh=0.62, lens=135, yaw=(-0.8, 0.8)),
         eye=dict(x=0.82, y=-0.03, r=0.32), props=dict(lights=1.35)),
    dict(id='S06', t0=35.60, t1=41.80, cam=dict(h=5, yh=0.64, lens=(40, 43)), eye=dict(x=0.5, y=0.30, r=0.14),
         props=dict(lights=0.12)),
    dict(id='S07', t0=41.80, t1=48.30, cam=dict(h=(3, 18), yh=(0.70, 0.74), lens=45), eye=dict(x=0.5, y=0.36, r=0.24),
         props=dict(fire=[(41.8, 0.0), (W(10, 0), 0.0), (W(10, 3) + 0.6, 1.0)], ap=[(41.8, 1.0), (W(10, 3), 1.0), (W(10, 3) + 0.25, 1.15)],
                    eye_int=[(41.8, 1.0), (W(10, 3), 1.0), (W(10, 3) + 0.4, 1.3)], sky_glow=0.4)),
    dict(id='S08', t0=48.30, t1=55.98, cam=dict(h=4, yh=0.72, lens=(50, 62)), eye=COVER,
         props=dict(fire=(0.9, 0.3), ap=(1.15, 1.0), eye_int=(1.25, 1.1))),
    dict(id='S09a', t0=55.98, t1=62.70, cam=dict(h=1.2, yh=0.70, lens=(24, 26)), eye=dict(x=0.5, y=0.30, r=0.42),
         props=dict(eye_int=1.25, sky_glow=0.5, sea_chop=1.25)),
    dict(id='S09b', t0=62.70, t1=66.10, cam=dict(h=4, aim=9.0, lens=(140, 160)), eye=dict(x=0.5, y=0.5, r=0.62),
         props=dict(bezel_rot=(0, 30), iris_rot=(0, -12), eye_int=1.25), v=dict(aim=True, rw=0.62)),
    dict(id='S09c', t0=66.10, t1=69.40, cam=dict(h=26, yh=0.58, lens=35, x=(12, -12)), eye=dict(x=0.5, y=0.30, r=0.20),
         props=dict(eye_int=1.2, sky_glow=0.45)),
    dict(id='S10', t0=69.40, t1=73.60, cam=dict(h=4, yh=0.70, lens=(50, 54)), eye=dict(x=0.5, y=0.38, r=0.22),
         props=dict(ap=1.08, eye_int=0.85, sky_glow=0.15), v=dict(rw=(0.36, 0.39))),
    dict(id='S11', t0=73.60, t1=79.50, cam=dict(h=(15, 10), yh=(0.29, 0.22), lens=30), eye=dict(x=0.5, y=0.155, r=0.06, R=25.0),
         props=dict(sea_chop=1.6, eye_int=0.9), v=dict(y=0.12, rw=0.10, hz=0.20)),
    dict(id='S12', t0=79.50, t1=86.00, cam=dict(h=2.5, yh=0.50, lens=(50, 54)), eye=dict(x=0.5, y=0.27, r=0.16),
         props=dict(sea_chop=0.22, sea_rough=0.015, sky_glow=0.2), v=dict(y=0.32, rw=(0.26, 0.28), hz=0.50)),
    dict(id='S13', t0=86.00, t1=92.90, cam=dict(h=6, yh=0.62, lens=55, x=(0, 30)), eye=dict(x=0.66, y=0.44, r=0.12),
         props=dict(eye_int=0.75, sky_glow=0.15, lights=0.8)),
    dict(id='S14', t0=92.90, t1=99.50, cam=dict(h=5, yh=0.66, lens=(85, 92)), eye=dict(x=0.30, y=0.34, r=0.10, R=18.0),
         props=dict(eye_int=0.8, lights=0.22, lone=1.0)),
    dict(id='S15', t0=99.50, t1=105.50, cam=dict(h=5, yh=0.68, lens=(85, 92), yaw=1.95), eye=dict(x=0.16, y=0.30, r=0.09, R=18.0),
         props=dict(eye_int=0.8, lights=0.3, lone=0.8)),
    dict(id='S16', t0=105.50, t1=112.40, cam=dict(h=(4, 30), yh=(0.74, 0.70), lens=(40, 32)), eye=dict(x=0.5, y=0.34, r=0.13),
         props=dict(eye_int=0.95, lights=1.15, sky_glow=0.22)),
    dict(id='S17', t0=112.40, t1=125.24, cam=dict(h=(5, 10), yh=0.70, lens=45), eye=dict(x=0.5, y=0.36, r=0.20),
         props=dict(fire=[(112.4, 0.0), (W(30, 3), 0.0), (W(30, -1), 0.85), (W(31, 0), 0.85), (W(31, -1) + 0.4, 0.0)],
                    ap=[(112.4, 1.0), (W(30, 3), 1.12), (W(31, -1), 1.12), (W(32, -1), 0.98)],
                    eye_int=[(112.4, 1.0), (W(31, 0), 1.25), (W(32, -1), 1.05)])),
    dict(id='S18a', t0=125.24, t1=131.70, cam=dict(h=3, yh=0.64, lens=(30, 32)), eye=dict(x=0.5, y=0.28, r=0.30),
         props=dict(sky_pre=(0.55, 0.7), eye_gold=0.12, eye_int=1.2, sky_glow=0.5)),
    dict(id='S18b', t0=131.70, t1=137.20, cam=dict(h=9, yh=0.66, lens=60, x=(-45, 45), track=True), eye=dict(x=0.5, y=0.40, r=0.25),
         props=dict(sky_pre=0.72, eye_gold=0.12, eye_int=1.2, bezel_rot=(0, 25), sky_glow=0.5)),
    dict(id='S18c', t0=137.20, t1=141.26, cam=dict(h=4, yh=0.70, lens=(50, 54)), eye=dict(x=0.5, y=0.38, r=0.22),
         props=dict(sky_pre=0.75, eye_gold=0.14, ap=1.08, eye_int=0.9)),
    dict(id='S18d', t0=141.26, t1=146.20, cam=dict(h=(15, 10), yh=(0.29, 0.22), lens=30), eye=dict(x=0.5, y=0.155, r=0.06, R=25.0),
         props=dict(sky_pre=0.75, eye_gold=0.14, sea_chop=1.6), v=dict(y=0.12, rw=0.10, hz=0.20)),
    dict(id='S18e', t0=146.20, t1=151.00, cam=dict(h=2.5, yh=0.50, lens=(50, 54)), eye=dict(x=0.5, y=0.27, r=0.16),
         props=dict(sky_pre=0.8, eye_gold=0.15, sea_chop=0.22, sea_rough=0.015), v=dict(y=0.32, rw=0.26, hz=0.50)),
    dict(id='S19', t0=151.00, t1=167.60, cam=dict(h=4, yh=0.70, lens=(50, 75)), eye=dict(x=0.5, y=0.38, r=0.22),
         props=dict(eye_int=[(151, 1.3), (164.4, 1.6), (166.6, 0.4)], fire=[(151, 0.3), (158, 0.6), (164, 0.8), (166.8, 0.0)],
                    sky_pre=[(151, 0.6), (154, 0.0)], ap=[(151, 1.1), (164, 1.22), (166.6, 0.9)], bezel_rot=(0, 90),
                    iris_rot=(0, -40), sky_glow=0.6), v=dict(y=0.40, rw=0.40, hz=0.62)),
    dict(id='S20', t0=167.60, t1=180.28, cam=dict(h=0.8, yh=0.58, lens=(50, 55)), eye=dict(x=0.5, y=0.43, r=0.085, R=20.0),
         props=dict(eye_ember=1.0, eye_int=0.75, ap=0.95, sea_chop=0.2, sea_rough=0.015, lights=0.55, sky_glow=0.1),
         v=dict(y=0.40, rw=(0.17, 0.19), hz=0.52)),
    dict(id='S21', t0=180.28, t1=194.61, cam=dict(h=3, yh=(0.86, 0.64), lens=40), eye_world=dict(D=520, az=0.0,
         H=[(180.28, 190.0), (194.4, 13.0)], R=[(180.28, 120.0), (194.4, 38.0)]),
         props=dict(eye_ember=[(180.28, 1.0), (194.4, 0.6)], eye_gold=[(180.28, 0.0), (194.4, 0.35)], eye_int=(0.85, 1.0),
                    sky_pre=[(180.28, 0.0), (194.4, 0.75)], lights=0.6, sea_chop=0.5, sky_glow=(0.1, 0.5)),
         v=dict(y=0.45, rw=0.30, hz=[(180.28, 0.85), (194.4, 0.56)])),
    dict(id='S22', t0=194.61, t1=208.20, cam=dict(h=(2.0, 1.2), yh=0.58, lens=(26, 24), y=(0, 140)), eye=dict(x=0.5, y=0.47, r=0.20),
         anchor='start', props=dict(eye_gold=[(194.61, 0.35), (196.2, 1.0)], eye_ember=[(194.61, 0.6), (196.2, 0.0)],
                                    sky_pre=[(194.61, 0.75), (196.6, 1.0)], sky_dawn=[(194.61, 0.0), (197.0, 1.0)],
                                    eye_int=1.25, sky_glow=1.0, sea_chop=1.5, lights=0.25, sea_rough=0.06),
         v=dict(y=0.44, rw=0.30, hz=0.50)),
    dict(id='S23a', t0=208.20, t1=213.90, cam=dict(h=2.5, yh=0.50, lens=(50, 54)), eye=dict(x=0.5, y=0.27, r=0.16),
         props=dict(eye_gold=1.0, sky_pre=1.0, sky_dawn=1.0, eye_int=1.1, sky_glow=0.45, sky_bright=0.78, sea_chop=0.3, sea_rough=0.02, lights=0.2),
         v=dict(y=0.30, rw=(0.25, 0.27), hz=0.50)),
    # the third "'cause I was made of you": the same overhead as S11, now at dawn, in gold
    dict(id='S23m', t0=213.90, t1=219.00, cam=dict(h=(15, 10), yh=(0.29, 0.22), lens=30), eye=dict(x=0.5, y=0.155, r=0.06, R=25.0),
         props=dict(eye_gold=1.0, sky_pre=1.0, sky_dawn=1.0, eye_int=1.1, sky_glow=0.6, sky_bright=0.85, sea_chop=1.5, lights=0.2,
                    sea_rough=0.05), v=dict(y=0.12, rw=0.10, hz=0.20)),
    dict(id='S23b', t0=219.00, t1=224.54, cam=dict(h=(30, 20), yh=0.60, lens=30), eye=dict(x=0.5, y=0.38, r=0.14),
         props=dict(eye_gold=1.0, sky_pre=1.0, sky_dawn=1.0, eye_int=1.1, sky_glow=0.6, sky_bright=0.85, sea_chop=1.3, lights=0.2)),
    dict(id='S23c', t0=224.54, t1=232.10, cam=dict(h=3, yh=0.62, lens=(40, 72)), eye=dict(x=0.5, y=0.45, r=0.18),
         props=dict(eye_gold=1.0, sky_pre=1.0, sky_dawn=1.0, eye_int=(1.1, 1.35), sky_glow=0.7, sky_bright=0.85, sea_chop=1.3, lights=0.2)),
    dict(id='S24', t0=232.10, t1=DURATION + 0.01, plate=False, cam={}, eye=COVER),
]
for s in SHOTS:
    s.setdefault('plate', True)


def shot_at(t):
    for s in SHOTS:
        if s['t0'] <= t < s['t1']:
            return s
    return SHOTS[-1]


# ------------------------------------------------------------------ geometry
def cam_params(spec, t, u):
    c = dict(D16)
    for k, v in spec['cam'].items():
        c[k] = v
    out = {}
    for k in ('h', 'yh', 'lens', 'yaw', 'roll', 'x', 'y'):
        out[k] = val(c.get(k, D16.get(k, 0.0)), t, u)
    out['aim'] = c.get('aim')
    out['track'] = c.get('track', False)
    return out


def dir_vec(pitch, yaw):
    p, y = math.radians(pitch), math.radians(yaw)
    return (math.cos(p) * math.sin(y), math.cos(p) * math.cos(y), math.sin(p))


def pitch_for(cp):
    tv = 10.125 / cp['lens']
    return math.degrees(math.atan((2 * cp['yh'] - 1) * tv))


def place_eye(cp, comp, R=40.0):
    tv, th = 10.125 / cp['lens'], 18.0 / cp['lens']
    pitch = cp['aim'] if cp['aim'] is not None else pitch_for(cp)
    e = pitch + math.degrees(math.atan((1 - 2 * comp['y']) * tv))
    az = cp['yaw'] + math.degrees(math.atan((2 * comp['x'] - 1) * th))
    a = math.atan(comp['r'] * 2 * tv)
    D = R / math.tan(a)
    d = dir_vec(e, az)
    loc = (cp['x'], cp['y'], cp['h'])
    return (loc[0] + D * d[0], loc[1] + D * d[1], loc[2] + D * d[2]), R


_eye_cache = {}


def eye_state(spec, t):
    if 'eye_world' in spec:
        ew = spec['eye_world']
        H = val(ew['H'], t, 0)
        R = val(ew['R'], t, 0)
        a = math.radians(ew['az'])
        return (ew['D'] * math.sin(a), ew['D'] * math.cos(a), H), R
    key = spec['id']
    if key not in _eye_cache:
        anchor = spec.get('anchor', 'start')
        ut = 1.0 if anchor == 'end' else 0.0
        tt = spec['t1'] if anchor == 'end' else spec['t0']
        cp = cam_params(spec, tt, ut)
        _eye_cache[key] = place_eye(cp, spec['eye'], spec['eye'].get('R', 40.0))
    return _eye_cache[key]


def solve_v(v, cam_loc, eye_loc, R, t, u=0.0):
    v = dict(VDEF, **(v or {}))
    dx, dy = eye_loc[0] - cam_loc[0], eye_loc[1] - cam_loc[1]
    Dh = math.hypot(dx, dy)
    yaw = math.degrees(math.atan2(dx, dy))
    rh = val(v['rw'], t, u) * 9.0 / 16.0
    z = cam_loc[2]
    if v.get('aim'):
        D = math.sqrt(Dh * Dh + (eye_loc[2] - z) ** 2)
        tv = math.tan(math.atan(R / D)) / (2 * rh)
        pitch = math.degrees(math.atan2(eye_loc[2] - z, Dh))
    else:
        hz = val(v['hz'], t, 0)
        for _ in range(4):
            D = math.sqrt(Dh * Dh + (eye_loc[2] - z) ** 2)
            tv = math.tan(math.atan(R / D)) / (2 * rh)
            p = math.atan((2 * hz - 1) * tv)
            e = p + math.atan((1 - 2 * v['y']) * tv)
            z = min(400.0, max(0.5, eye_loc[2] - Dh * math.tan(e)))
        pitch = math.degrees(p)
    lens = 18.0 / tv
    loc = (cam_loc[0], cam_loc[1], z)
    d = dir_vec(pitch, yaw)
    return dict(loc=loc, target=(loc[0] + d[0] * 100, loc[1] + d[1] * 100, loc[2] + d[2] * 100), lens=lens, roll=0.0)


def state(t):
    spec = shot_at(t)
    u = smooth((t - spec['t0']) / max(1e-6, spec['t1'] - spec['t0']))
    st = {}
    for k, dv in PROPS.items():
        st[k] = val(spec.get('props', {}).get(k, dv), t, u)
    eye_loc, R = eye_state(spec, t)
    cp = cam_params(spec, t, u)
    loc = (cp['x'], cp['y'], cp['h'])
    if cp['aim'] is not None or cp['track']:
        target = eye_loc
    else:
        d = dir_vec(pitch_for(cp), cp['yaw'])
        target = (loc[0] + d[0] * 100, loc[1] + d[1] * 100, loc[2] + d[2] * 100)
    if cp['track'] and cp['aim'] is None:
        # keep the horizon where yh says while turning toward the eye
        dx, dy = eye_loc[0] - loc[0], eye_loc[1] - loc[1]
        yaw = math.degrees(math.atan2(dx, dy))
        d = dir_vec(pitch_for(cp), yaw)
        target = (loc[0] + d[0] * 100, loc[1] + d[1] * 100, loc[2] + d[2] * 100)
    st['cam'] = dict(loc=loc, target=target, lens=cp['lens'], roll=cp['roll'])
    st['camv'] = solve_v(spec.get('v'), loc, eye_loc, R, t, u)
    st['eye_loc'] = eye_loc
    st['eye_R'] = R
    st['shot'] = spec['id']
    return st


# ------------------------------------------------------------------ Shorts
SHORTS = {
    'SH1': [(55.98, 82.95)],
    'SH2': [(167.60, 194.61)],
    'SH3': [(157.70, 167.60), (194.61, 220.40)],
}


if __name__ == '__main__':
    for s in SHOTS:
        st = state(s['t0'] + 0.01)
        e = st['eye_loc']
        print(f"{s['id']:5s} {s['t0']:7.2f}-{s['t1']:7.2f} eye=({e[0]:7.1f},{e[1]:7.1f},{e[2]:6.1f}) R={st['eye_R']:5.1f} "
              f"lens={st['cam']['lens']:5.1f} camv_lens={st['camv']['lens']:6.1f} camv_z={st['camv']['loc'][2]:6.1f}")
