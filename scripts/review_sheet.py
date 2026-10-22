"""Captioned review sheet: python review_sheet.py out.jpg title cols tile_w "file|caption" ..."""
import sys, os
from PIL import Image, ImageDraw, ImageFont

# Project root: HELLO_WORLD_ROOT if set, otherwise the folder above scripts/.
ROOT = os.environ.get('HELLO_WORLD_ROOT') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out, title, cols, tw = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
items = [a.split('|', 1) for a in sys.argv[5:]]
mono = ImageFont.truetype(os.path.join(ROOT, 'fonts', 'MartianMono.ttf'), 17)
sans = ImageFont.truetype(os.path.join(ROOT, 'fonts', 'InstrumentSans.ttf'), 21)
head = ImageFont.truetype(os.path.join(ROOT, 'fonts', 'InstrumentSerif-Italic.ttf'), 46)
tiles = []
for path, cap in items:
    im = Image.open(path).convert('RGB')
    im = im.resize((tw, round(im.height * tw / im.width)), Image.LANCZOS)
    tiles.append((im, cap))
th = max(t.height for t, _ in tiles)
pad, capH, top = 14, 58, 84
rows = (len(tiles) + cols - 1) // cols
S = Image.new('RGB', (cols * (tw + pad) + pad, top + rows * (th + capH + pad) + pad), (14, 13, 13))
d = ImageDraw.Draw(S)
d.text((pad + 4, 22), title, font=head, fill=(243, 236, 226))
for i, (im, cap) in enumerate(tiles):
    r, c = divmod(i, cols)
    x, y = pad + c * (tw + pad), top + r * (th + capH + pad)
    S.paste(im, (x, y + (th - im.height) // 2))
    tc, _, rest = cap.partition('  ')
    d.text((x + 2, y + th + 10), tc, font=mono, fill=(255, 106, 74))
    d.text((x + 2 + mono.getlength(tc + '  '), y + th + 8), rest, font=sans, fill=(226, 218, 206))
S.save(out, quality=90)
print('REVIEW', out, S.size)
