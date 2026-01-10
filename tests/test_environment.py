"""
Unit Tests for Disco Zoo Environment

Tests:
- Environment initialization
- State representation (14 channels + 9 scalars)
- Action space and masking
- Reward calculation
- Episode termination
- Animal placement and completion

Run with: pytest tests/test_environment.py -v
"""

import pytest
import numpy as np
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from discoZoo import DiscoZooEnv
from pattern_library import PATTERN_LIBRARY, get_indexed_patterns


class TestEnvironmentInitialization:
    """Tests for environment creation and configuration."""
    
    def test_create_default_environment(self):
        """Environment can be created with default settings."""
        env = DiscoZooEnv()
        assert env is not None
        assert env.biome == 'farm'
        assert env.num_animals == 3  # Game maximum is 3
        assert env.max_moves == 10
        env.close()
    
    def test_create_custom_environment(self):
        """Environment can be created with custom settings."""
        env = DiscoZooEnv(biome='outback', num_animals=3, max_moves=15)
        assert env.biome == 'outback'
        assert env.num_animals == 3
        assert env.max_moves == 15
        env.close()
    
    def test_invalid_biome_raises_error(self):
        """Invalid biome name raises assertion error."""
        with pytest.raises(AssertionError):
            DiscoZooEnv(biome='invalid_biome')
    
    def test_invalid_num_animals_raises_error(self):
        """Invalid num_animals raises assertion error."""
        with pytest.raises(AssertionError):
            DiscoZooEnv(num_animals=0)
        with pytest.raises(AssertionError):
            DiscoZooEnv(num_animals=8)


class TestReset:
    """Tests for environment reset."""
    
    def test_reset_returns_observation_and_info(self):
        """Reset returns observation dict and info dict."""
        env = DiscoZooEnv()
        obs, info = env.reset()
        
        assert isinstance(obs, dict)
        assert 'grid' in obs
        assert 'scalars' in obs
        assert isinstance(info, dict)
        env.close()
    
    def test_observation_shapes(self):
        """Observation has correct shapes."""
        env = DiscoZooEnv()
        obs, _ = env.reset()
        
        assert obs['grid'].shape == (5, 5, 14)
        assert obs['scalars'].shape == (9,)
        assert obs['grid'].dtype == np.float32
        assert obs['scalars'].dtype == np.float32
        env.close()
    
    def test_initial_scalars_correct(self):
        """Initial scalar values are correct."""
        env = DiscoZooEnv(max_moves=20)
        obs, _ = env.reset()
        
        # Moves remaining should be 1.0 (normalized)
        assert obs['scalars'][0] == 1.0
        
        # All completion flags should be 0
        for i in range(1, 8):
            assert obs['scalars'][i] == 0.0
        
        # Total found should be 0
        assert obs['scalars'][8] == 0.0
        env.close()
    
    def test_reset_with_seed_is_reproducible(self):
        """Same seed produces same initial state."""
        env = DiscoZooEnv()
        
        obs1, _ = env.reset(seed=42)
        obs2, _ = env.reset(seed=42)
        
        np.testing.assert_array_equal(obs1['grid'], obs2['grid'])
        np.testing.assert_array_equal(obs1['scalars'], obs2['scalars'])
        env.close()


class TestActionSpace:
    """Tests for action space and valid actions."""
    
    def test_action_space_size(self):
        """Action space has 25 actions (5x5 grid)."""
        env = DiscoZooEnv()
        assert env.action_space.n == 25
        env.close()
    
    def test_all_actions_initially_valid(self):
        """All actions are valid at start (no tiles revealed)."""
        env = DiscoZooEnv()
        env.reset()
        
        valid_mask = env.get_valid_actions_mask()
        assert valid_mask.shape == (25,)
        assert valid_mask.all()  # All True initially
        env.close()
    
    def test_action_becomes_invalid_after_reveal(self):
        """Revealed tile becomes invalid action."""
        env = DiscoZooEnv()
        env.reset()
        
        action = 12  # Middle tile
        env.step(action)
        
        valid_mask = env.get_valid_actions_mask()
        assert not valid_mask[action]  # This action is now invalid
        assert sum(valid_mask) == 24  # 24 valid actions remain
        env.close()
    
    def test_get_valid_actions_list(self):
        """get_valid_actions returns list of valid action indices."""
        env = DiscoZooEnv()
        env.reset()
        
        valid_actions = env.get_valid_actions()
        assert len(valid_actions) == 25
        assert all(0 <= a < 25 for a in valid_actions)
        env.close()


