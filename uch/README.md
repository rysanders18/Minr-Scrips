# uch

A multiplayer party game for the Minr server in the style of Ultimate Chicken Horse: players race an obstacle course, then each draws a random block from a "party box" and places it on the course, making it harder for the next round. Rounds repeat with the same roster until someone reaches the win score. The game loop, scoring, block draft and build phase are implemented as MSC functions bound to a start button, a finish line, a fall zone and eight pedestals.

The game concept is Ultimate Chicken Horse by Clever Endeavour Games; this is a scripted approximation for a single course.

## How it works

**Game loop.** `startButton` gathers the roster, zeroes scores and calls `startRound`. `startRound` sets everyone to adventure mode, teleports them to the start, and runs a one-second-per-iteration backstop timer for `roundSeconds`. A round ends early when every runner is resolved (`finishLine` or `fallRegion` calls `endRound`) or when the timer expires. Either way the timer loop is the only caller of `buildPhase`, so exactly one build phase runs per round and no stale timers leak into the next. `buildPhase` checks the game-over condition, runs the block draft (`selectPhase`), gives `buildSeconds` for placement with a 5..1 countdown, then starts the next round with whoever is still online. `endGame` announces the winner and resets scores.

**Roster without a radius query.** MSC has no "players within N blocks" primitive; the only player-list source is `Region.getPlayersInside()`. `startButton` therefore reads candidates from a lobby region and measures the true 30-block radius from the presser in-script.

**Scoring** (`endRound.msc`, `awardPoints.msc`). UCH's default values scaled by ten so points stay integers: a round pays out only when somebody finished *and* somebody did not. Goal +10 for every finisher; First +2 for the first finisher when two or more finished; Solo +6 when exactly one of three or more finished. Points are only awarded in `endRound`, so `totalScore` is stable throughout a round.

**House rules.** These differ from UCH:
- *Underdog bonus* (+8): every finisher who entered the round `underdogGap` (25) or more points behind the leader. Underdog status is snapshotted before any points are awarded.
- *Underdog bonus life*: an underdog's first fall respawns them at the start instead of eliminating them (`fallRegion.msc`).
- Runners are on a `uchghosts` team with no-particle invisibility for the round: invisible to bystanders, translucent to each other via `seeFriendlyInvisibles`.

**Block draft** (`selectPhase.msc`, `selectBlock.msc`). Eight pedestals are stocked with weighted-random picks from four parallel pool arrays in `uch.nms` (block to place, item to give, display name, weight). The weighted pick walks cumulative weights and keeps reassigning the winner until the sum passes the roll, because MSC has no `break`. Players are dropped into the box in adventure mode with cleared inventories and claim a pedestal by clicking it; the block is removed so it is first come, first served. The countdown loop exits early the same way: once everyone has picked it simply stops delaying, so the remaining iterations drain instantly. Global arrays cannot be written by index in MSC (only `relative` arrays can), so marking a pedestal taken rebuilds `slotPick` with `-1` in that position. `createHoles` randomises the drop-tube floors each round.

**Per-player state.** Scores and round flags are `relative` variables (keyed by player), so `totalScore[p]` persists across rounds and is read back after each write in `awardPoints` so a failed write is visible in chat. Messages from functions that run under the button presser use `/tellraw {{player}}` rather than `@player`, which would address the wrong person.

## Layout

| File | Role |
| --- | --- |
| `uch.nms` | Namespace: setup instructions, config (timers, points, positions), block pool, game state, signatures. |
| `uch/__init__.msc` | One-time setup: binds the finish line and the eight pedestal interact scripts. |
| `uch/startButton.msc`, `startRound.msc`, `endRound.msc`, `buildPhase.msc`, `endGame.msc` | Game loop. |
| `uch/finishLine.msc`, `fallRegion.msc` | Trigger handlers bound to world positions/regions. |
| `uch/selectPhase.msc`, `selectBlock.msc`, `createHoles.msc` | Block draft. |
| `uch/isUnderdog.msc`, `awardPoints.msc`, `showScore.msc` | Scoring helpers and a debug print. |

## Running it

Server setup is listed at the top of `uch.nms`: create a `uchlobby` region around the start button, bind `uch::startButton(Player)` to the button, `uch::finishLine(Player)` to the finish trigger, `uch::fallRegion(Player)` to the fall zone, and `uch::selectBlock(player, N)` to each pedestal (`__init__.msc` does the pedestal bindings). Pressing the button once starts a whole game; later rounds start automatically. Debug: `/function execute uch::showScore(Player("Name"))`.

## Notes and limitations

- One game at a time; game state is global.
- Placement during the build phase is honour-system (survival mode, one item given).
- `startRound` clones a fixed block region to reset the course; coordinates are hardcoded to the Theta world.
- `maxRounds` is only a backstop against a game that never scores.
