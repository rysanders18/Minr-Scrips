# make_fallgrounds.py - emit the fallgrounds1..N chain: a walk-script
# import for every EXPOSED floor block in slimemaze1.schem, so landing
# on the maze floor anywhere triggers slimemaze::fall(player).
#
# Coordinate source: slimemaze1.schem (sponge v2, world-anchored -
# its Offset IntArray is the world min corner, so world = offset +
# local index; no shift needed).
#
# A block is a walk target iff (rules agreed with Ryan 2026-08-31):
#   1. its type is a FLOOR material: the andesite/stone noise mix, the
#      two outline-ring bases (prismarine_bricks / diamond_ore) plus
#      every per-palette remap of them (16 themes x 2), and the
#      netherite divider slices (they override floor cells, players
#      stand on them). smooth_stone is EXCLUDED - it is also the main
#      wall material and would tag wall tops.
#   2. the block directly above has no collision. Solid = full blocks,
#      slabs, trapdoors, glass, melon, everything else; NON-solid =
#      air, light, signs, buttons, carpets, moss_carpet, sculk_vein.
#      (A solid block above means nobody can ever stand there.)
#   3. of the survivors: any block with AIR in its 8 same-Y horizontal
#      neighbors (plate edges / hole rims; out-of-schem = air) is
#      always included; interior blocks only on the x%2==z%2
#      checkerboard (world coords, both positive here).
#
# Output: slimemaze/fallgrounds<N>.msc - house slimegrounds style:
# remove-then-create pair per block, @delay 1 every BATCH command
# lines (default 50 = 25 blocks/tick; lower BATCH if it lags), files
# capped under the ~4k-line hastebin import limit, each chaining to
# the next with @var. Also rewrites the fallgrounds declarations in
# slimemaze.nms between the AUTO markers (appends them before
# @endnamespace on first run).
#
# Safety: any candidate coordinate that collides with a wired trigger
# in splices.txt or a slimegrounds walk trigger is dropped with a
# warning - our `script remove walk` would silently kill the maze
# wiring there.

import nbtlib, os, re, sys, glob

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEM = os.path.join(HERE, 'slimemaze1.schem')
OUTDIR = os.path.join(HERE, 'slimemaze')
NMS = os.path.join(HERE, 'slimemaze.nms')
WORLD = 'Epsilon'
BATCH = 50          # @command lines per tick (2 lines per block)
MAX_LINES = 3900    # per-file cap (hastebin import ~4k)

FLOOR = {
    'minecraft:andesite', 'minecraft:stone',
    # outline ring #1: prismarine_bricks + 16 palette remaps
    'minecraft:prismarine_bricks', 'minecraft:gold_block',
    'minecraft:red_nether_bricks', 'minecraft:amethyst_block',
    'minecraft:emerald_block', 'minecraft:lapis_block',
    'minecraft:obsidian', 'minecraft:copper_block',
    'minecraft:diamond_block', 'minecraft:quartz_block',
    'minecraft:cherry_wood', 'minecraft:sculk',
    'minecraft:iron_block', 'minecraft:smooth_red_sandstone',
    'minecraft:coal_block', 'minecraft:green_concrete',
    'minecraft:end_stone_bricks',
    # outline ring #2: diamond_ore + 16 palette remaps
    'minecraft:diamond_ore', 'minecraft:gold_ore',
    'minecraft:redstone_ore', 'minecraft:purpur_block',
    'minecraft:emerald_ore', 'minecraft:lapis_ore',
    'minecraft:ancient_debris', 'minecraft:copper_ore',
    'minecraft:deepslate_diamond_ore', 'minecraft:nether_quartz_ore',
    'minecraft:pink_glazed_terracotta', 'minecraft:sculk_catalyst',
    'minecraft:iron_ore', 'minecraft:orange_glazed_terracotta',
    'minecraft:deepslate_coal_ore', 'minecraft:melon',
    'minecraft:pearlescent_froglight',
    # theme-divider slices override floor cells
    'minecraft:netherite_block',
}

# blocks a player can stand INSIDE of (no collision at y+1)
NO_COLLISION = {
    'minecraft:air', 'minecraft:light', 'minecraft:sculk_vein',
    'minecraft:moss_carpet',
}
def open_above(name):
    return (name in NO_COLLISION or name.endswith('_carpet')
            or name.endswith('_sign') or name.endswith('_button'))


def load_schem():
    f = nbtlib.load(SCHEM)
    W, H, L = int(f['Width']), int(f['Height']), int(f['Length'])
    ox, oy, oz = (int(v) for v in f['Offset'])
    pal = {int(v): k.split('[')[0] for k, v in f['Palette'].items()}
    data = bytes(b & 0xFF for b in f['BlockData'])
    ids, i, n = [], 0, len(data)
    while i < n:                       # sponge varint stream
        v, shift = 0, 0
        while True:
            b = data[i]; i += 1
            v |= (b & 0x7F) << shift
            if not (b & 0x80):
                break
            shift += 7
        ids.append(v)
    assert len(ids) == W * H * L
    return ids, pal, W, H, L, (ox, oy, oz)