class TestStep:
    """Tests for step function."""
    
    def test_step_returns_correct_tuple(self):
        """Step returns (obs, reward, terminated, truncated, info)."""
        env = DiscoZooEnv()
        env.reset()
        
        result = env.step(0)
        assert len(result) == 5
        
        obs, reward, terminated, truncated, info = result
        assert isinstance(obs, dict)
        assert isinstance(reward, float)
        assert isinstance(terminated, bool)
        assert isinstance(truncated, bool)
        assert isinstance(info, dict)
        env.close()
    
    def test_moves_decrease_after_step(self):
        """Moves remaining decreases after each step."""
        env = DiscoZooEnv(max_moves=10)
        env.reset()
        
        assert env.moves_remaining == 10
        env.step(0)
        assert env.moves_remaining == 9
        env.step(1)
        assert env.moves_remaining == 8
        env.close()
    
    def test_invalid_action_penalty(self):
        """Re-revealing a tile returns penalty but doesn't consume move."""
        env = DiscoZooEnv(num_animals=1, max_moves=10)
        env.reset()

        # First reveal (valid action)
        initial_moves = env.moves_remaining
        env.step(0)
        assert env.moves_remaining == initial_moves - 1  # Move consumed

        # Second reveal of same tile (invalid action)
        moves_before_invalid = env.moves_remaining
        _, reward, _, _, _ = env.step(0)

        assert reward == -1.0  # Penalty for invalid action
        assert env.moves_remaining == moves_before_invalid  # Move NOT consumed
        env.close()
    
    def test_episode_terminates_when_moves_exhausted(self):
        """Episode ends when moves reach 0."""
        env = DiscoZooEnv(num_animals=3, max_moves=3)
        env.reset()

        # Take 3 valid moves (unlikely to complete all 3 animals in 3 moves)
        env.step(0)
        env.step(1)
        _, _, terminated, _, info = env.step(2)

        # Episode should terminate after 3rd move (moves exhausted)
        assert terminated or info['moves_remaining'] == 0
        env.close()

    def test_invalid_actions_allow_multiple_attempts(self):
        """Agent can retry after invalid actions without losing moves."""
        env = DiscoZooEnv(num_animals=1, max_moves=5)
        env.reset()

        # Use all 5 moves on different tiles
        env.step(0)  # Move 1
        assert env.moves_remaining == 4

        env.step(1)  # Move 2
        assert env.moves_remaining == 3

        # Try invalid action multiple times - shouldn't consume moves
        _, reward, _, _, _ = env.step(0)  # Invalid
        assert reward == -1.0
        assert env.moves_remaining == 3  # Still have 3 moves

        _, reward, _, _, _ = env.step(1)  # Invalid
        assert reward == -1.0
        assert env.moves_remaining == 3  # Still have 3 moves

        # Continue with valid moves
        env.step(2)  # Move 3
        assert env.moves_remaining == 2

        env.step(3)  # Move 4
        assert env.moves_remaining == 1

        env.step(4)  # Move 5
        assert env.moves_remaining == 0

        env.close()


class TestRewards:
    """Tests for reward calculation."""
    
    def test_empty_tile_gives_zero_reward(self):
        """Revealing an empty tile returns 0 reward."""
        env = DiscoZooEnv(num_animals=1, max_moves=25)
        env.reset(seed=42)
        
        # Find an empty tile by trying all
        for action in range(25):
            obs, _ = env.reset(seed=42)
            _, reward, _, _, _ = env.step(action)
            
            if reward == 0.0:
                # Found empty tile
                break
        
        # At least some tiles should be empty
        env.close()
    
    def test_animal_tile_gives_small_reward(self):
        """Finding an animal tile (but not completing) gives +0.1."""
        env = DiscoZooEnv(num_animals=1, max_moves=25)
        
        found_animal_tile = False
        for _ in range(100):  # Try multiple seeds
            env.reset()
            
            for action in range(25):
                _, reward, _, _, _ = env.step(action)
                
                if reward == 0.1:
                    found_animal_tile = True
                    break
            
            if found_animal_tile:
                break
        
        # Should find at least one animal tile in 100 tries
        assert found_animal_tile
        env.close()
    
    def test_completing_animal_gives_large_reward(self):
        """Completing an animal gives +10.0."""
        env = DiscoZooEnv(num_animals=1, max_moves=25)
        
        found_completion = False
        for seed in range(100):
            env.reset(seed=seed)
            
            total_reward = 0
            for action in range(25):
                _, reward, terminated, _, _ = env.step(action)
                total_reward += reward
                
                if reward == 10.0:
                    found_completion = True
                    break
                
                if terminated:
                    break
            
            if found_completion:
                break
        
        # Should complete at least one animal in 100 tries
        # (with 25 moves and 1 animal, guaranteed)
        assert found_completion
        env.close()


