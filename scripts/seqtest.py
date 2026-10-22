"""Render a short contiguous run and save the last frame: python seqtest.py fmt t0 t1 out.jpg"""
import os, sys
os.environ['OPENCV_IO_ENABLE_OPENEXR'] = '1'
sys.path.insert(0, os.path.dirname(__file__))
import cv2
import comp
fmt, t0, t1, out = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
frames = list(range(int(round(t0 * comp.FPS)) + 1, int(round(t1 * comp.FPS)) + 1))
img = comp.render_seq(frames, fmt)[-1]
cv2.imwrite(out, img[..., ::-1], [cv2.IMWRITE_JPEG_QUALITY, 90])
print('SEQ', len(frames), out)
