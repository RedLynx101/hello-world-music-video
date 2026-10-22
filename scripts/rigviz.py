"""Quick look at the rig features for a time window: python rigviz.py t0 t1 out.png"""
import sys, json, os
import numpy as np
import cv2
# Project root: HELLO_WORLD_ROOT if set, otherwise the folder above scripts/.
ROOT = os.environ.get('HELLO_WORLD_ROOT') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
t0, t1, out = float(sys.argv[1]), float(sys.argv[2]), sys.argv[3]
R = json.load(open(os.path.join(ROOT, 'analysis', 'rig.json')))
spec = cv2.imread(os.path.join(ROOT, 'analysis', 'rig_spec.png'), cv2.IMREAD_GRAYSCALE)
a, b = int(t0 * 24), int(t1 * 24)
W = (b - a) * 3
img = np.zeros((40 * 4 + 300, W, 3), np.uint8)
s = cv2.resize(spec[a:b].T[::-1], (W, 160), interpolation=cv2.INTER_NEAREST)
img[:160] = cv2.applyColorMap(s, cv2.COLORMAP_INFERNO)
for name, c, y0 in (('vocal', (90, 200, 255), 170), ('kick', (80, 80, 255), 240), ('energy', (120, 255, 120), 310), ('bass', (255, 160, 80), 380)):
    v = np.array(R[name][a:b])
    pts = np.stack([np.arange(len(v)) * 3, y0 + 60 - v * 60], 1).astype(np.int32)
    cv2.polylines(img, [pts], False, c, 1)
    cv2.putText(img, name, (4, y0 + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4, c, 1)
for t, st, d in R['kicks']:
    if t0 <= t < t1:
        x = int((t - t0) * 24 * 3)
        cv2.line(img, (x, 440), (x, 460 if d else 452), (255, 255, 255), 1)
for s_ in range(int(t0), int(t1) + 1):
    x = int((s_ - t0) * 24 * 3)
    cv2.putText(img, str(s_), (x + 2, 455), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (150, 150, 150), 1)
cv2.imwrite(out, img)
print('VIZ', out, img.shape)
