"""Contact sheet of test EXRs through the look: python preview.py out.jpg exposure file1.exr file2.exr ..."""
import sys, os
os.environ['OPENCV_IO_ENABLE_OPENEXR'] = '1'
import numpy as np
import cv2
sys.path.insert(0, os.path.dirname(__file__))
from look import read_exr, finish, grain_vignette

out, exposure = sys.argv[1], float(sys.argv[2])
files = sys.argv[3:]
tiles = []
for f in files:
    img = read_exr(f)
    h, w = img.shape[:2]
    g = finish(img, exposure=exposure, scale=h / 1080 if w > h else w / 1080)
    g = grain_vignette(g, np.random.default_rng(1), grain=0.0)
    tw = 640 if w > h else 270
    th = int(h * tw / w)
    t = cv2.resize((g * 255).astype(np.uint8), (tw, th), interpolation=cv2.INTER_AREA)
    cv2.putText(t, os.path.basename(f)[:-4], (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (90, 120, 255), 1)
    tiles.append(t)
cols = 3 if tiles and tiles[0].shape[1] > tiles[0].shape[0] else 4
rows = (len(tiles) + cols - 1) // cols
th, tw = max(t.shape[0] for t in tiles), max(t.shape[1] for t in tiles)
sheet = np.full((rows * (th + 4), cols * (tw + 4), 3), 20, np.uint8)
for i, t in enumerate(tiles):
    r, c = divmod(i, cols)
    sheet[r * (th + 4):r * (th + 4) + t.shape[0], c * (tw + 4):c * (tw + 4) + t.shape[1]] = t
cv2.imwrite(out, sheet[..., ::-1], [cv2.IMWRITE_JPEG_QUALITY, 88])
print('PREVIEW', out, sheet.shape)
