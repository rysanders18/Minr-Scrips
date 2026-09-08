# make_buildall.py (Ryan 2026-08-17): repackage the ENTIRE build -
# every setblock/fill from build + walls + lanterns + dome + floor +
# decor - into ONE buildALL1..N chain bucketed by 4x4-CHUNK (64x64)
# regions: per region teleport the player to its center, @delay 500
# ticks, place every block in it, then hop to the next region. Each
# part opens with @fast (burst-then-wait pattern). The last part
# tail-calls grounds1 so trigger wiring still happens, mirroring
# build2. Rerun after any re-emission: python make_buildall.py
import os
import re
import sys

REGION = 64          # 4x4 chunks
WAIT = 500           # ticks between regions
PART_LINES = 2600    # hastebin caps: ~4k lines AND ~300KB
PART_BYTES = 250 * 1024
FAMILIES = ('build', 'walls', 'lanterns', 'dome', 'floor', 'decor')

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'slimemaze')
CMD = re.compile(r'^@bypass /(?:minecraft:)?(setblock|fill) '
                 r'(-?\d+) (-?\d+) (-?\d+)')

regions = {}   # (rx, rz) -> [command lines in family order]
tops = {}      # (rx, rz) -> max y seen
total = 0
pat = re.compile(r'^(%s)(\d+)\.msc$' % '|'.join(FAMILIES))
files = []
for f in os.listdir(SRC):
    m = pat.match(f)
    if m:
        files.append((FAMILIES.index(m.group(1)), int(m.group(2)), f))
for _, _, f in sorted(files):
    for line in open(os.path.join(SRC, f), encoding='utf-8'):
        line = line.rstrip('\n')
        m = CMD.match(line)
        if not m:
            continue
        x, y, z = int(m.group(2)), int(m.group(3)), int(m.group(4))
        key = (x // REGION, z // REGION)
        regions.setdefault(key, []).append(line)
        tops[key] = max(tops.get(key, y), y)
        total += 1

parts, cur, n, nb = [], [], 0, 0
for key in sorted(regions):
    cmds = regions[key]
    cx = key[0] * REGION + REGION // 2
    cz = key[1] * REGION + REGION // 2
    tp = '@bypass tp %d %d %d' % (cx, tops[key] + 4, cz)
    # entering a NEW region: full WAIT. A part boundary inside a
    # region re-anchors with a 10-tick delay only (chunks loaded)
    hdr = [tp, '@delay %d' % WAIT]
    cont = [tp, '@delay 10']
    pending = hdr
    for line in cmds:
        need = len(line) + 1 + (sum(len(h) + 1 for h in pending)
                                if pending else 0)
        if cur and (n + 2 > PART_LINES or nb + need > PART_BYTES):
            parts.append(cur)
            cur, n, nb = [], 0, 0
            if pending is None:
                pending = cont
            need = len(line) + 1 + sum(len(h) + 1 for h in pending)
        if pending is not None:
            cur.extend(pending)
            n += len(pending)
            pending = None
        cur.append(line)
        n += 1
        nb += need
if cur:
    parts.append(cur)

# clear stale parts
for old in os.listdir(SRC):
    if re.fullmatch(r'buildALL\d+\.msc', old):
        os.remove(os.path.join(SRC, old))
names = []
for k, body in enumerate(parts, 1):
    name = 'buildALL%d' % k
    head = ['# %s(Player player)' % name,
            '# whole-maze build in %dx%d regions: tp, wait %d ticks, '
            'place, hop (part %d of %d)'
            % (REGION, REGION, WAIT, k, len(parts)),
            '', '@using slimemaze', '@fast', '']
    if k < len(parts):
        tail = ['', '@var buildALL%d(player)' % (k + 1)]
    else:
        tail = ['', '@var grounds1(player)']
    with open(os.path.join(SRC, '%s.msc' % name), 'w',
              newline='\n', encoding='utf-8') as fh:
        fh.write('\n'.join(head + body + tail) + '\n')
    names.append(name)

# declare in the nms (replace any previous buildALL block)
nms = os.path.join(HERE, 'slimemaze.nms')
lines = [l for l in open(nms, encoding='utf-8').read().splitlines()
         if not re.fullmatch(r'\s*buildALL\d+\(Player player\)\s*', l)]
at = lines.index('@endnamespace')
lines[at:at] = ['    %s(Player player)' % nm for nm in names]

# the server set is the ONLY generation target (user 2026-08-17):
# the segmented decoration chains exist just long enough to be
# packed into buildALL - consume and DELETE them, along with every
# remove* and grounds file any tool may have left behind. The kept
# set is exactly: build, buildALL, slimegrounds, and the core
# singles (__init__, splice, fall, fallFx1/2, slimeblock, spliceFx,
# scaryTitle). grounds declarations STAY in the nms (build2 and
# buildALL315 tail-call grounds1, whose implementation lives on the
# server); the file-level wiring is stable for the frozen geometry
DROP_FILE = re.compile(
    r'^(walls|lanterns|dome|floor|decor|remove[a-zA-Z]*|grounds)'
    r'\d+\.msc$')
dropped = 0
for old in os.listdir(SRC):
    if DROP_FILE.match(old):
        os.remove(os.path.join(SRC, old))
        dropped += 1
DROP_DECL = re.compile(
    r'\s*(walls|lanterns|dome|floor|decor|remove[a-zA-Z]*)\d+'
    r'\(Player player\)\s*')
lines = [l for l in lines if not DROP_DECL.fullmatch(l)]

with open(nms, 'w', newline='\n', encoding='utf-8') as fh:
    fh.write('\n'.join(lines) + '\n')

print('buildALL: %d commands, %d regions, %d parts '
      '(max %d lines); ~%d min of region waits'
      % (total, len(regions), len(parts), PART_LINES,
         len(regions) * WAIT // 20 // 60))
print('server set: %d consumed/stale files deleted from slimemaze/'
      % dropped)
print('run: /function execute slimemaze::buildALL1(Player("You"))')
