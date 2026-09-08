# mannequin

A server-side reimplementation of Minecraft player movement physics, driving a `mannequin` entity that sprints, bunny-hops, collides with terrain, and plays footstep and landing sounds like a real player would. It runs as MSC scripts on the Minr server: each tick the script integrates velocity, sweeps the player-sized AABB against block collision shapes it resolves itself, and teleports the entity to the result. A second motion path replays motion-captured player recordings. The `rychess` chess engine (`../rychess`) uses this namespace as its visible opponent: the mannequin physically walks to the board, turns its head to look at squares, and moves pieces.

## How it works

**Physics constants** (`mannequin.nms`). The per-tick horizontal update is `v += accel * heading; pos += v; v *= drag`, with the vanilla asymmetry preserved: `sprintAccel = 0.13` on the ground but `sprintAirAccel = 0.026` in the air, `groundDrag = 0.546`, `airDrag = 0.91`. Vertical motion uses `jumpVel = 0.42`, `gravity = 0.08`, `airDragVertical = 0.98`. On every grounded cruise tick a sprint-jump kick fires (`velY = 0.42`, plus `sprintJumpBoost = 0.2` along the heading) — the bunny-hop that raises terminal speed from about 0.286 to 0.357 blocks/tick. Drag is selected from the start-of-tick grounded flag, matching where vanilla samples friction; using the post-collision flag inflated terminal speed noticeably.

**Tick loop** (`cruiseTick.msc`). Two phases share one physics body. *Cruising* tracks yaw toward the target and applies acceleration and jump kicks; *coasting* applies no input and lets drag and gravity decay momentum until the entity is grounded and slower than `restSpeedSq`. The cruise-to-coast switch fires at `brakeDistSq` (1.5 blocks) so the slide lands near the target. In-progress jumps are never aborted, which is why arrival has some variance, as it does for a real player.

**Collision** (`getBlockBoxes.msc`, `collideX/Y/Z.msc`). `getBlockBoxes` returns a block's collision shape as a flat `Double[]` of local AABBs (six values per box), decoding block state for slabs, stairs, trapdoors, fences, panes, walls, and fence gates (fences and walls extend to 1.5 tall, as in vanilla). Unknown blocks default to a full cube. `collideY` clamps the vertical delta against those boxes and is the sole writer of `onGround`; `collideX`/`collideZ` clamp the horizontal deltas. The axis order flips between Y-X-Z and Y-Z-X depending on which horizontal velocity dominates, reproducing the vanilla 1.14+ corner behaviour. Overlap tests run per sub-box, not per cell, so a stair's upper quadrant does not over-claim its block.

**Cancellation without threads.** MSC has no way to cancel a running loop, so `tickGen` is a generation counter: `cruiseTo` bumps it and starts a fresh `cruiseTick`, and any older loop notices the mismatch on its next iteration and returns. `stopCruising` deliberately does *not* bump it — it flips `isCruising` to `isCoasting` so the existing loop carries the momentum to rest instead of stopping dead. Every loop also has an iteration cap (1000 ticks) as a safety net.

**Facing.** `easeStep.msc` is a three-regime turn curve (capped at `maxTurnPerTickDeg`, exponential in the middle, floored at `minFacingStepDeg`) used by the coast phase of `cruiseToFacing`, by `easeFaceTo` (turn in place), and via `clampTurn` while tracking the target. Yaw differences are wrapped to (-180, 180] so turns take the short way. There is no `atan2` in MSC; the heading is built from single-argument `math::arctan` plus a hand-written quadrant correction.

**Recording and playback.** `recordInputs` samples the player's seven movement keys once per tick. MSC cannot read key state directly, so each tick appends `false` to every array and issues `/execute if predicate` commands (the 1.21.2+ `entity_properties` input predicate) that call back into `recInputTrue` to flip a slot to `true`. `recordPrerecording` captures 1000 ticks of position, yaw, pitch and sneak into one of ten `prerecording<N>` slots; `playPrerecording` replays a slot at one teleport per tick, emitting sprint dust on fast frames and switching the entity pose on sneak transitions. Playback checks `prerecordingActive` every tick so `stopPrerecording` can interrupt it, freezing the mannequin at its last frame. `startRandomPrerecording` dispatches playback through `/function execute` so the caller does not block.

