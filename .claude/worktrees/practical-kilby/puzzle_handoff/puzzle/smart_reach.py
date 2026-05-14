#!/usr/bin/env python3
"""
Smart reachability: track reds-ever-reached, but dedupe by (red footprint, non-red footprint signature).

A critical optimization: if two states have the SAME red footprint and the same set of
other-color-blocks-with-concrete flags, they are equivalent for red-movement purposes.

We still need some info about other blocks to determine what chains are formable,
but we can reduce state space by treating states with equivalent "move structure" as same.

Strategy: beam-style search where we keep one exemplar per red-footprint, pick the one
with fewest conversions used.
"""
import sys
import time
import heapq
from fast_engine import (
    parse_initial, compound_moves, int_to_pos, pos_to_int,
    COLOR_IDS, ID_TO_COLOR, GOAL_POS, State
)
from validate_phase1 import parse_move_line, apply_move

sys.stdout.reconfigure(line_buffering=True)

RED = COLOR_IDS['red']
GOAL = GOAL_POS


def load_phase1():
    state = parse_initial()
    lines = []
    with open('phase1_solution.txt', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            lines.append(line)
            mv = parse_move_line(line)
            state, err = apply_move(state, mv)
    return state, lines


def full_key(s):
    return tuple(sorted(pi * 16 + v[0] * 2 + (1 if v[1] else 0)
                        for pi, v in s.grid.items()))


def red_key(s):
    return tuple(sorted(pi for pi, (c, _) in s.grid.items() if c == RED))


def won(s):
    v = s.get(GOAL)
    return v is not None and v[0] == RED and v[1]


def main():
    t0 = time.time()
    start, phase1_lines = load_phase1()
    print(f'Phase1 end conv={start.conversions}')

    # BFS by full state, but prefer exploring unique red-footprints
    visited_full = {full_key(start): 0}
    reds_ever = set(int_to_pos(pi) for pi in red_key(start))
    frontier = [(start, [])]
    depth = 0
    best_red_dist = 999
    # track distance achieved
    def min_red_dist(s):
        gx, gy, gz = GOAL
        best = 999
        for pi, (c, _) in s.grid.items():
            if c == RED:
                p = int_to_pos(pi)
                d = abs(p[0]-gx) + abs(p[1]-gy) + abs(p[2]-gz)
                if d < best:
                    best = d
        return best

    best_red_dist = min_red_dist(start)
    print(f'Initial min_red_dist: {best_red_dist}')

    MEM_CAP_STATES = 1_200_000  # ~500MB
    while frontier:
        if time.time() - t0 > 600:
            print('Time cap 10min')
            break
        depth += 1
        new_frontier = []
        unique_red_in_new = {}
        for s, path in frontier:
            for ns, desc, conv_added in compound_moves(s, 60):
                if won(ns):
                    print(f'WON at depth {depth}: {desc}')
                    # emit solution
                    full_path = path + [desc]
                    with open('full_solution.txt', 'w', encoding='utf-8') as f:
                        for line in phase1_lines + full_path:
                            f.write(line + '\n')
                    print(f'Wrote full_solution.txt, {len(full_path)} phase-n moves, conv={ns.conversions}')
                    return
                k = full_key(ns)
                if k in visited_full:
                    continue
                visited_full[k] = depth
                # red positions
                rk = red_key(ns)
                if rk not in unique_red_in_new:
                    unique_red_in_new[rk] = (ns, path + [desc])
                new_frontier.append((ns, path + [desc]))
                # track reds ever
                for pi in rk:
                    if pi not in reds_ever:
                        reds_ever.add(pi)
                        print(f'  d={depth}: new red at {int_to_pos(pi)} via: {desc}')
                rd = min_red_dist(ns)
                if rd < best_red_dist:
                    best_red_dist = rd
                    print(f'  d={depth}: new best_red_dist={rd} via: {desc}')
        mem_mb = len(visited_full) * 500 / (1024*1024)
        elapsed = time.time() - t0
        print(f'd={depth}: frontier={len(new_frontier)}, visited={len(visited_full)}, '
              f'reds_ever={len(reds_ever)}, best_dist={best_red_dist}, '
              f't={elapsed:.0f}s, mem={mem_mb:.0f}MB')
        if len(visited_full) > MEM_CAP_STATES:
            print('Memory cap hit, stopping')
            break
        if not new_frontier:
            break
        # Trim frontier: keep only one exemplar per red-footprint (minimal path)
        # Actually keep ALL (to explore different orderings), but pre-sort by h
        frontier = new_frontier

    print('Done.')
    print(f'Visited {len(visited_full)} full states, unique red positions ever reached: {len(reds_ever)}')
    for p in sorted(int_to_pos(pi) for pi in reds_ever):
        print(f'  {p}')


if __name__ == '__main__':
    main()
