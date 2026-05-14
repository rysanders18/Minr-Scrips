"""
3D Chain Puzzle Solver
=====================
Solves a Minecraft 3D sliding-block puzzle (Rush Hour variant).

Chains = concrete-[glass*]-concrete of same color along one axis.
Chains slide 1 block when an endpoint is clicked.
Glass blocks can be irreversibly converted to concrete (max 60).
Goal: red concrete face-adjacent to the sea lantern.

Usage: edit the PUZZLE section at the bottom, then run:
    python chain_solver.py
"""

import numpy as np
from heapq import heappush, heappop
from time import time

# ── Grid Constants ───────────────────────────────────────────────────

SIZE = 9  # 9 to fit this puzzle's X-span; Y and Z use 0-7
EMPTY = 0
LANTERN = 1

COLORS = {
    'red': 0, 'orange': 1, 'yellow': 2, 'lime': 3, 'green': 4,
    'cyan': 5, 'light_blue': 6, 'blue': 7, 'purple': 8, 'magenta': 9,
    'pink': 10, 'white': 11, 'light_gray': 12, 'gray': 13, 'black': 14, 'brown': 15,
}
COLOR_NAMES = {v: k for k, v in COLORS.items()}
RED = COLORS['red']

ADJ6 = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]
AXIS_LABEL = 'xyz'

# ── Block-value encoding ────────────────────────────────────────────
#   EMPTY=0  LANTERN=1  glass(c)=2+2c  concrete(c)=3+2c

def glass(c):       return 2 + 2 * c
def concrete(c):    return 3 + 2 * c
def is_glass(v):    return v >= 2 and v % 2 == 0
def is_concrete(v): return v >= 3 and v % 2 == 1
def color_of(v):    return (v - 2) // 2 if v >= 2 else -1


# ── Chain Detection ──────────────────────────────────────────────────

def find_chains(grid):
    """
    Return every valid chain as (start, end, axis, color, has_glass).
    `start` always has the lower coordinate along `axis`.
    A chain is: concrete – [glass]* – concrete, all same color, contiguous
    along one axis.  Concrete blocks *between* endpoints break the chain.
    """
    chains = []
    for x in range(SIZE):
        for y in range(SIZE):
            for z in range(SIZE):
                v = grid[x, y, z]
                if not is_concrete(v):
                    continue
                c = color_of(v)
                # scan only in the positive direction to avoid duplicates
                for axis in range(3):
                    p = [x, y, z]
                    p[axis] += 1
                    has_glass = False
                    while 0 <= p[axis] < SIZE:
                        cv = grid[p[0], p[1], p[2]]
                        if color_of(cv) != c:
                            break
                        if is_glass(cv):
                            has_glass = True
                            p[axis] += 1
                            continue
                        if is_concrete(cv):
                            chains.append(((x, y, z), tuple(p), axis, c, has_glass))
                            break
                        break  # non-colored block
    return chains


# ── Chain Movement ───────────────────────────────────────────────────

def try_move(grid, start, end, axis, direction):
    """
    Slide a chain 1 step along *direction* (+1 or -1) on *axis*.
    Returns the new grid, or None if the move is blocked / out of bounds.
    """
    leading = list(end if direction > 0 else start)
    dest = leading[:]
    dest[axis] += direction

    if not (0 <= dest[axis] < SIZE):
        return None
    if grid[dest[0], dest[1], dest[2]] != EMPTY:
        return None

    # collect every block in the chain
    blocks = []
    p = list(start)
    while True:
        blocks.append((tuple(p), grid[p[0], p[1], p[2]]))
        if tuple(p) == end:
            break
        p[axis] += 1

    ng = grid.copy()
    for pos, _ in blocks:
        ng[pos[0], pos[1], pos[2]] = EMPTY
    for pos, val in blocks:
        np_ = list(pos)
        np_[axis] += direction
        ng[np_[0], np_[1], np_[2]] = val
    return ng


# ── Goal & Heuristic ────────────────────────────────────────────────

