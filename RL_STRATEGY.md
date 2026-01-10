# Reinforcement Learning Strategy for Disco Zoo
## Adapting Battleship AI Techniques to Animal Pattern Discovery

> 📖 **Note**: This document discusses general RL strategies. For the **current neural network architecture** (14-channel, biome-agnostic design), see **[NEURAL_NETWORK_ARCHITECTURE_V2.md](NEURAL_NETWORK_ARCHITECTURE_V2.md)**.

---

## Problem Comparison: Battleship vs. Disco Zoo

### Similarities
Both games share fundamental characteristics that make Battleship AI strategies highly applicable:

| Aspect | Battleship | Disco Zoo |
|--------|-----------|-----------|
| **Grid-Based** | 10×10 grid | 5×5 grid |
| **Hidden Patterns** | Ships (5 types, 2-5 squares) | Animals (7 types, 2-5 squares) |
| **Partial Observability** | Unknown ship locations | Unknown animal locations |
| **Sequential Revelation** | Fire shots to reveal | Flip tiles to reveal |
| **Resource Constraint** | Minimize shots to win | Limited tile flips per game |
| **Pattern Completion** | Sink entire ship | Find all tiles of animal |
| **Multiple Targets** | Multiple ships on grid | Multiple animals on grid |
| **No Overlap** | Ships can't overlap | Animals can't overlap |

### Key Differences
| Aspect | Battleship | Disco Zoo | Impact on Strategy |
|--------|-----------|-----------|-------------------|
| **Objective** | Sink ALL ships | Maximize animals found | Disco Zoo requires triage |
| **Feedback** | "Hit" or "Miss" | "Animal" or "Empty" | Disco Zoo: Unknown which animal |
| **Victory Condition** | 100% elimination | Partial success acceptable | Different risk tolerance |
| **Pattern Orientation** | Horizontal/Vertical only | Any fixed orientation | More pattern variety |
| **Grid Size** | 10×10 (100 tiles) | 5×5 (25 tiles) | Disco Zoo: Higher tile density |

---

## Core Battleship AI Strategies

### 1. **Hunt and Target Mode** (Most Common Approach)

Classic Battleship AI uses two distinct behavioral modes:

#### **Hunt Mode** (Exploration Phase)
- **Goal**: Efficiently search for new ships
- **Strategy**: Use probability-based search patterns
- **Common Patterns**:
  - **Checkerboard**: Skip every other square (works for ships ≥2 squares)
  - **Diagonal**: Search diagonals systematically
  - **Random with constraints**: Weighted random based on remaining ship sizes

#### **Target Mode** (Exploitation Phase)
- **Triggered**: When a hit is registered
- **Goal**: Sink the discovered ship completely
- **Strategy**: 
  1. Try adjacent squares (up, down, left, right)
  2. Once second hit found, determine orientation (horizontal/vertical)
  3. Continue in that direction until ship sinks
  4. Return to Hunt Mode

**Adaptation for Disco Zoo:**
- **Hunt Mode**: Search for any animal tile
- **Target Mode**: Once animal tile found, explore neighbors to complete pattern
- **Challenge**: Don't know which animal species hit, so pattern is unknown
- **Solution**: Use pattern likelihood heatmaps based on revealed neighbors

---

### 2. **Probability Density Function (PDF) / Heatmap Strategy**

Advanced Battleship AI maintains a probability map of ship locations.

#### **How it Works:**
1. **Initialize**: Start with uniform probability across all tiles
2. **Update After Each Shot**:
   - **Hit**: Increase probability of adjacent squares (ship extends there)
   - **Miss**: Zero out probability for that tile
   - **Sink**: Zero out probability for entire ship area + buffer
3. **Next Shot**: Select highest probability tile(s)

#### **Probability Calculation:**
For each unrevealed tile, count how many valid ship placements include that tile:
```python
for each unrevealed_tile:
    probability = 0
    for each unsunk_ship:
        for each valid_placement:
            if placement includes unrevealed_tile:
                probability += 1
    heatmap[tile] = probability
```

