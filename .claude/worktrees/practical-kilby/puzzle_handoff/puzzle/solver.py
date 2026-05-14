#!/usr/bin/env python3
"""
Puzzle Solver - Dependency-driven approach.
Analyzes what needs to happen to get red to the goal, 
traces dependencies, and searches for solutions.
"""

from engine import PuzzleState, Block, parse_initial_state, GLASS, CONCRETE, GOAL_POS, SEA_LANTERN
from engine import X_MIN, X_MAX, Y_MIN, Y_MAX, Z_MIN, Z_MAX
from collections import defaultdict, deque
import heapq
import time

def find_contiguous_groups(state):
    """Find all maximal contiguous groups of same-color blocks along each axis."""
    groups = []
    visited = set()
    
    for pos, block in state.grid.items():
        x, y, z = pos
        color = block.color
        
        for axis_idx in range(3):
            # Check if this is the start of a group along this axis
            prev = list(pos)
            prev[axis_idx] -= 1
            prev = tuple(prev)
            
            if prev in state.grid and state.grid[prev].color == color:
                continue  # Not the start
            
            # Walk forward
            group = [pos]
            p = list(pos)
            while True:
                p[axis_idx] += 1
                tp = tuple(p)
                if tp in state.grid and state.grid[tp].color == color:
                    group.append(tp)
                else:
                    break
            
            if len(group) >= 2:
                key = (axis_idx, tuple(group))
                if key not in visited:
                    visited.add(key)
                    groups.append((axis_idx, group, color))
    
    return groups


def analyze_state(state):
    """Detailed analysis of the current state."""
    print("=" * 70)
    print("STATE ANALYSIS")
    print("=" * 70)
    
    # Find all contiguous groups (potential chains if endpoints converted)
    groups = find_contiguous_groups(state)
    print(f"\nContiguous same-color groups (potential chains):")
    for axis_idx, group, color in sorted(groups, key=lambda x: (-len(x[1]), x[2])):
        axis = ['X', 'Y', 'Z'][axis_idx]
        
        # Check if it's already a valid chain
        first = state.grid[group[0]]
        last = state.grid[group[-1]]
        is_chain = (first.material == CONCRETE and last.material == CONCRETE)
        
        # Check movement in both directions
        can_neg = state.can_move_chain(axis_idx, group, -1) if is_chain else None
        can_pos = state.can_move_chain(axis_idx, group, +1) if is_chain else None
        
        # What blocks are adjacent in each direction?
        end_low = list(group[0])
        end_low[axis_idx] -= 1
        end_low = tuple(end_low)
        end_high = list(group[-1])
        end_high[axis_idx] += 1
        end_high = tuple(end_high)
        
        low_info = state.grid[end_low].color if end_low in state.grid else ("OOB" if not state.in_bounds(*end_low) else "empty")
        high_info = state.grid[end_high].color if end_high in state.grid else ("OOB" if not state.in_bounds(*end_high) else "empty")
        
        status = "CHAIN" if is_chain else "formable"
        move_info = ""
        if is_chain:
            dirs = []
            if can_neg: dirs.append(f"-{axis}")
            if can_pos: dirs.append(f"+{axis}")
            move_info = f" moves: {dirs}" if dirs else " STUCK"
        
        vals = [p[axis_idx] for p in group]
        print(f"  {color:8s} {axis}-axis len={len(group):2d} range={min(vals)}-{max(vals)} [{status}]{move_info}")
        print(f"           adj: -{axis}={low_info}, +{axis}={high_info}")
    
    # Existing chains
    chains = state.find_all_chains()
    print(f"\nActive chains: {len(chains)}")
    for axis_idx, positions in chains:
        axis = ['X', 'Y', 'Z'][axis_idx]
        color = state.grid[positions[0]].color
        can_neg = state.can_move_chain(axis_idx, positions, -1)
        can_pos = state.can_move_chain(axis_idx, positions, +1)
        print(f"  {color} {axis}-axis: {positions} can_move: -{axis}={can_neg} +{axis}={can_pos}")
    
    # Red block positions and distances to goal
    print(f"\nRed blocks and Manhattan distance to goal {GOAL_POS}:")
    for pos, block in sorted(state.grid.items()):
        if block.color == 'red':
            dist = abs(pos[0]-GOAL_POS[0]) + abs(pos[1]-GOAL_POS[1]) + abs(pos[2]-GOAL_POS[2])
            mat = "CONCRETE" if block.material == CONCRETE else "glass"
            print(f"  {pos} [{mat}] dist={dist}")
    
    # What's at and around the goal
    print(f"\nGoal area (x=6925, y=146, z=2546):")
    for dx in range(-1, 3):
        for dy in range(-1, 2):
            for dz in range(-1, 2):
                p = (6925+dx, 146+dy, 2546+dz)
                if p in state.grid:
                    b = state.grid[p]
                    print(f"  {p}: {b.color} ({b.material})")
    
    print(f"\nConversions used: {state.conversions_used}/{state.max_conversions}")
    print(f"Won: {state.is_won()}")


