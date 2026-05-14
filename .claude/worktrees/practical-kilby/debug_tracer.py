"""
Decision Tracer for Disco Zoo RL Debugging

Traces every decision in an episode with full context:
- Q-values for all actions
- Probability heatmaps
- Chosen action and reasoning
- Reward outcomes
- Episode-level statistics

Usage:
    from debug_tracer import DecisionTracer
    from discoZoo import DiscoZooEnv
    from agent import DQNAgent

    env = DiscoZooEnv(biome='farm', num_animals=3, max_moves=15)
    agent = DQNAgent()
    agent.load('models/my_model.pt')

    tracer = DecisionTracer(env, agent, verbose=True)
    summary = tracer.trace_episode(seed=42, epsilon=0.0)
"""

import numpy as np
import json
from typing import Dict, List, Optional, Tuple, Any
from scipy.stats import spearmanr


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def format_grid_ascii(revealed, tile_to_animal, animals_completed, animals_present):
    """
    Create ASCII art grid showing current game state.

    Legend:
        . = Unrevealed
        _ = Revealed empty
        0-6 = Revealed animal tile (animal index)
        * = Completed animal tile
    """
    lines = []
    for row in range(5):
        row_str = ""
        for col in range(5):
            if not revealed[row, col]:
                row_str += " ."
            else:
                tile = (row, col)
                animal_idx = tile_to_animal.get(tile)
                if animal_idx is None:
                    row_str += " _"
                elif animal_idx in animals_completed and animal_idx in animals_present:
                    row_str += " *"
                else:
                    row_str += f" {animal_idx}"
        lines.append(row_str)
    return "\n".join(lines)


