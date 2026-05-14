#!/usr/bin/env python3
"""Verify key insights about the puzzle by manually executing moves."""

from fast_engine import (
    State, parse_initial, compound_moves, find_formable_chains,
    find_all_chains, slide_chain, max_slide, pos_to_int, int_to_pos,
    COLOR_IDS, ID_TO_COLOR, display_state, GOAL_POS
)


def describe_greens(state, note=""):
    print(f"\n--- Greens {note} ---")
    greens = []
    for pi, (c, is_c) in state.grid.items():
        if c == COLOR_IDS['green']:
            pos = int_to_pos(pi)
            m = 'CONCRETE' if is_c else 'glass'
            greens.append((pos, m))
    for pos, m in sorted(greens):
        # Check adjacencies
        adj_greens = []
        for dx,dy,dz in [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)]:
            ap = (pos[0]+dx, pos[1]+dy, pos[2]+dz)
            v = state.get(ap)
            if v and v[0] == COLOR_IDS['green']:
                adj_greens.append(ap)
        adj_str = f" adj: {adj_greens}" if adj_greens else ""
        print(f"  {pos} [{m}]{adj_str}")


def verify_g14_g10():
    state = parse_initial()
    print("INITIAL STATE")
    describe_greens(state, "initial")
    
    # Step 1: Convert G14 (6930, 151, 2545) and G15 (6930, 151, 2546) to concrete
    state = state.convert((6930, 151, 2545))
    state = state.convert((6930, 151, 2546))
    print(f"\nConverted G14, G15. Conversions: {state.conversions}")
    
    # Step 2: Verify G14-G15 forms a Z-chain
    chains = find_all_chains(state)
    print(f"\nActive chains: {len(chains)}")
    for axis_idx, positions in chains:
        axis = ['X','Y','Z'][axis_idx]
        color = ID_TO_COLOR[state.get(positions[0])[0]]
        print(f"  {color} {axis}-chain: {list(positions)}")
    
    # Step 3: Slide G14-G15 +Z by 4 steps to reach z=2549-2550
    # Wait - we want G14 at z=2550. Starting z=2545-2546, +Z by 4: z=2549-2550.
    # G14 at z=2549? No. G14 starts at z=2545 (the lower end). After +Z by 4, G14 at z=2549, G15 at z=2550.
    # Hmm. I want G14 at z=2550 so it aligns with G10 at (6929, 151, 2550).
    # +Z by 5: G14 at z=2550, G15 at z=2551. Let me verify.
    g14_g15 = ((6930,151,2545), (6930,151,2546))
    axis_idx = 2  # Z-axis
    
    # Find the current chain
    chain_positions = find_all_chains(state)
    target_chain = None
    for a, p in chain_positions:
        if set(p) == set(g14_g15):
            target_chain = p
            break
    
    if not target_chain:
        print("ERROR: G14-G15 chain not found!")
        return
    
    print(f"\nSliding G14-G15 +Z...")
    cur = state
    cur_pos = list(target_chain)
    for step in range(1, 6):
        new_cur = slide_chain(cur, axis_idx, cur_pos, +1)
        cur_pos = [(p[0], p[1], p[2]+1) for p in cur_pos]
        cur = new_cur
        print(f"  Step {step}: chain at {cur_pos}")
    
    # Now G14 should be at (6930, 151, 2550)
    # G10 is at (6929, 151, 2550)
    g14_now = cur.get((6930, 151, 2550))
    g10 = cur.get((6929, 151, 2550))
    print(f"\n(6930, 151, 2550): {g14_now}")  # Should be green, concrete
    print(f"(6929, 151, 2550): {g10}")  # Should be green, glass
    
    # Step 4: Convert G10
    cur = cur.convert((6929, 151, 2550))
    print(f"\nConverted G10. Conversions: {cur.conversions}")
    
    # Step 5: Verify X-chain G10-G14
    chains = find_all_chains(cur)
    print(f"\nActive chains after converting G10:")
    for axis_idx, positions in chains:
        axis = ['X','Y','Z'][axis_idx]
        color = ID_TO_COLOR[cur.get(positions[0])[0]]
        print(f"  {color} {axis}-chain: {list(positions)}")
    
    # Step 6: Slide X-chain -X
    # X-chain should be at (6929, 151, 2550) - (6930, 151, 2550)
    # Slide -X 4 times to get to (6925, 151, 2550) - (6926, 151, 2550)
    print(f"\nSliding G10-G14 X-chain -X...")
    x_chain = ((6929, 151, 2550), (6930, 151, 2550))
    axis_idx = 0  # X-axis
    cur_pos = list(x_chain)
    for step in range(1, 5):
        if not all(cur.in_bounds((p[0]-1, p[1], p[2])) for p in cur_pos):
            print(f"  Out of bounds at step {step}")
            break
        # Check if can slide
        can = True
        for p in cur_pos:
            np = (p[0]-1, p[1], p[2])
            if np in cur_pos:
                continue
            if cur.get(np) is not None:
                print(f"  Blocked at step {step} by {cur.get(np)} at {np}")
                can = False
                break
        if not can:
            break
        new_cur = slide_chain(cur, axis_idx, cur_pos, -1)
        cur_pos = [(p[0]-1, p[1], p[2]) for p in cur_pos]
        cur = new_cur
        print(f"  Step {step}: chain at {cur_pos}")
    
    describe_greens(cur, "after X-chain slide")
    
    # Now let's check: is G10 now at x=6925?
    # And does it form a Y-chain with G3?
    g10_pos = None
    for pi, (c, is_c) in cur.grid.items():
        if c == COLOR_IDS['green'] and is_c:
            p = int_to_pos(pi)
            if p[1] == 151 and p[2] == 2550:
                print(f"  Concrete green at {p}")
    
    # G3 is at (6925, 150, 2550)
    g3 = cur.get((6925, 150, 2550))
    print(f"\n(6925, 150, 2550) = {g3}")  # Should be green, glass
    # If g10 is at (6925, 151, 2550), we can form Y-chain with G3
    
    # Step 7: Convert G3 to concrete to form Y-chain G3-G10
    cur = cur.convert((6925, 150, 2550))
    print(f"\nConverted G3. Conversions: {cur.conversions}")
    
    chains = find_all_chains(cur)
    print(f"\nActive chains after converting G3:")
    for axis_idx, positions in chains:
        axis = ['X','Y','Z'][axis_idx]
        color = ID_TO_COLOR[cur.get(positions[0])[0]]
        print(f"  {color} {axis}-chain: {list(positions)}")
    
    # Slide Y-chain -Y as far as possible
    print(f"\nSliding G3-G10 Y-chain -Y...")
    y_chain = ((6925, 150, 2550), (6925, 151, 2550))
    axis_idx = 1
    cur_pos = list(y_chain)
    for step in range(1, 10):
        can = True
        for p in cur_pos:
            np = (p[0], p[1]-1, p[2])
            if np in cur_pos:
                continue
            if not cur.in_bounds(np):
                print(f"  OOB at step {step}")
                can = False
                break
            if cur.get(np) is not None:
                print(f"  Blocked at step {step} by {cur.get(np)} at {np}")
                can = False
                break
        if not can:
            break
        new_cur = slide_chain(cur, axis_idx, cur_pos, -1)
        cur_pos = [(p[0], p[1]-1, p[2]) for p in cur_pos]
        cur = new_cur
        print(f"  Step {step}: chain at {cur_pos}")
    
    describe_greens(cur, "after Y-chain slide")
    print(f"\nConversions used: {cur.conversions}")


verify_g14_g10()
