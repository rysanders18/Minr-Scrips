# rychess engine — recreation & shortest-mate search

A faithful JavaScript port of the rychess MSC chess engine, plus an exhaustive
search for the shortest possible checkmate against it. Because the engine has
**zero randomness**, it plays the exact same move in the exact same position
every time — so the game tree only branches on the human's moves, and "shortest
forced mate" = shortest mate, full stop.

## Files

| File | Purpose |
|---|---|
| `engine.js` | 1:1 port of the MSC engine (movegen, make/unmake, eval, search) |
| `selftest.js` | validation: perft, make/unmake round-trip, eval consistency, sample games |
| `mate.js` | iterative-deepening exhaustive search for the shortest mate |

Run: `node selftest.js`, `node mate.js [maxHumanMoves] [humanColor]`

---

## How the engine works, layer by layer

### 1. Board & move representation

- `board[64]`: 0 = empty, 1–6 = white P N B R Q K, 7–12 = black. Square 0 = a1,
  7 = h1, 56 = a8 (file = sq % 8, rank = sq / 8).
- A move is one packed Int (MSC has no bitwise ops, so it's mul/mod arithmetic):
  `move = from + to·64 + promo·4096 + flags·32768`
  with flags 0=quiet, 1=capture, 2=double-push, 3=en-passant, 4=O-O, 5=O-O-O.
- State beyond the board: `sideToMove`, `castling` bitmask (1=WK 2=WQ 4=BK 8=BQ),
  `epSquare`, `halfmoveClock`, and `runningScore` — an incrementally maintained
  material+PST total (white's point of view) updated by every makeMove/unmakeMove
  via `pieceContrib()` deltas and restored from the undo stack on unmake.

### 2. Variant rules (this is NOT standard chess)

From `genPawnMoves.msc` / `isSquareAttacked.msc`:

1. **Pawns may move OR capture one square sideways** (left/right). Lateral
   moves never promote. Correspondingly, every pawn *attacks* its two lateral
   neighbours, which matters for check detection and castling legality.
2. **Pawns may double-push from ANY rank**, not just their start rank. Every
   double push sets the en-passant square behind it — so en-passant can happen
   mid-board, and (delightfully) a double push *onto the back rank* promotes
   and can then be "en-passant captured", removing the fresh queen.
3. **Auto-queen**: any pawn move landing on the back rank promotes to a queen
   (promo field = 4); there is no under-promotion.

### 3. Move generation

`genAllPseudoLegal` scans squares 0→63 and dispatches per piece. **Generation
order is fixed and matters** (it's the tie-break of the whole engine):

- Pawn: push, double-push, capture-left, capture-right, ep-left, ep-right,
  lateral-left, lateral-right.
- Knight/King: fixed 8-offset tables. Sliders: 4 rays in fixed order, queen =
  rook rays then bishop rays.
- Castling is generated pre-filtered (not-in-check, not-through-check) because
  the generic legality filter only checks the landing square.

`genLegalMoves` = pseudo-legal, then make → "is my king attacked?" → unmake.

### 4. Evaluation (`evaluate.msc`)

O(1): return `runningScore` (material 100/320/330/500/900/20000 + Michniewski
piece-square tables, white POV), negated when black is to move. The old +3cp
lateral-pawn-mobility bonus was dropped when eval went incremental.

### 5. Search — the exact decision procedure

The engine's whole personality comes from three functions:

**`chooseMove` (root, depth 2 total):**
1. `genOrderedLegalMoves` — actually **pseudo-legal** moves, sorted best-first:
   captures get `10000 + 100·value(victim) − value(attacker)` (MVV/LVA, always
   above quiets; ep counts as a pawn victim), quiet moves get the **destination
   square's PST value** for the moving piece. Sort is stable: descending score,
   ties keep generation order.
2. Walk that list. Per move: make it; if own king is attacked, skip (doesn't
   count toward the cap); otherwise score it with `−searchInner(depth 1)`.
   **Cap: only the first 20 legal moves are searched.**
3. Keep the best score; ties broken by **strict `>`** — the *earliest* move in
   the ordering wins. This plus the fixed generation order is why the engine is
   perfectly deterministic.

**`searchInner` (fail-soft negamax alpha-beta):**
- depth 0 → static eval. No legal-move filter — it searches **pseudo-legal**
  moves, relying on "opponent captures my king (worth 20000)" to punish
  illegal lines.
- **Cap: only the top 5 ordered moves per node.** This is the engine's big
  tactical blind spot: any reply ranked 6th or lower by the ordering is
  invisible to it.
- At depth 1 the leaves call `qsearch` seeded with the just-made move's
  destination square.

**`qsearch` (recapture-only quiescence):**
- If in check: full legal evasion search (returns −100000 on mate).
- Otherwise stand-pat eval, then extend **only captures that land on the one
  recapture square**, recursively, capped at 8 plies. Multi-square tactics are
  out of scope by design.

Net effect: the engine sees its move + the 5 "most obvious" replies + capture
chains on a single square. It never misses a hanging capture, but a **quiet**
threat that doesn't rank in the top 5 replies simply does not exist for it.

### 6. Game flow

In-world play: `newGame` (human = White, `playerColor` defaults to 0) →
human clicks a piece + destination (`interactEntity` matches against
`genLegalMoves`) → `engineMove` runs `chooseMove` for Black and commits it via
`performEngineMove` (all the mannequin theater — delays, head-turns, taunts —
is cosmetic; the move is decided before any of it). Game ends on checkmate,
stalemate, or the 50-move rule (`checkGameOver`).

---

## Port fidelity

Everything that influences move choice is replicated exactly: generation order,
ordering scores and stable sort, both branching caps (20 root / 5 inner), the
legality-filter quirks (a missing king counts as "legal"), fail-soft alpha-beta
windows, qsearch's flags==1-only recapture filter, the incremental eval, and
makeMove's castling-rights edge cases. Validation (`selftest.js`):

- perft(1) = 20, perft(2) = 400 — matches `testPerft.msc` expectations.
  (Variant perft(3) = 10314; the "8902" in the test file is the standard-chess
  value from before the variant rules — laterals first appear at ply 3.)
- make/unmake round-trips restore the full state bit-for-bit over random
  playouts, and `runningScore` never drifts from a from-scratch recount.
- Found mate lines are re-verified by an independent replay that re-derives
  every engine move with a fresh `chooseMove` call.

## Shortest-mate search (`mate.js`)

Iterative deepening on the number of human moves N = 1, 2, 3, …; at each N an
exhaustive DFS tries every legal human move, computes the engine's unique
deterministic reply (memoized by position), and recurses. Transpositions that
were proven mate-free with ≥ the remaining budget are pruned. The first N with
a mate is provably the minimum.

Results (human = White, engine = Black — the live configuration):

- N = 1–5: **no mate exists**, exhaustively proven (≈3.3M positions checked).
- N = 6: **mate found** (95s total, ~5.2M human nodes, ~205k unique engine
  replies computed):

```
1. Nb1-c3   d7d5      (engine grabs the center)
2. d2-d4    e7e5      (engine offers the center pawn trade)
3. Nc3xd5   Qd8xd5    (engine recaptures with the queen — as designed)
4. g2-g3    Qd5xh1    (greed: the queen dives for the undefended rook)
5. d4-d6!!  Qh1xg1    (variant double-push from rank 4; queen keeps eating)
6. d6-d8=Q#            (variant double-push ONTO the back rank, auto-queen,
                        protected by Qd1 down the open d-file — checkmate)
```

Final position (uppercase = White):

```
8  r n b Q k b n r
7  p p p . . p p p
6  . . . . . . . .
5  . . . . p . . .
4  . . . . . . . .
3  . . . . . . P .
2  P P P . P P . P
1  R . B Q K B q .
   a b c d e f g h
```

Why the engine walks into it: its search is depth 2 with a top-5 reply cap and
recapture-only quiescence. `4...Qxh1` and `5...Qxg1` are the highest-MVV/LVA
moves on the board, so they dominate its 2-ply horizon; the mating resource
`d6-d8=Q` is a *quiet* move (no capture) whose threat only materializes a ply
past its horizon. The double-push-from-any-rank rule is what makes the pawn
sprint d4→d6→d8 fast enough to outrun the queen's shopping spree — in standard
chess this mate would be impossible.

The verify pass replays the line from scratch, re-deriving every engine move
with an independent `chooseMove` call, and confirms the final position is
checkmate with the engine to move.

### Human = Black (engine = White, `node mate.js 7 1`)

Also mate in exactly **6 human moves** (none in ≤ 5, exhaustively proven;
~5.5M positions, 99s). The engine opens 1.d4 from the start position:

```
1. d4    a6      2. e4    c5     3. dxc5  a6-b6!  (lateral pawn move)
4. cxb6  d5      5. Qxd5  Bg4    6. Qxb7  Qd8-d1#
```

Black's queen mates on d1 down the opened d-file, protected by the g4 bishop;
the white king can neither take (Bg4 covers d1) nor flee (d2/e2 covered, f1
occupied). Same engine pathology: `5.Qxd5` and `6.Qxb7` are the greedy
top-of-ordering captures, and the quiet `Qd1` sits one ply past its horizon.

---

## Elo evaluation

Two independent measurements (files: `opponents.js`, `opponents_factory.js`,
`tourney.js`, `engine_standard.js`, `uci_match.js`):

**1. Variant-rules ladder** (`node tourney.js 50`): gauntlet vs reference
opponents sharing the exact same eval, so the gaps measure search quality.
100 games per pairing, paired random openings, colors swapped; adjudication =
mate / stalemate / 50-move / threefold / 400-ply.

| opponent | rychess result | score | Elo diff |
|---|---|---|---|
| random legal mover | 57W 43D 0L | 78.5% | **+225** [179, 280] |
| greedy 1-ply | 23W 77D 0L | 61.5% | **+81** [52, 112] |
| full-width depth-2 + real qsearch | 2W 42D 56L | 23.0% | **−210** [−267, −162] |
| full-width depth-3 | 0W 21D 79L | 10.5% | **−372** [−463, −308] |
| full-width depth-4 (30 games) | 0W 3D 27L | 5.0% | **−512** [−1200, −375] |

**2. Standard-chess anchor** (`node uci_match.js 1320 25 …`): the engine's
search transplanted onto standard rules (validated: perft 1–5 match the
canonical values exactly), 50 games vs Stockfish 17.1 at its minimum
calibrated strength (UCI_LimitStrength, UCI_Elo 1320, movetime 60ms):

| player | vs SF-1320 | implied Elo |
|---|---|---|
| rychess | 3W 11D 36L → 17.0% | **≈ 1045** [915, 1130] |
| fw2 reference | 26W 4D 20L → 56.0% | ≈ 1362 [1270, 1461] |

Cross-check: SF scale puts fw2 − rychess at ~317; the direct variant match
measured ~210 (compressed by rychess's extreme draw-proneness). The direct
anchor is the better number.

**Verdict: ≈ 1000–1100 Elo** (UCI_Elo/CCRL-like scale), i.e. a casual club
or scholastic player. Systematic caveats: Stockfish's limited-strength model
is itself approximate (±~100), the number describes standard-rules play
(variant strength should be similar, and in practice the bot plays the
variant against humans who *don't know the variant rules* — worth a few
dozen practical Elo in its favor), and threefold repetition was adjudicated
although the in-game `checkGameOver` only implements the 50-move rule.

Style profile:
- **Never hangs a piece to a one-move capture and instantly punishes hung
  material** — captures always top its move ordering, so its 2-ply window has
  100% coverage of capture tactics. This is why it feels solid to casual play.
- **Sensible development**: PST-guided ordering/eval produces knights-out,
  center pawns, castling.
- **Blind to quiet threats** ranked below its top-5 reply cap (the mate-in-6
  exploit), and blind to any 3-ply tactic (its horizon is its move + your
  reply + single-square recaptures).
- **Cannot convert won positions**: mate scores carry no distance bonus, so
  mate-in-1 ties with mate-in-5 and the tie-break picks whatever sorts first;
  it drew 43/100 games against a *random mover* (up a full army, shuffling
  until the 50-move rule). Its practical rating against patient opponents is
  lower than its tactics deserve.
- **No repetition awareness, no opening book, fixed depth 2.**
