"""Print the segments of a stable-ts JSON result: python show.py analysis/align.json"""
import json, sys
d = json.load(open(sys.argv[1], encoding='utf-8'))
for s in d['segments']:
    print(f"{s['start']:7.2f} {s['end']:7.2f} {s['text'].strip()}")
