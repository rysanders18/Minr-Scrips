# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Scope

This document covers the **rychess** chess engine and visual board: `rychess.nms` (namespace declaration) and the `rychess/` directory of `.msc` script files. Other top-level scripts in the repo (Cookie, endmap, lendfishing, nfa, Harha, Chess) are unrelated.

## Language & runtime

This is **MSC** — a server-side scripting language for the Minr Minecraft server, not a standard programming language. Build/lint/test commands as you'd find in a typical project do not exist; scripts are uploaded to a Minr server and invoked there. See `MSC_FORMAT_DOCUMENTATION.md` for language details.

Key MSC conventions used throughout:
- `@using rychess` + `@fast` at the top of every function file
- `@define` declares a variable for the first time; `@var` reassigns or calls a void function
- `@bypass /<minecraft command>` runs raw vanilla commands
- `{{expr}}` templates Minecraft commands at script-emit time (used heavily in `__init__.msc` for the `m` board-scale factor and per-entity tag suffixes)
- `relative Int foo` in `.nms` files = per-player state (keyed by `Player`); access as `foo[player]`
- One function per file. Filename = function name. Function signatures live in `rychess.nms`.

## Repository layout

- `rychess.nms` — **the namespace manifesto.** Declares per-player state variables, namespace constants (PSTs, board textures, piece base-translation tables), and the signature of every public function. Adding/removing a function requires editing this file. Order is loosely: variables → constants → function signatures grouped by phase.
- `rychess/<name>.msc` — implementation of one function. The first comment block in each file is its docstring; rely on these — they describe non-obvious invariants (e.g. tag mirroring, variant rules, why a particular Minecraft command form was chosen).
- `rychess/__init__.msc` — runs once to summon the world. Kills any existing rychess entities (lines 1–3), defines the board scale `@define Float m`, then issues 9 `@bypass /summon block_display` commands at world coords `-9133 31 9681`, each carrying many block_display passengers. Every passenger is tagged and its `transformation` matrix is templated with `{{value*m}}f` so the whole board can be uniformly scaled by editing `m`.

## Big-picture architecture

The project is two intertwined systems sharing per-player state:

### 1. Pure chess engine (no Minecraft dependencies)

State (all `relative`, per-player): `board[64]`, `sideToMove`, `castling` (bitmask 1=WK, 2=WQ, 4=BK, 8=BQ), `epSquare`, `halfmoveClock`, `fullmove`, `undoStack[1000]`, `undoPly`.

Pieces: `0=empty`, `1–6 = white P/N/B/R/Q/K`, `7–12 = black P/N/B/R/Q/K`. Squares: `0=a1, 7=h1, 56=a8, 63=h8` (`file=sq%8, rank=sq/8`).

**Moves are packed into a single Int** (`moveEncode.msc`): `from + to*64 + promo*4096 + flags*32768`. MSC has no bitwise operators, so encode/decode use multiplication and modulo. Flags: `0=quiet, 1=capture, 2=double-push, 3=ep-capture, 4=castle-K, 5=castle-Q`.

Move generation pipeline: `gen<Piece>Moves` (pseudo-legal) → `genAllPseudoLegal` → `genLegalMoves` (filters via make/unmake + `inCheck`). King castling generation in `genKingMoves.msc` already filters check-through-check because the legality post-filter only catches the landing square.

Search: `searchInner.msc` is fail-soft negamax alpha-beta, calls `evaluate.msc` at depth 0 (material + Michniewski PSTs from `rychess.nms`, side-to-move-relative). `chooseMove` is the entry point and yields one tick (`@delay 1`) between every root move so the search doesn't monopolize the tick thread.

**Variant rules** (these differ from standard chess — see `genPawnMoves.msc`, `evaluate.msc`):
- Pawns auto-promote to a queen on the back rank. The move's `promo` field (bit 12-14, value 4 = queen) is set by `genPawnMoves` on any forward push, double push, diagonal capture, or ep-capture whose destination is the back rank. `makeMove` reads it to swap the piece on the board; `unmakeMove` reads it to restore the pawn; `applyMoveVisually` reads it to call `recolorPiece` (white_concrete_powder → light_blue_concrete_powder). Pre-promotion piece type is not stored on `undoStack` — the promo flag plus the queen's color is enough to reconstruct it.
- Pawns may move **or** capture one square left/right.
- Pawns may double-push from **any** rank, not just rank 2/7.
- Pawn attacks in `isSquareAttacked` include the immediate left/right squares.
- Evaluation gives pawns +3cp per empty adjacent file (rewards lateral mobility).

