"""
Pattern Library for Disco Zoo Reinforcement Learning

Contains animal patterns for each biome. Patterns are defined as lists of 
(row, col) offsets from the pattern's anchor point (top-left of bounding box).

Usage:
    from pattern_library import PATTERN_LIBRARY, get_all_valid_placements
    
    # Get patterns for a biome
    patterns = PATTERN_LIBRARY['farm']
    pig_pattern = patterns['pig']  # [(0,0), (0,1), (1,0), (1,1)]
    
    # Get all valid placements of a pattern on the grid
    placements = get_all_valid_placements(pig_pattern)
"""

from typing import List, Tuple, Dict

# Type aliases
Pattern = List[Tuple[int, int]]  # List of (row, col) offsets
BiomePatterns = Dict[str, Pattern]  # Animal name -> pattern

# =============================================================================
# PATTERN LIBRARY
# =============================================================================

PATTERN_LIBRARY: Dict[str, BiomePatterns] = {
    'farm': {
        'pig':      [(0, 0), (0, 1), (1, 0), (1, 1)],  # 2x2 square
        'sheep':    [(0, 0), (0, 1), (0, 2), (0, 3)],  # 1x4 horizontal
        'rabbit':   [(0, 0), (1, 0), (2, 0), (3, 0)],  # 4x1 vertical
        'horse':    [(0, 0), (1, 0), (2, 0)],          # 3x1 vertical
        'cow':      [(0, 0), (0, 1), (0, 2)],          # 1x3 horizontal
        'unicorn':  [(0, 1), (0, 2), (1, 0)],          # L-shape
        'chicken':  [(0, 0), (1, 1)],                  # 2-tile diagonal
    },
    
    'outback': {
        'kangaroo':  [(0, 0), (1, 1), (2, 2), (3, 3)],  # 4-tile diagonal
        'platypus':  [(0, 0), (0, 1), (1, 0), (1, 1)],  # 2x2 square
        'crocodile': [(0, 0), (0, 1), (0, 2), (0, 3)],  # 1x4 horizontal
        'koala':     [(0, 0), (0, 1), (1, 1)],          # Corner shape
        'cockatoo':  [(0, 0), (1, 1), (2, 1)],          # Offset vertical
        'tiddalik':  [(0, 1), (1, 0), (1, 2)],          # V-shape
        'echidna':   [(0, 2), (1, 0), (1, 1)],          # T-like shape
    },
    
    'savanna': {
        'zebra':     [(0, 0), (0, 1), (0, 2), (0, 3)],  # 1x4 horizontal
        'hippo':     [(0, 0), (0, 1), (1, 0), (1, 1)],  # 2x2 square
        'giraffe':   [(0, 0), (1, 0), (2, 0), (3, 0)],  # 4x1 vertical
        'lion':      [(0, 0), (0, 1), (0, 2)],          # 1x3 horizontal
        'elephant':  [(0, 0), (1, 0), (2, 0)],          # 3x1 vertical
        'gryphon':   [(0, 0), (0, 1), (1, 1), (1, 2)],  # Z-shape
        'vulture':   [(0, 1), (1, 0), (1, 1), (1, 2)],  # T-shape
    },
    
    'northern': {
        'beaver':    [(0, 0), (0, 1)],                  # 1x2 horizontal
        'moose':     [(0, 0), (1, 0), (2, 0)],          # 3x1 vertical
        'fox':       [(0, 0), (0, 1), (1, 1)],          # L-shape
        'bear':      [(0, 0), (0, 1), (1, 0), (1, 1)],  # 2x2 square
        'skunk':     [(0, 0), (1, 0)],                  # 2x1 vertical
        'sasquatch': [(0, 0), (0, 1), (0, 2)],          # 1x3 horizontal
        'wolf':      [(0, 0), (1, 1), (2, 2)],          # 3-tile diagonal
    },
    
    'polar': {
        'penguin':   [(0, 0), (1, 0)],                  # 2x1 vertical
        'seal':      [(0, 0), (0, 1), (0, 2)],          # 1x3 horizontal
        'walrus':    [(0, 0), (0, 1), (1, 0), (1, 1)],  # 2x2 square
        'polar_bear': [(0, 0), (1, 0), (2, 0)],         # 3x1 vertical
        'musk_ox':   [(0, 0), (0, 1), (1, 1)],          # Corner shape
        'yeti':      [(0, 0), (0, 1), (0, 2), (0, 3)],  # 1x4 horizontal
        'mammoth':   [(0, 0), (1, 0), (2, 0), (3, 0)],  # 4x1 vertical
    },
    
    'jungle': {
        'toucan':    [(0, 0), (0, 1)],                  # 1x2 horizontal
        'gorilla':   [(0, 0), (0, 1), (1, 0), (1, 1)],  # 2x2 square
        'panda':     [(0, 0), (1, 0), (2, 0)],          # 3x1 vertical
        'tiger':     [(0, 0), (0, 1), (0, 2)],          # 1x3 horizontal
        'snake':     [(0, 0), (0, 1), (0, 2), (0, 3)],  # 1x4 horizontal
        'phoenix':   [(0, 1), (1, 0), (1, 1), (1, 2)],  # T-shape
        'monkey':    [(0, 0), (1, 1), (2, 0)],          # Zigzag
    },
    
    'jurassic': {
        'raptor':      [(0, 0), (0, 1), (1, 1)],          # L-shape
        'triceratops': [(0, 0), (0, 1), (0, 2)],          # 1x3 horizontal
        'stegosaurus': [(0, 0), (1, 0), (2, 0)],          # 3x1 vertical
        'brontosaurus': [(0, 0), (1, 0), (2, 0), (3, 0)], # 4x1 vertical
        'pterodactyl': [(0, 0), (0, 1), (0, 2), (0, 3)],  # 1x4 horizontal
        'trex':        [(0, 0), (0, 1), (1, 0), (1, 1)],  # 2x2 square
        'dragon':      [(0, 0), (1, 1), (2, 2), (3, 3)],  # 4-tile diagonal
    },
    
    'ice_age': {
        'woolly_rhino':   [(0, 0), (0, 1), (0, 2)],          # 1x3 horizontal
        'saber_tooth':    [(0, 0), (1, 0), (2, 0)],          # 3x1 vertical
        'giant_sloth':    [(0, 0), (0, 1), (1, 0), (1, 1)],  # 2x2 square
        'dire_wolf':      [(0, 0), (1, 1), (2, 2)],          # 3-tile diagonal
        'giant_armadillo': [(0, 0), (0, 1)],                 # 1x2 horizontal
        'cave_bear':      [(0, 0), (1, 0), (2, 0), (3, 0)],  # 4x1 vertical
        'snow_queen':     [(0, 0), (0, 1), (0, 2), (0, 3)],  # 1x4 horizontal
    },
}

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_all_valid_placements(pattern: Pattern, grid_size: int = 5) -> List[List[Tuple[int, int]]]:
    """
    Return all valid positions where a pattern can be placed on the grid.
    
    Args:
        pattern: List of (row, col) offsets defining the animal shape
        grid_size: Size of the grid (default 5x5)
    
    Returns:
        List of placements, where each placement is a list of (row, col) tile coordinates
    """
    placements = []
    
    for anchor_row in range(grid_size):
        for anchor_col in range(grid_size):
            # Compute absolute positions for this anchor
            tiles = [(anchor_row + dr, anchor_col + dc) for dr, dc in pattern]
            
            # Check if all tiles are within bounds
            if all(0 <= r < grid_size and 0 <= c < grid_size for r, c in tiles):
                placements.append(tiles)
    
    return placements


