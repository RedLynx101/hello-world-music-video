import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import shots
prev = 0.0
for i, L in enumerate(shots.LINES):
    bad = []
    for k, w in enumerate(L['words']):
        if w[2] - w[1] < 0.03:
            bad.append(('zero', w[0], round(w[1], 2)))
        if w[1] < prev - 0.05:
            bad.append(('back', w[0], round(w[1], 2), round(prev, 2)))
        if w[2] - w[1] > 1.6 and k < len(L['words']) - 1:
            bad.append(('long', w[0], round(w[1], 2), round(w[2], 2)))
        prev = max(prev, w[1])
    if L['start'] != L['words'][0][1]:
        bad.append(('start', L['start'], L['words'][0][1]))
    if bad:
        print(i, L['text'], bad)
print('CHECKED')
