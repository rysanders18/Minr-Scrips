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

## Open items for the user

- Confirm WINDOW=7 as the v3 default (requested last session, never measured; 6–7
  bounces past the trigger at 8 → 5–6 at 7).
- Target splice/landing count and entry count stay at v2-ish levels (10 entries,
  ~150+ terminations) unless you want a different density.
- Whether the emitted v3 replaces the world immediately (Phase 6) or v3 is validated
  offline first while seed-13 v2 keeps standing. Plan assumes offline-first.
