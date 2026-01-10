"""
Unit Tests for DQN Agent

Tests:
- Warm-up period enforcement
- Target network update frequency
- Action selection and masking
- Replay buffer functionality

Run with: pytest tests/test_agent.py -v
"""

import pytest
import numpy as np
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import DQNAgent, RandomAgent, HeatmapAgent, TORCH_AVAILABLE


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="PyTorch not available")
class TestDQNAgent:
    """Tests for DQN agent functionality."""

    def test_agent_creation(self):
        """Agent can be created with default parameters."""
        agent = DQNAgent()
        assert agent is not None
        assert agent.warmup_steps == 1000
        assert agent.target_update_freq == 5000
        assert agent.batch_size == 64

    def test_warmup_period_prevents_training(self):
        """Agent doesn't train during warm-up period."""
        agent = DQNAgent(warmup_steps=100, batch_size=32)

        # Create dummy state
        state = {
            'grid': np.random.rand(5, 5, 14).astype(np.float32),
            'scalars': np.random.rand(9).astype(np.float32)
        }
        valid_mask = np.ones(25, dtype=bool)

        # Add 50 transitions (less than warm-up)
        for i in range(50):
            agent.store_transition(state, 0, 1.0, state, False, valid_mask)

        # Should not train yet (warm-up not complete)
        loss = agent.train_step()
        assert loss is None, "Should not train during warm-up period"
        assert len(agent.replay_buffer) == 50

        # Add more transitions to exceed warm-up (100 total)
        for i in range(60):
            agent.store_transition(state, 0, 1.0, state, False, valid_mask)

        # Should train now (110 transitions > 100 warm-up)
        loss = agent.train_step()
        assert loss is not None, "Should train after warm-up period"
        assert isinstance(loss, float)

    def test_warmup_respects_batch_size(self):
        """Training requires both warm-up completion AND sufficient batch size."""
        agent = DQNAgent(warmup_steps=50, batch_size=100)

        state = {
            'grid': np.random.rand(5, 5, 14).astype(np.float32),
            'scalars': np.random.rand(9).astype(np.float32)
        }
        valid_mask = np.ones(25, dtype=bool)

        # Add 75 transitions (exceeds warm-up but not batch_size)
        for i in range(75):
            agent.store_transition(state, 0, 1.0, state, False, valid_mask)

        # Should not train (batch_size not met)
        loss = agent.train_step()
        assert loss is None, "Should not train when buffer < batch_size"

        # Add more to exceed batch size
        for i in range(30):
            agent.store_transition(state, 0, 1.0, state, False, valid_mask)

        # Now should train
        loss = agent.train_step()
        assert loss is not None, "Should train when both conditions met"

    def test_custom_warmup_steps(self):
        """Agent respects custom warm-up period."""
        agent = DQNAgent(warmup_steps=200, batch_size=64)

        state = {
            'grid': np.random.rand(5, 5, 14).astype(np.float32),
            'scalars': np.random.rand(9).astype(np.float32)
        }
        valid_mask = np.ones(25, dtype=bool)

        # Add 150 transitions (less than custom warm-up of 200)
        for i in range(150):
            agent.store_transition(state, 0, 1.0, state, False, valid_mask)

        loss = agent.train_step()
        assert loss is None, "Should respect custom warm-up period"

        # Add more to exceed warm-up
        for i in range(60):
            agent.store_transition(state, 0, 1.0, state, False, valid_mask)

        loss = agent.train_step()
        assert loss is not None, "Should train after custom warm-up"

    def test_action_selection_with_masking(self):
        """Agent respects action masking during selection."""
        agent = DQNAgent()

        state = {
            'grid': np.random.rand(5, 5, 14).astype(np.float32),
            'scalars': np.random.rand(9).astype(np.float32)
        }

        # Create mask with only a few valid actions
        valid_mask = np.zeros(25, dtype=bool)
        valid_mask[5] = True
        valid_mask[10] = True
        valid_mask[15] = True

        # Random action (epsilon=1.0) should only select from valid actions
        for _ in range(20):
            action = agent.select_action(state, valid_mask, epsilon=1.0)
            assert action in [5, 10, 15], f"Selected invalid action {action}"

    def test_target_network_update_frequency(self):
        """Target network updates at correct frequency."""
        agent = DQNAgent(target_update_freq=10, warmup_steps=50, batch_size=32)

        state = {
            'grid': np.random.rand(5, 5, 14).astype(np.float32),
            'scalars': np.random.rand(9).astype(np.float32)
        }
        valid_mask = np.ones(25, dtype=bool)

        # Fill buffer past warm-up
        for i in range(100):
            agent.store_transition(state, 0, 1.0, state, False, valid_mask)

        # Get initial target network state
        initial_target_params = agent.target_net.state_dict()['fc1.weight'].clone()

        # Train for 9 steps (shouldn't update target)
        for _ in range(9):
            agent.train_step()

        # Target should be unchanged
        current_target_params = agent.target_net.state_dict()['fc1.weight']
        assert np.allclose(
            initial_target_params.cpu().numpy(),
            current_target_params.cpu().numpy()
        ), "Target should not update before frequency threshold"

        # One more step (10th step) should trigger update
        agent.train_step()

        # Policy network should have changed
        policy_params = agent.policy_net.state_dict()['fc1.weight']
        assert not np.allclose(
            initial_target_params.cpu().numpy(),
            policy_params.cpu().numpy()
        ), "Policy network should have changed"


class TestBaselineAgents:
    """Tests for baseline agents."""

    def test_random_agent_selection(self):
        """Random agent selects from valid actions."""
        agent = RandomAgent()

        state = {
            'grid': np.random.rand(5, 5, 14).astype(np.float32),
            'scalars': np.random.rand(9).astype(np.float32)
        }
        valid_mask = np.zeros(25, dtype=bool)
        valid_mask[[3, 7, 11]] = True

        for _ in range(10):
            action = agent.select_action(state, valid_mask)
            assert action in [3, 7, 11]

    def test_heatmap_agent_selection(self):
        """Heatmap agent selects highest probability tile."""
        agent = HeatmapAgent()

        # Create state with clear highest probability
        grid = np.zeros((5, 5, 14), dtype=np.float32)
        grid[2, 3, 10] = 0.9  # High probability in channel 10 (probability channel)

        state = {
            'grid': grid,
            'scalars': np.zeros(9, dtype=np.float32)
        }
        valid_mask = np.ones(25, dtype=bool)

        action = agent.select_action(state, valid_mask)
        expected_action = 2 * 5 + 3  # Row 2, Col 3 = action 13
        assert action == expected_action
