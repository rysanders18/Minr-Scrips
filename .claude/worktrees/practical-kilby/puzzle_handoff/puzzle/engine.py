#!/usr/bin/env python3
"""
Minecraft 3D Sliding Block Puzzle - Game Engine
Handles state representation, chain detection, move generation, and move execution.
"""

from copy import deepcopy
from collections import defaultdict

# Grid bounds
X_MIN, X_MAX = 6925, 6932
Y_MIN, Y_MAX = 145, 152
Z_MIN, Z_MAX = 2544, 2551

SEA_LANTERN = (6924, 146, 2546)
GOAL_POS = (6925, 146, 2546)

GLASS = 'glass'
CONCRETE = 'concrete'


class Block:
    __slots__ = ['color', 'material']
    def __init__(self, color, material=GLASS):
        self.color = color
        self.material = material
    
    def __repr__(self):
        return f"{self.color}({'C' if self.material == CONCRETE else 'G'})"


class PuzzleState:
    def __init__(self):
        # grid: dict of (x,y,z) -> Block
        self.grid = {}
        self.conversions_used = 0
        self.max_conversions = 60
    
    def copy(self):
        new = PuzzleState()
        new.grid = {pos: Block(b.color, b.material) for pos, b in self.grid.items()}
        new.conversions_used = self.conversions_used
        new.max_conversions = self.max_conversions
        return new
    
    def in_bounds(self, x, y, z):
        return (X_MIN <= x <= X_MAX and Y_MIN <= y <= Y_MAX and Z_MIN <= z <= Z_MAX)
    
    def is_empty(self, pos):
        return pos not in self.grid
    
    def is_won(self):
        """Check if red concrete is adjacent to the sea lantern."""
        for dx, dy, dz in [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)]:
            adj = (SEA_LANTERN[0]+dx, SEA_LANTERN[1]+dy, SEA_LANTERN[2]+dz)
            if adj in self.grid:
                b = self.grid[adj]
                if b.color == 'red' and b.material == CONCRETE:
                    return True
        return False
    
    def find_chain(self, pos):
        """
        Given a position with a concrete block, find the chain it belongs to.
        A chain is: concrete endpoint - [same-color glass]* - concrete endpoint, all collinear.
        Returns (axis, direction, positions_list) or None.
        May return multiple chains if the block is a shared endpoint.
        """
        if pos not in self.grid or self.grid[pos].material != CONCRETE:
            return []
        
        block = self.grid[pos]
        color = block.color
        chains = []
        
        # Check each axis
        for axis_idx, axis_name in enumerate(['X', 'Y', 'Z']):
            for direction in [+1, -1]:
                # Walk from pos in the given direction
                positions = [pos]
                p = list(pos)
                
                found_other_concrete = False
                while True:
                    p[axis_idx] += direction
                    tp = tuple(p)
                    
                    if not self.in_bounds(*tp):
                        break
                    if tp not in self.grid:
                        break
                    
                    other = self.grid[tp]
                    if other.color != color:
                        break
                    
                    positions.append(tp)
                    
                    if other.material == CONCRETE:
                        found_other_concrete = True
                        break
                    # else it's glass of same color, continue
                
                if found_other_concrete and len(positions) >= 2:
                    # We have a valid chain from pos to the other concrete endpoint
                    chains.append((axis_idx, positions))
        
        return chains
    
    def find_all_chains(self):
        """Find all valid chains in the current state."""
        seen_chain_sets = set()
        all_chains = []
        
        for pos, block in self.grid.items():
            if block.material != CONCRETE:
                continue
            for axis_idx, positions in self.find_chain(pos):
                # Normalize: sort positions to avoid duplicates
                key = (axis_idx, tuple(sorted(positions)))
                if key not in seen_chain_sets:
                    seen_chain_sets.add(key)
                    all_chains.append((axis_idx, positions))
        
        return all_chains
    
    def can_move_chain(self, axis_idx, positions, direction):
        """
        Check if a chain can move 1 step in the given direction along its axis.
        direction is +1 or -1.
        """
        for p in positions:
            new_p = list(p)
            new_p[axis_idx] += direction
            new_p = tuple(new_p)
            
            if not self.in_bounds(*new_p):
                return False
            
            # The new position must be empty OR already part of this chain
            if new_p not in self.grid:
                continue
            if new_p in positions:
                continue
            # Occupied by something else
            return False
        
        return True
    
    def move_chain(self, axis_idx, positions, direction):
        """
        Move a chain 1 step. Returns new state.
        Assumes the move is valid.
        """
        new_state = self.copy()
        
        # Collect blocks to move
        moving_blocks = {}
        for p in positions:
            moving_blocks[p] = new_state.grid.pop(p)
        
        # Place them in new positions
        for p, block in moving_blocks.items():
            new_p = list(p)
            new_p[axis_idx] += direction
            new_p = tuple(new_p)
            new_state.grid[new_p] = block
        
        return new_state
    
    def click_endpoint(self, pos, direction):
        """
        Click a concrete endpoint to move its chain(s) in the specified direction.
        direction is +1 or -1 along the chain's axis.
        
        Returns (new_state, chains_moved) or None if no valid moves.
        """
        chains = self.find_chain(pos)
        if not chains:
            return None
        
        state = self
        chains_moved = []
        
        for axis_idx, positions in chains:
            # The direction must be along this chain's axis
            # Check which direction from the clicked endpoint
            # The clicked pos should be at one end of the chain
            sorted_pos = sorted(positions, key=lambda p: p[axis_idx])
            
            if pos == sorted_pos[0]:
                # Clicked the low end - can move in -direction (further low) 
                move_dir = -1
            elif pos == sorted_pos[-1]:
                # Clicked the high end - can move in +direction
                move_dir = +1
            else:
                continue  # Not an endpoint of this chain
            
            # User specifies direction by clicking the end from the direction they want to move
            # "clicking the end of the chain from the direction we want it to move"
            # So clicking the low end means we want to move it in the -direction (lower)
            # Wait, re-reading: "we can control which way we want the chain to move by 
            # clicking the end of the chain from the direction we want it to move"
            # This means: click the end that is in the direction you want to move.
            # Click top end → move up. Click bottom end → move down.
            # Actually this means: clicking the end that faces the direction of movement.
            # Click the +X end → move in +X direction.
            # But that doesn't make sense physically - if you click the top, you push down?
            
            # Let me re-read: "clicking the end of the chain from the direction we want it to move"
            # I think: click the end FROM WHICH direction you want to move.
            # Click the -X end → chain moves in -X direction
            # That way you're "pulling" it toward where you clicked.
            
            # Actually: in Rush Hour style, clicking one end means move toward that end.
            # So clicking the low end = move in -direction, clicking high end = move in +direction.
            
            if state.can_move_chain(axis_idx, positions, move_dir):
                state = state.move_chain(axis_idx, positions, move_dir)
                chains_moved.append((axis_idx, positions, move_dir))
        
        if not chains_moved:
            return None
        
        return state, chains_moved
    
    def get_all_moves(self):
        """
        Generate all possible moves from current state.
        Returns list of (action_type, action_params, new_state, description)
        """
        moves = []
        
        # Type 1: Convert a glass block to concrete
        if self.conversions_used < self.max_conversions:
            for pos, block in self.grid.items():
                if block.material == GLASS:
                    new_state = self.copy()
                    new_state.grid[pos].material = CONCRETE
                    new_state.conversions_used += 1
                    moves.append(('convert', pos, new_state, 
                                  f"Convert {block.color} at {pos} to concrete"))
        
        # Type 2: Click a chain endpoint
        # First find all concrete blocks that are chain endpoints
        for pos, block in self.grid.items():
            if block.material != CONCRETE:
                continue
            
            chains = self.find_chain(pos)
            for axis_idx, positions in chains:
                sorted_pos = sorted(positions, key=lambda p: p[axis_idx])
                
                # Try clicking as low endpoint (move in -direction)
                if pos == sorted_pos[0]:
                    move_dir = -1
                    if self.can_move_chain(axis_idx, positions, move_dir):
                        new_state = self.move_chain(axis_idx, positions, move_dir)
                        axis_name = ['X', 'Y', 'Z'][axis_idx]
                        moves.append(('click', (pos, axis_idx, move_dir), new_state,
                                      f"Click {block.color} at {pos} → move {axis_name}{move_dir}"))
                
                # Try clicking as high endpoint (move in +direction)
                if pos == sorted_pos[-1]:
                    move_dir = +1
                    if self.can_move_chain(axis_idx, positions, move_dir):
                        new_state = self.move_chain(axis_idx, positions, move_dir)
                        axis_name = ['X', 'Y', 'Z'][axis_idx]
                        moves.append(('click', (pos, axis_idx, move_dir), new_state,
                                      f"Click {block.color} at {pos} → move {axis_name}{move_dir}"))
        
        return moves
    
    def get_chain_moves_only(self):
        """Get only chain movement moves (not conversions)."""
        moves = []
        for pos, block in self.grid.items():
            if block.material != CONCRETE:
                continue
            chains = self.find_chain(pos)
            for axis_idx, positions in chains:
                sorted_pos = sorted(positions, key=lambda p: p[axis_idx])
                if pos == sorted_pos[0]:
                    move_dir = -1
                    if self.can_move_chain(axis_idx, positions, move_dir):
                        new_state = self.move_chain(axis_idx, positions, move_dir)
                        axis_name = ['X', 'Y', 'Z'][axis_idx]
                        moves.append(('click', (pos, axis_idx, move_dir), new_state,
                                      f"Click {block.color} at {pos} → move {axis_name}{move_dir}"))
                if pos == sorted_pos[-1]:
                    move_dir = +1
                    if self.can_move_chain(axis_idx, positions, move_dir):
                        new_state = self.move_chain(axis_idx, positions, move_dir)
                        axis_name = ['X', 'Y', 'Z'][axis_idx]
                        moves.append(('click', (pos, axis_idx, move_dir), new_state,
                                      f"Click {block.color} at {pos} → move {axis_name}{move_dir}"))
        return moves
    
    def display_layer(self, y):
        """Display a horizontal slice at Y level."""
        COLOR_ABBREV = {
            'red': 'R', 'blue': 'B', 'green': 'G', 'purple': 'P',
            'pink': 'K', 'orange': 'O', 'cyan': 'C', 'brown': 'W',
        }
        lines = []
        lines.append(f"Y={y}  X→")
        header = "Z↓  "
        for x in range(X_MIN, X_MAX + 1):
            header += f" {x%100:2d}"
        lines.append(header)
        
        for z in range(Z_MAX, Z_MIN - 1, -1):
            row = f"{z%100:2d} |"
            for x in range(X_MIN, X_MAX + 1):
                pos = (x, y, z)
                if pos in self.grid:
                    b = self.grid[pos]
                    c = COLOR_ABBREV.get(b.color, '?')
                    if b.material == CONCRETE:
                        c = c.lower()  # lowercase = concrete
                    row += f"  {c}"
                else:
                    row += "  ."
            lines.append(row)
        return '\n'.join(lines)
    
    def state_hash(self):
        """Create a hashable representation of the state."""
        items = []
        for pos in sorted(self.grid.keys()):
            b = self.grid[pos]
            items.append((pos, b.color, b.material))
        return (tuple(items), self.conversions_used)


