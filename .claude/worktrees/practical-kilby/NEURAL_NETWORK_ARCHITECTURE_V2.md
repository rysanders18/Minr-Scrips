# Neural Network Architecture - REVISED
## Biome-Agnostic Design with Minimal Input Representation

---

## Design Principles

### 1. Biome-Agnostic Architecture
The model should work for **ALL Disco Zoo regions** (Farm, Outback, Savanna, Northern, Jungle, etc.) without architecture changes. Each region has **exactly 7 animals** with unique patterns.

### 2. Minimal Representation
Remove redundant channels - if information can be derived from other inputs, don't include it explicitly.

### 3. Pattern-Aware
The probability heatmaps encode pattern knowledge, making the CNN's job easier.

---

## Critical Information Analysis

### What Does the Agent ACTUALLY Know?

#### **At Episode Start:**
1. ✅ **Region/Biome**: Which region we're rescuing from (determines pattern library)
2. ✅ **Animal Slots 0-6**: The 7 possible animals (abstract IDs, not hardcoded species names)
3. ✅ **Animal Patterns**: The exact shape of each animal in this region
4. ✅ **Max Moves**: How many tile flips allowed
5. ❌ **Animal Locations**: Hidden until revealed
6. ❌ **Which animals are present**: Unknown which of the 7 are on this grid

#### **During Gameplay (After Each Tile Flip):**
1. ✅ **Tile Contents**: Empty OR specific animal ID (0-6)
2. ✅ **Completed Animals**: Which animal IDs have been fully found
3. ✅ **Moves Remaining**: How many flips left
4. ❌ **Unrevealed Tiles**: Still hidden

---

## Minimal Input Representation

### Key Insight: What's Redundant?

| Information | Explicit Channel? | Reasoning |
|-------------|-------------------|-----------|
| Animal X tiles revealed | **YES - REQUIRED** | Core information |
| Animal X probability heatmap | **YES - REQUIRED** | Guides exploration |
| Empty tiles | **NO - DERIVABLE** | Empty = revealed AND not in any animal channel |
| Unrevealed tiles | **NO - DERIVABLE** | Unrevealed = NOT revealed as anything |

### Minimal Channel Architecture (14 Channels)

```python
# Works for ANY biome with 7 animals
input_shape = (5, 5, 14)  # Height × Width × Channels

# Channels 0-6: CONFIRMED animal tiles (one per animal slot)
Channel 0: Animal_0 tiles revealed (binary: 0 or 1)
Channel 1: Animal_1 tiles revealed (binary: 0 or 1)
Channel 2: Animal_2 tiles revealed (binary: 0 or 1)
Channel 3: Animal_3 tiles revealed (binary: 0 or 1)
Channel 4: Animal_4 tiles revealed (binary: 0 or 1)
Channel 5: Animal_5 tiles revealed (binary: 0 or 1)
Channel 6: Animal_6 tiles revealed (binary: 0 or 1)

# Channels 7-13: PROBABILITY heatmaps (one per animal slot)
Channel 7:  Animal_0 probability heatmap (continuous: 0.0-1.0)
Channel 8:  Animal_1 probability heatmap (continuous: 0.0-1.0)
Channel 9:  Animal_2 probability heatmap (continuous: 0.0-1.0)
Channel 10: Animal_3 probability heatmap (continuous: 0.0-1.0)
Channel 11: Animal_4 probability heatmap (continuous: 0.0-1.0)
Channel 12: Animal_5 probability heatmap (continuous: 0.0-1.0)
Channel 13: Animal_6 probability heatmap (continuous: 0.0-1.0)
```

### Deriving Removed Information

```python
def derive_empty_tiles(animal_channels, prob_channels):
    """Empty = revealed (prob=0 for all animals) AND not any animal"""
    any_animal = np.max(animal_channels, axis=-1)  # Max across channels 0-6
    any_prob = np.max(prob_channels, axis=-1)      # Max across channels 7-13
    
    # Empty = no animal found AND probability is 0 (we've ruled it out)
    empty = (any_animal == 0) & (any_prob == 0)
    return empty

def derive_unrevealed_mask(animal_channels, prob_channels):
    """Unrevealed = not revealed as animal AND still has probability"""
    any_animal = np.max(animal_channels, axis=-1)
    any_prob = np.max(prob_channels, axis=-1)
    
    # Unrevealed = no animal found AND still has non-zero probability
    unrevealed = (any_animal == 0) & (any_prob > 0)
    return unrevealed

def get_valid_actions(animal_channels, prob_channels):
    """Valid actions = unrevealed tiles only"""
    return derive_unrevealed_mask(animal_channels, prob_channels).flatten()
```

