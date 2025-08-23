import itertools
import numpy as np
import random
from fractions import Fraction
import time

class DiscoZooSolver:
    """
    An AI solver for a Disco Zoo-style puzzle. It uses probability and combinatorial
    analysis to determine the best tile to flip next.
    """
    def __init__(self, grid_size, animal_patterns, selected_animals, testing_mode=False):
        self.grid_size = grid_size
        self.animal_patterns = {a: frozenset(p) for a, p in animal_patterns.items()}
        self.selected_animals = selected_animals
        self.testing_mode = testing_mode

        self.total_animal_tiles = sum(len(animal_patterns[a]) for a in selected_animals)
        
        # --- State Tracking ---
        self.flipped_tiles = {}
        self.confirmed_animals = {}
        self.initial_placements = {a: self.generate_valid_placements(animal_patterns[a]) for a in selected_animals}
        self.flip_count = 0

        # --- Solver Configuration ---
        self.step_bias_config = {
            0: 0.0,   # Early game: Pure information gain.
            1: 0.1,   # Mid game: Slight bias to complete animals.
            2: 0.25   # Late game: Stronger bias.
        }
        # NEW: Weights for the hybrid scoring system. These must sum to 1.0.
        self.INFO_SCORE_WEIGHT = 0.7 # How much to value pure information gain.
        self.HITCHANCE_SCORE_WEIGHT = 0.3 # How much to value raw probability of a hit.


        # --- For Simulation/Debugging ---
        self.hidden_animal_tiles = {} 
        self.latest_heatmap = np.zeros((grid_size, grid_size))
        self.per_animal_hit_probs = {}
        self.miss_probs = np.ones((grid_size, grid_size))
        self.latest_total_combos = 0
        self.unsimplified_probs = {}

    def generate_valid_placements(self, pattern):
        """Generates all possible placements for a given animal pattern on the grid."""
        placements = []
        max_dx = max(x for x, y in pattern)
        max_dy = max(y for x, y in pattern)
        for x_offset in range(self.grid_size - max_dx):
            for y_offset in range(self.grid_size - max_dy):
                placements.append(frozenset([(x + x_offset, y + y_offset) for x, y in pattern]))
        return placements

    def game_phase(self):
        """Determines the current game phase based on the number of flips and confirmed animals."""
        early_game_flips = 9 - self.total_animal_tiles
        if self.flip_count < early_game_flips:
            return 0  # Early game
        if len(self.confirmed_animals) < len(self.selected_animals):
            return 1  # Mid game
        return 2  # Late game

    def compute_best_tile(self, max_guesses):
        """The core of the solver. It calculates the best tile to flip next."""
        remaining_animals = [a for a in self.selected_animals if a not in self.confirmed_animals]
        if not remaining_animals:
            unflipped = self.confirmed_unflipped_tiles()
            return unflipped[0] if unflipped else None

        # --- 1. Filter Placements Based on Flipped Tiles ---
        revealed_animal_tiles = {animal: set() for animal in remaining_animals}
        for tile, animal_name in self.flipped_tiles.items():
            if animal_name != "empty" and animal_name in revealed_animal_tiles:
                revealed_animal_tiles[animal_name].add(tile)

        filtered_placements = {}
        for animal in remaining_animals:
            valid_for_animal = []
            animal_revealed_set = revealed_animal_tiles[animal]
            for placement in self.initial_placements[animal]:
                is_valid = True
                if not animal_revealed_set.issubset(placement):
                    is_valid = False
                    continue
                for tile, result in self.flipped_tiles.items():
                    if tile in placement and result != animal:
                        is_valid = False
                        break
                if is_valid:
                    valid_for_animal.append(placement)
            filtered_placements[animal] = valid_for_animal

        # --- 2. Generate All Valid Non-Overlapping Combinations ---
        placements_by_animal = [filtered_placements[a] for a in remaining_animals]
        if any(not p for p in placements_by_animal): return None
        all_combos = itertools.product(*placements_by_animal)

        structured_valid_combos = []
        for combo in all_combos:
            occupied = set()
            overlap = False
            for placement in combo:
                if not placement.isdisjoint(occupied):
                    overlap = True
                    break
                occupied.update(placement)
            if not overlap:
                structured_valid_combos.append(combo)
        
        total_combos = len(structured_valid_combos)
        self.latest_total_combos = total_combos
        if total_combos == 0:
            return None

        # --- 3. Calculate Probabilities and Score Each Unflipped Tile ---
        tile_scores = np.full((self.grid_size, self.grid_size), np.inf)
        self.miss_probs = np.ones((self.grid_size, self.grid_size))

        # Calculate per-animal probabilities first, as they are needed for the bias calculation.
        self.unsimplified_probs = {}
        self.per_animal_hit_probs = {}
        for animal in remaining_animals:
            placements_for_animal = filtered_placements.get(animal, [])
            total_placements = len(placements_for_animal)
            
            numerators = np.zeros((self.grid_size, self.grid_size), dtype=int)
            probs = np.zeros((self.grid_size, self.grid_size))

            if total_placements > 0:
                for r_idx in range(self.grid_size):
                    for c_idx in range(self.grid_size):
                        tile = (r_idx, c_idx)
                        num = sum(1 for p in placements_for_animal if tile in p)
                        numerators[r_idx, c_idx] = num
                        probs[r_idx, c_idx] = num / total_placements
            
            self.unsimplified_probs[animal] = {
                'numerators': numerators,
                'denominator': total_placements
            }
            self.per_animal_hit_probs[animal] = probs

        flat_valid_combos = []
        for combo_tuple in structured_valid_combos:
            combo_set = set()
            for placement_frozenset in combo_tuple:
                combo_set.update(placement_frozenset)
            flat_valid_combos.append(combo_set)

        for r in range(self.grid_size):
            for c in range(self.grid_size):
                tile = (r, c)
                if tile in self.flipped_tiles: continue

                combos_with_tile = [combo for combo in flat_valid_combos if tile in combo]
                num_hit = len(combos_with_tile)
                
                p_hit = num_hit / total_combos if total_combos > 0 else 0
                self.miss_probs[r, c] = 1.0 - p_hit

                # --- Hybrid Scoring Calculation ---
                info_score = (p_hit * num_hit) + (self.miss_probs[r,c] * (total_combos - num_hit))
                hitchance_score = self.miss_probs[r, c] # Lower is better
                
                final_score = (info_score * self.INFO_SCORE_WEIGHT) + (hitchance_score * self.HITCHANCE_SCORE_WEIGHT)
                tile_scores[r, c] = final_score

        # --- 4. Determine Strategy: Optimal vs. Best Effort ---
        remaining_guesses = max_guesses - self.flip_count
        found_animal_tiles_count = sum(1 for res in self.flipped_tiles.values() if res != 'empty')
        remaining_animal_tiles_to_find = self.total_animal_tiles - found_animal_tiles_count

        if remaining_guesses < remaining_animal_tiles_to_find:
            if self.testing_mode and self.flip_count > 0: print("(!) Switching to best-effort mode: Not enough guesses to guarantee completion.")
            best_effort_scores = np.full((self.grid_size, self.grid_size), np.inf)
            for r in range(self.grid_size):
                for c in range(self.grid_size):
                    if (r,c) not in self.flipped_tiles:
                        best_effort_scores[r, c] = self.miss_probs[r, c]

            self.latest_heatmap = best_effort_scores
            return np.unravel_index(np.argmin(best_effort_scores), best_effort_scores.shape)

        # --- 5. Apply Mid-Game Bias (Optimal Strategy) ---
        bias_strength = self.step_bias_config[self.game_phase()]
        if bias_strength > 0:
            for r in range(self.grid_size):
                for c in range(self.grid_size):
                    if tile_scores[r, c] == np.inf: continue
                    bias_score = 0
                    for animal in remaining_animals:
                        if any(res == animal for res in self.flipped_tiles.values()):
                            bias_score += self.per_animal_hit_probs[animal][r, c]
                    tile_scores[r, c] -= bias_score * bias_strength

        self.latest_heatmap = tile_scores

        # --- 6. Select Best Tile, Prioritizing Guaranteed Hits ---
        guaranteed_hits = []
        for r in range(self.grid_size):
            for c in range(self.grid_size):
                if (r, c) not in self.flipped_tiles and self.miss_probs[r, c] == 0:
                    guaranteed_hits.append((r, c))

        if guaranteed_hits:
            best_guaranteed_hit = min(guaranteed_hits, key=lambda tile: tile_scores[tile])
            return best_guaranteed_hit

        best_tile_coords = np.unravel_index(np.argmin(tile_scores), tile_scores.shape)
        return best_tile_coords

    def flip_tile(self, x, y, result, animal_completed, animal_tiles=None):
        """Updates the solver's state with the result of a flip."""
        self.flipped_tiles[(x, y)] = result
        self.flip_count += 1
        if result != "empty" and animal_completed:
            self.confirmed_animals[result] = frozenset(animal_tiles)

    def confirmed_unflipped_tiles(self):
        """Returns a list of tiles that are part of a confirmed animal but haven't been flipped."""
        tiles = set()
        for animal_tiles in self.confirmed_animals.values():
            tiles.update(animal_tiles)
        return [t for t in tiles if t not in self.flipped_tiles]

    def reveal_hidden_animals(self, animal_placements):
        """Stores the secret locations of all animals for the simulator."""
        self.hidden_animal_tiles.clear()
        for animal, placement in animal_placements.items():
            for tile in placement:
                self.hidden_animal_tiles[tile] = animal

    def display_board(self):
        """Prints the current state of the board, including solver's deductions and heatmaps."""
        print(f"Flip number: {self.flip_count} | Remaining Combos: {self.latest_total_combos}")
        
        prob_headers = ""
        if self.testing_mode and self.unsimplified_probs:
            for animal in self.unsimplified_probs:
                width = self.grid_size * 6 
                prob_headers += f" {animal:<{width}}"

        if self.testing_mode:
            print(f"{'Board':^15}   {'Heatmap':^20}  {prob_headers}")

        for r in range(self.grid_size):
            board_row, heatmap_row = "", "["
            
            for c in range(self.grid_size):
                tile = (r, c)
                if tile in self.flipped_tiles:
                    result = self.flipped_tiles[tile]
                    board_row += f" {result[0].upper()} " if result != "empty" else " O "
                else:
                    guaranteed_animal = next((animal for animal, tiles in self.confirmed_animals.items() if tile in tiles), None)
                    if guaranteed_animal: board_row += f" {guaranteed_animal[0].lower()} "
                    elif self.miss_probs[r, c] == 0: board_row += " * "
                    else: board_row += " . "
                
                if self.testing_mode:
                    heatmap_row += f"{self.latest_heatmap[r, c]:4.1f} "
            
            heatmap_row = heatmap_row.strip() + "]"
            
            prob_str = ""
            if self.testing_mode and self.unsimplified_probs:
                for animal in self.unsimplified_probs:
                    prob_data = self.unsimplified_probs[animal]
                    denominator = prob_data['denominator']
                    numerators_row = prob_data['numerators'][r]
                    
                    frac_list = [f"{num:02d}/{denominator:02d}" for num in numerators_row]
                    prob_str += f" [{', '.join(frac_list)}]"
            
            if self.testing_mode:
                print(f"{board_row} | {heatmap_row} |{prob_str}")
            else:
                print(board_row)
        print("-" * 20)

