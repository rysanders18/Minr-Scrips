#!/usr/bin/env python3
"""
Phase 1 solver v2 - more aggressive search with better heuristics.
Goal: green concrete adjacent to blocker at (6925, 146, 2546).
"""

from fast_engine import (
    State, parse_initial, compound_moves, find_formable_chains,
    find_all_chains, slide_chain, max_slide, pos_to_int, int_to_pos,
    COLOR_IDS, ID_TO_COLOR, GOAL_POS
)
import time
import sys
import gc

BLOCKER_ADJ = [
    (6925, 146, 2545),
    (6925, 146, 2547),
    (6925, 145, 2546),
    (6925, 147, 2546),
]
BLOCKER_ADJ_SET = set(BLOCKER_ADJ)
BLOCKER = (6925, 146, 2546)

GREEN_ID = COLOR_IDS['green']


def is_phase1_won(state):
    for p in BLOCKER_ADJ:
        v = state.get(p)
        if v and v[0] == GREEN_ID and v[1]:
            return True
    return False


def count_movable_greens(state):
    """Count greens in any formable chain (indicates mobility)."""
    chains = find_formable_chains(state)
    in_chain = set()
    for axis_idx, positions, color, needed in chains:
        if color == GREEN_ID:
            for p in positions:
                in_chain.add(p)
    return len(in_chain)


def count_greens_at_x(state, target_x):
    """How many greens are at given x column (proxies 'progress toward x=6925')."""
    n = 0
    for pi, (c, is_c) in state.grid.items():
        if c == GREEN_ID:
            p = int_to_pos(pi)
            if p[0] == target_x:
                n += 1
    return n


def heuristic_phase1(state):
    """
    Composite heuristic:
    - Min Manhattan distance from any green to any blocker-adj position
    - Negative bonus for greens at x=6925 (target column)
    - Negative bonus for concrete greens at low y (near blocker)
    """
    best_dist = 1000
    greens_at_6925_low_y = 0
    greens_concrete_at_6925 = 0
    total_greens_at_6925 = 0
    
    for pi, (c, is_c) in state.grid.items():
        if c != GREEN_ID:
            continue
        pos = int_to_pos(pi)
        
        if pos[0] == 6925:
            total_greens_at_6925 += 1
            if is_c:
                greens_concrete_at_6925 += 1
            if pos[1] <= 147:
                greens_at_6925_low_y += 1
        
        for target in BLOCKER_ADJ:
            d = abs(pos[0]-target[0]) + abs(pos[1]-target[1]) + abs(pos[2]-target[2])
            if d < best_dist:
                best_dist = d
    
    # Composite: primary = distance, secondary bonuses
    h = best_dist - 0.3 * total_greens_at_6925 - 0.5 * greens_concrete_at_6925 - 0.8 * greens_at_6925_low_y
    return h


def state_hash(state):
    # Don't include conversions in hash: same grid states should be equivalent regardless
    # of conversion path. But we should prefer lower-conversion paths. We'll handle this
    # by keeping the lowest-conversions state per grid-hash.
    return hash(frozenset(state.grid.items()))


def beam_search_phase1(initial_state, beam_width=20000, max_depth=40, max_conversions=60, time_limit=14400):
    """
    Wide beam search with best-first expansion at each depth.
    """
    start_time = time.time()
    
    if is_phase1_won(initial_state):
        return []
    
    # Frontier: (state, moves_so_far)
    frontier = [(initial_state, [])]
    visited = {state_hash(initial_state): initial_state.conversions}
    
    initial_h = heuristic_phase1(initial_state)
    best_h = initial_h
    print(f"[{0:.0f}s] Initial h: {initial_h:.2f}, beam_width={beam_width}, max_depth={max_depth}")
    
    for depth in range(1, max_depth + 1):
        if time.time() - start_time > time_limit:
            print(f"\n[TIMEOUT] at depth {depth} after {time.time()-start_time:.0f}s")
            return None
        
        # Expand frontier with progress updates
        next_frontier = []
        n_expanded = 0
        n_dups = 0
        n_won = 0
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
                
                if is_phase1_won(new_state):
                    elapsed = time.time() - start_time
                    print(f"\n*** PHASE 1 SOLUTION at depth {depth} in {elapsed:.0f}s ***")
                    return moves + [desc]
                
                h = heuristic_phase1(new_state)
                next_frontier.append((h, new_state, moves + [desc]))
        
        if not next_frontier:
            print(f"[depth {depth}] No unexpanded states")
            return None
        
        # Top beam_width by h
        next_frontier.sort(key=lambda x: x[0])
        next_frontier = next_frontier[:beam_width]
        
        depth_best_h = next_frontier[0][0]
        if depth_best_h < best_h:
            best_h = depth_best_h
        
        elapsed = time.time() - start_time
        t_depth = time.time() - t_start_depth
        print(f"[{elapsed:.0f}s] depth={depth}: expanded={n_expanded}, frontier={len(next_frontier)}, "
              f"dups={n_dups}, best_h={depth_best_h:.2f} ever={best_h:.2f}, "
              f"visited={len(visited)}, depth_time={t_depth:.1f}s")
        
        # Memory management
        if len(visited) > 10_000_000:
            print(f"  [gc] resetting visited set")
            visited = {sh: c for sh, c in list(visited.items())[:1_000_000]}
            gc.collect()
        
        frontier = [(s, m) for h, s, m in next_frontier]
    
    print(f"\nNo phase 1 solution within depth {max_depth}")
    return None


def trace_solution(initial_state, moves):
    """Re-run solution to verify."""
    print("\n=== Verifying solution ===")
    state = initial_state
    for i, m in enumerate(moves):
        cm = compound_moves(state, conversion_limit=60)
        found = None
        for new_state, desc, n_conv in cm:
            if desc == m:
                found = new_state
                break
        if found is None:
            print(f"  {i+1}. ERROR: move not reproducible: {m}")
            return False
        state = found
        print(f"  {i+1}. {m}  [conv={state.conversions}]")
    print(f"  Final: won={is_phase1_won(state)}, conversions={state.conversions}")
    return is_phase1_won(state)


if __name__ == '__main__':
    state = parse_initial()
    print(f"Starting phase 1 search (already won? {is_phase1_won(state)})")
    
    # Arguments: beam_width max_depth time_limit_seconds
    bw = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    md = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    tl = int(sys.argv[3]) if len(sys.argv) > 3 else 14400
    
    print(f"Config: beam_width={bw}, max_depth={md}, time_limit={tl}s")
    
    solution = beam_search_phase1(state, beam_width=bw, max_depth=md, time_limit=tl)
    
    if solution:
        print(f"\n=== Phase 1 Solution ({len(solution)} moves) ===")
        for i, m in enumerate(solution):
            print(f"  {i+1}. {m}")
        
        # Verify
        trace_solution(state, solution)
        
        # Save
        with open('/home/claude/puzzle/phase1_solution.txt', 'w') as f:
            for m in solution:
                f.write(m + '\n')
        print("\nSaved to phase1_solution.txt")
    else:
        print("\nNo solution found")
