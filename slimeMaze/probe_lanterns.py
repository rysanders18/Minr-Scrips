# probe_lanterns.py - classify every lantern's vertical relation to
# stone in its own column and to the local corridor band, to pin down
# the "one block above / below the walls" reports.
import os
from collections import defaultdict

import walls as W

data = W.load_or_build(os.path.join(W.HERE, 'v3_seed2'), False)
passes, open_model, walls = W.paint(data)
W.stamp(walls, data['regions'], passes)
W.sweep_debris(walls, open_model)
W.erode_floaters(walls, open_model)
W.close_ceiling_seams(walls, open_model)
W.seal_repair(walls, open_model)
W.thin_walls(walls, open_model)
lant = W.paint_lanterns(walls, open_model)

wall_cols = defaultdict(set)
for x, y, z in walls:
    wall_cols[(x, z)].add(y)

cats = defaultdict(int)
samples = defaultdict(list)
for x, y, z in sorted(lant):
    ws = wall_cols.get((x, z), set())
    # sealing context: the open cell(s) the lateral wall neighbours
    # seal at this slice; use their open run for band position
    band_pos = set()
    for dx, dz in W.N4:
        if (x + dx, y, z + dz) in walls:
            for ax, az in W.N4:
                ox, oz = x + dx + ax, z + dz + az
                for lo, hi in open_model.iv.get((ox, oz), ()):
                    if lo <= y <= hi:
                        band_pos.add('top' if y == hi else
                                     'bottom' if y == lo else 'mid')
    key = None
    if (y + 2 in ws or y + 3 in ws) and y + 1 not in ws:
        key = 'hangs 1-2 below stone in own column (floor zone)'
    elif (y - 2 in ws or y - 3 in ws) and y - 1 not in ws:
        key = 'floats 1-2 above stone in own column (dome zone)'
    elif 'top' in band_pos and 'mid' not in band_pos:
        key = 'at band TOP slice (dome springs here)'
    elif 'bottom' in band_pos and 'mid' not in band_pos:
        key = 'at band BOTTOM slice (floor plane)'
    else:
        key = 'mid-band side curtain'
    cats[key] += 1
    if len(samples[key]) < 5:
        samples[key].append((x, y, z))

print()
for k in sorted(cats, key=lambda k: -cats[k]):
    print('%7d  %s' % (cats[k], k))
    for s in samples[k]:
        print('           e.g. (%d,%d,%d)' % s)
