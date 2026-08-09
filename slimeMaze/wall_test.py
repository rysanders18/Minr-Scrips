# wall_test.py - DRAFT: curvature-following decorated walls for the maze.
#
# Walls are the parallel curves of the slime centerline (offset +-WALL_D,
# so on constant-turn arcs they are concentric circles and the spline is
# equidistant between them). The centerline is NOT the raw chord
# polyline: each stream's bounce points are interpolated with a
# Catmull-Rom spline, so the sampled centerline (and every wall, dome
# and floor point offset from it) curves continuously instead of
# kinking 22.5 deg at every bounce. The spline passes exactly through
# every block center, so corridor clearance is unchanged (max deviation
# from the old chords is the arc sagitta, ~0.31 blocks at mid-chord),
# and its tangent gives a continuously rotating wall normal - the old
# per-vertex corner fans are gone. On top of the shape, the columns are
# CLASSIFIED the way the friend's WorldEdit pipeline classifies cells
# with fence-connection magic - except we derive the classes directly
# from geometry:
#
#   PANEL  - ordinary wall column: prismarine-brick base, cyan-glass
#            body with a sea-lantern glow layer inset one block
#            behind it (fully deterministic, no randomized details)
#   PILLAR - every RHYTHM blocks of wall arc-length: a full dark
#            prismarine pier (the friend's iterated lime->blue/brown
#            segmentation, computed exactly; no lantern cap)
#   TUFF   - the wall columns immediately flanking each pier become
#            full tuff-brick pillars, so every pier reads as a
#            tuff | dark prismarine | tuff cluster
#
# DOME: a blackstone barrel vault (semicircular arch of radius
# WALL_D across the corridor) rises from the two wall tops and
# roofs each corridor; where corridors meet, the vaults intersect and
# shell points inside another corridor's interior are pruned. EVERY
# setblock/fill this script emits uses the `strict` placement mode
# (1.21.5+): no block updates on placement. (A holdover from when the
# vault was concrete powder, which would have fallen - kept because
# update-free placement is harmless and protects any future gravity
# or update-sensitive blocks.)
#
# FLOOR: a SINGLE-LAYER andesite plane at the wall-base level (path-4)
# spans the corridor to just past the wall line (WALL_D + 0.4 rounds
# into the wall column, never beyond, so wall-foot cells exist
# wherever walls step or are pruned). The floor steps down with the
# path; own steps are always exactly 1 block, and full solid cubes
# keep every riser closed (the old 2-thick step overlap was armor for
# hole bugs - self-pruning and seam slots - that are fixed at the
# root, so one layer suffices). Where a cluster holds two blended
# levels (junction blends) the LOWER level wins. Wherever a
# 4-neighbour floor cell sits 2..13 blocks lower (junction seams,
# stacked-corridor boundaries), the higher cell's column extends down
# to one block above the neighbour. Points inside another corridor's
# interior are pruned like the dome, BUT only by samples >= ~2 levels
# below the rib's own path level (floor_near) - the plain [-3, 9]
# window let a corridor prune its own floor just before each level
# step, punching trenches along step lines. Levels a wall run
# occupies are left to the wall.
#
# FLOOR DECOR: the surface ring where the floor meets a wall is
# prismarine bricks, and the ring where the prismarine meets the
# andesite is diamond ore. Corner cells are added to both lines so no
# two line blocks are ever connected only diagonally - and because
# the prismarine line visually continues through the wall's
# panel-base course, those bases join the connect pass as passive
# members (they pair and connect but never initiate base-to-base
# fills), so corners against tuff/pier bases are filled too. Painted
# BEFORE the splice stamp, so every tail tube copies its window's
# decoration exactly.
#
# WALL BANDS: the wall face gets the same two-line outline where it
# meets the floor and the dome. Bottom of every wall run: the lo and
# lo+1 courses are BOTH deepslate tiles (two courses deep, into the
# floor - a floorboard that quantizes a block lower than the run
# bottom still meets deepslate, never bare base/tuff), the course
# above them polished deepslate. Top, where the vault springs
# off the wall: hi is deepslate tiles, hi-1 polished deepslate
# (replacing the old dark-prismarine trim row). Wherever a line steps
# 1 level between along-wall (8-neighbour) columns, the column on the
# receding side doubles the line to cover both levels and the polished
# line stacks on the doubled span - the floor lines' corner rule
# transposed into the wall face. Plan-diagonal travel is inherent to a
# 1-block-thick curve and is left alone. Bands cross every column
# class (panels, piers, tuff flanks, tip frames) so the outline never
# breaks. Painted before the splice stamp, after the floor lines.
#
# GLASS DEPTH: the body rows are cyan stained glass, and the sea
# lanterns sit one block INTO the wall behind them: every cell a
# corridor-facing glass block's horizontal faces touch that is
# neither open corridor space nor a corridor-facing wall surface
# becomes a sea lantern - added where the shell was 1 thick,
# converted where a buried second wall layer already stood (the
# 2-thick spots). Open space is decided by flood-filling the actual
# air volume from the corridor centerlines through empty cells,
# leashed to a coarse envelope around the sampled centerlines - a
# radius test CANNOT work here: the discretized wall lands anywhere
# from ~4.5 to ~5.7 blocks off the centerline (bends, junction
# fans), so any fixed cutoff both floats lanterns in front of
# far-out wall faces and eats corridor-facing blocks of close-in
# ones (both were observed in-world). Reachable cells never receive
# a lantern and any wall block touching reachable air keeps its
# material; unreachable cells are enclosed wall interior. Buried
# glass that faces no open air is folded into the lantern layer.
# Dome and floor cells behind glass are left as they are.
#   TIP    - a wall run's end where an opening (fork mouth, junction
#            cavern) cuts it: a glowing alternating frame column (the
#            friend's yellow markers)
#
# Wall points within CLEAR of ANY other corridor centerline are skipped,
# which opens the shared caverns; the columns flanking each opening
# become TIP frames. No floor or ceiling yet. Deterministic: all random
# detail comes from a coordinate hash.
#
# SPLICE SHELL STAMPING: the seamless teleports swap the player from a
# splice tail onto its window by a pure translation, so everything the
# player can see around the tail must be an EXACT translated copy of
# what surrounds the window. All decoration is first painted into a
# single world model ((x,y,z) -> family, material; dome, then floor,
# then walls, so "the wall wins" by construction); then for every
# splice the window's FINAL block tube - columns within SHELL_R of the
# window stretch, y in [path-5, path+14], air included - is copied
# over the tail tube. Stamping final blocks (not intermediate
# structures) makes the copy immune to emission-stage divergence (run
# merging, wall-skips, class recipes). Deletions stop at path-3:
# below that, local sub-floor blocks are invisible and removing them
# could hole a lower corridor's vault. Nothing past the window end is
# stamped: beyond the dead end there is no separation guarantee, and
# the constant 22.5 deg/bounce curvature occludes sightlines past ~4
# bounces. Splices stamp highest-window-first so chained splices (a
# window lying on another splice's tail) propagate top-down.
#
# CHUNK LOADING: /setblock and /fill silently fail in unloaded chunks.
# Every chain (build and remove) emits its commands bucketed into
# REGION x REGION (128-block, 8-chunk) areas: one tp to the bucket's
# center, a 10-tick @delay so the chunks around the player load, then
# every block in the bucket - never more than ~4 chunks from the
# player. A part boundary inside a bucket re-emits the tp + delay at
# the top of the next part so each part is self-sufficient.
#
# Outputs: slimemaze/walls1..N.msc / removewalls1..N.msc,
# slimemaze/dome1..N.msc / removedome1..N.msc and slimemaze/floor1..N /
# removefloor1..N.msc (chained), and rewrites the wall/dome/floor
# declarations in slimemaze.nms (regenerating the maze rewrites the
# .nms - rerun this script afterwards).
#
# Usage: python wall_test.py

import math
import os
import re
from collections import defaultdict

import generate_maze as gm


def emitted_seed():
    # read the seed of the currently emitted maze from the .nms header
    nms = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            '%s.nms' % gm.NAMESPACE)).read()
    return int(re.search(r'seed (\d+)', nms).group(1))


SEED = emitted_seed()    # always matches the emitted maze
LAYERS = 201             # test band: START_Y .. START_Y-LAYERS+1
                         # (down to y=100 - covers all six transitions)
WALL_D = 5.0             # wall offset from the centerline (4 air between)
WALL_BASE = -4           # wall bottom relative to the local path level
WALL_H = 13              # wall height (path-4 .. path+8)
CLEAR = 4.3              # skip wall points this close to any centerline
CLEAR_DY = 12            # ...within this many levels vertically
STRIDE = 0.4             # sampling stride along each chord
RHYTHM = 5.0             # wall arc-length between pillars
REGION = 128             # placement bucket size (8 chunks): tp once per
                         # bucket, @delay 10 to load, then place
HERE = os.path.dirname(os.path.abspath(__file__))

BAND_TOP = gm.START_Y
BAND_BOT = gm.START_Y - LAYERS + 1

# palette (no randomized details - fully deterministic recipes)
BASE = 'minecraft:prismarine_bricks'
BODY = 'minecraft:cyan_stained_glass'
LANTERN = 'minecraft:sea_lantern'    # glow layer inset behind the glass
TRIM = 'minecraft:dark_prismarine'
PIER = 'minecraft:dark_prismarine'
TUFF = 'minecraft:tuff_bricks'
DOME = 'minecraft:blackstone'
FLOOR = 'minecraft:andesite'
FLOOR_EDGE = 'minecraft:prismarine_bricks'
FLOOR_TRIM = 'minecraft:diamond_ore'
WALL_EDGE = 'minecraft:deepslate_tiles'      # wall course against floor & dome
WALL_TRIM = 'minecraft:polished_deepslate'   # second wall course inward

# ---- palette transitions ------------------------------------------------
# The palette is a property of the SLIME BLOCK a stretch belongs to,
# not of the block's own y: every geometry sample inherits the palette
# of its chord's blocks, so a divide through walls/floor/dome is a
# vertical cross-section plane, never a horizontal stripe. Each PATH
# flips permanently to the next palette at a per-branch random
# threshold drawn inside a TRANSITIONS window, inheriting "already
# flipped" across forks - different corridors change color at
# different depths and never revert mid-run. Where the two blocks of
# a chord disagree, samples near the chord midpoint become a clean
# netherite slice (full ring, corners and all). Merging dead ends
# adopt the junction's palette over their last MERGE_LEAD bounces;
# splice tails are overridden block-by-block to their window
# counterparts', with the flip SPLICE_LEAD bounces before the
# trigger - the player is already in the destination's colors at
# every seam and swap. The flip logic itself (SPLICE_LEAD, MERGE_LEAD,
# MIN_RUN, TRANSITIONS and every repair rule) lives in
# generate_maze.compute_palette - shared with emit()'s onward-path
# fork resolution so the trigger scripts and the painted world agree.
NETHER_SLICE = 'minecraft:netherite_block'
SLICE_HALF = 0.8         # slice half-thickness in blocks of arc
PALETTES = {
    1: {   # gold
        'minecraft:prismarine_bricks': 'minecraft:gold_block',
        'minecraft:diamond_ore': 'minecraft:gold_ore',
        'minecraft:dark_prismarine': 'minecraft:bamboo_mosaic',
        'minecraft:cyan_stained_glass': 'minecraft:yellow_stained_glass',
    },
    2: {   # crimson
        'minecraft:prismarine_bricks': 'minecraft:red_nether_bricks',
        'minecraft:diamond_ore': 'minecraft:redstone_ore',
        'minecraft:dark_prismarine': 'minecraft:crimson_hyphae',
        'minecraft:cyan_stained_glass': 'minecraft:red_stained_glass',
    },
    3: {   # amethyst
        'minecraft:prismarine_bricks': 'minecraft:amethyst_block',
        'minecraft:diamond_ore': 'minecraft:purpur_block',
        'minecraft:dark_prismarine': 'minecraft:purpur_pillar',
        'minecraft:cyan_stained_glass': 'minecraft:purple_stained_glass',
    },
    4: {   # emerald
        'minecraft:prismarine_bricks': 'minecraft:emerald_block',
        'minecraft:diamond_ore': 'minecraft:emerald_ore',
        'minecraft:dark_prismarine': 'minecraft:moss_block',
        'minecraft:cyan_stained_glass': 'minecraft:lime_stained_glass',
    },
    5: {   # lapis
        'minecraft:prismarine_bricks': 'minecraft:lapis_block',
        'minecraft:diamond_ore': 'minecraft:lapis_ore',
        'minecraft:dark_prismarine': 'minecraft:blue_ice',
        'minecraft:cyan_stained_glass': 'minecraft:blue_stained_glass',
    },
    6: {   # obsidian
        'minecraft:prismarine_bricks': 'minecraft:obsidian',
        'minecraft:diamond_ore': 'minecraft:ancient_debris',
        'minecraft:dark_prismarine': 'minecraft:crying_obsidian',
        'minecraft:cyan_stained_glass': 'minecraft:magenta_stained_glass',
    },
}
DECOR_SLAB = {0: 'minecraft:prismarine_slab[type=top]',
              1: 'minecraft:bamboo_mosaic_slab[type=top]',
              2: 'minecraft:crimson_slab[type=top]',
              3: 'minecraft:purpur_slab[type=top]',
              4: 'minecraft:mossy_stone_brick_slab[type=top]',
              5: 'minecraft:dark_prismarine_slab[type=top]',
              6: 'minecraft:blackstone_slab[type=top]'}
