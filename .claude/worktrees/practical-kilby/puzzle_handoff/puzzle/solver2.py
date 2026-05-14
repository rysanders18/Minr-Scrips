#!/usr/bin/env python3
"""
Compound-action solver.
Instead of individual conversions/clicks, treats "form a chain and slide it N times" 
as a single action. This dramatically reduces branching factor.
"""

from engine import PuzzleState, Block, parse_initial_state, GLASS, CONCRETE, GOAL_POS, SEA_LANTERN
from engine import X_MIN, X_MAX, Y_MIN, Y_MAX, Z_MIN, Z_MAX
from collections import defaultdict, deque
import heapq
import time


def find_formable_chains(state):
    """
    Find all contiguous same-color groups that can be formed into chains.
    Returns list of (axis_idx, positions, color, conversions_needed).
    conversions_needed is the list of positions that need converting.
    """
    chains = []
    visited = set()
    
    for pos, block in state.grid.items():
        color = block.color
        
        for axis_idx in range(3):
            # Find the start of this contiguous group
            prev = list(pos)
            prev[axis_idx] -= 1
            prev = tuple(prev)
            if prev in state.grid and state.grid[prev].color == color:
                continue
            
            # Walk forward to find the full group
            group = [pos]
            p = list(pos)
            while True:
                p[axis_idx] += 1
                tp = tuple(p)
                if tp in state.grid and state.grid[tp].color == color:
                    group.append(tp)
                else:
                    break
            
            if len(group) < 2:
                continue
            
            key = (axis_idx, tuple(sorted(group)))
            if key in visited:
                continue
            visited.add(key)
            
            # What conversions are needed?
            first = state.grid[group[0]]
            last = state.grid[group[-1]]
            conversions = []
            if first.material == GLASS:
                conversions.append(group[0])
            if last.material == GLASS:
                conversions.append(group[-1])
            
            # Can we afford the conversions?
            if state.conversions_used + len(conversions) <= state.max_conversions:
                chains.append((axis_idx, group, color, conversions))
    
    return chains


def get_compound_moves(state):
    """
    Generate all compound moves: form a chain + slide it 1 step in either direction.
    Each compound move is: convert endpoints (if needed) + click endpoint to move.
    Returns list of (new_state, description, conversions_used).
    """
    moves = []
    
    formable = find_formable_chains(state)
    
    for axis_idx, group, color, conversions in formable:
        axis = ['X', 'Y', 'Z'][axis_idx]
        
        # Create state with conversions applied
        chain_state = state.copy()
        for conv_pos in conversions:
            chain_state.grid[conv_pos].material = CONCRETE
            chain_state.conversions_used += 1
        
        # Try sliding in each direction (possibly multiple steps)
        for direction in [-1, +1]:
            # Try 1 step at a time, up to max possible
            current = chain_state
            current_group = list(group)
            
            for steps in range(1, 9):  # Max 8 steps in 8x8x8 grid
                if not current.can_move_chain(axis_idx, current_group, direction):
                    break
                
                current = current.move_chain(axis_idx, current_group, direction)
                # Update group positions
                current_group = [
                    tuple(p[i] + (direction if i == axis_idx else 0) for i in range(3))
                    for p in current_group
                ]
                
                dir_str = '+' if direction > 0 else '-'
                conv_desc = f" (convert {len(conversions)})" if conversions else ""
                desc = f"{color} {axis}-chain len={len(group)} slide {dir_str}{axis} x{steps}{conv_desc}"
                moves.append((current, desc, len(conversions)))
    
    # Also include already-formed chains that just need clicking
    # (these are covered by the above since conversions=[] for already-concrete chains)
    
    return moves


def heuristic_v2(state):
    """
    Better heuristic that considers:
    1. Distance of closest red to goal
    2. Whether the goal position is blocked
    3. Whether there's a formable red chain near the goal
    """
    # Base: min Manhattan distance of any red to goal
    min_dist = float('inf')
    for pos, block in state.grid.items():
        if block.color == 'red':
            dist = abs(pos[0]-GOAL_POS[0]) + abs(pos[1]-GOAL_POS[1]) + abs(pos[2]-GOAL_POS[2])
            min_dist = min(min_dist, dist)
    
    # Penalty: is goal blocked?
    if GOAL_POS in state.grid and state.grid[GOAL_POS].color != 'red':
        min_dist += 2  # Need extra moves to clear
    
    return min_dist


def state_fingerprint(state):
    """Compact state hash for dedup."""
    items = []
    for pos in sorted(state.grid.keys()):
        b = state.grid[pos]
        items.append((pos, b.color, b.material))
    return hash((tuple(items), state.conversions_used))


def compound_solver(initial_state, max_depth=30, time_limit=300):
    """
    A* solver using compound moves (form chain + slide).
    """
    start_time = time.time()
    
    counter = 0
    h = heuristic_v2(initial_state)
    # (f_score, counter, depth, conversions_used, state, moves_list)
    queue = [(h, counter, 0, 0, initial_state, [])]
    visited = set()
    
    best_h = h
    nodes_explored = 0
    
    print(f"Initial heuristic: {h}")
    print(f"Starting compound solver with max_depth={max_depth}, time_limit={time_limit}s")
    
    while queue:
        elapsed = time.time() - start_time
        if elapsed > time_limit:
            print(f"\nTime limit reached. Explored {nodes_explored} nodes. Best h={best_h}")
            return None
        
        f, _, depth, conv_used, state, moves = heapq.heappop(queue)
        
        fp = state_fingerprint(state)
        if fp in visited:
            continue
        visited.add(fp)
        
        nodes_explored += 1
        
        if nodes_explored % 5000 == 0:
            print(f"Explored {nodes_explored}, depth={depth}, h={heuristic_v2(state):.0f}, "
                  f"best_h={best_h:.0f}, queue={len(queue)}, conv={conv_used}, time={elapsed:.1f}s")
        
        if state.is_won():
            elapsed = time.time() - start_time
            print(f"\n*** SOLUTION FOUND! ***")
            print(f"Moves: {len(moves)}, Conversions: {conv_used}, "
                  f"Nodes: {nodes_explored}, Time: {elapsed:.1f}s")
            return moves
        
        if depth >= max_depth:
            continue
        
        h = heuristic_v2(state)
        if h < best_h:
            best_h = h
            print(f"New best h={best_h:.0f} at depth={depth}, nodes={nodes_explored}, "
                  f"conv={conv_used}, time={elapsed:.1f}s")
        
        # Generate compound moves
        compound_moves = get_compound_moves(state)
        
        for new_state, desc, n_conv in compound_moves:
            counter += 1
            new_h = heuristic_v2(new_state)
            new_conv = state.conversions_used + n_conv  # Already applied in new_state
            f_score = new_h + depth + 1
            heapq.heappush(queue, (f_score, counter, depth + 1, new_state.conversions_used, 
                                    new_state, moves + [desc]))
    
    print(f"\nNo solution found. Explored {nodes_explored} nodes.")
    return None


if __name__ == '__main__':
    state = parse_initial_state()
    
    # First, let's see how many compound moves are available initially
    moves = get_compound_moves(state)
    print(f"Compound moves available from initial state: {len(moves)}")
    for m in sorted(moves, key=lambda x: x[1]):
        h = heuristic_v2(m[0])
        print(f"  h={h:.0f} conv={m[2]} | {m[1]}")
    
    print(f"\n{'='*70}")
    solution = compound_solver(state, max_depth=25, time_limit=120)
    if solution:
        print("\nSolution:")
        for i, move in enumerate(solution):
            print(f"  {i+1}. {move}")
