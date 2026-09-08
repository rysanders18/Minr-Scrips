# debug_outline.py - print plan-view maps of floor/outline/walls
# around a reported missing-corner cell:
#   python debug_outline.py <x> <z> <y> [radius]
# Legend per cell (at each of y-1, y, y+1):
#   # wall (standing: wall above too)   w wall (no wall above)
#   P outline   F plain floor   o corridor air   . nothing
import os
import sys

import walls as W

TX, TZ, TY = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
R = int(sys.argv[4]) if len(sys.argv) > 4 else 8

data = W.load_or_build(os.path.join(W.HERE, 'v3_seed2'), False)
passes, open_model, walls = W.paint(data)
W.stamp(walls, data['regions'], passes)
W.purge_in_air_walls(walls, open_model)
W.close_ceiling_seams(walls, open_model)
W.seal_repair(walls, open_model)
W.thin_walls(walls, open_model)
W.drop_hanging_remnants(walls, open_model)
floor = W.paint_floor(open_model, walls, set(data['slime']))
outline = W.paint_outline(floor, walls, open_model)

for y in (TY + 1, TY, TY - 1):
    print('\ny = %d   (target column marked with *)' % y)
    hdr = '     ' + ''.join('%2d' % (x % 10)
                            for x in range(TX - R, TX + R + 1))
    print(hdr)
    for z in range(TZ - R, TZ + R + 1):
        row = []
        for x in range(TX - R, TX + R + 1):
            p = (x, y, z)
            if p in walls:
                ch = '#' if (x, y + 1, z) in walls else 'w'
            elif p in outline:
                ch = 'P'
            elif p in floor:
                ch = 'F'
            elif open_model.at(x, z, y):
                ch = 'o'
            else:
                ch = '.'
            if x == TX and z == TZ:
                ch = '*' if ch == 'F' else ch.upper()
            row.append(' ' + ch)
        print('%5d%s' % (z, ''.join(row)))
