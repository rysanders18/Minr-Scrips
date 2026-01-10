# Disco Zoo Reinforcement Learning

An AI agent trained using Deep Q-Network (DQN) to play Disco Zoo's rescue puzzle game.

## 🎮 Game Overview

Disco Zoo is a puzzle game where players reveal tiles on a 5×5 grid to discover hidden animals. Each animal occupies a unique geometric pattern (2-4 tiles). The goal is to complete as many animal patterns as possible before running out of moves.

## 🏗️ Project Structure

```
├── pattern_library.py      # Animal patterns for all biomes
├── probability_engine.py   # Constraint satisfaction for probability heatmaps
├── discoZoo.py            # Gymnasium environment implementation
├── agent.py               # DQN agent with CNN architecture
├── train.py               # Training loop with curriculum learning
├── evaluate.py            # Evaluation and visualization
├── requirements.txt       # Python dependencies
├── tests/                 # Unit tests
│   ├── test_environment.py
│   └── test_probability.py
├── models/                # Saved model checkpoints (created during training)
├── logs/                  # TensorBoard logs (created during training)
└── results/               # Evaluation plots (created during evaluation)
```

## 🚀 Quick Start

### Installation

```bash
pip install -r requirements.txt
```

### Run a Single Episode (with visualization)

```bash
python evaluate.py --single --agent heatmap
```

### Compare Agents

```bash
python evaluate.py --compare --episodes 500
```

### Quick Training (test mode)

```bash
python train.py --quick --episodes 1000
```

### Full Curriculum Training

```bash
python train.py --biome farm --phases 1,2,3,4
```

## 🧠 Architecture

### State Representation
- **Grid**: (5, 5, 14) tensor
  - Channels 0-6: Confirmed tiles for each animal (binary)
  - Channels 7-13: Probability heatmaps for each animal (0.0-1.0)
- **Scalars**: (9,) vector
  - `[0]`: Moves remaining (normalized)
  - `[1-7]`: Completion flags for each animal
  - `[8]`: Total animals found (normalized)

### Neural Network (DQN)
- 3 Convolutional layers (32, 64, 64 filters)
- Flatten + concatenate scalars
- 2 Dense layers (256, 128)
- Output: 25 Q-values (one per tile)
- **Total parameters**: ~507,000

### Reward Structure
- **+10.0**: Complete an animal (all pattern tiles revealed)
- **+0.1**: Find an animal tile (partial discovery)
- **-1.0**: Invalid action (re-reveal same tile)
- **0.0**: Reveal empty tile

## 📊 Baseline Performance (3 animals, 15 moves)

| Agent | Animals/Episode | Completion Rate |
|-------|-----------------|-----------------|
| Random | 0.27 | 9.3% |
| Heatmap | 1.69 | 57.7% |
| DQN (trained) | TBD | TBD |

## 🗺️ Supported Biomes

- Farm, Outback, Savanna, Northern
- Polar, Jungle, Jurassic, Ice Age

Each biome has 7 unique animals with different patterns.

## 📈 Curriculum Learning

| Phase | Animals | Moves | Description |
|-------|---------|-------|-------------|
| 1 | 1 | 20 | Single animal, generous moves |
| 2 | 3 | 15 | Multiple animals, moderate moves |
| 3 | 5 | 12 | Most animals, realistic moves |
| 4 | 7 | 10 | Full difficulty |

## 🧪 Testing

```bash
python -m pytest tests/ -v
```

## 📖 Documentation

- [Game Rules](DISCO_ZOO_RULES.md) - Detailed game mechanics
- [Network Architecture](NEURAL_NETWORK_ARCHITECTURE_V2.md) - Full architecture spec
- [Development Prompt](AGENTIC_DEVELOPMENT_PROMPT.md) - Implementation guide

## 📜 License

MIT License