class DiscoZooSimulator:
    """Runs a simulation of the game using the solver."""
    def __init__(self, solver):
        self.solver = solver
        self.animal_placements = {}

    def random_animal_placements(self):
        """Generates a random, valid placement of animals on the board."""
        placements = {}
        occupied = set()
        sorted_animals = sorted(self.solver.selected_animals, key=lambda a: len(self.solver.animal_patterns[a]), reverse=True)
        for animal in sorted_animals:
            possible = list(self.solver.initial_placements[animal])
            random.shuffle(possible)
            placed = False
            for placement in possible:
                if placement.isdisjoint(occupied):
                    occupied.update(placement)
                    placements[animal] = placement
                    placed = True
                    break
            if not placed: raise ValueError(f"Could not place animal: {animal}. Board may be too full.")
        self.animal_placements = placements
        return placements

    def run_simulation(self, max_guesses=10, verbose=False):
        """
        Executes a full game simulation.
        Returns a dictionary of results for aggregation.
        """
        try:
            self.random_animal_placements()
        except ValueError as e:
            if verbose: print(f"Error setting up simulation: {e}")
            return None
        
        self.solver.reveal_hidden_animals(self.animal_placements)
            
        if verbose: 
            print(f"Animals: {', '.join(self.solver.selected_animals)}")
            print("Initial Board State:")
            for r in range(self.solver.grid_size):
                row_str = "".join(f" {self.solver.hidden_animal_tiles.get((r, c), '.')[0].upper()} " if self.solver.hidden_animal_tiles.get((r, c)) else " . " for c in range(self.solver.grid_size))
                print(row_str)
            print("-" * 20)

        all_animal_tiles = set()
        for placement in self.animal_placements.values():
            all_animal_tiles.update(placement)
        
        found_tiles = set()

        # Always compute for initial heatmap, display if in testing_mode
        self.solver.compute_best_tile(max_guesses=max_guesses)
        if self.solver.testing_mode:
            self.solver.display_board()

        while self.solver.flip_count < max_guesses and found_tiles != all_animal_tiles:
            next_tile = self.solver.compute_best_tile(max_guesses=max_guesses)
            if next_tile is None:
                if verbose: print("Solver could not find a valid move. Halting.")
                break

            r, c = int(next_tile[0]), int(next_tile[1])
            if verbose: print(f"Solver suggests flipping: ({r}, {c})")
            
            if (r, c) in self.solver.hidden_animal_tiles:
                animal = self.solver.hidden_animal_tiles[(r, c)]
                found_tiles.add((r, c))
                animal_tile_set = self.animal_placements[animal]
                is_completed = animal_tile_set.issubset(found_tiles)
                self.solver.flip_tile(r, c, animal, is_completed, animal_tile_set)
            else:
                self.solver.flip_tile(r, c, "empty", False)
            
            # Always display the board after a flip if in testing_mode
            if self.solver.testing_mode:
                self.solver.display_board()

        if verbose: print(f"Simulation complete. {len(found_tiles)} of {len(all_animal_tiles)} animal tiles found in {self.solver.flip_count} flips.")
        
        return {
            "success": found_tiles == all_animal_tiles,
            "flips_taken": self.solver.flip_count,
            "animal_tiles_found": len(found_tiles),
            "total_animal_tiles": len(all_animal_tiles),
            "selected_animals": self.solver.selected_animals
        }

