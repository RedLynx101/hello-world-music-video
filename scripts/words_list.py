"""Write analysis/words/words.json: the non-Latin thank-yous and the Windows font each should be shaped with."""
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))
import comp

FONTS = [  # (test, family, style)
    (lambda c: 0x0400 <= ord(c) <= 0x04FF, 'Times New Roman', 'Italic'),      # Cyrillic
    (lambda c: 0x0600 <= ord(c) <= 0x06FF, 'Times New Roman', 'Regular'),     # Arabic
    (lambda c: 0x0900 <= ord(c) <= 0x097F, 'Nirmala UI', 'Regular'),          # Devanagari
    (lambda c: 0x3040 <= ord(c) <= 0x30FF, 'Yu Gothic Light', 'Regular'),           # Japanese kana
    (lambda c: 0xAC00 <= ord(c) <= 0xD7AF, 'Malgun Gothic Semilight', 'Regular'),  # Hangul
    (lambda c: 0x4E00 <= ord(c) <= 0x9FFF, 'SimSun', 'Regular'),              # CJK ideographs
]
out = []
for w in dict.fromkeys(comp.THANKS):
    if all(ord(c) < 0x0250 for c in w):
        continue
    fam = None
    for test, family, style in FONTS:
        if any(test(c) for c in w):
            fam = (family, style)
            break
    out.append(dict(word=w, family=fam[0] if fam else 'Segoe UI', style=fam[1] if fam else 'Regular'))
d = os.path.join(comp.AN, 'words')
os.makedirs(d, exist_ok=True)
json.dump(out, open(os.path.join(d, 'words.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('WORDS', len(out), [o['family'] for o in out])
