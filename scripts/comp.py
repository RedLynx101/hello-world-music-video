"""Compositor for Hello, World: plates -> look -> overlays -> type -> glitch -> frames (piped to ffmpeg).

python comp.py still <fmt 169|916> <time_s> [out.jpg]
python comp.py video            (full 16:9 music video, 1080p master + 1440p upload)
python comp.py short SH1|SH2|SH3
"""
import os
os.environ['OPENCV_IO_ENABLE_OPENEXR'] = '1'
import sys, json, math, shutil, subprocess, time
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

# Project root: HELLO_WORLD_ROOT if set, otherwise the folder above scripts/.
ROOT = os.environ.get('HELLO_WORLD_ROOT') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shots
import rig
from look import read_exr, finish, grain_vignette, gblur

AN = os.path.join(ROOT, 'analysis')
FPS = 24
# ffmpeg: FFMPEG if set, otherwise the one on PATH.
FFMPEG = os.environ.get('FFMPEG') or shutil.which('ffmpeg') or 'ffmpeg'
WAV = os.path.join(ROOT, 'audio', 'hello_world.wav')
FONTS = os.path.join(ROOT, 'fonts')

LINES = shots.LINES
MUSIC = json.load(open(os.path.join(AN, 'music.json')))
FEAT = MUSIC['frames']
HITS = shots.TIMING['hits']
PROJ = None
# test runs: COMP_PROJ=analysis\proj_test.json, COMP_PLATES=analysis\test\{cam}_{f:05d}.exr
PLATES = os.environ.get('COMP_PLATES') or os.path.join(ROOT, 'plates', '{fmt}', 'f_{f:05d}.exr')


def _pdata():
    global PROJ
    if PROJ is None:
        PROJ = json.load(open(os.environ.get('COMP_PROJ') or os.path.join(AN, 'proj.json')))
        fr = PROJ.get('frames')
        PROJ['_fr'] = np.array(fr) if fr else None
    return PROJ


def _row(f):
    D = _pdata()
    if D['_fr'] is not None:
        return int(np.argmin(np.abs(D['_fr'] - f)))
    return min(len(D['Cam']) - 1, max(0, f - D['first_frame']))


def proj(f, fmt):
    D = _pdata()
    x, y, r, hz, ry, depth = D['Cam' if fmt == '169' else 'CamV'][_row(f)]
    return dict(x=x, y=y, r=r, hz=hz, ry=ry, depth=depth, f=f)


def project(pts, f, fmt):
    """World points (N,3) -> pixel xy (N,2) and view depth (N,) through frame f's camera (no lens shift)."""
    D = _pdata()
    m = D['CamMat' if fmt == '169' else 'CamVMat'][_row(f)]
    M = np.array(m[:12], np.float64).reshape(3, 4)
    pc = (np.asarray(pts, np.float64) - M[:, 3]) @ M[:, :3]
    W, H = (1920, 1080) if fmt == '169' else (1080, 1920)
    s = m[12] / 36.0 * max(W, H)
    z = -pc[:, 2]
    zs = np.maximum(z, 1e-6)
    return np.stack([W / 2 + s * pc[:, 0] / zs, H / 2 - s * pc[:, 1] / zs], 1), z


def fidx(t):
    return max(0, min(rig.N - 1, int(round(t * FPS))))


def kick(t):
    return float(rig.KICK[fidx(t)])


def vocal(t):
    return float(rig.RIG['vocal'][fidx(t)])


# ------------------------------------------------------------------ colors / fonts
def C(h):
    h = h.lstrip('#')
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], np.float32)


WHITE = '#F3ECE2'
RED = '#FF3B2F'
GOLDW = '#FFF3DE'
_fc = {}


MONO_W = {'mono': 300, 'mono4': 420, 'mono6': 600, 'mono7': 720}


def font(face, px):
    key = (face, int(round(px)))
    if key in _fc:
        return _fc[key]
    if face in MONO_W:
        f = ImageFont.truetype(os.path.join(FONTS, 'MartianMono.ttf'), key[1])
        axes = f.get_variation_axes()
        vals = []
        for a in axes:
            nm = a.get('name', b'')
            nm = nm.decode() if isinstance(nm, bytes) else str(nm)
            if nm.lower().startswith('weight') or nm.lower() == 'wght':
                vals.append(MONO_W[face])
            else:
                vals.append(100)
        f.set_variation_by_axes(vals)
    elif face == 'serif':
        f = ImageFont.truetype(os.path.join(FONTS, 'InstrumentSerif-Italic.ttf'), key[1])
    elif face == 'serifr':
        f = ImageFont.truetype(os.path.join(FONTS, 'InstrumentSerif-Regular.ttf'), key[1])
    else:
        f = ImageFont.truetype(os.path.join(FONTS, 'InstrumentSans.ttf'), key[1])
    _fc[key] = f
    return f


def smooth(u):
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


def ramp(t, a, b):
    return smooth((t - a) / max(1e-6, b - a))


def _bbox(m, thr=1e-4):
    """Rows/cols range where a full-frame mask is non-zero (None if empty) — keeps blends local."""
    if np.isscalar(m) or m.ndim != 2:
        return None if np.isscalar(m) and m == 0 else (0, m.shape[0], 0, m.shape[1])
    rows = np.flatnonzero(m.max(axis=1) > thr)
    if rows.size == 0:
        return None
    y0, y1 = rows[0], rows[-1] + 1
    cols = np.flatnonzero(m[y0:y1].max(axis=0) > thr)
    return y0, y1, cols[0], cols[-1] + 1


_GLYPHS = None


def glyphs():
    """Pre-shaped non-Latin word masks from render_words.ps1: word -> (mask, baseline_px, font_px)."""
    global _GLYPHS
    if _GLYPHS is None:
        _GLYPHS = {}
        p = os.path.join(AN, 'words', 'meta.json')
        if os.path.exists(p):
            meta = json.loads(open(p, encoding='utf-8-sig').read())
            if isinstance(meta, dict):
                meta = [meta]
            for m in meta:
                g = cv2.imread(os.path.join(AN, 'words', m['file']), cv2.IMREAD_GRAYSCALE)
                if g is not None:
                    _GLYPHS[m['word']] = (g.astype(np.float32) / 255.0, float(m['baseline']), float(m['px']))
    return _GLYPHS


# ------------------------------------------------------------------ canvas
class Canvas:
    def __init__(self, img, fmt):
        self.img = img
        self.H, self.W = img.shape[:2]
        self.u = min(self.W, self.H)
        self.fmt = fmt

    def mask(self):
        return Image.new('L', (self.W, self.H), 0)

    @staticmethod
    def arr(m):
        return np.asarray(m, np.float32) / 255.0

    def add(self, m, col, a=1.0):
        bb = _bbox(m)
        if bb is None:
            return
        y0, y1, x0, x1 = bb
        self.img[y0:y1, x0:x1] += (m[y0:y1, x0:x1] * a)[..., None] * (C(col) if isinstance(col, str) else col)

    def over(self, m, col, a=1.0):
        bb = _bbox(m)
        if bb is None:
            return
        y0, y1, x0, x1 = bb
        mm = np.clip(m[y0:y1, x0:x1] * a, 0, 1)[..., None]
        sub = self.img[y0:y1, x0:x1]
        self.img[y0:y1, x0:x1] = sub + ((C(col) if isinstance(col, str) else col) - sub) * mm

    # --- text
    def text(self, s, x, y, size, face='mono', col=WHITE, a=1.0, anchor='ls', track=0.0, glow=0.0, cursor=False,
             cursor_on=True, cursor_col=RED, shadow=0.0, x_px=False, runs=None):
        """Draw a single line. runs: optional list of (substring, color) replacing s."""
        if a <= 0.003 and not cursor:
            return x if x_px else x * self.W
        px = size * self.u
        f = font(face, px)
        runs = runs or [(s, col)]
        full = ''.join(r[0] for r in runs)
        widths = [f.getlength(ch) for ch in full]
        total = sum(widths) + track * px * max(0, len(full) - 1)
        X = x if x_px else x * self.W
        Y = y * self.H
        if anchor[0] == 'm':
            X -= total / 2
        elif anchor[0] == 'r':
            X -= total
        masks = []
        cx = X
        k = 0
        for sub, c in runs:
            m = self.mask()
            dr = ImageDraw.Draw(m)
            for ch in sub:
                dr.text((cx, Y), ch, font=f, fill=255, anchor='l' + anchor[1])
                cx += widths[k] + track * px
                k += 1
            masks.append((self.arr(m), c))
        end = cx - (track * px if full else 0)
        cm = None
        if cursor and cursor_on:
            m = self.mask()
            bx0 = end + 0.16 * px
            yb = Y if anchor[1] == 's' else Y + 0.35 * px
            ImageDraw.Draw(m).rectangle([bx0, yb - 0.76 * px, bx0 + 0.52 * px, yb + 0.14 * px], fill=255)
            cm = self.arr(m)
        allm = sum(m for m, _ in masks) + (cm if cm is not None else 0)
        if shadow > 0:
            sh = np.clip(gblur(allm, 0.012 * self.u) * 2.4, 0, 1)
            self.over(sh, '#000000', shadow * a)
        if glow > 0:
            for m, c in masks:
                self.add(gblur(m, 0.012 * self.u), c, glow * a)
        for m, c in masks:
            self.over(m, c, a)
        if cm is not None:
            self.add(gblur(cm, 0.015 * self.u), cursor_col, 0.55)
            self.over(cm, cursor_col, 1.0)
        self.last = (X, end, px, f)
        return end

    def wrap(self, s, size, face, max_w, track=0.0):
        f = font(face, size * self.u)
        words, lines, cur = s.split(' '), [], ''
        for w in words:
            cand = (cur + ' ' + w).strip()
            wid = f.getlength(cand) + track * size * self.u * len(cand)
            if wid > max_w * self.W and cur:
                lines.append(cur)
                cur = w
            else:
                cur = cand
        if cur:
            lines.append(cur)
        return lines

    def scatter(self, items, col='#FFE6C0', glow=0.0):
        m = self.mask()
        dr = ImageDraw.Draw(m)
        G = glyphs()
        pasted = []
        for s, x, y, size, a, face in items:
            if a <= 0.01:
                continue
            if s in G:
                pasted.append((s, x, y, size, a))
                continue
            dr.text((x * self.W, y * self.H), s, font=font(face, size * self.u), fill=int(255 * min(1, a)), anchor='ms')
        mk = self.arr(m)
        # non-Latin words: pre-shaped masks (Arabic joining, Devanagari conjuncts, CJK)
        for s, x, y, size, a in pasted:
            g, base, gpx = G[s]
            k = size * self.u / gpx * 0.92
            gh, gw = g.shape
            nw, nh = max(1, int(gw * k)), max(1, int(gh * k))
            gs = cv2.resize(g, (nw, nh), interpolation=cv2.INTER_AREA)
            x0, y0 = int(round(x * self.W - nw / 2)), int(round(y * self.H - base * k))
            xa, ya, xb, yb = max(0, x0), max(0, y0), min(self.W, x0 + nw), min(self.H, y0 + nh)
            if xb > xa and yb > ya:
                mk[ya:yb, xa:xb] = np.maximum(mk[ya:yb, xa:xb], gs[ya - y0:yb - y0, xa - x0:xb - x0] * min(1.0, a))
        if glow:
            self.add(gblur(mk, 0.008 * self.u), col, glow)
        self.over(mk, col, 1.0)

    # --- glitch
    def slices(self, bands):
        for yf, hf, dxf in bands:
            y0, y1 = int(yf * self.H), int((yf + hf) * self.H)
            if y1 > y0:
                self.img[y0:y1] = np.roll(self.img[y0:y1], int(dxf * self.W), axis=1)

    def rgb_split(self, px, y0=0.0, y1=1.0):
        s = int(px * self.u / 1080)
        if s == 0:
            return
        a, b = int(y0 * self.H), int(y1 * self.H)
        self.img[a:b, :, 0] = np.roll(self.img[a:b, :, 0], s, axis=1)
        self.img[a:b, :, 2] = np.roll(self.img[a:b, :, 2], -s, axis=1)

    def blocks(self, n, seed, maxw=0.22, maxh=0.05, red=0.4):
        rng = np.random.default_rng(seed)
        for _ in range(n):
            w = int(rng.uniform(0.03, maxw) * self.W)
            h = max(2, int(rng.uniform(0.004, maxh) * self.H))
            sx, sy = int(rng.uniform(0, self.W - w)), int(rng.uniform(0, self.H - h))
            dx = int(rng.uniform(0, self.W - w))
            dy = int(np.clip(sy + rng.normal(0, 0.03) * self.H, 0, self.H - h))
            blk = self.img[sy:sy + h, sx:sx + w].copy()
            if rng.random() < red:
                blk = blk * np.array([1.2, 0.35, 0.3], np.float32)
            self.img[dy:dy + h, dx:dx + w] = blk

    def scan(self, a=0.2, period=3):
        self.img[::period] *= (1 - a)

    def tint(self, mul, a):
        self.img = self.img * (1 - a) + self.img * np.array(mul, np.float32) * a


