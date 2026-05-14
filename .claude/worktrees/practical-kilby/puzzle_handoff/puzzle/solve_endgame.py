#!/usr/bin/env python3
"""
Self-contained end-to-end solver.
Loads phase1_solution.txt, applies it, then searches for remaining moves to win.

Uses beam search with memory-efficient state storage.
Focused heuristic for end-game (red needs to reach goal).
"""

import sys
import time
import gc
import heapq
from collections import defaultdict

from fast_engine import (
    State, parse_initial, compound_moves, find_formable_chains,
    slide_chain, int_to_pos, pos_to_int, COLOR_IDS, ID_TO_COLOR, GOAL_POS,
    X_MIN, X_MAX, Y_MIN, Y_MAX, Z_MIN, Z_MAX
)
from validate_phase1 import parse_move_line, apply_move

RED_ID = COLOR_IDS['red']
GREEN_ID = COLOR_IDS['green']
PURPLE_ID = COLOR_IDS['purple']


def load_phase1_state():
    """Apply validated phase 1, return state."""
    with open('phase1_solution.txt', encoding='utf-8') as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    state = parse_initial()
    for line in lines:
        mv = parse_move_line(line)
        ns, err = apply_move(state, mv)
        if ns is None:
            raise RuntimeError(f"phase1 failed: {err} :: {line}")
        state = ns
    return state, lines


def is_won(state):
    v = state.get(GOAL_POS)
    return v is not None and v[0] == RED_ID and v[1]


def heuristic(state):
    """
    Heuristic H(state) estimating distance to goal.
    Lower is better. Returns -1 if won.
    """
    v = state.get(GOAL_POS)
    if v and v[0] == RED_ID and v[1]:
        return -1000

    # Any red concrete already at goal-adjacent?
    gx, gy, gz = GOAL_POS

    # Compute several signals:
    # 1. Min Manhattan distance from any red to goal
    # 2. Distance from red X-chain (current "mobile red" location) to goal-aligned position
    # 3. Blocker status at GOAL_POS
    # 4. Reds that are already concrete

    min_red_dist = 1e9
    reds = []
    reds_at_y146 = 0
    reds_at_z2546 = 0
    reds_concrete_count = 0
    for pi, (c, is_c) in state.grid.items():
        if c == RED_ID:
            pos = int_to_pos(pi)
            reds.append((pos, is_c))
            d = abs(pos[0] - gx) + abs(pos[1] - gy) + abs(pos[2] - gz)
            if d < min_red_dist:
                min_red_dist = d
            if pos[1] == gy:
                reds_at_y146 += 1
            if pos[2] == gz:
                reds_at_z2546 += 1
            if is_c:
                reds_concrete_count += 1

    # Blocker at goal
    blocker_bad = 0
    vg = state.get(GOAL_POS)
    if vg is not None and vg[0] != RED_ID:
        blocker_bad = 2

    # Goal-adjacent positions — presence of red here would be great
    adj_scores = 0
    for dx, dy, dz in [(1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]:
        ap = (gx + dx, gy + dy, gz + dz)
        va = state.get(ap)
        if va is not None and va[0] == RED_ID:
            adj_scores += 1
            if va[1]:
                adj_scores += 1

    # Check if red X-chain has been freed
    # Original X-chain at y=148, z=2548 - is still there?
    red_xchain_mobility = 0
    # Check +X blocker (6928, 148, 2548)
    vp = state.get((6928, 148, 2548))
    vm = state.get((6925, 148, 2548))
    if vp is None or vp[0] == RED_ID:
        red_xchain_mobility += 3  # +X clear
    if vm is None or vm[0] == RED_ID:
        red_xchain_mobility += 3  # -X clear

    h = (min_red_dist
         + blocker_bad
         - 0.3 * reds_at_y146
         - 0.3 * reds_at_z2546
         - 0.2 * reds_concrete_count
         - 1.0 * adj_scores
         - 0.5 * red_xchain_mobility)
    return h


def state_key(state):
    """Compact hashable signature."""
    # Pack entire grid as sorted tuple (small int keys)
    items = tuple(sorted((pi, v[0], int(v[1])) for pi, v in state.grid.items()))
    return items


def beam_search(initial_state, beam_width, max_depth, time_limit_s):
    if is_won(initial_state):
        return []

    frontier = [(initial_state, [])]
    visited = {}
    visited[state_key(initial_state)] = initial_state.conversions

    start = time.time()
    initial_h = heuristic(initial_state)
    print(f"[0s] Start: h={initial_h:.2f}, conv={initial_state.conversions}")

    for depth in range(1, max_depth + 1):
        if time.time() - start > time_limit_s:
            print(f"[TIMEOUT] at depth {depth}")
            return None

        next_frontier = []
        n_exp = 0
        n_dup = 0

        for state, moves in frontier:
            cm = compound_moves(state, conversion_limit=60)
            n_exp += 1
            for ns, desc, nconv in cm:
                k = state_key(ns)
                prev = visited.get(k)
                if prev is not None and prev <= ns.conversions:
                    n_dup += 1
                    continue
                visited[k] = ns.conversions

                if is_won(ns):
                    elapsed = time.time() - start
                    print(f"\n*** WIN at depth {depth} in {elapsed:.1f}s ***")
                    return moves + [desc]

                h = heuristic(ns)
                next_frontier.append((h, ns, moves + [desc]))

        if not next_frontier:
            print(f"[d={depth}] empty frontier")
            return None

        next_frontier.sort(key=lambda x: x[0])
        next_frontier = next_frontier[:beam_width]

        elapsed = time.time() - start
        best_h = next_frontier[0][0]
        print(f"[{elapsed:.1f}s] d={depth} exp={n_exp} "
              f"front={len(next_frontier)} dup={n_dup} "
              f"best_h={best_h:.2f} visited={len(visited)}")

        # Memory hygiene
        if len(visited) > 3_000_000:
            # Keep only lowest-conversion half
            items = list(visited.items())
            items.sort(key=lambda x: x[1])
            visited = dict(items[:500_000])
            gc.collect()

        frontier = [(s, m) for h, s, m in next_frontier]

    print("No solution within depth")
    return None


def verify(initial_state, solution):
    state = initial_state
    for i, m in enumerate(solution):
        cm = compound_moves(state, conversion_limit=60)
        found = None
        for ns, desc, nc in cm:
            if desc == m:
                found = ns
                break
        if found is None:
            print(f"Verify FAIL at {i+1}: {m}")
            return False
        state = found
    return is_won(state)


if __name__ == '__main__':
    bw = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    md = int(sys.argv[2]) if len(sys.argv) > 2 else 25
    tl = int(sys.argv[3]) if len(sys.argv) > 3 else 300

    state, phase1_moves = load_phase1_state()
    print(f"Phase 1 loaded: {len(phase1_moves)} moves, conv={state.conversions}")
    print(f"Config: beam={bw}, depth={md}, time={tl}s")

    sol = beam_search(state, bw, md, tl)
    if sol is None:
        print("FAILED")
        sys.exit(1)

    full = phase1_moves + sol
    print(f"\nFull solution: {len(full)} moves")
    # Verify from initial
    initial = parse_initial()
    ok = verify(initial, full)
    print(f"Verify: {ok}")

    with open('full_solution.txt', 'w', encoding='utf-8') as f:
        for m in full:
            f.write(m + '\n')
    print("Saved full_solution.txt")
