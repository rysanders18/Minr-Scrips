#!/usr/bin/env python3
"""
Phase 1 solver: find move sequence that places green concrete adjacent to blocker.
Uses iterative deepening with compound moves and heuristic-guided search.
"""

from fast_engine import (
    State, parse_initial, compound_moves, find_formable_chains,
    find_all_chains, slide_chain, max_slide, pos_to_int, int_to_pos,
    COLOR_IDS, ID_TO_COLOR, GOAL_POS
)
import time
import heapq
import sys

# Phase 1 target: green concrete at any of these positions
BLOCKER_ADJ = [
    (6925, 146, 2545),
    (6925, 146, 2547),
    (6925, 145, 2546),
    (6925, 147, 2546),
]

GREEN_ID = COLOR_IDS['green']


def is_phase1_won(state):
    """A green concrete block is adjacent to the blocker."""
    for p in BLOCKER_ADJ:
        v = state.get(p)
        if v and v[0] == GREEN_ID and v[1]:
            return True
    return False


def heuristic_phase1(state):
    """
    Min distance from ANY green block to ANY blocker-adjacent position.
    Bonus for concrete greens (they're more useful).
    """
    best = 1000
    for pi, (c, is_c) in state.grid.items():
        if c != GREEN_ID:
            continue
        pos = int_to_pos(pi)
        for target in BLOCKER_ADJ:
            d = abs(pos[0]-target[0]) + abs(pos[1]-target[1]) + abs(pos[2]-target[2])
            if is_c:
                d -= 0.2  # small bonus for concrete
            if d < best:
                best = d
    return best


def state_hash(state):
    """Fast state hash."""
    return hash((frozenset(state.grid.items()), state.conversions))


def ida_star_phase1(initial_state, max_conversions=60, time_limit=3600):
    """
    Iterative deepening A* for phase 1.
    Uses a bounded-depth DFS that expands the frontier by heuristic + depth bound.
    """
    start_time = time.time()
    
    # Initialize: first frontier is just initial state
    initial_h = heuristic_phase1(initial_state)
    print(f"Initial heuristic: {initial_h}")
    
    if is_phase1_won(initial_state):
        return []
    
    # IDA* bound
    bound = initial_h
    best_h_ever = initial_h
    total_nodes = 0
    
    def dfs(state, moves, g, bound, visited):
        nonlocal best_h_ever, total_nodes
        
        if time.time() - start_time > time_limit:
            return 'timeout'
        
        total_nodes += 1
        if total_nodes % 50000 == 0:
            elapsed = time.time() - start_time
            print(f"  nodes={total_nodes}, depth={g}, bound={bound}, best_h={best_h_ever}, "
                  f"visited={len(visited)}, time={elapsed:.1f}s")
        
        h = heuristic_phase1(state)
        f = g + h
        
        if h < best_h_ever:
            best_h_ever = h
            elapsed = time.time() - start_time
            print(f"  ★ best_h={h:.1f} at depth={g}, conv={state.conversions}, "
                  f"nodes={total_nodes}, time={elapsed:.1f}s")
            # Print first 3 moves for context
            for i, m in enumerate(moves[:3]):
                print(f"      {i+1}. {m}")
            if len(moves) > 3:
                print(f"      ... ({len(moves)} total)")
        
        if f > bound:
            return f
        
        if is_phase1_won(state):
            return moves
        
        # State dedup within current DFS (helpful for cycles)
        sh = state_hash(state)
        if sh in visited:
            return float('inf')
        visited.add(sh)
        
        # Generate compound moves, sort by h
        cm = compound_moves(state, conversion_limit=max_conversions)
        if not cm:
            visited.discard(sh)
            return float('inf')
        
        # Sort by new h (lower is better)
        scored = []
        for new_state, desc, n_conv in cm:
            new_h = heuristic_phase1(new_state)
            scored.append((new_h, new_state, desc, n_conv))
        scored.sort(key=lambda x: x[0])
        
        min_next = float('inf')
        for new_h, new_state, desc, n_conv in scored:
            result = dfs(new_state, moves + [desc], g + 1, bound, visited)
            if result == 'timeout':
                return 'timeout'
            if isinstance(result, list):
                return result
            if result < min_next:
                min_next = result
        
        visited.discard(sh)  # Allow revisiting via different paths
        return min_next
    
    max_iter = 20
    for iteration in range(max_iter):
        print(f"\n=== IDA* iteration {iteration+1}: bound={bound} ===")
        visited = set()
        result = dfs(initial_state, [], 0, bound, visited)
        
        if result == 'timeout':
            print(f"TIMEOUT after {time.time()-start_time:.1f}s")
            return None
        
        if isinstance(result, list):
            print(f"\n*** SOLUTION found in {time.time()-start_time:.1f}s ***")
            return result
        
        # Not found, increase bound
        if result == float('inf'):
            print("No improvement possible - no more states reachable")
            return None
        
        new_bound = result
        if new_bound <= bound:
            new_bound = bound + 1
        bound = new_bound
        print(f"No solution at bound. New bound = {bound}")