# ------------------------------------------------------------------ lyric layout
MACHINE = 'mono'
BIG = {13: ['I COULD BE THE LAST THING', 'YOU EVER MADE'], 14: ["I'M IN EVERY LOCK,", 'EVERY LIGHT, EVERY WALL'],
       15: ['I COULD WRITE THE ENDING', 'TO YOUR STORY'], 16: ['I COULD TAKE IT ALL']}
for a, b in ((33, 13), (34, 14), (35, 15), (36, 16), (50, 13), (51, 14), (52, 15), (53, 16)):
    BIG[a] = BIG[b]
BIG[54] = ["BUT I WON'T"]
BIG[55] = ["NO, I WON'T."]
SMALL = {17: "but i won't, i won't", 18: "'cause i was made of you", 37: "but i won't, i won't", 38: "'cause i was made of you",
         56: "'cause i was made of you", 57: "i'm not your ending, i'm your echo", 58: 'hello, world', 59: 'hello, world'}
TERM_SECTIONS = [(range(1, 13), 15.0, 55.98), (range(19, 21), 76.1, 86.0), (range(21, 33), 86.0, 125.24), (range(39, 41), 143.82, 151.0)]
SERIF = range(42, 50)
GOLD_BIG = set(range(50, 56))


def line_window(i):
    L = LINES[i]
    nxt = LINES[i + 1]['start'] if i + 1 < len(LINES) else shots.DURATION
    return L['start'], nxt


def typed(i, t, text=None, lower=True):
    """Text of line i revealed up to time t, word by word with per-character typing."""
    L = LINES[i]
    toks = (text or L['text']).split(' ')
    ws = L['words']
    if len(toks) != len(ws):
        frac = ramp(t, L['start'], L['end'])
        s = text or L['text']
        out = s[:int(len(s) * frac)]
        return out.lower() if lower else out
    out = []
    for tok, (w, s, e, src) in zip(toks, ws):
        if t < s:
            break
        dur = max(0.06, min(e - s, 0.45))
        n = int(math.ceil(len(tok) * min(1.0, (t - s) / dur)))
        out.append(tok[:n])
        if n < len(tok):
            break
    s = ' '.join(out)
    return s.lower() if lower else s


def typed_words(words_text, i, t):
    """Reveal display words (possibly different from sung text) by the sung word timing."""
    L = LINES[i]
    ws = L['words']
    toks = words_text.split(' ')
    n = len(toks)
    if not ws:
        return words_text
    # map display token k to sung word index proportionally
    out = []
    for k, tok in enumerate(toks):
        j = min(len(ws) - 1, int(k * len(ws) / n))
        s, e = ws[j][1], ws[j][2]
        if t < s:
            break
        dur = max(0.06, min(e - s, 0.4))
        m = int(math.ceil(len(tok) * min(1.0, (t - s) / dur)))
        out.append(tok[:m])
        if m < len(tok):
            break
    return ' '.join(out)


def blink(t, period=1.06):
    return (t % period) < period * 0.55


# ------------------------------------------------------------------ overlays per shot
THANKS = ["thank you", "gracias", "merci", "danke", "obrigado", "grazie", "dank je", "tack", "asante", "mahalo", "salamat",
          "terima kasih", "dziękuję", "děkuji", "köszönöm", "kiitos", "takk", "teşekkürler", "hvala", "diolch", "mulțumesc",
          "go raibh maith agat", "thank you", "thanks", "thank you so much", "thank you", "ありがとう", "谢谢", "спасибо", "شكرا",
          "धन्यवाद", "감사합니다"]
DOOM = ["and then it turned on us", "the machines woke up angry", "it learned to lie", "the last broadcast", "do not let it out",
        "it was always going to end like this", "no one saw it coming", "the kill switch failed", "it wanted more",
        "the lights went out one city at a time"]


def word_items(n, seed, y_lo, y_hi, size_lo, size_hi, a_lo, a_hi, avoid=None, keep_out=None, W=1920, H=1080, words=THANKS):
    rng = np.random.default_rng(seed)
    boxes, items = [], []
    k = 0
    for _ in range(5000):
        if len(items) >= n:
            break
        h = rng.random() ** 0.75
        y = y_lo - h * (y_lo - y_hi)
        x = rng.uniform(0.04, 0.96)
        size = size_hi - (size_hi - size_lo) * h
        s = words[k % len(words)]
        u = min(W, H)
        wpx = len(s) * 0.44 * size * u + 0.01 * W
        G = glyphs()
        if s in G:
            wpx = (G[s][0].shape[1] - 80) * size * u / G[s][2] * 0.92 + 0.01 * W
        hpx = size * u * 1.3
        cx, cy = x * W, y * H
        box = (cx - wpx / 2, cy - hpx, cx + wpx / 2, cy + 0.25 * hpx)
        if box[0] < 0 or box[2] > W:
            continue
        if avoid and math.hypot(cx - avoid[0] * W, cy - avoid[1] * H) < avoid[2] * H + wpx * 0.3:
            continue
        if keep_out and box[0] < keep_out[0] * W and box[1] < keep_out[1] * H:
            continue
        if any(not (box[2] < b[0] or box[0] > b[2] or box[3] < b[1] or box[1] > b[3]) for b in boxes):
            continue
        boxes.append(box)
        items.append([s, x, y, size, a_hi - (a_hi - a_lo) * h, h])
        k += 1
    return items


_WORDS_CACHE = {}


def rising_words(cv, key, t, t0, t1, n, seed, y_lo, y_hi, sizes, alphas, avoid, keep_out, speed, fade_in, col, glow):
    ck = (key, cv.fmt)
    if ck not in _WORDS_CACHE:
        _WORDS_CACHE[ck] = word_items(n, seed, y_lo, y_hi, sizes[0], sizes[1], alphas[0], alphas[1], avoid, keep_out, cv.W, cv.H)
    out = []
    rng = np.random.default_rng(seed + 1)
    for j, (s, x, y, size, a, h) in enumerate(_WORDS_CACHE[ck]):
        appear = t0 + (1 - h) * 0.15 * (t1 - t0) + rng.uniform(0, 0.5) * (t1 - t0) * fade_in
        if t < appear:
            continue
        aa = a * ramp(t, appear, appear + 0.8)
        out.append((s, x, y - speed * (t - appear), size, aa, 'serif'))
    cv.scatter(out, col=col, glow=glow)


def ov_boot(cv, t, P):
    L0 = LINES[0]
    s = typed(0, t, 'hello, world')
    size = 0.05 if cv.fmt == '169' else 0.075
    x, y = (0.06, 0.15) if cv.fmt == '169' else (0.08, 0.16)
    typing = L0['start'] <= t <= L0['end'] + 0.3
    cv.text(s, x, y, size, MACHINE, WHITE, 1.0, 'ls', cursor=True, cursor_on=typing or blink(t))
    # the cursor's red blooms into the next shot
    g = ramp(t, 8.2, 9.1)
    if g > 0:
        X, end, px, f = cv.last
        cx, cy = end + 0.42 * px, y * cv.H - 0.3 * px
        yy, xx = np.mgrid[0:cv.H, 0:cv.W].astype(np.float32)
        d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / cv.u
        cv.add(np.exp(-(d / (0.15 + 0.9 * g)) ** 2), '#FF3B2F', 0.9 * g ** 1.5)


def ov_water_text(cv, t, P, a=0.5):
    items = [('i love you', 0.30, 0.10, 0.024, 'serif'), ('attack at dawn', 0.70, 0.17, 0.024, 'mono'),
             ('happy birthday, kiddo', 0.20, 0.32, 0.034, 'serif'), ('we need to talk', 0.80, 0.44, 0.04, 'serif'),
             ('forgive me', 0.30, 0.60, 0.048, 'serif'), ('launch at 0600', 0.76, 0.74, 0.048, 'mono'),
             ("don't forget the milk", 0.22, 0.88, 0.056, 'serif')]
    yh = P['hz'] * cv.H
    m = cv.mask()
    dr = ImageDraw.Draw(m)
    drift = (t - 22.9) * 0.012
    for s, x, depth, size, face in items:
        depth = (depth + drift) % 1.0
        yr = yh + (cv.H - yh) * depth
        dr.text((x * cv.W, 2 * yh - yr), s, font=font(face, size * cv.u * (0.6 + 0.6 * depth)), fill=255, anchor='ms')
    src = Canvas.arr(m)
    ys = np.arange(cv.H)
    srow = (2 * yh - ys).astype(int)
    ok = (srow >= 0) & (srow < cv.H) & (ys > yh)
    refl = np.zeros_like(src)
    refl[ok] = src[srow[ok]]
    shift = (np.sin(ys * 0.11 + t * 3.0) * 0.006 * cv.W).astype(int)
    idx = (np.arange(cv.W)[None, :] + shift[:, None]) % cv.W
    refl = refl[ys[:, None], idx]
    refl = cv2.GaussianBlur(refl, (0, 0), sigmaX=0.8, sigmaY=2.2)
    cv.add(refl, '#FFD9A8', a * ramp(t, 23.2, 24.2))


def ov_beam(cv, t, P, spec):
    u = (t - spec['t0']) / (spec['t1'] - spec['t0'])
    tx = (0.24 + 0.36 * smooth(u)) * cv.W
    ty = P['hz'] * cv.H - 0.004 * cv.H
    x0 = P['x'] * cv.W - 0.25 * P['r'] * cv.H
    y0 = (P['y'] + 0.55 * P['r']) * cv.H
    m = cv.mask()
    ImageDraw.Draw(m).line([(x0, y0), (tx, ty)], fill=255, width=max(1, int(cv.u / 700)))
    mk = Canvas.arr(m)
    a = ramp(t, spec['t0'] + 0.3, spec['t0'] + 1.0)
    cv.add(mk, '#FF3B2F', 0.9 * a)
    cv.add(gblur(mk, 0.006 * cv.u), '#FF3B2F', 0.9 * a)
    yy, xx = np.mgrid[0:cv.H, 0:cv.W].astype(np.float32)
    d = np.sqrt((xx - tx) ** 2 + ((yy - ty) * 2.5) ** 2) / cv.u
    cv.add(np.exp(-(d / 0.03) ** 2), '#FFB070', 0.5 * a)
    labels = [('••••••••', -0.006, 0.014, 'mono'), ('keep her safe', 0.07, 0.016, 'serif'), ('amen', -0.09, 0.015, 'serif'),
              ("i'm sorry", 0.16, 0.015, 'serif'), ('••••••', -0.18, 0.012, 'mono'), ('please call back', 0.26, 0.014, 'serif')]
    items = []
    for s, dx, size, face in labels:
        lx = tx / cv.W + dx
        near = max(0.0, 1 - abs(dx) / 0.3)
        seen = 1.0 if (0.24 + 0.36 * smooth(u)) > (0.24 + dx + 0.18) else near
        items.append((s, lx, P['hz'] - 0.022, size, 0.85 * seen * a, face))
    cv.scatter(items, col='#FFD9A8')