def is_won(grid, lpos):
    lx, ly, lz = lpos
    tgt = concrete(RED)
    for dx, dy, dz in ADJ6:
        nx, ny, nz = lx + dx, ly + dy, lz + dz
        if 0 <= nx < SIZE and 0 <= ny < SIZE and 0 <= nz < SIZE:
            if grid[nx, ny, nz] == tgt:
                return True
    return False


def heuristic(grid, lpos):
    """Min Manhattan distance from any red block to the lantern, minus 1."""
    lx, ly, lz = lpos
    best = SIZE * 3
    rg, rc = glass(RED), concrete(RED)
    for x in range(SIZE):
        for y in range(SIZE):
            for z in range(SIZE):
                v = grid[x, y, z]
                if v == rg or v == rc:
                    d = abs(x - lx) + abs(y - ly) + abs(z - lz)
                    if d < best:
                        best = d
    return max(0, best - 1)


def _block_mobility(grid, pos, color, depth, max_depth, visiting):
    """
    Recursively estimate the minimum number of actions needed to move
    a colored block at `pos` out of `pos` (i.e. make that cell empty).

    Returns an integer cost estimate. Higher = harder to clear.
    visiting: set of positions currently being considered (cycle detection).
    """
    if pos in visiting:
        return 8  # cycle — assume hard
    if depth >= max_depth:
        return 4  # bottom out — moderate penalty

    visiting.add(pos)
    best = 12
    x, y, z = pos

    # For each axis, see if this block can be part of a chain moving in either direction.
    for axis in range(3):
        # Find the potential chain endpoints along this axis (same color, contiguous)
        # Chain extends as far as possible on each side with matching-color cells.
        # Simplification: just look for ANY same-colored neighbor along the axis
        #   — that's the minimum needed to form a chain of length 2.
        has_partner = False
        for d in (-1, +1):
            p = [x, y, z]
            p[axis] += d
            if 0 <= p[axis] < SIZE:
                nv = grid[p[0], p[1], p[2]]
                if nv >= 2 and color_of(nv) == color:
                    has_partner = True
                    break

        chain_form_cost = 0 if has_partner else 3  # need to bring one adjacent somehow

        # Check each direction the chain could try to move
        for d in (-1, +1):
            # Where would the 'leading' edge go? Simplification: the cell just past `pos`
            # in direction d (treating `pos` as if it were the leading edge of a length-2 chain).
            dest = [x, y, z]
            dest[axis] += d
            if not (0 <= dest[axis] < SIZE):
                continue  # wall
            dv = grid[dest[0], dest[1], dest[2]]

            if dv == LANTERN:
                continue  # can't move into lantern
            if dv == EMPTY:
                cost = 1 + chain_form_cost  # just move (+ form chain if needed)
            else:
                # Something blocks the move — recurse
                dest_color = color_of(dv)
                if dest_color == color:
                    # Same-colored: would be part of chain, not a blocker
                    # (conservatively: treat as free to move further, approximate cost)
                    cost = 1 + chain_form_cost
                else:
                    sub = _block_mobility(grid, tuple(dest), dest_color,
                                          depth + 1, max_depth, visiting)
                    cost = 1 + chain_form_cost + sub

            if cost < best:
                best = cost

    visiting.discard(pos)
    return best


