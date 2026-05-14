#!/usr/bin/env python3
"""
Full solver: start from initial state, goal = red concrete at (6925, 146, 2546).
Uses a structural heuristic that rewards:
- Reds at/near the target layer (y=146, z=2546)
- Empty/red positions in the would-be red X-chain
- Blocker position cleared
"""

from fast_engine import (
    State, parse_initial, compound_moves, find_formable_chains,
    slide_chain, int_to_pos, pos_to_int, COLOR_IDS, ID_TO_COLOR, GOAL_POS,
    X_MIN, X_MAX, Y_MIN, Y_MAX, Z_MIN, Z_MAX
)
import time
import sys
import gc

RED_ID = COLOR_IDS['red']
GREEN_ID = COLOR_IDS['green']
PURPLE_ID = COLOR_IDS['purple']

# For red to slide into (6925, 146, 2546) we need a red X-chain at y=146, z=2546
TARGET_LINE = [(x, 146, 2546) for x in range(X_MIN, X_MAX + 1)]


def is_won(state):
    v = state.get(GOAL_POS)
    return v is not None and v[0] == RED_ID and v[1]


def structural_heuristic(state):
    """
    Combined heuristic:
    1. Is blocker cleared? (blocker = non-red at goal position)
    2. Min red-to-goal distance (raw Manhattan)
    3. Count of reds at y=146, z=2546 (target layer)
    4. Count of empty slots at y=146, z=2546 in the critical span [6925, 6930]
       (more empty = more flexible for chain formation, but also reds needed)
    5. Is red X-chain at y=148, z=2548 still blocked? (penalty)
    """
    goal_v = state.get(GOAL_POS)
    
    # Win condition check
    if goal_v is not None and goal_v[0] == RED_ID and goal_v[1]:
        return -100
    
    blocker_penalty = 0
    if goal_v is not None:
        if goal_v[0] != RED_ID:
            blocker_penalty = 3
    
    # Red metrics
    best_red_dist = 1000
    reds_at_target_line = 0
    reds_at_y146 = 0
    reds_at_z2546 = 0
    reds_at_x6925 = 0
    reds_at_x_in_span = [0] * 8  # x=6925..6932
    
    for pi, (c, is_c) in state.grid.items():
        if c != RED_ID:
            continue
        pos = int_to_pos(pi)
        d = abs(pos[0]-GOAL_POS[0]) + abs(pos[1]-GOAL_POS[1]) + abs(pos[2]-GOAL_POS[2])
        if d < best_red_dist:
            best_red_dist = d
        if pos[1] == 146 and pos[2] == 2546:
            reds_at_target_line += 1
        if pos[1] == 146:
            reds_at_y146 += 1
        if pos[2] == 2546:
            reds_at_z2546 += 1
        if pos[0] == 6925:
            reds_at_x6925 += 1
        reds_at_x_in_span[pos[0] - X_MIN] += 1
    
    # Red X-chain at y=148, z=2548: is either blocker cleared?
    minusX_blocker = state.get((6925, 148, 2548))
    plusX_blocker = state.get((6928, 148, 2548))
    
    red_chain_unblocked = 0
    if minusX_blocker is None:
        red_chain_unblocked += 2  # -X clear! Huge bonus
    if plusX_blocker is None:
        red_chain_unblocked += 1  # +X clear, small bonus (still needs more)
    
    # Compute heuristic
    h = (best_red_dist
         + blocker_penalty
         - 2.0 * reds_at_target_line    # Strongly reward reds on target line
         - 0.3 * reds_at_y146
         - 0.3 * reds_at_z2546
         - 2.0 * reds_at_x6925           # Huge bonus for reds at x=6925
         - 0.5 * red_chain_unblocked)    # Bonus for clearing red chain path
    return h


def state_hash(state):
    return hash(frozenset(state.grid.items()))


def beam_search_full(initial_state, beam_width, max_depth, max_conversions, time_limit):
    start_time = time.time()
    
    if is_won(initial_state):
        return []
    
    frontier = [(initial_state, [])]
    visited = {state_hash(initial_state): initial_state.conversions}
    
    initial_h = structural_heuristic(initial_state)
    best_h = initial_h
    print(f"[0s] FULL search: initial h={initial_h:.2f}, beam={beam_width}, depth={max_depth}")
    
    for depth in range(1, max_depth + 1):
        if time.time() - start_time > time_limit:
            print(f"\n[TIMEOUT] depth {depth} after {time.time()-start_time:.0f}s")
            return None, visited
        
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
                    print(f"\n*** SOLUTION at depth {depth} in {elapsed:.0f}s ***")
                    return moves + [desc], visited
                
                h = structural_heuristic(new_state)
                next_frontier.append((h, new_state, moves + [desc]))
        
        if not next_frontier:
            print(f"[depth {depth}] no more states")
            return None, visited
        
        next_frontier.sort(key=lambda x: x[0])
        next_frontier = next_frontier[:beam_width]
        
        depth_best_h = next_frontier[0][0]
        if depth_best_h < best_h:
            best_h = depth_best_h
        
        elapsed = time.time() - start_time
        t_depth = time.time() - t_start_depth
        mem_est = len(visited) * 200 / 1024 / 1024  # Rough estimate in MB
        print(f"[{elapsed:.0f}s] d={depth}: exp={n_expanded}, front={len(next_frontier)}, "
              f"dups={n_dups}, h={depth_best_h:.2f} best={best_h:.2f}, "
              f"visited={len(visited)} (~{mem_est:.0f}MB), dt={t_depth:.1f}s")
        
        # Memory management
        if len(visited) > 20_000_000:
            print(f"  [gc] pruning visited set")
            sample_items = sorted(visited.items(), key=lambda x: x[1])[:3_000_000]
            visited = dict(sample_items)
            gc.collect()
        
        frontier = [(s, m) for h, s, m in next_frontier]
    
    print(f"\nNo solution within depth {max_depth}")
    return None, visited


def verify_solution(initial_state, solution):
    state = initial_state
    for i, m in enumerate(solution):
        cm = compound_moves(state, conversion_limit=60)
        found = None
        for new_state, desc, n_conv in cm:
            if desc == m:
                found = new_state
                break
        if found is None:
            print(f"VERIFY FAIL at step {i+1}: {m}")
            return False
        state = found
    return is_won(state)


if __name__ == '__main__':
    state = parse_initial()
    
    bw = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    md = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    tl = int(sys.argv[3]) if len(sys.argv) > 3 else 14400
    
    print(f"Config: bw={bw}, depth={md}, time={tl}s")
    
    sol, visited = beam_search_full(state, beam_width=bw, max_depth=md, 
                                      max_conversions=60, time_limit=tl)
    
    if sol:
        print(f"\n=== Full Solution ({len(sol)} moves) ===")
        for i, m in enumerate(sol):
            print(f"  {i+1}. {m}")
        
        if verify_solution(state, sol):
            print("\nVERIFIED ✓")
        else:
            print("\nVERIFICATION FAILED")
        
        with open('/home/claude/puzzle/full_solution.txt', 'w') as f:
            for m in sol:
                f.write(m + '\n')
    else:
        print("No solution found")
