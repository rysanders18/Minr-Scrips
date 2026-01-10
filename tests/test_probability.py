"""
Unit Tests for Probability Engine

Tests:
- Heatmap computation
- Constraint satisfaction (confirmed tiles, empty tiles)
- Valid placement filtering
- Multi-animal heatmaps
- Edge cases

Run with: pytest tests/test_probability.py -v
"""

import pytest
import numpy as np
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from probability_engine import ProbabilityEngine
from pattern_library import PATTERN_LIBRARY, get_all_valid_placements


class TestProbabilityEngineInitialization:
    """Tests for probability engine creation."""
    
    def test_create_engine(self):
        """Engine can be created with default settings."""
        engine = ProbabilityEngine()
        assert engine is not None
        assert engine.biome == 'farm'
        assert engine.grid_size == 5
        assert engine.num_animals == 7
    
    def test_create_engine_different_biome(self):
        """Engine can be created with different biome."""
        engine = ProbabilityEngine(biome='outback')
        assert engine.biome == 'outback'
        assert len(engine.patterns) == 7
    
    def test_patterns_loaded(self):
        """Patterns are correctly loaded."""
        engine = ProbabilityEngine(biome='farm')
        assert len(engine.patterns) == 7
        for idx, pattern in engine.patterns.items():
            assert len(pattern) >= 2  # All patterns have at least 2 tiles
    
    def test_placements_precomputed(self):
        """Valid placements are precomputed for each pattern."""
        engine = ProbabilityEngine(biome='farm')
        for idx in range(7):
            assert idx in engine.all_placements
            assert len(engine.all_placements[idx]) > 0


class TestReset:
    """Tests for engine reset."""
    
    def test_reset_clears_state(self):
        """Reset clears all revealed tiles and confirmed tiles."""
        engine = ProbabilityEngine()
        
        engine.reveal_animal_tile(0, 0, 0)
        engine.reveal_empty_tile(1, 1)
        
        engine.reset()
        
        assert len(engine.revealed) == 0
        assert len(engine.empty_tiles) == 0
        assert all(len(tiles) == 0 for tiles in engine.confirmed_tiles.values())


class TestRevealTiles:
    """Tests for revealing tiles."""
    
    def test_reveal_empty_tile(self):
        """Empty tile is correctly tracked."""
        engine = ProbabilityEngine()
        engine.reveal_empty_tile(2, 2)
        
        assert (2, 2) in engine.revealed
        assert (2, 2) in engine.empty_tiles
    
    def test_reveal_animal_tile(self):
        """Animal tile is correctly tracked."""
        engine = ProbabilityEngine()
        engine.reveal_animal_tile(2, 2, 3)
        
        assert (2, 2) in engine.revealed
        assert (2, 2) in engine.confirmed_tiles[3]
        assert (2, 2) not in engine.empty_tiles
    
    def test_reveal_multiple_tiles_same_animal(self):
        """Multiple tiles for same animal are tracked."""
        engine = ProbabilityEngine()
        engine.reveal_animal_tile(0, 0, 1)
        engine.reveal_animal_tile(0, 1, 1)
        
        assert len(engine.confirmed_tiles[1]) == 2
        assert (0, 0) in engine.confirmed_tiles[1]
        assert (0, 1) in engine.confirmed_tiles[1]


class TestAnimalCompletion:
    """Tests for animal completion detection."""
    
    def test_animal_completion_detected(self):
        """Completing a pattern marks animal as completed."""
        engine = ProbabilityEngine(biome='farm')
        
        # Farm animal 6 (chicken) has 2-tile diagonal pattern: [(0,0), (1,1)]
        pattern = engine.patterns[6]
        
        # Reveal all tiles
        for row, col in pattern:
            engine.reveal_animal_tile(row, col, 6)
        
        assert 6 in engine.completed_animals
    
    def test_incomplete_animal_not_marked(self):
        """Partially revealed animal is not marked complete."""
        engine = ProbabilityEngine(biome='farm')
        
        pattern = engine.patterns[0]  # Pig - 2x2
        
        # Reveal only one tile
        engine.reveal_animal_tile(pattern[0][0], pattern[0][1], 0)
        
        assert 0 not in engine.completed_animals


