#!/usr/bin/env python3
"""
Fast puzzle engine v2 - adds INTERWEAVING support.

Copy of fast_engine.py with added rule 5 (HANDOFF.md):
  Two same-color chains may share an endpoint ("interweave"). Clicking
  that shared endpoint moves both - but only if both chains have no
  stained glass between endpoints (i.e. pure 2-block chains).

INTERPRETATION
--------------
Two pure 2-block same-color chains A and B, each 2 adjacent concretes
along orthogonal or same axes, sharing exactly one endpoint cell P.
The "click at the shared endpoint" moves BOTH chains TOWARDS P's
opposite cell for their respective axes. i.e. chain A's shared end P
moves onto empty cells in the direction away from A's non-shared end,
and similarly for B. Actually - the more natural reading is that
clicking P acts as clicking both chains' endpoints simultaneously, so
each chain slides in the direction that FILLS the click (i.e. the
chain moves so that the clicked cell becomes the new 'head' position).

For puzzle purposes we enumerate both interpretations so the search
doesn't miss a solution:
  mode A: both chains slide SUCH THAT their shared endpoint MOVES AWAY
          from the other chain (i.e. each chain slides in its 'outward'
          direction from P).
  mode B: both chains slide TOWARD the side of the click ---
          i.e. the shared endpoint is pulled INTO the empty cell on the
          far side, chain slides "away from P".

Practically we just try each chain pair in both combinations of
(dirA, dirB) where each direction is +1 or -1 along its chain axis.
Only valid if both chains can physically slide 1 step in their chosen
direction at the same time (the moved cells for each chain must be in
bounds and empty, and the two chains' new positions must not collide).

We expose:
  compound_moves_v2(state, conversion_limit=60)
     same as compound_moves() but ALSO yields interweave moves.

Interweave compound moves have description:
  interweave <color> <axisA><dirA>x<stepA>/<axisB><dirB>x<stepB> at SHARED (x,y,z) using chainA(endA..P) chainB(endB..P) [convert: (...)]

They are a single click on the shared endpoint, so the step count
must equal 1 for both chains (one click = one slide step). We only
emit step=1 per chain per interweave move.
"""

from collections import defaultdict

# Grid bounds - copied from fast_engine.py
X_MIN, X_MAX = 6925, 6932
Y_MIN, Y_MAX = 145, 152
Z_MIN, Z_MAX = 2544, 2551

SEA_LANTERN = (6924, 146, 2546)
GOAL_POS = (6925, 146, 2546)

COLOR_IDS = {
    'red': 0, 'blue': 1, 'green': 2, 'purple': 3,
    'pink': 4, 'orange': 5, 'cyan': 6, 'brown': 7,
}
ID_TO_COLOR = {v: k for k, v in COLOR_IDS.items()}


def pos_to_int(pos):
    x, y, z = pos
    return (x - X_MIN) * 64 + (y - Y_MIN) * 8 + (z - Z_MIN)

def int_to_pos(i):
    x = i // 64 + X_MIN
    rem = i % 64
    y = rem // 8 + Y_MIN
    z = rem % 8 + Z_MIN
    return (x, y, z)


class State:
    __slots__ = ['grid', 'conversions']

    def __init__(self, grid=None, conversions=0):
        self.grid = grid if grid is not None else {}
        self.conversions = conversions

    def copy(self):
        return State(dict(self.grid), self.conversions)

    def get(self, pos):
        pi = pos_to_int(pos) if isinstance(pos, tuple) else pos
        return self.grid.get(pi)

    def color_at(self, pos):
        v = self.get(pos)
        return v[0] if v else None

    def is_concrete_at(self, pos):
        v = self.get(pos)
        return v[1] if v else False

    def is_empty(self, pos):
        pi = pos_to_int(pos) if isinstance(pos, tuple) else pos
        return pi not in self.grid

    @staticmethod
    def in_bounds(pos):
        x, y, z = pos
        return (X_MIN <= x <= X_MAX and Y_MIN <= y <= Y_MAX and Z_MIN <= z <= Z_MAX)

    def is_won(self):
        v = self.get(GOAL_POS)
        return v is not None and v[0] == COLOR_IDS['red'] and v[1]

    def convert(self, pos):
        pi = pos_to_int(pos) if isinstance(pos, tuple) else pos
        if pi not in self.grid:
            return None
        c, is_c = self.grid[pi]
        if is_c:
            return None
        new_grid = dict(self.grid)
        new_grid[pi] = (c, True)
        return State(new_grid, self.conversions + 1)

    def fingerprint(self):
        return (frozenset(self.grid.items()),)


