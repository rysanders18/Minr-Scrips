# V3 Generator Plan — correct-by-construction slime maze

*Written 2026-08-09, from the conclusion of the 0a27feee session (postmortem of the
12-hour fork-cadence session) and project memory.*

## Why v3

The v2 architecture is **search-and-repair**: generate corridors organically, discover
they're illegal, repair, repeat. Telemetry from the fork-cadence work showed >95% of
runtime is discarded work — ~500k window candidates evaluated per seed to land ~180
splices, thousands of decoy arms born and erased, repair passes that plateau at
fork-gap viol ~26–29 and never reach 0. The constraint set self-defeats: more forks →
more dead ends → more splices → each freezes a 9-block window + 9-block tail + two
r=6.5×20 tubes → less room for the next fork.

**Targets for v3** (user-set):
- Generation in **≤ 5 seconds** per seed.
- **Fork cadence viol = 0** — a fork at most every `FORK_GAP_MAX=20` blocks along any
  traversable path (tail blocks past the first splice trigger exempt), guaranteed by
  construction, not repaired after.
- **Splice suppression** (added 2026-08-09): after a splice fires, the player must
  travel at least **5 blocks** before another splice can fire (`SPLICE_SUPPRESS=5`).
- No more seed lotteries: every seed passes the gates by design.

## The three pillars (conclusion of the last chat)

1. **Skeleton-first planning.** Decide the full fork/merge/dead-end tree — entries,
   funnel merges, golden trunk, braids, fork spacing ≤ 20, dead-end terminations,
   splice-chain heights — as pure graph math *before placing any block*. Cadence
   violations become impossible. Delete `enforce_fork_gaps`, `insert_fork`,
   chew-rescue, `rewind_retry`, and the fix_leaves splice-rescue machinery.

2. **Landing-only dead ends.** Every dead end terminates with a **landing splice**
   (the user's 2026-08-07 idea): build the teleport *destination* as a translated copy
   of the dead end's own fork-free tail, placed in free space (delta is the free
   variable), merged back into the live maze via an exactly-solved connector. No
   window *search* ever happens — the 500k-candidate churn, the single biggest time
   sink, vanishes. Landings are novel territory by construction (the destination is
   freshly built), chain safely (each rises ≥ MIN_RISE), and satisfy every
   seamlessness rule because the copy is an exact integer translation.

3. **Spatial hash for collision checks.** `clear()` kin-BFS neighborhood queries and
   tube-clash tests currently scan linearly per candidate; a grid index (cell size ~8,
   buckets of block indices / tube ids) makes them O(1). Applies to corridor
   separation, junction clearance, tube overlap, and landing placement probes.

Optional multiplier if 1–3 fall short of 5s: **PyPy** (drop-in, ~5–20× on this kind of
dict/loop code). Don't design for it; treat as headroom.

## What is already validated vs. not

