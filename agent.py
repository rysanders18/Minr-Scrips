"""
DQN Agent for Disco Zoo Reinforcement Learning

Implements a Deep Q-Network (DQN) agent with:
- CNN architecture for processing grid state
- Experience replay buffer
- Target network for stable learning
- Epsilon-greedy exploration with action masking
- Double DQN for reduced overestimation

Usage:
    from agent import DQNAgent
    from discoZoo import DiscoZooEnv
    
    env = DiscoZooEnv(biome='farm')
    agent = DQNAgent(
        grid_shape=(5, 5, 14),
        num_scalars=9,
        num_actions=25
    )
    
    obs, info = env.reset()
    action = agent.select_action(obs, env.get_valid_actions_mask(), epsilon=0.1)
"""

import numpy as np
from typing import Dict, List, Tuple, Optional
from collections import deque
import random

# Try to import torch, provide helpful error if not available
try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    import torch.optim as optim
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    print("Warning: PyTorch not installed. Install with: pip install torch")


# =============================================================================
# NEURAL NETWORK ARCHITECTURE
# =============================================================================

if TORCH_AVAILABLE:
    class DQNNetwork(nn.Module):
        """
        Deep Q-Network for Disco Zoo.
        
        Architecture:
        - Grid branch: 3 Conv2D layers (32, 64, 64 filters)
        - Flatten and concatenate with scalars
        - Dense layers: 256 -> 128 -> 25 (Q-values)
        
        Total parameters: ~507,000
        """
        
        def __init__(
            self,
            grid_shape: Tuple[int, int, int] = (5, 5, 14),
            num_scalars: int = 9,
            num_actions: int = 25
        ):
            """
            Initialize the DQN network.
            
            Args:
                grid_shape: (height, width, channels) of grid input
                num_scalars: Number of scalar features
                num_actions: Number of output Q-values (25 for 5x5 grid)
            """
            super().__init__()
            
            self.grid_shape = grid_shape
            self.num_scalars = num_scalars
            self.num_actions = num_actions
            
            num_channels = grid_shape[2]  # 14 channels
            
            # Convolutional layers for grid processing
            self.conv1 = nn.Conv2d(num_channels, 32, kernel_size=3, padding=1)
            self.conv2 = nn.Conv2d(32, 64, kernel_size=3, padding=1)
            self.conv3 = nn.Conv2d(64, 64, kernel_size=3, padding=1)
            
            # Compute flattened size after convolutions
            # With padding='same', spatial dims stay 5x5
            self.conv_output_size = 64 * 5 * 5  # 1600
            
            # Combined size: conv output + scalars
            combined_size = self.conv_output_size + num_scalars  # 1609
            
            # Fully connected layers
            self.fc1 = nn.Linear(combined_size, 256)
            self.fc2 = nn.Linear(256, 128)
            self.fc3 = nn.Linear(128, num_actions)
        
        def forward(
            self,
            grid: torch.Tensor,
            scalars: torch.Tensor
        ) -> torch.Tensor:
            """
            Forward pass through the network.
            
            Args:
                grid: (batch, height, width, channels) tensor
                scalars: (batch, num_scalars) tensor
            
            Returns:
                Q-values: (batch, num_actions) tensor
            """
            # Convert grid from HWC to CHW format for PyTorch
            x = grid.permute(0, 3, 1, 2)  # (batch, channels, height, width)
            
            # Convolutional layers with ReLU
            x = F.relu(self.conv1(x))
            x = F.relu(self.conv2(x))
            x = F.relu(self.conv3(x))
            
            # Flatten (use reshape instead of view for non-contiguous tensors)
            x = x.reshape(x.size(0), -1)  # (batch, 1600)
            
            # Concatenate with scalars
            x = torch.cat([x, scalars], dim=1)  # (batch, 1609)
            
            # Fully connected layers
            x = F.relu(self.fc1(x))
            x = F.relu(self.fc2(x))
            q_values = self.fc3(x)
            
            return q_values
        
        def count_parameters(self) -> int:
            """Count total trainable parameters."""
            return sum(p.numel() for p in self.parameters() if p.requires_grad)


# =============================================================================
# EXPERIENCE REPLAY BUFFER
# =============================================================================