**Adaptation for Disco Zoo:**
```python
for each unrevealed_tile:
    probability = 0
    for each possible_animal_pattern:
        for each valid_placement:
            # Check if placement fits with revealed information
            if placement_is_consistent_with_revealed_tiles():
                if placement includes unrevealed_tile:
                    probability += 1
    heatmap[tile] = probability
```

**Key Insight**: Tiles that are part of MORE possible pattern placements should be explored first.

---

### 3. **Constraint Satisfaction / Bayesian Inference**

After each revelation, update beliefs about what patterns could still fit.

#### **Battleship Approach:**
- Eliminate impossible ship configurations based on hits/misses
- Maintain set of valid placements for each unsunk ship
- Narrow down possibilities with each shot

#### **Disco Zoo Adaptation:**
```python
# After each tile reveal:
for each animal_pattern in possible_patterns:
    for each placement in valid_placements[pattern]:
        # Check consistency
        if any revealed_animal_tile not in placement:
            remove placement  # Inconsistent
        if any revealed_empty_tile in placement:
            remove placement  # Impossible
        
# If all placements for a pattern eliminated:
    remove animal_pattern from possible_patterns
```

**Example:**
- Reveal tile (2,3) → Animal
- Reveal tile (2,4) → Empty
- Conclusion: No animal pattern extends from (2,3) to (2,4)
- Update: Eliminate all patterns with that configuration

---

### 4. **Parity-Based Search Patterns**

Efficient search exploiting minimum ship sizes.

#### **Battleship Concept:**
If minimum ship size is 2, can use checkerboard pattern:
```
O . O . O
. O . O .
O . O . O
. O . O .
O . O . O
```
Guaranteed to hit every ship with 50% of shots.

#### **Disco Zoo Adaptation:**
Since minimum animal pattern is 2 tiles:
- **Phase 1**: Checkerboard search to find initial hits
- **Phase 2**: Once hit found, search immediate neighbors
- **Efficiency**: Cover 25 tiles with ~13 shots to hit all 2+ tile patterns

**Advanced Parity:**
- Different search patterns for different assumed minimum sizes
- Adaptive parity based on learned animal pattern statistics
- Dynamic switching between search densities

---

## Neural Network Architecture for Disco Zoo

> ⚠️ **OUTDATED**: The examples below show a simplified 4-channel architecture for illustration. The **actual implementation** uses a **14-channel biome-agnostic design** with separate channels per animal species. See **[NEURAL_NETWORK_ARCHITECTURE_V2.md](NEURAL_NETWORK_ARCHITECTURE_V2.md)** for the current specification.

### Input Representation (Conceptual Overview)

#### **Option 1: Multi-Channel Grid (Recommended)**
Represent state as stacked 5×5 grids (channels):
```python
# SIMPLIFIED EXAMPLE (actual uses 14 channels - see V2 doc)
state_shape = (5, 5, 4)  # Height × Width × Channels

Channel 0: Unrevealed tiles (1 = unrevealed, 0 = revealed)
Channel 1: Revealed animal tiles (1 = animal, 0 = not)
Channel 2: Revealed empty tiles (1 = empty, 0 = not)
Channel 3: Probability heatmap (0.0-1.0 = likelihood of animal)
```

**Advantages:**
- Preserves spatial relationships
- Natural input for CNNs
- Can add more channels (pattern likelihood, move history, etc.)

#### **Option 2: Flattened Feature Vector**
```python
state_vector = [
    *grid.flatten(),        # 25 values: tile states (0=unrevealed, 1=empty, 2=animal)
    moves_remaining,         # 1 value: normalized 0-1
    animals_found,           # 1 value: count
    *probability_heatmap     # 25 values: per-tile probabilities
]
# Total: 52 features
```

**Advantages:**
- Simple architecture
- Fast computation
- Works with fully connected networks

