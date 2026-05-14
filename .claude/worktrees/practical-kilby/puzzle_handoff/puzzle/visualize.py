#!/usr/bin/env python3
"""Visualize the puzzle layer by layer and analyze the critical red path."""

from collections import defaultdict

# Parse blocks (same as before)
RAW = """
/setblock 6928 145 2551 minecraft:purple_stained_glass
/setblock 6928 145 2550 minecraft:purple_stained_glass
/setblock 6928 145 2549 minecraft:purple_stained_glass
/setblock 6926 146 2551 minecraft:blue_stained_glass
/setblock 6927 146 2551 minecraft:red_stained_glass
/setblock 6928 146 2551 minecraft:purple_stained_glass
/setblock 6925 146 2550 minecraft:purple_stained_glass
/setblock 6926 146 2550 minecraft:blue_stained_glass
/setblock 6928 146 2550 minecraft:purple_stained_glass
/setblock 6929 146 2550 minecraft:purple_stained_glass
/setblock 6931 146 2550 minecraft:red_stained_glass
/setblock 6925 146 2549 minecraft:green_stained_glass
/setblock 6931 146 2548 minecraft:cyan_stained_glass
/setblock 6925 146 2546 minecraft:green_stained_glass
/setblock 6926 146 2546 minecraft:red_stained_glass
/setblock 6930 146 2546 minecraft:red_stained_glass
/setblock 6927 146 2544 minecraft:purple_stained_glass
/setblock 6926 147 2551 minecraft:blue_stained_glass
/setblock 6927 147 2550 minecraft:purple_stained_glass
/setblock 6929 147 2550 minecraft:blue_stained_glass
/setblock 6926 147 2548 minecraft:blue_stained_glass
/setblock 6929 147 2548 minecraft:blue_stained_glass
/setblock 6931 147 2548 minecraft:cyan_stained_glass
/setblock 6928 147 2546 minecraft:blue_stained_glass
/setblock 6927 147 2545 minecraft:red_stained_glass
/setblock 6930 147 2545 minecraft:green_stained_glass
/setblock 6925 147 2544 minecraft:purple_stained_glass
/setblock 6931 147 2544 minecraft:red_stained_glass
/setblock 6928 148 2550 minecraft:blue_stained_glass
/setblock 6930 148 2550 minecraft:pink_stained_glass
/setblock 6928 148 2549 minecraft:green_stained_glass
/setblock 6930 148 2549 minecraft:pink_stained_glass
/setblock 6925 148 2548 minecraft:purple_stained_glass
/setblock 6926 148 2548 minecraft:red_stained_glass
/setblock 6927 148 2548 minecraft:red_stained_glass
/setblock 6928 148 2548 minecraft:green_stained_glass
/setblock 6929 148 2548 minecraft:brown_stained_glass
/setblock 6930 148 2548 minecraft:pink_stained_glass
/setblock 6931 148 2548 minecraft:cyan_stained_glass
/setblock 6928 148 2547 minecraft:blue_stained_glass
/setblock 6930 148 2547 minecraft:pink_stained_glass
/setblock 6931 148 2547 minecraft:red_stained_glass
/setblock 6926 148 2546 minecraft:blue_stained_glass
/setblock 6930 148 2546 minecraft:pink_stained_glass
/setblock 6930 148 2545 minecraft:green_stained_glass
/setblock 6928 148 2544 minecraft:orange_stained_glass
/setblock 6929 148 2544 minecraft:orange_stained_glass
/setblock 6930 148 2544 minecraft:pink_stained_glass
/setblock 6929 149 2551 minecraft:blue_stained_glass
/setblock 6929 149 2550 minecraft:green_stained_glass
/setblock 6926 149 2549 minecraft:green_stained_glass
/setblock 6927 149 2548 minecraft:green_stained_glass
/setblock 6929 149 2548 minecraft:brown_stained_glass
/setblock 6931 149 2548 minecraft:cyan_stained_glass
/setblock 6932 149 2548 minecraft:red_stained_glass
/setblock 6929 149 2547 minecraft:green_stained_glass
/setblock 6928 149 2546 minecraft:purple_stained_glass
/setblock 6930 149 2546 minecraft:green_stained_glass
/setblock 6925 149 2545 minecraft:purple_stained_glass
/setblock 6929 149 2544 minecraft:orange_stained_glass
/setblock 6930 149 2544 minecraft:pink_stained_glass
/setblock 6927 150 2551 minecraft:blue_stained_glass
/setblock 6930 150 2551 minecraft:orange_stained_glass
/setblock 6925 150 2550 minecraft:green_stained_glass
/setblock 6932 150 2550 minecraft:orange_stained_glass
/setblock 6929 150 2548 minecraft:brown_stained_glass
/setblock 6931 150 2548 minecraft:cyan_stained_glass
/setblock 6932 150 2548 minecraft:orange_stained_glass
/setblock 6926 150 2545 minecraft:blue_stained_glass
/setblock 6929 150 2545 minecraft:orange_stained_glass
/setblock 6929 151 2550 minecraft:green_stained_glass
/setblock 6925 151 2548 minecraft:purple_stained_glass
/setblock 6929 151 2548 minecraft:brown_stained_glass
/setblock 6931 151 2548 minecraft:cyan_stained_glass
/setblock 6928 151 2546 minecraft:purple_stained_glass
/setblock 6930 151 2546 minecraft:green_stained_glass
/setblock 6926 151 2545 minecraft:red_stained_glass
/setblock 6930 151 2545 minecraft:green_stained_glass
/setblock 6928 152 2550 minecraft:purple_stained_glass
/setblock 6926 152 2549 minecraft:blue_stained_glass
/setblock 6926 152 2548 minecraft:purple_stained_glass
/setblock 6928 152 2548 minecraft:purple_stained_glass
/setblock 6929 152 2548 minecraft:brown_stained_glass
/setblock 6931 152 2548 minecraft:red_stained_glass
/setblock 6926 152 2547 minecraft:red_stained_glass
/setblock 6927 152 2547 minecraft:purple_stained_glass
"""

