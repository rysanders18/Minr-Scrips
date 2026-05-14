"""
Evaluation and Visualization for Disco Zoo Reinforcement Learning

Provides:
- Agent comparison (DQN vs Random vs Heatmap baselines)
- Performance metrics and statistics
- Episode visualization
- Q-value heatmap visualization
- Training curve plotting

Usage:
    python evaluate.py --model models/final_model.pt --biome farm
    python evaluate.py --compare --episodes 500  # Compare all agents
"""

import argparse
import os
from typing import Dict, List, Optional, Tuple
import json

import numpy as np

# Local imports
from discoZoo import DiscoZooEnv
from agent import DQNAgent, RandomAgent, HeatmapAgent, TORCH_AVAILABLE

# Try to import matplotlib for plotting
try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("Warning: matplotlib not available. Install with: pip install matplotlib")


# =============================================================================
# EVALUATION FUNCTIONS
# =============================================================================

def evaluate_agent(
    env: DiscoZooEnv,
    agent,
    num_episodes: int = 100,
    epsilon: float = 0.0,
    verbose: bool = False
) -> Dict[str, float]:
    """
    Evaluate an agent over multiple episodes.
    
    Args:
        env: The Disco Zoo environment
        agent: Any agent with select_action(state, mask, epsilon) method
        num_episodes: Number of evaluation episodes
        epsilon: Exploration rate during evaluation
        verbose: Whether to print per-episode info
    
    Returns:
        Dict with comprehensive evaluation statistics
    """
    rewards = []
    animals_found = []
    animals_present = []
    tiles_revealed = []
    moves_used = []
    
    for i in range(num_episodes):
        obs, info = env.reset()
        episode_reward = 0.0
        
        while True:
            valid_mask = env.get_valid_actions_mask()
            action = agent.select_action(obs, valid_mask, epsilon)
            obs, reward, terminated, truncated, info = env.step(action)
            episode_reward += reward
            
            if terminated or truncated:
                break
        
        rewards.append(episode_reward)
        animals_found.append(info['animals_found'])
        animals_present.append(info['animals_present'])
        tiles_revealed.append(info['tiles_revealed'])
        moves_used.append(info['moves_used'])
        
        if verbose:
            print(f"Episode {i+1}: Reward={episode_reward:.2f}, "
                  f"Animals={info['animals_found']}/{info['animals_present']}")
    
    return {
        'mean_reward': np.mean(rewards),
        'std_reward': np.std(rewards),
        'min_reward': np.min(rewards),
        'max_reward': np.max(rewards),
        'mean_animals': np.mean(animals_found),
        'std_animals': np.std(animals_found),
        'total_animals_found': sum(animals_found),
        'total_animals_present': sum(animals_present),
        'completion_rate': sum(animals_found) / sum(animals_present) if sum(animals_present) > 0 else 0.0,
        'mean_tiles': np.mean(tiles_revealed),
        'efficiency': sum(animals_found) / sum(tiles_revealed) if sum(tiles_revealed) > 0 else 0.0,
        'rewards': rewards,
        'animals': animals_found,
    }


def compare_agents(
    biome: str = 'farm',
    num_animals: int = 3,
    max_moves: int = 15,
    num_episodes: int = 500,
    dqn_model_path: Optional[str] = None,
    verbose: bool = True
) -> Dict[str, Dict[str, float]]:
    """
    Compare DQN agent against baselines.
    
    Args:
        biome: Biome to evaluate on
        num_animals: Number of animals per episode
        max_moves: Maximum moves per episode
        num_episodes: Number of evaluation episodes per agent
        dqn_model_path: Path to trained DQN model (optional)
        verbose: Whether to print results
    
    Returns:
        Dict mapping agent name to evaluation stats
    """
    env = DiscoZooEnv(biome=biome, num_animals=num_animals, max_moves=max_moves)
    
    results = {}
    
    # Random baseline
    if verbose:
        print("Evaluating Random Agent...")
    random_agent = RandomAgent()
    results['Random'] = evaluate_agent(env, random_agent, num_episodes)
    
    # Heatmap baseline
    if verbose:
        print("Evaluating Heatmap Agent...")
    heatmap_agent = HeatmapAgent()
    results['Heatmap'] = evaluate_agent(env, heatmap_agent, num_episodes)
    
    # DQN agent (if available)
    if TORCH_AVAILABLE and dqn_model_path is not None and os.path.exists(dqn_model_path):
        if verbose:
            print("Evaluating DQN Agent...")
        dqn_agent = DQNAgent()
        dqn_agent.load(dqn_model_path)
        results['DQN'] = evaluate_agent(env, dqn_agent, num_episodes)
    elif TORCH_AVAILABLE:
        # Untrained DQN for comparison
        if verbose:
            print("Evaluating Untrained DQN Agent...")
        dqn_agent = DQNAgent()
        results['DQN (untrained)'] = evaluate_agent(env, dqn_agent, num_episodes)
    
    env.close()
    
    if verbose:
        print("\n" + "=" * 70)
        print("AGENT COMPARISON RESULTS")
        print("=" * 70)
        print(f"{'Agent':<20} {'Reward':>10} {'Animals':>10} {'Completion':>12} {'Efficiency':>12}")
        print("-" * 70)
        
        for name, stats in results.items():
            print(f"{name:<20} "
                  f"{stats['mean_reward']:>10.2f} "
                  f"{stats['mean_animals']:>10.2f} "
                  f"{stats['completion_rate']:>11.1%} "
                  f"{stats['efficiency']:>12.3f}")
        
        print("-" * 70)
        
        # Compute performance ratios
        random_animals = results['Random']['mean_animals']
        if random_animals > 0:
            print("\nPerformance vs Random:")
            for name, stats in results.items():
                if name != 'Random':
                    ratio = stats['mean_animals'] / random_animals
                    print(f"  {name}: {ratio:.2f}x")
    
    return results


