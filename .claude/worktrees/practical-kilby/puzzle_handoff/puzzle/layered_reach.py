#!/usr/bin/env python3
"""
Layered reachability: dedupe by (red_positions_frozenset), keeping only ONE
non-red state representative per red footprint.

This massively reduces state space since reds rarely move but many other
configurations can support a given red movement.
"""
import sys
import time
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


def red_frozen(s):
    return frozenset(pi for pi, (c, _) in s.grid.items() if c == RED)


def full_key(s):
    return tuple(sorted(pi * 16 + v[0] * 2 + (1 if v[1] else 0)
                        for pi, v in s.grid.items()))


def won(s):
    v = s.get(GOAL)
    return v is not None and v[0] == RED and v[1]


def main():
    t0 = time.time()
    start, phase1_lines = load_phase1()

    # For each unique red-footprint, we keep the shortest-path/lowest-conv representative
    # Map: red_frozen -> (state, path, conv)
    best_by_red = {red_frozen(start): (start, [], start.conversions)}
    # For full-state dedup within frontier
    visited_full = {full_key(start): 0}
    frontier = [(start, [])]
    depth = 0
    MEM_CAP = 1_000_000

    print(f'Start conv={start.conversions}, red footprints found: 1')

    while frontier:
        if time.time() - t0 > 700:
            print('Time cap')
            break
        depth += 1
        new_frontier = []
        # We'll limit: only keep states where either (a) red footprint is new,
        # (b) at most K representatives per red footprint
        # Let's keep up to 5 non-red-diverse representatives per red footprint
        reps_per_red = {}
        new_red_footprints = 0

        for s, path in frontier:
            for ns, desc, conv_added in compound_moves(s, 60):
                if won(ns):
                    print(f'WON at depth {depth}')
                    full_path = path + [desc]
                    with open('full_solution.txt', 'w', encoding='utf-8') as f:
                        for line in phase1_lines + full_path:
                            f.write(line + '\n')
                    print(f'SOLUTION: {len(full_path)} post-phase1 moves, conv={ns.conversions}')
                    return

                k = full_key(ns)
                if k in visited_full:
                    continue
                visited_full[k] = depth

                rk = red_frozen(ns)
                if rk not in best_by_red:
                    # New red footprint!
                    new_red_footprints += 1
                    best_by_red[rk] = (ns, path + [desc], ns.conversions)
                    for pi in rk - red_frozen(s):
                        print(f'  d={depth}: NEW red pos {int_to_pos(pi)} via: {desc} (conv={ns.conversions})')

                # Limit reps per red footprint in frontier
                rep_count = reps_per_red.get(rk, 0)
                if rep_count < 12:  # keep some diversity
                    reps_per_red[rk] = rep_count + 1
                    new_frontier.append((ns, path + [desc]))

        elapsed = time.time() - t0
        mem_mb = len(visited_full) * 500 / (1024*1024)
        print(f'd={depth}: frontier={len(new_frontier)}, visited={len(visited_full)}, '
              f'red_footprints={len(best_by_red)} (+{new_red_footprints}), '
              f't={elapsed:.0f}s, mem={mem_mb:.0f}MB')
        if len(visited_full) > MEM_CAP:
            print('Memory cap')
            break
        frontier = new_frontier
        if not new_frontier:
            break

    print(f'\nDone. Red footprints explored: {len(best_by_red)}')
    # Show all red positions ever seen
    all_reds = set()
    for rk in best_by_red:
        all_reds |= rk
    print(f'Total unique red positions ever seen: {len(all_reds)}')
    for pi in sorted(all_reds):
        print(f'  {int_to_pos(pi)}')
    target = pos_to_int(GOAL)
    print(f'\nTarget {GOAL} ever reached by red: {target in all_reds}')


if __name__ == '__main__':
    main()