### 2. Visual board (Minecraft block_display entities)

The world has two entity families, both summoned by `__init__.msc`:

**Pieces.** Each of the 32 starting pieces is a *cluster* of block_display passengers, all tagged `rychess<rankTag><fileTag><NN>` where `NN` is the entity-within-piece index (`00`, `01`, ...). Piece-identity codes use `pieceCode = rankTag*10 + fileTag`:
- rankTag 0 = white back rank (spawnRank 0)
- rankTag 1 = white pawns    (spawnRank 1)
- rankTag 2 = black pawns    (spawnRank 6)
- rankTag 3 = black back rank (spawnRank 7)

So `04` = white king (e1), `14` = white pawn that started on e2, `37` = black rook on h8.

**Board squares.** 64 interaction entities tagged `rychessboard<R><F>` are the click targets and texture surfaces for highlights. **The `R` digit is `7 - rank`, mirrored along the rank axis** — see `highlightMoves.msc` and `clearHighlights.msc`. The world position is correct; only the tag digit is flipped.

### How the two systems connect

- `pieceCodeAt[player]` is a 64-element array tracking which `pieceCode` currently sits on each square (`-1` = empty). It's updated by `applyMoveVisually` in lockstep with `board[player]` after every human/engine move.
- `applyMoveVisually` is called **only** from `play`/`engineMove`/`interactEntity`, NEVER from inside the search. The search uses `makeMove`/`unmakeMove` thousands of times — animating those would flicker the world.
- `highlightMoves`/`clearHighlights` re-skin the 64 board entities by editing their `item.components."minecraft:profile"` to one of four base64 player-head textures defined in `rychess.nms` (light/dark/movable/capturable).

### The transformation-matrix subtlety (critical)

Each piece-passenger entity has a `transformation` 4×4 row-major matrix carrying its rotation, scale, and translation. To move a piece, **`applyTransform.msc` writes ONLY `transformation.translation`** via `/data modify entity ... transformation.translation set value [x,y,z]`. This:
1. Triggers Minecraft's interpolation system (the smooth slide), and
2. Preserves rotation and scale, leaving each entity's within-piece offset and shape intact.

The older `transformation:{translation:[...]}` compound form decomposes the matrix and resets rotation/scale to defaults — which is why every entity used to collapse to the same point. Don't reintroduce that form.

`applyTransform` reads each entity's spawn-time base translation triple `(m03, m13, m23)` from `pieceXXBase` (32 namespace-constant arrays in `rychess.nms`, auto-extracted from `__init__.msc`'s transformation arrays) and adds the spawn-to-target delta. `lookupPieceBase` is a hand-coded `@if` chain over the 32 codes because MSC can't dynamically resolve a constant by computed name.

`movePieceVisually` = `applyTransform` with `yOffset=0`. `sinkPiece` = `applyTransform` with `yOffset=-0.3F` (drops captured pieces below the slab; entities stay alive so `newGame` can resurrect them).

### Board geometry

`squareSize = 0.18655F` per square. Files a→h go +X, ranks 1→8 go **−Z**. The summon anchor is the piece-cluster origin; transformations are in that local space, so scaling `m` in `__init__.msc` scales the whole board around the anchor without moving it.

## When editing

- Adding a function requires editing **both** `rychess.nms` (declare signature in the appropriate phase section) **and** creating `rychess/<name>.msc`. Forgetting the `.nms` declaration is the most common breakage.
- The first comment block of each `.msc` file is the canonical spec — when changing a function, update the doc comment in the same edit. Several files document non-obvious choices (tag mirroring, why `.translation` not `[3]/[7]/[11]`, variant rule deltas) that aren't deducible from the code.
- Tests are MSC functions, not a runner: `testMoveCodec`, `testSquareNames`, `testStartPosDisplay`, `testPlayerKeyedArray`, `testRecursion`, `testReturnInLoop`, `testGenStartPos`, `testMakeUnmake`, `testPerft`, `testEngineMove`. They `@player`-print results when invoked in-game.
- `__init__.msc` is regenerated/edited as a whole; it's the world-spawn source of truth. The `pieceXXBase` arrays in `rychess.nms` are derived from its transformation arrays, so if you re-export entity geometry, both must move together.
- The board can be uniformly resized by editing the single `@define Float m` in `__init__.msc` — every transformation cell is templated `{{value*m}}f`, including off-diagonal rotation×scale entries (multiplying the full 3×3 by `m` preserves rotation while scaling magnitude by `m`).
