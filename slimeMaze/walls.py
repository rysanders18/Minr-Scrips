# walls.py - decoration rework, stage 1: smooth gap-free smooth_stone
# walls (see WALLS_PLAN.md for the locked decisions).
#
# Replaces wall_test.py's offset-curve painter with a FOOTPRINT approach:
# instead of sampling the wall curve and quantizing wall points to
# columns (the source of the old 1-block jitter and gap risk), the
# corridor INTERIOR is rasterized per y-slice and the wall is its
# boundary - gap-free, exactly 1 thick, inner corners filled and outer
# corners open, all by construction.
#
#   1. The slime centerline is Catmull-Rom-sampled per branch stream
#      (the spline passes exactly through every block center - the path
#      itself is untouched, this script only reads it).
#   2. Every sample opens a disc of corridor air on the y-slices of its
#      band [path-4, path+6]. Per slice, each plan cell's field value is
#      its horizontal distance to the nearest covering sample. Cells of
#      ALL corridors union into one region, so forks, junctions and
#      close corridors merge into shared caverns and the wall only ever
#      traces the outside (the "merged caverns" decision).
#   3. Openness: d <= 4.0 is hard-open (the wall may NEVER be closer
#      than 4 blocks to the centerline - hard user requirement),
#      d >= 5.5 is hard-outside, 4.0 < d < 5.5 is flexible - the
#      smoothness drift budget. Init open at d < 4.5, then a
#      synchronous cellular relaxation on flexible cells irons out
#      1-cell bumps (open, <= CLOSE_TH open 8-neighbours -> close) and
#      dents (closed, >= OPEN_TH open 8-neighbours -> open), leaving
#      long clean runs.
#   4. Wall = cells 4-adjacent to the slice's open set, not open
#      themselves, and NOT open on the slice below: a cell that is
#      corridor air one level down is a CEILING TRANSITION (the band
#      stepping down with the descending path), and walling it would
#      hang a floating ribbon across the tunnel. Cells open only on the
#      slice above (floor-side transitions) DO get walls - they are the
#      1-block risers of the future floor steps and keep every slice
#      laterally sealed. A vertical hole-fill closes 1-slice gaps in a
#      column (band-step seams).
#   5. SPLICE STAMP: the seamless teleports demand tail == window, so
#      for every splice (highest window first, so chains propagate
#      top-down) the window tube - columns within SHELL_R of the window
#      stretch, wall band in y, air included - is copied over the tail
#      tube. STAMP WINS, no repair: Phase 5 (V3_PLAN.md) proved that
#      reverting stamped cells trades an intrusion for a see-through
#      hole; both are wall errors and identity at least keeps the swap
#      invisible. The verifier REPORTS both classes exactly (the open
#      model makes the old distance heuristics unnecessary):
#      stamped wall cells inside corridor air (intrusions) and seal
#      breaks inside tail tubes (holes).
#   6. Verification runs on the FINAL post-stamp model (the Phase 5
#      lesson): per-slice seal, 1-thickness, path/trigger clearance,
#      drift histogram, bump/dent smoothness count.
#   7. Later stages share the file: lantern wrap, floor plates with
#      andesite/stone spiderweb texture (splice-copied so teleport
#      sections stay identical - see texture_floor), prismarine and
#      diamond floor outlines, wall trim courses, and the blackstone
#      dome vault (paint_dome - the vertical enclosure gate 1 defers).
#
# Emission: vertical runs per column collapsed into /fill (identical
# runs further merged across consecutive z), bucketed into REGION x
# REGION cells with one tp + @delay 10 per bucket (setblock/fill fail
# silently in unloaded chunks), chained as walls1..N.msc /
# removewalls1..N.msc under MAX_PART_LINES (hastebin cap). The
# walls/removewalls declarations are rewritten into the sandbox's
# slimemaze.nms, and stale walls/dome/floor parts and declarations are
# dropped (stage 1 has no dome or floor).
#
# Usage:
#   python emit_sandbox.py 2 v3_seed2        (once: emit the maze)
#   python walls.py v3_seed2 --preview       (render PNG slices, no emit)
#   python walls.py v3_seed2                 (paint + stamp + verify + emit)
#   python walls.py v3_seed2 --install Slimemaze
#       (also run make_datapack.py --src ... --install Slimemaze)
# The sim build is cached in <dir>/walls_cache.pkl (invalidated by
# seed); --fresh forces a rebuild.

import argparse
import math
import os
import pickle
import random
import re
import subprocess
import sys
import time
from collections import defaultdict, deque

import generate_maze_v3 as gm

HERE = os.path.dirname(os.path.abspath(__file__))

BAND_LO, BAND_HI = -4, 6   # wall column spans [path-4, path+6]
HARD_OPEN = 4.0            # d <= this: always corridor air. HARD
                           # REQUIREMENT (2026-08-13): the wall may
                           # NEVER sit closer than 4 blocks to the
                           # centerline - this floor enforces it for
                           # the painter AND the stamp guard (the
                           # earlier "narrower ~4" calibration with
                           # walls from d 3.5 was taken back)
OPEN_INIT = 4.5            # initial open threshold: wall line ~4.5-5.5
HARD_OUT = 5.5             # d >= this: never opened by relaxation
FIELD_R = 6.0              # per-sample cell scan radius (> HARD_OUT)
STRIDE = 1.0               # spline sampling stride (field accuracy
                           # gain below 1.0 is < the +-1 drift budget)
CLOSE_TH = 3               # open flexible cell closes at <= this many
OPEN_TH = 5                # closed flexible cell opens at >= this many
RELAX_MAX = 12             # relaxation iteration cap per slice
SHELL_R = 6.5              # splice tube radius (matches wall_test)
REGION = 128               # emission bucket (8 chunks)
WORLD_MIN_Y = -76          # decoration floor. The maze is SHIFTED
                           # DOWN 8 (Ryan 2026-08-16: top 314->306);
                           # its lowest slime sits at -72, below the
                           # vanilla world floor. Decoration models
                           # the full geometry; commands below y=-64
                           # simply fail in-game (accepted - Ryan is
                           # hand-building an end room down there)
MAT = 'minecraft:smooth_stone'
GLASS_MAT = 'minecraft:cyan_stained_glass'  # wall body (panel glass)
LANTERN = 'minecraft:sea_lantern'
FLOOR_MAT = 'minecraft:andesite'
STONE_MAT = 'minecraft:stone'  # floor texture: noise-mixed w/ andesite
OUTLINE_MAT = 'minecraft:prismarine_bricks'   # floor outline #1
DIAMOND_MAT = 'minecraft:diamond_ore'         # floor outline #2
WEB_SIZE = 4.0             # Worley cell size: web pocket diameter
WEB_TH = 0.6               # F2-F1 < this -> stone: filament thickness
TRIM1_MAT = 'minecraft:deepslate_tiles'      # wall bottom course
TRIM2_MAT = 'minecraft:polished_deepslate'   # wall second course
DOME_MAT = 'minecraft:blackstone'
DOME_RISE = 5              # fixed max vault rise above the band top
                           # (Ryan 2026-08-15: fixed height - wide
                           # caverns get a broad flat crown, never a
                           # taller dome)
DOME_SPAN = 5.0            # horizontal semi-axis of the arch profile
                           # (rings past this distance sit at full
                           # DOME_RISE - the flat crown)
DOME_MAX_LID = 320         # world roof: no dome cell above the
                           # tallest wall slice the build already uses
PIER_MAT = 'minecraft:dark_prismarine'   # rhythm piers (wall_test look)
TUFF_MAT = 'minecraft:tuff_bricks'       # pier flank columns
PIER_RHYTHM = 5.0          # wall arc-length between piers (the
                           # wall_test RHYTHM value: tuff|pier|tuff
                           # cluster every ~5 blocks of wall)

# ---- palettes (Ryan 2026-08-16): the wall_test color system on the
# new pipeline. A palette remaps exactly four base materials -
# prismarine_bricks (floor edge ring + wall under-line), diamond_ore
# (second ring + its under-line), dark_prismarine (piers), and the
# cyan glass body. Trim courses, tuff, dome, lanterns and the floor
# noise mix stay constant in every palette. Palettes 1-6 are copied
# from wall_test verbatim; 7-16 are new. The flip logic itself is the
# generator's compute_palette (per-branch random threshold inside a
# TRANSITIONS window, "already flipped" inherited across forks, never
# reverting, splice tails overridden block-by-block to their windows)
# - run at cache-build time on the PINNED sim with PAL_TRANSITIONS
# patched in (16 windows over the full y -64..314 drop instead of the
# old 6), so every sample and slime block carries its palette in the
# cache ----
# transition ladder (Ryan 2026-08-16): first color change in
# 275-285, red in 258-268, then the y-distance between changes
# SHRINKS (gaps 17 down to 12) so the 16th window lands exactly on
# the rapid zone at y=53 - the maze tightens its color rhythm all
# the way into the crazy section (maze top 306 after the shift)
PAL_TRANSITIONS = tuple(
    (c - 5, c + 5) for c in
    (280, 263, 246, 230, 214, 198, 183, 168, 153, 138,
     124, 110, 96, 83, 70, 58))
SPLICE_LEAD = 4    # palette flips this many bounces before a splice
MERGE_LEAD = 3     # merging arm's last 3 bounces take the junction color
MIN_RUN = 3        # no color lasts fewer than 3 blocks along any path
XGUARD_R = 3       # intersection exclusion radius (Ryan 2026-08-16):
                   # no color switch within 3 blocks before OR after
                   # any fork or merge junction
RAPID_Y = 53       # rapid finale: below this path level (maze bottom
                   # -72 + 125 = the bottom 125 levels after the
                   # 8-block shift) the palette re-rolls randomly
                   # along the path...
RAPID_MIN = 3      # ...every RAPID_MIN..RAPID_MAX blocks (Ryan
RAPID_MAX = 5      # 2026-08-16: was 5-8; with 77% of the rapid zone
                   # locked inside constraint components, the free
                   # stretches must cycle at nearly every legal
                   # chance for the bottom to feel rapid)
NETHER_MAT = 'minecraft:netherite_block'
SLICE_HALF = 0.8   # netherite divider half-thickness (wall_test
                   # value): wall/floor/dome cells whose center is
                   # within this distance of the transition plane
                   # convert - overriding every course (trim, piers,
                   # rings, floor mix)
RING_R = 7.0       # divider plane clip radius around the chord
                   # midpoint: covers the corridor's own shell
                   # (walls drift to d 6.0 + corner slack) without
                   # reaching a separate neighboring corridor
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
    7: {   # copper
        'minecraft:prismarine_bricks': 'minecraft:copper_block',
        'minecraft:diamond_ore': 'minecraft:copper_ore',
        'minecraft:dark_prismarine': 'minecraft:cut_copper',
        'minecraft:cyan_stained_glass': 'minecraft:orange_stained_glass',
    },
    8: {   # diamond
        'minecraft:prismarine_bricks': 'minecraft:diamond_block',
        'minecraft:diamond_ore': 'minecraft:deepslate_diamond_ore',
        'minecraft:dark_prismarine': 'minecraft:warped_planks',
        'minecraft:cyan_stained_glass':
            'minecraft:light_blue_stained_glass',
    },
    9: {   # quartz
        'minecraft:prismarine_bricks': 'minecraft:quartz_block',
        'minecraft:diamond_ore': 'minecraft:nether_quartz_ore',
        'minecraft:dark_prismarine': 'minecraft:quartz_pillar',
        'minecraft:cyan_stained_glass': 'minecraft:white_stained_glass',
    },
    10: {  # cherry
        'minecraft:prismarine_bricks': 'minecraft:cherry_wood',
        'minecraft:diamond_ore': 'minecraft:pink_glazed_terracotta',
        'minecraft:dark_prismarine': 'minecraft:cherry_planks',
        'minecraft:cyan_stained_glass': 'minecraft:pink_stained_glass',
    },
    11: {  # sculk
        'minecraft:prismarine_bricks': 'minecraft:sculk',
        'minecraft:diamond_ore': 'minecraft:sculk_catalyst',
        'minecraft:dark_prismarine': 'minecraft:warped_hyphae',
        'minecraft:cyan_stained_glass': 'minecraft:gray_stained_glass',
    },
    12: {  # iron
        'minecraft:prismarine_bricks': 'minecraft:iron_block',
        'minecraft:diamond_ore': 'minecraft:iron_ore',
        'minecraft:dark_prismarine': 'minecraft:polished_basalt',
        'minecraft:cyan_stained_glass':
            'minecraft:light_gray_stained_glass',
    },
    13: {  # red sandstone
        'minecraft:prismarine_bricks': 'minecraft:smooth_red_sandstone',
        'minecraft:diamond_ore': 'minecraft:orange_glazed_terracotta',
        'minecraft:dark_prismarine': 'minecraft:cut_red_sandstone',
        'minecraft:cyan_stained_glass': 'minecraft:brown_stained_glass',
    },
    14: {  # onyx
        'minecraft:prismarine_bricks': 'minecraft:coal_block',
        'minecraft:diamond_ore': 'minecraft:deepslate_coal_ore',
        'minecraft:dark_prismarine': 'minecraft:smooth_basalt',
        'minecraft:cyan_stained_glass': 'minecraft:black_stained_glass',
    },
    15: {  # kelp
        'minecraft:prismarine_bricks': 'minecraft:green_concrete',
        'minecraft:diamond_ore': 'minecraft:melon',
        'minecraft:dark_prismarine': 'minecraft:dried_kelp_block',
        'minecraft:cyan_stained_glass': 'minecraft:green_stained_glass',
    },
    16: {  # end
        'minecraft:prismarine_bricks': 'minecraft:end_stone_bricks',
        'minecraft:diamond_ore': 'minecraft:pearlescent_froglight',
        'minecraft:dark_prismarine': 'minecraft:bone_block',
        'minecraft:cyan_stained_glass': 'minecraft:tinted_glass',
    },
}
# slime-block dressing per palette (wall_test values for 0-6): top
# slab below the bounce block, carpet + light above it, open
# trapdoors hugging all four sides
DECOR_SLAB = {0: 'minecraft:prismarine_slab[type=top]',
              1: 'minecraft:bamboo_mosaic_slab[type=top]',
              2: 'minecraft:crimson_slab[type=top]',
              3: 'minecraft:purpur_slab[type=top]',
              4: 'minecraft:mossy_stone_brick_slab[type=top]',
              5: 'minecraft:dark_prismarine_slab[type=top]',
              6: 'minecraft:blackstone_slab[type=top]',
              7: 'minecraft:cut_copper_slab[type=top]',
              8: 'minecraft:warped_slab[type=top]',
              9: 'minecraft:quartz_slab[type=top]',
              10: 'minecraft:cherry_slab[type=top]',
              11: 'minecraft:cobbled_deepslate_slab[type=top]',
              12: 'minecraft:smooth_stone_slab[type=top]',
              13: 'minecraft:red_sandstone_slab[type=top]',
              14: 'minecraft:polished_blackstone_slab[type=top]',
              15: 'minecraft:spruce_slab[type=top]',
              16: 'minecraft:end_stone_brick_slab[type=top]'}
DECOR_DOOR = {0: 'minecraft:warped_trapdoor',
              1: 'minecraft:bamboo_trapdoor',
              2: 'minecraft:crimson_trapdoor',
              3: 'minecraft:cherry_trapdoor',
              4: 'minecraft:spruce_trapdoor',
              5: 'minecraft:oxidized_copper_trapdoor',
              6: 'minecraft:dark_oak_trapdoor',
              7: 'minecraft:copper_trapdoor',
              8: 'minecraft:iron_trapdoor',
              9: 'minecraft:birch_trapdoor',
              10: 'minecraft:mangrove_trapdoor',
              11: 'minecraft:weathered_copper_trapdoor',
              12: 'minecraft:oak_trapdoor',
              13: 'minecraft:acacia_trapdoor',
              14: 'minecraft:jungle_trapdoor',
              15: 'minecraft:waxed_oxidized_copper_trapdoor',
              16: 'minecraft:exposed_copper_trapdoor'}
DECOR_CARPET = {0: 'minecraft:light_blue_carpet',
                1: 'minecraft:yellow_carpet',
                2: 'minecraft:red_carpet',
                3: 'minecraft:purple_carpet',
                4: 'minecraft:lime_carpet',
                5: 'minecraft:blue_carpet',
                6: 'minecraft:magenta_carpet',
                7: 'minecraft:orange_carpet',
                8: 'minecraft:cyan_carpet',
                9: 'minecraft:white_carpet',
                10: 'minecraft:pink_carpet',
                11: 'minecraft:gray_carpet',
                12: 'minecraft:light_gray_carpet',
                13: 'minecraft:brown_carpet',
                14: 'minecraft:black_carpet',
                15: 'minecraft:green_carpet',
                16: 'minecraft:moss_carpet'}

