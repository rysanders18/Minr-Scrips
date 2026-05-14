# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`.msc` scripts for the **Minr** Minecraft server that let a player build and simulate a Nondeterministic Finite Automaton (NFA) inside the world. Players place blocks to define states and transitions, draw curved "branches" between them with particles, then run test strings through the resulting machine.

There is no build system, compiler, or test runner — these files are uploaded to the Minr server and invoked by the Minr scripting engine. "Running" something means triggering the corresponding script in-game (block interaction events, chat scripts, function calls). When iterating, the only way to verify behavior is to run it on the server.

The MSC language reference for the whole repo lives in `MSC_FORMAT_DOCUMENTATION.md` (this directory). All functions here use `@using nfa` and are called as `nfa::functionName(...)`.

## Block → NFA element mapping

This convention is the core domain model and is hardcoded across nearly every file. Do not invent new block meanings without updating all of them.

| Block                 | Meaning                                                |
|-----------------------|--------------------------------------------------------|
| `NETHERITE_BLOCK`     | Basic state with no incident transitions              |
| `IRON_BLOCK`          | Basic state that has at least one transition          |
| `SEA_LANTERN`         | Start state                                           |
| `EMERALD_BLOCK`       | Accept state                                          |
| `VERDANT_FROGLIGHT`   | Start **and** accept state (combined)                 |
| `GOLD_BLOCK` edge     | Transition on symbol `"0"`                            |
| `DIAMOND_BLOCK` edge  | Transition on symbol `"1"`                            |
| `IRON_BLOCK` edge     | Epsilon (ε) transition                                |

Held-item → tool mapping (see `hotbarFunction.msc` and the dispatch chain in `nfaInteractBlock.msc`):
- Golden / Diamond / Iron Sword → place a `0` / `1` / `ε` transition between two clicked block-faces
- Netherite Pickaxe → remove a state (only allowed if no transitions touch it)
- Netherite Block → add a new state 3 blocks away in the clicked face direction
- Netherite Ingot / Prismarine Crystals / Emerald → convert a state to Basic / Initial / Accepting

## Per-player state model

Everything is keyed by `[player]` because multiple players can build their own NFA in the same world. The important player-scoped variables (set elsewhere on the server, read here):

- `listOfConnections[player]` — `String[]` of `"connection;x1,y1,z1;x2,y2,z2;minecraft:<edge_block>;<pos1Str>;<pos2Str>"` entries. Always 6 `;`-delimited parts; `parts[0] == "connection"` is the canonical guard. Connections are **directed** (`parts[1]` → `parts[2]`).
- `listOfBranches[player]` — `String[]` of `"branch{x1}{y1}{z1}{x2}{y2}{z2}"` tags (both orderings stored) used to look up the `block_display` entities that render the curve.
- `posMode[player]` — Boolean two-click state machine for sword tools (false = next click sets pos1, true = next click sets pos2).
- `pos01[player]`, `pos02[player]`, `norm01[player]`, `norm02[player]` — `Vector3` clicked-face center + outward normal for the in-progress branch.
- `hotbarLevel[player]` — gates which hotbar slots are populated (0/1/2 tiers).
- `timeOfLastBranch[player]` — debounce for branch removal (900ms).

The world is hardcoded to `"Theta"` everywhere — block lookups go through `Block(x, y, z, "Theta")`.

## Simulation pipeline

`processString.msc` is the canonical reference for how the NFA simulator runs. Conceptual flow:

1. `getStartStates(player)` — scans `listOfConnections[player]`, dedupes endpoints, returns those whose block is `SEA_LANTERN` or `VERDANT_FROGLIGHT`.
2. Take ε-closure of every start via `getEpsilonClosure(player, blockCoords)` — BFS over directed `iron_block` edges, capped at 100 iterations (no real `while` loop in MSC, so the code uses `list::range(0, 100)` as a bounded loop).
3. For each input character: `move(player, currentStates, symbol)` (gold for `"0"`, diamond for `"1"`), then re-take the ε-closure of the result.
4. `isAcceptState(coords)` — true if the block is `EMERALD_BLOCK` or `VERDANT_FROGLIGHT`. Accept iff any final state passes.

