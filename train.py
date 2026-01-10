"""
Training Loop for Disco Zoo Reinforcement Learning

Implements:
- DQN training with experience replay
- Curriculum learning (progressive difficulty)
- Epsilon decay scheduling
- Periodic evaluation and logging
- Model checkpointing

Usage:
    python train.py                           # Train with default settings
    python train.py --biome outback --phases 1,2  # Train specific biome/phases
    python train.py --load models/checkpoint.pt  # Resume training
"""

import argparse
import os
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import json

import numpy as np

# Local imports
from discoZoo import DiscoZooEnv
from agent import DQNAgent, RandomAgent, HeatmapAgent, TORCH_AVAILABLE

# Try to import tensorboard for logging
try:
    from torch.utils.tensorboard import SummaryWriter
    TENSORBOARD_AVAILABLE = True
except ImportError:
    TENSORBOARD_AVAILABLE = False
    print("Warning: TensorBoard not available. Install with: pip install tensorboard")


# =============================================================================
# CURRICULUM CONFIGURATION
# =============================================================================

CURRICULUM = {
    1: {
        'num_animals': 1,
        'max_moves': 20,
        'target_episodes': 10000,
        'description': 'Single animal, generous moves (learning basics)'
    },
    2: {
        'num_animals': 2,
        'max_moves': 15,
        'target_episodes': 20000,
        'description': 'Two animals, moderate moves'
    },
    3: {
        'num_animals': 3,
        'max_moves': 12,
        'target_episodes': 50000,
        'description': 'Full game (3 animals, realistic moves)'
    },
    4: {
        'num_animals': 3,
        'max_moves': 10,
        'target_episodes': 100000,
        'description': 'Full difficulty (3 animals, limited moves)'
    }
}


# =============================================================================
# TRAINING FUNCTIONS
# =============================================================================

def train_episode(
    env: DiscoZooEnv,
    agent: DQNAgent,
    epsilon: float
) -> Dict[str, float]:
    """
    Train for one episode.
    
    Args:
        env: The Disco Zoo environment
        agent: The DQN agent
        epsilon: Current exploration rate
    
    Returns:
        Dict with episode statistics
    """
    obs, info = env.reset()
    
    episode_reward = 0.0
    episode_steps = 0
    episode_losses = []
    
    while True:
        # Get valid actions mask
        valid_mask = env.get_valid_actions_mask()
        
        # Select action
        action = agent.select_action(obs, valid_mask, epsilon)
        
        # Take action
        next_obs, reward, terminated, truncated, info = env.step(action)
        done = terminated or truncated
        
        # Get next valid mask for storage
        next_valid_mask = env.get_valid_actions_mask()
        
        # Store transition
        agent.store_transition(obs, action, reward, next_obs, done, next_valid_mask)
        
        # Train
        loss = agent.train_step()
        if loss is not None:
            episode_losses.append(loss)
        
        # Update state
        episode_reward += reward
        episode_steps += 1
        obs = next_obs
        
        if done:
            break
    
    return {
        'reward': episode_reward,
        'steps': episode_steps,
        'animals_found': info['animals_found'],
        'animals_present': info['animals_present'],
        'loss': np.mean(episode_losses) if episode_losses else 0.0,
    }


def evaluate_agent(
    env: DiscoZooEnv,
    agent,
    num_episodes: int = 100,
    epsilon: float = 0.0
) -> Dict[str, float]:
    """
    Evaluate an agent over multiple episodes.
    
    Args:
        env: The Disco Zoo environment
        agent: Any agent with select_action(state, mask, epsilon) method
        num_episodes: Number of evaluation episodes
        epsilon: Exploration rate during evaluation
    
    Returns:
        Dict with evaluation statistics
    """
    total_reward = 0.0
    total_animals = 0
    total_present = 0
    total_steps = 0
    
    for _ in range(num_episodes):
        obs, info = env.reset()
        episode_reward = 0.0
        
        while True:
            valid_mask = env.get_valid_actions_mask()
            action = agent.select_action(obs, valid_mask, epsilon)
            obs, reward, terminated, truncated, info = env.step(action)
            episode_reward += reward
            
            if terminated or truncated:
                break
        
        total_reward += episode_reward
        total_animals += info['animals_found']
        total_present += info['animals_present']
        total_steps += info['moves_used']
    
    return {
        'mean_reward': total_reward / num_episodes,
        'mean_animals': total_animals / num_episodes,
        'completion_rate': total_animals / total_present if total_present > 0 else 0.0,
        'mean_steps': total_steps / num_episodes,
    }