def heuristic_blocker(grid, lpos):
    """
    Recursive-blocker heuristic.

    Takes the nearest red block, walks the Manhattan path toward the lantern, and for
    every non-red/non-empty cell on that path adds an estimate of how hard that
    cell is to clear (which in turn may depend on its own blockers).
    """
    lx, ly, lz = lpos
    rg, rc = glass(RED), concrete(RED)

    nearest = None
    nearest_d = SIZE * 3
    for x in range(SIZE):
        for y in range(SIZE):
            for z in range(SIZE):
                v = grid[x, y, z]
                if v == rg or v == rc:
                    d = abs(x - lx) + abs(y - ly) + abs(z - lz)
                    if d < nearest_d:
                        nearest_d = d
                        nearest = (x, y, z)

    if nearest is None:
        return 100

    h = max(0, nearest_d - 1)

    # Is a red chain formable from `nearest`?
    rx, ry, rz = nearest
    red_chain = False
    for ax in range(3):
        for d in (-1, +1):
            p = [rx, ry, rz]
            p[ax] += d
            if 0 <= p[ax] < SIZE:
                nv = grid[p[0], p[1], p[2]]
                if nv >= 2 and color_of(nv) == RED:
                    red_chain = True
                    break
        if red_chain:
            break
    if not red_chain:
        h += 3  # need to bring another red adjacent somehow

    # Walk the bounding box between nearest red and lantern; sum blocker costs.
    xs = range(min(rx, lx), max(rx, lx) + 1)
    ys = range(min(ry, ly), max(ry, ly) + 1)
    zs = range(min(rz, lz), max(rz, lz) + 1)

    blocker_total = 0
    for x in xs:
        for y in ys:
            for z in zs:
                if (x, y, z) == nearest or (x, y, z) == lpos:
                    continue
                v = grid[x, y, z]
                if v >= 2 and color_of(v) != RED:
                    c = color_of(v)
                    # Cost to clear this specific block (recursive, bounded)
                    cost = _block_mobility(grid, (x, y, z), c, 0, 2, set())
                    blocker_total += cost

    # Weight blockers; don't let them dominate the heuristic entirely.
    return h + blocker_total * 0.25


# ── Move Generation ─────────────────────────────────────────────────

def generate_moves(grid, conv_left, prune_conv=True):
    """
    Yield (new_grid, new_conv, move_tuple) for every legal successor.
    Chain moves are yielded before conversions (better move ordering).
    """
    chains = find_chains(grid)

    # -- endpoint map for interweave detection --
    ep = {}  # pos -> [(start, end, axis, color, has_glass, direction)]
    for s, e, ax, c, hg in chains:
        ep.setdefault(e, []).append((s, e, ax, c, hg, +1))   # click end  → +dir
        ep.setdefault(s, []).append((s, e, ax, c, hg, -1))   # click start→ -dir

    for pos, cms in ep.items():
        if len(cms) == 1:
            s, e, ax, c, hg, d = cms[0]
            ng = try_move(grid, s, e, ax, d)
            if ng is not None:
                yield ng, conv_left, ('click', pos, c, s, e, d, ax)
        else:
            # interweave: all must be same colour and glass-free
            same_color = len({c for _, _, _, c, _, _ in cms}) == 1
            no_glass = all(not hg for _, _, _, _, hg, _ in cms)
            if same_color and no_glass:
                ng = grid.copy()
                moved = False
                details = []
                for s, e, ax, c, hg, d in cms:
                    r = try_move(ng, s, e, ax, d)
                    if r is not None:
                        ng = r
                        moved = True
                        details.append((c, s, e, d, ax))
                if moved:
                    yield ng, conv_left, ('interweave', pos, details)
            # also let each chain be reached via its *other* endpoint
            # (those entries are separate keys in `ep`)

    # -- individual conversions: only if adjacent to existing concrete of same color --
    if conv_left > 0:
        for x in range(SIZE):
            for y in range(SIZE):
                for z in range(SIZE):
                    v = grid[x, y, z]
                    if not is_glass(v):
                        continue
                    c = color_of(v)
                    # Must be adjacent to existing CONCRETE of same color (extend/split chain)
                    useful = False
                    for ax in range(3):
                        for d in (-1, +1):
                            p = [x, y, z]
                            p[ax] += d
                            if 0 <= p[ax] < SIZE:
                                nv = grid[p[0], p[1], p[2]]
                                if is_concrete(nv) and color_of(nv) == c:
                                    useful = True
                                    break
                        if useful:
                            break
                    if not useful:
                        continue
                    ng = grid.copy()
                    ng[x, y, z] = v + 1
                    yield ng, conv_left - 1, ('convert', (x, y, z), c)

    # -- pair conversions: create a new chain in one atomic move (2 conversions) --
    if conv_left >= 2:
        seen_pairs = set()
        for x in range(SIZE):
            for y in range(SIZE):
                for z in range(SIZE):
                    v = grid[x, y, z]
                    if not is_glass(v):
                        continue
                    c = color_of(v)
                    # Look for another same-colored glass along each axis (positive dir)
                    # with only same-colored glass between them
                    for axis in range(3):
                        p = [x, y, z]
                        p[axis] += 1
                        while 0 <= p[axis] < SIZE:
                            cv = grid[p[0], p[1], p[2]]
                            if color_of(cv) != c:
                                break  # different color or empty -> chain not formable
                            if is_glass(cv):
                                # Both (x,y,z) and tuple(p) are glass of color c.
                                # Convert both to concrete to form a chain.
                                pair_key = ((x, y, z), tuple(p), axis)
                                if pair_key not in seen_pairs:
                                    seen_pairs.add(pair_key)
                                    ng = grid.copy()
                                    ng[x, y, z] = v + 1
                                    ng[p[0], p[1], p[2]] = cv + 1
                                    yield ng, conv_left - 2, (
                                        'form_chain', (x, y, z), tuple(p), c, axis
                                    )
                            if is_concrete(cv):
                                break  # existing concrete blocks further scanning
                            p[axis] += 1


