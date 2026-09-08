# Cookie clicker

An incremental "cookie clicker" secret built in MSC for the Minr server's Theta world. Players click a floating cookie to earn cookies, spend them on seven upgrade ladders, and finish by buying a 100,000,000-cookie completion button. Five identical rooms spaced 20 blocks apart on the X axis let five players play at once; all progress is per-player. `cookie_opt.py` is a small analytic optimiser that computes the fastest upgrade order under the game's actual rules.

## How it works

**Click loop** (`# Cookie Item Script V2.msc`, bound to the cookie's interaction entity). A click lands only if `cookieCooldown` ms have passed since the last landed click; otherwise it plays a "cooldown" particle and returns. A landed click adds `cookieMultiplier` cookies (times `milkMultiplier` while milk is active), records the running total into a 100-entry ring buffer (`cookieLog` / `cookieLogTimes`) that `cookieTextUpdate.msc` uses to compute cookies-per-second over a 10-second window, and rolls for a golden cookie with probability `1/goldenCookieChance`. A golden spawn picks one of 14 fixed slots around the main cookie; if the slot is occupied the spawn is lost. Each spawn is a diamond cookie with probability `1/diamondCookieChance`. `goldenCookieFunction.msc` handles clicks on those item displays and pays `20 x multiplier` (golden) or `200 x multiplier` (diamond). `checkIfNewUpgrade.msc` compares the pre- and post-click balance against the next price on every ladder and draws a particle line from the cookie to any button that just became affordable.

**Upgrade ladders** are hardcoded price/value arrays in `Cookie.nms` and consumed by the `# _*.msc` button scripts:

| Ladder | Stages | Effect |
|---|---|---|
| Cooldown | 11 | 1000 ms down to 50 ms between landed clicks |
| Multiplier | 500 | cookies per click x2 ... x501; price `10 + 5*i*(i+1)` |
| Golden chance | 16 | spawn odds 1/50 down to 1/2 |
| Diamond chance | 13 | diamond odds 1/500 down to 1/3 |
| Milk unlock | 1 | 15,000 cookies; reveals the milk button |
| Milk duration | 10 | 5 s up to 20 s of active milk |
| Milk multiplier | 11 | x2 up to x20 on all gains while milk is active |
| Completion | 1 | 100,000,000 cookies (`# _Netherite Unlock Button.msc`) |

**Milk** (`milkActivation.msc`, `milkAnimation.msc`) is a 45-second `@cooldown` ability: it swaps the cookie display for a milk bucket, multiplies every gain for `milkDuration` seconds, then reverts. The duration is spent inside `Harha::delay` because the timing must wait across ticks without blocking the click script.

**Rooms.** `cookieSecretJoin.msc` runs on region entry and hands the player the first of `harhacookie0..4` with nobody inside; `cookieRoomSetup.msc` teleports them in, clears golden-cookie slots, kills stale item displays, and redraws the text displays for that player's state. `# Cookie Reset Button.msc` wipes all per-player state after a typed "yes" confirmation via `@prompt`.

**Optimiser** (`cookie_opt.py`). The model is a closed-form income rate per upgrade state, derived from the scripts:

- A player clicks 20 times per second. Landed main-cookie clicks `m = min(20, 1000/C)`; golden clicks share the same click budget, so the golden click rate `s` solves `s = p*(m + s)` with `p = 1/G`.
- Average value of one golden spawn `V = M*(20*(1 - 1/D) + 200/D)`; base income `R0 = m*M + s*V`.
- With milk unlocked, income is averaged over the 45-second cycle, `T` seconds of it at `K x`.
- Save-up strategy: during downtime the player stops clicking goldens for the last `tau` seconds so up to 14 sit on the board when milk starts, then clicks them at `K x`. Held cookies block re-spawns, so the trade-off has an optimum at `tau = min(45 - T, (14/a) ln K)` where `a` is the spawn success rate; the board fills to `b = 14*(1 - exp(-a*tau/14))` and the bonus is `max(0, b*K*V - a*tau*V)`.

The purchase order is found by beam search (width 600) over sequences of ladder purchases, deduplicating on the seven-tuple upgrade state and scoring each node by projected finish time; a myopic payback-period greedy is run afterwards as a cross-check. `cookie_upgrade_order.txt` is the captured output: 22.8 minutes to 100M with the optimal order.

## Layout

| File | Purpose |
|---|---|
| `Cookie.nms` (repo root) | Ladder tables, per-player state, function signatures |
| `Cookie/# Cookie Item Script V2.msc` | Main click handler |
| `Cookie/goldenCookieFunction.msc` | Golden/diamond cookie click handler |
| `Cookie/# _*.msc`, `_milkButton.msc` | One script per upgrade button |
| `Cookie/milkActivation.msc`, `milkAnimation.msc` | Milk ability and its block animation |
| `Cookie/cookieTextUpdate.msc`, `upgradeTextUpdate.msc` | Text-display refresh (totals, CPS, next prices) |
| `Cookie/checkIfNewUpgrade.msc` | Affordability threshold notification |
| `Cookie/cookieSecretJoin.msc`, `cookieRoomSetup.msc`, `# cookieExit.msc`, `# Cookie Reset Button.msc` | Room assignment, entry, exit, reset |
| `Cookie/__init__.msc`, `# all summons.msc`, `interactionScriptImport.msc` | One-time world setup: entities and script bindings |
| `Cookie/cookie_opt.py`, `cookie_upgrade_order.txt` | Upgrade-order optimiser and its output |

## Running it

In-game, everything is event-driven: region entry, interaction-entity clicks and button presses. The optimiser is plain Python with no dependencies: `python Cookie/cookie_opt.py`.

## Notes and limitations

- `upgradeTextUpdate.msc` re-declares the ladder arrays locally instead of reading them from `Cookie.nms`; the button scripts read the namespace copies (their own local copies are commented out). Price changes need to be made in both places.
- The scripts depend on two other namespaces in this repo: `Harha::formatNumber`, `Harha::musicNotes`, `Harha::delay` and `rytools::particleLine`.
- Room positions and entity tags are hardcoded to the Theta world coordinates around `-9149, 100, 9301`.