N8 = [(dx, dz) for dx in (-1, 0, 1) for dz in (-1, 0, 1)
      if (dx, dz) != (0, 0)]
N4 = [(1, 0), (-1, 0), (0, 1), (0, -1)]
N6 = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1),
      (0, 0, -1)]


def read_seed(outdir):
    nms = open(os.path.join(outdir, '%s.nms' % gm.NAMESPACE)).read()
    return int(re.search(r'seed (\d+)', nms).group(1))


# ---- centerline sampling (port of wall_test's stream construction:
# branch chains prefixed with their fork/funnel parent and suffixed
# with the junction block they merge into, so the footprint flows
# across attachments) ----

def cr_pos(p0, p1, p2, p3, t):
    return 0.5 * (2 * p1 + (p2 - p0) * t
                  + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                  + (-p0 + 3 * p1 - 3 * p2 + p3) * t * t * t)


def build_samples(sim, pal_blk):
    blks = sim.blocks
    streams = []
    for br in sim.branches:
        chain = [i for i in br['blocks'] if blks[i] is not None]
        if not chain:
            continue
        first = blks[chain[0]]
        if first['prev'] is not None and blks[first['prev']] is not None:
            chain.insert(0, first['prev'])
        for k in sim.kids.get(chain[-1], ()):
            kb = blks[k]
            if kb is not None and kb['prev2'] == chain[-1]:
                chain.append(k)
                break
        streams.append(chain)

    def point_runs(chain):
        runs, run = [], []
        for a, b in zip(chain, chain[1:]):
            ab, bb = blks[a], blks[b]
            ok = (ab is not None and bb is not None
                  and ab['px'] is not None and bb['px'] is not None
                  and (bb['prev'] == a or bb['prev2'] == a))
            if ok:
                if not run:
                    run = [a]
                run.append(b)
            else:
                if run:
                    runs.append(run)
                run = []
        if run:
            runs.append(run)
        return runs

    # each sample carries its stream id, the cumulative horizontal arc
    # along that stream (the longitudinal coordinate the pier rhythm
    # stripes by - paint_piers), and its palette: the palette of the
    # nearer of its chord's two slime blocks (the palette divide is
    # the chord midpoint).
    # NETHERITE DIVIDER PLANES (Ryan 2026-08-16, v2): each palette
    # transition also emits an explicit slice record - the spline
    # position at the chord midpoint plus the chord's unit horizontal
    # direction. paint_nether cuts one flat vertical plane per record,
    # perpendicular to the route; the old per-sample slice flag
    # (nearest-owner conversion) sprawled where a flagged sample owned
    # a large Voronoi territory and gapped where quantization skipped
    # a run - see git history
    samples = []
    slices = []
    for sid, chain in enumerate(streams):
        arc = 0.0
        prev = None
        for run in point_runs(chain):
            pts = [(blks[i]['px'], blks[i]['pz'], float(blks[i]['y']))
                   for i in run]
            pals = [pal_blk.get(i, 0) for i in run]
            ext = [pts[0]] + pts + [pts[-1]]
            for i in range(len(pts) - 1):
                p0, p1, p2, p3 = ext[i], ext[i + 1], ext[i + 2], ext[i + 3]
                ln = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
                if ln < 1e-9:
                    continue
                if pals[i] != pals[i + 1]:
                    mx = cr_pos(p0[0], p1[0], p2[0], p3[0], 0.5)
                    mz = cr_pos(p0[1], p1[1], p2[1], p3[1], 0.5)
                    my = cr_pos(p0[2], p1[2], p2[2], p3[2], 0.5)
                    ux = (p2[0] - p1[0]) / ln
                    uz = (p2[1] - p1[1]) / ln
                    slices.append((mx, mz, my, ux, uz,
                                   pals[i], pals[i + 1]))
                steps = max(2, int(ln / STRIDE))
                # t=1 is skipped: the next chord's t=0 is the same point
                last = i == len(pts) - 2
                for s in range(steps + (1 if last else 0)):
                    t = s / steps
                    px = cr_pos(p0[0], p1[0], p2[0], p3[0], t)
                    pz = cr_pos(p0[1], p1[1], p2[1], p3[1], t)
                    py = cr_pos(p0[2], p1[2], p2[2], p3[2], t)
                    if prev is not None:
                        arc += math.hypot(px - prev[0], pz - prev[1])
                    prev = (px, pz)
                    pal = pals[i] if t < 0.5 else pals[i + 1]
                    samples.append((px, pz, py, sid, arc, pal))
    return samples, slices


def splice_regions(sim):
    # port of wall_test.splice_regions: per splice, the shell columns
    # around the copied window stretch w1..wN (w0 overlaps the tail's
    # own approach arc; past the dead end there is no separation
    # guarantee), each mapped to the local path-y range of the stretch.
    # Sorted highest window first so chained splices propagate top-down
    blks = sim.blocks
    regions = []
    for sp in sim.splices:
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
                for cx in range(int(sx - SHELL_R), int(sx + SHELL_R) + 2):
                    for cz in range(int(sz - SHELL_R),
                                    int(sz + SHELL_R) + 2):
                        if math.hypot(cx - sx, cz - sz) > SHELL_R:
                            continue
                        lo, hi = band.get((cx, cz), (sy, sy))
                        band[(cx, cz)] = (min(lo, sy), max(hi, sy))
        if band:
            regions.append((sp['delta'], band, blks[sp['win'][1]]['y']))
    regions.sort(key=lambda r: -r[2])
    return regions


