# Puzzle Solver — Final Report

## Status: No valid solution found

Two Claude sessions (this one + a subagent) independently searched from multiple
angles and converged on the same structural conclusion under the rules as
written in `HANDOFF.md` and implemented in `fast_engine.py`:

**The puzzle appears unsolvable.** Red cannot reach (6925, 146, 2546).

## What was accomplished

1. **Phase 1 validated end-to-end.** `validate_phase1.py` confirms the 15-move
   `phase1_solution.txt` sequence runs cleanly through the engine with 19
   conversions, placing green concretes at (6925, 146, 2547) and
   (6925, 146, 2548).

2. **Novel cascade found that DOES move red.** Despite the handoff's implication
   that reds cannot move at all without pre-existing cascades, I found a
   3-extra-move cascade that slides the red X-chain:

   ```
   green X-chain (6925, 149, 2548)..(6926, 149, 2548) slide +X×2
   green Y-chain (6928, 148, 2548)..(6928, 149, 2548) slide -Y×3
       [convert: ((6928, 148, 2548),)]
   red X-chain (6926, 148, 2548)..(6927, 148, 2548) slide +X×1
       [convert: ((6926, 148, 2548), (6927, 148, 2548))]
   ```

   This demonstrates reds ARE mobile — but only along x at y=148, z=2548.
   Saved in `best_partial_solution.txt` (18 moves, 22 conversions).

## Why red can't reach (6925, 146, 2546)

The goal cell is at y=146, z=2546. Reds can only be moved as part of red chains.

- **Only formable red chains** at any point through any cascade are:
  - Red X-chain at y=148, z=2548 (the original (6926–6927)).
  - After the cascade above, it extends/shifts to x∈{6925..6928} at y=148, z=2548.
- Red chains slide only along their axis — an X-chain preserves y and z.
- Therefore no red the X-chain moves ever reaches y=146 or z=2546.

- **Every other red** is isolated (no other red shares any two coordinates):
  - (6926, 146, 2546), (6930, 146, 2546) — the only collinear pair on the
    goal plane, but separated by 3 empty cells.
  - The other 9 reds each have no same-(x,y), same-(x,z), or same-(y,z) red
    partner at all.
- An isolated red can never become part of a chain (middles of a would-be chain
  have to be same-color, and no red can be pushed into those middles because
  no red chain reaches the needed x/y/z).

Therefore no red chain can ever be formed with (6925, 146, 2546) as
endpoint or middle. The goal cell can never be occupied by a red block.

## Interweaving (rule 5) does not save this

The subagent implemented three interpretations of interweaving in
`fast_engine_v2.py`. Interweaving requires TWO pure 2-block chains of the
SAME COLOR sharing an endpoint. Red has only ONE formable 2-block chain (the
X-chain at y=148, z=2548) — there's no second red 2-block chain to interweave
with, in the initial state or any reachable state tested.

## Search effort

- Beam search widths 300–3000, depths up to 30.
- IDA* with low-memory tuning.
- Reachability BFS from initial state up to depth 4 (~310k states, 0 new red
  footprints).
- Targeted purple-deposit BFS to see if (6925, 148, 2548) purple blocker could
  ever be dislodged (it cannot — Y-chain requires purple middles at y=149,
  y=150 on x=6925, z=2548, and no purple chain exists that can deposit there).
- Search with interweaving: 91 compound moves from phase 1 end (vs 58
  without), reached same plateau.

Across all attempts: best heuristic value plateaued with the goal cell
occupied by green and no red anywhere near the y=146, z=2546 plane.

## What would unblock progress

1. **Confirm the goal.** Is it really red-concrete at (6925, 146, 2546), or
   could it be green-concrete? If green, the goal is reachable: convert
   (6925, 146, 2546) after Phase 1 → green concrete at goal (20 moves, 20
   conversions).
2. **Different Phase 1.** Ryan manually found a working solution, so maybe
   the validated Phase 1 misallocates conversions in a way that locks the
   board. Re-planning Phase 1 with red mobility (not green adjacency) as
   the primary objective might enable a different endgame.
3. **Additional rule we're missing.** Interweaving, pushing, merging, or
   some other mechanic documented elsewhere than HANDOFF.md.
4. **Misread of the initial state.** Re-verify that (6925, 146, 2546)
   really is green in the source-of-truth setblock commands (not red).

## Files left for you

- `phase1_solution.txt` — validated Phase 1 (15 moves, 19 conversions)
- `best_partial_solution.txt` — Phase 1 + red-mobility cascade (18 moves, 22
  conversions, reds moved but goal not won)
- `validate_phase1.py` — validates any move sequence against fast_engine.py
- `check_solvable.py` — prints the structural solvability analysis
- `analyze_after_phase1.py` — post-Phase-1 state dump + formable chains
- `manual_cascade.py` — runs the red-mobility cascade and shows the result
- `trace_purple.py` — purple-deposit reachability BFS
- `fast_engine_v2.py` — interweaving-aware engine (from subagent)
- `search_v2.py`, `search_v2b.py`, `search_v2c.py` — attempted searches with
  interweaving
- `solve_endgame.py` — phase-3 beam search used by this session
- `novel_solver.py`, `focused_solver.py`, `red_reachability.py`,
  `layered_reach.py`, `structural_analysis.py` — subagent artifacts
