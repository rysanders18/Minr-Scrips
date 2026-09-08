# Minimal patch for the live entity_ai namespace

Use these instead of the full rebuild when the ORIGINAL namespace is still
installed. Replace only these two methods; leave everything else alone.

| Method | File | Change |
|---|---|---|
| `EntityPose.string()` | `EntityPose/string.msc` | line 9: `Rotation:[Xf]` -> `Rotation:[Xf,0.0f]` |
| `EntityAI.rotate()` | `EntityAI/rotate.msc` | lines 23 and 28: `{Rotation:[Xf]}` -> `{Rotation:[Xf,0.0f]}` |

Everything else in both files is verbatim from the in-game export (apart from
the two FIX comments).

Why: since Minecraft 1.21.6 entity `Rotation` NBT is decoded with a
fixed-size-2 codec. The one-element list the library wrote fails to decode and
the stand falls back to yaw 0 / pitch 0, so rotate() snaps the stand south
instead of turning it, and watch()'s return-to-pose does the same. No other
method writes Rotation with one element (watchSingleTick already wrote two).

Optional follow-ups, NOT needed for this bug, available in the full rebuild
under `../entity_ai/`: number formatting that avoids scientific notation in
SNBT, the walkSingleTick/walkJumpSingleTick argument-count fix (only affects
jumpFoward), and NaN guards in look/watch/steer.
