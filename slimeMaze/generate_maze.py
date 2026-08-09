# generate_maze.py - generator for the seamless slime-bounce parkour maze.
#
# Curvature rule (reverse-engineered from the reference arc at 4852 145 2960):
#   every bounce turns the heading exactly 22.5 deg (16 bounces = full circle,
#   turning radius ~16.3 blocks), travels a ~6.3-block horizontal chord, and
#   drops exactly 1 y-level. The only degree of freedom is the turn direction
#   (CW / CCW), which flips at random intervals and diverges at forks.
#
# The maze is a DAG with a seamless-teleport illusion:
#
#   ENTRY FUNNEL. ENTRIES start corridors at y=START_Y physically merge
#   pairwise (a merge junction is an inverted fork: two arcs arrive at
#   +-22.5 deg around one continuation) down to FUNNELS tunnel tops over
#   FUNNEL_DEPTH levels: the golden trunk top plus PORT tunnels - merge
#   junctions created directly on the golden trunk PORT_MIN..PORT_MAX
#   levels down, whose funnels grow upward from the port slot - so the
#   funnel waist is FUNNELS parallel tunnels yet every entry keeps a
#   physical route to the bottom. A fall returns the player to a
#   random entry.
#
#   GOLDEN TRUNK. One winning line from the trunk top to y=BOTTOM_Y, built
#   with backtracking; every FORK_MIN..FORK_MAX levels it reserves a decoy
#   fork (guaranteed cadence). Only this line descends past MORTAL_FLOOR.
#
#   DECOYS. Wrong choices at forks. They fork among themselves, can pair-
#   MERGE into shared doomed corridors (connector search finds a turn
#   sequence that arrives at the junction's second slot exactly), and are
#   pruned to an exponential width curve. Doomed corridors stop wandering
#   at WANDER_FLOOR.
#
#   SPLICES. No corridor is allowed to visibly dead-end. When a doomed
#   corridor dies, it is extended with an ALIGNMENT arc (constant turns
#   until its heading matches the window's entry turn) plus an exact
#   TRANSLATED COPY of a "window" somewhere higher up: WINDOW consecutive
#   bounces of a live corridor that contain no fork (turn direction may
#   vary inside the window). Because the copy is
#   a pure integer translation, a single relative `tp ~dx ~dy ~dz` while
#   the player is anywhere on the copied stretch moves them onto the real
#   corridor with position, facing, view and momentum all consistent -
#   they are "back up" without noticing. The splice dispatch function is
#   emitted as MSC; triggering it automatically is wired up later.
#
#   FORK CADENCE. No traversable stretch may run more than FORK_GAP_MAX
#   bounces without a fork (a real choice: >= 2 live kids; merges do not
#   count). The replica tail past the first splice trigger is exempt -
#   the player is teleported away there. enforce_fork_gaps() repairs
#   over-long runs with short gap-repair decoy arms, build_golden forces
#   its deepest fork at FORK_FLOOR+2 so the finish run fits the cap, and
#   verify() + the seed gate reject anything that still exceeds it.
#
# Separation stays tunnel-aware (Chebyshev >= SEP_CHEB within +-SEP_DY
# levels) so the cave shell can return later unchanged. Lineage-neighbour
# blocks are exempt within MAX_KIN undirected hops; the exemption deepens
# to JUNC_KIN when the connecting path crosses a fork or merge junction
# (sibling arms of the same junction are supposed to be close).
#
# Outputs (written next to this file):
#   slimemaze.nms          - namespace declaring all functions
#   slimemaze/buildN.msc   - slime build chain (auto-chains, no @fast);
#                            the last part chains into grounds1
#   slimemaze/groundsN.msc - the ground-scripts import as declared chain
#                            functions: creates the splice trigger ground
#                            scripts on the replica-tail slime blocks.
#                            Runs automatically at the end of the build
#                            chain, or standalone via slimemaze::grounds1
#   slimemaze/removeN.msc  - undo chain; last part chains into
#                            removegrounds1
#   slimemaze/removegroundsN.msc - removes all splice trigger ground
#                            scripts (undo counterpart of groundsN)
#   slimemaze/slimegroundsN.msc - creates a slimeblock(player) ground
#                            script on EVERY slime block except the
#                            splice trigger blocks; runs after groundsN
#                            in the build chain. Too big for __init__ -
#                            re-run once after every namespace import
#   slimemaze/removeslimegroundsN.msc - undo chain (runs after
#                            removegroundsN)
#   slimemaze/__init__.msc - runs on every namespace import: the same
#                            ground-scripts import inline, so importing
#                            the namespace always (re)wires the triggers
#   slimemaze/splice.msc   - splice dispatcher: per-id relative tp, then
#                            falls through to spliceFx(player)
#   slimemaze/fall.msc     - fall(player): teleport to a random one of
#                            the 3 starts furthest from the fall point
#                            (fallFx1 before the tp, fallFx2 after);
#                            wire it to the map's fall-catch region
#   slimemaze/spliceFx.msc, fallFx1.msc, fallFx2.msc, scaryTitle.msc,
#   slimemaze/slimeblock.msc - HAND-TUNED effect hooks: never emitted
#                            or deleted (emit spares files whose header
#                            says HAND-TUNED), only declared in the
#                            .nms. Edit these for particles/sounds;
#                            regens never touch them
#   splices.txt            - registry: trigger region + delta per dead end
#   starts.txt             - the ENTRIES start positions
#   solution.txt           - the winning route and every fork decision
#
# Usage: python generate_maze.py [seed]   (no arg = search seeds from 1)

import itertools
import math
import random
import sys
import os
from collections import defaultdict, deque

# ---- layout ------------------------------------------------------------
START_X, START_Y, START_Z = 4852, 300, 2960
BOTTOM_Y = -64
TOTAL_DEPTH = START_Y - BOTTOM_Y            # 364

# ---- curvature (matches the reference arc - do not change) --------------
CHORD = 6.3                                 # horizontal blocks per bounce
TURN = math.radians(22.5)                   # heading change per bounce
H0 = math.atan2(-2.0, -6.0)                 # reference-arc base heading

# ---- maze shape ----------------------------------------------------------
MAX_R_TOP, MAX_R_BOT = 198.0, 198.0
SOFT_MARGIN = 40.0   # inside the hard bound, prefer turns that curve inward
W_MAX = 70           # target concurrent (non-doomed) paths near the bottom
W_MID_BOOST = 0.45   # mid-depth bump on the live-path width curve: the
                     # middle of the maze reads several corridors wide
                     # instead of one trunk plus stubs
FORK_MIN, FORK_MAX = 5, 9    # levels between forks along any path
FORK_GAP_MAX = 20    # HARD cadence cap: no traversable stretch may run
                     # more than this many bounces without a fork (a
                     # block with >= 2 live kids - merge junctions are
                     # not choices and do not reset the count). The
                     # replica tail past the FIRST splice trigger is
                     # exempt (the player teleports away there).
                     # Enforced by enforce_fork_gaps() + verify() + the
                     # seed gate; stats report the worst gap and the
                     # average blocks per fork
FLIP_MIN, FLIP_MAX = 5, 18    # bounces between turn-direction flips; the
                              # max exceeds a full 16-bounce circle, so some
                              # stretches are descending helixes that return
                              # over their own start (kills dead reckoning)
FORK_TURN_LOCK = 4   # levels after a fork before a branch may flip its turn
LIFE_MIN, LIFE_MAX = 8, 24    # bounces a doomed branch survives (at the
                              # trunk top; both bounds grow with depth up
                              # to LIFE_MAX_DEEP - late mistakes cost more)
LIFE_MAX_DEEP = 40   # doomed-life upper bound at DOOM_ALL_AT depth; still
                     # clamped by y - WANDER_FLOOR, so the growth pays off
                     # in the mid-band and tapers at the wander floor
MORTAL_FLOOR = -55   # only the winning branch may descend below this
FORK_FLOOR = -46     # no new forks below this. build_golden FORCES a
                     # fork at the last legal level (fork block at
                     # FORK_FLOOR+2 = -44) so the finish run from the
                     # deepest fork to y=BOTTOM_Y is exactly
                     # FORK_GAP_MAX bounces. Only the golden trunk gets
                     # this deep (decoys stop at WANDER_FLOOR); the
                     # deep arm's splice tail bottoms out at
                     # tip-(ALIGN+WINDOW) >= MORTAL_FLOOR, which caps
                     # its alignment arc at 1-2 turns
DOOM_ALL_AT = -30    # every surviving mortal is doomed at this level
MIN_STUB = 5         # dead-end tails shorter than this are erased
BACKTRACK_MAX = 12000  # phase-1 backtrack budget per seed
MAX_KIN = 3          # tree distance up to which blocks are exempt
JUNC_KIN = MAX_KIN + 3  # exemption depth across fork/junction nodes

# ---- entry funnel ---------------------------------------------------------
ENTRIES = 10                   # number of start positions
FUNNELS = 3                    # tunnels at the funnel waist: the entries
                               # merge down to FUNNELS tunnel tops - the
                               # golden trunk top plus FUNNELS-1 ports,
                               # merge junctions created directly on the
                               # golden trunk (inverted forks), so every
                               # entry keeps a physical route down
PORT_MIN, PORT_MAX = 10, 32    # depth below TRUNK_TOP of the ports; the
                               # port funnel stays junction-free until
                               # above TRUNK_TOP, so this is also the
                               # visible length of the extra tunnels
PORT_SEP = 6                   # min level gap between two ports
FUNNEL_DEPTH = 45              # levels the funnel needs to merge them
TRUNK_TOP = START_Y - FUNNEL_DEPTH   # golden trunk starts here
FUNNEL_GAP_MIN, FUNNEL_GAP_MAX = 7, 12   # levels between funnel merges

# ---- dead-end handling ----------------------------------------------------
WANDER_FLOOR = -38   # doomed corridors stop wandering here so that...
WINDOW = 8           # ...their splice tails (<= ALIGN_MAX + WINDOW deeper)
ALIGN_MAX = 6        #    stay above MORTAL_FLOOR. The teleport triggers
                     #    sit on the first two tail blocks, so 6-7
                     #    bounces continue past whichever trigger fires -
                     #    long enough that the corridor's end is never in
                     #    sight before the splice. Windows this long are
                     #    plentiful only because turn direction may vary
                     #    inside a window (the copy is an exact
                     #    translation either way; only the entry turn
                     #    matters for the alignment arc)
MIN_RISE = 8         # a splice must send the player at least this far up
SPLICE_MAX_RISE = 128  # max vertical tp rise: seamless teleports never
                       # jump more than this many blocks up (user-
                       # approved raise from 75: vertical distance does
                       # not affect chunk loading - the horizontal
                       # SPLICE_MAX_D is the loading constraint - and
                       # the wider window pool feeds the fork-cadence
                       # machinery)
SPLICE_MAX_D = 128   # max horizontal tp distance (8 chunks): the window
                     # must be within loaded chunks of the copy tail
SPLICE_TRIES = 24    # windows tried (placement attempts) per splice
                     # attempt. Do NOT raise globally: more splice
                     # success in run_decoys means more fork-forbidden
                     # window/tail real estate, which strangles the
                     # fork-cadence repairs (A/B: 24 -> 64 nearly
                     # doubled the residual violations). Repair-context
                     # splices get SPLICE_BOOST x this instead
SPLICE_BOOST = 3     # try-budget multiplier for gap-repair arms, whose
                     # splices happen in the dense finished maze where
                     # most arc/copy placements are blocked
SPLICE_BAND = 8      # doomed corridors start trying to splice this many
                     # bounces before their life runs out
MERGE_RANGE = 30.0   # max Chebyshev tip distance to attempt a pair-merge
MERGE_K_MIN, MERGE_K_MAX = 6, 9   # bounces down to a merge junction
MERGE_PER_LEVEL = 6  # pair-merge attempts per level
MERGE_TOL = 0.9      # connector landing tolerance (chord check has slack)
MERGE_PROB = 0.9     # chance a nearby doomed pair tries to merge

# ---- separation grading ---------------------------------------------------
JUNC_NEAR_KIN = 2    # <= this many hops apart: the junction shape itself
JUNC_NEAR_MIN = 5.0  # kin-exempt pairs beyond JUNC_NEAR_KIN hops must
                     # still keep this Chebyshev distance. Sibling arms
                     # may sit close only right AT their junction; two
                     # corridors can never interweave a few hops out
                     # (the port-slot-beside-golden-fork bug that put
                     # slime blocks (4830,244,2903)/(4827,243,2903)
                     # 3 apart on crossing paths)

# ---- braids (alternate winning routes) ------------------------------------
BRAIDS = 1                     # braids attempted (kept if they build):
                               # a single alternate winning route
BRAID_MIN = 1                  # seed gate: at least this many must build
                               # (must be <= BRAIDS - stats caps at BRAIDS)
BRAID_LEN_MIN = 12             # trunk levels between fork and rejoin
BRAID_LEN_MAX = 24
BRAID_TOP_Y = TRUNK_TOP - 34   # braid forks start below the port zone
BRAID_FLOOR_Y = -20            # braid arms never descend below this
BRAID_LOCK = 4                 # diverging bounces after a braid fork
BRAID_SPACING = 4              # min trunk-level gap between braid ends
BRAID_CONNECT = 12             # start trying to land this many levels up
BRAID_HUG = 15.0               # steering floor: stay at least this far
                               # from the slot until the landing (just
                               # outside the trunk's separation alley)
BRAID_TRIES = 400              # (fork, rejoin) pairs tried per maze

# ---- splice destinations --------------------------------------------------
NOVEL_P = 0.85        # chance a dead end prefers a window OFF its own
                      # route down, so the teleport lands somewhere the
                      # player has NOT already been (windows on other
                      # ended dead-end corridors qualify)
NOVEL_MIN_FRAC = 0.2  # seed gate: min fraction of splices landing new

# ---- tunnel geometry (kept for when the cave shell returns) ---------------
AIR_R = 4
AIR_UP = 10
AIR_DOWN = 4
WALL_T = 1
WORLD_TOP = 319
LIGHT_BLOCK = 'minecraft:light[level=10]'
WALL_BLOCK = 'minecraft:stone'
DEEP_BLOCK = 'minecraft:deepslate'
DEEP_Y = 5
NAMESPACE = 'slimemaze'
WORLD_NAME = 'Epsilon'  # world the ground scripts are created in
MAX_PART_LINES = 3400   # hastebin import limit is ~4k lines; stay under
SG_PART_LINES = 2300    # slimegrounds parts: the 3-literal-Block create
                        # lines are ~230 chars, so the CHARACTER budget
                        # blows before the line budget - split earlier
SPLICE_FX_MIN_D = 64    # spliceFx only fires when the teleport moves
                        # the player more than this many blocks
                        # (euclidean |delta|); short hops stay silent
DONE_SOUND = ('@bypass /playsound minecraft:ui.toast.challenge_complete '
              'master {{player}} ~ ~ ~ 1 1')
# audible end-of-chain notification, emitted right before each final
# @player done message (chains run for minutes; the user is AFK)
BUILD_REGION = 128      # placement bucket (8 chunks): the build/remove
                        # chains tp once per bucket, @delay 10 ticks so
                        # the chunks around the player load, then place
                        # every block in the bucket - never a tp per
                        # setblock

# ---- separation rules (tunnel-aware) --------------------------------------
SEP_CHEB = 11.0
SEP_DY = AIR_UP + AIR_DOWN + 1


def rnd(v):
    return int(math.floor(v + 0.5))


def hn(h):
    # heading -> index on the 16-direction lattice around H0. NOTE:
    # branches accumulate heading windings independently, so differences
    # of hn() across branches must be wrapped with hwrap().
    return round((h - H0) / TURN)


def hwrap(n):
    # wrap a lattice-index difference to (-8, 8]
    return (n + 8) % 16 - 8


def target_width(y):
    if y >= TRUNK_TOP:
        return 3            # a few early decoys in the funnel zone
    d = TRUNK_TOP - y
    t = d / (TRUNK_TOP - BOTTOM_Y)
    return max(1, rnd((W_MAX ** t) * (1.0 + W_MID_BOOST * math.sin(
        math.pi * t))))


def max_r(y):
    return MAX_R_TOP + (MAX_R_BOT - MAX_R_TOP) * (START_Y - y) / TOTAL_DEPTH


