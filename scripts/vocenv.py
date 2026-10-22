"""Print the vocal-stem RMS envelope over given windows: python vocenv.py "69.2-72.6,76-78.6" """
import sys, os
import numpy as np
import soundfile as sf
# Project root: HELLO_WORLD_ROOT if set, otherwise the folder above scripts/.
ROOT = os.environ.get('HELLO_WORLD_ROOT') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
y, sr = sf.read(os.path.join(ROOT, 'analysis', 'sep', 'htdemucs', 'hello_world', 'vocals.wav'))
if y.ndim > 1:
    y = y.mean(axis=1)
hop = int(sr * 0.1)
for win in sys.argv[1].split(','):
    a, b = [float(x) for x in win.split('-')]
    row = []
    t = a
    while t < b:
        seg = y[int(t * sr):int(t * sr) + hop]
        r = 20 * np.log10(np.sqrt(np.mean(seg ** 2)) + 1e-9)
        row.append('%.1f:%d' % (t, r))
        t += 0.1
    print(win, ' '.join(row))
