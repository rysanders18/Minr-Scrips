#!/usr/bin/env python3
"""
Fast puzzle engine - v2.
Compact state representation for efficient search.
State = frozenset of (pos, color_id, is_concrete).
"""

from collections import defaultdict

# Grid bounds
X_MIN, X_MAX = 6925, 6932
Y_MIN, Y_MAX = 145, 152
Z_MIN, Z_MAX = 2544, 2551

SEA_LANTERN = (6924, 146, 2546)
GOAL_POS = (6925, 146, 2546)

# Color ID encoding
COLOR_IDS = {
    'red': 0, 'blue': 1, 'green': 2, 'purple': 3,
    'pink': 4, 'orange': 5, 'cyan': 6, 'brown': 7,
}
ID_TO_COLOR = {v: k for k, v in COLOR_IDS.items()}


def pos_to_int(pos):
    """Pack (x,y,z) into a single int for compact storage."""
    x, y, z = pos
    return (x - X_MIN) * 64 + (y - Y_MIN) * 8 + (z - Z_MIN)

def int_to_pos(i):
    x = i // 64 + X_MIN
    rem = i % 64
    y = rem // 8 + Y_MIN
    z = rem % 8 + Z_MIN
    return (x, y, z)


class State:
    """
    Immutable state using frozensets for efficient hashing.
    grid: dict {pos_int: (color_id, is_concrete)}
    """
    __slots__ = ['grid', 'conversions']
    
    def __init__(self, grid=None, conversions=0):
        self.grid = grid if grid is not None else {}
        self.conversions = conversions
    
    def copy(self):
        return State(dict(self.grid), self.conversions)
    
    def get(self, pos):
        """Get (color_id, is_concrete) tuple or None."""
        pi = pos_to_int(pos) if isinstance(pos, tuple) else pos
        return self.grid.get(pi)
    
    def color_at(self, pos):
        v = self.get(pos)
        return v[0] if v else None
    
    def is_concrete_at(self, pos):
        v = self.get(pos)
        return v[1] if v else False
    
    def is_empty(self, pos):
        pi = pos_to_int(pos) if isinstance(pos, tuple) else pos
        return pi not in self.grid
    
    @staticmethod
    def in_bounds(pos):
        x, y, z = pos
        return (X_MIN <= x <= X_MAX and Y_MIN <= y <= Y_MAX and Z_MIN <= z <= Z_MAX)
    
    def is_won(self):
        """Check if red concrete is adjacent to sea lantern at (6925, 146, 2546)."""
        v = self.get(GOAL_POS)
        return v is not None and v[0] == COLOR_IDS['red'] and v[1]
    
    def convert(self, pos):
        """Return new state with pos converted to concrete."""
        pi = pos_to_int(pos) if isinstance(pos, tuple) else pos
        if pi not in self.grid:
            return None
        c, is_c = self.grid[pi]
        if is_c:
            return None  # Already concrete
        new_grid = dict(self.grid)
        new_grid[pi] = (c, True)
        return State(new_grid, self.conversions + 1)
    
    def fingerprint(self):
        """Hashable representation."""
        return (frozenset(self.grid.items()),)


def find_chain_at(state, pos, axis_idx):
    """
    Find the chain containing pos along given axis, if any.
    Returns list of positions, or None.
    A chain: sequence of same-color blocks, endpoints concrete, middle glass+concrete allowed.
    """
    v = state.get(pos)
    if v is None:
        return None
    color, is_concrete = v
    if not is_concrete:
        return None  # Must start at concrete
    
    # Walk backward to find chain start
    start = list(pos)
    while True:
        p = list(start)
        p[axis_idx] -= 1
        tp = tuple(p)
        v2 = state.get(tp)
        if v2 is None or v2[0] != color:
            break
        start = p
    
    # Walk forward to find chain end
    end = list(pos)
    while True:
        p = list(end)
        p[axis_idx] += 1
        tp = tuple(p)
        v2 = state.get(tp)
        if v2 is None or v2[0] != color:
            break
        end = p
    
    start_pos = tuple(start)
    end_pos = tuple(end)
    start_v = state.get(start_pos)
    end_v = state.get(end_pos)
    
    # Both endpoints must be concrete
    if not start_v[1] or not end_v[1]:
        return None
    
    # Build position list
    positions = []
    p = list(start_pos)
    while True:
        positions.append(tuple(p))
        if tuple(p) == end_pos:
            break
        p[axis_idx] += 1
    
    if len(positions) < 2:
        return None
    
    return positions