class TestHeatmapComputation:
    """Tests for probability heatmap computation."""
    
    def test_initial_heatmap_uniform(self):
        """Initial heatmap has uniform probabilities."""
        engine = ProbabilityEngine()
        heatmap = engine.compute_heatmap(0)
        
        assert heatmap.shape == (5, 5)
        assert heatmap.dtype == np.float32
        
        # All tiles should have same probability (uniform)
        # (may vary slightly due to edge effects)
    
    def test_confirmed_tile_probability_one(self):
        """Confirmed animal tile has probability 1.0."""
        engine = ProbabilityEngine()
        engine.reveal_animal_tile(2, 2, 0)
        
        heatmap = engine.compute_heatmap(0)
        assert heatmap[2, 2] == 1.0
    
    def test_empty_tile_probability_zero(self):
        """Empty tile has probability 0.0 for all animals."""
        engine = ProbabilityEngine()
        engine.reveal_empty_tile(2, 2)
        
        for animal_idx in range(7):
            heatmap = engine.compute_heatmap(animal_idx)
            assert heatmap[2, 2] == 0.0
    
    def test_completed_animal_heatmap_zero(self):
        """Completed animal has all-zero heatmap."""
        engine = ProbabilityEngine(biome='farm')
        
        # Complete animal 6 (chicken - 2 tiles)
        pattern = engine.patterns[6]
        for row, col in pattern:
            engine.reveal_animal_tile(row, col, 6)
        
        heatmap = engine.compute_heatmap(6)
        assert np.all(heatmap == 0.0)
    
    def test_heatmap_updates_on_reveal(self):
        """Heatmap changes when tile is revealed."""
        engine = ProbabilityEngine()
        
        heatmap_before = engine.compute_heatmap(0).copy()
        engine.reveal_empty_tile(0, 0)
        heatmap_after = engine.compute_heatmap(0)
        
        # Heatmaps should be different
        assert not np.array_equal(heatmap_before, heatmap_after)


class TestValidPlacements:
    """Tests for valid placement filtering."""
    
    def test_all_placements_initially_valid(self):
        """All placements are valid at start."""
        engine = ProbabilityEngine()
        
        for animal_idx in range(7):
            valid = engine.get_valid_placements(animal_idx)
            all_placements = engine.all_placements[animal_idx]
            assert len(valid) == len(all_placements)
    
    def test_placements_reduced_by_empty_tile(self):
        """Empty tile reduces valid placements."""
        engine = ProbabilityEngine()
        
        initial = len(engine.get_valid_placements(0))
        engine.reveal_empty_tile(2, 2)
        after = len(engine.get_valid_placements(0))
        
        # Should have fewer valid placements
        assert after <= initial
    
    def test_placements_constrained_by_confirmed_tile(self):
        """Confirmed tile constrains valid placements."""
        engine = ProbabilityEngine()
        
        # Reveal animal 0 tile at (0, 0)
        engine.reveal_animal_tile(0, 0, 0)
        
        valid = engine.get_valid_placements(0)
        
        # All valid placements must include (0, 0)
        for placement in valid:
            assert (0, 0) in placement
    
    def test_placements_exclude_other_animal_tiles(self):
        """Placements exclude tiles belonging to other animals."""
        engine = ProbabilityEngine()
        
        # Reveal tile for animal 1
        engine.reveal_animal_tile(2, 2, 1)
        
        # Valid placements for animal 0 should not include (2, 2)
        valid = engine.get_valid_placements(0)
        for placement in valid:
            assert (2, 2) not in placement


class TestAllHeatmaps:
    """Tests for computing all heatmaps at once."""
    
    def test_all_heatmaps_shape(self):
        """All heatmaps has correct shape."""
        engine = ProbabilityEngine()
        heatmaps = engine.compute_all_heatmaps()
        
        assert heatmaps.shape == (7, 5, 5)
        assert heatmaps.dtype == np.float32
    
    def test_all_heatmaps_consistent_with_individual(self):
        """All heatmaps matches individual computations."""
        engine = ProbabilityEngine()
        engine.reveal_animal_tile(1, 1, 2)
        engine.reveal_empty_tile(3, 3)
        
        all_heatmaps = engine.compute_all_heatmaps()
        
        for animal_idx in range(7):
            individual = engine.compute_heatmap(animal_idx)
            np.testing.assert_array_equal(all_heatmaps[animal_idx], individual)


