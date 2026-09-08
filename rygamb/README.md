# rygamb

A three-reel slot machine for the Minr server. The reels are the three item slots of a container block, updated with `/item replace` each animation frame; a button press starts a spin. The outcome of every spin is decided before the reels start moving, which lets the machine deliberately produce near-misses (two jackpot symbols, then a miss) with a tuned frequency, while the payout is still read honestly from the symbols that finally land.

## How it works

The namespace is split into a small logic core and a set of presentation functions.

**Logic.**
- `rollResult.msc` makes one weighted roll out of 1000 and picks a tier from cumulative thresholds: jackpot (`< 15`, a triple of one of `jackpotSymbols`), minor triple (`< 70`, a triple of one of `commonSymbols`), near-miss (`< 150`, `teaseSymbol, teaseSymbol, other`), pair (`< 300`, `X, X, other`), or nothing. It stores the result in the per-player `target1..3`. The whole house edge lives in these thresholds.
- `otherThan.msc` returns a random symbol different from its argument, so a pair or near-miss can never accidentally complete a triple. In the "nothing" tier reel 2 is forced to differ from reel 1 for the same reason.
- `resolveOutcome.msc` classifies the final three symbols independently of how they were chosen: `100 + symbol` for a triple, `1` for a pair, `0` otherwise. Because it reads the symbols rather than the tier, an incidental pair in the "nothing" tier is still paid as a pair.
- `applyOutcome.msc` maps outcomes to rewards and calls the matching effect function. Each jackpot symbol has its own branch so different prizes can be attached.

**Presentation.**
- `spin.msc` runs the reel animation over 24 frames. Every reel shows a random face until its lock frame (10, 16, 22), when it snaps to its predetermined target with a stop effect. Frame delay increases as reels lock, and when the first two reels match the final reel crawls at a longer delay. That slowdown fires for real triples and engineered near-misses alike, since at that moment the animation "does not know" which it is.
- `updateSlots.msc` writes the three faces into the container.
- `fxSpinTick`, `fxReelStop` (pitch rises per reel), `fxWin`, `fxJackpot`, `fxLose` are sound and particle hooks, intentionally placeholder-level.

**Concurrency.** The animation uses `@delay` inside a loop, which yields the server tick each frame. A per-player `relative Boolean spinning` lock in `pressButton.msc` rejects presses while that player's spin is running.

## Layout

| File | Role |
| --- | --- |
| `rygamb.nms` | Symbol list (index is the symbol id), jackpot/common/tease symbol sets, per-player spin state, signatures. |
| `rygamb/pressButton.msc` | Entry point bound to the button. |
| `rygamb/spin.msc` | Reel animation and sequencing. |
| `rygamb/rollResult.msc`, `otherThan.msc`, `resolveOutcome.msc`, `applyOutcome.msc` | Outcome logic and payout. |
| `rygamb/updateSlots.msc` | Writes reel faces into the container block. |
| `rygamb/fx*.msc` | Sound and particle effects. |

## Running it

Bind `rygamb::pressButton(Block, Player)` to an interact script on the button, where the `Block` argument is the container block that displays the reels.

## Notes and limitations

- Rewards in `applyOutcome.msc` are marked as placeholders; no economy calls are wired up.
- Tier thresholds and lock frames are the tunables; symbol ids index `itemList`, so reordering that list changes which symbols are jackpots.
