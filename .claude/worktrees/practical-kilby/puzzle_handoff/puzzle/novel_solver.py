#!/usr/bin/env python3
"""
Novel solver for the 3D sliding block puzzle.
Goal: red concrete at (6925, 146, 2546).

Strategy:
1. Load phase1 end state (15 moves, 19 conversions used).
2. Run a beam search with a structural heuristic that rewards:
   - reds near the goal
   - red chains existing (axis-aligned red pairs at similar y/z)
   - green blocker cell being empty or non-green
3. Cap conversions at 60.
4. Limit memory with bounded beam width and frontier size.
"""

import sys
import time
import heapq
import pickle
from collections import defaultdict

from fast_engine import (
    State, parse_initial, compound_moves, int_to_pos, pos_to_int,
    COLOR_IDS, ID_TO_COLOR, GOAL_POS, display_state
)
from validate_phase1 import parse_move_line, apply_move

RED = COLOR_IDS['red']
GREEN = COLOR_IDS['green']

MAX_CONVERSIONS = 60
GOAL = GOAL_POS  # (6925, 146, 2546)


def build_phase1_end():
    """Apply phase1_solution.txt and return ending state + the lines."""
    state = parse_initial()
    phase1_lines = []
    with open('phase1_solution.txt', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            phase1_lines.append(line)
            mv = parse_move_line(line)
            state, err = apply_move(state, mv)
            if state is None:
                print(f'Phase1 parse error: {err}')
                sys.exit(1)
    return state, phase1_lines


def red_positions(state):
    return [int_to_pos(pi) for pi, (c, _) in state.grid.items() if c == RED]


def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])


def goal_cell_status(state):
    """Return code: 0=empty, 1=red, 2=green(blocker), 3=other."""
    v = state.get(GOAL)
    if v is None:
        return 0
    c = v[0]
    if c == RED:
        return 1
    if c == GREEN:
        return 2
    return 3


def heuristic(state):
    """
    Cost heuristic (lower = closer to goal).
    Structural:
      - If red concrete at goal -> 0
      - Else, distance from nearest red to goal
      - Bonus for reds at y=146
      - Bonus for reds at z=2546
      - Bonus for goal cell empty (not green blocker)
      - Bonus for reds at low x
    """
    # Win check
    v = state.get(GOAL)
    if v is not None and v[0] == RED and v[1]:
        return 0

    reds = red_positions(state)
    if not reds:
        return 999

    # Minimum Manhattan distance from any red to goal
    dist_min = min(manhattan(r, GOAL) for r in reds)

    # Count reds on target y=146 and z=2546 planes
    y146 = sum(1 for r in reds if r[1] == 146)
    z2546 = sum(1 for r in reds if r[2] == 2546)

    # Low-x reds (goal at x=6925)
    # Penalize high-x reds
    min_x = min(r[0] for r in reds)
    x_penalty = (min_x - 6925)

    # Blocker status
    blk = goal_cell_status(state)
    blk_penalty = 0
    if blk == 2:
        blk_penalty = 1  # green blocker present
    elif blk == 3:
        blk_penalty = 2  # other color blocker
    # blk==0 empty is good, blk==1 we won already

    # Count axis-aligned red pairs (potential chains)
    pairs = 0
    for i in range(len(reds)):
        for j in range(i+1, len(reds)):
            a, b = reds[i], reds[j]
            diff = tuple(b[k]-a[k] for k in range(3))
            shared = sum(1 for k in range(3) if diff[k] == 0)
            if shared == 2:
                pairs += 1

    h = dist_min * 2 + x_penalty + blk_penalty * 3 - y146 * 2 - z2546 * 2 - pairs
    return h


def state_key(state):
    """Compact hashable key for a state."""
    # Use frozenset of (pos_int, color, concrete_bit)
    items = []
    for pi, (c, is_c) in state.grid.items():
        items.append(pi * 16 + c * 2 + (1 if is_c else 0))
    items.sort()
    return tuple(items)


