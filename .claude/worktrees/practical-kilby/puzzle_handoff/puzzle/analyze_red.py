#!/usr/bin/env python3
"""Analyze the red situation to design a better phase 3 heuristic."""

from fast_engine import (
    State, parse_initial, compound_moves, find_formable_chains,
    find_all_chains, int_to_pos, pos_to_int, COLOR_IDS, ID_TO_COLOR, GOAL_POS
)
from phase3_solver import apply_solution

def load_phase1_state():
    state = parse_initial()
    with open('/home/claude/puzzle/phase1_solution.txt') as f:
        phase1 = [line.rstrip() for line in f if line.strip()]
    return apply_solution(state, phase1)


def find_potential_red_chains(state):
    """Find all red PAIRS that could form chains (with/without filling)."""
    reds = []
    for pi, (c, is_c) in state.grid.items():
        if c == COLOR_IDS['red']:
            reds.append((int_to_pos(pi), is_c))
    
    print(f"Reds ({len(reds)}):")
    for pos, is_c in reds:
        print(f"  {pos}: {'concrete' if is_c else 'glass'}")
    
    # For each red pair, check if they're collinear on some axis
    print("\nCollinear red pairs (could form chain if gap filled):")
    for i, (p1, _) in enumerate(reds):
        for j, (p2, _) in enumerate(reds):
            if i >= j:
                continue
            diff = [p2[0]-p1[0], p2[1]-p1[1], p2[2]-p1[2]]
            nonzero = [k for k in range(3) if diff[k] != 0]
            if len(nonzero) == 1:
                axis = ['X','Y','Z'][nonzero[0]]
                gap = abs(diff[nonzero[0]]) - 1
                # Check what's in the gap
                start, end = p1, p2
                if diff[nonzero[0]] < 0:
                    start, end = p2, p1
                gap_contents = []
                for k in range(1, abs(diff[nonzero[0]])):
                    gp = list(start)
                    gp[nonzero[0]] += k
                    gp = tuple(gp)
                    v = state.get(gp)
                    gap_contents.append(f"{gp}={v}")
                print(f"  {axis}-axis {p1} -> {p2} gap={gap}: {gap_contents}")


def analyze_red_path_to_goal(state):
    """What chains could deliver a red to goal position?"""
    goal = GOAL_POS  # (6925, 146, 2546)
    print(f"\nGOAL: {goal}")
    
    # X-chain that could slide red INTO goal via -X slide (endpoint at x=6926+)
    # Need red X-chain at y=146, z=2546, with endpoint at x_min <= 6926
    # (the chain's lower endpoint would need to slide to x=6925 which is goal)
    print("\nFor X-chain at y=146, z=2546 to slide INTO goal:")
    print("  Need red blocks at (x, 146, 2546) for contiguous x starting from 6926")
    for x in range(6925, 6933):
        p = (x, 146, 2546)
        v = state.get(p)
        print(f"    {p}: {v}")
    
    # Can reds reach any of those positions?
    print("\nPotential sources for a red at each relevant (x, 146, 2546):")
    targets = [(x, 146, 2546) for x in [6927, 6928, 6929]]
    for t in targets:
        print(f"\n  Target {t}:")
        # A red at this position would come from:
        # 1. Y-chain at (x, ?, 2546) sliding to y=146
        # 2. Z-chain at (x, 146, ?) sliding to z=2546
        # 3. X-chain at (?, 146, 2546) sliding to x=t[0]
        
        # Reds at same x, z=2546 (Y-chain would bring to y=146 via slide)
        same_x_z = []
        for pi, (c, is_c) in state.grid.items():
            if c == COLOR_IDS['red']:
                p = int_to_pos(pi)
                if p[0] == t[0] and p[2] == 2546:
                    same_x_z.append(p)
        # Reds at same x, y=146
        same_x_y = []
        for pi, (c, is_c) in state.grid.items():
            if c == COLOR_IDS['red']:
                p = int_to_pos(pi)
                if p[0] == t[0] and p[1] == 146:
                    same_x_y.append(p)
        # Reds at same y=146, z=2546 (X-chain)
        same_yz = []
        for pi, (c, is_c) in state.grid.items():
            if c == COLOR_IDS['red']:
                p = int_to_pos(pi)
                if p[1] == 146 and p[2] == 2546:
                    same_yz.append(p)
        print(f"    Reds at x={t[0]}, z=2546 (for Y-chain): {same_x_z}")
        print(f"    Reds at x={t[0]}, y=146 (for Z-chain): {same_x_y}")
        print(f"    Reds at y=146, z=2546 (for X-chain): {same_yz}")


def check_path_red_chain_stuck(state):
    """Is the red X-chain at y=148, z=2548 still stuck?"""
    p1 = (6926, 148, 2548)
    p2 = (6927, 148, 2548)
    v1 = state.get(p1)
    v2 = state.get(p2)
    print(f"\nRed X-chain at y=148, z=2548:")
    print(f"  {p1}: {v1}")
    print(f"  {p2}: {v2}")
    
    # -X blocker
    p_minus = (6925, 148, 2548)
    v_m = state.get(p_minus)
    print(f"  -X block at {p_minus}: {v_m}")  # Should be purple
    
    # +X blocker
    p_plus = (6928, 148, 2548)
    v_p = state.get(p_plus)
    print(f"  +X block at {p_plus}: {v_p}")  # Should be green


def find_all_chains_by_color(state):
    """Group formable chains by color."""
    chains = find_formable_chains(state)
    by_color = {}
    for axis_idx, positions, color, needed in chains:
        color_name = ID_TO_COLOR[color]
        if color_name not in by_color:
            by_color[color_name] = []
        by_color[color_name].append((['X','Y','Z'][axis_idx], positions, needed))
    
    print("\n=== Formable chains by color ===")
    for color_name, cs in sorted(by_color.items()):
        print(f"\n{color_name}:")
        for axis, positions, needed in cs:
            print(f"  {axis}-chain {positions} (need convert: {needed})")


if __name__ == '__main__':
    state = load_phase1_state()
    print(f"Phase 1 end state, conv={state.conversions}\n")
    
    find_potential_red_chains(state)
    analyze_red_path_to_goal(state)
    check_path_red_chain_stuck(state)
    find_all_chains_by_color(state)
