# slimeMaze

Procedural generator for a seamless slime-bounce maze on the Minr Minecraft server. A player enters at y=300 and descends to y=-64 by bouncing on slime blocks; every bounce follows one fixed arc law, so the corridor network can be planned on an integer grid. The maze is a directed acyclic graph with a single winning line, and its dead ends are hidden by a relative teleport that the player cannot detect. The generators are Python; their output is a set of MSC scripts (about 815k `/setblock` and `/fill` commands for the shipped seed) plus the per-block trigger scripts that make the maze play.

## How it works

### Bounce arc law

Every bounce turns the heading 22.5 degrees, covers a horizontal chord of about 6.3 blocks, and drops exactly one y-level (`generate_maze_v3.py` module header; reverse-engineered from a reference arc). Sixteen bounces make a full circle of radius ~16.3 blocks. The only free choice per bounce is the turn direction, so a corridor is a sequence of CW/CCW decisions and all geometry is exact.

### DAG structure

- **Entry funnel.** Ten entry corridors physically merge pairwise into three tunnels. A merge junction is an inverted fork: two arcs arrive at +-22.5 degrees around one continuation.
- **Golden trunk.** One winning line from the funnel to the bottom, built with backtracking. Every `FORK_MIN..FORK_MAX` levels it reserves a decoy fork.
- **Decoys.** Wrong choices at forks. They fork among themselves, can pair-merge into shared doomed corridors, and are pruned to a width curve. Only the trunk descends past `MORTAL_FLOOR`.
- **Fork cadence.** No traversable stretch may run more than `FORK_GAP_MAX=20` bounces without a real choice; `verify()` rejects a seed that breaks this.

### Seamless dead ends

No corridor is allowed to visibly end. When a doomed corridor dies it is extended with an alignment arc and then an exact integer-translated copy of a *window*: `WINDOW` consecutive fork-free, constant-turn bounces of a live corridor higher up. A ground trigger on the first blocks of the copied tail calls `splice()`, which runs a single relative `/tp ~dx ~dy ~dz`. Because the copy is a pure translation, position, facing, view direction and momentum all stay consistent, and the player continues on the real corridor without noticing. Rotation is never used (it would break both the grid and momentum). Every hop rises by at least `MIN_RISE`, so chains of splices terminate, and no other trigger may sit within `SPLICE_SUPPRESS=5` bounces of a landing. `splices.txt` records the trigger region and delta of every dead end; `fall()` returns a player who falls off the maze to a splice window at least 30 blocks above their last bounce.

### v2 to v3

`generate_maze.py` (v2) was search-and-repair: grow corridors, discover violations, repair, repeat. Telemetry showed more than 95% of its runtime was discarded work (about 500k window candidates evaluated per seed to place ~180 splices) and the fork-cadence repair plateaued at 26-29 violations. `generate_maze_v3.py` is correct by construction: fork cadence is enforced during the walk (skeleton-first); every dead end *builds* its own teleport destination as a translated copy of its tail instead of searching for one (landing-only); and `clear()` runs on an 8x8 spatial hash. The design and its postmortem are in [V3_PLAN.md](V3_PLAN.md).

### Decoration

`walls.py` reads the finished simulation and paints the corridor shell. Instead of offsetting the centerline curve and quantising it to columns (the approach in `wall_test.py`, which produced 1-block jitter and gaps), it rasterises the corridor *interior* per y-slice and takes its boundary:

1. The slime centerline is Catmull-Rom sampled per branch.
2. Each y-slice gets a distance field to the nearest covering sample. All corridors union into one region, so junctions become shared caverns and the wall only traces the outside.
3. Cells with `d <= 4.0` are always open, `d >= 5.5` always closed, and the band between is a smoothness budget: a synchronous cellular-automaton relaxation closes open cells with too few open neighbours and opens closed cells with too many, ironing out single-cell bumps and dents.
4. The wall is the set of closed cells 4-adjacent to the open set, excluding cells that are corridor air one slice down (ceiling transitions of the descending path).
5. For every splice, the window's surrounding tube is stamped over the tail's tube so the teleport source and destination are identical; the verifier reports intrusions and holes on the final model.

Decisions and hard requirements are in [WALLS_PLAN.md](WALLS_PLAN.md).

### Emission constraints

- **Chunk loading.** `/setblock` and `/fill` fail silently in unloaded chunks. Commands are bucketed by region; each bucket teleports the player to its centre and waits (`@delay`) before placing (`make_buildall.py` uses 64x64 regions and a 500-tick wait).
- **Import size cap.** Minr imports scripts from a paste service with a ~4k-line / ~300 KB limit, so every build is split into chained parts (`build1..N`, `walls1..N`, ...) where each part tail-calls the next and all parts are declared in `slimemaze.nms`.
- **Singleplayer backend.** `make_datapack.py` re-emits the same commands as vanilla `.mcfunction` files (`slimemaze:build`, `clear`, `wipe`) with a forceload, for testing geometry without a Minr server. Ground triggers are server features and are not reproduced.

## Layout

| Path | Role |
|---|---|
| `generate_maze_v3.py` | Current generator: simulation, `verify()`, MSC emission |
| `generate_maze.py` | v2 generator, superseded; kept for reference |
| `walls.py` | Footprint-boundary decoration, splice stamping, verifier |
| `wall_test.py` | Older offset-curve decoration painter, reference only |
| `make_datapack.py` | Converts emitted chains to a vanilla datapack |
| `verify_build.py`, `verify_direct.py` | Independent checks of emitted files / of `verify()` |
| `emit_sandbox.py` | Emit one seed into a sandbox directory |
| `v3_seed2/` | The shipped seed: `make_buildall.py`, `make_server_export.py`, `SERVER_IMPORT.md` |
| `v3_salvage/` | Landing-search prototypes salvaged from the v2 line |
| `slimemaze.nms`, `solution.txt`, `splices.txt`, `starts.txt` | Namespace declaration and registries for the emitted seed |
| `V3_PLAN.md`, `WALLS_PLAN.md` | Design documents |

## Running it

```
python generate_maze_v3.py [seed]        # simulate, verify, emit next to the script
python emit_sandbox.py 2 v3_seed2        # emit a seed into a sandbox directory
python walls.py v3_seed2 --preview       # render PNG slices, no emit
python walls.py v3_seed2                 # paint, stamp, verify, emit walls chains
python make_datapack.py --install World  # singleplayer datapack
```

For the server, inside `v3_seed2/`: `python make_buildall.py` then `python make_server_export.py`, then follow the runbook in [v3_seed2/SERVER_IMPORT.md](v3_seed2/SERVER_IMPORT.md). In-game the whole maze is placed by `/function execute slimemaze::buildALL1(Player("You"))`, which tail-calls the trigger-wiring chains when it finishes.

## Notes

- All emitted build scripts, backups, datapack output, pickles and schematics are gitignored. Only the generators, the docs and the small registries (`solution.txt`, `splices.txt`, `starts.txt`, `slimemaze.nms`) are committed.
- `slimeblock.msc`, `splice.msc`'s effect hook `spliceFx.msc`, `fallFx1/2.msc` and `scaryTitle.msc` are hand-tuned: the generator declares them in the `.nms` but never overwrites them.
- `solution.txt` lists the correct choice at every fork of the winning line, in world coordinates.