class ReplayBuffer:
    """
    Experience replay buffer for storing and sampling transitions.
    
    Stores (state, action, reward, next_state, done) tuples.
    """
    
    def __init__(self, capacity: int = 100000):
        """
        Initialize the replay buffer.
        
        Args:
            capacity: Maximum number of transitions to store
        """
        self.buffer = deque(maxlen=capacity)
    
    def add(
        self,
        state: Dict[str, np.ndarray],
        action: int,
        reward: float,
        next_state: Dict[str, np.ndarray],
        done: bool,
        valid_mask: np.ndarray
    ):
        """
        Add a transition to the buffer.
        
        Args:
            state: Current observation dict
            action: Action taken
            reward: Reward received
            next_state: Next observation dict
            done: Whether episode ended
            valid_mask: Valid actions mask for next state
        """
        self.buffer.append((state, action, reward, next_state, done, valid_mask))
    
    def sample(self, batch_size: int) -> List[Tuple]:
        """
        Sample a batch of transitions.
        
        Args:
            batch_size: Number of transitions to sample
        
        Returns:
            List of (state, action, reward, next_state, done, valid_mask) tuples
        """
        return random.sample(self.buffer, min(batch_size, len(self.buffer)))
    
    def __len__(self) -> int:
        return len(self.buffer)


# =============================================================================
# DQN AGENT
# =============================================================================