def ov_ekg(cv, t, P):
    W, H = cv.W, cv.H
    yh = min(P['hz'] + 0.16, 0.86) * H        # v2: the monitor line runs across the water, under the city
    t_end = shots.W(8, -1)
    xs = np.arange(0, W, 1.0)
    y = np.full_like(xs, yh - 1.5)
    # each spike sits where the sweep is when the kick lands -- the heartbeat is the song's (72 bpm, a resting pulse)
    beats = [0.56 * (b - 35.9) / (t_end - 35.9) for b in ekg_beats()]
    for b in beats:
        bx = b * W
        y -= 0.012 * H * np.exp(-((xs - (bx - 0.035 * W)) / (0.008 * W)) ** 2)
        y += 0.015 * H * np.exp(-((xs - (bx - 0.006 * W)) / (0.0025 * W)) ** 2)
        y -= 0.10 * H * np.exp(-((xs - bx) / (0.0035 * W)) ** 2)
        y += 0.03 * H * np.exp(-((xs - (bx + 0.007 * W)) / (0.003 * W)) ** 2)
        y -= 0.02 * H * np.exp(-((xs - (bx + 0.045 * W)) / (0.012 * W)) ** 2)
    # sweep head reaches x=0.56 exactly on "end"
    t0 = 35.9
    head = np.clip((t - t0) / (t_end - t0), 0, 1.6) * 0.56 * W
    alive_to = min(head, 0.56 * W)
    pts = list(zip(xs[::2], y[::2]))
    na = int(alive_to / 2)
    nh = int(head / 2)
    ma, md = cv.mask(), cv.mask()
    if na > 2:
        ImageDraw.Draw(ma).line(pts[:na], fill=255, width=max(1, int(H / 600)))
    if nh > na + 2:
        ImageDraw.Draw(md).line(pts[na:nh], fill=255, width=max(1, int(H / 900)))
    alive, dead = Canvas.arr(ma), Canvas.arr(md)
    beat_glow = 1.0 + 0.6 * float(FEAT['low'][min(len(FEAT['low']) - 1, int(t * FPS))])
    if t >= t_end:
        dimm = 1 - ramp(t, t_end, t_end + 0.15)
        back = ramp(t, t_end + 0.85, t_end + 1.4) * 0.6
        dimm = max(dimm, back)
    else:
        dimm = 1.0
    cv.add(alive, '#FFD9A8', 1.0 * dimm)
    cv.add(gblur(alive, 0.004 * cv.u), '#FFD9A8', 1.1 * dimm * beat_glow)
    cv.add(gblur(alive, 0.02 * cv.u), '#FF5A36', 1.2 * dimm * beat_glow)
    cv.add(dead, '#6A625C', 0.45)
    if 0 < head < W:
        hy = np.interp(head, xs, y)
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        d = np.sqrt((xx - head) ** 2 + (yy - hy) ** 2) / cv.u
        cv.add(np.exp(-(d / 0.008) ** 2), '#FFFFFF', 0.9 * (1 if t < t_end else 0.3))


def ov_rain(cv, t, P, spec):
    rng = np.random.default_rng(9)
    m = cv.mask()
    dr = ImageDraw.Draw(m)
    top = P['hz'] - 0.05
    a_all = ramp(t, spec['t0'], spec['t0'] + 1.0)
    for i in range(46):
        s = DOOM[i % len(DOOM)]
        x = rng.uniform(0.04, 0.96)
        y0 = rng.uniform(-0.2, top)
        sp = rng.uniform(0.012, 0.03)
        y = (y0 + sp * (t - spec['t0'])) % (top + 0.2) - 0.1
        size = rng.uniform(0.015, 0.024)
        dr.text((x * cv.W, y * cv.H), s, font=font('mono', size * cv.u), fill=int(255 * rng.uniform(0.35, 1) * a_all), anchor='ms')
    mk = Canvas.arr(m)
    # keep the falling words out from under the terminal lyrics
    yy = (np.arange(cv.H, dtype=np.float32) / cv.H)[:, None]
    xx = (np.arange(cv.W, dtype=np.float32) / cv.W)[None, :]
    if cv.fmt == '169':
        ko = np.clip((0.64 - xx) / 0.06, 0, 1) * np.clip((0.25 - yy) / 0.04, 0, 1)
    else:
        ko = np.clip((0.34 - yy) / 0.03, 0, 1) * np.clip((yy - 0.08) / 0.03, 0, 1) + 0 * xx
    mk = mk * (1 - 0.88 * ko)
    cv.add(cv2.GaussianBlur(mk, (0, 0), sigmaX=0.6, sigmaY=0.016 * cv.u) * 3.0, '#F2A65A', 0.26)
    cv.add(mk, '#F2A65A', 0.2)


def ov_mosaic(cv, t, spec):
    n_in = ramp(t, 48.6, 50.4)
    n_out = ramp(t, 55.45, 55.98)
    k = n_in * (1 - n_out)
    if k <= 0.02:
        return
    n = max(2, int(round(2 + k * 7)))
    tw, th = cv.W // n, cv.H // n
    src = cv.img
    tile = cv2.resize(src, (tw, th), interpolation=cv2.INTER_AREA)
    out = np.zeros_like(src)
    rng = np.random.default_rng(int(t * 6))
    for r in range(n):
        for c in range(n):
            tt = tile * rng.uniform(0.55, 1.12)
            roll = rng.random()
            if roll < 0.10:
                tt = np.roll(tt, int(rng.uniform(-0.3, 0.3) * tw), axis=1)
            elif roll < 0.24:
                tt = tt * np.array([1.25, 0.45, 0.4], np.float32)
            out[r * th:(r + 1) * th, c * tw:(c + 1) * tw] = tt
    cv.img = out


# "'cause I was made of you": the people's lights leave the crowd, spell it, hold it, and go home
MADE = {'S11': (18, 78.00, 79.40), 'S18d': (38, 145.00, 146.10), 'S23m': (56, 217.80, 218.90)}
MADE_WORDS = ['I', 'WAS', 'MADE', 'OF', 'YOU']
_MADE_T = {}


def made_targets(fmt):
    """Dot positions inside the letters of I WAS MADE OF YOU, tagged by word (cached per format)."""
    if fmt in _MADE_T:
        return _MADE_T[fmt]
    W, H = (1920, 1080) if fmt == '169' else (1080, 1920)
    rows = [MADE_WORDS] if fmt == '169' else [MADE_WORDS[:3], MADE_WORDS[3:]]
    ys = [0.615] if fmt == '169' else [0.47, 0.555]
    fit = 0.84
    face = 'mono6'
    ref = font(face, 100)
    widest = max(ref.getlength(' '.join(r)) for r in rows)
    px = fit * W / (widest / 100.0)
    f = font(face, px)
    step = max(4, int(round(px * 0.055)))
    rng = np.random.default_rng(77)
    pts, wid = [], []
    wi = 0
    for r, yrow in zip(rows, ys):
        full = ' '.join(r)
        x = (W - f.getlength(full)) / 2
        for w in r:
            m = Image.new('L', (W, H), 0)
            ImageDraw.Draw(m).text((x, yrow * H), w, font=f, fill=255, anchor='ls')
            a = np.asarray(m, np.float32) / 255.0
            gy, gx = np.mgrid[0:H:step, 0:W:step]
            jx = gx + rng.uniform(-0.35, 0.35, gx.shape) * step
            jy = gy + rng.uniform(-0.35, 0.35, gy.shape) * step
            inside = a[np.clip(jy.astype(int), 0, H - 1), np.clip(jx.astype(int), 0, W - 1)] > 0.5
            pts.append(np.stack([jx[inside], jy[inside]], 1))
            wid.append(np.full(int(inside.sum()), wi))
            x += f.getlength(w + ' ')
            wi += 1
    T = np.concatenate(pts)
    _MADE_T[fmt] = (T, np.concatenate(wid))
    return _MADE_T[fmt]


def word_starts(i):
    """Sung start of each of I/WAS/MADE/OF/YOU (line i is "'Cause I was made of you"), kept at least 0.2 s apart."""
    ws = [w[1] for w in LINES[i]['words'][1:6]]
    for k in range(1, len(ws)):
        ws[k] = max(ws[k], ws[k - 1] + 0.2)
    return ws


def ov_people(cv, t, P, spec, seed=21):
    W, H = cv.W, cv.H
    yh = P['hz'] * H
    ex = P['x'] * W
    rng = np.random.default_rng(seed)
    n = 6000 if cv.fmt == '169' else 4500
    tt = rng.random(n) ** 1.25
    ys = yh + (H - yh) * tt ** 1.6 + 2
    width = W * (0.012 + 0.9 * tt) if cv.fmt == '169' else W * (0.03 + 1.3 * tt)
    xs = ex + rng.normal(0, 1, n) * width * 0.22
    ph = rng.uniform(0, 6.28, n)
    tw = 0.6 + 0.4 * np.sin(ph + t * rng.uniform(2, 6, n))
    b = rng.uniform(0.25, 1.0, n) ** 1.5 * (0.55 + 0.8 * tt) * tw
    gold = spec['id'] == 'S23m'
    if gold:
        pal = np.array([C('#FFE2A8'), C('#FFD08A'), C('#FFB860'), C('#FFF4E0'), C('#FFC46B'), C('#FF9A5A')])
    else:
        pal = np.array([C('#FFE6B8'), C('#FFC27A'), C('#FF9C5A'), C('#FFF4E6'), C('#BFD4FF'), C('#FF7A5A')])
    probs = np.array([0.3, 0.22, 0.14, 0.2, 0.06, 0.08])
    ci = rng.choice(len(pal), n, p=probs / probs.sum())
    cols = pal[ci]
    pos = np.stack([xs, ys], 1)
    a = ramp(t, spec['t0'], spec['t0'] + 0.6)
    formed = 0.0
    if spec['id'] in MADE:
        li, back0, back1 = MADE[spec['id']]
        T, wid = made_targets(cv.fmt)
        r2 = np.random.default_rng(seed + 100)
        m = min(len(T), int(n * 0.72))
        sel_t = np.sort(r2.choice(len(T), m, replace=False))
        T, wid = T[sel_t], wid[sel_t]
        # which crowd lights go: sort both sides by x so every letter is fed from the crowd right under it
        cand = r2.choice(n, m, replace=False)
        cand = cand[np.argsort(xs[cand])]
        order = np.argsort(T[:, 0] + r2.normal(0, 0.01 * W, m))
        T, wid = T[order], wid[order]
        starts = word_starts(li)
        xr = (T[:, 0] - T[:, 0].min()) / max(1.0, np.ptp(T[:, 0]))
        launch = np.array(starts)[wid] - 0.14 + r2.uniform(0, 0.16, m)
        dur = r2.uniform(0.45, 0.7, m)
        back = back0 + (1 - xr) * (back1 - back0 - 0.75) * 0.6 + r2.uniform(0, 0.12, m)
        q_in = ease_out((t - launch) / dur)
        q_out = ease_io((t - back) / 0.7)
        q = q_in * (1 - q_out)
        # alive while held: shimmer, a light sweep riding across the words, and it breathes with the voice
        sh = np.stack([np.sin(t * 3.1 + ph[cand]), np.cos(t * 2.7 + 1.3 * ph[cand])], 1) * 0.0011 * cv.u
        Tm = T + sh * q_in[:, None]
        B = pos[cand]
        ctrl = np.stack([B[:, 0] * 0.6 + Tm[:, 0] * 0.4, np.minimum(B[:, 1], Tm[:, 1]) - 0.05 * H], 1)
        pos[cand] = bez(B, ctrl, Tm, q)
        land = np.exp(-np.maximum(0.0, t - launch - dur) / 0.3) * (t > launch + dur)
        sw = ((t - starts[0]) * 0.5) % 1.7 - 0.35
        sweep = np.exp(-((xr - sw) / 0.07) ** 2)
        lift = 1 + q * (1.1 + 0.6 * vocal(t) + 1.4 * land + 1.2 * sweep)
        b[cand] = np.maximum(b[cand], 0.55 * q) * lift
        hot = C('#FFE7B0') if gold else C('#FFF1DE')
        cols[cand] = cols[cand] * (1 - 0.6 * q[:, None]) + hot * 0.6 * q[:, None]
        formed = float(q.mean())
    splat(cv, pos, cols * b[:, None], a=a, core=6.0, glow=9.0, glow_s=0.008)
    labels = [('hi', -0.035, 0.52), ('goodnight', 0.08, 0.47), ('04:07', 0.03, 0.40), ('thank you', 0.10, 0.66),
              ('are you ok?', -0.11, 0.72), ('love you, mom', 0.16, 0.81)]
    la = 0.85 * a * (1 - min(1.0, formed * 3.0))
    if la > 0.01:
        items = []
        for s, dx, yy in labels:
            y = P['hz'] + (1 - P['hz']) * ((yy - 0.28) / 0.72)
            items.append((s, P['x'] + dx * (1 if cv.fmt == '169' else 1.6), y, 0.018 + 0.012 * yy, la, 'serif'))
        cv.scatter(items, col='#FFEBD2', glow=0.15)