| Piece | Status |
|---|---|
| Non-destructive landing search (no rewind_retry, capped growth, arm's own tail as copy source) | **Implemented** in the 0a27feee sandbox (`landfix/generate_maze.py`, WINDOW=8; `landfix7/` = same + WINDOW=7). **Never validated** — all survey runs died 0-byte when the session closed. |
| Landing infinite-hang root cause (uncapped forward-1/rewind-3 cycle) | Confirmed (47 CPU-min stuck process caught live) and fixed by the non-destructive rewrite. |
| State-corruption crashes (chew vs. failed landing erasures) | Root-caused: destructive walking machinery borrowed for speculative search. v3 avoids the class entirely — landings never mutate existing corridor state during search. |
| Build-time stubs (reserve fork sites while world is near-empty) | The 12-hour session's only breakthrough (viol 103→29). Superseded in v3 by skeleton planning, but the *lesson* (decide early, while space is free) is the core of pillar 1. |
| WINDOW=7 (user request, shrinks each splice's frozen footprint) | Set up, never measured. v3 should adopt **WINDOW=7** as the default and parameterize everything off it (the landfix7 copy already does). |

## Constraints that must survive unchanged (the seamlessness spec)

These are hard-won invariants from v1/v2 — v3 re-architects *how* the maze is found,
not *what* a legal maze is:

- Splices/landings are **pure integer translations** (rotation breaks grid + momentum).
- Teleport horizontal Chebyshev ≤ `SPLICE_MAX_D=128` (destination stays in loaded chunks).
- Tail/window decoration **tubes** (r≈6.5, height ~20) must not overlap any other
  splice's tubes; own window needs max(|dx|,|dz|)≥14 or |dy|≥20. Landings must
  register their destination tube in the same tracker.
- Each splice hop rises ≥ `MIN_RISE` so chains terminate.
- Fork-free window/tail of `WINDOW` bounces; triggers on the **first two tail blocks**;
  entry-turn `dw` stored for the alignment arc; the two onward tail blocks passed to
  `splice()` re-based by +delta onto the destination.
- Solid **end-caps** (`wall_test` half-ring) on every tail.
- **Splice suppression, `SPLICE_SUPPRESS=5`** (new v3 rule, 2026-08-09): no other
  splice's trigger block may lie within 5 bounces downstream of any splice landing
  point. This must be a **generation-time geometry invariant** (checked in landing
  placement, re-derived in `verify()`), NOT a runtime-only suppression: a
  runtime-suppressed trigger sits on a dead-end tail, so a player who skipped it
  would continue into the solid end cap and be stranded. Consequence for chains:
  a landing may not deposit the player directly on another tail's trigger blocks —
  the v2-style instant chain (window == tail, land on trigger) is retired; chained
  descents must land ≥ 5 bounces upstream of the next trigger. Optional runtime
  safety net (belt-and-braces, should never actually fire if geometry holds):
  `relative Int sinceSplice` declared via NMS_VARS, zeroed in splice dispatch,
  incremented in hand-tuned `slimeblock.msc`, initialized high in `fall()`, guard
  `@if` at the top of splice dispatch.
- Graded kin separation: `JUNC_KIN=6`, near-kin pairs beyond 2 hops keep Chebyshev ≥ 5;
  junction-adjacent trunk depths rejected for ports/braids.
- 10 entries physically merging (inverted forks) to 3 tunnels at the funnel waist
  (golden trunk + 2 ports); every entry keeps a physical route to the bottom.
- Braids (mid-maze merges off the trunk) — keep ≥ 1; they're the "merging below the
  top" feature the user asked for.
- All cross-branch lattice-index comparisons go through `hwrap()`.
- Fork resolution palette rule (longest same-color downstream run) and all
  `wall_test.py` palette/decoration invariants — `wall_test` consumes the Sim, so it
  should carry over as-is; rerun after every emit.
- Emit formats frozen: `@console /function execute slimemaze::...` +
  `Player("{{player.getName()}}")` forms, `{{player}}` fall tps, `@s ~` splice tps,
  `doFx` only when delta ≥ `SPLICE_FX_MIN_D=64`, DONE_SOUND before final `@player`
  line, `NMS_VARS` hand-added state, part caps (`MAX_PART_LINES=3400`,
  `SG_PART_LINES=2300` — the hastebin cap is bytes *and* lines), grounds ==
  `__init__` content, 3×3 walk-script blankets with literal blocks + world "Epsilon".
- Emit's .msc wipe spares files whose first 600 bytes contain **HAND-TUNED**
  (spliceFx/fallFx1/fallFx2/scaryTitle/slimeblock hooks). Check emitted files for hand
  edits before overwriting (the `@console` fix in splice.msc was nearly clobbered once).

## Architecture

Develop as a **new entry point** in the repo — `generate_maze_v3.py` (plus small
modules if convenient: `skeleton.py`, `spatial.py`) — copied from the best current
base and refactored. Do **not** edit `generate_maze.py` in place: it's the only
(drifted) v2 reference in the repo and the standing world is still seed-13 v2.

Base to start from: `landfix7/generate_maze.py` from the 0a27feee sandbox (repo
file + non-destructive landing search + WINDOW=7). **(Salvaged — see
`v3_salvage/v3_base_landfix7.py`, alongside the WINDOW=8 variant, `patch_fix.py`,
and the landing profiler.)**

### Pipeline

```
plan_skeleton(seed)      # pure graph, no geometry, <0.01s
   ├─ entries=10, funnel merge tree → 3 tunnels (trunk + 2 ports)
   ├─ golden trunk depth range, forced fork at y=-44 (finish run = exactly 20)
   ├─ braid arms (≥1) with fork/merge nodes
   ├─ fork nodes spaced so every path has gap ≤ 20 (cheap DP on the tree)
   └─ every leaf = dead end scheduled for a landing (chain heights rise ≥ MIN_RISE)

realize(skeleton)        # geometry, using existing primitives + spatial hash
   ├─ trunk first, then ports/funnels upward, braids, then fork arms outward
   ├─ each corridor: existing bounce-chord walk (place/clear/turn_seqs), but
   │  target lengths/turn budgets come from the skeleton, not doom lifetimes
   ├─ bounded local replan: if an arm can't reach its planned length, shorten it
   │  and move its fork node up (skeleton edit that preserves the ≤20 invariant),
   │  never global repair
   └─ spatial hash backs clear(), kin checks, tube checks

place_landings(sim)      # one landing per dead end, correct-by-construction
   ├─ copy source = the arm's own last WINDOW+1 blocks (fork-free by construction)
   ├─ destination search = enumerate legal deltas directly (rise ≥ MIN_RISE,
   │  Chebyshev ≤ 128, tube-clash-free via spatial hash) — a solve, not a walk
   └─ connector merges destination back into a planned continuation corridor

verify(sim)              # KEEP the existing independent verifier unchanged —
                         # it re-derives fork gaps, reachability, separation,
                         # splice legality from scratch; it is the safety net
emit(sim)                # existing emit pipeline, byte-format-frozen
```

### What gets deleted

`enforce_fork_gaps`, `insert_fork`, `steer_merge`-as-repair, `rewind_retry`,
chew-time splice rescue, `splice_boost`, doom-lifetime tuning as the fork-density
lever, the window *scan* in `splice_tail` (landing solve replaces it), seed-survey
scripts. `fix_leaves` shrinks to a sanity pass (skeleton realization shouldn't
produce illegal leaves; if it does, that's a bug to fix, not chew).

## Phases & acceptance criteria

**Phase 0 — Salvage & baseline (do first, cheap)**
- Copy `landfix7/generate_maze.py` out of the dead session's scratchpad into the repo
  (e.g. `v3_base_landfix7.py`) before temp cleanup eats it. Same for `patch_fix.py`.
- Re-run the interrupted validation on 2–3 seeds (WINDOW=7 base, landings on):
  confirm `verify` clean and `ld_ok` > 0. This proves the landing *geometry* is sound
  before v3 builds on it. Timebox: if a seed exceeds ~10 min, kill it — v3 doesn't
  need these runs to finish, only to show landings verify.
- Git: commit the current repo state (generate_maze.py drift included) so v3 work has
  a baseline to diff against. The file is currently untracked — that's how the v2
  reconstruction pain happened.

**Phase 1 — Spatial hash (isolated, testable win)**
- Grid index over placed blocks + registered tubes; back `clear()`, kin checks,
  tube-clash, landing probes with it.
- Acceptance: byte-identical maze output on a test seed vs. linear scans (pure
  optimization, zero behavior change), measured speedup on the hot paths.

**Phase 2 — Skeleton planner**
- Pure-Python tree builder: entries/funnel/trunk/ports/braids/forks/leaves with the
  ≤20 cadence as a construction invariant; deterministic per seed.
- Acceptance: standalone check that every path in the planned tree has gap ≤ 20,
  entries = 10, funnels = 3, braids ≥ 1, leaf chain heights rise ≥ MIN_RISE; runs in
  milliseconds; prints planned blocks-per-fork.

**Phase 3 — Geometric realization**
- Realize the skeleton with the existing walk/junction/port/funnel primitives, driven
  by planned targets; bounded local replan on geometric failure.
- Acceptance: `verify()` (unchanged v2 verifier + fork-gap re-derivation) passes with
  viol = 0 on ≥ 5 seeds; no global repair passes ran; wall-clock for
  plan+realize ≤ ~3s.

**Phase 4 — Landings**
- Landing solve for every leaf; register tubes; splice records carry the same fields
  emit expects (`copy`, `dw`, delta, tail blocks) so emit/wall_test don't change.
- Acceptance: 100% of dead ends terminated (landing or planned merge), `verify`
  clean, novel fraction = 100% for landings (report it), **no trigger block within
  `SPLICE_SUPPRESS=5` bounces downstream of any landing point**, total
  generation ≤ 5s.

**Phase 5 — Emit + downstream compatibility**
- Emit a chosen seed in a sandbox; run `verify_build.py`; run `wall_test.py` against
  the v3 sim; confirm splices.txt, build headers, grounds/slimegrounds structure, and
  part-size caps all behave.
- Acceptance: verify_build green; wall_test completes with its checks at their v2 end
  state (0 visible mismatches, 0 fork-chord flips, etc.); hand-tuned hook files
  untouched by the emit wipe.

**Phase 6 — Install (in-world migration)**
- Snapshot the current v2 emitted scripts (`backup_v2_final/`, like
  `backup_seed13_pre_caps/`).
- Remove the standing seed-13-v2 build with **its own v2 chains** or the datapack
  `slimemaze:wipe` (bbox air-fill) — required before importing v3's namespace; the
  new remove chains cannot remove the old build.
- Import namespace, build, then run `removeoldslimegrounds`-equivalents if signatures
  changed, then `grounds1` once (build chain also wires it).
- Rerun `wall_test` output chains (walls/dome/floor/decor) for the new maze.

## Risks & mitigations

- **Landing geometry unproven** → Phase 0 validates it standalone before v3 depends
  on it. If landings fail verification structurally, fall back: window *sharing*
  (multiple tails onto one window costs zero new tube; the stamp already forces
  tail == window) was the agreed capacity fallback.
- **Skeleton plans that geometry can't realize** → bounded local replan (shorten arm,
  move fork up — both preserve cadence). Track replan counts; if a seed needs
  global backtracking, that's a design smell to fix in the planner's spacing
  margins, not with repair passes.
- **Process lessons from the failed 12-hour session** (bake into workflow): never
  judge a config on single-seed noise (same config spanned 67–113 on seed 1); never
  abandon a best-known config without an A/B revert; never launch an untested
  mechanism as a session's final act; every speculative search loop gets an
  iteration cap on day one.
- **Emit/wall_test drift** → treat their input contract (Sim fields, splice record
  shape) as frozen; any change there must come with a same-session wall_test run.

## Build status (2026-08-09, session 94f9b144 — commit 512c134)

`generate_maze_v3.py` exists and runs end-to-end (~2.5–3 min/seed on seed 1;
was: never finished). Independent `verify()` on the v3 maze: **zero structural
errors** — exact-translation landings, reachability, separation, no visible
dead ends, and the SPLICE_SUPPRESS=5 rule all pass. The one open defect class
is the fork-gap count: **viol ~220 vs the target 0**.

Done: spatial-hash `clear()`; hybrid landing tails (arm's own suffix as copy
source); the postmortem's infinite-rewind hang found live and fixed; static
pre-pass to viol 0 in <1s; walk-time cadence (forced forks at gap 12, landing
termination at 17); termination tiers landing → window splice → terminal
merge → safe-erase-classified chew; landing search made ~10× cheaper
(horizontal prefilter, free-space prescreen, edge bias into the LAND_R_EXTRA
annulus).

Open problem (measured, not guessed): **landing-volume saturation**. Cadence
fixes fork density at ~1 per 15 blocks, so termination demand = corridor
mass / 15 ≈ 450+, while the maze's capacity for new landing corridors
saturates ~250 (the copy must sit just above a stable corridor — inside the
dense cloud).

**Continuation session update (commits `58b2dce`, `b4513b5`):** found and
fixed the biggest single source — `landing_for_tail` never checked the
forkless run *below* its junction, so every landing (arriving with 9+m
bounces) could mint violation runs on the destination corridor. That guard
plus fork redundancy (doomed timer 8–12), the landing-extension band (gap
17–25), funnel stub tightening, and precious-arm boosts brought the 4-seed
viol to **98/61/119/130** (from ~250–320), with ~200 splices/seed, ~2 min/
seed, and every other verify check clean. Tried and rejected: walk-time
sweet-spot merges (~1/4400 yield — unsteered merges never land, the old v2
lesson), suffix window matching (~1/4500 — full fork-free suffixes are rare
at rescue positions), widened precious (A/B worse). The remaining viol is
repair-resistant residue concentrated in the funnel zone (no landing
headroom above the maze top) — closing it needs either fork-site/landing
co-reservation at spawn time (the real skeleton move) or a user-owned rule
change (cap 24, or funnel-zone down-splices).

## Session update (2026-08-09/10, commits `f39fdaf`, `8fb56df`)

Baseline re-measured (viol 98 seed 1, bimodal y-quartiles
[-44, 15, 245, 277, 293]: funnel zone + deep band, both with zero
landing capacity; seed-1 noise band for one config spans ±30 — no
single-seed conclusions). Four levers built and measured 4-seed:

| Lever | 4-seed viol | Verdict |
|---|---|---|
| b4513b5 baseline (stubs 4-6) | 98/61/119/130 (mean 102) | prior best |
| Window farm (pre-built shareable windows in the dead zones) | 107/124/151/116 | **rejected** — ~17 uses/seed don't pay the interior congestion; default OFF (`GM_FARM=1`) |
| Steered suffix termination (arm rides onto a window) | 3/59 conversion | **rejected** — the ride hits the same arm-side congestion as a splice arc and rounds worse than a translation; gated (`GM_STEER=1`) |
| Funnel stub relaxation 4-6 → 7-10 | 134/127/97/115 | **rejected** — removes redundancy without removing the failure mode |
| **Bubble braids** (build-time pre-terminated funnel forks) | 94/43/89/57 (mean 71) | works — funnel bucket collapses |
| **Bubble braids + close-retries** (commit `21b5e15`) | **70/33/65/63 (mean 58)** | **new best, default ON** (`GM_BUBBLE=0` reverts) |

The unifying measurement: every mechanism that leaves speculative
arms in the funnel zone loses. The stub pads (12.5-14 Chebyshev
× ±15 y each, every 4-6 levels × 10 corridors) blanket the zone and
starve *arm-side* placement for every termination flavor — GM_FARMDBG
nearest-blocker dumps proved the blockers are `br=-1` stub blocks.
Bubble braids remove the speculation: spawn mirror-turn fork arms
(pass 1 — the fork exists immediately), then terminate each arm **at
build time** via `splice_tail` in the near-empty world (pass 2; entry
corridors above are fresh window supply, no tails to chain-reject).
Merge-based closing measured ~0/63 (exact-solve arrival too sparse —
the v2 unsteered-merge lesson again); the splice's translation delta
is the free variable that makes closing high-yield. Funnel-bucket
viol collapsed 64-115 → 18-63; the residue is now mid-band `spliced`
runs (chew erasures near spliced arms).

Also fixed (latent, live-observed): float-solved connector/arc
placements can round a 6.3 chord past verify's 7.6 cap —
`chord_int_ok()` guards farm/landing/merge/braid/arc placement incl.
the arrival→J chord. `verify_direct.py` (committed) runs the full
independent verify bypassing the stats gate; structural errors = 0.

Next levers for the remaining ~70: raise bubble-close conversion
(seed 5's funnel residue 63 tracks its low `bub_ok`), then attack the
mid-band `spliced` bucket — its runs come from chew erasures whose
rescue splices fail in the dense end-state maze; the bubble lesson
(terminate at build time / while sparse) suggests scheduling walk-arm
terminations earlier in the sweep rather than at death.

## Phase 5 first run (2026-08-10) — emit works, decoration does not

Phase 5 had never been executed. Run on seed 2 (viol 33, the sweep's best)
via `emit_sandbox.py` (new; bypasses main()'s seed gate, emits to an
explicit sandbox — the gate had kept every v3 maze from ever reaching
emit). Results:

| Check | Result |
|---|---|
| `emit()` to sandbox | **works** — 68 files, 0.7s, all chains + splices/starts/solution |
| `verify_build.py` | **PASS** (chains, part caps, unique setblocks, splice deltas vs splices.txt, .nms declarations) |
| `gm.verify()` structural | **0 non-fork-gap errors** |
| `wall_test.py` against a v3 sim | **completes** — 251 wall/dome/floor/decor chains emitted |
| wall_test too-close audit | **REGRESSION: 96 (30 unannotated) vs v2's 3 (1 unannotated)** |

`wall_test.py` hardcodes `import generate_maze` (v2) — a v3 run needs that
line pointed at `generate_maze_v3`. It was never a v3-aware script.

**The open defect.** The too-close audit reports built wall columns whose
run bottom sits within 3.5 blocks of a corridor centerline. v2's cached
world (`wt_debug.pkl`, Aug 4 — a *larger* world, 523k cells) yields 3 such
columns, 1 outside the two documented-benign classes. v3 seed 2 yields 96,
30 outside them — and 29 of those 30 cluster tightly at **dy ≈ +2.7..+3.7**,
i.e. a wall column rising from ~3 levels below a corridor it stands
1.4–3.5 blocks away from. Attribution (nearest 3 corridor blocks per
column): **69 spliced + 18 unterminated-arm blocks, 0 junction blocks** —
so this is *not* the landing/junction geometry, it is v3's much denser
population of splice-tail and leftover-arm corridors stacking ~3 levels
apart at sub-wall-thickness horizontal distance. `clear()` permits it
(kin exemption), the wall shell cannot.

Consequence: decoration blocks intrude into corridor air the player
bounces through. Slime geometry is unaffected — the maze is *structurally*
fine and *cosmetically* not.

Fix directions (untried): raise the wall-prune rule to cover the
dy +2..+4 band; or add a wall-clearance term to `clear()` for
non-junction pairs (a corridor-vs-corridor vertical separation floor
around ±4 levels rather than relying on Chebyshev alone); or accept
and prune at stamp time. Whichever, re-run this audit as the gate —
the v2 numbers (3 / 1) are the target.

## Phase 5 second run (2026-08-11) — defect closed, datapack shipped

All three fix directions above were wrong about the *culprit*. Provenance
instrumentation (tag every wall column with slit-refill / gap-fill / path
origin, then diff the audit offenders against `pre_stamp_world`) showed
**44 of the 48 unannotated columns never came from the wall painter at
all — the splice stamp created them**; the other 4 were the documented
benign `dy −12` class. The painter's prune has enough margin (4.3 vs the
audit's 3.5, > the 0.71 worst-case rounding gain) that it cannot produce
an offender; but it *opens* those cells, and then the stamp copies the
window's solid wall back over them to preserve tail == window.

**Fix — stamp intrusion repair** (`wall_test.py`, immediately after the
stamp overwrite repair, sharing its `restored` list): a tail is an exact
integer translation of its window, so the tail's own corridor scores an
identical distance-to-nearest-centerline on both sides. Only a bystander
can make a cell measurably closer at the tail (`dt < dw − INTRUDE_MARGIN`,
carved-space window `INTRUDE_LO..INTRUDE_HI` = −4..+13). Those cells revert
to their pre-stamp value — the painter's opening wins over identity, the
same call the floor-overwrite repair already makes. A boolean "is a
corridor near" test does NOT work here: the tail's own corridor answers
yes for every cell of its own tube, which is why the distance *profile*
(not a predicate) is the operative idea.

Also: the audit gained a third benign annotation class, *base above that
corridor's vault* (`yb ≥ sy + 10`) — the old `dy −12` rows, hand-verified
in-world 2026-08-05. It reclassifies 18 of the original 48. The v2 number
below was re-derived under the identical rule, so the comparison is fair.

| audit | total | unannotated |
|---|---|---|
| v3 seed 2, before | 96 | 30 |
| v3 seed 2, after | **67** | **3** |
| v2 cached world (same rules) | 3 | 1 |

The 3 residuals (`dy +3.4/+3.5`, d 3.31–3.49) are the same marginal class
as v2's single residual (`dy +3.8`, d 3.48) — cells the *window itself*
carries that close to a centerline, so the bystander test correctly
declines them. The 67-vs-3 total gap is almost entirely the benign
stacked-corridor classes, which scale with corridor density.

Cost: 773 cells (≈4 per splice) now deliberately differ between window and
tail — at those spots the tail shows an opening into the neighbouring
corridor where the window shows wall. They are registered in
`restored_set`, so the shell verify still reports **0 visible mismatches**.
The alternative (constrain generation so tails never run that close to a
bystander) costs splice supply and was not attempted.

Everything else at its v2 end state: 0 visible mismatches, 0 band-edge
remnants, 184/184 tails capped, 0 floating lanterns, prismarine joints 5,
ore joints 10. `verify_build.py` **PASS** (5598 blocks, 184 splices, 3312
splice triggers, 47070 slimeblock triggers).

**REVERTED 2026-08-12 — the repair was the wrong trade.** The user walked
the build and reported wall/dome errors. Reverting a stamped cell to its
pre-stamp value means reverting it to *air*, which is by construction a
HOLE in the tail's shell (see-through into the neighbouring corridor).
Measured by diffing the two dumps — tail cells that are air where the
window is solid: **with the repair 605 wall + 102 dome + 14 floor; without
it, zero.** The repair traded an intrusion for a hole; both are wall
errors, and the audit metric it optimized could not see the hole because
the cells were registered in `restored_set` as sanctioned divergences.

The repair is now behind `WT_INTRUDE=1`, **off by default**, and the
painter is byte-identical to the committed baseline (verified: with the
gate off, deletion repair 12340, overwrite repair 175, 15389
deletion-repair blocks, joints 6/10, too-close 96/30 — every figure
matches the pre-change run). There has only ever been ONE wall/dome
painter, shared by every generator; "v1/v2/v3" name maze-construction
generations, not painter versions. Anything that changes it changes the
in-world-validated build too, so it stays opt-in.

The stamp-intrusion detector itself (distance profile, tail vs window)
is still the correct way to FIND these, and stays in the file for that.
The fix belongs on the generation side: keep tail tubes away from
bystander corridors so the painter never has to choose between an
intrusion and a hole.

Tooling: `wall_test.py` now selects its generator with `WT_GM`
(default `generate_maze`, so the standing v2 world still regenerates
byte-identically); `make_datapack.py` gained `--src` / `--out` so a
sandbox emit can be packed without touching the repo's v2 scripts.

**Shipped for feedback:** seed 2 (5598 blocks, 178 forks, 184 splices /
175 novel, 101 landings, viol 33, WINDOW=8), emitted to a sandbox and
installed as a datapack into the `Slimemaze` singleplayer world
(403,916 build commands). The repo's emitted v2 scripts are untouched;
the standing Minr world is still seed-13 v2.

## Wall/dome layer audit (2026-08-12) — bands and the lantern backdrop

User asked to verify two properties of the FINAL product: no gaps in the
deepslate-tiles / polished-deepslate bands, and an uninterrupted sea-lantern
layer around the walls. Both were audited against the emitted world model
(`WT_DUMP=1` dump), with the identical audit replayed against a
reconstructed v1/v2 seed-13 world (`backup_pre_decorfix/gen_v2.py`) to
separate "inherent to the painter" from "v3 regression". Neither property
held, and both predate v3.

**Bands.** Per wall run, checking the foot and top courses, netherite
excluded (the palette slice ring is *designed* to override bands):

| | v3 seed 2 | v1/v2 seed 13 |
|---|---|---|
| runs | 25,523 | 20,401 |
| band gaps | 1,274 (4.99%) | 517 (2.53%) |
| of those, AIR (a real hole) | 783 | 49 |
| AIR gaps outside a splice tail | **0** | **0** |

`band_paint` is not at fault. EVERY air gap sits inside a splice tail:
the stamp forces tail == window, so a window whose wall shell was pruned
open (a bystander corridor near the WINDOW) copies that hole onto every
tail that lands on it, with no local reason for it. v3's rate is 16x v2's
because its tails and windows crowd bystanders far more often — the same
root cause as the stamp-intrusion problem above.

**Lantern layer.** Void cells beside a wall, visible diagonally from
corridor air (i.e. darkness seen through a thinning crack): v3 25,029,
v2 14,562 (0.98 vs 0.71 per wall run). Two mechanisms, both in the
layer's own definition: (1) the suppression radius `CLEAR + 1.0` = 5.3
was tested against ALL centerlines including the wall's OWN, and the wall
line sits at `WALL_D` = 5.0 — so every cell at the wall line, which is
exactly where corner thinning removes blocks, was vetoed, contradicting
the header's claim that "diagonal thinning cracks show lantern";
(2) the layer is one cell thick, so a crack sees past it. The post-stamp
backdrop heal only fills behind corridor-facing GLASS, which is 6% of
these cells.

### Fixes (2026-08-12) — ALL REVERTED at user request the same day

The three changes below were implemented, measured and shipped, then
reverted on the user's instruction. The AUDIT FINDINGS above stand (they
describe the painter as it is today); the fixes do not exist in the code
any more. `generate_maze_v3.py` is back at HEAD (WINDOW=7, no shell
preference) and `wall_test.py` keeps only the earlier-round changes
(`WT_GM` generator switch, the `WT_INTRUDE`-gated stamp intrusion repair,
the audit's third annotation class). Kept here as the record of what was
tried, what it cost, and what it bought.

1. **Own corridor can no longer veto its own backdrop** (`wall_test.py`).
   Two tiers now: never inside ANY corridor's air tube (`CLEAR`), and
   never in a NEIGHBOURING corridor's margin (`CLEAR + 1.0`, blind to the
   wall's own streams). Needed stream identity on the wall paths:
   `sid_grid` mirrors `grid` with the owning stream index, `cols['sids']`
   carries it, and `near_center_foreign()` consumes it. `grid` itself
   keeps its 3-tuple shape — every other consumer and the debug dump
   unpack 3-tuples.
2. **Backdrop crack seal** (`wall_test.py`, right after the pre-stamp
   open-air flood): any empty cell touching a wall, not itself reachable
   corridor air, but visible diagonally from reachable air becomes
   lantern. Iterates to a fixed point (cap 6) — 76% of what 2 passes left
   sat directly behind the seal's own outer face. Runs PRE-stamp on
   purpose, so tails inherit the seal by copy and splice fidelity holds
   by construction: **0 visible mismatches** on both v3 and v2.
3. **Intact-shell window preference** (`generate_maze_v3.py`):
   `shell_ok()` rejects windows with a foreign corridor inside
   `SHELL_REACH` = 9.3 (`WALL_D` 5.0 + `CLEAR` 4.3); `shell_waves()`
   yields clear-shell windows first and falls back to pruned ones so
   splice supply cannot collapse. Probe budget `SHELL_TRIES` = 40 per
   splice; `GM_SHELL=0` disables. 3-seed viol mean 106 -> 86 at WINDOW=8
   (better on 2 of 3), so it pays for itself on cadence as well.

Measured effect on the v1/v2 standing maze (the shared painter, seed 13):
crack-visible voids **14,562 -> 8,833**, 0 visible mismatches, 153/153
tails capped, joints 1->2 prismarine / 6->5 ore. NOTE: both v2 painter
runs die at chain emission with `gen_v2 has no attribute DONE_SOUND` —
a pre-existing incompatibility between the current wall_test and the
Aug-6 generator reconstruction, identical before and after, so the world
model comparison is valid but chain emission is unverified on v2.

A band-gap class that LOOKS new is not: ~400 top-course cells reading
`sea_lantern` outside tails are buried cells (no corridor-facing
neighbour) that the pre-existing glass-depth rule folds into the lantern
layer. Invisible from any corridor; the audit metric has no visibility
model.

### WINDOW = 7 -> 8 (user-set 2026-08-12, then REVERTED to 7)

v3 had been forked at `WINDOW = 7` while v1/v2 use 8; the seed-2 build
shipped on 2026-08-11 was 7, not 8 as reported at the time. Set to 8 per
the user. Measured cost at WINDOW=8 (shell preference on):

| seed | WINDOW=7 | WINDOW=8 |
|---|---|---|
| 1 | 70 | 78 |
| 2 | 33 | 78 |
| 5 | 63 | 102 |
| 3 | builds | **fails: funnel 2 could not grow** |

Roughly double the violations plus a loss of buildable seeds, in exchange
for 6-7 bounces past the trigger instead of 5-6. One-line revert.

## Open items for the user

- Confirm WINDOW=7 as the v3 default (requested last session, never measured; 6–7
  bounces past the trigger at 8 → 5–6 at 7).
- Target splice/landing count and entry count stay at v2-ish levels (10 entries,
  ~150+ terminations) unless you want a different density.
- Whether the emitted v3 replaces the world immediately (Phase 6) or v3 is validated
  offline first while seed-13 v2 keeps standing. Plan assumes offline-first.

### TURN-RUN RULE + CONSTANT WINDOWS (user rules, 2026-08-15)

Two hard curvature rules, enforced at every placement site and
re-verified independently in `verify()`:

1. **Turn-run rule** (`TURN_RUN_MIN = 3`): after a turn-direction
   change, the next two bounces keep the new direction - on EVERY
   traversable route (junction second arrivals ride through `h2`
   chords and are checked path-by-path). Enforced by `turn_ok`
   (downward walkers, incl. forced fork mirrors), `down_turn_ok`
   (upward walkers: funnels, ports, farm chains), and `flips_ok`
   over every constructed turn sequence (splice arcs, connectors,
   steered rides) with upstream history (depth 3 - depth 2 provably
   leaks `[a,-a,-a,a]`) and downstream junction turns appended.
2. **Constant-direction windows**: splice windows (and therefore every
   replica tail past a trigger) never flip direction - a flipping
   tail could S-bend and bring its own dead end into view before the
   teleport fires. `scan_seq_windows` rejects mixed windows; landing
   suffixes/growth are constant arcs; weave tail shapes removed.

Verification: `verify()` gained a ride-DFS turn-rule check (all
4-turn windows over arrival-correct chords) and a window-constancy
check per splice. All build-able seeds pass with **0 rule errors**.

Knock-on effects and what was rebuilt to absorb them:

- Window supply needs runs >= WINDOW+1: `FLIP_MIN 5 -> 7`, funnel
  commit runs 8..12, doomed arms get a death-band `noflip` commitment
  (constant final arc = legal copy stretch).
- Ports: a port junction is only legal where the trunk flips right
  below it or holds its turn 3 stub-free bounces; `PORT_MIN,MAX ->
  10,64`, `PORT_SEP -> 4`, port-band flip pacing in `build_golden`,
  run-aware 3-bounce escape probe, ports grow BEFORE funnel 0.
- Funnel growth: `down_turn_ok` per upward step + 3-bounce lookahead
  prune on direction changes (a change commits 2 more bounces).
- Braids: the steer-then-connect walk got ZERO braids under the rule
  (legal connector shapes too sparse to hit blind). Replaced with a
  shape SOLVER: enumerate run-compositions (`run_comps`) of the exact
  bounce count fork->join over every legal join slot in the band,
  filter by heading mod 16 + flips_ok + float-walk arrival, then
  place. Lands ~1 braid on roughly half the buildable seeds.
- Bubbles walk constant arcs to a full WINDOW+1 suffix (`noflip`),
  close via splice_tail -> splice_landing -> merge_end. Success is
  still only ~13% in the funnel disk - an 8-bounce constant arc
  rarely fits there. This is the main open cadence hole.
- `ALIGN_MAX 6 -> 8`, `W_MAX 40 -> 30`, `BACKTRACK_MAX -> 30000`,
  merge/braid candidate caps raised.

**Measured state (seeds 1-20)**: ~40-50% of seeds build (rest die in
golden trunk backtracking or port-funnel growth); builders show
forkgap_viol ~60-185 vs the pre-rule ~30-130 and the viol=0 ship
gate. `merges` collapsed to ~0-3 (exact-arrival connectors have
almost no run-legal shapes; landings/suffix tiers carry
terminations). The rules themselves hold everywhere; the OPEN work
is termination capacity: funnel-zone bubbles, repair-arm landings
(`ld_j_slack`, `ld_growblk`), or a user decision to relax
FORK_GAP_MAX / maze size. Window farms (GM_FARM=1) measured worse
and have a residual rule bug - leave off.

## Trigger-color rule (user, 2026-08-17)

**Rule**: at least one slime block of the destination palette before
every seamless teleport - the color switch must never sit on the
teleport bounce.

Root cause of violations (2-10 per buildable seed): the SPLICE_LEAD
loop in `compute_palette` refuses to recolor fork-guard blocks, so a
trigger hanging one bounce past a fork got zero lead-colored approach
blocks and the flip landed exactly on the trigger.

**Enforced at the palette layer** (`compute_palette` empty-lead
rescue): recolor the blocking guard cluster - fork block plus all its
guarded kids, chains walked up - to the window palette, plus
MIN_RUN-2 plain blocks above the topmost fork so sibling-arm rides
never see a lead_lock-pinned short run; `absorb_up` clears slivers
above the cluster. `verify()` re-checks the rule on the final palette
("trigger color" errors).

Placement-time enforcement (rejecting splices whose trigger feeder is
fork-guarded, incl. suffix-walk trimming for landings) was built and
measured first and **rejected**: 7-seed (1/5/6/7/8/11/14) mean
forkgap viol 96 -> 120, splices down, erasures up - the funnel band
cannot spare the landing capacity. The palette rescue is
geometry-free: all stats bit-identical to baseline, pinned short runs
~identical, 16-22 rescues per seed, 0 unrescued, 0 trigger-color
verify errors.

**Landing side (same day)**: the block the teleport drops the player
on (win[1]) must not sit immediately after a color switch either.
win_uniform used to paint win[1:] to the window MAX palette, shoving
the flip onto the landing bounce with win[0] behind it in the old
color. Now windows uniform to the BASE block's (win[0]) palette - the
flip moves past the window end (monotone-safe: base level <= every
natural in-window level <= downstream). Anchoring runs PER-TURN
inside the sorted splice loop, not as a pre-pass, so a trigger
rescue that recolors a later-processed window's blocks self-heals:
the window re-anchors to the palette as it now stands (lead_locked
members keep their color; the copy mirrors the mixed sequence, so
tail fidelity always holds). The rescue veto is window-y aware:
copies, lead_locked blocks and windows processed at >= our y are
untouchable; strictly-later windows are fair game. verify() gained
"landing color" alongside "trigger color". 7-seed: both hists >= 1
everywhere, 0 color errors, geometry unchanged, pinned short runs
11 -> 13 total (reported-only).

Both rules are ALSO in walls.py's union-find palette (the one that
actually colors the world): the approach unions already covered the
trigger side; the landing side is `union(win[0], win[1])` plus a
validator line, with the window-side boundary-legalization walk
starting at win[0]. Seed-6 build: palette attempt 0 VALID, 0 rule
violations, datapack installed. Note wall_test.py is dead (imports
v2 generate_maze and hangs in its rewind_retry landing search).