#### **Option 3: Graph Neural Network (Advanced)**
Represent grid as graph where tiles are nodes:
```python
nodes = 25 (one per tile)
edges = adjacency (4-8 edges per node: up, down, left, right, diagonals)
node_features = [revealed, is_animal, is_empty, probability]
```

**Advantages:**
- Explicitly models spatial relationships
- Can learn pattern structures
- Generalizes to different grid sizes

---

### Network Architecture Options

#### **Architecture 1: Convolutional Neural Network (CNN)** - *Best for spatial patterns*
```python
Input: (5, 5, 4) multi-channel grid

Conv2D(32 filters, 3×3, padding='same', activation='relu')
Conv2D(64 filters, 3×3, padding='same', activation='relu')
Conv2D(64 filters, 3×3, padding='same', activation='relu')
Flatten()
Dense(256, activation='relu')
Dense(128, activation='relu')
Output: Dense(25, activation='linear')  # Q-values for each tile
```

**Why CNNs?**
- **Spatial invariance**: Pattern at (0,0) same as pattern at (2,3)
- **Local connectivity**: Animal patterns are local structures
- **Parameter efficiency**: Share weights across spatial locations
- **Proven**: Excellent for board games (AlphaGo, etc.)

#### **Architecture 2: Fully Connected (MLP)** - *Simpler baseline*
```python
Input: 52-dimensional feature vector

Dense(256, activation='relu')
Dense(256, activation='relu')
Dense(128, activation='relu')
Output: Dense(25, activation='linear')  # Q-values for each tile
```

**Use Case:**
- Baseline comparison
- Faster training
- Good if spatial structure not critical

#### **Architecture 3: Recurrent Neural Network (LSTM/GRU)** - *For sequential memory*
```python
Input: Sequence of (state, action) pairs from episode

LSTM(128 units, return_sequences=True)
LSTM(128 units)
Dense(256, activation='relu')
Output: Dense(25, activation='linear')
```

**Why RNNs?**
- **Temporal patterns**: Remember what was tried before
- **Context**: Full episode history
- **Credit assignment**: Link early moves to later outcomes

**Caveat**: Slower training, more complex

#### **Architecture 4: Dueling DQN** - *Separates value and advantage*
```python
Input: (5, 5, 4)

# Shared convolutional layers
Conv2D(32, 3×3, relu)
Conv2D(64, 3×3, relu)
Flatten()
Dense(256, relu)

# Split into value and advantage streams
Value Stream:                Advantage Stream:
  Dense(128, relu)             Dense(128, relu)
  Dense(1)                     Dense(25)

# Combine: Q(s,a) = V(s) + (A(s,a) - mean(A(s)))
Output: Q-values (25)
```

**Benefits:**
- **Better learning**: Separates "how good is this state" from "which action is best"
- **Faster convergence**: Especially when most actions have similar value
- **Proven**: Standard in modern DQN implementations

---

### Output Layer and Action Selection

#### **Output Format:**
```python
# Q-value for each action (tile position)
output = [Q(s, a_0), Q(s, a_1), ..., Q(s, a_24)]

# Map action index to grid position
action_idx = 0-24
row = action_idx // 5
col = action_idx % 5
```

#### **Action Masking** (Critical!)
Prevent selecting already-revealed tiles:
```python
valid_actions_mask = (grid == 0).flatten()  # True for unrevealed tiles
q_values_masked = np.where(valid_actions_mask, q_values, -np.inf)
action = np.argmax(q_values_masked)
```

Without masking → wasted moves on revealed tiles!

#### **Exploration Strategies:**

**1. Epsilon-Greedy** (Standard)
```python
if random() < epsilon:
    action = random_choice(valid_actions)  # Explore
else:
    action = argmax(q_values_masked)       # Exploit
    
# Decay epsilon: 1.0 → 0.01 over training
```

**2. Boltzmann/Softmax Exploration** (Temperature-based)
```python
probabilities = softmax(q_values_masked / temperature)
action = sample(probabilities)

# Decay temperature over training
```

