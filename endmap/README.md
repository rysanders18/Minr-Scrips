# endmap

Scripts for a checkpoint parkour map in the End dimension (`theta_the_end`) on the Minr server. The namespace holds sixteen checkpoints with per-player progress, a respawn-anchor and end-portal-frame set piece, and "The Cube": a cutscene that assembles a 9x9x9 cube of `block_display` entities shell by shell while the player is carried past it on an invisible pig.

## How it works

- **Checkpoints.** `cpnumber` is a `relative Int`, so each player has their own progress. `checkpointPressurePlate(cp, player)` grants a checkpoint only if `cp` is higher than the one held, calls the server's `setCheckpoint()`, and plays a two-note chime plus a double particle helix around the plate. `returnToCP` teleports to `respawnPositions[cp]`; `kill.msc` is the fall handler that calls it. `__init__.msc` binds every region, walk and interact script to its world position with `@command /script i ...` lines pointing at the pasted script sources.
- **End portal frames.** `endPortalFrame(block, frameNumber)` fills the frame the player clicked (`eye=true`), places a small set of stained-glass blocks associated with that frame index, alternating magenta and purple by parity, and runs a two-second particle and sound sequence. `# endPortalFrameInteract.msc` is the standalone interact script with the frame number hard-coded.
- **The Cube.** 631 `block_display` entities in a 9x9x9 grid carry two coordinate systems in their tags: `rycube_x<X>_y<Y>_z<Z>` is the grid cell, and `rycube_d<D>_i<I>` is the diagonal shell, where `D = (8 - x) + y + z` (0..24) is the plane perpendicular to a body diagonal and `I` is the entity's index within that plane. `theCubeShellAnimation` restores one shell to the identity transform every 4 ticks with a 30-tick interpolation, so the cube sweeps into existence along the diagonal. Pre-tagging the shells replaces the earlier approach (still visible commented out at the end of `theCubeAnimation.msc`) of looping over all 1000 grid tags per shell and testing `(9 - x) + y + z == d`; the shell sizes `1, 3, 6, 10, ..., 49, ..., 1` are hard-coded in the animation. `theCubeShellParticles` emits dust at each shell with a rising pitch sweep.
- **The cutscene.** `theCubeAnimation.msc` refuses to start if anyone is already inside the cutscene region, scatters the cube to random invisible transforms, mounts the player on a silent, gravity-less pig, and forces their facing toward the cube each tick while calling the shell animation and particles on fixed ticks. It then draws a glyph with several hundred `rytools::particleLine` calls and teleports the player back to the start. `finalAnimation.msc` is the ending variant of the same pig ride.

## Layout

| Path | Role |
|---|---|
| `endmap.nms` | Namespace: `cpnumber`, the 17 respawn positions, the 16 plate locations, function signatures |
| `endmap/__init__.msc` | Script bindings plus the (commented-out) summon dump for the 631 cube entities |
| `endmap/checkpointPressurePlate.msc`, `returnToCP.msc`, `kill.msc` | Checkpoint flow |
| `endmap/endPortalFrame.msc`, `# endPortalFrameInteract.msc` | Portal-frame set piece |
| `endmap/respawnAnchor.msc` | Two-second particle/sound sequence for the anchor |
| `endmap/theCubeShellAnimation.msc`, `theCubeShellParticles.msc` | Shell-by-shell cube assembly |
| `endmap/theCubeAnimation.msc`, `finalAnimation.msc` | The pig-ride cutscenes |

## Notes

- `__init__.msc` (631 summon commands) and `theCubeAnimation.msc` (384 particle-line commands) are mostly generated command dumps; the hand-written logic in each is a few dozen lines.
- The summon lines in `__init__.msc` are commented out because they were run once to create the entities, which persist in the world.
