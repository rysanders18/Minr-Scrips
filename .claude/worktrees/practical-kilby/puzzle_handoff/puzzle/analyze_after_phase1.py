#!/usr/bin/env python3
"""
After applying the validated phase1_solution.txt, examine:
- All available compound moves
- Status of every known blocker around the red X-chain
- All formable chains by color
- Show full grid state around y=146-148 plane
"""

from fast_engine import (
    State, parse_initial, compound_moves, find_formable_chains,
    find_all_chains, int_to_pos, pos_to_int, COLOR_IDS, ID_TO_COLOR,
    GOAL_POS, display_state, X_MIN, X_MAX, Y_MIN, Y_MAX, Z_MIN, Z_MAX,
)
from validate_phase1 import parse_move_line, apply_move

RED_ID = COLOR_IDS['red']


def apply_phase1(state, lines):
    for line in lines:
        mv = parse_move_line(line)
        ns, err = apply_move(state, mv)
        if ns is None:
            raise RuntimeError(f"phase1 failed: {err} :: {line}")
        state = ns
    return state


def main():
    with open('phase1_solution.txt', encoding='utf-8') as f:
        lines = [ln.strip() for ln in f if ln.strip()]

    state = parse_initial()
    state = apply_phase1(state, lines)
    print(f"Phase 1 end: conv={state.conversions}, blocks={len(state.grid)}\n")

    # Status of key blockers
    print("=== Key blockers for red X-chain at (6926, 148, 2548)-(6927, 148, 2548) ===")
    for p in [(6925, 148, 2548), (6928, 148, 2548), (6925, 146, 2546)]:
        v = state.get(p)
        print(f"  {p}: {v}")

    # Count all reds and their status
    print("\n=== All reds ===")
    reds = []
    for pi, (c, is_c) in state.grid.items():
        if c == RED_ID:
            reds.append((int_to_pos(pi), is_c))
    for pos, is_c in sorted(reds):
        state_str = "CONCRETE" if is_c else "glass"
        # Chain analysis: which axes have other reds?
        axes = []
        for axis_idx in range(3):
            # same-axis reds
            near = []
            for p2, _ in reds:
                if p2 == pos:
                    continue
                diff = [p2[i] - pos[i] for i in range(3)]
                nz = [k for k in range(3) if diff[k] != 0]
                if nz == [axis_idx]:
                    near.append(p2)
            if near:
                axes.append((["X", "Y", "Z"][axis_idx], near))
        print(f"  {pos} [{state_str}] : {axes}")

    # Find all compound moves
    print(f"\n=== Compound moves available: {len(compound_moves(state))} ===")
    moves = compound_moves(state)
    by_color = {}
    for ns, desc, nc in moves:
        color = desc.split()[0]
        by_color.setdefault(color, []).append(desc)
    for color, ds in sorted(by_color.items()):
        print(f"  {color}: {len(ds)} moves")

    # Show y=148 slice
    print("\n=== Y=148 slice ===")
    display_state(state, 148)

    # Show y=149 slice (middle between 148 and 151 for purple Y-chain)
    print("\n=== Y=149 slice ===")
    display_state(state, 149)

    # Show y=150 slice
    print("\n=== Y=150 slice ===")
    display_state(state, 150)

    # Show y=151 slice
    print("\n=== Y=151 slice ===")
    display_state(state, 151)


if __name__ == '__main__':
    main()