def train_phase(
    agent: DQNAgent,
    phase: int,
    biome: str,
    episodes: int,
    eval_freq: int = 1000,
    save_freq: int = 5000,
    log_freq: int = 100,
    save_dir: str = 'models',
    writer: Optional['SummaryWriter'] = None,
    start_epsilon: float = 1.0,
    end_epsilon: float = 0.01,
    verbose: bool = True
) -> Dict[str, List[float]]:
    """
    Train the agent for one curriculum phase.
    
    Args:
        agent: The DQN agent
        phase: Curriculum phase (1-4)
        biome: Biome to train on
        episodes: Number of episodes to train
        eval_freq: Episodes between evaluations
        save_freq: Episodes between checkpoints
        log_freq: Episodes between console logging
        save_dir: Directory for saving checkpoints
        writer: TensorBoard writer (optional)
        start_epsilon: Starting exploration rate
        end_epsilon: Final exploration rate
        verbose: Whether to print progress
    
    Returns:
        Dict with training history
    """
    config = CURRICULUM[phase]
    
    # Create environment for this phase
    env = DiscoZooEnv(
        biome=biome,
        num_animals=config['num_animals'],
        max_moves=config['max_moves']
    )
    
    # Create evaluation environment
    eval_env = DiscoZooEnv(
        biome=biome,
        num_animals=config['num_animals'],
        max_moves=config['max_moves']
    )
    
    # Epsilon decay
    epsilon_decay = (end_epsilon / start_epsilon) ** (1.0 / episodes)
    epsilon = start_epsilon
    
    # History tracking
    history = {
        'rewards': [],
        'animals': [],
        'losses': [],
        'epsilons': [],
        'eval_rewards': [],
        'eval_animals': [],
    }
    
    # Baselines for comparison
    random_agent = RandomAgent()
    heatmap_agent = HeatmapAgent()
    
    if verbose:
        print(f"\n{'='*60}")
        print(f"Phase {phase}: {config['description']}")
        print(f"Animals: {config['num_animals']}, Moves: {config['max_moves']}")
        print(f"Training for {episodes:,} episodes")
        print(f"{'='*60}")
    
    start_time = time.time()
    
    for episode in range(episodes):
        # Train one episode
        stats = train_episode(env, agent, epsilon)
        
        # Record history
        history['rewards'].append(stats['reward'])
        history['animals'].append(stats['animals_found'])
        history['losses'].append(stats['loss'])
        history['epsilons'].append(epsilon)
        
        # Decay epsilon
        epsilon = max(end_epsilon, epsilon * epsilon_decay)
        
        # TensorBoard logging
        global_step = agent.steps_done
        if writer is not None:
            writer.add_scalar(f'Phase{phase}/Reward', stats['reward'], global_step)
            writer.add_scalar(f'Phase{phase}/Animals', stats['animals_found'], global_step)
            writer.add_scalar(f'Phase{phase}/Loss', stats['loss'], global_step)
            writer.add_scalar(f'Phase{phase}/Epsilon', epsilon, global_step)
        
        # Console logging
        if verbose and (episode + 1) % log_freq == 0:
            recent_reward = np.mean(history['rewards'][-log_freq:])
            recent_animals = np.mean(history['animals'][-log_freq:])
            elapsed = time.time() - start_time
            eps_per_sec = (episode + 1) / elapsed
            
            print(f"Episode {episode+1:6d} | "
                  f"Reward: {recent_reward:6.2f} | "
                  f"Animals: {recent_animals:.2f} | "
                  f"ε: {epsilon:.3f} | "
                  f"EPS: {eps_per_sec:.1f}")
        
        # Evaluation
        if (episode + 1) % eval_freq == 0:
            eval_stats = evaluate_agent(eval_env, agent, num_episodes=50, epsilon=0.0)
            history['eval_rewards'].append(eval_stats['mean_reward'])
            history['eval_animals'].append(eval_stats['mean_animals'])
            
            if writer is not None:
                writer.add_scalar(f'Phase{phase}/Eval/Reward', eval_stats['mean_reward'], global_step)
                writer.add_scalar(f'Phase{phase}/Eval/Animals', eval_stats['mean_animals'], global_step)
                writer.add_scalar(f'Phase{phase}/Eval/CompletionRate', eval_stats['completion_rate'], global_step)
            
            if verbose:
                print(f"  [EVAL] Reward: {eval_stats['mean_reward']:.2f} | "
                      f"Animals: {eval_stats['mean_animals']:.2f} | "
                      f"Completion: {eval_stats['completion_rate']:.1%}")
        
        # Save checkpoint
        if (episode + 1) % save_freq == 0:
            os.makedirs(save_dir, exist_ok=True)
            checkpoint_path = os.path.join(save_dir, f'phase{phase}_episode{episode+1}.pt')
            agent.save(checkpoint_path)
    
    # Final evaluation with baselines
    if verbose:
        print(f"\n{'='*60}")
        print("Final Evaluation (100 episodes each)")
        print(f"{'='*60}")
        
        # DQN Agent
        dqn_stats = evaluate_agent(eval_env, agent, num_episodes=100, epsilon=0.0)
        print(f"DQN Agent:     Reward: {dqn_stats['mean_reward']:6.2f} | Animals: {dqn_stats['mean_animals']:.2f}")
        
        # Random Agent
        random_stats = evaluate_agent(eval_env, random_agent, num_episodes=100)
        print(f"Random Agent:  Reward: {random_stats['mean_reward']:6.2f} | Animals: {random_stats['mean_animals']:.2f}")
        
        # Heatmap Agent
        heatmap_stats = evaluate_agent(eval_env, heatmap_agent, num_episodes=100)
        print(f"Heatmap Agent: Reward: {heatmap_stats['mean_reward']:6.2f} | Animals: {heatmap_stats['mean_animals']:.2f}")
        
        # Performance ratio
        if random_stats['mean_animals'] > 0:
            ratio = dqn_stats['mean_animals'] / random_stats['mean_animals']
            print(f"\nDQN vs Random: {ratio:.2f}x")
    
    env.close()
    eval_env.close()
    
    return history


