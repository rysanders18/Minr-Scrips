"""Convert the emitted slimemaze .msc chains into a vanilla datapack for
fast singleplayer testing - no Minr server, no MSC imports, no chunk-walk
teleports.

Reads every @bypass /setblock and @bypass /fill line out of the already
emitted script chains in slimemaze/ and re-emits them as mcfunctions:

    /function slimemaze:build   - forceloads the maze area, then places
                                  every block (build+walls+dome+floor+decor)
    /function slimemaze:clear   - same but the remove* chains (all air)
    /function slimemaze:wipe    - air-fills the ENTIRE maze bounding box.
                                  Use instead of clear when the standing
                                  build came from an OLDER datapack: clear
                                  only removes cells the current build
                                  owns, so blocks that only the old build
                                  placed linger as strays. wipe + build =
                                  guaranteed-clean rebuild.

Usage:
    python make_datapack.py                 # writes datapack/slimemaze/
    python make_datapack.py --install MyWorld
        also copies it into %APPDATA%/.minecraft/saves/MyWorld/datapacks/
    python make_datapack.py --no-strict
        strips the trailing 'strict' flag (needed below MC 1.21.5)

In the singleplayer world (once per world):
    /gamerule maxCommandChainLength 10000000
Then after every regeneration: copy the datapack in (or rerun with
--install), /reload, /function slimemaze:clear, /function slimemaze:build.

The ground-trigger scripts (splice teleports, slimeblock bounce hooks) are
Minr server features and are NOT reproduced here - this tests geometry and
bounce lines only.
"""
import argparse
import os
import re
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'slimemaze')
OUT = os.path.join(HERE, 'datapack', 'slimemaze')

# chain-name prefixes making up the build and the undo (prefix + digits)
BUILD_PREFIXES = ('build', 'walls', 'dome', 'floor', 'decor')
CLEAR_PREFIXES = ('remove', 'removewalls', 'removedome', 'removefloor',
                  'removedecor')

CMD_RE = re.compile(r'^@bypass /(setblock|fill) (.+)$')
INT_RE = re.compile(r'-?\d+')
PART_LINES = 50000  # commands per mcfunction file (readability only)


