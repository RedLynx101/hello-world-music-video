"""Print merged word timings for lyric lines: python words.py 12,21,55  (* = from the forced alignment)"""
import json, os, sys
ROOT = os.environ.get('HELLO_WORLD_ROOT') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
d = json.load(open(os.path.join(ROOT, 'analysis', 'timing.json')))
for i in [int(x) for x in sys.argv[1].split(',')]:
    L = d['lines'][i]
    print(i, L['text'])
    print('   ', ' '.join(f"{w}@{s:.2f}-{e:.2f}{'*' if src == 'al' else ''}" for w, s, e, src in L['words']))