def run_single_episode(
    biome: str = 'farm',
    num_animals: int = 3,
    max_moves: int = 15,
    model_path: Optional[str] = None,
    agent_type: str = 'dqn',
    seed: Optional[int] = None,
    verbose: bool = True
) -> Dict:
    """
    Run a single episode with detailed step-by-step output.
    
    Args:
        biome: Biome to use
        num_animals: Number of animals
        max_moves: Maximum moves
        model_path: Path to DQN model (required if agent_type='dqn')
        agent_type: 'dqn', 'random', or 'heatmap'
        seed: Random seed for reproducibility
        verbose: Whether to print each step
    
    Returns:
        Dict with episode details
    """
    env = DiscoZooEnv(biome=biome, num_animals=num_animals, max_moves=max_moves, render_mode='human' if verbose else None)
    
    # Create agent
    if agent_type == 'dqn':
        if not TORCH_AVAILABLE:
            raise ImportError("PyTorch required for DQN agent")
        agent = DQNAgent()
        if model_path and os.path.exists(model_path):
            agent.load(model_path)
        epsilon = 0.0
    elif agent_type == 'heatmap':
        agent = HeatmapAgent()
        epsilon = 0.0
    else:  # random
        agent = RandomAgent()
        epsilon = 1.0
    
    obs, info = env.reset(seed=seed)
    
    if verbose:
        print(f"\n{'='*60}")
        print(f"Single Episode - {agent_type.upper()} Agent")
        print(f"Biome: {biome}, Animals: {num_animals}, Moves: {max_moves}")
        print(f"{'='*60}\n")
        env.render()
    
    history = []
    total_reward = 0.0
    step = 0
    
    while True:
        valid_mask = env.get_valid_actions_mask()
        action = agent.select_action(obs, valid_mask, epsilon)
        row, col = action // 5, action % 5
        
        obs, reward, terminated, truncated, info = env.step(action)
        total_reward += reward
        step += 1
        
        history.append({
            'step': step,
            'action': action,
            'position': (row, col),
            'reward': reward,
            'animals_found': info['animals_found'],
        })
        
        if verbose:
            reward_str = f"+{reward:.1f}" if reward >= 0 else f"{reward:.1f}"
            print(f"Step {step}: ({row}, {col}) -> {reward_str}")
        
        if terminated or truncated:
            break
    
    if verbose:
        print(f"\n{'='*60}")
        print("FINAL STATE")
        env.render()
        print(f"\nTotal Reward: {total_reward:.2f}")
        print(f"Animals Found: {info['animals_found']}/{info['animals_present']}")
        print(f"{'='*60}")
    
    env.close()
    
    return {
        'total_reward': total_reward,
        'animals_found': info['animals_found'],
        'animals_present': info['animals_present'],
        'moves_used': info['moves_used'],
        'history': history,
    }


# =============================================================================
# VISUALIZATION FUNCTIONS
# =============================================================================

def plot_comparison(
    results: Dict[str, Dict[str, float]],
    save_path: Optional[str] = None
):
    """
    Plot bar chart comparing agent performance.
    
    Args:
        results: Dict from compare_agents()
        save_path: Path to save figure (optional)
    """
    if not MATPLOTLIB_AVAILABLE:
        print("matplotlib required for plotting")
        return
    
    agents = list(results.keys())
    metrics = ['mean_reward', 'mean_animals', 'completion_rate']
    
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    
    colors = plt.cm.Set2(np.linspace(0, 1, len(agents)))
    
    for i, metric in enumerate(metrics):
        values = [results[a][metric] for a in agents]
        bars = axes[i].bar(agents, values, color=colors)
        axes[i].set_title(metric.replace('_', ' ').title())
        axes[i].set_ylabel('Value')
        
        # Add value labels on bars
        for bar, val in zip(bars, values):
            height = bar.get_height()
            axes[i].annotate(f'{val:.2f}',
                           xy=(bar.get_x() + bar.get_width() / 2, height),
                           xytext=(0, 3),
                           textcoords="offset points",
                           ha='center', va='bottom')
    
    plt.suptitle('Agent Comparison', fontsize=14, fontweight='bold')
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"Saved comparison plot to {save_path}")
    
    plt.show()


