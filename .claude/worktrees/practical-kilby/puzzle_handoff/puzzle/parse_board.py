#!/usr/bin/env python3
"""Parse the Minecraft sliding block puzzle and analyze it."""

from collections import defaultdict

# Raw setblock commands
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
GOAL_POS = (6925, 146, 2546)  # Red concrete must reach here

# Parse
blocks = {}
for line in RAW.strip().split('\n'):
    line = line.strip()
    if not line or not line.startswith('/setblock'):
        continue
    parts = line.split()
    x, y, z = int(parts[1]), int(parts[2]), int(parts[3])
    block_type = parts[4].replace('minecraft:', '').replace('_stained_glass', '')
    blocks[(x, y, z)] = block_type

# Coordinate ranges
xs = sorted(set(p[0] for p in blocks))
ys = sorted(set(p[1] for p in blocks))
zs = sorted(set(p[2] for p in blocks))

print(f"Total blocks: {len(blocks)}")
print(f"X range: {min(xs)}-{max(xs)} ({max(xs)-min(xs)+1} wide)")
print(f"Y range: {min(ys)}-{max(ys)} ({max(ys)-min(ys)+1} tall)")
print(f"Z range: {min(zs)}-{max(zs)} ({max(zs)-min(zs)+1} deep)")
print(f"Sea lantern: {SEA_LANTERN}")
print(f"Goal position (red concrete needed): {GOAL_POS}")
print(f"Current block at goal: {blocks.get(GOAL_POS, 'EMPTY')}")

# Count by color
by_color = defaultdict(list)
for pos, color in blocks.items():
    by_color[color].append(pos)

print(f"\nBlocks by color:")
for color, positions in sorted(by_color.items(), key=lambda x: -len(x[1])):
    print(f"  {color}: {len(positions)}")

# Analyze red blocks specifically
print(f"\nRed block positions:")
for pos in sorted(by_color['red']):
    print(f"  {pos}")

# Find potential chain lines for red blocks
# A chain line is a set of same-color blocks that are collinear along one axis
print(f"\n=== Potential chain analysis (all colors) ===")
for color, positions in sorted(by_color.items()):
    # Group by (axis, other two coords)
    # X-axis chains: same Y,Z, different X
    # Y-axis chains: same X,Z, different Y
    # Z-axis chains: same X,Y, different Z
    
    x_groups = defaultdict(list)
    y_groups = defaultdict(list)
    z_groups = defaultdict(list)
    
    for x, y, z in positions:
        x_groups[(y, z)].append(x)
        y_groups[(x, z)].append(y)
        z_groups[(x, y)].append(z)
    
    chains = []
    for (y, z), x_vals in x_groups.items():
        if len(x_vals) >= 2:
            x_vals_s = sorted(x_vals)
            # Check if contiguous
            is_contiguous = all(x_vals_s[i+1] - x_vals_s[i] == 1 for i in range(len(x_vals_s)-1))
            chains.append(('X', f"y={y},z={z}", x_vals_s, is_contiguous))
    
    for (x, z), y_vals in y_groups.items():
        if len(y_vals) >= 2:
            y_vals_s = sorted(y_vals)
            is_contiguous = all(y_vals_s[i+1] - y_vals_s[i] == 1 for i in range(len(y_vals_s)-1))
            chains.append(('Y', f"x={x},z={z}", y_vals_s, is_contiguous))
    
    for (x, y), z_vals in z_groups.items():
        if len(z_vals) >= 2:
            z_vals_s = sorted(z_vals)
            is_contiguous = all(z_vals_s[i+1] - z_vals_s[i] == 1 for i in range(len(z_vals_s)-1))
            chains.append(('Z', f"x={x},y={y}", z_vals_s, is_contiguous))
    
    if chains:
        print(f"\n{color}:")
        for axis, coords, vals, contig in chains:
            gap_info = "CONTIGUOUS" if contig else "HAS GAPS"
            # Check if other colored blocks fill the gaps
            if not contig:
                gap_blocks = []
                for i in range(len(vals)-1):
                    for v in range(vals[i]+1, vals[i+1]):
                        if axis == 'X':
                            y_val, z_val = int(coords.split(',')[0].split('=')[1]), int(coords.split(',')[1].split('=')[1])
                            gap_pos = (v, y_val, z_val)
                        elif axis == 'Y':
                            x_val, z_val = int(coords.split(',')[0].split('=')[1]), int(coords.split(',')[1].split('=')[1])
                            gap_pos = (x_val, v, z_val)
                        else:
                            x_val, y_val = int(coords.split(',')[0].split('=')[1]), int(coords.split(',')[1].split('=')[1])
                            gap_pos = (x_val, y_val, v)
                        gap_block = blocks.get(gap_pos, 'EMPTY')
                        gap_blocks.append(f"{gap_pos}={gap_block}")
                gap_info += f" gaps: {gap_blocks}"
            print(f"  {axis}-axis at {coords}: vals={vals} ({gap_info})")

# Show what's between the nearest red block and the goal along X axis at y=146, z=2546
print(f"\n=== Path analysis: red to goal at y=146, z=2546 along X-axis ===")
for x in range(6924, 6933):
    pos = (x, 146, 2546)
    if pos == SEA_LANTERN:
        print(f"  x={x}: SEA LANTERN")
    elif pos in blocks:
        print(f"  x={x}: {blocks[pos]}")
    else:
        print(f"  x={x}: empty")