**Total Spatial Input: 5×5×14 = 350 nodes** (down from 400)

### Example State

```python
# After revealing some tiles in Outback region:
# Animal_0 (Kangaroo) at (0,2), (0,3)
# Animal_1 (Koala) at (3,0)
# Empty at (1,1), (2,3) - derived from probability = 0

Channel_0_Animal0 = [
    [0, 0, 1, 1, 0],  # Animal_0 tiles confirmed
    [0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0]
]

Channel_1_Animal1 = [
    [0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0],
    [1, 0, 0, 0, 0],  # Animal_1 tile confirmed
    [0, 0, 0, 0, 0]
]

# Channels 2-6: All zeros (no tiles found for these animals yet)

Channel_7_Animal0_Probability = [
    [0.0, 0.3, 1.0, 1.0, 0.8],  # High prob near confirmed tiles
    [0.0, 0.0, 0.2, 0.2, 0.1],  # (1,1) is 0.0 = confirmed empty
    [0.0, 0.0, 0.0, 0.0, 0.0],
    [0.0, 0.0, 0.0, 0.0, 0.0],
    [0.0, 0.0, 0.0, 0.0, 0.0]
]

# Note: Empty and unrevealed are DERIVED:
# - Empty at (1,1) → ALL probability channels show 0.0, no animal confirmed
# - Unrevealed → not in any animal channel AND at least one prob > 0
```

---

### Scalar Features (Minimal)

```python
scalar_features = [
    moves_remaining,           # Normalized 0-1: e.g., 0.67
    
    # Completion status for each animal slot (7 values)
    animal_0_completed,        # Binary: 0 or 1
    animal_1_completed,        # Binary: 0 or 1
    animal_2_completed,        # Binary: 0 or 1
    animal_3_completed,        # Binary: 0 or 1
    animal_4_completed,        # Binary: 0 or 1
    animal_5_completed,        # Binary: 0 or 1
    animal_6_completed,        # Binary: 0 or 1
    
    total_animals_found,       # Count: 0-7
]
# Total: 9 scalar features
```

**Note**: Partial pattern counts (tiles found per animal) are **redundant** - they can be derived by summing each animal channel.

**Total Input: 350 + 9 = 359 nodes**

---

## Revised Network Architecture

### Full Architecture with Biome-Agnostic Channels

```python
# INPUT LAYER
grid_input = (5, 5, 14)           # 350 nodes (7 animal + 7 probability)
scalar_input = (9,)               # 9 nodes
# Total input: 359 nodes

# CONVOLUTIONAL LAYERS (process spatial grid)
Conv2D(32 filters, 3×3, relu)     # Output: (5, 5, 32)
Conv2D(64 filters, 3×3, relu)     # Output: (5, 5, 64)
Conv2D(64 filters, 3×3, relu)     # Output: (5, 5, 64)

# FLATTEN
Flatten()                          # Output: (1600,)

# CONCATENATE with scalar features
Concatenate()                      # Output: (1609,)

# DENSE LAYERS
Dense(256, relu)                   # Output: (256,)
Dense(128, relu)                   # Output: (128,)

# OUTPUT LAYER
Dense(25, linear)                  # Output: (25,) Q-values for each tile
```

---

## What Each Channel Represents

### Spatial Channels (14 total) - Biome Agnostic

| Channel | Content | Values | Purpose |
|---------|---------|--------|---------|
| 0-6 | Animal_X tiles confirmed | Binary | Track confirmed tiles for each animal slot |
| 7-13 | Animal_X probability | Continuous 0.0-1.0 | Where each animal likely is |

**Derived Information (not stored, computed on-the-fly):**
- **Empty tiles**: All probability channels = 0 AND no animal confirmed
- **Unrevealed tiles**: At least one probability > 0 AND no animal confirmed
- **Valid actions**: Same as unrevealed tiles

### Scalar Features (9 total)