def plot_reward_distribution(
    results: Dict[str, Dict[str, float]],
    save_path: Optional[str] = None
):
    """
    Plot reward distribution for each agent.
    
    Args:
        results: Dict from compare_agents() with 'rewards' key
        save_path: Path to save figure (optional)
    """
    if not MATPLOTLIB_AVAILABLE:
        print("matplotlib required for plotting")
        return
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    data = []
    labels = []
    
    for agent, stats in results.items():
        if 'rewards' in stats:
            data.append(stats['rewards'])
            labels.append(agent)
    
    ax.boxplot(data, labels=labels)
    ax.set_ylabel('Episode Reward')
    ax.set_title('Reward Distribution by Agent')
    ax.grid(True, alpha=0.3)
    
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"Saved distribution plot to {save_path}")
    
    plt.show()


def plot_training_history(
    history_path: str,
    save_path: Optional[str] = None
):
    """
    Plot training curves from saved history.
    
    Args:
        history_path: Path to training_history.json
        save_path: Path to save figure (optional)
    """
    if not MATPLOTLIB_AVAILABLE:
        print("matplotlib required for plotting")
        return
    
    with open(history_path, 'r') as f:
        history = json.load(f)
    
    num_phases = len(history)
    fig, axes = plt.subplots(num_phases, 2, figsize=(14, 4 * num_phases))
    
    if num_phases == 1:
        axes = [axes]
    
    for i, (phase, data) in enumerate(history.items()):
        # Smooth rewards
        rewards = np.array(data['rewards'])
        window = min(100, len(rewards) // 10)
        if window > 1:
            smoothed = np.convolve(rewards, np.ones(window)/window, mode='valid')
        else:
            smoothed = rewards
        
        axes[i][0].plot(smoothed, label='Reward (smoothed)')
        axes[i][0].set_xlabel('Episode')
        axes[i][0].set_ylabel('Reward')
        axes[i][0].set_title(f'Phase {phase} - Training Reward')
        axes[i][0].legend()
        axes[i][0].grid(True, alpha=0.3)
        
        # Animals found
        animals = np.array(data['animals'])
        if window > 1:
            smoothed_animals = np.convolve(animals, np.ones(window)/window, mode='valid')
        else:
            smoothed_animals = animals
        
        axes[i][1].plot(smoothed_animals, label='Animals (smoothed)', color='green')
        axes[i][1].set_xlabel('Episode')
        axes[i][1].set_ylabel('Animals Found')
        axes[i][1].set_title(f'Phase {phase} - Animals Found')
        axes[i][1].legend()
        axes[i][1].grid(True, alpha=0.3)
    
    plt.suptitle('Training Progress', fontsize=14, fontweight='bold')
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"Saved training plot to {save_path}")
    
    plt.show()


