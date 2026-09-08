# CLAUDE.md

Guidance for Claude Code when working in this repository. The human-facing
overview is [README.md](README.md); each project directory has its own README
with the architecture for that namespace.

## Language & runtime

This is **MSC**, the server-side scripting language of the Minr Minecraft
server, not a standard programming language. There is no local build, lint or
test command; scripts are uploaded to the server and invoked there. See
`MSC_FORMAT_DOCUMENTATION.md` for the language reference.

Conventions used throughout:
- `@using <ns>` + `@fast` at the top of most function files (omit `@fast` on huge build scripts so work spreads across ticks)
- `@define` declares a variable for the first time; `@var` reassigns or calls a void function
- `@bypass /<command>` runs a raw vanilla command; `{{expr}}` templates values into commands
- `relative T foo` in a `.nms` file is per-player state, accessed as `foo[player]`
- One function per file; filename = function name; signatures live in the `.nms`
- `# name.msc` files are standalone in-game scripts (buttons, signs, regions), not namespace functions
- MSC classes exist (`@class` in the `.nms`); constructors are `Class(ArgTypes).msc` inside `<ns>/<Class>/`

## Repository layout

Every namespace is `<ns>.nms` plus `<ns>/<fn>.msc` (some older namespaces keep
the `.nms` at the repo root, e.g. `Cookie.nms`, `lendfishing.nms`). Python
generators sit beside the namespace they serve; general converters are in
`tools/`. `clone-map/` is a git submodule of AK1089's repo. `Harha/` holds
production scripts for a live map and should be left alone unless asked.

Generated build output (setblock/fill dumps, datapacks, pickles, keyframes,
motion capture) is gitignored; never commit it. The generators and the small
registries needed to reproduce a build are what belongs in git.

## When editing

- Adding a function requires editing **both** the `.nms` (declare the signature) **and** creating `<ns>/<name>.msc`. Forgetting the `.nms` declaration is the most common breakage.
- The first comment block of each `.msc` file is the canonical spec. When changing a function, update that comment in the same edit.
- `rychess`: read `rychess/README.md` first. In particular, `applyTransform` must write only `transformation.translation` (the compound form resets rotation and scale), the `pieceXXBase` arrays in `rychess.nms` are derived from `__init__.msc` and must move together, and `applyMoveVisually` is never called from inside the search.
- `slimeMaze`: only the generators, docs and registries are tracked. Large emitted scripts must be chained parts under the ~4k-line paste cap, with a tp and delay before world-mutating commands in each region bucket.
- Tests are MSC functions named `test*` invoked in-game; there is no runner.
