"""
Disco Zoo Reinforcement Learning Environment

A Gymnasium-compatible environment for training RL agents to play Disco Zoo's
rescue puzzle game. The agent must efficiently reveal tiles on a 5x5 grid to
discover hidden animals before running out of moves.

State Space:
    - Grid: (5, 5, 14) array with 7 confirmed + 7 probability channels
    - Scalars: (9,) array with moves_remaining + 7 completion flags + total_found

Action Space:
    - Discrete(25): Select tile at position (action // 5, action % 5)
    - Invalid actions (already revealed) are masked

Rewards:
    - +10.0 for completing an animal (all pattern tiles revealed)
    - +0.1 for revealing an animal tile (partial discovery)
    - -1.0 for attempting to reveal an already-revealed tile
    - 0.0 for revealing an empty tile

Usage:
    import gymnasium as gym
    from discoZoo import DiscoZooEnv
    
    env = DiscoZooEnv(biome='farm', num_animals=3, max_moves=15)
    obs, info = env.reset()
    
    while True:
        action = env.action_space.sample()  # Random action
        obs, reward, terminated, truncated, info = env.step(action)
        if terminated or truncated:
            break
"""

import numpy as np
import gymnasium as gym
from gymnasium import spaces
from typing import Tuple, List, Dict, Optional, Set, Any
import random

from pattern_library import PATTERN_LIBRARY, get_indexed_patterns, get_all_valid_placements
from probability_engine import ProbabilityEngine