`runTest.msc` mirrors this pipeline but adds per-step `@player` debug output, `visualizeStates` particle highlights, and `@delay 20` between steps when `debug == true`. Use `runTest` (not `processString`) when you need step-by-step traces.

`# Test Multiple Cases.msc` is the integrated test harness — it holds many predefined languages (regex / counting / divisibility challenges) as commented-out `acceptStrings` / `rejectStrings` blocks, runs `runTest(testString, player, false)` over each, and writes per-string results to two `block_display` entities (`nfaAccepted1`, `nfaRejected1`) with clickable `@chatscript` triggers that re-run a specific case in debug mode.

When changing the simulator: update `processString.msc` and `runTest.msc` together — they implement the same algorithm twice and will silently diverge otherwise.

## `nfaInteractBlock.msc` (the dispatcher)

This file is large (~700 lines) and is the entry point for **every** block click in NFA-build mode. Structure: a flat sequence of `@if player.getItemInMainHand().getItemType() == "..."` blocks, each ending in `@return`. New tools should be added as another such block, not nested into an existing one.

Important sub-flows already in the file:
- Sword branch creation walks through: pick face → set pos1 → pick face → set pos2 → if same branch already exists then remove it (with smoke particles + revert iron→netherite if no other connections remain) → otherwise validate (no shared endpoint, no duplicate symbol from same source) → store connection → render curved branch with `nfa::hermiteTwoPoint` → spawn `block_display` entities tagged `nfaBranch`, `nfaBranch{i}`, and the per-branch tag.
- Pickaxe (state removal) refuses if any connection in `listOfConnections[player]` references the block.
- Netherite ingot toggles a state between `IRON_BLOCK` (when it has connections) and `NETHERITE_BLOCK` (when it doesn't).

Branch entities are tagged `nfaBranch` plus a per-coordinate tag — kill with `/kill @e[tag=branch{x1}{y1}{z1}{x2}{y2}{z2}]`. The reset script (`# test reset button.msc`) clears `listOfBranches`, `listOfConnections`, and `@e[tag=nfaBranch]` together.

## MSC language gotchas in this codebase

- **No `while` loops.** Use `@for Int i in list::range(0, N)` with an internal counter and `@if index < toProcess.length()` guard (see `getEpsilonClosure.msc`).
- **No `atan2`, `toDegrees`, `min`, or `max`** in MSC's math library. `math::arctan` already returns degrees — do **not** wrap it in a degree conversion. Implement quadrant correction manually if you need full-circle angles.
- **No inline comments.** `@var x = 5  # comment` will break the parser; comments must be on their own line.
- **String coordinate keys.** Block coordinates are passed around as `"x,y,z"` strings (split with `.split(",")`, parse with `Int(...)`). Position face coordinates in connection records are `"{{x}}{{y}}{{z}}"` strings with **no separators** — the floats are concatenated directly. Don't change one format without updating both endpoints of every connection lookup.
- **Connection record validation.** Always guard with `parts.length() == 6 && parts[0] == "connection"` before indexing — older entries or unrelated strings can leak into the list.
- **Booleans in arrays / nested expressions.** Side-effect calls go through `@var foo.append(...)`; reading uses `@define`. Mixing them up silently does nothing.

## When editing curve / geometry code

`hermiteTwoPoint.msc`, `catmull.msc`, `vecToXYZ.msc` are the spline utilities used for branch rendering. `vecToXYZ` parses a `Vector3` by `"{{v}}".split(" ")` — it depends on the engine's default Vector3 string format, so don't reformat the interpolation.

`nfaInteractBlock.msc` has a special-case `count` override based on a substring of `String(arcLength)` (look for `"1.00984782"`). This is a workaround for floating-point quirks in unit-length branches; leave it unless you're rewriting the whole arc-length pass.

## Conventions

- camelCase for functions, variables, files (`getStartStates.msc`, `processString`).
- Function header comment on line 1 with the signature, e.g. `# Boolean processString(Player player, String input)`.
- `@fast` and `@using nfa` at the top of every file in this directory.
- Player-facing strings use Minecraft color codes (`&c`, `&e`, `&a`, `&6`); debug lines are usually left commented as `# @player DEBUG: ...`.
