#!/usr/bin/env python3
"""List all blocks grouped by color."""
from fast_engine import parse_initial, int_to_pos, COLOR_IDS, ID_TO_COLOR
from collections import defaultdict

state = parse_initial()
by_color = defaultdict(list)
for pi, (c, is_c) in state.grid.items():
    by_color[ID_TO_COLOR[c]].append(int_to_pos(pi))

for color in sorted(by_color):
    ps = sorted(by_color[color])
    print(f"\n{color} ({len(ps)}):")
    for p in ps:
        print(f"  {p}")
