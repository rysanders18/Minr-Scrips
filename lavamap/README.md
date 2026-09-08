# lavamap

Intro cutscene rig for the "Katla" lava map on the Minr server. Pressing the start trigger mounts the player on a gravity-less pig, blinds them briefly, and drives the pig along a scripted flight path by writing its `Motion` vector every tick for about nine seconds, with lava sounds and flame particles, before dropping the player at the map start. The namespace also handles the awkward case of a player logging off mid-flight, and includes a colour-sweep animation for the map's title display.

## How it works

**Pig camera** (`startAnimation.msc`). The pig is summoned with `NoGravity`, `Silent` and `Invulnerable`, tagged `lavamappig<N>`, and the player is mounted with `/ride`. `motionValues` is a table of roughly 185 per-tick velocity vectors; the loop applies one per tick with `/data merge entity ... {Motion:[...]}`, re-aims the rider with `/rotate` (facing a fixed point for the first 120 ticks, then a fixed yaw/pitch for the landing), and emits particles and three layered lava sounds whose pitch falls as the flight progresses. On completion the pig is teleported away and killed.

**Pig numbering** (`# startAnimationWalkScript.msc`). Each cutscene increments a global `pigNumber` (wrapping 0..9) so every pig has a unique tag; the walk script kills the previous number's pig before starting a new one. `lastPigNumber[player]` records which pig a player rode.

**Logout handling and the idempotence gate** (`rejoinFunction.msc`, `lavamap.nms`). A player who logs off while mounted takes the pig with them; it reappears when they rejoin, still mounted, and would continue where it was. The loop checks `player.isOnline()` every tick. At the moment it detects a logout it still holds the `Player` object, so it queues a `/login action add <name> function execute lavamap::rejoinFunction("<name>")` with the username baked in as a literal, and sets `loggedOffMidCutscene[player] = 1`.

That flag is the idempotence gate. A queued login action can outlive the situation that created it: the player could rejoin, start a fresh cutscene, and only then have the stale action fire. `startAnimation` clears the flag at the start of every cutscene, and `rejoinFunction` returns immediately unless the flag is `1`, then clears it once cleanup has run. Cleanup kills whatever the player is riding (`/execute as <name> on vehicle run kill @s`, which needs no tag bookkeeping) and teleports them to the map start.

Two other designs were tried and rejected, documented in `rejoinFunction.msc`: a WorldGuard entry command with `%username%` (the server does not substitute the placeholder, so `Player("%username%")` had a null UUID), and an entry flag with `Region.getPlayersInside()` (entry flags fire on boundary crossing; a relogging player is already inside and crosses nothing). Two invariants follow from running under a login action: `Player(username)` resolves the UUID at construction, so the `@delay` must come before it, not after; and the function runs from console with no executor, so every command uses `@console` with explicit selectors and `/execute in` for the dimension.

**Title animation** (`katlaTextDisplay.msc`). A 16-frame effect on the `katlaTextDisplay` text entity: a white-blue wavefront sweeps across the five letters one per tick, then each letter fades back to its resting colour on a staggered schedule through a precomputed six-step path (stored flat as `fadeSteps[j*6 + step]` because MSC has no 2D arrays). Every frame rewrites the full text component list with `/data merge`; the final frame equals the resting colours so the function is safe to re-run. A 15-tick global cooldown prevents overlapping runs.

## Layout

| File | Role |
| --- | --- |
| `lavamap.nms` | Namespace: `pigNumber`, per-player `lastPigNumber`, `lastCutsceneTime`, `loggedOffMidCutscene`, signatures. |
| `lavamap/__init__.msc` | Summons the title text displays, the hanging-sign hint displays along the route, and the minecart. |
| `lavamap/startAnimation.msc` | The cutscene loop. |
| `lavamap/rejoinFunction.msc` | Login-action cleanup for mid-cutscene logouts. |
| `lavamap/katlaTextDisplay.msc` | Title colour-sweep animation. |
| `# startAnimationWalkScript.msc` | Standalone trigger script: rotates `pigNumber` and calls `startAnimation`. |

## Running it

`# startAnimationWalkScript.msc` is bound to the start trigger (a walk-on script) and calls `lavamap::startAnimation(player, pigNumber)`. `katlaTextDisplay()` is intended for a nearby trigger and calls `rytools::particleLine` for an accent effect. `__init__.msc` is run once to place the display entities.

## Notes and limitations

- All coordinates are hardcoded to the Theta world.
- `rejoinFunction` relies on the 1.19.4+ `on vehicle` selector; a tag-based fallback using `lastPigNumber` is left commented out.
- Blindness on mount lasts one second; the ride itself has no fade-in.