def compass(dx, dz):
    ang = math.degrees(math.atan2(dz, dx)) % 360.0
    names = ['E', 'SE', 'S', 'SW', 'W', 'NW', 'N', 'NE']
    return names[int((ang + 22.5) // 45) % 8]


def turn_seqs(m, gap):
    # all +-1 sequences of length m whose sum == gap
    if abs(gap) > m or (m - abs(gap)) % 2:
        return
    for plus in itertools.combinations(range(m), (m + gap) // 2):
        seq = [-1] * m
        for p in plus:
            seq[p] = 1
        yield seq


class Sim:
    def __init__(self, seed):
        self.seed = seed
        self.rng = random.Random(seed)
        self.blocks = []            # dicts or None (erased)
        self.by_y = defaultdict(list)
        self.kids = defaultdict(list)
        self.branches = []
        self.forks = []
        self.reserved = []
        self.windows = []
        self.win_used = set()       # block idxs fork-forbidden (in a window)
        self.tail_tubes = []        # (pts, bbox, copy idx set) per splice
        self.win_tubes = []         # (pts, bbox) per window in use
        self.splices = []
        self.entry_tips = []
        self.funnel_seqs = []       # per funnel corridor: downward block list
        self.ports = []             # (slot, px, pz, ho, bearing, y) per port
        self.braid_seqs = []        # per braid arm: downward block list
        self.braid_list = []        # braid records (fork/join y, branch)
        self.merges = 0
        self.unspliced = 0
        self.peak_width = 0
        self.fstats = defaultdict(int)   # funnel fork-spawner outcomes
        self.bstats = defaultdict(int)   # braid attempt outcomes
        self.rstats = defaultdict(int)   # gap-repair outcomes
                                         # (insert_fork stages)
        self.sp_ctx = ''                 # rstats key prefix: 'R' while
                                         # a gap-repair arm splices
        self.fail = None                 # why run() returned False

    # ---- block store ----
    def place(self, x, y, z, prev, br, f=None):
        idx = len(self.blocks)
        b = {'x': x, 'y': y, 'z': z, 'prev': prev, 'prev2': None, 'br': br,
             'px': None, 'pz': None, 'h': None}
        if f is not None:
            b['px'], b['pz'], b['h'] = f
        self.blocks.append(b)
        self.by_y[y].append(idx)
        if prev is not None:
            self.kids[prev].append(idx)
        return idx

    def pop_block(self, idx):
        b = self.blocks[idx]
        self.by_y[b['y']].remove(idx)
        if b['prev'] is not None:
            self.kids[b['prev']].remove(idx)
        assert idx == len(self.blocks) - 1
        self.blocks.pop()

    def set_prev(self, child, parent):
        b = self.blocks[child]
        if b['prev'] is None:
            b['prev'] = parent
        else:
            b['prev2'] = parent
        self.kids[parent].append(child)

    def erase_block(self, idx):
        # non-LIFO removal: unlink from parents and children, mark None
        b = self.blocks[idx]
        self.by_y[b['y']].remove(idx)
        if b['prev'] is not None:
            try:
                self.kids[b['prev']].remove(idx)
            except ValueError:
                pass
        for k in list(self.kids.get(idx, ())):
            kb = self.blocks[k]
            if kb is not None:
                if kb['prev'] == idx:
                    kb['prev'] = None
                elif kb['prev2'] == idx:
                    kb['prev2'] = None
        self.kids.pop(idx, None)
        self.blocks[idx] = None

    def is_multi(self, i):
        b = self.blocks[i]
        if b is None:
            return False
        if b['prev2'] is not None:
            return True
        live_kids = sum(1 for k in self.kids.get(i, ())
                        if self.blocks[k] is not None)
        return live_kids >= 2

    def kin_ok(self, seeds, j, plain, junc, cheb=None):
        # Two-label BFS over the undirected block graph from `seeds`
        # (idx -> (dist, crossed_junction)). The pair is kin-exempt if
        # j is reached within `plain` hops, or within `junc` hops on a
        # path that crosses a fork or merge junction node - BUT exempt
        # pairs further than JUNC_NEAR_KIN hops must additionally keep
        # Chebyshev >= JUNC_NEAR_MIN (`cheb` is the pair's distance;
        # None skips the check). Only the junction shape itself may be
        # arbitrarily close; corridors a few hops beyond it can no
        # longer interweave.
        best = {}
        q = deque()
        for i, (d, crossed) in seeds.items():
            key = (i, bool(crossed))
            if best.get(key, 99) > d:
                best[key] = d
                q.append((i, d, bool(crossed)))
        while q:
            i, d, crossed = q.popleft()
            if best.get((i, crossed), 99) < d or d >= junc:
                continue
            b = self.blocks[i]
            if b is None:
                continue
            out = crossed or self.is_multi(i)
            nbs = [b['prev'], b['prev2']] + list(self.kids.get(i, ()))
            for nb in nbs:
                if nb is None or self.blocks[nb] is None:
                    continue
                if best.get((nb, out), 99) > d + 1:
                    best[(nb, out)] = d + 1
                    q.append((nb, d + 1, out))
        d0 = best.get((j, False), 99)
        d1 = best.get((j, True), 99)
        if not (d0 <= plain or d1 <= junc):
            return False
        if min(d0, d1) <= JUNC_NEAR_KIN:
            return True
        return cheb is None or cheb >= JUNC_NEAR_MIN

    def clear(self, x, z, y, prev, pad=False, extra=None):
        # pad=True (or a reserved fork block, br == -1) widens the keep-out
        # bubble so a newborn decoy always has room for its first bounces.
        # extra is a list of (idx, dist) seeds that let the kin BFS pass
        # through not-yet-linked junction edges (funnel arms, connectors).
        seeds = None
        for dy in range(-SEP_DY, SEP_DY + 1):
            row = self.by_y.get(y + dy)
            if not row:
                continue
            lim = SEP_CHEB
            plim = 14.0 if abs(dy) <= 7 else 12.5
            for i in row:
                b = self.blocks[i]
                if b is None:
                    continue
                d = max(abs(b['x'] - x), abs(b['z'] - z))
                if dy == 0 and d == 0:
                    return False  # exact cell taken: never allowed,
                                  # kin exemption or not (junction
                                  # connectors can otherwise land ON a
                                  # kin-exempt block - duplicate block)
                if d < (plim if (pad or b['br'] == -1) else lim):
                    if seeds is None:
                        seeds = {}
                        if prev is not None:
                            seeds[prev] = (1, False)
                        if extra:
                            for ei, ed in extra:
                                seeds[ei] = (ed, True)
                    plain = MAX_KIN if d < lim else JUNC_KIN
                    if seeds and self.kin_ok(seeds, i, plain, JUNC_KIN,
                                             cheb=d):
                        continue          # lineage neighbour: exempt
                    return False
        return True

    # ---- branches ----
    def new_branch(self, px, pz, h, d, y, last, golden=False):
        br = {'id': len(self.branches), 'px': px, 'pz': pz, 'h': h, 'dir': d,
              'flip': self.rng.randint(FLIP_MIN, FLIP_MAX),
              'fork': self.rng.randint(FORK_MIN, FORK_MAX),
              'y': y, 'last': last, 'golden': golden, 'alive': True,
              'doomed': False, 'life': 0, 'blocks': [], 'forked': False,
              'lfl': 0, 'pending': None, 'min_stub': MIN_STUB,
              'funnel': False, 'merged': False, 'skip': 0, 'spliced': False,
              'braid': False, 'landing': False}
        self.branches.append(br)
        return br

    def step(self, br, forced=None):
        rlim = max_r(br['y'] - 1)
        if forced is not None:
            cands = [forced]
        else:
            want = -br['dir'] if br['flip'] <= 0 else br['dir']
            cands = [want, -want]
            if (math.hypot(br['px'] - START_X, br['pz'] - START_Z)
                    > rlim - SOFT_MARGIN):
                cands.sort(key=lambda d: math.hypot(
                    br['px'] + CHORD * math.cos(br['h'] + d * TURN) - START_X,
                    br['pz'] + CHORD * math.sin(br['h'] + d * TURN) - START_Z))
        for d in cands:
            h2 = br['h'] + d * TURN
            nx = br['px'] + CHORD * math.cos(h2)
            nz = br['pz'] + CHORD * math.sin(h2)
            if math.hypot(nx - START_X, nz - START_Z) > rlim:
                continue
            bx, bz = rnd(nx), rnd(nz)
            if not self.clear(bx, bz, br['y'] - 1, br['last']):
                continue
            if d != br['dir']:
                br['dir'] = d
                br['flip'] = self.rng.randint(FLIP_MIN, FLIP_MAX)
            else:
                br['flip'] -= 1
            br['px'], br['pz'], br['h'] = nx, nz, h2
            br['y'] -= 1
            br['last'] = self.place(bx, br['y'], bz, br['last'], br['id'],
                                    f=(nx, nz, h2))
            br['blocks'].append(br['last'])
            return d
        return None

    def erase_tail(self, br):
        keep = br['lfl']
        tail = br['blocks'][keep:]
        for i in tail:
            b = self.blocks[i]
            self.by_y[b['y']].remove(i)
            if b['prev'] is not None:
                try:
                    self.kids[b['prev']].remove(i)
                except ValueError:
                    pass
            self.blocks[i] = None
        br['blocks'] = br['blocks'][:keep]
        if keep == 0:
            self.forks = [f for f in self.forks if f['decoy'] != br['id']]

    def end_branch(self, br):
        # a corridor may never visibly dead-end. Try to splice here; if
        # that fails, leave it - the fix_leaves post-pass will retry the
        # splice at every position and erase what cannot be saved.
        br['alive'] = False
        if br['golden'] or br['merged']:
            return
        if br['pending'] is not None:
            # claim the reserved second block so it isn't orphaned
            pd = br['pending']
            br['pending'] = None
            self.blocks[pd['idx']]['br'] = br['id']
            br['px'], br['pz'], br['h'] = pd['px'], pd['pz'], pd['h']
            br['y'] -= 1
            br['last'] = pd['idx']
            br['blocks'].append(pd['idx'])
        if not br['blocks']:
            return
        if self.splice_tail(br) or self.splice_landing(br):
            br['spliced'] = True
        else:
            # no window fits at the tip: chew NOW, mid-sweep, INCLUDING
            # the full erasure cascade through any corpse above (the
            # fix_leaves logic run at death time). Sweep-time splices
            # work because their tails grow into the still open space
            # below the sweep, and a hole this chew punches becomes
            # visible immediately - the interleaved enforcement then
            # repairs it while there is still room. Cascades left for
            # the post-pass used to DOUBLE the violation count, all of
            # it unrepairable in the finished maze
            self.chew_leaves(deque([br['last']]))

    def chew_leaves(self, q):
        # chew every illegal leaf reachable from the queue upward: try
        # to splice at each position, otherwise erase the block and
        # cascade into its parents - crossing branch corpses. Called
        # per-death mid-sweep (end_branch) and over all leaves as the
        # final post-pass (fix_leaves). Never touches ALIVE branches'
        # tips (mid-sweep they are working blocks, not corpses).
        # splice_boost: chew-time splices SAVE forks from erasure, so
        # they get the enlarged placement budget like the repair arms
        prev_boost = getattr(self, 'splice_boost', False)
        self.splice_boost = True
        tail_ends = {sp['copy'][-1] for sp in self.splices}

        def is_leaf(i):
            return not any(self.blocks[k] is not None
                           for k in self.kids.get(i, ()))

        while q:
            i = q.popleft()
            b = self.blocks[i]
            if b is None or not is_leaf(i):
                continue
            if b['y'] == BOTTOM_Y or i in tail_ends:
                continue
            brid = b['br']
            br = (self.branches[brid]
                  if isinstance(brid, int)
                  and 0 <= brid < len(self.branches) else None)
            if br is None or br['funnel'] or br['golden'] \
                    or br['alive'] or br.get('landing'):
                continue          # never erase these
            if self.splice_tail(br, tip_idx=i) \
                    or self.splice_landing(br, tip_idx=i):
                br['spliced'] = True
                tail_ends.add(self.splices[-1]['copy'][-1])
                continue
            parents = [p for p in (b['prev'], b['prev2'])
                       if p is not None]
            self.erase_block(i)
            self.unspliced += 1     # counts erased blocks
            for p in parents:
                if self.blocks[p] is not None and is_leaf(p):
                    q.append(p)
        self.splice_boost = prev_boost

    def fix_leaves(self):
        # post-pass: whatever the per-death chews left (arms alive at
        # the very bottom, corpses shielded by then-alive branches)
        self.chew_leaves(deque(
            i for i, b in enumerate(self.blocks)
            if b is not None
            and not any(self.blocks[k] is not None
                        for k in self.kids.get(i, ()))))
        # drop fork records whose arms were chewed away
        self.forks = [f for f in self.forks
                      if self.blocks[f['decoy_idx']] is not None
                      and self.blocks[f['cont_idx']] is not None]

    # ---- fork-gap cadence (FORK_GAP_MAX) -----------------------------------
    def live_fork(self, i):
        # a fork is a CHOICE going down: >= 2 live kids. A merge
        # junction (prev2) is not one and never resets the gap count
        return sum(1 for k in self.kids.get(i, ())
                   if self.blocks[k] is not None) >= 2

    def fork_gap_map(self):
        # worst-case bounces since the player last stood on a fork,
        # per live block, over EVERY upstream route: 0 at the entry
        # tips, resets to 1 on the block after a fork, max across the
        # two arrivals of a merge. Every edge steps down exactly one
        # level, so descending y order is topological
        blks = self.blocks
        d = {}
        order = sorted((i for i in range(len(blks))
                        if blks[i] is not None),
                       key=lambda i: -blks[i]['y'])
        for i in order:
            best = 0
            for p in (blks[i]['prev'], blks[i]['prev2']):
                if p is None or blks[p] is None:
                    continue
                best = max(best,
                           1 if self.live_fork(p) else d.get(p, 0) + 1)
            d[i] = best
        return d

    def fork_gap_exempt(self):
        # the replica tail past the FIRST splice trigger: the trigger
        # ground script teleports the player away, so the remaining 7
        # tail bounces are never ridden. copy[0] itself (and therefore
        # the backup trigger on copy[1], one bounce later at most one
        # over) stays enforced
        ex = set()
        for sp in self.splices:
            ex.update(sp['copy'][1:])
        return ex

    def braid_repair(self, i):
        # golden-trunk cadence runs get a REAL braid: the steered
        # phase-1c machinery (make_braid) lands on the trunk reliably
        # where plain arm insertion fails in the crowded mid-maze. The
        # braid fork at D0 resets the run, both children win, and the
        # short span keeps the fork-free arm itself within the cap
        # (arm blocks = D1 - D0 - 1 <= 13, no fspawn runs post-hoc)
        g0 = self.branches[0]['blocks']
        pos = {b: n for n, b in enumerate(g0)}
        if i not in pos:
            return False
        Dv = pos[i]
        tdir = {}
        for D in range(max(1, Dv - FORK_GAP_MAX),
                       min(len(g0) - 2, Dv + 14)):
            if TRUNK_TOP - D < MORTAL_FLOOR + 2:
                continue          # arm would dip below the mortal floor
            if not self.trunk_junc_free(D, 1):
                continue
            b = self.blocks[g0[D]]
            kids = [k for k in self.kids.get(g0[D], ())
                    if self.blocks[k] is not None]
            if b is None or b['h'] is None or len(kids) != 1:
                continue
            kb = self.blocks[kids[0]]
            if kb['h'] is None:
                continue
            t = hwrap(hn(kb['h']) - hn(b['h']))
            if abs(t) == 1:
                tdir[D] = t
        pairs = [(D0, D1) for D0 in tdir for D1 in tdir
                 if D0 < Dv and Dv - D0 <= FORK_GAP_MAX
                 and 8 <= D1 - D0 <= 14 and tdir[D0] == tdir[D1]]
        self.rng.shuffle(pairs)
        used = []
        for bd in self.braid_list:
            for key in ('fork_idx', 'join_idx'):
                D = pos.get(bd[key])
                if D is not None:
                    used.append(D)
        for D0, D1 in pairs[:60]:
            if not self.make_braid(D0, D1, used):
                continue
            arm = self.branches[-1]
            self.braid_seqs.append(list(arm['blocks']))
            self.braid_list.append({
                'arm': arm['id'], 'fork_idx': g0[D0], 'join_idx': g0[D1],
                'fy': TRUNK_TOP - D0, 'jy': TRUNK_TOP - D1})
            cont = next(k for k in self.kids.get(g0[D0], ())
                        if self.blocks[k] is not None
                        and k != arm['blocks'][0])
            self.forks.append({
                'br': 0, 'decoy': arm['id'], 'parent_idx': g0[D0],
                'cont_idx': cont, 'decoy_idx': arm['blocks'][0],
                'y': TRUNK_TOP - D0, 'golden': False, 'braid': True})
            return True
        return False

    def insert_fork(self, B):
        # gap-repair fork: spawn a short doomed decoy arm off the
        # 1-kid block B (the fspawn shape: mirror of the turn the
        # corridor takes there) and ride it to a splice, or - when no
        # window fits anywhere - chewed away again. Returns False (and
        # leaves no debris) if the slot is structurally unusable, the
        # first bounce has no room, or the arm cannot splice from any
        # of its positions
        bb = self.blocks[B]
        if bb is None or bb['h'] is None or bb['px'] is None \
                or bb['prev2'] is not None:
            self.rstats['if_struct'] += 1
            return False
        # never fork on a used window or a replica tail (translation
        # fidelity: tail and window must stay block-for-block twins)
        if B in self.win_used \
                or any(B in sp['copy'] for sp in self.splices):
            self.rstats['if_locked'] += 1
            return False
        kids = [k for k in self.kids.get(B, ())
                if self.blocks[k] is not None]
        if len(kids) != 1:
            self.rstats['if_kids'] += 1
            return False
        kb = self.blocks[kids[0]]
        if kb is None or kb['h'] is None:
            self.rstats['if_struct'] += 1
            return False
        t_used = hwrap(hn(kb['h']) - hn(bb['h']))
        if abs(t_used) != 1:
            self.rstats['if_struct'] += 1
            return False
        y = bb['y'] - 1
        hd = bb['h'] - t_used * TURN
        nx = bb['px'] + CHORD * math.cos(hd)
        nz = bb['pz'] + CHORD * math.sin(hd)
        bx, bz = rnd(nx), rnd(nz)
        if math.hypot(nx - START_X, nz - START_Z) > max_r(y) \
                or not self.clear(bx, bz, y, B):
            self.rstats['if_blocked'] += 1
            return False
        child = self.new_branch(bb['px'], bb['pz'], hd, -t_used,
                                y + 1, B)
        child['flip'] = max(child['flip'], FORK_TURN_LOCK)
        child['doomed'] = True
        c1 = self.place(bx, y, bz, B, child['id'], f=(nx, nz, hd))
        child['px'], child['pz'] = nx, nz
        child['y'] = y
        child['last'] = c1
        child['blocks'].append(c1)
        # the arm may wander close to the cap: splice_tail's cadence
        # guard (d_tip + |g| + 1 <= FORK_GAP_MAX) self-regulates which
        # windows stay legal as the arm deepens, so a longer walk just
        # means more splice chances with progressively stricter arcs
        child['life'] = min(
            self.rng.randint(8, FORK_GAP_MAX - 4),
            child['y'] - WANDER_FLOOR)
        self.sp_ctx = 'R'
        while child['life'] > 0 and child['y'] - 1 >= WANDER_FLOOR:
            # a repair arm splices as soon as any window fits - the
            # fork is the point, not the wander
            if self.splice_tail(child):
                child['spliced'] = True
                break
            if self.step(child) is None \
                    and self.rewind_retry(child) is None:
                # without the rewind, one double-blocked bounce in the
                # busy band strands the arm on a tip where no splice
                # can ever place - the single dominant repair failure
                break
            child['life'] -= 1
        child['alive'] = False
        if not child['spliced'] and self.splice_landing(child):
            child['spliced'] = True
        if not child['spliced']:
            # chew upward (with landing retries per position): if the
            # whole arm goes, the fork never existed
            self.chew_leaves(deque([child['last']]))
        self.sp_ctx = ''
        if not child['spliced'] and not child['merged']:
            self.rstats['if_arm_died'] += 1
            return False
        self.rstats['if_ok'] += 1
        self.forks.append({
            'br': bb['br'], 'decoy': child['id'], 'parent_idx': B,
            'cont_idx': kids[0], 'decoy_idx': c1, 'y': bb['y'],
            'golden': bb['br'] == 0})
        return True

    def enforce_fork_gaps(self, min_y=None, passes=12):
        # wherever a traversable stretch runs more than FORK_GAP_MAX
        # bounces without a fork, grow a gap-repair arm (insert_fork)
        # as deep into the run as clearance allows. A run start always
        # has gap exactly FORK_GAP_MAX+1 (the count rises by at most 1
        # per bounce), and one fork there resets everything downstream
        # of it; longer runs converge over the passes.
        # Called INTERLEAVED with the run_decoys sweep (min_y = just
        # above the sweep level): a violation above the sweep is final
        # the moment it forms - forks are only ever added at the sweep
        # level - and repairing it immediately, while the maze below
        # is still empty, succeeds far more often than the end pass.
        # The final full call (min_y=None) mops up; whatever remains
        # is reported by verify()/stats and fails the seed
        self.splice_boost = True
        try:
            self._enforce_fork_gaps(min_y, passes)
        finally:
            self.splice_boost = False

    def _enforce_fork_gaps(self, min_y, passes):
        failed = set()
        for _pass in range(passes):
            d = self.fork_gap_map()
            ex = self.fork_gap_exempt()
            if not any(v > FORK_GAP_MAX and i not in ex
                       and (min_y is None or self.blocks[i]['y'] > min_y)
                       for i, v in d.items()):
                return
            starts = [i for i, v in d.items()
                      if v == FORK_GAP_MAX + 1 and i not in ex
                      and (min_y is None
                           or self.blocks[i]['y'] > min_y)]
            # never fork within 5 bounces upstream of a splice arc end:
            # the arm would be kin-exempt (JUNC_KIN) beside the replica
            # tail tube and the decoration stamp would overwrite its
            # corridor. Natural forks keep this margin automatically
            # (do_fork needs life >= MIN_STUB before the splice)
            near_tail = set()
            for sp in self.splices:
                j = self.blocks[sp['copy'][0]]['prev']
                for _ in range(6):
                    if j is None or self.blocks[j] is None:
                        break
                    near_tail.add(j)
                    j = self.blocks[j]['prev']
            progress = False
            for i in starts:
                # golden-trunk runs: try a braid first (see braid_repair)
                if self.blocks[i]['br'] == 0 and self.braid_repair(i):
                    progress = True
                    continue
                # candidates: ancestors along the offending route,
                # deepest (largest remaining reset effect) first
                cands = []
                j = i
                while len(cands) < FORK_GAP_MAX + 1:
                    b = self.blocks[j]
                    nxt = None
                    for p in (b['prev'], b['prev2']):
                        if p is not None and self.blocks[p] is not None \
                                and (1 if self.live_fork(p)
                                     else d.get(p, 0) + 1) == d[j]:
                            nxt = p
                            break
                    if nxt is None or self.live_fork(nxt):
                        break
                    cands.append(nxt)
                    j = nxt
                for B in cands:
                    if B in failed or B in near_tail:
                        continue
                    # repeated attempts: the arm's walk and window
                    # shuffle are random, so a retry explores
                    # different space
                    if any(self.insert_fork(B) for _try in range(5)):
                        progress = True
                        break
                    failed.add(B)
            if not progress:
                return

    def rewind_retry(self, br, tries=3):
        # a wandering arm used to die on its first double-blocked
        # bounce. Early deaths high in the maze are the main source of
        # fork-cadence holes: the young tip sits above the window-rich
        # depths, can neither splice nor merge, and fix_leaves erases
        # the arm AND its fork. Instead: rewind a few bounces (non-LIFO
        # erase - other branches place blocks between our steps), flip
        # direction and step again. Never erases through a block that
        # carries another live kid (a decoy fork hangs there)
        for _ in range(tries):
            want = min(self.rng.randint(2, 4), len(br['blocks']) - 1)
            done = 0
            while done < want and len(br['blocks']) > 1:
                idx = br['blocks'][-1]
                if any(self.blocks[kk] is not None
                       for kk in self.kids.get(idx, ())):
                    break
                br['blocks'].pop()
                self.erase_block(idx)
                done += 1
            if done == 0:
                return None
            nb = self.blocks[br['blocks'][-1]]
            br['px'], br['pz'], br['h'] = nb['px'], nb['pz'], nb['h']
            br['y'] = nb['y']
            br['last'] = br['blocks'][-1]
            br['dir'] = -br['dir']
            br['flip'] = self.rng.randint(FLIP_MIN, FLIP_MAX)
            if br['doomed']:
                br['life'] += done
            d = self.step(br)
            if d is not None:
                return d
        return None

    def doom(self, br):
        br['doomed'] = True
        # depth-scaled lifetime: near the trunk top a wrong turn dies in
        # LIFE_MIN..LIFE_MAX bounces; by DOOM_ALL_AT both bounds have
        # grown (up to LIFE_MAX_DEEP) so deep mistakes wander far longer
        # before their splice fires
        t = min(1.0, max(0.0, (TRUNK_TOP - br['y'])
                         / float(TRUNK_TOP - DOOM_ALL_AT)))
        life = self.rng.randint(LIFE_MIN + rnd(t * 10),
                                LIFE_MAX + rnd(t * (LIFE_MAX_DEEP
                                                    - LIFE_MAX)))
        # arms born in the funnel zone must wander deep enough to reach
        # window-rich depths, or they can never splice and get erased
        # (which visually deletes their fork)
        if br['y'] > TRUNK_TOP - 5:
            life = max(life, 18)
        br['life'] = min(life, br['y'] - WANDER_FLOOR)
        if br['life'] <= 0:
            self.end_branch(br)

    # ---- phase 1: golden trunk + reserved fork spots -----------------------
    def reserve_decoy(self, pre, d, cont_idx):
        px, pz, h, y, last = pre
        h2 = h - d * TURN
        nx = px + CHORD * math.cos(h2)
        nz = pz + CHORD * math.sin(h2)
        if math.hypot(nx - START_X, nz - START_Z) > max_r(y - 1):
            return None
        bx, bz = rnd(nx), rnd(nz)
        if not self.clear(bx, bz, y - 1, last, pad=True):
            return None
        i1 = self.place(bx, y - 1, bz, last, -1, f=(nx, nz, h2))
        h3 = h2 - d * TURN
        nx2 = nx + CHORD * math.cos(h3)
        nz2 = nz + CHORD * math.sin(h3)
        bx2, bz2 = rnd(nx2), rnd(nz2)
        if (math.hypot(nx2 - START_X, nz2 - START_Z) > max_r(y - 2)
                or not self.clear(bx2, bz2, y - 2, i1, pad=True)):
            self.pop_block(i1)
            return None
        i2 = self.place(bx2, y - 2, bz2, i1, -1, f=(nx2, nz2, h3))
        return {'y': y - 1, 'dir': -d, 'parent_idx': last,
                'cont_idx': cont_idx, 'py': y,
                'c1': i1, 'px1': nx, 'pz1': nz, 'h1': h2,
                'c2': i2, 'px2': nx2, 'pz2': nz2, 'h2': h3}

    def build_golden(self):
        idx0 = self.place(START_X, TRUNK_TOP, START_Z, None, 0,
                          f=(float(START_X), float(START_Z), None))
        g = self.new_branch(float(START_X), float(START_Z), H0 - TURN, +1,
                            TRUNK_TOP, idx0, golden=True)
        g['blocks'].append(idx0)
        g['gfork'] = self.rng.randint(FORK_MIN, FORK_MAX)

        def snap():
            return {k: g[k] for k in ('px', 'pz', 'h', 'dir', 'flip',
                                      'y', 'last', 'gfork')}

        def undo_step():
            self.pop_block(g['blocks'].pop())

        meta = [{'snap': snap(), 'res': None}]
        backtracks = 0
        while g['y'] > BOTTOM_Y:
            pre_snap = snap()
            pre = (g['px'], g['pz'], g['h'], g['y'], g['last'])
            # a fork is also FORCED at the deepest legal level so the
            # forkless finish run to y=BOTTOM_Y stays <= FORK_GAP_MAX
            fork_due = (g['gfork'] <= 1 or g['y'] == FORK_FLOOR + 2) \
                and g['y'] - 1 > FORK_FLOOR
            g['gfork'] -= 1
            res = None
            if fork_due:
                d = self.step(g)
                if d is not None:
                    res = self.reserve_decoy(pre, d, g['last'])
                    if res is None:
                        undo_step()
                        g.update(pre_snap)
                        g['gfork'] = pre_snap['gfork'] - 1
                        d2 = self.step(g, forced=-d)
                        if d2 is not None:
                            res = self.reserve_decoy(pre, d2, g['last'])
                            if res is None:
                                undo_step()
                                g.update(pre_snap)
                                g['gfork'] = pre_snap['gfork'] - 1
                                d = None
                            else:
                                d = d2
                        else:
                            d = None
                if d is not None:
                    g['gfork'] = self.rng.randint(FORK_MIN, FORK_MAX)
                    g['flip'] = max(g['flip'], FORK_TURN_LOCK)
                ok = d is not None
            else:
                ok = self.step(g) is not None
            if ok:
                meta.append({'snap': snap(), 'res': res})
                continue
            backtracks += 1
            if backtracks > BACKTRACK_MAX:
                return None
            k = min(len(meta) - 1, self.rng.randint(3, 10))
            for _ in range(k):
                ent = meta.pop()
                if ent['res'] is not None:
                    self.pop_block(ent['res']['c2'])
                    self.pop_block(ent['res']['c1'])
                undo_step()
            g.update(meta[-1]['snap'])
            g['flip'] = self.rng.randint(1, FLIP_MAX)
            if self.rng.random() < 0.5:
                g['dir'] = -g['dir']
        g['alive'] = False
        self.reserved = [m['res'] for m in meta if m['res'] is not None]
        return g

    def reserve_along(self, chain, gap_lo=6, gap_hi=9):
        # cadence stubs for static corridors: walk a DOWNWARD block
        # chain (funnel corridors incl. port climbs, braid arms) and
        # reserve a mirror-turn 2-block decoy stub (reserve_decoy: pad
        # bubble, activated by run_decoys like the golden ones) every
        # gap_lo..gap_hi levels. These corridors are junction-free by
        # construction and used to rely on fspawn forks placed
        # mid-sweep - when those chewed, the corridor injected a
        # 20+ forkless ride straight into its junction. Reserving at
        # build time, in a nearly empty world, almost never fails
        timer = self.rng.randint(gap_lo, gap_hi)
        for n in range(len(chain) - 1):
            B, K = chain[n], chain[n + 1]
            timer -= 1
            if timer > 0:
                continue
            bb, kb = self.blocks[B], self.blocks[K]
            if bb is None or kb is None or bb['h'] is None \
                    or kb['h'] is None or bb['px'] is None \
                    or bb['prev2'] is not None or self.is_multi(B):
                timer = 1
                continue
            t = hwrap(hn(kb['h']) - hn(bb['h']))
            if abs(t) != 1:
                timer = 1
                continue
            res = self.reserve_decoy((bb['px'], bb['pz'], bb['h'],
                                      bb['y'], B), t, K)
            if res is None:
                timer = 1
                continue
            res['golden'] = False
            self.reserved.append(res)
            timer = self.rng.randint(gap_lo, gap_hi)

    def trunk_junc_free(self, D, span):
        # no fork or merge junction within `span` trunk steps of depth
        # D: stacked junctions hang their side arms (reserved decoy +
        # port/braid slot) within a couple of blocks of each other -
        # exactly the interweave the separation grading forbids
        g = self.branches[0]['blocks']
        for dd in range(max(0, D - span), min(len(g), D + span + 1)):
            if self.blocks[g[dd]] is None or self.is_multi(g[dd]):
                return False
        return True

    # ---- phase 1a: trunk ports (the extra tunnel mouths) --------------------
    def make_port(self, used):
        # a PORT is a merge junction created directly ON the golden
        # trunk at depth PORT_MIN..PORT_MAX below TRUNK_TOP, the exact
        # inverted-fork shape every pair-merge produces (two arrivals
        # +-22.5 deg around one continuation). The trunk's own parent
        # is one arrival; the port adds the second arrival slot one
        # level up and one chord back - always on the OUTSIDE of the
        # trunk's local turn, which curves away from it. The entry
        # funnel for the port then grows upward from the slot, so the
        # funnel waist reads as FUNNELS parallel tunnels and every
        # entry keeps a physical route to the bottom through its port.
        # Slot legality is the sanctioned sibling-arm case (1 kin hop
        # through J); the escape probe rejects slots whose two possible
        # climb-out parents are both blocked - a funnel rooted there
        # could never leave
        g = self.branches[0]['blocks']
        depths = [d for d in range(PORT_MIN, PORT_MAX + 1)
                  if d < len(g)
                  and not any(abs(d - u) < PORT_SEP for u in used)]
        self.rng.shuffle(depths)
        for D in depths:
            if not self.trunk_junc_free(D, 1):
                continue      # a fork right beside the port junction
                              # would interweave its decoy with the slot
            J = g[D]
            jb = self.blocks[J]
            if jb is None or jb['h'] is None \
                    or jb['prev2'] is not None:
                continue
            kids_live = [kk for kk in self.kids.get(J, ())
                         if self.blocks[kk] is not None]
            if len(kids_live) != 1:
                continue          # golden fork or reserved decoy at J
            kb = self.blocks[kids_live[0]]
            if kb['h'] is None:
                continue
            t = hwrap(hn(kb['h']) - hn(jb['h']))
            if abs(t) != 1:
                continue
            arr2 = jb['h'] + 2 * t * TURN
            sx = jb['px'] - CHORD * math.cos(arr2)
            sz = jb['pz'] - CHORD * math.sin(arr2)
            u = jb['y'] + 1
            if not self.clear(rnd(sx), rnd(sz), u, None,
                              extra=[(J, 1)]):
                continue
            esc = False
            for tt in (-1, 1):
                arr = arr2 - tt * TURN
                ex = sx - CHORD * math.cos(arr)
                ez = sz - CHORD * math.sin(arr)
                if self.clear(rnd(ex), rnd(ez), u + 1, None,
                              extra=[(J, 2)]):
                    esc = True
                    break
            if not esc:
                continue
            slot = self.place(rnd(sx), u, rnd(sz), None, -2,
                              f=(sx, sz, None))
            self.set_prev(J, slot)
            jb['h2'] = arr2
            return (slot, sx, sz, arr2,
                    math.atan2(sz - START_Z, sx - START_X), u, D, J)
        return None

    def unmake_port(self, port):
        # undo a port whose funnel could not grow: drop the slot (this
        # also unlinks J's prev2) and clear the junction heading
        slot, J = port[0], port[7]
        self.blocks[J]['h2'] = None
        self.erase_block(slot)

    # ---- phase 1c: braids (alternate winning routes) ------------------------
    def braid_connect(self, br, J, arr2, sx, sz, m):
        # land the braid arm back on the trunk: find a +-22.5-turn
        # sequence of length m from the arm tip that arrives exactly at
        # the slot (one chord back from J along arr2, one level above) -
        # the same inverted-fork junction shape pair-merges and ports
        # produce. All cross-branch lattice gaps go through hwrap()
        # (branch windings differ)
        jb = self.blocks[J]
        if math.hypot(br['px'] - sx, br['pz'] - sz) > CHORD * m * 0.95:
            self.rstats['bc_far'] += 1
            return False
        cands = []
        for fin_off in (-1, 1):
            gap = hwrap(hn(arr2) + fin_off - hn(br['h']))
            for seq in turn_seqs(m, gap):
                px, pz, h = br['px'], br['pz'], br['h']
                pts = []
                for t2 in seq:
                    h += t2 * TURN
                    px += CHORD * math.cos(h)
                    pz += CHORD * math.sin(h)
                    pts.append((px, pz, h))
                err = math.hypot(px - sx, pz - sz)
                if err <= MERGE_TOL:
                    cands.append((err, pts))
        if not cands:
            self.rstats['bc_noseq'] += 1
            return False
        cands.sort(key=lambda c: c[0])
        for err, pts in cands[:10]:
            placed = []
            last = br['last']
            ok = True
            for si, (px, pz, h) in enumerate(pts):
                bx, bz = rnd(px), rnd(pz)
                yy = br['y'] - si - 1
                if (math.hypot(px - START_X, pz - START_Z) > max_r(yy)
                        or not self.clear(bx, bz, yy, last,
                                          extra=[(J, m - si)])):
                    self.rstats['bc_place'] += 1
                    ok = False
                    break
                last = self.place(bx, yy, bz, last, br['id'],
                                  f=(px, pz, h))
                placed.append(last)
            if ok:
                self.set_prev(J, placed[-1])
                jb['h2'] = arr2
                br['blocks'].extend(placed)
                br['last'] = placed[-1]
                br['y'] -= m
                br['merged'] = True
                return True
            for i in reversed(placed):
                self.pop_block(i)
        return False

    def make_braid(self, D0, D1, used):
        # one braid: fork OFF the golden trunk at depth D0, wander
        # parallel on the outside of the trunk's local turn, and land
        # back ON the trunk at depth D1 - an alternate winning route.
        # Both trunk ends must be junction-free (trunk_junc_free): a
        # junction beside a junction hangs its side arms within a few
        # blocks of each other, which the separation grading forbids.
        # The arm's mid blocks are far-kin from the mid-trunk, so
        # clear() keeps the two corridors >= SEP_CHEB apart until the
        # sanctioned landing shape
        if any(abs(D0 - u) < BRAID_SPACING or abs(D1 - u) < BRAID_SPACING
               for u in used):
            self.bstats['spacing'] += 1
            return False
        if not (self.trunk_junc_free(D0, 1) and self.trunk_junc_free(D1, 1)):
            self.bstats['junction'] += 1
            return False
        g0 = self.branches[0]['blocks']
        F, J = g0[D0], g0[D1]
        fb, jb = self.blocks[F], self.blocks[J]
        if fb is None or jb is None or fb['h'] is None \
                or jb['h'] is None or jb['prev2'] is not None:
            self.bstats['geometry'] += 1
            return False
        fkids = [k for k in self.kids.get(F, ())
                 if self.blocks[k] is not None]
        jkids = [k for k in self.kids.get(J, ())
                 if self.blocks[k] is not None]
        if len(fkids) != 1 or len(jkids) != 1:
            self.bstats['kids'] += 1
            return False
        cb, kb = self.blocks[fkids[0]], self.blocks[jkids[0]]
        if cb['h'] is None or kb['h'] is None:
            self.bstats['geometry'] += 1
            return False
        t_c = hwrap(hn(cb['h']) - hn(fb['h']))
        t_j = hwrap(hn(kb['h']) - hn(jb['h']))
        if abs(t_c) != 1 or abs(t_j) != 1 or t_j != t_c:
            self.bstats['side'] += 1
            return False          # slot must open on the arm's side
        arr2 = jb['h'] + 2 * t_j * TURN
        sx = jb['px'] - CHORD * math.cos(arr2)
        sz = jb['pz'] - CHORD * math.sin(arr2)
        sy = jb['y'] + 1
        n_b = len(self.blocks)
        br = self.new_branch(fb['px'], fb['pz'], fb['h'], -t_c,
                             fb['y'], F)
        br['alive'] = False
        br['braid'] = True

        def fail():
            for i in range(len(self.blocks) - 1, n_b - 1, -1):
                self.pop_block(i)
            assert self.branches[-1] is br
            self.branches.pop()
            return False

        # diverge: the first bounce is the fork mirror (forced away
        # from the continuation); the rest of the lock keeps dir=-t_c
        # via the fresh flip counter but may fall back inward around a
        # blocking decoy stub (the upward mirror of FORK_TURN_LOCK)
        for k in range(BRAID_LOCK):
            if br['y'] - 1 <= sy + 2 or self.step(
                    br, forced=-t_c if k == 0 else None) is None:
                self.bstats['lock'] += 1
                return fail()
        # steer along the alley beside the trunk: outside the trunk's
        # separation ring and the reserved-stub bubbles, inside landing
        # reach of the slot. On a double-blocked bounce, rewind a few
        # bounces and try the other family (the funnel growth pattern)
        tpts = [(self.blocks[g]['px'], self.blocks[g]['pz'])
                for g in self.branches[0]['blocks'][D0:D1 + 1]]
        hist, taken = [], []
        attempts = 0
        while True:
            m = br['y'] - sy
            if m < 3:
                self.bstats['overshoot'] += 1
                return fail()
            if m <= BRAID_CONNECT:
                if self.braid_connect(br, J, arr2, sx, sz, m):
                    break
                if m <= 3:
                    self.bstats['no_landing'] += 1
                    return fail()
            cap = CHORD * (m - 1) * 0.92
            opts = []
            for t in (br['dir'], -br['dir']):
                h2 = br['h'] + t * TURN
                nx = br['px'] + CHORD * math.cos(h2)
                nz = br['pz'] + CHORD * math.sin(h2)
                nd = math.hypot(nx - sx, nz - sz)
                if nd > cap:
                    opts.append((1e9, t))
                    continue          # would leave landing range
                lat = min(math.hypot(nx - tx, nz - tz)
                          for tx, tz in tpts)
                pen = max(0.0, nd - cap * 0.9)
                if lat < 13.0:
                    pen += (13.0 - lat) * 3.0
                elif lat > 26.0:
                    pen += (lat - 26.0) * 0.5
                opts.append((pen, t))
            opts.sort(key=lambda o: o[0])
            snap = {k: br[k] for k in ('px', 'pz', 'h', 'dir', 'flip',
                                       'y', 'last')}
            stepped = None
            for pen, t in opts:
                if pen >= 1e9:
                    continue
                if self.step(br, forced=t) is not None:
                    stepped = t
                    break
            if stepped is None:
                attempts += 1
                if attempts > 40 or not hist:
                    self.bstats['blocked'] += 1
                    return fail()
                r = min(len(hist), self.rng.randint(2, 3 + attempts))
                for _ in range(r):
                    self.pop_block(br['blocks'].pop())
                br.update(hist[-r])
                br['dir'] = -taken[-r]
                del hist[-r:], taken[-r:]
                continue
            hist.append(snap)
            taken.append(stepped)
        self.bstats['ok'] += 1
        return True

    def build_braids(self):
        # phase 1c: alternate winning routes through the middle of the
        # maze. Each braid is a fork where BOTH children reach the
        # bottom and a merge junction far below the entry funnel, so
        # merging stops being a top-only feature and the mid-maze stops
        # reading as one memorizable line
        g0 = self.branches[0]['blocks']
        dmin = TRUNK_TOP - BRAID_TOP_Y
        dmax = min(len(g0) - 2, TRUNK_TOP - BRAID_FLOOR_Y + 1)
        # enumerate junction-free, same-turn depth pairs up front
        # (random rolls mostly land on reserved golden forks or
        # mismatched sides); make_braid re-checks junction-freeness
        # because committed braids add junctions
        tdir = {}
        for D in range(dmin, dmax + 1):
            if not self.trunk_junc_free(D, 1):
                continue
            b = self.blocks[g0[D]]
            kids = [k for k in self.kids.get(g0[D], ())
                    if self.blocks[k] is not None]
            if b is None or b['h'] is None or len(kids) != 1:
                continue
            kb = self.blocks[kids[0]]
            if kb['h'] is None:
                continue
            t = hwrap(hn(kb['h']) - hn(b['h']))
            if abs(t) == 1:
                tdir[D] = t
        # alley pre-screen: a braid arm rides ~15 blocks outside the
        # trunk. Where the trunk S-curves back, that offset point sits
        # closer than the separation minimum to some other trunk block
        # and every arm through the span dies - skip those spans
        # without placing a single block
        span_ok = {}
        for d in range(dmin, dmax + 1):
            b = self.blocks[g0[d]]
            if b is None or b['h'] is None:
                span_ok[d] = {-1: False, 1: False}
                continue
            span_ok[d] = {}
            for s in (-1, 1):
                px = b['px'] + 15.0 * math.cos(b['h'] + s * math.pi / 2)
                pz = b['pz'] + 15.0 * math.sin(b['h'] + s * math.pi / 2)
                ok = math.hypot(px - START_X, pz - START_Z) \
                    <= max_r(b['y'])
                if ok:
                    for e in range(max(0, d - SEP_DY),
                                   min(len(g0), d + SEP_DY + 1)):
                        if abs(e - d) <= 3:
                            continue
                        eb = self.blocks[g0[e]]
                        if eb is None:
                            continue
                        if math.hypot(px - eb['px'],
                                      pz - eb['pz']) < 11.5:
                            ok = False
                            break
                span_ok[d][s] = ok
        pairs = [(D0, D1) for D0 in tdir for D1 in tdir
                 if BRAID_LEN_MIN <= D1 - D0 <= BRAID_LEN_MAX
                 and tdir[D0] == tdir[D1]
                 and all(span_ok[d][-tdir[D0]]
                         for d in range(D0 + 2, D1 - 1))]
        self.rng.shuffle(pairs)
        used = []
        for D0, D1 in pairs[:BRAID_TRIES]:
            if len(self.braid_list) >= BRAIDS:
                break
            if not self.make_braid(D0, D1, used):
                continue
            used += [D0, D1]
            arm = self.branches[-1]
            self.braid_seqs.append(list(arm['blocks']))
            self.braid_list.append({
                'arm': arm['id'], 'fork_idx': g0[D0], 'join_idx': g0[D1],
                'fy': TRUNK_TOP - D0, 'jy': TRUNK_TOP - D1})
            cont = next(k for k in self.kids.get(g0[D0], ())
                        if self.blocks[k] is not None
                        and k != arm['blocks'][0])
            self.forks.append({
                'br': 0, 'decoy': arm['id'], 'parent_idx': g0[D0],
                'cont_idx': cont, 'decoy_idx': arm['blocks'][0],
                'y': TRUNK_TOP - D0, 'golden': False, 'braid': True})

    # ---- phase 1b: entry funnel (grown upward from the tunnel tops) --------
    def build_funnel(self, ridx, rx, rz, ho, y0, quota, theta, spread):
        # grow ONE funnel: the subtree of entry corridors that merges
        # down onto the root block ridx (the golden trunk top or a
        # port slot on the trunk). Called once per funnel by run(),
        # which rolls back and re-rolls just this subtree on failure
        def new_cor(top, px, pz, ho, y, quota, theta, spread):
            br = self.new_branch(px, pz, ho, self.rng.choice((-1, 1)),
                                 y, top)
            br['alive'] = False
            br['funnel'] = True
            return {'top': top, 'px': px, 'pz': pz, 'ho': ho, 'y': y,
                    'quota': quota, 'birth_ho': ho,
                    'theta': theta, 'spread': spread,
                    'timer': self.rng.randint(FUNNEL_GAP_MIN, FUNNEL_GAP_MAX),
                    'dir': self.rng.choice((-1, 1)),
                    'flip': self.rng.randint(FLIP_MIN, FLIP_MAX),
                    'br': br}

        def rewind(cor, n):
            # erase up to n of this corridor's own blocks and re-anchor
            br = cor['br']
            take = min(n, len(br['blocks']) - 1)
            if take <= 0:
                return False
            for _ in range(take):
                self.erase_block(br['blocks'].pop())
            top = br['blocks'][-1]
            tb = self.blocks[top]
            cor['top'] = top
            cor['px'], cor['pz'], cor['y'] = tb['px'], tb['pz'], tb['y']
            if len(br['blocks']) == 1:
                cor['ho'] = cor['birth_ho']
            else:
                kid = next(k for k in self.kids.get(top, ())
                           if self.blocks[k] is not None)
                cor['ho'] = self.blocks[kid]['h']
            cor['timer'] += take
            return True

        work = deque([new_cor(ridx, rx, rz, ho, y0, quota,
                              theta, spread)])
        cor0 = work[0]
        if self.blocks[ridx]['br'] == -2:
            # a port slot: the funnel corridor owns it, so it is
            # emitted with the branch (block 0 stays golden's)
            self.blocks[ridx]['br'] = cor0['br']['id']
            cor0['br']['blocks'].append(ridx)
        # the trunk top junctions immediately; a port corridor stays
        # junction-free until clear of TRUNK_TOP, so the waist is
        # exactly FUNNELS tunnels wide
        cor0['timer'] = (0 if y0 == TRUNK_TOP
                         else TRUNK_TOP - y0 + self.rng.randint(3, 7))
        budget = 9000
        while work:
            cor = work.popleft()
            attempts = 0
            while True:
                budget -= 1
                if budget <= 0:
                    return False
                if cor['y'] >= START_Y:
                    if cor['quota'] != 1:
                        return False
                    self.entry_tips.append(cor['top'])
                    break
                u = cor['y'] + 1
                remaining = START_Y - cor['y']
                need = (max(0, cor['quota'] - 1).bit_length()
                        * FUNNEL_GAP_MIN + 3)
                force = cor['quota'] >= 2 and remaining <= need
                if cor['quota'] >= 2 and (cor['timer'] <= 0 or force):
                    # merge junction: both arrival slots become parents
                    tops = []
                    got = True
                    for s in (-1, 1):
                        arr = cor['ho'] + s * TURN
                        nx = cor['px'] - CHORD * math.cos(arr)
                        nz = cor['pz'] - CHORD * math.sin(arr)
                        bx, bz = rnd(nx), rnd(nz)
                        seeds = [(cor['top'], 1)] + [(t[4], 2)
                                                     for t in tops]
                        if (math.hypot(nx - START_X, nz - START_Z)
                                > max_r(u)
                                or not self.clear(bx, bz, u, None,
                                                  extra=seeds)):
                            got = False
                            break
                        tops.append((nx, nz, arr, s,
                                     self.place(bx, u, bz, None, -2,
                                                f=(nx, nz, None))))
                    if got:
                        qa = (cor['quota'] + 1) // 2
                        for (nx, nz, arr, s, pidx), q in zip(
                                tops, (qa, cor['quota'] - qa)):
                            self.set_prev(cor['top'], pidx)
                            # each child owns half the parent's angular
                            # sector; its growth biases toward it
                            c2 = new_cor(pidx, nx, nz, arr, u, q,
                                         cor['theta'] + s * cor['spread'] / 4,
                                         cor['spread'] / 2)
                            # keep the arms rotating apart for a few
                            # bounces (upward mirror of FORK_TURN_LOCK)
                            c2['dir'] = -s
                            c2['flip'] = FORK_TURN_LOCK + 2
                            self.blocks[pidx]['br'] = c2['br']['id']
                            c2['br']['blocks'].append(pidx)
                            work.append(c2)   # FIFO: subtrees interleave
                        jb = self.blocks[cor['top']]
                        jb['h'] = tops[0][2]
                        jb['h2'] = tops[1][2]
                        break            # this corridor ends at the junction
                    for t in tops:
                        self.pop_block(t[4])
                    cor['timer'] = 1    # retry the merge next level
                # plain upward step: the parent sits one chord back along
                # the arrival heading into the current top block. Turn
                # choice biases toward the corridor's own radial sector so
                # the ten corridors fan apart deterministically.
                ux = math.cos(cor['theta'])
                uz = math.sin(cor['theta'])

                def sector_score(t):
                    a = cor['ho'] - t * TURN
                    return ((cor['px'] - CHORD * math.cos(a) - START_X) * ux
                            + (cor['pz'] - CHORD * math.sin(a) - START_Z)
                            * uz)

                if cor['flip'] <= 0:
                    # commit to a fresh same-direction run toward the
                    # corridor's sector - long runs create splice windows
                    cor['dir'] = max((-1, 1), key=sector_score)
                    cor['flip'] = self.rng.randint(6, 10)
                order = (cor['dir'], -cor['dir'])
                stepped = False
                for t in order:
                    arr = cor['ho'] - t * TURN
                    nx = cor['px'] - CHORD * math.cos(arr)
                    nz = cor['pz'] - CHORD * math.sin(arr)
                    bx, bz = rnd(nx), rnd(nz)
                    if (math.hypot(nx - START_X, nz - START_Z) > max_r(u)
                            or not self.clear(bx, bz, u, None,
                                              extra=[(cor['top'], 1)])):
                        continue
                    pidx = self.place(bx, u, bz, None, cor['br']['id'],
                                      f=(nx, nz, None))
                    self.set_prev(cor['top'], pidx)
                    self.blocks[cor['top']]['h'] = arr
                    # 'flip' is purely the post-split divergence lock here;
                    # once it expires the sector bias drives every choice
                    cor['dir'] = t
                    cor['flip'] -= 1
                    cor['top'] = pidx
                    cor['px'], cor['pz'] = nx, nz
                    cor['ho'] = arr
                    cor['y'] = u
                    cor['timer'] -= 1
                    cor['br']['blocks'].append(pidx)
                    stepped = True
                    break
                if not stepped:
                    attempts += 1
                    if attempts > 250:
                        return False
                    depth = min(2 + attempts // 3, 14)
                    if not rewind(cor, self.rng.randint(2, depth)):
                        cor['dir'] = -cor['dir']
                    cor['flip'] = self.rng.randint(1, FLIP_MAX)
        return True

    # ---- splice windows -----------------------------------------------------
    def scan_seq_windows(self, seq, dest):
        for i in range(len(seq) - WINDOW):
            w = seq[i:i + WINDOW + 1]
            bs = [self.blocks[j] for j in w]
            if any(b is None or b['h'] is None for b in bs):
                continue
            if any(b['prev2'] is not None for b in bs):
                continue
            # consecutive entries must really be parent->child (a chain
            # trimmed by erasures could otherwise fake adjacency)
            if any(b2['prev'] != a for a, b2 in zip(w, bs[1:])):
                continue
            # no fork inside the window (reserved decoys are kids too),
            # and no merge junction directly below it (the other arm
            # would be visible but absent from the replica)
            if any(len(self.kids.get(j, ())) > 1 for j in w[:-1]):
                continue
            if any(self.blocks[kk] is not None
                   and self.blocks[kk]['prev2'] is not None
                   for j in w for kk in self.kids.get(j, ())):
                continue
            turns = [hwrap(hn(b2['h']) - hn(b1['h']))
                     for b1, b2 in zip(bs, bs[1:])]
            if any(abs(t) != 1 for t in turns):
                continue
            # 'dw' is the window's ENTRY turn (the turn into its first
            # copied block): the alignment arc must end one turn short
            # of the first copy chord. Turns INSIDE the window may vary
            # freely - the replica is an exact translation either way
            dest.append({'blocks': w, 'y': bs[0]['y'], 'dw': turns[0]})

    def scan_windows(self):
        seqs = ([self.branches[0]['blocks']] + self.funnel_seqs
                + self.braid_seqs)
        for seq in seqs:
            self.scan_seq_windows(seq, self.windows)
        self.rng.shuffle(self.windows)

    def register_branch_windows(self, br):
        # a dead end that just spliced is final geometry: its fork-free
        # stretches become windows for LATER splices, so a teleport can
        # land the player on a corridor they have never ridden. Only SPLICED branches: their tail end is protected
        # from fix_leaves erasure, so a copied window can never be
        # chewed afterwards (merged branches drain into corridors that
        # may still be erased - excluded)
        chain = [i for i in br['blocks'] if self.blocks[i] is not None]
        self.scan_seq_windows(chain, self.windows)

    def bounces_since_fork(self, i, cap=FORK_GAP_MAX):
        # worst-case bounces since the last fork at block i - the
        # fork_gap_map value computed locally: DFS up the parent links,
        # stopping at forks (>= 2 live kids), capped at cap+1. Merges
        # branch the walk (both arrivals count); they are rare within
        # a cap-length window so the fan-out stays tiny
        best = 0
        stack = [(i, 0)]
        while stack:
            j, n = stack.pop()
            if n > cap:
                return cap + 1
            b = self.blocks[j]
            parents = [p for p in (b['prev'], b['prev2'])
                       if p is not None and self.blocks[p] is not None]
            if not parents:
                best = max(best, n)
                continue
            for p in parents:
                if sum(1 for k in self.kids.get(p, ())
                       if self.blocks[k] is not None) >= 2:
                    best = max(best, n + 1)
                else:
                    stack.append((p, n + 1))
        return best

    def ancestors_of(self, idx):
        # every block on any upstream route into idx: the union of
        # corridors the player COULD have ridden to get here
        seen = set()
        q = deque([idx])
        while q:
            i = q.popleft()
            b = self.blocks[i]
            if b is None:
                continue
            for p in (b['prev'], b['prev2']):
                if p is not None and p not in seen \
                        and self.blocks[p] is not None:
                    seen.add(p)
                    q.append(p)
        return seen

    # ---- decoration-tube geometry ------------------------------------------
    # the wall/dome/floor shell around a corridor stretch fills a tube
    # of radius ~6.5 and height ~20 around the centerline. Splice
    # stamping copies the window tube over the tail tube, so tubes of
    # different splices must never overlap (the copies would fight) -
    # except a window lying exactly on another splice's copied tail,
    # which is the sanctioned seamless chain.
    def tube_pts(self, idxs):
        pts = []
        bs = [self.blocks[i] for i in idxs
              if self.blocks[i] is not None
              and self.blocks[i]['px'] is not None]
        for a, b in zip(bs, bs[1:]):
            ln = math.hypot(b['px'] - a['px'], b['pz'] - a['pz'])
            steps = max(1, int(ln / 2))
            for s in range(steps + 1):
                t = s / steps
                pts.append((a['px'] + t * (b['px'] - a['px']),
                            a['pz'] + t * (b['pz'] - a['pz']),
                            a['y'] + t * (b['y'] - a['y'])))
        return pts

    @staticmethod
    def tube_box(pts):
        xs = [p[0] for p in pts]
        zs = [p[1] for p in pts]
        ys = [p[2] for p in pts]
        return (min(xs), max(xs), min(zs), max(zs), min(ys), max(ys))

    @staticmethod
    def tubes_clash(pa, boxa, pb, boxb):
        if (boxa[0] > boxb[1] + 13.5 or boxb[0] > boxa[1] + 13.5
                or boxa[2] > boxb[3] + 13.5 or boxb[2] > boxa[3] + 13.5
                or boxa[4] > boxb[5] + 20 or boxb[4] > boxa[5] + 20):
            return False
        for x1, z1, y1 in pa:
            for x2, z2, y2 in pb:
                if (abs(y1 - y2) < 20
                        and math.hypot(x1 - x2, z1 - z2) < 13.5):
                    return True
        return False

    def splice_tail(self, br, tip_idx=None):
        # extend the dead corridor with an alignment arc plus an exact
        # translated copy of an eligible window higher up, then record the
        # relative teleport that swaps the player onto the real corridor.
        # tip_idx lets the post-pass splice from any block of the corridor.
        if tip_idx is None:
            tip_idx = br['last']
        tip = self.blocks[tip_idx]
        if tip is None or tip['h'] is None or tip['px'] is None:
            return False
        tip_y = tip['y']
        # cheap screen: the tp delta is window minus alignment-arc end,
        # and the arc reaches at most ALIGN_MAX chords from the tip, so
        # windows beyond SPLICE_MAX_D + that reach can never pass the
        # exact cap below
        arc_reach = ALIGN_MAX * CHORD
        rise_cap = SPLICE_MAX_RISE
        cands = []
        for w in self.windows:
            if w['y'] < tip_y + MIN_RISE:
                continue
            if w['y'] > tip_y + rise_cap:
                continue          # rise only grows with arc depth
            wb0 = self.blocks[w['blocks'][0]]
            if wb0 is None:
                continue
            if max(abs(wb0['x'] - tip['x']),
                   abs(wb0['z'] - tip['z'])) > SPLICE_MAX_D + arc_reach:
                continue
            cands.append(w)
        self.rng.shuffle(cands)
        # destination mix: NOVEL_P of dead ends prefer windows OFF the
        # union of routes into this tip - the teleport drops the player
        # somewhere they have NOT already been. Within the preferred
        # class, windows on DOOMED branches come first (doom chains: the
        # teleport lands on another dead corridor, whose own dead end
        # splices again - a wrong turn cascades through several seamless
        # hops before touching live path; chains terminate because every
        # hop rises >= MIN_RISE). Doomed windows only enter self.windows
        # via register_branch_windows, i.e. after their branch spliced,
        # so they are erasure-safe. Last, prefer windows below the
        # funnel zone: high funnel stretches are scarce fork real
        # estate, and every window a splice consumes is fork-forbidden
        def doomed_win(w):
            # owning branch via a MIDDLE block: blocks[0] can be a
            # cross-branch parent, and 'br' has -1/-2 sentinels for
            # reserved/port blocks
            bid = self.blocks[w['blocks'][WINDOW // 2]]['br']
            return bid >= 0 and self.branches[bid]['doomed']
        anc = self.ancestors_of(tip_idx)
        tail_blocks = {c for sp in self.splices for c in sp['copy']}
        # cadence guard input: the player's bounces since their last
        # choice when they reach this tip. A window whose alignment
        # arc is |g| turns puts the first trigger d_tip + |g| + 1
        # bounces past that fork - the per-window check below never
        # lets that exceed FORK_GAP_MAX, so a splice is cadence-clean
        # BY CONSTRUCTION (the tail past the trigger is exempt, the
        # trigger itself is not). Tips too deep in a forkless run
        # simply cannot splice; the fix_leaves chew then walks them
        # upward, d_tip shrinking each step, until a position can
        d_tip = self.bounces_since_fork(tip_idx)
        novel_first = self.rng.random() < NOVEL_P
        cands.sort(key=lambda w: ((w['blocks'][0] in anc) == novel_first,
                                  not doomed_win(w),
                                  w['y'] > TRUNK_TOP))
        tried = 0
        budget = SPLICE_TRIES * (SPLICE_BOOST
                                 if getattr(self, 'splice_boost', False)
                                 else 1)
        for w in cands:
            if tried >= budget:
                break
            wbs = [self.blocks[j] for j in w['blocks']]
            # re-validate: the window may have gained a fork (funnel decoy
            # spawns) since it was scanned
            if any(b is None for b in wbs):
                continue
            if any(len([k for k in self.kids.get(j, ())
                        if self.blocks[k] is not None]) > 1
                   for j in w['blocks'][:-1]):
                continue
            # window-use cadence cap: a used window is fork-forbidden
            # over its 9 blocks, and adjacent used windows merge into
            # one forbidden stretch nothing can ever break. Reject a
            # use that would grow a contiguous forbidden run past
            # FORK_GAP_MAX - 4 (margin for repair forks at its ends).
            # Windows on replica tails are exempt (the sanctioned
            # chain: tails are already gap-exempt past their trigger)
            if w['blocks'][0] not in tail_blocks:
                up = 0
                j = wbs[0]['prev']
                while j is not None and self.blocks[j] is not None \
                        and j in self.win_used and up <= FORK_GAP_MAX:
                    up += 1
                    j = self.blocks[j]['prev']
                dn = 0
                j = w['blocks'][-1]
                while dn <= FORK_GAP_MAX:
                    ks = [k for k in self.kids.get(j, ())
                          if self.blocks[k] is not None]
                    if len(ks) != 1 or ks[0] not in self.win_used:
                        break
                    j = ks[0]
                    dn += 1
                if up + WINDOW + 1 + dn > FORK_GAP_MAX - 4:
                    self.rstats[self.sp_ctx + 'sp_contig'] += 1
                    continue
            g = hwrap(hn(wbs[1]['h']) - w['dw'] - hn(tip['h']))
            if abs(g) > ALIGN_MAX:
                self.rstats[self.sp_ctx + 'sp_align'] += 1
                continue
            if d_tip + abs(g) + 1 > FORK_GAP_MAX:
                self.rstats[self.sp_ctx + 'sp_guard'] += 1
                continue          # trigger would land past the cap
            depth = abs(g) + WINDOW
            if tip_y - depth < MORTAL_FLOOR:
                self.rstats[self.sp_ctx + 'sp_mortal'] += 1
                continue
            if w['y'] - (tip_y - depth) > rise_cap:
                continue          # exact rise incl. the alignment arc
            # the window tube must not overlap any existing tail tube -
            # its decoration would be overwritten by that stamp - unless
            # the window IS that tail's copy stretch (sanctioned chain)
            wpts = self.tube_pts(w['blocks'])
            wbox = self.tube_box(wpts)
            wset = set(w['blocks'][1:])
            if any(not wset <= tcopy
                   and self.tubes_clash(wpts, wbox, tpts, tbox)
                   for tpts, tbox, tcopy in self.tail_tubes):
                self.rstats[self.sp_ctx + 'sp_wintube'] += 1
                continue
            tried += 1
            placed = []
            px, pz, h, y, last = (tip['px'], tip['pz'], tip['h'],
                                  tip_y, tip_idx)
            ok = True
            d_al = 1 if g > 0 else -1
            for _ in range(abs(g)):
                h += d_al * TURN
                px += CHORD * math.cos(h)
                pz += CHORD * math.sin(h)
                bx, bz = rnd(px), rnd(pz)
                y -= 1
                if (math.hypot(px - START_X, pz - START_Z) > max_r(y)
                        or not self.clear(bx, bz, y, last)):
                    self.rstats[self.sp_ctx + 'sp_arc_blocked'] += 1
                    ok = False
                    break
                last = self.place(bx, y, bz, last, br['id'], f=(px, pz, h))
                placed.append(last)
            if ok:
                t0 = self.blocks[last]
                dx = t0['x'] - wbs[0]['x']
                dz = t0['z'] - wbs[0]['z']
                dy = t0['y'] - wbs[0]['y']
                # the seamless tp delta is exactly (-dx, -dy, -dz): cap
                # its horizontal reach at SPLICE_MAX_D (8 chunks) so the
                # destination is always inside loaded chunks
                if max(abs(dx), abs(dz)) > SPLICE_MAX_D:
                    self.rstats[self.sp_ctx + 'sp_tpfar'] += 1
                    ok = False
                # and the decoration tubes (shell radius ~6.5, height
                # ~20) of tail and window must not overlap, or the
                # walls/dome/floor around the tail can never be made
                # identical to the window's - require clear horizontal
                # OR vertical separation
                elif max(abs(dx), abs(dz)) < 14 and abs(dy) < 20:
                    self.rstats[self.sp_ctx + 'sp_tubesep'] += 1
                    ok = False
            if ok:
                for wi in wbs[1:]:
                    cx, cy, cz = wi['x'] + dx, wi['y'] + dy, wi['z'] + dz
                    if not self.clear(cx, cz, cy, last):
                        self.rstats[self.sp_ctx + 'sp_copy_blocked'] += 1
                        ok = False
                        break
                    fx = (wi['px'] + dx) if wi['px'] is not None else None
                    fz = (wi['pz'] + dz) if wi['pz'] is not None else None
                    last = self.place(cx, cy, cz, last, br['id'],
                                      f=(fx, fz, wi['h']))
                    placed.append(last)
            if ok:
                # the new tail tube must not overlap any existing tail
                # or window tube - stamps must never fight over blocks
                t0i = (placed[-WINDOW - 1] if len(placed) > WINDOW
                       else tip_idx)
                cpts = self.tube_pts([t0i] + placed[-WINDOW:])
                cbox = self.tube_box(cpts)
                if any(self.tubes_clash(cpts, cbox, tpts, tbox)
                       for tpts, tbox, _ in self.tail_tubes) \
                        or any(self.tubes_clash(cpts, cbox, opts, obox)
                               for opts, obox in self.win_tubes):
                    self.rstats[self.sp_ctx + 'sp_tailtube'] += 1
                    ok = False
            if ok:
                br['blocks'].extend(placed)
                br['last'] = last
                copy = placed[-WINDOW:]
                self.tail_tubes.append(
                    (cpts, cbox, set(copy) | {t0i}))
                self.win_tubes.append((wpts, wbox))
                c1 = self.blocks[copy[0]]
                w1 = self.blocks[w['blocks'][1]]
                self.splices.append({
                    'branch': br['id'],
                    'delta': (w1['x'] - c1['x'], w1['y'] - c1['y'],
                              w1['z'] - c1['z']),
                    'w0': w['blocks'][0],
                    'novel': w['blocks'][0] not in anc,
                    'doomed_dest': doomed_win(w),
                    'copy': copy, 'win': list(w['blocks'])})
                self.win_used.update(w['blocks'])
                # the copied stretch is itself a perfect window (same
                # turns, fork-free): later dead ends may splice onto it
                # and the teleports chain seamlessly - every hop rises
                # by at least MIN_RISE, so chains always terminate
                t0_idx = (placed[-WINDOW - 1] if len(placed) > WINDOW
                          else tip_idx)
                self.windows.append({'blocks': [t0_idx] + copy,
                                     'y': self.blocks[t0_idx]['y'],
                                     'dw': w['dw']})
                # the whole branch is final now: its own stretches
                # become windows, so later dead ends can teleport onto
                # corridors the player has never ridden
                self.register_branch_windows(br)
                self.rstats[self.sp_ctx + 'sp_ok'] += 1
                return True
            for i in reversed(placed):
                self.pop_block(i)
        return False

    def splice_landing(self, br, tip_idx=None):
        # LANDING splice (user-designed): when no existing window fits
        # the dying arm, keep the seamless-teleport rule by BUILDING
        # the destination instead of finding one. The arm grows a
        # natural fork-free 8-bounce tail (no alignment arc - the
        # landing is made to match the tail, not the other way round),
        # and an exact integer-translated copy of [t0 + tail] is
        # erected elsewhere as a LANDING BRANCH: a corridor that
        # starts in mid-air (unreachable from above - the player can
        # only ever be teleported onto it, so it is new territory by
        # construction) and, after the copied stretch, runs a short
        # connector that merges onto a STABLE real corridor with the
        # standard inverted-fork junction shape. The translation delta
        # is a free variable, which turns the junction landing from a
        # near-impossible random-walk arrival into an exact solve:
        # every connector turn-sequence yields the delta that lands it
        # perfectly. Cadence: the landing root counts as a path start
        # (d=0), the ride to the junction is 8 + m + 1 <= 17 bounces,
        # and the tail trigger sits d_tip + 1 past the arm last fork.
        if tip_idx is None:
            tip_idx = br['last']
        tip = self.blocks[tip_idx]
        if tip is None or tip['h'] is None or tip['px'] is None:
            return False
        if self.bounces_since_fork(tip_idx) + 1 > FORK_GAP_MAX:
            return False
        # sync the branch cursor to the tip (chews call from any block)
        br['px'], br['pz'], br['h'] = tip['px'], tip['pz'], tip['h']
        br['y'] = tip['y']
        br['last'] = tip_idx
        if br['dir'] not in (-1, 1):
            br['dir'] = self.rng.choice((-1, 1))
        orig = list(br['blocks'])

        def rollback():
            keep = 0
            lim = min(len(orig), len(br['blocks']))
            while keep < lim and orig[keep] == br['blocks'][keep]:
                keep += 1
            for i in br['blocks'][keep:]:
                if self.blocks[i] is not None:
                    self.erase_block(i)
            del br['blocks'][keep:]

        # natural fork-free tail: 8 bounces of the arm's own curvature
        target = len(br['blocks']) + WINDOW
        while len(br['blocks']) < target:
            if br['y'] - 1 < MORTAL_FLOOR + 1:
                rollback()
                return False
            if self.step(br) is None \
                    and self.rewind_retry(br) is None:
                rollback()
                return False
        S = br['blocks'][-(WINDOW + 1):]
        if len(S) < WINDOW + 1 \
                or any(self.blocks[i] is None
                       or self.blocks[i]['h'] is None
                       or self.blocks[i]['px'] is None for i in S):
            rollback()
            return False
        t0i, copy = S[0], S[1:]
        if self.bounces_since_fork(t0i) + 1 > FORK_GAP_MAX:
            rollback()
            return False
        sb = [self.blocks[i] for i in S]
        c7 = sb[-1]
        h_end = c7['h']
        cpts = self.tube_pts(S)
        cbox = self.tube_box(cpts)
        # the new tail tube must not fight any existing stamp tube
        if any(self.tubes_clash(cpts, cbox, tpts, tbox)
               for tpts, tbox, _ in self.tail_tubes) \
                or any(self.tubes_clash(cpts, cbox, opts, obox)
                       for opts, obox in self.win_tubes):
            rollback()
            self.rstats['ld_tailtube'] += 1
            return False
        tails = {c for sp in self.splices for c in sp['copy']}

        def stable(bid):
            # the landing merges INTO this corridor: it must never be
            # chewed later, or the junction (and with it the window
            # the tail mirrors) would dangle
            if not (isinstance(bid, int)
                    and 0 <= bid < len(self.branches)):
                return False
            b2 = self.branches[bid]
            return (b2['golden'] or b2['funnel'] or b2.get('braid')
                    or b2.get('landing') or b2['spliced']) \
                and not b2['alive']

        ms = list(range(3, 9))
        self.rng.shuffle(ms)
        for m in ms:
            ylo = c7['y'] - 1 - m + MIN_RISE
            yhi = c7['y'] - 1 - m + SPLICE_MAX_RISE
            rows = []
            for yy in range(ylo, yhi + 1):
                rows.extend(self.by_y.get(yy, ()))
            self.rng.shuffle(rows)
            tried_j = 0
            for J in rows:
                if tried_j >= 40:
                    break
                jb = self.blocks[J]
                if jb is None or jb['h'] is None or jb['px'] is None \
                        or jb['prev2'] is not None:
                    continue
                if J in self.win_used or J in tails \
                        or not stable(jb['br']):
                    continue
                kids = [k for k in self.kids.get(J, ())
                        if self.blocks[k] is not None]
                if len(kids) != 1 or kids[0] in self.win_used \
                        or self.is_multi(kids[0]):
                    continue
                kb = self.blocks[kids[0]]
                if kb['h'] is None or kb['prev2'] is not None:
                    continue
                pv = jb['prev']
                if pv is not None and (self.blocks[pv] is None
                                       or self.is_multi(pv)
                                       or pv in self.win_used):
                    continue
                t = hwrap(hn(kb['h']) - hn(jb['h']))
                if abs(t) != 1:
                    continue
                tried_j += 1
                arr2 = jb['h'] + 2 * t * TURN
                sx = jb['px'] - CHORD * math.cos(arr2)
                sz = jb['pz'] - CHORD * math.sin(arr2)
                dy = (jb['y'] + 1 + m) - c7['y']
                seqs = []
                for fin_off in (-1, 1):
                    gap = hwrap(hn(arr2) + fin_off - hn(h_end))
                    seqs.extend(turn_seqs(m, gap))
                self.rng.shuffle(seqs)
                for seq in seqs[:24]:
                    offx = offz = 0.0
                    h = h_end
                    pts = []
                    for tt in seq:
                        h += tt * TURN
                        offx += CHORD * math.cos(h)
                        offz += CHORD * math.sin(h)
                        pts.append((offx, offz, h))
                    dx = rnd((sx - offx) - c7['px'])
                    dz = rnd((sz - offz) - c7['pz'])
                    if max(abs(dx), abs(dz)) > SPLICE_MAX_D:
                        continue
                    if max(abs(dx), abs(dz)) < 14 and abs(dy) < 20:
                        continue      # decoration tube separation
                    if math.hypot(c7['px'] + dx + offx - sx,
                                  c7['pz'] + dz + offz - sz) \
                            > MERGE_TOL:
                        continue      # integer rounding broke arrival
                    wpts = [(x + dx, z + dz, y + dy)
                            for x, z, y in cpts]
                    wbox = self.tube_box(wpts)
                    if any(self.tubes_clash(wpts, wbox, tpts, tbox)
                           for tpts, tbox, _ in self.tail_tubes):
                        continue
                    # place the 9 landing blocks (exact translation)
                    placed = []
                    last = None
                    ok = True
                    for bsrc in sb:
                        lx, ly, lz = (bsrc['x'] + dx, bsrc['y'] + dy,
                                      bsrc['z'] + dz)
                        if (math.hypot(bsrc['px'] + dx - START_X,
                                       bsrc['pz'] + dz - START_Z)
                                > max_r(ly)
                                or not self.clear(lx, lz, ly, last)):
                            ok = False
                            break
                        last = self.place(lx, ly, lz, last, -3,
                                          f=(bsrc['px'] + dx,
                                             bsrc['pz'] + dz,
                                             bsrc['h']))
                        placed.append(last)
                    if ok:
                        # connector down onto the junction slot
                        for si, (ox, oz, hh) in enumerate(pts):
                            fx = c7['px'] + dx + ox
                            fz = c7['pz'] + dz + oz
                            yy = c7['y'] + dy - si - 1
                            if (math.hypot(fx - START_X, fz - START_Z)
                                    > max_r(yy)
                                    or not self.clear(
                                        rnd(fx), rnd(fz), yy, last,
                                        extra=[(J, m - si)])):
                                ok = False
                                break
                            last = self.place(rnd(fx), yy, rnd(fz),
                                              last, -3, f=(fx, fz, hh))
                            placed.append(last)
                    if not ok:
                        for i in reversed(placed):
                            self.pop_block(i)
                        continue
                    # commit: the landing is its own (unreachable)
                    # branch; the junction ties it into the maze
                    lastb = self.blocks[last]
                    lb = self.new_branch(lastb['px'], lastb['pz'],
                                         lastb['h'], t, lastb['y'],
                                         last)
                    lb['alive'] = False
                    lb['landing'] = True
                    lb['merged'] = True
                    lb['blocks'] = list(placed)
                    for i in placed:
                        self.blocks[i]['br'] = lb['id']
                    self.set_prev(J, last)
                    jb['h2'] = arr2
                    win = placed[:WINDOW + 1]
                    self.tail_tubes.append((cpts, cbox,
                                            set(copy) | {t0i}))
                    self.win_tubes.append((wpts, wbox))
                    self.splices.append({
                        'branch': br['id'],
                        'delta': (dx, dy, dz),
                        'w0': win[0],
                        'novel': True,
                        'doomed_dest': False,
                        'copy': list(copy), 'win': list(win)})
                    self.win_used.update(win)
                    br['last'] = copy[-1]
                    # the tail is a chain window; the landing corridor
                    # itself offers fresh never-visited windows too
                    self.windows.append({'blocks': [t0i] + list(copy),
                                         'y': self.blocks[t0i]['y'],
                                         'dw': hwrap(
                                             hn(sb[1]['h'])
                                             - hn(sb[0]['h']))})
                    self.register_branch_windows(br)
                    self.scan_seq_windows(lb['blocks'], self.windows)
                    self.rstats['ld_ok'] += 1
                    return True
        rollback()
        self.rstats['ld_nofit'] += 1
        return False

    # ---- doomed pair-merges -------------------------------------------------
    def try_merge(self, d1, d2):
        # converging corridors approach a junction almost in parallel
        # (arrivals sit +-22.5 deg around one continuation), so only
        # heading-similar pairs are viable. d1 wanders on naturally and a
        # junction is attempted at every depth in the merge band.
        dh = hwrap(hn(d1['h']) - hn(d2['h']))
        if abs(dh) > 3:
            return False
        before = len(d1['blocks'])
        result = False
        k = 0
        while k < MERGE_K_MAX:
            if (d1['life'] <= k + 9 or d2['life'] <= k + 9
                    or d1['y'] - (k + 2) <= WANDER_FLOOR):
                break
            if self.step(d1) is None:
                break
            k += 1
            if k < MERGE_K_MIN:
                continue
            if self.attempt_junction(d1, d2, k):
                result = True
                break
        done = len(d1['blocks']) - before
        d1['skip'] = done
        d1['fork'] -= done      # the walked bounces are ridden corridor
                                # and must count toward the fork cadence,
                                # or a failed merge walk could stretch a
                                # forkless run past FORK_GAP_MAX
        if not result:
            d1['life'] -= done
        return result

    def attempt_junction(self, d1, d2, k):
        J = d1['last']
        jb = self.blocks[J]
        arr_a = jb['h']
        m = k - 1
        # cadence guard: d2's connector walks m fork-free bounces into
        # the junction - the arriving count must stay within the cap
        if self.bounces_since_fork(d2['last']) + m + 1 > FORK_GAP_MAX:
            return False
        for t in (d1['dir'], -d1['dir']):
            arr_b = arr_a + 2 * t * TURN
            tgt_x = jb['px'] - CHORD * math.cos(arr_b)
            tgt_z = jb['pz'] - CHORD * math.sin(arr_b)
            if (math.hypot(d2['px'] - tgt_x, d2['pz'] - tgt_z)
                    > CHORD * m * 0.95):
                continue
            cands = []
            for fin_off in (-1, 1):
                gap = hwrap(hn(arr_b) + fin_off - hn(d2['h']))
                for seq in turn_seqs(m, gap):
                    px, pz, h = d2['px'], d2['pz'], d2['h']
                    pts = []
                    for t2 in seq:
                        h += t2 * TURN
                        px += CHORD * math.cos(h)
                        pz += CHORD * math.sin(h)
                        pts.append((px, pz, h))
                    err = math.hypot(px - tgt_x, pz - tgt_z)
                    if err <= MERGE_TOL:
                        cands.append((err, pts))
            if not cands:
                continue
            cands.sort(key=lambda c: c[0])
            # commit d1's continuation with this turn direction
            if self.step(d1, forced=t) is None:
                return False
            for err, pts in cands[:10]:
                placed = []
                last = d2['last']
                ok = True
                for si, (px, pz, h) in enumerate(pts):
                    bx, bz = rnd(px), rnd(pz)
                    yy = d2['y'] - si - 1
                    if (math.hypot(px - START_X, pz - START_Z)
                            > max_r(yy)
                            or not self.clear(bx, bz, yy, last,
                                              extra=[(J, m - si)])):
                        ok = False
                        break
                    last = self.place(bx, yy, bz, last, d2['id'],
                                      f=(px, pz, h))
                    placed.append(last)
                if ok:
                    self.set_prev(J, placed[-1] if placed else d2['last'])
                    jb['h2'] = arr_b
                    d2['blocks'].extend(placed)
                    d2['last'] = placed[-1] if placed else d2['last']
                    d2['alive'] = False
                    d2['merged'] = True
                    d1['life'] = max(d1['life'] - (k + 1),
                                     d2['life'] - k, 6)
                    self.merges += 1
                    return True
                for i in reversed(placed):
                    self.pop_block(i)
            return False
        return False

    # ---- phase 2: decoys, merges, splices ----------------------------------
    def run_decoys(self):
        pending = sorted(self.reserved, key=lambda r: -r['y'])
        pi = 0
        # fork spawners along the static corridors: the funnel corridors
        # and the braid arms (both are winning routes and need their own
        # wrong choices)
        fspawn = [{'seq': seq,
                   'by_y': {self.blocks[i]['y']: n
                            for n, i in enumerate(seq)},
                   'timer': self.rng.randint(FORK_MIN, FORK_MAX)}
                  for seq in self.funnel_seqs + self.braid_seqs]

        for y in range(START_Y - 1, BOTTOM_Y - 1, -1):
            cohort = sorted([b for b in self.branches if b['alive']],
                            key=lambda b: len(b['blocks'])
                            if len(b['blocks']) < MIN_STUB else 999)
            for br in cohort:
                if br['skip'] > 0:
                    br['skip'] -= 1
                    continue
                if br['pending'] is not None:
                    pd = br['pending']
                    br['pending'] = None
                    self.blocks[pd['idx']]['br'] = br['id']
                    br['px'], br['pz'], br['h'] = pd['px'], pd['pz'], pd['h']
                    br['y'] -= 1
                    br['flip'] -= 1
                    br['last'] = pd['idx']
                    br['blocks'].append(pd['idx'])
                    if br['doomed']:
                        br['life'] -= 1
                    continue
                if br['doomed']:
                    # in the final stretch, look for a splice window every
                    # level - far more chances than a single death attempt
                    if br['life'] <= SPLICE_BAND and self.splice_tail(br):
                        br['spliced'] = True
                        br['alive'] = False
                        continue
                    if br['life'] <= 0 or br['y'] - 1 < WANDER_FLOOR:
                        self.end_branch(br)
                        continue
                    br['life'] -= 1
                    do_fork = (br['fork'] <= 1 and br['y'] - 1 > FORK_FLOOR
                               and br['life'] >= MIN_STUB)
                    br['fork'] -= 1
                    pre = (br['px'], br['pz'], br['h'], br['y'], br['last'])
                    d = self.step(br)
                    if d is None:
                        d = self.rewind_retry(br)
                        if d is not None:
                            do_fork = False   # pre-state is stale
                    if d is None:
                        self.end_branch(br)
                        continue
                    if do_fork:
                        child = self.new_branch(pre[0], pre[1], pre[2], -d,
                                                pre[3], pre[4])
                        child['flip'] = max(child['flip'], FORK_TURN_LOCK)
                        child['doomed'] = True
                        child['life'] = br['life']
                        if self.step(child, forced=-d) is None:
                            self.branches.pop()
                            br['fork'] = 1
                        else:
                            br['fork'] = self.rng.randint(FORK_MIN, FORK_MAX)
                            br['flip'] = max(br['flip'], FORK_TURN_LOCK)
                            br['forked'] = True
                            br['lfl'] = len(br['blocks']) - 1
                            self.forks.append({
                                'br': br['id'], 'decoy': child['id'],
                                'parent_idx': pre[4], 'cont_idx': br['last'],
                                'decoy_idx': child['last'], 'y': pre[3],
                                'golden': False})
                    continue
                if br['y'] - 1 < WANDER_FLOOR:
                    self.end_branch(br)
                    continue
                do_fork = br['fork'] <= 1 and br['y'] - 1 > FORK_FLOOR
                br['fork'] -= 1
                pre = (br['px'], br['pz'], br['h'], br['y'], br['last'])
                d = self.step(br)
                if d is None:
                    d = self.rewind_retry(br)
                    if d is not None:
                        do_fork = False   # pre-state is stale
                if d is None:
                    self.end_branch(br)
                    continue
                if do_fork:
                    child = self.new_branch(pre[0], pre[1], pre[2], -d,
                                            pre[3], pre[4])
                    child['flip'] = max(child['flip'], FORK_TURN_LOCK)
                    if self.step(child, forced=-d) is None:
                        self.branches.pop()
                        br['fork'] = 1
                    else:
                        br['fork'] = self.rng.randint(FORK_MIN, FORK_MAX)
                        br['flip'] = max(br['flip'], FORK_TURN_LOCK)
                        br['forked'] = True
                        br['lfl'] = len(br['blocks']) - 1
                        self.forks.append({
                            'br': br['id'], 'decoy': child['id'],
                            'parent_idx': pre[4], 'cont_idx': br['last'],
                            'decoy_idx': child['last'], 'y': pre[3],
                            'golden': False})

            # decoy forks off the static funnel corridors
            for fs in fspawn:
                fs['timer'] -= 1
                if fs['timer'] > 0:
                    continue
                n = fs['by_y'].get(y + 1)
                if n is None or n + 1 >= len(fs['seq']):
                    continue
                B = fs['seq'][n]
                bb = self.blocks[B]
                if bb is None or bb['h'] is None or bb['px'] is None \
                        or bb['prev2'] is not None:
                    self.fstats['junction'] += 1
                    fs['timer'] = 1
                    continue
                if B in self.win_used:
                    self.fstats['window'] += 1
                    fs['timer'] = 1
                    continue
                if len(self.kids.get(B, ())) > 1:
                    self.fstats['taken'] += 1
                    fs['timer'] = 1
                    continue
                kid = self.blocks[fs['seq'][n + 1]]
                if kid is None or kid['h'] is None:
                    fs['timer'] = 1
                    continue
                t_used = hn(kid['h']) - hn(bb['h'])
                if abs(t_used) != 1:
                    self.fstats['turn'] += 1
                    fs['timer'] = 1
                    continue
                hd = bb['h'] - t_used * TURN
                nx = bb['px'] + CHORD * math.cos(hd)
                nz = bb['pz'] + CHORD * math.sin(hd)
                bx, bz = rnd(nx), rnd(nz)
                if (math.hypot(nx - START_X, nz - START_Z) <= max_r(y)
                        and self.clear(bx, bz, y, B)):
                    child = self.new_branch(bb['px'], bb['pz'], hd,
                                            -t_used, y + 1, B)
                    child['flip'] = max(child['flip'], FORK_TURN_LOCK)
                    c1 = self.place(bx, y, bz, B, child['id'],
                                    f=(nx, nz, hd))
                    child['px'], child['pz'] = nx, nz
                    child['y'] = y
                    child['last'] = c1
                    child['blocks'].append(c1)
                    self.forks.append({
                        'br': self.blocks[B]['br'], 'decoy': child['id'],
                        'parent_idx': B, 'cont_idx': fs['seq'][n + 1],
                        'decoy_idx': c1, 'y': y + 1, 'golden': False})
                    self.fstats['ok'] += 1
                    fs['timer'] = self.rng.randint(FORK_MIN, FORK_MAX)
                else:
                    self.fstats['blocked'] += 1
                    fs['timer'] = 1

            # activate golden-reserved decoys at this level
            while pi < len(pending) and pending[pi]['y'] == y:
                r = pending[pi]
                pi += 1
                child = self.new_branch(r['px1'], r['pz1'], r['h1'],
                                        r['dir'], r['y'], r['c1'])
                child['flip'] = max(child['flip'], FORK_TURN_LOCK - 1)
                child['blocks'].append(r['c1'])
                self.blocks[r['c1']]['br'] = child['id']
                child['pending'] = {'idx': r['c2'], 'px': r['px2'],
                                    'pz': r['pz2'], 'h': r['h2']}
                self.forks.append({
                    'br': self.blocks[r['parent_idx']]['br'],
                    'decoy': child['id'],
                    'parent_idx': r['parent_idx'], 'cont_idx': r['cont_idx'],
                    'decoy_idx': r['c1'], 'y': r['py'],
                    'golden': r.get('golden', True)})

            # pruning to the width curve
            live = [b for b in self.branches if b['alive']]
            nd = [b for b in live if not b['doomed']]
            self.peak_width = max(self.peak_width, len(nd) + 1)
            over = (len(nd) + 1) - target_width(y)
            while over > 0 and nd:
                self.doom(nd.pop(self.rng.randrange(len(nd))))
                over -= 1
            if y == DOOM_ALL_AT:
                for b in nd:
                    self.doom(b)

            # doomed pair-merges
            if TRUNK_TOP - 5 > y > WANDER_FLOOR + 20:
                pool = [b for b in self.branches
                        if b['alive'] and b['doomed'] and b['skip'] == 0
                        and b['pending'] is None and b['life'] >= 12]
                self.rng.shuffle(pool)
                tries = 0
                while len(pool) >= 2 and tries < MERGE_PER_LEVEL:
                    a = pool.pop()
                    mate = None
                    for b in pool:
                        if (max(abs(a['px'] - b['px']),
                                abs(a['pz'] - b['pz'])) <= MERGE_RANGE):
                            mate = b
                            break
                    if mate is None:
                        continue
                    pool.remove(mate)
                    tries += 1
                    if self.rng.random() < MERGE_PROB:
                        self.try_merge(a, mate)

            # interleaved fork-cadence repair (see enforce_fork_gaps):
            # a violation above the sweep can never heal on its own,
            # and the per-death chew means holes surface within an
            # arm-length of the sweep. Repair EVERY level: each level
            # of delay is one more built level the repair arm must
            # cross before it reaches open space, and arms that have
            # to cross the busy sweep band are exactly the ones that
            # die. min_y skips the top few levels still being worked
            if y < START_Y - 8:
                self.enforce_fork_gaps(min_y=y + 3, passes=1)

        # anything still alive at the bottom of the sweep ends now
        for br in self.branches:
            if br['alive'] and not br['golden'] and not br['funnel']:
                self.end_branch(br)

    def grow_funnel(self, ridx, rx, rz, ho, theta, y0, quota, tries):
        # build_funnel with rollback-and-retry: on failure, erase just
        # this funnel's debris and reset the root block
        spread = math.tau * (0.45 if ridx == 0 else 0.38)
        for _retry in range(tries):
            n_b, n_br = len(self.blocks), len(self.branches)
            n_t = len(self.entry_tips)
            if self.build_funnel(ridx, rx, rz, ho, y0, quota, theta,
                                 spread):
                return True
            for i in range(len(self.blocks) - 1, n_b - 1, -1):
                if self.blocks[i] is not None:
                    self.erase_block(i)
            del self.blocks[n_b:]
            del self.branches[n_br:]
            del self.entry_tips[n_t:]
            rb = self.blocks[ridx]
            rb['h'] = rb['h2'] = None
            rb['prev'] = rb['prev2'] = None
            if ridx != 0:
                rb['br'] = -2
        return False

    def run(self):
        if self.build_golden() is None:
            self.fail = 'golden trunk (backtrack budget)'
            return False
        quotas = [ENTRIES // FUNNELS + (1 if k < ENTRIES % FUNNELS else 0)
                  for k in range(FUNNELS)]
        # funnels grow ONE AT A TIME, each to completion: later funnels
        # route around the finished earlier trees, and when one jams
        # only THAT funnel rolls back and re-rolls with fresh
        # randomness. Funnels 1.. root at ports; a port whose funnel
        # cannot climb out is unmade and re-rolled at another depth
        self.ports = []
        used = []
        for k in range(FUNNELS):
            if k == 0:
                grown = self.grow_funnel(0, float(START_X),
                                         float(START_Z), H0,
                                         H0 + math.pi, TRUNK_TOP,
                                         quotas[0], 10)
            else:
                grown = False
                for _p in range(8):
                    port = self.make_port(used)
                    if port is None:
                        break
                    slot, sx, sz, arr2, ak, y0 = port[:6]
                    if self.grow_funnel(slot, sx, sz, arr2, ak, y0,
                                        quotas[k], 6):
                        self.ports.append(port)
                        used.append(port[6])
                        grown = True
                        break
                    self.unmake_port(port)
            if not grown:
                self.fail = 'funnel %d could not grow' % k
                return False
        if len(self.entry_tips) != ENTRIES:
            self.fail = 'entry tips %d != %d' % (len(self.entry_tips),
                                                 ENTRIES)
            return False
        for br in self.branches:
            if br['funnel'] and br['blocks']:
                br['blocks'].reverse()
                self.funnel_seqs.append(br['blocks'])
        self.build_braids()
        # build-time cadence stubs (reserve_along) on every static
        # junction-free stretch: funnel corridors (incl. port climbs)
        # and braid arms. Placed after the braids so the braid steering
        # never has to dodge stub bubbles; before scan_windows so
        # stub-forked blocks are never scanned as fork-free windows
        for seq in self.funnel_seqs:
            self.reserve_along(seq[1:-1])
        for seq in self.braid_seqs:
            self.reserve_along(seq[3:-3])
        self.scan_windows()

        def viol_now():
            d = self.fork_gap_map()
            ex = self.fork_gap_exempt()
            return sum(1 for i, v in d.items()
                       if v > FORK_GAP_MAX and i not in ex)

        # skeleton pre-pass: the static maze (trunk + funnels + stubs
        # + braids) is final geometry and the world is at its thinnest
        # it will ever be - repair any cadence hole the stub
        # reservations could not cover NOW, while repair arms can
        # still splice freely
        self.enforce_fork_gaps(passes=6)
        self.run_decoys()
        self.gap_stages = {'sweep': viol_now()}
        self.fix_leaves()
        self.gap_stages['fix_leaves'] = viol_now()
        self.enforce_fork_gaps()
        self.gap_stages['final'] = viol_now()
        return True

    def stats(self):
        blks = [b for b in self.blocks if b is not None]
        dead_ends = [b for b in self.branches
                     if not b['golden'] and not b['funnel'] and b['blocks']]
        gys = sorted([f['y'] for f in self.forks if f['golden']],
                     reverse=True)
        gaps = ([TRUNK_TOP - gys[0]] +
                [a - b for a, b in zip(gys, gys[1:])]) if gys else [999]
        xs = [b['x'] for b in blks]
        zs = [b['z'] for b in blks]
        # fork cadence: worst-case bounces without a fork over every
        # traversable route (tail past the first trigger exempt), and
        # the average gap measured at every reset point (forks, first
        # splice triggers, the finish)
        d = self.fork_gap_map()
        ex = self.fork_gap_exempt()
        nforks = sum(1 for i in d if self.live_fork(i))
        resets = [v for i, v in d.items() if self.live_fork(i)]
        resets += [d[sp['copy'][0]] for sp in self.splices
                   if self.blocks[sp['copy'][0]] is not None]
        resets += [v for i, v in d.items()
                   if self.blocks[i]['y'] == BOTTOM_Y]
        enforced = [v for i, v in d.items() if i not in ex]
        return {'blocks': len(blks), 'forks': len(self.forks),
                'landings': sum(1 for b2 in self.branches
                                if b2.get('landing')),
                'forkgap_max': max(enforced) if enforced else 0,
                'forkgap_viol': sum(1 for v in enforced
                                    if v > FORK_GAP_MAX),
                'forkgap_mean': (sum(resets) / float(len(resets))
                                 if resets else 0.0),
                'blocks_per_fork': len(blks) / float(max(1, nforks)),
                'fork_blocks': nforks,
                'golden_forks': len(gys), 'dead_ends': len(dead_ends),
                'peak_width': self.peak_width,
                'gap_mean': sum(gaps) / len(gaps), 'gap_max': max(gaps),
                'splices': len(self.splices), 'unspliced': self.unspliced,
                'merges': self.merges, 'windows': len(self.windows),
                'entries': len(self.entry_tips),
                'braids': len(self.braid_list),
                'novel_splices': sum(1 for sp in self.splices
                                     if sp.get('novel')),
                'doom_chains': sum(1 for sp in self.splices
                                   if sp.get('doomed_dest')),
                'bbox': (min(xs), max(xs), min(zs), max(zs))}


# ---- independent verification -------------------------------------------
def verify(sim):
    errs = []
    blks = sim.blocks
    live = [i for i in range(len(blks)) if blks[i] is not None]

    coords = {}
    for i in live:
        b = blks[i]
        key = (b['x'], b['y'], b['z'])
        if key in coords:
            errs.append('duplicate block at %s' % (key,))
        coords[key] = i

    bottom = [i for i in live if blks[i]['y'] == BOTTOM_Y]
    if len(bottom) != 1:
        errs.append('expected exactly 1 block at y=%d, found %d'
                    % (BOTTOM_Y, len(bottom)))
    for i in live:
        if blks[i]['y'] < MORTAL_FLOOR and blks[i]['br'] != 0:
            errs.append('non-golden block below mortal floor at y=%d'
                        % blks[i]['y'])

    for i in live:
        b = blks[i]
        for p in (b['prev'], b['prev2']):
            if p is None:
                continue
            pb = blks[p]
            if pb is None:
                errs.append('parent of %d erased' % i)
                continue
            if b['y'] != pb['y'] - 1:
                errs.append('y step != -1 at block %d' % i)
            c = math.hypot(b['x'] - pb['x'], b['z'] - pb['z'])
            if not (5.0 <= c <= 7.6):
                errs.append('chord %.2f out of range at block %d (y=%d)'
                            % (c, i, b['y']))

    # separation
    for i in live:
        b = blks[i]
        for dy in range(0, SEP_DY + 1):
            for j in sim.by_y.get(b['y'] - dy, []):
                if j >= i or blks[j] is None:
                    continue
                o = blks[j]
                dist = max(abs(o['x'] - b['x']), abs(o['z'] - b['z']))
                if dist < SEP_CHEB:
                    if sim.kin_ok({i: (0, False)}, j, MAX_KIN, JUNC_KIN,
                                  cheb=dist):
                        continue
                    errs.append('separation %d < %.1f between blocks %d,%d '
                                '(y %d,%d)' % (dist, SEP_CHEB, i, j,
                                               b['y'], o['y']))

    # fork cadence: no traversable stretch runs more than FORK_GAP_MAX
    # bounces without a fork (>= 2 live kids; merges are not choices).
    # The replica tail past the FIRST trigger of each splice is exempt
    # (the trigger ground script teleports the player away). Computed
    # independently of sim.fork_gap_map: descending y is topo order
    exempt = set()
    for sp in sim.splices:
        exempt.update(sp['copy'][1:])
    gapd = {}
    for i in sorted(live, key=lambda j: -blks[j]['y']):
        best = 0
        for p in (blks[i]['prev'], blks[i]['prev2']):
            if p is None or blks[p] is None:
                continue
            pk = sum(1 for k in sim.kids.get(p, ())
                     if blks[k] is not None)
            best = max(best, 1 if pk >= 2 else gapd.get(p, 0) + 1)
        gapd[i] = best
        if best > FORK_GAP_MAX and i not in exempt:
            errs.append('fork gap %d > %d at block %d (%d,%d,%d)'
                        % (best, FORK_GAP_MAX, i, blks[i]['x'],
                           blks[i]['y'], blks[i]['z']))

    # no visible dead ends: every leaf is the finish or a splice-tail end
    tail_ends = {sp['copy'][-1] for sp in sim.splices}
    for i in live:
        kids_live = [k for k in sim.kids.get(i, ())
                     if blks[k] is not None]
        if kids_live:
            continue
        if blks[i]['y'] == BOTTOM_Y:
            continue
        if i in tail_ends:
            continue
        errs.append('visible dead end at block %d (%d,%d,%d)'
                    % (i, blks[i]['x'], blks[i]['y'], blks[i]['z']))

    # splices: exact translated copies of same-direction fork-free windows
    for sp in sim.splices:
        wbs = [blks[j] for j in sp['win']]
        cbs = [blks[j] for j in sp['copy']]
        if any(b is None for b in wbs + cbs):
            errs.append('splice %s references erased blocks' % sp['branch'])
            continue
        dx, dy, dz = sp['delta']
        for wb, cb in zip(wbs[1:], cbs):
            if (cb['x'] + dx, cb['y'] + dy, cb['z'] + dz) != \
                    (wb['x'], wb['y'], wb['z']):
                errs.append('splice for branch %d: copy is not an exact '
                            'translation' % sp['branch'])
                break
        turns = [hwrap(hn(b2['h']) - hn(b1['h']))
                 for b1, b2 in zip(wbs, wbs[1:])]
        if any(abs(t) != 1 for t in turns):
            errs.append('splice for branch %d: window contains an '
                        'illegal turn' % sp['branch'])
        if any(len([k for k in sim.kids.get(j, ())
                    if blks[k] is not None]) > 1 for j in sp['win'][:-1]):
            errs.append('splice for branch %d: window contains a fork'
                        % sp['branch'])
        if dy <= 0:
            errs.append('splice for branch %d does not go up (dy=%d)'
                        % (sp['branch'], dy))
        if dy > SPLICE_MAX_RISE:
            errs.append('splice for branch %d rises %d > %d'
                        % (sp['branch'], dy, SPLICE_MAX_RISE))

    # every entry tip reaches the bottom
    if len(sim.entry_tips) != ENTRIES:
        errs.append('expected %d entry tips, found %d'
                    % (ENTRIES, len(sim.entry_tips)))
    bottom_idx = bottom[0] if len(bottom) == 1 else None

    def reaches_bottom(start):
        seen, q = {start}, deque([start])
        while q:
            i = q.popleft()
            if i == bottom_idx:
                return True
            for k in sim.kids.get(i, ()):
                if k not in seen and blks[k] is not None:
                    seen.add(k)
                    q.append(k)
        return False

    for tip in sim.entry_tips:
        if not reaches_bottom(tip):
            errs.append('entry tip %d cannot reach the bottom' % tip)

    # braids: BOTH children of a braid fork are winning routes
    for bd in sim.braid_list:
        arm = sim.branches[bd['arm']]
        first = arm['blocks'][0] if arm['blocks'] else None
        if first is None or blks[first] is None:
            errs.append('braid arm %d has no blocks' % bd['arm'])
            continue
        if not reaches_bottom(first):
            errs.append('braid arm %d (fork y=%d) cannot reach the '
                        'bottom' % (bd['arm'], bd['fy']))
        jb = blks[bd['join_idx']]
        if jb is None or jb['prev2'] is None:
            errs.append('braid join at y=%d lost its second arrival'
                        % bd['jy'])

    return errs


# ---- output ---------------------------------------------------------------
START_PITCH = 45.0
# spawn view pitch, tuned in-world: the descent-matched ~9 deg felt
# too flat; 45 looks down at the first bounces
SPAWN_RAISE = 4
# fall/start spawns sit this many blocks above the entry tip block.
# Tuned in-world (3 -> 8 -> 4); hand-edits to fall.msc desync
# starts.txt and fail verify_build - tune THIS constant instead
NMS_VARS = [
    '    relative Int streak = 0',
    '    relative Long timeOfLastDarkness = 0L',
    '    relative Boolean darkness = false',
    '    relative String lastColor = "LIGHT_BLUE"',
]
# hand-added namespace state referenced by the HAND-TUNED hooks; the
# emitter re-declares these on every regen so hook code keeps working

SPAWN_OVERRIDE = {(4846, 3086): (4846, 3046)}
# in-world spawn-column tweaks, keyed by entry-tip (x, z) -> spawn
# (x, z): both the fall teleport and its distance anchor move. Seed-6
# start 3 was pulled 40 blocks up-corridor after testing. Stale keys
# (from older seeds) simply never match anything


# ---- palette transitions (single source of truth - wall_test.py calls
# compute_palette for its wall/floor/dome recolor and carpet decor, and
# emit() calls it to resolve forks when choosing each trigger's onward
# path). Each PATH flips permanently to the next palette at a
# per-branch random threshold drawn inside a TRANSITIONS window
# (deterministic in the seed), inheriting "already flipped" across
# forks - different corridors change color at different depths and
# never revert mid-run. Merging dead ends adopt the junction's palette
# over their last MERGE_LEAD bounces; splice tails are overridden
# block-by-block to their window counterparts', with the flip
# SPLICE_LEAD bounces before the trigger ----
SPLICE_LEAD = 4          # palette flips this many bounces before a splice
MERGE_LEAD = 3           # ...and this many before a merge junction
MIN_RUN = 3              # a palette stretch along any traversable path is
                         # at least this many slime blocks - no color may
                         # appear and vanish again within a bounce or two.
                         # Enforced by: fork guard (no flip on the bounce
                         # right after a split), uniform used windows,
                         # upstream absorption at splice/merge leads, and
                         # a final sandwich repair pass
TRANSITIONS = (          # each path flips PERMANENTLY to palette i+1 at
    (250, 260),          # a per-branch random threshold y inside this
    (220, 230),          # window (deterministic in the seed); one row
    (190, 200),          # per palette, top to bottom, ~30 levels per
    (160, 170),          # color
    (130, 140),
    (100, 110),
)


def compute_palette(sim, verbose=True):
    # per-block palette level (0..len(TRANSITIONS)), deterministic in
    # sim.seed - the block index -> level dict wall_test.py turns into
    # materials/carpets. A block is at least as deep in the palette
    # sequence as its predecessor ("already flipped" inherits across
    # forks - a run never reverts)
    blks = sim.blocks
    br_of = {}
    for br in sim.branches:
        for i in br['blocks']:
            br_of[i] = br['id']
    thresholds = {}
    for br in sim.branches:
        for ti in range(len(TRANSITIONS)):
            tlo, thi = TRANSITIONS[ti]
            rng = random.Random('%d:%d:%d' % (sim.seed, br['id'], ti))
            thresholds[(br['id'], ti)] = rng.randint(tlo, thi)

    def live_kids(i):
        return [k for k in sim.kids.get(i, ()) if blks[k] is not None]

    # fork guard: the first bounce PAST a fork keeps the fork block's
    # palette on BOTH arms - a path always travels at least one block
    # after splitting off before it may change color, so the netherite
    # slice never sits on the fork chord itself
    guard = set()
    for i, b in enumerate(blks):
        if b is None:
            continue
        pv = b['prev']
        if pv is not None and blks[pv] is not None \
                and len(live_kids(pv)) >= 2:
            guard.add(i)

    pal_blk = {}
    changed = True
    while changed:               # prev links are near-topological;
        changed = False          # iterate to a monotone fixed point
        for i, b in enumerate(blks):
            if b is None:
                continue
            lvl = pal_blk.get(i, 0)
            bid = br_of.get(i)
            if bid is not None and i not in guard:
                for ti in range(len(TRANSITIONS)):
                    if b['y'] <= thresholds[(bid, ti)]:
                        lvl = max(lvl, ti + 1)
            pv = b['prev']
            if pv is not None:
                lvl = max(lvl, pal_blk.get(pv, 0))
            if lvl != pal_blk.get(i):
                pal_blk[i] = lvl
                changed = True

    # blocks whose palette is pinned by splice fidelity (used windows
    # and replica tails must stay block-for-block identical) or by the
    # fork guard - repairs below never touch them
    winlock = set()
    for sp in sim.splices:
        winlock.update(sp['win'][1:])
        winlock.update(sp['copy'])
    lead_lock = set()

    def absorb_up(top, level, branch_id):
        # a color run shorter than MIN_RUN directly above an override
        # region gets absorbed into the override color, repeatedly,
        # so overrides never leave 1-2 block color slivers behind.
        # Flips stay inside the override's own branch and never touch
        # pinned or guarded blocks (best effort - the sandwich pass
        # reports anything left)
        absorbed = 0
        while True:
            p = blks[top]['prev'] if blks[top] is not None else None
            if p is None or blks[p] is None:
                return absorbed
            v = pal_blk.get(p, 0)
            if v == level:
                return absorbed
            run = []
            q = p
            while q is not None and blks[q] is not None \
                    and pal_blk.get(q, 0) == v:
                run.append(q)
                if len(run) >= MIN_RUN:
                    return absorbed          # long enough - done
                q = blks[q]['prev']
            if any(r in winlock or r in lead_lock or r in guard
                   or br_of.get(r) != branch_id for r in run):
                return absorbed
            for r in run:
                pal_blk[r] = level
                lead_lock.add(r)
            absorbed += len(run)
            top = run[-1]

    # merge transitions: the merging arm's last bounces take the
    # junction block's palette so the seam is crossed in one color
    merge_flips = 0
    for br in sim.branches:
        chain = [i for i in br['blocks'] if blks[i] is not None]
        if not chain:
            continue
        for k in sim.kids.get(chain[-1], ()):
            kb = blks[k]
            if kb is not None and kb['prev2'] == chain[-1]:
                jp = pal_blk.get(k, 0)
                p2 = chain[-1]
                n2 = 0
                top2 = chain[-1]
                while n2 < MERGE_LEAD - 1 and p2 is not None \
                        and br_of.get(p2) == br['id'] \
                        and blks[p2] is not None and p2 not in guard:
                    if pal_blk.get(p2) != jp:
                        pal_blk[p2] = jp
                        merge_flips += 1
                    lead_lock.add(p2)
                    top2 = p2
                    p2 = blks[p2]['prev']
                    n2 += 1
                merge_flips += absorb_up(top2, jp, br['id'])
                break

    # used windows become one color: a splice tail mirrors its window
    # block-for-block, and a flip in a window's last bounces would
    # strand a 1-2 block sliver at the visible end of the tail. The
    # window's own flip point moves up to its start instead (levels
    # only ever increase, so downstream stays monotone)
    win_uniform = 0
    for sp in sim.splices:
        wb = [j for j in sp['win'][1:] if blks[j] is not None]
        if not wb:
            continue
        hi = max(pal_blk.get(j, 0) for j in wb)
        for j in wb:
            if pal_blk.get(j, 0) != hi:
                pal_blk[j] = hi
                win_uniform += 1

    lead_short = flipped = 0
    for sp in sorted(sim.splices,
                     key=lambda s: -blks[s['win'][1]]['y']):
        wpal = [pal_blk.get(j, 0) for j in sp['win'][1:]]
        for cj, pj in zip(sp['copy'], wpal):
            if blks[cj] is not None and pal_blk.get(cj) != pj:
                pal_blk[cj] = pj
                flipped += 1
        p = blks[sp['copy'][0]]['prev']
        n = 0
        top = sp['copy'][0]
        while p is not None and n < SPLICE_LEAD - 1 \
                and br_of.get(p) == sp['branch'] \
                and blks[p] is not None and p not in guard:
            pal_blk[p] = wpal[0]
            lead_lock.add(p)
            top = p
            p = blks[p]['prev']
            n += 1
        if n < SPLICE_LEAD - 1:
            lead_short += 1
        flipped += absorb_up(top, wpal[0], sp['branch'])

    # sandwich pass: no color may last fewer than MIN_RUN blocks along
    # any traversable path. Short runs are repaired by advancing them
    # to the downstream color (or the upstream one where the guard
    # pins the run's first block); pinned regions are reported
    def short_runs():
        found = []
        for i, b in enumerate(blks):
            if b is None:
                continue
            pi = pal_blk.get(i, 0)
            for k in live_kids(i):
                pk = pal_blk.get(k, 0)
                if pk == pi:
                    continue
                stack = [[k]]
                while stack:
                    path = stack.pop()
                    if len(path) >= MIN_RUN:
                        continue
                    for k2 in live_kids(path[-1]):
                        p2 = pal_blk.get(k2, 0)
                        if p2 == pk:
                            stack.append(path + [k2])
                        else:
                            found.append((i, path, k2))
        return found

    repaired = residual = 0
    for _pass in range(6):
        bad = short_runs()
        if not bad:
            break
        progress = False
        for up, path, down in bad:
            pk = pal_blk.get(path[0], 0)
            if any(pal_blk.get(j, 0) != pk for j in path):
                continue          # already repaired via an overlap
            # the repair moves the whole guard cluster: recoloring a
            # fork parent drags every guarded kid along, so the fork
            # chord stays one color and each arm re-flips (legally)
            # one bounce later on its own corridor
            cluster = list(path)
            for j in path:
                for k2 in live_kids(j):
                    if k2 in guard and k2 not in cluster:
                        cluster.append(k2)
            if any(j in winlock or j in lead_lock for j in cluster):
                continue          # pinned: count at the end
            tgt = (pal_blk.get(up, 0) if any(j in guard for j in path)
                   else pal_blk.get(down, 0))
            for j in cluster:
                pal_blk[j] = tgt
            repaired += len(cluster)
            progress = True
        if not progress:
            break
    residual = len(short_runs())

    if verbose:
        print('palette: %d of %d blocks past their transition, %d '
              'merge-arm blocks flipped, %d splice-tail blocks flipped, '
              '%d approaches shorter than the %d-bounce lead'
              % (sum(1 for p in pal_blk.values() if p), len(pal_blk),
                 merge_flips, flipped, lead_short, SPLICE_LEAD))
        print('palette rules: %d fork-guarded blocks, %d window blocks '
              'uniformed, %d short-run blocks repaired, %d short runs '
              'left pinned (min run %d)'
              % (len(guard), win_uniform, repaired, residual, MIN_RUN))
        if residual:
            for up, path, down in short_runs()[:8]:
                bb = blks[path[0]]
                print('   short run at (%d,%d,%d) len %d: %d -> %d -> %d'
                      % (bb['x'], bb['y'], bb['z'], len(path),
                         pal_blk.get(up, 0), pal_blk.get(path[0], 0),
                         pal_blk.get(down, 0)))
    return pal_blk


def start_yaw(sim, tip):
    # Minecraft yaw looking straight down the entry corridor's first
    # chord (the heading stored on the tip's kid block). Minecraft:
    # yaw 0 = +Z (south), 90 = -X (west); direction from yaw is
    # (-sin, cos), so yaw = atan2(-dx, dz). Headings here measure
    # from +X toward +Z: (dx, dz) = (cos h, sin h)
    kid = next(k for k in sim.kids.get(tip, ())
               if sim.blocks[k] is not None)
    h = sim.blocks[kid]['h']
    return math.degrees(math.atan2(-math.cos(h), math.sin(h)))
def emit(sim, outdir):
    st = sim.stats()
    x1, x2, z1, z2 = st['bbox']
    info = [
        '# Seamless slime-bounce maze - generate_maze.py (seed %d)'
        % sim.seed,
        '# %d entries at y=%d merge into %d tunnels (golden trunk + '
        'trunk ports); one line reaches y=%d'
        % (ENTRIES, START_Y, FUNNELS, BOTTOM_Y),
        '# %d blocks, %d forks, %d dead ends (%d spliced, %d merged)'
        % (st['blocks'], st['forks'], st['dead_ends'], st['splices'],
           st['merges']),
        '# %d braids (both fork choices win, rejoining lower) and %d of '
        '%d teleports land somewhere the player has not been'
        % (st['braids'], st['novel_splices'], st['splices']),
        '# fork cadence: no stretch runs more than %d bounces without a '
        'fork (max %d, avg %.1f, %.1f blocks per fork)'
        % (FORK_GAP_MAX, st['forkgap_max'], st['forkgap_mean'],
           st['blocks_per_fork']),
        '# Bounds: x %d..%d, z %d..%d' % (x1, x2, z1, z2),
    ]

    rows_by_branch = []
    for br in sim.branches:
        rows = [sim.blocks[i] for i in br['blocks'] if sim.blocks[i]]
        if rows:
            rows_by_branch.append((br, rows))

    def branch_tag(br):
        if br['golden']:
            return 'WINNING PATH'
        if br['funnel']:
            return 'entry corridor'
        if br.get('braid'):
            return 'braid (alternate winning route, rejoins the trunk)'
        if br.get('landing'):
            return ('teleport landing (unreachable from above: entered '
                    'only by splice tp; merges back into the maze)')
        if br['merged']:
            return 'dead end (merges into another)'
        if br['spliced']:
            return 'dead end (splice tail)'
        return 'dead end'

    # blocks as (anchor, branch note, setblock line): the spatial
    # splitter buckets them into BUILD_REGION cells and re-emits the
    # branch note whenever it changes inside a bucket
    build_items, undo_items = [], []
    for br, rows in rows_by_branch:
        note = '# branch %d (%s, y %d -> %d)' % (br['id'], branch_tag(br),
                                                 rows[0]['y'], rows[-1]['y'])
        for b in rows:
            anchor = (b['x'], b['y'], b['z'])
            build_items.append((anchor, note,
                                '@bypass /setblock %d %d %d '
                                'minecraft:slime_block'
                                % (b['x'], b['y'], b['z'])))
            undo_items.append((anchor, note,
                               '@bypass /setblock %d %d %d minecraft:air'
                               % (b['x'], b['y'], b['z'])))

    def split_parts(groups, max_lines=MAX_PART_LINES):
        parts, cur, n = [], [], 0
        for g in groups:
            if cur and n + len(g) > max_lines:
                parts.append(cur)
                cur, n = [], 0
            cur.extend(g)
            n += len(g)
        if cur:
            parts.append(cur)
        return parts

    def split_blocks(items):
        # spatial emission: bucket blocks into BUILD_REGION cells; per
        # bucket teleport once to the center of its blocks, @delay 10
        # ticks so the chunks around the player load, then place every
        # block in the bucket (all within ~4 chunks of the player). A
        # part boundary inside a bucket re-emits the tp + delay at the
        # top of the next part so each part is self-sufficient
        buckets = defaultdict(list)
        for it in items:
            buckets[(it[0][0] // BUILD_REGION,
                     it[0][2] // BUILD_REGION)].append(it)
        parts, cur, n = [], [], 0
        for key in sorted(buckets):
            bl = buckets[key]
            xs = [a[0] for a, _, _ in bl]
            ys = [a[1] for a, _, _ in bl]
            zs = [a[2] for a, _, _ in bl]
            hdr = ['@bypass tp %d %d %d'
                   % ((min(xs) + max(xs)) // 2, max(ys) + 2,
                      (min(zs) + max(zs)) // 2),
                   '@delay 10']
            pending_hdr = True
            cur_note = None
            for anchor, note, line in bl:
                lines = ([note] if note != cur_note else []) + [line]
                need = len(lines) + (len(hdr) if pending_hdr else 0)
                if cur and n + need > MAX_PART_LINES:
                    parts.append(cur)
                    cur, n = [], 0
                    pending_hdr = True
                    lines = [note, line]
                    need = len(lines) + len(hdr)
                if pending_hdr:
                    cur.extend(hdr)
                    pending_hdr = False
                cur.extend(lines)
                n += need
                cur_note = note
        if cur:
            parts.append(cur)
        return parts

    def write(path, lines):
        with open(path, 'w', newline='\n') as fh:
            fh.write('\n'.join(lines).rstrip('\n') + '\n')

    fndir = os.path.join(outdir, NAMESPACE)
    os.makedirs(fndir, exist_ok=True)
    for old in os.listdir(fndir):
        if not old.endswith('.msc'):
            continue
        # spare HAND-TUNED files (effect hooks: spliceFx, fallFx1/2,
        # scaryTitle, slimeblock, ...): owned by the map maker,
        # declared in the .nms but never emitted. Everything else
        # (incl. wall_test outputs) is regenerated
        try:
            with open(os.path.join(fndir, old)) as fh:
                if 'HAND-TUNED' in fh.read(600):
                    continue
        except OSError:
            pass
        os.remove(os.path.join(fndir, old))

    def emit_chain(parts, name, done_msg, next_fn=None):
        for k, body in enumerate(parts, 1):
            head = (['# %s%d(Player player)' % (name, k),
                     '# part %d of %d - chains to the next part when done'
                     % (k, len(parts))] + info +
                    ['', '@using %s' % NAMESPACE, ''])
            if k < len(parts):
                tail = ['', '@var %s%d(player)' % (name, k + 1)]
            elif next_fn:
                tail = ['', '@var %s(player)' % next_fn]
            else:
                # audible done-notification (long chains run while the
                # player is AFK), then the chat message - the @player
                # line stays LAST (verify_build keys on it)
                tail = ['', DONE_SOUND, '@player %s' % done_msg]
            write(os.path.join(fndir, '%s%d.msc' % (name, k)),
                  head + body + tail)
        return len(parts)

    # Onward-path map for the 3-block trigger calls: every trigger
    # passes its own block plus the NEXT TWO bounce blocks along the
    # path the player is expected to ride. At a fork the kid whose
    # corridor keeps the CURRENT block's palette color longest wins
    # (compute_palette is the same code wall_test.py colors the world
    # with, so "color" here IS the carpet/wall color in-game); ties
    # fall to the lower block index for determinism. A dead-end tip
    # with no continuation repeats itself.
    pal = compute_palette(sim, verbose=False)
    live = [i for i, b in enumerate(sim.blocks) if b is not None]

    def live_kids(i):
        return [k for k in sim.kids.get(i, ()) if sim.blocks[k] is not None]

    indeg = {i: 0 for i in live}
    for i in live:
        for k in live_kids(i):
            indeg[k] += 1
    topo, q = [], deque(i for i in live if indeg[i] == 0)
    while q:
        i = q.popleft()
        topo.append(i)
        for k in live_kids(i):
            indeg[k] -= 1
            if indeg[k] == 0:
                q.append(k)
    same_run = {}                # longest same-color run from each block
    for i in reversed(topo):
        best = 0
        for k in live_kids(i):
            if pal.get(k, 0) == pal.get(i, 0):
                best = max(best, same_run[k])
        same_run[i] = best + 1
    succ = {}
    for i in topo:
        kids = live_kids(i)
        if kids:
            ci = pal.get(i, 0)
            succ[i] = min(kids, key=lambda k: (
                -(same_run[k] if pal.get(k, 0) == ci else 0), k))

    def nexts(i):
        n1 = succ.get(i, i)
        return sim.blocks[n1], sim.blocks[succ.get(n1, n1)]

    # The splice-trigger import: a 3x3 BLANKET of WALK scripts per
    # trigger block (first two tail blocks of each splice) on the
    # carpet layer (y+1), exactly like the slimeblock blankets - walk,
    # not ground, because the carpet/air cells are passed through, not
    # stood on. Every cell calls the splice dispatcher (one shared
    # place for the teleport plus any future swap-time effects) with
    # three LITERAL blocks: the owning TRIGGER SLIME BLOCK (never the
    # cell - splice() re-bases by trigger+delta) plus its two onward
    # tail blocks (the tail is fork-free, so these are the next two
    # replica bounces and the same +delta lands them on the window).
    # One remove+create pair per cell keeps re-runs idempotent; cells
    # on a live slime block are dropped, and cross-splice collisions
    # cannot happen (tail tubes never overlap) but the same
    # nearest-owner dedup guards it anyway. Grouped per splice so a
    # chain split never separates a splice's cells. Far too many lines
    # to inline in __init__ (hastebin cap) - the groundsN chain is the
    # ONLY wiring (build chains into it; it tail-calls slimegrounds1),
    # mirrored by the removegroundsN undo chain.
    splice_trigger = {ci for sp in sim.splices for ci in sp['copy'][:2]}
    slime_pos = {(b['x'], b['y'], b['z'])
                 for b in sim.blocks if b is not None}
    sp_cells = {}            # cell -> (d2, owner trigger index)
    for ti in splice_trigger:
        tb = sim.blocks[ti]
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                pos = (tb['x'] + dx, tb['y'] + 1, tb['z'] + dz)
                if pos in slime_pos:
                    continue
                claim = (dx * dx + dz * dz, ti)
                if pos not in sp_cells or claim < sp_cells[pos]:
                    sp_cells[pos] = claim
    sp_cells_of = defaultdict(list)
    for pos, (d2, ti) in sp_cells.items():
        sp_cells_of[ti].append(pos)
    ground_groups, unground_groups = [], []
    for n, sp in enumerate(sim.splices, 1):
        gg = ['# splice %d (branch %d)' % (n, sp['branch'])]
        ug = ['# splice %d (branch %d)' % (n, sp['branch'])]
        for ci in sp['copy'][:2]:
            cb = sim.blocks[ci]
            n1, n2 = nexts(ci)
            for pos in sorted(sp_cells_of[ci]):
                rm = ('@command script remove walk %d %d %d %s'
                      % (pos[0], pos[1], pos[2], WORLD_NAME))
                gg.append(rm)
                gg.append('@command script create walk %d %d %d %s '
                          '@var %s::splice(player, %d, '
                          'Block(%d, %d, %d, "%s"), '
                          'Block(%d, %d, %d, "%s"), '
                          'Block(%d, %d, %d, "%s"))'
                          % (pos[0], pos[1], pos[2], WORLD_NAME,
                             NAMESPACE, n,
                             cb['x'], cb['y'], cb['z'], WORLD_NAME,
                             n1['x'], n1['y'], n1['z'], WORLD_NAME,
                             n2['x'], n2['y'], n2['z'], WORLD_NAME))
                ug.append(rm)
        ground_groups.append(gg)
        unground_groups.append(ug)

    # slimeblock bounce triggers: a 3x3 BLANKET of WALK scripts per
    # slime block on the carpet layer (y+1) - the carpet cell plus the
    # 8 cells it touches (trapdoor tops / air). Walk, not ground:
    # ground scripts only fire on blocks the player STANDS on, and
    # carpet/air cells are passed through, not stood on - walk scripts
    # fire on pass-through, so grazing bounces and
    # near-misses still fire the HAND-TUNED slimeblock(player, here,
    # next1, next2) hook. All three Block args are literals: `here` is
    # the OWNING SLIME BLOCK (never the cell - the hook's particle
    # origin and carpet lookup key off the real block), next1/next2
    # the next two along the onward path (forks resolved by the
    # longest-same-color rule). Cells are deduped: nearest owner
    # (squared horizontal distance, then lower block index) wins; a
    # cell that lands on a live slime block is dropped (that block's
    # own blanket covers it one level up), and the 3x3 above a splice
    # trigger block (first two tail blocks of each splice, which keep
    # their single splice(player, n) script at slime level) is left
    # empty so nothing shadows the splice() zone. Same remove+create
    # idempotent pattern as the splice triggers, but far too many
    # lines to inline in __init__ (hastebin cap), so they are wired
    # only by the chains: grounds tail-calls slimegrounds1,
    # removegrounds tail-calls removeslimegrounds1. After a namespace
    # re-import, run grounds1 once by hand to re-wire everything
    no_cell = set()          # 3x3 above splice triggers: reserved
                             # for the splice blankets emitted above
    for ti in splice_trigger:
        tb = sim.blocks[ti]
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                no_cell.add((tb['x'] + dx, tb['y'] + 1, tb['z'] + dz))
    cells = {}               # cell -> (d2, owner block index)
    for i, b in enumerate(sim.blocks):
        if b is None or i in splice_trigger:
            continue
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                pos = (b['x'] + dx, b['y'] + 1, b['z'] + dz)
                if pos in no_cell or pos in slime_pos:
                    continue
                claim = (dx * dx + dz * dz, i)
                if pos not in cells or claim < cells[pos]:
                    cells[pos] = claim
    by_owner = defaultdict(list)
    for pos, (d2, i) in cells.items():
        by_owner[i].append(pos)
    sg_groups, rsg_groups = [], []
    for i in sorted(by_owner):
        b = sim.blocks[i]
        n1, n2 = nexts(i)
        gg, ug = [], []
        for pos in sorted(by_owner[i]):
            rm = ('@command script remove walk %d %d %d %s'
                  % (pos[0], pos[1], pos[2], WORLD_NAME))
            gg.append(rm)
            # world name hardcoded (not block.getWorld()): walk
            # scripts should not depend on the runtime block context
            gg.append('@command script create walk %d %d %d %s '
                      '@var %s::slimeblock(player, '
                      'Block(%d, %d, %d, "%s"), '
                      'Block(%d, %d, %d, "%s"), '
                      'Block(%d, %d, %d, "%s"))'
                      % (pos[0], pos[1], pos[2], WORLD_NAME,
                         NAMESPACE, b['x'], b['y'], b['z'], WORLD_NAME,
                         n1['x'], n1['y'], n1['z'], WORLD_NAME,
                         n2['x'], n2['y'], n2['z'], WORLD_NAME))
            ug.append(rm)
        sg_groups.append(gg)
        rsg_groups.append(ug)

    nb = emit_chain(split_blocks(build_items), 'build', None,
                    next_fn='grounds1')
    ng = emit_chain(split_parts(ground_groups, SG_PART_LINES),
                    'grounds', None, next_fn='slimegrounds1')
    nsg = emit_chain(split_parts(sg_groups, SG_PART_LINES),
                     'slimegrounds',
                     '&aSlime maze build complete - splice + slime '
                     'bounce triggers imported!')
    nr = emit_chain(split_blocks(undo_items), 'remove', None,
                    next_fn='removegrounds1')
    nrg = emit_chain(split_parts(unground_groups), 'removegrounds', None,
                     next_fn='removeslimegrounds1')
    nrsg = emit_chain(split_parts(rsg_groups), 'removeslimegrounds',
                      '&aSlime maze removed - all ground triggers '
                      'cleared.')

    # splice dispatcher
    def toff(name, axis, v):
        return '%s.get%s() %s %d' % (name, axis, '+' if v >= 0 else '-',
                                     abs(v))

    def tblock(name, dx, dy, dz):
        return ('Block(%s, %s, %s, trigger.getWorld())'
                % (toff(name, 'X', dx), toff(name, 'Y', dy),
                   toff(name, 'Z', dz)))

    sp_lines = [
        '# splice(Player player, Int n, Block trigger, Block next1, '
        'Block next2)',
        '# Applies dead-end n\'s seamless relative teleport: run it while',
        '# the player is ANYWHERE on that dead end\'s replica tail and they',
        '# are shifted onto the identical real corridor higher up, keeping',
        '# position, facing and momentum. See splices.txt for trigger',
        '# regions. The splice ground triggers call this function with',
        '# the trigger block and its two onward tail blocks; each branch',
        '# teleports, then calls slimeblock() with all three re-based onto',
        '# the DESTINATION window (block + delta - the copy is an exact',
        '# translation), so bounce effects match the real corridor the',
        '# player now rides. Every branch falls through (no @return) to',
        '# the spliceFx(player) call - the HAND-TUNED swap effects hook,',
        '# which regeneration never overwrites - but the hook only fires',
        '# when the teleport moves the player more than %d blocks'
        % SPLICE_FX_MIN_D,
        '# (euclidean |delta|, decided at emit time per branch): short',
        '# hops stay effect-free.',
        '',
        '@using %s' % NAMESPACE,
        '@fast',
        '',
        '@cooldown 5',
        '',
        '@define Boolean doFx = false',
        '',
    ]
    # the hook calls pass Player("{{player.getName()}}") - the console
    # dispatch re-resolves the player by name (hand-tested in-world
    # 2026-08-07, like the @console form itself from 2026-08-06, which
    # decouples the hooks from the walk script's execution context)
    pname = 'Player("{{player.getName()}}")'
    fx_count = 0
    first = True
    for n, sp in enumerate(sim.splices, 1):
        dx, dy, dz = sp['delta']
        kw = '@if' if first else '@elseif'
        first = False
        sp_lines.append('%s n == %d' % (kw, n))
        sp_lines.append('    @bypass /minecraft:tp @s ~%d ~%d ~%d'
                        % (dx, dy, dz))
        sp_lines.append('    @console /function execute '
                        '%s::slimeblock(%s, %s, %s, %s)'
                        % (NAMESPACE, pname,
                           tblock('trigger', dx, dy, dz),
                           tblock('next1', dx, dy, dz),
                           tblock('next2', dx, dy, dz)))
        if dx * dx + dy * dy + dz * dz > SPLICE_FX_MIN_D ** 2:
            sp_lines.append('    @var doFx = true')
            fx_count += 1
    if not first:
        sp_lines.append('@else')
        sp_lines.append('    @player &cUnknown splice id {{n}}')
        sp_lines.append('@fi')
    sp_lines += [
        '',
        '@if doFx',
        '    @console /function execute %s::spliceFx(%s)'
        % (NAMESPACE, pname),
        '@fi',
    ]
    print('splice fx: %d of %d teleports exceed %d blocks and fire '
          'spliceFx' % (fx_count, len(sim.splices), SPLICE_FX_MIN_D))
    write(os.path.join(fndir, 'splice.msc'), sp_lines)

    # __init__: runs on every namespace import. Since the splice
    # triggers became 3x3 walk-script blankets (2026-08-07) they are
    # far too many lines to inline here (hastebin cap), so the import
    # wires NOTHING - documentation only. All trigger wiring lives in
    # the grounds1..N chain (splice blankets, tail-calls slimegrounds1
    # for the slimeblock blankets); the build chain runs it for you.
    init = [
        '# __init__ - runs on every namespace import. Documentation only:',
        '# since the splice triggers are 3x3 walk-script blankets, they',
        '# are far too many lines to inline here (hastebin cap), so',
        '# importing wires NOTHING. All trigger wiring is the',
        '# grounds1..%d chain (splice blankets; tail-calls slimegrounds1'
        % ng,
        '# for the slimeblock blankets) - the build chain runs it, and',
        '# after any namespace re-import run grounds1 once by hand to',
        '# re-wire every trigger.',
        '# Registry: splices.txt. Manual fallback: splice(player, n, ...).',
    ]
    write(os.path.join(fndir, '__init__.msc'), init)

    # fall handler: teleports a fallen player to one of the 3 starts
    # FURTHEST from where they fell (random among those 3)
    fl = [
        '# fall(Player player)',
        '# Run whenever a player falls off the maze: teleports them above',
        '# one of the %d start positions (see starts.txt) - a random pick'
        % ENTRIES,
        '# among the 3 FURTHEST (horizontal block distance) from where',
        '# they fell, so a fall never dumps them back at a nearby',
        '# entrance and the opening cannot simply be re-memorized. Wire',
        '# this to the map\'s fall-catch region / kill floor. Effects',
        '# live in fallFx1 (pre-tp) and fallFx2 (post-tp) - HAND-TUNED',
        '# hooks that regeneration never overwrites.',
        '',
        '@using %s' % NAMESPACE,
        '@fast',
        '',
        '@define BlockLocation ploc = player.getLocation().asBlockLocation()',
        '@define Int px = ploc.getX()',
        '@define Int pz = ploc.getZ()',
        '',
        '# squared horizontal distance to each start column',
    ]
    for n, tip in enumerate(sim.entry_tips):
        b = sim.blocks[tip]
        sx, sz = SPAWN_OVERRIDE.get((b['x'], b['z']), (b['x'], b['z']))
        fl.append('@define Int d%d = (px - %d) * (px - %d)'
                  ' + (pz - %d) * (pz - %d)'
                  % (n, sx, sx, sz, sz))
    fl += [
        '@define Int[] dists = Int[%s]'
        % ', '.join('d%d' % n for n in range(len(sim.entry_tips))),
        '',
        '# indices of the 3 furthest starts: 3 max-passes, each',
        '# excluding the winners of the earlier passes',
        '@define Int best = -1',
        '@define Int m1 = -1',
        '@for Int i in list::range(0, %d)' % len(sim.entry_tips),
        '    @if dists[i] > best',
        '        @var best = dists[i]',
        '        @var m1 = i',
        '    @fi',
        '@done',
        '@var best = -1',
        '@define Int m2 = -1',
        '@for Int j in list::range(0, %d)' % len(sim.entry_tips),
        '    @if j != m1 && dists[j] > best',
        '        @var best = dists[j]',
        '        @var m2 = j',
        '    @fi',
        '@done',
        '@var best = -1',
        '@define Int m3 = -1',
        '@for Int k in list::range(0, %d)' % len(sim.entry_tips),
        '    @if k != m1 && k != m2 && dists[k] > best',
        '        @var best = dists[k]',
        '        @var m3 = k',
        '    @fi',
        '@done',
        '',
        '@define Int r = Int(math::random(0D, 2D))',
        '@define Int pick = m1',
        '@if r == 1',
        '    @var pick = m2',
        '@elseif r == 2',
        '    @var pick = m3',
        '@fi',
        '',
        '@var fallFx1(player)',
        '',
    ]
    for n, tip in enumerate(sim.entry_tips):
        b = sim.blocks[tip]
        sx, sz = SPAWN_OVERRIDE.get((b['x'], b['z']), (b['x'], b['z']))
        if n == 0:
            fl.append('@if pick == 0')
        elif n < len(sim.entry_tips) - 1:
            fl.append('@elseif pick == %d' % n)
        else:
            fl.append('@else')
        fl.append('    @bypass /minecraft:tp {{player}} %d %d %d '
                  '%.1f %.1f'
                  % (sx, b['y'] + SPAWN_RAISE, sz,
                     start_yaw(sim, tip), START_PITCH))
    fl.append('@fi')
    fl.append('')
    fl.append('@var fallFx2(player)')
    write(os.path.join(fndir, 'fall.msc'), fl)

    nms = (['@namespace %s' % NAMESPACE, ''] + info + [
        '#', '',
        '# Variables (hand-added state used by the HAND-TUNED hooks)',
        '',
    ] + NMS_VARS + [
        '',
        '#',
        '# Build:  /function execute %s::build1(Player("You"))' % NAMESPACE,
        '# Undo:   /function execute %s::remove1(Player("You"))' % NAMESPACE,
        '# Splice: /function execute %s::splice(Player("You"), Int(n), '
        'Block(x, y, z, "%s"), Block(...), Block(...))'
        % (NAMESPACE, WORLD_NAME),
        '# Fall:   /function execute %s::fall(Player("You"))' % NAMESPACE,
        '# Grounds: /function execute %s::grounds1(Player("You"))'
        % NAMESPACE,
        '# Build/remove parts chain automatically; the build chain runs',
        '# grounds1 (splice trigger blankets) then slimegrounds1 (per-',
        '# block slimeblock() bounce blankets); the remove chain mirrors',
        '# both. Importing the namespace wires NOTHING (__init__ is',
        '# documentation only - every trigger import is too many lines) -',
        '# after a re-import, run grounds1 once to re-wire everything.',
        ''])
    for k in range(1, nb + 1):
        nms.append('    build%d(Player player)' % k)
    for k in range(1, ng + 1):
        nms.append('    grounds%d(Player player)' % k)
    for k in range(1, nr + 1):
        nms.append('    remove%d(Player player)' % k)
    for k in range(1, nrg + 1):
        nms.append('    removegrounds%d(Player player)' % k)
    for k in range(1, nsg + 1):
        nms.append('    slimegrounds%d(Player player)' % k)
    for k in range(1, nrsg + 1):
        nms.append('    removeslimegrounds%d(Player player)' % k)
    nms.append('    splice(Player player, Int n, Block trigger, '
               'Block next1, Block next2)')
    # hand-written companions (not emitted): the effect hooks called by
    # splice/fall and the spooky title - keep them declared or imports
    # break them
    nms.append('    scaryTitle(Player player)')
    nms.append('    spliceFx(Player player)')
    nms.append('    fallFx1(Player player)')
    nms.append('    fallFx2(Player player)')
    nms.append('    slimeblock(Player player, Block slimeblock, '
               'Block next1, Block next2)')
    nms.append('    fall(Player player)')
    nms.append('@endnamespace')
    write(os.path.join(outdir, '%s.nms' % NAMESPACE), nms)

    # splice registry
    reg = ['SPLICE REGISTRY (seed %d)' % sim.seed,
           'For each dead end: the replica tail blocks, the relative tp,',
           'and the real window it maps onto. Trigger when the player is',
           'anywhere over the tail stretch (suggested: on entering the',
           'first tail block\'s column).', '']
    for n, sp in enumerate(sim.splices, 1):
        c1 = sim.blocks[sp['copy'][0]]
        c5 = sim.blocks[sp['copy'][-1]]
        w0 = sim.blocks[sp['w0']]
        dx, dy, dz = sp['delta']
        reg.append('splice %3d  branch %3d  tail (%d,%d,%d)..(%d,%d,%d)'
                   % (n, sp['branch'], c1['x'], c1['y'], c1['z'],
                      c5['x'], c5['y'], c5['z']))
        reg.append('            /minecraft:tp @s ~%d ~%d ~%d   '
                   '-> window at (%d,%d,%d)%s'
                   % (dx, dy, dz, w0['x'], w0['y'], w0['z'],
                      '   [NEW TERRITORY - off the route down]'
                      if sp.get('novel') else ''))
    write(os.path.join(outdir, 'splices.txt'), reg)

    # start positions
    sl = ['START POSITIONS (seed %d) - one per entry corridor' % sim.seed,
          'A fall teleports the player above a random one of the 3 of',
          'these furthest from the fall point (see fall.msc).',
          '']
    for n, tip in enumerate(sim.entry_tips, 1):
        b = sim.blocks[tip]
        sx, sz = SPAWN_OVERRIDE.get((b['x'], b['z']), (b['x'], b['z']))
        sl.append('start %2d: %d %d %d   (spawn at %d %d %d, yaw %.1f)'
                  % (n, b['x'], b['y'], b['z'],
                     sx, b['y'] + SPAWN_RAISE, sz,
                     start_yaw(sim, tip)))
    write(os.path.join(outdir, 'starts.txt'), sl)

    # solution
    gforks = sorted([f for f in sim.forks if f['golden']],
                    key=lambda f: -f['y'])
    sol = [
        'SLIME MAZE SOLUTION (seed %d)' % sim.seed,
        'All %d entries funnel to the trunk top at (%d, %d, %d).'
        % (ENTRIES, START_X, TRUNK_TOP, START_Z),
        'Finish: one block at y=%d' % BOTTOM_Y,
        '',
        'At each fork you bounce off the parent block; take the CORRECT',
        'child. Compass: +X=E, -X=W, +Z=S, -Z=N.',
        '',
    ]
    for n, f in enumerate(gforks, 1):
        p = sim.blocks[f['parent_idx']]
        c = sim.blocks[f['cont_idx']]
        dd = sim.blocks[f['decoy_idx']]
        if p is None or c is None or dd is None:
            continue
        sol.append('Fork %2d @ y=%4d  from (%d, %d, %d):' %
                   (n, f['y'], p['x'], p['y'], p['z']))
        sol.append('    CORRECT -> (%d, %d, %d)  heading %s' %
                   (c['x'], c['y'], c['z'],
                    compass(c['x'] - p['x'], c['z'] - p['z'])))
        sol.append('    decoy   -> (%d, %d, %d)  heading %s' %
                   (dd['x'], dd['y'], dd['z'],
                    compass(dd['x'] - p['x'], dd['z'] - p['z'])))
    sol.append('')
    sol.append('Braids - forks where BOTH choices win (arms rejoin the '
               'trunk lower down):')
    for n, bd in enumerate(sim.braid_list, 1):
        fp = sim.blocks[bd['fork_idx']]
        jp = sim.blocks[bd['join_idx']]
        arm = sim.branches[bd['arm']]
        sol.append('Braid %d: fork @ (%d, %d, %d) y=%d -> rejoins the '
                   'trunk @ (%d, %d, %d) y=%d (%d bounces around)'
                   % (n, fp['x'], fp['y'], fp['z'], bd['fy'],
                      jp['x'], jp['y'], jp['z'], bd['jy'],
                      len(arm['blocks'])))
    sol.append('')
    sol.append('Winning-path coordinates (trunk top to bottom):')
    for i in sim.branches[0]['blocks']:
        b = sim.blocks[i]
        if b:
            sol.append('%d %d %d' % (b['x'], b['y'], b['z']))
    write(os.path.join(outdir, 'solution.txt'), sol)


def main():
    outdir = os.path.dirname(os.path.abspath(__file__))
    seeds = [int(sys.argv[1])] if len(sys.argv) > 1 else range(1, 400)
    for seed in seeds:
        sim = Sim(seed)
        if not sim.run():
            print('seed %d: could not route golden trunk / funnel' % seed)
            continue
        st = sim.stats()
        if (st['peak_width'] < 10 or st['forks'] < 60
                or st['golden_forks'] < 22
                or st['gap_mean'] > 13.5 or st['gap_max'] > 26
                or st['forkgap_viol'] > 0
                or st['entries'] != ENTRIES
                or st['splices'] < 40
                or st['braids'] < BRAID_MIN
                or st['novel_splices'] < st['splices'] * NOVEL_MIN_FRAC):
            print('seed %d: weak maze (%d forks, %d golden, peak %d, gaps '
                  '%.1f/%d, fork gap %d (%d blocks over %d), %d splices, '
                  '%d novel, %d merges, %d braids)'
                  % (seed, st['forks'], st['golden_forks'],
                     st['peak_width'], st['gap_mean'], st['gap_max'],
                     st['forkgap_max'], st['forkgap_viol'], FORK_GAP_MAX,
                     st['splices'], st['novel_splices'], st['merges'],
                     st['braids']))
            continue
        errs = verify(sim)
        if errs:
            print('seed %d failed verification (%d):' % (seed, len(errs)))
            for e in errs[:15]:
                print('  ' + e)
            continue
        emit(sim, outdir)
        print('seed %d OK: %d blocks, %d forks (%d golden, gaps %.1f/%d), '
              '%d dead ends, %d splices (%d novel, %d onto doomed, '
              '%d unspliced), %d merges, %d braids, %d windows, peak %d, '
              'bounds x %d..%d z %d..%d'
              % (seed, st['blocks'], st['forks'], st['golden_forks'],
                 st['gap_mean'], st['gap_max'], st['dead_ends'],
                 st['splices'], st['novel_splices'], st['doom_chains'],
                 st['unspliced'], st['merges'], st['braids'],
                 st['windows'], st['peak_width'], *st['bbox']))
        print('fork cadence: max gap %d (cap %d), avg gap %.1f bounces, '
              '%d fork blocks = %.1f blocks per fork, %d landing '
              'branches (teleport-only territory)'
              % (st['forkgap_max'], FORK_GAP_MAX, st['forkgap_mean'],
                 st['fork_blocks'], st['blocks_per_fork'],
                 st['landings']))
        return
    print('no seed satisfied all constraints')
    sys.exit(1)


if __name__ == '__main__':
    main()