DECOR_DOOR = {0: 'minecraft:warped_trapdoor',
              1: 'minecraft:bamboo_trapdoor',
              2: 'minecraft:crimson_trapdoor',
              3: 'minecraft:cherry_trapdoor',
              4: 'minecraft:spruce_trapdoor',
              5: 'minecraft:oxidized_copper_trapdoor',
              6: 'minecraft:dark_oak_trapdoor'}
DECOR_CARPET = {0: 'minecraft:light_blue_carpet',
                1: 'minecraft:yellow_carpet',
                2: 'minecraft:red_carpet',
                3: 'minecraft:purple_carpet',
                4: 'minecraft:lime_carpet',
                5: 'minecraft:blue_carpet',
                6: 'minecraft:magenta_carpet'}




def main():
    print('regenerating maze (seed %d)...' % SEED)
    sim = gm.Sim(SEED)
    assert sim.run(), 'seed %d no longer generates' % SEED
    blks = sim.blocks

    # ---- ordered centerline streams, one per branch ----
    # each stream is the branch's live block chain, prefixed with its
    # cross-branch parent (fork/funnel attachment) and suffixed with a
    # junction block it merges into, so walls flow across attachments
    streams = []
    for br in sim.branches:
        chain = [i for i in br['blocks'] if blks[i] is not None]
        if len(chain) == 0:
            continue
        first = blks[chain[0]]
        if first['prev'] is not None and blks[first['prev']] is not None:
            chain.insert(0, first['prev'])
        for k in sim.kids.get(chain[-1], ()):
            kb = blks[k]
            if kb is not None and kb['prev2'] == chain[-1]:
                chain.append(k)          # merge junction
                break
        streams.append(chain)

    # ---- per-block palette: computed by the shared
    # generate_maze.compute_palette (deterministic in the seed) - the
    # full flip rules (per-branch TRANSITIONS thresholds, fork guard,
    # merge/splice leads, uniform windows, sandwich repairs) live
    # there, shared with emit()'s onward-path fork resolution ----
    pal_blk = gm.compute_palette(sim)

    pal_xyz = {(blks[i]['x'], blks[i]['y'], blks[i]['z']): p
               for i, p in pal_blk.items()}

    # ---- clearance grid over all centerline points (band + margin) ----
    grid = defaultdict(list)

    def grid_add(x, z, y):
        grid[(int(x // 4), int(z // 4))].append((x, z, y))

    def near_center(x, z, y, limit):
        gx, gz = int(x // 4), int(z // 4)
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                for sx, sz, sy in grid.get((gx + dx, gz + dz), ()):
                    if (abs(sy - y) <= CLEAR_DY
                            and math.hypot(sx - x, sz - z) < limit):
                        return True
        return False

    def point_runs(chain):
        # maximal runs of consecutive, validly-linked blocks that carry
        # geometry - each run is one smooth spline domain
        runs, run = [], []
        for a, b in zip(chain, chain[1:]):
            ab, bb = blks[a], blks[b]
            ok = (ab is not None and bb is not None
                  and ab['px'] is not None and bb['px'] is not None
                  and (bb['prev'] == a or bb['prev2'] == a))
            if ok:
                if not run:
                    run = [ab]
                run.append(bb)
            else:
                if run:
                    runs.append(run)
                run = []
        if run:
            runs.append(run)
        return runs

    def cr_pos(p0, p1, p2, p3, t):
        return 0.5 * (2 * p1 + (p2 - p0) * t
                      + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                      + (-p0 + 3 * p1 - 3 * p2 + p3) * t * t * t)

    def cr_der(p0, p1, p2, p3, t):
        return 0.5 * ((p2 - p0)
                      + 2 * (2 * p0 - 5 * p1 + 4 * p2 - p3) * t
                      + 3 * (-p0 + 3 * p1 - 3 * p2 + p3) * t * t)

    def spline_segments(run):
        # per raw chord: (its two blocks, chord length, samples). Each
        # sample is (x, z, y, tx, tz, t) with (tx, tz) the unit
        # tangent and t the position along the chord (0 at the first
        # block, 1 at the second - used for the palette flip point).
        # Endpoints are clamped (duplicated), which halves the end
        # tangents' magnitude but keeps their direction - only the
        # direction is used
        pts = [(b['px'], b['pz'], float(b['y'])) for b in run]
        ext = [pts[0]] + pts + [pts[-1]]
        for i in range(len(pts) - 1):
            p0, p1, p2, p3 = ext[i], ext[i + 1], ext[i + 2], ext[i + 3]
            ln = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
            if ln < 1e-9:
                continue
            steps = max(2, int(ln / STRIDE))
            samples = []
            for s in range(steps + 1):
                t = s / steps
                x = cr_pos(p0[0], p1[0], p2[0], p3[0], t)
                z = cr_pos(p0[1], p1[1], p2[1], p3[1], t)
                y = cr_pos(p0[2], p1[2], p2[2], p3[2], t)
                dx = cr_der(p0[0], p1[0], p2[0], p3[0], t)
                dz = cr_der(p0[1], p1[1], p2[1], p3[1], t)
                dl = math.hypot(dx, dz)
                if dl < 1e-9:
                    continue
                samples.append((x, z, y, dx / dl, dz / dl, t))
            yield run[i], run[i + 1], ln, samples

    stream_runs = [point_runs(chain) for chain in streams]

    for runs in stream_runs:
        for run in runs:
            for b1, b2, ln, samples in spline_segments(run):
                y1, y2 = float(b1['y']), float(b2['y'])
                if y1 < BAND_BOT - CLEAR_DY or y2 > BAND_TOP + CLEAR_DY:
                    continue
                for x, z, y, tx, tz, t in samples:
                    grid_add(x, z, y)

    # ---- walk each stream, emitting wall points per side in order ----
    # cols[(x,z)] = {'bases': {yb}, 'cls': best class, 'out': [outward
    # normals]} cls: 0 panel, 1 pillar, 2 tip (higher wins)
    cols = defaultdict(lambda: {'bases': set(), 'cls': 0, 'out': []})
    pruned = 0
    wall_paths = []

    # palette anchors: every primary pass notes (column, anchor y) ->
    # (palette, in-slice) as it paints; the final recolor pass looks
    # cells up by nearest anchor so derived cells (bands, lines,
    # backdrops, closures) inherit the palette of the geometry that
    # spawned them. Slice wins over palette on collision
    pal_anchor = {}

    def pal_note(cx, cz, ay, pal, sl):
        k = (cx, cz, ay)
        e = pal_anchor.get(k)
        if e is None:
            pal_anchor[k] = [pal, sl]
        elif sl and not e[1]:
            e[1] = True

    # every wall is an ORDERED PATH of column visits per (stream,
    # side), remembering which side of the corridor it is on: entry
    # keys 'key' (column), 'ybs' (base courses the samples touched),
    # 'cls', 'prn' (pruned by another corridor), 'out' (unit outward
    # normal - away from the own corridor), 'pal'/'sl'. The paths are
    # post-processed (slit refill, corner thinning, gap repair, tip
    # marking) before they populate cols - see below
    def wall_point(x, z, y, nx, nz, side, state, pal, sl):
        nonlocal pruned
        wx = x + side * WALL_D * nx
        wz = z + side * WALL_D * nz
        # pillar rhythm from accumulated wall arc-length
        cls = 0
        if state['last'] is not None:
            state['s'] += math.hypot(wx - state['last'][0],
                                     wz - state['last'][1])
        state['last'] = (wx, wz)
        if state['s'] >= RHYTHM:
            state['s'] = 0.0
            cls = 1
        prn = near_center(wx, wz, y, CLEAR)
        if prn:
            pruned += 1
        key = (gm.rnd(wx), gm.rnd(wz))
        yb = int(math.floor(y + 0.5)) + WALL_BASE
        path = state['path']
        if path and path[-1]['key'] == key and path[-1]['prn'] == prn:
            e = path[-1]
            e['ybs'].add(yb)
            e['cls'] = max(e['cls'], cls)
        else:
            path.append({'key': key, 'ybs': {yb}, 'cls': cls,
                         'prn': prn, 'out': (side * nx, side * nz),
                         'pal': pal, 'sl': sl})

    # ---- dome shell points ----
    # dome_cols[(x,z)] = set of shell block y's (may hold clusters from
    # several corridor passes; clustered into runs at emission)
    dome_cols = defaultdict(set)

    def dome_near(wx, wz, yd):
        # prune shell points inside ANOTHER corridor's interior: within
        # CLEAR of a centerline and from 3 below its path (tunnel) to 9
        # above (below that corridor's own shell). The own centerline
        # never matches: directly overhead the shell is 13 above the
        # path, and by the time the arch drops to +9 it is > CLEAR out
        for ddx in (-1, 0, 1):
            for ddz in (-1, 0, 1):
                for sx, sz, sy in grid.get((int(wx // 4) + ddx,
                                            int(wz // 4) + ddz), ()):
                    if (-3 <= yd - sy <= 9
                            and math.hypot(sx - wx, sz - wz) < CLEAR):
                        return True
        return False

    def dome_span(x, z, y, nx, nz, pal, sl):
        # one arch rib across the full corridor width at this sample
        top = int(math.floor(y + 0.5)) + WALL_BASE + WALL_H - 1
        d = -WALL_D
        while d <= WALL_D + 1e-9:
            wx = x + d * nx
            wz = z + d * nz
            rise = math.sqrt(max(0.0, WALL_D * WALL_D - d * d))
            yd = top + max(1, int(round(rise)))
            if not dome_near(wx, wz, yd):
                dome_cols[(gm.rnd(wx), gm.rnd(wz))].add(yd)
                pal_note(gm.rnd(wx), gm.rnd(wz), yd, pal, sl)
            d += STRIDE

    # floor_cols[(x,z)] = set of floor-surface y's
    floor_cols = defaultdict(set)

    def floor_near(wx, wz, yd, py):
        # interior test for FLOOR points only: like dome_near, but a
        # sample prunes only if it sits >= ~2 levels below the rib's
        # own path level. The rib's own corridor (and sibling arms near
        # junctions) descend < 1 level within CLEAR horizontally, so
        # they can never prune their own floor - the plain [-3, 9]
        # window's edge grazed own samples 3-4 blocks ahead just before
        # each level step and punched multi-column trenches in the
        # floor (found at (4978, 288, 2970)). Corridors converging at
        # the same level +-1 now blend 2-thick instead of "lower
        # wins"; true tunnels ~2..13 below still prune
        for ddx in (-1, 0, 1):
            for ddz in (-1, 0, 1):
                for sx, sz, sy in grid.get((int(wx // 4) + ddx,
                                            int(wz // 4) + ddz), ()):
                    if (sy <= py - 1.7 and -3 <= yd - sy <= 9
                            and math.hypot(sx - wx, sz - wz) < CLEAR):
                        return True
        return False

    def floor_span(x, z, y, nx, nz, pal, sl):
        # one flat floor rib at this sample, spanning to just past the
        # wall line so wall-foot cells exist wherever walls step or are
        # pruned (wall-occupied levels are filtered at emission). The
        # same interior test as the dome prunes points in other
        # corridors, guarded by floor_near
        base = int(math.floor(y + 0.5)) + WALL_BASE
        d = -(WALL_D + 0.4)
        while d <= WALL_D + 0.4 + 1e-9:
            wx = x + d * nx
            wz = z + d * nz
            if not floor_near(wx, wz, base, y):
                floor_cols[(gm.rnd(wx), gm.rnd(wz))].add(base)
                pal_note(gm.rnd(wx), gm.rnd(wz), base, pal, sl)
            d += STRIDE

    for runs in stream_runs:
        st = {1.0: {'s': 0.0, 'last': None, 'path': []},
              -1.0: {'s': 0.0, 'last': None, 'path': []}}
        for run in runs:
            for b1, b2, ln, samples in spline_segments(run):
                y1, y2 = b1['y'], b2['y']
                if not (BAND_BOT <= y1 <= BAND_TOP
                        or BAND_BOT <= y2 <= BAND_TOP):
                    continue
                pal1 = pal_xyz.get((b1['x'], b1['y'], b1['z']), 0)
                pal2 = pal_xyz.get((b2['x'], b2['y'], b2['z']), 0)
                for x, z, y, tx, tz, t in samples:
                    pal = pal1 if t < 0.5 else pal2
                    sl = (pal1 != pal2
                          and abs(t - 0.5) * ln <= SLICE_HALF)
                    nx, nz = -tz, tx
                    for side in (1.0, -1.0):
                        wall_point(x, z, y, nx, nz, side, st[side],
                                   pal, sl)
                    dome_span(x, z, y, nx, nz, pal, sl)
                    floor_span(x, z, y, nx, nz, pal, sl)
        wall_paths.append(st[1.0]['path'])
        wall_paths.append(st[-1.0]['path'])

    # ---- wall path post-processing (per wall, per user spec) ----
    # 1. SLIT REFILL: the other-corridor prune can delete just 1-2
    #    columns of a wall (a see-through slit, not a real opening) -
    #    interior pruned runs covering <= 2 unique columns are
    #    unpruned (found in-world at (4766, 146, 3110)).
    # 2. TIP MARKING: the first surviving column on each side of a
    #    remaining pruned run becomes a TIP frame (was inline).
    # 3. CORNER THINNING: no wall block may touch same-wall blocks on
    #    two different axes - a column whose predecessor and successor
    #    are diagonal of each other (or identical: a spur) is an
    #    outside-corner block and is dropped; its pillar class moves
    #    to a neighbour. Turns step diagonally; the lantern layer
    #    behind seals the diagonal cracks.
    # 4. GAP REPAIR: consecutive surviving columns must stay
    #    8-adjacent; anything further apart gets interpolated columns
    #    so a wall can never have a hole.
    slits = corners = gapfill = 0
    for path in wall_paths:
        # 1. slit refill: a pruned run is a slit (not a real opening)
        # when the surviving columns flanking it are still within
        # Chebyshev 3 of each other - at most ~2 columns of wall are
        # missing between them. Real openings (fork mouths, caverns)
        # separate their flanks much further
        i = 0
        while i < len(path):
            if path[i]['prn']:
                j = i
                while j < len(path) and path[j]['prn']:
                    j += 1
                if i > 0 and j < len(path):
                    a = path[i - 1]['key']
                    b = path[j]['key']
                    if max(abs(a[0] - b[0]), abs(a[1] - b[1])) <= 3:
                        uniq = {path[k]['key'] for k in range(i, j)}
                        for k in range(i, j):
                            path[k]['prn'] = False
                        slits += len(uniq)
                i = j
            else:
                i += 1
        # 2. tip marking around remaining pruned runs
        for i, e in enumerate(path):
            if e['prn']:
                continue
            if (i > 0 and path[i - 1]['prn']) \
                    or (i + 1 < len(path) and path[i + 1]['prn']):
                e['cls'] = max(e['cls'], 2)
        # 3+4 operate on the surviving segments
        segs, seg = [], []
        for e in path:
            if e['prn']:
                if seg:
                    segs.append(seg)
                seg = []
            else:
                if seg and seg[-1]['key'] == e['key']:
                    seg[-1]['ybs'] |= e['ybs']
                    seg[-1]['cls'] = max(seg[-1]['cls'], e['cls'])
                else:
                    seg.append(e)
        if seg:
            segs.append(seg)
        final_entries = []
        for seg in segs:
            # 3. corner thinning, iterated to a fixed point
            changed = True
            while changed:
                changed = False
                k = 1
                while k < len(seg) - 1:
                    a, b, c2 = seg[k - 1]['key'], seg[k]['key'], \
                        seg[k + 1]['key']
                    axes = {(abs(b[0] - a[0]), abs(b[1] - a[1])),
                            (abs(b[0] - c2[0]), abs(b[1] - c2[1]))}
                    spur = a == c2
                    corner = (axes == {(1, 0), (0, 1)}
                              and max(abs(a[0] - c2[0]),
                                      abs(a[1] - c2[1])) == 1)
                    if spur or corner:
                        if seg[k]['cls'] == 1:
                            seg[k - 1]['cls'] = max(seg[k - 1]['cls'], 1)
                        del seg[k]
                        if k > 1 and k < len(seg) \
                                and seg[k - 1]['key'] == seg[k]['key']:
                            seg[k - 1]['ybs'] |= seg[k]['ybs']
                            seg[k - 1]['cls'] = max(seg[k - 1]['cls'],
                                                    seg[k]['cls'])
                            del seg[k]
                        corners += 1
                        changed = True
                    else:
                        k += 1
            # 4. gap repair
            k = 0
            while k < len(seg) - 1:
                a, b = seg[k]['key'], seg[k + 1]['key']
                cheb = max(abs(a[0] - b[0]), abs(a[1] - b[1]))
                if cheb > 1:
                    mx = (a[0] + b[0]) // 2
                    mz = (a[1] + b[1]) // 2
                    mid = dict(seg[k])
                    mid['key'] = (mx, mz)
                    mid['ybs'] = set(seg[k]['ybs']) | set(seg[k + 1]['ybs'])
                    mid['cls'] = 0
                    seg.insert(k + 1, mid)
                    gapfill += 1
                else:
                    k += 1
            final_entries.extend(seg)
        # feed cols
        for e in final_entries:
            c = cols[e['key']]
            c['bases'] |= e['ybs']
            c['cls'] = max(c['cls'], e['cls'])
            c['out'].append(e['out'])
            for yb in e['ybs']:
                pal_note(e['key'][0], e['key'][1], yb, e['pal'],
                         e['sl'])
    print('wall paths: %d slit columns refilled, %d corner blocks '
          'thinned, %d gap columns inserted'
          % (slits, corners, gapfill))

    # ---- tuff-brick flank pillars: wall columns adjacent to each dark
    # prismarine pier become full tuff-brick pillars (class 3). Only
    # PANEL columns whose bases align with the pier's (same wall
    # stretch) are converted - tips keep their frame role and stacked
    # wall runs passing nearby at other levels are left alone ----
    for (x, z), c in list(cols.items()):
        if c['cls'] != 1:
            continue
        for dx2 in (-1, 0, 1):
            for dz2 in (-1, 0, 1):
                if dx2 == 0 and dz2 == 0:
                    continue
                nb = cols.get((x + dx2, z + dz2))
                if nb is None or nb['cls'] != 0:
                    continue
                if any(any(abs(by - ny) <= 2 for ny in nb['bases'])
                       for by in c['bases']):
                    nb['cls'] = 3

    # ---- splice shell regions: for each splice, the decoration
    # columns around its window stretch (see header). band maps a
    # window column to the local PATH y range of the stretch; the
    # world-level stamp copies the block tube [path-5, path+14] and the
    # tail column is the window column minus the tp delta
    SHELL_R = 6.5

    def splice_regions():
        regions = []
        for sp in sim.splices:
            # exactly the copied stretch w1..w5 (the tp maps c1<->w1 and
            # the trigger sits on c1/c2), nothing before or past it: the
            # w0 disc overlaps the tail's own approach arc (different
            # curvature than the window's approach - stamping there can
            # push wall columns into the approach corridor), and beyond
            # the dead end lies space with no separation guarantee. The
            # 22.5 deg/bounce curvature occludes sightlines beyond ~4
            # bounces, so neither trim is visible at the swap
            seq = [i for i in sp['win'][1:] if blks[i] is not None
                   and blks[i]['px'] is not None]
            band = {}
            pts = [blks[i] for i in seq]
            for a, b in zip(pts, pts[1:]):
                ddx, ddz = b['px'] - a['px'], b['pz'] - a['pz']
                ln = math.hypot(ddx, ddz)
                steps = max(1, int(ln))
                for s in range(steps + 1):
                    t = s / steps
                    sx = a['px'] + t * ddx
                    sz = a['pz'] + t * ddz
                    sy = a['y'] + t * (b['y'] - a['y'])
                    for cx in range(int(sx - SHELL_R),
                                    int(sx + SHELL_R) + 2):
                        for cz in range(int(sz - SHELL_R),
                                        int(sz + SHELL_R) + 2):
                            if math.hypot(cx - sx, cz - sz) > SHELL_R:
                                continue
                            lo, hi = band.get((cx, cz), (sy, sy))
                            band[(cx, cz)] = (min(lo, sy), max(hi, sy))
            regions.append((sp['delta'], band,
                            blks[sp['win'][1]]['y']))
        regions.sort(key=lambda r: -r[2])   # highest window first
        return regions

    REGIONS = splice_regions()

    # ---- world model: every block the scripts will place, keyed
    # (x,y,z) -> (family, material). Painted dome -> floor -> walls so
    # collisions resolve deterministically ("the wall wins"); the
    # splice stamp then copies final blocks, so tail tubes are
    # guaranteed block-for-block identical to their windows no matter
    # which passes produced them ----
    world = {}

    # recipes per merged vertical run so overlapping spiral columns get
    # ONE base course and ONE trim row
    def run_mats(lo, hi, cls):
        if cls == 1:      # PILLAR: full dark prismarine pier
            return {y: PIER for y in range(lo, hi + 1)}
        if cls == 3:      # TUFF: full tuff-brick flank pillar
            return {y: TUFF for y in range(lo, hi + 1)}
        if cls == 2:      # TIP frame: dark / lantern alternation
            return {y: (TRIM if (y - lo) % 2 == 0 else BODY)
                    for y in range(lo, hi + 1)}
        mats = {y: BODY for y in range(lo + 1, hi)}
        mats[lo] = BASE
        mats[hi] = TRIM
        return mats

    def merged_runs(bases):
        runs = []
        for y in sorted(bases):
            lo, hi = y, y + WALL_H - 1
            if runs and lo <= runs[-1][1] + 1:
                runs[-1][1] = max(runs[-1][1], hi)
            else:
                runs.append([lo, hi])
        return runs

    counts = [0, 0, 0, 0]

    # ---- dome emission: cluster each column's shell y's into runs,
    # dropping any block a wall run already occupies (a higher corridor
    # pass may stand its wall through the vault - the wall wins) ----
    def y_runs(ys):
        runs = []
        for y in sorted(ys):
            if runs and y <= runs[-1][1] + 2:
                runs[-1][1] = y
            else:
                runs.append([y, y])
        return runs

    dome_ncols = 0
    for (x, z), ys in sorted(dome_cols.items()):
        if (x, z) in cols:
            wruns = merged_runs(cols[(x, z)]['bases'])
            ys = {y for y in ys
                  if not any(lo <= y <= hi for lo, hi in wruns)}
        if not ys:
            continue
        dome_ncols += 1
        for lo, hi in y_runs(ys):
            for y in range(lo, hi + 1):
                world[(x, y, z)] = ('dome', DOME)

    # ---- dome pinhole closure: the vault is painted by discrete arch
    # ribs, and at the shell fringe (and at seams between stacked
    # corridors) the rounding can skip a single column, leaving a
    # see-through pinhole in the roof (found in-world at
    # (4831, 285, 2949)). Fill every empty cell whose opposite
    # orthogonal neighbours both hold dome cells within 1 level - the
    # vault sheet demonstrably passes through it - unless a wall run
    # occupies the level (the wall is the shell there). Later floor
    # and wall painting overwrite these cells like any dome cell ----
    dome_ys = defaultdict(set)
    for (x, y, z), (f, m_) in world.items():
        if f == 'dome':
            dome_ys[(x, z)].add(y)
    dome_filled = 0
    for (x, z) in {n for (cx, cz) in dome_ys
                   for n in ((cx + 1, cz), (cx - 1, cz),
                             (cx, cz + 1), (cx, cz - 1), (cx, cz))}:
        wr = merged_runs(cols[(x, z)]['bases']) if (x, z) in cols \
            else ()
        own = dome_ys.get((x, z), ())
        for a, b in (((x - 1, z), (x + 1, z)),
                     ((x, z - 1), (x, z + 1))):
            ya, yb = dome_ys.get(a), dome_ys.get(b)
            if not ya or not yb:
                continue
            for y in {yy + d for yy in ya for d in (-1, 0, 1)}:
                # a true pinhole: the column has no dome sheet of its
                # own anywhere near this level (its own vault, if any,
                # is a different corridor's far above/below) - without
                # this, the rule merely thickens every vault interior
                if any(abs(y - t) <= 3 for t in own):
                    continue
                if any(abs(y - t) <= 1 for t in yb) \
                        and (x, y, z) not in world \
                        and not any(lo <= y <= hi for lo, hi in wr):
                    world[(x, y, z)] = ('dome', DOME)
                    dome_filled += 1
    if dome_filled:
        print('dome pinhole closure: %d cells' % dome_filled)

    # ---- floor cells: single-layer - each cluster collapses to its
    # LOWEST level (junction blends: the lower corridor's floor wins),
    # skip levels a wall run occupies (the wall itself is the floor
    # there), then seal risers: where a 4-neighbour cell sits 2..13
    # below, the higher cell's column extends down to one block above
    # it so level changes never expose the void under the floor (own
    # 1-steps need no seal; deeper drops occur at junction seams and
    # stacked-corridor boundaries) ----
    fcell_levels = defaultdict(list)
    for (x, z), ys in sorted(floor_cols.items()):
        if (x, z) in cols:
            wruns = merged_runs(cols[(x, z)]['bases'])
            ys = {y for y in ys
                  if not any(lo <= y <= hi for lo, hi in wruns)}
        if not ys:
            continue
        fcell_levels[(x, z)].extend([lo, lo] for lo, hi in y_runs(ys))

    # ---- closure pass: seam slots between two nearby corridors (each
    # > span from both centerlines, missed by both floors and both
    # walls thanks to rounding) and any other residual gap. An empty
    # column whose opposite neighbours both have support within 2
    # levels, with no wall run at that level, gets a floor cell at the
    # lower of the two supports; iterate so 2-wide slots close from
    # both sides. Support is a floor top OR a wall run's lo course -
    # the slot right against a wall line (floor on one side, wall base
    # on the other) is the commonest pinhole, and floor-only support
    # left it open (found in-world at (4831, 271, 2949)) ----
    wall_runs_map = {k: merged_runs(cols[k]['bases']) for k in cols}

    def covered(k, lvl, m):
        return any(lo - 1 <= lvl <= hi + 1 for lo, hi in m.get(k, ()))

    def closure_support(k):
        s = [t for _, t in fcell_levels.get(k, ())]
        s += [lo for lo, _hi in wall_runs_map.get(k, ())]
        return s

    def closure_pass():
        total = 0
        for _ in range(4):
            patches = set()
            cand = set()
            for (x, z) in fcell_levels:
                cand.update(((x + 1, z), (x - 1, z),
                             (x, z + 1), (x, z - 1)))
            for (x, z) in wall_runs_map:
                cand.update(((x + 1, z), (x - 1, z),
                             (x, z + 1), (x, z - 1)))
            for (x, z) in cand:
                for a, b in (((x - 1, z), (x + 1, z)),
                             ((x, z - 1), (x, z + 1))):
                    for ta in closure_support(a):
                        for tb in closure_support(b):
                            if abs(ta - tb) > 2:
                                continue
                            lvl = min(ta, tb)
                            if not covered((x, z), lvl, fcell_levels) \
                                    and not covered((x, z), lvl,
                                                    wall_runs_map):
                                patches.add(((x, z), lvl))
            added = 0
            for k, lvl in sorted(patches):
                if not covered(k, lvl, fcell_levels):
                    fcell_levels[k].append([lvl, lvl])
                    added += 1
            if not added:
                break
            total += added
        return total

    patched = closure_pass()

    floor_ncols = len(fcell_levels)
    fcells = []
    for (x, z), clusters in fcell_levels.items():
        for lo, hi in clusters:
            bot = lo
            for nb in ((x - 1, z), (x + 1, z), (x, z - 1), (x, z + 1)):
                for lo2, hi2 in fcell_levels.get(nb, ()):
                    if hi - 13 <= hi2 <= hi - 2:
                        bot = min(bot, hi2 + 1)
            fcells.append((x, hi, bot, z))
    for x, yt, yb, z in fcells:
        for y in range(yb, yt + 1):
            world[(x, y, z)] = ('floor', FLOOR)

    # ---- walls painted last: they overwrite dome and floor wherever
    # they collide ("the wall wins") ----
    for (x, z), c in sorted(cols.items()):
        counts[c['cls']] += 1
        for lo, hi in merged_runs(c['bases']):
            for y, mat in run_mats(lo, hi, c['cls']).items():
                world[(x, y, z)] = ('walls', mat)

    # ---- wall-top seal: at path steps the dome rib above a wall
    # column can quantize a course higher than the run top, leaving a
    # see-through slit between wall top and vault (found in-world at
    # (4911, 113, 3039)). Extend the run top with deepslate up to a
    # dome or wall cell at most 3 above ----
    topseal = 0
    for (x, z), c in sorted(cols.items()):
        for lo, hi in merged_runs(c['bases']):
            if world.get((x, hi + 1, z)) is not None:
                continue
            for k in (2, 3):
                v = world.get((x, hi + k, z))
                if v is None:
                    continue
                if v[0] in ('dome', 'walls'):
                    for yy in range(hi + 1, hi + k):
                        world[(x, yy, z)] = ('walls', WALL_EDGE)
                        topseal += 1
                break
    if topseal:
        print('wall-top seal: %d slit cells closed under the vault'
              % topseal)

    # ---- structural lantern backdrop layer: every wall knows its
    # outside (the 'out' normals - away from its own corridor), and a
    # full second layer of sea lanterns replaces every AIR cell an
    # outside wall face touches, over the run's whole height. This is
    # deterministic geometry, not visibility guessing - the backdrop
    # can no longer have holes, and diagonal thinning cracks show
    # lantern, never void. Cells inside or near another corridor's
    # open interior (within CLEAR+1 of a centerline) are skipped: a
    # wall that survives next to a neighbouring corridor must not
    # shine bare lanterns into it ----
    layer = 0
    for (x, z), c in sorted(cols.items()):
        if not c['out']:
            continue
        dirs = set()
        for ox, oz in c['out']:
            for dx2, dz2 in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if dx2 * ox + dz2 * oz > 0.3:
                    dirs.add((dx2, dz2))
        for lo, hi in merged_runs(c['bases']):
            for dx2, dz2 in dirs:
                nx2, nz2 = x + dx2, z + dz2
                for y in range(lo, hi + 1):
                    p = (nx2, y, nz2)
                    if p in world:
                        continue
                    if near_center(nx2, nz2, y, CLEAR + 1.0):
                        continue
                    world[p] = ('walls', LANTERN)
                    layer += 1
    print('lantern layer: %d backdrop cells behind the walls' % layer)

    # ---- floor edge decoration: the surface ring against the walls
    # becomes prismarine bricks, the next ring inward diamond ore.
    # line_connect adds corner cells so no two line blocks of the same
    # material ever touch only diagonally. Runs BEFORE the splice
    # stamp, so window tubes carry the decoration and every tail
    # copies it identically ----
    ftops = {}
    fys = defaultdict(set)
    for (x, y, z), (f, m_) in world.items():
        if f == 'floor':
            fys[(x, z)].add(y)
    for k, ys in fys.items():
        ftops[k] = [y for y in ys if y + 1 not in ys]

    def floor_top_at(cx, cz, y):
        for yy in ftops.get((cx, cz), ()):
            if abs(yy - y) <= 1:
                return yy
        return None

    def line_connect(cells, convert, passive=()):
        # for each diagonal pair of line cells with no shared
        # orthogonal line cell, convert a block between them (the
        # callback paints it and returns its y, or None if there is
        # nothing convertible); iterate until stable. `passive`
        # cells count as line for pairing and connection - the
        # panel-base prismarine course IS the visual line where it
        # runs along the wall foot - but never initiate a fill
        # between themselves (base-to-base diagonals are the wall's
        # own inherent travel). Active cells scan all four diagonal
        # directions because a passive mate cannot scan back
        idx = defaultdict(set)
        for x, z, y in cells:
            idx[(x, z)].add(y)
        pdx = defaultdict(set)
        for x, z, y in passive:
            pdx[(x, z)].add(y)

        def has(cx, cz, y):
            return (any(abs(yy - y) <= 1
                        for yy in idx.get((cx, cz), ()))
                    or any(abs(yy - y) <= 1
                           for yy in pdx.get((cx, cz), ())))

        grew = True
        while grew:
            grew = False
            for x, z, y in sorted(cells):
                for dx2, dz2 in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
                    if not has(x + dx2, z + dz2, y):
                        continue
                    if has(x + dx2, z, y) or has(x, z + dz2, y):
                        continue
                    for cx, cz in ((x + dx2, z), (x, z + dz2)):
                        cy = convert(cx, cz, y)
                        if cy is not None:
                            cells.add((cx, cz, cy))
                            idx[(cx, cz)].add(cy)
                            grew = True
                            break
        return cells

    def wall_base_at(cx, cz, y):
        # the bottom block of a wall run at surface level: the line may
        # pass through it (panel bases are prismarine already)
        for yy in (y, y - 1, y + 1):
            v = world.get((cx, yy, cz))
            if (v is not None and v[0] == 'walls'
                    and world.get((cx, yy - 1, cz),
                                  ('', ''))[0] != 'walls'):
                return yy
        return None

    def prism_convert(cx, cz, y):
        t = floor_top_at(cx, cz, y)
        if t is not None:
            world[(cx, t, cz)] = ('floor', FLOOR_EDGE)
            return t
        wb = wall_base_at(cx, cz, y)
        if wb is not None:
            world[(cx, wb, cz)] = ('walls', FLOOR_EDGE)
            return wb
        return None

    prism = set()
    for (x, z), ys in ftops.items():
        for y in ys:
            for nx, nz in ((x + 1, z), (x - 1, z),
                           (x, z + 1), (x, z - 1)):
                if any(world.get((nx, yy, nz), (None,))[0] == 'walls'
                       for yy in (y - 1, y, y + 1)):
                    prism.add((x, z, y))
                    world[(x, y, z)] = ('floor', FLOOR_EDGE)
                    break
    # panel bases are prismarine by recipe: the line visually
    # continues through them, so they join the connect pass as
    # passive members - without them, a floor-line cell meeting the
    # base course diagonally across a tuff/pier corner was invisible
    # to the filler and the corner stayed open (one-sided corners)
    prism_bases = set()
    for (x, z), rr in wall_runs_map.items():
        for lo, _hi in rr:
            if world.get((x, lo, z), ('', ''))[1] == FLOOR_EDGE:
                prism_bases.add((x, z, lo))
    prism = line_connect(prism, prism_convert, prism_bases)

    pidx = defaultdict(set)
    for x, z, y in prism:
        pidx[(x, z)].add(y)

    def ore_convert(cx, cz, y):
        t = floor_top_at(cx, cz, y)
        if t is None or any(abs(yy - t) <= 1
                            for yy in pidx.get((cx, cz), ())):
            return None
        world[(cx, t, cz)] = ('floor', FLOOR_TRIM)
        return t

    ore = set()
    for (x, z), ys in ftops.items():
        for y in ys:
            if any(abs(yy - y) <= 1 for yy in pidx.get((x, z), ())):
                continue
            if any(any(abs(yy - y) <= 1 for yy in pidx.get(nb, ()))
                   for nb in ((x + 1, z), (x - 1, z),
                              (x, z + 1), (x, z - 1))):
                ore.add((x, z, y))
                world[(x, y, z)] = ('floor', FLOOR_TRIM)
    ore = line_connect(ore, ore_convert)
    print('floor decor: %d prismarine edge, %d diamond ore trim'
          % (len(prism), len(ore)))

    # ---- wall bands: the same two-line outline in the wall face,
    # against the floor (bottom of each run) and against the dome
    # (top of each run) - see the WALL BANDS header paragraph. The
    # deepslate lines anchor at lo+1 / hi; where an 8-neighbour
    # column holds the same line exactly 1 level further, the line
    # doubles to cover both levels (the corner fill), and the
    # polished line anchors one course past the deepslate span
    # actually painted, doubling by the same rule - so both lines
    # turn every step as an L, never a diagonal-only joint. Bands
    # only repaint blocks the wall family owns, and touch the lo
    # course (where the floor's prismarine line may run) only when
    # the adjacent floorboard sits a block lower and exposes it ----
    NB8 = ((1, 0), (-1, 0), (0, 1), (0, -1),
           (1, 1), (1, -1), (-1, 1), (-1, -1))

    def band_paint(levels, sgn, mat):
        # levels: (x,z) -> [per-run line anchor y]. Extends each
        # anchor one step along sgn (up for bottom lines, down for
        # top lines) wherever a neighbour anchors exactly there,
        # then paints. Returns the spans so the next line inward can
        # stack on what was actually painted
        spans = {}
        painted = doubled = 0
        for (x, z), ys in levels.items():
            ext = []
            for y in ys:
                far = y
                for dx2, dz2 in NB8:
                    if any(ny == y + sgn for ny in
                           levels.get((x + dx2, z + dz2), ())):
                        far = y + sgn
                        break
                ext.append((y, far))
            spans[(x, z)] = ext
        for (x, z), ext in spans.items():
            for y, far in ext:
                if far != y:
                    doubled += 1
                for yy in range(min(y, far), max(y, far) + 1):
                    if world.get((x, yy, z), ('', ''))[0] == 'walls':
                        world[(x, yy, z)] = ('walls', mat)
                        painted += 1
        return spans, painted, doubled

    # the deepslate line at the wall foot is TWO courses tall - lo AND
    # lo+1 - so a floorboard that quantizes a block lower than the run
    # bottom still meets deepslate, never bare base/tuff. (The first
    # attempt detected exposed lo courses case-by-case - flush-floor
    # and line-joint exceptions - and still missed in-world cases;
    # unconditional coverage is the user-chosen fix. The floor line's
    # corner joints through wall bases now read as deepslate ends,
    # which the joint audit and stamp-seam repair accept as closed.)
    wb_bot = {k: [a for lo, hi in rr for a in (lo, lo + 1)]
              for k, rr in wall_runs_map.items()}
    wb_top = {k: [hi for lo, hi in rr]
              for k, rr in wall_runs_map.items()}
    bspan, nb1, db1 = band_paint(wb_bot, 1, WALL_EDGE)
    tspan, nt1, dt1 = band_paint(wb_top, -1, WALL_EDGE)
    pbot = {k: [far + 1 for _, far in ext] for k, ext in bspan.items()}
    ptop = {k: [far - 1 for _, far in ext] for k, ext in tspan.items()}
    _, nb2, db2 = band_paint(pbot, 1, WALL_TRIM)
    _, nt2, dt2 = band_paint(ptop, -1, WALL_TRIM)
    print('wall bands: %d deepslate, %d polished '
          '(%d step corners doubled)'
          % (nb1 + nt1, nb2 + nt2, db1 + dt1 + db2 + dt2))

    # ---- glass depth: sea lanterns inset one block behind the glass
    # skin (see the GLASS DEPTH header paragraph). "Open" cells are
    # found by flood fill: seed the centerline cells, spread through
    # empty world cells, leashed to a coarse (4-block-bucket)
    # envelope around the sampled centerlines so the fill can never
    # run away through an unsealed band edge. Everything the
    # player's air volume can reach is open; everything else at
    # glass height is enclosed wall interior ----
    env = set()
    for gkey, gsamples in grid.items():
        cores = {(int(sx) // 4, int(sz) // 4, int(sy) // 4)
                 for sx, sz, sy in gsamples}
        for cx4, cz4, cy4 in cores:
            for edx in (-2, -1, 0, 1, 2):
                for edz in (-2, -1, 0, 1, 2):
                    for edy in (-1, 0, 1, 2, 3):
                        env.add((cx4 + edx, cz4 + edz, cy4 + edy))

    # the fill is depth-capped: the shell is sealed in cross-section
    # but the tubes have open ends (181 splice-tail dead ends, the
    # band's start and end), so an uncapped fill escapes and paints
    # the whole exterior "open". Every real interior cell is within
    # ~13 geodesic steps of a centerline seed (vault apex 13 up,
    # notches ~6, caverns are seeded by their own arms); a cell
    # behind the wall shell can only be reached by wrapping around a
    # tube end, far beyond the cap
    FLOOD_MAX = 16
    F6 = ((1, 0, 0), (-1, 0, 0), (0, 1, 0),
          (0, -1, 0), (0, 0, 1), (0, 0, -1))

    def flood_open(blocked):
        # geodesic-capped flood of the air the corridors' open space
        # can reach in `blocked` (a world dict). Run pre-stamp to
        # drive lantern placement, and again post-stamp for the
        # audit (the stamp reshapes tail air, so pre-stamp air is
        # stale inside tail tubes)
        opn = set()
        frontier = []
        for gsamples in grid.values():
            for sx, sz, sy in gsamples:
                for sdy2 in (0, 1):
                    c = (gm.rnd(sx), gm.rnd(sy) + sdy2, gm.rnd(sz))
                    if c not in opn and c not in blocked:
                        opn.add(c)
                        frontier.append(c)
        fseen = set(opn)
        for _depth in range(FLOOD_MAX):
            nxt = []
            for x, y, z in frontier:
                for dx2, dy2, dz2 in F6:
                    p = (x + dx2, y + dy2, z + dz2)
                    if p in fseen:
                        continue
                    fseen.add(p)
                    if p in blocked \
                            or (p[0] // 4, p[2] // 4,
                                p[1] // 4) not in env:
                        continue
                    opn.add(p)
                    nxt.append(p)
            frontier = nxt
        return opn

    open_air = flood_open(world)
    print('open-air flood: %d cells (reach %d)'
          % (len(open_air), FLOOD_MAX))

    # ray visibility: an open cell only counts as player-visible if a
    # straight horizontal line from a corridor center reaches it
    # without passing through a solid cell (tried at the cell's own y
    # and one above, from the 4 nearest in-window samples). Radius
    # tests CANNOT work here: corridor air in front of a wall lies
    # 4.2-5.4 from the centerline, crack-plume air BEHIND the wall
    # 5.0-6.5 - the ranges overlap, so every cutoff both bled plumes
    # through (backdrop lanterns scrubbed into dark glass stacks) and
    # blinded real faces (glass columns folded into the lantern
    # layer). The ray decides by geometry: a plume is behind the wall
    # by definition, so its ray is blocked. Cells with no in-window
    # sample at all (over tall merged runs) count visible - the safe
    # side for a wall skin. The memo is cleared after the stamp: the
    # world the rays traverse changes
    vis_memo = {}

    def ray_visible(cx, cy, cz):
        k = (cx, cy, cz)
        if k in vis_memo:
            return vis_memo[k]
        cands = []
        for ddx in (-1, 0, 1):
            for ddz in (-1, 0, 1):
                for sx, sz, sy in grid.get((int(cx // 4) + ddx,
                                            int(cz // 4) + ddz), ()):
                    if -3.6 <= cy - sy <= 12.6:
                        cands.append((math.hypot(sx - cx, sz - cz),
                                      sx, sz))
        ok = False
        if not cands:
            ok = True
        cands.sort()
        for d, sx, sz in cands[:4]:
            for ry in (cy, cy + 1):
                steps = max(2, int(d * 2))
                clear = True
                for i in range(1, steps):
                    t = i / steps
                    c = (gm.rnd(sx + (cx - sx) * t), ry,
                         gm.rnd(sz + (cz - sz) * t))
                    if c[0] == cx and c[2] == cz:
                        continue
                    if world.get(c) is not None:
                        clear = False
                        break
                if clear:
                    ok = True
                    break
            if ok:
                break
        vis_memo[k] = ok
        return ok

    ORTH = ((1, 0), (-1, 0), (0, 1), (0, -1))

    def corridor_facing(cx, cz, y):
        return any((cx + dx2, y + dy2, cz + dz2) in open_air
                   and ray_visible(cx + dx2, y + dy2, cz + dz2)
                   for dx2, dy2, dz2 in F6)

    glass_cells = [pos for pos, v in world.items()
                   if v == ('walls', BODY)]
    facing = {pos: corridor_facing(pos[0], pos[2], pos[1])
              for pos in glass_cells}
    added = conv_wall = conv_glass = 0
    for (x, y, z) in glass_cells:
        if not facing[(x, y, z)]:
            continue
        for dx2, dz2 in ORTH:
            p = (x + dx2, y, z + dz2)
            if p in open_air and ray_visible(p[0], p[1], p[2]):
                continue
            v = world.get(p)
            if v is None:
                # never give a lantern a face on visible open air (at
                # flood fringes near tube ends the cell itself can be
                # enclosed while a neighbour is visible)
                if any((p[0] + a, p[1] + b, p[2] + c) in open_air
                       and ray_visible(p[0] + a, p[1] + b, p[2] + c)
                       for a, b, c in F6):
                    continue
                world[p] = ('walls', LANTERN)
                added += 1
            elif (v[0] == 'walls' and v[1] not in (LANTERN, BODY)
                    and not corridor_facing(p[0], p[2], y)):
                world[p] = ('walls', LANTERN)
                conv_wall += 1
    for (x, y, z) in glass_cells:
        if not facing[(x, y, z)] \
                and world.get((x, y, z)) == ('walls', BODY):
            world[(x, y, z)] = ('walls', LANTERN)
            conv_glass += 1
    print('glass depth: %d glass cells, %d lanterns added behind, '
          '%d buried wall blocks + %d buried glass converted'
          % (len(glass_cells) - conv_glass, added, conv_wall,
             conv_glass))

    pre_stamp_world = dict(world)   # for the bystander repair + dumps

    # ---- world-level splice stamp: copy the window's final block tube
    # [path-5, path+14] over the tail tube, air included (deletions
    # only from path-3 up: below that, local sub-floor blocks - seals,
    # stacked-vault cells - are invisible and removing them could hole
    # a lower corridor's vault). Highest window first so chained
    # splices propagate top-down ----
    deleted_by_stamp = {}
    for (sdx, sdy, sdz), band, _ in REGIONS:
        for (cx, cz), (plo, phi) in band.items():
            for y in range(int(plo) - 5, int(phi) + 15):
                wv = world.get((cx, y, cz))
                tpos = (cx - sdx, y - sdy, cz - sdz)
                if wv is not None:
                    world[tpos] = wv
                    deleted_by_stamp.pop(tpos, None)
                elif y >= plo - 3:
                    if world.pop(tpos, None) is not None:
                        deleted_by_stamp[tpos] = ((cx, y, cz), band)

    # ---- stamp deletion repair: the deletion zone can hole geometry
    # that the swap cannot actually see. Two restorable classes,
    # judged with the pre-stamp open-air flood:
    #  - the WINDOW counterpart of the deleted cell is not reachable
    #    by open air: the difference is invisible from both ends
    #    (bystander corridors' shells, buried tube-edge geometry) -
    #    restore the pre-stamp block outright;
    #  - the counterpart IS visible open space but the deleted cell
    #    was FLOOR whose pit drops onto nothing at the tail (no open
    #    air 1-2 below - at the window the pit opens into a live
    #    corridor, at the tail it lands on a bystander's vault or
    #    void): re-floor it. A fall-through hole is worse than an
    #    identity nick. Copied wall openings and caverns stay open ----
    restored = []
    for tpos, (wpos, dband) in deleted_by_stamp.items():
        if tpos in world:
            continue
        pv = pre_stamp_world.get(tpos)
        if pv is None:
            continue
        if wpos not in open_air:
            world[tpos] = pv
            restored.append(tpos)
        elif pv[0] == 'floor' \
                and (tpos[0], tpos[1] - 1, tpos[2]) not in open_air \
                and (tpos[0], tpos[1] - 2, tpos[2]) not in open_air:
            world[tpos] = pv
            restored.append(tpos)
        elif pv[0] == 'walls' and any(
                nb not in dband
                for nb in ((wpos[0] + 1, wpos[2]), (wpos[0] - 1, wpos[2]),
                           (wpos[0], wpos[2] + 1), (wpos[0], wpos[2] - 1))):
            # boundary notch: the tube edge shaved a LOCAL wall the
            # window legitimately has open air over. Inside the tube
            # the opening is the window's geometry; at the very edge
            # it just cuts a notch out of a wall that visibly runs on
            # (found in-world at (4778, 192-197, 2981)) - local
            # continuity wins at the fringe
            world[tpos] = pv
            restored.append(tpos)
    print('stamp deletion repair: %d of %d deleted blocks restored'
          % (len(restored), len(deleted_by_stamp)))

    # ---- stamp overwrite repair: the copied tube can also LAND
    # non-air window content (its own vault, wall feet) on a cell
    # that is a BYSTANDER corridor's walking surface at the tail
    # (found in-world: a window's vault apex turned another tunnel's
    # gold floor block to blackstone at (4825, 236, 2910)). A wrong
    # block in a floor a player walks on is worse than an identity
    # nick on the tube fringe, so the floor wins: restore the
    # pre-stamp block wherever the pre-stamp cell was a floor-family
    # surface (nothing above it), the stamp changed it to a non-floor
    # family, and a centerline path passes 3.4-5.6 above it within
    # floor reach - the signature of a real walked floor. Cells the
    # stamp kept floor-family (the tail's own floor, copied from the
    # window's) are left to the stamp - identity there is the point
    def walked_floor(tx, ty, tz):
        gx, gz = int(tx // 4), int(tz // 4)
        for ddx in (-1, 0, 1):
            for ddz in (-1, 0, 1):
                for sx, sz, sy in grid.get((gx + ddx, gz + ddz), ()):
                    if (3.4 <= sy - ty <= 5.6
                            and math.hypot(sx - tx, sz - tz)
                            <= WALL_D + 0.6):
                        return True
        return False

    overwrote = 0
    for (sdx, sdy, sdz), band, _ in REGIONS:
        for (cx, cz), (plo, phi) in band.items():
            for y in range(int(plo) - 5, int(phi) + 15):
                t = (cx - sdx, y - sdy, cz - sdz)
                pv = pre_stamp_world.get(t)
                if pv is None or pv[0] != 'floor':
                    continue
                wv = world.get(t)
                if wv is None or wv == pv or wv[0] == 'floor':
                    continue
                if pre_stamp_world.get((t[0], t[1] + 1, t[2])) \
                        is None \
                        and pre_stamp_world.get((t[0], t[1] + 2,
                                                 t[2])) is None \
                        and walked_floor(t[0], t[1], t[2]):
                    world[t] = pv
                    restored.append(t)
                    overwrote += 1
    restored_set = set(restored)
    print('stamp overwrite repair: %d bystander floor surfaces '
          'restored' % overwrote)

    # ---- restoration chase: a restored cell that is itself the
    # WINDOW of another splice must force its value onto that splice's
    # tail copies - the tails were stamped from the pre-restoration
    # content and would diverge (found: a restored bystander floor
    # line cell serving as window to two other tails). Deltas rise
    # strictly window-over-tail, so the chase terminates ----
    forced = 0
    chase = list(restored)
    while chase:
        p = chase.pop()
        pv = world.get(p)
        for (sdx, sdy, sdz), band, _ in REGIONS:
            pl = band.get((p[0], p[2]))
            if pl and int(pl[0]) - 5 <= p[1] < int(pl[1]) + 15:
                q = (p[0] - sdx, p[1] - sdy, p[2] - sdz)
                if q in restored_set:
                    continue        # its own restoration wins
                if world.get(q) != pv:
                    if pv is None:
                        world.pop(q, None)
                    else:
                        world[q] = pv
                    chase.append(q)
                    forced += 1
    if forced:
        print('restoration chase: %d tail copies re-synced' % forced)

    # ---- world-level closure: the stamp can delete a tail floor cell
    # whose window counterpart is open interior (a pit at the window is
    # backed by a live corridor just below; the copied pit at the tail
    # has no backing and would drop the player under the maze). A
    # fall-through hole is worse than a one-column identity nick at the
    # shell edge, so re-close: an empty column flanked on opposite
    # sides by support within 2 levels, with no wall at that level,
    # gets a floor block at the lower support. Support is a floor top
    # OR a wall run's bottom course, matching closure_pass - a slot
    # right against a wall line has wall on one side, not floor ----
    def world_closure():
        filled = 0
        for _ in range(3):
            col_ys = defaultdict(lambda: {'floor': set(), 'walls': set()})
            for (x, y, z), (f, m_) in world.items():
                if f in ('floor', 'walls'):
                    col_ys[(x, z)][f].add(y)

            def tops(k):
                e = col_ys.get(k)
                if e is None:
                    return []
                s = [y for y in e['floor'] if y + 1 not in e['floor']]
                s += [y for y in e['walls'] if y - 1 not in e['walls']]
                return s

            adds = set()
            for (x, z) in list(col_ys):
                for nb in ((x + 1, z), (x - 1, z),
                           (x, z + 1), (x, z - 1)):
                    if nb in col_ys:
                        continue
                    nx, nz = nb
                    for a, b in ((( nx - 1, nz), (nx + 1, nz)),
                                 ((nx, nz - 1), (nx, nz + 1))):
                        for ta in tops(a):
                            for tb in tops(b):
                                if abs(ta - tb) > 2:
                                    continue
                                adds.add((nx, nz, min(ta, tb)))
            # also columns that exist but lack floor/wall at the level
            for (x, z), fam in list(col_ys.items()):
                for a, b in (((x - 1, z), (x + 1, z)),
                             ((x, z - 1), (x, z + 1))):
                    for ta in tops(a):
                        for tb in tops(b):
                            if abs(ta - tb) > 2:
                                continue
                            lvl = min(ta, tb)
                            if any(lvl - 1 <= y <= lvl + 1
                                   for y in fam['floor']) \
                                    or any(lvl - 1 <= y <= lvl + 1
                                           for y in fam['walls']):
                                continue
                            adds.add((x, z, lvl))
            new = [(x, z, lvl) for x, z, lvl in adds
                   if world.get((x, lvl, z)) is None]
            if not new:
                break
            for x, z, lvl in new:
                world[(x, lvl, z)] = ('floor', FLOOR)
                positions.add((x, lvl, z))
                seal_cells.add((x, lvl, z))
            filled += len(new)
        return filled

    positions = set()
    positions.update(restored)
    seal_cells = set()      # closure fills + riser extensions: support
                            # blocks that may exist on only one side of
                            # a splice mapping - the verifier treats
                            # them as sanctioned, like closure andesite
    world_filled = world_closure()

    # closure fills and bystander restorations that land inside
    # another splice's window must propagate to that splice's tail
    # (REGIONS is already sorted highest window first, so chains
    # resolve top-down)
    def propagate_fills(cells):
        added = 0
        for (sdx, sdy, sdz), band, _ in REGIONS:
            for (fx, fy, fz) in list(cells):
                pl = band.get((fx, fz))
                if pl and int(pl[0]) - 5 <= fy < int(pl[1]) + 15:
                    tpos = (fx - sdx, fy - sdy, fz - sdz)
                    if world.get(tpos) is None:
                        world[tpos] = world.get((fx, fy, fz),
                                                ('floor', FLOOR))
                        cells.add(tpos)
                        if world[tpos][0] == 'floor':
                            seal_cells.add(tpos)
                        added += 1
        return added

    world_filled += propagate_fills(positions)

    # ---- world-level riser seal: stamping juxtaposes floor levels
    # from different contexts at tube boundaries; wherever adjacent
    # floor surfaces differ by 2..13 and the higher column does not
    # reach down to one above the lower surface, extend it with
    # andesite. Extensions sit below a walking surface (invisible from
    # above and below the stamp verifier's deletion zone) ----
    fcols2 = defaultdict(set)
    for (x, y, z), (f, m_) in world.items():
        if f == 'floor':
            fcols2[(x, z)].add(y)
    sealed2 = 0
    riser_cells = set()
    for (x, z), ys in sorted(fcols2.items()):
        for t in [y for y in ys if y + 1 not in ys]:
            b = t
            while b - 1 in ys:
                b -= 1
            need = None
            for nb in ((x + 1, z), (x - 1, z), (x, z + 1), (x, z - 1)):
                nys = fcols2.get(nb, ())
                for t2 in [y for y in nys if y + 1 not in nys]:
                    if t - 13 <= t2 <= t - 2:
                        need = t2 + 1 if need is None \
                            else min(need, t2 + 1)
            if need is not None and b > need:
                for y in range(need, b):
                    world[(x, y, z)] = ('floor', FLOOR)
                    riser_cells.add((x, y, z))
                    seal_cells.add((x, y, z))
                sealed2 += b - need
    if sealed2:
        # riser extensions inside a window band must reach the tail
        # too, like closure fills - an unpropagated window-side
        # extension reads as a tail hole to the verifier
        propagate_fills(riser_cells)
        print('world riser seal: %d blocks' % sealed2)

    # ---- post-stamp line repair: tube copying juxtaposes the window's
    # decoration lines with local ones at tube boundaries, leaving
    # diagonal-only joints there. Reconnect them: conversions outside
    # every stamp band are free; conversions inside a band are MIRRORED
    # through the splice mapping (tail and window painted alike,
    # transitively through chains) so tail tubes stay identical to
    # their windows ----
    in_band = set()
    for (sdx, sdy, sdz), band, _ in REGIONS:
        for (cx, cz) in band:
            in_band.add((cx, cz))
            in_band.add((cx - sdx, cz - sdz))

    def mirror_convert(pos, val):
        # paint pos and every splice-mapped image of it, in both
        # directions, to closure - identity is preserved because every
        # copy of the position gets the same block
        work = [pos]
        seen = {pos}
        while work:
            p = work.pop()
            world[p] = val
            for (sdx, sdy, sdz), band, _ in REGIONS:
                pl = band.get((p[0], p[2]))
                if pl and int(pl[0]) - 5 <= p[1] < int(pl[1]) + 15:
                    q = (p[0] - sdx, p[1] - sdy, p[2] - sdz)
                    if q not in seen:
                        seen.add(q)
                        work.append(q)
                pl = band.get((p[0] + sdx, p[2] + sdz))
                if pl and int(pl[0]) - 5 <= p[1] + sdy < int(pl[1]) + 15:
                    q = (p[0] + sdx, p[1] + sdy, p[2] + sdz)
                    if q not in seen:
                        seen.add(q)
                        work.append(q)

    def repair_lines():
        fys2 = defaultdict(set)
        for (x, y, z), (f, m_) in world.items():
            if f == 'floor':
                fys2[(x, z)].add(y)
        tops2 = {k: [y for y in ys if y + 1 not in ys]
                 for k, ys in fys2.items()}
        # walls-family prismarine cells: passive line members, same
        # role as in line_connect. Not restricted to run bottoms -
        # the stamp can juxtapose a window's line cell mid-column at
        # a tail (over a local band row), and it is just as visible
        wbase2 = defaultdict(list)
        for (x, y, z), (f, m_) in world.items():
            if f == 'walls' and m_ == FLOOR_EDGE:
                wbase2[(x, z)].append(y)

        def top2(cx, cz, y):
            for yy in tops2.get((cx, cz), ()):
                if abs(yy - y) <= 1:
                    return yy
            return None

        def mate_at(cx, cz, y, m1):
            # a diagonal line mate: a floor top carrying m1, or (for
            # the edge line) the wall's prismarine base course
            t = top2(cx, cz, y)
            if t is not None and world.get((cx, t, cz),
                                           ('', ''))[1] == m1:
                return t
            if m1 == FLOOR_EDGE:
                for yy in wbase2.get((cx, cz), ()):
                    if abs(yy - y) <= 1:
                        return yy
            return None

        def connected(cx, cz, m1, lo, hi):
            for yy in range(lo, hi + 1):
                v = world.get((cx, yy, cz))
                if v is None:
                    continue
                if v[1] == m1:
                    return True
                if m1 == FLOOR_EDGE and v == ('walls', WALL_EDGE):
                    # the wall-foot band: the line ends into it - a
                    # closed joint, not a break to repair
                    return True
                if m1 == FLOOR_TRIM and v[1] == FLOOR_EDGE:
                    # the ore line ending into the prismarine ring is
                    # equally closed
                    return True
            return False

        fixed = skipped = 0
        for (x, z), ts in sorted(tops2.items()):
            for y in ts:
                v = world.get((x, y, z))
                if not v or v[1] not in (FLOOR_EDGE, FLOOR_TRIM):
                    continue
                m1 = v[1]
                for dx2, dz2 in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
                    y2 = mate_at(x + dx2, z + dz2, y, m1)
                    if y2 is None:
                        continue
                    lo, hi = min(y, y2) - 1, max(y, y2) + 1
                    if connected(x + dx2, z, m1, lo, hi) \
                            or connected(x, z + dz2, m1, lo, hi):
                        continue
                    done = False
                    # prefer an outside-band conversion; fall back to a
                    # mirrored in-band one
                    for banded in (False, True):
                        for cx, cz in ((x + dx2, z), (x, z + dz2)):
                            if ((cx, cz) in in_band) != banded:
                                continue
                            t = top2(cx, cz, y)
                            if t is not None:
                                tv = world.get((cx, t, cz))
                                if m1 == FLOOR_TRIM \
                                        and tv[1] == FLOOR_EDGE:
                                    continue  # never break the edge line
                                if banded:
                                    mirror_convert((cx, t, cz),
                                                   ('floor', m1))
                                else:
                                    world[(cx, t, cz)] = ('floor', m1)
                                done = True
                                break
                            if m1 == FLOOR_EDGE:
                                wb = wall_base_at(cx, cz, y)
                                if wb is not None:
                                    if banded:
                                        mirror_convert((cx, wb, cz),
                                                       ('walls', m1))
                                    else:
                                        world[(cx, wb, cz)] = \
                                            ('walls', m1)
                                    done = True
                                    break
                        if done:
                            break
                    if done:
                        fixed += 1
                    else:
                        skipped += 1
        return fixed, skipped

    tot_fixed = tot_skipped = 0
    for _ in range(8):
        f2, s2 = repair_lines()
        tot_fixed += f2
        tot_skipped = s2
        if not f2:
            break
    print('line repair at stamp seams: %d joints fixed, %d not fixable '
          'outside stamp bands' % (tot_fixed, tot_skipped))

    # ---- tail end-caps: a wall that curves around the last slime of
    # every replica tail, connecting the two side walls smoothly. The
    # cap is a WALL_D-radius half-ring around the end block, painted
    # AFTER the stamp so it replaces the window's phantom continuation
    # with a closed end (the stamped side walls run on behind it,
    # hidden). Solid recipe - base course, prismarine body, dark trim -
    # so it seals the view, recolors with the corridor's palette, and
    # reads as a deliberate dead end. The player teleports 6-7 bounces
    # earlier, so the cap is scenery, never a reachable wall. Columns
    # that already hold wall cells (the side walls at the ring's ends)
    # are left alone, which is what joins the cap to them seamlessly
    cap_cells = set()
    caps = 0
    for sp in sim.splices:
        E = sp['copy'][-1]
        eb = blks[E]
        if eb is None or eb['h'] is None or eb['px'] is None:
            continue
        ex, ez, ey = eb['px'], eb['pz'], eb['y']
        yb = ey + WALL_BASE
        ytop = ey + 10                  # two courses past WALL_H: meets
        pal_e = pal_blk.get(E, 0)       # the dome over the cap rim
        ccols = []
        seen = set()
        steps = max(12, int(WALL_D * 3.4 / STRIDE))
        for s in range(steps + 1):
            a = eb['h'] - 1.66 + 3.32 * s / steps
            key = (gm.rnd(ex + WALL_D * math.cos(a)),
                   gm.rnd(ez + WALL_D * math.sin(a)))
            if key not in seen:
                seen.add(key)
                ccols.append(key)

        def cap_blocked(cx, cz, y):
            # the cell would sit inside a PASSING corridor's carved
            # space (its floor line up to its headroom). The tail's
            # own approach samples stay >= ~4.7 from the radius-5
            # ring, so only foreign corridors ever match
            gx, gz = int(cx // 4), int(cz // 4)
            for dx3 in (-1, 0, 1):
                for dz3 in (-1, 0, 1):
                    for sx, sz, sy in grid.get((gx + dx3, gz + dz3),
                                               ()):
                        if (y - 10 <= sy <= y + 1
                                and math.hypot(sx - cx,
                                               sz - cz) < CLEAR):
                            return True
            return False

        placed_any = False
        for (cx, cz) in ccols:
            if any(world.get((cx, y, cz), (None,))[0] == 'walls'
                   for y in range(yb, ytop + 1)):
                continue                # a real wall column: keep it
            wrote = False
            for y in range(yb, ytop + 1):
                if cap_blocked(cx, cz, y):
                    continue            # a corridor passes here: the
                                        # cap yields its right of way
                mat = (BASE if y == yb else
                       TRIM if y == ytop else BASE)
                world[(cx, y, cz)] = ('walls', mat)
                cap_cells.add((cx, y, cz))
                wrote = True
            if wrote:
                pal_note(cx, cz, yb, pal_e, False)
                placed_any = True
        if placed_any:
            caps += 1
    print('tail end-caps: %d capped of %d splices, %d cap cells'
          % (caps, len(sim.splices), len(cap_cells)))

    # ---- backdrop heal (post-stamp): the tube stamp copies a
    # window's glass skin onto tail columns, but the lantern layer
    # behind the skin can sit just OUTSIDE the copied tube radius -
    # the tail keeps its local (empty) cell and the player sees a
    # dark hole behind the glass (found in-world at (5037, 263, 2964)
    # etc). Re-run the backdrop rule against the FINAL world and its
    # own flood: behind every corridor-facing glass cell, an empty
    # unreachable cell becomes a lantern - or the glass skin itself
    # where visible open air touches it (a bare lantern face on
    # visible air is worse than plain glass). Additions inside a
    # window band chase down to still-empty tail copies; all are
    # filed with the restorations for the tube verifier ----
    open_post = flood_open(world)
    vis_memo.clear()     # the stamp reshaped the world the rays see

    def vis_open(px, py, pz):
        return any((px + a, py + b, pz + c) in open_post
                   and ray_visible(px + a, py + b, pz + c)
                   for a, b, c in F6)

    # ---- lantern audit + scrub run BEFORE the heal, so glass the
    # scrub restores gets its backdrop lanterns from the heal too.
    # A lantern's only job is to glow behind glass: any lantern face
    # on ray-visible open air is wrong (plume-touching backdrop
    # lanterns stay lit). Floating lanterns are removed; exposed-face
    # ones are repainted as the glass skin. Both are deliberate
    # context-local edits, filed with the restorations ----
    lanterns = [pos for pos, v in world.items()
                if v == ('walls', LANTERN)]
    floating2 = sorted(p for p in lanterns if p in open_post)
    touching2 = sorted(
        p for p in lanterns if p not in open_post and vis_open(*p))
    print('lantern audit: %d floating in open air, %d with a face '
          'on open air' % (len(floating2), len(touching2)))
    for p in floating2:
        world.pop(p, None)
        restored_set.add(p)
    for p in touching2:
        world[p] = ('walls', BODY)
        restored_set.add(p)
    if floating2 or touching2:
        print('lantern scrub: %d floating removed, %d exposed '
              'repainted as glass'
              % (len(floating2), len(touching2)))

    # ---- post-stamp wall-foot repaint: the stamp copies the window's
    # wall feet onto the tail, but the floorboard beside the TAIL copy
    # comes from the tail's local context and can sit lower than at
    # the window, re-exposing a base/tuff lo course. Same rule as the
    # band anchors, applied to the post-stamp world - but only where
    # the exposing air is ray-visible: stamped stray wall cells inside
    # the backdrop layer are NOT exposed feet (found in-world at
    # (4890, 107, 3071): backdrop cells deepslated by this pass; they
    # belong to the lantern layer and the heal converts them). Window
    # repaints chase down to still-identical tail copies ----
    fcols3 = defaultdict(set)
    wcols3 = defaultdict(set)
    for (x, y, z), (f, m_) in world.items():
        if f == 'floor':
            fcols3[(x, z)].add(y)
        elif f == 'walls':
            wcols3[(x, z)].add(y)
    feet = 0
    for (x, z), wys in sorted(wcols3.items()):
        for lo in [y for y in wys if y - 1 not in wys]:
            v = world.get((x, lo, z))
            if v[1] == WALL_EDGE:
                continue
            orth = ((x + 1, z), (x - 1, z), (x, z + 1), (x, z - 1))
            exposed = False
            for nx, nz in orth:
                nys = fcols3.get((nx, nz), ())
                if (lo - 1 in nys or lo - 2 in nys) and lo not in nys \
                        and world.get((nx, lo, nz)) is None \
                        and (nx, lo, nz) in open_post \
                        and ray_visible(nx, lo, nz):
                    exposed = True
                    break
            if not exposed:
                continue
            work = [(x, lo, z)]
            seen3 = {(x, lo, z)}
            while work:
                p = work.pop()
                old = world.get(p)
                if old is None or old[0] != 'walls':
                    continue
                world[p] = ('walls', WALL_EDGE)
                restored_set.add(p)
                feet += 1
                for (sdx, sdy, sdz), band, _ in REGIONS:
                    pl = band.get((p[0], p[2]))
                    if pl and int(pl[0]) - 5 <= p[1] < int(pl[1]) + 15:
                        q = (p[0] - sdx, p[1] - sdy, p[2] - sdz)
                        if q not in seen3 and world.get(q) == old:
                            seen3.add(q)
                            work.append(q)
    if feet:
        print('post-stamp wall-foot repaint: %d exposed lo courses'
              % feet)

    # ---- post-stamp wall-top seal: stamping juxtaposes a window's
    # vault with a tail's local wall top (and vice versa), which can
    # leave a 1-2 cell slit between run top and the blackstone above
    # (found in-world at (4911, 113, 3039)). Same rule as the
    # pre-stamp seal, on the post-stamp world; fills are chased down
    # through window bands and filed with the restorations ----
    topseal2 = 0
    for (x, z), wys in sorted(wcols3.items()):
        for t in [y for y in wys if y + 1 not in wys]:
            if world.get((x, t + 1, z)) is not None:
                continue
            for k in (2, 3):
                v = world.get((x, t + k, z))
                if v is None:
                    continue
                if v[0] in ('dome', 'walls'):
                    for yy in range(t + 1, t + k):
                        work = [(x, yy, z)]
                        seen5 = {(x, yy, z)}
                        while work:
                            p = work.pop()
                            if world.get(p) is not None:
                                continue
                            world[p] = ('walls', WALL_EDGE)
                            restored_set.add(p)
                            topseal2 += 1
                            for (sdx, sdy, sdz), band, _ in REGIONS:
                                pl = band.get((p[0], p[2]))
                                if pl and int(pl[0]) - 5 <= p[1] \
                                        < int(pl[1]) + 15:
                                    q = (p[0] - sdx, p[1] - sdy,
                                         p[2] - sdz)
                                    if q not in seen5:
                                        seen5.add(q)
                                        work.append(q)
                break
    if topseal2:
        print('post-stamp wall-top seal: %d slit cells closed'
              % topseal2)

    heal_l = heal_g = heal_w = heal_b = 0
    post_glass = [pos for pos, v in world.items()
                  if v == ('walls', BODY)]
    for (x, y, z) in post_glass:
        if not vis_open(x, y, z):
            # post-stamp buried glass: a window's skin stamped into a
            # tail position that is enclosed there (dark glass stacks
            # in the backdrop, found at (4806, 116-119, 2959)) folds
            # into the lantern layer, like conv_glass at placement -
            # but ONLY when a viewer actually sees it: through an
            # adjacent visible glass face. Glass sealed off entirely
            # (the phantom continuation behind an end cap) is left
            # alone - folding it would be 13k invisible diffs
            if world.get((x, y, z)) == ('walls', BODY) \
                    and any(world.get((x + a, y + b, z + c))
                            == ('walls', BODY)
                            and vis_open(x + a, y + b, z + c)
                            for a, b, c in F6):
                world[(x, y, z)] = ('walls', LANTERN)
                restored_set.add((x, y, z))
                heal_b += 1
            continue
        for dx2, dz2 in ORTH:
            p = (x + dx2, y, z + dz2)
            if p in open_post and ray_visible(p[0], p[1], p[2]):
                continue        # real visible air in front of a face
            pv2 = world.get(p)
            if pv2 is not None:
                # stamped stray wall material inside the backdrop
                # layer (bands, bases): buried behind facing glass,
                # it belongs to the lantern layer - conv_wall's
                # post-stamp analog
                if pv2[0] == 'walls' \
                        and pv2[1] not in (LANTERN, BODY) \
                        and not vis_open(p[0], p[1], p[2]):
                    world[p] = ('walls', LANTERN)
                    restored_set.add(p)
                    heal_w += 1
                continue
            vis = vis_open(p[0], p[1], p[2])
            val = ('walls', BODY if vis else LANTERN)
            work2 = [p]
            seen4 = {p}
            while work2:
                q = work2.pop()
                if world.get(q) is not None:
                    continue
                world[q] = val
                restored_set.add(q)
                if vis:
                    heal_g += 1
                else:
                    heal_l += 1
                for (sdx, sdy, sdz), band, _ in REGIONS:
                    pl = band.get((q[0], q[2]))
                    if pl and int(pl[0]) - 5 <= q[1] < int(pl[1]) + 15:
                        r = (q[0] - sdx, q[1] - sdy, q[2] - sdz)
                        if r not in seen4:
                            seen4.add(r)
                            work2.append(r)
    if heal_l or heal_g or heal_w or heal_b:
        print('backdrop heal: %d lanterns, %d glass skin cells added, '
              '%d stray wall cells + %d buried glass folded to '
              'lantern post-stamp' % (heal_l, heal_g, heal_w, heal_b))

    # verify: after stamping and closure, every tail tube must match
    # its window tube block-for-block. Allowed deviations, counted
    # separately: sub-floor remnants below path-3 (hidden under the
    # floor), closure fills (tail-only andesite where the window has a
    # pit the tail cannot safely copy), and band-EDGE remnants - rows
    # under the floor line or above the dome, where structures of
    # OTHER stacked corridors poke into the compared band. Those rows
    # are outside the corridor interior the player can see, and a
    # denser maze stacks corridors 14-16 apart routinely, so they are
    # not seam breaks. 'visible mismatches' is only the interior band
    mism = hidden = fills = rest = edges = capx = 0
    mism_list = []
    for (sdx, sdy, sdz), band, _ in REGIONS:
        for (cx, cz), (plo, phi) in band.items():
            for y in range(int(plo) - 5, int(phi) + 15):
                tpos2 = (cx - sdx, y - sdy, cz - sdz)
                wv = world.get((cx, y, cz))
                tv = world.get(tpos2)
                wm = wv[1] if wv else None
                tm = tv[1] if tv else None
                if wm is None and tm is not None and y < plo - 3:
                    hidden += 1
                elif tpos2 in restored_set or (cx, y, cz) in restored_set:
                    rest += 1    # a deliberate context-local edit on
                                 # either side (repairs, heals, scrubs)
                elif wm is None and tm == FLOOR:
                    fills += 1
                elif tm == FLOOR and tpos2 in seal_cells:
                    fills += 1       # tail-side seal support under
                                     # stamped window content
                elif wm == FLOOR and (cx, y, cz) in seal_cells:
                    fills += 1       # window-side seal support the
                                     # tail copy did not need
                elif tpos2 in cap_cells or (cx, y, cz) in cap_cells:
                    capx += 1        # tail end-cap: the window side
                                     # legitimately continues here
                                     # (window side: another tail's
                                     # cap ring grazes this window)
                elif wm != tm:
                    if y < plo - 3 or y > phi + 12:
                        edges += 1
                    else:
                        mism += 1
                        mism_list.append(((cx, y, cz), wm, tpos2, tm))
    print('splice tubes: %d stamped, %d visible mismatches, '
          '%d band-edge remnants, %d cap cells in band, '
          '%d closure fills, %d deletion-repair blocks, '
          '%d hidden sub-floor remnants, %d world-closure blocks'
          % (len(REGIONS), mism, edges, capx, fills, rest, hidden,
             world_filled))
    for w, wm, t, tm in mism_list[:12]:
        print('  mismatch: win %s=%s  tail %s=%s'
              % (w, (wm or '-').replace('minecraft:', ''),
                 t, (tm or '-').replace('minecraft:', '')))

    # ---- decoration-line joint audit: no two visually-prismarine
    # line blocks (floor line or wall base course) may meet only
    # diagonally, except base-to-base pairs (the wall's own travel);
    # same check for the diamond ore line. A deepslate wall-foot
    # course at the corner closes a prismarine joint too (the line
    # deliberately ends into the band there - the same acceptance
    # the stamp-seam line repair uses) ----
    def joint_audit(mat):
        cs = defaultdict(list)
        wedge = defaultdict(set)
        for (x, y, z), (f, m_) in world.items():
            if m_ == mat:
                cs[(x, z)].append((y, f))
            elif (mat == FLOOR_EDGE and f == 'walls'
                    and m_ == WALL_EDGE):
                wedge[(x, z)].add(y)
            elif mat == FLOOR_TRIM and m_ == FLOOR_EDGE:
                # the ore line ending into the prismarine ring is a
                # closed joint (thinned wall corners put the ring on
                # the ore line's corner cell)
                wedge[(x, z)].add(y)
        broken = set()
        for (x, z), ys in cs.items():
            for y, f in ys:
                for dx2, dz2 in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
                    mates = [(yy, ff) for yy, ff in
                             cs.get((x + dx2, z + dz2), ())
                             if abs(yy - y) <= 1]
                    if not mates:
                        continue
                    if f == 'walls' and all(ff == 'walls'
                                            for yy, ff in mates):
                        continue
                    if any(abs(yy - y) <= 1 for yy, ff in
                           cs.get((x + dx2, z), ())) \
                            or any(abs(yy - y) <= 1 for yy, ff in
                                   cs.get((x, z + dz2), ())):
                        continue
                    if any(abs(yy - y) <= 1 for yy in
                           wedge.get((x + dx2, z), ())) \
                            or any(abs(yy - y) <= 1 for yy in
                                   wedge.get((x, z + dz2), ())):
                        continue
                    broken.add(tuple(sorted(((x, z, y),
                                             (x + dx2, z + dz2,
                                              mates[0][0])))))
        return sorted(broken)

    for label, mat in (('prismarine', FLOOR_EDGE),
                       ('diamond ore', FLOOR_TRIM)):
        bj = joint_audit(mat)
        # below-band joints sit on stamped tube shells around
        # sub-band splice tails, in bare undecorated space with
        # nothing local to connect to - noise, reported separately
        inb = [p for p in bj if p[0][2] >= BAND_BOT - 5]
        print('line joint audit: %d diagonal-only %s joints in band '
              '(%d more on sub-band stamped shells)'
              % (len(inb), label, len(bj) - len(inb)))
        for pair in inb[:6]:
            print('  %s <-> %s' % pair)

    # ---- palette recolor: runs LAST, after every base-palette pass,
    # stamp and audit (all of which reason in base materials). Each
    # cell takes the palette of its nearest anchor - own column
    # first, then the 8 plan-neighbours for derived cells (backdrop
    # lanterns, closure fills) whose column no primary pass touched.
    # Slice anchors win: the whole cross-section there (walls, bands,
    # lines, glass, floor, vault) becomes one clean netherite ring.
    # Stamped tail tubes recolor by the TAIL's anchors, which the
    # splice overrides made equal to their window counterparts', so
    # tubes stay identical across the swap ----
    pal_map = defaultdict(list)
    for (cx, cz, ay), (p, sl) in pal_anchor.items():
        pal_map[(cx, cz)].append((ay, p, sl))

    def cell_pal(x, y, z):
        best = None
        for dx3, dz3 in ((0, 0),) + NB8:
            for ay, p, sl in pal_map.get((x + dx3, z + dz3), ()):
                d = abs(y - ay) + (0.0 if dx3 == 0 and dz3 == 0
                                   else 0.5)
                if d <= 16 and (best is None or d < best[0]):
                    best = (d, p, sl)
        return (0, False) if best is None else (best[1], best[2])

    recolored = sliced = 0
    for pos, (fam, mat) in list(world.items()):
        p, sl = cell_pal(pos[0], pos[1], pos[2])
        if sl:
            world[pos] = (fam, NETHER_SLICE)
            sliced += 1
        elif p:
            nm = PALETTES[p].get(mat)
            if nm is not None:
                world[pos] = (fam, nm)
                recolored += 1
    print('palette recolor: %d cells recolored, %d netherite '
          'slice cells' % (recolored, sliced))

    if os.environ.get('WT_DUMP'):
        import pickle
        with open(os.path.join(HERE, 'wt_debug.pkl'), 'wb') as fh:
            pickle.dump({
                'pre_world': pre_stamp_world,
                'world': dict(world),
                'grid': dict(grid),
                'regions': REGIONS,
                'cols': {k: (tuple(sorted(c['bases'])), c['cls'])
                         for k, c in cols.items()},
                'cap_cells': cap_cells,
                'restored': restored_set,
                'open_air': open_air,
                'open_post': open_post,
                'env': env,
            }, fh)
        print('debug dump written to wt_debug.pkl')

    # ---- emission from the world: per family, vertical runs of one
    # material per column, then identical runs merged across
    # consecutive z ----
    def family_groups(fam):
        cells = defaultdict(dict)
        for (x, y, z), (f, mat) in world.items():
            if f == fam:
                cells[(x, z)][y] = mat
        vruns = []
        for (x, z), ys in sorted(cells.items()):
            run = None
            for y in sorted(ys):
                if run and y == run[1] + 1 and ys[y] == run[2]:
                    run[1] = y
                else:
                    if run:
                        vruns.append((x, run[0], run[1], run[2], z))
                    run = [y, y, ys[y]]
            if run:
                vruns.append((x, run[0], run[1], run[2], z))
        vruns.sort()
        zr = []
        for x, ylo, yhi, mat, z in vruns:
            if zr and zr[-1][0] == x and zr[-1][1] == ylo \
                    and zr[-1][2] == yhi and zr[-1][3] == mat \
                    and zr[-1][5] == z - 1:
                zr[-1][5] = z
            else:
                zr.append([x, ylo, yhi, mat, z, z])
        build, undo = [], []
        for x, ylo, yhi, mat, z1, z2 in zr:
            anchor = (x, yhi, (z1 + z2) // 2)
            if yhi > ylo or z2 > z1:
                cmd = ('@bypass /fill %d %d %d %d %d %d %s strict'
                       % (x, ylo, z1, x, yhi, z2, mat))
            else:
                cmd = ('@bypass /setblock %d %d %d %s strict'
                       % (x, ylo, z1, mat))
            build.append((anchor, [cmd]))
            undo.append((anchor, [
                '@bypass /fill %d %d %d %d %d %d minecraft:air strict'
                % (x, ylo, z1, x, yhi, z2)]))
        return build, undo

    build_groups, undo_groups = family_groups('walls')
    dome_build, dome_undo = family_groups('dome')
    floor_build, floor_undo = family_groups('floor')

    # ---- slime-block dressing: light blue carpet above every bounce
    # block with a full-bright light block above the carpet, a top
    # prismarine slab below it, and open warped
    # trapdoors hugging all four sides (facing away from the block,
    # bottom half, open - the open panels press flush against the
    # slime faces). Cells holding another slime block, an earlier
    # dressing cell, or a decoration-world block (walls/floor/dome
    # at tight seams) are skipped, so build order cannot matter.
    # Identical per block by construction, so splice tails match
    # their windows without stamping ----
    seen_b = set()
    live = []
    for br in sim.branches:
        for i in br['blocks']:
            if i not in seen_b and blks[i] is not None:
                seen_b.add(i)
                live.append(blks[i])
    slime_pos = {(b['x'], b['y'], b['z']) for b in live}
    claimed = {}
    skipped_d = 0
    for b in live:
        x, y, z = b['x'], b['y'], b['z']
        bp = pal_xyz.get((x, y, z), 0)
        slab_mat = DECOR_SLAB[bp]
        door = DECOR_DOOR[bp]
        for pos, mat in (
                ((x, y + 1, z), DECOR_CARPET[bp]),
                ((x, y + 2, z), 'minecraft:light[level=15]'),
                ((x, y - 1, z), slab_mat),
                ((x + 1, y, z), door +
                 '[facing=east,half=bottom,open=true]'),
                ((x - 1, y, z), door +
                 '[facing=west,half=bottom,open=true]'),
                ((x, y, z + 1), door +
                 '[facing=south,half=bottom,open=true]'),
                ((x, y, z - 1), door +
                 '[facing=north,half=bottom,open=true]')):
            if pos in slime_pos or pos in claimed \
                    or world.get(pos) is not None:
                skipped_d += 1
                continue
            claimed[pos] = mat
    decor_build = [(pos, ['@bypass /setblock %d %d %d %s strict'
                          % (pos[0], pos[1], pos[2], mat)])
                   for pos, mat in sorted(claimed.items())]
    decor_undo = [(pos, ['@bypass /setblock %d %d %d minecraft:air '
                         'strict' % pos])
                  for pos in sorted(claimed)]
    print('slime dressing: %d bounce blocks, %d dressing cells '
          '(%d skipped: occupied)'
          % (len(live), len(claimed), skipped_d))

    def split(groups):
        # spatial emission: bucket the (anchor, lines) groups into
        # REGION x REGION cells; per bucket teleport once to the center
        # of its blocks, @delay 10 ticks so the chunks around the player
        # load, then place everything in the bucket (all of it within
        # ~4 chunks of the player). A part boundary inside a bucket
        # re-emits the tp + delay at the top of the next part
        buckets = defaultdict(list)
        for anchor, lines in groups:
            buckets[(anchor[0] // REGION,
                     anchor[2] // REGION)].append((anchor, lines))
        parts, cur, n = [], [], 0
        for key in sorted(buckets):
            items = buckets[key]
            xs = [a[0] for a, _ in items]
            ys = [a[1] for a, _ in items]
            zs = [a[2] for a, _ in items]
            hdr = ['@bypass tp %d %d %d'
                   % ((min(xs) + max(xs)) // 2, max(ys) + 2,
                      (min(zs) + max(zs)) // 2),
                   '@delay 10']
            pending_hdr = True
            for anchor, lines in items:
                need = len(lines) + (len(hdr) if pending_hdr else 0)
                if cur and n + need > gm.MAX_PART_LINES:
                    parts.append(cur)
                    cur, n = [], 0
                    pending_hdr = True
                    need = len(lines) + len(hdr)
                if pending_hdr:
                    cur.extend(hdr)
                    pending_hdr = False
                cur.extend(lines)
                n += need
        if cur:
            parts.append(cur)
        return parts

    def write(path, lines):
        with open(path, 'w', newline='\n') as fh:
            fh.write('\n'.join(lines).rstrip('\n') + '\n')

    fndir = os.path.join(HERE, gm.NAMESPACE)
    # clear stale wall parts from previous runs - the part count can
    # shrink, and a leftover wallsN.msc would import as an undeclared,
    # never-called function
    for old in os.listdir(fndir):
        if re.fullmatch(r'(?:remove)?(?:walls|dome|floor|decor)\d+\.msc',
                        old):
            os.remove(os.path.join(fndir, old))
    names = []
    for name, groups, done in (('walls', build_groups,
                                '&aWall test built!'),
                               ('removewalls', undo_groups,
                                '&aWall test removed.'),
                               ('dome', dome_build,
                                '&aDome built!'),
                               ('removedome', dome_undo,
                                '&aDome removed.'),
                               ('floor', floor_build,
                                '&aAndesite floor built!'),
                               ('removefloor', floor_undo,
                                '&aAndesite floor removed.'),
                               ('decor', decor_build,
                                '&aSlime dressing built!'),
                               ('removedecor', decor_undo,
                                '&aSlime dressing removed.')):
        parts = split(groups)
        for k, body in enumerate(parts, 1):
            head = ['# %s%d(Player player)' % (name, k),
                    '# DRAFT decorated curvature walls, part %d of %d'
                    % (k, len(parts)),
                    '# band y %d..%d, offset %.1f, height %d, seed %d'
                    % (BAND_BOT, BAND_TOP, WALL_D, WALL_H, SEED),
                    '', '@using %s' % gm.NAMESPACE, '']
            tail = (['', '@var %s%d(player)' % (name, k + 1)]
                    if k < len(parts)
                    else ['', gm.DONE_SOUND, '@player %s' % done])
            write(os.path.join(fndir, '%s%d.msc' % (name, k)),
                  head + body + tail)
            names.append('%s%d' % (name, k))

    # rewrite the wall declarations inside the namespace block: drop any
    # stale wallsN/removewallsN lines, then insert the current set just
    # before @endnamespace (idempotent across reruns)
    nms_path = os.path.join(HERE, '%s.nms' % gm.NAMESPACE)
    nms_lines = [l for l in open(nms_path).read().splitlines()
                 if not re.fullmatch(r'\s*(?:remove)?'
                                     r'(?:walls|dome|floor|decor)'
                                     r'\d+\(Player player\)\s*', l)]
    if '@endnamespace' not in nms_lines:
        nms_lines.append('@endnamespace')
    at = nms_lines.index('@endnamespace')
    nms_lines[at:at] = ['    %s(Player player)' % n for n in names]
    with open(nms_path, 'w', newline='\n') as fh:
        fh.write('\n'.join(nms_lines) + '\n')

    # audit: built wall columns (post-stamp, from the world) whose run
    # bottom sits close to ANY centerline sample; list each offender
    # with its distance and the vertical gap to the sample so
    # stacked-corridor coincidences are recognizable. dy -12 = benign
    # vault-piercing over a stacked corridor; a '(capped)' row has a
    # floor or dome cell directly above the run bottom - a stamped
    # tail-tube remnant buried under the passing corridor's own floor,
    # equally benign (verified against the world model 2026-08-05)
    audit_bases = defaultdict(list)
    for (x, y, z), (f, mat) in world.items():
        if f == 'walls':
            audit_bases[(x, z)].append(y)
    bad = []
    for (x, z), wys in audit_bases.items():
        wys = sorted(wys)
        for i, yb in enumerate(wys):
            if i and wys[i - 1] == yb - 1:
                continue                     # not a run bottom
            top = yb
            j = i
            while j + 1 < len(wys) and wys[j + 1] == wys[j] + 1:
                top = wys[j + 1]
                j += 1
            best = None
            for ddx in (-1, 0, 1):
                for ddz in (-1, 0, 1):
                    for sx, sz, sy in grid.get((int(x // 4) + ddx,
                                                int(z // 4) + ddz), ()):
                        d = math.hypot(sx - x, sz - z)
                        if (abs(sy - yb) <= CLEAR_DY and d < CLEAR - 0.8
                                and (best is None or d < best[0])):
                            best = (d, sy)
            if best:
                bad.append((x, z, yb, top, best[0], best[1]))
    for x, z, yb, top, d, sy in bad:
        capped = any(world.get((x, yb + up, z), (None,))[0]
                     in ('floor', 'dome') for up in (1, 2))
        note = ('  (capped)' if capped else
                '  (run tops at %d, below that corridor)' % top
                if top <= sy - 2 else '')
        print('too-close column (%d, %d) base y=%d: %.2f from a '
              'centerline sample at y=%.1f (dy %+.1f)%s'
              % (x, z, yb, d, sy, sy - yb, note))
    print('columns: %d (panel %d, pillar %d, tip %d, tuff %d)  '
          'dome cols: %d  floor cols: %d (%d hole-patched)  '
          'pruned pts: %d  too-close: %d'
          % (sum(counts), counts[0], counts[1], counts[2], counts[3],
             dome_ncols, floor_ncols, patched, pruned, len(bad)))
    print('functions: %s' % ', '.join(names))
    print('run:  /function execute %s::walls1(Player("You"))'
          % gm.NAMESPACE)
    print('undo: /function execute %s::removewalls1(Player("You"))'
          % gm.NAMESPACE)
    print('dome: /function execute %s::dome1(Player("You"))'
          % gm.NAMESPACE)
    print('undo: /function execute %s::removedome1(Player("You"))'
          % gm.NAMESPACE)
    print('floor: /function execute %s::floor1(Player("You"))'
          % gm.NAMESPACE)
    print('undo:  /function execute %s::removefloor1(Player("You"))'
          % gm.NAMESPACE)
    print('decor: /function execute %s::decor1(Player("You"))'
          % gm.NAMESPACE)
    print('undo:  /function execute %s::removedecor1(Player("You"))'
          % gm.NAMESPACE)


if __name__ == '__main__':
    main()