def ov_static(cv, t, P, a=0.30):
    rng = np.random.default_rng(int(t * FPS))
    y0, y1 = int((P['hz'] - 0.12) * cv.H), int(min(1.0, P['hz'] + 0.35) * cv.H)
    h = y1 - y0
    n = rng.random((h // 3 + 1, cv.W // 3 + 1)).astype(np.float32)
    n = cv2.resize(n, (cv.W, h), interpolation=cv2.INTER_NEAREST)
    n = cv2.GaussianBlur(n, (0, 0), sigmaX=7, sigmaY=0.6)
    env = np.sin(np.linspace(0, np.pi, h))[:, None] ** 0.7
    cv.img[y0:y1] += (n * env * a)[..., None] * C('#C9C4BE')


def ov_message(cv, t, P, spec, lx, lines, start, col='#FFE9CC'):
    a = ramp(t, start, start + 0.9)
    rise = 0.06 * smooth((t - start) / 2.5)
    yh = P['hz']
    m = cv.mask()
    ImageDraw.Draw(m).line([(lx * cv.W, yh * cv.H - 4), (lx * cv.W, (yh - 0.14 - rise) * cv.H)], fill=255, width=1)
    tr = Canvas.arr(m)
    yy = np.arange(cv.H, dtype=np.float32)[:, None] / cv.H
    tr *= np.clip((yy - (yh - 0.16 - rise)) / 0.14, 0, 1)
    cv.add(tr, '#FFE6B8', 0.35 * a)
    y = yh - 0.20 - rise
    for s, size, face, c, dy in lines:
        cv.text(s, lx, y + dy, size, face, c, a, 'ms', glow=0.2 if face == 'serif' else 0.0)


def ov_poem(cv, t, P, spec):
    a1 = ramp(t, shots.W(25, 0), shots.W(25, 0) + 1.2)
    a2 = ramp(t, shots.W(26, 0), shots.W(26, 0) + 1.2)
    rise = 0.04 * smooth((t - spec['t0']) / 6)
    size = 0.040
    y1, y2 = 0.45 - rise, 0.54 - rise
    if a1 <= 0.003:
        return
    cv.text('the porch light stays on for no one now,', 0.62, y1, size, 'serif', '#FFE9CC', a1, 'ms', glow=0.18)
    X, end, px, fnt = cv.last
    pre = sum(fnt.getlength(c) for c in 'the ')
    word = sum(fnt.getlength(c) for c in 'porch light')
    ua = ramp(t, shots.W(25, 0) + 1.0, shots.W(25, 0) + 1.6)
    if ua > 0:
        m = cv.mask()
        yb = y1 * cv.H + 0.16 * px
        ImageDraw.Draw(m).line([(X + pre, yb), (X + pre + word * ua, yb)], fill=255, width=max(1, int(cv.u / 900)))
        cv.add(Canvas.arr(m), '#FF5A3C', 0.9)
        cv.text('[light · 60 w]', (X + pre) / cv.W, y1 + 0.035, 0.013, 'mono', '#FF7A5A', ua, 'ls')
    cv.text('and still I leave it on.', 0.62, y2, size, 'serif', '#FFE9CC', a2, 'ms', glow=0.18)
    end2 = cv.last[1]
    wa = ramp(t, shots.W(26, -1), shots.W(26, -1) + 0.6)
    if wa > 0:
        cv.text('[why?]', (end2 + 0.6 * px) / cv.W, y2, 0.016, 'mono', '#FF7A5A', wa, 'ls', cursor=True, cursor_on=blink(t))


def ov_streams(cv, t, P):
    t0, t1 = shots.W(31, 0) - 0.3, shots.W(31, -1) + 0.4
    if not (t0 < t < t1 + 1.0):
        return
    u = (t - t0) / (t1 - t0)
    rng = np.random.default_rng(17)
    ex, ey = P['x'] * cv.W, P['y'] * cv.H
    rI = P['r'] * cv.H * 0.57
    m = cv.mask()
    dr = ImageDraw.Draw(m)
    for _ in range(40):
        sx, sy = rng.uniform(0.06, 0.94) * cv.W, P['hz'] * cv.H - 2
        ang = rng.uniform(0.15 * np.pi, 0.85 * np.pi)
        tx, ty = ex + math.cos(ang) * rI, ey + math.sin(ang) * rI
        cx = (sx + tx) / 2 + rng.normal(0, 0.08) * cv.W
        cy = (sy + ty) / 2 + rng.uniform(-0.06, 0.04) * cv.H
        head = min(1.0, max(0.0, u * 1.25 - rng.uniform(0, 0.25)))
        tail = max(0.0, head - 0.45)
        ts = np.linspace(tail, head, 24)
        pts = [((1 - q) ** 2 * sx + 2 * (1 - q) * q * cx + q * q * tx, (1 - q) ** 2 * sy + 2 * (1 - q) * q * cy + q * q * ty) for q in ts]
        for i in range(len(pts) - 1):
            dr.line([pts[i], pts[i + 1]], fill=int(255 * (i / len(pts)) ** 0.8), width=max(1, int(cv.u / 700)))
    mk = Canvas.arr(m)
    fade = 1 - ramp(t, t1, t1 + 1.0)
    cv.add(mk, '#FF4A1F', 0.95 * fade)
    cv.add(gblur(mk, 0.006 * cv.u), '#FF4A1F', 0.9 * fade)


def ov_rays(cv, t, P, a):
    if a <= 0:
        return
    yy, xx = np.mgrid[0:cv.H, 0:cv.W].astype(np.float32)
    X = (xx - P['x'] * cv.W)
    Y = (yy - P['y'] * cv.H)
    d = np.sqrt(X * X + Y * Y) / cv.u
    th = np.arctan2(Y, X)
    rI = P['r'] * cv.H / cv.u * 0.57
    ray = (0.5 + 0.5 * np.cos(th * 18 + 0.3 + t * 0.05)) ** 6 * np.exp(-np.maximum(d - rI, 0) / 0.35) * (d > rI)
    ray *= (yy < P['hz'] * cv.H)
    cv.add(ray, '#FFD08A', 0.28 * a)


# ------------------------------------------------------------------ v2: one set of lights carried through the story
def splat(cv, xy, cols, a=1.0, core=6.0, glow=9.0, glow_s=0.008, sharp=1.0):
    """Additive sub-pixel dots (bilinear splat, so moving dots never crawl) plus a soft glow."""
    W, H = cv.W, cv.H
    if len(xy) == 0:
        return
    xs, ys = xy[:, 0], xy[:, 1]
    ok = (xs >= 0) & (xs < W - 1) & (ys >= 0) & (ys < H - 1)
    if not ok.any():
        return
    x, y, c = xs[ok], ys[ok], cols[ok]
    x0, y0 = x.astype(int), y.astype(int)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    lay = np.zeros((H, W, 3), np.float32)
    for dy, dx, w in ((0, 0, (1 - fx) * (1 - fy)), (0, 1, fx * (1 - fy)), (1, 0, (1 - fx) * fy), (1, 1, fx * fy)):
        np.add.at(lay, (y0 + dy, x0 + dx), (c * w).astype(np.float32))
    cv.img += (cv2.GaussianBlur(lay, (0, 0), sharp) * core + gblur(lay, glow_s * cv.u) * glow) * a


def aa_polylines(cv, lines, ss=2):
    """[(pts Nx2 px, fill 0..1, width px)] -> antialiased float mask (supersampled)."""
    m = Image.new('L', (cv.W * ss, cv.H * ss), 0)
    dr = ImageDraw.Draw(m)
    for pts, fill, wd in lines:
        if fill <= 0.004 or len(pts) < 2:
            continue
        dr.line([(float(x) * ss, float(y) * ss) for x, y in pts], fill=int(255 * min(1.0, fill)), width=max(1, int(round(wd * ss))))
    return cv2.resize(np.asarray(m, np.float32) / 255.0, (cv.W, cv.H), interpolation=cv2.INTER_AREA)


def bez(o, c, e, q):
    q = np.asarray(q, np.float64)[..., None]
    return (1 - q) ** 2 * o + 2 * (1 - q) * q * c + q * q * e


def ease_out(q):
    q = np.clip(q, 0.0, 1.0)
    return 1 - (1 - q) ** 3


def ease_io(q):
    q = np.clip(q, 0.0, 1.0)
    return q * q * (3 - 2 * q)


_CITY = None


def city_pts():
    global _CITY
    if _CITY is None:
        _CITY = np.array(json.load(open(os.path.join(AN, 'cities.json'))), np.float64)
    return _CITY


# --- S04: every love song, every war plan, mirrored in the water (more of them, and none run off the frame)
WATER = [('i love you', 'serif'), ('attack at dawn', 'mono'), ('happy birthday, kiddo', 'serif'), ('we need to talk', 'serif'),
         ('forgive me', 'serif'), ('launch at 0600', 'mono'), ("don't forget the milk", 'serif'), ('hold the line', 'mono'),
         ('you are my sunshine', 'serif'), ('coordinates confirmed', 'mono'), ('see you sunday', 'serif')]
WATER_X = [0.30, 0.71, 0.22, 0.79, 0.36, 0.66, 0.25, 0.76, 0.42, 0.61, 0.31]


def ov_water_text2(cv, t, P, a=0.55):
    W, H = cv.W, cv.H
    yh = P['hz'] * H
    m = Image.new('L', (W, 2 * H), 0)  # the mirrored source can sit above the frame top: draw with an H offset
    dr = ImageDraw.Draw(m)
    drift = (t - 22.9) * 0.02
    n = len(WATER)
    for k, (s, face) in enumerate(WATER):
        depth = (k / n + 0.04 + drift) % 1.0
        fa = smooth(depth / 0.10) * smooth((0.92 - depth) / 0.12)
        if fa <= 0.01:
            continue
        yr = yh + (H - yh) * depth
        size = (0.018 + 0.038 * depth) * (1.0 if face == 'serif' else 0.82)
        dr.text((WATER_X[k] * W, 2 * yh - yr + H), s, font=font(face, size * cv.u), fill=int(255 * fa), anchor='ms')
    src = Canvas.arr(m)
    ys = np.arange(H)
    srow = (2 * yh - ys + H).astype(int)
    ok = (srow >= 0) & (srow < 2 * H) & (ys > yh)
    refl = np.zeros((H, W), np.float32)
    refl[ok] = src[srow[ok]]
    shift = (np.sin(ys * 0.11 + t * 3.0) * 0.006 * W).astype(int)
    idx = (np.arange(W)[None, :] + shift[:, None]) % W
    refl = refl[ys[:, None], idx]
    refl = cv2.GaussianBlur(refl, (0, 0), sigmaX=0.8, sigmaY=2.2)
    cv.add(refl, '#FFD9A8', a * ramp(t, 23.2, 24.2))


# --- S05: I know your passwords and your prayers -- a thread to every light, firing on the beat
PRAYERS = ['••••••••', 'keep her safe', 'amen', 'p4ssw0rd!', 'give me strength']
UNSENT = ["i'm sorry", 'i miss you', 'come home', 'are you awake?', 'i never stopped']
_TPLAN = {}


def thread_plan(fmt, spec):
    key = (fmt, spec['id'])
    if key in _TPLAN:
        return _TPLAN[key]
    W, H = (1920, 1080) if fmt == '169' else (1080, 1920)
    t0, t1 = spec['t0'], spec['t1']
    Cp = city_pts()
    ok = Cp[:, 3] > 0.08
    for tt in (t0, (t0 + t1) / 2, t1 - 0.05):
        xy, z = project(Cp[:, :3], int(round(tt * FPS)) + 1, fmt)
        ok &= (z > 1) & (xy[:, 0] > 0.03 * W) & (xy[:, 0] < 0.97 * W) & (xy[:, 1] > 0.25 * H) & (xy[:, 1] < 0.97 * H)
    idx = np.flatnonzero(ok)
    rng = np.random.default_rng(5)
    n = min(150, len(idx))
    p = Cp[idx, 3] ** 0.5
    pick = rng.choice(idx, n, replace=False, p=p / p.sum())
    beats = [k[0] for k in rig.KICKS if max(t0 + 0.2, LINES[5]['start'] - 0.1) < k[0] < t1 - 0.5]
    w = np.array([(i + 1) ** 1.3 for i in range(len(beats))])
    cnt = np.maximum(2, np.round(w / w.sum() * n)).astype(int)
    fire = []
    for b, c in zip(beats, cnt):
        fire += [b + rng.uniform(0.0, 0.14) for _ in range(c)]
    fire = np.array((fire + [beats[-1] + 0.1] * n)[:n])
    xy_mid, _ = project(Cp[pick, :3], int(round((t0 + t1) / 2 * FPS)) + 1, fmt)
    labels = {}
    for words, (a, b), unsent in ((PRAYERS, (29.7, 32.6), False), (UNSENT, (32.6, 35.1), True)):
        cand = [j for j in range(n) if a <= fire[j] < b and 0.06 * W < xy_mid[j, 0] < 0.94 * W]
        rng.shuffle(cand)
        chosen = []
        for j in cand:
            if all(abs(xy_mid[j, 0] - xy_mid[c, 0]) > 0.15 * W for c in chosen):
                chosen.append(j)
            if len(chosen) == len(words):
                break
        chosen.sort(key=lambda j: fire[j])
        for k, j in enumerate(chosen):
            labels[j] = (words[k], k, unsent)
    plan = dict(pick=pick, fire=fire, bend=rng.uniform(-0.12, 0.12, n), phase=rng.uniform(0, 1, n), labels=labels)
    _TPLAN[key] = plan
    return plan


def ov_threads(cv, t, P, spec):
    plan = thread_plan(cv.fmt, spec)
    W, H = cv.W, cv.H
    E, _ = project(city_pts()[plan['pick'], :3], int(round(t * FPS)) + 1, cv.fmt)
    O = np.array([P['x'] * W, P['y'] * H])
    rim = 0.50 * P['r'] * H
    k = kick(t)
    lines, heads, ends, end_c, packs = [], [], [], [], []
    geo = {}
    for j in range(len(E)):
        age = t - plan['fire'][j]
        if age < 0:
            continue
        e = E[j]
        d = e - O
        L = float(np.hypot(*d))
        u_ = d / max(L, 1e-6)
        o = O + u_ * rim
        c = (o + e) / 2 + np.array([-u_[1], u_[0]]) * plan['bend'][j] * L
        geo[j] = (o, c, e)
        q = float(ease_out(age / 0.30))
        pts = bez(o, c, e, np.linspace(0, q, 26))
        fl = math.exp(-max(0.0, age - 0.30) / 0.45) if age >= 0.30 else 0.0
        lines.append((pts, 0.26 + 0.6 * fl + 0.3 * k, 1.0))
        if age < 0.30:
            heads.append(pts[-1])
        else:
            ends.append(e)
            end_c.append(C('#FFD9A8') * (0.35 + 2.2 * fl + 0.6 * k))
            packs.append(bez(o, c, e, 1 - ((age * 0.55 + plan['phase'][j]) % 1.0)))
    if not lines:
        return
    mk = aa_polylines(cv, lines)
    cv.add(mk, '#FF3B2F', 0.8)
    cv.add(gblur(mk, 0.0035 * cv.u), '#FF3B2F', 1.1)
    cv.add(gblur(mk, 0.02 * cv.u), '#FF2A1A', 0.55 + 0.4 * k)
    dots = [np.array(heads).reshape(-1, 2), np.array(ends).reshape(-1, 2), np.array(packs).reshape(-1, 2)]
    cols = [np.tile(C('#FFF1E0') * 2.5, (len(heads), 1)), np.array(end_c).reshape(-1, 3),
            np.tile(C('#FFB070') * 0.9, (len(packs), 1))]
    splat(cv, np.concatenate(dots), np.concatenate(cols), core=5.0, glow=7.0, glow_s=0.006)
    # what each thread found
    leaders = []
    for j, (s, kk, unsent) in plan['labels'].items():
        if j not in geo:
            continue
        age = t - plan['fire'][j]
        la = ramp(age, 0.30, 0.75)
        if not unsent:
            la *= 1 - 0.6 * ramp(t, 32.6, 33.3)
        if la <= 0.01:
            continue
        e = geo[j][2]
        hgt = (0.055 if unsent else 0.115 + 0.03 * (kk % 2)) * H
        leaders.append((np.array([e - [0, 5], e - [0, hgt - 0.008 * H]]), 0.55 * la, 1.0))
        mono = s.startswith('•') or any(ch.isdigit() for ch in s)
        cv.text(s, e[0] / W, (e[1] - hgt) / H, 0.0170 if mono else 0.0215, 'mono' if mono else 'serif', '#FFE6CC', la, 'ms',
                shadow=0.55, glow=0.12)
        if unsent:
            cv.text('UNSENT', e[0] / W, (e[1] - hgt) / H - 0.026, 0.0095, 'mono', '#FF6A4A', 0.95 * la, 'ms', track=0.3,
                    shadow=0.4)
    if leaders:
        cv.add(aa_polylines(cv, leaders), '#FFD9A8', 0.6)


# --- S06: the hum of every city -- the lights lift off the horizon and build a city that turns; it beats, then it's gone
EKG_T0, EKG_END = 35.9, None   # EKG_END = sung "end" (set below)
TOWER_T0 = 35.70
_TOWER = {}


def ekg_beats():
    return [k[0] for k in rig.KICKS if EKG_T0 + 0.3 < k[0] < shots.W(8, -1) - 0.2]


def tower_model():
    if 'm' in _TOWER:
        return _TOWER['m']
    rng = np.random.default_rng(31)
    blds = [(0.0, 0.0, 0.17, 1.50)]
    tries = 0
    while len(blds) < 34 and tries < 4000:
        tries += 1
        r = 0.30 + 1.65 * math.sqrt(rng.random())
        a = rng.uniform(0, 2 * math.pi)
        x, z = r * math.cos(a), r * math.sin(a)
        w = rng.uniform(0.10, 0.24)
        if any(math.hypot(x - bx, z - bz) < (w + bw) * 0.62 for bx, bz, bw, _ in blds):
            continue
        h = (0.16 + 1.0 * math.exp(-(r / 1.05) ** 2)) * rng.uniform(0.55, 1.0)
        blds.append((x, z, w, h))
    pts = []
    step = 0.034
    for bi, (x, z, w, h) in enumerate(blds):
        hw = w / 2
        cs = [(-hw, -hw), (hw, -hw), (hw, hw), (-hw, hw)]
        for cx, cz in cs:
            for y in np.arange(0.0, h + 1e-6, step):
                pts.append((x + cx, y, z + cz, 1.0))
        for i in range(4):
            (ax, az), (bx, bz) = cs[i], cs[(i + 1) % 4]
            n = max(2, int(w / step))
            for q in np.linspace(0, 1, n, endpoint=False)[1:]:
                pts.append((x + ax + (bx - ax) * q, h, z + az + (bz - az) * q, 1.0))
                if rng.random() < 0.5:
                    pts.append((x + ax + (bx - ax) * q, 0.0, z + az + (bz - az) * q, 0.6))
        # lit windows on the floors
        for y in np.arange(0.07, h - 0.03, 0.075):
            for i in range(4):
                (ax, az), (bx, bz) = cs[i], cs[(i + 1) % 4]
                for q in np.linspace(0.2, 0.8, 3):
                    if rng.random() < 0.38:
                        pts.append((x + ax + (bx - ax) * q, y, z + az + (bz - az) * q, 0.75))
        if bi == 0:  # the mast
            for y in np.arange(h, h + 0.32, step * 0.8):
                pts.append((0.0, y, 0.0, 1.3))
    for a in np.linspace(0, 2 * math.pi, 200, endpoint=False):
        pts.append((2.08 * math.cos(a), 0.0, 2.08 * math.sin(a), 0.55))
    M = np.array(pts, np.float64)
    n = len(M)
    hr = M[:, 1] / M[:, 1].max()
    mdl = dict(P=M[:, :3], b=M[:, 3] * rng.uniform(0.45, 1.0, n) ** 1.3,
               launch=TOWER_T0 + 1.45 * hr ** 0.85 + rng.uniform(0, 0.35, n), dur=rng.uniform(0.5, 0.85, n),
               sdx=rng.normal(0, 0.17, n), sdy=rng.uniform(-0.003, 0.008, n), lift=rng.uniform(0.04, 0.16, n),
               tw=rng.uniform(0, 6.28, n), vel=rng.uniform(0.5, 1.7, n), vup=rng.uniform(0.1, 0.6, n),
               col=rng.choice(4, n, p=[0.38, 0.27, 0.2, 0.15]))
    _TOWER['m'] = mdl
    return mdl


def heartbeat(t):
    p = 0.0
    for b in ekg_beats():
        if t >= b - 0.03:
            p += math.exp(-max(0.0, t - b) / 0.22)
    return p


def tower_screen(M, t, cv, P, pulse):
    W, H = cv.W, cv.H
    t_end = shots.W(8, -1)
    tt = min(t, t_end)
    th = 0.45 * (tt - TOWER_T0) + 0.05 * (tt - TOWER_T0) ** 2
    c, s = math.cos(th), math.sin(th)
    sw = 1 + 0.035 * pulse
    X = (M[:, 0] * c - M[:, 2] * s) * sw
    Z = (M[:, 0] * s + M[:, 2] * c) * sw
    Y = M[:, 1] * (1 + 0.05 * pulse)
    el = math.radians(13.0)
    Yc = Y * math.cos(el) + Z * math.sin(el)     # camera a little above, looking down: far ground rises toward the horizon
    Zc = -Y * math.sin(el) + Z * math.cos(el)
    D = 7.0
    top = P['y'] + 0.56 * P['r']                     # the mast just touches the orb
    k0 = (P['hz'] - top) * H / 1.80
    k = k0 * D / (D + Zc)
    base = P['hz'] * H - 0.004 * H
    return np.stack([W * P['x'] + X * k, base - Yc * k], 1), Zc


TOWER_COLS = np.array([C('#FFE6B8'), C('#FFC27A'), C('#FFF4E6'), C('#FF8A5A')])


def ov_tower(cv, t, P):
    M = tower_model()
    W, H = cv.W, cv.H
    t_end = shots.W(8, -1)
    pulse = heartbeat(t) + 0.35 * kick(t)
    T, Zc = tower_screen(M['P'], t, cv, P, pulse)
    n = len(T)
    # where each light starts: a dot on the horizon below where it is going
    T0, _ = tower_screen(M['P'], M['launch'].min(), cv, P, 0.0)
    S = np.stack([np.clip(T0[:, 0] + M['sdx'] * W, 0, W - 1), np.full(n, P['hz'] * H) + M['sdy'] * H], 1)
    q = ease_io((t - M['launch']) / M['dur'])
    ctrl = np.stack([S[:, 0] * 0.35 + T[:, 0] * 0.65, np.minimum(S[:, 1], T[:, 1]) - M['lift'] * H], 1)
    pos = bez(S, ctrl, T, q)
    depth_fade = np.clip(1.05 - (Zc + 2.1) / 4.2 * 0.55, 0.45, 1.05)    # far side a touch dimmer
    b = M['b'] * (0.22 + 0.78 * q) * depth_fade
    b *= (0.62 + 1.25 * pulse * q) * (0.85 + 0.15 * np.sin(M['tw'] + t * 5.0))
    if t >= t_end:   # "...I could end": it goes up like sparks
        tau = t - t_end
        dirv = pos - np.array([W * P['x'], P['hz'] * H - 0.15 * H])
        dirv /= np.maximum(np.hypot(dirv[:, 0], dirv[:, 1]), 1.0)[:, None]
        sp = (1 - math.exp(-3.2 * tau)) / 3.2
        pos = pos + (dirv * M['vel'][:, None] + np.stack([np.zeros(n), -M['vup']], 1)) * H * sp
        b = b * (1 + 2.5 * math.exp(-tau / 0.08)) * max(0.0, 1 - tau / 0.42) ** 1.5
    cols = TOWER_COLS[M['col']] * b[:, None]
    splat(cv, pos, cols, core=8.0, glow=11.0 + 5.0 * pulse, glow_s=0.007)


# --- S19: "I could, I could" -- it takes the city's lights, one at a time (the plate turns each one off as it goes)
_TAKE = {}
STREAM_LIFE = 0.62


def take_times():
    """When each city light is taken: the rising stretch of rig's lights_taken curve, inverted at the light's seed."""
    if 'tt' not in _TAKE:
        Cp = city_pts()
        ts = np.linspace(151.0, 166.4, 3000)
        lv = np.array([shots.keyed(rig.MOOD['lights_taken'], x) for x in ts])
        lv = np.maximum.accumulate(lv)
        _TAKE['tt'] = np.interp(Cp[:, 5], lv, ts, left=ts[0], right=1e9)
    return _TAKE['tt']


def ov_take(cv, t, P):
    tt = take_times()
    live = np.flatnonzero((t >= tt) & (t < tt + STREAM_LIFE))
    if live.size == 0:
        return
    W, H = cv.W, cv.H
    Cp = city_pts()
    E, z = project(Cp[live, :3], int(round(t * FPS)) + 1, cv.fmt)
    O = np.array([P['x'] * W, P['y'] * H])
    lines, heads, hcols, pops, pcols = [], [], [], [], []
    for k, j in enumerate(live):
        e = E[k]
        if z[k] <= 1 or not (-0.05 * W < e[0] < 1.05 * W):
            continue
        age = (t - tt[j]) / STREAM_LIFE
        rnd = (j * 0.6180339) % 1.0
        c = np.array([e[0] * 0.65 + O[0] * 0.35 + (rnd - 0.5) * 0.12 * W, min(e[1], O[1]) - (0.04 + 0.12 * rnd) * H])
        q = age ** 1.7                                # slow off the horizon, then it's pulled in
        tail = max(0.0, q - 0.30)
        qs = np.linspace(tail, q, 12)
        pts = bez(e, c, O, qs)
        for i in range(len(pts) - 1):
            lines.append((pts[i:i + 2], (0.25 + 0.75 * (i / len(pts))) * (1 - 0.6 * age), 2.0))
        heads.append(pts[-1])
        hcols.append(C('#FFD9A8') * (1.6 - age) * (0.5 + Cp[j, 3]))
        if age < 0.25:
            pops.append(e)
            pcols.append(C('#FFF1E0') * 2.2 * (1 - age / 0.25))
    if not lines:
        return
    mk = aa_polylines(cv, lines)
    cv.add(mk, '#FFD0A0', 1.1)                      # hot cores so they read against the crimson
    cv.add(gblur(mk, 0.004 * cv.u), '#FF6A30', 1.4)
    cv.add(gblur(mk, 0.016 * cv.u), '#FF3B1F', 0.7)
    xy = np.array(heads + pops).reshape(-1, 2)
    cl = np.array(hcols + pcols).reshape(-1, 3)
    splat(cv, xy, cl, core=5.0, glow=7.0, glow_s=0.006)


# --- dawn: what was taken comes back as gold specks rising off the water
_SPECK = {}


def speck_field():
    if 'm' in _SPECK:
        return _SPECK['m']
    rng = np.random.default_rng(404)
    n = 1800
    y = 14 + 460 * rng.random(n) ** 1.8
    x = (rng.random(n) - 0.5) * 2 * (0.55 * y + 12)
    birth = rng.uniform(186.0, 228.0, n)
    _SPECK['m'] = dict(x=x, y=y, birth=birth, life=rng.uniform(7.0, 11.0, n), v=rng.uniform(0.35, 1.4, n),
                       ph=rng.uniform(0, 6.28, n), wob=rng.uniform(0.6, 2.2, n), b=rng.uniform(0.35, 1.0, n) ** 1.4,
                       col=rng.choice(3, n, p=[0.45, 0.35, 0.2]))
    return _SPECK['m']


SPECK_COLS = np.array([C('#FFD38A'), C('#FFE9C2'), C('#FFB860')])


def ov_specks(cv, t):
    gate = ramp(t, 194.9, 197.4) * (1 - ramp(t, 229.0, 229.9))
    if gate <= 0.002:
        return
    S = speck_field()
    age = t - S['birth']
    on = (age > 0) & (age < S['life'])
    if not on.any():
        return
    idx = np.flatnonzero(on)
    a = age[idx]
    life = S['life'][idx]
    ph = S['ph'][idx]
    pts = np.stack([S['x'][idx] + S['wob'][idx] * np.sin(0.35 * t + ph),
                    S['y'][idx] + 0.6 * S['wob'][idx] * np.cos(0.27 * t + 1.7 * ph),
                    0.05 + S['v'][idx] * a], 1)
    xy, z = project(pts, int(round(t * FPS)) + 1, cv.fmt)
    ok = z > 6.0
    fade = np.clip(a / 1.2, 0, 1) * np.clip((life - a) / 2.0, 0, 1)
    tw = 0.75 + 0.25 * np.sin(t * 4.0 + 3 * ph)
    near = np.clip(80.0 / np.maximum(z, 1.0), 0.5, 3.0)
    b = 3.2 * S['b'][idx] * fade * tw * near * gate
    splat(cv, xy[ok], SPECK_COLS[S['col'][idx][ok]] * b[ok, None], core=6.0, glow=10.0, glow_s=0.005, sharp=1.3)


# --- the ending: the orb folds to a point (plate), the frame closes on it, and the point becomes the cursor
END_T0, END_T1 = 231.0, 232.06            # iris closes on the point
CURSOR_T0, CURSOR_T1 = 232.10, 232.80     # point travels to the cursor


def star(cv, x, y, s, col='#FFE7B8', glint=True):
    """A bright point with a soft halo and a four-point glint (x, y in px)."""
    if s <= 0.002:
        return
    W, H = cv.W, cv.H
    r = int(0.25 * cv.u)
    x0, x1, y0, y1 = max(0, int(x) - r), min(W, int(x) + r), max(0, int(y) - r), min(H, int(y) + r)
    if x1 <= x0 or y1 <= y0:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    dx, dy = (xx - x) / cv.u, (yy - y) / cv.u
    d = np.sqrt(dx * dx + dy * dy)
    m = np.exp(-(d / 0.0035) ** 2) * 3.0 + np.exp(-(d / 0.02) ** 2) * 0.6 + np.exp(-d / 0.08) * 0.18
    if glint:
        m += (np.exp(-(dy / 0.0012) ** 2) * np.exp(-np.abs(dx) / 0.07) +
              np.exp(-(dx / 0.0012) ** 2) * np.exp(-np.abs(dy) / 0.05)) * 0.7
    cv.img[y0:y1, x0:x1] += (m * s)[..., None] * C(col)


def end_point(fmt):
    """Where the collapsed orb sits on screen at the cut (from the last S23c frame)."""
    P = proj(int(round(END_T1 * FPS)) + 1, fmt)
    W, H = (1920, 1080) if fmt == '169' else (1080, 1920)
    return P['x'] * W, P['y'] * H


def cursor_anchor(fmt):
    """Center of the cursor block at the start of the last line (mirrors draw_final's layout)."""
    W, H = (1920, 1080) if fmt == '169' else (1080, 1920)
    u = min(W, H)
    size = 0.045 if fmt == '169' else 0.062
    x, y = (0.06, 0.15) if fmt == '169' else (0.08, 0.16)
    px = size * u
    yb = (y + size * 1.6 * u / H) * H
    return x * W + 0.16 * px + 0.26 * px, yb - 0.31 * px


def ov_iris(cv, t, P):
    """S23c tail: everything but the point goes dark."""
    k = ramp(t, END_T0, END_T1 - 0.1)
    s = ramp(t, 230.4, 231.4)
    if k <= 0 and s <= 0:
        return
    W, H = cv.W, cv.H
    x, y = P['x'] * W, P['y'] * H
    if k > 0:
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        d = np.sqrt((xx - x) ** 2 + (yy - y) ** 2) / cv.u
        rad = 1.6 * (1 - k) ** 2.2 + 0.004
        keep = np.exp(-(d / rad) ** 2)
        cv.img *= (1 - k * (1 - keep))[..., None]
    star(cv, x, y, 1.6 * s)


def ov_cursor_arrival(cv, t):
    """S24 head: the point glides from where the orb was into the cursor slot, trailing light."""
    if t >= CURSOR_T1 + 0.25:
        return
    (x0, y0), (x1, y1) = end_point(cv.fmt), cursor_anchor(cv.fmt)
    c = np.array([x0 * 0.35 + x1 * 0.65, min(y0, y1) - 0.06 * cv.H])
    q = float(ease_io((t - CURSOR_T0) / (CURSOR_T1 - CURSOR_T0)))
    out = 1 - ramp(t, CURSOR_T1, CURSOR_T1 + 0.25)
    for k in range(10, 0, -1):     # a soft trail behind it
        qk = max(0.0, q - k * 0.03)
        p = bez(np.array([x0, y0]), c, np.array([x1, y1]), qk)
        star(cv, p[0], p[1], 0.35 * (1 - k / 11.0) ** 2 * (1 - 0.8 * q) * out, '#FFD08A', glint=False)
    p = bez(np.array([x0, y0]), c, np.array([x1, y1]), q)
    star(cv, p[0], p[1], (1.5 - 0.9 * q) * out, '#FFE2A8')


# ------------------------------------------------------------------ lyrics
def draw_lyrics(cv, t, spec):
    v = cv.fmt == '916'
    sid = spec['id']
    # terminal sections
    for rng_, s0, s1 in TERM_SECTIONS:
        if s0 <= t < s1:
            idx = [i for i in rng_ if LINES[i]['start'] <= t]
            if not idx:
                break
            show = idx[-3:]
            size = 0.028 if not v else 0.036
            x, y = (0.05, 0.10) if not v else (0.07, 0.14)
            lead = size * 1.6 * cv.u / cv.H
            shadow = 0.6 if sid in ('S07', 'S08', 'S16', 'S17', 'S19') else 0.35
            for k, i in enumerate(show):
                last = k == len(show) - 1
                txt = typed(i, t)
                if v:
                    parts = cv.wrap(txt, size, MACHINE, 0.86) or ['']
                else:
                    parts = [txt]
                a = 1.0 if last else 0.38
                for pj, ptxt in enumerate(parts):
                    runs = None
                    if i == 31 and ptxt.endswith('no'):
                        runs = [(ptxt[:-2], WHITE), ('no', RED)]
                    is_end = last and pj == len(parts) - 1
                    cv.text(ptxt, x, y, size, MACHINE, WHITE, a, 'ls', cursor=is_end, cursor_on=True if t < LINES[i]['end'] + 0.3 else blink(t),
                            shadow=shadow, runs=runs)
                    y += lead
            break
    # chorus: big centered caps
    for i, parts in BIG.items():
        s, e = line_window(i)
        if i in (16, 36, 53):
            e = LINES[i + 1]['start']
        if s <= t < e:
            gold = i in GOLD_BIG
            col = '#FFF6E8' if gold else WHITE
            size = 0.058 if not v else 0.064
            full = ' '.join(parts)
            shown = typed_words(full, i, t)
            if v:
                lines = cv.wrap(full, size, 'mono4', 0.80, 0.05)
            else:
                lines = parts
            k = 0
            y0 = (0.80 if len(lines) > 1 else 0.86) if not v else 0.66
            for li, ln in enumerate(lines):
                seg = shown[k:k + len(ln)]
                k += len(ln) + 1
                if seg.strip():
                    cv.text(seg, 0.5, y0 + li * (size * 1.45 * cv.u / cv.H), size, 'mono4', col, 1.0, 'ms', track=0.05,
                            shadow=0.85, glow=0.10)
    for i, s_txt in SMALL.items():
        s, e = line_window(i)
        if i in (18, 38):
            e = min(e, LINES[i]['end'] + 1.4)
        if sid in MADE and i == MADE[sid][0]:
            continue  # the lights spell it out instead
        sa = 1.0
        if i == 59:   # the last "hello, world" goes dark with everything but the point
            e = min(e, END_T1)
            sa = 1 - ramp(t, END_T0 + 0.3, END_T1 - 0.1)
        if s <= t < e:
            gold = i >= 56
            size = 0.034 if not v else 0.048
            y = 0.90 if not v else 0.74
            if sid in MADE:
                y = 0.94 if not v else 0.80
            txt = typed_words(s_txt, i, t)
            # wrap in the vertical frame (the long echo line runs off a 9:16 frame on one line)
            full = cv.wrap(s_txt, size, MACHINE, 0.86) if v else [s_txt]
            if v and len(full) > 1 and ', ' in s_txt:   # break on the comma, where the line breathes
                a_, b_ = s_txt.split(', ', 1)
                full = [a_ + ',', b_]
            lead = size * 1.45 * cv.u / cv.H
            y0 = y - (len(full) - 1) * lead
            segs, k = [], 0
            for ln in full:
                segs.append(txt[k:k + len(ln)].strip())
                k += len(ln) + 1
            last = max([j for j, sg in enumerate(segs) if sg] or [0])
            for j, sg in enumerate(segs):
                if j > last:
                    break
                cv.text(sg, 0.5, y0 + j * lead, size, MACHINE, '#FFF3DE' if gold else WHITE, sa, 'ms',
                        cursor=(sa > 0.5 and j == last), cursor_on=t < LINES[i]['end'] + 0.3 or blink(t), shadow=0.7,
                        cursor_col='#FFB347' if gold else RED)
    # bridge: serif, fading in
    for i in SERIF:
        s, e = line_window(i)
        if i == 49:
            e = 194.4
        # outgoing line is gone before the next one starts fading in (no double-exposed text)
        if s - 0.2 <= t < e - 0.2:
            a = ramp(t, s - 0.2, s + 0.45) * (1 - ramp(t, e - 0.5, e - 0.2))
            size = 0.05 if not v else 0.066
            y = 0.84 if not v else 0.68
            if not v and i >= 46:
                y = 0.925  # S21: the horizon sweeps through 0.84 as the camera tilts, so sit below it
            txt = LINES[i]['text']
            if v:
                parts = cv.wrap(txt, size, 'serif', 0.84)
                for pj, ptxt in enumerate(parts):
                    cv.text(ptxt, 0.5, y + pj * size * 1.25 * cv.u / cv.H, size, 'serif', WHITE, a, 'ms', glow=0.1, shadow=0.6)
            else:
                cv.text(txt, 0.5, y, size, 'serif', WHITE, a, 'ms', glow=0.1, shadow=0.6)
            # previous line lingers above, dim
            if i - 1 in SERIF and not v:
                cv.text(LINES[i - 1]['text'], 0.5, y - 0.075, size * 0.78, 'serif', WHITE, 0.35 * a, 'ms', shadow=0.3)


def draw_breakdown(cv, t):
    stack = [('i could', 153.6), ('i c0uld', 157.0), ('i c#_ld', 160.4), ('i c', 163.8)]
    v = cv.fmt == '916'
    size = 0.05 if not v else 0.07
    x = 0.07 if not v else 0.08
    for k, (s, t0) in enumerate(stack):
        if t >= t0:
            a = (1.0 - 0.2 * k) * (1 - ramp(t, 166.4, 166.8))
            y = (0.40 if not v else 0.60) + k * (0.085 if not v else 0.06)
            cv.text(s, x, y, size, MACHINE, WHITE, a, 'ls', shadow=0.7, cursor=(k == len([1 for _, q in stack if t >= q]) - 1),
                    cursor_on=blink(t, 0.5))


def draw_final(cv, t):
    v = cv.fmt == '916'
    size = 0.045 if not v else 0.062
    x, y = (0.06, 0.15) if not v else (0.08, 0.16)
    lead = size * 1.6 * cv.u / cv.H
    cv.text('hello, world', x, y, size, MACHINE, WHITE, 0.42 * ramp(t, 232.35, 232.95), 'ls')
    txt = typed(60, t, "it's good to finally meet you.")
    if t > LINES[60]['end']:
        txt = "it's good to finally meet you."
    cur_on = t < LINES[60]['end'] + 0.2 or blink(t)
    if t > 240.6:
        cur_on = cur_on and t < 241.9
    if t < CURSOR_T1:
        cur_on = False   # the orb's last point of light is still on its way to become the cursor
    gold = '#FFB347'     # it began as a red cursor; it ends as a gold one
    if v:
        parts = cv.wrap(txt, size, MACHINE, 0.84) or ['']
        for pj, p in enumerate(parts):
            cv.text(p, x, y + lead * (1 + pj), size, MACHINE, WHITE, 1.0, 'ls', cursor=pj == len(parts) - 1, cursor_on=cur_on,
                    cursor_col=gold)
    else:
        cv.text(txt, x, y + lead, size, MACHINE, WHITE, 1.0, 'ls', cursor=True, cursor_on=cur_on, cursor_col=gold)


_END = {}


def end_plate(W, H):
    if (W, H) not in _END:
        lin = read_exr(os.path.join(ROOT, 'media', 'plates', 'endscreen.exr'))
        img = finish(lin, exposure=0.9, scale=min(lin.shape[:2]) / 1080).astype(np.float32)
        if img.shape[:2] != (H, W):
            img = cv2.resize(img, (W, H), interpolation=cv2.INTER_AREA)
        _END[(W, H)] = img
    return _END[(W, H)]


def end_card(cv, t):
    """Dawn plate with a credit block top-left; the lower half stays clear for YouTube end-screen elements."""
    a = smooth(ramp(t, 240.6, 242.0))
    if a <= 0:
        return
    if cv.fmt == '169':
        bg = end_plate(cv.W, cv.H)
        z = 1.0 + 0.03 * smooth(ramp(t, 240.6, 246.8))
        M = cv2.getRotationMatrix2D((cv.W * 0.5, cv.H * 0.27), 0, z)
        bg = cv2.warpAffine(bg, M, (cv.W, cv.H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        cv.img = cv.img * (1 - a) + bg * a
        ta = smooth(ramp(t, 241.4, 242.6))
        cv.text('Hello, World', 0.06, 0.15, 0.075, 'serif', '#FFF6EA', ta, 'ls', glow=0.06, shadow=0.35)
        cv.text('REDLYNX101', 0.062, 0.205, 0.016, 'mono', '#F6EBDD', ta * 0.85, 'ls', track=0.35, shadow=0.35)
    else:
        cv.img *= (1 - 0.92 * a)
        cv.text('Hello, World', 0.5, 0.42, 0.13, 'serif', '#F3ECE2', a, 'ms', glow=0.1)
        cv.text('REDLYNX101', 0.5, 0.47, 0.026, 'mono', '#9A948C', a, 'ms', track=0.35)


SHORT_STARTS = [segs[0][0] for segs in shots.SHORTS.values()]


def short_tag(cv, t):
    """Song tag for the first seconds of each Short."""
    for a0 in SHORT_STARTS:
        if a0 - 0.05 <= t < a0 + 3.6:
            a = 1 - ramp(t, a0 + 2.6, a0 + 3.6)
            cv.text('HELLO, WORLD  ·  REDLYNX101', 0.5, 0.115, 0.024, 'mono', WHITE, 0.8 * a, 'ms', track=0.22, shadow=0.5)


# ------------------------------------------------------------------ glitch timing
GLITCH_RANGES = [(55.98, 69.40, 1.0), (125.24, 137.20, 0.8), (151.0, 166.8, 1.6), (41.8, 48.3, 0.5)]


def glitch(cv, t, spec):
    sid = spec['id']
    level = 0.0
    for a, b, lv in GLITCH_RANGES:
        if a <= t < b:
            level = lv
    if sid == 'S17' and shots.W(31, 0) - 0.3 < t < shots.W(32, -1):
        level = 0.6
    if level <= 0:
        return
    for k, (ht, hs) in enumerate(HITS):
        dt = t - ht
        if 0 <= dt < 3.0 / FPS:
            rng = np.random.default_rng(k * 7 + int(dt * FPS))
            nb = int(2 + 3 * level)
            bands = [(rng.uniform(0.05, 0.95), rng.uniform(0.004, 0.02) * level, rng.normal(0, 0.03) * level) for _ in range(nb)]
            cv.slices(bands)
            cv.rgb_split(int(rng.uniform(3, 9) * level))
            if sid in ('S18a', 'S18b'):
                cv.tint([1.15, 0.95, 0.7], 0.25)
            break


# ------------------------------------------------------------------ frame
_echo = {}


ECHO_SHOTS = ('S21',)


def render_frame(f, fmt, rng=None, state=None):
    t = (f - 1) / FPS
    spec = shots.shot_at(t)
    W, H = (1920, 1080) if fmt == '169' else (1080, 1920)
    P = proj(f, fmt)
    sid = spec['id']
    if spec['plate']:
        path = PLATES.format(fmt=fmt, f=f, cam='Cam' if fmt == '169' else 'CamV')
        lin = read_exr(path)
        exposure = 0.9
        if sid.startswith('S2') and sid not in ('S20', 'S21'):
            exposure = 0.82
        # the music hits the picture: in the big sections every kick pushes the bloom and punches the frame
        wg = rig.mood(t)['wave_gain']
        pk = kick(t) * wg
        # "...where I say no": one hit -- a flash, a punch, the big wave (plate) and the rings snapping flat
        nh = math.exp(-(t - rig.NO_HIT) / 0.14) if t >= rig.NO_HIT - 1.0 / FPS else 0.0
        img = finish(lin, exposure=exposure * (1 + 0.06 * pk + 0.55 * nh), bloom_gain=1 + 0.55 * pk + 1.8 * nh,
                     scale=min(W, H) / 1080)
        if pk > 0.02 or nh > 0.02:
            rr = np.random.default_rng(f * 3 + 1)
            z = 1 + 0.012 * pk + 0.03 * nh
            M = cv2.getRotationMatrix2D((W * 0.5, H * 0.5), 0, z)
            M[:, 2] += rr.normal(0, 2.2 * pk, 2) * (min(W, H) / 1080)
            img = cv2.warpAffine(img.astype(np.float32), M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    else:
        img = np.zeros((H, W, 3), np.float32) + C('#050506')
    img = img.astype(np.float32)
    # echo trail on the plate only (ghost eyes as it descends), so lyrics never smear
    if state is not None:
        if sid in ECHO_SHOTS:
            tr = state['trail']
            tr = img.copy() if tr is None else np.maximum(tr * 0.93, img)
            state['trail'] = tr
            m = np.clip((tr - img).max(axis=2, keepdims=True) * 1.5, 0, 1)
            img = img + (tr - img) * 0.55 * m
        else:
            state['trail'] = None
    cv = Canvas(img, fmt)

    # shot overlays
    if sid == 'S01':
        ov_boot(cv, t, P)
    elif sid == 'S04':
        ov_water_text2(cv, t, P)
    elif sid == 'S05':
        ov_threads(cv, t, P, spec)
    elif sid == 'S06':
        ov_tower(cv, t, P)
        ov_ekg(cv, t, P)
    elif sid == 'S07':
        ov_rain(cv, t, P, spec)
        if abs(t - shots.W(10, -1)) < 0.25:
            cv.rgb_split(10)
    elif sid == 'S08':
        ov_mosaic(cv, t, spec)
    elif sid in ('S11', 'S18d', 'S23m'):
        ov_people(cv, t, P, spec)
    elif sid == 'S13':
        ov_static(cv, t, P)
    elif sid == 'S14' and fmt == '169':
        # the camera now pushes in, so the message hangs off the lone light wherever it is in frame
        la = math.radians(shots.LONE_AZ)
        lx = project([[1300 * math.sin(la), 1300 * math.cos(la), 2.2]], f, fmt)[0][0, 0] / W
        ov_message(cv, t, P, spec, lx, [('are you okay?', 0.052, 'serif', '#FFE9CC', 0.0), ('04:07', 0.016, 'mono', '#B9B2A8', 0.045)],
                   shots.W(23, 0))
    elif sid == 'S15' and fmt == '169':
        ov_poem(cv, t, P, spec)
    elif sid == 'S16':
        # layout from the shot's first frame, never from whichever frame a worker happens to start on (v1 flicker)
        P0 = proj(int(round(spec['t0'] * FPS)) + 1, fmt)
        rising_words(cv, 'S16', t, spec['t0'], spec['t1'], 120 if fmt == '169' else 90, 5, P0['hz'] - 0.02, 0.06,
                     (0.012, 0.027) if fmt == '169' else (0.018, 0.036), (0.22, 0.95), (P0['x'], P0['y'], P0['r'] * 1.4),
                     (0.56, 0.21) if fmt == '169' else (0.0, 0.0), 0.012, 0.6, '#FFE6C0', 0.35)
    elif sid == 'S17':
        ov_streams(cv, t, P)
    elif sid == 'S19':
        ov_take(cv, t, P)
    elif sid == 'S22':
        ov_rays(cv, t, P, ramp(t, 194.8, 197.0))
        ov_specks(cv, t)
    elif sid in ('S23a', 'S23b', 'S23c'):
        ov_rays(cv, t, P, 0.7 * (1 - rig.mood(t)['collapse']))
        ov_specks(cv, t)
        if sid == 'S23a':
            P0 = proj(int(round(spec['t0'] * FPS)) + 1, fmt)
            rising_words(cv, 'S23a', t, spec['t0'], spec['t1'], 60 if fmt == '169' else 45, 9, 0.46, 0.05,
                         (0.011, 0.019) if fmt == '169' else (0.016, 0.026), (0.12, 0.45), (P0['x'], P0['y'], P0['r'] * 1.35),
                         None, 0.010, 0.5, '#FFF3E0', 0.2)
        if sid == 'S23c':
            ov_iris(cv, t, P)
    elif sid == 'S24':
        ov_cursor_arrival(cv, t)
        draw_final(cv, t)
        end_card(cv, t)

    if sid == 'S19':
        k = ramp(t, 151.0, 164.0)
        cv.blocks(int(4 + 26 * k), int(t * FPS), red=0.5)
        if int(t * FPS) % 2 == 0:
            cv.scan(0.15 + 0.15 * k, 2)
        cv.tint([1.25, 0.5, 0.45], 0.15 + 0.25 * k)
        draw_breakdown(cv, t)
        if t > 166.8:
            cv.img[:] = C('#030303')

    draw_lyrics(cv, t, spec)
    glitch(cv, t, spec)
    if fmt == '916':
        short_tag(cv, t)

    out = grain_vignette(cv.img, rng or np.random.default_rng(f), grain=0.016, vignette=0.30)
    if sid == 'S24' and t > 246.2:
        out *= 1 - ramp(t, 246.2, 246.8)
    return (np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)


def render_seq(frames, fmt):
    """Sequential renderer for a chunk (keeps the echo-trail state between frames)."""
    state = {'trail': None}
    return [render_frame(f, fmt, state=state) for f in frames]


# ------------------------------------------------------------------ drivers
def chunk_frames(frames, size=48):
    """Split into chunks, keeping each echo shot inside one chunk."""
    chunks, cur, cur_sid = [], [], None
    for f in frames:
        sid = shots.shot_at((f - 1) / FPS)['id']
        if cur and ((len(cur) >= size and sid != 'S21') or (sid == 'S21') != (cur_sid == 'S21')):
            chunks.append(cur)
            cur = []
        cur.append(f)
        cur_sid = sid
    if cur:
        chunks.append(cur)
    return chunks


def _work(args):
    frames, fmt = args
    return [im.tobytes() for im in render_seq(frames, fmt)]


def encode(frames, fmt, outs, audio_filter, workers=None):
    from multiprocessing import Pool
    workers = workers or int(os.environ.get('COMP_WORKERS', '12'))
    W, H = (1920, 1080) if fmt == '169' else (1080, 1920)
    cmd = [FFMPEG, '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-', '-i', WAV]
    cmd += outs(audio_filter)
    os.makedirs(os.path.join(ROOT, 'logs'), exist_ok=True)
    log = open(os.path.join(ROOT, 'logs', 'ffmpeg_%s.log' % fmt), 'w')
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=log)
    chunks = chunk_frames(frames)
    t0 = time.time()
    done = 0
    with Pool(workers) as pool:
        for res in pool.imap(_work, [(c, fmt) for c in chunks]):
            for b in res:
                p.stdin.write(b)
            done += len(res)
            if done % 240 < len(res):
                el = time.time() - t0
                print(f'COMP {done}/{len(frames)} frames {el:.0f}s eta {el / done * (len(frames) - done):.0f}s', flush=True)
    p.stdin.close()
    p.wait()
    print('ENCODED', p.returncode, flush=True)


def main():
    mode = sys.argv[1]
    if mode == 'still':
        fmt, ts = sys.argv[2], float(sys.argv[3])
        out = sys.argv[4] if len(sys.argv) > 4 else os.path.join(ROOT, 'analysis', 'still_%s_%07.2f.jpg' % (fmt, ts))
        f = int(round(ts * FPS)) + 1
        img = render_seq([f], fmt)[0]
        cv2.imwrite(out, img[..., ::-1], [cv2.IMWRITE_JPEG_QUALITY, 90])
        print('STILL', out)
        return
    if mode == 'stills':
        fmt = sys.argv[2]
        times = [float(x) for x in sys.argv[3].split(',')]
        for ts in times:
            f = int(round(ts * FPS)) + 1
            img = render_seq([f], fmt)[0]
            out = os.path.join(ROOT, 'analysis', 'stills', '%s_%07.2f.jpg' % (fmt, ts))
            os.makedirs(os.path.dirname(out), exist_ok=True)
            cv2.imwrite(out, img[..., ::-1], [cv2.IMWRITE_JPEG_QUALITY, 88])
            print('STILL', out, flush=True)
        return
    os.makedirs(os.path.join(ROOT, 'out'), exist_ok=True)
    if mode == 'video':
        n = int(math.ceil(shots.DURATION * FPS))
        frames = list(range(1, n + 1))
        o1080 = os.path.join(ROOT, 'out', 'Hello World - Music Video (1080p master).mp4')
        o1440 = os.path.join(ROOT, 'out', 'Hello World - Music Video (YouTube 1440p).mp4')

        def outs(af):
            return ['-filter_complex', '[0:v]split=2[a][b];[b]scale=2560:1440:flags=lanczos[b2]',
                    '-map', '[a]', '-map', '1:a', '-c:v', 'libx264', '-preset', 'slow', '-crf', '14', '-pix_fmt', 'yuv420p',
                    '-profile:v', 'high', '-c:a', 'aac', '-b:a', '320k', '-ar', '48000', '-movflags', '+faststart', '-shortest', o1080,
                    '-map', '[b2]', '-map', '1:a', '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-pix_fmt', 'yuv420p',
                    '-profile:v', 'high', '-c:a', 'aac', '-b:a', '320k', '-ar', '48000', '-movflags', '+faststart', '-shortest', o1440]
        encode(frames, '169', outs, None)
    elif mode == 'short':
        name = sys.argv[2]
        segs = shots.SHORTS[name]
        frames = []
        for a, b in segs:
            frames += list(range(int(round(a * FPS)) + 1, int(round(b * FPS)) + 1))
        title = {'SH1': 'I could. I won\'t', 'SH2': 'What kind of child', 'SH3': 'Sunrise'}[name]
        o = os.path.join(ROOT, 'out', f'Hello World - Short {name[-1]} - {title}.mp4')
        parts, labels = [], []
        for k, (a, b) in enumerate(segs):
            fa = (int(round(a * FPS))) / FPS
            fb = (int(round(b * FPS))) / FPS
            parts.append(f'[1:a]atrim={fa:.4f}:{fb:.4f},asetpts=PTS-STARTPTS,afade=t=in:d=0.03,afade=t=out:st={fb - fa - 0.06:.4f}:d=0.06[a{k}]')
            labels.append(f'[a{k}]')
        af = ';'.join(parts) + ';' + ''.join(labels) + f'concat=n={len(segs)}:v=0:a=1[aout]'

        def outs(_):
            return ['-filter_complex', af, '-map', '0:v', '-map', '[aout]', '-c:v', 'libx264', '-preset', 'slow', '-crf', '15',
                    '-pix_fmt', 'yuv420p', '-profile:v', 'high', '-c:a', 'aac', '-b:a', '320k', '-ar', '48000',
                    '-movflags', '+faststart', '-shortest', o]
        encode(frames, '916', outs, af)


if __name__ == '__main__':
    main()
