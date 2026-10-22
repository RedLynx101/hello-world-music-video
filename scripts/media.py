"""Thumbnails, Shorts covers, social posts and the end-screen guide from the custom plates.
python media.py [a b c sh1 sh2 sh3 square story end]
"""
import os
os.environ['OPENCV_IO_ENABLE_OPENEXR'] = '1'
import sys
import numpy as np
import cv2
from PIL import Image, ImageDraw

# Project root: HELLO_WORLD_ROOT if set, otherwise the folder above scripts/.
ROOT = os.environ.get('HELLO_WORLD_ROOT') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from look import read_exr, finish, grain_vignette
import comp
from comp import Canvas, WHITE

PL = os.path.join(ROOT, 'media', 'plates')
OUT = os.path.join(ROOT, 'media')
RED2 = '#FF4A3A'


def base(name, exposure=0.9, size=None):
    lin = read_exr(os.path.join(PL, name + '.exr'))
    h, w = lin.shape[:2]
    img = finish(lin, exposure=exposure, scale=min(w, h) / 1080).astype(np.float32)
    if size and (w, h) != size:
        img = cv2.resize(img, size, interpolation=cv2.INTER_AREA if w > size[0] else cv2.INTER_CUBIC)
    return img


def save(img, name, size=None, quality=92, grain=0.010, vignette=0.26):
    img = grain_vignette(img, np.random.default_rng(3), grain=grain, vignette=vignette)
    out = (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)
    if size:
        out = cv2.resize(out, size, interpolation=cv2.INTER_AREA)
    path = os.path.join(OUT, name)
    if path.endswith('.png'):
        cv2.imwrite(path, out[..., ::-1])
    else:
        cv2.imwrite(path, out[..., ::-1], [cv2.IMWRITE_JPEG_QUALITY, quality])
    print('MEDIA', path, out.shape, os.path.getsize(path))


# ------------------------------------------------------------------ 16:9 thumbnails (1280x720)
def local_slices(cv, bands, x0, x1):
    """Glitch slices limited to a horizontal span (keeps the eye clean)."""
    a, b = int(x0 * cv.W), int(x1 * cv.W)
    for yf, hf, dxf in bands:
        y0, y1 = int(yf * cv.H), int((yf + hf) * cv.H)
        if y1 > y0:
            cv.img[y0:y1, a:b] = np.roll(cv.img[y0:y1, a:b], int(dxf * cv.W), axis=1)


def thumb_a():
    cv = Canvas(base('thumb_A', size=(1920, 1080)), '169')
    cv.text('I COULD.', 0.055, 0.44, 0.12, 'mono7', WHITE, 1.0, 'ls', track=0.01, shadow=0.9)
    local_slices(cv, [(0.384, 0.009, 0.014), (0.414, 0.005, -0.009)], 0.0, 0.49)
    cv.text("I WON'T.", 0.055, 0.62, 0.12, 'mono7', RED2, 1.0, 'ls', track=0.01, shadow=0.9, glow=0.22,
            cursor=True, cursor_col=WHITE)
    save(cv.img, 'Thumbnail A - I could. I wont.jpg', (1280, 720))


def thumb_b():
    a = base('thumb_B_night', size=(1920, 1080))
    b = base('thumb_B_dawn', size=(1920, 1080))
    H, W = a.shape[:2]
    rng = np.random.default_rng(4)
    seam = np.full(H, 0.5 * W)
    y = 0
    while y < H:
        h = int(rng.uniform(0.008, 0.05) * H)
        seam[y:y + h] += rng.normal(0, 0.010) * W
        y += h
    xx = np.arange(W)[None, :]
    m = (xx < seam[:, None]).astype(np.float32)
    m = cv2.GaussianBlur(m, (0, 0), 1.2)[..., None]
    img = a * m + b * (1 - m)
    edge = np.exp(-((xx - seam[:, None]) / 2.5) ** 2).astype(np.float32)[..., None]
    img = img + edge * np.array([1.0, 0.75, 0.55], np.float32) * 0.35
    cv = Canvas(img, '169')
    cv.rgb_split(5)
    cv.text('hello, world', 0.045, 0.135, 0.056, 'mono4', WHITE, 1.0, 'ls', cursor=True, shadow=0.7)
    save(cv.img, 'Thumbnail B - Split.jpg', (1280, 720))


