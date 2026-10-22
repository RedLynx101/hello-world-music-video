"""The orb's sound rig: mood color, gimbal rings, voice ring, kick pulses and shockwaves.

Pure Python (imported by Blender for the bake and by the compositor). Section-level "mood" keys run across
shot cuts, so the orb's state flows continuously; per-frame audio features (analysis/rig.json) ride on top.
"""
import json, math, os
import shots
from shots import keyed, W, smooth

# Project root: HELLO_WORLD_ROOT if set, otherwise the folder above scripts/.
ROOT = os.environ.get('HELLO_WORLD_ROOT') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RIG = json.load(open(os.path.join(ROOT, 'analysis', 'rig.json')))
FPS = 24
N = RIG['n']
VOC, KICK, ENERGY, BASS = RIG['vocal'], RIG['kick'], RIG['energy'], RIG['bass']
KICKS = RIG['kicks']          # [t, strength, is_downbeat]
NO = W(31, -1)                # "...where I say no"

# ------------------------------------------------------------------ section moods (absolute seconds)
MOOD = {
    # color: cold red verse 1 -> white-hot chorus -> amber when it meets people -> crimson temptation
    # (ember and gold come from the shot props in the bridge and final chorus)
    'eye_cold': [(0, 1.0), (41.9, 1.0), (54.5, 0.0)],
    'eye_heat': [(0, 0.0), (41.9, 0.0), (55.4, 0.35), (56.4, 1.0), (73.0, 1.0), (74.6, 0.25), (84.0, 0.35), (86.6, 0.05),
                 (112.4, 0.05), (121.0, 0.45), (125.0, 0.5), (125.7, 0.9), (141.0, 0.9), (142.4, 0.25), (150.0, 0.4),
                 (151.6, 0.7), (166.6, 0.85), (166.8, 0.0)],
    'eye_amber': [(0, 0.0), (86.0, 0.0), (95.0, 0.55), (105.0, 0.9), (112.4, 0.8), (W(30, 3), 0.6), (W(31, 0), 0.25),
                  (NO + 0.12, 0.85), (125.0, 0.6), (141.0, 0.5), (142.6, 0.8), (150.5, 0.6), (152.6, 0.0)],
    'eye_crimson': [(0, 0.0), (151.0, 0.0), (153.0, 0.8), (160.0, 1.0), (166.7, 1.0), (166.8, 0.0)],
    # motion: how far the rings leave the face plane, how fast they turn, how out of sync they get
    'rig_tilt': [(0, 0.0), (15.65, 0.0), (17.0, 0.14), (41.9, 0.14), (54.5, 0.45), (56.2, 0.9), (73.0, 0.9), (74.7, 0.12),
                 (79.5, 0.25), (85.5, 0.2), (87.0, 0.06), (105.5, 0.06), (107.0, 0.22), (112.4, 0.2), (W(30, 3), 0.35),
                 (W(31, 0), 0.65), (NO, 0.65), (NO + 0.22, 0.0), (124.6, 0.05), (125.7, 0.8), (141.0, 0.8), (142.5, 0.15),
                 (146.2, 0.25), (151.0, 0.5), (153.0, 0.95), (166.7, 1.0), (167.6, 0.0), (180.28, 0.0), (194.0, 0.3),
                 (195.5, 0.72), (213.4, 0.72), (214.6, 0.18), (219.0, 0.45), (228.0, 0.35), (232.0, 0.0)],
    'rig_spin': [(0, 4.0), (15.65, 5.0), (41.9, 6.0), (55.0, 10.0), (56.2, 16.0), (73.0, 16.0), (74.7, 6.0), (86.0, 4.0),
                 (112.4, 6.0), (NO, 14.0), (NO + 0.3, 3.0), (125.7, 15.0), (141.0, 15.0), (142.5, 6.0), (151.0, 12.0),
                 (163.0, 30.0), (166.8, 0.0), (167.6, 1.5), (180.28, 2.0), (194.6, 8.0), (213.4, 9.0), (214.6, 4.0),
                 (219.0, 7.0), (229.9, 4.0), (231.3, 190.0), (232.1, 0.0)],
    # the ending: on the last "hello, world" the rings fold in and the orb shrinks to one point of light
    'collapse': [(0, 0.0), (229.9, 0.0), (231.5, 1.0)],
    # the breakdown takes the city's lights one by one (center first); a few come back in the bridge, the rest at dawn
    'lights_taken': [(0, 0.0), (151.4, 0.0), (156.0, 0.18), (161.0, 0.5), (164.5, 0.85), (166.3, 1.0), (167.6, 0.96),
                     (180.28, 0.70), (193.9, 0.50), (197.2, 0.0)],
    'rig_chaos': [(0, 0.0), (44.0, 0.0), (46.5, 0.2), (48.3, 0.0), (151.0, 0.0), (155.0, 0.4), (163.5, 1.0), (166.8, 0.0)],
    'voice_gain': [(0, 0.7), (41.9, 0.8), (56.0, 1.0), (73.6, 0.8), (86.0, 0.65), (112.4, 0.8), (125.0, 1.0), (151.0, 1.15),
                   (166.8, 1.0), (167.6, 0.35), (180.28, 0.45), (194.6, 1.0), (232.0, 1.0)],
    'wave_gain': [(0, 0.0), (55.7, 0.0), (56.0, 1.0), (73.0, 1.0), (73.8, 0.0), (79.5, 0.0), (79.9, 0.35), (84.5, 0.35),
                  (86.0, 0.0), (125.0, 0.0), (125.3, 1.0), (141.0, 1.0), (141.5, 0.0), (146.2, 0.0), (146.5, 0.4),
                  (151.0, 0.6), (166.6, 0.8), (166.8, 0.0), (194.5, 0.0), (194.8, 1.0), (213.4, 1.0), (214.0, 0.0),
                  (219.0, 0.0), (219.4, 0.7), (229.6, 0.6), (230.2, 0.0)],
    'pulse_gain': [(0, 0.012), (56.0, 0.04), (73.6, 0.015), (125.0, 0.04), (141.3, 0.015), (151.0, 0.05), (166.8, 0.01),
                   (194.6, 0.035), (232.0, 0.03)],
    'g1_vis': [(0, 1.0), (167.6, 1.0), (168.6, 0.18), (180.28, 0.18), (190.0, 1.0)],
    'breath': [(0, 0.0), (167.3, 0.0), (168.0, 1.0), (186.0, 1.0), (190.0, 0.0)],
    # the boot sequence on the first close-up: outer ring draws on, then the mid ring, then the voice ring
    'boot1': [(0, 0.0), (9.4, 0.0), (11.6, 1.0)],
    'boot2': [(0, 0.0), (10.6, 0.0), (12.8, 1.0)],
    'boot3': [(0, 0.0), (11.9, 0.0), (14.0, 1.0)],
}
MOOD_PROPS = ['eye_cold', 'eye_heat', 'eye_amber', 'eye_crimson', 'voice_gain', 'g1_vis', 'boot1', 'boot2', 'boot3',
              'shell_vis', 'g3_vis']


