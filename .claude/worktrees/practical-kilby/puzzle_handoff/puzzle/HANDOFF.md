# 3D Minecraft Sliding Block Puzzle — Solver Project

## Status

You're handing this off to a new Claude session (likely Cowork). Read this file first, then the code files in order listed.

## The Puzzle

- **Grid**: 8×8×8 (x 6925–6932, y 145–152, z 2544–2551), hard walls on all sides
- **86 colored stained-glass blocks**, 8 colors
- **Goal**: get a **red concrete** block adjacent to the sea lantern at (6924, 146, 2546)
- Only in-grid adjacent cell: **(6925, 146, 2546)** — currently a green stained-glass block (the "blocker")

## Core Rules

1. Blocks start as stained glass. Convert to concrete (irreversible). Budget: **60 total conversions**.
2. A **chain** = 2 same-color concrete endpoints + any number of same-color stained-glass in between, **collinear on one axis**.
3. A chain slides 1 block at a time along its axis. Blocked by: other blocks OR the grid boundary.
4. Blocks can only move as part of a chain of their own color. Chains don't push — they're just blocked.
5. Two same-color chains may share an endpoint ("interweave"). Clicking that shared endpoint moves both — but **only** if both chains have no stained glass between endpoints (i.e. pure 2-block chains).
6. Click direction controls slide direction: click the end from the side you want the chain to move toward.

## Key Structural Facts (verified)

- **Only directly-formable green chains**: G11-G12 Y-chain at (x=6930, z=2545), G14-G15 Z-chain at (x=6930, y=151), G6-G7 Z-chain at (x=6928, y=148) — but G6-G7 is forever blocked by isolated blues at z=2547 and z=2550.
- **The only formable red chain initially**: X-chain at y=148, z=2548 (the "two adjacent red blocks" Ryan references as the starting point).
- **Green blocker G2 at (6925, 146, 2546)** is isolated; no green X-chain directly formable (no two greens share (y, z)).
- **Reds can ONLY form an X-chain** — there are no red pairs sharing (x, y) or (x, z) for any Y or Z chain. That means reds are locked at y=148, z=2548 unless new chains form through cascading.

## The Unlock Mechanic: Cascading Chain Formation

The trick to this puzzle — chains moved into new positions create adjacencies that enable NEW chains with previously-isolated blocks. Verified example:

1. Convert G14 (6930, 151, 2545), G15 (6930, 151, 2546) → slide +Z×5 → G14 at (6930, 151, 2550)
2. G14 now adjacent to G10 at (6929, 151, 2550). Convert G10 → forms green X-chain at y=151, z=2550
3. Slide X-chain -X×4 → G10 at (6925, 151, 2550), G14 at (6926, 151, 2550)
4. G10 now adjacent to G3 at (6925, 150, 2550). Convert G3 → forms green Y-chain at x=6925, z=2550
5. Slide -Y×3 → blocked at y=147 by purple at (6925, 146, 2550)

This gets greens into x=6925 but stuck at z=2550. Further cascading required to reach the blocker.

## Ryan's Hint

> "Going from the start of the problem, which is navigating the only two adjacent red blocks."

The solution path likely starts by manipulating the red X-chain (y=148, z=2548) early, even though the green blocker must eventually be moved.

## Files

All code is in this folder. Dependencies: just stdlib Python 3.

- **`fast_engine.py`** — core engine. `parse_initial()`, `State` class, `compound_moves(state)`, `find_all_chains`, `slide_chain`, `max_slide`, `display_state`. Compact state (dict int→(color_id, is_concrete)), compound moves = form chain + slide N steps as one action. Run directly to see initial state + 56 compound moves available.
- **`verify_insight.py`** — manual trace of the G14→G10→G3 cascade. Run to confirm engine and mechanic.
- **`parse_board.py`** — board parser + chain analysis by color.
- **`analyze_green.py`** — proves green blocker isolation.
- **`analyze_red.py`** — red chain analysis.
- **`visualize.py`** — layer-by-layer ASCII visualization.
- **`phase1_solver.py`** — beam search + IDA* for Phase 1 (green adjacent to blocker).
- **`phase1_v2.py`** — second attempt at Phase 1.
- **`phase1_solution.txt`** — candidate Phase 1 move sequence (UNVERIFIED — needs to be re-run through engine to confirm validity and reaching the phase-1 goal).
- **`phase2.py`** / **`phase2_state.pkl`** — Phase 2 (move blocker G2 out).
- **`phase3_solver.py`** — Phase 3 (red concrete to goal).
- **`full_solver.py`** — end-to-end solver with structural heuristic.
- **`engine.py`**, **`solver.py`**, **`solver2.py`** — older versions, kept for reference, SLOW.

## Where Things Stand

**Completed and verified:**
- Engine mechanics (chain finding, sliding, conversion, compound moves)
- G14→G10→G3 cascade trace
- Structural analysis showing cascading is required

**Partial / unverified:**
- `phase1_solution.txt` exists but hasn't been validated end-to-end. First step should be: **apply these moves through `fast_engine` and check whether the resulting state has a green concrete adjacent to (6925, 146, 2546)**. If yes, Phase 1 is done and we move to Phase 2. If no, the solver got a false positive or the save is stale.

**Not yet working:**
- End-to-end solution. Full solver hasn't produced a validated path to goal.

## Suggested Next Steps

1. **Validate `phase1_solution.txt`**: write a small script that parses the file, applies each move via `compound_moves`, and prints whether Phase 1 goal (green concrete at any of the 4 blocker-adjacent positions) is achieved. This takes 5 minutes and tells you immediately whether to trust this output.
2. If Phase 1 is valid: build/run Phase 2 to move the blocker G2 out.
3. If not: go back to Phase 1 solver. The beam search approach is in `phase1_solver.py`. Wider beam + smarter heuristic + better move ordering will help. Consider seeding the search with the verified G14→G10→G3 cascade as a prefix.
4. Phase 3 (red to goal) requires the red X-chain at y=148, z=2548 to eventually end up with red concrete at (6925, 146, 2546). That needs Y or Z chain formation for red, which in turn needs cascading to align two reds at the same (x, y) or (x, z).
5. Once all phases chain together, output the final move list in the format Ryan wants: plain list of moves.

## Running

```bash
cd puzzle
python3 fast_engine.py          # sanity check: 56 compound moves from initial
python3 verify_insight.py       # trace the G14→G10→G3 cascade
python3 phase1_solver.py        # run Phase 1 search (currently beam search)
```

## Budget / Constraints

- 60 total conversions allowed across the entire solution
- Solution likely uses ~20-30 of them
- Solution depth probably 30-50 compound moves
- Memory: previous container had 4 GB limit and OOM'd around 17k nodes in blind A*. On Cowork/local you have more headroom — use it.

## Ryan's Preferences

- Output final answer first, then explain
- Concise prose, short sentences
- Make code changes directly in files, not suggested diffs in chat
- Be skeptical of assumptions Ryan states — correct errors rather than agree

## Context

This is a personal Minecraft puzzle Ryan is solving. He's already solved it manually before and says moving the green blocker is the hard part. He explicitly said he's willing to spend hours of compute on this.