def train_curriculum(
    biome: str = 'farm',
    phases: List[int] = [1, 2, 3, 4],
    save_dir: str = 'models',
    log_dir: str = 'logs',
    resume_from: Optional[str] = None,
    verbose: bool = True
) -> DQNAgent:
    """
    Train agent through full curriculum.
    
    Args:
        biome: Biome to train on
        phases: List of curriculum phases to train (1-4)
        save_dir: Directory for model checkpoints
        log_dir: Directory for TensorBoard logs
        resume_from: Path to checkpoint to resume from
        verbose: Whether to print progress
    
    Returns:
        Trained DQN agent
    """
    if not TORCH_AVAILABLE:
        raise ImportError("PyTorch is required. Install with: pip install torch")
    
    # Create agent
    agent = DQNAgent()
    
    # Resume from checkpoint if specified
    if resume_from is not None:
        agent.load(resume_from)
        if verbose:
            print(f"Resumed from {resume_from}")
    
    # Set up TensorBoard
    writer = None
    if TENSORBOARD_AVAILABLE:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        run_dir = os.path.join(log_dir, f'{biome}_{timestamp}')
        writer = SummaryWriter(run_dir)
        if verbose:
            print(f"TensorBoard logs: {run_dir}")
    
    # Train each phase
    all_history = {}
    
    for phase in phases:
        if phase not in CURRICULUM:
            print(f"Warning: Unknown phase {phase}, skipping")
            continue
        
        history = train_phase(
            agent=agent,
            phase=phase,
            biome=biome,
            episodes=CURRICULUM[phase]['target_episodes'],
            save_dir=save_dir,
            writer=writer,
            verbose=verbose
        )
        all_history[phase] = history
    
    # Save final model
    os.makedirs(save_dir, exist_ok=True)
    final_path = os.path.join(save_dir, 'final_model.pt')
    agent.save(final_path)
    
    # Save training history
    history_path = os.path.join(save_dir, 'training_history.json')
    with open(history_path, 'w') as f:
        # Convert numpy arrays to lists for JSON serialization
        json_history = {}
        for phase, hist in all_history.items():
            json_history[str(phase)] = {k: [float(v) for v in vals] for k, vals in hist.items()}
        json.dump(json_history, f)
    
    if writer is not None:
        writer.close()
    
    if verbose:
        print(f"\n{'='*60}")
        print("Training Complete!")
        print(f"Final model saved to: {final_path}")
        print(f"History saved to: {history_path}")
        print(f"{'='*60}")
    
    return agent


