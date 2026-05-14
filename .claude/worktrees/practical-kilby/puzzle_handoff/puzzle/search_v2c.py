#!/usr/bin/env python3
"""
Focused search with faster engine calls.
Filters to only red-related compound moves when possible, and
only uses "vacate" modes of interweave (not the duplicate mode).
"""
import time
import sys
from collections import defaultdict

from fast_engine_v2 import (
    State, parse_initial, compound_moves, interweave_moves,
    COLOR_IDS, ID_TO_COLOR, int_to_pos, pos_to_int, GOAL_POS, X_MIN, X_MAX,
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


def compound_moves_c(state, conversion_limit=60):
    """Regular + interweave (vacate modes only, not duplicate)."""
    m = compound_moves(state, conversion_limit)
    im = interweave_moves(state, conversion_limit)
    # filter out 'dup' mode
    im2 = [x for x in im if 'interweave-dup' not in x[1]]
    m.extend(im2)
    return m


REF_REDS = None


def heuristic(state):
    v_goal = state.get(GOAL_POS)
    if v_goal is not None and v_goal[0] == COLOR_IDS['red'] and v_goal[1]:
        return 0

    reds = []
    for pi, (c, is_c) in state.grid.items():
        if c == COLOR_IDS['red']:
            reds.append((int_to_pos(pi), is_c))

    orig_reds = set(REF_REDS)
    moved_reds = sum(1 for p, _ in reds if p not in orig_reds)

    min_dist = min(abs(p[0] - GOAL_POS[0]) + abs(p[1] - GOAL_POS[1]) + abs(p[2] - GOAL_POS[2])
                   for (p, _) in reds)
    min_dist_concrete = 999
    for p, isc in reds:
        if isc:
            d = abs(p[0] - GOAL_POS[0]) + abs(p[1] - GOAL_POS[1]) + abs(p[2] - GOAL_POS[2])
            if d < min_dist_concrete: min_dist_concrete = d

    chains = find_formable_chains(state)
    red_chains = sum(1 for ax, pos, col, need in chains if col == COLOR_IDS['red'])

    blocker_pen = 25 if v_goal is not None and v_goal[0] != COLOR_IDS['red'] else 0
    conv_pen = max(0, state.conversions - 45) * 3

    return (30 * min_dist
            + (10 if min_dist_concrete >= 999 else 0)  # penalty if no concrete red close
            + blocker_pen
            + conv_pen
            - 8 * moved_reds
            - 12 * red_chains)


def beam_search(start_state, max_time=700, beam_width=3000, max_depth=50):
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
            print(f"[TIMEOUT] depth {depth} elapsed={time.time()-t0:.1f}s", flush=True)
            break
        if not beam:
            print(f"[EMPTY] depth {depth}", flush=True)
            break

        cand = []
        for h_val, state, path in beam:
            if state.is_won():
                return path, state
            moves = compound_moves_c(state, conversion_limit=60)
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
                    print(f"  [IMP d={depth+1}] h={hh}: {desc[:90]}", flush=True)
                cand.append((hh, new_state, path + [desc]))

        cand.sort(key=lambda x: (x[0], x[1].conversions, len(x[2])))
        beam = cand[:beam_width]

        elapsed = time.time() - t0
        best_now = beam[0][0] if beam else '-'
        print(f"[d={depth+1}] in={len(cand)} keep={len(beam)} now={best_now} ever={best_h} vis={len(visited)} t={elapsed:.1f}s", flush=True)
        if len(visited) > 2_500_000:
            print("[MEM CAP] stopping", flush=True)
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
    global REF_REDS
    print("Loading phase1 end state...", flush=True)
    start = load_phase1_end()
    REF_REDS = [int_to_pos(pi) for pi, (c, _) in start.grid.items() if c == COLOR_IDS['red']]
    print(f"Start: {len(start.grid)} blocks, conv={start.conversions}, reds={len(REF_REDS)}", flush=True)
    print(f"Start heuristic: {heuristic(start)}", flush=True)

    max_time = 680
    sol, info = beam_search(start, max_time=max_time, beam_width=3000, max_depth=60)
    if sol is not None:
        print(f"\n!!! SOLUTION in {len(sol)} moves !!!", flush=True)
        with open('phase1_solution.txt', encoding='utf-8') as f:
            phase1 = [ln.strip() for ln in f if ln.strip()]
        full = phase1 + sol
        with open('full_solution.txt', 'w', encoding='utf-8') as f:
            for line in full:
                f.write(line + "\n")
        ok, msg = verify_solution(full)
        print(f"v1 verify: {ok} -- {msg}", flush=True)
        return

    best_state, best_path, best_h = info
    print(f"\nBest h: {best_h}, path len: {len(best_path)}", flush=True)
    with open('best_partial_v2c.txt', 'w', encoding='utf-8') as f:
        for line in best_path:
            f.write(line + "\n")
    print("wrote best_partial_v2c.txt", flush=True)


if __name__ == '__main__':
    main()