def find_all_chains(state):
    """Find all valid chains. Returns list of (axis_idx, positions_tuple)."""
    chains = set()
    for pi, (c, is_c) in state.grid.items():
        if not is_c:
            continue
        pos = int_to_pos(pi)
        for axis_idx in range(3):
            chain = find_chain_at(state, pos, axis_idx)
            if chain is not None:
                chains.add((axis_idx, tuple(chain)))
    return list(chains)


def can_slide(state, axis_idx, positions, direction):
    """Can chain slide 1 step in direction?"""
    position_set = set(positions)
    for p in positions:
        new_p = list(p)
        new_p[axis_idx] += direction
        new_p = tuple(new_p)
        if not State.in_bounds(new_p):
            return False
        if new_p in position_set:
            continue  # Part of chain itself
        if not state.is_empty(new_p):
            return False
    return True


def slide_chain(state, axis_idx, positions, direction):
    """Return new state with chain slid 1 step in direction."""
    new_grid = dict(state.grid)
    # Collect block data
    block_data = {}
    for p in positions:
        pi = pos_to_int(p)
        block_data[p] = new_grid[pi]
        del new_grid[pi]
    # Place at new positions
    for p in positions:
        new_p = list(p)
        new_p[axis_idx] += direction
        new_p = tuple(new_p)
        new_grid[pos_to_int(new_p)] = block_data[p]
    return State(new_grid, state.conversions)


def max_slide(state, axis_idx, positions, direction):
    """Return max number of steps the chain can slide in direction."""
    position_set = set(positions)
    steps = 0
    current_positions = list(positions)
    while True:
        # Check if next step is valid
        next_positions = []
        for p in current_positions:
            np = list(p)
            np[axis_idx] += direction
            np = tuple(np)
            next_positions.append(np)
        
        # Is it valid?
        next_set = set(next_positions)
        current_set = set(current_positions)
        valid = True
        for np in next_positions:
            if not State.in_bounds(np):
                valid = False
                break
            if np in current_set:
                continue  # Occupies position of another chain block
            pi = pos_to_int(np)
            if pi in state.grid:
                valid = False
                break
        
        if not valid:
            break
        
        steps += 1
        current_positions = next_positions
        
        if steps >= 10:  # Safety limit
            break
    
    return steps