# ── Solver ───────────────────────────────────────────────────────────

def solve(grid, lpos, max_conv=60, max_states=500_000,
          strategy='astar', prune_conv=True,
          h_func=None, goal_func=None):
    """
    Search for a solution.

    strategy : 'astar'  – optimal (f = g + h)
               'greedy' – fast, non-optimal (f = h only)
    h_func   : callable(grid, lpos) -> float. Default = heuristic().
    goal_func: callable(grid, lpos) -> bool. Default = is_won(). Use to set sub-goals.

    Returns a list of move tuples, or None.
    """
    t0 = time()
    if h_func is None:
        h_func = heuristic
    if goal_func is None:
        goal_func = is_won

    if goal_func(grid, lpos):
        print("Already solved!")
        return []

    h0 = h_func(grid, lpos)
    cnt = 0
    # pq entries: (priority, tiebreak, grid_bytes, conv, depth, path_linked_list)
    pq = [(h0, cnt, grid.tobytes(), max_conv, 0, None)]
    # dominance: grid_bytes -> best conv remaining seen
    visited = {grid.tobytes(): max_conv}
    explored = 0
    best_h = h0

    print(f"Starting {strategy} search | h0={h0} | budget={max_conv} conv | limit={max_states} states")

    while pq and explored < max_states:
        pri, _, gb, conv, depth, path = heappop(pq)
        g = np.frombuffer(gb, dtype=np.int8).reshape(SIZE, SIZE, SIZE).copy()
        explored += 1

        h_now = pri - depth if strategy == 'astar' else pri
        if h_now < best_h:
            best_h = h_now
            print(f"  h={best_h}  depth={depth}  explored={explored}  "
                  f"queue={len(pq)}  {time() - t0:.1f}s")

        if explored % 100_000 == 0:
            print(f"  ...  explored={explored}  queue={len(pq)}  "
                  f"f={pri}  {time() - t0:.1f}s")

        for ng, nc, mv in generate_moves(g, conv, prune_conv):
            ngb = ng.tobytes()

            if goal_func(ng, lpos):
                moves = []
                p = (mv, path)
                while p is not None:
                    moves.append(p[0])
                    p = p[1]
                moves.reverse()
                elapsed = time() - t0
                print(f"\n  SOLVED  {len(moves)} moves | "
                      f"{explored + 1} states | {elapsed:.1f}s")
                return moves

            # dominance pruning: skip if we saw this grid with >= conv remaining
            prev = visited.get(ngb)
            if prev is not None and prev >= nc:
                continue
            visited[ngb] = nc

            hv = h_func(ng, lpos)
            cnt += 1
            npri = (depth + 1 + hv) if strategy == 'astar' else hv
            heappush(pq, (npri, cnt, ngb, nc, depth + 1, (mv, path)))

    elapsed = time() - t0
    print(f"\n  No solution after {explored} states | {elapsed:.1f}s")
    return None


# ── Grid Builder ─────────────────────────────────────────────────────

