import os, sys, time, cProfile, pstats
sys.path.insert(0, os.path.dirname(__file__))
import comp
f = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
fmt = sys.argv[2] if len(sys.argv) > 2 else '169'
comp.render_seq([f], fmt)  # warm caches (fonts, proj)
t0 = time.time()
cProfile.run('comp.render_seq([%d], %r)' % (f + 1, fmt), os.path.join(comp.ROOT, 'analysis', 'prof.out'))
print('FRAME_SECONDS', round(time.time() - t0, 2))
pstats.Stats(os.path.join(comp.ROOT, 'analysis', 'prof.out')).sort_stats('tottime').print_stats(18)
