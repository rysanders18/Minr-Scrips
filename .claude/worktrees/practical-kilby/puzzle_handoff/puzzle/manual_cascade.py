#!/usr/bin/env python3
"""
Manual cascade attempt starting from phase1 end state.
Goal: free red X-chain's +X direction, slide reds, then try to reach goal.

Sequence:
1. After phase1: green concretes at (6925,149,2548) and (6926,149,2548)
2. Slide this X-chain +X×2 to put green at (6928,149,2548)
3. Convert (6928,148,2548) -> forms Y-chain with (6928,149,2548)
4. Slide Y-chain -Y×3 clearing the +X blocker
5. Convert red X-chain (6926,148,2548) and (6927,148,2548) -> concrete
6. Slide red X-chain +X×1 -> reds at (6927,148,2548), (6928,148,2548)
7. Further moves ...
"""

from fast_engine import (
    State, parse_initial, compound_moves, find_formable_chains,
    find_all_chains, slide_chain, max_slide, pos_to_int, int_to_pos,
    COLOR_IDS, ID_TO_COLOR, GOAL_POS, display_state
)
from validate_phase1 import parse_move_line, apply_move

RED_ID = COLOR_IDS['red']


def load_phase1():
    with open('phase1_solution.txt', encoding='utf-8') as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    state = parse_initial()
    for line in lines:
        mv = parse_move_line(line)
        ns, err = apply_move(state, mv)
        if ns is None:
            raise RuntimeError(err)
        state = ns
    return state, lines


def show_chains(state, label=""):
    chains = find_all_chains(state)
    print(f"\n{label} active chains ({len(chains)}):")
    for axis_idx, positions in chains:
        axis = ['X', 'Y', 'Z'][axis_idx]
        color_id = state.get(positions[0])[0]
        color = ID_TO_COLOR[color_id]
        print(f"  {color} {axis}-chain: {list(positions)}")


def find_and_apply(state, axis, endpoints, direction, steps, convs=None):
    """Find matching compound move and apply. Returns (new_state, desc) or None."""
    axis_idx = {'X': 0, 'Y': 1, 'Z': 2}[axis]
    sign = '+' if direction > 0 else '-'
    # Build expected descriptor fragment
    p1, p2 = endpoints
    chain_str = f"({p1[0]}, {p1[1]}, {p1[2]})..({p2[0]}, {p2[1]}, {p2[2]})"
    frag = f"{axis}-chain {chain_str} slide {sign}{axis}\u00d7{steps}"
    cm = compound_moves(state, conversion_limit=60)
    for ns, desc, nc in cm:
        if frag in desc:
            if convs is not None:
                # Check conversion list matches
                pass
            return ns, desc
    return None, None


def main():
    state, phase1 = load_phase1()
    print(f"After phase1: conv={state.conversions}")
    show_chains(state, "Post-phase1")

    # Step A: slide X-chain (6925-6926, 149, 2548) +X by 2
    # First verify the chain exists
    chains = find_all_chains(state)
    x_chain_149 = None
    for axis_idx, positions in chains:
        if axis_idx == 0:  # X
            if positions[0] == (6925, 149, 2548) and positions[-1] == (6926, 149, 2548):
                x_chain_149 = positions
                break
    print(f"\nX-chain at y=149, z=2548: {x_chain_149}")

    if x_chain_149 is None:
        print("ERROR: expected X-chain not found")
        return

    # Check +X slide room
    ms = max_slide(state, 0, list(x_chain_149), +1)
    print(f"Max +X slide: {ms}")

    # Apply +X slide by 2
    ns, desc = find_and_apply(state, 'X',
                              ((6925, 149, 2548), (6926, 149, 2548)),
                              +1, 2)
    if ns is None:
        # Try without requiring exact match - browse all moves with greens
        cm = compound_moves(state)
        print("Green moves available:")
        for s, d, nc in cm:
            if 'green' in d and '149, 2548' in d:
                print(f"  {d}")
        return

    state = ns
    print(f"Applied: {desc}")
    moves = list(phase1) + [desc]

    # Now (6927, 149, 2548) and (6928, 149, 2548) should be green concrete
    for p in [(6925, 149, 2548), (6926, 149, 2548), (6927, 149, 2548),
              (6928, 149, 2548), (6929, 149, 2548)]:
        print(f"  {p}: {state.get(p)}")

    # Step B: convert (6928, 148, 2548) and form Y-chain with (6928, 149, 2548)
    # Actually the Y-chain: we need green at (6928, 148, 2548) and (6928, 149, 2548)
    # (6928, 148, 2548) is green glass originally.
    # Use compound move that converts it as part of forming Y-chain
    cm = compound_moves(state)
    print(f"\nCompound moves available: {len(cm)}")
    print("Y-chain options at (6928, *, 2548):")
    for ns2, d, nc in cm:
        if '(6928,' in d and 'Y-chain' in d:
            print(f"  [{nc} conv] {d}")

    # Find the green Y-chain (6928, 148, 2548)..(6928, 149, 2548) slide -Y x 3
    target = None
    for ns2, d, nc in cm:
        if ('green Y-chain' in d and
            '(6928, 148, 2548)..(6928, 149, 2548)' in d and
            '-Y\u00d73' in d):
            target = (ns2, d, nc)
            break

    if target is None:
        print("Y-chain move not found; trying smaller slide")
        for ns2, d, nc in cm:
            if ('green Y-chain' in d and
                '(6928, 148, 2548)..(6928, 149, 2548)' in d):
                print(f"  candidate: {d}")

        return

    state, desc, nc = target
    print(f"\nApplied: {desc}")
    moves.append(desc)

    # Check state
    print(f"\nAfter Y-chain slide:")
    for p in [(6928, 145, 2548), (6928, 146, 2548), (6928, 147, 2548),
              (6928, 148, 2548), (6928, 149, 2548)]:
        print(f"  {p}: {state.get(p)}")
    print(f"conv={state.conversions}")

    # Step C: convert red X-chain and slide +X
    cm = compound_moves(state)
    print(f"\nRed moves available:")
    for ns2, d, nc in cm:
        if 'red' in d:
            print(f"  [{nc} conv] {d}")

    # The red X-chain is (6926, 148, 2548)-(6927, 148, 2548) with +X clear
    target = None
    for ns2, d, nc in cm:
        if ('red X-chain' in d and
            '(6926, 148, 2548)..(6927, 148, 2548)' in d and
            '+X\u00d71' in d):
            target = (ns2, d, nc)
            break

    if target is None:
        print("Red move not found")
        return

    state, desc, nc = target
    print(f"\nApplied: {desc}")
    moves.append(desc)

    print(f"\nAfter red slide: conv={state.conversions}")
    for p in [(6925, 148, 2548), (6926, 148, 2548), (6927, 148, 2548),
              (6928, 148, 2548), (6929, 148, 2548)]:
        print(f"  {p}: {state.get(p)}")

    # Show current state y=146, 148, 149
    for y in [146, 147, 148, 149]:
        print(f"\n=== Y={y} ===")
        display_state(state, y)

    # Save state
    with open('cascade_snapshot.txt', 'w', encoding='utf-8') as f:
        for m in moves:
            f.write(m + '\n')

    print(f"\nSaved {len(moves)} moves.")
    print(f"Red at goal? {state.get(GOAL_POS)}")


if __name__ == '__main__':
    main()
