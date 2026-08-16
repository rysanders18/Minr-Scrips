# generate_maze_v3.py - V3 generator for the seamless slime-bounce maze:
# CORRECT-BY-CONSTRUCTION (see V3_PLAN.md). Differences from v2:
#   - spatial hash behind clear() (grid, 8x8 cells)
#   - fork cadence guaranteed during the walk (FORK_FORCE_AT /
#     FORK_LAND_AT) instead of repaired after; enforce_fork_gaps
#     survives only as the static-maze pre-pass + a dirty-flag backstop
#   - LANDING-ONLY dead ends: every termination BUILDS its teleport
#     destination (splice_landing); the v2 window search never runs for
#     dead ends (splice_tail remains for the static pre-pass only)
#   - SPLICE_SUPPRESS: no trigger within 5 bounces of any landing
#     (holds by construction, proven in verify())
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
#   bounces of a live corridor that contain no fork and turn in ONE
#   CONSTANT direction (user rule 2026-08-15: the tail past the trigger
#   may never flip, or its own dead end could swing into view before
#   the teleport fires). Because the copy is
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
import time
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
W_MAX = 30           # target concurrent (non-doomed) paths near the bottom
                     # (v3: 70 -> 40 - termination demand scales with
                     # corridor mass at ~1 fork per 15 blocks, and the
                     # maze's landing/merge capacity is ~250: total mass
                     # must stay near v2's ~4800 blocks for viol 0.
                     # 40 -> 30 with the turn-run rule: constant-window
                     # scarcity cut termination capacity again, so the
                     # corridor mass follows it down)
W_MID_BOOST = 0.2    # mid-depth bump on the live-path width curve: the
                     # middle of the maze reads several corridors wide
                     # instead of one trunk plus stubs (v3: 0.45 -> 0.2,
                     # the mid-band is where landing volume is scarcest)
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
# v3 CORRECT-BY-CONSTRUCTION CADENCE (see V3_PLAN.md): the walk itself
# guarantees the cap instead of post-hoc repair. Once a tip's exact
# bounces-since-fork reaches FORK_FORCE_AT a fork spawn is attempted
# EVERY level (overriding the random timer); if none succeeds by
# FORK_LAND_AT the arm is terminated on the spot with a LANDING splice
# (always legal: the trigger lands at gap <= FORK_LAND_AT + 1 + 1 <
# FORK_GAP_MAX). Merge walks are capped so the junction never arrives
# past FORK_LAND_AT either. enforce_fork_gaps survives ONLY as the
# skeleton pre-pass on the static maze (trunk/funnels/braids, run
# while the world is near-empty - the dbg6k breakthrough).
FORK_FORCE_AT = 12   # exact-gap threshold: force fork attempts per level
FORK_LAND_AT = 17    # exact-gap threshold: terminate the arm via landing
LAND_R_EXTRA = 36    # landing corridors may sit this far beyond max_r:
                     # the corridor cloud self-limits to ~150 of the
                     # allowed 198, and the empty annulus outside it is
                     # perfect landing real estate - the copy volume
                     # contest (ld_s_place ~230k/seed) happens only
                     # inside the cloud
SPLICE_SUPPRESS = 5  # user rule (2026-08-09): after a splice fires the
                     # player must ride at least this many bounces before
                     # another trigger can fire. Landing splices give
                     # >= WINDOW-1 copy bounces + a 3..8-bounce connector
                     # before rejoining the maze, so the rule holds BY
                     # CONSTRUCTION (verified in verify()); v2-style
                     # instant chains (windows overlapping replica tails,
                     # teleporting straight onto another trigger) are
                     # rejected in splice_tail
FLIP_MIN, FLIP_MAX = 7, 18    # bounces between turn-direction flips; the
                              # max exceeds a full 16-bounce circle, so some
                              # stretches are descending helixes that return
                              # over their own start (kills dead reckoning).
                              # (5 -> 8 with the turn-run rule: windows and
                              # splice suffixes must be WINDOW=7 constant
                              # turns now, so wander runs must reach 8+
                              # bounces or the termination tiers starve)
TURN_RUN_MIN = 3     # user rule (2026-08-15): after a turn-direction
                     # change, the next TURN_RUN_MIN-1 bounces must keep
                     # the new direction - no second change within two
                     # blocks of the first, on ANY traversable route
                     # (forced fallback flips, connector sequences and
                     # fork mirrors included, not just the flip timer).
                     # Enforced by turn_ok/down_turn_ok/flips_ok at
                     # every placement site and re-checked in verify()
FORK_TURN_LOCK = 4   # levels after a fork before a branch may flip its turn
LIFE_MIN, LIFE_MAX = 6, 16    # (v3: 8,24 -> 6,16 - arm economics)
                              # bounces a doomed branch survives (at the
                              # trunk top; both bounds grow with depth up
                              # to LIFE_MAX_DEEP - late mistakes cost more)
LIFE_MAX_DEEP = 24   # (v3: 40 -> 24 - the evil-mode long wanders bred
                     # doomed subtrees far beyond termination capacity)
                     # doomed-life upper bound at DOOM_ALL_AT depth; still
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
BACKTRACK_MAX = 30000  # phase-1 backtrack budget per seed (12000 ->
                       # 30000: the turn-run rule prunes step options,
                       # so legal trunks need deeper backtracking)
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
PORT_MIN, PORT_MAX = 10, 64    # depth below TRUNK_TOP of the ports; the
                               # port funnel stays junction-free until
                               # above TRUNK_TOP, so this is also the
                               # visible length of the extra tunnels.
                               # (10,32 -> 10,64 with the turn-run rule:
                               # a port needs the trunk to flip right
                               # below the junction - or hold its turn
                               # for 3 stub-free bounces - which thinned
                               # the eligible depths severely)
PORT_SEP = 4                   # min level gap between two ports
FUNNEL_DEPTH = 45              # levels the funnel needs to merge them
TRUNK_TOP = START_Y - FUNNEL_DEPTH   # golden trunk starts here
FUNNEL_GAP_MIN, FUNNEL_GAP_MAX = 7, 12   # levels between funnel merges

# ---- dead-end handling ----------------------------------------------------
WANDER_FLOOR = -38   # doomed corridors stop wandering here so that...
WINDOW = 7           # ...their splice tails (<= ALIGN_MAX + WINDOW deeper)
ALIGN_MAX = 8        #    stay above MORTAL_FLOOR (-38-15=-53 >= -55 ok;
                     #    6 -> 8 buys back window reach lost to the
                     #    constant-direction window rule). The teleport triggers
                     #    sit on the first two tail blocks, so 6-7
                     #    bounces continue past whichever trigger fires -
                     #    long enough that the corridor's end is never in
                     #    sight before the splice. Windows are CONSTANT
                     #    turn direction (user rule 2026-08-15): a tail
                     #    that flipped past the trigger could curl back
                     #    and show its own dead end. That makes windows
                     #    scarcer (only runs >= WINDOW+1 bounces long
                     #    qualify), paid for by the turn-run rule keeping
                     #    runs long everywhere
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
FARM_ZONES = ((240, 288), (FORK_FLOOR, 20))
                     # WINDOW FARM (build-time co-reservation): root-y
                     # bands for pre-built window corridors, set from
                     # the measured viol distribution of the 98-viol
                     # baseline (y quartiles [-44, 15, 245, 277, 293]):
                     # the funnel zone and the deep band are where
                     # dying arms find no landing volume - so shareable
                     # window capacity is manufactured there at build
                     # time, while the annulus is still empty
FARM_GAP_LO, FARM_GAP_HI = 5, 9   # levels between farm roots along a
                                  # static corridor
FARM_TOP_CAP = START_Y - 2   # no farm block above this: corridors must
                             # never poke out of the maze dome
FARM_WALK_TRIES = 10  # upward-wander attempts per farm root (each try
                      # samples a different drift bearing)
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
BRAID_LOCK = 3                 # diverging bounces after a braid fork
                               # (4 -> 3 = TURN_RUN_MIN: the shortest
                               # legal mirror run - one bounce earlier
                               # into steering, where flips are legal)
BRAID_SPACING = 4              # min trunk-level gap between braid ends
BRAID_CONNECT = 12             # start trying to land this many levels up
BRAID_HUG = 15.0               # steering floor: stay at least this far
                               # from the slot until the landing (just
                               # outside the trunk's separation alley)
BRAID_TRIES = 1000             # (fork, rejoin) pairs tried per maze
                               # (400 -> 1000: the turn-run rule kills
                               # most arms in the diverge lock or the
                               # alley steering, so more pairs must be
                               # rolled to land one braid)

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


def chord_int_ok(ax, az, bx, bz):
    # verify() checks chords between INTEGER block coords (5.0..7.6);
    # a float-solved 6.3 chord can stretch to ~7.7 once both endpoints
    # round (observed live: 7.62 on a connector arrival). Every
    # placement from float-solved points must run this guard and treat
    # overflow as a placement failure
    c = math.hypot(ax - bx, az - bz)
    return 5.0 <= c <= 7.6


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


def flips_ok(turns):
    # TURN_RUN_MIN user rule on a ride-ordered turn list: every
    # direction change must be followed by at least TURN_RUN_MIN-1
    # turns of the new direction. Truncated windows at either end of
    # the list are legal - the caller extends the list with whatever
    # boundary turns exist (upstream history, junction arrivals,
    # existing downstream corridor) and the stateful checks
    # (turn_ok/down_turn_ok) own anything beyond the list
    for i in range(1, len(turns)):
        if turns[i] != turns[i - 1]:
            for j in range(i + 1, min(i + TURN_RUN_MIN, len(turns))):
                if turns[j] != turns[i]:
                    return False
    return True


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


def run_comps(n, lo=TURN_RUN_MIN):
    # ordered compositions of n into parts >= lo: the maximal-run
    # lengths of every turn sequence that satisfies the turn-run rule
    # internally (signs alternate between consecutive runs)
    if n == 0:
        yield ()
        return
    for p in range(lo, n + 1):
        if n - p == 0 or n - p >= lo:
            for rest in run_comps(n - p, lo):
                yield (p,) + rest