def get_pattern_bounds(pattern: Pattern) -> Tuple[int, int]:
    """
    Get the bounding box dimensions of a pattern.
    
    Args:
        pattern: List of (row, col) offsets
    
    Returns:
        (height, width) of the pattern's bounding box
    """
    if not pattern:
        return (0, 0)
    
    rows = [r for r, c in pattern]
    cols = [c for r, c in pattern]
    
    height = max(rows) - min(rows) + 1
    width = max(cols) - min(cols) + 1
    
    return (height, width)


def get_biome_animal_names(biome: str) -> List[str]:
    """
    Get list of animal names for a biome.
    
    Args:
        biome: Name of the biome
    
    Returns:
        List of animal names in order
    """
    if biome not in PATTERN_LIBRARY:
        raise ValueError(f"Unknown biome: {biome}. Available: {list(PATTERN_LIBRARY.keys())}")
    
    return list(PATTERN_LIBRARY[biome].keys())


def get_indexed_patterns(biome: str) -> Dict[int, Pattern]:
    """
    Get patterns indexed by animal slot (0-6) instead of name.
    
    This is the format used by the environment for biome-agnostic processing.
    
    Args:
        biome: Name of the biome
    
    Returns:
        Dictionary mapping animal index (0-6) to pattern
    """
    if biome not in PATTERN_LIBRARY:
        raise ValueError(f"Unknown biome: {biome}. Available: {list(PATTERN_LIBRARY.keys())}")
    
    biome_patterns = PATTERN_LIBRARY[biome]
    return {i: pattern for i, pattern in enumerate(biome_patterns.values())}


def get_pattern_tile_count(pattern: Pattern) -> int:
    """Get the number of tiles in a pattern."""
    return len(pattern)


def validate_pattern_library():
    """
    Validate that all patterns in the library are valid.
    
    Checks:
    - Each biome has exactly 7 animals
    - All patterns have at least 2 tiles
    - All patterns fit within a 5x5 grid
    - No duplicate tiles within a pattern
    
    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []
    
    for biome, animals in PATTERN_LIBRARY.items():
        # Check animal count
        if len(animals) != 7:
            errors.append(f"{biome}: Expected 7 animals, got {len(animals)}")
        
        for animal, pattern in animals.items():
            # Check minimum tiles
            if len(pattern) < 2:
                errors.append(f"{biome}/{animal}: Pattern has fewer than 2 tiles")
            
            # Check for duplicates
            if len(pattern) != len(set(pattern)):
                errors.append(f"{biome}/{animal}: Pattern has duplicate tiles")
            
            # Check bounds
            height, width = get_pattern_bounds(pattern)
            if height > 5 or width > 5:
                errors.append(f"{biome}/{animal}: Pattern exceeds 5x5 grid ({height}x{width})")
            
            # Check that pattern can be placed at least once
            placements = get_all_valid_placements(pattern)
            if not placements:
                errors.append(f"{biome}/{animal}: Pattern cannot be placed on 5x5 grid")
    
    return errors


# =============================================================================
# MAIN (Validation)
# =============================================================================

if __name__ == "__main__":
    print("Pattern Library Validation")
    print("=" * 50)
    
    errors = validate_pattern_library()
    
    if errors:
        print("ERRORS FOUND:")
        for error in errors:
            print(f"  - {error}")
    else:
        print("✅ All patterns valid!")
    
    print("\nBiome Summary:")
    for biome, animals in PATTERN_LIBRARY.items():
        total_tiles = sum(len(p) for p in animals.values())
        print(f"  {biome}: {len(animals)} animals, {total_tiles} total tiles")
        
        for i, (animal, pattern) in enumerate(animals.items()):
            placements = get_all_valid_placements(pattern)
            print(f"    [{i}] {animal}: {len(pattern)} tiles, {len(placements)} valid placements")
