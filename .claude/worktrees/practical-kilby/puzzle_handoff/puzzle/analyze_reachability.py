#!/usr/bin/env python3
"""
Reachability analysis: from initial state, can any configuration move reds?
We don't care about finding a solution, just whether ANY reachable state has
reds at new positions (proving chains can form through cascading).

Strategy: BFS limited by conversion budget and depth, tracking red positions.
"""
from fast_engine import (
    State, parse_initial, compound_moves, find_all_chains,
    int_to_pos, pos_to_int, COLOR_IDS, ID_TO_COLOR, GOAL_POS,
    X_MIN, X_MAX, Y_MIN, Y_MAX, Z_MIN, Z_MAX
)
import time

RED_ID = COLOR_IDS['red']


def red_signature(state):
    positions = []
    for pi, (c, is_c) in state.grid.items():
        if c == RED_ID:
            positions.append((int_to_pos(pi), is_c))
    positions.sort()
    return tuple(positions)


def red_positions_only(state):
    positions = set()
    for pi, (c, is_c) in state.grid.items():
        if c == RED_ID:
            positions.add(int_to_pos(pi))
    return frozenset(positions)


def main():
    initial = parse_initial()
    initial_red_sig = red_positions_only(initial)

    print(f"Initial red positions ({len(initial_red_sig)}):")
    for p in sorted(initial_red_sig):
        print(f"  {p}")

    # BFS exploring unique states up to some frontier
    seen_red_configs = {initial_red_sig}
    seen_states = {initial.fingerprint(): 0}
    frontier = [initial]

    max_depth = 8
    start = time.time()

    for depth in range(1, max_depth + 1):
        next_frontier = []
        for state in frontier:
            cm = compound_moves(state, conversion_limit=40)
            for new_state, desc, n_conv in cm:
                fp = new_state.fingerprint()
                if fp in seen_states:
                    if seen_states[fp] <= new_state.conversions:
                        continue
                seen_states[fp] = new_state.conversions

                rc = red_positions_only(new_state)
                if rc not in seen_red_configs:
                    seen_red_configs.add(rc)
                    diff = rc - initial_red_sig
                    if diff:
                        print(f"[d={depth}] NEW RED POSITIONS: {sorted(diff)}")
                        print(f"  move: {desc}")

                next_frontier.append(new_state)

        frontier = next_frontier
        elapsed = time.time() - start
        print(f"[d={depth}] frontier={len(frontier)}, "
              f"seen_states={len(seen_states)}, "
              f"red_configs={len(seen_red_configs)}, "
              f"t={elapsed:.1f}s")
        if elapsed > 120:
            print("TIMEOUT")
            break


if __name__ == '__main__':
    main()