class Sim:
    def __init__(self, seed):
        self.seed = seed
        self.rng = random.Random(seed)
        self.blocks = []            # dicts or None (erased)
        self.by_y = defaultdict(list)
        self.grid = defaultdict(list)   # (x>>3, z>>3) -> live block idxs:
                                        # spatial hash backing clear() -
                                        # by_y row scans went O(maze) per
                                        # probe; the grid is O(1)
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
        self.chew_dirty = False          # a chew erased blocks since the
                                         # last interleaved cadence check
        self.repair_failed = set()       # insert_fork candidates that
                                         # exhausted their tries (kept
                                         # across enforce calls)
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
        self.grid[(x >> 3, z >> 3)].append(idx)
        if prev is not None:
            self.kids[prev].append(idx)
        return idx

    def pop_block(self, idx):
        b = self.blocks[idx]
        self.by_y[b['y']].remove(idx)
        self.grid[(b['x'] >> 3, b['z'] >> 3)].remove(idx)
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
        self.grid[(b['x'] >> 3, b['z'] >> 3)].remove(idx)
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
        lim = SEP_CHEB
        # spatial hash: only blocks within Chebyshev 14 (the widest
        # keep-out radius) can matter, so probe the 8x8 grid cells
        # covering that square instead of scanning 31 full y-rows.
        # The scan is any-quantified (first non-exempt neighbour kills
        # the probe), so iteration order cannot change the result
        for gx in range((x - 14) >> 3, ((x + 14) >> 3) + 1):
            for gz in range((z - 14) >> 3, ((z + 14) >> 3) + 1):
                cell = self.grid.get((gx, gz))
                if not cell:
                    continue
                for i in cell:
                    b = self.blocks[i]
                    if b is None:
                        continue
                    dy = b['y'] - y
                    if dy > SEP_DY or dy < -SEP_DY:
                        continue
                    plim = 14.0 if abs(dy) <= 7 else 12.5
                    d = max(abs(b['x'] - x), abs(b['z'] - z))
                    if dy == 0 and d == 0:
                        return False  # exact cell taken: never allowed,
                                      # kin exemption or not (junction
                                      # connectors can otherwise land ON
                                      # a kin-exempt block - duplicate)
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
                            continue      # lineage neighbour: exempt
                        return False
        return True

    # ---- turn-run rule (TURN_RUN_MIN) --------------------------------------
    def _turn_hist(self, j, ho, n):
        # ride-ordered turn history (newest first, up to n turns) made
        # at block j and its ancestors, where ho is the chord heading
        # leaving j on the ride being checked. Junction blocks have
        # two incoming chords (h from prev, h2 from prev2) and the
        # player may have ridden either, so every arrival path yields
        # its own tuple. Paths end early (shorter tuple) at path
        # starts, None headings or non-lattice chords - unknown
        # history never constrains
        out = []

        def rec(i, hout, acc):
            if len(acc) >= n or i is None or self.blocks[i] is None:
                out.append(acc)
                return
            b = self.blocks[i]
            ext = False
            for p, hin in ((b['prev'], b['h']),
                           (b['prev2'], b.get('h2'))):
                if hin is None:
                    continue
                t = hwrap(hn(hout) - hn(hin))
                if abs(t) != 1:
                    continue
                ext = True
                rec(p, hin, acc + (t,))
            if not ext:
                out.append(acc)
        rec(j, ho, ())
        return out

    def hist_into(self, idx, depth=TURN_RUN_MIN):
        # turn tuples (newest first) made strictly BEFORE the bounce
        # at block idx, one per arrival path - the upstream prefix for
        # flips_ok checks on freshly constructed turn sequences.
        # depth must be >= TURN_RUN_MIN: with less context a run of
        # exactly two turns is indistinguishable from a settled run
        # and a second flip slips through (found by verify())
        jb = self.blocks[idx]
        if jb is None:
            return [()]
        out = []
        for p, hin in ((jb['prev'], jb['h']),
                       (jb['prev2'], jb.get('h2'))):
            if hin is None:
                continue
            out.extend(self._turn_hist(p, hin, depth))
        return out or [()]

    def turn_ok(self, idx, h_next):
        # would a bounce leaving block idx with chord heading h_next
        # obey the turn-run rule on EVERY arrival path into idx? A
        # path forbids the bounce when a direction change happened
        # within its last two turns and h_next does not continue the
        # new direction; a non-lattice bend on any real arrival is
        # always illegal
        jb = self.blocks[idx]
        if jb is None:
            return True
        for p, hin in ((jb['prev'], jb['h']),
                       (jb['prev2'], jb.get('h2'))):
            if hin is None:
                continue
            t_tip = hwrap(hn(h_next) - hn(hin))
            if abs(t_tip) != 1:
                return False
            for ts in self._turn_hist(p, hin, TURN_RUN_MIN):
                if ts and ts[0] != t_tip \
                        and any(t != ts[0] for t in ts[1:]):
                    return False
        return True

    def down_turn_ok(self, top_idx, arr, prev_turn=None):
        # upward mirror of turn_ok: a parent is about to arrive above
        # block top_idx along chord heading `arr` (parent -> top),
        # fixing the downward turn AT top_idx on every ride below.
        # Check the run rule for the changes this creates: at top_idx
        # itself (vs prev_turn, the turn made one bounce earlier on
        # the arriving ride, when the caller knows it) and at the kid
        # below (whose own turn is already fixed). Deeper changes were
        # validated when they were created
        def hold(j, hin, base, need):
            # every ride below block j (incoming chord hin) keeps
            # turning `base` for `need` more bounces; rides that end
            # sooner are truncated runs and legal
            if need <= 0:
                return True
            for k in self.kids.get(j, ()):
                kb = self.blocks[k]
                if kb is None:
                    continue
                hk = kb['h'] if kb['prev'] == j else kb.get('h2')
                if hk is None:
                    continue
                if hwrap(hn(hk) - hn(hin)) != base \
                        or not hold(k, hk, base, need - 1):
                    return False
            return True

        for k in self.kids.get(top_idx, ()):
            kb = self.blocks[k]
            if kb is None:
                continue
            hk = kb['h'] if kb['prev'] == top_idx else kb.get('h2')
            if hk is None:
                continue
            t_top = hwrap(hn(hk) - hn(arr))
            if abs(t_top) != 1:
                return False
            if prev_turn is not None and t_top != prev_turn \
                    and not hold(k, hk, t_top, TURN_RUN_MIN - 1):
                return False
            for k2 in self.kids.get(k, ()):
                k2b = self.blocks[k2]
                if k2b is None:
                    continue
                hk2 = k2b['h'] if k2b['prev'] == k else k2b.get('h2')
                if hk2 is None:
                    continue
                d1 = hwrap(hn(hk2) - hn(hk))
                if abs(d1) != 1:
                    continue
                if d1 != t_top \
                        and not hold(k2, hk2, d1, TURN_RUN_MIN - 1):
                    return False
        return True

    def down_seq(self, j, hin, n):
        # ride-ordered downward turn lists (up to n turns) below block
        # j, one per kid path, using arrival-correct chords; hin is
        # the chord heading into j on the ride being checked. The
        # suffix for flips_ok checks on connector sequences that end
        # on existing corridor
        out = []

        def rec(i, hi, acc):
            if len(acc) >= n:
                out.append(acc)
                return
            ext = False
            for k in self.kids.get(i, ()):
                kb = self.blocks[k]
                if kb is None:
                    continue
                hk = kb['h'] if kb['prev'] == i else kb.get('h2')
                if hk is None:
                    continue
                t = hwrap(hn(hk) - hn(hi))
                if abs(t) != 1:
                    continue
                ext = True
                rec(k, hk, acc + [t])
            if not ext:
                out.append(acc)
        rec(j, hin, [])
        return out

    # ---- branches ----
    def new_branch(self, px, pz, h, d, y, last, golden=False):
        br = {'id': len(self.branches), 'px': px, 'pz': pz, 'h': h, 'dir': d,
              'flip': self.rng.randint(FLIP_MIN, FLIP_MAX),
              'fork': self.rng.randint(FORK_MIN, FORK_MAX),
              'y': y, 'last': last, 'golden': golden, 'alive': True,
              'doomed': False, 'life': 0, 'blocks': [], 'forked': False,
              'lfl': 0, 'pending': None, 'min_stub': MIN_STUB,
              'funnel': False, 'merged': False, 'skip': 0, 'spliced': False,
              'braid': False, 'landing': False,
              'gap': 0}   # incremental bounces-since-fork HINT for the
                          # tip: +1 per step, 1 after a fork, re-synced
                          # from bounces_since_fork() (exact) whenever a
                          # cadence decision is due - the hint only
                          # decides WHEN to pay for the exact check
        self.branches.append(br)
        return br

    def step(self, br, forced=None):
        rlim = max_r(br['y'] - 1)
        if forced is not None:
            cands = [forced]
        elif br.get('noflip'):
            # death-band commitment: no fallback flip either - a
            # blocked committed arm ends instead, carrying a clean
            # constant suffix into the termination tiers
            cands = [br['dir'] if br['flip'] > 0 else -br['dir']]
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
            # turn-run rule: a flip (scheduled OR the blocked-bounce
            # fallback) within two bounces of the previous direction
            # change is illegal on every arrival path into the tip
            if not self.turn_ok(br['last'], h2):
                continue
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
            self.grid[(b['x'] >> 3, b['z'] >> 3)].remove(i)
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
        # v3 LANDING-FIRST: no window search ever happens - the
        # destination is BUILT (splice_landing). If no landing fits at
        # the tip, SHRINK-RETRY: erase a couple of the arm's own leaf
        # blocks (safe non-LIFO: a leaf has no dependants) and retry
        # higher, where the local geometry differs. Only when that is
        # exhausted fall back to the chew (which itself retries a
        # landing at every position on the way up)
        # tier 0: suffix window match - free (no blocks placed)
        if self.splice_suffix(br):
            br['spliced'] = True
            return
        boost = self.precious(br)
        for _attempt in range(6 if boost else 4):
            if boost:
                self.land_boost = True
            try:
                landed = self.splice_landing(br)
            finally:
                self.land_boost = False
            if landed:
                br['spliced'] = True
                return
            # fallback tiers, cheapest capacity first: a v2-style
            # splice onto an EXISTING window (costs no new volume -
            # landing corridors are purpose-built fork-free windows),
            # then a terminal merge (costs m blocks, no tubes)
            if self.splice_tail(br):
                br['spliced'] = True
                return
            if self.merge_end(br):
                return          # merged into a stable corridor:
                                # nothing dead-ends, nothing to splice
            cut = 0
            while cut < 2 and len(br['blocks']) > 1:
                i = br['blocks'][-1]
                if self.blocks[i] is None \
                        or any(self.blocks[k] is not None
                               for k in self.kids.get(i, ())):
                    break
                br['blocks'].pop()
                self.erase_block(i)
                self.unspliced += 1
                cut += 1
            if cut == 0:
                break
            br['last'] = br['blocks'][-1]
        if br['blocks']:
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
            # rescue attempt at EVERY position: while the arm is still
            # long its own suffix serves as the copy source, so the
            # call is one (cheap) junction search - and an early rescue
            # stops the erasure cascade before it eats the arm's forks
            if self.splice_suffix(br, tip_idx=i):
                br['spliced'] = True
                tail_ends.add(self.splices[-1]['copy'][-1])
                continue
            if self.precious(br):
                self.land_boost = True
            try:
                rescued = self.splice_landing(br, tip_idx=i)
            finally:
                self.land_boost = False
            if rescued:
                br['spliced'] = True
                tail_ends.add(self.splices[-1]['copy'][-1])
                continue
            parents = [p for p in (b['prev'], b['prev2'])
                       if p is not None]
            # v3 SAFE-ERASE classification: erasing is free while the
            # parent fork stays surplus; where erasure would break the
            # cap, retry with a boosted landing budget plus a terminal
            # merge before giving in
            unsafe = False
            for p in parents:
                if self.blocks[p] is None:
                    continue
                pk = [k for k in self.kids.get(p, ())
                      if self.blocks[k] is not None and k != i]
                if len(pk) != 1:
                    continue    # p stays a fork (or becomes a leaf:
                                # the cascade will reconsider it)
                if self.bounces_since_fork(p) \
                        + self.down_slack(p, skip=i) > FORK_GAP_MAX:
                    unsafe = True
                    break
            if unsafe:
                self.land_boost = True
                try:
                    ok = self.splice_landing(br, tip_idx=i)
                finally:
                    self.land_boost = False
                if ok:
                    br['spliced'] = True
                    tail_ends.add(self.splices[-1]['copy'][-1])
                    continue
                if self.splice_tail(br, tip_idx=i):
                    br['spliced'] = True
                    tail_ends.add(self.splices[-1]['copy'][-1])
                    continue
                if self.merge_end(br, tip_idx=i):
                    continue    # leaf became a junction arrival
                self.rstats['chew_unsafe'] += 1
            if self.blocks[i] is not None:
                self.erase_block(i)
            self.unspliced += 1     # counts erased blocks
            self.chew_dirty = True  # erasures can retro-lengthen runs
                                    # (a fork whose last decoy died is
                                    # no longer a fork) - tell the
                                    # sweep to re-check cadence
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
            Dj = self.make_braid(D0, used)
            if not Dj:
                continue
            arm = self.branches[-1]
            self.braid_seqs.append(list(arm['blocks']))
            self.braid_list.append({
                'arm': arm['id'], 'fork_idx': g0[D0], 'join_idx': g0[Dj],
                'fy': TRUNK_TOP - D0, 'jy': TRUNK_TOP - Dj})
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
        if not self.turn_ok(B, hd):
            # the mirror turn would flip within two bounces of an
            # upstream direction change (turn-run rule)
            self.rstats['if_runrule'] += 1
            return False
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
        # v3: walk a short stub then BUILD the termination (landing) -
        # the v2 splice-per-level window hunt here was the pre-pass's
        # entire runtime (a 72-window budget burned at every level of
        # every repair arm; the stack profile showed the whole run
        # parked inside it). The fork is the point, not the wander
        child['life'] = min(
            self.rng.randint(MIN_STUB, 10),
            child['y'] - WANDER_FLOOR)
        self.sp_ctx = 'R'
        # plain step() only, hard iteration cap: rewind_retry ADDS life
        # on doomed arms, so an arm pocketed against built corridors
        # cycles forward-1/rewind-3 forever - the postmortem's infinite
        # hang, reproduced here at pre-pass candidate #11. A stranded
        # short arm is fine now: landings reuse the arm's own existing
        # blocks as the copy source (mode A), no open space needed
        # steps cap FORK_GAP_MAX - WINDOW - 1: the arm's landing trigger
        # must stay within the cadence cap (a 20-step walk put the
        # trigger at 21+ and every repair landing died on ld_guard)
        steps = 0
        while child['life'] > 0 and child['y'] - 1 >= WANDER_FLOOR \
                and steps < FORK_GAP_MAX - WINDOW - 1:
            steps += 1
            if self.step(child) is None:
                break
            child['life'] -= 1
        child['alive'] = False
        if self.splice_landing(child):
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
        # failed candidates persist across calls (v3): the world above
        # the sweep only ever gets denser, so a candidate that could
        # not host a fork will not start working later - without this
        # the interleaved calls re-grind the same dead candidates every
        # level (measured: ~100k insert_fork probes per seed)
        failed = self.repair_failed
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
            if os.environ.get('GM_DEBUG'):
                nviol = sum(1 for i, v in d.items()
                            if v > FORK_GAP_MAX and i not in ex
                            and (min_y is None
                                 or self.blocks[i]['y'] > min_y))
                print('[enforce] pass %d: viol=%d starts=%d failed=%d '
                      'rstats=%s' % (_pass, nviol, len(starts),
                                     len(failed), dict(self.rstats)),
                      flush=True)
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
                # v3: braid_repair (a full braid-construction search,
                # tens of seconds per call) is retired here - landings
                # make plain insert_fork repair arms reliable on trunk
                # runs too, and build_braids already provides the
                # mid-maze merges
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
        # the stub's mirror turn is a direction change on the decoy
        # route - the turn-run rule must allow one here
        if not self.turn_ok(last, h2):
            return None
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
            # port-band flip pacing: a port junction is only turn-run
            # legal where the trunk flips right below it (stubs break
            # the 3-bounce hold anywhere else), so keep runs short in
            # the band to manufacture flip points for make_port
            if PORT_MIN - 2 <= TRUNK_TOP - g['y'] <= PORT_MAX + 2:
                g['flip'] = min(g['flip'], TURN_RUN_MIN + 2)
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
                self.rstats['port_junc'] += 1
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
                self.rstats['port_kids'] += 1
                continue          # golden fork or reserved decoy at J
            kb = self.blocks[kids_live[0]]
            if kb['h'] is None:
                continue
            t = hwrap(hn(kb['h']) - hn(jb['h']))
            if abs(t) != 1:
                continue
            arr2 = jb['h'] + 2 * t * TURN
            # turn-run rule: the port ride turns -t at J; if the trunk
            # below J does not continue with two more -t bounces this
            # depth cannot host a port
            if not self.down_turn_ok(J, arr2):
                self.rstats['port_runrule'] += 1
                continue
            sx = jb['px'] - CHORD * math.cos(arr2)
            sz = jb['pz'] - CHORD * math.sin(arr2)
            u = jb['y'] + 1
            if not self.clear(rnd(sx), rnd(sz), u, None,
                              extra=[(J, 1)]):
                self.rstats['port_clear'] += 1
                continue
            # escape probe, turn-run aware: the funnel's first climb
            # turn tt is legal only when it continues the junction's
            # -t turn, or when the trunk itself runs -t below J (the
            # hold case). Probe 3 bounces up the legal direction(s) -
            # a port whose only legal escape is walled is dead on
            # arrival and must be rejected here, not after 6 failed
            # grow attempts
            k1 = k2t = None
            kk = [k for k in self.kids.get(kids_live[0], ())
                  if self.blocks[k] is not None]
            if len(kk) == 1 and self.blocks[kk[0]]['h'] is not None:
                k1 = hwrap(hn(self.blocks[kk[0]]['h']) - hn(kb['h']))
                kk2 = [k for k in self.kids.get(kk[0], ())
                       if self.blocks[k] is not None]
                if len(kk2) == 1 \
                        and self.blocks[kk2[0]]['h'] is not None:
                    k2t = hwrap(hn(self.blocks[kk2[0]]['h'])
                                - hn(self.blocks[kk[0]]['h']))
            legal = [-t]
            if k1 == -t and k2t == -t:
                legal.append(t)
            esc = False
            for tt in legal:
                ok3 = True
                arr, ex, ez = arr2, sx, sz
                for li in range(1, TURN_RUN_MIN + 1):
                    arr -= tt * TURN
                    ex -= CHORD * math.cos(arr)
                    ez -= CHORD * math.sin(arr)
                    if not self.clear(rnd(ex), rnd(ez), u + li, None,
                                      extra=[(J, 1 + li)]):
                        ok3 = False
                        break
                if ok3:
                    esc = True
                    break
            if not esc:
                self.rstats['port_esc'] += 1
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
    # ---- bubble braids (pre-terminated cadence forks) -----------------------
    def bubble_at(self, B, K):
        # BUBBLE spawn: fork at static-corridor block B (continuation
        # kid K) whose decoy arm will be terminated AT BUILD TIME
        # (bubble_close). Cadence gets its fork the moment the
        # child's first block lands, and the arm never joins the
        # runtime termination economy: no doomed walk, no chew, no
        # repair, no pad reservation. Replaces the funnel stubs,
        # whose arms were the largest unpayable termination bill
        # (2026-08-09 4-seed evidence: farms, steering and
        # pad-relaxation all failed to pay it; per-type viol was
        # dominated by stub-loss runs on funnel corridors)
        bb, kb = self.blocks[B], self.blocks[K]
        if bb is None or kb is None or bb['h'] is None \
                or bb['px'] is None or kb['h'] is None \
                or bb['prev2'] is not None or kb['prev2'] is not None \
                or B in self.win_used or self.is_multi(B) \
                or self.is_multi(K):
            return None
        t = hwrap(hn(kb['h']) - hn(bb['h']))
        if abs(t) != 1:
            return None
        # decoy first bounce mirrors the corridor turn (try_fork
        # shape) plus a short natural wander. The rejoin happens in a
        # SECOND pass (bubble_close): a rejoin is an ARRIVAL, and
        # down_slack demands forks below the junction - which are
        # exactly what this pass is still creating top-down
        # (me_slack 1749 killed the single-pass version)
        child = self.new_branch(bb['px'], bb['pz'], bb['h'], -t,
                                bb['y'], B)
        child['flip'] = max(child['flip'], FORK_TURN_LOCK)
        # constant-arc walk to a full WINDOW+1 suffix: an arm carrying
        # its whole copy stretch lands with need=0, so the landing
        # places only the translated copy (out in the empty annulus) -
        # no growth in the crowded funnel disk. noflip matters: a
        # fallback flip mid-walk would break the constant suffix and
        # the arm could never host a trigger (user rule)
        child['noflip'] = True
        ok = self.step(child, forced=-t) is not None
        walked = 1
        wmax = self.rng.randint(WINDOW + 1, WINDOW + 4)
        while ok and walked < wmax:
            ok = self.step(child) is not None
            walked += 1
        if not ok and walked >= 2:
            ok = True      # a shorter wrong corridor still splices
        if ok:
            self.forks.append({
                'br': bb['br'], 'decoy': child['id'],
                'parent_idx': B, 'cont_idx': K,
                'decoy_idx': child['blocks'][0], 'y': bb['y'],
                'golden': False})
            return child
        for i in reversed(child['blocks']):
            if self.blocks[i] is not None:
                self.pop_block(i)
        self.branches.pop()
        self.rstats['bub_nospawn'] += 1
        return None

    def bubble_close(self, child):
        # pass 2: terminate the spawned arm IN THE EMPTY WORLD, where
        # every runtime killer is absent. splice_tail first - its
        # translation delta is a free variable, so unlike a merge it
        # needs no half-block-precise arrival (merge closers measured
        # ~0/63: the exact-solve reach set is too sparse - the old v2
        # unsteered-merge lesson). At build time arc placement is
        # nearly free, no tails exist to chain-reject, and the entry
        # corridors above are fresh window supply. merge_end stays as
        # a rare lucky fallback. Failure erases the arm (non-LIFO -
        # later spawns sit above it in the store) and reports False
        # so the caller can fall back to a classic stub promise
        prev_boost = getattr(self, 'splice_boost', False)
        self.splice_boost = True
        try:
            if self.splice_tail(child):
                child['spliced'] = True
                child['alive'] = False
                self.rstats['bub_ok'] += 1
                return True
        finally:
            self.splice_boost = prev_boost
        # LANDING tier for bubbles (turn-run rework): windows legal
        # for splice_tail are scarcer now (constant-direction only),
        # but a landing BUILDS its destination and the world is at its
        # thinnest here - placement is nearly free
        self.land_boost = True
        try:
            if self.splice_landing(child):
                child['spliced'] = True
                child['alive'] = False
                self.rstats['bub_ok'] += 1
                return True
        finally:
            self.land_boost = False
        if self.merge_end(child):
            child['funnel'] = True
            self.rstats['bub_ok'] += 1
            return True
        for i in reversed(child['blocks']):
            if self.blocks[i] is not None:
                self.erase_block(i)
        child['blocks'] = []
        child['alive'] = False
        self.forks = [f for f in self.forks
                      if f['decoy'] != child['id']]
        self.rstats['bub_fail'] += 1
        return False

    def bubble_along(self, seq, gap_lo=6, gap_hi=10):
        # pass 1: spawn bubble fork arms every gap_lo..gap_hi levels.
        # The fork exists the moment the child's first block lands -
        # cadence is served immediately; the rejoins wait for
        # bubble_close once every corridor's forks are down.
        # Returns (child, forkblock, contblock) triples
        out = []
        timer = self.rng.randint(gap_lo, gap_hi)
        for n in range(len(seq) - 1):
            timer -= 1
            if timer > 0:
                continue
            ch = self.bubble_at(seq[n], seq[n + 1])
            if ch is not None:
                out.append((ch, seq[n], seq[n + 1]))
                timer = self.rng.randint(gap_lo, gap_hi)
            else:
                timer = 1
        return out

    def braid_join_at(self, D1c, used):
        # slot data for a candidate braid rejoin at trunk depth D1c,
        # or None if the junction there would be illegal. Split out of
        # make_braid so a descending arm can try EVERY legal join in
        # its band: the turn-run rule thins connector shapes so much
        # that a single pre-chosen slot almost never matches
        if any(abs(D1c - u) < BRAID_SPACING for u in used):
            return None
        if not self.trunk_junc_free(D1c, 1):
            return None
        g0 = self.branches[0]['blocks']
        J = g0[D1c]
        jb = self.blocks[J]
        if jb is None or jb['h'] is None or jb['prev2'] is not None:
            return None
        jkids = [k for k in self.kids.get(J, ())
                 if self.blocks[k] is not None]
        if len(jkids) != 1:
            return None
        kb = self.blocks[jkids[0]]
        if kb['h'] is None:
            return None
        t_j = hwrap(hn(kb['h']) - hn(jb['h']))
        if abs(t_j) != 1:
            return None
        # (the old steer-era same-side requirement t_j == t_c is gone:
        # the shape solver can approach a slot from either side)
        arr2 = jb['h'] + 2 * t_j * TURN
        return (D1c, J,
                arr2,
                jb['px'] - CHORD * math.cos(arr2),
                jb['pz'] - CHORD * math.sin(arr2),
                jb['y'] + 1)

    def make_braid(self, D0, used):
        # one braid: fork OFF the golden trunk at depth D0 and land
        # back ON the trunk at some legal join in the braid band - an
        # alternate winning route. Returns the ACTUAL join depth or
        # False. Both trunk ends must be junction-free
        # (trunk_junc_free): a junction beside a junction hangs its
        # side arms within a few blocks of each other, which the
        # separation grading forbids. The arm's mid blocks are far-kin
        # from the mid-trunk, so clear() keeps the corridors apart
        if any(abs(D0 - u) < BRAID_SPACING for u in used):
            self.bstats['spacing'] += 1
            return False
        if not self.trunk_junc_free(D0, 1):
            self.bstats['junction'] += 1
            return False
        g0 = self.branches[0]['blocks']
        F = g0[D0]
        fb = self.blocks[F]
        if fb is None or fb['h'] is None or fb['prev2'] is not None:
            self.bstats['geometry'] += 1
            return False
        fkids = [k for k in self.kids.get(F, ())
                 if self.blocks[k] is not None]
        if len(fkids) != 1:
            self.bstats['kids'] += 1
            return False
        cb = self.blocks[fkids[0]]
        if cb['h'] is None:
            self.bstats['geometry'] += 1
            return False
        t_c = hwrap(hn(cb['h']) - hn(fb['h']))
        if abs(t_c) != 1:
            self.bstats['geometry'] += 1
            return False
        # every legal join slot in the band; the shape solver connects
        # to whichever slot a run-legal arm actually reaches
        joins = []
        for D1c in range(D0 + BRAID_LEN_MIN,
                         min(D0 + BRAID_LEN_MAX, len(g0) - 2) + 1):
            jn = self.braid_join_at(D1c, used)
            if jn is not None:
                joins.append(jn)
        if not joins:
            self.bstats['nojoin'] += 1
            return False
        # SOLVER (turn-run rework): the old steer-then-connect walk got
        # zero braids under the run rule - legal connector shapes are
        # too sparse for a blind approach ride to ever line up with
        # one. Enumerate the arm SHAPES directly instead: every
        # run-legal turn sequence is a composition of the bounce count
        # into maximal runs >= TURN_RUN_MIN, signs alternating from
        # the fork mirror (-t_c). Filter by final heading (mod 16),
        # boundary legality (flips_ok incl. trunk turns above F and
        # below J), then a float walk with an exact arrival check, and
        # only then place blocks (LIFO rollback)
        if not self.turn_ok(F, fb['h'] - t_c * TURN):
            self.bstats['lock'] += 1
            return False
        pre_hists = [list(reversed(ts)) for ts in self.hist_into(F)]
        self.rng.shuffle(joins)
        for D1c, Jc, arr2c, sxc, szc, syc in joins:
            jb2 = self.blocks[Jc]
            L = fb['y'] - syc
            if L < 4:
                continue
            gaps = {}
            for fin_off in (-1, 1):
                gaps[(hn(arr2c) + fin_off - hn(fb['h'])) % 16] = fin_off
            ds = self.down_seq(Jc, arr2c, 4)
            for comp in run_comps(L):
                s_alt = sum(p * (1, -1)[i % 2]
                            for i, p in enumerate(comp))
                fin_off = gaps.get((-t_c * s_alt) % 16)
                if fin_off is None:
                    continue
                turns = []
                sgn = -t_c
                for p in comp:
                    turns.extend([sgn] * p)
                    sgn = -sgn
                if not all(flips_ok(ph + turns + [-fin_off] + d2)
                           for ph in pre_hists for d2 in ds):
                    continue
                # float walk + exact arrival check, no blocks placed
                px, pz, h = fb['px'], fb['pz'], fb['h']
                pts = []
                ok = True
                for tt in turns:
                    h += tt * TURN
                    px += CHORD * math.cos(h)
                    pz += CHORD * math.sin(h)
                    if math.hypot(px - START_X, pz - START_Z) \
                            > max_r(fb['y'] - len(pts) - 1):
                        ok = False
                        break
                    pts.append((px, pz, h))
                if not ok or math.hypot(px - sxc, pz - szc) > MERGE_TOL:
                    self.bstats['miss'] += 1
                    continue
                br = self.new_branch(fb['px'], fb['pz'], fb['h'], -t_c,
                                     fb['y'], F)
                br['alive'] = False
                br['braid'] = True
                placed = []
                last = F
                for si, (qx, qz, qh) in enumerate(pts):
                    bx, bz = rnd(qx), rnd(qz)
                    yy = fb['y'] - si - 1
                    if (not chord_int_ok(bx, bz,
                                         self.blocks[last]['x'],
                                         self.blocks[last]['z'])
                            or (si == L - 1 and not chord_int_ok(
                                bx, bz, jb2['x'], jb2['z']))
                            or not self.clear(bx, bz, yy, last,
                                              extra=[(Jc, L - si)])):
                        break
                    last = self.place(bx, yy, bz, last, br['id'],
                                      f=(qx, qz, qh))
                    placed.append(last)
                if len(placed) != L:
                    for i in reversed(placed):
                        self.pop_block(i)
                    assert self.branches[-1] is br
                    self.branches.pop()
                    self.bstats['place'] += 1
                    self.bstats['place_%d' % (3 * len(placed) // L)] += 1
                    continue
                br['blocks'] = placed
                br['last'] = last
                br['px'], br['pz'], br['h'] = pts[-1]
                br['y'] = syc
                br['merged'] = True
                self.set_prev(Jc, last)
                jb2['h2'] = arr2c
                self.bstats['ok'] += 1
                return D1c
        self.bstats['nofit'] += 1
        return False

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
        # (the steer-era alley pre-screen is gone: the shape solver
        # does not hug a 15-block alley, and placement clear() is the
        # real arbiter)
        d0s = sorted(tdir)
        self.rng.shuffle(d0s)
        used = []
        for D0 in d0s[:BRAID_TRIES]:
            if len(self.braid_list) >= BRAIDS:
                break
            Dj = self.make_braid(D0, used)
            if not Dj:
                continue
            used += [D0, Dj]
            arm = self.branches[-1]
            self.braid_seqs.append(list(arm['blocks']))
            self.braid_list.append({
                'arm': arm['id'], 'fork_idx': g0[D0], 'join_idx': g0[Dj],
                'fy': TRUNK_TOP - D0, 'jy': TRUNK_TOP - Dj})
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
                    self.fstats['grow_budget'] += 1
                    return False
                if cor['y'] >= START_Y:
                    if cor['quota'] != 1:
                        self.fstats['grow_quota'] += 1
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
                        # turn-run rule: each arrival fixes a new
                        # downward turn at the junction top - the
                        # corridor's last turns below must be able to
                        # absorb the change (down_turn_ok)
                        if not self.down_turn_ok(cor['top'], arr):
                            self.rstats['fun_jrunrule'] += 1
                            got = False
                            break
                        if (math.hypot(nx - START_X,
                                       nz - START_Z) > max_r(u)
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
                    # (8..12: runs must span WINDOW+1 blocks now that
                    # windows are constant-direction)
                    cor['dir'] = max((-1, 1), key=sector_score)
                    cor['flip'] = self.rng.randint(8, 12)
                # the corridor's current downward run direction: the
                # turn at its top kid (None right after a junction).
                # Chords must be ARRIVAL-CORRECT: a port slot's kid is
                # the trunk junction, whose slot-side chord is h2, not
                # h (reading h deadlocked every port funnel)
                t_run = None
                kid0 = next((k for k in self.kids.get(cor['top'], ())
                             if self.blocks[k] is not None), None)
                if kid0 is not None:
                    kb0 = self.blocks[kid0]
                    h_k0 = kb0['h'] if kb0['prev'] == cor['top'] \
                        else kb0.get('h2')
                    k2 = next((k for k in self.kids.get(kid0, ())
                               if self.blocks[k] is not None), None)
                    if k2 is not None and h_k0 is not None:
                        k2b = self.blocks[k2]
                        h_k2 = k2b['h'] if k2b['prev'] == kid0 \
                            else k2b.get('h2')
                        if h_k2 is not None:
                            tr = hwrap(hn(h_k2) - hn(h_k0))
                            if abs(tr) == 1:
                                t_run = tr
                order = (cor['dir'], -cor['dir'])
                stepped = False
                for t in order:
                    arr = cor['ho'] - t * TURN
                    nx = cor['px'] - CHORD * math.cos(arr)
                    nz = cor['pz'] - CHORD * math.sin(arr)
                    bx, bz = rnd(nx), rnd(nz)
                    # turn-run rule (upward mirror): the new parent
                    # fixes the downward turn at the current top -
                    # a change there must keep the run below intact
                    if not self.down_turn_ok(cor['top'], arr):
                        self.rstats['fun_runrule'] += 1
                        continue
                    if (math.hypot(nx - START_X,
                                   nz - START_Z) > max_r(u)
                            or not self.clear(bx, bz, u, None,
                                              extra=[(cor['top'], 1)])):
                        self.rstats['fun_clear'] += 1
                        continue
                    # a direction change commits the next
                    # TURN_RUN_MIN-1 bounces to the same turn -
                    # prescreen those positions so doomed changes are
                    # pruned before they cost blocks and rewinds
                    if t_run is not None and t != t_run:
                        la_ok = True
                        lx, lz, lh = nx, nz, arr
                        for li in range(1, TURN_RUN_MIN):
                            lh -= t * TURN
                            lx -= CHORD * math.cos(lh)
                            lz -= CHORD * math.sin(lh)
                            if (math.hypot(lx - START_X, lz - START_Z)
                                    > max_r(u + li)
                                    or not self.clear(
                                        rnd(lx), rnd(lz), u + li, None,
                                        extra=[(cor['top'], 1 + li)])):
                                la_ok = False
                                break
                        if not la_ok:
                            self.rstats['fun_lookahead'] += 1
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
                    if attempts > 400:
                        self.fstats['grow_attempts'] += 1
                        return False
                    depth = min(2 + attempts // 3, 14)
                    if not rewind(cor, self.rng.randint(2, depth)):
                        cor['dir'] = -cor['dir']
                    cor['flip'] = self.rng.randint(1, FLIP_MAX)
        return True

    # ---- splice windows -----------------------------------------------------
    # ---- window farm (build-time co-reservation) ---------------------------
    def farm_at(self, J, K):
        # try to erect one window corridor rooted at static-corridor
        # block J (continuation kid K): an exactly-solved junction
        # arrival (same shape as landing_for_tail's connector) plus a
        # free UPWARD wander - both endpoints are never constrained at
        # once, so no exact solve can fail; only clear() can. The top
        # WINDOW+1 stretches register as shareable 'farm' windows
        jb, kb = self.blocks[J], self.blocks[K]
        if jb is None or kb is None or jb['h'] is None \
                or jb['px'] is None or kb['h'] is None \
                or jb['prev2'] is not None or kb['prev2'] is not None:
            return False
        jy = jb['y']
        if not any(lo <= jy <= hi for lo, hi in FARM_ZONES):
            return False
        kids = [k for k in self.kids.get(J, ())
                if self.blocks[k] is not None]
        if len(kids) != 1 or J in self.win_used \
                or kids[0] in self.win_used or self.is_multi(kids[0]):
            return False
        pv = jb['prev']
        if pv is not None and (self.blocks[pv] is None
                               or self.is_multi(pv)
                               or pv in self.win_used):
            return False
        t = hwrap(hn(kb['h']) - hn(jb['h']))
        if abs(t) != 1:
            return False
        # the farm ride arrives at J carrying WINDOW+1+m bounces from
        # its leaf top, and a junction resets nothing - same guard as
        # landings: the run below J must still fit in the cap
        slack = self.down_slack(J)
        m_max = min(8, FORK_GAP_MAX - WINDOW - 2 - slack,
                    FARM_TOP_CAP - jy - WINDOW - 1)
        if m_max < 3:
            self.rstats['farm_slack'] += 1
            return False
        arr2 = jb['h'] + 2 * t * TURN
        sx = jb['px'] - CHORD * math.cos(arr2)
        sz = jb['pz'] - CHORD * math.sin(arr2)
        # free space around a root is a narrow wedge between the
        # parent corridor's own outward ascent and the neighbor
        # funnel corridors (~2*pi*r/10 apart): blind drift bearings
        # walked into walls ~85% of the time (farm_clear0). Measure
        # instead: grid-probe the swept slab along 12 bearings and
        # walk only into the emptiest wedges
        ux = jb['px'] - kb['px']
        uz = jb['pz'] - kb['pz']
        un = math.hypot(ux, uz) or 1.0
        ux, uz = ux / un, uz / un
        bearings = []
        taken = [(fx, fz, ftx, ftz)
                 for fx, fz, ftx, ftz in getattr(self, 'farm_dirs', ())
                 if max(abs(fx - jb['px']), abs(fz - jb['pz'])) < 48]
        for k in range(12):
            ang = math.tau * k / 12.0
            bx_, bz_ = math.cos(ang), math.sin(ang)
            if bx_ * ux + bz_ * uz > 0.7:
                continue      # the parent's own ascent cone
            if any(bx_ * ftx + bz_ * ftz > 0.5 for _, _, ftx, ftz
                   in taken):
                continue      # a nearby farm already owns this wedge:
                              # parallel farms a few levels apart sit
                              # inside SEP_DY and always collide (the
                              # one-farm-per-corridor plateau)
            n = 0
            for step in (16, 32, 48):
                cxp = rnd(jb['px'] + bx_ * step)
                czp = rnd(jb['pz'] + bz_ * step)
                if math.hypot(cxp - START_X, czp - START_Z) \
                        > max_r(jy) + LAND_R_EXTRA - 8:
                    n += 30   # bearing exits the buildable disk
                    continue
                for gx in range((cxp - 10) >> 3, ((cxp + 10) >> 3) + 1):
                    for gz in range((czp - 10) >> 3,
                                    ((czp + 10) >> 3) + 1):
                        for i in self.grid.get((gx, gz), ()):
                            b2 = self.blocks[i]
                            if b2 is not None \
                                    and jy - 4 <= b2['y'] <= jy + 20:
                                n += 1
            bearings.append((n + self.rng.random(), bx_, bz_))
        if not bearings:
            self.rstats['farm_fail'] += 1
            return False
        bearings.sort()
        ds0 = self.down_seq(J, arr2, 3)
        for _try in range(FARM_WALK_TRIES):
            m = self.rng.randint(3, m_max)
            L = m + WINDOW + 1
            _, tx, tz = bearings[_try % len(bearings)]
            # the arrival block's own heading is one turn short of the
            # arrival chord (the player turns +-1 onto J's slot)
            ta = self.rng.choice((-1, 1))
            chain = [(sx, sz, arr2 - ta * TURN, jy + 1)]
            # turn-run rule bookkeeping: tl[i] = downward turn at
            # chain[i], seeded with the junction turn and the trunk
            # turns below so boundary changes keep their runs; the top
            # WINDOW+1 blocks must additionally be CONSTANT-turn (they
            # are the registered farm windows)
            seed = (list(reversed(ds0[0])) if ds0 else []) + [-t]
            tl = list(seed) + [ta]
            ok = True
            while len(chain) < L:
                px, pz, h, y = chain[-1]
                ppx = px - CHORD * math.cos(h)
                ppz = pz - CHORD * math.sin(h)
                if math.hypot(ppx - START_X, ppz - START_Z) \
                        > max_r(y + 1) + LAND_R_EXTRA:
                    self.rstats['farm_rad'] += 1
                    ok = False
                    break
                # turn INTO this block = heading of the block above.
                # The initial heading is fixed by the junction arrival
                # and usually points at the crowded interior; a fixed
                # drift target cannot see the walls on the way there
                # (the 22.5deg/step swing takes up to 8 bounces). Probe
                # instead: two-step lookahead per heading choice, pick
                # the emptier side, drift target only as tiebreak
                sc = []
                for hp in (h - TURN, h + TURN):
                    tn = 1 if hp == h - TURN else -1
                    # run rule: a differing turn is only legal after
                    # three settled bounces; the window section (the
                    # top WINDOW+1 blocks) never changes direction
                    if tn != tl[-1]:
                        if len(chain) >= L - WINDOW:
                            continue
                        if any(v != tl[-1] for v in tl[-3:]):
                            continue
                    qx = rnd(ppx - CHORD * 1.6 * math.cos(hp))
                    qz = rnd(ppz - CHORD * 1.6 * math.sin(hp))
                    n = 0
                    for gx in range((qx - 8) >> 3, ((qx + 8) >> 3) + 1):
                        for gz in range((qz - 8) >> 3,
                                        ((qz + 8) >> 3) + 1):
                            for i3 in self.grid.get((gx, gz), ()):
                                b3 = self.blocks[i3]
                                if b3 is not None \
                                        and abs(b3['y'] - (y + 2)) \
                                        <= SEP_DY:
                                    n += 1
                    o = -(math.cos(hp) * tx + math.sin(hp) * tz)
                    sc.append((n, -o, hp))
                if not sc:
                    ok = False
                    break
                sc.sort()
                hp = sc[0][2] if self.rng.random() > 0.1 else sc[-1][2]
                tl.append(1 if hp == h - TURN else -1)
                chain.append((ppx, ppz, hp, y + 1))
            if not ok:
                continue
            # full-ride re-check over every trunk path below the
            # junction (the greedy seed used only the first path)
            ride = list(reversed(tl[len(seed):])) + [-t]
            if any(not flips_ok(ride + ds)
                   for ds in self.down_seq(J, arr2, 3)):
                self.rstats['farm_runrule'] += 1
                continue
            placed = []
            last = None
            for i2, (px, pz, h, y) in enumerate(reversed(chain)):
                bx, bz = rnd(px), rnd(pz)
                if last is not None and not chord_int_ok(
                        bx, bz, self.blocks[last]['x'],
                        self.blocks[last]['z']):
                    self.rstats['farm_chord'] += 1
                    ok = False
                    break
                if i2 == L - 1 and not chord_int_ok(
                        bx, bz, jb['x'], jb['z']):
                    self.rstats['farm_chord'] += 1
                    ok = False
                    break
                if not self.clear(bx, bz, y, last,
                                  extra=[(J, L - i2)]):
                    self.rstats['farm_clear%d' % (3 * i2 // L)] += 1
                    if os.environ.get('GM_FARMDBG') \
                            and self.rstats.get('farm_dbg', 0) < 12:
                        self.rstats['farm_dbg'] += 1
                        near = []
                        for gx in range((bx - 14) >> 3,
                                        ((bx + 14) >> 3) + 1):
                            for gz in range((bz - 14) >> 3,
                                            ((bz + 14) >> 3) + 1):
                                for i3 in self.grid.get((gx, gz), ()):
                                    b3 = self.blocks[i3]
                                    if b3 is None or abs(b3['y'] - y) \
                                            > SEP_DY:
                                        continue
                                    d3 = max(abs(b3['x'] - bx),
                                             abs(b3['z'] - bz))
                                    if d3 < 14:
                                        near.append(
                                            (d3, b3['y'] - y, b3['br']))
                        near.sort()
                        print('[farmdbg] jy=%d i2=%d/%d blockers=%s'
                              % (jy, i2, L, near[:4]), flush=True)
                    ok = False
                    break
                last = self.place(bx, y, bz, last, -3, f=(px, pz, h))
                placed.append(last)
            if not ok:
                for i2 in reversed(placed):
                    self.pop_block(i2)
                continue
            lastb = self.blocks[last]
            lb = self.new_branch(lastb['px'], lastb['pz'], lastb['h'],
                                 ta, lastb['y'], last)
            lb['alive'] = False
            lb['landing'] = True
            lb['merged'] = True
            lb['blocks'] = list(placed)
            for i2 in placed:
                self.blocks[i2]['br'] = lb['id']
            self.set_prev(J, last)
            jb['h2'] = arr2
            wins = []
            self.scan_seq_windows(lb['blocks'], wins)
            for w in wins:
                w['farm'] = True
            self.windows.extend(wins)
            self.rstats['farm_ok'] += 1
            self.rstats['farm_ok_hi' if jy >= FARM_ZONES[0][0]
                        else 'farm_ok_lo'] += 1
            self.rstats['farm_win'] += len(wins)
            if not hasattr(self, 'farm_dirs'):
                self.farm_dirs = []
            self.farm_dirs.append((jb['px'], jb['pz'], tx, tz))
            return True
        self.rstats['farm_fail'] += 1
        return False

    def build_window_farm(self):
        # default OFF (GM_FARM=1 re-enables): 4-seed A/B measured
        # 107/124/151/116 vs 98/61/119/130 baseline - the ~17
        # window uses per seed do not pay for the interior congestion
        # the farm connectors add near their roots
        if os.environ.get('GM_FARM') != '1':
            return
        # pre-build shareable window corridors along the static maze,
        # in the zones where the 98-viol baseline measured zero
        # termination capacity (FARM_ZONES). Runs at build time, right
        # after the cadence stubs (down_slack must see them), while
        # the world is ~1000 blocks: placement almost never fails, and
        # every farm bought here is a termination that does not have
        # to fight the saturated mid-band later
        seqs = ([self.branches[0]['blocks']] + self.funnel_seqs
                + self.braid_seqs)
        for seq in seqs:
            timer = self.rng.randint(FARM_GAP_LO, FARM_GAP_HI)
            for n in range(len(seq) - 1):
                timer -= 1
                if timer > 0:
                    continue
                if self.farm_at(seq[n], seq[n + 1]):
                    timer = self.rng.randint(FARM_GAP_LO, FARM_GAP_HI)
                else:
                    timer = 1

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
            # user rule (2026-08-15): windows are CONSTANT-direction.
            # The replica tail is an exact copy of the window, and the
            # player rides it past the trigger blocks - if it flipped
            # direction it could S-bend back and bring its own dead
            # end into view before the teleport fires
            if any(t != turns[0] for t in turns):
                continue
            # 'dw' is the window's ENTRY turn (the turn into its first
            # copied block, equal to every other turn now): the
            # alignment arc must end one turn short of the first copy
            # chord
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
                                  not w.get('farm'),
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
            # v3 SPLICE_SUPPRESS: a window overlapping a replica tail
            # would teleport the player straight onto (or within a few
            # bounces of) that tail's OWN trigger - the v2 "sanctioned
            # chain". The 5-bounce suppression rule forbids it: chains
            # now happen only through landings, whose ride back to the
            # maze is >= WINDOW - 1 + connector bounces long
            if any(j in tail_blocks for j in w['blocks']):
                self.rstats[self.sp_ctx + 'sp_chainrej'] += 1
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
            # turn-run rule over the whole tail: recent turns into the
            # tip, then the constant alignment arc, then the window's
            # constant turns (dw x WINDOW). Rejects arcs that flip too
            # close to an upstream change AND arc->window boundaries
            # that S-bend right before the trigger
            tail_turns = [1 if g > 0 else -1] * abs(g) \
                + [w['dw']] * WINDOW
            if any(not flips_ok(list(reversed(ts)) + tail_turns)
                   for ts in self.hist_into(tip_idx)):
                self.rstats[self.sp_ctx + 'sp_runrule'] += 1
                continue
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
                        or not chord_int_ok(
                            bx, bz, self.blocks[last]['x'],
                            self.blocks[last]['z'])
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
                if w.get('farm'):
                    self.rstats[self.sp_ctx + 'sp_farm'] += 1
                if tip_y >= FARM_ZONES[0][0]:
                    self.rstats[self.sp_ctx + 'sp_hi'] += 1
                return True
            for i in reversed(placed):
                self.pop_block(i)
        return False

    def splice_landing(self, br, tip_idx=None):
        # LANDING splice (user-designed): when no existing window fits
        # the dying arm, keep the seamless-teleport rule by BUILDING
        # the destination instead of finding one. The arm grows a
        # fork-free 8-bounce tail; an exact integer-translated copy of
        # [tip + tail] is erected elsewhere as a LANDING BRANCH: a
        # corridor that starts in mid-air (parentless - the player can
        # only ever be teleported onto it, new territory by
        # construction) and, past the copied stretch, runs an
        # m-bounce connector that merges onto a STABLE corridor with
        # the standard junction shape. The translation delta is a free
        # variable, solved backwards from the junction, so the landing
        # arrives exactly. Cadence: the landing root is a path start
        # (d=0, fork_gap_map gives parentless blocks 0), the ride to
        # the junction is 8 + m + 1 <= 17 bounces, the trigger sits
        # d_tip + 1 past the arm's last fork.
        #
        # SEARCH DISCIPLINE (v2, the postmortem rewrite): everything
        # speculative is placed via place() and unwound via
        # pop_block() strict LIFO, the same protocol as splice_tail.
        # The v1 implementation borrowed the branch-walk machinery
        # (step + rewind_retry) whose non-LIFO erases can neither be
        # bounded (forward-1/rewind-3 cycles hang forever) nor rolled
        # back (rollback() cannot restore what rewinds erased -> the
        # chew crashes on blocks a failed attempt ate). No shared
        # branch state is touched until the commit point.
        self.rstats['ld_call'] += 1
        if tip_idx is None:
            tip_idx = br['last']
        tip = self.blocks[tip_idx]
        if tip is None or tip['h'] is None or tip['px'] is None:
            return False
        g_tip = self.bounces_since_fork(tip_idx)
        # HYBRID TAIL (postmortem fix plan #1, generalized): the copy
        # source is WINDOW+1 consecutive fork-free blocks ending at the
        # dead end. Reuse the longest valid SUFFIX of the arm's own
        # blocks (already placed - needs no open space) and grow only
        # the missing bounces. An arm terminated by the cadence
        # backstop is forkless for 12+ bounces, so its landing usually
        # places ZERO new blocks; a freshly-forked arm grows a few.
        # Pure fresh growth (the old mode B) failed ld_nofit ~200k
        # times per seed in the busy band - 7 clear bounces rarely
        # exist there, but 0-3 usually do
        suffix = [tip_idx]
        t_suf = None       # the copy stretch must be CONSTANT-turn
                           # (user rule: no flips past the trigger)
        blocks_ = br['blocks']
        if tip_idx in blocks_:
            pos = len(blocks_) - 1 - blocks_[::-1].index(tip_idx)
            j = pos
            while len(suffix) < WINDOW + 1 and j > 0:
                cand = blocks_[j - 1]
                cb = self.blocks[cand]
                nb = self.blocks[suffix[0]]
                if (cb is None or cb['h'] is None or cb['px'] is None
                        or cb['prev2'] is not None
                        or nb['prev'] != cand
                        or cand in self.win_used
                        or sum(1 for k in self.kids.get(cand, ())
                               if self.blocks[k] is not None) > 1):
                    break
                t = hwrap(hn(nb['h']) - hn(cb['h']))
                if abs(t) != 1 or (t_suf is not None and t != t_suf):
                    break
                t_suf = t
                suffix.insert(0, cand)
                j -= 1
        need = WINDOW + 1 - len(suffix)
        # cadence guard on the TRIGGER, not the tip: the trigger is
        # copy[0] = S[1], which for a full suffix sits WINDOW-1 bounces
        # ABOVE the tip - so an arm may walk to gap ~26 and still land
        # legally (the copy past the trigger is exempt). The old
        # tip-based guard threw away ~7 retry levels per arm
        if g_tip - (len(suffix) - 2) > FORK_GAP_MAX:
            self.rstats['ld_guard'] += 1
            return False
        if tip['y'] - need < MORTAL_FLOOR:
            self.rstats['ld_mortal'] += 1
            return False
        if need == 0:
            if self.landing_for_tail(br, suffix[0], suffix[1:],
                                     new_placed=[]):
                self.rstats['ld_own'] += 1
                return True
            self.rstats['ld_nofit'] += 1
            return False
        dir0 = br['dir'] if br['dir'] in (-1, 1) \
            else self.rng.choice((-1, 1))
        # candidate shapes for the grown part: CONSTANT arcs only
        # (user rule: the copy stretch may never flip direction). A
        # suffix with a known turn fixes the direction; a bare tip may
        # try either chirality, subject to the turn-run rule upstream
        if t_suf is not None:
            dirs = [t_suf]
        else:
            dirs = [dir0, -dir0]
        seqs_tail = [[t] * need for t in dirs
                     if self.turn_ok(tip_idx, tip['h'] + t * TURN)]
        if not seqs_tail:
            self.rstats['ld_noseq'] += 1
        for st in seqs_tail:
            placed = []
            px, pz, h, y, last = (tip['px'], tip['pz'], tip['h'],
                                  tip['y'], tip_idx)
            ok = True
            for t in st:
                h += t * TURN
                px += CHORD * math.cos(h)
                pz += CHORD * math.sin(h)
                y -= 1
                bx, bz = rnd(px), rnd(pz)
                if (math.hypot(px - START_X, pz - START_Z) > max_r(y)
                        or not self.clear(bx, bz, y, last)):
                    self.rstats['ld_growblk'] += 1
                    ok = False
                    break
                last = self.place(bx, y, bz, last, br['id'],
                                  f=(px, pz, h))
                placed.append(last)
            if ok and self.landing_for_tail(
                    br, suffix[0], suffix[1:] + placed,
                    new_placed=placed):
                self.rstats['ld_grow%d' % need] += 1
                return True
            for i in reversed(placed):
                self.pop_block(i)
        self.rstats['ld_nofit'] += 1
        return False

    def landing_for_tail(self, br, tip_idx, placed, new_placed=None):
        # second half of splice_landing: given the copy stretch
        # `placed` (its first blocks may be the arm's own pre-existing
        # suffix; only `new_placed` was freshly placed and is
        # LIFO-unwindable by the caller - touch nothing else on
        # failure), find a junction + connector turn-sequence whose
        # backwards-solved translation erects a legal landing corridor.
        # Commits everything and returns True, or touches nothing and
        # returns False
        S = [tip_idx] + list(placed)
        sb = [self.blocks[i] for i in S]
        c7 = sb[-1]
        h_end = c7['h']
        # the copy stretch is constant-turn (user rule); its direction
        # is the ride prefix for the connector's turn-run check
        t_cs = hwrap(hn(sb[1]['h']) - hn(sb[0]['h']))
        cpts = self.tube_pts(S)
        cbox = self.tube_box(cpts)
        # the new tail tube must not fight any existing stamp tube
        if any(self.tubes_clash(cpts, cbox, tpts, tbox)
               for tpts, tbox, _ in self.tail_tubes) \
                or any(self.tubes_clash(cpts, cbox, opts, obox)
                       for opts, obox in self.win_tubes):
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

        # candidate junctions, collected ONCE: only blocks horizontally
        # within reach can ever satisfy |delta| <= SPLICE_MAX_D (the
        # landing sits within connector-reach of J), so filter the
        # y-band by Chebyshev up front - without this ~90% of the seq
        # budget died on ld_s_far (measured 1.17M rejections per seed).
        # r_j = SPLICE_MAX_D: J's further out need a luckily-oriented
        # connector to squeak under the cap - not worth the budget
        r_j = SPLICE_MAX_D
        cx, cz = c7['x'], c7['z']
        cand_j = []
        for yy in range(c7['y'] - 1 - 8 + MIN_RISE,
                        c7['y'] - 1 - 3 + SPLICE_MAX_RISE + 1):
            for i in self.by_y.get(yy, ()):
                b = self.blocks[i]
                if b is not None and abs(b['x'] - cx) <= r_j \
                        and abs(b['z'] - cz) <= r_j:
                    cand_j.append((i, yy))

        def roomy(jb, m):
            # free-space prescreen: the copy will sit ~m levels above J
            # within ~45 blocks horizontally. Count built blocks in
            # that shell via the grid - a crowded J dies in the seq
            # loop after burning 9-15 clear() probes per seq (measured
            # 444k such deaths per seed), so reject it for pennies here
            n = 0
            jy = jb['y']
            for gx in range((jb['x'] - 24) >> 3,
                            ((jb['x'] + 24) >> 3) + 1):
                for gz in range((jb['z'] - 24) >> 3,
                                ((jb['z'] + 24) >> 3) + 1):
                    for i in self.grid.get((gx, gz), ()):
                        b2 = self.blocks[i]
                        if b2 is not None \
                                and jy + 2 <= b2['y'] <= jy + m + 11:
                            n += 1
                            if n > 14:
                                return False
            return True
        # boosted budget only for load-bearing positions (land_boost).
        # NOTE: connectors cannot get longer than m~8 - the landing
        # arrives at J carrying 9 + m bounces and the down_slack guard
        # needs that within the cap, so m >= 10 can never pass
        boost = getattr(self, 'land_boost', False)
        jmax = 72 if boost else 24
        smax = 32 if boost else 16
        ms = list(range(3, 9))
        self.rng.shuffle(ms)
        for m in ms:
            ylo = c7['y'] - 1 - m + MIN_RISE
            yhi = c7['y'] - 1 - m + SPLICE_MAX_RISE
            rows = [i for i, yy in cand_j if ylo <= yy <= yhi]
            # EDGE BIAS: try junctions near the rim of the corridor
            # cloud first - their outboard side (the empty annulus,
            # LAND_R_EXTRA) is where copies actually fit. Random order
            # burned the budget on interior Js whose surroundings are
            # contested (ld_s_place ~124k/seed). Jitter keeps variety
            rows.sort(key=lambda i: (
                -max(abs(self.blocks[i]['x'] - START_X),
                     abs(self.blocks[i]['z'] - START_Z))
                + self.rng.random() * 30))
            tried_j = 0
            for J in rows:
                if tried_j >= jmax:
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
                if not roomy(jb, m):
                    self.rstats['ld_j_crowd'] += 1
                    continue
                # THE down_slack GUARD (the missing check that minted
                # most of the fork-gap violations): the landing's ride
                # arrives at J carrying d = 9 + m bounces (its root is
                # a fresh path start), and a junction resets nothing -
                # so J's remaining forkless run below must fit in the
                # cap or the landing itself creates a violation run on
                # the DESTINATION corridor (measured: viol runs on
                # landing/funnel/golden corridors, y-quartiles at the
                # funnel zone)
                if WINDOW + 2 + m + self.down_slack(J) > FORK_GAP_MAX:
                    self.rstats['ld_j_slack'] += 1
                    continue
                tried_j += 1
                arr2 = jb['h'] + 2 * t * TURN
                sx = jb['px'] - CHORD * math.cos(arr2)
                sz = jb['pz'] - CHORD * math.sin(arr2)
                dy = (jb['y'] + 1 + m) - c7['y']
                # turn-run rule at the junction: validate the full
                # ride - window prefix (constant t_cs), connector,
                # the -fin_off turn into J, and the existing turns
                # below J via the second-arrival chord (down_seq)
                dtails = self.down_seq(J, arr2, 4)
                seqs = []
                for fin_off in (-1, 1):
                    gap = hwrap(hn(arr2) + fin_off - hn(h_end))
                    seqs.extend(
                        (fin_off, seq) for seq in turn_seqs(m, gap)
                        if all(flips_ok([t_cs, t_cs] + seq
                                        + [-fin_off] + ds)
                               for ds in dtails))
                self.rng.shuffle(seqs)
                for fin_off, seq in seqs[:smax]:
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
                        self.rstats['ld_s_far'] += 1
                        continue
                    if max(abs(dx), abs(dz)) < 14 and abs(dy) < 20:
                        self.rstats['ld_s_sep'] += 1
                        continue      # decoration tube separation
                    if math.hypot(c7['px'] + dx + offx - sx,
                                  c7['pz'] + dz + offz - sz) \
                            > MERGE_TOL:
                        self.rstats['ld_s_arr'] += 1
                        continue      # integer rounding broke arrival
                    wpts = [(x + dx, z + dz, y2 + dy)
                            for x, z, y2 in cpts]
                    wbox = self.tube_box(wpts)
                    if any(self.tubes_clash(wpts, wbox, tpts, tbox)
                           for tpts, tbox, _ in self.tail_tubes):
                        self.rstats['ld_s_wintube'] += 1
                        continue
                    # place the 9 landing blocks (exact translation)
                    lplaced = []
                    last = None
                    ok = True
                    for bsrc in sb:
                        lx, ly, lz = (bsrc['x'] + dx, bsrc['y'] + dy,
                                      bsrc['z'] + dz)
                        if (math.hypot(bsrc['px'] + dx - START_X,
                                       bsrc['pz'] + dz - START_Z)
                                > max_r(ly) + LAND_R_EXTRA
                                or not self.clear(lx, lz, ly, last)):
                            ok = False
                            break
                        last = self.place(lx, ly, lz, last, -3,
                                          f=(bsrc['px'] + dx,
                                             bsrc['pz'] + dz,
                                             bsrc['h']))
                        lplaced.append(last)
                    if ok:
                        # connector down onto the junction slot
                        for si, (ox, oz, hh) in enumerate(pts):
                            fx = c7['px'] + dx + ox
                            fz = c7['pz'] + dz + oz
                            yy = c7['y'] + dy - si - 1
                            if (math.hypot(fx - START_X, fz - START_Z)
                                    > max_r(yy) + LAND_R_EXTRA
                                    or not chord_int_ok(
                                        rnd(fx), rnd(fz),
                                        self.blocks[last]['x'],
                                        self.blocks[last]['z'])
                                    or (si == m - 1
                                        and not chord_int_ok(
                                            rnd(fx), rnd(fz),
                                            jb['x'], jb['z']))
                                    or not self.clear(
                                        rnd(fx), rnd(fz), yy, last,
                                        extra=[(J, m - si)])):
                                ok = False
                                break
                            last = self.place(rnd(fx), yy, rnd(fz),
                                              last, -3, f=(fx, fz, hh))
                            lplaced.append(last)
                    if not ok:
                        self.rstats['ld_s_place'] += 1
                        for i in reversed(lplaced):
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
                    lb['blocks'] = list(lplaced)
                    for i in lplaced:
                        self.blocks[i]['br'] = lb['id']
                    self.set_prev(J, last)
                    jb['h2'] = arr2
                    win = lplaced[:WINDOW + 1]
                    copy = list(placed)
                    self.tail_tubes.append((cpts, cbox,
                                            set(copy) | {tip_idx}))
                    self.win_tubes.append((wpts, wbox))
                    self.splices.append({
                        'branch': br['id'],
                        'delta': (dx, dy, dz),
                        'w0': win[0],
                        'novel': True,
                        'doomed_dest': False,
                        'copy': copy, 'win': list(win)})
                    self.win_used.update(win)
                    if new_placed is None:
                        new_placed = placed
                    br['blocks'].extend(new_placed)
                    if new_placed:
                        br['last'] = copy[-1]
                    # the tail is a chain window; the landing corridor
                    # itself offers fresh never-visited windows too
                    self.windows.append({'blocks': [tip_idx] + copy,
                                         'y': self.blocks[tip_idx]['y'],
                                         'dw': hwrap(
                                             hn(sb[1]['h'])
                                             - hn(sb[0]['h']))})
                    self.register_branch_windows(br)
                    self.scan_seq_windows(lb['blocks'], self.windows)
                    self.rstats['ld_ok'] += 1
                    return True
            self.rstats['ld_j%d' % tried_j] += 1
        self.rstats['ld_nojunc'] += 1
        return False

    def down_slack(self, J, skip=None):
        # worst-case extra bounces below J before a fork resets the
        # count (the fork/trigger block itself still counts; the
        # replica tail past a trigger is exempt). skip= pretends one
        # block is already erased (safe-erase classification)
        triggers = {sp['copy'][0] for sp in self.splices}
        best = 0
        stack = [(J, 0)]
        while stack:
            i, n = stack.pop()
            if n > FORK_GAP_MAX:
                return 99
            ks = [k for k in self.kids.get(i, ())
                  if self.blocks[k] is not None and k != skip]
            if (n > 0 and (len(ks) >= 2 or i in triggers)) \
                    or self.blocks[i]['y'] == BOTTOM_Y:
                continue
            for k in ks:
                if n + 1 > best:
                    best = n + 1
                stack.append((k, n + 1))
        return best

    def win_signature(self, idxs):
        # chord-heading signature of a WINDOW+1 block chain: the tuple
        # of quantized headings of its WINDOW chords. Two chains with
        # equal signatures are exact translations of each other up to
        # an integer delta (all chords match in heading, hence in
        # rounded x/z step) - the basis of the suffix window match
        hs = []
        for a, b in zip(idxs, idxs[1:]):
            bb = self.blocks[b]
            if bb is None or bb['h'] is None:
                return None
            hs.append(hn(bb['h']))
        return tuple(hs)

    def splice_suffix(self, br, tip_idx=None):
        # SUFFIX WINDOW MATCH (v3 capacity tier 0): terminate a dying
        # arm by matching its own last WINDOW+1 blocks against a
        # registered window with the IDENTICAL chord-heading signature.
        # The arm's suffix becomes the replica tail verbatim - zero new
        # blocks are placed, so this tier is immune to the volume
        # saturation that limits landings. Costs only the tail tube
        # registration.
        self.rstats['sx_call'] += 1
        if tip_idx is None:
            tip_idx = br['last']
        tip = self.blocks[tip_idx]
        if tip is None or tip['h'] is None or tip['px'] is None:
            return False
        # suffix extraction identical to splice_landing's, but the
        # FULL length is required (nothing is grown here). Constant
        # turn direction is required too (user rule) - non-constant
        # suffixes could never match a registered window anyway
        suffix = [tip_idx]
        t_suf = None
        blocks_ = br['blocks']
        if tip_idx not in blocks_:
            return False
        pos = len(blocks_) - 1 - blocks_[::-1].index(tip_idx)
        j = pos
        while len(suffix) < WINDOW + 1 and j > 0:
            cand = blocks_[j - 1]
            cb = self.blocks[cand]
            nb = self.blocks[suffix[0]]
            if (cb is None or cb['h'] is None or cb['px'] is None
                    or cb['prev2'] is not None
                    or nb['prev'] != cand
                    or cand in self.win_used
                    or sum(1 for k in self.kids.get(cand, ())
                           if self.blocks[k] is not None) > 1):
                break
            t = hwrap(hn(nb['h']) - hn(cb['h']))
            if abs(t) != 1 or (t_suf is not None and t != t_suf):
                break
            t_suf = t
            suffix.insert(0, cand)
            j -= 1
        if len(suffix) < WINDOW + 1:
            self.rstats['sx_short'] += 1
            return False
        if self.bounces_since_fork(suffix[1]) > FORK_GAP_MAX:
            self.rstats['sx_guard'] += 1
            return False
        sig = self.win_signature(suffix)
        if sig is None:
            return False
        # signature index over self.windows, rebuilt when it grows
        if getattr(self, '_wsig_n', -1) != len(self.windows):
            idx = {}
            for w in self.windows:
                s2 = self.win_signature(w['blocks'])
                if s2 is not None:
                    idx.setdefault(s2, []).append(w)
            self._wsig = idx
            self._wsig_n = len(self.windows)
        cands = self._wsig.get(sig, ())
        if not cands:
            self.rstats['sx_nomatch'] += 1
            return False
        sb = [self.blocks[i] for i in suffix]
        tails = {c for sp in self.splices for c in sp['copy']}
        cpts = self.tube_pts(suffix)
        cbox = self.tube_box(cpts)
        for w in cands:
            wbs = [self.blocks[i] for i in w['blocks']]
            if any(b is None or b['h'] is None for b in wbs):
                continue
            # window must still be fork-free / merge-free and live
            if any(len([k for k in self.kids.get(i, ())
                        if self.blocks[k] is not None]) > 1
                   for i in w['blocks'][:-1]):
                continue
            if any(b['prev2'] is not None for b in wbs):
                continue
            if any(i in tails for i in w['blocks']):
                continue      # SPLICE_SUPPRESS: never land on a tail
            if any(i in self.win_used for i in w['blocks']):
                continue
            if any(i in suffix for i in w['blocks']):
                continue      # never map the suffix onto itself
            dx = wbs[1]['x'] - sb[1]['x']
            dy = wbs[1]['y'] - sb[1]['y']
            dz = wbs[1]['z'] - sb[1]['z']
            if not (MIN_RISE <= dy <= SPLICE_MAX_RISE):
                self.rstats['sx_rise'] += 1
                continue
            if max(abs(dx), abs(dz)) > SPLICE_MAX_D:
                self.rstats['sx_far'] += 1
                continue
            if max(abs(dx), abs(dz)) < 14 and abs(dy) < 20:
                self.rstats['sx_sep'] += 1
                continue
            # exact translation check over the whole copy
            if any((wb['x'] - cb2['x'], wb['y'] - cb2['y'],
                    wb['z'] - cb2['z']) != (dx, dy, dz)
                   for wb, cb2 in zip(wbs[1:], sb[1:])):
                self.rstats['sx_mismatch'] += 1
                continue
            wpts = self.tube_pts(w['blocks'])
            wbox = self.tube_box(wpts)
            wset = set(w['blocks'][1:])
            if any(not wset <= tcopy
                   and self.tubes_clash(wpts, wbox, tpts, tbox)
                   for tpts, tbox, tcopy in self.tail_tubes):
                self.rstats['sx_wintube'] += 1
                continue
            if any(self.tubes_clash(cpts, cbox, tpts, tbox)
                   for tpts, tbox, _ in self.tail_tubes) \
                    or any(self.tubes_clash(cpts, cbox, op, ob)
                           for op, ob in self.win_tubes):
                self.rstats['sx_tailtube'] += 1
                continue
            copy = suffix[1:]
            self.tail_tubes.append((cpts, cbox, set(copy) | {suffix[0]}))
            self.win_tubes.append((wpts, wbox))
            anc = self.ancestors_of(suffix[0])
            self.splices.append({
                'branch': br['id'],
                'delta': (dx, dy, dz),
                'w0': w['blocks'][0],
                'novel': w['blocks'][0] not in anc,
                'doomed_dest': False,
                'copy': copy, 'win': list(w['blocks'])})
            self.win_used.update(w['blocks'])
            self.rstats['sx_ok'] += 1
            return True
        self.rstats['sx_nofit'] += 1
        return False

    # ---- steered suffix termination ----------------------------------------
    def sim_steer(self, br, g, w):
        # exact dry-run of the forced ride: |g| alignment bounces
        # (constant turn sign(g)) then the window's own 7-turn
        # sequence, replicating step()'s float/round arithmetic
        # bounce for bounce. Returns the forced-turn list iff the
        # ridden suffix would be an EXACT integer translation of the
        # window inside every splice rule - selection-time certainty
        # is what lets the walk commit 8-15 bounces to the plan
        wbs = [self.blocks[i] for i in w['blocks']]
        turns = [1 if g > 0 else -1] * abs(g) + [w['dw']] \
            + [hwrap(hn(b2['h']) - hn(b1['h']))
               for b1, b2 in zip(wbs[1:], wbs[2:])]
        # turn-run rule over the whole forced ride incl. the arm's
        # recent turns (windows are constant-direction now, so only
        # the arc boundaries can flip)
        if any(not flips_ok(list(reversed(ts)) + turns)
               for ts in self.hist_into(br['last'])):
            self.rstats['steer_runrule'] += 1
            return None
        px, pz, h, y = br['px'], br['pz'], br['h'], br['y']
        tb = self.blocks[br['last']]
        ints = [(tb['x'], tb['y'], tb['z'])]
        pts = [(px, pz, y)]
        for t in turns:
            h += t * TURN
            px += CHORD * math.cos(h)
            pz += CHORD * math.sin(h)
            y -= 1
            if math.hypot(px - START_X, pz - START_Z) > max_r(y):
                return None
            ints.append((rnd(px), y, rnd(pz)))
            pts.append((px, pz, y))
        suf = ints[abs(g):]
        dx = wbs[1]['x'] - suf[1][0]
        dy = wbs[1]['y'] - suf[1][1]
        dz = wbs[1]['z'] - suf[1][2]
        if not (MIN_RISE <= dy <= SPLICE_MAX_RISE):
            return None
        if max(abs(dx), abs(dz)) > SPLICE_MAX_D:
            return None
        if max(abs(dx), abs(dz)) < 14 and abs(dy) < 20:
            return None
        if any((wb['x'] - c[0], wb['y'] - c[1], wb['z'] - c[2])
               != (dx, dy, dz) for wb, c in zip(wbs[1:], suf[1:])):
            self.rstats['steer_round'] += 1
            return None       # rounding diverged: not a translation
        # the suffix tube must not clash existing stamps (pre-check
        # what splice_suffix will demand, or the ride is wasted)
        spts = []
        for (ax, az, ay), (bx2, bz2, by2) in zip(
                pts[abs(g):], pts[abs(g) + 1:]):
            steps = max(1, int(math.hypot(bx2 - ax, bz2 - az) / 2))
            for s in range(steps + 1):
                f = s / steps
                spts.append((ax + f * (bx2 - ax), az + f * (bz2 - az),
                             ay + f * (by2 - ay)))
        sbox = self.tube_box(spts)
        if any(self.tubes_clash(spts, sbox, tp, tb2)
               for tp, tb2, _ in self.tail_tubes) \
                or any(self.tubes_clash(spts, sbox, op, ob)
                       for op, ob in self.win_tubes):
            self.rstats['steer_tube'] += 1
            return None
        return turns

    def pick_steer(self, br):
        # choose a window this arm can ride onto. Windows are the
        # cheap resource (farms + every spliced corridor); the ride
        # is the arm's own corridor, so this termination needs NO new
        # volume on either side - immune to both measured walls
        # (landing saturation, arm-side arc placement)
        self.rstats['steer_call'] += 1
        gap = br['gap']
        tip_y = br['y']
        h_tip = br['h']
        tails = {c for sp in self.splices for c in sp['copy']}
        cands = []
        for w in self.windows:
            wb1 = self.blocks[w['blocks'][1]]
            wb0 = self.blocks[w['blocks'][0]]
            if wb0 is None or wb1 is None or wb1['h'] is None:
                continue
            g = hwrap(hn(wb1['h']) - w['dw'] - hn(h_tip))
            if gap + abs(g) + 1 > FORK_GAP_MAX:
                continue      # trigger would land past the cap
            ride = abs(g) + WINDOW
            if tip_y - ride < MORTAL_FLOOR + 2:
                continue
            dy = wb1['y'] - (tip_y - abs(g) - 1)
            if not (MIN_RISE <= dy <= SPLICE_MAX_RISE):
                continue
            if max(abs(wb0['x'] - self.blocks[br['last']]['x']),
                   abs(wb0['z'] - self.blocks[br['last']]['z'])) \
                    > SPLICE_MAX_D:
                continue
            cands.append((g, w))
        if not cands:
            self.rstats['steer_nocand'] += 1
            return None
        self.rng.shuffle(cands)
        cands.sort(key=lambda gw: (not gw[1].get('farm'),
                                   abs(gw[0])))
        tried = 0
        for g, w in cands:
            if tried >= 16:
                break
            wbs = [self.blocks[i] for i in w['blocks']]
            if any(b is None or b['h'] is None for b in wbs) \
                    or any(b['prev2'] is not None for b in wbs) \
                    or any(i in self.win_used or i in tails
                           for i in w['blocks']) \
                    or any(len([k for k in self.kids.get(i, ())
                                if self.blocks[k] is not None]) > 1
                           for i in w['blocks'][:-1]):
                continue
            tried += 1
            turns = self.sim_steer(br, g, w)
            if turns is not None:
                self.rstats['steer_pick'] += 1
                return {'turns': turns, 'k': 0}
        self.rstats['steer_nofit'] += 1
        return None

    def precious(self, br):
        # an arm rooted on a FINAL corridor - static (trunk/funnel/
        # braid/stub/port) or already terminated (spliced/merged/
        # landing): losing its root fork permanently scars kept maze,
        # so always worth the boosted landing budget. Arms rooted on
        # still-alive or doomed-unterminated parents are not: those
        # parents' own cadence tracking (or their chew) handles it
        if not br['blocks']:
            return False
        b0 = self.blocks[br['blocks'][0]]
        p = b0['prev'] if b0 else None
        if p is None or self.blocks[p] is None:
            return False
        bid = self.blocks[p]['br']
        if bid in (-1, -2):
            return True
        if isinstance(bid, int) and 0 <= bid < len(self.branches):
            b2 = self.branches[bid]
            # NOTE: widening this to spliced/merged/landing parents was
            # A/B-tested (2 seeds) and made things worse - the extra
            # boosted calls shift every downstream RNG draw and the
            # static-rooted definition measured best
            return b2['golden'] or b2['funnel'] or b2.get('braid')
        return False

    def build_merge_targets(self):
        # blocks 1-5 upstream of a fork on a STABLE corridor, indexed
        # by y: a merge arriving just above a fork has minimal
        # down_slack, so walk-time sweet-spot merges aim only there
        idx = {}
        for f in self.forks:
            b = self.blocks[f['parent_idx']]
            if b is None:
                continue
            bid = b['br']
            if not (isinstance(bid, int)
                    and 0 <= bid < len(self.branches)):
                continue
            b2 = self.branches[bid]
            if not ((b2['golden'] or b2['funnel'] or b2.get('braid')
                     or b2.get('landing') or b2['spliced'])
                    and not b2['alive']):
                continue
            j = b['prev']
            for _ in range(5):
                if j is None or self.blocks[j] is None:
                    break
                idx.setdefault(self.blocks[j]['y'], []).append(j)
                j = self.blocks[j]['prev']
        return idx

    def merge_end(self, br, tip_idx=None, targets=None):
        # TERMINAL MERGE (v3): a dying arm connects INTO a stable
        # corridor with the standard junction shape - the landing's
        # exactly-solved connector with no copy to build: the arm just
        # becomes the junction's second arrival. Costs m blocks and no
        # decoration tubes, so it is the capacity valve when landing
        # volume saturates (~2000 arms want terminations; free volume
        # holds ~200 landings). Invisible to the player: corridors
        # simply flow together mid-maze.
        # Cadence: a junction resets nothing, so the arrival gap plus
        # the remaining forkless run BELOW J must stay within the cap -
        # down_slack() measures it exactly
        self.rstats['me_call'] += 1
        if tip_idx is None:
            tip_idx = br['last']
        tip = self.blocks[tip_idx]
        if tip is None or tip['h'] is None or tip['px'] is None:
            return False
        g_tip = self.bounces_since_fork(tip_idx)
        h_end = tip['h']
        pre_hists = [list(reversed(ts)) for ts in self.hist_into(tip_idx)]
        tails = {c for sp in self.splices for c in sp['copy']}
        triggers = {sp['copy'][0] for sp in self.splices}
        # a junction within 5 bounces upstream of a replica tail would
        # put the connector kin-exempt inside the tail's stamp tube
        # (same rule as repair forks) - the stamp would overwrite it
        near_tail = set()
        for sp in self.splices:
            j = self.blocks[sp['copy'][0]]['prev'] \
                if self.blocks[sp['copy'][0]] is not None else None
            for _ in range(6):
                if j is None or self.blocks[j] is None:
                    break
                near_tail.add(j)
                j = self.blocks[j]['prev']

        def stable(bid):
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
            if g_tip + m + 1 > FORK_GAP_MAX - 1:
                continue
            if targets is not None:
                rows = list(targets.get(tip['y'] - m - 1, ()))
            else:
                rows = list(self.by_y.get(tip['y'] - m - 1, ()))
            self.rng.shuffle(rows)
            tried_j = 0
            for J in rows:
                if tried_j >= 16:
                    break
                jb = self.blocks[J]
                if jb is None or jb['h'] is None or jb['px'] is None \
                        or jb['prev2'] is not None:
                    continue
                if max(abs(jb['x'] - tip['x']),
                       abs(jb['z'] - tip['z'])) > (m + 2) * CHORD:
                    continue
                if J in self.win_used or J in tails \
                        or J in near_tail or not stable(jb['br']):
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
                if g_tip + m + 1 + self.down_slack(J) > FORK_GAP_MAX:
                    self.rstats['me_slack'] += 1
                    continue
                tried_j += 1
                arr2 = jb['h'] + 2 * t * TURN
                sx = jb['px'] - CHORD * math.cos(arr2)
                sz = jb['pz'] - CHORD * math.sin(arr2)
                if math.hypot(tip['px'] - sx, tip['pz'] - sz) \
                        > CHORD * m * 0.95:
                    continue
                # turn-run rule: whole-ride validation (tip history +
                # connector + junction arrival + existing turns below)
                dtails = self.down_seq(J, arr2, 4)
                seqs = []
                for fin_off in (-1, 1):
                    gap = hwrap(hn(arr2) + fin_off - hn(h_end))
                    seqs.extend(
                        (fin_off, seq) for seq in turn_seqs(m, gap)
                        if all(flips_ok(ph + seq + [-fin_off] + ds)
                               for ph in pre_hists for ds in dtails))
                self.rng.shuffle(seqs)
                for fin_off, seq in seqs[:24]:
                    px, pz, h = tip['px'], tip['pz'], h_end
                    pts = []
                    for tt in seq:
                        h += tt * TURN
                        px += CHORD * math.cos(h)
                        pz += CHORD * math.sin(h)
                        pts.append((px, pz, h))
                    if math.hypot(px - sx, pz - sz) > MERGE_TOL:
                        continue
                    placed = []
                    last = tip_idx
                    ok = True
                    for si, (fx, fz, hh) in enumerate(pts):
                        yy = tip['y'] - si - 1
                        if (math.hypot(fx - START_X, fz - START_Z)
                                > max_r(yy)
                                or not chord_int_ok(
                                    rnd(fx), rnd(fz),
                                    self.blocks[last]['x'],
                                    self.blocks[last]['z'])
                                or (si == m - 1
                                    and not chord_int_ok(
                                        rnd(fx), rnd(fz),
                                        jb['x'], jb['z']))
                                or not self.clear(
                                    rnd(fx), rnd(fz), yy, last,
                                    extra=[(J, m - si)])):
                            ok = False
                            break
                        last = self.place(rnd(fx), yy, rnd(fz), last,
                                          br['id'], f=(fx, fz, hh))
                        placed.append(last)
                    if not ok:
                        for i in reversed(placed):
                            self.pop_block(i)
                        continue
                    self.set_prev(J, last)
                    jb['h2'] = arr2
                    br['blocks'].extend(placed)
                    br['last'] = last
                    br['merged'] = True
                    br['alive'] = False
                    self.merges += 1
                    self.rstats['me_ok'] += 1
                    return True
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
        # v3 cadence cap: the merge walk steps d1 without fork checks,
        # so bound it by the exact gap - the junction (which resets
        # nothing) must arrive before FORK_LAND_AT
        g0 = self.bounces_since_fork(d1['last'])
        k = 0
        while k < MERGE_K_MAX:
            # arrival cap FORK_GAP_MAX - 2: the merged continuation's
            # backstop fires one step later (gap+1) and its landing
            # trigger adds one more - both must stay within the cap.
            # (Capping at FORK_LAND_AT killed every merge: the walk
            # broke before MERGE_K_MIN was ever reached)
            if g0 + k + 1 > FORK_GAP_MAX - 2:
                break
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
        # the junction - the arriving count must leave the merged
        # continuation room for its landing (backstop fires at gap+1,
        # trigger sits one bounce further: arrival <= cap - 2)
        if self.bounces_since_fork(d2['last']) + m + 1 > FORK_GAP_MAX - 2:
            return False
        pre_hists = [list(reversed(ts))
                     for ts in self.hist_into(d2['last'])]
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
                    # turn-run rule: d2's history + connector + the
                    # -fin_off turn into J + the -t turn at J onto
                    # d1's (forced) continuation; d1's later bounces
                    # are guarded by turn_ok once the junction exists
                    if not all(flips_ok(ph + seq + [-fin_off, -t])
                               for ph in pre_hists):
                        continue
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
    def try_fork(self, br, pre, d):
        # spawn a decoy child at the pre-step block (the fork block):
        # shared by the random-timer forks and the v3 forced-cadence
        # forks. On success both tips sit 1 bounce past the fork
        child = self.new_branch(pre[0], pre[1], pre[2], -d, pre[3], pre[4])
        child['flip'] = max(child['flip'], FORK_TURN_LOCK)
        if br['doomed']:
            child['doomed'] = True
            child['life'] = br['life']
        if self.step(child, forced=-d) is None:
            self.branches.pop()
            br['fork'] = 1
            return False
        br['fork'] = (self.rng.randint(8, 12) if br['doomed']
                      else self.rng.randint(FORK_MIN, FORK_MAX))
        br['flip'] = max(br['flip'], FORK_TURN_LOCK)
        br['forked'] = True
        br['lfl'] = len(br['blocks']) - 1
        br['gap'] = 1
        child['gap'] = 1
        self.forks.append({
            'br': br['id'], 'decoy': child['id'],
            'parent_idx': pre[4], 'cont_idx': br['last'],
            'decoy_idx': child['last'], 'y': pre[3],
            'golden': False})
        return True

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

        self._mt = {}
        mt_age = 0
        for y in range(START_Y - 1, BOTTOM_Y - 1, -1):
            # refresh the sweet-spot merge target index every few
            # levels (forks/stability change as branches splice)
            if mt_age <= 0:
                self._mt = self.build_merge_targets()
                mt_age = 8
            mt_age -= 1
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
                    br['gap'] += 1
                    if br['doomed']:
                        br['life'] -= 1
                    continue
                # steered suffix termination: mid-ride arms are
                # committed - forced turns, no forks, and the life /
                # wander-floor rules are suspended (the plan already
                # proved the ride stays above MORTAL_FLOOR and ends
                # in a legal splice)
                if br.get('steer') is not None:
                    st = br['steer']
                    d = self.step(br, forced=st['turns'][st['k']])
                    if d is None:
                        br['steer'] = None
                        self.rstats['steer_blocked'] += 1
                        br['gap'] = self.bounces_since_fork(br['last'])
                        continue
                    st['k'] += 1
                    br['gap'] += 1
                    if st['k'] == len(st['turns']):
                        br['steer'] = None
                        if self.splice_suffix(br):
                            br['spliced'] = True
                            br['alive'] = False
                            self.rstats['steer_ok'] += 1
                        else:
                            self.rstats['steer_lost'] += 1
                            br['gap'] = self.bounces_since_fork(
                                br['last'])
                    continue
                # v3: no early splice band - landings are reliable, so
                # every arm lives its full life and terminates at death
                if br['doomed'] and (br['life'] <= 0
                                     or br['y'] - 1 < WANDER_FLOOR):
                    self.end_branch(br)
                    continue
                if not br['doomed'] and br['y'] - 1 < WANDER_FLOOR:
                    self.end_branch(br)
                    continue
                if br['doomed']:
                    br['life'] -= 1
                    # death-band run commitment: an arm close to its
                    # splice stops flipping ALTOGETHER (scheduled and
                    # fallback - 'noflip'), so its last WINDOW+1
                    # blocks form one constant arc: a legal copy
                    # stretch (user rule) feeding the zero-cost
                    # suffix/landing tiers
                    if br['life'] <= WINDOW + 2 \
                            or br['gap'] + 1 >= FORK_FORCE_AT:
                        br['flip'] = max(br['flip'], WINDOW + 2)
                        br['noflip'] = True
                # v3 arm economics: doomed arms fork on a SLOWER timer
                # (8-12) than winners (5-9) - fast timers bred an arm
                # cascade far beyond termination capacity, but pure
                # cadence-forced forks (12-17 spacing) had ZERO
                # redundancy: terminations fail ~half the time, and one
                # lost fork on a 12-17 spacing is an automatic
                # violation. Oversample so safe-erase can absorb the
                # losses
                do_fork = ((br['fork'] <= 1
                            or br['gap'] + 1 >= FORK_FORCE_AT)
                           and br['gap'] + 1 < FORK_LAND_AT
                           and br['y'] - 1 > FORK_FLOOR
                           and (not br['doomed']
                                or br['life'] >= MIN_STUB))
                br['fork'] -= 1
                pre = (br['px'], br['pz'], br['h'], br['y'], br['last'])
                d = self.step(br)
                if d is None:
                    # funnel-zone precious arms get extra rewind
                    # persistence: an arm that escapes the crowded
                    # entry disk dies lower, where landings fit -
                    # dying high strands its static fork forever
                    d = self.rewind_retry(
                        br, tries=6 if (br['y'] > TRUNK_TOP - 8
                                        and self.precious(br)) else 3)
                    if d is not None:
                        # rewind erased tail blocks: hint is stale, and
                        # the fork pre-state is gone - resync and apply
                        # only the cadence backstop this level
                        br['gap'] = self.bounces_since_fork(br['last'])
                        if br['gap'] >= FORK_LAND_AT:
                            self.end_branch(br)
                        continue
                if d is None:
                    self.end_branch(br)
                    continue
                br['gap'] += 1
                forked = do_fork and self.try_fork(br, pre, d)
                # walk-time sweet-spot merges: while the gap is still
                # small a terminal merge just above a stable fork is
                # cadence-cheap (down_slack tiny, arrival low) - drain
                # the termination queue BEFORE arms are in trouble
                if (not forked and br['doomed'] and br['alive']
                        and 4 <= br['gap'] <= 9
                        and getattr(self, '_mt', None)
                        and self.rng.random() < 0.3):
                    if self.merge_end(br, targets=self._mt):
                        continue
                # steering trigger: doomed arms whose forced forks
                # failed (cadence band) or that approach the wander
                # floor pick a window and ride onto it. gap is
                # re-synced exact first - the plan's trigger-cadence
                # guarantee depends on it
                # (A/B 2026-08-09: 59 rides -> 3 splices on seed 1 -
                # the ride suffers the same arm-side congestion as a
                # splice_tail arc and rounds worse than an exact
                # translation. Default OFF, GM_STEER=1 to re-test)
                if (os.environ.get('GM_STEER') == '1'
                        and not forked and br['alive'] and br['doomed']
                        and br.get('steer') is None
                        and (br['gap'] >= FORK_FORCE_AT + 1
                             or (br['y'] <= WANDER_FLOOR + 18
                                 and br['gap'] >= 4))):
                    br['gap'] = self.bounces_since_fork(br['last'])
                    if br['gap'] + 1 < FORK_GAP_MAX:
                        st = self.pick_steer(br)
                        if st is not None:
                            br['steer'] = st
                            continue
                if not forked and br['gap'] >= FORK_FORCE_AT:
                    # cadence backstop: pay for the exact gap. From
                    # FORK_LAND_AT on, the arm enters the LANDING
                    # EXTENSION band: forks are off (do_fork gate), and
                    # a landing is attempted at every level - the
                    # trigger is the suffix top (WINDOW-1 above the
                    # tip), so landings stay legal up to gap ~26. Only
                    # an arm that exhausts the whole band dies the hard
                    # way (full tiers + chew)
                    br['gap'] = self.bounces_since_fork(br['last'])
                    if br['gap'] >= FORK_GAP_MAX + WINDOW - 2:
                        self.end_branch(br)
                    elif br['gap'] >= FORK_LAND_AT:
                        # farm windows serve the extension band too:
                        # in the farm zones a landing rarely fits, but
                        # a pre-built window almost always does
                        if self.splice_landing(br) or self.splice_tail(br):
                            br['spliced'] = True
                            br['alive'] = False

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
                if (self.turn_ok(B, hd)
                        and math.hypot(nx - START_X,
                                       nz - START_Z) <= max_r(y)
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
                    child['gap'] = 1
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
                child['gap'] = 1
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
                        and b['pending'] is None and b['life'] >= 12
                        and b.get('steer') is None]
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
                        # the merge walk moved a's tip (and a junction
                        # never resets the count) - resync the hint
                        a['gap'] = self.bounces_since_fork(a['last'])

            # v3: cadence holes can only appear when a chew ERASES
            # blocks (a fork's last decoy child dying retroactively
            # lengthens runs through it) - with landing-first
            # termination that is the rare fallback, so the interleaved
            # repair only runs when a chew actually fired since the
            # last check instead of burning a fork_gap_map every level
            if y < START_Y - 8 and getattr(self, 'chew_dirty', False):
                self.chew_dirty = False
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
        dbg = os.environ.get('GM_DEBUG')
        t_run = time.time()

        def tick(label):
            if dbg:
                print('[t] %-10s %7.2fs  blocks=%d branches=%d '
                      'splices=%d'
                      % (label, time.time() - t_run,
                         sum(1 for b in self.blocks if b is not None),
                         len(self.branches), len(self.splices)),
                      flush=True)

        if self.build_golden() is None:
            self.fail = 'golden trunk (backtrack budget)'
            return False
        tick('golden')
        quotas = [ENTRIES // FUNNELS + (1 if k < ENTRIES % FUNNELS else 0)
                  for k in range(FUNNELS)]
        # funnels grow ONE AT A TIME, each to completion: later funnels
        # route around the finished earlier trees, and when one jams
        # only THAT funnel rolls back and re-rolls with fresh
        # randomness. Funnels 1.. root at ports; a port whose funnel
        # cannot climb out is unmade and re-rolled at another depth
        self.ports = []
        used = []
        # ports grow FIRST (v3 turn-run rule): run-legal corridors
        # cannot zigzag through gaps narrower than a 3-bounce weave,
        # so the port funnels must thread the central disk while it
        # is still empty; funnel 0 (trunk top) has always been the
        # robust grower and routes around them fine
        for k in list(range(1, FUNNELS)) + [0]:
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
                        self.rstats['port_none'] += 1
                        break
                    slot, sx, sz, arr2, ak, y0 = port[:6]
                    if self.grow_funnel(slot, sx, sz, arr2, ak, y0,
                                        quotas[k], 6):
                        self.ports.append(port)
                        used.append(port[6])
                        grown = True
                        break
                    self.rstats['port_grow'] += 1
                    self.unmake_port(port)
            if not grown:
                self.fail = 'funnel %d could not grow' % k
                return False
        if len(self.entry_tips) != ENTRIES:
            self.fail = 'entry tips %d != %d' % (len(self.entry_tips),
                                                 ENTRIES)
            return False
        tick('funnels')
        for br in self.branches:
            if br['funnel'] and br['blocks']:
                br['blocks'].reverse()
                self.funnel_seqs.append(br['blocks'])
        self.build_braids()
        tick('braids')
        # static windows scanned BEFORE the funnel forks: bubble_close
        # splices its arms onto them at build time. Blocks forked
        # later inside a scanned window go stale, which is safe -
        # splice_tail re-validates every window at use
        self.scan_windows()
        # build-time cadence forks on every static junction-free
        # stretch: funnel corridors (incl. port climbs) get bubbles
        # (below), braid arms keep classic reserve_along stubs
        # funnel-zone cadence forks. Default: BUBBLE BRAIDS (pre-
        # terminated, no arm to pay for later - the stub arms were
        # the funnel zone's unpayable termination bill). Two passes:
        # spawn every corridor's fork arms first, THEN rejoin them -
        # a rejoin is an arrival and its down_slack guard needs the
        # forks below already in place. GM_BUBBLE=0 restores the
        # classic stub blanket (GM_STUBGAP=a,b tunes it) for A/B
        if os.environ.get('GM_BUBBLE') == '0':
            for seq in self.funnel_seqs:
                sg = os.environ.get('GM_STUBGAP')
                lo, hi = (int(v) for v in sg.split(',')) if sg \
                    else (4, 6)
                self.reserve_along(seq[1:-1], gap_lo=lo, gap_hi=hi)
        else:
            spawned = []
            for seq in self.funnel_seqs:
                spawned.extend(self.bubble_along(seq[1:-1]))
            for ch, B, K in spawned:
                done = self.bubble_close(ch)
                # a close failure is usually THIS arm's local splice
                # geometry - respawn with a fresh wander before
                # surrendering the site to a stub promise
                for _r in range(4):
                    if done:
                        break
                    ch2 = self.bubble_at(B, K)
                    if ch2 is None:
                        break
                    done = self.bubble_close(ch2)
                if done:
                    continue
                # stub-promise fallback so the fork site is not lost
                bb, kb = self.blocks[B], self.blocks[K]
                if bb is None or kb is None or bb['h'] is None \
                        or kb['h'] is None or bb['px'] is None \
                        or bb['prev2'] is not None \
                        or self.is_multi(B):
                    continue
                t = hwrap(hn(kb['h']) - hn(bb['h']))
                if abs(t) != 1:
                    continue
                res = self.reserve_decoy(
                    (bb['px'], bb['pz'], bb['h'], bb['y'], B), t, K)
                if res is not None:
                    res['golden'] = False
                    self.reserved.append(res)
                    self.rstats['bub_stub'] += 1
        for seq in self.braid_seqs:
            self.reserve_along(seq[3:-3])
        self.build_window_farm()
        tick('stubs+wins')

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
        if dbg:
            print('[t] static viol before pre-pass: %d' % viol_now(),
                  flush=True)
        self.enforce_fork_gaps(passes=6)
        tick('pre-pass')
        if dbg:
            print('[t] static viol after pre-pass: %d' % viol_now(),
                  flush=True)
        self.run_decoys()
        tick('decoys')
        if dbg:
            d = self.fork_gap_map()
            ex = self.fork_gap_exempt()
            runs = {}
            ys = []
            for i, v in d.items():
                if v > FORK_GAP_MAX and i not in ex:
                    b = self.blocks[i]
                    bid = b['br']
                    br2 = (self.branches[bid]
                           if isinstance(bid, int)
                           and 0 <= bid < len(self.branches) else None)
                    key = ('sentinel' if br2 is None else
                           'golden' if br2['golden'] else
                           'funnel' if br2['funnel'] else
                           'braid' if br2.get('braid') else
                           'landing' if br2.get('landing') else
                           'spliced' if br2['spliced'] else
                           'merged' if br2['merged'] else
                           'alive' if br2['alive'] else 'dead-other')
                    runs[key] = runs.get(key, 0) + 1
                    ys.append(b['y'])
            ys.sort()
            print('[viol] by branch type: %s | y quartiles %s'
                  % (runs, [ys[k * (len(ys) - 1) // 4]
                            for k in range(5)] if ys else []),
                  flush=True)
        self.gap_stages = {'sweep': viol_now()}
        self.fix_leaves()
        tick('fix_leaves')
        self.gap_stages['fix_leaves'] = viol_now()
        # final repair runs with the boosted landing budget - a few
        # hundred calls at most, and these are the last-chance spots
        self.land_boost = True
        try:
            self.enforce_fork_gaps()
        finally:
            self.land_boost = False
        tick('final')
        self.gap_stages['final'] = viol_now()
        if dbg:
            print('[t] gap stages %s rstats=%s'
                  % (self.gap_stages, dict(self.rstats)), flush=True)
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
        elif any(t != turns[0] for t in turns):
            errs.append('splice for branch %d: window flips turn '
                        'direction (user rule: the tail past the '
                        'trigger must be constant)' % sp['branch'])
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

    # turn-run rule (user, 2026-08-15): on every traversable route a
    # turn-direction change is followed by at least TURN_RUN_MIN-1
    # bounces of the new direction. Enumerate every ride window of
    # TURN_RUN_MIN+1 turns via arrival-correct chords (a junction
    # block stores h for its prev chord and h2 for its prev2 chord)
    # and re-run flips_ok independently of the generation-side checks
    def chord_pc(p, c):
        cb = blks[c]
        return cb['h'] if cb['prev'] == p else cb.get('h2')

    def ride_dfs(i, hprev, acc):
        if len(acc) == TURN_RUN_MIN + 1:
            if not flips_ok(acc):
                errs.append('turn-run rule violated at block %d '
                            '(%d,%d,%d): turns %s'
                            % (i, blks[i]['x'], blks[i]['y'],
                               blks[i]['z'], acc))
            return
        ks = [k for k in sim.kids.get(i, ()) if blks[k] is not None]
        if not ks:
            if not flips_ok(acc):
                errs.append('turn-run rule violated at leaf %d '
                            '(%d,%d,%d): turns %s'
                            % (i, blks[i]['x'], blks[i]['y'],
                               blks[i]['z'], acc))
            return
        for k in ks:
            hk = chord_pc(i, k)
            if hk is None:
                if not flips_ok(acc):
                    errs.append('turn-run rule violated at block %d: '
                                'turns %s' % (i, acc))
                continue
            if hprev is None:
                ride_dfs(k, hk, acc)
                continue
            t = hwrap(hn(hk) - hn(hprev))
            if abs(t) != 1:
                errs.append('non-lattice turn %d at block %d (%d,%d,%d)'
                            % (t, i, blks[i]['x'], blks[i]['y'],
                               blks[i]['z']))
                continue
            ride_dfs(k, hk, acc + [t])

    for i in live:
        if len(errs) > 400:
            break             # flood guard: something is very wrong
        b = blks[i]
        arrs = [h for h in (b['h'], b.get('h2')) if h is not None]
        if arrs:
            for a in arrs:
                ride_dfs(i, a, [])
        else:
            ride_dfs(i, None, [])

    # SPLICE_SUPPRESS (v3 user rule): once a splice fires, no other
    # trigger may sit within SPLICE_SUPPRESS bounces of where the
    # player lands. Triggers live on the first two blocks of every
    # replica tail; a player who fired trigger k lands on win[k+1], so
    # walk every downstream route from both landing points and demand
    # the ride is trigger-free for SPLICE_SUPPRESS bounces
    triggers = {}
    for sp in sim.splices:
        for k in (0, 1):
            if k < len(sp['copy']):
                triggers[sp['copy'][k]] = sp['branch']
    for sp in sim.splices:
        for k in (1, 2):
            if k >= len(sp['win']):
                continue
            start = sp['win'][k]
            q = deque([(start, 0)])
            seen = {start}
            while q:
                i, n = q.popleft()
                if n > 0 and i in triggers:
                    errs.append('splice suppression: trigger of branch '
                                '%d only %d bounces after the landing '
                                'of branch %d (< %d)'
                                % (triggers[i], n, sp['branch'],
                                   SPLICE_SUPPRESS))
                    break
                if n >= SPLICE_SUPPRESS:
                    continue
                for kk in sim.kids.get(i, ()):
                    if kk not in seen and blks[kk] is not None:
                        seen.add(kk)
                        q.append((kk, n + 1))

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
        t0 = time.time()
        sim = Sim(seed)
        if not sim.run():
            print('seed %d: could not route golden trunk / funnel (%s)'
                  % (seed, sim.fail))
            continue
        t_gen = time.time() - t0
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
        print('v3 timing: generate %.2fs, verify+emit %.2fs; gap stages '
              '%s; chew-erased %d'
              % (t_gen, time.time() - t0 - t_gen,
                 getattr(sim, 'gap_stages', {}), st['unspliced']))
        return
    print('no seed satisfied all constraints')
    sys.exit(1)


if __name__ == '__main__':
    main()