def parse_initial():
    """Parse initial state from setblock commands."""
    RAW = """
/setblock 6928 145 2551 minecraft:purple_stained_glass
/setblock 6928 145 2550 minecraft:purple_stained_glass
/setblock 6928 145 2549 minecraft:purple_stained_glass
/setblock 6926 146 2551 minecraft:blue_stained_glass
/setblock 6927 146 2551 minecraft:red_stained_glass
/setblock 6928 146 2551 minecraft:purple_stained_glass
/setblock 6925 146 2550 minecraft:purple_stained_glass
/setblock 6926 146 2550 minecraft:blue_stained_glass
/setblock 6928 146 2550 minecraft:purple_stained_glass
/setblock 6929 146 2550 minecraft:purple_stained_glass
/setblock 6931 146 2550 minecraft:red_stained_glass
/setblock 6925 146 2549 minecraft:green_stained_glass
/setblock 6931 146 2548 minecraft:cyan_stained_glass
/setblock 6925 146 2546 minecraft:green_stained_glass
/setblock 6926 146 2546 minecraft:red_stained_glass
/setblock 6930 146 2546 minecraft:red_stained_glass
/setblock 6927 146 2544 minecraft:purple_stained_glass
/setblock 6926 147 2551 minecraft:blue_stained_glass
/setblock 6927 147 2550 minecraft:purple_stained_glass
/setblock 6929 147 2550 minecraft:blue_stained_glass
/setblock 6926 147 2548 minecraft:blue_stained_glass
/setblock 6929 147 2548 minecraft:blue_stained_glass
/setblock 6931 147 2548 minecraft:cyan_stained_glass
/setblock 6928 147 2546 minecraft:blue_stained_glass
/setblock 6927 147 2545 minecraft:red_stained_glass
/setblock 6930 147 2545 minecraft:green_stained_glass
/setblock 6925 147 2544 minecraft:purple_stained_glass
/setblock 6931 147 2544 minecraft:red_stained_glass
/setblock 6928 148 2550 minecraft:blue_stained_glass
/setblock 6930 148 2550 minecraft:pink_stained_glass
/setblock 6928 148 2549 minecraft:green_stained_glass
/setblock 6930 148 2549 minecraft:pink_stained_glass
/setblock 6925 148 2548 minecraft:purple_stained_glass
/setblock 6926 148 2548 minecraft:red_stained_glass
/setblock 6927 148 2548 minecraft:red_stained_glass
/setblock 6928 148 2548 minecraft:green_stained_glass
/setblock 6929 148 2548 minecraft:brown_stained_glass
/setblock 6930 148 2548 minecraft:pink_stained_glass
/setblock 6931 148 2548 minecraft:cyan_stained_glass
/setblock 6928 148 2547 minecraft:blue_stained_glass
/setblock 6930 148 2547 minecraft:pink_stained_glass
/setblock 6931 148 2547 minecraft:red_stained_glass
/setblock 6926 148 2546 minecraft:blue_stained_glass
/setblock 6930 148 2546 minecraft:pink_stained_glass
/setblock 6930 148 2545 minecraft:green_stained_glass
/setblock 6928 148 2544 minecraft:orange_stained_glass
/setblock 6929 148 2544 minecraft:orange_stained_glass
/setblock 6930 148 2544 minecraft:pink_stained_glass
/setblock 6929 149 2551 minecraft:blue_stained_glass
/setblock 6929 149 2550 minecraft:green_stained_glass
/setblock 6926 149 2549 minecraft:green_stained_glass
/setblock 6927 149 2548 minecraft:green_stained_glass
/setblock 6929 149 2548 minecraft:brown_stained_glass
/setblock 6931 149 2548 minecraft:cyan_stained_glass
/setblock 6932 149 2548 minecraft:red_stained_glass
/setblock 6929 149 2547 minecraft:green_stained_glass
/setblock 6928 149 2546 minecraft:purple_stained_glass
/setblock 6930 149 2546 minecraft:green_stained_glass
/setblock 6925 149 2545 minecraft:purple_stained_glass
/setblock 6929 149 2544 minecraft:orange_stained_glass
/setblock 6930 149 2544 minecraft:pink_stained_glass
/setblock 6927 150 2551 minecraft:blue_stained_glass
/setblock 6930 150 2551 minecraft:orange_stained_glass
/setblock 6925 150 2550 minecraft:green_stained_glass
/setblock 6932 150 2550 minecraft:orange_stained_glass
/setblock 6929 150 2548 minecraft:brown_stained_glass
/setblock 6931 150 2548 minecraft:cyan_stained_glass
/setblock 6932 150 2548 minecraft:orange_stained_glass
/setblock 6926 150 2545 minecraft:blue_stained_glass
/setblock 6929 150 2545 minecraft:orange_stained_glass
/setblock 6929 151 2550 minecraft:green_stained_glass
/setblock 6925 151 2548 minecraft:purple_stained_glass
/setblock 6929 151 2548 minecraft:brown_stained_glass
/setblock 6931 151 2548 minecraft:cyan_stained_glass
/setblock 6928 151 2546 minecraft:purple_stained_glass
/setblock 6930 151 2546 minecraft:green_stained_glass
/setblock 6926 151 2545 minecraft:red_stained_glass
/setblock 6930 151 2545 minecraft:green_stained_glass
/setblock 6928 152 2550 minecraft:purple_stained_glass
/setblock 6926 152 2549 minecraft:blue_stained_glass
/setblock 6926 152 2548 minecraft:purple_stained_glass
/setblock 6928 152 2548 minecraft:purple_stained_glass
/setblock 6929 152 2548 minecraft:brown_stained_glass
/setblock 6931 152 2548 minecraft:red_stained_glass
/setblock 6926 152 2547 minecraft:red_stained_glass
/setblock 6927 152 2547 minecraft:purple_stained_glass
"""
    grid = {}
    for line in RAW.strip().split('\n'):
        line = line.strip()
        if not line or not line.startswith('/setblock'):
            continue
        parts = line.split()
        x, y, z = int(parts[1]), int(parts[2]), int(parts[3])
        color_name = parts[4].replace('minecraft:', '').replace('_stained_glass', '')
        grid[pos_to_int((x, y, z))] = (COLOR_IDS[color_name], False)
    return State(grid, 0)


