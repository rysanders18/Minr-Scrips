# verify_build.py - independent checks of the emitted seamless-maze files.
#
# The deep geometric invariants (separation, chords, DAG structure, no
# visible dead ends, splice window equivalence, entry connectivity) are
# checked in-simulation by generate_maze.verify() before emission. This
# script re-checks what can be read back from the emitted files:
#   - build/grounds/remove/removegrounds chains: every part <4k lines,
#     @using, no @fast, each part chains to the next; build's last part
#     chains into grounds1 and remove's into removegrounds1; the grounds
#     chains end with an @player message
#   - grounds chain wires the splice walk-script blankets (__init__ is
#     documentation-only); removegrounds removes exactly the created cells
#   - all slime setblocks unique; exactly one block at y=-64
#   - splice.msc: sequential dispatch ids, one relative tp each, deltas
#     exactly matching splices.txt, every delta strictly upward
#   - slimemaze.nms declares every emitted function
#
# Usage: python verify_build.py

import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FNDIR = os.path.join(HERE, 'slimemaze')
BOTTOM_Y = -64


def main():
    fails = []
    parts = {os.path.basename(f)[:-4]: open(f).read().splitlines()
             for f in glob.glob(os.path.join(FNDIR, '*.msc'))}
    nb = sum(1 for n in parts if re.fullmatch(r'build\d+', n))
    nr = sum(1 for n in parts if re.fullmatch(r'remove\d+', n))
    ng = sum(1 for n in parts if re.fullmatch(r'grounds\d+', n))
    nrg = sum(1 for n in parts if re.fullmatch(r'removegrounds\d+', n))
    nsg = sum(1 for n in parts if re.fullmatch(r'slimegrounds\d+', n))
    nrsg = sum(1 for n in parts
               if re.fullmatch(r'removeslimegrounds\d+', n))
    if not ng:
        fails.append('no grounds parts emitted')
    if not nrg:
        fails.append('no removegrounds parts emitted')
    if not nsg:
        fails.append('no slimegrounds parts emitted')
    if not nrsg:
        fails.append('no removeslimegrounds parts emitted')
    for chain, n, final in (('build', nb, '@var grounds1(player)'),
                            ('grounds', ng, '@var slimegrounds1(player)'),
                            ('slimegrounds', nsg, '@player'),
                            ('remove', nr, '@var removegrounds1(player)'),
                            ('removegrounds', nrg,
                             '@var removeslimegrounds1(player)'),
                            ('removeslimegrounds', nrsg, '@player')):
        for k in range(1, n + 1):
            name = '%s%d' % (chain, k)
            lines = parts.get(name)
            if lines is None:
                fails.append('missing part %s' % name)
                continue
            if len(lines) > 4000:
                fails.append('%s: %d lines (>4000)' % (name, len(lines)))
            if '@using slimemaze' not in lines:
                fails.append('%s: missing @using' % name)
            if any(l.strip() == '@fast' for l in lines):
                fails.append('%s: contains @fast' % name)
            last = [l for l in lines if l.strip()][-1]
            want = ('@var %s%d(player)' % (chain, k + 1)
                    if k < n else final)
            if not last.startswith(want):
                fails.append('%s ends with %r' % (name, last))

    blocks = []
    for k in range(1, nb + 1):
        for l in parts.get('build%d' % k, ()):
            m = re.match(r'@bypass /setblock (-?\d+) (-?\d+) (-?\d+) '
                         r'minecraft:slime_block', l)
            if m:
                blocks.append(tuple(map(int, m.groups())))
    if len(blocks) != len(set(blocks)):
        fails.append('duplicate slime coordinates in build chain')
    nbottom = sum(1 for b in blocks if b[1] == BOTTOM_Y)
    if nbottom != 1:
        fails.append('expected 1 block at y=%d, found %d'
                     % (BOTTOM_Y, nbottom))

    sp = parts.get('splice', [])
    text = '\n'.join(sp)
    if '@fast' not in [l.strip() for l in sp]:
        fails.append('splice.msc must be @fast (it fires mid-flight)')
    ids = [int(i) for i in re.findall(r'@(?:if|elseif) n == (\d+)', text)]
    tps = [tuple(map(int, t)) for t in
           re.findall(r'@bypass /minecraft:tp @s ~(-?\d+) ~(-?\d+) '
                      r'~(-?\d+)', text)]
    if ids != list(range(1, len(ids) + 1)):
        fails.append('splice ids are not sequential')
    if len(tps) != len(ids):
        fails.append('splice tp count != id count')
    if any(t[1] <= 0 for t in tps):
        fails.append('a splice does not teleport upward')
    reg = open(os.path.join(HERE, 'splices.txt')).read()
    regtps = [tuple(map(int, t)) for t in
              re.findall(r'/minecraft:tp @s ~(-?\d+) ~(-?\d+) ~(-?\d+)',
                         reg)]
    if tps != regtps:
        fails.append('splice.msc deltas do not match splices.txt')

    # splice trigger import: a 3x3 BLANKET of WALK scripts per trigger
    # block (two triggers per splice) on the carpet layer (y+1), wired
    # ONLY by the grounds chain - __init__ is documentation-only. Each
    # create passes three literal blocks (owning trigger slime block,
    # then its two onward tail blocks), all real slime blocks; cells
    # sit in the 3x3 one above their owner; each owner keeps its
    # center carpet cell; two owners per splice id, ids 1..N;
    # removegrounds removes exactly the created cells
    init = '\n'.join(parts.get('__init__', []))
    if '@command script' in init:
        fails.append('__init__ still contains script commands (must be '
                     'documentation-only)')
    bset = set(blocks)
    blk_pat = r'Block\((-?\d+), (-?\d+), (-?\d+), "[^"]+"\)'
    gr_text = '\n'.join(l for k in range(1, ng + 1)
                        for l in parts.get('grounds%d' % k, ()))
    grounds = re.findall(r'@command script create walk (-?\d+) (-?\d+) '
                         r'(-?\d+) \S+ @var \S+::splice\(player, (\d+), '
                         + blk_pat + r', ' + blk_pat + r', ' + blk_pat
                         + r'\)', gr_text)
    ngr_creates = sum(1 for l in gr_text.splitlines()
                      if '@command script create' in l)
    if len(grounds) != ngr_creates:
        fails.append('%d grounds creates do not parse as 3-literal-'
                     'block splice calls' % (ngr_creates - len(grounds)))
    spc = set()
    gset = set()             # owner trigger blocks (slime level)
    own_of_id = {}
    sp_dup = sp_on = sp_bad = sp_far = 0
    for g in grounds:
        v = tuple(map(int, g))
        cell, gn, own, nx1, nx2 = v[0:3], v[3], v[4:7], v[7:10], v[10:13]
        if cell in spc:
            sp_dup += 1
        spc.add(cell)
        gset.add(own)
        own_of_id.setdefault(gn, set()).add(own)
        if cell in bset:
            sp_on += 1
        if any(p not in bset for p in (own, nx1, nx2)):
            sp_bad += 1
        if (cell[1] != own[1] + 1 or abs(cell[0] - own[0]) > 1
                or abs(cell[2] - own[2]) > 1):
            sp_far += 1
    if sp_dup:
        fails.append('%d duplicate splice trigger cells' % sp_dup)
    if sp_on:
        fails.append('%d splice cells sit ON a slime block' % sp_on)
    if sp_bad:
        fails.append('%d splice creates pass a literal that is not a '
                     'slime block' % sp_bad)
    if sp_far:
        fails.append('%d splice cells are not in the 3x3 one above '
                     'their owner' % sp_far)
    if sorted(own_of_id) != list(range(1, len(ids) + 1)):
        fails.append('grounds splice ids are not exactly 1..%d'
                     % len(ids))
    if any(len(o) != 2 for o in own_of_id.values()):
        fails.append('a splice id does not have exactly 2 trigger '
                     'blocks')
    sp_missing = sum(1 for x, y, z in gset if (x, y + 1, z) not in spc)
    if sp_missing:
        fails.append('%d splice triggers lack their own carpet-cell '
                     'script' % sp_missing)
    rg_text = '\n'.join(l for k in range(1, nrg + 1)
                        for l in parts.get('removegrounds%d' % k, ()))
    rgs = re.findall(r'@command script (create|remove) walk (-?\d+) '
                     r'(-?\d+) (-?\d+)', rg_text)
    if any(kind != 'remove' for kind, _, _, _ in rgs):
        fails.append('removegrounds contains a script create')
    rgset = {(int(x), int(y), int(z)) for _, x, y, z in rgs}
    if rgset != spc:
        fails.append('removegrounds cells (%d) do not match grounds '
                     'creates (%d)' % (len(rgset), len(spc)))

    # slimeblock bounce triggers: a 3x3 BLANKET of WALK scripts (fire
    # on pass-through - the carpet/air cells are never stood on) on
    # the carpet layer (y+1) around every non-splice-trigger slime
    # block, each create passing three literal blocks (the owning
    # slime block, then next1/next2 along the onward path). Checks:
    # every create parses, all three literals are real slime blocks,
    # each cell sits one level above and within Chebyshev 1 of its
    # owner, no cell lands on a slime block or inside the 3x3 above a
    # splice trigger, cells are unique, every non-trigger block's own
    # carpet cell (x, y+1, z) exists, and the undo chain removes
    # exactly the created cells
    sg_text = '\n'.join(l for k in range(1, nsg + 1)
                        for l in parts.get('slimegrounds%d' % k, ()))
    sgl = re.findall(r'@command script create walk (-?\d+) (-?\d+) '
                     r'(-?\d+) \S+ @var \S+::slimeblock\(player, '
                     + blk_pat + r', ' + blk_pat + r', ' + blk_pat
                     + r'\)', sg_text)
    ncreates = sum(1 for l in sg_text.splitlines()
                   if '@command script create' in l)
    if len(sgl) != ncreates:
        fails.append('%d slimegrounds creates do not parse as '
                     '3-literal-block slimeblock calls'
                     % (ncreates - len(sgl)))
    trig3x3 = {(gx + dx, gy + 1, gz + dz)
               for gx, gy, gz in gset
               for dx in (-1, 0, 1) for dz in (-1, 0, 1)}
    sgc = set()
    dup = on_slime = in_trig = bad_lit = far = 0
    for g in sgl:
        v = tuple(map(int, g))
        cell, own, nx1, nx2 = v[0:3], v[3:6], v[6:9], v[9:12]
        if cell in sgc:
            dup += 1
        sgc.add(cell)
        if cell in bset:
            on_slime += 1
        if cell in trig3x3:
            in_trig += 1
        if any(p not in bset for p in (own, nx1, nx2)):
            bad_lit += 1
        if (cell[1] != own[1] + 1 or abs(cell[0] - own[0]) > 1
                or abs(cell[2] - own[2]) > 1):
            far += 1
    if dup:
        fails.append('%d duplicate slimeblock trigger cells' % dup)
    if on_slime:
        fails.append('%d trigger cells sit ON a slime block' % on_slime)
    if in_trig:
        fails.append('%d trigger cells shadow a splice trigger 3x3'
                     % in_trig)
    if bad_lit:
        fails.append('%d creates pass a literal that is not a slime '
                     'block' % bad_lit)
    if far:
        fails.append('%d cells are not in the 3x3 one above their '
                     'owner' % far)
    missing_center = sum(1 for x, y, z in bset - gset
                         if (x, y + 1, z) not in sgc)
    if missing_center:
        fails.append('%d slime blocks lack their own carpet-cell '
                     'trigger' % missing_center)
    rsg_text = '\n'.join(l for k in range(1, nrsg + 1)
                         for l in parts.get('removeslimegrounds%d' % k,
                                            ()))
    rsgs = re.findall(r'@command script (create|remove) walk (-?\d+) '
                      r'(-?\d+) (-?\d+)', rsg_text)
    if any(kind != 'remove' for kind, _, _, _ in rsgs):
        fails.append('removeslimegrounds contains a script create')
    rsgset = {(int(x), int(y), int(z)) for _, x, y, z in rsgs}
    if rsgset != sgc:
        fails.append('removeslimegrounds cells (%d) do not match '
                     'slimegrounds creates (%d)'
                     % (len(rsgset), len(sgc)))
    if sgc & spc:
        fails.append('%d cells carry BOTH a splice and a slimeblock '
                     'walk script' % len(sgc & spc))

    # fall.msc: one absolute tp per start, matching starts.txt spawns
    fall = '\n'.join(parts.get('fall', []))
    ftps = {tuple(map(int, t)) for t in
            re.findall(r'@bypass /minecraft:tp \S+ (-?\d+) (-?\d+) '
                       r'(-?\d+)', fall)}
    starts = open(os.path.join(HERE, 'starts.txt')).read()
    stps = {tuple(map(int, t)) for t in
            re.findall(r'spawn at (-?\d+) (-?\d+) (-?\d+)', starts)}
    if not stps:
        fails.append('starts.txt has no spawn points')
    if ftps != stps:
        fails.append('fall.msc spawns (%d) do not match starts.txt (%d)'
                     % (len(ftps), len(stps)))

    nms = open(os.path.join(HERE, 'slimemaze.nms')).read()
    for k in range(1, nb + 1):
        if 'build%d(Player player)' % k not in nms:
            fails.append('nms missing build%d' % k)
    for k in range(1, nr + 1):
        if 'remove%d(Player player)' % k not in nms:
            fails.append('nms missing remove%d' % k)
    for k in range(1, ng + 1):
        # leading space so 'removegrounds1(...)' can't satisfy this check
        if ' grounds%d(Player player)' % k not in nms:
            fails.append('nms missing grounds%d' % k)
    for k in range(1, nrg + 1):
        if 'removegrounds%d(Player player)' % k not in nms:
            fails.append('nms missing removegrounds%d' % k)
    if ('splice(Player player, Int n, Block trigger, Block next1, '
            'Block next2)') not in nms:
        fails.append('nms missing splice')
    if ('slimeblock(Player player, Block slimeblock, Block next1, '
            'Block next2)') not in nms:
        fails.append('nms missing slimeblock')
    if 'fall(Player player)' not in nms:
        fails.append('nms missing fall')
    if '@endnamespace' not in nms:
        fails.append('nms missing @endnamespace')
    # every function file must be declared (catches stale leftovers from
    # runs whose part counts shrank)
    for name in parts:
        if name != '__init__' and not re.search(
                r'(?m)^\s+%s\(Player' % re.escape(name), nms):
            fails.append('stale or undeclared function file: %s.msc'
                         % name)

    print('build parts: %d  grounds parts: %d  remove parts: %d  '
          'removegrounds parts: %d  slimegrounds parts: %d/%d  '
          'blocks: %d  splices: %d  splice triggers: %d  '
          'slimeblock triggers: %d'
          % (nb, ng, nr, nrg, nsg, nrsg, len(blocks), len(ids),
             len(grounds), len(sgc)))
    for f in fails:
        print('FAIL:', f)
    print('RESULT:', 'PASS' if not fails else 'FAIL')
    sys.exit(0 if not fails else 1)


if __name__ == '__main__':
    main()