**Sounds and particles** (`emitStepSound.msc`, `emitFallSound.msc`, `emitBlockSound.msc`, `emitSprintParticle.msc`). These mirror the vanilla 1.21 `Entity#move`, `updateFallStateInternal`, `handleFallDamage` and `spawnSprintParticle` logic: a `moveDist` accumulator (`+= sqrt(dx²+dz²) * 0.6` per tick) that fires a step when it crosses `nextStep`; a fall-distance tracker that plays `small_fall`/`big_fall` only when `ceil(fallDistance - 3) > 0`, so flat-ground sprint-jumps stay silent; and a block-to-sound-group table with the vanilla volume and pitch scaling. Sneaking mutes steps but still advances the accumulator, so there is no burst of footsteps when sneaking ends.

**Final approach** (`sneakWalkTo.msc`). Closes the residual gap left by a coast at sneak-walk speed with the heading locked to one of the eight key-direction vectors, so the approach reads as a player adjusting rather than a rig panning.

## Layout

| File | Role |
| --- | --- |
| `mannequin.nms` | Namespace: per-player state, physics constants, function signatures. The header comments are the spec. |
| `mannequin/spawnMannequin.msc` | Summons the entity and resets all per-player state. |
| `mannequin/cruiseTo.msc`, `cruiseToFacing.msc`, `stopCruising.msc` | Public movement API. |
| `mannequin/cruiseTick.msc` | The per-tick physics loop. |
| `mannequin/getBlockBoxes.msc`, `collideX.msc`, `collideY.msc`, `collideZ.msc` | Collision. |
| `mannequin/easeFaceTo.msc`, `easeStep.msc`, `clampTurn.msc`, `setFacing.msc` | Orientation. |
| `mannequin/sneakWalkTo.msc` | Crouched final approach. |
| `mannequin/recordInputs.msc`, `recInputTrue.msc` | Per-tick key-state capture. |
| `mannequin/recordPrerecording.msc`, `recPrerecordingSneak.msc`, `playPrerecording.msc`, `startRandomPrerecording.msc`, `stopPrerecording.msc` | Motion capture and replay. |
| `mannequin/emit*.msc` | Footstep, fall, block-sound and sprint-particle emulation. |
| `mannequin/testMannequin.msc`, `testRandomCruise.msc` | In-game end-to-end tests. |

The motion-capture data files (`# prerecordingSet1..3.msc`, which load the captured `prerecording<N>` arrays with `/var set`) and the `# Chess Room.msc` build dump are generated data of several hundred kilobytes each and are kept out of the repository. `# @player prerecordings.msc` is the utility that prints captured arrays so they can be pasted into a set file.

## Running it

Functions are invoked in-game with `/function execute`, for example `/function execute mannequin::cruiseTo(Player("Name"), Float(-9120.0), Float(9670.0))`. `testMannequin` and `testRandomCruise` are intended to be bound to a button or sign on flat ground. In normal use the namespace is driven by `rychess` (`play`, `engineMove`, `performEngineMove`).

## Notes and limitations

- Spawn position and the initial teleport in `recordPrerecording` are hardcoded to the chess room; the entity is tagged `mannequin_rychess`.
- Vanilla's 0.6-block auto step-up is not implemented, so carpets and bottom slabs stop the mannequin.
- The sneak-walk path does not run collision; it assumes the flat chess-room floor.
- The entity is a regular server entity moved with `/tp` every tick, not a display entity; smoothness comes from the 20 Hz update plus client interpolation.
- Only the sprint-sized AABB (0.6 x 1.8) is modelled; sneak, swim and glide resizes are not.