**3. Upper Confidence Bound (UCB)** (Optimistic exploration)
```python
# Bonus for under-explored actions
q_ucb = q_values + c * sqrt(log(total_steps) / action_counts)
action = argmax(q_ucb_masked)
```

**4. Probability Heatmap Exploration** (Domain-specific)
```python
# Blend Q-values with probability heatmap
combined = alpha * q_values + (1 - alpha) * heatmap
action = argmax(combined_masked)
```

---

## Reinforcement Learning Algorithm Selection

### **Option 1: Deep Q-Network (DQN)** - *Recommended starting point*

**Why DQN?**
- ✅ **Discrete action space**: Perfect fit (25 actions)
- ✅ **Proven**: Works well for grid-based games
- ✅ **Off-policy**: Learn from experience replay (data efficient)
- ✅ **Stable**: With modern improvements (Double DQN, Dueling DQN)

**Core Components:**
```python
# Experience replay buffer
replay_buffer = [(state, action, reward, next_state, done), ...]

# Training loop
for episode in episodes:
    state = env.reset()
    while not done:
        # Epsilon-greedy action selection
        action = select_action(state, epsilon)
        next_state, reward, done = env.step(action)
        
        # Store experience
        replay_buffer.append((state, action, reward, next_state, done))
        
        # Sample minibatch and train
        if len(replay_buffer) > batch_size:
            batch = sample(replay_buffer, batch_size)
            loss = compute_loss(batch)
            optimizer.minimize(loss)
        
        state = next_state
```

**DQN Loss:**
```python
# Q-learning target (Bellman equation)
target_q = reward + gamma * max(Q_target(next_state))

# Current Q-value prediction
predicted_q = Q(state, action)

# Loss (MSE)
loss = (target_q - predicted_q)^2
```

**Modern Improvements:**
- **Double DQN**: Reduce overestimation bias
- **Dueling DQN**: Separate value/advantage
- **Prioritized Experience Replay**: Sample important transitions more
- **Rainbow DQN**: Combine all improvements

### **Option 2: Proximal Policy Optimization (PPO)** - *Alternative*

**Why PPO?**
- ✅ **Stable training**: Conservative policy updates
- ✅ **On-policy**: Can incorporate exploration bonuses
- ✅ **Flexible**: Works with continuous/discrete actions

**Trade-offs:**
- ❌ Less sample efficient than DQN (no replay)
- ❌ More hyperparameters to tune
- ✅ Often more stable in practice

**Use Case**: If DQN training is unstable or you want to add intrinsic motivation rewards.

### **Option 3: Monte Carlo Tree Search (MCTS)** - *Planning-based*

**Why MCTS?**
- ✅ **Lookahead**: Simulate future moves
- ✅ **No training**: Can work without learning
- ✅ **Optimal with enough compute**: Guaranteed improvement

**Trade-offs:**
- ❌ Slow: Requires simulations per move
- ❌ Needs accurate forward model
- ✅ Can combine with neural network (AlphaZero style)

**Hybrid Approach**: Use neural network to guide MCTS.

---

## Training Strategy

### Phase 1: Curriculum Learning

Start simple, gradually increase difficulty:

**Level 1: Single Animal, Easy Patterns**
```python
num_animals = 1
max_moves = 20
pattern_library = ["horizontal_2", "vertical_2", "L_shape"]
```
**Goal**: Agent learns basic exploration and pattern completion.

**Level 2: Multiple Animals, Medium Moves**
```python
num_animals = 2-3
max_moves = 15
pattern_library = ["all_common_patterns"]
```
**Goal**: Agent learns to balance multiple targets.

**Level 3: Full Difficulty**
```python
num_animals = 4-7
max_moves = 10-12
pattern_library = ["all_patterns"]
```
**Goal**: Agent masters efficient search and triage.

### Phase 2: Transfer Learning