def print_summary(results, duration):
    """Prints a formatted summary of the batch simulation results."""
    num_runs = len(results)
    if num_runs == 0:
        print("No simulations were completed successfully.")
        return
        
    successes = sum(1 for r in results if r['success'])
    
    print("\n" + "="*40)
    print(" " * 10 + "BATCH SIMULATION SUMMARY")
    print("="*40)
    print(f"Total simulations run: {num_runs}")
    print(f"Total execution time: {duration:.2f} seconds")
    if num_runs > 0:
        print(f"Average time per simulation: {duration/num_runs:.3f} seconds")
    print("-" * 40)
    
    if successes > 0:
        avg_flips_success = sum(r['flips_taken'] for r in results if r['success']) / successes
        print(f"Success Rate: {successes / num_runs:.1%}")
        print(f"Average flips on SUCCESS: {avg_flips_success:.2f}")
    else:
        print("Success Rate: 0.0%")

    avg_flips_total = sum(r['flips_taken'] for r in results) / num_runs
    avg_tiles_found = sum(r['animal_tiles_found'] for r in results) / num_runs
    total_possible_tiles = sum(r['total_animal_tiles'] for r in results) / num_runs if num_runs > 0 else 0
    
    print(f"Average flips (all runs): {avg_flips_total:.2f}")
    if total_possible_tiles > 0:
        print(f"Average animal tiles found: {avg_tiles_found:.2f} / {total_possible_tiles:.2f} ({avg_tiles_found/total_possible_tiles:.1%})")
    else:
        print(f"Average animal tiles found: {avg_tiles_found:.2f}")
    print("="*40 + "\n")

