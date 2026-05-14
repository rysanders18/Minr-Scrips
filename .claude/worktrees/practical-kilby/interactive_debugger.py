"""
Interactive Debugger for Disco Zoo RL

Step-through debugger for episodes with interactive REPL.
Allows manual inspection of agent decisions, Q-values, and probabilities.

Usage:
    python interactive_debugger.py --model models/my_model.pt --seed 42
"""

import numpy as np
import argparse
from discoZoo import DiscoZooEnv
from agent import DQNAgent, HeatmapAgent
from debug_tracer import format_grid_ascii, format_heatmap_ascii


class InteractiveDebugger:
    """Interactive step-through debugger for episodes."""

    def __init__(self, env, agent):
        """
        Initialize the debugger.

        Args:
            env: DiscoZooEnv instance
            agent: Agent with select_action method
        """
        self.env = env
        self.agent = agent
        self.obs = None
        self.info = None
        self.step_count = 0
        self.total_reward = 0.0

    def start_episode(self, seed=None):
        """Start a new episode."""
        self.obs, self.info = self.env.reset(seed=seed)
        self.step_count = 0
        self.total_reward = 0.0
        print(f"\n{'='*60}")
        print(f"NEW EPISODE (Seed: {seed})")
        print(f"{'='*60}")
        print(f"Animals present: {self.info['animals_present']}")
        print(f"Max moves: {self.env.max_moves}")
        self.show_state()

    def show_state(self):
        """Display current game state in detail."""
        print(f"\n--- State (Step {self.step_count}) ---")
        print(f"Moves remaining: {self.env.moves_remaining}/{self.env.max_moves}")
        print(f"Animals found: {self.info['animals_found']}/{self.info['animals_present']}")
        print(f"Total reward: {self.total_reward:.2f}")

        print("\nGrid:")
        grid_str = format_grid_ascii(
            self.env.revealed,
            self.env.tile_to_animal,
            [i for i in range(7) if self.env.animals_completed[i]],
            list(self.env.animal_placements.keys())
        )
        print(grid_str)

        # Show scalar features
        scalars = self.obs['scalars']
        print(f"\nScalars: [moves={scalars[0]:.2f}, completions={scalars[1:8].tolist()}, total={scalars[8]:.2f}]")

    def show_q_values(self, top_n=10):
        """Show Q-values for all actions."""
        print(f"\n--- Q-Values (Top {top_n}) ---")

        valid_mask = self.env.get_valid_actions_mask()

        if hasattr(self.agent, 'get_q_values_detailed'):
            q_details = self.agent.get_q_values_detailed(self.obs, valid_mask)

            print(f"Statistics: Mean={q_details['mean_valid']:.3f}, Std={q_details['std_valid']:.3f}")
            print(f"\nRanked by Q-value:")

            for i, item in enumerate(q_details['top_5'][:top_n], 1):
                valid_marker = "✓" if valid_mask[item['action']] else "✗"
                print(f"  {i:2d}. Action {item['action']:2d} (row={item['row']}, col={item['col']}) | "
                      f"Q={item['q_value']:7.3f} {valid_marker}")

            # Show as heatmap
            print("\nQ-Value Heatmap:")
            q_grid = q_details['raw'].reshape(5, 5)
            print(format_heatmap_ascii(q_grid))

        elif hasattr(self.agent, 'get_q_values'):
            q_values = self.agent.get_q_values(self.obs)
            q_grid = q_values.reshape(5, 5)
            print(format_heatmap_ascii(q_grid))
        else:
            print("Agent doesn't support get_q_values()")

    def show_probabilities(self):
        """Show probability heatmaps for each animal."""
        print("\n--- Probability Heatmaps ---")

        grid = self.obs['grid']  # (5, 5, 14)

        # Show max probability across all animals
        prob_channels = grid[:, :, 7:14]
        max_prob = np.max(prob_channels, axis=2)
        print("\nMax Probability (across all animals):")
        print(format_heatmap_ascii(max_prob))

        # Show per-animal probabilities
        print("\nPer-Animal Probabilities:")
        animal_names = ['Pig', 'Sheep', 'Rabbit', 'Horse', 'Cow', 'Unicorn', 'Chicken']

        for animal_idx in range(7):
            prob_map = grid[:, :, 7 + animal_idx]
            max_val = np.max(prob_map)

            # Only show if non-trivial
            if max_val > 0.01:
                print(f"\n  Animal {animal_idx} ({animal_names[animal_idx]}):")
                print(f"  " + "\n  ".join(format_heatmap_ascii(prob_map, width=3).split("\n")))

    def show_confirmed(self):
        """Show confirmed tiles for each animal."""
        print("\n--- Confirmed Tiles ---")

        grid = self.obs['grid']  # (5, 5, 14)
        animal_names = ['Pig', 'Sheep', 'Rabbit', 'Horse', 'Cow', 'Unicorn', 'Chicken']

        for animal_idx in range(7):
            confirmed_map = grid[:, :, animal_idx]
            if np.max(confirmed_map) > 0:
                print(f"\n  Animal {animal_idx} ({animal_names[animal_idx]}):")
                print(f"  " + "\n  ".join(format_heatmap_ascii(confirmed_map, width=1).split("\n")))

    def step(self, action=None):
        """
        Execute one step.

        Args:
            action: Specific action to take (or None to let agent choose)

        Returns:
            True if episode ended, False otherwise
        """
        if action is None:
            # Let agent choose
            valid_mask = self.env.get_valid_actions_mask()
            action = self.agent.select_action(self.obs, valid_mask, epsilon=0.0)
            print(f"\nAgent chose action: {action}")

        # Execute
        next_obs, reward, terminated, truncated, info = self.env.step(action)

        # Display results
        row, col = action // 5, action % 5
        print(f"\n{'='*60}")
        print(f"Action: {action} (row={row}, col={col})")
        print(f"Reward: {reward:+.2f} ({self._interpret_reward(reward)})")
        print(f"{'='*60}")

        self.obs = next_obs
        self.info = info
        self.step_count += 1
        self.total_reward += reward

        if terminated or truncated:
            print("\n=== EPISODE ENDED ===")
            print(f"Final reward: {self.total_reward:.2f}")
            print(f"Animals found: {info['animals_found']}/{info['animals_present']}")
            print(f"Moves used: {self.step_count}/{self.env.max_moves}")
            return True

        return False

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

    def run(self):
        """Interactive REPL loop."""
        print("\n" + "="*60)
        print("INTERACTIVE DISCO ZOO DEBUGGER")
        print("="*60)
        print("\nCommands:")
        print("  s / step         - Take one step (agent chooses)")
        print("  s <N>            - Take action N (specific tile)")
        print("  q / qvalues      - Show Q-values")
        print("  p / prob         - Show probability heatmaps")
        print("  c / confirmed    - Show confirmed tiles")
        print("  g / grid         - Show current grid")
        print("  r / reset [seed] - Reset episode (optional seed)")
        print("  h / help         - Show this help")
        print("  quit / exit      - Exit debugger")

        while True:
            try:
                cmd = input("\n> ").strip().lower()

                if not cmd:
                    continue

                if cmd in ['quit', 'exit']:
                    print("Exiting debugger.")
                    break

                elif cmd in ['h', 'help']:
                    print("\nCommands:")
                    print("  s / step         - Take one step (agent chooses)")
                    print("  s <N>            - Take action N (specific tile)")
                    print("  q / qvalues      - Show Q-values")
                    print("  p / prob         - Show probability heatmaps")
                    print("  c / confirmed    - Show confirmed tiles")
                    print("  g / grid         - Show current grid")
                    print("  r / reset [seed] - Reset episode (optional seed)")
                    print("  quit / exit      - Exit debugger")

                elif cmd in ['s', 'step']:
                    done = self.step()
                    if not done:
                        self.show_state()

                elif cmd.startswith('s '):
                    try:
                        action = int(cmd.split()[1])
                        if 0 <= action < 25:
                            done = self.step(action)
                            if not done:
                                self.show_state()
                        else:
                            print("Error: Action must be 0-24")
                    except ValueError:
                        print("Error: Invalid action number")

                elif cmd in ['q', 'qvalues']:
                    self.show_q_values()

                elif cmd in ['p', 'prob']:
                    self.show_probabilities()

                elif cmd in ['c', 'confirmed']:
                    self.show_confirmed()

                elif cmd in ['g', 'grid']:
                    self.show_state()

                elif cmd.startswith('r') or cmd.startswith('reset'):
                    parts = cmd.split()
                    seed = int(parts[1]) if len(parts) > 1 else None
                    self.start_episode(seed=seed)

                else:
                    print(f"Unknown command: {cmd}. Type 'h' for help.")

            except KeyboardInterrupt:
                print("\nInterrupted. Type 'quit' to exit.")
            except Exception as e:
                print(f"Error: {e}")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Interactive Disco Zoo Debugger')
    parser.add_argument('--model', type=str, default=None,
                       help='Path to trained model (.pt file)')
    parser.add_argument('--agent', type=str, default='dqn', choices=['dqn', 'heatmap'],
                       help='Agent type')
    parser.add_argument('--seed', type=int, default=42,
                       help='Initial random seed')
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

    # Start debugger
    debugger = InteractiveDebugger(env, agent)
    debugger.start_episode(seed=args.seed)
    debugger.run()
