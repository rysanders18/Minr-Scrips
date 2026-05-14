#!/usr/bin/env python3
"""
Targeted solver: only care about red-propagation frontier.

Observation: we need to get RED blocks to new positions. Most moves don't
do that. We'll track states by their "red footprint" (sorted red positions)
plus enough state to enable future red-enabling cascades.

Strategy:
1. Start at phase1-end state.
2. Run BFS with strict memory bounds: <=500k states, <=1.5GB.
3. Heuristic: focus on moves that either (a) move a red, or (b) clear a cell
   adjacent to or blocking a red chain.
4. Prioritize: A* with cost = conversions + depth, heuristic = min-dist-to-goal
   for any red, but also consider "could this red ever reach (6925, 146, 2546)
   along currently-unblocked paths?"
"""

import sys
import time
import heapq
from collections import defaultdict
from fast_engine import (
    parse_initial, compound_moves, find_formable_chains, max_slide,
    slide_chain, int_to_pos, pos_to_int,
    COLOR_IDS, ID_TO_COLOR, GOAL_POS, State
)
from validate_phase1 import parse_move_line, apply_move

sys.stdout.reconfigure(line_buffering=True)

RED = COLOR_IDS['red']
GREEN = COLOR_IDS['green']
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


def red_positions(s):
    return [int_to_pos(pi) for pi, (c, _) in s.grid.items() if c == RED]


def state_key(s):
    return tuple(sorted((pi, v[0], 1 if v[1] else 0) for pi, v in s.grid.items()))


def red_min_dist_to_goal(s):
    best = 999
    for pi, (c, _) in s.grid.items():
        if c == RED:
            p = int_to_pos(pi)
            d = abs(p[0]-GOAL[0]) + abs(p[1]-GOAL[1]) + abs(p[2]-GOAL[2])
            if d < best:
                best = d
    return best


def goal_cell_empty(s):
    return s.get(GOAL) is None


def red_at_goal(s):
    v = s.get(GOAL)
    return v is not None and v[0] == RED and v[1]


def h_cost(s):
    """Heuristic: lower is better. 0 if won."""
    if red_at_goal(s):
        return 0
    d = red_min_dist_to_goal(s)
    # Penalties
    reds = red_positions(s)
    # Reward reds at y=146
    y146 = sum(1 for r in reds if r[1] == 146)
    z2546 = sum(1 for r in reds if r[2] == 2546)
    # Reward goal cell cleared
    blk = 0 if goal_cell_empty(s) else 2
    # Reward reds being on the x=6925 column
    x6925 = sum(1 for r in reds if r[0] == 6925)
    return d * 3 + blk - y146 - z2546 - x6925 * 3


def astar(start, max_time_sec=600, max_states=600_000):
    """A* search with aggressive pruning."""
    t0 = time.time()
    start_h = h_cost(start)
    counter = 0
    pq = [(start_h, 0, counter, start, [])]
    seen = {state_key(start): 0}
    best_h = start_h
    best = (start, [])
    popped = 0
    while pq:
        if time.time() - t0 > max_time_sec:
            print(f'Time cap hit at {popped} popped, {len(seen)} seen')
            break
        if len(seen) > max_states:
            print(f'State cap hit at {len(seen)}')
            break
        f, g, _, s, path = heapq.heappop(pq)
        popped += 1
        if red_at_goal(s):
            return s, path, popped
        if popped % 10000 == 0:
            elapsed = time.time() - t0
            print(f'popped={popped}, seen={len(seen)}, best_h={best_h}, g_cur={g}, t={elapsed:.1f}s')
        # Expand
        moves = compound_moves(s, conversion_limit=60)
        # Prefer 0-conversion moves first? Doesn't affect A*.
        for ns, desc, conv_added in moves:
            if ns.conversions > 60:
                continue
            k = state_key(ns)
            newg = g + 1
            if k in seen and seen[k] <= newg:
                continue
            seen[k] = newg
            nh = h_cost(ns)
            if red_at_goal(ns):
                return ns, path + [desc], popped
            if nh < best_h:
                best_h = nh
                best = (ns, path + [desc])
                print(f'[best_h={best_h}] at g={newg}, move: {desc}')
            counter += 1
            # Tiebreak by h
            heapq.heappush(pq, (nh + newg, newg, counter, ns, path + [desc]))
    return None, [], popped


def main():
    t0 = time.time()
    start, phase1_lines = load_phase1()
    print(f'Phase1 end: conv={start.conversions}')
    print(f'Start h_cost: {h_cost(start)}')

    result_state, path, popped = astar(start, max_time_sec=600, max_states=500_000)
    elapsed = time.time() - t0
    print(f'\nDone: popped={popped}, elapsed={elapsed:.1f}s')

    if result_state is not None and result_state.is_won():
        print(f'SOLUTION FOUND! moves={len(path)}, conv={result_state.conversions}')
        with open('full_solution.txt', 'w', encoding='utf-8') as f:
            for line in phase1_lines:
                f.write(line + '\n')
            for line in path:
                f.write(line + '\n')
        print('Wrote full_solution.txt')
    else:
        print('No solution found via A*')


if __name__ == '__main__':
    main()