| Feature | Type | Range | Purpose |
|---------|------|-------|---------|
| Moves remaining | Float | 0.0-1.0 | Urgency/time pressure |
| Animal_0 completed | Binary | 0 or 1 | Stop searching for this animal |
| Animal_1 completed | Binary | 0 or 1 | Stop searching for this animal |
| Animal_2 completed | Binary | 0 or 1 | Stop searching for this animal |
| Animal_3 completed | Binary | 0 or 1 | Stop searching for this animal |
| Animal_4 completed | Binary | 0 or 1 | Stop searching for this animal |
| Animal_5 completed | Binary | 0 or 1 | Stop searching for this animal |
| Animal_6 completed | Binary | 0 or 1 | Stop searching for this animal |
| Total found | Integer | 0-7 | Overall progress |

---

## Parameter Count

| Layer | Input | Output | Parameters |
|-------|-------|--------|------------|
| Conv1 (32 filters, 3×3) | (5,5,14) | (5,5,32) | 4,064 |
| Conv2 (64 filters, 3×3) | (5,5,32) | (5,5,64) | 18,432 |
| Conv3 (64 filters, 3×3) | (5,5,64) | (5,5,64) | 36,864 |
| Flatten | (5,5,64) | (1600,) | 0 |
| Concat | (1600,)+(9,) | (1609,) | 0 |
| Dense1 (256) | (1609,) | (256,) | 412,160 |
| Dense2 (128) | (256,) | (128,) | 32,896 |
| Output (25) | (128,) | (25,) | 3,225 |

**Total: ~507,641 parameters**

---

## How Information Flows

### Scenario: Finding a Partial Pattern (Generic Biome)

**Initial State (Episode Start):**
```
Grid: All unrevealed
Moves: 12/12 remaining
Animals completed: None
All probability channels: uniform ~0.5 (any animal could be anywhere)
```

**After First Flip - Tile (2,3) → Animal_0:**
```python
# Update Channel 0 (Animal_0 confirmed tiles)
Channel_0[2][3] = 1

# Update Channel 7 (Animal_0 probability) - spike around hit
Channel_7[2][3] = 1.0  # Confirmed
Channel_7[2][2] = 0.8  # Adjacent - likely part of pattern
Channel_7[2][4] = 0.8  # Adjacent - likely part of pattern
Channel_7[1][3] = 0.6  # One away - possible

# Other probability channels decrease around (2,3)
# (Animal_1 can't also be at a confirmed Animal_0 tile)

# Update scalar features
moves_remaining = 11/12 = 0.92
```

**After Second Flip - Tile (1,1) → Empty:**
```python
# All probability channels at (1,1) go to 0.0
Channel_7[1][1] = 0.0  # No Animal_0 here
Channel_8[1][1] = 0.0  # No Animal_1 here
# ... etc for all probability channels

# This tile is now "empty" (derived: all probs = 0, no animal confirmed)
# Valid action mask excludes (1,1)
```

**If Animal_0 Pattern Completed (e.g., 3 tiles found):**
```python
# Update scalar completion status
animal_0_completed = 1
total_animals_found = 1

# Probability Channel 7 (Animal_0) goes to all zeros
Channel_7[:] = 0.0  # Don't search for Animal_0 anymore

# Network now knows:
# - Animal_0 is found, don't waste moves on it
# - Focus on Animals 1-6
```

---

## Why This Architecture is Better

### Problem with Original Design:
```python
# Old: Single "animal" channel
Channel_Animal = [0,0,1,0,0, 0,0,0,0,0, 0,0,0,0,0, 1,0,0,0,0, 0,0,0,0,0]
#                    ↑                                ↑
#                Animal?                           Animal?
# Agent doesn't know these are DIFFERENT animals!
```

### New Design:
```python
# New: Separate channels per animal slot
Channel_0 = [0,0,1,0,0, 0,0,0,0,0, ...]  # Animal_0 (e.g., Kangaroo)
Channel_1 = [0,0,0,0,0, 0,0,0,0,0, ...]
Channel_2 = [0,0,0,0,0, 0,0,0,0,0, ...]
Channel_3 = [0,0,0,0,0, 0,0,0,0,0, 1, ...]  # Animal_3 (e.g., Crocodile)
# Agent explicitly knows which animal is where!
```

**Benefits:**
1. ✅ **Species Discrimination**: Network knows which partial pattern belongs to which animal
2. ✅ **Pattern Association**: Can learn "Animal_0 pattern is X, Animal_1 pattern is Y"
3. ✅ **Parallel Tracking**: Track multiple incomplete animals simultaneously
4. ✅ **Completion Awareness**: Know when to stop searching for completed animals
5. ✅ **Biome Agnostic**: Same architecture works for Farm, Outback, Jungle, etc.

---

## Pattern Knowledge: Where Does It Come From?