def try_manual_sequence(state, moves_desc):
    """
    Execute a sequence of moves and show results.
    Each move is either:
      ('convert', (x, y, z))
      ('click', (x, y, z), direction)  where direction is +1 or -1, along the chain axis
    """
    current = state.copy()
    for i, move in enumerate(moves_desc):
        print(f"\n--- Step {i+1}: {move} ---")
        
        if move[0] == 'convert':
            pos = move[1]
            if pos not in current.grid:
                print(f"  ERROR: No block at {pos}")
                return current
            b = current.grid[pos]
            if b.material == CONCRETE:
                print(f"  ERROR: Already concrete at {pos}")
                return current
            current.grid[pos].material = CONCRETE
            current.conversions_used += 1
            print(f"  Converted {b.color} at {pos} to concrete (#{current.conversions_used})")
        
        elif move[0] == 'click':
            pos = move[1]
            direction = move[2]
            if pos not in current.grid:
                print(f"  ERROR: No block at {pos}")
                return current
            b = current.grid[pos]
            if b.material != CONCRETE:
                print(f"  ERROR: Block at {pos} is not concrete")
                return current
            
            chains = current.find_chain(pos)
            if not chains:
                print(f"  ERROR: No chain found at {pos}")
                return current
            
            moved_any = False
            for axis_idx, positions in chains:
                sorted_pos = sorted(positions, key=lambda p: p[axis_idx])
                # Determine move direction based on which endpoint was clicked
                if pos == sorted_pos[0] and direction == -1:
                    move_dir = -1
                elif pos == sorted_pos[-1] and direction == +1:
                    move_dir = +1
                elif pos == sorted_pos[0] and direction == +1:
                    # Clicking low end with +1 direction? 
                    # Maybe the user means the chain should move +
                    # Re-interpretation: direction IS the move direction
                    move_dir = +1
                    # But this endpoint would need to be the high end for +1
                    # Skip if not matching
                    if pos != sorted_pos[-1]:
                        continue
                elif pos == sorted_pos[-1] and direction == -1:
                    move_dir = -1
                    if pos != sorted_pos[0]:
                        continue
                else:
                    continue
                
                if current.can_move_chain(axis_idx, positions, move_dir):
                    current = current.move_chain(axis_idx, positions, move_dir)
                    axis = ['X', 'Y', 'Z'][axis_idx]
                    print(f"  Moved {b.color} chain {axis}{'+' if move_dir > 0 else '-'}")
                    moved_any = True
                else:
                    axis = ['X', 'Y', 'Z'][axis_idx]
                    print(f"  Chain {axis} blocked in direction {move_dir}")
            
            if not moved_any:
                print(f"  WARNING: No chain could be moved")
        
        if current.is_won():
            print(f"\n*** WIN! Red concrete is adjacent to the sea lantern! ***")
            return current
    
    return current


