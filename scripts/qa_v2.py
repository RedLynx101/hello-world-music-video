"""QA: probe a finished MP4 and pull frames at given times. python qa_v2.py <mp4> <outdir> t1,t2,...  (seconds)"""
import os, sys, shutil, subprocess, json
sys.path.insert(0, os.path.dirname(__file__))
# ffmpeg / ffprobe: FFMPEG / FFPROBE if set, otherwise the ones on PATH.
FFMPEG = os.environ.get('FFMPEG') or shutil.which('ffmpeg') or 'ffmpeg'
FFPROBE = os.environ.get('FFPROBE') or shutil.which('ffprobe') or 'ffprobe'
src, out = sys.argv[1], sys.argv[2]
times = [float(x) for x in sys.argv[3].split(',')]
os.makedirs(out, exist_ok=True)
p = subprocess.run([FFPROBE, '-v', 'error', '-show_entries',
                    'format=duration:stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,duration',
                    '-of', 'json', src], capture_output=True, text=True)
info = json.loads(p.stdout)
print('PROBE', round(float(info['format']['duration']), 3), [(s['codec_type'], s.get('codec_name'), s.get('width'), s.get('height'),
                                                            s.get('r_frame_rate'), s.get('sample_rate'), s.get('duration')) for s in info['streams']])
for t in times:
    o = os.path.join(out, 'q_%07.2f.jpg' % t)
    subprocess.run([FFMPEG, '-y', '-v', 'error', '-ss', '%.3f' % t, '-i', src, '-frames:v', '1', '-q:v', '3', o])
    print('FRAME', o, os.path.exists(o))