### The Probability Heatmaps Encode Pattern Knowledge!

The probability heatmaps (Channels 7-13) are **not learned by the network** - they are **computed by a separate probability engine** using constraint satisfaction:

```python
def compute_probability_heatmap(grid_state, animal_id, pattern_library):
    """
    Given current confirmed tiles and a pattern shape,
    compute probability each unrevealed tile is part of this animal.
    """
    pattern = pattern_library[animal_id]  # e.g., [(0,0), (0,1), (0,2)]
    heatmap = np.zeros((5, 5))
    
    # For each unrevealed tile
    for row in range(5):
        for col in range(5):
            if is_revealed(row, col):
                continue
                
            # Count valid placements that include this tile
            valid_placements = count_valid_placements(
                pattern, 
                grid_state, 
                must_include=(row, col)
            )
            heatmap[row, col] = valid_placements / total_possible_placements
    
    return heatmap
```

**This means:**
- Pattern knowledge is **external** to the neural network
- The network receives **pre-computed guidance** via probability channels
- Network learns **how to use** the probability information, not the patterns themselves

### Pattern Library Structure (Per Biome)

```python
# Pattern library loaded based on current biome
pattern_libraries = {
    'farm': {
        0: [(0,0), (0,1), (0,2)],           # Pig - horizontal 3
        1: [(0,0), (1,0), (2,0), (2,1)],    # Cow - L-shape
        2: [(0,0), (0,1), (1,0)],           # Sheep - small L
        3: [(0,0), (0,1)],                  # Chicken - 2 tiles
        4: [(0,0), (1,0), (1,1), (2,1)],    # Horse - zigzag
        5: [(0,0), (0,1), (1,1)],           # Rabbit - diagonal
        6: [(0,0), (1,0)],                  # Duck - vertical 2
    },
    'outback': {
        0: [(0,0), (0,1), (0,2), (0,3)],    # Kangaroo - horizontal 4
        1: [(0,0), (1,0)],                  # Koala - vertical 2
        # ... etc
    },
    # ... other biomes
}
```

---

## Complete Input/Output Specification

### INPUT (359 nodes total)

**Spatial Grid (350 nodes)** - Shape: (5, 5, 14)
- Channels 0-6: Confirmed animal tiles per slot (7 × 25 = 175 nodes)
- Channels 7-13: Probability heatmap per animal (7 × 25 = 175 nodes)

**Derived from above (NOT stored):**
- Empty tiles: All probability = 0, no animal confirmed
- Unrevealed tiles: At least one probability > 0, no animal confirmed
- Valid actions: Unrevealed tiles only

**Scalar Features (9 nodes)** - Shape: (9,)
- 1 node: Moves remaining (0.0-1.0)
- 7 nodes: Animal completion flags (binary)
- 1 node: Total animals found (0-7)

