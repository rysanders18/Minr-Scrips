# weight_windows.py (Ryan 2026-08-25): classify the 161 fall.msc splice
# windows by "splice inevitability" and emit the integer weight table
# (wwt) that fall.msc's weighted respawn picks use.
#
# Classes (walk the corridor down from each window landing):
#   FREE   - a real fork comes before any splice trigger        f = 1
#   FORCED - a splice trigger comes before any fork: the player
#            WILL be teleported higher no matter what           f = 1/3
#   SOFT   - exactly one fork first, but BOTH arms then hit a
#            trigger with no further fork (the choice is
#            illusory - every path splices)                     f = 1/2
# Chains multiply (user rule 2026-08-25): a FORCED window's factor is
# 1/3 x f(destination window); a SOFT window's is 1/2 x min over its
# two arms' destination factors (worse arm). Recursion is memoized;
# splice tps always move up the maze so chains terminate.
#
# Integer weights: exact Fractions scaled by the LCM of denominators,
# so FREE windows share the max weight and every ratio is exact.
#
# Rerun after any fall.msc re-emission (needs the emitted wxs/wys/wzs
# arrays + sim_debug.pkl) and paste the printed wwt line into fall.msc:
#   python weight_windows.py
import pickle
import re
from fractions import Fraction
from math import lcm

HERE = __file__.rsplit('\\', 1)[0] if '\\' in __file__ else '.'

with open(HERE + '\\sim_debug.pkl', 'rb') as f:
    d = pickle.load(f)
blocks, kids, splices = d['blocks'], d['kids'], d['splices']

trig = {}
for s in splices:
    for c in s['copy']:
        trig[c] = s

pos2idx = {(b['x'], b['y'], b['z']): i
           for i, b in enumerate(blocks) if b is not None}

src = open(HERE + '\\slimemaze\\fall.msc', encoding='utf-8').read()


def arr(name):
    m = re.search(r'@define Int\[\] %s = Int\[([^\]]*)\]' % name, src)
    return [int(x) for x in m.group(1).split(',')]


wxs, wys, wzs = arr('wxs'), arr('wys'), arr('wzs')
N = len(wxs)
w0_to_widx = {(wxs[i], wys[i], wzs[i]): i for i in range(N)}


def walk_to_event(start):
    # follow the single-kid corridor: first splice trigger or first fork
    cur = start
    while True:
        if cur in trig:
            return ('trig', trig[cur])
        ks = [k for k in kids.get(cur, []) if blocks[k] is not None]
        if len(ks) >= 2:
            return ('fork', cur)
        if not ks:
            return ('end', None)
        cur = ks[0]


def dest_widx(s):
    b = blocks[s['w0']]
    return w0_to_widx.get((b['x'], b['y'], b['z']))


cls, dests = {}, {}
for i in range(N):
    kind, obj = walk_to_event(pos2idx[(wxs[i], wys[i], wzs[i])])
    if kind == 'trig':
        cls[i], dests[i] = 'FORCED', [dest_widx(obj)]
    elif kind == 'fork':
        arms = [k for k in kids.get(obj, []) if blocks[k] is not None]
        ev = [walk_to_event(a) for a in arms]
        if ev and all(k == 'trig' for k, _ in ev):
            cls[i], dests[i] = 'SOFT', [dest_widx(o) for _, o in ev]
        else:
            cls[i] = 'FREE'
    else:
        cls[i] = 'FREE'

memo = {}


def f(i, seen=frozenset()):
    if i is None or i in seen:      # dest outside table / cycle guard
        return Fraction(1)
    if i in memo:
        return memo[i]
    if cls[i] == 'FREE':
        r = Fraction(1)
    elif cls[i] == 'FORCED':
        r = Fraction(1, 3) * f(dests[i][0], seen | {i})
    else:                           # SOFT: worse arm
        r = Fraction(1, 2) * min(f(j, seen | {i}) for j in dests[i])
    memo[i] = r
    return r


fs = [f(i) for i in range(N)]
scale = lcm(*[fr.denominator for fr in fs])
wts = [int(fr * scale) for fr in fs]

from collections import Counter
print('classes:', dict(Counter(cls.values())))
print('scale (FREE weight):', scale)
print('weight histogram:', dict(sorted(Counter(wts).items(), reverse=True)))
for i in sorted(range(N), key=lambda i: fs[i]):
    if cls[i] != 'FREE':
        print('  w%-3d (%d,%d,%d)  %-6s f=%-6s -> %d'
              % (i, wxs[i], wys[i], wzs[i], cls[i], fs[i], wts[i]))
print()
print('@define Int[] wwt = Int[%s]' % ', '.join(map(str, wts)))