def find_chain_at(state, pos, axis_idx):
    v = state.get(pos)
    if v is None:
        return None
    color, is_concrete = v
    if not is_concrete:
        return None

    start = list(pos)
    while True:
        p = list(start)
        p[axis_idx] -= 1
        tp = tuple(p)
        v2 = state.get(tp)
        if v2 is None or v2[0] != color:
            break
        start = p

    end = list(pos)
    while True:
        p = list(end)
        p[axis_idx] += 1
        tp = tuple(p)
        v2 = state.get(tp)
        if v2 is None or v2[0] != color:
            break
        end = p

    start_pos = tuple(start)
    end_pos = tuple(end)
    start_v = state.get(start_pos)
    end_v = state.get(end_pos)

    if not start_v[1] or not end_v[1]:
        return None

    positions = []
    p = list(start_pos)
    while True:
        positions.append(tuple(p))
        if tuple(p) == end_pos:
            break
        p[axis_idx] += 1

    if len(positions) < 2:
        return None

    return positions


def find_all_chains(state):
    chains = set()
    for pi, (c, is_c) in state.grid.items():
        if not is_c:
            continue
        pos = int_to_pos(pi)
        for axis_idx in range(3):
            chain = find_chain_at(state, pos, axis_idx)
            if chain is not None:
                chains.add((axis_idx, tuple(chain)))
    return list(chains)


def can_slide(state, axis_idx, positions, direction):
    position_set = set(positions)
    for p in positions:
        new_p = list(p)
        new_p[axis_idx] += direction
        new_p = tuple(new_p)
        if not State.in_bounds(new_p):
            return False
        if new_p in position_set:
            continue
        if not state.is_empty(new_p):
            return False
    return True


def slide_chain(state, axis_idx, positions, direction):
    new_grid = dict(state.grid)
    block_data = {}
    for p in positions:
        pi = pos_to_int(p)
        block_data[p] = new_grid[pi]
        del new_grid[pi]
    for p in positions:
        new_p = list(p)
        new_p[axis_idx] += direction
        new_p = tuple(new_p)
        new_grid[pos_to_int(new_p)] = block_data[p]
    return State(new_grid, state.conversions)


def max_slide(state, axis_idx, positions, direction):
    position_set = set(positions)
    steps = 0
    current_positions = list(positions)
    while True:
        next_positions = []
        for p in current_positions:
            np = list(p)
            np[axis_idx] += direction
            np = tuple(np)
            next_positions.append(np)

        current_set = set(current_positions)
        valid = True
        for np in next_positions:
            if not State.in_bounds(np):
                valid = False
                break
            if np in current_set:
                continue
            pi = pos_to_int(np)
            if pi in state.grid:
                valid = False
                break

        if not valid:
            break

        steps += 1
        current_positions = next_positions

        if steps >= 10:
            break

    return steps