def mood(t):
    return {k: keyed(v, t) for k, v in MOOD.items()}


def _fi(t):
    return max(0, min(N - 1, int(round(t * FPS))))


def _noise(t, k):
    """Smooth deterministic wobble in [-1, 1] (sum of incommensurate sines)."""
    return (math.sin(2.31 * t + 1.7 * k) * 0.5 + math.sin(5.13 * t + 0.6 * k + 1.0) * 0.3 +
            math.sin(11.7 * t + 2.9 * k + 2.0) * 0.2)


# ------------------------------------------------------------------ integrated motion (precomputed per frame)
_SPIN, _PREC = [0.0] * N, [0.0] * N
_s = _p = 0.0
for _f in range(N):
    _t = _f / FPS
    _m_spin = keyed(MOOD['rig_spin'], _t)
    _s += _m_spin * (1.0 + 0.8 * KICK[_f] * keyed(MOOD['wave_gain'], _t)) / FPS
    _p += (0.22 + 0.055 * _m_spin) / FPS
    _SPIN[_f], _PREC[_f] = _s, _p

# shockwave events: beats inside wave sections; 4 slots, oldest reused
LIFE = 2.6
SLOTS = 4
_EVENTS = []
for _t, _st, _d in KICKS:
    _wg = keyed(MOOD['wave_gain'], _t)
    if _wg < 0.05:
        continue
    if not _d and _st < 0.5 and _wg < 0.9:
        continue
    _EVENTS.append((_t, min(1.0, _st * _wg * (1.0 if _d else 0.8))))