def compute_palette(sim):
    # COLOR ASSIGNMENT BY UNIFICATION + GENERATE-AND-VERIFY
    # (Ryan 2026-08-16 v2). The rules are compiled into a constraint
    # graph FIRST, so they cannot conflict later:
    #   - any two adjacent blocks whose seam would sit within
    #     XGUARD_R (3) of a fork/merge are unioned (R1: the whole
    #     exclusion zone of an intersection is one color),
    #   - every splice window block is unioned with its tail mirror
    #     (block-for-block teleport fidelity),
    #   - the approach blocks are unioned with the tail start (the
    #     player is already in the destination color before every
    #     swap trigger).
    # Union-find collapses these into components; a component takes
    # exactly ONE color, so R1, fidelity, and the lead rule hold BY
    # CONSTRUCTION - chained splices and windows overlapping
    # intersections (which defeated force-based approaches, see git
    # history) just merge into bigger components.
    # GENERATE then walks every path in order: a color switch is
    # possible only at a component boundary (such seams are >= 3
    # from every intersection by construction) and only MIN_RUN (3)
    # blocks after the previous switch; slow-zone switches come from
    # the 16 PAL_TRANSITIONS thresholds, rapid-zone (y <= RAPID_Y)
    # from the 5-8 block countdown. Entering an already-colored
    # component (a mirrored tail, a shared junction zone) forces
    # that color - the only way this can break a rule is a short
    # run between two forced regions, which VERIFY catches: a pure
    # global validator (no repairs) rejects the attempt and the
    # next candidate seed runs. The returned assignment has zero
    # violations by proof.
    blks = sim.blocks
    br_of = {}
    for br in sim.branches:
        for i in br['blocks']:
            br_of[i] = br['id']

    def live_kids(i):
        return [k for k in sim.kids.get(i, ()) if blks[k] is not None]

    def neighbors(i):
        b = blks[i]
        ns = [j for j in (b['prev'], b['prev2'])
              if j is not None and blks[j] is not None]
        return ns + live_kids(i)

    # intersections + capped path-distance map (R1)
    inter = set()
    for i, b in enumerate(blks):
        if b is None:
            continue
        if len(live_kids(i)) >= 2 or (b['prev2'] is not None
                                      and blks[b['prev2']] is not None):
            inter.add(i)
    dmap = {i: 0 for i in inter}
    frontier = set(inter)
    for d in range(1, XGUARD_R + 1):
        nf = set()
        for i in frontier:
            for j in neighbors(i):
                if j not in dmap:
                    dmap[j] = d
                    nf.add(j)
        frontier = nf

    def seam_ok(a, b):
        return min(dmap.get(a, 99), dmap.get(b, 99)) >= XGUARD_R

    splices = []
    for sp in sorted(sim.splices, key=lambda s: -blks[s['win'][1]]['y']):
        wb = [j for j in sp['win'][1:] if blks[j] is not None]
        cb = [j for j in sp['copy'] if blks[j] is not None]
        if not wb or not cb:
            continue
        app = []
        p = blks[cb[0]]['prev']
        while p is not None and blks[p] is not None \
                and len(app) < SPLICE_LEAD - 1:
            app.append(p)
            p = blks[p]['prev']
        w0 = sp['win'][0]
        if blks[w0] is None:
            w0 = None
        splices.append((wb, cb, app, w0))

    # ---- constraint graph -> components (union-find) ----
    parent = {}

    def find(a):
        r = a
        while parent.get(r, r) != r:
            r = parent[r]
        while parent.get(a, a) != a:
            parent[a], a = r, parent[a]
        return r

    def union(a, b):
        parent[find(a)] = find(b)

    for i, b in enumerate(blks):
        if b is None:
            continue
        for j in neighbors(i):
            if j > i and not seam_ok(i, j):
                union(i, j)
    for wb, cb, app, w0 in splices:
        for wj, cj in zip(wb, cb):
            union(wj, cj)
        for a in app:
            union(a, cb[0])
        if w0 is not None:
            # landing rule (user 2026-08-17): the block the teleport
            # drops the player on (win[1], via the tail mirror) must
            # never be the first block of a new color - the window
            # BASE joins the window component, so the seam sits at
            # least one block above the landing bounce
            union(w0, wb[0])
        # boundary legalization: the seeded window color (below)
        # forces a seam where the carrying corridor enters the
        # window and where the dying arm enters the approach; if
        # that seam would sit within XGUARD_R of an intersection,
        # pull the upstream blocks into the component until it is
        # legal - by construction, like the intersection zones
        # (the window-side walk starts at win[0] now that it is in
        # the component)
        for entry in (w0 if w0 is not None else wb[0],
                      app[-1] if app else cb[0]):
            cur = entry
            p = blks[cur]['prev']
            hops = 0
            while p is not None and blks[p] is not None \
                    and not seam_ok(p, cur) and hops < 10:
                union(p, cur)
                cur = p
                p = blks[cur]['prev']
                hops += 1
    ncomp = len({find(i) for i, b in enumerate(blks) if b is not None})

    # WINDOW COLORS FOLLOW THE LADDER (Ryan 2026-08-16): without
    # this, whichever branch walks a window/tail pair first colors
    # it - deep dying arms won and dragged mid-maze colors up into
    # top-of-maze teleport destinations (46 colored window blocks
    # above y=285, found in-world). Every splice component above the
    # rapid zone is pre-seeded with the ladder level AT ITS WINDOW'S
    # HEIGHT, so a window looks like its surroundings and the deep
    # approach flashes the DESTINATION color before the swap - the
    # original wall_test lead semantics. Rapid-zone windows stay
    # first-walker-colored (variety). Highest window seeds first on
    # shared components
    centers = [(lo + hi) // 2 for lo, hi in PAL_TRANSITIONS]

    def ladder(y):
        return sum(1 for c in centers if y <= c)

    def seeded_roots():
        # seed ONLY windows above the first transition window - the
        # region that must be uniformly base-colored. Deeper windows
        # keep first-walker colors, which are already
        # height-appropriate (seeding every window was tried and
        # froze 80%+ of the slow zone at the top windows' levels)
        sr = {}
        for wb, cb, app, w0 in splices:   # highest window seeds first
            wy = blks[wb[len(wb) // 2]]['y']
            if wy <= PAL_TRANSITIONS[0][1]:
                continue
            lv = ladder(wy)
            for wj in wb:
                r = find(wj)
                if r not in sr:
                    sr[r] = lv
        return sr

    # GAP ABSORPTION: a free stretch shorter than MIN_RUN squeezed
    # between two seeded components can never carry a legal run -
    # union the gap and both components into one, which then takes
    # a single seeded color (highest window wins). Iterate: merges
    # can create new short gaps
    for _pass in range(4):
        sr = seeded_roots()
        merged = 0
        for i, b in enumerate(blks):
            if b is None or find(i) not in sr:
                continue
            for k in live_kids(i):
                path = []
                q = k
                for _depth in range(MIN_RUN):
                    if q is None or blks[q] is None:
                        break
                    rq = find(q)
                    if rq in sr:
                        if path or rq != find(i):
                            for g in path:
                                union(g, i)
                            union(q, i)
                            merged += 1
                        break
                    path.append(q)
                    kk = live_kids(q)
                    q = kk[0] if len(kk) == 1 else None
        if not merged:
            break

    seeds = seeded_roots()

    # branch walk order: parents first
    order = []
    pending = list(sim.branches)
    guard_rounds = 0
    while pending:
        guard_rounds += 1
        assert guard_rounds <= len(sim.branches) + 2
        nxt = []
        done = {i for br in order for i in br['blocks']}
        for br in pending:
            chain = [i for i in br['blocks'] if blks[i] is not None]
            if not chain:
                continue
            pv = blks[chain[0]]['prev']
            if pv is not None and blks[pv] is not None \
                    and pv not in done and guard_rounds <= len(pending):
                nxt.append(br)
            else:
                order.append(br)
        pending = nxt

    nlv = len(PAL_TRANSITIONS)

    def generate(attempt):
        pal = {}
        comp_color = dict(seeds)
        state = {}   # block -> (color, run length so far, rapid due)
        for br in order:
            bid = br['id']
            chain = [i for i in br['blocks'] if blks[i] is not None]
            if not chain:
                continue
            rng = random.Random('%d:pal:%d:%d'
                                % (sim.seed, attempt, bid))
            thr = [rng.randint(*PAL_TRANSITIONS[ti])
                   for ti in range(nlv)]
            for idx, i in enumerate(chain):
                b = blks[i]
                pv = b['prev']
                cur, since, due = state.get(pv, (0, 99, 0)) \
                    if pv is not None else (0, 99, 0)
                ci = find(i)
                if ci in comp_color:
                    c = comp_color[ci]
                    if c != cur:      # forced entry (mirrored tail,
                        cur = c       # shared junction zone)
                        since = 1
                        due = rng.randint(RAPID_MIN, RAPID_MAX)
                    else:
                        since += 1
                else:
                    want = None
                    if b['y'] <= RAPID_Y:
                        due -= 1
                        if due <= 0:
                            # roll levels 1..nlv excluding cur -
                            # NEVER level 0: a deep base-material
                            # stretch reads as "the transition
                            # skipped this section" (Ryan)
                            lvl = rng.randrange(
                                nlv if cur == 0 else nlv - 1) + 1
                            if cur and lvl >= cur:
                                lvl += 1
                            want = lvl
                    else:
                        w = cur
                        for ti in range(nlv):
                            if b['y'] <= thr[ti]:
                                w = max(w, ti + 1)
                        if w > cur:
                            want = w
                    if want is not None and since >= MIN_RUN \
                            and (pv is None or find(pv) != ci):
                        # lookahead: the new color must survive
                        # MIN_RUN blocks along EVERY downstream
                        # path (forks included) - an already-colored
                        # component of another color within 2 steps
                        # would cut the run short, so the switch
                        # defers instead
                        frontier = [i]
                        for _step in range(MIN_RUN - 1):
                            nf = []
                            for q in frontier:
                                for k2 in live_kids(q):
                                    c2 = comp_color.get(find(k2))
                                    if c2 is not None and c2 != want:
                                        want = None
                                        break
                                    nf.append(k2)
                                if want is None:
                                    break
                            if want is None:
                                break
                            frontier = nf
                    else:
                        want = None
                    if want is not None:
                        cur = want
                        since = 1
                        due = rng.randint(RAPID_MIN, RAPID_MAX)
                    else:
                        since += 1
                    comp_color[ci] = cur
                pal[i] = cur
                state[i] = (cur, since, due)
        return pal

    def validate(pal, verbose=False):
        # pure re-check of every rule - no repairs, any hit rejects
        v = 0
        for i, b in enumerate(blks):
            if b is None:
                continue
            for j in neighbors(i):
                if j < i:
                    continue
                if pal.get(i, 0) != pal.get(j, 0) \
                        and not seam_ok(i, j):
                    v += 1
                    if verbose:
                        print('   seam near intersection at '
                              '(%d,%d,%d): %d|%d dist %d'
                              % (b['x'], b['y'], b['z'],
                                 pal.get(i, 0), pal.get(j, 0),
                                 min(dmap.get(i, 9),
                                     dmap.get(j, 9))))
        for i, b in enumerate(blks):   # R2: runs >= MIN_RUN along
            if b is None:              # every traversable path
                continue
            pi = pal.get(i, 0)
            for k in live_kids(i):
                pk = pal.get(k, 0)
                if pk == pi:
                    continue
                stack = [[k]]
                while stack:
                    path = stack.pop()
                    if len(path) >= MIN_RUN:
                        continue
                    for k2 in live_kids(path[-1]):
                        if pal.get(k2, 0) == pk:
                            stack.append(path + [k2])
                        else:
                            v += 1
                            if verbose:
                                bb = blks[path[0]]
                                print('   short run at (%d,%d,%d) '
                                      'len %d: %d -> %d -> %d'
                                      % (bb['x'], bb['y'], bb['z'],
                                         len(path), pi, pk,
                                         pal.get(k2, 0)))
        for wb, cb, app, w0 in splices:
            v += sum(1 for cj, wj in zip(cb, wb)
                     if pal.get(cj, 0) != pal.get(wj, 0))
            v += sum(1 for a in app
                     if pal.get(a, 0) != pal.get(cb[0], 0))
            # landing rule: win[0] carries the window color
            if w0 is not None and pal.get(w0, 0) != pal.get(wb[0], 0):
                v += 1
        return v

    best = None
    no_show = 0
    for attempt in range(300):
        pal = generate(attempt)
        v = validate(pal)
        if best is None or v < best[0]:
            best = (v, attempt)
        if v == 0:
            # every color level must appear somewhere (Ryan
            # 2026-08-16) - a seed hiding a level is rejected like
            # a rule violation
            present = set(pal.values())
            if any(l not in present for l in range(1, nlv + 1)):
                no_show += 1
                continue
            seams = sum(1 for i, b in enumerate(blks) if b is not None
                        for j in neighbors(i) if j > i
                        and pal.get(i, 0) != pal.get(j, 0))
            rapid = sum(1 for i, b in enumerate(blks)
                        if b is not None and b['y'] <= RAPID_Y
                        and b['prev'] is not None
                        and blks[b['prev']] is not None
                        and pal.get(i, 0) != pal.get(b['prev'], 0))
            print('palette: attempt %d VALID - 0 rule violations, '
                  'all %d levels present (%d attempts rejected, %d '
                  'for hidden levels); %d color seams total, %d in '
                  'the rapid zone (y<=%d), %d of %d blocks past '
                  'palette 0, %d constraint components'
                  % (attempt, nlv, attempt, no_show, seams, rapid,
                     RAPID_Y, sum(1 for p in pal.values() if p),
                     len(pal), ncomp))
            print('palette rules: seam distance >= %d from all %d '
                  'forks/merges, min run %d, %d splice tails '
                  'mirrored blockwise + %d-block leads - all '
                  'unified into the constraint graph'
                  % (XGUARD_R, len(inter), MIN_RUN, len(splices),
                     SPLICE_LEAD - 1))
            return pal
    print('best attempt breakdown (attempt %d, %d violations):'
          % (best[1], best[0]))
    validate(generate(best[1]), verbose=True)
    raise RuntimeError(
        'no valid palette assignment in 300 attempts '
        '(best: %d violations at attempt %d)' % best)


def load_generator(outdir):
    # GENERATOR PINNING: the sandbox was emitted by a specific
    # generate_maze_v3.py commit, and HEAD may no longer generate the
    # emitted seed (the turn-run rule broke seed 2 - see memory).
    # The commit's generator is checked into the sandbox as
    # gen_pinned.py; prefer it for sim rebuilds
    pin = os.path.join(outdir, 'gen_pinned.py')
    if os.path.isfile(pin):
        import importlib.util
        spec = importlib.util.spec_from_file_location('gen_pinned', pin)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        print('  using pinned generator %s' % pin)
        return mod
    return gm


def load_or_build(outdir, fresh):
    cache = os.path.join(outdir, 'walls_cache.pkl')
    seed = read_seed(outdir)
    if not fresh and os.path.isfile(cache):
        with open(cache, 'rb') as fh:
            data = pickle.load(fh)
        if data.get('seed') == seed and data.get('fmt') == 13:
            print('cache: seed %d, %d samples, %d splice regions, '
                  '%d slime blocks'
                  % (seed, len(data['samples']), len(data['regions']),
                     len(data['blocks'])))
            return data
        print('cache is for seed %s fmt %s, rebuilding'
              % (data.get('seed'), data.get('fmt')))
    t0 = time.time()
    print('building sim (seed %d)...' % seed)
    pgm = load_generator(outdir)
    sim = pgm.Sim(seed)
    assert sim.run(), 'seed %d no longer generates' % seed
    # sandbox translation (Ryan 2026-08-17): the emitted chains are
    # rigidly translated (translate_maze.py leaves shift.txt with
    # "dx dy dz"); the sim regenerates untranslated, so apply the
    # same shift here or every decoration lands at the old position
    shf = os.path.join(outdir, 'shift.txt')
    if os.path.isfile(shf):
        dx, dy, dz = (int(v) for v in open(shf).read().split())
        for b in sim.blocks:
            if b is not None:
                b['x'] += dx
                b['y'] += dy
                b['z'] += dz
                if b['px'] is not None:
                    b['px'] += dx
                    b['pz'] += dz
        print('  applied sandbox shift (%d, %d, %d)' % (dx, dy, dz))
    st = sim.stats()
    print('  %d blocks, %d splices in %.1fs'
          % (st['blocks'], st['splices'], time.time() - t0))
    # palette levels: walls.py's own compute_palette (the generator's
    # flip logic + the intersection exclusion + the rapid finale)
    pal_blk = compute_palette(sim)
    blks = sim.blocks
    # live bounce blocks in branch order (first appearance wins) with
    # their palette - the slime-dressing input (wall_test's live list)
    seen_b = set()
    blocks = []
    for br in sim.branches:
        for i in br['blocks']:
            if i not in seen_b and blks[i] is not None:
                seen_b.add(i)
                b = blks[i]
                blocks.append((b['x'], b['y'], b['z'],
                               pal_blk.get(i, 0)))
    samples, slices = build_samples(sim, pal_blk)
    data = {
        'fmt': 13,  # samples carry (sid, arc) since the pier rhythm
                    # and pal since the palettes; blocks since the
                    # slime dressing; slices (divider planes) since
                    # netherite v2
        'seed': seed,
        'samples': samples,
        'slices': slices,
        'regions': splice_regions(sim),
        'slime': sorted((b['x'], b['y'], b['z'])
                        for b in sim.blocks if b is not None),
        'blocks': blocks,
    }
    with open(cache, 'wb') as fh:
        pickle.dump(data, fh)
    print('  cached %d samples, %d regions -> %s'
          % (len(data['samples']), len(data['regions']), cache))
    return data


# ---- footprint field: per plan cell, {rounded path level: min d} of
# every corridor pass within FIELD_R. A pass's band is taken from the
# rounded level; the +-0.5 rounding error at the band edges is inside
# the design slack (the band edge is a tuning constant, and adjacent
# cells of one pass share the same key so edges stay coherent) ----

def build_field(samples):
    passes = defaultdict(dict)
    for sx, sz, sy, _sid, _arc, _pal in samples:
        ipy = int(round(sy))
        for cx in range(int(math.floor(sx - FIELD_R)),
                        int(math.floor(sx + FIELD_R)) + 1):
            ddx = cx + 0.5 - sx
            for cz in range(int(math.floor(sz - FIELD_R)),
                            int(math.floor(sz + FIELD_R)) + 1):
                d = math.hypot(ddx, cz + 0.5 - sz)
                if d >= FIELD_R:
                    continue
                e = passes[(cx, cz)]
                if d < e.get(ipy, 99.0):
                    e[ipy] = d
    cells_by_ipy = defaultdict(list)
    for cell, e in passes.items():
        for ipy, d in e.items():
            cells_by_ipy[ipy].append((cell, d))
    return passes, cells_by_ipy


def slice_field(cells_by_ipy, y):
    # field of slice y: min d over every pass whose band covers y
    fld = {}
    for ipy in range(y - BAND_HI, y - BAND_LO + 1):
        for cell, d in cells_by_ipy.get(ipy, ()):
            if d < fld.get(cell, 99.0):
                fld[cell] = d
    return fld


def relax(fld):
    # synchronous cellular smoothing on the flexible band; hard cells
    # never flip, so bounce clearance and the 4-block floor hold.
    # Each slice relaxes INDEPENDENTLY from the same d<OPEN_INIT
    # init: identical fields give identical boundaries, so wall faces
    # stack vertically wherever the field does not change. (An
    # inter-slice hysteresis variant - seeding flexible cells from the
    # slice above - was tried 2026-08-13 and reverted: the CA fixpoint
    # differs from its init, so inheritance ratchets the boundary a
    # cell per slice toward the hard caps and the walls taper outward
    # down the band instead of standing vertical)
    open_set = {c for c, d in fld.items() if d < OPEN_INIT}
    flex = [c for c, d in fld.items() if HARD_OPEN < d < HARD_OUT]
    iters = 0
    for _ in range(RELAX_MAX):
        iters += 1
        flips = []
        for c in flex:
            n = sum(1 for dx, dz in N8
                    if (c[0] + dx, c[1] + dz) in open_set)
            if c in open_set:
                if n <= CLOSE_TH:
                    flips.append((c, False))
            elif n >= OPEN_TH:
                flips.append((c, True))
        if not flips:
            break
        for c, to_open in flips:
            if to_open:
                open_set.add(c)
            else:
                open_set.discard(c)
    return open_set, iters


def bump_dent_count(open_set):
    bumps = dents = 0
    for c in open_set:
        n = sum(1 for dx, dz in N8 if (c[0] + dx, c[1] + dz) in open_set)
        if n <= 2:
            bumps += 1
    # dents: closed cells nearly surrounded - scan the boundary only
    seen = set()
    for c in open_set:
        for dx, dz in N4:
            nb = (c[0] + dx, c[1] + dz)
            if nb in open_set or nb in seen:
                continue
            seen.add(nb)
            n = sum(1 for ddx, ddz in N8
                    if (nb[0] + ddx, nb[1] + ddz) in open_set)
            if n >= 6:
                dents += 1
    return bumps, dents


class OpenModel:
    # per plan cell, the sorted list of (ylo, yhi) open runs - compact
    # (one or two runs per cell) but fast to query
    def __init__(self):
        self.iv = defaultdict(list)

    def add_slice(self, open_set, y):
        # slices are added ascending, so runs grow upward at hi
        for c in open_set:
            runs = self.iv[c]
            if runs and runs[-1][1] == y - 1:
                runs[-1][1] = y
            else:
                runs.append([y, y])

    def at(self, x, z, y):
        for lo, hi in self.iv.get((x, z), ()):
            if lo <= y <= hi:
                return True
        return False

    def cells(self):
        for (x, z), runs in self.iv.items():
            for lo, hi in runs:
                for y in range(lo, hi + 1):
                    yield x, y, z


def paint(data, preview_dir=None):
    t0 = time.time()
    passes, cells_by_ipy = build_field(data['samples'])
    print('field: %d plan cells in %.1fs'
          % (len(passes), time.time() - t0))

    ys = sorted(cells_by_ipy)
    ytop = ys[-1] + BAND_HI
    ybot = max(ys[0] + BAND_LO, WORLD_MIN_Y)
    print('slices: y %d..%d' % (ybot, ytop))

    open_model = OpenModel()
    walls = set()
    preview_ys = set(range(ytop - 8, ybot, -25)) if preview_dir else set()
    previews = {}
    t0 = time.time()
    tot_bumps = tot_dents = 0
    itmax = 0
    propagated = 0
    # ascending sweep with UPWARD-OPEN PROPAGATION: a cell open on the
    # slice below that is still covered here (d < HARD_OUT) stays
    # open. Each slice's CA still relaxes independently from the raw
    # field (no compounding - the seeded-CA hysteresis that ratcheted
    # was reverted 2026-08-13); the union is taken AFTER. Effect:
    # upper slices can never close INSIDE the lower footprint, so a
    # band-top wall ring can never be stranded hanging over its own
    # corridor's air (per-slice CA fuzz did exactly that - found
    # in-world at (4723,196-197,2928): a 2-block fragment over open
    # air, invisible to the floater metric because each cell had wall
    # above or wall below). Side walls stack vertically at the band's
    # outer envelope; cap fronts still recede by coverage
    below = None
    for y in range(ybot, ytop + 1):
        fld = slice_field(cells_by_ipy, y)
        open_set, iters = relax(fld)
        itmax = max(itmax, iters)
        if below:
            for c in below:
                # any covered cell qualifies (not just d < HARD_OUT):
                # cutting propagation at the 5.5 line recreated the
                # inward ring shift right at that edge (23 residual
                # short hangs). The only hard width contract is the
                # 4-block MINIMUM; letting the envelope run out to
                # coverage costs a rare wider spot at a band top,
                # never a hanging fragment
                if c not in open_set and c in fld:
                    open_set.add(c)
                    propagated += 1
        open_model.add_slice(open_set, y)
        extract_walls(open_set, below or set(), y, walls)
        if y in preview_ys or (preview_dir and y == ybot):
            b, d = bump_dent_count(open_set)
            tot_bumps += b
            tot_dents += d
            previews[y] = (fld, open_set)
        below = open_set
    print('paint: %d wall cells in %.1fs (relax iters max %d, %d '
          'cells propagated open upward; sampled slices: %d bumps, '
          '%d dents)'
          % (len(walls), time.time() - t0, itmax, propagated,
             tot_bumps, tot_dents))

    hole_filled = fill_column_holes(walls, open_model)
    print('vertical hole fill: %d cells' % hole_filled)
    seams = close_ceiling_seams(walls, open_model)
    print('junction seam closure: %d ceiling-transition slits walled'
          % seams)

    if preview_dir:
        render_previews(previews, walls, data, preview_dir)
    return passes, open_model, walls


def extract_walls(open_set, below, y, walls):
    if y < WORLD_MIN_Y:
        return
    for c in open_set:
        for dx, dz in N4:
            nb = (c[0] + dx, c[1] + dz)
            if nb in open_set or nb in below:
                continue        # open, or ceiling transition
            walls.add((nb[0], y, nb[1]))


def fill_column_holes(walls, open_model):
    cols = defaultdict(list)
    for x, y, z in walls:
        cols[(x, z)].append(y)
    added = 0
    for (x, z), wys in cols.items():
        s = set(wys)
        for y in wys:
            if y + 2 in s and y + 1 not in s \
                    and not open_model.at(x, z, y + 1):
                walls.add((x, y + 1, z))
                added += 1
    return added


def close_ceiling_seams(walls, open_model):
    # The ceiling-transition suppression (extract_walls) is right for a
    # corridor's OWN band stepping down with the descending path -
    # walling those faces would hang 1-block arcs floating across the
    # tunnel. But when the air one slice below belongs to a DIFFERENT
    # corridor passing under a junction, the same suppression leaves a
    # 1-block-tall see-through slit directly UNDER the upper corridor's
    # wall run (found in-world 2026-08-13: "gaps near intersections").
    # The two cases are locally identical in the field; what separates
    # them is what hangs overhead: a junction slit sits under a wall
    # column, a floating-ribbon position has void above (its cap line
    # is ~a chord-length uphill, not stacked). So: close every
    # suppressed face that has wall DIRECTLY above - the wall curtain
    # extends flush down to the lower corridor's ceiling level.
    # Ribbon arcs keep their void overhead and stay suppressed.
    #
    # DIRECTLY above only: a first version also closed under LATERAL
    # 4-neighbours of the above slice (for boundary drift), but where
    # the footprint narrows near a corridor's band top the wall ring
    # shifts inward between slices, and that variant planted blocks
    # over open corridor air - 1-block ledges floating at the ceiling
    # line (found in-world 2026-08-13 at (4743,162,2956): "partial
    # walls, only the top blocks remain"). The open-below test makes
    # the direct case safe by construction; drift slits keep their
    # ceiling-transition exemption instead of gaining a floater
    added = 0
    for x, y, z in sorted(walls):
        cy = y - 1
        if cy < WORLD_MIN_Y or (x, cy, z) in walls:
            continue
        if open_model.at(x, z, cy):
            continue                        # real corridor air
        if not open_model.at(x, z, cy - 1):
            continue                        # not a ceiling transition
        if not any(open_model.at(x + ax, z + az, cy)
                   for ax, az in N4):
            continue                        # no open face to seal
        walls.add((x, cy, z))
        added += 1
    return added


# ---- splice stamp: tail == window, stamp wins (see header), with ONE
# guard: a stamped wall never lands in a cell whose strict-band field
# distance is <= HARD_OPEN - that is bounce space the painter itself
# guarantees never to wall, and a solid block there can physically
# stop a bystander corridor's bounce line. The Phase 5 revert showed
# broad bystander repair (d < 4.3) trades intrusions for visible
# holes; this guard keeps only the gameplay-critical core of it, and
# every skip is reported (it IS a window/tail divergence) ----

def strict_d(passes, x, y, z):
    e = passes.get((x, z))
    best = None
    if e:
        for ipy, d in e.items():
            if ipy + BAND_LO <= y <= ipy + BAND_HI \
                    and (best is None or d < best):
                best = d
    return best


def stamp(walls, regions, passes, guard=True):
    placed, removed, guarded = 0, 0, 0
    for (sdx, sdy, sdz), band, _ in regions:
        for (cx, cz), (plo, phi) in band.items():
            ylo = max(int(math.floor(plo)) + BAND_LO, WORLD_MIN_Y)
            yhi = int(math.ceil(phi)) + BAND_HI + 1
            for y in range(ylo, yhi + 1):
                t = (cx - sdx, y - sdy, cz - sdz)
                if t[1] < WORLD_MIN_Y:
                    continue
                if (cx, y, cz) in walls:
                    if t not in walls:
                        d = strict_d(passes, *t) if guard else None
                        if d is not None and d <= HARD_OPEN:
                            guarded += 1
                            continue
                        walls.add(t)
                        placed += 1
                elif t in walls:
                    walls.discard(t)
                    removed += 1
    print('stamp: %d cells placed, %d removed, %d placements guarded '
          '(would sit in d<=%.1f bounce space) across %d regions'
          % (placed, removed, guarded, HARD_OPEN, len(regions)))


def purge_in_air_walls(walls, open_model):
    # NO WALL STANDS IN CORRIDOR AIR - EVER (Ryan 2026-08-14: "remove
    # those stand alone wall columns"). Every wall cell that is
    # model-open at its own slice is removed, including the coherent
    # stamped identity columns/faces the earlier passes kept for
    # tail==window fidelity. Removal is provably seal-safe: a face
    # between two corridor-air cells needs no wall, so deleting an
    # in-air cell can never unseal anything. This single rule
    # subsumes the two passes it replaces (the component debris sweep
    # and the top-exposed strand erosion - see git history) and turns
    # the intrusion metric into a hard zero gate. The cost is a
    # window/tail divergence per removed cell (a column pops in at
    # the swap) - accepted by the user over permanent mid-air stone
    gone = [p for p in walls if open_model.at(p[0], p[2], p[1])]
    for p in gone:
        walls.discard(p)
    print('in-air wall purge: %d cells removed (identity columns, '
          'fragments, strands)' % len(gone))
    return len(gone)


def seal_repair(walls, open_model):
    # FINAL SEAL (user requirement 2026-08-13: every section sealed and
    # enclosed, no holes): rebuild the painter's boundary wherever the
    # stamp left a lateral face of corridor air unsealed. Because the
    # painter's wall IS the boundary of the open set, walling every
    # violating face's neighbour restores exactly the missing pieces:
    # the curved endcap at each spliced dead-end tail (the stamp copies
    # the window's onward-open tube over it), backdrops behind copied
    # cavern mouths, and the holes left by guarded placements. Added
    # cells are never model-open, so they cannot block bounce space or
    # the 4-block floor. Each one is a deliberate window/tail
    # divergence - pre-swap wall where post-swap shows an opening - but
    # they sit 3-5 bounces past the swap trigger or on the tube fringe,
    # where the 22.5deg/bounce curvature occludes them; a sealed tube
    # beats exact identity there (the inverse of the Phase 5 trade:
    # this ADDS walls outside corridor air, it never re-opens them)
    added = 0
    for x, y, z in open_model.cells():
        for dx, dz in N4:
            nx, nz = x + dx, z + dz
            if open_model.at(nx, nz, y) or (nx, y, nz) in walls \
                    or open_model.at(nx, nz, y - 1):
                continue
            walls.add((nx, y, nz))
            added += 1
    print('seal repair: %d boundary cells restored (tail endcaps, '
          'cavern backdrops, guard patches)' % added)
    return added


def thin_walls(walls, open_model):
    # OUTSIDE-SHELL SCAN (user request 2026-08-13, prep for the sea
    # lantern layer that will wrap the wall): keep only wall cells
    # that actually seal a face - corridor air as a 4-neighbour on
    # their own slice. Everything else is outside the immediate wall:
    # outside corners (diagonal-only contact), stamped stubs running
    # past a tail's rounded endcap, far tube-fringe copies, buried
    # second layers where stamps overlap. A non-sealing cell cannot
    # be load-bearing (sealing means an open 4-neighbour by
    # definition), so this can never break the seal gate; afterwards
    # the shell is MINIMAL - removing any remaining cell would
    # unseal a face - i.e. the thinnest possible smooth_stone skin.
    # (Would exempt fill_column_holes cells - wall above+below, no
    # lateral air - but that pass fills 0 cells on current seeds.)
    removed = 0
    for x, y, z in list(walls):
        if any(open_model.at(x + dx, z + dz, y) for dx, dz in N4):
            continue
        walls.discard((x, y, z))
        removed += 1
    print('outside-shell scan: %d non-sealing cells removed '
          '(corners, stubs, buried layers)' % removed)
    return removed


def lantern_eligible(x, y, z, walls, open_model):
    # SEA LANTERN placement rules, v3 (Ryan 2026-08-14, second
    # revision). One shared predicate for painter AND verifier:
    #  (a) the cell is neither wall nor corridor air;
    #  (b) it touches a wall cell LATERALLY on its own slice;
    #  (c) no wall within 2 cells vertically in its own column (the
    #      +-1 rule of v2 still let lanterns hover with a 1-block air
    #      gap above/below staggered stone - 174 cases);
    #  (d) BAND INTERIOR only: some corridor-air column sealed by one
    #      of its lateral wall neighbours must contain y STRICTLY
    #      inside its open run (lo < y < hi). The run's lo is the
    #      floor plane (path-4) and its hi the dome line (path+6);
    #      v2 placed 106k lanterns beside the wall's bottom course
    #      and 65k beside the top course - exactly where the floor
    #      and dome stages will build. The curtain now spans only the
    #      middle of the band, leaving both edge slices bare stone
    if (x, y, z) in walls or open_model.at(x, z, y):
        return False
    for dy in (1, 2, -1, -2):
        if (x, y + dy, z) in walls:
            return False
    lateral = mid = False
    for dx, dz in N4:
        wx, wz = x + dx, z + dz
        if (wx, y, wz) not in walls:
            continue
        lateral = True
        for ax, az in N4:
            for lo, hi in open_model.iv.get((wx + ax, wz + az), ()):
                if lo < y < hi:
                    mid = True
                    break
            if mid:
                break
        if mid:
            break
    return lateral and mid


def paint_lanterns(walls, open_model):
    lant = set()
    for x, y, z in walls:
        for dx, dz in N4:
            c = (x + dx, y, z + dz)
            if c not in lant and lantern_eligible(c[0], y, c[2],
                                                  walls, open_model):
                lant.add(c)
    print('lantern layer: %d cells (band-interior side curtain)'
          % len(lant))
    return lant


# ---- DOME (Ryan 2026-08-15, stage 3): a blackstone vault lids every
# corridor, springing from the bare smooth_stone top course at the
# band top (path+6). Same inversion as the walls: no swept arch ribs
# (the wall_test vault needed pinhole closure + wall-top seal + prune
# patches) - instead the corridor's open volume is EXTENDED upward
# and the dome is the boundary of the extension.
#
#   1. Chambers: every open run is a node; runs in 8-adjacent columns
#      whose y-intervals overlap are the same chamber. dt(run) = BFS
#      distance (chebyshev, 8-adj steps) to the nearest column with
#      no chamber run - i.e. distance to the AS-BUILT wall, so the
#      vault springs flush from the wall that actually stands,
#      drift and all, and junction crowns blend into one basin with
#      no seams (the "smooth uninterrupted through intersections"
#      requirement, satisfied by construction).
#   2. Vault air: each run's top is raised by min(dt, DOME_RISE) - a
#      45-degree corbel profile, fixed max height; wide caverns clamp
#      into a broad flat crown. Clamps: stop 2 below the next run's
#      floor plate in the same column (stacked corridors), below any
#      standing wall/lantern in the column (junction curtains hanging
#      into the vault space), and below the DOME_MAX_LID world roof.
#      Vault cells are simply left as the air they already are - only
#      the shell is emitted.
#   3. Shell: every non-open, non-wall, non-lantern cell touching
#      vault air laterally, plus the lid cell over each vault top
#      (over the bare run top where the rise clamps to 0). One face
#      enumeration (dome_faces) shared by the initial shell, the
#      post-stamp repair, and verify gate 13, so painter and verifier
#      cannot drift. Existing walls and lanterns count as sealing and
#      are never overwritten ("the wall wins").
#   4. Splice identity: stamped like the walls but with the y-band
#      extended by DOME_RISE+1, then in-air purge (no dome cell in
#      corridor or vault air, ever), then dome_faces as seal repair -
#      the exact stamp-wins/purge/repair triple proven on the walls.
#
# The dome is a separate cell family (never inside `walls`), so the
# floor outlines, under-lines, trim courses and lantern rules cannot
# see or recolor it - the plan's "dome material excluded from outline
# replacement" holds structurally. It only ever ADDS blocks in cells
# that are outside every open volume, so path clearance, the lateral
# seal gates and the floor stages are untouched by construction ----

class Vault:
    # vault extensions per open run. iv mirrors OpenModel (per-column
    # air intervals ABOVE the band top); top[(x, z, run_lo)] = the
    # run's highest vault air level V (V == run hi means no rise)
    def __init__(self):
        self.iv = defaultdict(list)
        self.top = {}

    def at(self, x, z, y):
        for lo, hi in self.iv.get((x, z), ()):
            if lo <= y <= hi:
                return True
        return False


def dome_faces(open_model, vault, walls, lant, dome):
    # add every missing shell cell: lateral covers of each vault air
    # cell and the lid over each vault top. Idempotent - used for the
    # initial shell, the post-stamp seal repair, and (on a copy) as
    # verify gate 13, so the three can never disagree on shape
    added = 0
    for (x, z), runs in open_model.iv.items():
        for lo, hi in runs:
            V = vault.top.get((x, z, lo), hi)
            for y in range(hi + 1, V + 2):
                cells = ([(x + dx, y, z + dz) for dx, dz in N4]
                         if y <= V else [(x, y, z)])
                for c in cells:
                    if c in dome or c in walls or c in lant:
                        continue
                    if open_model.at(c[0], c[2], c[1]) \
                            or vault.at(c[0], c[2], c[1]):
                        continue
                    dome.add(c)
                    added += 1
    return added


def run_graph(open_model):
    # the CHAMBER structure: every open run is a node, runs in
    # 8-adjacent columns with overlapping y-intervals are the same
    # chamber. Shared by the dome (BFS distance to the wall) and the
    # pier rhythm (connected components + footprint boundary), so the
    # two stages can never disagree on what a chamber is
    col_runs = {c: sorted(tuple(r) for r in rl)
                for c, rl in open_model.iv.items()}
    runs = []
    rid = {}
    for c in sorted(col_runs):
        for i, (lo, hi) in enumerate(col_runs[c]):
            rid[(c, i)] = len(runs)
            runs.append((c[0], c[1], lo, hi, i))

    def overlaps(c, lo, hi):
        for i, (l2, h2) in enumerate(col_runs.get(c, ())):
            if l2 <= hi and lo <= h2:
                yield rid[(c, i)]

    return col_runs, runs, overlaps


def paint_dome(open_model, walls, lant):
    col_runs, runs, overlaps = run_graph(open_model)

    # multi-source BFS from the wall line inward
    dt = [0] * len(runs)
    q = deque()
    for r, (x, z, lo, hi, _) in enumerate(runs):
        for dx, dz in N8:
            if next(overlaps((x + dx, z + dz), lo, hi), None) is None:
                dt[r] = 1
                q.append(r)
                break
    while q:
        r = q.popleft()
        x, z, lo, hi, _ = runs[r]
        for dx, dz in N8:
            for r2 in overlaps((x + dx, z + dz), lo, hi):
                if not dt[r2]:
                    dt[r2] = dt[r] + 1
                    q.append(r2)

    def dome_rise(d):
        # circular arch profile sampled at ring centers (dt - 0.5):
        # rises ~[2, 4, 4, 5, 5] over the default span instead of the
        # linear corbel's [1, 2, 3, 4, 5] - tall narrow steps at the
        # springline, wide flat rings toward the crown, which is what
        # reads as CURVED in blocks (the min(dt, DOME_RISE) 45-degree
        # profile read as a pyramid - Ryan 2026-08-15). Monotone in
        # dt, so the ring-nesting the shell relies on still holds
        a = min(d, DOME_SPAN) - 0.5
        return int(round(DOME_RISE * math.sqrt(
            max(0.0, 1.0 - ((DOME_SPAN - a) / DOME_SPAN) ** 2))))

    vault = Vault()
    stack_cl = roof_cl = solid_cl = 0
    for r, (x, z, lo, hi, i) in enumerate(runs):
        cap = hi + dome_rise(dt[r] or 1)
        rl = col_runs[(x, z)]
        if i + 1 < len(rl) and rl[i + 1][0] - 2 < cap:
            cap = rl[i + 1][0] - 2
            stack_cl += 1
        if cap > DOME_MAX_LID - 1:
            cap = DOME_MAX_LID - 1
            roof_cl += 1
        V = hi
        y = hi + 1
        while y <= cap and (x, y, z) not in walls \
                and (x, y, z) not in lant:
            V = y
            y += 1
        if y <= cap:
            solid_cl += 1
        if V > hi:
            vault.iv[(x, z)].append((hi + 1, V))
        vault.top[(x, z, lo)] = V

    dome = set()
    dome_faces(open_model, vault, walls, lant, dome)
    print('dome: %d blackstone shell cells over %d runs (rise<=%d; '
          'clamped: %d stacked-run, %d world-roof, %d under standing '
          'walls/lanterns)'
          % (len(dome), len(runs), DOME_RISE, stack_cl, roof_cl,
             solid_cl))
    return dome, vault


def stamp_dome(dome, regions, passes, walls, lant, open_model, vault):
    # tail == window for the vault too: same stamp-wins copy as the
    # walls, y-band extended to cover the dome, then the in-air purge
    # and a dome_faces repair pass (the walls' proven triple)
    placed = removed = guarded = 0
    for (sdx, sdy, sdz), band, _ in regions:
        for (cx, cz), (plo, phi) in band.items():
            ylo = max(int(math.floor(plo)) + BAND_LO, WORLD_MIN_Y)
            yhi = int(math.ceil(phi)) + BAND_HI + DOME_RISE + 2
            for y in range(ylo, yhi + 1):
                t = (cx - sdx, y - sdy, cz - sdz)
                if t[1] < WORLD_MIN_Y:
                    continue
                if (cx, y, cz) in dome:
                    if t not in dome:
                        if t in walls or t in lant:
                            guarded += 1
                            continue
                        d = strict_d(passes, *t)
                        if d is not None and d <= HARD_OPEN:
                            guarded += 1
                            continue
                        dome.add(t)
                        placed += 1
                elif t in dome:
                    dome.discard(t)
                    removed += 1
    gone = [p for p in dome if open_model.at(p[0], p[2], p[1])
            or vault.at(p[0], p[2], p[1])]
    for p in gone:
        dome.discard(p)
    repaired = dome_faces(open_model, vault, walls, lant, dome)
    print('dome stamp: %d placed, %d removed, %d guarded; %d in-air '
          'purged, %d faces repaired'
          % (placed, removed, guarded, len(gone), repaired))


def paint_floor(open_model, walls, slime):
    # FLOOR (Ryan 2026-08-14): solidify the BOTTOM slice of every
    # open run - the open model already defines the floor plane: each
    # corridor-air column bottoms out at path-4 (the run's lo, the
    # same slice the lantern band-interior rule reserves). This
    # inherits the old floor design's rules for free: the plate spans
    # the corridor to exactly the wall line (the footprint ends
    # there), steps 1 block with the descending path (the riser lips
    # at step boundaries sit directly under each step edge), and at
    # junction blends the LOWER level wins (merged runs bottom out at
    # the deeper corridor). Stacked corridors each get their own
    # floor (one per run). Cells already holding a wall (stamped
    # identity walls reaching the floor plane) are left to the wall -
    # "the wall wins", same as the old painter. Slime blocks and
    # their walk-trigger cells are skipped: where the maze bottoms
    # out at the world floor (y=-64) the band clips, the run's lo IS
    # the path level, and an unchecked plate would overwrite the
    # finish bounce blocks (caught by verify gate 9 on first run)
    floor = set()
    walled = skipped = 0
    for (x, z), runs in open_model.iv.items():
        for lo, hi in runs:
            if lo < WORLD_MIN_Y:
                continue
            c = (x, lo, z)
            if c in slime or (x, lo - 1, z) in slime:
                skipped += 1
                continue
            if c in walls:
                walled += 1
                continue
            floor.add(c)
    print('floor: %d cells (bottom slice of every open run; %d left '
          'to standing walls, %d skipped on slime/trigger cells)'
          % (len(floor), walled, skipped))
    return floor


def drop_hanging_remnants(walls, open_model):
    # After the in-air purge, the TOP cell of a purged standalone
    # column can survive: it sits just above the corridor air, so the
    # model-open rule cannot see it - a 1-block remnant hovering over
    # the corridor (found in-world at (4819,162,2808)). Remove every
    # wall cell that hangs DIRECTLY over corridor air with no wall
    # resting on it. Seal-safe: a face pointing at a cell that is
    # over corridor air becomes a ceiling-transition exemption, the
    # same rule extraction itself uses. Riser lips survive (nothing
    # open below them), curtain bottoms survive (wall above), curtain
    # tops survive (wall below, not air). Loop to fixpoint for
    # multi-cell remnants exposed one at a time
    total = 0
    while True:
        gone = [p for p in walls
                if open_model.at(p[0], p[2], p[1] - 1)
                and (p[0], p[1] + 1, p[2]) not in walls]
        if not gone:
            break
        for p in gone:
            walls.discard(p)
        total += len(gone)
    print('hanging remnant drop: %d cells removed' % total)
    return total


def outline_ring(floor, walls, open_model):
    # FLOOR OUTLINE ring - COMPLETE REWRITE (Ryan 2026-08-14, fifth
    # pass; the standing-wall / corner-pocket variants are retired,
    # see git history). Mirror of the sea-lantern rule, pointed
    # inward: every wall cell has lateral inside faces that touch a
    # corridor-air column; PROJECT each contact DOWN that air column
    # to the bottom of its open run and recolor the floor block
    # there. One rule, no step/terrace special cases: the outline
    # appears wherever wall face stands anywhere above the floor
    # edge, projected down - which is exactly where the lantern
    # curtain runs on the other side of the same wall. Only
    # smooth_stone floor is replaced (the floor set already excludes
    # slime/trigger cells; when the dome stage lands, lower paths'
    # domes can reach a higher floor plane and their material must be
    # excluded here too)
    # Descent risers do NOT project (Ryan 2026-08-14): a riser is a
    # 1-high wall lip with the upper floor plate resting directly on
    # it and nothing beneath - "air above" alone cannot identify it,
    # because the plate's bottom slice IS model-open floor sitting on
    # the lip. So: skip wall cells whose above-cell is model-open
    # (air or floor plate) AND that have no wall below them. Cliff
    # faces keep projecting (floor-capped top course, but wall
    # below); standing walls keep projecting (wall above)
    ring = set()
    for wx, wy, wz in walls:
        if open_model.at(wx, wz, wy + 1) \
                and (wx, wy - 1, wz) not in walls:
            continue
        for dx, dz in N4:
            cx, cz = wx + dx, wz + dz
            for lo, hi in open_model.iv.get((cx, cz), ()):
                if lo <= wy <= hi:
                    t = (cx, lo, cz)
                    if t in floor:
                        ring.add(t)
                    break
    return ring


def paint_outline(floor, walls, open_model):
    # ring (see outline_ring), then ADJACENCY CORNERS across all
    # levels the floor can sit on: where two outline cells touch
    # plan-diagonally within 2 levels of each other and share no
    # orthogonal connector (outline or wall, anywhere in the pair's
    # level window), recolor a floor cell at a connector position so
    # the line is 4-connected as seen from above. Deterministic:
    # sorted scan, first floor-holding candidate wins
    ring = outline_ring(floor, walls, open_model)
    floor_set = floor
    ring_by_plan = defaultdict(list)
    for x, y, z in ring:
        ring_by_plan[(x, z)].append(y)
    corners = set()

    def fill(ax, ay, az, bx, by, bz):
        ylo, yhi = min(ay, by) - 1, max(ay, by) + 1
        cands = []
        for cx, cz in ((bx, az), (ax, bz)):
            for yy in range(ylo, yhi + 1):
                c = (cx, yy, cz)
                if c in ring or c in corners or c in walls:
                    return
                if c in floor_set:
                    cands.append(c)
        if cands:
            corners.add(cands[0])

    for (x, z) in sorted(ring_by_plan):
        for y in sorted(ring_by_plan[(x, z)]):
            for dx, dz in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
                for by in sorted(ring_by_plan.get((x + dx, z + dz),
                                                  ())):
                    if abs(by - y) <= 2:
                        fill(x, y, z, x + dx, by, z + dz)
    outline = ring | corners
    print('floor outline: %d ring cells + %d corner fills = %d '
          'prismarine cells' % (len(ring), len(corners), len(outline)))
    return outline


def course_corners(course, walls, open_model, occupied, dy):
    # THE corner rule (Ryan 2026-08-14), shared by every trim course:
    # a corner = any smooth_stone wall cell with a course tile
    # directly on the far side (dy=+1: underneath, for the floor-side
    # courses; dy=-1: above, for the dome-side courses) AND a course
    # tile adjacent in one of the 8 plan directions at its own level,
    # WITHIN THE SAME WALL. Same-wall test: a wall cell's identity is
    # the corridor air it seals, so candidate and adjacent tile
    # connect only if the open cells they face touch (equal or
    # plan-adjacent, diagonals included); back-to-back walls of
    # different corridors face air >= 2 apart and never bridge. One
    # simultaneous pass; `occupied` cells never become corners
    def faces(wx, wy, wz):
        return [(wx + dx, wz + dz) for dx, dz in N4
                if open_model.at(wx + dx, wz + dz, wy)]

    corners = set()
    for tx, ty, tz in course:
        c = (tx, ty + dy, tz)
        if c not in walls or c in occupied:
            continue
        fc = faces(*c)
        if not fc:
            continue
        hit = False
        for dx, dz in N8:
            t = (tx + dx, ty + dy, tz + dz)
            if t not in course:
                continue
            for a in fc:
                if hit:
                    break
                for b in faces(*t):
                    if abs(a[0] - b[0]) <= 1 \
                            and abs(a[1] - b[1]) <= 1:
                        hit = True
                        break
            if hit:
                break
        if hit:
            corners.add(c)
    return corners


def paint_wall_trim(floor, walls, open_model, reserved):
    # WALL-BOTTOM TRIM (Ryan 2026-08-14): the floor's trim recipe
    # rotated onto the wall face. Same contact enumeration as
    # outline_ring (descent risers excluded, hanging curtains skip
    # via the walls-membership guard): wherever a wall column meets a
    # floored run, its bottom VISIBLE course above the floor plane
    # (lo+1) is recolored to deepslate_tiles. Recolor only: cells
    # must already be walls and must face the run's air, so no block
    # is ever added and every seal/minimality gate holds as-is.
    # DE-STACK (Ryan: "remove every deepslate_tile that is above
    # another deepslate_tile"): where the floor steps, a wall column
    # borders two runs one level apart and collects a tile for each -
    # one simultaneous pass drops every tile resting on another, so
    # only the bottom of each stack survives and the trim is a single
    # course that steps with the floor. Corners are then re-added by
    # the corner pass below.
    # SECOND COURSE (Ryan 2026-08-15): polished_deepslate = every
    # smooth_stone directly above a deepslate_tile, then corners by
    # the SAME rule run against the polished course. `reserved` =
    # cells the floor under-lines already claim (they keep
    # precedence); subtracted from the tile course BEFORE the second
    # course is derived so "above a deepslate_tile" means the tiles
    # actually emitted
    trim = set()
    for wx, wy, wz in walls:
        if open_model.at(wx, wz, wy + 1) \
                and (wx, wy - 1, wz) not in walls:
            continue   # descent riser: 1-high, floor/air-capped
        for dx, dz in N4:
            cx, cz = wx + dx, wz + dz
            for lo, hi in open_model.iv.get((cx, cz), ()):
                if lo <= wy <= hi:
                    c1 = (wx, lo + 1, wz)
                    if (cx, lo, cz) in floor and lo + 1 <= hi \
                            and c1 in walls:
                        trim.add(c1)
                    break
    stacked = {p for p in trim if (p[0], p[1] - 1, p[2]) in trim}
    trim -= stacked

    # TRIM CORNERS (Ryan 2026-08-14): a corner = any smooth_stone
    # wall cell with a tile DIRECTLY UNDERNEATH and a tile adjacent
    # in one of the 8 plan directions (diagonals included) at its own
    # level, WITHIN THE SAME WALL. Same-wall test: a wall cell's
    # identity is the corridor air it seals, so the candidate and the
    # adjacent tile connect only if the open cells they face touch
    # (equal or plan-adjacent, diagonals included). Back-to-back
    # walls of different corridors face air on opposite sides -
    # always >= 2 apart - so a corner can never bridge them. One
    # simultaneous pass against the de-stacked course (these ARE
    # tiles-above-tiles, added back on purpose where the step of the
    # trim line turns within one wall)
    corners = course_corners(trim, walls, open_model, trim, 1)
    trim |= corners
    trim -= reserved
    print('wall trim: %d deepslate_tiles bottom-course cells '
          '(%d stacked tiles removed, %d step corners re-added)'
          % (len(trim), len(stacked), len(corners)))

    trim2 = {(x, y + 1, z) for x, y, z in trim} & walls - trim
    corners2 = course_corners(trim2, walls, open_model,
                              trim | trim2, 1)
    trim2 |= corners2
    trim2 -= reserved
    print('wall trim: %d polished_deepslate second-course cells '
          '(%d corners)' % (len(trim2), len(corners2)))
    return trim, trim2


def paint_dome_trim(walls, dome, open_model, reserved):
    # DOME-TOP TRIM (Ryan 2026-08-15): the bottom trim mirrored onto
    # the springline, growing DOWNWARD from the vault. Course 1:
    # every smooth_stone wall cell DIRECTLY UNDER a blackstone dome
    # cell -> deepslate_tiles. No de-stack pass here: a stacked pair
    # would need dome cells at both y+1 and y+2 with walls at y and
    # y+1, but dome and walls are disjoint sets - stacking is
    # impossible by construction (the floor-step mechanism that
    # stacked the bottom course has no mirror). Corners by the exact
    # bottom-course rule run downward (course_corners dy=-1):
    # candidate directly UNDER a tile, N8-adjacent tile at its own
    # level, same-wall faced-air test. Course 2: polished_deepslate =
    # every smooth_stone directly under a tile, then its corners one
    # further down. `reserved` = cells the floor under-lines and the
    # bottom trim courses already claim (they keep precedence; only
    # stubby stamped columns could ever collide)
    trim3 = {(x, y, z) for x, y, z in walls
             if (x, y + 1, z) in dome} - reserved
    c3 = course_corners(trim3, walls, open_model,
                        trim3 | reserved, -1)
    trim3 |= c3
    print('dome trim: %d deepslate_tiles top-course cells '
          '(%d step corners added)' % (len(trim3), len(c3)))

    trim4 = ({(x, y - 1, z) for x, y, z in trim3}
             & walls - trim3 - reserved)
    c4 = course_corners(trim4, walls, open_model,
                        trim3 | trim4 | reserved, -1)
    trim4 |= c4
    print('dome trim: %d polished_deepslate second-course cells '
          '(%d corners)' % (len(trim4), len(c4)))
    return trim3, trim4


def paint_piers(samples, walls, reserved, regions):
    # PIER RHYTHM (Ryan 2026-08-16): the wall_test column classes
    # revived on the footprint walls - a full-height dark prismarine
    # pier with tuff-brick flanks (the "tuff | dark prismarine |
    # tuff" cluster) every PIER_RHYTHM blocks of corridor.
    # v2 - the first attempt traced chamber footprint boundaries for
    # wall ordering, but the maze air volume is ONE connected chamber
    # (junctions connect everything), so the plan projection had no
    # interior boundaries and interior walls got no piers (1499 pier
    # columns on 100k+ wall columns - see git history). The rhythm
    # now keys off the CENTERLINE instead: build_samples orders its
    # samples along each branch stream and carries (stream id,
    # cumulative horizontal arc); every wall column takes the arc of
    # the nearest sample whose band covers one of its cells, and the
    # class is a pure function of arc mod PIER_RHYTHM:
    #     [0, 1)                     -> pier (dark prismarine)
    #     [1, 2) + [PIER_RHYTHM-1,.) -> tuff flank
    # One stripe hits BOTH walls at the same arc, so piers face each
    # other across the corridor like vault ribs (the old per-side
    # walk had independent phases; paired ribs read better under the
    # dome). Full column height, curtains crossed by a stripe
    # included; the reserved courses (floor under-lines + all four
    # trim courses) keep precedence - the old "bands cross every
    # column class" rule.
    # NO VERTICAL MIXING (Ryan 2026-08-16): no smooth_stone may stand
    # directly above or below a tuff or dark prismarine cell. The one
    # mixing source was the CELL-level splice sync (a tail column
    # half-forced to the window's class, half left panel), so the
    # class is a property of each contiguous vertical WALL RUN - the
    # exact unit the invariant ranges over (cells in different runs
    # of a column never touch vertically) - and the splice sync
    # forces whole tail runs to their window run's class, matched by
    # translated y-overlap within the region band (fixpoint over the
    # highest-first regions, like the stamp). A plan-column-level
    # sync was tried first and oscillated: it ignores height, and a
    # column serving unrelated corridors (or window of one splice,
    # tail of another) gets contradictory forces. Uniform runs make
    # the invariant hold by construction - only reserved course
    # cells interrupt a run, and those are never smooth_stone.
    # Verify gate 14 hard-checks cell identity AND the invariant.
    # PALETTES (Ryan 2026-08-16): the same nearest-in-band-sample
    # search also assigns each wall run its palette level (samples
    # carry it from compute_palette via the cache) - one palette per
    # contiguous run, so a column never stripes horizontally, and the
    # same run-level splice sync forces tail runs to their window
    # run's palette. Returned as a cell->palette map for emission;
    # verify gate 15 checks splice identity
    grid = defaultdict(list)
    for sx, sz, sy, sid, arc, pal in samples:
        grid[(int(sx // 8), int(sz // 8))].append((sx, sz, sy, arc, pal))

    cols = defaultdict(list)
    for x, y, z in walls:
        cols[(x, z)].append(y)

    wall_runs = {}   # plan column -> [(ylo, yhi)] contiguous wall runs
    for c, ys in cols.items():
        s = sorted(ys)
        rl = []
        for y in s:
            if rl and y == rl[-1][1] + 1:
                rl[-1][1] = y
            else:
                rl.append([y, y])
        wall_runs[c] = [tuple(r) for r in rl]

    rcls = {}   # (x, z, run ylo) -> 0 panel, 1 pier, 2 tuff
    rpal = {}   # (x, z, run ylo) -> palette level of the nearest pass
    for (wx, wz), rl in wall_runs.items():
        for ylo, yhi in rl:
            best = None
            for ddx in (-1, 0, 1):
                for ddz in (-1, 0, 1):
                    for sx, sz, sy, arc, pal in grid.get(
                            (int(wx // 8) + ddx,
                             int(wz // 8) + ddz), ()):
                        ipy = int(round(sy))
                        if ipy + BAND_LO > yhi or ipy + BAND_HI < ylo:
                            continue
                        d = math.hypot(sx - (wx + 0.5),
                                       sz - (wz + 0.5))
                        if best is None or d < best[0]:
                            best = (d, arc, pal)
            k = p = 0
            if best is not None and best[0] <= FIELD_R:
                m = best[1] % PIER_RHYTHM
                if m < 1.0:
                    k = 1
                elif m < 2.0 or m >= PIER_RHYTHM - 1.0:
                    k = 2
                p = best[2]
            rcls[(wx, wz, ylo)] = k
            rpal[(wx, wz, ylo)] = p

    forced, rounds = 0, 0
    while True:
        rounds += 1
        assert rounds <= 20, 'pier run sync did not converge'
        n = 0
        for (sdx, sdy, sdz), band, _ in regions:
            for (cx, cz), (plo, phi) in band.items():
                ylo_b = max(int(math.floor(plo)) + BAND_LO,
                            WORLD_MIN_Y)
                yhi_b = int(math.ceil(phi)) + BAND_HI + 1
                tc = (cx - sdx, cz - sdz)
                trl = wall_runs.get(tc)
                if not trl:
                    continue
                for wlo, whi in wall_runs.get((cx, cz), ()):
                    if wlo > yhi_b or whi < ylo_b:
                        continue
                    k = rcls[(cx, cz, wlo)]
                    p = rpal[(cx, cz, wlo)]
                    for tlo, thi in trl:
                        if tlo > whi - sdy or thi < wlo - sdy:
                            continue
                        tk = (tc[0], tc[1], tlo)
                        if rcls[tk] != k or rpal[tk] != p:
                            rcls[tk] = k
                            rpal[tk] = p
                            n += 1
        forced += n
        if not n:
            break

    pier, tuff = set(), set()
    wpal = {}
    npier = ntuff = 0
    for (wx, wz), rl in wall_runs.items():
        for ylo, yhi in rl:
            k = rcls[(wx, wz, ylo)]
            p = rpal[(wx, wz, ylo)]
            if p:
                for y in range(ylo, yhi + 1):
                    wpal[(wx, y, wz)] = p
            if not k:
                continue
            tgt = pier if k == 1 else tuff
            if k == 1:
                npier += 1
            else:
                ntuff += 1
            for y in range(ylo, yhi + 1):
                tgt.add((wx, y, wz))
    pier -= reserved
    tuff -= reserved
    print('piers: %d pier / %d tuff wall runs -> %d dark prismarine '
          '+ %d tuff cells (%d tail runs forced to window class/'
          'palette, %d passes); %d wall cells past palette 0'
          % (npier, ntuff, len(pier), len(tuff), forced, rounds,
             len(wpal)))
    return pier, tuff, wpal


# ---- floor texture (Ryan 2026-08-14): the plain andesite plates get
# a DETERMINISTIC stone spiderweb (Worley cell edges - see
# worley_edge; fbm blobs and ridged-multi veins were both tried and
# rejected as too clumpy, see git history). Seamless-teleport
# identity: noise is a function of WORLD coordinates, and a splice
# tail sits at a different world position than its window - so after
# sampling, the texture choice is copied window->tail through the
# EXACT same region iteration the wall stamp uses (same y-range, same
# highest-window-first order so chained splices propagate top-down).
# Verify gate 12 re-walks the pairs and requires zero mismatches ----

def noise_hash(seed, ix, iy, iz):
    # integer lattice hash -> [0,1); pure int ops, platform-stable
    h = (ix * 374761393 + iy * 668265263 + iz * 1442695041
         + seed * 40503) & 0xffffffff
    h = ((h ^ (h >> 13)) * 1274126177) & 0xffffffff
    return ((h ^ (h >> 16)) & 0xffff) / 65535.0


def worley_edge(seed, x, y, z, size):
    # Worley (cellular) noise, edge measure: one feature point
    # jittered inside every size x size plan grid cell (y folded into
    # the hash: each floor level gets its own web; level seams hide in
    # the pattern), return F2 - F1 = second-nearest minus nearest
    # point distance. Near zero exactly on the boundary between two
    # Voronoi cells, so thresholding it low traces THIN CONNECTED
    # FILAMENTS enclosing polygonal pockets - spiderweb by
    # construction, no large groups possible (a clump would need a
    # region equidistant to two points, which is a line, not an area)
    fx, fz = x / size, z / size
    ix, iz = math.floor(fx), math.floor(fz)
    f1 = f2 = 1e9
    for dx in (-1, 0, 1):
        for dz in (-1, 0, 1):
            cx, cz = ix + dx, iz + dz
            px = cx + noise_hash(seed, cx, y, cz)
            pz = cz + noise_hash(seed + 7919, cx, y, cz)
            d = math.hypot((px - fx) * size, (pz - fz) * size)
            if d < f1:
                f1, f2 = d, f1
            elif d < f2:
                f2 = d
    return f2 - f1


def splice_pairs(regions):
    # every (window cell, tail cell) pair of every splice region, in
    # stamp order and stamp y-range - the ONE shared iteration for
    # texture copy (texture_floor) and identity check (verify gate
    # 12), so painter and verifier cannot drift
    for (sdx, sdy, sdz), band, _ in regions:
        for (cx, cz), (plo, phi) in band.items():
            ylo = max(int(math.floor(plo)) + BAND_LO, WORLD_MIN_Y)
            yhi = int(math.ceil(phi)) + BAND_HI + 1
            for y in range(ylo, yhi + 1):
                t = (cx - sdx, y - sdy, cz - sdz)
                if t[1] < WORLD_MIN_Y:
                    continue
                yield (cx, y, cz), t


def texture_floor(floor, outline, diamond, regions, seed):
    # sample the web over the plain plates, then force tail = window.
    # SWAPPED (Ryan 2026-08-14): stone fills the polygonal pockets,
    # the andesite is the thin web filaments between them
    plain = floor - outline - diamond
    stone = set()
    for x, y, z in plain:
        if worley_edge(seed, x, y, z, WEB_SIZE) >= WEB_TH:
            stone.add((x, y, z))
    # copy to FIXPOINT: one ordered pass handles simple chains (like
    # the stamp), the repeat covers overlapping tubes where a later
    # region's copy could re-break an earlier pair. Copies are always
    # window->tail so this converges unless splices were cyclic
    # (impossible: windows strictly descend); gate 12 double-checks
    forced, rounds = 0, 0
    while True:
        rounds += 1
        assert rounds <= 20, 'texture copy did not converge'
        n = 0
        for w, t in splice_pairs(regions):
            if w in plain and t in plain \
                    and (w in stone) != (t in stone):
                n += 1
                if w in stone:
                    stone.add(t)
                else:
                    stone.discard(t)
        forced += n
        if not n:
            break
    print('floor texture: %d stone / %d andesite (%.0f%% stone, web '
          'size %.1f edge<%.2f), %d tail cells forced to window '
          'texture (%d passes)'
          % (len(stone), len(plain) - len(stone),
             100.0 * len(stone) / max(1, len(plain)), WEB_SIZE,
             WEB_TH, forced, rounds))
    return stone


def palette_floor(samples, cells, regions):
    # per-cell palette for the recolorable floor cells (the prismarine
    # edge ring + the diamond ring): nearest sample whose band covers
    # the cell's level, then tail = window to fixpoint like the stone
    # texture (cell-level is safe here - the rings are single-cell
    # tall, so there is no vertical-mixing hazard). Returns
    # cell -> palette for cells past palette 0
    grid = defaultdict(list)
    for sx, sz, sy, _sid, _arc, pal in samples:
        grid[(int(sx // 8), int(sz // 8))].append((sx, sz, sy, pal))
    fpal = {}
    for x, y, z in cells:
        best = None
        for ddx in (-1, 0, 1):
            for ddz in (-1, 0, 1):
                for sx, sz, sy, pal in grid.get(
                        (int(x // 8) + ddx, int(z // 8) + ddz), ()):
                    ipy = int(round(sy))
                    if not ipy + BAND_LO <= y <= ipy + BAND_HI:
                        continue
                    d = math.hypot(sx - (x + 0.5), sz - (z + 0.5))
                    if best is None or d < best[0]:
                        best = (d, pal)
        if best is not None and best[0] <= FIELD_R and best[1]:
            fpal[(x, y, z)] = best[1]
    forced, rounds = 0, 0
    while True:
        rounds += 1
        assert rounds <= 20, 'floor palette copy did not converge'
        n = 0
        for w, t in splice_pairs(regions):
            if w in cells and t in cells \
                    and fpal.get(w, 0) != fpal.get(t, 0):
                n += 1
                if fpal.get(w, 0):
                    fpal[t] = fpal[w]
                else:
                    fpal.pop(t, None)
        forced += n
        if not n:
            break
    print('floor palette: %d ring cells past palette 0 of %d '
          '(%d tail cells forced to window palette, %d passes)'
          % (len(fpal), len(cells), forced, rounds))
    return fpal


def paint_nether(slices, walls, floor, dome, regions, wpal, fpal,
                 rings):
    # NETHERITE DIVIDER v2 (Ryan 2026-08-16): one flat vertical
    # PLANE per palette transition, perpendicular to the slime-route
    # chord at its midpoint. A wall/floor/dome cell converts when
    #   |along|   <= SLICE_HALF   (cell center's signed distance
    #                              along the route direction), and
    #   |lateral| <= RING_R       (distance from the centerline
    #                              within the plane), and
    #   y within the corridor's local vertical extent
    #                             (band bottom - 2 .. band top +
    #                              dome rise + 2 around the
    #                              midpoint's path level).
    # Pure geometry - no sample ownership. The v1 nearest-owner
    # approach sprawled across the floor where a flagged sample
    # owned a wide Voronoi territory and missed runs entirely where
    # quantization skipped the flag (in-world finding); a clipped
    # plane is exactly the "singular cross-section ring" spec.
    # Tail cells then copy their window counterparts to fixpoint
    # (same iteration as the stone texture); gate 15 checks identity
    # PLANE PARTITION (Ryan 2026-08-16): besides cutting the ring,
    # each plane also SNAPS the colors around it - every wall/floor
    # cell in the clipped cylinder but off the plane is forced to
    # the color of the side it sits on (pal1 behind the plane, pal2
    # past it), overriding the nearest-sample assignment. A cell
    # inside several cylinders takes the side of the NEAREST plane
    # (planes 5-8 blocks apart overlap; last-wins would color the
    # far side of a neighboring transition wrongly). Transitions are
    # therefore exactly flat boundaries coinciding with the ring
    wnether, fnether, dnether = set(), set(), set()
    snap = {}   # cell -> (distance to its nearest plane, side color)
    ylo_off = BAND_LO - 2
    yhi_off = BAND_HI + DOME_RISE + 2
    for mx, mz, my, ux, uz, p1, p2 in slices:
        for cx in range(int(mx - RING_R) - 1, int(mx + RING_R) + 2):
            for cz in range(int(mz - RING_R) - 1,
                            int(mz + RING_R) + 2):
                dx = cx + 0.5 - mx
                dz = cz + 0.5 - mz
                if math.hypot(dx, dz) > RING_R:
                    continue                      # outside the ring
                along = dx * ux + dz * uz
                on_plane = abs(along) <= SLICE_HALF
                side = p1 if along < 0 else p2
                for y in range(int(my) + ylo_off,
                               int(my) + yhi_off + 1):
                    c = (cx, y, cz)
                    if on_plane:
                        if c in walls:
                            wnether.add(c)
                        elif c in floor:
                            fnether.add(c)
                        elif c in dome:
                            dnether.add(c)
                    elif c in walls or c in floor:
                        e = snap.get(c)
                        if e is None or abs(along) < e[0]:
                            snap[c] = (abs(along), side)
    snapped = 0
    for c, (_d, side) in snap.items():
        tgt = wpal if c in walls else fpal
        if tgt.get(c, 0) != side:
            snapped += 1
            if side:
                tgt[c] = side
            else:
                tgt.pop(c, None)

    # CROSS-CORRIDOR BOUNDARY PLANES (Ryan 2026-08-16): where the
    # territories of two corridors meet mid-cavern, their colors
    # collide with no path chord - and so no plane - to mark it
    # (found in-world: unexplained base patches against colored
    # rings). Every adjacent differently-colored pair now goes
    # netherite on both sides: walls per horizontal N4 (colors are
    # column-uniform, so this yields full-height bands
    # automatically), floor RING cells per 3D chebyshev-1 (the
    # visible lines; plain floor and stone are constant materials -
    # a color boundary there is invisible and gets no mark).
    # Divider-ring cells count as colorless: comparisons skip them
    badd = set()
    for x, y, z in walls:
        c = (x, y, z)
        if c in wnether:
            continue
        c0 = wpal.get(c, 0)
        for dx, dz in N4:
            nb = (x + dx, y, z + dz)
            if nb in walls and nb not in wnether \
                    and wpal.get(nb, 0) != c0:
                badd.add(c)
                badd.add(nb)
    nb_wall = len(badd)
    wnether |= badd
    badd = set()
    for x, y, z in rings:
        c = (x, y, z)
        if c in fnether:
            continue
        c0 = fpal.get(c, 0)
        for dx, dz in N8:
            for dy in (-1, 0, 1):
                nb = (x + dx, y + dy, z + dz)
                if nb in rings and nb not in fnether \
                        and fpal.get(nb, 0) != c0:
                    badd.add(c)
                    badd.add(nb)
    nb_ring = len(badd)
    fnether |= badd
    forced, rounds = 0, 0
    while True:
        rounds += 1
        assert rounds <= 20, 'nether copy did not converge'
        n = 0
        for w, t in splice_pairs(regions):
            for cells, tgt in ((walls, wnether), (floor, fnether),
                               (dome, dnether)):
                if w in cells and t in cells \
                        and (w in tgt) != (t in tgt):
                    n += 1
                    if w in tgt:
                        tgt.add(t)
                    else:
                        tgt.discard(t)
            for cells, pmap in ((walls, wpal), (floor, fpal)):
                if w in cells and t in cells \
                        and pmap.get(w, 0) != pmap.get(t, 0):
                    n += 1
                    if pmap.get(w, 0):
                        pmap[t] = pmap[w]
                    else:
                        pmap.pop(t, None)
        forced += n
        if not n:
            break
    print('netherite divider: %d planes -> %d wall + %d floor + %d '
          'dome cells (%d wall + %d ring cells from cross-corridor '
          'boundaries), %d cells color-snapped to their plane side '
          '(%d tail cells forced to window, %d passes)'
          % (len(slices), len(wnether), len(fnether), len(dnether),
             nb_wall, nb_ring, snapped, forced, rounds))
    return wnether, fnether, dnether


def diagnose(slices, open_model, walls, floor, dome, wnether,
             fnether, dnether, outline, diamond, samples, fpal):
    # one-off investigation pass (Ryan 2026-08-16): (A) ring cells
    # with no owning sample - they keep base prismarine/diamond
    # through transitions; (B) per-plane vertical audit - ring cells
    # punched into a DIFFERENT stacked corridor's open run, and dome
    # cells above the fixed y-clip that the ring missed
    rings = outline | diamond
    grid = defaultdict(list)
    for sx, sz, sy, _sid, _arc, _pal in samples:
        grid[(int(sx // 8), int(sz // 8))].append((sx, sz, sy))
    orphan = []
    for x, y, z in rings:
        best = None
        for ddx in (-1, 0, 1):
            for ddz in (-1, 0, 1):
                for sx, sz, sy in grid.get(
                        (int(x // 8) + ddx, int(z // 8) + ddz), ()):
                    ipy = int(round(sy))
                    if not ipy + BAND_LO <= y <= ipy + BAND_HI:
                        continue
                    d = math.hypot(sx - (x + 0.5), sz - (z + 0.5))
                    if best is None or d < best:
                        best = d
        if best is None or best > FIELD_R:
            orphan.append(((x, y, z), best))
    print('diagnose A: %d of %d ring cells have NO owning sample '
          'within FIELD_R %.1f -> they keep base material through '
          'any transition' % (len(orphan), len(rings), FIELD_R))
    for (x, y, z), b in orphan[:6]:
        print('   orphan ring cell (%d,%d,%d) nearest in-band '
              'sample %s' % (x, y, z, '%.2f' % b if b else 'none'))

    # A2: base-material ring cells directly against COLORED ring
    # cells with no divider plane nearby to explain the boundary -
    # the reported "ring not included in the transition" cases
    a2 = []
    for x, y, z in rings:
        if fpal.get((x, y, z), 0):
            continue
        hit = None
        for dx2 in (-1, 0, 1):
            for dz2 in (-1, 0, 1):
                for dy2 in (-1, 0, 1):
                    c = (x + dx2, y + dy2, z + dz2)
                    if c in rings and fpal.get(c, 0):
                        hit = fpal[c]
                        break
        if hit is None:
            continue
        near = any(math.hypot(x + 0.5 - mx, z + 0.5 - mz)
                   <= RING_R + 2 and abs(y - my) < 16
                   for mx, mz, my, _ux, _uz, _p1, _p2 in slices)
        if not near:
            a2.append(((x, y, z), hit))
    print('diagnose A2: %d base-material ring cells touch a colored '
          'ring cell with NO plane within %.1f (unexplained base '
          'patch)' % (len(a2), RING_R + 2))
    for (x, y, z), h in a2[:8]:
        print('   base ring cell (%d,%d,%d) beside color %d'
              % (x, y, z, h))

    ylo_off = BAND_LO - 2
    yhi_off = BAND_HI + DOME_RISE + 2
    ph_planes = dm_planes = 0
    ph_cells = dm_cells = 0
    exph, exdm = [], []
    nset = wnether | fnether | dnether
    for mx, mz, my, ux, uz, p1, p2 in slices:
        foreign = missed = 0
        for cx in range(int(mx - RING_R) - 1, int(mx + RING_R) + 2):
            for cz in range(int(mz - RING_R) - 1,
                            int(mz + RING_R) + 2):
                dx = cx + 0.5 - mx
                dz = cz + 0.5 - mz
                if math.hypot(dx, dz) > RING_R:
                    continue
                if abs(dx * ux + dz * uz) > SLICE_HALF:
                    continue
                # a column's runs, pooled over its N8 neighborhood
                # (wall columns have no run of their own - they seal
                # the runs beside them)
                own_hi = None
                stacked = []
                for ax in (-1, 0, 1):
                    for az in (-1, 0, 1):
                        for lo, hi in open_model.iv.get(
                                (cx + ax, cz + az), ()):
                            if lo <= my + BAND_HI \
                                    and hi >= my + BAND_LO:
                                if own_hi is None or hi > own_hi[1]:
                                    own_hi = (lo, hi)
                            else:
                                stacked.append((lo, hi))
                for y in range(int(my) + ylo_off,
                               int(my) + yhi_off + 1):
                    if (cx, y, cz) in nset:
                        in_own = own_hi is not None and \
                            own_hi[0] - 3 <= y \
                            <= own_hi[1] + DOME_RISE + 2
                        in_stk = any(lo - 3 <= y <= hi + DOME_RISE + 2
                                     for lo, hi in stacked)
                        if not in_own and in_stk:
                            foreign += 1
                            if len(exph) < 6:
                                exph.append((cx, y, cz))
                if own_hi is not None:
                    for y in range(int(my) + yhi_off + 1,
                                   own_hi[1] + DOME_RISE + 3):
                        if (cx, y, cz) in dome:
                            missed += 1
                            if len(exdm) < 6:
                                exdm.append((cx, y, cz))
        if foreign:
            ph_planes += 1
            ph_cells += foreign
        if missed:
            dm_planes += 1
            dm_cells += missed
    print('diagnose B1: %d of %d planes punched %d netherite cells '
          'into a STACKED corridor (cell seals another open run, '
          'not the transition band, inside the fixed y-clip '
          '%+d..%+d)'
          % (ph_planes, len(slices), ph_cells, ylo_off, yhi_off))
    for c in exph:
        print('   stacked-corridor netherite at (%d,%d,%d)' % c)
    print('diagnose B2: %d of %d planes have %d dome cells in their '
          'slab ABOVE the y-clip (tall merged caverns - ring never '
          'reaches the vault)'
          % (dm_planes, len(slices), dm_cells))
    for c in exdm:
        print('   missed dome cell at (%d,%d,%d)' % c)


def paint_decor(blocks, slime, occupied):
    # SLIME-BLOCK DRESSING (copied verbatim from wall_test - Ryan:
    # "It was perfect"): light blue carpet above every bounce block
    # with a full-bright light block above the carpet, a top slab
    # below it, and open trapdoors hugging all four sides (facing
    # away from the block, bottom half, open - the open panels press
    # flush against the slime faces). Slab/door/carpet materials are
    # palette-keyed (DECOR_*). Cells holding another slime block, an
    # earlier dressing cell, or a decoration block (walls/floor/dome/
    # lanterns at tight seams) are skipped, so build order cannot
    # matter. Identical per block by construction - block palettes
    # are splice-synced by compute_palette, so tails match their
    # windows without stamping
    claimed = {}
    skipped = 0
    for x, y, z, bp in blocks:
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
            if pos in slime or pos in claimed or pos in occupied:
                skipped += 1
                continue
            claimed[pos] = mat
    print('slime dressing: %d bounce blocks, %d dressing cells '
          '(%d skipped: occupied)'
          % (len(blocks), len(claimed), skipped))
    return claimed


def tail_tube_index(regions):
    # plan cell -> True for every tail-tube column (violation triage)
    tails = {}
    for (sdx, sdy, sdz), band, _ in regions:
        for (cx, cz), (plo, phi) in band.items():
            tails[(cx - sdx, cz - sdz)] = True
    return tails


# ---- verification on the final model ----

def verify(passes, open_model, walls, data, regions, lant=None,
           floor=None, outline=None, outline2=None, stone=None,
           dome=None, vault=None, pier=None, tuff=None, wres=None,
           wpal=None, fpal=None, wnether=None, fnether=None,
           dnether=None):
    slime = set(data['slime'])
    tails = tail_tube_index(regions)
    ok = True

    # 1. seal + enclosure (HARD GATE, everywhere - splice tubes
    #    included since seal_repair): every horizontal face of every
    #    corridor-air cell must be air, wall, or a band-step front
    #    (air on the slice below - the corridor's own band descending
    #    with the path; vertical enclosure is the dome's and floor's
    #    job in later stages). With all 4 faces of every open cell
    #    sealed, no lateral line of sight or movement can leave the
    #    corridor volume: the sections are laterally ENCLOSED
    viol_in_tube, viol_outside = [], []
    for x, y, z in open_model.cells():
        for dx, dz in N4:
            nx, nz = x + dx, z + dz
            if open_model.at(nx, nz, y) or (nx, y, nz) in walls \
                    or open_model.at(nx, nz, y - 1):
                continue
            (viol_in_tube if (nx, nz) in tails or (x, z) in tails
             else viol_outside).append((x, y, z, nx, nz))
    print('seal: %d unsealed faces outside splice tubes, %d inside'
          % (len(viol_outside), len(viol_in_tube)))
    for v in (viol_outside + viol_in_tube)[:10]:
        print('  SEAL BREAK open (%d,%d,%d) face -> (%d,%d)' % v)
    if viol_outside or viol_in_tube:
        ok = False
    else:
        print('  every lateral face of every corridor-air cell is '
              'sealed: sections are laterally enclosed')

    # 2. intrusions (HARD GATE since the in-air purge): no wall cell
    #    may stand in corridor air, anywhere, for any reason
    intr = [p for p in walls if open_model.at(p[0], p[2], p[1])]
    print('intrusions (wall inside corridor air): %d (must be 0)'
          % len(intr))
    for v in intr[:10]:
        print('  INTRUSION at (%d,%d,%d)' % v)
    if intr:
        ok = False

    # 3. path clearance: never on a slime block or its trigger cell
    bad = [p for p in walls
           if p in slime or (p[0], p[1] - 1, p[2]) in slime]
    print('path clearance: %d wall cells on slime/trigger cells'
          % len(bad))
    if bad:
        ok = False
        for v in bad[:10]:
            print('  PATH HIT at (%d,%d,%d)' % v)

    # 4. drift: lateral wall cells' distance to the nearest pass whose
    #    band strictly covers their slice. Cells with no strict-band
    #    pass are risers / band-edge cells (their pass covers y+-1) or
    #    far stamp copies - counted separately, they have no
    #    meaningful lateral distance
    hist = defaultdict(int)
    edge = far = 0
    for x, y, z in walls:
        best = strict_d(passes, x, y, z)
        if best is not None:
            hist[round(best * 2) / 2] += 1
            continue
        e = passes.get((x, z))
        near = e and any(ipy + BAND_LO - 1 <= y <= ipy + BAND_HI + 1
                         for ipy in e)
        if near:
            edge += 1
        else:
            far += 1
    print('drift: %s' % ', '.join('%.1f:%d' % (k, hist[k])
                                  for k in sorted(hist)))
    print('       + %d band-edge cells (risers/ceiling), %d far '
          'stamp copies' % (edge, far))

    # 5. floaters: wall cells hanging over corridor air with no wall
    #    directly above - they read as debris (the "partial wall"
    #    in-world report). The painter cannot produce them (extraction
    #    suppresses open-below cells, closure only adds flush under an
    #    existing wall), so any that appear are stamp copies
    floats = [(x, y, z) for x, y, z in walls
              if open_model.at(x, z, y - 1) and (x, y + 1, z) not in walls]
    print('floaters (over corridor air, nothing above): %d'
          % len(floats))
    for v in floats[:10]:
        print('  floater at (%d,%d,%d)' % v)

    # 6. hanging runs: wall column runs whose BOTTOM cell sits over
    #    corridor air. The floater metric (5) structurally misses
    #    multi-cell hangs (each cell has wall above or wall below), so
    #    this walks whole runs. Long hangs are junction curtains - an
    #    upper corridor's wall ending at a lower corridor's ceiling
    #    level, intended. Short hangs (<=3) were the band-top fuzz
    #    fragments; upward-open propagation should hold them at ~0
    cols2 = defaultdict(list)
    for x, y, z in walls:
        cols2[(x, z)].append(y)
    hang_short, hang_long = [], 0
    for (x, z), wys in cols2.items():
        s = sorted(wys)
        i, n = 0, len(s)
        while i < n:
            j = i
            while j + 1 < n and s[j + 1] == s[j] + 1:
                j += 1
            if open_model.at(x, z, s[i] - 1):
                if s[j] - s[i] + 1 <= 3:
                    hang_short.append((x, s[i], z))
                else:
                    hang_long += 1
            i = j + 1
    print('hanging runs: %d short (<=3, fuzz fragments), %d long '
          '(junction curtains)' % (len(hang_short), hang_long))
    for v in hang_short[:10]:
        print('  short hang bottom at (%d,%d,%d)' % v)

    # 7. minimality (HARD GATE since the outside-shell scan): every
    #    wall cell seals at least one face - the shell is as thin as
    #    possible, ready for the lantern wrap
    buried = sum(1 for x, y, z in walls
                 if not any(open_model.at(x + dx, z + dz, y)
                            for dx, dz in N4))
    print('minimality: %d wall cells, %d non-sealing (must be 0)'
          % (len(walls), buried))
    if buried:
        ok = False

    # 8. lantern encasement (HARD GATE when the layer is painted):
    #    every LATERAL face of every wall cell touches corridor air,
    #    wall, or lantern - or is bare specifically because of the
    #    no-vertical-contact rule (a lantern there would sit on/under
    #    stone). And no lantern breaks the placement rules: never in
    #    corridor air, never in stone, never with stone directly
    #    above or below
    if lant is not None:
        exposed = excluded = 0
        for x, y, z in walls:
            for dx, dz in N4:
                c = (x + dx, y, z + dz)
                if c in walls or c in lant \
                        or open_model.at(c[0], c[2], c[1]):
                    continue
                if lantern_eligible(c[0], y, c[2], walls, open_model):
                    exposed += 1
                else:
                    excluded += 1
        bad = sum(1 for c in lant
                  if not lantern_eligible(c[0], c[1], c[2], walls,
                                          open_model))
        print('encasement: %d lantern cells, %d eligible-but-bare '
              'lateral wall faces (must be 0), %d faces bare by the '
              'placement rules (band edges, vertical clearance), '
              '%d rule-breaking lanterns (must be 0)'
              % (len(lant), exposed, excluded, bad))
        if exposed or bad:
            ok = False

    # 9. floor coverage (HARD GATE when the floor is painted): every
    #    open run's bottom cell holds floor or a standing wall - the
    #    corridors are closed from below; and no floor cell sits on a
    #    slime block, a trigger cell, or coincides with wall/lantern
    if floor is not None:
        missing = 0
        for (x, z), runs in open_model.iv.items():
            for lo, hi in runs:
                if lo >= WORLD_MIN_Y and (x, lo, z) not in floor \
                        and (x, lo, z) not in walls \
                        and (x, lo, z) not in slime \
                        and (x, lo - 1, z) not in slime:
                    missing += 1
        fbad = sum(1 for p in floor
                   if p in slime or (p[0], p[1] - 1, p[2]) in slime
                   or p in walls or (lant and p in lant))
        print('floor: %d cells, %d uncovered run bottoms (must be 0), '
              '%d misplaced cells (must be 0)'
              % (len(floor), missing, fbad))
        if missing or fbad:
            ok = False

    # 10. floor outline (HARD GATE when painted): the ring is
    #     complete (every floor cell against a wall is outlined), it
    #     stays on the floor, and it is 4-CONNECTED: any two
    #     diagonally-touching outline cells share an orthogonal
    #     neighbour that is outline or wall (the corner-fill
    #     guarantee)
    if outline is not None:
        o_missing = sum(1 for p in outline_ring(floor, walls,
                                                open_model)
                        if p not in outline)
        o_off = sum(1 for p in outline if p not in floor)
        o_diag = 0
        out_by_plan = defaultdict(list)
        for x, y, z in outline:
            out_by_plan[(x, z)].append(y)
        for (x, z), ys in out_by_plan.items():
            for y in ys:
                for dx, dz in ((1, 1), (1, -1)):
                    for by in out_by_plan.get((x + dx, z + dz), ()):
                        if abs(by - y) > 2:
                            continue
                        joined = False
                        for cx, cz in ((x + dx, z), (x, z + dz)):
                            for yy in range(min(y, by) - 1,
                                            max(y, by) + 2):
                                c = (cx, yy, cz)
                                if c in outline or c in walls:
                                    joined = True
                        if not joined:
                            o_diag += 1
        print('outline: %d cells, %d wall-adjacent floor cells missed '
              '(must be 0), %d off-floor (must be 0), %d diagonal-only '
              'joints (must be 0)'
              % (len(outline), o_missing, o_off, o_diag))
        if o_missing or o_off or o_diag:
            ok = False

    # 11. second outline (HARD GATE when painted): diamond cells are
    #     floor, never overlap the prismarine line, and every one
    #     touches prismarine or another diamond horizontally (no
    #     strays)
    if outline2 is not None:
        d_off = sum(1 for p in outline2
                    if p not in floor or p in outline)
        stray = sum(
            1 for x, y, z in outline2
            if not any((x + dx, y, z + dz) in outline
                       or (x + dx, y, z + dz) in outline2
                       or (x + dx, y, z + dz) in walls
                       for dx, dz in N4))
        print('outline2 (diamond): %d cells, %d off-floor/overlap '
              '(must be 0), %d strays (must be 0)'
              % (len(outline2), d_off, stray))
        if d_off or stray:
            ok = False

    # 12. floor texture identity (HARD GATE when textured): re-walk
    #     every splice pair (the same shared iteration texture_floor
    #     copied through) - wherever window AND tail are both plain
    #     plates, the andesite/stone choice must be IDENTICAL, or the
    #     teleport swap would visibly retexture the floor. One-sided
    #     pairs (plain on one end only) are the already-accepted
    #     geometry divergences - reported, not gated
    if stone is not None and floor is not None:
        plain = floor - (outline or set()) - (outline2 or set())
        t_mm = t_side = 0
        for w, t in splice_pairs(regions):
            wp, tp = w in plain, t in plain
            if wp and tp:
                if (w in stone) != (t in stone):
                    t_mm += 1
            elif wp != tp:
                t_side += 1
        print('texture: %d stone cells, %d window/tail texture '
              'mismatches (must be 0), %d one-sided pairs (geometry '
              'divergences, accepted)' % (len(stone), t_mm, t_side))
        if t_mm:
            ok = False

    # 13. dome enclosure (HARD GATE when the dome is painted): the
    #     deferred VERTICAL half of gate 1. dome_faces on a copy
    #     returns exactly the unsealed vault faces (the painter, the
    #     repair pass and this gate share the one enumeration, so 0
    #     added means every run top and every vault air cell is
    #     lidded by dome/wall/lantern). Plus: no dome cell inside
    #     corridor or vault air, none overlapping walls or lanterns,
    #     none on slime/trigger cells
    if dome is not None:
        unsealed = dome_faces(open_model, vault, walls, lant or set(),
                              set(dome))
        d_air = sum(1 for p in dome
                    if open_model.at(p[0], p[2], p[1])
                    or vault.at(p[0], p[2], p[1]))
        d_over = sum(1 for p in dome
                     if p in walls or (lant and p in lant))
        d_slime = sum(1 for p in dome
                      if p in slime or (p[0], p[1] - 1, p[2]) in slime)
        print('dome: %d cells, %d unsealed vault faces (must be 0), '
              '%d in corridor/vault air (must be 0), %d overlapping '
              'walls/lanterns (must be 0), %d on slime/trigger '
              '(must be 0)'
              % (len(dome), unsealed, d_air, d_over, d_slime))
        if unsealed or d_air or d_over or d_slime:
            ok = False

    # 14. pier class identity + NO VERTICAL MIXING (HARD GATES when
    #     painted): both-wall splice pairs outside the reserved
    #     courses must agree on the pier/tuff/panel class (or the
    #     teleport swap would visibly reskin the wall face), and no
    #     panel (glass-body) wall cell may stand directly above or
    #     below a pier or tuff cell (Ryan 2026-08-16; the column-uniform
    #     classification makes this hold by construction, this gate
    #     proves it survived every later pass)
    if pier is not None:
        mm = both = 0
        for w, t in splice_pairs(regions):
            if w in walls and t in walls \
                    and w not in wres and t not in wres:
                both += 1
                if (w in pier) != (t in pier) \
                        or (w in tuff) != (t in tuff):
                    mm += 1
        vert = 0
        for x, y, z in pier | tuff:
            for dy in (1, -1):
                c = (x, y + dy, z)
                if c in walls and c not in pier and c not in tuff \
                        and c not in wres:
                    vert += 1
        print('piers: %d dark prismarine / %d tuff cells, %d class '
              'mismatches among %d both-wall splice pairs (must be '
              '0), %d panel (glass) cells vertically touching '
              'pier/tuff (must be 0)'
              % (len(pier), len(tuff), mm, both, vert))
        if mm or vert:
            ok = False

    # 15. palette splice identity (HARD GATE when painted): every
    #     both-wall splice pair must agree on the palette level (the
    #     nearest-sample assignment could otherwise bleed a foreign
    #     corridor's color into a tail tube - the exact failure mode
    #     of the old pipeline), and the same for the recolorable
    #     floor ring cells. compute_palette already syncs the BLOCK
    #     levels; this proves the CELL assignment survived too
    if wpal is not None:
        wm = fm = nm = 0
        rings = (outline | outline2) if outline is not None else set()
        for w, t in splice_pairs(regions):
            if w in walls and t in walls:
                if wpal.get(w, 0) != wpal.get(t, 0):
                    wm += 1
                if (w in wnether) != (t in wnether):
                    nm += 1
            if w in rings and t in rings \
                    and fpal.get(w, 0) != fpal.get(t, 0):
                fm += 1
            if floor is not None and w in floor and t in floor \
                    and (w in fnether) != (t in fnether):
                nm += 1
            if dome is not None and w in dome and t in dome \
                    and (w in dnether) != (t in dnether):
                nm += 1
        dist = defaultdict(int)
        for p in wpal.values():
            dist[p] += 1
        print('palette: %d wall / %d floor-ring splice pairs with '
              'mismatched palettes, %d netherite mismatches (all '
              'must be 0); wall cells per level: %s'
              % (wm, fm, nm, ', '.join('%d:%d' % kv
                                       for kv in sorted(dist.items()))))
        if wm or fm or nm:
            ok = False
    return ok


# ---- preview rendering ----

def render_previews(previews, walls, data, preview_dir):
    from PIL import Image
    os.makedirs(preview_dir, exist_ok=True)
    slime_by_y = defaultdict(set)
    for x, y, z in data['slime']:
        slime_by_y[y].add((x, z))
    wall_by_y = defaultdict(set)
    for x, y, z in walls:
        wall_by_y[y].add((x, z))
    for y, (fld, open_set) in sorted(previews.items()):
        cells = set(fld) | wall_by_y[y]
        if not cells:
            continue
        xs = [c[0] for c in cells]
        zs = [c[1] for c in cells]
        x0, z0 = min(xs) - 2, min(zs) - 2
        w, h = max(xs) - x0 + 3, max(zs) - z0 + 3
        img = Image.new('RGB', (w, h), (12, 12, 16))
        px = img.load()
        for c, d in fld.items():
            if c in open_set:
                col = (20, 90, 110) if d > HARD_OPEN else (16, 60, 80)
            else:
                col = (35, 35, 42) if d < HARD_OUT else (22, 22, 28)
            px[c[0] - x0, c[1] - z0] = col
        for c in wall_by_y[y]:
            px[c[0] - x0, c[1] - z0] = (225, 225, 220)
        for yy in (y, y - 1, y - 2):    # path within the slice band
            for c in slime_by_y.get(yy, ()):
                if 0 <= c[0] - x0 < w and 0 <= c[1] - z0 < h:
                    px[c[0] - x0, c[1] - z0] = (60, 220, 60)
        img = img.resize((w * 2, h * 2), Image.NEAREST)
        img.save(os.path.join(preview_dir, 'slice_y%04d.png' % y))
    print('preview: %d slice images -> %s'
          % (len(previews), preview_dir))


# ---- emission (port of wall_test's family_groups + split) ----

def family_groups(cells, mat):
    # vertical runs per column, identical runs merged across
    # consecutive z, one /fill (or /setblock) per merged run
    cols = defaultdict(list)
    for x, y, z in cells:
        cols[(x, z)].append(y)
    vruns = []
    for (x, z), ys in sorted(cols.items()):
        run = None
        for y in sorted(ys):
            if run and y == run[1] + 1:
                run[1] = y
            else:
                if run:
                    vruns.append((x, run[0], run[1], z))
                run = [y, y]
        if run:
            vruns.append((x, run[0], run[1], z))
    vruns.sort()
    zr = []
    for x, ylo, yhi, z in vruns:
        if zr and zr[-1][0] == x and zr[-1][1] == ylo \
                and zr[-1][2] == yhi and zr[-1][4] == z - 1:
            zr[-1][4] = z
        else:
            zr.append([x, ylo, yhi, z, z])
    build, undo = [], []
    for x, ylo, yhi, z1, z2 in zr:
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


def emit(walls, lant, floor, outline, under, diamond, under2, stone,
         trim, trim2, dome, pier, tuff, wpal, fpal, wnether, fnether,
         dnether, decor, outdir, seed):
    # `under`/`under2` = wall cells directly beneath outline cells
    # (riser lips under upper-plate edges, cliff top courses - no
    # smooth_stone in the floor underneath the lines), in the line
    # materials; `trim`/`trim2` = the wall-bottom courses
    # (paint_wall_trim), deepslate_tiles + polished_deepslate.
    # Model-wise all four stay walls - material only. Whatever wall
    # cell no course claims is the panel body: cyan stained glass
    # (the lantern curtain behind it provides the glow) - no
    # smooth_stone remains on the walls.
    # PALETTES: the four recolorable families (glass body, both
    # under-lines, piers on walls; both rings on the floor) are
    # partitioned by their cell's palette level and each partition
    # emits in the palette's remap of the base material

    def pal_groups(cells, mat, pmap):
        parts = defaultdict(set)
        for c in cells:
            parts[pmap.get(c, 0)].add(c)
        build, undo = [], []
        for p in sorted(parts):
            m = PALETTES[p].get(mat, mat) if p else mat
            b, u = family_groups(parts[p], m)
            build += b
            undo += u
        return build, undo

    recolored = under | under2 | trim | trim2 | pier | tuff | wnether
    w_build, w_undo = pal_groups(walls - recolored, GLASS_MAT, wpal)
    for cells, mat in ((under - wnether, OUTLINE_MAT),
                       (under2 - wnether, DIAMOND_MAT),
                       (pier - wnether, PIER_MAT)):
        b, u = pal_groups(cells, mat, wpal)
        w_build += b
        w_undo += u
    for cells, mat in ((trim - wnether, TRIM1_MAT),
                       (trim2 - wnether, TRIM2_MAT),
                       (tuff - wnether, TUFF_MAT),
                       (wnether, NETHER_MAT)):
        b, u = family_groups(cells, mat)
        w_build += b
        w_undo += u
    l_build, l_undo = family_groups(lant, LANTERN)
    d_build, d_undo = family_groups(dome - dnether, DOME_MAT)
    b, u = family_groups(dnether, NETHER_MAT)
    d_build += b
    d_undo += u
    # the floor chains carry all floor materials: plain plates (the
    # andesite/stone noise mix), the prismarine line, the diamond
    # line (removefloor air-fills all)
    f_build, f_undo = family_groups(
        floor - outline - diamond - stone - fnether, FLOOR_MAT)
    for cells, mat in ((stone - fnether, STONE_MAT),
                       (fnether, NETHER_MAT)):
        b, u = family_groups(cells, mat)
        f_build += b
        f_undo += u
    for cells, mat in ((outline - fnether, OUTLINE_MAT),
                       (diamond - fnether, DIAMOND_MAT)):
        b, u = pal_groups(cells, mat, fpal)
        f_build += b
        f_undo += u
    # slime dressing: single setblocks (slabs, trapdoors, carpet,
    # light - block states, so no fill merging)
    x_build = [(pos, ['@bypass /setblock %d %d %d %s strict'
                      % (pos[0], pos[1], pos[2], mat)])
               for pos, mat in sorted(decor.items())]
    x_undo = [(pos, ['@bypass /setblock %d %d %d minecraft:air '
                     'strict' % pos])
              for pos in sorted(decor)]
    print('emission: %d wall cells (%d/%d under lines, %d/%d trim '
          'courses, %d/%d pier/tuff) -> %d commands, %d lantern '
          'cells -> %d commands, %d dome cells -> %d commands, '
          '%d floor cells (%d stone, %d prismarine, %d diamond) -> '
          '%d commands, %d dressing cells'
          % (len(walls), len(under), len(under2), len(trim),
             len(trim2), len(pier), len(tuff), len(w_build),
             len(lant), len(l_build), len(dome), len(d_build),
             len(floor), len(stone), len(outline), len(diamond),
             len(f_build), len(decor)))

    def split(groups):
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

    fndir = os.path.join(outdir, gm.NAMESPACE)
    # stage 1 owns walls/lanterns and the retired dome/floor slots:
    # stale parts would import as undeclared, never-called functions
    for old in os.listdir(fndir):
        if re.fullmatch(r'(?:remove)?(?:walls|lanterns|dome|floor'
                        r'|decor)\d+\.msc', old):
            os.remove(os.path.join(fndir, old))
    names = []
    for name, groups, done in (('walls', w_build, '&aWalls built!'),
                               ('removewalls', w_undo,
                                '&aWalls removed.'),
                               ('lanterns', l_build,
                                '&aLantern layer built!'),
                               ('removelanterns', l_undo,
                                '&aLantern layer removed.'),
                               ('dome', d_build, '&aDome built!'),
                               ('removedome', d_undo,
                                '&aDome removed.'),
                               ('floor', f_build, '&aFloor built!'),
                               ('removefloor', f_undo,
                                '&aFloor removed.'),
                               ('decor', x_build,
                                '&aSlime dressing built!'),
                               ('removedecor', x_undo,
                                '&aSlime dressing removed.')):
        parts = split(groups)
        for k, body in enumerate(parts, 1):
            head = ['# %s%d(Player player)' % (name, k),
                    '# stage-1 footprint walls (walls.py), part %d of %d'
                    % (k, len(parts)),
                    '# seed %d, open<%.1f drift +-1, band path%+d..%+d'
                    % (seed, OPEN_INIT, BAND_LO, BAND_HI),
                    '', '@using %s' % gm.NAMESPACE, '']
            tail = (['', '@var %s%d(player)' % (name, k + 1)]
                    if k < len(parts)
                    else ['', gm.DONE_SOUND, '@player %s' % done])
            write(os.path.join(fndir, '%s%d.msc' % (name, k)),
                  head + body + tail)
            names.append('%s%d' % (name, k))

    nms_path = os.path.join(outdir, '%s.nms' % gm.NAMESPACE)
    nms_lines = [l for l in open(nms_path).read().splitlines()
                 if not re.fullmatch(r'\s*(?:remove)?'
                                     r'(?:walls|lanterns|dome|floor'
                                     r'|decor)\d+\(Player player\)\s*',
                                     l)]
    at = nms_lines.index('@endnamespace')
    nms_lines[at:at] = ['    %s(Player player)' % n for n in names]
    with open(nms_path, 'w', newline='\n') as fh:
        fh.write('\n'.join(nms_lines) + '\n')
    print('functions: %s' % ', '.join(names))
    print('run:  /function execute %s::walls1(Player("You"))'
          % gm.NAMESPACE)
    print('undo: /function execute %s::removewalls1(Player("You"))'
          % gm.NAMESPACE)
    print('lanterns: /function execute %s::lanterns1(Player("You"))'
          % gm.NAMESPACE)
    print('undo:     /function execute %s::removelanterns1'
          '(Player("You"))' % gm.NAMESPACE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('outdir', help='sandbox dir holding slimemaze.nms '
                                   'and slimemaze/ (from emit_sandbox)')
    ap.add_argument('--preview', action='store_true',
                    help='render PNG slice previews, skip emission')
    ap.add_argument('--fresh', action='store_true',
                    help='ignore walls_cache.pkl')
    ap.add_argument('--no-stamp', action='store_true',
                    help='skip the splice stamp (raw painter output)')
    ap.add_argument('--diagnose', action='store_true',
                    help='run color/divider diagnostics, no emission')
    ap.add_argument('--install', metavar='WORLD',
                    help='after emission, run make_datapack.py '
                         '--src <outdir>/slimemaze --install WORLD')
    args = ap.parse_args()
    outdir = os.path.abspath(args.outdir)

    data = load_or_build(outdir, args.fresh)
    preview_dir = os.path.join(outdir, 'walls_preview') \
        if args.preview else None
    passes, open_model, walls = paint(data, preview_dir)
    if not args.no_stamp:
        stamp(walls, data['regions'], passes)
        purge_in_air_walls(walls, open_model)
        # second closure: the stamp can delete curtain cells and land
        # new wall-above-slit configurations; conditions are the same
        seams2 = close_ceiling_seams(walls, open_model)
        print('post-stamp seam closure: %d slits walled' % seams2)
        seal_repair(walls, open_model)
    thin_walls(walls, open_model)
    drop_hanging_remnants(walls, open_model)
    lant = paint_lanterns(walls, open_model)
    dome, vault = paint_dome(open_model, walls, lant)
    if not args.no_stamp:
        stamp_dome(dome, data['regions'], passes, walls, lant,
                   open_model, vault)
    floor = paint_floor(open_model, walls, set(data['slime']))
    outline = paint_outline(floor, walls, open_model)
    # CORNER PASS (Ryan 2026-08-14): every smooth_stone FLOOR cell
    # (walls excluded) touching >= 2 prismarine blocks HORIZONTALLY
    # (4-adjacent, same slice - not diagonal) becomes prismarine too.
    # All prismarine counts: the floor outline and the under-outline
    # wall cells (riser lips / cliff tops a floor cell can touch
    # side-on across a step). ONE simultaneous pass against the
    # pre-pass prismarine set: iterating to a fixpoint would creep a
    # second row along every inside bend (each converted corner hands
    # its neighbour a second contact)
    under = {(x, y - 1, z) for x, y, z in outline} & walls
    pris = outline | under
    extra = {p for p in floor if p not in outline
             and sum(1 for dx, dz in N4
                     if (p[0] + dx, p[1], p[2] + dz) in pris) >= 2}
    outline |= extra
    under = {(x, y - 1, z) for x, y, z in outline} & walls
    print('corner pass: %d floor cells touching >=2 prismarine '
          'horizontally -> prismarine (outline now %d)'
          % (len(extra), len(outline)))
    # SECOND OUTLINE (Ryan 2026-08-14): diamond_ore where the
    # prismarine band meets plain floor - the same recipe as line 1:
    # ring = smooth_stone floor cells 4-adjacent (same slice) to any
    # prismarine block (floor line or under-cells), then the
    # >=2-horizontal-contact corner pass (one simultaneous pass, same
    # no-cascade reasoning), then no smooth_stone beneath a diamond
    # cell either
    pris = outline | under
    ring2 = {p for p in floor if p not in outline
             and any((p[0] + dx, p[1], p[2] + dz) in pris
                     for dx, dz in N4)}
    under2 = {(x, y - 1, z) for x, y, z in ring2} & walls
    dset = ring2 | under2
    extra2 = {p for p in floor
              if p not in outline and p not in ring2
              and sum(1 for dx, dz in N4
                      if (p[0] + dx, p[1], p[2] + dz) in dset) >= 2}
    diamond = ring2 | extra2
    under2 = {(x, y - 1, z) for x, y, z in diamond} & walls
    print('second outline: %d ring + %d corner cells = %d diamond_ore'
          % (len(ring2), len(extra2), len(diamond)))
    # WALL-BOTTOM TRIM: bottom visible wall course recolored to
    # deepslate_tiles, second course to polished_deepslate. The
    # floor's under-line rules keep precedence on any shared cell
    # (stacked-corridor corner cases) - passed in as `reserved`
    trim, trim2 = paint_wall_trim(floor, walls, open_model,
                                  under | under2)
    # DOME-TOP TRIM: same two courses mirrored down from the vault
    # springline; unioned into the same material groups for emission
    # (floor lines + bottom courses keep precedence via `reserved`)
    trim3, trim4 = paint_dome_trim(walls, dome, open_model,
                                   under | under2 | trim | trim2)
    trim |= trim3
    trim2 |= trim4
    # PIER RHYTHM: dark prismarine piers + tuff flanks striped by
    # centerline arc, column-uniform (no smooth_stone ever directly
    # above/below either); the lines and courses above keep
    # precedence on shared cells
    wres = under | under2 | trim | trim2
    pier, tuff, wpal = paint_piers(
        data['samples'], walls, wres,
        [] if args.no_stamp else data['regions'])
    stone = texture_floor(floor, outline, diamond,
                          [] if args.no_stamp else data['regions'],
                          data['seed'])
    fpal = palette_floor(data['samples'], outline | diamond,
                         [] if args.no_stamp else data['regions'])
    wnether, fnether, dnether = paint_nether(
        data['slices'], walls, floor, dome,
        [] if args.no_stamp else data['regions'], wpal, fpal,
        outline | diamond)
    if args.diagnose:
        diagnose(data['slices'], open_model, walls, floor, dome,
                 wnether, fnether, dnether, outline, diamond,
                 data['samples'], fpal)
        return
    decor = paint_decor(data['blocks'], set(data['slime']),
                        walls | lant | dome | floor)
    ok = verify(passes, open_model, walls, data,
                [] if args.no_stamp else data['regions'], lant, floor,
                outline, diamond, stone, dome, vault, pier, tuff,
                wres, wpal, fpal, wnether, fnether, dnether)
    if args.preview:
        print('preview only: no emission')
        return
    if not ok:
        print('VERIFY FAILED: not emitting')
        sys.exit(2)
    emit(walls, lant, floor, outline, under, diamond, under2, stone,
         trim, trim2, dome, pier, tuff, wpal, fpal, wnether, fnether,
         dnether, decor, outdir, data['seed'])
    if args.install:
        subprocess.check_call(
            [sys.executable, os.path.join(HERE, 'make_datapack.py'),
             '--src', os.path.join(outdir, gm.NAMESPACE),
             '--out', os.path.join(HERE, 'datapack', 'slimemaze'),
             '--install', args.install])


if __name__ == '__main__':
    main()
