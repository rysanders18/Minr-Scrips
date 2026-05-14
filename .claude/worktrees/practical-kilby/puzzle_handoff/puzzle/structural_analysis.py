#!/usr/bin/env python3
"""
Structural analysis: can RED ever reach (6925, 146, 2546)?

For red to end up at (6925, 146, 2546), at minimum some red must traverse a
path of single-step slides through chains of SAME COLOR. The red color locks
all reds to their (x, y, z) coordinates unless they share (y, z) for X-chain,
(x, z) for Y-chain, or (x, y) for Z-chain with another red.

Let's enumerate ALL possible positions ANY red could EVER reach, under the
relaxation: forget about blockers, just consider chain-formation logic.

Key insight: a red at position P can move only if it's in a chain with
another red. So we track (red_positions_set) and iteratively:
- For each pair of reds that share two coordinates, they form a potential
  chain along the non-shared axis. That chain can slide (under relaxation)
  to any position along that axis (within the grid).
- Sliding can bring a red to any position along the chain's axis.
- After sliding, new reds at new positions may enable new chains.

Compute closure. If (6925, 146, 2546) is NOT in the closure, puzzle is
structurally unsolvable.
"""

from fast_engine import parse_initial, COLOR_IDS, X_MIN, X_MAX, Y_MIN, Y_MAX, Z_MIN, Z_MAX

RED = COLOR_IDS['red']

def compute_closure(initial_reds):
    """
    Relaxed chain-slide closure: ignore blockers.
    For any pair sharing 2 coords, axis-chain slides to any valid x/y/z.
    """
    reds = set(initial_reds)
    changed = True
    iterations = 0
    while changed and iterations < 100:
        changed = False
        iterations += 1
        new = set(reds)
        reds_list = sorted(reds)
        n = len(reds_list)
        for i in range(n):
            for j in range(i+1, n):
                a = reds_list[i]
                b = reds_list[j]
                diff = tuple(b[k]-a[k] for k in range(3))
                shared = [k for k in range(3) if diff[k] == 0]
                if len(shared) != 2:
                    continue
                axis = [k for k in range(3) if diff[k] != 0][0]
                # Chain of length |diff[axis]|+1 with reds at endpoints
                # Under relaxation, this chain can slide along axis to any positions
                # where endpoints are within grid
                # Chain spans from min to max on axis
                chain_min = min(a[axis], b[axis])
                chain_max = max(a[axis], b[axis])
                chain_len = chain_max - chain_min + 1
                # After sliding, chain can occupy any starting min_slide where
                # min_slide in [axis_min, axis_max - chain_len + 1]
                axis_min = [X_MIN, Y_MIN, Z_MIN][axis]
                axis_max = [X_MAX, Y_MAX, Z_MAX][axis]
                # For chain to slide to new starting pos s (new chain_min):
                # s in [axis_min, axis_max - chain_len + 1]
                # but reality: chain can land ANYWHERE in this range (relaxation)
                # RELAXATION: only endpoints move (but that's what we care about for reds)
                # NOTE: the MIDDLES of the chain are stained-glass of same color.
                # They must be there already! If there's no red middle, no chain forms.
                # So we actually need reds AT EVERY intermediate position too.
                # Under STRICT rule: the chain of length 2 needs only 2 reds.
                # For this pair (dist=|axis diff|+1), middles must be red-stained-glass.
                # If dist > 1, we need reds at intermediate positions.
                # The pair (a, b) forms a chain only if reds exist at each intermediate.

                # For exact modeling, only pairs with dist==1 can directly form chain.
                # Higher dists require filling middles.
                if chain_len > 2:
                    # Check all middles are red
                    all_red = all(tuple(a[k] if k != axis else pos for k in range(3))
                                  in reds for pos in range(chain_min+1, chain_max))
                    if not all_red:
                        continue
                # Chain can slide — generate all possible new endpoint positions
                # New endpoint positions for the FIRST red: axis_min to axis_max - chain_len + 1
                # Then reds at (new_start, new_start+1, ..., new_start+chain_len-1)
                # But only endpoints are guaranteed red — middles are color only within chain.
                # After slide, ALL chain positions carry the block that was originally there.
                # For red endpoints, they remain red at new positions.
                # For red middles, they remain red at new positions too.
                # So: ALL chain_len reds move together.
                for new_start in range(axis_min, axis_max - chain_len + 2):
                    # New positions
                    new_positions = []
                    for k in range(chain_len):
                        p = list(a)
                        p[axis] = new_start + k
                        new_positions.append(tuple(p))
                    # Old positions to remove
                    old_positions = []
                    for k in range(chain_len):
                        p = list(a)
                        p[axis] = chain_min + k
                        old_positions.append(tuple(p))
                    # In closure we just add new positions without removing old
                    # (closure = union of all reachable)
                    for np in new_positions:
                        if np not in new:
                            new.add(np)
                            changed = True
        reds = new
        if iterations <= 5 or iterations % 5 == 0:
            print(f'Iter {iterations}: |reds| = {len(reds)}')
    return reds


def main():
    state = parse_initial()
    initial_reds = set(tuple(k) for k in
                       [(int(pi)//64 + X_MIN, (int(pi)%64)//8 + Y_MIN, int(pi)%8 + Z_MIN)
                        for pi, (c, _) in state.grid.items() if c == RED])
    # Simpler:
    from fast_engine import int_to_pos
    initial_reds = set(int_to_pos(pi) for pi, (c, _) in state.grid.items() if c == RED)
    print(f'Initial reds: {sorted(initial_reds)}')
    closure = compute_closure(initial_reds)
    print(f'\nClosure size: {len(closure)}')
    goal = (6925, 146, 2546)
    if goal in closure:
        print(f'Goal {goal} IS in the closure — solution is THEORETICALLY possible.')
    else:
        print(f'Goal {goal} is NOT in the closure — structurally unsolvable under relaxed rules.')
    # Show closure positions near goal
    near_goal = [p for p in closure if abs(p[0]-goal[0]) <= 2 and abs(p[1]-goal[1]) <= 2 and abs(p[2]-goal[2]) <= 2]
    print(f'\nClosure positions within 2-dist of goal:')
    for p in sorted(near_goal):
        print(f'  {p}')


if __name__ == '__main__':
    main()