def parse_initial():
    RAW = """
/setblock 6928 145 2551 minecraft:purple_stained_glass
/setblock 6928 145 2550 minecraft:purple_stained_glass
/setblock 6928 145 2549 minecraft:purple_stained_glass
/setblock 6926 146 2551 minecraft:blue_stained_glass
/setblock 6927 146 2551 minecraft:red_stained_glass
/setblock 6928 146 2551 minecraft:purple_stained_glass
/setblock 6925 146 2550 minecraft:purple_stained_glass
/setblock 6926 146 2550 minecraft:blue_stained_glass
/setblock 6928 146 2550 minecraft:purple_stained_glass
/setblock 6929 146 2550 minecraft:purple_stained_glass
/setblock 6931 146 2550 minecraft:red_stained_glass
/setblock 6925 146 2549 minecraft:green_stained_glass
/setblock 6931 146 2548 minecraft:cyan_stained_glass
/setblock 6925 146 2546 minecraft:green_stained_glass
/setblock 6926 146 2546 minecraft:red_stained_glass
/setblock 6930 146 2546 minecraft:red_stained_glass
/setblock 6927 146 2544 minecraft:purple_stained_glass
/setblock 6926 147 2551 minecraft:blue_stained_glass
/setblock 6927 147 2550 minecraft:purple_stained_glass
/setblock 6929 147 2550 minecraft:blue_stained_glass
/setblock 6926 147 2548 minecraft:blue_stained_glass
/setblock 6929 147 2548 minecraft:blue_stained_glass
/setblock 6931 147 2548 minecraft:cyan_stained_glass
/setblock 6928 147 2546 minecraft:blue_stained_glass
/setblock 6927 147 2545 minecraft:red_stained_glass
/setblock 6930 147 2545 minecraft:green_stained_glass
/setblock 6925 147 2544 minecraft:purple_stained_glass
/setblock 6931 147 2544 minecraft:red_stained_glass
/setblock 6928 148 2550 minecraft:blue_stained_glass
/setblock 6930 148 2550 minecraft:pink_stained_glass
/setblock 6928 148 2549 minecraft:green_stained_glass
/setblock 6930 148 2549 minecraft:pink_stained_glass
/setblock 6925 148 2548 minecraft:purple_stained_glass
/setblock 6926 148 2548 minecraft:red_stained_glass
/setblock 6927 148 2548 minecraft:red_stained_glass
/setblock 6928 148 2548 minecraft:green_stained_glass
/setblock 6929 148 2548 minecraft:brown_stained_glass
/setblock 6930 148 2548 minecraft:pink_stained_glass
/setblock 6931 148 2548 minecraft:cyan_stained_glass
/setblock 6928 148 2547 minecraft:blue_stained_glass
/setblock 6930 148 2547 minecraft:pink_stained_glass
/setblock 6931 148 2547 minecraft:red_stained_glass
/setblock 6926 148 2546 minecraft:blue_stained_glass
/setblock 6930 148 2546 minecraft:pink_stained_glass
/setblock 6930 148 2545 minecraft:green_stained_glass
/setblock 6928 148 2544 minecraft:orange_stained_glass
/setblock 6929 148 2544 minecraft:orange_stained_glass
/setblock 6930 148 2544 minecraft:pink_stained_glass
/setblock 6929 149 2551 minecraft:blue_stained_glass
/setblock 6929 149 2550 minecraft:green_stained_glass
/setblock 6926 149 2549 minecraft:green_stained_glass
/setblock 6927 149 2548 minecraft:green_stained_glass
/setblock 6929 149 2548 minecraft:brown_stained_glass
/setblock 6931 149 2548 minecraft:cyan_stained_glass
/setblock 6932 149 2548 minecraft:red_stained_glass
/setblock 6929 149 2547 minecraft:green_stained_glass
/setblock 6928 149 2546 minecraft:purple_stained_glass
/setblock 6930 149 2546 minecraft:green_stained_glass
/setblock 6925 149 2545 minecraft:purple_stained_glass
/setblock 6929 149 2544 minecraft:orange_stained_glass
/setblock 6930 149 2544 minecraft:pink_stained_glass
/setblock 6927 150 2551 minecraft:blue_stained_glass
/setblock 6930 150 2551 minecraft:orange_stained_glass
/setblock 6925 150 2550 minecraft:green_stained_glass
/setblock 6932 150 2550 minecraft:orange_stained_glass
/setblock 6929 150 2548 minecraft:brown_stained_glass
/setblock 6931 150 2548 minecraft:cyan_stained_glass
/setblock 6932 150 2548 minecraft:orange_stained_glass
/setblock 6926 150 2545 minecraft:blue_stained_glass
/setblock 6929 150 2545 minecraft:orange_stained_glass
/setblock 6929 151 2550 minecraft:green_stained_glass
/setblock 6925 151 2548 minecraft:purple_stained_glass
/setblock 6929 151 2548 minecraft:brown_stained_glass
/setblock 6931 151 2548 minecraft:cyan_stained_glass
/setblock 6928 151 2546 minecraft:purple_stained_glass
/setblock 6930 151 2546 minecraft:green_stained_glass
/setblock 6926 151 2545 minecraft:red_stained_glass
/setblock 6930 151 2545 minecraft:green_stained_glass
/setblock 6928 152 2550 minecraft:purple_stained_glass
/setblock 6926 152 2549 minecraft:blue_stained_glass
/setblock 6926 152 2548 minecraft:purple_stained_glass
/setblock 6928 152 2548 minecraft:purple_stained_glass
/setblock 6929 152 2548 minecraft:brown_stained_glass
/setblock 6931 152 2548 minecraft:red_stained_glass
/setblock 6926 152 2547 minecraft:red_stained_glass
/setblock 6927 152 2547 minecraft:purple_stained_glass
"""
    grid = {}
    for line in RAW.strip().split('\n'):
        line = line.strip()
        if not line or not line.startswith('/setblock'):
            continue
        parts = line.split()
        x, y, z = int(parts[1]), int(parts[2]), int(parts[3])
        color_name = parts[4].replace('minecraft:', '').replace('_stained_glass', '')
        grid[pos_to_int((x, y, z))] = (COLOR_IDS[color_name], False)
    return State(grid, 0)