def beam_search(start_state, beam_width=200, max_depth=40, time_budget_sec=600, verbose=True):
    """
    Beam search with structural heuristic.
    Returns: (final_state, path, total_moves) or (None, [], 0) if no solution.
    Path is list of description strings.
    """
    t0 = time.time()
    # frontier: list of (state, path, g)
    frontier = [(start_state, [], 0)]
    seen = {state_key(start_state): 0}
    nodes_expanded = 0

    best_h = heuristic(start_state)
    best_state = start_state
    best_path = []

    for depth in range(max_depth):
        if time.time() - t0 > time_budget_sec:
            if verbose:
                print(f'Time budget exhausted at depth {depth}')
            break

        # Score + expand
        expansions = []
        for st, path, g in frontier:
            # win?
            if st.get(GOAL) is not None and st.get(GOAL)[0] == RED and st.get(GOAL)[1]:
                if verbose:
                    print(f'SOLVED at depth {depth}, conv={st.conversions}')
                return st, path, len(path)

            moves = compound_moves(st, conversion_limit=MAX_CONVERSIONS)
            for new_st, desc, conv_added in moves:
                if new_st.conversions > MAX_CONVERSIONS:
                    continue
                nodes_expanded += 1
                new_path = path + [desc]
                k = state_key(new_st)
                newg = g + 1
                if k in seen and seen[k] <= newg:
                    continue
                seen[k] = newg
                h = heuristic(new_st)
                # win check cheaper
                if h == 0:
                    if verbose:
                        print(f'SOLVED at depth {depth+1}, conv={new_st.conversions}, path={len(new_path)}')
                    return new_st, new_path, len(new_path)
                if h < best_h:
                    best_h = h
                    best_state = new_st
                    best_path = new_path
                expansions.append((h + newg * 0.5, new_st, new_path, newg))

        if not expansions:
            if verbose:
                print(f'No expansions at depth {depth}')
            break

        # Keep top beam_width
        expansions.sort(key=lambda x: x[0])
        frontier = [(s, p, g) for _, s, p, g in expansions[:beam_width]]

        if verbose and depth % 2 == 0:
            elapsed = time.time() - t0
            mem_mb_est = len(seen) * 200 / (1024 * 1024)
            print(f'Depth {depth+1}: frontier={len(frontier)}, seen={len(seen)}, '
                  f'best_h={best_h}, nodes={nodes_expanded}, t={elapsed:.1f}s, '
                  f'est_mem={mem_mb_est:.0f}MB')

    if verbose:
        print(f'\nBest state h={best_h}, path_len={len(best_path)}')
        print(f'Total nodes: {nodes_expanded}, seen: {len(seen)}')
    return best_state, best_path, len(best_path)


def verify_full(phase1_lines, solver_descs):
    """Apply phase1 + solver moves, verify win."""
    state = parse_initial()
    for line in phase1_lines:
        mv = parse_move_line(line)
        state, err = apply_move(state, mv)
        if state is None:
            return False, f'Phase1 failed: {err}'
    for line in solver_descs:
        mv = parse_move_line(line)
        if mv is None:
            return False, f'Cannot parse: {line}'
        state, err = apply_move(state, mv)
        if state is None:
            return False, f'Solver move failed: {err} on {line}'
    won = state.is_won()
    return won, f'conv={state.conversions}, won={won}'


def main():
    t_total_start = time.time()
    print('Loading phase1 end state...')
    start_state, phase1_lines = build_phase1_end()
    print(f'Phase1 end: conv={start_state.conversions}, blocks={len(start_state.grid)}')
    print(f'Initial heuristic: {heuristic(start_state)}')

    sys.stdout.reconfigure(line_buffering=True)
    # Try progressively wider beams if we have time
    configs = [
        (200, 30, 180),
        (500, 35, 300),
        (1000, 40, 400),
    ]

    best_solution = None
    for bw, md, tb in configs:
        elapsed_total = time.time() - t_total_start
        if elapsed_total > 850:
            break
        print(f'\n=== Beam search: width={bw}, depth={md}, budget={tb}s ===')
        remaining = min(tb, 850 - elapsed_total)
        st, path, plen = beam_search(start_state, beam_width=bw, max_depth=md, time_budget_sec=remaining)
        if st is not None and st.is_won():
            print(f'\nFound solution! Verifying...')
            ok, msg = verify_full(phase1_lines, path)
            print(f'Verification: {ok} — {msg}')
            if ok:
                best_solution = (path, st.conversions)
                break

    if best_solution:
        path, conv_used = best_solution
        total_moves = len(phase1_lines) + len(path)
        print(f'\n=== SOLUTION FOUND ===')
        print(f'Phase1 moves: {len(phase1_lines)}')
        print(f'Solver moves: {len(path)}')
        print(f'Total moves: {total_moves}')
        print(f'Conversions used: {conv_used}')

        with open('full_solution.txt', 'w', encoding='utf-8') as f:
            for line in phase1_lines:
                f.write(line + '\n')
            for line in path:
                f.write(line + '\n')
        print('Wrote full_solution.txt')
    else:
        print('\n=== NO SOLUTION FOUND ===')
        print('Final conclusion pending further analysis.')


if __name__ == '__main__':
    main()