### OUTPUT (25 nodes)
- One Q-value per grid position
- Node i = Expected reward for flipping tile at (i//5, i%5)
- Action masking: set Q = -inf for already-revealed tiles

---

## Implementation Code Sketch

```python
import numpy as np
import tensorflow as tf

class DiscoZooState:
    """Biome-agnostic state representation for any Disco Zoo region."""
    
    def __init__(self, num_animals=7, grid_size=5, biome='farm'):
        self.num_animals = num_animals
        self.grid_size = grid_size
        self.biome = biome
        
        # Spatial channels: 7 confirmed + 7 probability = 14 channels
        self.grid = np.zeros((grid_size, grid_size, num_animals * 2))
        
        # Initialize probability channels to uniform prior
        for i in range(num_animals):
            prob_channel = num_animals + i  # Channels 7-13
            self.grid[:, :, prob_channel] = 0.5
        
        # Scalar features
        self.moves_remaining = 1.0  # Normalized
        self.animals_completed = np.zeros(num_animals)
        self.total_found = 0
    
    def reveal_tile(self, row, col, content):
        """
        Update state after revealing a tile.
        content: 'empty' or animal_id (0-6)
        """
        if content == 'empty':
            # Zero out ALL probability channels at this location
            for i in range(self.num_animals):
                prob_channel = self.num_animals + i
                self.grid[row, col, prob_channel] = 0.0
        else:
            # content is animal_id (0-6)
            animal_id = content
            self.grid[row, col, animal_id] = 1  # Confirmed channel
            
            # Update probability based on pattern constraints
            self._update_probabilities(animal_id, row, col)
    
    def _update_probabilities(self, found_animal, row, col):
        """
        After finding an animal tile, update probability heatmaps
        using constraint satisfaction from pattern library.
        """
        # This would call out to the probability engine
        # which knows the pattern shapes for this biome
        pass  # Implementation depends on pattern library
    
    def complete_animal(self, animal_id):
        """Mark animal as completed."""
        self.animals_completed[animal_id] = 1
        self.total_found += 1
        
        # Zero out both confirmed and probability channels
        self.grid[:, :, animal_id] = 0  # Confirmed channel
        self.grid[:, :, self.num_animals + animal_id] = 0  # Probability channel
    
    def get_valid_actions(self):
        """Return mask of valid actions (unrevealed tiles)."""
        # Tile is revealed if: any confirmed channel = 1 OR all probabilities = 0
        confirmed = np.max(self.grid[:, :, :self.num_animals], axis=-1)
        all_prob_zero = np.all(
            self.grid[:, :, self.num_animals:] == 0, 
            axis=-1
        )
        
        # Unrevealed = not confirmed AND not empty (has probability > 0)
        unrevealed = (confirmed == 0) & (~all_prob_zero)
        return unrevealed.flatten()
    
    def get_input_tensor(self):
        """Convert state to network input."""
        # Grid: (5, 5, 14)
        grid_input = self.grid
        
        # Scalar: (9,)
        scalar_input = np.concatenate([
            [self.moves_remaining],
            self.animals_completed,
            [self.total_found]
        ])
        
        return grid_input, scalar_input


def build_network(num_animals=7):
    """Build biome-agnostic DQN network."""
    num_channels = num_animals * 2  # 7 confirmed + 7 probability = 14
    num_scalars = 1 + num_animals + 1  # moves + completions + total = 9
    
    # Grid input
    grid_input = tf.keras.Input(shape=(5, 5, num_channels), name='grid')
    
    # Conv layers
    x = tf.keras.layers.Conv2D(32, 3, padding='same', activation='relu')(grid_input)
    x = tf.keras.layers.Conv2D(64, 3, padding='same', activation='relu')(x)
    x = tf.keras.layers.Conv2D(64, 3, padding='same', activation='relu')(x)
    x = tf.keras.layers.Flatten()(x)
    
    # Scalar input
    scalar_input = tf.keras.Input(shape=(num_scalars,), name='scalar')
    
    # Concatenate
    combined = tf.keras.layers.Concatenate()([x, scalar_input])
    
    # Dense layers
    x = tf.keras.layers.Dense(256, activation='relu')(combined)
    x = tf.keras.layers.Dense(128, activation='relu')(x)
    
    # Output: Q-values for 25 tiles
    q_values = tf.keras.layers.Dense(25, activation='linear', name='q_values')(x)
    
    model = tf.keras.Model(inputs=[grid_input, scalar_input], outputs=q_values)
    return model


def select_action(model, state, epsilon=0.1):
    """Epsilon-greedy action selection with masking."""
    grid, scalar = state.get_input_tensor()
    
    # Get Q-values
    q_values = model.predict([grid[np.newaxis], scalar[np.newaxis]])[0]
    
    # Mask invalid actions
    valid_mask = state.get_valid_actions()
    q_values[~valid_mask] = -np.inf
    
    # Epsilon-greedy
    if np.random.random() < epsilon:
        valid_actions = np.where(valid_mask)[0]
        return np.random.choice(valid_actions)
    else:
        return np.argmax(q_values)
```

---

## Summary

### Final Architecture (Minimal & Biome-Agnostic)

| Component | Size | Description |
|-----------|------|-------------|
| **Spatial Input** | (5, 5, 14) = 350 | 7 confirmed + 7 probability channels |
| **Scalar Input** | (9,) | Moves + 7 completions + total found |
| **Total Input** | 359 nodes | |
| **Output** | 25 nodes | Q-value per tile |
| **Parameters** | ~507k | |

### Key Design Decisions:

1. ✅ **Biome-Agnostic**: Uses generic "Animal_0-6" slots, not hardcoded species
2. ✅ **Minimal Representation**: Removed redundant empty/unrevealed channels
3. ✅ **Per-Animal Probability**: 7 separate heatmaps guide exploration
4. ✅ **External Pattern Knowledge**: Probabilities computed by constraint engine, not learned
5. ✅ **Derived Valid Actions**: Computed from channels, not stored separately

This architecture works identically for Farm, Outback, Savanna, Jungle, and all other Disco Zoo regions! 🎯