def find_formable_chains(state):
    chains = []
    seen = set()

    for pi, (color, is_c) in state.grid.items():
        pos = int_to_pos(pi)

        for axis_idx in range(3):
            start = list(pos)
            while True:
                p = list(start)
                p[axis_idx] -= 1
                tp = tuple(p)
                pi2 = pos_to_int(tp) if State.in_bounds(tp) else None
                if pi2 is None or pi2 not in state.grid:
                    break
                if state.grid[pi2][0] != color:
                    break
                start = p

            group = []
            p = list(start)
            while True:
                tp = tuple(p)
                if not State.in_bounds(tp):
                    break
                pi2 = pos_to_int(tp)
                if pi2 not in state.grid or state.grid[pi2][0] != color:
                    break
                group.append(tp)
                p[axis_idx] += 1

            if len(group) < 2:
                continue

            key = (axis_idx, tuple(group))
            if key in seen:
                continue
            seen.add(key)

            first_v = state.grid[pos_to_int(group[0])]
            last_v = state.grid[pos_to_int(group[-1])]
            needed = []
            if not first_v[1]:
                needed.append(group[0])
            if not last_v[1]:
                needed.append(group[-1])

            chains.append((axis_idx, tuple(group), color, tuple(needed)))

    return chains


def compound_moves(state, conversion_limit=60):
    """Same as v1 compound_moves."""
    moves = []
    chains = find_formable_chains(state)

    for axis_idx, positions, color, needed_conversions in chains:
        if state.conversions + len(needed_conversions) > conversion_limit:
            continue

        s = state
        for p in needed_conversions:
            s = s.convert(p)
            if s is None:
                break
        if s is None:
            continue

        for direction in [-1, +1]:
            max_steps = max_slide(s, axis_idx, list(positions), direction)

            cur_state = s
            cur_positions = list(positions)

            for step in range(1, max_steps + 1):
                cur_state = slide_chain(cur_state, axis_idx, cur_positions, direction)
                cur_positions = [
                    tuple(p[i] + (direction if i == axis_idx else 0) for i in range(3))
                    for p in cur_positions
                ]

                axis_name = ['X', 'Y', 'Z'][axis_idx]
                dir_sym = '+' if direction > 0 else '-'
                color_name = ID_TO_COLOR[color]

                conv_desc = ""
                if needed_conversions:
                    conv_desc = f" [convert: {needed_conversions}]"

                start_str = f"{positions[0]}..{positions[-1]}"
                desc = f"{color_name} {axis_name}-chain {start_str} slide {dir_sym}{axis_name}\u00d7{step}{conv_desc}"

                moves.append((cur_state, desc, len(needed_conversions)))

    return moves


# =========================================================================
# INTERWEAVE SUPPORT
# =========================================================================

