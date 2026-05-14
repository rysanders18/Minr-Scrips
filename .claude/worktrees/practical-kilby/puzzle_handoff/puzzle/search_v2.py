#!/usr/bin/env python3
"""
Beam + IDA* search from phase1 end state using fast_engine_v2.

Heuristic considers:
 - min manhattan of any red block to GOAL_POS
 - whether goal cell is empty (bonus) or occupied by non-red (penalty)
 - conversion pressure
 - number of red-adjacent pairs (more pairs => more chain opportunities)
"""

import time
import sys
import os

from fast_engine_v2 import (
    State, parse_initial, compound_moves_v2, compound_moves,
    COLOR_IDS, ID_TO_COLOR, int_to_pos, pos_to_int, GOAL_POS, X_MIN, X_MAX,
    Y_MIN, Y_MAX, Z_MIN, Z_MAX, display_state
)
from validate_phase1 import parse_move_line, apply_move


def load_phase1_end():
    state = parse_initial()
    with open('phase1_solution.txt', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            mv = parse_move_line(line)
            state, err = apply_move(state, mv)
            if state is None:
                raise RuntimeError(f"Phase1 apply failed: {err}")
    return state


def heuristic(state):
    v_goal = state.get(GOAL_POS)
    if v_goal is not None and v_goal[0] == COLOR_IDS['red'] and v_goal[1]:
        return 0

    reds = []
    for pi, (c, is_c) in state.grid.items():
        if c == COLOR_IDS['red']:
            reds.append((int_to_pos(pi), is_c))

    # min manhattan of any red to GOAL
    if not reds:
        return 999
    min_dist = min(abs(p[0] - GOAL_POS[0]) + abs(p[1] - GOAL_POS[1]) + abs(p[2] - GOAL_POS[2])
                   for (p, _) in reds)

    # count red adjacencies (pairs sharing 2 of 3 coords)
    red_ps = [p for (p, _) in reds]
    red_set = set(red_ps)
    adj_pairs = 0
    for (x, y, z) in red_ps:
        for dx, dy, dz in [(1,0,0),(0,1,0),(0,0,1)]:
            if (x+dx, y+dy, z+dz) in red_set:
                adj_pairs += 1

    # Red pairs by (y,z), (x,z), (x,y) => potential X/Y/Z chains
    yz = {}; xz = {}; xy = {}
    for (x,y,z) in red_ps:
        yz.setdefault((y,z), []).append(x)
        xz.setdefault((x,z), []).append(y)
        xy.setdefault((x,y), []).append(z)
    chain_pair_count = 0
    for d in (yz, xz, xy):
        for k, v in d.items():
            if len(v) >= 2:
                chain_pair_count += 1

    # Goal adj: how many reds are within distance 2 of goal
    near_goal = sum(1 for p, _ in reds
                    if abs(p[0] - GOAL_POS[0]) + abs(p[1] - GOAL_POS[1]) + abs(p[2] - GOAL_POS[2]) <= 2)

    # Blocker penalty
    blocker_pen = 0
    if v_goal is not None:
        if v_goal[0] != COLOR_IDS['red']:
            blocker_pen = 25

    # Red at (6926, 146, 2546) is 1 away - we really want to bring it to goal.
    # Count concrete reds
    concrete_reds_near = sum(1 for p, isc in reds
                             if isc and abs(p[0] - GOAL_POS[0]) + abs(p[1] - GOAL_POS[1]) + abs(p[2] - GOAL_POS[2]) <= 3)

    # Conv pressure
    conv_pen = max(0, state.conversions - 35) * 2

    return (20 * min_dist
            + blocker_pen
            + conv_pen
            - 3 * adj_pairs
            - 5 * chain_pair_count
            - 4 * near_goal
            - 6 * concrete_reds_near)


def beam_search(start_state, max_time=900, beam_width=600, max_depth=30):
    t0 = time.time()
    visited = {}
    init_fp = start_state.fingerprint()
    visited[init_fp] = 0
    beam = [(heuristic(start_state), start_state, [])]
    best_h = heuristic(start_state)
    best_state = start_state
    best_path = []

    for depth in range(max_depth):
        if time.time() - t0 > max_time:
            print(f"[TIMEOUT] at depth {depth}, elapsed={time.time()-t0:.1f}s", flush=True)
            break
        if not beam:
            print(f"[EMPTY] beam at depth {depth}", flush=True)
            break

        cand = []
        for h_val, state, path in beam:
            if state.is_won():
                return path, state
            moves = compound_moves_v2(state, conversion_limit=60)
            for new_state, desc, n_conv in moves:
                if new_state.conversions > 60:
                    continue
                fp = new_state.fingerprint()
                if fp in visited:
                    continue
                visited[fp] = depth + 1
                if new_state.is_won():
                    return path + [desc], new_state
                hh = heuristic(new_state)
                if hh < best_h:
                    best_h = hh
                    best_state = new_state
                    best_path = path + [desc]
                cand.append((hh, new_state, path + [desc]))

        cand.sort(key=lambda x: (x[0], x[1].conversions, len(x[2])))
        beam = cand[:beam_width]

        elapsed = time.time() - t0
        best_now = beam[0][0] if beam else '-'
        print(f"[d={depth+1}] beam_in={len(cand)} kept={len(beam)} best_h_now={best_now} best_ever={best_h} visited={len(visited)} elapsed={elapsed:.1f}s", flush=True)
        if len(visited) > 3_000_000:
            print("[MEM] trimming visited set", flush=True)
            break

    return None, (best_state, best_path, best_h)


def ida_star(start_state, max_time=300, branch_cap=30):
    t0 = time.time()
    start_h = heuristic(start_state)
    threshold = start_h
    nodes = [0]
    best = [start_state, [], start_h]

    def dfs(state, g, path, threshold, visited_on_path):
        if time.time() - t0 > max_time:
            return None
        nodes[0] += 1
        f = g + heuristic(state)
        if f > threshold:
            return f
        if state.is_won():
            return ('FOUND', path[:])
        hh = heuristic(state)
        if hh < best[2]:
            best[0] = state; best[1] = path[:]; best[2] = hh
        fp = state.fingerprint()
        if fp in visited_on_path:
            return None
        visited_on_path.add(fp)
        min_exceeded = float('inf')
        moves = compound_moves_v2(state, conversion_limit=60)
        moves.sort(key=lambda m: (heuristic(m[0]), m[2]))
        for new_state, desc, n_conv in moves[:branch_cap]:
            path.append(desc)
            res = dfs(new_state, g + 1, path, threshold, visited_on_path)
            if isinstance(res, tuple) and res and res[0] == 'FOUND':
                return res
            if isinstance(res, (int, float)):
                if res < min_exceeded:
                    min_exceeded = res
            path.pop()
        visited_on_path.discard(fp)
        return min_exceeded if min_exceeded != float('inf') else None

    while time.time() - t0 < max_time:
        visited = set()
        res = dfs(start_state, 0, [], threshold, visited)
        print(f"[IDA] thr={threshold} nodes={nodes[0]} best_h={best[2]} elapsed={time.time()-t0:.1f}s", flush=True)
        if isinstance(res, tuple) and res and res[0] == 'FOUND':
            return res[1], None
        if res is None or res == float('inf'):
            break
        threshold = res
    return None, (best[0], best[1], best[2])


def verify_solution(full_lines):
    """Apply full_lines to parse_initial() state. Return True if wins."""
    state = parse_initial()
    for i, line in enumerate(full_lines, 1):
        mv = parse_move_line(line)
        if mv is None:
            return False, f"parse failed at line {i}"
        new_state, err = apply_move(state, mv)
        if new_state is None:
            return False, f"apply failed at line {i}: {err}"
        state = new_state
    if state.is_won():
        return True, f"Won! Total conversions: {state.conversions}"
    return False, f"Did not win. Goal block: {state.get(GOAL_POS)}"


def main():
    print("Loading phase1 end state...", flush=True)
    start = load_phase1_end()
    print(f"Start: {len(start.grid)} blocks, conv={start.conversions}", flush=True)
    print(f"Start heuristic: {heuristic(start)}", flush=True)

    moves = compound_moves_v2(start, conversion_limit=60)
    print(f"Start moves available: {len(moves)}", flush=True)
    iw = [m for m in moves if m[1].startswith('interweave')]
    print(f"  Interweave moves at start: {len(iw)}", flush=True)

    max_time = 780
    print(f"\nBeam search (wallclock {max_time}s, width=800, depth<=30)...", flush=True)
    sol, info = beam_search(start, max_time=max_time, beam_width=800, max_depth=30)
    if sol is not None:
        print(f"\n!!! SOLUTION FOUND in {len(sol)} moves !!!", flush=True)
        with open('phase1_solution.txt', encoding='utf-8') as f:
            phase1 = [ln.strip() for ln in f if ln.strip()]
        full = phase1 + sol
        with open('full_solution.txt', 'w', encoding='utf-8') as f:
            for line in full:
                f.write(line + "\n")
        print(f"Full solution written ({len(full)} lines)", flush=True)

        # Verify - try v1 first (without interweave)
        ok, msg = verify_solution(full)
        print(f"v1 verify: {ok} -- {msg}", flush=True)
        return

    best_state, best_path, best_h = info
    print(f"\nBest heuristic reached: {best_h}", flush=True)
    print(f"Best path length: {len(best_path)}", flush=True)
    with open('best_partial_v2.txt', 'w', encoding='utf-8') as f:
        for line in best_path:
            f.write(line + "\n")
    print("Wrote best_partial_v2.txt", flush=True)


if __name__ == '__main__':
    main()
