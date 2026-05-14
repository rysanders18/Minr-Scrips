#!/usr/bin/env python3
"""
Continuation: Phase 2 (move blocker) and prepare phase 3.
"""

from fast_engine import (
    State, parse_initial, compound_moves, find_formable_chains,
    find_all_chains, slide_chain, max_slide, pos_to_int, int_to_pos,
    COLOR_IDS, ID_TO_COLOR, GOAL_POS, X_MIN, X_MAX, Y_MIN, Y_MAX, Z_MIN, Z_MAX
)
import pickle

RED_ID = COLOR_IDS['red']


def apply_solution(state, solution):
    """Apply a list of moves to initial state. Returns final state."""
    cur = state
    for move in solution:
        cm = compound_moves(cur, conversion_limit=60)
        found = None
        for new_state, desc, n_conv in cm:
            if desc == move:
                found = new_state
                break
        if found is None:
            return None
        cur = found
    return cur


def describe_state_at_layer(state, y):
    """Show what's at a particular y-layer."""
    ABBREV = {0:'R', 1:'B', 2:'G', 3:'P', 4:'K', 5:'O', 6:'C', 7:'W'}
    print(f"\n  === Y={y} ===")
    print(f"    X:", end="")
    for x in range(X_MIN, X_MAX+1):
        print(f" {x%100:2d}", end="")
    print()
    for z in range(Z_MAX, Z_MIN-1, -1):
        print(f"  Z={z%100:2d}:", end="")
        for x in range(X_MIN, X_MAX+1):
            v = state.get((x, y, z))
            if v is None:
                print("  .", end="")
            else:
                c = ABBREV[v[0]]
                c = c if v[1] else c.lower()
                print(f"  {c}", end="")
        print()


def find_reds(state):
    reds = []
    for pi, (c, is_c) in state.grid.items():
        if c == RED_ID:
            reds.append((int_to_pos(pi), is_c))
    return sorted(reds)


if __name__ == '__main__':
    state = parse_initial()
    
    # Load phase 1 solution
    with open('/home/claude/puzzle/phase1_solution.txt') as f:
        phase1 = [line.rstrip() for line in f if line.strip()]
    
    # Apply phase 1
    state = apply_solution(state, phase1)
    assert state is not None, "phase 1 replay failed"
    print(f"Phase 1 end: conversions={state.conversions}")
    
    # Check blocker-adjacent green
    for p in [(6925, 146, 2545), (6925, 146, 2547), (6925, 145, 2546), (6925, 147, 2546)]:
        v = state.get(p)
        print(f"  {p}: {v}")
    
    # Now phase 2: convert G2 and slide Z-chain +Z×1 to clear (6925, 146, 2546)
    print("\n--- Phase 2 ---")
    state = state.convert((6925, 146, 2546))
    print(f"Converted G2. Conversions now: {state.conversions}")
    
    # What chains exist now?
    chains = find_all_chains(state)
    print("Current active chains:")
    for axis_idx, positions in chains:
        axis = ['X','Y','Z'][axis_idx]
        color = ID_TO_COLOR[state.get(positions[0])[0]]
        print(f"  {color} {axis}-chain: {list(positions)}")
    
    # Apply green Z-chain slide +Z
    cm = compound_moves(state)
    phase2 = []
    # Find slide +Z for the green chain at x=6925, y=146
    for new_state, desc, n_conv in cm:
        if 'green Z-chain (6925, 146, 2546)' in desc and '+Z×1' in desc:
            state = new_state
            phase2.append(desc)
            print(f"\nApplied: {desc}")
            break
    
    goal_v = state.get(GOAL_POS)
    print(f"Goal position {GOAL_POS}: {goal_v}")
    print(f"Phase 2 end: conversions={state.conversions}")
    
    # Save state for phase 3
    with open('/home/claude/puzzle/phase2_state.pkl', 'wb') as f:
        pickle.dump({
            'grid': state.grid,
            'conversions': state.conversions,
            'phase1': phase1,
            'phase2': phase2,
        }, f)
    
    print("\n=== Current reds ===")
    for pos, is_c in find_reds(state):
        cstatus = 'CONCRETE' if is_c else 'glass'
        print(f"  {pos}: {cstatus}")
    
    print("\n=== Layer Y=146 (goal layer) ===")
    describe_state_at_layer(state, 146)
    
    print("\n=== Layer Y=148 (red X-chain) ===")
    describe_state_at_layer(state, 148)