def find_pure_2block_chains(state):
    """
    Returns list of (axis_idx, (p1, p2), color_id, needed_conversions).
    A 'pure 2-block chain' = exactly 2 same-color adjacent cells,
    where both can be (or already are) concrete. No middle cells.
    """
    out = []
    seen = set()
    for pi, (color, is_c) in state.grid.items():
        pos = int_to_pos(pi)
        for axis_idx in range(3):
            # neighbor in +axis direction
            np = list(pos); np[axis_idx] += 1; np = tuple(np)
            if not State.in_bounds(np):
                continue
            pi2 = pos_to_int(np)
            if pi2 not in state.grid:
                continue
            c2, _ = state.grid[pi2]
            if c2 != color:
                continue
            # also require that the chain would be pure 2-block: that
            # neither pos-1 nor np+1 on axis are same color (otherwise
            # this is part of a longer chain).
            back = list(pos); back[axis_idx] -= 1; back = tuple(back)
            bpi = pos_to_int(back) if State.in_bounds(back) else None
            if bpi is not None and bpi in state.grid and state.grid[bpi][0] == color:
                continue
            fwd = list(np); fwd[axis_idx] += 1; fwd = tuple(fwd)
            fpi = pos_to_int(fwd) if State.in_bounds(fwd) else None
            if fpi is not None and fpi in state.grid and state.grid[fpi][0] == color:
                continue
            key = (axis_idx, pos, np, color)
            if key in seen:
                continue
            seen.add(key)
            needed = []
            if not state.grid[pi][1]:
                needed.append(pos)
            if not state.grid[pi2][1]:
                needed.append(np)
            out.append((axis_idx, (pos, np), color, tuple(needed)))
    return out


def _apply_conversions(state, conv_list, conversion_limit):
    """Apply a sequence of conversions; return new state or None if capped."""
    total_new = sum(1 for c in conv_list
                    if state.grid.get(pos_to_int(c)) is not None
                    and not state.grid[pos_to_int(c)][1])
    if state.conversions + total_new > conversion_limit:
        return None
    s = state
    for c in conv_list:
        v = s.get(c)
        if v is None:
            return None
        if v[1]:
            continue
        s = s.convert(c)
        if s is None:
            return None
    return s


