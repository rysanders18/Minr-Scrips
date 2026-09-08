# NFA builder

An in-world editor and simulator for nondeterministic finite automata, written in MSC for the Minr Minecraft server. Players place blocks in a 5x5x5 grid to define states, click block faces with colour-coded swords to draw transitions as curved particle trails, and press a button to run a bank of accept/reject strings through the machine they built. Each room is a graded exercise: the button checks the player's automaton against the language for their current level.

## Block mapping

The automaton is stored as blocks and edge records, not as a separate data structure. This mapping is hardcoded across most files.

| Block | Meaning |
|---|---|
| `NETHERITE_BLOCK` | State with no incident transitions |
| `IRON_BLOCK` | State with at least one transition |
| `SEA_LANTERN` | Start state |
| `EMERALD_BLOCK` | Accept state |
| `VERDANT_FROGLIGHT` | Start and accept state |
| `GOLD_BLOCK` edge | Transition on symbol `0` |
| `DIAMOND_BLOCK` edge | Transition on symbol `1` |
| `WAXED_COPPER_BLOCK` edge | Transition on symbol `2` (only offered at `hotbarLevel > 2`) |
| `IRON_BLOCK` edge | Epsilon transition |

Held item selects the tool (`hotbarFunction.msc` populates the hotbar; `nfaInteractBlock.msc` dispatches on it): golden/diamond/copper/iron swords draw a `0`/`1`/`2`/epsilon transition between two clicked faces; a netherite pickaxe removes a state (refused if any transition touches it); a netherite block adds a state three blocks away in the clicked-face direction; netherite ingot / prismarine crystals / emerald convert a state to basic / start / accept.

## How it works

**Data model.** Everything is keyed by coordinates. States are `"x,y,z"` strings. A transition is one entry in a connection list: `connection;x1,y1,z1;x2,y2,z2;minecraft:<edge_block>;<pos1>;<pos2>;<geometry>`, where the last field carries the clicked-face positions, normals and sample count so a room can be redrawn without recomputing them. Transitions are directed. A parallel branch list holds the entity tags (`branch{pos1}{pos2}`, both orderings) used to find and kill the block_display entities that render each curve. A third structure, `listOfBlocks`, is a 125-entry positional array of state-type codes over the grid (index = `dx/3*25 + dy/3*5 + dz/3` relative to the room origin), which is what `setupRoom.msc` replays to rebuild a room.

**Simulation** (`processString.msc` is the reference implementation):

1. `getStartStates` scans the connection list and returns endpoints whose block is a sea lantern or froglight.
2. `getEpsilonClosure` does a breadth-first search over iron edges. MSC has no `while` loop, so the worklist is driven by `@for ... list::range(0, 100)` with an index guard; 100 is the iteration cap.
3. For each input symbol, `move` collects the targets of matching edges from every current state, then the epsilon closure is taken again.
4. `isAcceptState` checks the final set for an emerald block or froglight.

`runTest.msc` implements the same algorithm with per-step chat output and particle highlights (`visualizeStates`) for debugging; the two must be kept in sync. `processStringFast` / `moveFast` / `getEpsilonClosureFast` are the batch variants: the connection list is split into parallel `froms`/`tos`/`types` arrays once, and the start-state closure is computed once by the caller, so a test bank of 30 strings does not re-parse every record on every scan.

**Curved branches.** `drawTransition.msc` samples a Hermite curve (`hermiteTwoPoint.msc`) from the first clicked face to the second, using the face normals as tangents, and summons one small block_display per sample point, animating with a delay every three entities. The last point is an emerald block that acts as the arrowhead. Scale is jittered slightly per branch to avoid z-fighting between overlapping curves. `catmull.msc` is a Catmull-Rom sampler kept alongside it. `visualizeString.msc` walks a string's path and toggles `glow_color_override` on each traversed branch's entities so a player can see why a test string was accepted or rejected.

**Sharded room state.** MSC's `relative` variables are per-player, but a room is co-op: several players edit one automaton. There is no dynamic variable lookup, so `nfa.nms` declares twenty copies of the three lists (`listOfBranches0..19`, `listOfConnections0..19`, `listOfBlocks0..19`, indexed `world*5 + room`) and accessor functions (`getBranches`, `appendConnection`, `removeBranch`, `editListOfBlocks`, `clearRoom`, ...) that are `@if roomIdx == N` chains over the copies. The shared copy is the source of truth for reads; writes also update the relative copy of every player currently in the room's region so a player's own build survives when they leave. `rejoinRegion.msc` handles re-entry: join a room that already holds a same-level teammate (`loadRoomToRelative` adopts its state), else claim an empty room and `setupRoom` replays the player's saved build into it, translating coordinates by 100 blocks in Z per room (`changePlayersRoomVariables`).

**Exercise bank.** `testMultipleCases.msc` holds 80 levels, each a language description plus accept and reject strings (equality, substring, divisibility, parity, regex-style patterns, and so on). The button runs every string, writes a tick/cross list into two text_display entities per room (`nfaAccepted{room}{world}`, `nfaRejected{room}{world}`), attaches a clickable `@chatscript` to each failing string that lights up its path, and plays `allTestsPassedTitle` for everyone in the room on a clean pass. A five-second debounce stops button spam.

## Layout

| File | Purpose |
|---|---|
| `nfa.nms` | Namespace: room origins, the 20 sharded lists, per-player state, function signatures |
| `nfa/nfaInteractBlock.msc` | Every block click in build mode; tool dispatch and branch creation/removal |
| `nfa/drawTransition.msc`, `hermiteTwoPoint.msc`, `catmull.msc`, `vecToXYZ.msc` | Curve rendering |
| `nfa/processString.msc`, `move.msc`, `getEpsilonClosure.msc`, `getStartStates.msc`, `isAcceptState.msc` | Simulator |
| `nfa/*Fast.msc` | Pre-parsed batch simulator |
| `nfa/runTest.msc`, `testMultipleCases.msc`, `visualizeString*.msc` | Test harness and path visualisation |
| `nfa/get*/append*/remove*/clearRoom/editListOfBlocks.msc` | Room-state accessors |
| `nfa/setupRoom.msc`, `loadRoomToRelative.msc`, `changePlayersRoomVariables.msc`, `rejoinRegion.msc` | Room lifecycle |
| `nfa/# *.msc` | Standalone scripts bound to regions, buttons and levers in-game |
| `nfa/__init__.msc` | One-time world setup: region scripts and the 125 interaction scripts per room |

## Running it

Functions are invoked by the server: `__init__.msc` imports the region-enter script and one interaction script per grid slot in each room via `/script import`, and the `# *.msc` files are attached to the reset button, test button and visualise lever. The world is hardcoded to `Theta`.

## Notes and limitations

- MSC has no `while`, no `atan2`/`min`/`max`, and no inline comments. Bounded `@for` loops stand in for `while`.
- Coordinates travel as strings; face keys inside connection records are concatenated floats with no separator, so they cannot be parsed back and are regenerated from the geometry field when rooms are shifted.
- Twenty shards are declared (four worlds of five rooms) but only world 0's five room origins and regions exist.
- No per-room locking: two players can start drawing the same branch at the same time (noted as a TODO in `nfaInteractBlock.msc`).