class DiscoZooEnv(gym.Env):
    """
    Disco Zoo Rescue Puzzle Environment.
    
    The agent must reveal tiles on a 5x5 grid to discover hidden animals.
    Each animal occupies a fixed geometric pattern of 2-4 tiles.
    The goal is to complete as many animals as possible before running out of moves.
    """
    
    metadata = {"render_modes": ["human", "ansi"], "render_fps": 4}
    
    def __init__(
        self,
        biome: str = 'farm',
        num_animals: int = 3,
        max_moves: int = 10,
        render_mode: Optional[str] = None,
        reward_animal_complete: float = 10.0,
        reward_animal_tile: float = 0.1,
        reward_empty_tile: float = 0.0,
        penalty_invalid_action: float = -1.0
    ):
        """
        Initialize the Disco Zoo environment.
        
        Args:
            biome: Which biome's animal patterns to use (e.g., 'farm', 'outback')
            num_animals: Number of animals to place on the grid (1-7)
            max_moves: Maximum number of tile reveals allowed per episode
            render_mode: How to render ('human', 'ansi', or None)
            reward_animal_complete: Reward for completing an animal (+10.0)
            reward_animal_tile: Reward for finding an animal tile (+0.1)
            reward_empty_tile: Reward for revealing an empty tile (0.0)
            penalty_invalid_action: Penalty for re-revealing a tile (-1.0)
        """
        super().__init__()
        
        assert biome in PATTERN_LIBRARY, f"Unknown biome: {biome}"
        assert 1 <= num_animals <= 3, "num_animals must be between 1 and 3 (game maximum)"
        assert max_moves >= 1, "max_moves must be at least 1"
        
        self.biome = biome
        self.num_animals = num_animals
        self.max_moves = max_moves
        self.render_mode = render_mode
        self.grid_size = 5
        self.num_channels = 14  # 7 confirmed + 7 probability
        self.num_scalars = 9    # 1 moves + 7 completion flags + 1 total
        
        # Reward configuration
        self.reward_animal_complete = reward_animal_complete
        self.reward_animal_tile = reward_animal_tile
        self.reward_empty_tile = reward_empty_tile
        self.penalty_invalid_action = penalty_invalid_action
        
        # Load patterns for biome
        self.patterns = get_indexed_patterns(biome)
        self.animal_names = list(PATTERN_LIBRARY[biome].keys())
        
        # Define observation space
        self.observation_space = spaces.Dict({
            'grid': spaces.Box(
                low=0.0, high=1.0,
                shape=(self.grid_size, self.grid_size, self.num_channels),
                dtype=np.float32
            ),
            'scalars': spaces.Box(
                low=0.0, high=1.0,
                shape=(self.num_scalars,),
                dtype=np.float32
            )
        })
        
        # Define action space (25 tiles = 5x5 grid)
        self.action_space = spaces.Discrete(self.grid_size * self.grid_size)
        
        # Initialize state variables (set in reset())
        self._reset_state_vars()
    
    def _reset_state_vars(self):
        """Reset internal state tracking variables."""
        # Grid state
        self.revealed = np.zeros((self.grid_size, self.grid_size), dtype=bool)
        
        # Animal placements: Dict[int, List[Tuple[int, int]]]
        self.animal_placements: Dict[int, List[Tuple[int, int]]] = {}
        
        # Tile to animal mapping: (row, col) -> animal_idx or None
        self.tile_to_animal: Dict[Tuple[int, int], Optional[int]] = {}
        
        # Completion tracking
        self.animals_completed: List[bool] = [False] * 7
        self.tiles_found_per_animal: Dict[int, Set[Tuple[int, int]]] = {i: set() for i in range(7)}
        
        # Move tracking
        self.moves_remaining = self.max_moves
        
        # Probability engine
        self.prob_engine: Optional[ProbabilityEngine] = None
    
    def reset(
        self,
        seed: Optional[int] = None,
        options: Optional[Dict[str, Any]] = None
    ) -> Tuple[Dict[str, np.ndarray], Dict[str, Any]]:
        """
        Reset the environment for a new episode.
        
        Args:
            seed: Random seed for reproducibility
            options: Optional configuration (can override num_animals, max_moves)
        
        Returns:
            observation: Dict with 'grid' and 'scalars'
            info: Additional information
        """
        super().reset(seed=seed)
        
        # Handle options
        if options:
            if 'num_animals' in options:
                self.num_animals = options['num_animals']
            if 'max_moves' in options:
                self.max_moves = options['max_moves']
        
        # Reset state
        self._reset_state_vars()
        self.moves_remaining = self.max_moves
        
        # Place animals on the grid
        self._place_animals()
        
        # Initialize probability engine
        self.prob_engine = ProbabilityEngine(biome=self.biome)
        
        # Get initial observation
        obs = self._get_observation()
        info = self._get_info()
        
        return obs, info
    
    def _place_animals(self):
        """
        Randomly place animals on the grid without overlapping tiles.
        
        Randomly selects which animals (from all 7 in the biome) appear,
        then uses rejection sampling to find non-overlapping placements.
        """
        occupied_tiles: Set[Tuple[int, int]] = set()
        
        # Randomly select WHICH animals appear (from all 7 possible)
        all_animal_indices = list(range(7))
        random.shuffle(all_animal_indices)
        animals_to_place = all_animal_indices[:self.num_animals]
        
        for animal_idx in animals_to_place:
            pattern = self.patterns[animal_idx]
            valid_placements = get_all_valid_placements(pattern, self.grid_size)
            
            # Filter out placements that overlap with occupied tiles
            available_placements = []
            for placement in valid_placements:
                if not any(tile in occupied_tiles for tile in placement):
                    available_placements.append(placement)
            
            if not available_placements:
                # No valid placement found - skip this animal
                continue
            
            # Randomly select a placement
            chosen = random.choice(available_placements)
            self.animal_placements[animal_idx] = chosen
            
            # Mark tiles as occupied
            for tile in chosen:
                occupied_tiles.add(tile)
                self.tile_to_animal[tile] = animal_idx
    
    def step(
        self,
        action: int
    ) -> Tuple[Dict[str, np.ndarray], float, bool, bool, Dict[str, Any]]:
        """
        Execute one step in the environment.
        
        Args:
            action: Tile index to reveal (0-24), maps to (action // 5, action % 5)
        
        Returns:
            observation: Updated state
            reward: Reward for this action
            terminated: True if episode ended (no moves or all animals found)
            truncated: Always False (no time limit beyond moves)
            info: Additional information
        """
        assert self.action_space.contains(action), f"Invalid action: {action}"
        
        # Decode action to grid position
        row = action // self.grid_size
        col = action % self.grid_size
        
        reward = 0.0
        terminated = False
        
        # Check if tile already revealed (invalid action)
        if self.revealed[row, col]:
            # Invalid action: penalize but don't consume move
            reward = self.penalty_invalid_action
            # Move is NOT consumed - agent can try again
        else:
            # Reveal the tile
            self.revealed[row, col] = True
            self.moves_remaining -= 1
            
            # Check what's under the tile
            tile = (row, col)
            animal_idx = self.tile_to_animal.get(tile)
            
            if animal_idx is not None:
                # Found an animal tile!
                reward = self.reward_animal_tile
                
                # Update probability engine
                self.prob_engine.reveal_animal_tile(row, col, animal_idx)
                
                # Track found tiles for this animal
                self.tiles_found_per_animal[animal_idx].add(tile)
                
                # Check if animal is now complete
                if len(self.tiles_found_per_animal[animal_idx]) == len(self.animal_placements[animal_idx]):
                    self.animals_completed[animal_idx] = True
                    reward = self.reward_animal_complete
                    self.prob_engine.mark_animal_completed(animal_idx)
            else:
                # Empty tile
                reward = self.reward_empty_tile
                self.prob_engine.reveal_empty_tile(row, col)
        
        # Check termination conditions
        if self.moves_remaining <= 0:
            terminated = True
        elif all(self.animals_completed[i] for i in range(self.num_animals) if i in self.animal_placements):
            # All placed animals found
            terminated = True
        
        obs = self._get_observation()
        info = self._get_info()
        
        return obs, reward, terminated, False, info
    
    def _get_observation(self) -> Dict[str, np.ndarray]:
        """
        Construct the observation from current state.
        
        Returns:
            Dict with 'grid' (5, 5, 14) and 'scalars' (9,) arrays
        """
        # Get grid channels from probability engine
        grid = self.prob_engine.get_state_channels()  # (5, 5, 14)
        
        # Build scalar features
        scalars = np.zeros(self.num_scalars, dtype=np.float32)
        
        # Normalized moves remaining (0 to 1)
        scalars[0] = self.moves_remaining / self.max_moves
        
        # Completion flags for each animal slot (0 or 1)
        for i in range(7):
            scalars[1 + i] = 1.0 if self.animals_completed[i] else 0.0
        
        # Total animals found (normalized by 7)
        scalars[8] = sum(self.animals_completed) / 7.0
        
        return {'grid': grid, 'scalars': scalars}
    
    def _get_info(self) -> Dict[str, Any]:
        """
        Get additional information about current state.
        
        Returns:
            Dict with debugging and evaluation info
        """
        return {
            'moves_remaining': self.moves_remaining,
            'moves_used': self.max_moves - self.moves_remaining,
            'animals_found': sum(self.animals_completed),
            'animals_present': len(self.animal_placements),
            'tiles_revealed': int(self.revealed.sum()),
            'completion_progress': self.prob_engine.get_completion_progress() if self.prob_engine else {},
            'biome': self.biome,
        }
    
    def get_valid_actions_mask(self) -> np.ndarray:
        """
        Get mask of valid (unrevealed) actions.
        
        Returns:
            (25,) boolean array where True = valid action
        """
        return ~self.revealed.flatten()
    
    def get_valid_actions(self) -> List[int]:
        """
        Get list of valid action indices.
        
        Returns:
            List of action indices (0-24) that haven't been revealed
        """
        mask = self.get_valid_actions_mask()
        return list(np.where(mask)[0])
    
    def render(self) -> Optional[str]:
        """
        Render the current state.
        
        Returns:
            String representation if render_mode='ansi', else None
        """
        if self.render_mode == "ansi":
            return self._render_ansi()
        elif self.render_mode == "human":
            print(self._render_ansi())
            return None
        return None
    
    def _render_ansi(self) -> str:
        """
        Create ASCII representation of the grid.
        
        Legend:
            . = Unrevealed
            _ = Revealed empty
            0-6 = Revealed animal tile (animal index)
            * = Completed animal tile
        """
        lines = []
        lines.append(f"Disco Zoo - {self.biome.title()} | Moves: {self.moves_remaining}/{self.max_moves}")
        lines.append(f"Animals found: {sum(self.animals_completed)}/{len(self.animal_placements)}")
        lines.append("-" * 15)
        
        for row in range(self.grid_size):
            row_str = ""
            for col in range(self.grid_size):
                if not self.revealed[row, col]:
                    row_str += " ."
                else:
                    tile = (row, col)
                    animal_idx = self.tile_to_animal.get(tile)
                    if animal_idx is None:
                        row_str += " _"
                    elif self.animals_completed[animal_idx]:
                        row_str += " *"
                    else:
                        row_str += f" {animal_idx}"
            lines.append(row_str)
        
        lines.append("-" * 15)
        
        # Show animal status
        for animal_idx in sorted(self.animal_placements.keys()):
            found = len(self.tiles_found_per_animal[animal_idx])
            total = len(self.animal_placements[animal_idx])
            status = "✓" if self.animals_completed[animal_idx] else f"{found}/{total}"
            name = self.animal_names[animal_idx] if animal_idx < len(self.animal_names) else f"Animal_{animal_idx}"
            lines.append(f"  [{animal_idx}] {name}: {status}")
        
        return "\n".join(lines)
    
    def close(self):
        """Clean up resources."""
        pass


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def create_curriculum_env(phase: int, biome: str = 'farm') -> DiscoZooEnv:
    """
    Create an environment configured for curriculum learning.
    
    Args:
        phase: Curriculum phase (1-4)
        biome: Biome to use
    
    Returns:
        Configured DiscoZooEnv
    """
    curriculum = {
        1: {'num_animals': 1, 'max_moves': 20},
        2: {'num_animals': 2, 'max_moves': 15},
        3: {'num_animals': 3, 'max_moves': 12},
        4: {'num_animals': 3, 'max_moves': 10},
    }
    
    config = curriculum.get(phase, curriculum[4])
    return DiscoZooEnv(biome=biome, **config)


