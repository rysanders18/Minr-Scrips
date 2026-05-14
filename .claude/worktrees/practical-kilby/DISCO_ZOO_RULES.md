# Disco Zoo: Rescue Puzzle Mechanics

## Core Puzzle Game
Disco Zoo's rescue mini-game is a grid-based pattern-matching puzzle where players reveal tiles to discover hidden animals.

---

## Game Rules

### Grid Setup
- **Grid Size**: 5×5 (25 tiles total)
- **Initial State**: All tiles are hidden/unrevealed
- **Animals Present**: 1-7 animals hidden on the grid (depending on region)
- **Animal Placement**: Each animal occupies a unique geometric pattern of tiles

### Gameplay Flow
1. Game starts with blank 5×5 grid
2. Player selects a tile coordinate (x, y) to reveal
3. Tile shows either:
   - **Animal tile**: Part of an animal's pattern
   - **Empty tile**: No animal present
4. When all tiles of an animal's pattern are revealed → Animal is captured
5. Game continues until moves are exhausted
6. Unrevealed tiles are shown at game end

### Win Conditions
- **Primary Goal**: Maximize number of animals captured per episode
- **Success**: Revealing all tiles belonging to an animal's pattern
- **Episode End**: All moves are used (no partial credit for incomplete patterns)

### Key Constraints
- **Limited Moves**: Fixed number of tile flips per game (varies by region/difficulty)
- **No Undo**: Tile reveals are permanent
- **No Rotation**: Animal patterns are fixed orientation
- **Overlap Allowed**: Multiple animals can share the grid (patterns don't overlap tiles)

---

## Animal Patterns

### Pattern Properties
- Each animal species has a **unique geometric pattern** on the grid
- Patterns are **fixed** (no rotation or reflection)
- Patterns consist of 2-5 connected or disconnected tiles
- Multiple animals can coexist on the same 5×5 grid without tile overlap

### Pattern Complexity
- **Simple Patterns**: 2-3 tiles (e.g., straight line, L-shape, small cluster)
- **Medium Patterns**: 3-4 tiles (e.g., T-shape, diagonal, scattered)
- **Complex Patterns**: 4-5 tiles (e.g., cross, zigzag, large cluster)

### Example Pattern Shapes
```
Simple (2 tiles):      Medium (3 tiles):      Complex (4 tiles):
██                     ██                      ██
██                     ████                  ██████
                                               ██

Line               L-Shape              T-Shape              Cross
```

### Pattern Placement
- Patterns can be placed anywhere on the 5×5 grid
- Patterns maintain their shape but vary in position between games
- Tile coordinates: (0,0) = top-left, (4,4) = bottom-right

---

## RL Problem Formulation

### State Space
**Observation Components**:
- **Grid State**: 5×5×14 tensor with separate channels per animal:
  - Channels 0-6: Confirmed tiles for each of the 7 animals (binary)
  - Channels 7-13: Probability heatmaps for each animal (continuous 0.0-1.0)
- **Remaining Moves**: Normalized float (0.0-1.0)
- **Animals Captured**: 7 binary flags (one per animal slot) + total count

**State Representation**:
```python
state = {
    'grid': np.array(shape=(5, 5, 14), dtype=float),  # 7 confirmed + 7 probability channels
    'moves_remaining': float,     # Normalized 0-1
    'animals_completed': [0,1,0,0,0,0,0],  # Binary flags per animal
    'total_found': int            # Count 0-7
}
```

📖 See **[NEURAL_NETWORK_ARCHITECTURE_V2.md](NEURAL_NETWORK_ARCHITECTURE_V2.md)** for detailed input/output specification.

### Action Space
- **Type**: Discrete (25 actions)
- **Actions**: Select grid coordinate (x, y) where 0 ≤ x, y < 5
- **Action Encoding**: Single integer from 0-24 mapping to grid positions
  - Action `i` → Position `(i // 5, i % 5)`
- **Invalid Actions**: Tiles already revealed (must be masked)

### Reward Structure

**Recommended: Hybrid Approach** (Balances learning speed with goal alignment)

The objective is to **maximize completed animals** with limited moves. A hybrid reward structure provides both:
- **Strong sparse signals** for the true objective (complete animals)
- **Weak dense signals** for exploration guidance (animal tiles)

```python
# Primary reward: Completed animals (10x weight - the actual goal)
reward = +10 * num_animals_completed_this_step

# Secondary reward: Small bonus for revealing animal tiles (exploration aid)
if revealed_tile_is_animal:
    reward += +0.1  # 100x weaker than completing an animal
    
# Penalty: Discourage invalid moves (already-revealed tiles)
if action_invalid:
    reward += -1.0

# Optional efficiency bonus: Reward move conservation
if episode_done and animals_found > 0:
    reward += animals_found * (moves_left / max_moves)
```

**Why This Works:**
- Completing animals is **100x more valuable** than finding individual tiles
- Agent learns to prioritize pattern completion over tile discovery
- Dense component (+0.1) helps early exploration without dominating policy
- Invalid action penalty prevents wasted moves
- Efficiency bonus encourages completing patterns quickly

**Alternative: Pure Sparse** (Cleaner but slower learning)
```python
# Only reward the actual objective
reward = +1 * num_animals_completed_this_step
reward = 0  # All other moves

# Use curriculum learning to accelerate:
# Phase 1: 1 animal, 20 moves (easy to get signal)
# Phase 2: 2-3 animals, 15 moves
# Phase 3: Full difficulty, 10-12 moves
```

**Key Principle:** The primary reward should directly measure what you want to maximize (completed animals), with optional dense signals kept 10-100x weaker to avoid distorting the objective.

### Episode Termination
**Terminal Conditions**:
- `moves_left == 0` → Episode ends
- Optional: All animals found early (bonus condition)

**Episode Reset**:
- New random animal placement
- All tiles reset to unrevealed
- Moves reset to initial count

### Information Structure
**Agent Knows**:
- Which tiles have been revealed
- **Which animal species** each revealed tile belongs to (Animal_0 through Animal_6)
- Number of moves remaining
- Which animals have been completed
- **Probability heatmaps** for each animal (computed from pattern constraints)

**Agent Doesn't Know**:
- Contents of unrevealed tiles
- Which of the 7 possible animals are actually present on this grid
- Exact locations of uncompleted animals

**Note**: Animal patterns are provided to the agent via probability heatmaps computed by a constraint satisfaction engine, not learned by the neural network.

---

## Implementation Strategy

### Phase 1: Simplified Version
Start with constrained problem:
- **Single animal** per grid
- **Known pattern** (agent sees target pattern)
- **Generous moves** (15-20 flips)
- **Simple patterns** (2-3 tiles)

### Phase 2: Progressive Complexity
- Multiple animals (2-3) per grid
- Pattern library (5-10 possible patterns)
- Realistic moves (10-12 flips)
- Medium complexity patterns

### Phase 3: Full Game
- Full animal set (7 per region)
- Complete pattern variety
- Varied move counts by difficulty
- Pattern memorization required

### Key Challenges
1. **Partial Observability**: Agent must infer animal presence from partial reveals
2. **Credit Assignment**: Which tiles contributed to finding an animal?
3. **Exploration vs. Exploitation**: When to search new areas vs. complete known patterns?
4. **Pattern Learning**: Agent must memorize 10-100+ unique patterns
5. **Move Efficiency**: Maximize animals per move spent

### Success Metrics
- **Animals/Episode**: Primary metric
- **Completion Rate**: % of animals found vs. present
- **Efficiency**: Animals found / tiles revealed
- **Wasted Moves**: Tiles revealed with no pattern nearby