class DQNAgent:
    """
    Deep Q-Network agent with experience replay and target network.
    
    Features:
    - Action masking for invalid actions
    - Epsilon-greedy exploration
    - Target network for stable learning
    - Double DQN for reduced overestimation
    """
    
    def __init__(
        self,
        grid_shape: Tuple[int, int, int] = (5, 5, 14),
        num_scalars: int = 9,
        num_actions: int = 25,
        learning_rate: float = 1e-4,
        gamma: float = 0.99,
        buffer_capacity: int = 100000,
        batch_size: int = 64,
        target_update_freq: int = 5000,
        warmup_steps: int = 1000,
        device: Optional[str] = None
    ):
        """
        Initialize the DQN agent.

        Args:
            grid_shape: Shape of grid observation
            num_scalars: Number of scalar features
            num_actions: Number of possible actions (25)
            learning_rate: Learning rate for optimizer
            gamma: Discount factor
            buffer_capacity: Size of replay buffer
            batch_size: Batch size for training
            target_update_freq: Steps between target network updates (default: 5000)
            warmup_steps: Number of transitions to collect before training starts (default: 1000)
            device: 'cuda' or 'cpu' (auto-detect if None)
        """
        if not TORCH_AVAILABLE:
            raise ImportError("PyTorch is required. Install with: pip install torch")

        self.grid_shape = grid_shape
        self.num_scalars = num_scalars
        self.num_actions = num_actions
        self.gamma = gamma
        self.batch_size = batch_size
        self.target_update_freq = target_update_freq
        self.warmup_steps = warmup_steps
        
        # Device selection
        if device is None:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)
        
        # Networks
        self.policy_net = DQNNetwork(grid_shape, num_scalars, num_actions).to(self.device)
        self.target_net = DQNNetwork(grid_shape, num_scalars, num_actions).to(self.device)
        self.target_net.load_state_dict(self.policy_net.state_dict())
        self.target_net.eval()  # Target network is always in eval mode
        
        # Optimizer
        self.optimizer = optim.Adam(self.policy_net.parameters(), lr=learning_rate)
        
        # Replay buffer
        self.replay_buffer = ReplayBuffer(capacity=buffer_capacity)
        
        # Training stats
        self.steps_done = 0
        self.training_losses = []
    
    def select_action(
        self,
        state: Dict[str, np.ndarray],
        valid_mask: np.ndarray,
        epsilon: float = 0.0
    ) -> int:
        """
        Select an action using epsilon-greedy with action masking.
        
        Args:
            state: Observation dict with 'grid' and 'scalars'
            valid_mask: Boolean mask of valid actions
            epsilon: Exploration probability
        
        Returns:
            Selected action index (0-24)
        """
        # Epsilon-greedy: random action with probability epsilon
        if random.random() < epsilon:
            valid_indices = np.where(valid_mask)[0]
            if len(valid_indices) == 0:
                return 0  # Fallback (shouldn't happen with proper masking)
            return int(np.random.choice(valid_indices))
        
        # Greedy: select best valid action
        with torch.no_grad():
            grid = torch.FloatTensor(state['grid']).unsqueeze(0).to(self.device)
            scalars = torch.FloatTensor(state['scalars']).unsqueeze(0).to(self.device)
            
            q_values = self.policy_net(grid, scalars).cpu().numpy()[0]
            
            # Mask invalid actions
            q_values[~valid_mask] = -np.inf
            
            return int(np.argmax(q_values))
    
    def store_transition(
        self,
        state: Dict[str, np.ndarray],
        action: int,
        reward: float,
        next_state: Dict[str, np.ndarray],
        done: bool,
        next_valid_mask: np.ndarray
    ):
        """
        Store a transition in the replay buffer.
        
        Args:
            state: Current observation
            action: Action taken
            reward: Reward received
            next_state: Next observation
            done: Whether episode ended
            next_valid_mask: Valid actions mask for next state
        """
        self.replay_buffer.add(state, action, reward, next_state, done, next_valid_mask)
    
    def train_step(self) -> Optional[float]:
        """
        Perform one training step on a batch from the replay buffer.

        Returns:
            Loss value if training occurred, None if buffer too small or during warm-up
        """
        # Don't train during warm-up period
        if len(self.replay_buffer) < self.warmup_steps:
            return None

        # Also need minimum batch size
        if len(self.replay_buffer) < self.batch_size:
            return None
        
        # Sample batch
        batch = self.replay_buffer.sample(self.batch_size)
        
        # Unpack batch
        states, actions, rewards, next_states, dones, valid_masks = zip(*batch)
        
        # Convert to tensors
        grid_batch = torch.FloatTensor(np.array([s['grid'] for s in states])).to(self.device)
        scalar_batch = torch.FloatTensor(np.array([s['scalars'] for s in states])).to(self.device)
        
        next_grid_batch = torch.FloatTensor(np.array([s['grid'] for s in next_states])).to(self.device)
        next_scalar_batch = torch.FloatTensor(np.array([s['scalars'] for s in next_states])).to(self.device)
        
        action_batch = torch.LongTensor(actions).to(self.device)
        reward_batch = torch.FloatTensor(rewards).to(self.device)
        done_batch = torch.FloatTensor(dones).to(self.device)
        valid_mask_batch = torch.BoolTensor(np.array(valid_masks)).to(self.device)
        
        # Current Q-values
        current_q = self.policy_net(grid_batch, scalar_batch)
        current_q = current_q.gather(1, action_batch.unsqueeze(1)).squeeze(1)
        
        # Target Q-values (Double DQN)
        with torch.no_grad():
            # Use policy network to select best action
            next_q_policy = self.policy_net(next_grid_batch, next_scalar_batch)
            # Mask invalid actions
            next_q_policy[~valid_mask_batch] = -float('inf')
            best_actions = next_q_policy.argmax(dim=1)
            
            # Use target network to evaluate
            next_q_target = self.target_net(next_grid_batch, next_scalar_batch)
            next_q = next_q_target.gather(1, best_actions.unsqueeze(1)).squeeze(1)
            
            # Bellman target
            target_q = reward_batch + (1 - done_batch) * self.gamma * next_q
        
        # Compute loss
        loss = F.smooth_l1_loss(current_q, target_q)
        
        # Optimize
        self.optimizer.zero_grad()
        loss.backward()
        # Gradient clipping for stability
        torch.nn.utils.clip_grad_norm_(self.policy_net.parameters(), max_norm=1.0)
        self.optimizer.step()
        
        self.steps_done += 1
        loss_value = loss.item()
        self.training_losses.append(loss_value)
        
        # Update target network periodically
        if self.steps_done % self.target_update_freq == 0:
            self.update_target_network()
        
        return loss_value
    
    def update_target_network(self):
        """Copy weights from policy network to target network."""
        self.target_net.load_state_dict(self.policy_net.state_dict())
    
    def save(self, path: str):
        """
        Save the agent's state to a file.
        
        Args:
            path: File path to save to
        """
        torch.save({
            'policy_net_state_dict': self.policy_net.state_dict(),
            'target_net_state_dict': self.target_net.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'steps_done': self.steps_done,
        }, path)
        print(f"Agent saved to {path}")
    
    def load(self, path: str):
        """
        Load the agent's state from a file.
        
        Args:
            path: File path to load from
        """
        checkpoint = torch.load(path, map_location=self.device)
        self.policy_net.load_state_dict(checkpoint['policy_net_state_dict'])
        self.target_net.load_state_dict(checkpoint['target_net_state_dict'])
        self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
        self.steps_done = checkpoint['steps_done']
        print(f"Agent loaded from {path}")
    
    def get_q_values(
        self,
        state: Dict[str, np.ndarray]
    ) -> np.ndarray:
        """
        Get Q-values for all actions given a state.

        Args:
            state: Observation dict

        Returns:
            (25,) array of Q-values
        """
        with torch.no_grad():
            grid = torch.FloatTensor(state['grid']).unsqueeze(0).to(self.device)
            scalars = torch.FloatTensor(state['scalars']).unsqueeze(0).to(self.device)
            return self.policy_net(grid, scalars).cpu().numpy()[0]

    def get_q_values_detailed(
        self,
        state: Dict[str, np.ndarray],
        valid_mask: np.ndarray
    ) -> Dict:
        """
        Get Q-values with additional analysis for debugging.

        Args:
            state: Observation dict
            valid_mask: Boolean array of valid actions

        Returns:
            Dict with raw Q-values, masked values, top actions, and statistics
        """
        q_values = self.get_q_values(state)

        # Mask invalid actions
        masked_q = q_values.copy()
        masked_q[~valid_mask] = -np.inf

        # Get top K from valid actions
        valid_indices = np.where(valid_mask)[0]
        if len(valid_indices) == 0:
            return {
                'raw': q_values,
                'masked': masked_q,
                'best_action': None,
                'best_value': None,
                'top_5': [],
                'mean_valid': 0.0,
                'std_valid': 0.0,
            }

        valid_q = q_values[valid_indices]
        sorted_indices = valid_indices[np.argsort(valid_q)[::-1]]

        results = {
            'raw': q_values,
            'masked': masked_q,
            'best_action': int(np.argmax(masked_q)),
            'best_value': float(np.max(masked_q)),
            'top_5': [
                {
                    'action': int(a),
                    'row': int(a // 5),
                    'col': int(a % 5),
                    'q_value': float(q_values[a])
                }
                for a in sorted_indices[:min(5, len(sorted_indices))]
            ],
            'mean_valid': float(np.mean(valid_q)),
            'std_valid': float(np.std(valid_q)),
        }

        return results


# =============================================================================
# BASELINE AGENTS
# =============================================================================

class RandomAgent:
    """Random agent that selects uniformly from valid actions."""
    
    def select_action(
        self,
        state: Dict[str, np.ndarray],
        valid_mask: np.ndarray,
        epsilon: float = 1.0  # Ignored
    ) -> int:
        """Select a random valid action."""
        valid_indices = np.where(valid_mask)[0]
        if len(valid_indices) == 0:
            return 0
        return int(np.random.choice(valid_indices))


class HeatmapAgent:
    """
    Agent that always selects the tile with highest probability.
    
    Uses the probability heatmaps in the observation to make decisions.
    This is a strong baseline that doesn't require learning.
    """
    
    def select_action(
        self,
        state: Dict[str, np.ndarray],
        valid_mask: np.ndarray,
        epsilon: float = 0.0  # Ignored
    ) -> int:
        """Select the tile with highest probability across all animals."""
        grid = state['grid']  # (5, 5, 14)
        
        # Probability channels are 7-13
        prob_channels = grid[:, :, 7:14]  # (5, 5, 7)
        
        # Take max probability across animals for each tile
        max_probs = np.max(prob_channels, axis=2)  # (5, 5)
        
        # Flatten and mask invalid actions
        flat_probs = max_probs.flatten()  # (25,)
        flat_probs[~valid_mask] = -np.inf
        
        return int(np.argmax(flat_probs))


# =============================================================================
# MAIN (Testing)
# =============================================================================

if __name__ == "__main__":
    print("DQN Agent Test")
    print("=" * 50)
    
    if not TORCH_AVAILABLE:
        print("PyTorch not available. Install with: pip install torch")
        exit(1)
    
    # Create agent
    agent = DQNAgent()
    
    print(f"\nNetwork architecture:")
    print(f"  Parameters: {agent.policy_net.count_parameters():,}")
    print(f"  Device: {agent.device}")
    
    # Test with dummy input
    dummy_state = {
        'grid': np.random.rand(5, 5, 14).astype(np.float32),
        'scalars': np.random.rand(9).astype(np.float32)
    }
    valid_mask = np.ones(25, dtype=bool)
    valid_mask[0] = False  # Mark first action as invalid
    
    # Test action selection
    action = agent.select_action(dummy_state, valid_mask, epsilon=0.0)
    print(f"\nGreedy action: {action}")
    
    action = agent.select_action(dummy_state, valid_mask, epsilon=1.0)
    print(f"Random action: {action}")
    
    # Test Q-values
    q_values = agent.get_q_values(dummy_state)
    print(f"\nQ-values shape: {q_values.shape}")
    print(f"Q-values range: [{q_values.min():.3f}, {q_values.max():.3f}]")
    
    # Test replay buffer
    for i in range(100):
        next_state = {
            'grid': np.random.rand(5, 5, 14).astype(np.float32),
            'scalars': np.random.rand(9).astype(np.float32)
        }
        agent.store_transition(dummy_state, 0, 1.0, next_state, False, valid_mask)
    
    print(f"\nReplay buffer size: {len(agent.replay_buffer)}")
    
    # Test training step
    loss = agent.train_step()
    print(f"Training loss: {loss:.4f}")
    
    print("\n✅ Agent tests passed!")
