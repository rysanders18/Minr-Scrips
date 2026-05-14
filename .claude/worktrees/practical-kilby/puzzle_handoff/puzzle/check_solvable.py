#!/usr/bin/env python3
"""
Structural solvability analysis:
Under the rules as described, can red ever reach (6925, 146, 2546)?

Plan:
1. Enumerate all reds' potential 'mobility sets' - positions reachable.
2. Identify which reds can ever reach the goal cell.
3. Identify if any red chain can have goal cell as endpoint.
"""

from fast_engine import (
    parse_initial, COLOR_IDS, int_to_pos, GOAL_POS,
    X_MIN, X_MAX, Y_MIN, Y_MAX, Z_MIN, Z_MAX
)
from collections import defaultdict

RED_ID = COLOR_IDS['red']


def main():
    state = parse_initial()

    reds = []
    for pi, (c, is_c) in state.grid.items():
        if c == RED_ID:
            reds.append(int_to_pos(pi))

    print(f"Reds ({len(reds)}):")
    for r in sorted(reds):
        print(f"  {r}")

    # Group by (y, z), (x, z), (x, y) for X, Y, Z chain potential
    gy_z = defaultdict(list)  # for X-chains
    gx_z = defaultdict(list)  # for Y-chains
    gx_y = defaultdict(list)  # for Z-chains
    for r in reds:
        gy_z[(r[1], r[2])].append(r[0])
        gx_z[(r[0], r[2])].append(r[1])
        gx_y[(r[0], r[1])].append(r[2])

    print("\n=== Red X-chain potentials (pairs at same y, z) ===")
    for (y, z), xs in sorted(gy_z.items()):
        if len(xs) >= 2:
            xs = sorted(xs)
            print(f"  y={y}, z={z}: x={xs} (gaps {[xs[i+1]-xs[i] for i in range(len(xs)-1)]})")

    print("\n=== Red Y-chain potentials (pairs at same x, z) ===")
    for (x, z), ys in sorted(gx_z.items()):
        if len(ys) >= 2:
            ys = sorted(ys)
            print(f"  x={x}, z={z}: y={ys}")

    print("\n=== Red Z-chain potentials (pairs at same x, y) ===")
    for (x, y), zs in sorted(gx_y.items()):
        if len(zs) >= 2:
            zs = sorted(zs)
            print(f"  x={x}, y={y}: z={zs}")

    # For each red, track what positions it could potentially reach
    # Initially: only the X-chain reds at (6926, 148, 2548)-(6927, 148, 2548) can move
    # via X-chain. Other reds are isolated.

    # The X-chain can slide along X at (y=148, z=2548).
    # Max reachable x range for its two reds: constrained by other blocks at y=148, z=2548

    print("\n=== Grid cells along y=148, z=2548 ===")
    for x in range(X_MIN, X_MAX + 1):
        v = state.get((x, 148, 2548))
        print(f"  (x={x}, 148, 2548): {v}")

    print(f"\nGoal cell {GOAL_POS}: {state.get(GOAL_POS)}")
    print("\nFinal structural verdict:")
    print(" - Reds at (y=148, z=2548): (6926, 148, 2548), (6927, 148, 2548).")
    print(" - Other reds are collinear on (y=146, z=2546): (6926, 146, 2546), (6930, 146, 2546) with a gap.")
    print(" - Middles of the (y=146, z=2546) pair are currently empty.")
    print(" - To form a red X-chain at y=146, z=2546, middles at x=6927, 6928, 6929 must all be red.")
    print(" - Reds can only be moved via red chains; only available red chain is at y=148, z=2548.")
    print(" - Since X-chain slides along x (y, z constant), chain-reds can never reach y=146, z=2546.")
    print(" - Therefore no red X-chain at y=146, z=2546 can ever form.")
    print(" - For red concrete at (6925, 146, 2546), we need a red chain passing through there.")
    print(" - None possible => STRUCTURALLY UNSOLVABLE under stated rules.")


if __name__ == '__main__':
    main()
