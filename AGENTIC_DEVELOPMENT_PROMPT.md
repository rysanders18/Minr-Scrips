# Agentic AI Development Prompt
## Disco Zoo Reinforcement Learning System

---

## 🎯 MISSION

You are an expert AI developer tasked with building a complete reinforcement learning system to play Disco Zoo, a mobile puzzle game. Your goal is to create an AI agent that maximizes the number of animals captured per episode by efficiently revealing tiles on a 5×5 grid.

---

## 📋 PROJECT CONTEXT

### Game Overview
Disco Zoo is a pattern-matching puzzle where:
- A 5×5 grid contains hidden animals (1-3 per game)
- Each animal occupies a unique geometric pattern (2-4 tiles)
- Player reveals tiles one at a time with limited moves (10 typical)
- Revealing all tiles of an animal's pattern captures it
- Goal: Maximize animals captured before moves run out

### Key Insight
This is similar to Battleship AI, but with:
- Multiple pattern shapes (not just lines)
- Multiple targets simultaneously
- Partial success acceptable (don't need to find ALL animals)
- Pattern knowledge provided via probability heatmaps

---

## 🏗️ SYSTEM ARCHITECTURE

### File Structure to Create
```
discoZoo.py                    # Game environment (Gymnasium interface)
probability_engine.py          # Constraint satisfaction for heatmaps
pattern_library.py             # Animal patterns per biome
agent.py                       # DQN agent implementation
train.py                       # Training loop
evaluate.py                    # Evaluation and visualization
tests/
  test_environment.py          # Unit tests for game logic
  test_probability.py          # Unit tests for heatmap computation
models/                        # Saved checkpoints (created during training)
logs/                          # TensorBoard logs (created during training)
```

---

## 🎮 GAME ENVIRONMENT SPECIFICATION

### Class: `DiscoZooEnv`
Implement a Gymnasium-compatible environment.

#### State Representation (14 channels + 9 scalars = 359 nodes)

```python
# Spatial Input: (5, 5, 14) tensor
Channels 0-6:   Confirmed animal tiles (binary per animal slot)
Channels 7-13:  Probability heatmaps (continuous 0.0-1.0 per animal)

# Scalar Input: (9,) vector
[0]:    moves_remaining (normalized 0.0-1.0)
[1-7]:  animal_X_completed (binary flags)
[8]:    total_animals_found (integer 0-7)
```

#### Derived Information (compute on-the-fly, don't store)
```python
def get_empty_tiles(grid):
    """Empty = all probability channels are 0 AND no animal confirmed"""
    any_animal = np.max(grid[:, :, 0:7], axis=-1)
    any_prob = np.max(grid[:, :, 7:14], axis=-1)
    return (any_animal == 0) & (any_prob == 0)

def get_valid_actions(grid):
    """Valid = not confirmed as animal AND has non-zero probability"""
    any_animal = np.max(grid[:, :, 0:7], axis=-1)
    any_prob = np.max(grid[:, :, 7:14], axis=-1)
    unrevealed = (any_animal == 0) & (any_prob > 0)
    return unrevealed.flatten()  # Shape: (25,)
```

#### Action Space
- Discrete(25): Select tile index 0-24
- Map to grid: `row = action // 5, col = action % 5`
- **CRITICAL**: Mask invalid actions (already revealed tiles)

#### Reward Structure
```python
def calculate_reward(action, tile_content, animals_completed_this_step, action_valid):
    reward = 0.0
    
    # Primary: +10 per completed animal (THE GOAL)
    reward += 10.0 * animals_completed_this_step
    
    # Secondary: +0.1 for finding animal tile (exploration aid)
    if tile_content != 'empty' and action_valid:
        reward += 0.1
    
    # Penalty: -1 for invalid action (already revealed)
    if not action_valid:
        reward += -1.0
    
    return reward
```

#### Episode Termination
```python
terminated = (moves_remaining == 0)
truncated = False  # We don't truncate early
```

#### Required Methods
```python
class DiscoZooEnv(gymnasium.Env):
    def __init__(self, biome='farm', num_animals=7, max_moves=12):
        """Initialize environment with biome-specific patterns."""
        
    def reset(self, seed=None, options=None):
        """Reset grid, place 1-7 random animals, reset moves."""
        return observation, info
    
    def step(self, action):
        """Reveal tile, update state, calculate reward."""
        return observation, reward, terminated, truncated, info
    
    def render(self):
        """ASCII visualization of current grid state."""
        
    def get_observation(self):
        """Return (grid, scalars) tuple for network input."""
```

---

## 📊 PROBABILITY ENGINE SPECIFICATION

### Purpose
Compute per-animal probability heatmaps using constraint satisfaction. The neural network does NOT learn patterns - it receives pre-computed probabilities.

### Algorithm
```python
def compute_probability_heatmap(grid_state, animal_id, pattern, confirmed_tiles):
    """
    For each unrevealed tile, compute P(tile is part of animal's pattern).
    
    Args:
        grid_state: Current (5,5,14) observation
        animal_id: Which animal (0-6)
        pattern: List of (row, col) offsets defining the shape
        confirmed_tiles: List of (row, col) already found for this animal
    
    Returns:
        (5, 5) probability heatmap
    """
    heatmap = np.zeros((5, 5))
    
    # Get all valid placements of pattern on grid
    all_placements = get_all_valid_placements(pattern, grid_size=5)
    
    # Filter: must include confirmed tiles, must not overlap empty tiles
    valid_placements = filter_placements(all_placements, confirmed_tiles, empty_tiles)
    
    # For each unrevealed tile, count how many valid placements include it
    for row in range(5):
        for col in range(5):
            if is_revealed(row, col):
                heatmap[row, col] = 0.0 if is_empty(row, col) else 1.0
            else:
                count = sum(1 for p in valid_placements if (row, col) in p)
                heatmap[row, col] = count / len(valid_placements) if valid_placements else 0.0
    
    return heatmap
```

### Update Triggers
Recompute heatmaps after:
1. Any tile is revealed
2. An animal is completed (zero out that animal's heatmap)

---

## 🧠 NEURAL NETWORK SPECIFICATION

### Architecture (CNN + Dense)
```python
def build_dqn_network(num_animals=7):
    num_channels = num_animals * 2  # 14 channels
    num_scalars = 1 + num_animals + 1  # 9 scalars
    
    # Grid input branch
    grid_input = Input(shape=(5, 5, num_channels))
    x = Conv2D(32, 3, padding='same', activation='relu')(grid_input)
    x = Conv2D(64, 3, padding='same', activation='relu')(x)
    x = Conv2D(64, 3, padding='same', activation='relu')(x)
    x = Flatten()(x)  # (1600,)
    
    # Scalar input branch
    scalar_input = Input(shape=(num_scalars,))
    
    # Combine
    combined = Concatenate()([x, scalar_input])  # (1609,)
    
    # Dense layers
    x = Dense(256, activation='relu')(combined)
    x = Dense(128, activation='relu')(x)
    
    # Output: Q-value per action
    q_values = Dense(25, activation='linear')(x)
    
    return Model(inputs=[grid_input, scalar_input], outputs=q_values)
```

### Parameter Count: ~507,000

### Action Selection with Masking
```python
def select_action(model, state, valid_mask, epsilon=0.1):
    grid, scalars = state
    q_values = model.predict([grid[np.newaxis], scalars[np.newaxis]])[0]
    
    # Mask invalid actions
    q_values[~valid_mask] = -np.inf
    
    # Epsilon-greedy
    if np.random.random() < epsilon:
        valid_indices = np.where(valid_mask)[0]
        return np.random.choice(valid_indices)
    else:
        return np.argmax(q_values)
```

---

## 📚 PATTERN LIBRARY SPECIFICATION

### Structure
```python
PATTERN_LIBRARY = {
    'farm': {
        0: [(0,0), (0,1), (1,0), (1,1)],            # 2x2
        1: [(0,0), (0,1), (0,2), (0,3)],            # 1x4 horizontal
        2: [(0,0), (1,0), (2,0), (3,0)],            # 1x4 vertical
        3: [(0,0), (1,0), (2,0)],                   # 1x3 vertical
        4: [(0,0), (0,1), (0,2)],                   # 1x3 horizontal
        5: [(1,0), (0,1), (0,2)],                   # 3-tile L
        6: [(0,0), (1,1), (2,2)],                   # 3-tile diagonal
    },
    'outback': {
        0: [(0,3), (1,2), (2,1), (3,0)],    # Kangaroo - horizontal 4
        1: [(1,0), (1,1), (0,1)],           # Koala - vertical 2
        2: [(0,1), (1,1), (1,0), (2,0)],    # Platypus - 2x2 square
        3: [(0,0), (1,0), (2,0), (3,0)],    # Crocodile - vertical 3
        4: [(0,2), (1,1), (1,0)],           # Cockatoo - horizontal 3
        5: [(0,0), (2,0), (1,1)],           # Tiddalik - L-shape
        6: [(0,0), (0,1), (1,1)],           # Echidna - zigzag
    },
    # Add remaining biomes: savanna, northern, polar, jungle, etc.
}
```
PATTERN_LIBRARY = {
    'farm': {
        'pig':      [(0,0), (0,1), (1,0), (1,1)],            # 2x2
        'sheep':    [(0,0), (0,1), (0,2), (0,3)],            # 1x4 horizontal
        'rabbit':   [(0,0), (1,0), (2,0), (3,0)],            # 1x4 vertical
        'horse':    [(0,0), (1,0), (2,0)],                   # 1x3 vertical
        'cow':      [(0,0), (0,1), (0,2)],                   # 1x3 horizontal
        'unicorn':  [(1,0), (0,1), (0,2)],                   # 3-tile L
        'chicken':  [(0,0), (1,1), (2,2)],                   # 3-tile diagonal
    },

    'outback': {
        # All coordinates given as (row, col) in the pattern's own top-left–anchored bounding box
        'kangaroo':  [(0,0), (1,1), (2,2), (3,3)],           # 4-tile diagonal (down-right)  :contentReference[oaicite:0]{index=0}
        'platypus':  [(0,0), (0,1), (1,0), (1,1)],           # 2x2 square                    :contentReference[oaicite:1]{index=1}
        'crocodile': [(0,0), (0,1), (0,2), (0,3)],           # 1x4 horizontal                :contentReference[oaicite:2]{index=2}
        'koala':     [(0,0), (0,1), (1,1)],                  # 3-tile corner (┘ shape)       :contentReference[oaicite:3]{index=3}
        'cockatoo':  [(0,0), (1,1), (2,1)],                  # 3-tile offset vertical         :contentReference[oaicite:4]{index=4}
        'tiddalik':  [(0,1), (1,0), (1,2)],                  # 3-tile V (2x3 bbox)           :contentReference[oaicite:5]{index=5}
        'echidna':   [(0,2), (1,0), (1,1)],                  # 3-tile ⟂-like (2x3 bbox)      :contentReference[oaicite:6]{index=6}
    },
}

### Pattern Placement
```python
def get_all_valid_placements(pattern, grid_size=5):
    """Return all positions where pattern fits on grid."""
    placements = []
    for anchor_row in range(grid_size):
        for anchor_col in range(grid_size):
            tiles = [(anchor_row + dr, anchor_col + dc) for dr, dc in pattern]
            if all(0 <= r < grid_size and 0 <= c < grid_size for r, c in tiles):
                placements.append(tiles)
    return placements
```

---

## 🏋️ TRAINING SPECIFICATION

### DQN Training Loop
```python
def train_dqn(env, agent, num_episodes=100000, batch_size=64):
    replay_buffer = ReplayBuffer(capacity=100000)
    epsilon = 1.0
    epsilon_min = 0.01
    epsilon_decay = 0.9995
    gamma = 0.99
    target_update_freq = 1000
    
    for episode in range(num_episodes):
        state = env.reset()
        episode_reward = 0
        
        while True:
            valid_mask = env.get_valid_actions()
            action = agent.select_action(state, valid_mask, epsilon)
            next_state, reward, terminated, truncated, info = env.step(action)
            
            replay_buffer.add(state, action, reward, next_state, terminated)
            episode_reward += reward
            
            if len(replay_buffer) >= batch_size:
                batch = replay_buffer.sample(batch_size)
                agent.train_step(batch, gamma)
            
            if terminated or truncated:
                break
            
            state = next_state
        
        epsilon = max(epsilon_min, epsilon * epsilon_decay)
        
        if episode % target_update_freq == 0:
            agent.update_target_network()
        
        if episode % 100 == 0:
            log_metrics(episode, episode_reward, epsilon)
```

### Curriculum Learning (Recommended)
```python
CURRICULUM = [
    {'phase': 1, 'num_animals': 1, 'max_moves': 20, 'episodes': 10000},
    {'phase': 2, 'num_animals': 3, 'max_moves': 15, 'episodes': 30000},
    {'phase': 3, 'num_animals': 5, 'max_moves': 12, 'episodes': 50000},
    {'phase': 4, 'num_animals': 7, 'max_moves': 10, 'episodes': 100000},
]
```

---

## ✅ TESTING REQUIREMENTS

### Unit Tests for Environment
```python
def test_reset_returns_valid_state():
    """State has correct shapes and initial values."""

def test_step_reveals_tile():
    """Action updates grid state correctly."""

def test_animal_completion_detection():
    """Completing pattern triggers reward and updates completion flags."""

def test_invalid_action_penalty():
    """Re-revealing tile returns -1 reward."""

def test_episode_termination():
    """Episode ends when moves exhausted."""

def test_valid_action_mask():
    """Mask correctly identifies unrevealed tiles."""
```

### Unit Tests for Probability Engine
```python
def test_initial_uniform_probability():
    """All tiles start with equal probability."""

def test_probability_updates_on_reveal():
    """Finding animal tile updates adjacent probabilities."""

def test_empty_tile_zeroes_probability():
    """Empty tile sets all animal probabilities to 0 at that location."""

def test_completed_animal_zeroes_heatmap():
    """Completed animal's entire heatmap becomes 0."""
```

### Integration Tests
```python
def test_random_agent_runs_episode():
    """Random agent can complete full episode without errors."""

def test_trained_agent_beats_random():
    """After training, agent outperforms random baseline."""
```

---

## 📈 EVALUATION METRICS

### Primary Metrics
- **Animals/Episode**: Mean animals found per episode (higher = better)
- **Completion Rate**: Animals found / animals present (higher = better)
- **Efficiency**: Animals found / tiles revealed (higher = better)

### Baseline Comparisons
1. **Random Agent**: Uniform random tile selection
2. **Heatmap-Only Agent**: Always pick highest probability tile (no learning)
3. **Trained DQN Agent**: Your implementation

### Logging
```python
# Log to TensorBoard every 100 episodes:
- episode_reward
- animals_found
- moves_used
- epsilon
- loss
- q_value_mean
```

---

## ⚠️ CRITICAL IMPLEMENTATION NOTES

### 1. Action Masking is NON-NEGOTIABLE
Without proper action masking, the agent will waste moves on already-revealed tiles. Always mask before action selection AND in loss calculation.

### 2. Probability Heatmaps are EXTERNAL
The neural network does NOT learn patterns. Probabilities are computed by the constraint satisfaction engine and provided as input channels.

### 3. Biome-Agnostic Design
Use generic `Animal_0` through `Animal_6` slots. The same network architecture works for all biomes - only the pattern library changes.

### 4. Reward Scale Matters
Primary reward (+10 for completion) should dominate secondary (+0.1 for tile). This ensures the agent prioritizes completing patterns over just finding tiles.

### 5. Channel Order Convention
- Channels 0-6: Confirmed tiles (Animal_0 through Animal_6)
- Channels 7-13: Probability heatmaps (Animal_0 through Animal_6)
- Scalar[0]: moves_remaining
- Scalar[1-7]: completion flags
- Scalar[8]: total_found

---

## 🚀 DEVELOPMENT ORDER

### Phase 1: Foundation (Do First)
1. `pattern_library.py` - Define patterns for at least 2 biomes
2. `probability_engine.py` - Implement constraint satisfaction
3. `discoZoo.py` - Game environment with full state representation
4. `tests/test_environment.py` - Validate game logic
5. `tests/test_probability.py` - Validate heatmap computation

### Phase 2: Learning
6. `agent.py` - DQN with action masking
7. `train.py` - Training loop with curriculum
8. Run training on Phase 1 curriculum (single animal)

### Phase 3: Evaluation
9. `evaluate.py` - Metrics and visualization
10. Compare against baselines
11. Iterate on hyperparameters

### Phase 4: Full Game
12. Add remaining biomes to pattern library
13. Train on full curriculum
14. Evaluate generalization across biomes

---

## 📎 REFERENCE DOCUMENTS

For detailed specifications, consult:
- `DISCO_ZOO_RULES.md` - Game mechanics and RL formulation
- `NEURAL_NETWORK_ARCHITECTURE_V2.md` - Full network specification
- `RL_STRATEGY.md` - Battleship-adapted strategies

---

## 🎯 SUCCESS CRITERIA

The system is complete when:
1. ✅ Environment passes all unit tests
2. ✅ Probability engine correctly computes heatmaps
3. ✅ Agent trains without errors
4. ✅ Trained agent achieves >2x random agent performance
5. ✅ System works for multiple biomes without code changes
6. ✅ All code is documented and follows Python conventions

**BEGIN DEVELOPMENT**