def build_grid(blocks, lpos):
    """
    blocks : list of (x, y, z, 'color')   – all start as stained glass
    lpos   : (x, y, z)                    – sea lantern position
    """
    grid = np.zeros((SIZE, SIZE, SIZE), dtype=np.int8)
    grid[lpos[0], lpos[1], lpos[2]] = LANTERN
    for x, y, z, color_name in blocks:
        grid[x, y, z] = glass(COLORS[color_name])
    return grid


# ── Visualisation helpers ────────────────────────────────────────────

ABBR = {
    0: 'Rd', 1: 'Or', 2: 'Yl', 3: 'Lm', 4: 'Gn', 5: 'Cn',
    6: 'Lb', 7: 'Bl', 8: 'Pr', 9: 'Mg', 10: 'Pk', 11: 'Wh',
    12: 'Lg', 13: 'Gy', 14: 'Bk', 15: 'Br',
}


def print_layer(grid, lpos, z):
    """Print one z-layer of the grid (y increases upward)."""
    print(f"--- z={z} ---     (y ^ , x ->)")
    for y in range(SIZE - 1, -1, -1):
        row = []
        for x in range(SIZE):
            v = grid[x, y, z]
            if (x, y, z) == lpos:
                row.append(' [L]')
            elif v == EMPTY:
                row.append('  . ')
            else:
                c = color_of(v)
                t = 'C' if is_concrete(v) else 'g'
                row.append(f' {ABBR[c]}{t}')
        print(''.join(row))
    print()


def print_grid(grid, lpos):
    for z in range(SIZE):
        occupied = False
        for x in range(SIZE):
            for y in range(SIZE):
                if grid[x, y, z] != EMPTY or (x, y, z) == lpos:
                    occupied = True
                    break
            if occupied:
                break
        if occupied:
            print_layer(grid, lpos, z)


def print_solution(moves):
    print("\n" + "=" * 50)
    print("  SOLUTION")
    print("=" * 50)

    for i, mv in enumerate(moves):
        if mv[0] == 'convert':
            _, pos, cid = mv
            print(f"  {i + 1:3d}. CONVERT  {COLOR_NAMES[cid]:>10s} glass  at {pos}")
        elif mv[0] == 'form_chain':
            _, s, e, cid, ax = mv
            axis_name = AXIS_LABEL[ax]
            print(f"  {i + 1:3d}. FORM     {COLOR_NAMES[cid]:>10s} chain "
                  f"{s}->{e}  (convert {s} + {e}) [along {axis_name}]")
        elif mv[0] == 'click':
            _, pos, cid, s, e, d, ax = mv
            arrow = f"{'+'if d > 0 else '-'}{AXIS_LABEL[ax]}"
            print(f"  {i + 1:3d}. CLICK    {COLOR_NAMES[cid]:>10s} chain "
                  f"{s}->{e}  [{arrow}]  (click {pos})")
        elif mv[0] == 'interweave':
            _, pos, details = mv
            parts = []
            for cid, s, e, d, ax in details:
                arrow = f"{'+'if d > 0 else '-'}{AXIS_LABEL[ax]}"
                parts.append(f"{COLOR_NAMES[cid]} {s}->{e} [{arrow}]")
            print(f"  {i + 1:3d}. INTERWEAVE at {pos}:  {' & '.join(parts)}")

    convs = sum(1 for m in moves if m[0] == 'convert')
    pair_convs = sum(1 for m in moves if m[0] == 'form_chain')
    total_convs = convs + pair_convs * 2
    clicks = len(moves) - convs - pair_convs
    print(f"\n  Total: {len(moves)} moves  ({total_convs} conversions, {clicks} slides)")
    print("=" * 50)