# two set-piece waves: the word "no", and the orb's last breath as it collapses
NO_HIT = NO + 0.02
END_HIT = 231.35
_EVENTS += [(NO_HIT, 1.6), (END_HIT, 1.3)]
_EVENTS.sort()
_SLOT_EVENTS = [[] for _ in range(SLOTS)]
for _i, _e in enumerate(_EVENTS):
    _SLOT_EVENTS[_i % SLOTS].append(_e)


def waves(t):
    """[(u 0..1 progress, alpha)] per slot; alpha 0 when idle."""
    out = []
    for evs in _SLOT_EVENTS:
        cur = None
        for te, s in evs:
            if te <= t < te + LIFE:
                cur = (te, s)
        if cur is None:
            out.append((0.0, 0.0))
        else:
            u = (t - cur[0]) / LIFE
            out.append((u, cur[1] * (1 - u) ** 1.8))
    return out


def rig_state(t, bezel_rot=0.0, iris_rot=0.0):
    """Everything the bake needs for the orb at time t (angles in degrees)."""
    f = _fi(t)
    m = mood(t)
    col = m['collapse']
    A = m['rig_tilt'] * (1 - col)
    ch = m['rig_chaos']
    spin, prec = _SPIN[f], _PREC[f]
    jolt = 7.0 * KICK[f] * m['wave_gain']
    g1 = (A * 58.0 * math.sin(prec) + ch * 38.0 * _noise(t, 1) + jolt,
          A * 30.0 * math.cos(0.73 * prec + 0.9) + ch * 30.0 * _noise(t, 2),
          bezel_rot + spin)
    g2 = (-A * 42.0 * math.sin(1.21 * prec + 2.1) + ch * 45.0 * _noise(t, 3),
          A * 62.0 * math.cos(1.07 * prec) + ch * 36.0 * _noise(t, 4) - 0.8 * jolt,
          iris_rot - 1.4 * spin)
    g3_vis = smooth(A / 0.5)
    g3 = (64.0 + 10.0 * math.sin(0.4 * prec) + ch * 25.0 * _noise(t, 5), 0.0, math.degrees(prec * 0.8))
    breath = m['breath'] * 0.035 * math.sin(2 * math.pi * t / 3.34)
    no_hit = math.exp(-(t - NO_HIT) / 0.18) if t >= NO_HIT - 0.02 else 0.0
    ring_k = 1.0 - smooth(col / 0.8)                      # rings fold away first...
    core_k = 1.0 - 0.965 * smooth((col - 0.2) / 0.8)      # ...then the orb shrinks to a point
    st = dict(m)
    st.update(
        g1=g1, g2=g2, g3=g3, g3_spin=2.2 * spin, g3_vis=g3_vis,
        g2_scale=1.0 + breath,
        ring_scale=max(0.001, ring_k),
        int_boost=1.0 + 3.0 * col + 0.35 * no_hit,
        sky_glow_k=1.0 - 0.7 * col,
        core_scale=(1.0 + m['pulse_gain'] * KICK[f] + 0.5 * breath + 0.12 * no_hit) * core_k,
        shell_vis=0.18 + 0.6 * A,
        shell_rot=(18.0, 0.0, 4.0 * t + 0.25 * spin),
        waves=waves(t),
        vocal=VOC[f], kick=KICK[f], energy=ENERGY[f],
    )
    return st


if __name__ == '__main__':
    print('events', len(_EVENTS))
    for tt in (12.0, 30.0, 60.0, 64.0, 75.0, 96.0, 121.7, 135.0, 160.0, 175.0, 203.0, 215.0):
        s = rig_state(tt)
        print(tt, {k: (round(v, 2) if isinstance(v, float) else v) for k, v in s.items()
                   if k in ('rig_tilt', 'eye_heat', 'eye_amber', 'eye_crimson', 'wave_gain', 'g3_vis')},
              [tuple(round(x, 1) for x in s['g1'])], [tuple(round(a, 2) for a in w) for w in s['waves']])