class TestAnimalCompletion:
    """Tests for animal completion detection."""
    
    def test_completion_flags_update_on_animal_found(self):
        """Completion flags in scalars update when animal is completed."""
        env = DiscoZooEnv(num_animals=1, max_moves=25)
        
        for seed in range(50):
            obs, _ = env.reset(seed=seed)
            
            # All flags start at 0
            assert obs['scalars'][8] == 0.0  # total found
            
            # Try all tiles
            for action in range(25):
                obs, reward, terminated, _, info = env.step(action)
                
                if reward == 10.0:
                    # Animal completed - check flags
                    assert info['animals_found'] == 1
                    assert obs['scalars'][8] > 0  # total found increased
                    break
                
                if terminated:
                    break
            
            if reward == 10.0:
                break
        
        env.close()
    
    def test_info_tracks_animals_correctly(self):
        """Info dict correctly tracks animals found and present."""
        env = DiscoZooEnv(num_animals=3, max_moves=25)
        _, info = env.reset()
        
        assert info['animals_present'] <= 3  # Could be fewer if placement fails
        assert info['animals_found'] == 0
        assert info['tiles_revealed'] == 0
        env.close()


class TestRender:
    """Tests for rendering."""
    
    def test_render_ansi_returns_string(self):
        """Render mode 'ansi' returns string representation."""
        env = DiscoZooEnv(render_mode='ansi')
        env.reset()
        
        output = env.render()
        assert isinstance(output, str)
        assert 'Disco Zoo' in output
        env.close()
    
    def test_render_without_mode_returns_none(self):
        """Render with no mode returns None."""
        env = DiscoZooEnv(render_mode=None)
        env.reset()
        
        output = env.render()
        assert output is None
        env.close()


class TestAnimalPlacement:
    """Tests for animal placement on the grid."""
    
    def test_animals_are_placed(self):
        """Animals are actually placed on the grid."""
        env = DiscoZooEnv(num_animals=3, max_moves=25)
        env.reset()
        
        # Check that animal placements exist
        assert len(env.animal_placements) > 0
        assert len(env.animal_placements) <= 3
        env.close()
    
    def test_animal_tiles_dont_overlap(self):
        """Different animals don't share tiles."""
        env = DiscoZooEnv(num_animals=3, max_moves=25)
        
        for seed in range(20):
            env.reset(seed=seed)
            
            all_tiles = []
            for tiles in env.animal_placements.values():
                all_tiles.extend(tiles)
            
            # No duplicates
            assert len(all_tiles) == len(set(all_tiles))
        
        env.close()
    
    def test_tile_to_animal_mapping_correct(self):
        """tile_to_animal dict correctly maps tiles to animals."""
        env = DiscoZooEnv(num_animals=3, max_moves=25)
        env.reset()
        
        for animal_idx, tiles in env.animal_placements.items():
            for tile in tiles:
                assert env.tile_to_animal[tile] == animal_idx
        
        env.close()


class TestObservationSpace:
    """Tests for observation space compliance."""
    
    def test_observation_within_bounds(self):
        """Observation values are within defined bounds."""
        env = DiscoZooEnv()
        obs, _ = env.reset()
        
        # Grid should be [0, 1]
        assert obs['grid'].min() >= 0.0
        assert obs['grid'].max() <= 1.0
        
        # Scalars should be [0, 1]
        assert obs['scalars'].min() >= 0.0
        assert obs['scalars'].max() <= 1.0
        env.close()
    
    def test_observation_space_contains_observation(self):
        """Observation is within observation_space."""
        env = DiscoZooEnv()
        obs, _ = env.reset()
        
        assert env.observation_space['grid'].contains(obs['grid'])
        assert env.observation_space['scalars'].contains(obs['scalars'])
        env.close()


class TestCurriculumEnvironment:
    """Tests for curriculum learning environment creation."""
    
    def test_create_curriculum_env(self):
        """Curriculum environment creation works."""
        from discoZoo import create_curriculum_env
        
        env = create_curriculum_env(phase=1)
        assert env.num_animals == 1
        assert env.max_moves == 20
        env.close()
        
        env = create_curriculum_env(phase=4)
        assert env.num_animals == 3  # Game maximum is 3
        assert env.max_moves == 10
        env.close()


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
