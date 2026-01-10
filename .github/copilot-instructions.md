# Disco Zoo Reinforcement Learning Project

## Project Overview
This is a reinforcement learning (RL) project to train an AI agent to play Disco Zoo, a puzzle game where players uncover hidden animals on a grid.

## Project Status
⚠️ **Early Development** - Core implementation needed.

## Game Rules Reference
📖 See **[DISCO_ZOO_RULES.md](../DISCO_ZOO_RULES.md)** for comprehensive game mechanics, rules, and RL implementation considerations.

## Architecture Expectations

### Game Environment (`discoZoo.py`)
The main file should implement:
- **Game State**: Grid-based puzzle environment where animals are hidden in patterns
- **Action Space**: Grid coordinates to reveal (x, y positions)
- **Reward System**: +10 for completing animals, +0.1 for animal tiles, -1 for invalid moves
- **Episode Management**: Reset, step, and termination conditions

### Recommended Structure
```
discoZoo.py           # Main game environment (OpenAI Gym-style interface)
agent.py              # RL agent implementation (DQN, PPO, or similar)
train.py              # Training loop and hyperparameters
evaluate.py           # Model evaluation and visualization
models/               # Saved model checkpoints
logs/                 # Training metrics and TensorBoard logs
```

## Development Conventions

### Environment Interface
Follow OpenAI Gym/Gymnasium standards:
- `reset()` → returns initial observation
- `step(action)` → returns (observation, reward, done, info)
- `render()` → optional visualization

### Dependencies
Typical stack for RL projects:
- `gymnasium` or `gym` for environment interface
- `numpy` for grid/state representation
- `torch` or `tensorflow` for neural networks
- `stable-baselines3` (optional) for pre-built RL algorithms

### State Representation
Consider representing the game state as:
- 2D grid showing revealed/unrevealed cells
- Current score and remaining moves
- Animal patterns as observation or learned internally

### Testing Workflow
- Test game mechanics manually with random actions first
- Verify reward signals align with game objectives
- Validate episode termination conditions
- Profile training performance (episodes/second)

## Key Decisions Needed
- Which RL algorithm? (DQN for discrete actions, PPO for flexibility)
- State representation: raw grid or feature-engineered?
- Reward shaping: sparse (only on animal discovery) or dense (per-step feedback)?
- Training approach: from scratch or using pre-trained models?

## Getting Started
1. Implement basic Disco Zoo game logic in `discoZoo.py`
2. Add unit tests for game mechanics
3. Create a random agent baseline
4. Implement chosen RL algorithm
5. Set up training pipeline with logging

---
*This file should be updated as the project architecture solidifies.*
