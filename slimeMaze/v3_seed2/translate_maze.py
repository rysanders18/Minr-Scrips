# translate_maze.py (Ryan 2026-08-17, supersedes shift_down8.py):
# re-emit the seed-2 sandbox with the ENTIRE maze rigidly translated
# by (DX, DY, DZ) from the ORIGINAL generation. Current shift:
#   DY = -8   (top 314 -> 306; bottom sits below the world floor,
#              those commands fail in-game by design - manual end room)
#   DX = -233, DZ = +429  (world-geometric center (4851,2951) ->
#                          (4618.0, 3380.0) exactly)
# A rigid translation keeps every chord, bounce and splice identical.
# Writes shift.txt so walls.py applies the same translation to its
# regenerated sim (else decoration lands at the old position).
# Run from v3_seed2/:  python translate_maze.py
# Afterwards: python ../walls.py v3_seed2 --install <world>  and
#             python make_buildall.py
from collections import defaultdict

import gen_pinned as gm

DX, DY, DZ = -233, -8, 429

sim = gm.Sim(2)
assert sim.run(), 'seed 2 must regenerate identically'
errs = [e for e in gm.verify(sim) if not e.startswith('fork gap')]
assert not errs, errs[:5]

# identity proof vs sim_debug.pkl. The pickle is refreshed at the
# END of this script with the FULLY shifted maze, so on every re-run
# the fresh regen + (DX, DY, DZ) must match it exactly. (The first
# run, 2026-08-17, compared against the y-8-only pickle the one-off
# shift_down8.py left behind; that state is gone forever)
import pickle
old = pickle.load(open('sim_debug.pkl', 'rb'))
old_set = {(b['x'], b['y'], b['z']) for b in old['blocks']
           if b is not None}
new_set = {(b['x'] + DX, b['y'] + DY, b['z'] + DZ)
           for b in sim.blocks if b is not None}
assert new_set == old_set, 'regenerated maze differs from sandbox!'
print('identity proof: %d blocks match the shipped sandbox' % len(new_set))

for b in sim.blocks:
    if b is not None:
        b['x'] += DX
        b['y'] += DY
        b['z'] += DZ
        if b['px'] is not None:
            b['px'] += DX
            b['pz'] += DZ
for br in sim.branches:
    br['y'] += DY
    if br.get('px') is not None:
        br['px'] += DX
        br['pz'] += DZ
byy = defaultdict(list)
grid = defaultdict(list)
for i, b in enumerate(sim.blocks):
    if b is not None:
        byy[b['y']].append(i)
        grid[(b['x'] >> 3, b['z'] >> 3)].append(i)
sim.by_y = byy
sim.grid = grid

# hand-tuned spawn override is keyed by absolute coords - translate it
gm.SPAWN_OVERRIDE = {(x + DX, z + DZ): (tx + DX, tz + DZ)
                     for (x, z), (tx, tz) in gm.SPAWN_OVERRIDE.items()}

ys = [b['y'] for b in sim.blocks if b is not None]
xs = [b['x'] for b in sim.blocks if b is not None]
zs = [b['z'] for b in sim.blocks if b is not None]
print('post-shift: x %d..%d (center %.1f), y %d..%d, z %d..%d '
      '(center %.1f)'
      % (min(xs), max(xs), (min(xs) + max(xs) + 1) / 2.0,
         min(ys), max(ys), min(zs), max(zs),
         (min(zs) + max(zs) + 1) / 2.0))

gm.emit(sim, '.')
with open('shift.txt', 'w', newline='\n') as fh:
    fh.write('%d %d %d\n' % (DX, DY, DZ))

# refresh the solver debug pickle with the fully shifted structures
data = {
    'blocks': sim.blocks,
    'branches': sim.branches,
    'kids': dict(sim.kids),
    'splices': sim.splices,
    'seed': sim.seed,
}
with open('sim_debug.pkl', 'wb') as fh:
    pickle.dump(data, fh)
print('sandbox re-emitted at the new position; shift.txt + '
      'sim_debug.pkl updated')
