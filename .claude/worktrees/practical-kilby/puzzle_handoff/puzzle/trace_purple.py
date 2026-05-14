#!/usr/bin/env python3
"""
Trace where purples can go. Specifically: can a purple ever reach
(6925, 149, 2548) or (6925, 150, 2548)?
Uses BFS over purple chain movements only.
"""

from fast_engine import (
    parse_initial, compound_moves, find_formable_chains, int_to_pos,
    COLOR_IDS, ID_TO_COLOR, slide_chain, max_slide, pos_to_int,
    State, X_MIN, X_MAX, Y_MIN, Y_MAX, Z_MIN, Z_MAX
)
from validate_phase1 import parse_move_line, apply_move
from collections import defaultdict
import time


PURPLE_ID = COLOR_IDS['purple']
TARGETS = [(6925, 149, 2548), (6925, 150, 2548)]


def load_phase1():
    with open('phase1_solution.txt', encoding='utf-8') as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    state = parse_initial()
    for line in lines:
        mv = parse_move_line(line)
        ns, err = apply_move(state, mv)
        if ns is None:
            raise RuntimeError(err)
        state = ns
    return state


def purple_positions(state):
    ps = []
    for pi, (c, is_c) in state.grid.items():
        if c == PURPLE_ID:
            ps.append(int_to_pos(pi))
    return frozenset(ps)


def main():
    state = load_phase1()
    init_purples = purple_positions(state)
    print(f"Initial purple positions ({len(init_purples)}):")
    for p in sorted(init_purples):
        print(f"  {p}")

    # BFS: how do purple positions change across reachable states?
    # We explore ALL moves (not just purple) because other-color moves may cascade.
    seen_purple_configs = {init_purples}
    seen_states = {state.fingerprint(): 0}
    frontier = [state]
    start = time.time()

    for depth in range(1, 7):
        next_frontier = []
        new_purple_seen = 0
        for s in frontier:
            cm = compound_moves(s, conversion_limit=50)
            for ns, desc, nc in cm:
                fp = ns.fingerprint()
                if fp in seen_states and seen_states[fp] <= ns.conversions:
                    continue
                seen_states[fp] = ns.conversions
                pp = purple_positions(ns)
                if pp not in seen_purple_configs:
                    seen_purple_configs.add(pp)
                    new_purple_seen += 1
                    diff = pp - init_purples
                    if any(t in diff for t in TARGETS):
                        print(f"[d={depth}] TARGET REACHED by: {desc}")
                        print(f"   new purple positions: {sorted(diff)}")
                        return

                next_frontier.append(ns)

        elapsed = time.time() - start
        print(f"[d={depth}] frontier={len(next_frontier)}, seen={len(seen_states)}, "
              f"purple_configs={len(seen_purple_configs)}, new={new_purple_seen}, t={elapsed:.1f}s")
        frontier = next_frontier
        if elapsed > 90:
            print("TIMEOUT")
            break

    # Check all unique purple positions reached
    all_seen = set()
    for pc in seen_purple_configs:
        all_seen |= pc
    novel = all_seen - init_purples
    print(f"\nNew purple positions ever reached: {len(novel)}")
    for p in sorted(novel):
        mark = "*" if p in TARGETS else ""
        print(f"  {p}{mark}")

    # If targets not in novel, structurally can't put purple there from phase1 state
    for t in TARGETS:
        if t in novel:
            print(f"✓ Target {t} is reachable")
        else:
            print(f"✗ Target {t} NOT reachable (within search depth)")


if __name__ == '__main__':
    main()