def parse_initial_state():
    """Parse the setblock commands into initial state."""
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
    
    state = PuzzleState()
    for line in RAW.strip().split('\n'):
        line = line.strip()
        if not line or not line.startswith('/setblock'):
            continue
        parts = line.split()
        x, y, z = int(parts[1]), int(parts[2]), int(parts[3])
        block_type = parts[4].replace('minecraft:', '').replace('_stained_glass', '')
        state.grid[(x, y, z)] = Block(block_type, GLASS)
    
    return state


def test_engine():
    """Test the game engine with basic operations."""
    state = parse_initial_state()
    print(f"Initial state: {len(state.grid)} blocks")
    print(f"Won: {state.is_won()}")
    
    # Test: find chains (should be none since all glass)
    chains = state.find_all_chains()
    print(f"Chains (all glass): {len(chains)}")
    
    # Test: convert brown column endpoints to concrete and find chain
    # Brown at y=148,149,150,151,152 x=6929 z=2548
    test_state = state.copy()
    test_state.grid[(6929, 148, 2548)].material = CONCRETE
    test_state.grid[(6929, 152, 2548)].material = CONCRETE
    test_state.conversions_used = 2
    
    chains = test_state.find_all_chains()
    print(f"\nAfter converting brown endpoints:")
    print(f"Chains found: {len(chains)}")
    for axis_idx, positions in chains:
        axis = ['X', 'Y', 'Z'][axis_idx]
        colors = [test_state.grid[p].color for p in positions]
        mats = [test_state.grid[p].material for p in positions]
        print(f"  {axis}-axis: {positions}")
        print(f"    Colors: {colors}")
        print(f"    Materials: {mats}")
    
    # Test: try to move the brown chain
    if chains:
        axis_idx, positions = chains[0]
        for d in [-1, +1]:
            can = test_state.can_move_chain(axis_idx, positions, d)
            dir_name = '+' if d > 0 else '-'
            axis = ['X', 'Y', 'Z'][axis_idx]
            print(f"  Can move {dir_name}{axis}: {can}")
            if can:
                new_state = test_state.move_chain(axis_idx, positions, d)
                # Show new positions
                new_chain_blocks = []
                for pos, b in new_state.grid.items():
                    if b.color == 'brown':
                        new_chain_blocks.append(pos)
                print(f"    New brown positions: {sorted(new_chain_blocks)}")
    
    # Count available moves from initial state
    print(f"\nConversion moves available: {sum(1 for b in state.grid.values() if b.material == GLASS)}")
    print(f"Chain moves available: 0 (no chains yet)")


if __name__ == '__main__':
    test_engine()