def wired_triggers():
    """Coordinates already carrying maze walk scripts we must not
    remove: splice triggers (splices.txt) and every slimegrounds
    walk create."""
    coords = set()
    sp = os.path.join(HERE, 'splices.txt')
    if os.path.exists(sp):
        for m in re.finditer(r'Block\((-?\d+),\s*(-?\d+),\s*(-?\d+)',
                             open(sp).read()):
            coords.add(tuple(int(g) for g in m.groups()))
    pat = re.compile(r'@command script create walk '
                     r'(-?\d+) (-?\d+) (-?\d+)')
    for path in glob.glob(os.path.join(OUTDIR, 'slimegrounds*.msc')):
        for m in pat.finditer(open(path).read()):
            coords.add(tuple(int(g) for g in m.group(1, 2, 3)))
    return coords


def main():
    ids, pal, W, H, L, (ox, oy, oz) = load_schem()
    AIR = {i for i, nm in pal.items() if nm == 'minecraft:air'}
    floor_ids = {i for i, nm in pal.items() if nm in FLOOR}
    open_ids = {i for i, nm in pal.items() if open_above(nm)}
    plane = W * L

    def pid(lx, ly, lz):
        return ids[ly * plane + lz * W + lx]

    targets, n_edge, n_checker = [], 0, 0
    for ly in range(H):
        base = ly * plane
        for lz in range(L):
            row = base + lz * W
            for lx in range(W):
                if ids[row + lx] not in floor_ids:
                    continue
                # rule 1: collision above -> never standable
                if ly + 1 < H and pid(lx, ly + 1, lz) not in open_ids:
                    continue
                x, y, z = ox + lx, oy + ly, oz + lz
                edge = False
                for dx in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        if dx == 0 and dz == 0:
                            continue
                        nx, nz = lx + dx, lz + dz
                        if (not (0 <= nx < W and 0 <= nz < L)
                                or pid(nx, ly, nz) in AIR):
                            edge = True
                if edge:
                    n_edge += 1
                elif x % 2 == z % 2:
                    n_checker += 1
                else:
                    continue
                targets.append((y, z, x))

    wired = wired_triggers()
    kept = [(x, y, z) for (y, z, x) in sorted(targets)
            if (x, y, z) not in wired]
    dropped = len(targets) - len(kept)
    if dropped:
        print('WARNING: dropped %d floor blocks that collide with '
              'existing splice/slimegrounds triggers' % dropped)
    print('targets: %d (%d edge + %d checkerboard), emitting %d'
          % (len(targets), n_edge, n_checker, len(kept)))

    for old in glob.glob(os.path.join(OUTDIR, 'fallgrounds*.msc')):
        os.remove(old)

    # BATCH must be even: a @delay may never split a remove/create
    # pair (user rule 2026-08-25, same as slimegrounds)
    assert BATCH % 2 == 0

    # blocks per file: pairs + one @delay per BATCH lines + ~12
    # header/chain lines must stay under MAX_LINES
    per_file = ((MAX_LINES - 20) * BATCH) // (2 * BATCH + 1) // 2 * 2
    chunks = [kept[i:i + per_file]
              for i in range(0, len(kept), per_file)] or [[]]
    nfiles = len(chunks)
    for fi, chunk in enumerate(chunks, 1):
        lines = [
            '# fallgrounds%d(Player player)' % fi,
            '# HAND-TUNED FILE (owned by make_fallgrounds.py, not',
            '# gen_pinned - marker only shields it from the regen',
            '# cleanup sweep; re-run make_fallgrounds.py to regen,',
            '# and re-run it after any gen_pinned .nms regen to',
            '# restore the fallgrounds declarations)',
            '# part %d of %d - chains to the next part when done'
            % (fi, nfiles),
            '# walk-script blanket over every exposed floor block of',
            '# slimemaze1.schem: landing on the maze floor calls',
            '# slimemaze::fall(player). Emitted by make_fallgrounds.py',
            '# (floor materials + no-collision-above + edge-always /',
            '# interior-checkerboard rules). %d commands per tick.'
            % BATCH,
            '', '@using slimemaze', '@fast', '',
        ]
        cmds = 0
        for (x, y, z) in chunk:
            for verb in ('remove', 'create'):
                tail = (' @var slimemaze::fall(player)'
                        if verb == 'create' else '')
                lines.append('@command script %s walk %d %d %d %s%s'
                             % (verb, x, y, z, WORLD, tail))
                cmds += 1
                if cmds % BATCH == 0:
                    lines.append('@delay 1')
        lines.append('')
        if fi < nfiles:
            lines.append('@var fallgrounds%d(player)' % (fi + 1))
        else:
            lines.append('@player &aFall blanket wired: %d floor '
                         'blocks across %d parts.'
                         % (len(kept), nfiles))
        path = os.path.join(OUTDIR, 'fallgrounds%d.msc' % fi)
        open(path, 'w').write('\n'.join(lines) + '\n')
        print('wrote %s (%d lines, %d blocks)'
              % (os.path.basename(path), len(lines), len(chunk)))

    # ---- declarations in slimemaze.nms (between AUTO markers) ----
    decls = ('# AUTO fallgrounds (make_fallgrounds.py)\n'
             + ''.join('    fallgrounds%d(Player player)\n' % i
                       for i in range(1, nfiles + 1))
             + '# END AUTO fallgrounds\n')
    nms = open(NMS).read()
    if '# AUTO fallgrounds' in nms:
        nms = re.sub(r'# AUTO fallgrounds.*?# END AUTO fallgrounds\n',
                     decls, nms, flags=re.S)
    else:
        nms = nms.replace('@endnamespace', decls + '@endnamespace')
    open(NMS, 'w').write(nms)
    print('slimemaze.nms: declared fallgrounds1..%d' % nfiles)


if __name__ == '__main__':
    main()
