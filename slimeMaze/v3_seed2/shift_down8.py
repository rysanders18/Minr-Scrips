# One-off (Ryan 2026-08-16): re-emit the seed-2 sandbox with the ENTIRE
# maze translated down 8 blocks (top 314 -> 306). A rigid translation
# keeps every chord, bounce and splice identical - the only casualties
# are decoration commands below the world floor (y < -64), which fail
# in-game by design; Ryan is building a manual end room at the bottom.
# Run from v3_seed2/:  python shift_down8.py
import sys
from collections import defaultdict

import gen_pinned as gm

SHIFT = 8

sim = gm.Sim(2)
assert sim.run(), 'seed 2 must regenerate identically'
# fork-gap violations are pre-existing on seed 2 (the shipped sandbox
# has them - the FORK_GAP_MAX battle was abandoned); only OTHER
# verify errors would indicate a corrupted regeneration
errs = [e for e in gm.verify(sim) if not e.startswith('fork gap')]
assert not errs, errs[:5]
# identity proof: the regenerated maze must equal the shipped sandbox
# (sim_debug.pkl was dumped from it) before we shift anything
import pickle
old = pickle.load(open('sim_debug.pkl', 'rb'))
new_set = {(b['x'], b['y'], b['z']) for b in sim.blocks if b is not None}
old_set = {(b['x'], b['y'], b['z']) for b in old['blocks'] if b is not None}
assert new_set == old_set, 'regenerated maze differs from sandbox!'
print('identity proof: %d blocks match the shipped sandbox exactly'
      % len(new_set))
st = sim.stats()
print('regenerated: %d blocks, %d splices' % (st['blocks'], st['splices']))

ys = [b['y'] for b in sim.blocks if b is not None]
print('pre-shift slime y %d..%d' % (min(ys), max(ys)))
for b in sim.blocks:
    if b is not None:
        b['y'] -= SHIFT
for br in sim.branches:
    br['y'] -= SHIFT
byy = defaultdict(list)
for i, b in enumerate(sim.blocks):
    if b is not None:
        byy[b['y']].append(i)
sim.by_y = byy
ys = [b['y'] for b in sim.blocks if b is not None]
print('post-shift slime y %d..%d' % (min(ys), max(ys)))

gm.emit(sim, '.')
print('sandbox re-emitted, shifted down %d' % SHIFT)