def collect(prefixes):
    """All setblock/fill commands from <prefix><N>.msc, plus the chunk
    bbox they touch. Prefixes are matched longest-first so 'remove' does
    not swallow 'removewalls'."""
    pat = re.compile(r'^(%s)(\d+)\.msc$'
                     % '|'.join(sorted(prefixes, key=len, reverse=True)))
    files = []
    for fn in os.listdir(SRC):
        m = pat.match(fn)
        if m:
            files.append((BUILD_PREFIXES.index(m.group(1))
                          if m.group(1) in BUILD_PREFIXES
                          else CLEAR_PREFIXES.index(m.group(1)),
                          int(m.group(2)), fn))
    cmds = []
    bbox = [10**9, 10**9, -10**9, -10**9]  # cx1 cz1 cx2 cz2 (chunk coords)
    for _, _, fn in sorted(files):
        with open(os.path.join(SRC, fn)) as fh:
            for line in fh:
                m = CMD_RE.match(line.strip())
                if not m:
                    continue
                cmds.append('%s %s' % (m.group(1), m.group(2)))
                nums = [int(v) for v in INT_RE.findall(m.group(2))]
                pts = ([nums[0:3], nums[3:6]] if m.group(1) == 'fill'
                       else [nums[0:3]])
                for x, _, z in pts:
                    bbox[0] = min(bbox[0], x // 16)
                    bbox[1] = min(bbox[1], z // 16)
                    bbox[2] = max(bbox[2], x // 16)
                    bbox[3] = max(bbox[3], z // 16)
    return cmds, bbox


def emit(name, cmds, bbox, fndir, label):
    """<name>.mcfunction: forceload the area, schedule <name>_go 5t (so
    the chunks are live), which runs the command parts then drops the
    forceloads again."""
    cx1, cz1, cx2, cz2 = bbox
    loads = ['forceload add %d %d %d %d'
             % (cx1 * 16, cz * 16, cx2 * 16 + 15, cz * 16 + 15)
             for cz in range(cz1, cz2 + 1)]  # one chunk-row per command
    parts = [cmds[i:i + PART_LINES] for i in range(0, len(cmds), PART_LINES)]
    for k, body in enumerate(parts, 1):
        write(os.path.join(fndir, '%s_%d.mcfunction' % (name, k)), body)
    write(os.path.join(fndir, '%s.mcfunction' % name),
          ['tellraw @a "slimemaze: forceloading %d chunk rows, %s %d '
           'blocks in 5s (chunk-load grace)..."'
           % (len(loads), label, len(cmds))] +
          loads + ['schedule function slimemaze:%s_go 100t' % name])
    write(os.path.join(fndir, '%s_go.mcfunction' % name),
          ['function slimemaze:%s_%d' % (name, k + 1)
           for k in range(len(parts))] +
          ['forceload remove all',
           'tellraw @a "slimemaze: %s done (%d commands)."'
           % (label, len(cmds))])


def write(path, lines):
    with open(path, 'w', newline='\n') as fh:
        fh.write('\n'.join(lines) + '\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--install', metavar='WORLD',
                    help='also copy into .minecraft/saves/WORLD/datapacks')
    ap.add_argument('--no-strict', action='store_true',
                    help="strip the 'strict' flag (for MC < 1.21.5)")
    args = ap.parse_args()

    fndir = os.path.join(OUT, 'data', 'slimemaze', 'function')
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(fndir)
    write(os.path.join(OUT, 'pack.mcmeta'),
          ['{"pack": {"pack_format": 71, "supported_formats": [48, 999],',
           ' "description": "slimemaze singleplayer test build"}}'])

    ylims = [10**9, -10**9]
    for name, prefixes, label in (('build', BUILD_PREFIXES, 'placing'),
                                  ('clear', CLEAR_PREFIXES, 'clearing')):
        cmds, bbox = collect(prefixes)
        for c in cmds:
            nums = [int(v) for v in INT_RE.findall(c)]
            ys = [nums[1]] + ([nums[4]] if len(nums) >= 6 else [])
            ylims[0] = min(ylims[0], *ys)
            ylims[1] = max(ylims[1], *ys)
        if args.no_strict:
            cmds = [re.sub(r' strict$', '', c) for c in cmds]
        emit(name, cmds, bbox, fndir, label)
        print('%s: %d commands, chunks x %d..%d z %d..%d'
              % (name, len(cmds), bbox[0], bbox[2], bbox[1], bbox[3]))

    # wipe: air-fill the whole bounding box in 32k-block fill slabs,
    # so a rebuild is clean regardless of what any older datapack
    # generation left behind. Clamped to the forceloaded chunk range -
    # fills outside it would silently fail
    x1, z1 = bbox[0] * 16, bbox[1] * 16
    x2, z2 = bbox[2] * 16 + 15, bbox[3] * 16 + 15
    y1, y2 = ylims[0] - 4, ylims[1] + 6
    wx = x2 - x1 + 1
    rows = max(1, 32768 // wx)          # z-rows per 1-high fill slab
    wipe = []
    for y in range(y1, y2 + 1):
        z = z1
        while z <= z2:
            ze = min(z + rows - 1, z2)
            wipe.append('fill %d %d %d %d %d %d minecraft:air'
                        % (x1, y, z, x2, y, ze))
            z = ze + 1
    emit('wipe', wipe, bbox, fndir, 'wiping')
    print('wipe: %d fills, x %d..%d y %d..%d z %d..%d'
          % (len(wipe), x1, x2, y1, y2, z1, z2))

    print('datapack written to', OUT)
    if args.install:
        dst = os.path.join(os.environ['APPDATA'], '.minecraft', 'saves',
                           args.install, 'datapacks', 'slimemaze')
        if not os.path.isdir(os.path.dirname(dst)):
            raise SystemExit('no datapacks dir: %s' % os.path.dirname(dst))
        shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(OUT, dst)
        print('installed to', dst)


if __name__ == '__main__':
    main()
