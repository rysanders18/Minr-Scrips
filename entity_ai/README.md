# entity_ai (repaired)

D4rkSly's armor stand animation library (`entity_ai`, v1.4, forum thread
"EntityAI"), rebuilt from the in-game script export so it runs on current
Minecraft versions. The public API is unchanged: construct an `EntityAI`
with the stand and the player, then call actions.

```
@using entity_ai

@define EntityAI ai = EntityAI(entity, player)
@var ai.rotate(90D, 45D)
@var ai.walk(3D, 1D)
@var ai.wave(5)
```

## Layout

```
entity_ai/
  entity_ai.nms                  namespace manifest (constants, helpers, 3 classes)
  entity_ai/
    getEntityIndex.msc           namespace helpers (were missing from the export)
    getRoundDouble.msc
    getWithinDouble.msc
    easeOutQuad.msc
    EntityPose/                  EntityPose(Entity).msc, EntityPose(Entity,Double).msc, methods
    EntityAIHelper/              EntityAIHelper(Entity,Player).msc, per-tick primitives
    EntityAI/                    EntityAI(Entity,Player).msc, EntityAI(Entity,Player,Boolean).msc, actions
```

Constructor files are named `Class(Type,Type).msc`, method files `method.msc`,
matching the `clone-map/syd` and `lendfishing` namespaces in this repo.

## What broke, and the fix

**Rotation NBT.** Every place the library turned the stand wrote a
one-element list: `/data merge entity <uuid> {Rotation:[90f]}`. Before 1.21.6
the missing pitch silently read as 0. Since 1.21.6 entity NBT is decoded
through codecs and `Rotation` must be exactly `[yaw, pitch]`; the one-element
list fails to decode and the game falls back to yaw 0 / pitch 0. Symptom: the
stand snaps to face south instead of rotating, and `watch()`'s return-to-pose
does the same.

- `EntityPose.string()` now emits `Rotation:[yaw f,0.0f]`.
- `EntityAI.rotate()` now merges `{Rotation:[yaw f,0.0f]}`.
- `EntityAIHelper.watchSingleTick()` already wrote two elements; unchanged.

**Number formatting.** Doubles are templated straight into commands, as the
original did. Java may print a tiny value as `4.4E-16`; Minecraft's SNBT
float parser accepts that exponent form, and `walkSingleTick` clamps tiny
teleport offsets to 0 (original behaviour), so no formatting helper is used.

## Other repairs made while rebuilding

- `walkSingleTick` and `walkJumpSingleTick` called `walkAnimationSingleTick`
  with three arguments after v1.4 gave it four (`soundEnabled`). Both now take
  and pass a `soundEnabled` flag; `jumpFoward` passes `this.soundEnabled`.
- `applaud` now honours `soundEnabled` (only `walk` did before).
- `EntityPose` parts are stored as `Vector3` instead of
  `Location(x,y,z,world)`. Same `getX/getY/getZ` accessors, no world needed.
- `moveTo*` ended with `@var this = newPose` then re-setting rotation. That
  relied on reassigning `this` propagating to the caller. Replaced with
  `copyFrom(newPose)`, which copies the six parts and keeps rotation.
- `steer` computed `sqrt` of a negative at the arm limits (NaN merge that
  silently failed each swing). Arm X is clamped to the arc first.
- `look`, `watch`, `rotateToLocation` guard the zero-distance case that
  produced NaN angles.
- `sitGround`'s last keyframe had `setBody(-9.0D, 3-4D, 0.0D)`, which
  evaluates to -1.0. Kept as -1.0 (what shipped); change to `3.4D` if a body
  twist was intended.
- `moveTo(newPose)` delegates to `moveToWithSpeed(newPose, 20)` (same
  duration, now takes the short way round for each angle).

## MSC gotchas found while testing

- A namespace function `String formatFloat(Double)` (`@fast`, `@if/@else`,
  `@return String(rounded)`) always came back as **Void** on the server:
  `Could not assign value of type Void to variable rax of type String`.
  Used inside a `+` chain the same null showed up as
  `WrongMethodTypeException: cannot convert MethodHandle(StringValue,String)String to (Object)Object`.
  Root cause not identified (every construct in it is used successfully
  elsewhere in this repo). The helper was removed rather than debugged;
  the server may still hold the stale function, which is harmless.
- `getRoundDouble` (debug output only) is written the same way and is
  untested. If debug prints show `null`, replace its `Double(math::floor(..))`
  rounding with plain templating.

## Timing note

Animation loops are deliberately **not** `@fast`, and their loop bodies keep
the original line structure, because the library's speeds were tuned against
the server's line-per-tick execution. Pure helpers, getters, setters,
`string()` and `copyFrom()` are `@fast`. If an action runs noticeably faster
or slower than it used to, that is where to look.

## Importing

1. Create the namespace from `entity_ai.nms`.
2. Import each `.msc` under `entity_ai/entity_ai/` into the matching class
   (`EntityPose`, `EntityAIHelper`, `EntityAI`) or the namespace root.
3. Smoke test in-game with a stand and yourself as the player, in this order:
   `rotate(90D, 45D)` (the main fix), `watch(5)`, `look(5)`, `wave(3)`,
   `applaud(3)`, `walk(2D, 1D)`, `sitGround()` then `stand()`.

Things this repair could not verify without the server and that would show up
as import errors: overloaded constructors (two `EntityAI(...)` and two
`EntityPose(...)` files - the original library shipped both, so this should be
fine), and `@using entity_ai` inside constructor files (remove it if the
importer objects). If the namespace name must differ from `entity_ai`,
find-and-replace `entity_ai` across the folder.
