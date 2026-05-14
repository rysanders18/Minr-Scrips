#!/usr/bin/env python3
"""
Focused solver using beam search focused on reds.
Memory-bounded (<1.5GB), time-bounded (12 min).
"""

import sys
import time
import heapq
import gc
from fast_engine import (
    parse_initial, compound_moves, find_formable_chains, max_slide,
    int_to_pos, pos_to_int,
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


def red_positions_set(s):
    return frozenset(pi for pi, (c, _) in s.grid.items() if c == RED)


def state_key(s):
    # Pack smaller
    return tuple(sorted(pi * 16 + v[0] * 2 + (1 if v[1] else 0)
                        for pi, v in s.grid.items()))


def red_dist_to_goal(s):
    gx, gy, gz = GOAL
    best = 999
    for pi, (c, _) in s.grid.items():
        if c == RED:
            p = int_to_pos(pi)
            d = abs(p[0]-gx) + abs(p[1]-gy) + abs(p[2]-gz)
            if d < best:
                best = d
    return best


def red_won(s):
    v = s.get(GOAL)
    return v is not None and v[0] == RED and v[1]


def heuristic(s):
    if red_won(s):
        return 0
    gx, gy, gz = GOAL
    reds = [int_to_pos(pi) for pi, (c, _) in s.grid.items() if c == RED]
    dist = min(abs(p[0]-gx) + abs(p[1]-gy) + abs(p[2]-gz) for p in reds)
    # Bonus: reds at y=146
    y146 = sum(1 for r in reds if r[1] == gy)
    z2546 = sum(1 for r in reds if r[2] == gz)
    x6925 = sum(1 for r in reds if r[0] == gx)
    # Goal cell obstacle
    v = s.get(GOAL)
    blk = 0
    if v is not None:
        if v[0] == RED:
            blk = 0
        else:
            blk = 3  # something in way
    # Count pair potential (aligned red pairs)
    pairs = 0
    for i in range(len(reds)):
        for j in range(i+1, len(reds)):
            a, b = reds[i], reds[j]
            if sum(1 for k in range(3) if a[k] == b[k]) == 2:
                pairs += 1
    return dist * 4 + blk - y146 * 2 - z2546 * 2 - x6925 * 4 - pairs


def compute_red_hash(reds_frozen):
    return hash(reds_frozen)


def beam_search(start, beam_width=400, max_depth=50, time_budget=600, verbose=True):
    t0 = time.time()
    start_h = heuristic(start)
    # Each frontier item: (state, path, g_cost)
    frontier = [(start, [], 0)]
    # For dedup, keep key -> best g
    seen = {state_key(start): 0}
    best_by_redh = {}
    best_h = start_h
    best_path = []
    best_state = start

    for depth in range(max_depth):
        if time.time() - t0 > time_budget:
            break
        # Expand all of frontier
        candidates = []
        for st, path, g in frontier:
            if red_won(st):
                return st, path
            moves = compound_moves(st, 60)
            for ns, desc, conv_added in moves:
                k = state_key(ns)
                newg = g + 1
                if k in seen and seen[k] <= newg:
                    continue
                seen[k] = newg
                if red_won(ns):
                    return ns, path + [desc]
                h = heuristic(ns)
                if h < best_h:
                    best_h = h
                    best_path = path + [desc]
                    best_state = ns
                    if verbose:
                        print(f'[d={depth+1}] new best_h={best_h}: {desc}')
                candidates.append((h + newg * 0.3, ns, path + [desc], newg))

        if not candidates:
            if verbose:
                print(f'Exhausted at depth {depth}')
            break

        # Prune frontier
        candidates.sort(key=lambda x: x[0])
        # Keep diverse + top
        kept = candidates[:beam_width]

        # Also keep states that have unique red-position sets (even if higher h)
        unique_red_states = {}
        for f, st, path, g in candidates[:beam_width*3]:
            rk = compute_red_hash(red_positions_set(st))
            if rk not in unique_red_states:
                unique_red_states[rk] = (f, st, path, g)
        # Add to kept (avoid dupes)
        added = set(id(c[1]) for c in kept)
        for rk, (f, st, path, g) in unique_red_states.items():
            if id(st) in added:
                continue
            kept.append((f, st, path, g))
            added.add(id(st))
            if len(kept) >= beam_width * 2:
                break

        frontier = [(st, path, g) for _, st, path, g in kept]

        if verbose and depth % 2 == 0:
            mem_est = len(seen) * 600 / (1024*1024)
            elapsed = time.time() - t0
            print(f'd={depth+1}: frontier={len(frontier)}, seen={len(seen)}, '
                  f'best_h={best_h}, t={elapsed:.1f}s, est_mem={mem_est:.0f}MB')
            # GC occasionally
            if depth % 10 == 0:
                gc.collect()
            # Memory cap
            if len(seen) > 1_500_000:
                print('State cap hit, stopping')
                return best_state, best_path

    return best_state, best_path


def main():
    t0 = time.time()
    start, phase1_lines = load_phase1()
    print(f'Start: conv={start.conversions}, h={heuristic(start)}')

    # Run with medium beam, then wider if time remains
    configs = [
        (600, 25, 300),
        (1500, 30, 400),
    ]
    found = None
    for bw, md, tb in configs:
        elapsed = time.time() - t0
        if elapsed > 800:
            break
        print(f'\n=== beam={bw}, depth={md}, budget={min(tb, 850-elapsed):.0f}s ===')
        st, path = beam_search(start, beam_width=bw, max_depth=md,
                               time_budget=min(tb, 850-elapsed))
        if st is not None and red_won(st):
            found = (st, path)
            break

    if found is not None:
        st, path = found
        print(f'\nSOLUTION: {len(path)} moves, conv={st.conversions}')
        with open('full_solution.txt', 'w', encoding='utf-8') as f:
            for line in phase1_lines:
                f.write(line + '\n')
            for line in path:
                f.write(line + '\n')
        print(f'Wrote full_solution.txt')
    else:
        print('\nNo solution found.')


if __name__ == '__main__':
    main()
