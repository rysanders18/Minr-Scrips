# Minr Scripts

Game systems, engines and world generators for the [Minr](https://minr.org)
Minecraft server, written in MSC (Minr's server-side scripting language), with
the Python tooling that generates, verifies and analyses them.

MSC is a small, event-driven language: no bitwise operators, no `break`, no
threads, lists capped at 1000 elements, per-player state declared as
`relative`, and every script shares one server tick budget. Most of the
interesting work in this repo is about building real systems inside those
limits: a chess engine that yields between root moves, a player-physics model
driving an armour stand, a maze generator whose dead ends teleport you without
you noticing, and an image codec that moves 128x128 map art through the chat
box. [MSC_FORMAT_DOCUMENTATION.md](MSC_FORMAT_DOCUMENTATION.md) is the
language reference I maintain, since there is no official one.

## Highlights

| Project | What it is | Worth a look |
|---|---|---|
| [rychess](rychess/) | Chess engine plus a physical board of `block_display` entities. The opponent walks to the board and moves the pieces. | Negamax alpha-beta with quiescence and incremental evaluation in a language with no bit operators. Moves packed into one Int by multiply/modulo. Search yields a tick between root moves; `humanCanMove` guards the position from clicks mid-search. Perft and make/unmake tests. [`sim/`](rychess/sim/) is a JavaScript port with a shortest-forced-mate solver and a UCI match harness. |
| [slimeMaze](slimeMaze/) | Procedural generator for a seamless slime-bounce maze of roughly 815,000 blocks. | The maze is a DAG built from one reverse-engineered bounce arc. Every dead end is an integer-translated copy of a live corridor, so a relative `/tp` preserves position, view and momentum and the player never sees the end. v3 rewrite: skeleton-first planning, landing-only dead ends, spatial hash. Walls are the boundary of a rasterised footprint, gap-free by construction, then relaxed with a cellular automaton. |
| [rymaphub](rymaphub/) | Map-art importer that receives a 128x128 image as a series of chat messages and builds it. | Symbols are indices into a 2,980-character CJK alphabet because MSC's only char primitive is `indexOf`. Run-length coding, per-message checksums, and a structural invariant that no two adjacent characters are equal (the chat pipeline drops characters from long runs). Staircase heights are recomputed on both ends instead of transmitted. |
| [mannequin](mannequin/) | A reimplementation of Minecraft player movement so an armour stand can sprint, jump and coast like a player. | Sprint acceleration, ground/air drag, the sprint-jump speed kick, swept AABB collision against per-block shapes, a generation counter to cancel in-flight tick loops, input recording and playback, footstep sounds by block. |
| [clone-map](https://github.com/AK1089/clone-map) (submodule) | Bit-exact replay of a recorded input stream through a port of vanilla `LivingEntity.travel()` / `Entity.move()`. Joint project with AK1089. | Follows vanilla's float/double casts literally, uses the start-of-tick `onGround` flag for drag, and includes a probe that checks whether MSC's `Float` is real IEEE-754 single precision. |
| [nfa](nfa/) | Build a nondeterministic finite automaton out of blocks, draw transitions as particle curves, and run strings through it. | Epsilon closure, move and string simulation with memoised variants; Catmull-Rom and Hermite splines for the branches; state sharded across 20 rooms because MSC cannot resolve a variable by computed name; a graded bank of over 100 exercises. |
| [j100](j100/) | A 100-jump parkour hub with per-player telemetry and a difficulty ranking. | `rank_jumps.py` fits a latent-variable model (jump difficulty + player skill) to falls, teleports, times and ratings, treating unfinished jumps as censored data. `make_report.py` renders a self-contained HTML report. |
| [Cookie](Cookie/) | An idle/clicker game with golden cookies, a milk multiplier and seven upgrade ladders. | `cookie_opt.py` models the game analytically and solves for the fastest upgrade order, including a closed-form save-up window before each milk cycle. |
| [uch](uch/) | A multi-round party game in the style of Ultimate Chicken Horse: run, score, draft blocks, build, repeat. | Round state machine that owns its own timers, underdog catch-up, a first-come block draft, and workarounds for MSC having no radius query and no `break`. |
| [irodori](irodori/) | Colour-burst animation: 35 `block_display` entities scatter and re-converge with particles and a rising chime. | Entity tag doubles as colour index. `irodori_gradient.py` builds a 240-step armour-dye gradient in OKLCH so hue sweeps keep even lightness and chroma. |
| [entity_ai](entity_ai/) | Repaired build of D4rkSly's armour-stand animation library. | Root-caused a silent break on Minecraft 1.21.6+ (one-element `Rotation` NBT rejected by the fixed-size codec), recovered four helper functions missing from the export, and shipped a minimal patch for existing installs. |

Smaller pieces: [rygamb](rygamb/) (a slot machine with tuned near-miss
psychology), [lendfishing](lendfishing/) (fishing minigame with a weighted loot
table built from MSC classes), [endmap](endmap/) (End-dimension parkour with a
tag-addressed cube animation), [lavamap](lavamap/) (a rideable-pig cutscene
camera), [project](project/) (a BDEngine keyframe animation ported to MSC),
[Harha](Harha/) (production scripts for the Harha map: stages, checkpoints,
cosmetics, leaderboards, note-block music), [rytools](rytools/) (shared
helpers such as particle lines and bulk script binding) and [tools](tools/)
(one-off converters, including a Note Block Studio to MSC compiler that fits
whole songs under the paste size limit).

## How the code is organised

Each namespace follows Minr's on-disk convention:

```
<ns>.nms            namespace manifest: state, constants, every function signature
<ns>/<fn>.msc       one function per file; the first comment block is its spec
<ns>/__init__.msc   runs once on import to summon entities or wire triggers
<ns>/# <name>.msc   standalone scripts bound to a button, sign or region
<ns>/<Class>/       MSC classes: Class(ArgTypes).msc constructors and method files
```

Tests are MSC functions named `test*` that print their results in-game; there
is no runner because there is no local interpreter. Scripts are uploaded to the
server through Minr's paste service, which caps a single import at roughly
4,000 lines, so large generated builds are emitted as chains of functions that
tail-call the next part.

Python lives next to the namespace it serves (`slimeMaze/`, `j100/`,
`Cookie/`, `irodori/`) or in `tools/` when it is a general converter.

## What is deliberately not committed

The generators produce hundreds of megabytes of `/setblock` and `/fill`
scripts, datapack functions, pickled caches and motion-capture arrays. Those
outputs are gitignored (see [.gitignore](.gitignore)); the repo keeps the
generators, the design documents and the small registries needed to reproduce
a build. A few generated files stay because they are the world itself and are
not reproducible from source, such as `rychess/rychess/__init__.msc`.

## Credits

- `clone-map` is a collaboration with [AK1089](https://github.com/AK1089), tracked here as a submodule.
- `entity_ai` is a repair of D4rkSly's library; the original design and API are theirs.
- `rymaphub` uses the Valley staircasing method from MapartCraft. The chess evaluation uses Michniewski's piece-square tables.
- `project` animates a model exported from BDEngine. `uch` borrows its rules from Clever Endeavour Games' Ultimate Chicken Horse.