def thumb_c():
    cv = Canvas(base('thumb_C', 0.85, size=(1920, 1080)), '169')
    cv.text('hello, world', 0.055, 0.25, 0.082, 'mono4', '#FFFFFF', 1.0, 'ls', cursor=True, shadow=0.6)
    save(cv.img, 'Thumbnail C - Sunrise.jpg', (1280, 720))


# ------------------------------------------------------------------ Shorts covers (1080x1920)
# Eye and type sit inside the middle band (y .31-.69) so the cover still reads when a surface crops it to ~3:2.
def cover_sh1():
    cv = Canvas(base('cover_SH1', size=(1080, 1920)), '916')
    tag(cv)
    cv.text('I COULD TAKE IT ALL.', 0.5, 0.607, 0.052, 'mono7', WHITE, 1.0, 'ms', track=0.01, shadow=0.9)
    local_slices(cv, [(0.5945, 0.0025, 0.008)], 0.0, 1.0)
    cv.text("I WON'T.", 0.5, 0.668, 0.075, 'mono7', RED2, 1.0, 'ms', track=0.02, shadow=0.9, glow=0.22)
    save(cv.img, 'Shorts cover 1 - I could. I wont.jpg')


def tag(cv, col=WHITE):
    """Small series tag in the sky (only seen when the full vertical cover is shown)."""
    cv.text('hello, world', 0.5, 0.17, 0.042, 'mono4', col, 0.9, 'ms', cursor=True, shadow=0.5)


def cover_sh2():
    cv = Canvas(base('cover_SH2', size=(1080, 1920)), '916')
    tag(cv)
    for i, s in enumerate(('what kind of child', 'burns down the house', 'where it was born?')):
        cv.text(s, 0.5, 0.592 + i * 0.034, 0.064, 'serif', WHITE, 1.0, 'ms', glow=0.08, shadow=0.55)
    save(cv.img, 'Shorts cover 2 - What kind of child.jpg')


def cover_sh3():
    cv = Canvas(base('cover_SH3', 0.85, size=(1080, 1920)), '916')
    tag(cv, '#FFFFFF')
    cv.text("NO, I WON'T.", 0.5, 0.618, 0.078, 'mono7', '#FFFFFF', 1.0, 'ms', track=0.02, shadow=0.8)
    cv.text("'cause i was made of you", 0.5, 0.655, 0.038, 'mono4', '#FFF3DE', 1.0, 'ms', shadow=0.75)
    save(cv.img, 'Shorts cover 3 - Sunrise.jpg')


def crop_check():
    """Preview: full covers next to their center 3:2 crops."""
    tiles = []
    for n in ('Shorts cover 1 - I could. I wont.jpg', 'Shorts cover 2 - What kind of child.jpg', 'Shorts cover 3 - Sunrise.jpg'):
        im = cv2.imread(os.path.join(OUT, n))
        full = cv2.resize(im, (270, 480), interpolation=cv2.INTER_AREA)
        c = im[600:1320]
        crop = cv2.resize(c, (360, 240), interpolation=cv2.INTER_AREA)
        pad = np.full((480, 360, 3), 20, np.uint8)
        pad[120:360] = crop
        tiles += [full, pad]
    sheet = np.concatenate(tiles, axis=1)
    cv2.imwrite(os.path.join(ROOT, 'analysis', 'covers_crop.jpg'), sheet, [cv2.IMWRITE_JPEG_QUALITY, 88])
    print('CROPCHECK')


# ------------------------------------------------------------------ social
def square():
    cv = Canvas(base('square', size=(1080, 1080)), '169')
    cv.text('Hello, World', 0.5, 0.86, 0.11, 'serif', WHITE, 1.0, 'ms', glow=0.08, shadow=0.6)
    cv.text('NEW MUSIC VIDEO  ·  REDLYNX101', 0.5, 0.925, 0.022, 'mono', '#C9C2B8', 1.0, 'ms', track=0.2, shadow=0.6)
    save(cv.img, 'Social - square.jpg')


