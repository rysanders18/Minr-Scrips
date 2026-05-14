#!/usr/bin/env python3
"""
Critical analysis: Can the green blocker at (6925,146,2546) EVER be moved?
A block can only move as part of a same-color chain.
For the green blocker to move, it needs an adjacent green block.
Let's check if ANY green block can reach an adjacent position through chain moves.
"""

from engine import parse_initial_state, GLASS, CONCRETE

state = parse_initial_state()

# All green blocks
greens = {pos: block for pos, block in state.grid.items() if block.color == 'green'}
print(f"All {len(greens)} green blocks:")
for pos in sorted(greens):
    # Check if it has any adjacent green
    x, y, z = pos
    adj_greens = []
    for dx, dy, dz in [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)]:
        ap = (x+dx, y+dy, z+dz)
        if ap in state.grid and state.grid[ap].color == 'green':
            adj_greens.append(ap)
    status = f"adjacent to {adj_greens}" if adj_greens else "ISOLATED"
    print(f"  {pos}: {status}")

# Blocker's neighbors
blocker = (6925, 146, 2546)
print(f"\nBlocker {blocker} neighbors:")
x, y, z = blocker
for dx, dy, dz in [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)]:
    ap = (x+dx, y+dy, z+dz)
    if ap in state.grid:
        print(f"  {ap}: {state.grid[ap].color} ({state.grid[ap].material})")
    else:
        in_bounds = (6925 <= ap[0] <= 6932 and 145 <= ap[1] <= 152 and 2544 <= ap[2] <= 2551)
        if in_bounds:
            print(f"  {ap}: EMPTY")
        else:
            if ap == (6924, 146, 2546):
                print(f"  {ap}: SEA LANTERN")
            else:
                print(f"  {ap}: OUT OF BOUNDS")

# Green chain pairs and their mobility
print(f"\nGreen chain pairs (contiguous same-color):")
pairs = [
    ((6928,148,2548), (6928,148,2549), 'Z'),
    ((6930,147,2545), (6930,148,2545), 'Y'),
    ((6930,151,2545), (6930,151,2546), 'Z'),
]
for p1, p2, axis in pairs:
    print(f"\n  {p1}-{p2} ({axis}-axis)")
    # Check what's adjacent in move directions
    if axis == 'Z':
        low_z = min(p1[2], p2[2])
        high_z = max(p1[2], p2[2])
        check_neg = (p1[0], p1[1], low_z - 1)
        check_pos = (p1[0], p1[1], high_z + 1)
    elif axis == 'Y':
        low_y = min(p1[1], p2[1])
        high_y = max(p1[1], p2[1])
        check_neg = (p1[0], low_y - 1, p1[2])
        check_pos = (p1[0], high_y + 1, p1[2])
    elif axis == 'X':
        low_x = min(p1[0], p2[0])
        high_x = max(p1[0], p2[0])
        check_neg = (low_x - 1, p1[1], p1[2])
        check_pos = (high_x + 1, p1[1], p1[2])
    
    for check, label in [(check_neg, '-'), (check_pos, '+')]:
        in_bounds = (6925 <= check[0] <= 6932 and 145 <= check[1] <= 152 and 2544 <= check[2] <= 2551)
        if not in_bounds:
            print(f"    {label}{axis}: OUT OF BOUNDS at {check}")
        elif check in state.grid:
            print(f"    {label}{axis}: BLOCKED by {state.grid[check].color} at {check}")
        else:
            print(f"    {label}{axis}: CLEAR at {check}")

# Key question: green blocks are at x=6925, 6926, 6927, 6928, 6929, 6930
# Chains move along their axis only. So:
# - Z-chains move along Z (x and y unchanged)
# - Y-chains move along Y (x and z unchanged)
# - X-chains move along X (y and z unchanged)
# 
# For a green to reach adjacent to blocker (6925,146,2546), it needs to be at one of:
# (6925,146,2545), (6925,146,2547), (6925,145,2546), (6925,147,2546)
# 
# To reach x=6925, a green must ALREADY be at x=6925 (Y or Z chains don't change x)
# OR be part of an X-chain that slides to x=6925.
# But for an X-chain, we need 2 green blocks at same y,z, different x.

print(f"\n\nGreen blocks at x=6925:")
for pos in sorted(greens):
    if pos[0] == 6925:
        print(f"  {pos}")

print(f"\nGreen blocks that could form X-chains (same y,z, different x):")
from collections import defaultdict
yz_groups = defaultdict(list)
for pos in greens:
    yz_groups[(pos[1], pos[2])].append(pos[0])

for (y, z), x_vals in sorted(yz_groups.items()):
    if len(x_vals) >= 2:
        print(f"  y={y}, z={z}: x_vals={sorted(x_vals)}")
        x_sorted = sorted(x_vals)
        for i in range(len(x_sorted) - 1):
            gap = x_sorted[i+1] - x_sorted[i]
            if gap == 1:
                print(f"    ADJACENT: x={x_sorted[i]}-{x_sorted[i+1]}")
            else:
                between = []
                for x in range(x_sorted[i]+1, x_sorted[i+1]):
                    p = (x, y, z)
                    if p in state.grid:
                        between.append(f"{x}={state.grid[p].color}")
                    else:
                        between.append(f"{x}=empty")
                print(f"    GAP of {gap-1}: {between}")

# Also check if green could reach x=6925 via multi-step chain formation
print(f"\nAll green X-coordinates: {sorted(set(pos[0] for pos in greens))}")
print(f"Green blocks at x=6925, y=146: {[pos for pos in greens if pos[0]==6925 and pos[1]==146]}")
print(f"Green blocks near goal y=146, z=2546:")
for pos in sorted(greens):
    x, y, z = pos
    if abs(y - 146) <= 2 and abs(z - 2546) <= 2:
        print(f"  {pos} (dist to goal: x={abs(x-6925)}, y={abs(y-146)}, z={abs(z-2546)})")