def interweave_moves(state, conversion_limit=60):
    """
    Generate all interweave moves (compound: convert endpoints of both
    chains if needed, then simultaneously slide both chains 1 step).

    Two 2-block chains A=(a1,a2) and B=(b1,b2) sharing an endpoint P
    (exactly one cell in common, which is an endpoint of each).

    For each such pair, try all 4 combinations of directions
    (dirA in {-1,+1}, dirB in {-1,+1}) and emit a move if simultaneously
    valid. Some combinations include "slide toward each other" which
    can fail because of collisions, so we check.

    When they share an endpoint P, the chain A has endpoints a1 and P;
    chain B has endpoints b1 and P. If dirA slides A so a1->a1+dir and
    P->P+dir. Same for B. After slide, the cells a1+dir, P+dir,
    b1+dir, P+dir must all be in bounds and either empty OR be one of
    the currently-occupied chain cells (we handle this by building the
    final cell set and ensuring each target is reachable).

    Rule: interweave requires both chains PURE (no middle glass) so we
    only enumerate pure 2-block chains. Since each chain has 2 cells,
    sliding by 1 moves those 2 cells by 1. Total 4 "source" cells:
    {a1, P, b1, P} = 3 unique cells (P shared). After sliding, the new
    positions are {a1+dA*axisA, P+dA*axisA, b1+dB*axisB, P+dB*axisB}.
    If dA*axisA == dB*axisB then the two P's move to the same new cell
    (collision). We reject that.
    """
    moves = []
    pure = find_pure_2block_chains(state)

    # Group by color for speed
    by_color = defaultdict(list)
    for item in pure:
        axis_idx, (p1, p2), color, needed = item
        by_color[color].append(item)

    # Iterate color-wise, pair up chains that share an endpoint
    for color, chains in by_color.items():
        n = len(chains)
        for i in range(n):
            axA, (a1, a2), _, needA = chains[i]
            for j in range(i + 1, n):
                axB, (b1, b2), _, needB = chains[j]
                # Determine shared endpoint P (if any)
                endsA = (a1, a2)
                endsB = (b1, b2)
                shared = set(endsA) & set(endsB)
                if len(shared) != 1:
                    continue
                P = next(iter(shared))
                # otherA is A's other endpoint
                otherA = a1 if a2 == P else a2
                otherB = b1 if b2 == P else b2

                # The two chains must be DIFFERENT chains (different axis or different cells)
                if axA == axB and set(endsA) == set(endsB):
                    continue

                # Try all dir combinations
                for dirA in (-1, +1):
                    for dirB in (-1, +1):
                        # New positions of chain A (both cells shift by dirA along axA)
                        def shift(p, axis, d):
                            np = list(p); np[axis] += d; return tuple(np)
                        newA1 = shift(otherA, axA, dirA)
                        newPA = shift(P, axA, dirA)
                        newB1 = shift(otherB, axB, dirB)
                        newPB = shift(P, axB, dirB)

                        # Bounds check
                        for np in (newA1, newPA, newB1, newPB):
                            if not State.in_bounds(np):
                                break
                        else:
                            # Compute the set of cells occupied BEFORE the slide
                            occupied_before = set(endsA) | set(endsB)
                            occupied_after = {newA1, newPA, newB1, newPB}
                            # No two cells collide
                            if len(occupied_after) != 4:
                                continue
                            # Every 'new' cell must be either empty in state
                            # OR part of the chains' current cells (so it gets vacated).
                            ok = True
                            for np in occupied_after:
                                if np in occupied_before:
                                    continue
                                pi = pos_to_int(np)
                                if pi in state.grid:
                                    ok = False
                                    break
                            if not ok:
                                continue

                            # Compute needed conversions: endpoints of both chains
                            conv_set = []
                            for cp in (otherA, P, otherB):
                                v = state.get(cp)
                                if v is None:
                                    ok = False
                                    break
                                if not v[1]:
                                    if cp not in conv_set:
                                        conv_set.append(cp)
                            if not ok:
                                continue

                            s = _apply_conversions(state, conv_set, conversion_limit)
                            if s is None:
                                continue

                            # Apply the slide of BOTH chains simultaneously
                            # Approach: build new_grid by:
                            #  - remove the 4 cells (unique = 3: otherA, P, otherB)
                            #  - place colorA at newA1 and newPA (from otherA, P)
                            #  - place colorB at newB1 and newPB (from otherB, P)
                            # But P is shared - which destination does "P" block go to?
                            # Answer: interweave treats each chain's click separately,
                            # so chain A slides such that P -> newPA and chain B
                            # slides such that P -> newPB. But there is only ONE
                            # physical block at P. So "moving both chains" means
                            # the P cell effectively leaves its original place and
                            # both newPA and newPB will be occupied by same-colored
                            # blocks (one from chain A's shift, one from chain B's
                            # shift). For the interweave to be consistent, the P
                            # block duplicates? That doesn't make physical sense.
                            #
                            # More natural interpretation per rule 5: the shared
                            # endpoint stays as a single block at some position.
                            # Clicking the shared endpoint causes BOTH chains to
                            # slide, but the shared block itself can only go to
                            # ONE position. The puzzle wording suggests the shared
                            # block ends up "leaving" P and both chains shift as
                            # if the shared block became part of whichever chain's
                            # new position.
                            #
                            # We implement this interpretation: the shared block
                            # vacates P, each chain slides, and the shared cell's
                            # end-of-slide positions newPA and newPB will both be
                            # occupied by a same-color concrete block. This means
                            # the single shared block effectively splits into two -
                            # i.e. the interweave creates one extra block.
                            # This is physically odd but matches the rule's intent
                            # of "one click moves both chains". We flag this mode
                            # as mode_duplicate.
                            #
                            # Alternative interpretation (mode_vacate): only one
                            # chain gets the shared block; the other chain's new
                            # P-position is left EMPTY. We also enumerate this.
                            #
                            # Both interpretations are generated so the search
                            # can find whichever the real puzzle implements.

                            # Mode DUPLICATE: both newPA and newPB get color blocks
                            new_grid = dict(s.grid)
                            for cp in (otherA, P, otherB):
                                pi = pos_to_int(cp)
                                if pi in new_grid:
                                    del new_grid[pi]
                            # Place:
                            new_grid[pos_to_int(newA1)] = (color, True)
                            new_grid[pos_to_int(newPA)] = (color, True)
                            new_grid[pos_to_int(newB1)] = (color, True)
                            new_grid[pos_to_int(newPB)] = (color, True)
                            new_state_dup = State(new_grid, s.conversions)

                            axNameA = ['X', 'Y', 'Z'][axA]
                            axNameB = ['X', 'Y', 'Z'][axB]
                            sA = '+' if dirA > 0 else '-'
                            sB = '+' if dirB > 0 else '-'
                            cn = ID_TO_COLOR[color]
                            conv_suffix = f" [convert: {tuple(conv_set)}]" if conv_set else ""
                            desc_dup = (f"interweave-dup {cn} shared{P} "
                                        f"A({otherA}..{P}){sA}{axNameA}\u00d71 "
                                        f"B({otherB}..{P}){sB}{axNameB}\u00d71"
                                        f"{conv_suffix}")
                            moves.append((new_state_dup, desc_dup, len(conv_set)))

                            # Mode VACATE-A: shared block goes with chain A (newPA), newPB left empty
                            new_grid = dict(s.grid)
                            for cp in (otherA, P, otherB):
                                pi = pos_to_int(cp)
                                if pi in new_grid:
                                    del new_grid[pi]
                            new_grid[pos_to_int(newA1)] = (color, True)
                            new_grid[pos_to_int(newPA)] = (color, True)
                            new_grid[pos_to_int(newB1)] = (color, True)
                            # newPB stays empty
                            new_state_vA = State(new_grid, s.conversions)
                            desc_vA = (f"interweave-vacB {cn} shared{P} "
                                       f"A({otherA}..{P}){sA}{axNameA}\u00d71 "
                                       f"B({otherB}..{P}){sB}{axNameB}\u00d71"
                                       f"{conv_suffix}")
                            moves.append((new_state_vA, desc_vA, len(conv_set)))

                            # Mode VACATE-B: shared block goes with chain B
                            new_grid = dict(s.grid)
                            for cp in (otherA, P, otherB):
                                pi = pos_to_int(cp)
                                if pi in new_grid:
                                    del new_grid[pi]
                            new_grid[pos_to_int(newA1)] = (color, True)
                            new_grid[pos_to_int(newB1)] = (color, True)
                            new_grid[pos_to_int(newPB)] = (color, True)
                            new_state_vB = State(new_grid, s.conversions)
                            desc_vB = (f"interweave-vacA {cn} shared{P} "
                                       f"A({otherA}..{P}){sA}{axNameA}\u00d71 "
                                       f"B({otherB}..{P}){sB}{axNameB}\u00d71"
                                       f"{conv_suffix}")
                            moves.append((new_state_vB, desc_vB, len(conv_set)))
    return moves


