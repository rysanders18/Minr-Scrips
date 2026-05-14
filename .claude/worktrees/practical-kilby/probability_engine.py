"""
Probability Engine for Disco Zoo Reinforcement Learning

Implements constraint satisfaction to compute per-animal probability heatmaps.
The heatmaps indicate the likelihood that each unrevealed tile belongs to a 
specific animal based on:
1. Known confirmed tiles for that animal
2. Known empty tiles
3. All possible valid placements of the animal's pattern

Usage:
    from probability_engine import ProbabilityEngine
    
    engine = ProbabilityEngine(biome='farm')
    
    # Update state as tiles are revealed
    engine.reveal_animal_tile(row=2, col=3, animal_idx=0)
    engine.reveal_empty_tile(row=1, col=1)
    
    # Get probability heatmaps (shape: (7, 5, 5))
    heatmaps = engine.compute_all_heatmaps()
"""

import numpy as np
from typing import List, Tuple, Set, Dict, Optional
from pattern_library import PATTERN_LIBRARY, get_indexed_patterns, get_all_valid_placements

# Type aliases
Tile = Tuple[int, int]
Pattern = List[Tile]
Placement = List[Tile]


class ProbabilityEngine:
    """
    Computes probability heatmaps for each animal using constraint satisfaction.
    
    The engine tracks:
    - Which tiles have been revealed
    - Which animal each revealed tile belongs to (if any)
    - Which animals have been completed
    
    For each animal, it filters valid placements based on constraints and
    computes the probability that each unrevealed tile belongs to that animal.
    """
    
    def __init__(self, biome: str = 'farm', grid_size: int = 5, num_animals: int = 7):
        """
        Initialize the probability engine.
        
        Args:
            biome: The biome to use for animal patterns
            grid_size: Size of the grid (default 5x5)
            num_animals: Number of animal slots (default 7)
        """
        self.biome = biome
        self.grid_size = grid_size
        self.num_animals = num_animals
        
        # Load patterns for this biome
        self.patterns: Dict[int, Pattern] = get_indexed_patterns(biome)
        
        # Precompute all valid placements for each pattern
        self.all_placements: Dict[int, List[Placement]] = {}
        for animal_idx, pattern in self.patterns.items():
            self.all_placements[animal_idx] = get_all_valid_placements(pattern, grid_size)
        
        # State tracking
        self.revealed: Set[Tile] = set()  # All revealed tiles
        self.empty_tiles: Set[Tile] = set()  # Tiles that are empty
        self.confirmed_tiles: Dict[int, Set[Tile]] = {i: set() for i in range(num_animals)}  # Tiles per animal
        self.completed_animals: Set[int] = set()  # Animals fully discovered
        
        # Cache for valid placements (recomputed on state change)
        self._valid_placements_cache: Optional[Dict[int, List[Placement]]] = None
    
    def reset(self):
        """Reset the engine to initial state."""
        self.revealed.clear()
        self.empty_tiles.clear()
        self.confirmed_tiles = {i: set() for i in range(self.num_animals)}
        self.completed_animals.clear()
        self._invalidate_cache()
    
    def _invalidate_cache(self):
        """Invalidate the placement cache."""
        self._valid_placements_cache = None
    
    def reveal_empty_tile(self, row: int, col: int):
        """
        Mark a tile as revealed and empty.
        
        Args:
            row: Row index (0-4)
            col: Column index (0-4)
        """
        tile = (row, col)
        self.revealed.add(tile)
        self.empty_tiles.add(tile)
        self._invalidate_cache()
    
    def reveal_animal_tile(self, row: int, col: int, animal_idx: int):
        """
        Mark a tile as revealed and belonging to an animal.
        
        Args:
            row: Row index (0-4)
            col: Column index (0-4)
            animal_idx: Index of the animal (0-6)
        """
        tile = (row, col)
        self.revealed.add(tile)
        self.confirmed_tiles[animal_idx].add(tile)
        self._invalidate_cache()
        
        # Check if animal is now complete
        pattern = self.patterns[animal_idx]
        if len(self.confirmed_tiles[animal_idx]) == len(pattern):
            self.completed_animals.add(animal_idx)
    
    def mark_animal_completed(self, animal_idx: int):
        """
        Explicitly mark an animal as completed.
        
        Args:
            animal_idx: Index of the animal (0-6)
        """
        self.completed_animals.add(animal_idx)
        self._invalidate_cache()
    
    def get_valid_placements(self, animal_idx: int) -> List[Placement]:
        """
        Get all valid placements for an animal given current constraints.
        
        A placement is valid if:
        1. It includes all confirmed tiles for this animal
        2. It does not include any empty tiles
        3. It does not overlap with confirmed tiles of OTHER animals
        
        Args:
            animal_idx: Index of the animal (0-6)
        
        Returns:
            List of valid placements (each placement is a list of tile coordinates)
        """
        # Use cache if available
        if self._valid_placements_cache is not None:
            return self._valid_placements_cache.get(animal_idx, [])
        
        # Need to compute
        self._compute_valid_placements_cache()
        return self._valid_placements_cache.get(animal_idx, [])
    
    def _compute_valid_placements_cache(self):
        """Compute and cache valid placements for all animals."""
        self._valid_placements_cache = {}
        
        # Collect all tiles that belong to OTHER animals (for each animal)
        for animal_idx in range(self.num_animals):
            if animal_idx in self.completed_animals:
                # Completed animals have no valid placements (already found)
                self._valid_placements_cache[animal_idx] = []
                continue
            
            confirmed = self.confirmed_tiles[animal_idx]
            
            # Tiles belonging to other animals
            other_animal_tiles = set()
            for other_idx, tiles in self.confirmed_tiles.items():
                if other_idx != animal_idx:
                    other_animal_tiles.update(tiles)
            
            valid = []
            for placement in self.all_placements[animal_idx]:
                placement_set = set(placement)
                
                # Must include all confirmed tiles
                if not confirmed.issubset(placement_set):
                    continue
                
                # Must not include any empty tiles
                if placement_set & self.empty_tiles:
                    continue
                
                # Must not include tiles from other animals
                if placement_set & other_animal_tiles:
                    continue
                
                valid.append(placement)
            
            self._valid_placements_cache[animal_idx] = valid
    
    def compute_heatmap(self, animal_idx: int) -> np.ndarray:
        """
        Compute probability heatmap for a single animal.
        
        For each tile, the probability is the fraction of valid placements
        that include that tile.
        
        Args:
            animal_idx: Index of the animal (0-6)
        
        Returns:
            (5, 5) numpy array with probabilities 0.0-1.0
        """
        heatmap = np.zeros((self.grid_size, self.grid_size), dtype=np.float32)
        
        # Completed animals have zero probability everywhere
        if animal_idx in self.completed_animals:
            return heatmap
        
        valid_placements = self.get_valid_placements(animal_idx)
        
        if not valid_placements:
            return heatmap
        
        num_placements = len(valid_placements)
        
        for row in range(self.grid_size):
            for col in range(self.grid_size):
                tile = (row, col)
                
                if tile in self.revealed:
                    # Revealed tiles: 1.0 if belongs to this animal, 0.0 otherwise
                    if tile in self.confirmed_tiles[animal_idx]:
                        heatmap[row, col] = 1.0
                    else:
                        heatmap[row, col] = 0.0
                else:
                    # Unrevealed tiles: count how many placements include this tile
                    count = sum(1 for p in valid_placements if tile in p)
                    heatmap[row, col] = count / num_placements
        
        return heatmap
    
    def compute_all_heatmaps(self) -> np.ndarray:
        """
        Compute probability heatmaps for all animals.
        
        Returns:
            (7, 5, 5) numpy array where [i] is the heatmap for animal i
        """
        heatmaps = np.zeros((self.num_animals, self.grid_size, self.grid_size), dtype=np.float32)
        
        for animal_idx in range(self.num_animals):
            heatmaps[animal_idx] = self.compute_heatmap(animal_idx)
        
        return heatmaps
    
    def get_confirmed_channels(self) -> np.ndarray:
        """
        Get binary channels indicating confirmed tiles for each animal.
        
        Returns:
            (7, 5, 5) numpy array where [i] has 1.0 at confirmed tile positions
        """
        channels = np.zeros((self.num_animals, self.grid_size, self.grid_size), dtype=np.float32)
        
        for animal_idx in range(self.num_animals):
            for row, col in self.confirmed_tiles[animal_idx]:
                channels[animal_idx, row, col] = 1.0
        
        return channels
    
    def get_state_channels(self) -> np.ndarray:
        """
        Get full state representation as 14 channels.
        
        Channels 0-6: Confirmed tiles for each animal (binary)
        Channels 7-13: Probability heatmaps for each animal (0.0-1.0)
        
        Returns:
            (5, 5, 14) numpy array (HWC format for neural networks)
        """
        confirmed = self.get_confirmed_channels()  # (7, 5, 5)
        heatmaps = self.compute_all_heatmaps()     # (7, 5, 5)
        
        # Stack along first axis then transpose to HWC format
        stacked = np.concatenate([confirmed, heatmaps], axis=0)  # (14, 5, 5)
        return np.transpose(stacked, (1, 2, 0))  # (5, 5, 14)
    
    def get_best_tile_for_animal(self, animal_idx: int) -> Optional[Tile]:
        """
        Get the unrevealed tile with highest probability for an animal.
        
        Args:
            animal_idx: Index of the animal (0-6)
        
        Returns:
            (row, col) tuple or None if no good options
        """
        heatmap = self.compute_heatmap(animal_idx)
        
        best_prob = 0.0
        best_tile = None
        
        for row in range(self.grid_size):
            for col in range(self.grid_size):
                tile = (row, col)
                if tile not in self.revealed and heatmap[row, col] > best_prob:
                    best_prob = heatmap[row, col]
                    best_tile = tile
        
        return best_tile
    
    def get_best_tile_overall(self) -> Optional[Tile]:
        """
        Get the unrevealed tile with highest probability across all animals.
        
        Returns:
            (row, col) tuple or None if no options
        """
        all_heatmaps = self.compute_all_heatmaps()
        
        # Sum probabilities across all animals
        combined = np.max(all_heatmaps, axis=0)  # (5, 5)
        
        best_prob = 0.0
        best_tile = None
        
        for row in range(self.grid_size):
            for col in range(self.grid_size):
                tile = (row, col)
                if tile not in self.revealed and combined[row, col] > best_prob:
                    best_prob = combined[row, col]
                    best_tile = tile
        
        return best_tile
    
    def get_completion_progress(self) -> Dict[int, Tuple[int, int]]:
        """
        Get progress toward completing each animal.
        
        Returns:
            Dict mapping animal_idx to (found_tiles, total_tiles)
        """
        progress = {}
        for animal_idx in range(self.num_animals):
            found = len(self.confirmed_tiles[animal_idx])
            total = len(self.patterns[animal_idx])
            progress[animal_idx] = (found, total)
        return progress


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def create_engine_from_grid_state(
    biome: str,
    confirmed_channels: np.ndarray,
    revealed_mask: np.ndarray
) -> ProbabilityEngine:
    """
    Create a probability engine from existing grid state.
    
    Args:
        biome: Biome name
        confirmed_channels: (7, 5, 5) array of confirmed tiles per animal
        revealed_mask: (5, 5) boolean array of revealed tiles
    
    Returns:
        Initialized ProbabilityEngine
    """
    engine = ProbabilityEngine(biome=biome)
    
    for row in range(5):
        for col in range(5):
            if revealed_mask[row, col]:
                # Find which animal this tile belongs to (if any)
                animal_found = False
                for animal_idx in range(7):
                    if confirmed_channels[animal_idx, row, col] > 0:
                        engine.reveal_animal_tile(row, col, animal_idx)
                        animal_found = True
                        break
                
                if not animal_found:
                    engine.reveal_empty_tile(row, col)
    
    return engine