def run_batch_simulations(num_runs, grid_size, animal_patterns, max_guesses, animal_selection, testing_mode=False, verbose_per_run=False):
    """
    Runs a batch of simulations and prints a summary of the results.
    
    Args:
        num_runs (int): The number of simulations to execute.
        animal_selection (list or str): A list of animal names, or "random" to pick two random animals per run.
        verbose_per_run (bool): If True, prints extra text logging for each simulation.
    """
    results = []
    start_time = time.time()
    
    print(f"Starting batch of {num_runs} simulations...")
    
    for i in range(num_runs):
        if animal_selection == "random":
            current_animals = random.sample(list(animal_patterns.keys()), 2)
        else:
            current_animals = animal_selection
        
        # The verbose flag no longer controls board display, only text logs.
        if not verbose_per_run:
            print(f"\rRunning simulation {i+1}/{num_runs} with {current_animals[0]} and {current_animals[1]}...", end="")

        solver = DiscoZooSolver(grid_size, animal_patterns, current_animals, testing_mode)
        simulator = DiscoZooSimulator(solver)
        result = simulator.run_simulation(max_guesses, verbose=verbose_per_run)
        if result:
            results.append(result)

    duration = time.time() - start_time
    print(f"\nBatch finished in {duration:.2f} seconds.")
    
    print_summary(results, duration)