SEA_LANTERN = (6924, 146, 2546)
GOAL_POS = (6925, 146, 2546)
X_MIN, X_MAX = 6925, 6932
Y_MIN, Y_MAX = 145, 152
Z_MIN, Z_MAX = 2544, 2551

blocks = {}
for line in RAW.strip().split('\n'):
    line = line.strip()
    if not line or not line.startswith('/setblock'):
        continue
    parts = line.split()
    x, y, z = int(parts[1]), int(parts[2]), int(parts[3])
    block_type = parts[4].replace('minecraft:', '').replace('_stained_glass', '')
    blocks[(x, y, z)] = block_type

# Color abbreviations for display
COLOR_ABBREV = {
    'red': 'R',
    'blue': 'B',
    'green': 'G',
    'purple': 'P',
    'pink': 'K',
    'orange': 'O',
    'cyan': 'C',
    'brown': 'W',  # W for broWn
}

def display_layer(y):
    """Display a horizontal slice at Y level. X is columns, Z is rows (descending)."""
    print(f"\n{'='*60}")
    print(f"  Y={y} (layer {y - Y_MIN})    X →")
    print(f"  Z ↓  ", end="")
    for x in range(X_MIN, X_MAX + 1):
        print(f" {x%100:2d}", end="")
    print()
    print(f"       ", end="")
    for x in range(X_MIN, X_MAX + 1):
        print(f" --", end="")
    print()
    
    for z in range(Z_MAX, Z_MIN - 1, -1):
        print(f"  {z%100:2d} | ", end="")
        for x in range(X_MIN, X_MAX + 1):
            pos = (x, y, z)
            if pos == GOAL_POS and y == 146:
                # Mark the goal
                c = blocks.get(pos, '')
                if c:
                    print(f" {COLOR_ABBREV.get(c, '?')}*", end="")
                else:
                    print(" **", end="")
            elif pos in blocks:
                print(f"  {COLOR_ABBREV.get(blocks[pos], '?')}", end="")
            else:
                print("  .", end="")
        # Sea lantern annotation
        if y == 146 and z == 2546:
            print(f"  ← SEA LANTERN at x={SEA_LANTERN[0]}", end="")
        print()

for y in range(Y_MIN, Y_MAX + 1):
    display_layer(y)

# Analyze: what blocks are in the column above/below the goal position?
print(f"\n{'='*60}")
print(f"Vertical column at x=6925, z=2546 (above/below goal):")
for y in range(Y_MIN, Y_MAX + 1):
    pos = (6925, y, 2546)
    c = blocks.get(pos, 'EMPTY')
    marker = " ← GOAL Y-LEVEL" if y == 146 else ""
    print(f"  y={y}: {c}{marker}")

print(f"\nVertical column at x=6926, z=2546 (one right of goal):")
for y in range(Y_MIN, Y_MAX + 1):
    pos = (6926, y, 2546)
    c = blocks.get(pos, 'EMPTY')
    print(f"  y={y}: {c}")

# What's in the way if we want to slide red along X at y=146, z=2546?
print(f"\n{'='*60}")
print(f"X-row at y=146, z=2546 (the red path to goal):")
for x in range(6924, 6933):
    pos = (x, 146, 2546)
    if pos == SEA_LANTERN:
        print(f"  x={x}: SEA LANTERN")
    else:
        c = blocks.get(pos, 'EMPTY')
        print(f"  x={x}: {c}")

# Analyze what chains could potentially be formed to move the green at (6925,146,2546)
print(f"\n{'='*60}")
print(f"Analyzing green block at (6925,146,2546) - BLOCKER")
print(f"Green blocks that share an axis with it:")
gx, gy, gz = 6925, 146, 2546
by_color = defaultdict(list)
for pos, color in blocks.items():
    by_color[color].append(pos)

for pos in sorted(by_color['green']):
    x, y, z = pos
    if x == gx and z == gz and y != gy:
        print(f"  Y-axis: {pos} (could form Y-chain)")
    if x == gx and y == gy and z != gz:
        print(f"  Z-axis: {pos} (could form Z-chain)")
    if y == gy and z == gz and x != gx:
        print(f"  X-axis: {pos} (could form X-chain)")

print(f"\nAll green blocks:")
for pos in sorted(by_color['green']):
    print(f"  {pos}")

# What about moving green at goal via Z-axis?
print(f"\nZ-row at x=6925, y=146 (could form green Z-chain):")
for z in range(Z_MIN, Z_MAX + 1):
    pos = (6925, 146, z)
    c = blocks.get(pos, 'EMPTY')
    print(f"  z={z}: {c}")
