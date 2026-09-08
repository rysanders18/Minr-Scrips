# WALLS_PLAN.md — decoration rework, stage 1: smooth gap-free walls

Complete rework of the decoration generation (the old `wall_test.py`
pipeline). The path generator (`generate_maze_v3.py`) and everything
about the slime path is UNTOUCHED — this consumes the sim read-only.

Stage 1 scope: **walls only**, all `smooth_stone`. No floor, no dome,
no material classes (panels/piers/tuff), no bands, no lanterns. Those
come later as separate stages on top of the same core.

## Decisions (locked in with Ryan, 2026-08-13)

| Decision | Choice |
|---|---|
| Wall distance from centerline | **~4 blocks** (nominal wall line at d≈4, so ~3 air cells between the slime column and the wall's inner face) |
| Vertical band per column | **path−4 .. path+6** (11 tall), following the local path level |
| Junctions / close corridors | **Merged caverns**: union all corridor air, walls trace only the outer boundary of the merged space |
| Smoothness tolerance | **±1 block drift** from the exact offset distance, spent on long clean runs with no single-block zigzags |
| Generator | **v3 only** (`generate_maze_v3.py`); the v2 `WT_GM` env switch dies |
| Output | **Datapack-first iteration**: emit `walls1..N.msc` / `removewalls1..N.msc` chains (they stay the interchange format `make_datapack.py` reads), then `make_datapack.py --install` for in-world testing. MSC chains are therefore also the final Minr deliverable for free. |
| File layout | **Fresh script `walls.py`**, written from scratch. `wall_test.py` stays untouched as reference until the new pipeline is proven in-world, then gets deleted. |
| Splice stamping | **From day one** — walls are painted into a world model, window tubes copied over tail tubes before emission, so every in-world test is already teleport-seamless |
| Seal beats identity (added 2026-08-13) | Ryan: every section must be **sealed and enclosed**. After the stamp, `seal_repair` rebuilds the painter boundary at every unsealed face — tail endcaps (the same rounded cap as section starts), cavern-mouth backdrops, guard patches. The window/tail divergence this creates sits 3–5 bounces past the swap trigger where bounce curvature occludes it. The verifier hard-gates emission on **zero unsealed lateral faces everywhere**, splice tubes included; vertical enclosure is the dome/floor stages' job. |

## Hard requirements

1. **Absolutely no gaps.** At every y-slice, no line from corridor
   interior to outside may pass through anything but a wall cell.
   Diagonal block-pairs sharing an edge count as sealed (standard
   Minecraft corner).
2. **Exactly 1 block thick.** Wall = boundary cells only. Outside
   corners (cells touching the interior only diagonally) are
   deliberately NOT filled.
3. **Smooth.** No 1-block in/out jitter along a run. The wall may
   drift ±1 from the ideal offset to achieve this.
4. **Never touches the path.** No wall cell may land on a slime block
   or on the carpet/trigger layer (path y+1) cells above/around it.
5. **Splice-seamless.** Around every splice tail, the world is an
   exact translated copy of the window's surroundings.

## Core algorithm: per-y-slice footprint boundary

The old approach (sample the offset curve, quantize each offset point
to a column) is what produced jitter and gap risk — quantizing a
*curve* gives you noisy, possibly disconnected cells. The rework
inverts it: rasterize the *interior region*, then take its boundary.
A boundary of a filled region is gap-free and 1-thick by construction.

### 1. Centerline sampling
Load the v3 sim at the emitted seed (read from `slimemaze.nms`, same
trick as `wall_test.emitted_seed`). For each branch, run a Catmull-Rom
spline through its bounce-block centers (concept carried over from
wall_test — this describes the path, which is unchanged) and sample it
at a fine stride (~0.4). Each sample carries `(fx, fz, py)` where `py`
is the interpolated local path level.

### 2. Distance field per y-slice
For every integer y in the maze's range, build a 2D field over plan
cells: `d(x, z, y)` = min horizontal distance from the cell center to
any sample whose band `[py−4, py+6]` covers y. (Spatial hash over
samples keeps this fast — same trick as the v3 skeleton work.)

### 3. Open region with smoothing hysteresis
Per y-slice:
- **hard-open**: `d ≤ 2.5` → must be air (this protects the path and
  bounce clearance);
- **hard-outside**: `d ≥ 4.5` → must not be open;
- **flexible band**: `2.5 < d < 4.5` — these cells may go either way;
  this band is exactly the ±1 drift budget. (Air reaches d<3.5, so
  wall cells sit at d≈3.5–4.5 — centers ~4 from the centerline, the
  "narrower ~4" decision.)

Initialize `open = {d < 3.5}`, then run a boundary-relaxation pass
over flexible cells only: repeatedly flip a flexible cell to the
majority of its 8 neighbours when doing so shortens the region's
perimeter, until fixpoint (bounded iterations). Result: the same
region, but with 1-cell dents and bumps ironed out into long straight
or clean-staircase runs. Merged caverns need no special casing — the
union of all samples IS the region, so forks, junctions and close
corridors merge automatically and walls only ever trace the outside.

### 4. Wall extraction
`wall[y] = { cell ∉ open[y] : cell is 4-adjacent to a cell ∈ open[y] }`.

Properties, all by construction:
- gap-free per slice (every face of the region is covered; diagonal
  steps produce edge-sharing wall pairs — sealed);
- exactly 1 thick;
- inner corners filled, outer corners not (they're only diagonal to
  the interior, so the 4-adjacency test excludes them).

### 5. Vertical regularization
Columns should read as clean vertical stacks. Two cheap passes:
- **hole fill**: if `(x,z)` is wall at y−1 and y+1 but not at y, and
  not open at y, make it wall (kills 1-block horizontal seams where
  the band steps down along the descending path);
- sanity: never place wall where `open` says air, at any y.

### 6. World model + splice stamp
Paint every wall cell into a single dict `(x,y,z) → 'smooth_stone'`,
with `open` cells recorded as explicit air. Then port the stamp pass
from wall_test *as a mechanism* (it operates on the final world model,
independent of how the walls were painted): for each splice,
highest-window-first, copy the window tube (columns within SHELL_R of
the window stretch, band-limited in y, air included) onto the tail
tube. Keep the Phase-5 stamp-intrusion guards (INTRUDE window +
margin) — that repair was hard-won (96/30 → 67/3) and the failure
mode (a stamp carving a foreign corridor's shell near the tail) exists
regardless of wall style.

### 7. Emission
- Collapse each column's contiguous same-material vertical run into
  one `/fill x y1 z x y2 z minecraft:smooth_stone strict` (walls are
  ~11-tall stacks → ~10x fewer commands than setblock-per-cell).
- Emit `walls1..N.msc` / `removewalls1..N.msc` with the established
  REGION-bucket tp + `@delay 10` chunk-loading pattern and part
  chaining (reuse the emit_chain/split machinery pattern; hastebin
  line cap still applies to the Minr route).
- Rewrite the walls/removewalls declarations in `slimemaze.nms`
  (replacing whatever wall/dome/floor declarations stand — dome/floor
  chains no longer exist in stage 1, so their declarations and any
  stale `dome*/floor*` .msc files are removed).
- Run `make_datapack.py --install <world>`; its prefix lists already
  cover walls/removewalls, and dome/floor simply won't match anything.

## Built-in verification (runs after stamping, before emission)

The Phase-5 lesson: verify the FINAL model, because stamping can break
what the painter got right.

1. **Seal check**: for every open cell, each of its 4 horizontal
   neighbours is open or wall. Zero violations required.
2. **Thickness check**: every wall cell has ≥1 open 4-neighbour.
   Stamp copies may legitimately create rare exceptions — report a
   count, fail only above a small threshold.
3. **Path clearance**: no wall cell on any slime block or its y+1
   trigger cell. Zero required.
4. **Drift check**: every wall cell's `d` within [3.0, 6.0] (nominal
   ±1 plus rasterization slack). Report histogram.
5. **Smoothness metric**: count 1-block notches (wall cell whose two
   along-wall neighbours at the same y are both one cell further
   out/in). Report; goal ≈ 0 outside junction fans.

## Debug view before touching the world

`walls.py --preview` renders top-down PNG slices (one per ~10 y
levels; matplotlib or plain PPM) of open/wall cells so smoothness can
be judged and parameters (relaxation passes, 4.5 threshold) tuned
without a single in-world build. Cheap, and it protects the in-world
feedback loop for real judgement calls.

## Build order

1. `walls.py` skeleton: sim load (v3, emitted seed), spline sampling,
   distance field. Preview render of raw `d < 4.5` footprints.
2. Smoothing relaxation + wall extraction + vertical regularization.
   Preview again — iterate parameters here until the slices look
   clean.
3. World model + ported splice stamp + verification suite. All checks
   green on the current emitted seed.
4. Emission (fills, chains, .nms rewrite) + `make_datapack.py
   --install`. In-world look at seed's walls; Ryan judges smoothness,
   corridor feel, cavern shapes.
5. Only after in-world sign-off: delete `wall_test.py`, note the
   parameter choices here, and open stage 2 (floor) against the same
   core.

## Outside-shell scan + lantern prep (added 2026-08-13)

Final painter step before verification: `thin_walls` removes every
wall cell with no corridor-air 4-neighbour on its own slice — outside
corners, stamped stubs past tail endcaps, tube-fringe copies, buried
double layers. Removing a non-sealing cell can never break the seal
gate, and afterwards the shell is MINIMAL: removing any remaining cell
would unseal a face (verify gate #7, hard). This is the prep for the
next decoration stage Ryan described: a **sea lantern layer that
completely surrounds the smooth_stone shell**, with the stone as thin
as possible. Note for that stage: ~1k stamped identity walls stand
inside tail-tube corridor air (intrusion class) — decide whether the
lantern wrap should skip them.

## Flagged, not blocking

- **Entry mouths & finish**: dead-end tips and corridor ends get
  wrapped in a rounded wall cap automatically (the swept-disc
  footprint ends in a half-disc). If the 10 entries at START_Y or the
  finish need deliberate openings instead of caps, that's a small
  targeted follow-up once we see them in-world.
- **Band top at path+6**: bounce apexes fit, but the dome (stage 3)
  will spring from path+6 — if headroom feels tight in-world, the
  band constant is one number.
- **Closely stacked corridors** (vertical separation < ~11) share
  slices and will merge into tall caverns — consistent with the
  merged-caverns decision, but worth eyeballing in the preview
  renders.