def get_top_k_actions(values, k=5):
    """
    Get top K actions with their row/col and values.

    Returns list of dicts with 'action', 'row', 'col', 'value'
    """
    valid_indices = np.where(np.isfinite(values))[0]
    if len(valid_indices) == 0:
        return []

    valid_values = values[valid_indices]
    sorted_indices = valid_indices[np.argsort(valid_values)[::-1]]

    results = []
    for idx in sorted_indices[:min(k, len(sorted_indices))]:
        results.append({
            'action': int(idx),
            'row': int(idx // 5),
            'col': int(idx % 5),
            'value': float(values[idx])
        })

    return results


def compute_alignment_score(q_values, probabilities, valid_mask):
    """
    Measure how well Q-values align with probability heatmaps.

    Uses Spearman rank correlation on valid actions only.
    Returns correlation coefficient (-1 to 1).
    """
    valid_indices = np.where(valid_mask)[0]
    if len(valid_indices) < 2:
        return 0.0

    q_valid = q_values[valid_indices]
    p_valid = probabilities[valid_indices]

    # Check if all values are the same
    if np.std(q_valid) == 0 or np.std(p_valid) == 0:
        return 0.0

    try:
        corr, _ = spearmanr(q_valid, p_valid)
        return float(corr) if not np.isnan(corr) else 0.0
    except:
        return 0.0


def format_heatmap_ascii(values, highlight_pos=None, width=4):
    """Format a 5x5 heatmap as ASCII with optional highlight."""
    lines = []
    for row in range(5):
        row_str = ""
        for col in range(5):
            val = values[row, col]
            if highlight_pos and (row, col) == highlight_pos:
                row_str += f"[{val:>{width}.2f}]"
            else:
                row_str += f" {val:>{width}.2f} "
        lines.append(row_str)
    return "\n".join(lines)


# =============================================================================
# DECISION TRACER CLASS
# =============================================================================

class DecisionTracer:
    """
    Traces and logs every decision in an episode.

    Provides detailed step-by-step analysis of agent decisions including:
    - Q-values vs probability heatmaps
    - Action selection reasoning
    - Reward outcomes
    - Episode-level statistics
    """

    def __init__(self, env, agent, verbose=True, save_log=True):
        """
        Initialize the decision tracer.

        Args:
            env: DiscoZooEnv instance
            agent: Agent with select_action and get_q_values methods
            verbose: Whether to print step details to console
            save_log: Whether to save episode log to JSON
        """
        self.env = env
        self.agent = agent
        self.verbose = verbose
        self.save_log = save_log
        self.step_log = []
        self.episode_summary = {}

    def trace_episode(self, seed=None, epsilon=0.0):
        """
        Run one episode with full decision tracing.

        Args:
            seed: Random seed for reproducibility
            epsilon: Exploration rate (0.0 = fully greedy)

        Returns:
            Dict with episode summary statistics
        """
        # Reset episode
        obs, info = self.env.reset(seed=seed)
        self.step_log = []
        step_num = 0

        if self.verbose:
            print(f"\n{'='*80}")
            print(f"EPISODE START (Seed: {seed}, Epsilon: {epsilon:.3f})")
            print(f"Animals present: {info['animals_present']}")
            print(f"Max moves: {self.env.max_moves}")
            print(f"{'='*80}\n")

        # Run episode
        while True:
            step_num += 1

            # Get valid actions
            valid_mask = self.env.get_valid_actions_mask()

            # Get Q-values (with detailed analysis if agent supports it)
            if hasattr(self.agent, 'get_q_values_detailed'):
                q_details = self.agent.get_q_values_detailed(obs, valid_mask)
                q_values = q_details['raw']
            else:
                q_values = self.agent.get_q_values(obs) if hasattr(self.agent, 'get_q_values') else np.zeros(25)
                q_details = None

            # Select action
            import random
            chosen_randomly = random.random() < epsilon
            if chosen_randomly:
                valid_indices = np.where(valid_mask)[0]
                action = int(np.random.choice(valid_indices)) if len(valid_indices) > 0 else 0
            else:
                action = self.agent.select_action(obs, valid_mask, epsilon=0.0)

            # Execute step
            next_obs, reward, terminated, truncated, info = self.env.step(action)
            done = terminated or truncated

            # Log this step
            self.log_step(step_num, obs, q_values, q_details, valid_mask, action,
                         reward, chosen_randomly, info, done)

            # Display step if verbose
            if self.verbose:
                self.display_step(self.step_log[-1])

            # Update for next iteration
            obs = next_obs

            if done:
                break

        # Analyze episode
        self.episode_summary = self.analyze_episode()

        if self.verbose:
            self.display_summary()

        return self.episode_summary

    def log_step(self, step_num, obs, q_values, q_details, valid_mask, action,
                 reward, chosen_randomly, info, done):
        """Log detailed information for one step."""

        # Extract probability heatmaps from observation
        grid = obs['grid']  # (5, 5, 14)
        prob_channels = grid[:, :, 7:14]  # Animal probability channels
        confirmed_channels = grid[:, :, 0:7]  # Confirmed tile channels

        # Max probability across all animals for each tile
        max_prob = np.max(prob_channels, axis=2)  # (5, 5)
        max_prob_flat = max_prob.flatten()

        # Find highest probability tile
        best_prob_action = int(np.argmax(max_prob_flat))
        best_prob_value = float(max_prob_flat[best_prob_action])

        # Compute alignment score
        alignment = compute_alignment_score(q_values, max_prob_flat, valid_mask)

        step_data = {
            'step': step_num,
            'moves_remaining': info['moves_remaining'],
            'animals_found': info['animals_found'],
            'animals_present': info['animals_present'],
            'action': int(action),
            'action_row': int(action // 5),
            'action_col': int(action % 5),
            'reward': float(reward),
            'chosen_randomly': chosen_randomly,
            'done': done,
            'q_values': q_values.tolist(),
            'q_details': q_details,
            'max_prob_map': max_prob.tolist(),
            'best_prob_action': best_prob_action,
            'best_prob_value': best_prob_value,
            'prob_of_chosen': float(max_prob_flat[action]),
            'alignment_score': alignment,
            'valid_mask': valid_mask.tolist(),
        }

        self.step_log.append(step_data)

    def display_step(self, step_data):
        """Print formatted step information to console."""
        print(f"\nSTEP {step_data['step']} | Moves: {step_data['moves_remaining']}/{self.env.max_moves} | "
              f"Animals: {step_data['animals_found']}/{step_data['animals_present']}")
        print("-" * 80)

        # Current grid state
        print("Current Grid:")
        grid_str = format_grid_ascii(
            self.env.revealed,
            self.env.tile_to_animal,
            [i for i in range(7) if self.env.animals_completed[i]],
            list(self.env.animal_placements.keys())
        )
        print(grid_str)

        # Q-values (top 5)
        if step_data['q_details']:
            print("\nQ-Values (Top 5):")
            for i, item in enumerate(step_data['q_details']['top_5'], 1):
                marker = " <--" if item['action'] == step_data['action'] else ""
                print(f"  {i}. Action {item['action']:2d} (row={item['row']}, col={item['col']}) | "
                      f"Q={item['q_value']:7.3f}{marker}")
            print(f"  Mean: {step_data['q_details']['mean_valid']:.3f}, Std: {step_data['q_details']['std_valid']:.3f}")

        # Probability heatmap
        print("\nProbability Heatmap (Max across animals):")
        max_prob = np.array(step_data['max_prob_map'])
        highlight = (step_data['action_row'], step_data['action_col'])
        print(format_heatmap_ascii(max_prob, highlight_pos=highlight))

        # Best probability action
        best_row, best_col = step_data['best_prob_action'] // 5, step_data['best_prob_action'] % 5
        print(f"\nHighest Probability: Action {step_data['best_prob_action']} "
              f"(row={best_row}, col={best_col}) | P={step_data['best_prob_value']:.3f}")

        # Agent choice
        choice_type = "Random" if step_data['chosen_randomly'] else "Greedy"
        print(f"\nAGENT CHOICE: Action {step_data['action']} "
              f"(row={step_data['action_row']}, col={step_data['action_col']}) | {choice_type}")
        print(f"REWARD: {step_data['reward']:+.1f} ({self._interpret_reward(step_data['reward'])})")

        # Alignment analysis
        agrees = abs(step_data['action'] - step_data['best_prob_action']) == 0
        print(f"\nQ-value agrees with probability: {'YES' if agrees else 'NO'}")
        if not agrees:
            print(f"  Agent picked: P={step_data['prob_of_chosen']:.3f}")
            print(f"  Optimal would be: Action {step_data['best_prob_action']} with P={step_data['best_prob_value']:.3f}")
        print(f"  Alignment score: {step_data['alignment_score']:.3f}")

    def _interpret_reward(self, reward):
        """Human-readable interpretation of reward value."""
        if reward >= 10.0:
            return "Animal completed!"
        elif reward > 0.0:
            return "Partial animal tile found"
        elif reward == 0.0:
            return "Empty tile"
        elif reward < 0.0:
            return "Invalid action (already revealed)"
        return "Unknown"

    def analyze_episode(self):
        """Compute summary statistics for the episode."""
        if not self.step_log:
            return {}

        total_reward = sum(step['reward'] for step in self.step_log)
        last_step = self.step_log[-1]

        # Count optimal moves (agent picked highest probability tile)
        optimal_moves = sum(1 for step in self.step_log
                          if step['action'] == step['best_prob_action'])

        # Count wasted moves (empty tiles when high-probability tiles available)
        wasted_moves = sum(1 for step in self.step_log
                          if step['reward'] == 0.0 and step['best_prob_value'] > 0.3)

        # Average alignment score
        avg_alignment = np.mean([step['alignment_score'] for step in self.step_log])

        # Q-value statistics
        if self.step_log[0]['q_details']:
            avg_q_std = np.mean([step['q_details']['std_valid'] for step in self.step_log
                                if step['q_details'] is not None])
        else:
            avg_q_std = 0.0

        summary = {
            'total_reward': total_reward,
            'animals_found': last_step['animals_found'],
            'animals_present': last_step['animals_present'],
            'moves_used': len(self.step_log),
            'max_moves': self.env.max_moves,
            'optimal_moves': optimal_moves,
            'total_moves': len(self.step_log),
            'optimal_pct': optimal_moves / len(self.step_log) if self.step_log else 0.0,
            'wasted_moves': wasted_moves,
            'alignment_score': avg_alignment,
            'avg_q_std': avg_q_std,
            'completion_rate': last_step['animals_found'] / last_step['animals_present']
                             if last_step['animals_present'] > 0 else 0.0,
        }

        return summary

    def display_summary(self):
        """Print episode summary."""
        s = self.episode_summary
        print(f"\n{'='*80}")
        print("EPISODE SUMMARY")
        print(f"{'='*80}")
        print(f"Reward:               {s['total_reward']:7.2f}")
        print(f"Animals Found:        {s['animals_found']}/{s['animals_present']}")
        print(f"Completion Rate:      {s['completion_rate']:6.1%}")
        print(f"Moves Used:           {s['moves_used']}/{s['max_moves']}")
        print(f"\nDecision Quality:")
        print(f"  Optimal Moves:      {s['optimal_moves']}/{s['total_moves']} ({s['optimal_pct']:.1%})")
        print(f"  Wasted Moves:       {s['wasted_moves']}")
        print(f"  Alignment Score:    {s['alignment_score']:6.3f}")
        print(f"  Avg Q-value Std:    {s['avg_q_std']:6.3f}")
        print(f"{'='*80}\n")

    def save_episode_log(self, filename):
        """Save episode trace to JSON file."""
        if not self.save_log:
            return

        log_data = {
            'episode_summary': self.episode_summary,
            'steps': self.step_log,
        }

        with open(filename, 'w') as f:
            json.dump(log_data, f, indent=2)

        print(f"Episode log saved to: {filename}")


# =============================================================================
# MAIN (Testing)
# =============================================================================

if __name__ == "__main__":
    import argparse
    from discoZoo import DiscoZooEnv
    from agent import DQNAgent, HeatmapAgent

    parser = argparse.ArgumentParser(description='Trace episode decisions')
    parser.add_argument('--model', type=str, default=None,
                       help='Path to trained model (.pt file)')
    parser.add_argument('--agent', type=str, default='dqn', choices=['dqn', 'heatmap'],
                       help='Agent type to trace')
    parser.add_argument('--seed', type=int, default=42,
                       help='Random seed for reproducibility')
    parser.add_argument('--biome', type=str, default='farm',
                       help='Biome to use')
    parser.add_argument('--animals', type=int, default=3,
                       help='Number of animals')
    parser.add_argument('--moves', type=int, default=15,
                       help='Max moves per episode')

    args = parser.parse_args()

    # Create environment
    env = DiscoZooEnv(biome=args.biome, num_animals=args.animals, max_moves=args.moves)

    # Create agent
    if args.agent == 'heatmap':
        agent = HeatmapAgent()
        print("Using HeatmapAgent (optimal baseline)")
    else:
        agent = DQNAgent()
        if args.model:
            agent.load(args.model)
            print(f"Loaded DQN model from {args.model}")
        else:
            print("Warning: Using untrained DQN agent")

    # Trace episode
    tracer = DecisionTracer(env, agent, verbose=True)
    summary = tracer.trace_episode(seed=args.seed, epsilon=0.0)

    # Save log
    tracer.save_episode_log(f'trace_log_{args.agent}_seed{args.seed}.json')
