#!/usr/bin/env python3
"""
Determine which positions RED can ever reach from the phase1 end state.
This is the critical question - is (6925, 146, 2546) reachable by any red at all?

Approach: BFS from phase1 end state, tracking the set of positions where any
RED has ever been seen. If (6925, 146, 2546) appears, solution might exist.

Memory-bounded: we track (positions where red ever existed) as a summary,
plus visited states via hashing.
"""
import sys
import time
from fast_engine import (
    parse_initial, compound_moves, int_to_pos, pos_to_int,
    COLOR_IDS, ID_TO_COLOR, GOAL_POS
)
from validate_phase1 import parse_move_line, apply_move

RED = COLOR_IDS['red']
GOAL = GOAL_POS

sys.stdout.reconfigure(line_buffering=True)

def load_phase1():
    state = parse_initial()
    with open('phase1_solution.txt', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            mv = parse_move_line(line)
            state, err = apply_move(state, mv)
    return state


def red_set(s):
    return frozenset(pi for pi, (c, _) in s.grid.items() if c == RED)


def state_key(s):
    items = []
    for pi, (c, is_c) in s.grid.items():
        items.append(pi * 16 + c * 2 + (1 if is_c else 0))
    items.sort()
    return tuple(items)


def main():
    t0 = time.time()
    print('Loading phase1...')
    start = load_phase1()
    print(f'Phase1 end: conv={start.conversions}')
    # Red positions reachable (union over all states)
    reds_ever = set(red_set(start))
    print(f'Initial reds: {sorted(int_to_pos(pi) for pi in reds_ever)}')
    print(f'Goal pos int: {pos_to_int(GOAL)}  in reds_ever: {pos_to_int(GOAL) in reds_ever}')

    # BFS
    visited = {state_key(start): 0}
    frontier = [start]
    depth = 0
    MAX_DEPTH = 50
    MAX_STATES = 3_000_000  # hard cap to limit memory
    while frontier and depth < MAX_DEPTH:
        depth += 1
        new_frontier = []
        for s in frontier:
            if len(visited) > MAX_STATES:
                break
            for ns, desc, conv_added in compound_moves(s, 60):
                k = state_key(ns)
                if k in visited:
                    continue
                visited[k] = depth
                # Update reds_ever
                new_reds = red_set(ns)
                new_here = new_reds - reds_ever
                if new_here:
                    for pi in new_here:
                        reds_ever.add(pi)
                        p = int_to_pos(pi)
                        print(f'[depth {depth}] RED reached {p} via: {desc}')
                # Check goal
                v = ns.get(GOAL)
                if v is not None and v[0] == RED and v[1]:
                    print(f'WIN at depth {depth}!')
                    return
                new_frontier.append(ns)
        if len(visited) > MAX_STATES:
            print(f'Memory cap hit at {len(visited)} states')
            break
        frontier = new_frontier
        elapsed = time.time() - t0
        est_mem_mb = len(visited) * 500 / (1024*1024)
        print(f'Depth {depth}: frontier={len(frontier)}, visited={len(visited)}, '
              f'reds_ever={len(reds_ever)}, t={elapsed:.1f}s, est_mem={est_mem_mb:.0f}MB')
        if not new_frontier:
            break
        if elapsed > 300:  # 5 min cap on this phase
            print('Time cap hit')
            break

    print('\n=== Reachability result ===')
    reachable_red_positions = sorted(int_to_pos(pi) for pi in reds_ever)
    print(f'Total unique red positions ever seen: {len(reachable_red_positions)}')
    for p in reachable_red_positions:
        print(f'  {p}')
    print(f'\nGoal (6925, 146, 2546) reached by red: {pos_to_int(GOAL) in reds_ever}')


if __name__ == '__main__':
    main()