def replay_solution(initial_grid, lpos, moves):
    """Apply each move to the grid and print the state after every step."""
    grid = initial_grid.copy()
    for i, mv in enumerate(moves):
        if mv[0] == 'convert':
            _, (x, y, z), cid = mv
            grid[x, y, z] = grid[x, y, z] + 1  # glass -> concrete
        elif mv[0] == 'form_chain':
            _, s, e, cid, ax = mv
            grid[s[0], s[1], s[2]] = grid[s[0], s[1], s[2]] + 1
            grid[e[0], e[1], e[2]] = grid[e[0], e[1], e[2]] + 1
        elif mv[0] == 'click':
            _, pos, cid, s, e, d, ax = mv
            grid = try_move(grid, s, e, ax, d)
        elif mv[0] == 'interweave':
            _, pos, details = mv
            for cid, s, e, d, ax in details:
                r = try_move(grid, s, e, ax, d)
                if r is not None:
                    grid = r
        print(f"\n--- After step {i + 1} ---")
        print_grid(grid, lpos)

    won = is_won(grid, lpos)
    print(f"\nGoal reached: {won}")
    return grid


# ── Setblock File Parser ─────────────────────────────────────────────

def parse_setblock_file(filepath):
    """
    Parse a file of Minecraft /setblock commands.
    Returns (blocks, lantern_pos) with coordinates normalized to 0-based.
    """
    import re
    raw_blocks = []
    lantern_raw = None

    with open(filepath) as f:
        for m in re.finditer(
            r'/setblock\s+(\d+)\s+(\d+)\s+(\d+)\s+minecraft:(\w+)', f.read()
        ):
            x, y, z, block = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
            if block == 'sea_lantern':
                lantern_raw = (x, y, z)
            elif block.endswith('_stained_glass'):
                color = block.replace('_stained_glass', '')
                raw_blocks.append((x, y, z, color))

    if lantern_raw is None:
        raise ValueError("No sea_lantern found in file")

    # compute offsets so coordinates start at 0
    all_x = [b[0] for b in raw_blocks] + [lantern_raw[0]]
    all_y = [b[1] for b in raw_blocks] + [lantern_raw[1]]
    all_z = [b[2] for b in raw_blocks] + [lantern_raw[2]]
    ox, oy, oz = min(all_x), min(all_y), min(all_z)

    blocks = [(x - ox, y - oy, z - oz, c) for x, y, z, c in raw_blocks]
    lantern = (lantern_raw[0] - ox, lantern_raw[1] - oy, lantern_raw[2] - oz)

    print(f"Parsed {len(blocks)} blocks + lantern from {filepath}")
    print(f"World offset: ({ox}, {oy}, {oz})")
    print(f"Normalized lantern: {lantern}")
    return blocks, lantern


# ── Main ─────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import sys, os

    # Load puzzle from setblock file
    puzzle_file = os.path.join(os.path.dirname(__file__),
                               'Harha', 'chainweaverCoordinates.txt')
    if len(sys.argv) > 1:
        puzzle_file = sys.argv[1]

    blocks, lantern = parse_setblock_file(puzzle_file)
    grid = build_grid(blocks, lantern)

    # -- puzzle summary --
    color_counts = {}
    for x in range(SIZE):
        for y in range(SIZE):
            for z in range(SIZE):
                v = grid[x, y, z]
                if v >= 2:
                    cn = COLOR_NAMES[color_of(v)]
                    color_counts[cn] = color_counts.get(cn, 0) + 1

    print(f"\nPuzzle: {sum(color_counts.values())} blocks across "
          f"{len(color_counts)} colours")
    for cn in sorted(color_counts):
        print(f"  {cn:>12s}: {color_counts[cn]}")
    print(f"Sea lantern at {lantern}")
    print(f"Initial heuristic (Manhattan): {heuristic(grid, lantern)}")
    print()
    print_grid(grid, lantern)

    # -- solve --
    solution = solve(grid, lantern, strategy='astar', max_states=500_000)

    if solution is None:
        print("\nFalling back to greedy search ...\n")
        solution = solve(grid, lantern, strategy='greedy', max_states=2_000_000)

    if solution:
        print_solution(solution)
        # Uncomment to see step-by-step replay:
        # replay_solution(grid, lantern, solution)
    else:
        print("\nCould not solve within search limits.")
        print("Tips: increase max_states, disable prune_conv, or "
              "try a simpler sub-problem first.")
