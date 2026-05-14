#!/usr/bin/env python3
"""
Focused beam search - track 'ever moved a red chain' and 'red at/near goal'.

Uses fast_engine_v2.compound_moves_v2 (with interweave).
"""
import time
import sys
from collections import defaultdict

from fast_engine_v2 import (
    State, parse_initial, compound_moves_v2, COLOR_IDS, ID_TO_COLOR,
    int_to_pos, pos_to_int, GOAL_POS, X_MIN, X_MAX,
    Y_MIN, Y_MAX, Z_MIN, Z_MAX, find_formable_chains
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


REF_STATE = None
REF_REDS = None


def get_red_positions(state):
    s = []
    for pi, (c, is_c) in state.grid.items():
        if c == COLOR_IDS['red']:
            s.append((int_to_pos(pi), is_c))
    return s


def heuristic(state):
    v_goal = state.get(GOAL_POS)
    if v_goal is not None and v_goal[0] == COLOR_IDS['red'] and v_goal[1]:
        return 0
    reds = get_red_positions(state)
    if not reds:
        return 999

    # Key: check if reds have moved from their initial phase1 positions.
    # Count of reds that are NOT at their initial position.
    orig_reds = set(p for p, _ in REF_REDS)
    moved_reds = sum(1 for p, _ in reds if p not in orig_reds)

    # min dist from ANY red to goal
    min_dist = min(abs(p[0] - GOAL_POS[0]) + abs(p[1] - GOAL_POS[1]) + abs(p[2] - GOAL_POS[2])
                   for (p, _) in reds)

    # red chain-formable count
    chains = find_formable_chains(state)
    red_chain_count = sum(1 for ax, pos, col, need in chains if col == COLOR_IDS['red'])

    # bonus if red chain exists that CAN slide (not blocked)
    red_movable = 0
    for ax, pos, col, need in chains:
        if col != COLOR_IDS['red']:
            continue
        # conservative: if need is small, the chain can potentially be formed
        # We don't simulate slide here; just count as +1 if chain exists
        red_movable += 1

    # Blocker penalty
    blocker_pen = 20 if v_goal is not None and v_goal[0] != COLOR_IDS['red'] else 0

    # Conv pressure
    conv_pen = max(0, state.conversions - 40) * 2

    return (25 * min_dist
            + blocker_pen
            + conv_pen
            - 8 * moved_reds   # Big bonus for actually moving reds
            - 10 * red_movable)  # Big bonus for having red chain


def beam_search(start_state, max_time=600, beam_width=1500, max_depth=40):
    t0 = time.time()
    visited = set()
    init_fp = start_state.fingerprint()
    visited.add(init_fp)
    beam = [(heuristic(start_state), start_state, [])]
    best_h = heuristic(start_state)
    best_state = start_state
    best_path = []

    for depth in range(max_depth):
        if time.time() - t0 > max_time:
            print(f"[TIMEOUT] depth {depth}", flush=True)
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
                visited.add(fp)
                if new_state.is_won():
                    return path + [desc], new_state
                hh = heuristic(new_state)
                if hh < best_h:
                    best_h = hh
                    best_state = new_state
                    best_path = path + [desc]
                    print(f"  [IMPROVE d={depth+1}] new best_h={hh} via {desc[:80]}", flush=True)
                cand.append((hh, new_state, path + [desc]))

        cand.sort(key=lambda x: (x[0], x[1].conversions, len(x[2])))
        beam = cand[:beam_width]

        elapsed = time.time() - t0
        best_now = beam[0][0] if beam else '-'
        print(f"[d={depth+1}] beam_in={len(cand)} kept={len(beam)} best_now={best_now} best_ever={best_h} visited={len(visited)} elapsed={elapsed:.1f}s", flush=True)
        if len(visited) > 3_500_000:
            print("[MEM] pruning", flush=True)
            break

    return None, (best_state, best_path, best_h)


def verify_solution(full_lines):
    state = parse_initial()
    for i, line in enumerate(full_lines, 1):
        mv = parse_move_line(line)
        if mv is None:
            return False, f"parse failed at line {i}: {line}"
        new_state, err = apply_move(state, mv)
        if new_state is None:
            return False, f"apply failed at line {i}: {err}"
        state = new_state
    return state.is_won(), f"conversions={state.conversions}, goal={state.get(GOAL_POS)}"


def main():
    global REF_STATE, REF_REDS
    print("Loading phase1 end state...", flush=True)
    start = load_phase1_end()
    REF_STATE = start
    REF_REDS = get_red_positions(start)
    print(f"Start: {len(start.grid)} blocks, conv={start.conversions}, reds={len(REF_REDS)}", flush=True)
    print(f"Start heuristic: {heuristic(start)}", flush=True)

    max_time = 600
    sol, info = beam_search(start, max_time=max_time, beam_width=1500, max_depth=40)
    if sol is not None:
        print(f"\n!!! SOLUTION in {len(sol)} moves !!!", flush=True)
        with open('phase1_solution.txt', encoding='utf-8') as f:
            phase1 = [ln.strip() for ln in f if ln.strip()]
        full = phase1 + sol
        with open('full_solution.txt', 'w', encoding='utf-8') as f:
            for line in full:
                f.write(line + "\n")
        # Verify against original v1 engine
        ok, msg = verify_solution(full)
        print(f"v1 verify: {ok} -- {msg}", flush=True)
        return

    best_state, best_path, best_h = info
    print(f"\nBest h: {best_h}, path len: {len(best_path)}", flush=True)
    with open('best_partial_v2b.txt', 'w', encoding='utf-8') as f:
        for line in best_path:
            f.write(line + "\n")


if __name__ == '__main__':
    main()