# =============================================================================
# MAIN (Testing)
# =============================================================================

if __name__ == "__main__":
    print("Disco Zoo Environment Test")
    print("=" * 50)
    
    # Create environment
    env = DiscoZooEnv(biome='farm', num_animals=3, max_moves=15, render_mode='human')
    
    # Reset and show initial state
    obs, info = env.reset(seed=42)
    print(f"\nInitial observation shapes:")
    print(f"  Grid: {obs['grid'].shape}")
    print(f"  Scalars: {obs['scalars'].shape}")
    print(f"\nInitial info: {info}")
    
    env.render()
    
    # Run a few random steps
    print("\n" + "=" * 50)
    print("Running random episode...")
    print("=" * 50 + "\n")
    
    total_reward = 0
    step = 0
    
    while True:
        # Get valid actions and choose randomly
        valid_actions = env.get_valid_actions()
        if not valid_actions:
            break
        
        action = random.choice(valid_actions)
        row, col = action // 5, action % 5
        
        obs, reward, terminated, truncated, info = env.step(action)
        total_reward += reward
        step += 1
        
        print(f"Step {step}: Reveal ({row}, {col}) -> Reward: {reward:+.1f}")
        
        if terminated:
            break
    
    print("\n" + "=" * 50)
    print("Final state:")
    env.render()
    print(f"\nTotal reward: {total_reward:.1f}")
    print(f"Animals found: {info['animals_found']}/{info['animals_present']}")
    print(f"Moves used: {info['moves_used']}/{env.max_moves}")
    
    env.close()
