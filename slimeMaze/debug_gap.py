# debug_gap.py - inspect the model around a reported in-world gap:
# python debug_gap.py <x> <z> [ylo] [yhi]
import os
import sys

import walls as W

TX, TZ = int(sys.argv[1]), int(sys.argv[2])
Y0 = int(sys.argv[3]) if len(sys.argv) > 3 else 150
Y1 = int(sys.argv[4]) if len(sys.argv) > 4 else 172

data = W.load_or_build(os.path.join(W.HERE, 'v3_seed2'), False)
passes, open_model, walls = W.paint(data)
pre = set(walls)
W.stamp(walls, data['regions'], passes)

print('\ncolumn (%d, %d):' % (TX, TZ))
print('passes:', sorted(passes.get((TX, TZ), {}).items()))
for y in range(Y1, Y0 - 1, -1):
    o = open_model.at(TX, TZ, y)
    w = (TX, y, TZ) in walls
    pw = (TX, y, TZ) in pre
    d = W.strict_d(passes, TX, y, TZ)
    adj = sum(1 for dx, dz in W.N4 if open_model.at(TX + dx, TZ + dz, y))
    print('  y=%d %-5s %-9s d=%-5s adj_open=%d'
          % (y, 'open' if o else '-',
             'WALL' if w else ('pre-only' if pw else 'air'),
             ('%.2f' % d) if d is not None else 'None', adj))

hits = 0
for i, (delta, band, wy) in enumerate(data['regions']):
    sdx, sdy, sdz = delta
    if (TX, TZ) in band:
        print('IN WINDOW of region %d delta %s path-band %s'
              % (i, delta, band[(TX, TZ)]))
        hits += 1
    if (TX + sdx, TZ + sdz) in band:
        pl = band[(TX + sdx, TZ + sdz)]
        print('IN TAIL of region %d delta %s (window col %s path-band '
              '%s -> tail y %s)'
              % (i, delta, (TX + sdx, TZ + sdz), pl,
                 (pl[0] - sdy, pl[1] - sdy)))
        hits += 1
if not hits:
    print('not inside any splice window or tail tube')