# =============================================================================
# MAIN (Testing)
# =============================================================================

if __name__ == "__main__":
    print("Probability Engine Test")
    print("=" * 50)
    
    # Create engine for farm biome
    engine = ProbabilityEngine(biome='farm')
    
    print("\nInitial state (all unrevealed):")
    heatmaps = engine.compute_all_heatmaps()
    print(f"Heatmap shape: {heatmaps.shape}")
    print(f"Animal 0 heatmap sum: {heatmaps[0].sum():.2f}")
    
    # Simulate finding a tile
    print("\n--- Reveal animal tile at (2, 2) for Animal 0 ---")
    engine.reveal_animal_tile(2, 2, 0)
    
    heatmaps = engine.compute_all_heatmaps()
    print(f"Animal 0 heatmap after reveal:")
    print(heatmaps[0])
    
    # Simulate finding an empty tile
    print("\n--- Reveal empty tile at (0, 0) ---")
    engine.reveal_empty_tile(0, 0)
    
    heatmaps = engine.compute_all_heatmaps()
    print(f"Animal 0 heatmap after empty reveal:")
    print(heatmaps[0])
    
    # Get best tile
    best = engine.get_best_tile_for_animal(0)
    print(f"\nBest tile for Animal 0: {best}")
    
    # Full state channels
    state = engine.get_state_channels()
    print(f"\nFull state shape: {state.shape}")
    print(f"State dtype: {state.dtype}")