def find_formable_chains(state):
    """
    Find all same-color contiguous groups that could be chains after converting endpoints.
    Returns list of (axis_idx, positions, color_id, needed_conversions).
    """
    chains = []
    seen = set()
    
    for pi, (color, is_c) in state.grid.items():
        pos = int_to_pos(pi)
        
        for axis_idx in range(3):
            # Find start (walk back)
            start = list(pos)
            while True:
                p = list(start)
                p[axis_idx] -= 1
                tp = tuple(p)
                pi2 = pos_to_int(tp) if State.in_bounds(tp) else None
                if pi2 is None or pi2 not in state.grid:
                    break
                if state.grid[pi2][0] != color:
                    break
                start = p
            
            # Walk forward to collect
            group = []
            p = list(start)
            while True:
                tp = tuple(p)
                if not State.in_bounds(tp):
                    break
                pi2 = pos_to_int(tp)
                if pi2 not in state.grid or state.grid[pi2][0] != color:
                    break
                group.append(tp)
                p[axis_idx] += 1
            
            if len(group) < 2:
                continue
            
            key = (axis_idx, tuple(group))
            if key in seen:
                continue
            seen.add(key)
            
            # Determine needed conversions (endpoints must be concrete)
            first_v = state.grid[pos_to_int(group[0])]
            last_v = state.grid[pos_to_int(group[-1])]
            needed = []
            if not first_v[1]:
                needed.append(group[0])
            if not last_v[1]:
                needed.append(group[-1])
            
            chains.append((axis_idx, tuple(group), color, tuple(needed)))
    
    return chains


def compound_moves(state, conversion_limit=60):
    """
    Generate compound moves: (optionally convert endpoints) + slide N steps.
    Each compound move is represented as (new_state, description, conv_added).
    """
    moves = []
    chains = find_formable_chains(state)
    
    for axis_idx, positions, color, needed_conversions in chains:
        # Can we afford conversions?
        if state.conversions + len(needed_conversions) > conversion_limit:
            continue
        
        # Apply conversions
        s = state
        for p in needed_conversions:
            s = s.convert(p)
            if s is None:
                break
        if s is None:
            continue
        
        # Try sliding in each direction
        for direction in [-1, +1]:
            max_steps = max_slide(s, axis_idx, list(positions), direction)
            
            cur_state = s
            cur_positions = list(positions)
            
            for step in range(1, max_steps + 1):
                cur_state = slide_chain(cur_state, axis_idx, cur_positions, direction)
                cur_positions = [
                    tuple(p[i] + (direction if i == axis_idx else 0) for i in range(3))
                    for p in cur_positions
                ]
                
                axis_name = ['X', 'Y', 'Z'][axis_idx]
                dir_sym = '+' if direction > 0 else '-'
                color_name = ID_TO_COLOR[color]
                
                conv_desc = ""
                if needed_conversions:
                    conv_desc = f" [convert: {needed_conversions}]"
                
                start_str = f"{positions[0]}..{positions[-1]}"
                desc = f"{color_name} {axis_name}-chain {start_str} slide {dir_sym}{axis_name}×{step}{conv_desc}"
                
                moves.append((cur_state, desc, len(needed_conversions)))
    
    # Also: just slide already-existing chains
    # (these are a subset of the above where needed_conversions is empty)
    
    return moves


def display_state(state, y=None):
    """Display the state, optionally for a specific y slice."""
    COLOR_ABBREV = {0:'R', 1:'B', 2:'G', 3:'P', 4:'K', 5:'O', 6:'C', 7:'W'}
    
    ys = [y] if y is not None else range(Y_MIN, Y_MAX + 1)
    
    for y in ys:
        print(f"\nY={y}  X:", end="")
        for x in range(X_MIN, X_MAX + 1):
            print(f" {x%100:2d}", end="")
        print()
        
        for z in range(Z_MAX, Z_MIN - 1, -1):
            print(f"  Z={z%100:2d}:", end="")
            for x in range(X_MIN, X_MAX + 1):
                v = state.get((x, y, z))
                if v is None:
                    if (x, y, z) == GOAL_POS and y == 146:
                        print("  *", end="")
                    else:
                        print("  .", end="")
                else:
                    c = COLOR_ABBREV[v[0]]
                    # Uppercase for concrete, lowercase for glass
                    c = c if v[1] else c.lower()
                    if (x, y, z) == GOAL_POS and y == 146:
                        print(f" {c}*", end="")
                    else:
                        print(f"  {c}", end="")
            print()


if __name__ == '__main__':
    state = parse_initial()
    print(f"Initial state: {len(state.grid)} blocks")
    print(f"Is won: {state.is_won()}")
    
    moves = compound_moves(state)
    print(f"Compound moves available: {len(moves)}")
    for new_state, desc, n_conv in sorted(moves, key=lambda m: m[1])[:30]:
        print(f"  [{n_conv} conv] {desc}")
