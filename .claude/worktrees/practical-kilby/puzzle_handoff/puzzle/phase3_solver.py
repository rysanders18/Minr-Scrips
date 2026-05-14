#!/usr/bin/env python3
"""
Phase 3 solver: from end of phase 1, find moves that place RED concrete
at goal position (6925, 146, 2546). This includes the G2 blocker move.

Heuristic focuses on getting reds close to the goal.
"""

from fast_engine import (
    State, parse_initial, compound_moves, find_formable_chains,
    find_all_chains, slide_chain, max_slide, pos_to_int, int_to_pos,
    COLOR_IDS, ID_TO_COLOR, GOAL_POS, X_MIN, X_MAX, Y_MIN, Y_MAX, Z_MIN, Z_MAX
)
import time
import sys
import gc
import pickle

RED_ID = COLOR_IDS['red']
GREEN_ID = COLOR_IDS['green']


def apply_solution(state, solution):
    cur = state
    for move in solution:
        cm = compound_moves(cur, conversion_limit=60)
        found = None
        for new_state, desc, n_conv in cm:
            if desc == move:
                found = new_state
                break
        if found is None:
            return None
        cur = found
    return cur


def is_won(state):
    v = state.get(GOAL_POS)
    return v is not None and v[0] == RED_ID and v[1]


def heuristic_phase3(state):
    """
    Distance-based heuristic for red reaching goal.
    Considers:
    - Is blocker still at goal? (big penalty)
    - Min manhattan from any red to goal
    - Bonus for reds at low-x, y=146, z=2546 region
    """
    # Is blocker position still occupied by non-red?
    goal_v = state.get(GOAL_POS)
    blocker_penalty = 0
    if goal_v is not None and goal_v[0] != RED_ID:
        blocker_penalty = 5
    
    best_red_dist = 1000
    reds_near_goal = 0
    reds_at_y146 = 0
    reds_at_z2546 = 0
    reds_at_x6925 = 0
    
    for pi, (c, is_c) in state.grid.items():
        if c != RED_ID:
            continue
        pos = int_to_pos(pi)
        d = abs(pos[0]-GOAL_POS[0]) + abs(pos[1]-GOAL_POS[1]) + abs(pos[2]-GOAL_POS[2])
        if d < best_red_dist:
            best_red_dist = d
        if d <= 3:
            reds_near_goal += 1
        if pos[1] == 146:
            reds_at_y146 += 1
        if pos[2] == 2546:
            reds_at_z2546 += 1
        if pos[0] == 6925:
            reds_at_x6925 += 1
    
    h = (best_red_dist 
         + blocker_penalty 
         - 0.3 * reds_near_goal 
         - 0.2 * reds_at_y146 
         - 0.2 * reds_at_z2546
         - 1.0 * reds_at_x6925)
    return h


def state_hash(state):
    return hash(frozenset(state.grid.items()))


def beam_search_phase3(initial_state, beam_width=10000, max_depth=30, 
                      max_conversions=60, time_limit=14400, verbose=True):
    """Wide beam search for phase 3."""
    start_time = time.time()
    
    if is_won(initial_state):
        return []
    
    frontier = [(initial_state, [])]
    visited = {state_hash(initial_state): initial_state.conversions}
    
    initial_h = heuristic_phase3(initial_state)
    best_h = initial_h
    print(f"[0s] Phase 3: initial h={initial_h:.2f}, initial conv={initial_state.conversions}")
    
    for depth in range(1, max_depth + 1):
        if time.time() - start_time > time_limit:
            print(f"\n[TIMEOUT] depth {depth} after {time.time()-start_time:.0f}s")
            return None
        
        next_frontier = []
        n_expanded = 0
        n_dups = 0
        t_start_depth = time.time()
        
        for state, moves in frontier:
            cm = compound_moves(state, conversion_limit=max_conversions)
            n_expanded += 1
            for new_state, desc, n_conv in cm:
                sh = state_hash(new_state)
                prev_conv = visited.get(sh)
                if prev_conv is not None and prev_conv <= new_state.conversions:
                    n_dups += 1
                    continue
                visited[sh] = new_state.conversions
                
                if is_won(new_state):
                    elapsed = time.time() - start_time
                    print(f"\n*** PHASE 3 SOLUTION at depth {depth} in {elapsed:.0f}s ***")
                    return moves + [desc]
                
                h = heuristic_phase3(new_state)
                next_frontier.append((h, new_state, moves + [desc]))
        
        if not next_frontier:
            print(f"[depth {depth}] empty frontier")
            return None
        
        next_frontier.sort(key=lambda x: x[0])
        next_frontier = next_frontier[:beam_width]
        
        depth_best_h = next_frontier[0][0]
        if depth_best_h < best_h:
            best_h = depth_best_h
        
        elapsed = time.time() - start_time
        t_depth = time.time() - t_start_depth
        if verbose:
            print(f"[{elapsed:.0f}s] depth={depth}: expanded={n_expanded}, frontier={len(next_frontier)}, "
                  f"dups={n_dups}, best_h={depth_best_h:.2f} ever={best_h:.2f}, "
                  f"visited={len(visited)}, dt={t_depth:.1f}s")
        
        if len(visited) > 15_000_000:
            print(f"  [gc] pruning visited set")
            sample = list(visited.items())[:2_000_000]
            visited = dict(sample)
            gc.collect()
        
        frontier = [(s, m) for h, s, m in next_frontier]
    
    print(f"\nNo phase 3 solution within depth {max_depth}")
    return None


if __name__ == '__main__':
    # Load phase 1 state
    state = parse_initial()
    with open('/home/claude/puzzle/phase1_solution.txt') as f:
        phase1 = [line.rstrip() for line in f if line.strip()]
    state = apply_solution(state, phase1)
    assert state is not None
    
    print(f"Starting phase 3 from phase 1 end state (conv={state.conversions})")
    print(f"Phase 1 has {len(phase1)} moves")
    
    bw = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
    md = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    tl = int(sys.argv[3]) if len(sys.argv) > 3 else 14400
    
    print(f"Config: beam_width={bw}, max_depth={md}, time_limit={tl}s")
    
    solution = beam_search_phase3(state, beam_width=bw, max_depth=md, time_limit=tl)
    
    if solution:
        print(f"\n=== Phase 3 Solution ({len(solution)} moves) ===")
        for i, m in enumerate(solution):
            print(f"  {i+1}. {m}")
        
        # Verify
        final = apply_solution(state, solution)
        print(f"\nVerification: won={is_won(final)}, conversions={final.conversions}")
        
        with open('/home/claude/puzzle/phase3_solution.txt', 'w') as f:
            for m in solution:
                f.write(m + '\n')
        
        # Full solution
        with open('/home/claude/puzzle/full_solution.txt', 'w') as f:
            for m in phase1 + solution:
                f.write(m + '\n')
        print(f"\nFull solution ({len(phase1)+len(solution)} moves) saved to full_solution.txt")
    else:
        print("\nPhase 3 failed")