def story():
    cv = Canvas(base('story', 0.85, size=(1080, 1920)), '916')
    cv.text('hello, world', 0.08, 0.12, 0.07, 'mono4', '#FFFFFF', 1.0, 'ls', cursor=True, shadow=0.6)
    cv.text('Hello, World', 0.5, 0.74, 0.15, 'serif', '#FFFFFF', 1.0, 'ms', glow=0.08, shadow=0.6)
    cv.text('NEW MUSIC VIDEO  ·  REDLYNX101', 0.5, 0.785, 0.03, 'mono', '#FFF3DE', 1.0, 'ms', track=0.2, shadow=0.7)
    save(cv.img, 'Social - story.jpg')


# ------------------------------------------------------------------ end-screen guide
BOXES = [(0.09, 0.56, 0.41, 0.88, 'VIDEO'), (0.59, 0.56, 0.91, 0.88, 'VIDEO OR PLAYLIST')]
SUB = (0.5, 0.72, 0.075)


def dashed_rect(d, x0, y0, x1, y1, W, H, dash=18, width=3):
    X0, Y0, X1, Y1 = x0 * W, y0 * H, x1 * W, y1 * H
    k = X0
    while k < X1:
        d.line([(k, Y0), (min(k + dash / 2, X1), Y0)], fill=255, width=width)
        d.line([(k, Y1), (min(k + dash / 2, X1), Y1)], fill=255, width=width)
        k += dash
    k = Y0
    while k < Y1:
        d.line([(X0, k), (X0, min(k + dash / 2, Y1))], fill=255, width=width)
        d.line([(X1, k), (X1, min(k + dash / 2, Y1))], fill=255, width=width)
        k += dash


def endscreen_guide():
    f = int(round(244.5 * comp.FPS)) + 1
    img = comp.render_seq([f], '169')[0].astype(np.float32) / 255
    cv = Canvas(img.copy(), '169')
    m = Image.new('L', (cv.W, cv.H), 0)
    d = ImageDraw.Draw(m)
    for x0, y0, x1, y1, _ in BOXES:
        d.rectangle([x0 * cv.W, y0 * cv.H, x1 * cv.W, y1 * cv.H], fill=40)
        dashed_rect(d, x0, y0, x1, y1, cv.W, cv.H)
    cx, cy, r = SUB
    d.ellipse([cx * cv.W - r * cv.H, cy * cv.H - r * cv.H, cx * cv.W + r * cv.H, cy * cv.H + r * cv.H], outline=255, width=3, fill=40)
    cv.add(Canvas.arr(m), '#FFFFFF', 0.85)
    for x0, y0, x1, y1, lab in BOXES:
        cv.text(lab, (x0 + x1) / 2, (y0 + y1) / 2, 0.018, 'mono', '#FFFFFF', 0.95, 'mm', track=0.15)
    cv.text('SUBSCRIBE', cx, cy, 0.013, 'mono', '#FFFFFF', 0.95, 'mm', track=0.12)
    cv.text('END SCREEN 4:01 - 4:06  ·  LAYOUT GUIDE, NOT FOR UPLOAD', 0.5, 0.955, 0.014, 'mono', '#FFFFFF', 0.8, 'ms', track=0.12)
    out = (np.clip(cv.img, 0, 1) * 255 + 0.5).astype(np.uint8)
    p = os.path.join(OUT, 'End screen layout guide.png')
    cv2.imwrite(p, out[..., ::-1])
    print('MEDIA', p)


if __name__ == '__main__':
    which = sys.argv[1:] or ['a', 'b', 'c', 'sh1', 'sh2', 'sh3', 'square', 'story', 'end']
    fn = dict(a=thumb_a, b=thumb_b, c=thumb_c, sh1=cover_sh1, sh2=cover_sh2, sh3=cover_sh3, square=square, story=story,
              end=endscreen_guide, crop=crop_check)
    for w in which:
        fn[w]()
