# j100

A 100-jump parkour map for the Minr server (world Epsilon) with per-player progress tracking, and a Python pipeline that turns the collected play data into a difficulty ranking. The jumps sit in a 10x10 grid of 18-block cells; the MSC side records falls, retries, time on the clock and a self-reported 1-100 rating for every jump and every player. `rank_jumps.py` fits a latent difficulty per jump from those signals while correctly handling players who have not beaten everything, and `make_report.py` renders the result as a self-contained HTML page.

## How it works

**Level detection.** No script is told which jump it belongs to. `clickBlock.msc`, `fallRegion.msc` and `goldBlock.msc` all derive `level = i*10 + j` from the player's X/Z cell, so one script serves all 100 jumps.

**Events.** Touching the gold block at the top of a jump (`goldBlock.msc`) marks it beaten, banks the winning attempt's time, and opens the rating prompt (`gatherOpinion.msc`). Landing in the catch region underneath (`fallRegion.msc`) counts a fall and teleports the player back to the jump's start. The hotbar (`hotbarFunction.msc`) carries a stick that teleports to the current jump's start (counted in `levelTeleports`), a gold ingot that stores a custom start position (player must be on the ground and stationary for four ticks), redstone to clear it, and a barrier to leave. The chat menu is `showProgress`, `nextJump`, `selectJump` and `resetProgress`.

**Timing** (`touchLevel.msc`). Every event that proves the player is still on a jump moves a per-player clock; the gap since the previous event is banked into `levelTimes[previous]`. Gaps longer than `idleCapMs` (180 s) are clamped rather than discarded, so a slow attempt still counts but an AFK does not add hours. Falls, teleports and time are only recorded for jumps the player has not yet beaten: the statistics describe first clears.

**Deliberate design choices documented in the scripts:** `nextJump` picks a random unbeaten jump rather than the lowest-numbered one so that warm-up is spread evenly across the map instead of making early jumps look harder; `gatherOpinion` and `selectJump` validate chat input by comparing the reply against `String(n)` for every candidate `n`, because MSC has no safe string-to-int parse.

**Difficulty model** (`rank_jumps.py`). `j100/Data.txt` is a hand-assembled dump, one block per player per statistic (`# <Player> Falls|Teleports|Times|Ratings|Levels Completed`, 100 values each). The analysis is censoring-aware: only jumps a player has beaten are used, because an unbeaten jump's fall count is a lower bound and an unattempted jump has 0 falls, which would read as trivially easy. A missing "Levels Completed" block means the player beat all 100. Each signal is modelled as `signal[p][j] = d_j + o_p + noise`, a per-jump difficulty plus a per-player offset, and `fit_additive()` solves it by alternating least squares over the observed cells only (two-way ANOVA with missing data). Simply centring each player's scores would fail once progress is partial: a player who beat only their 30 easiest jumps has a low mean, and centring would push everything they touched upward. Signals are transformed before fitting: `log(falls + teleports + 1)` (attempts are geometric, so log attempts is the additive scale and it tames a 1734-fall outlier), log seconds, and log of the rating (players use the 1-100 scale multiplicatively). Fitted difficulties are z-scored and combined with weights 0.5 / 0.3 / 0.2; time is weighted lowest because the data was gathered under an older timing rule that under-recorded it. The script also prints a `slotOfRank` / `rankOfSlot` permutation pair for re-ordering the map in `j100.nms` without moving anyone's progress (not yet adopted there).

**Interact-script generator** (`gen_interact_imports.py`). Every clickable block in the map needs its own interact script registered. The generator replays the `/fill` and `/setblock` commands from `setup1.msc` and `setup2.msc` to get each coordinate's final block, drops air, light and plain glass, decomposes the rest into maximal cuboids, and emits `interactImport1..7.msc`: nested `@for` loops that remove and re-create the script on each block, chained part to part. Parts are capped at 2100 lines / 200 KB to fit the paste-site import limit, and no `@fast` is used so the work spreads over ticks.

## Layout

| File | Purpose |
|---|---|
| `j100.nms` | Per-player arrays (falls, teleports, times, ratings, completion, custom positions), default start positions, gold block coordinates, signatures |
| `j100/goldBlock.msc`, `fallRegion.msc`, `clickBlock.msc`, `touchLevel.msc` | Event handlers and the play clock |
| `j100/showProgress.msc`, `nextJump.msc`, `selectJump.msc`, `resetProgress.msc`, `gatherOpinion.msc` | Chat menu and rating prompt |
| `j100/hotbarFunction.msc` | Tool items |
| `j100/__init__.msc` | Registers the gold-block scripts; `# fallRegion.msc` pushes the `levelPositions` constant with `/var set` |
| `j100/Data.txt` | Collected player statistics (input to the analysis) |
| `rank_jumps.py`, `make_report.py`, `gen_interact_imports.py` | Analysis, report, generator |

Generated files are excluded from git and rebuilt by the scripts: `setup1.msc` / `setup2.msc` (world fill dumps), `j100/interactImport*.msc`, `scratch_j100.json`, `j100_ranking.html`.

## Running it

Python 3 with `numpy` and `scipy`:

```
python j100/rank_jumps.py [path/to/Data.txt] [--json out.json]   # console ranking; default input is j100/j100/Data.txt
python j100/make_report.py [out.html]                              # writes j100_ranking.html next to the script
cd j100 && python gen_interact_imports.py                          # needs setup1.msc and setup2.msc in the cwd
```

In-game, `interactImport1` is run once by hand and chains through part 7.

## Notes and limitations

- Times in `Data.txt` collected before `touchLevel.msc` existed are unreliable (the old rule only timed between two falls under 60 s apart), which is why the time weight is low; the docstring says to raise it once enough data exists under the new rule.
- Player state is keyed by physical grid slot, not by displayed jump number, so the map can be re-ordered by swapping permutation constants.
- Coordinates, cell size and the Epsilon world name are hardcoded in every handler.