**Pre-training:**
1. **Supervised learning**: Train on expert demonstrations or heatmap predictions
2. **Auxiliary tasks**: Predict animal locations from partial observations
3. **Self-play**: Agent plays against itself with different strategies

**Fine-tuning:**
- Start with pre-trained weights
- Lower learning rate
- Focus on hard cases

### Phase 3: Reward Shaping Evolution

**Stage 1: Dense rewards** (fast initial learning)
```python
reward = 10*animals + 0.1*animal_tiles - 0.05*empty_tiles
```

**Stage 2: Reduce shaping** (towards true objective)
```python
reward = 10*animals + 0.01*animal_tiles
```

**Stage 3: Pure sparse** (optimal policy)
```python
reward = 10*animals
```

---

## Key Implementation Techniques

### 1. **Dynamic Heatmap Integration**

Combine learned policy with probability heatmap:

```python
def select_action_with_heatmap(state, q_network, heatmap, alpha=0.5):
    q_values = q_network(state)
    
    # Compute probability heatmap from current state
    heatmap = compute_pattern_probability_heatmap(state)
    
    # Blend Q-values and heatmap
    combined_values = alpha * q_values + (1 - alpha) * heatmap
    
    # Action masking
    valid_mask = (state[:, :, 0] == 1).flatten()
    combined_values[~valid_mask] = -inf
    
    return argmax(combined_values)
```

**Benefits:**
- Incorporates domain knowledge
- Guides exploration
- Can anneal alpha over training (start heatmap-heavy, end Q-value-heavy)

### 2. **Pattern Likelihood Network** (Auxiliary Task)

Train separate network to predict "animal present" probability:

```python
# Auxiliary network
pattern_detector = CNN(
    input=(5, 5, 3),  # Revealed state
    output=(5, 5, 1)  # Per-tile probability
)

# Loss: Binary cross-entropy
loss = BCE(pattern_detector(state), true_animal_locations)
```

**Use:**
- Provides heatmap for action selection
- Helps Q-network learn features
- Can be trained with supervised learning initially

### 3. **Multi-Task Learning**

Train network on multiple objectives simultaneously:

```python
# Shared backbone
backbone = CNN_backbone(input_state)

# Task 1: Q-value prediction (RL)
q_values = Dense(25)(backbone)
q_loss = DQN_loss(q_values, targets)

# Task 2: Pattern detection (supervised)
pattern_pred = Conv2D(1)(backbone)
pattern_loss = BCE(pattern_pred, true_patterns)

# Task 3: Moves-to-completion prediction
moves_pred = Dense(1)(backbone)
moves_loss = MSE(moves_pred, actual_moves)

# Combined loss
total_loss = q_loss + 0.5*pattern_loss + 0.3*moves_loss
```

**Benefits:**
- Richer feature learning
- Better generalization
- Regularization effect

---

## Evaluation Metrics

### Performance Metrics
1. **Animals per Episode**: Primary metric (mean, median, max)
2. **Completion Rate**: % of animals found vs. present
3. **Efficiency**: Animals found / tiles revealed
4. **Pattern Success Rate**: Per-pattern completion statistics
5. **First-Hit Success**: % converted from first animal tile to complete animal

### Learning Metrics
1. **Convergence Speed**: Episodes to reach performance threshold
2. **Sample Efficiency**: Animals found per training step
3. **Stability**: Variance in performance over training
4. **Generalization**: Performance on unseen pattern combinations

### Baseline Comparisons
1. **Random Agent**: Uniform random tile selection
2. **Heuristic Agent**: Probability heatmap only
3. **Greedy Agent**: Always complete nearest partial pattern
4. **Human Player**: Average human performance

---

## Expected Challenges and Solutions

### Challenge 1: Sparse Rewards → Slow Learning
**Solution:**
- Curriculum learning (start easy)
- Dense auxiliary rewards (animal tiles)
- Hindsight Experience Replay (treat failures as successes for different goals)