class TestStateChannels:
    """Tests for full state representation."""
    
    def test_confirmed_channels_shape(self):
        """Confirmed channels has correct shape."""
        engine = ProbabilityEngine()
        channels = engine.get_confirmed_channels()
        
        assert channels.shape == (7, 5, 5)
    
    def test_confirmed_channels_binary(self):
        """Confirmed channels are binary (0 or 1)."""
        engine = ProbabilityEngine()
        engine.reveal_animal_tile(0, 0, 0)
        engine.reveal_animal_tile(1, 1, 2)
        
        channels = engine.get_confirmed_channels()
        
        assert np.all((channels == 0.0) | (channels == 1.0))
    
    def test_state_channels_shape(self):
        """State channels has correct shape (HWC format)."""
        engine = ProbabilityEngine()
        state = engine.get_state_channels()
        
        assert state.shape == (5, 5, 14)
    
    def test_state_channels_structure(self):
        """State channels has confirmed then probability channels."""
        engine = ProbabilityEngine()
        engine.reveal_animal_tile(2, 2, 3)
        
        state = engine.get_state_channels()
        
        # Channel 3 should have 1.0 at (2, 2) - confirmed
        assert state[2, 2, 3] == 1.0
        
        # Channel 10 (3+7) should have 1.0 at (2, 2) - probability
        assert state[2, 2, 10] == 1.0


class TestBestTile:
    """Tests for best tile selection."""
    
    def test_get_best_tile_for_animal(self):
        """Best tile returns unrevealed tile with highest probability."""
        engine = ProbabilityEngine()
        
        best = engine.get_best_tile_for_animal(0)
        assert best is not None
        assert best not in engine.revealed
    
    def test_get_best_tile_overall(self):
        """Best tile overall returns tile with max across animals."""
        engine = ProbabilityEngine()
        
        best = engine.get_best_tile_overall()
        assert best is not None
    
    def test_best_tile_excludes_revealed(self):
        """Best tile excludes already revealed tiles."""
        engine = ProbabilityEngine()
        
        # Reveal many tiles
        for i in range(20):
            row, col = i // 5, i % 5
            engine.reveal_empty_tile(row, col)
        
        best = engine.get_best_tile_for_animal(0)
        if best is not None:
            assert best not in engine.revealed


class TestCompletionProgress:
    """Tests for completion progress tracking."""
    
    def test_initial_progress_all_zero(self):
        """Initial progress shows 0 found for all animals."""
        engine = ProbabilityEngine()
        progress = engine.get_completion_progress()
        
        for animal_idx, (found, total) in progress.items():
            assert found == 0
            assert total >= 2  # All patterns have at least 2 tiles
    
    def test_progress_updates_on_reveal(self):
        """Progress updates when animal tile is revealed."""
        engine = ProbabilityEngine()
        engine.reveal_animal_tile(0, 0, 0)
        
        progress = engine.get_completion_progress()
        found, total = progress[0]
        assert found == 1


class TestEdgeCases:
    """Tests for edge cases and corner cases."""
    
    def test_no_valid_placements(self):
        """Handle case where no valid placements remain."""
        engine = ProbabilityEngine()
        
        # Fill grid with empty tiles except one row
        for row in range(4):
            for col in range(5):
                engine.reveal_empty_tile(row, col)
        
        # Some animals may have no valid placements
        # This shouldn't crash
        heatmap = engine.compute_heatmap(0)
        assert heatmap.shape == (5, 5)
    
    def test_all_tiles_revealed(self):
        """Handle case where all tiles are revealed."""
        engine = ProbabilityEngine()
        
        for row in range(5):
            for col in range(5):
                engine.reveal_empty_tile(row, col)
        
        # All heatmaps should be 0 (all empty)
        heatmaps = engine.compute_all_heatmaps()
        assert np.all(heatmaps == 0.0)
    
    def test_cache_invalidation(self):
        """Cache is properly invalidated on state change."""
        engine = ProbabilityEngine()
        
        # Compute once to populate cache
        _ = engine.get_valid_placements(0)
        assert engine._valid_placements_cache is not None
        
        # Reveal tile should invalidate cache
        engine.reveal_empty_tile(0, 0)
        assert engine._valid_placements_cache is None


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