def visualize_q_values(
    agent: DQNAgent,
    state: Dict[str, np.ndarray],
    valid_mask: np.ndarray,
    save_path: Optional[str] = None
):
    """
    Visualize Q-values as a heatmap over the grid.
    
    Args:
        agent: Trained DQN agent
        state: Current observation
        valid_mask: Valid actions mask
        save_path: Path to save figure (optional)
    """
    if not MATPLOTLIB_AVAILABLE:
        print("matplotlib required for plotting")
        return
    
    q_values = agent.get_q_values(state)
    q_grid = q_values.reshape(5, 5)
    
    # Mask invalid actions
    mask_grid = valid_mask.reshape(5, 5)
    q_grid_masked = np.where(mask_grid, q_grid, np.nan)
    
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    
    # Q-values heatmap
    im1 = axes[0].imshow(q_grid_masked, cmap='RdYlGn', aspect='equal')
    axes[0].set_title('Q-Values (valid actions only)')
    plt.colorbar(im1, ax=axes[0])
    
    # Add grid lines
    for i in range(6):
        axes[0].axhline(i - 0.5, color='black', linewidth=0.5)
        axes[0].axvline(i - 0.5, color='black', linewidth=0.5)
    
    # Add text annotations
    for i in range(5):
        for j in range(5):
            if mask_grid[i, j]:
                axes[0].text(j, i, f'{q_grid[i, j]:.2f}',
                           ha='center', va='center', fontsize=8)
            else:
                axes[0].text(j, i, 'X', ha='center', va='center', fontsize=12, color='red')
    
    # Probability heatmap (combined)
    prob_channels = state['grid'][:, :, 7:14]
    combined_prob = np.max(prob_channels, axis=2)
    
    im2 = axes[1].imshow(combined_prob, cmap='Blues', aspect='equal', vmin=0, vmax=1)
    axes[1].set_title('Max Probability Heatmap')
    plt.colorbar(im2, ax=axes[1])
    
    # Add grid lines
    for i in range(6):
        axes[1].axhline(i - 0.5, color='black', linewidth=0.5)
        axes[1].axvline(i - 0.5, color='black', linewidth=0.5)
    
    # Add text annotations
    for i in range(5):
        for j in range(5):
            axes[1].text(j, i, f'{combined_prob[i, j]:.2f}',
                       ha='center', va='center', fontsize=8)
    
    plt.suptitle('Agent Decision Analysis', fontsize=14, fontweight='bold')
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"Saved Q-value plot to {save_path}")
    
    plt.show()


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description='Evaluate Disco Zoo RL Agent')
    parser.add_argument('--model', type=str, default=None,
                        help='Path to trained model')
    parser.add_argument('--biome', type=str, default='farm',
                        help='Biome to evaluate on (default: farm)')
    parser.add_argument('--animals', type=int, default=3,
                        help='Number of animals (default: 3)')
    parser.add_argument('--moves', type=int, default=15,
                        help='Maximum moves (default: 15)')
    parser.add_argument('--episodes', type=int, default=500,
                        help='Number of evaluation episodes (default: 500)')
    parser.add_argument('--compare', action='store_true',
                        help='Compare all agents')
    parser.add_argument('--single', action='store_true',
                        help='Run single episode with visualization')
    parser.add_argument('--trace', action='store_true',
                        help='Trace decisions step-by-step for debugging')
    parser.add_argument('--trace-episodes', type=int, default=1,
                        help='Number of episodes to trace (default: 1)')
    parser.add_argument('--trace-seed', type=int, default=None,
                        help='Seed for reproducible tracing')
    parser.add_argument('--agent', type=str, default='heatmap',
                        choices=['dqn', 'random', 'heatmap'],
                        help='Agent type for single episode (default: heatmap)')
    parser.add_argument('--history', type=str, default=None,
                        help='Path to training_history.json for plotting')
    parser.add_argument('--save-dir', type=str, default='results',
                        help='Directory for saving plots (default: results)')
    
    args = parser.parse_args()

    os.makedirs(args.save_dir, exist_ok=True)

    if args.trace:
        # Trace mode: detailed step-by-step analysis
        from debug_tracer import DecisionTracer

        env = DiscoZooEnv(biome=args.biome, num_animals=args.animals, max_moves=args.moves)

        # Load agent
        if args.agent == 'heatmap':
            agent = HeatmapAgent()
        elif args.agent == 'random':
            agent = RandomAgent()
        else:  # dqn
            if not TORCH_AVAILABLE:
                print("Error: PyTorch not available for DQN agent")
                return
            agent = DQNAgent()
            if args.model:
                agent.load(args.model)
            else:
                print("Warning: Using untrained DQN agent")

        # Trace episodes
        for ep in range(args.trace_episodes):
            print(f"\n{'='*80}")
            print(f"TRACING EPISODE {ep+1}/{args.trace_episodes}")
            print(f"{'='*80}")

            tracer = DecisionTracer(env, agent, verbose=True)
            seed = args.trace_seed if args.trace_seed is not None else (42 + ep)
            summary = tracer.trace_episode(seed=seed, epsilon=0.0)

            # Save log
            log_file = os.path.join(args.save_dir, f'trace_{args.agent}_ep{ep+1}_seed{seed}.json')
            tracer.save_episode_log(log_file)

    elif args.single:
        run_single_episode(
            biome=args.biome,
            num_animals=args.animals,
            max_moves=args.moves,
            model_path=args.model,
            agent_type=args.agent,
            verbose=True
        )
    elif args.history:
        plot_training_history(
            args.history,
            save_path=os.path.join(args.save_dir, 'training_curves.png')
        )
    else:
        results = compare_agents(
            biome=args.biome,
            num_animals=args.animals,
            max_moves=args.moves,
            num_episodes=args.episodes,
            dqn_model_path=args.model,
            verbose=True
        )
        
        if MATPLOTLIB_AVAILABLE:
            plot_comparison(
                results,
                save_path=os.path.join(args.save_dir, 'comparison.png')
            )
            plot_reward_distribution(
                results,
                save_path=os.path.join(args.save_dir, 'distribution.png')
            )


if __name__ == "__main__":
    main()