def heuristic(state):
    """
    Heuristic: minimum Manhattan distance from any red block to GOAL_POS.
    Lower is better.
    """
    min_dist = float('inf')
    for pos, block in state.grid.items():
        if block.color == 'red':
            dist = abs(pos[0]-GOAL_POS[0]) + abs(pos[1]-GOAL_POS[1]) + abs(pos[2]-GOAL_POS[2])
            if block.material == CONCRETE:
                dist -= 0.5  # Slight bonus for already being concrete
            min_dist = min(min_dist, dist)
    return min_dist


def smart_conversion_candidates(state):
    """
    Instead of considering all 86 glass blocks for conversion,
    only consider conversions that would create or extend chains.
    """
    candidates = []
    
    # Find all contiguous groups
    groups = find_contiguous_groups(state)
    
    for axis_idx, group, color in groups:
        first_pos = group[0]
        last_pos = group[-1]
        first_block = state.grid[first_pos]
        last_block = state.grid[last_pos]
        
        # If this group could become a chain with 1-2 conversions
        needs = []
        if first_block.material == GLASS:
            needs.append(('convert', first_pos))
        if last_block.material == GLASS:
            needs.append(('convert', last_pos))
        
        if len(needs) <= 2:
            for conv in needs:
                candidates.append(conv)
    
    return list(set(candidates))


def bfs_solver(initial_state, max_depth=50, time_limit=120):
    """
    BFS solver with heuristic ordering and smart move generation.
    """
    start_time = time.time()
    
    # Priority queue: (heuristic + depth, counter, depth, state, moves)
    counter = 0
    h = heuristic(initial_state)
    queue = [(h, counter, 0, initial_state, [])]
    visited = set()
    
    best_h = h
    nodes_explored = 0
    
    while queue:
        if time.time() - start_time > time_limit:
            print(f"Time limit reached. Explored {nodes_explored} nodes. Best h={best_h}")
            return None
        
        f, _, depth, state, moves = heapq.heappop(queue)
        
        # State hash for dedup
        sh = state.state_hash()
        if sh in visited:
            continue
        visited.add(sh)
        
        nodes_explored += 1
        
        if nodes_explored % 10000 == 0:
            elapsed = time.time() - start_time
            print(f"Explored {nodes_explored} nodes, depth={depth}, h={heuristic(state):.1f}, "
                  f"best_h={best_h:.1f}, queue={len(queue)}, time={elapsed:.1f}s")
        
        if state.is_won():
            print(f"SOLUTION FOUND! {len(moves)} moves, {nodes_explored} nodes explored")
            return moves
        
        if depth >= max_depth:
            continue
        
        h = heuristic(state)
        if h < best_h:
            best_h = h
            elapsed = time.time() - start_time
            print(f"New best h={best_h:.1f} at depth={depth}, nodes={nodes_explored}, time={elapsed:.1f}s")
        
        # Generate moves
        # 1. Chain moves (cheap, always try)
        chain_moves = state.get_chain_moves_only()
        for action_type, params, new_state, desc in chain_moves:
            counter += 1
            new_h = heuristic(new_state)
            heapq.heappush(queue, (new_h + depth + 1, counter, depth + 1, new_state, moves + [desc]))
        
        # 2. Smart conversions (only endpoints of contiguous groups)
        if state.conversions_used < state.max_conversions:
            conv_candidates = smart_conversion_candidates(state)
            for _, pos in conv_candidates:
                new_state = state.copy()
                new_state.grid[pos].material = CONCRETE
                new_state.conversions_used += 1
                counter += 1
                new_h = heuristic(new_state)
                desc = f"Convert {state.grid[pos].color} at {pos}"
                heapq.heappush(queue, (new_h + depth + 1, counter, depth + 1, new_state, moves + [desc]))
    
    print(f"No solution found. Explored {nodes_explored} nodes.")
    return None


if __name__ == '__main__':
    state = parse_initial_state()
    analyze_state(state)
    
    print("\n" + "=" * 70)
    print("ATTEMPTING SOLVER (A* with smart conversions)")
    print("=" * 70)
    
    solution = bfs_solver(state, max_depth=40, time_limit=60)
    if solution:
        print("\nSolution moves:")
        for i, move in enumerate(solution):
            print(f"  {i+1}. {move}")