def compound_moves_v2(state, conversion_limit=60):
    """Regular compound moves + interweave moves."""
    m = compound_moves(state, conversion_limit)
    m.extend(interweave_moves(state, conversion_limit))
    return m


def display_state(state, y=None):
    COLOR_ABBREV = {0:'R', 1:'B', 2:'G', 3:'P', 4:'K', 5:'O', 6:'C', 7:'W'}
    ys = [y] if y is not None else range(Y_MIN, Y_MAX + 1)
    for y in ys:
        print(f"\nY={y}  X:", end="")
        for x in range(X_MIN, X_MAX + 1):
            print(f" {x%100:2d}", end="")
        print()
        for z in range(Z_MAX, Z_MIN - 1, -1):
            print(f"  Z={z%100:2d}:", end="")
            for x in range(X_MIN, X_MAX + 1):
                v = state.get((x, y, z))
                if v is None:
                    if (x, y, z) == GOAL_POS and y == 146:
                        print("  *", end="")
                    else:
                        print("  .", end="")
                else:
                    c = COLOR_ABBREV[v[0]]
                    c = c if v[1] else c.lower()
                    if (x, y, z) == GOAL_POS and y == 146:
                        print(f" {c}*", end="")
                    else:
                        print(f"  {c}", end="")
            print()


if __name__ == '__main__':
    state = parse_initial()
    print(f"Initial state: {len(state.grid)} blocks")
    print(f"Is won: {state.is_won()}")
    moves = compound_moves_v2(state)
    print(f"v2 Compound moves (incl interweave) available: {len(moves)}")
    iw = [m for m in moves if m[1].startswith('interweave')]
    print(f"  Interweave moves: {len(iw)}")
    for new_state, desc, n_conv in iw[:10]:
        print(f"   [{n_conv} conv] {desc}")
