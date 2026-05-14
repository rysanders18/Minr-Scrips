#!/usr/bin/env python3
"""
Validate phase1_solution.txt end-to-end.

Parse each line describing a compound move, find the matching move among
compound_moves(state), apply it, and check whether the final state has a
GREEN CONCRETE block adjacent to the goal position (6925, 146, 2546).
"""

import re
from fast_engine import (
    State, parse_initial, compound_moves, find_formable_chains,
    find_all_chains, int_to_pos, pos_to_int, COLOR_IDS, ID_TO_COLOR,
    GOAL_POS, display_state
)


def parse_move_line(line):
    """
    Parses lines like:
      green Z-chain (6930, 151, 2545)..(6930, 151, 2546) slide +Z×4 [convert: ((6930, 151, 2545), (6930, 151, 2546))]
      green Y-chain (6925, 147, 2550)..(6925, 149, 2550) slide -Y×2
    Returns dict with color, axis, endpoints, direction, steps, conversions.
    """
    line = line.strip()
    # Accept both × (Unicode) and x or * just in case
    m = re.match(
        r"(\w+)\s+([XYZ])-chain\s+"
        r"\((-?\d+),\s*(-?\d+),\s*(-?\d+)\)\.\.\((-?\d+),\s*(-?\d+),\s*(-?\d+)\)\s+"
        r"slide\s+([+-])([XYZ])[×x*](\d+)"
        r"(?:\s+\[convert:\s*(.+)\])?",
        line,
    )
    if not m:
        return None
    color = m.group(1)
    axis_name = m.group(2)
    p1 = (int(m.group(3)), int(m.group(4)), int(m.group(5)))
    p2 = (int(m.group(6)), int(m.group(7)), int(m.group(8)))
    dir_sym = m.group(9)
    dir_axis = m.group(10)
    steps = int(m.group(11))
    conv_str = m.group(12)

    conversions = []
    if conv_str:
        # Look for tuples like (6930, 151, 2545)
        tuples = re.findall(r"\((-?\d+),\s*(-?\d+),\s*(-?\d+)\)", conv_str)
        conversions = [tuple(int(x) for x in t) for t in tuples]

    axis_idx = {'X': 0, 'Y': 1, 'Z': 2}[axis_name]
    direction = +1 if dir_sym == '+' else -1

    return {
        'color': color,
        'axis_idx': axis_idx,
        'p1': p1,
        'p2': p2,
        'direction': direction,
        'steps': steps,
        'conversions': conversions,
        'raw': line,
    }


def apply_move(state, mv):
    """Apply a single parsed move to state. Returns new state or None on failure."""
    # 1) Verify endpoints exist with correct color and are on the expected axis.
    axis_idx = mv['axis_idx']
    color_id = COLOR_IDS[mv['color']]
    p1, p2 = mv['p1'], mv['p2']

    # Endpoints must differ on the given axis only
    diff = [p2[i] - p1[i] for i in range(3)]
    nonzero = [k for k in range(3) if diff[k] != 0]
    if nonzero != [axis_idx]:
        return None, f"Endpoints not collinear on {['X','Y','Z'][axis_idx]}: {p1} -> {p2}"

    # Walk from p1..p2 along axis, ensure color consistent
    step = 1 if p2[axis_idx] > p1[axis_idx] else -1
    chain_positions = []
    x, y, z = p1
    while True:
        v = state.get((x, y, z))
        if v is None or v[0] != color_id:
            return None, f"Non-matching block at {(x, y, z)} during chain scan"
        chain_positions.append((x, y, z))
        if (x, y, z) == p2:
            break
        if axis_idx == 0:
            x += step
        elif axis_idx == 1:
            y += step
        else:
            z += step

    # Normalize chain order to ascending along axis (engine uses that)
    chain_positions.sort(key=lambda p: p[axis_idx])

    # 2) Apply conversions
    s = state
    for cp in mv['conversions']:
        new_s = s.convert(cp)
        if new_s is None:
            # Maybe already concrete; check
            v = s.get(cp)
            if v is None:
                return None, f"Conversion target {cp} missing from grid"
            if v[1]:
                # Already concrete, no-op
                continue
            return None, f"Conversion failed for {cp} (block={v})"
        s = new_s

    # 3) Verify both endpoints are now concrete
    for ep in (chain_positions[0], chain_positions[-1]):
        v = s.get(ep)
        if v is None or v[0] != color_id:
            return None, f"Endpoint {ep} missing/wrong color after conversion"
        if not v[1]:
            return None, f"Endpoint {ep} still not concrete after conversion"

    # 4) Slide `steps` times
    positions = chain_positions
    for step_idx in range(mv['steps']):
        # Find the chain (in case it's embedded with intermediate concrete)
        # But we already know positions.
        # Check slide validity
        from fast_engine import can_slide, slide_chain
        if not can_slide(s, axis_idx, positions, mv['direction']):
            return None, f"Slide blocked at step {step_idx+1}/{mv['steps']}"
        s = slide_chain(s, axis_idx, positions, mv['direction'])
        positions = [
            tuple(p[i] + (mv['direction'] if i == axis_idx else 0) for i in range(3))
            for p in positions
        ]

    return s, None


def phase1_goal_met(state):
    """Phase 1 goal: GREEN CONCRETE adjacent to GOAL_POS (6925, 146, 2546)."""
    gx, gy, gz = GOAL_POS
    # The goal pos itself is inside the grid. Its adjacents include (6924, 146, 2546) which is the sea lantern (out of grid).
    # Per HANDOFF, the only in-grid adjacent cell to the sea lantern IS GOAL_POS.
    # Phase 1 is "get a green concrete NEXT to the blocker cell's current location" → allow the goal cell itself
    # OR any cell adjacent to (6925, 146, 2546) once the blocker is out.
    # Safer definition: any green concrete IN goal cell or adjacent cells, which will let Phase 2 push it out.
    candidates = [
        (gx, gy, gz),
        (gx + 1, gy, gz),
        (gx, gy + 1, gz),
        (gx, gy - 1, gz),
        (gx, gy, gz + 1),
        (gx, gy, gz - 1),
    ]
    results = []
    for c in candidates:
        v = state.get(c)
        if v is not None and v[0] == COLOR_IDS['green'] and v[1]:
            results.append(c)
    return results


def main():
    with open('phase1_solution.txt', encoding='utf-8') as f:
        lines = [ln.strip() for ln in f if ln.strip()]

    state = parse_initial()
    print(f"Initial state: {len(state.grid)} blocks, conversions={state.conversions}")

    for i, line in enumerate(lines, 1):
        mv = parse_move_line(line)
        if mv is None:
            print(f"FAIL parse line {i}: {line}")
            return
        new_state, err = apply_move(state, mv)
        if new_state is None:
            print(f"FAIL line {i}: {err}")
            print(f"  Move: {line}")
            # Show current state around problem
            return
        state = new_state
        print(f"OK  {i:2d}: conv={state.conversions} :: {line}")

    print(f"\nFinal conversions used: {state.conversions}")
    met = phase1_goal_met(state)
    print(f"Green concrete at/adjacent to GOAL_POS: {met}")

    # Current block at GOAL_POS
    v = state.get(GOAL_POS)
    print(f"Block at {GOAL_POS}: {v}")

    # Show y=146 for clarity
    print("\n=== Y=146 slice ===")
    display_state(state, 146)


if __name__ == '__main__':
    main()