# =============================================================================
# QUICK TRAINING MODE
# =============================================================================

def quick_train(
    biome: str = 'farm',
    episodes: int = 1000,
    num_animals: int = 3,
    max_moves: int = 15,
    verbose: bool = True
) -> DQNAgent:
    """
    Quick training for testing/debugging.
    
    Args:
        biome: Biome to train on
        episodes: Number of episodes
        num_animals: Number of animals per episode
        max_moves: Maximum moves per episode
        verbose: Whether to print progress
    
    Returns:
        Trained agent
    """
    if not TORCH_AVAILABLE:
        raise ImportError("PyTorch is required. Install with: pip install torch")
    
    agent = DQNAgent()
    env = DiscoZooEnv(biome=biome, num_animals=num_animals, max_moves=max_moves)
    
    epsilon = 1.0
    epsilon_decay = 0.995
    epsilon_min = 0.01
    
    if verbose:
        print(f"Quick training: {episodes} episodes, {num_animals} animals, {max_moves} moves")
    
    for episode in range(episodes):
        stats = train_episode(env, agent, epsilon)
        epsilon = max(epsilon_min, epsilon * epsilon_decay)
        
        if verbose and (episode + 1) % 100 == 0:
            print(f"Episode {episode+1}: Reward={stats['reward']:.2f}, Animals={stats['animals_found']}, eps={epsilon:.3f}")
    
    env.close()
    return agent


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description='Train Disco Zoo RL Agent')
    parser.add_argument('--biome', type=str, default='farm',
                        help='Biome to train on (default: farm)')
    parser.add_argument('--phases', type=str, default='1,2,3,4',
                        help='Comma-separated list of phases to train (default: 1,2,3,4)')
    parser.add_argument('--save-dir', type=str, default='models',
                        help='Directory for model checkpoints (default: models)')
    parser.add_argument('--log-dir', type=str, default='logs',
                        help='Directory for TensorBoard logs (default: logs)')
    parser.add_argument('--load', type=str, default=None,
                        help='Path to checkpoint to resume from')
    parser.add_argument('--quick', action='store_true',
                        help='Quick training mode for testing (1000 episodes)')
    parser.add_argument('--episodes', type=int, default=1000,
                        help='Episodes for quick training mode (default: 1000)')
    
    args = parser.parse_args()
    
    if args.quick:
        agent = quick_train(biome=args.biome, episodes=args.episodes)
    else:
        phases = [int(p) for p in args.phases.split(',')]
        agent = train_curriculum(
            biome=args.biome,
            phases=phases,
            save_dir=args.save_dir,
            log_dir=args.log_dir,
            resume_from=args.load
        )
    
    print("\nTraining complete!")


if __name__ == "__main__":
    main()