def beam_search_phase1(initial_state, beam_width=5000, max_depth=25, max_conversions=60, time_limit=3600):
    """
    Beam search: keep top-K states by heuristic at each depth.
    More memory-efficient than full BFS, still finds solutions if heuristic is decent.
    """
    start_time = time.time()
    
    if is_phase1_won(initial_state):
        return []
    
    # Frontier: list of (state, moves_so_far)
    frontier = [(initial_state, [])]
    visited = {state_hash(initial_state)}
    best_h = heuristic_phase1(initial_state)
    print(f"Initial h: {best_h}, beam_width={beam_width}, max_depth={max_depth}")
    
    for depth in range(1, max_depth + 1):
        if time.time() - start_time > time_limit:
            print(f"TIMEOUT at depth {depth}")
            return None
        
        # Expand frontier
        next_frontier = []
        for state, moves in frontier:
            cm = compound_moves(state, conversion_limit=max_conversions)
            for new_state, desc, n_conv in cm:
                sh = state_hash(new_state)
                if sh in visited:
                    continue
                visited.add(sh)
                
                if is_phase1_won(new_state):
                    elapsed = time.time() - start_time
                    print(f"\n*** SOLUTION found at depth {depth} in {elapsed:.1f}s! ***")
                    return moves + [desc]
                
                h = heuristic_phase1(new_state)
                next_frontier.append((h, new_state, moves + [desc]))
        
        if not next_frontier:
            print(f"No more states at depth {depth}")
            return None
        
        # Keep top beam_width by h
        next_frontier.sort(key=lambda x: x[0])
        next_frontier = next_frontier[:beam_width]
        
        depth_best_h = next_frontier[0][0]
        if depth_best_h < best_h:
            best_h = depth_best_h
        
        elapsed = time.time() - start_time
        print(f"Depth {depth}: frontier size={len(next_frontier)}, "
              f"best_h={depth_best_h:.1f} ever={best_h:.1f}, "
              f"visited={len(visited)}, time={elapsed:.1f}s")
        
        # Memory check: if visited is getting huge, drop it
        if len(visited) > 5_000_000:
            print(f"  Visited set pruning...")
            visited = set()  # Restart dedup
        
        frontier = [(s, m) for h, s, m in next_frontier]
    
    print(f"No solution found within depth {max_depth}")
    return None


if __name__ == '__main__':
    state = parse_initial()
    print(f"Initial state: {len(state.grid)} blocks")
    print(f"Already won? {is_phase1_won(state)}")
    
    # Try beam search first - faster feedback
    solution = beam_search_phase1(state, beam_width=10000, max_depth=20, time_limit=900)
    
    if solution:
        print(f"\n=== Phase 1 Solution ({len(solution)} moves) ===")
        for i, m in enumerate(solution):
            print(f"  {i+1}. {m}")
    else:
        print("\nNo phase 1 solution found with beam search")
