"""Tile JPG/PNG stills into one contact sheet: python sheet.py out.jpg tile_width file1 file2 ..."""
import sys, os
import cv2
import numpy as np

out, tw = sys.argv[1], int(sys.argv[2])
tiles = []
for f in sys.argv[3:]:
    im = cv2.imread(f)
    h, w = im.shape[:2]
    t = cv2.resize(im, (tw, int(h * tw / w)), interpolation=cv2.INTER_AREA)
    cv2.putText(t, os.path.basename(f).rsplit('.', 1)[0], (6, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 160, 90), 1)
    tiles.append(t)
cols = 3 if tiles[0].shape[1] >= tiles[0].shape[0] else 4
rows = (len(tiles) + cols - 1) // cols
th = max(t.shape[0] for t in tiles)
S = np.full((rows * (th + 4), cols * (tw + 4), 3), 20, np.uint8)
for i, t in enumerate(tiles):
    r, c = divmod(i, cols)
    S[r * (th + 4):r * (th + 4) + t.shape[0], c * (tw + 4):c * (tw + 4) + tw] = t
cv2.imwrite(out, S, [cv2.IMWRITE_JPEG_QUALITY, 88])
print('SHEET', out, S.shape)