# --- Game Configuration ---
ANIMAL_PATTERNS = {
    "pig": [(0, 0), (0, 1), (1, 0), (1, 1)],      # 4 tiles
    "sheep": [(0, 0), (0, 1), (0, 2), (0, 3)],    # 4 tiles
    "rabbit": [(0, 0), (1, 0), (2, 0), (3, 0)],   # 4 tiles
    "horse": [(0, 0), (1, 0), (2, 0)],            # 3 tiles
    "cow": [(0, 0), (0, 1), (0, 2)],              # 3 tiles
    "unicorn": [(1, 0), (0, 1), (0, 2)],          # 3 tiles
    "chicken": [(0, 0), (1, 1), (2, 2)],          # 3 tiles
}

# --- Batch Simulation Setup ---
if __name__ == "__main__":
    NUMBER_OF_RUNS = 100
    MAX_GUESSES = 10
    GRID_SIZE = 5
    
    # Option 1: Choose two specific animals
    ANIMAL_CHOICE = ["pig", "chicken"]
    
    # Option 2: Use two different random animals for each simulation
    # ANIMAL_CHOICE = "random"

    # Set testing_mode to True to see the board/heatmap after each flip.
    # Set verbose_per_run to True to see additional text logs.
    run_batch_simulations(
        num_runs=NUMBER_OF_RUNS,
        grid_size=GRID_SIZE,
        animal_patterns=ANIMAL_PATTERNS,
        max_guesses=MAX_GUESSES,
        animal_selection=ANIMAL_CHOICE,
        testing_mode=True,
        verbose_per_run=False 
    )