### Challenge 2: Credit Assignment
**Problem**: Which early moves led to finding animals?
**Solution:**
- N-step returns (longer horizons)
- LSTM/GRU for temporal context
- Reward shaping with intermediate milestones

### Challenge 3: Exploration in Large State Space
**Solution:**
- Probability heatmap guidance
- Curiosity-driven exploration (intrinsic motivation)
- Count-based exploration bonuses

### Challenge 4: Pattern Memorization
**Problem**: Agent must learn 100+ unique patterns
**Solution:**
- Large replay buffer (diverse experiences)
- Pattern augmentation (rotation/reflection of patterns)
- Meta-learning (learn to learn patterns quickly)

### Challenge 5: Action Masking Complexity
**Problem**: Valid actions change every step
**Solution:**
- Explicit masking in action selection
- Invalid action penalty in reward
- Separate "action validity" network

---

## Implementation Roadmap

### Week 1-2: Environment and Baseline
- [ ] Implement Disco Zoo environment (OpenAI Gym interface)
- [ ] Create simple pattern library (5-10 patterns)
- [ ] Implement random agent
- [ ] Implement heatmap-based agent (no learning)
- [ ] Establish baseline metrics

### Week 3-4: Basic DQN
- [ ] Implement vanilla DQN with experience replay
- [ ] CNN architecture for grid input
- [ ] Action masking
- [ ] Train on single animal, easy patterns
- [ ] Visualize Q-values and learned policy

### Week 5-6: Improvements
- [ ] Double DQN / Dueling DQN
- [ ] Prioritized experience replay
- [ ] Curriculum learning (progressive difficulty)
- [ ] Heatmap integration
- [ ] Hyperparameter tuning

### Week 7-8: Advanced Techniques
- [ ] Multi-task learning (pattern detection)
- [ ] Attention mechanisms
- [ ] Transfer learning experiments
- [ ] Full pattern library (50+ patterns)
- [ ] Ensemble methods

### Week 9-10: Evaluation and Analysis
- [ ] Comprehensive evaluation suite
- [ ] Ablation studies (which components help?)
- [ ] Visualization tools (attention maps, heatmaps)
- [ ] Compare to human performance
- [ ] Write up results

---

## References and Further Reading

### Reinforcement Learning
- **Mnih et al. (2015)**: "Human-level control through deep reinforcement learning" (DQN paper)
- **Van Hasselt et al. (2016)**: "Deep Reinforcement Learning with Double Q-learning"
- **Wang et al. (2016)**: "Dueling Network Architectures for Deep Reinforcement Learning"
- **Schaul et al. (2016)**: "Prioritized Experience Replay"

### Game-Playing AI
- **Silver et al. (2016)**: "Mastering the game of Go with deep neural networks and tree search" (AlphaGo)
- **Silver et al. (2017)**: "Mastering Chess and Shogi by Self-Play with a General Reinforcement Learning Algorithm" (AlphaZero)

### Battleship Strategy
- **Probabilistic Battleship**: [DataGenetics Blog](http://datagenetics.com/blog/december32011/index.html)
- **Optimal Battleship Strategy**: Various computer science competition solutions

### Spatial Reasoning
- **CNN for Board Games**: Numerous papers on chess, Go, Othello
- **Graph Neural Networks**: Recent work on structured prediction

---

## Conclusion

Disco Zoo presents a rich RL problem that combines:
- **Search optimization** (Battleship-style hunt/target)
- **Pattern recognition** (CNNs for spatial understanding)
- **Resource allocation** (limited moves, multiple targets)
- **Partial observability** (hidden information, Bayesian inference)

The recommended approach:
1. **Start with DQN + CNN** for spatial learning
2. **Integrate probability heatmaps** for domain knowledge
3. **Use curriculum learning** for stable training
4. **Employ hybrid rewards** (sparse + weak dense signals)
5. **Iterate and evaluate** against baselines

This strategy leverages proven techniques from Battleship AI while adapting to Disco Zoo's unique challenges. The combination of learned policies and probabilistic reasoning should yield strong performance.
