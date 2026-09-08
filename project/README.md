# project

A port of a BDEngine display-entity animation to MSC. [BDEngine](https://block-display.com) is a browser editor for Minecraft block/item display models; it exports an animation as a vanilla datapack in which each frame is a function that rewrites every part's transformation matrix. This namespace reproduces that datapack's model (216 parts riding a root entity, plus a camera entity) and its 283-frame animation on the Minr server, where datapack scheduling is not available.

## How it works

- **Model.** `createModel(player)` summons the root and camera `block_display`s at the player's feet and 216 `item_display` passengers (player heads with embedded textures), tagged `project_0`..`project_215`. `deleteModel` kills the tree.
- **Frames.** `keyframeN()` is the verbatim transform dump from the export's `keyframe_N.mcfunction`: one camera teleport and one `data merge entity` per part, each carrying a full 4x4 transformation matrix. Rendering and control flow are separated: a keyframe only renders.
- **Control flow translation** (`project.nms` header). The datapack advanced frames with `schedule function ... 0.1s` chains and kept pause/loop state in entity tags. MSC has no `schedule`, so playback is a loop with `@delay 2` inside it (`runFrame.msc`) and the state lives in namespace globals `playing`, `paused`, `looping`, `currentFrame`. A first version recursed (`runFrame(frame + 1)` after each delay); because `@delay` does not unwind the call stack this hit MSC's recursion limit near frame 97, so frames are advanced by iteration only. MSC caps `list::range` at 1000, so looping playback uses two nested counters.
- **Frame dispatch.** MSC cannot call a function by computed name, so `playFrame(frame)` is a hand-coded 283-branch `@if` chain.
- **Camera viewer.** The datapack tracked the spectating player with a scoreboard objective and an entity tag. The port uses per-player (`relative`) state, `savedGameMode` and `watchingCam`, plus a global `camClient` naming the single active viewer. `playAnimCam` records the gamemode, switches the player to spectator on the camera entity, and `stopAnim` restores it.

## Layout

| Path | Role |
|---|---|
| `project.nms` | Namespace: animation and camera state, all function signatures |
| `project/createModel.msc`, `deleteModel.msc` | Model setup and teardown (the summon commands are a generated dump) |
| `project/playAnim.msc`, `playAnimLoop.msc`, `playAnimCam.msc`, `playAnimLoopCam.msc` | Entry points |
| `project/pause.msc`, `resume.msc`, `stopAnim.msc`, `stopSound.msc` | Playback control |
| `project/start.msc`, `runFrame.msc`, `playFrame.msc` | The frame loop and dispatch |
| `project/keyframe0.msc` | Sample keyframe body |

## Running it

Call `createModel(Player("Name"))` once, then one of `playAnim()`, `playAnimLoop()`, `playAnimCam(Player("Name"))` or `playAnimLoopCam(Player("Name"))`. `@delay 2` per frame gives 10 frames per second, matching the export's 0.1 s schedule.

## Notes

- `project/keyframe1.msc` through `keyframe282.msc` (about 24 MB of generated transform dumps, ~84 KB each) are gitignored. Only `keyframe0.msc` is kept as a sample of the format; the rest are regenerated from the BDEngine export.
- `checkLoop.msc` is retained from the original structure but is no longer called; the loop/stop decision lives inside `runFrame`.
