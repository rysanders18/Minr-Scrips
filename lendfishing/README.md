# lendfishing

A fishing minigame for the Minr server written in MSC. Casting a rod starts a throw-strength meter on the XP bar, a bite arrives after a random delay, and a timed right-click reels in a loot item whose name, weight, price and rarity are rolled from a weighted loot table. Loot definitions use MSC's `@class` feature, with the constructor and methods split across files in `Loot/` and `LootTable/`.

## How it works

**Input capture.** Minr scripts attach to entities, not to right-clicks in general, so `summonInteraction.msc` summons a thin `interaction` entity tagged `<uuid>_inter`, makes it ride the player, and binds `interactionEntityScript` to it with `/script create entity`. Every right-click hits that entity. `disableInteraction` / `enableInteraction` collapse its height to 0 and restore it, which is how the script stops re-entering itself while the cast meter is running.

**Throw meter** (`interactionEntityScript.msc`). If the player is holding a rod and not already fishing, the script sets the XP bar to a triangle wave over a 40-tick cycle (0 to 1 and back) and polls the player's `useItem` statistic for the fishing rod each tick. When the count increases the rod has been cast: the newest untagged `fishing_bobber` is tagged `<uuid>_bobber` and the meter value at that tick is the throw strength. A perfect 1.0 plays a chime and particles, above 0.71 a softer note, below 0.71 a dull sound. If the loop ends without a cast the meter is cleared.

**Bite and catch** (`startFishing.msc`, `spawnFish.msc`). `startFishing(player, 0.1, 5, 2)` waits two seconds, then rolls a 10 percent bite chance every half second for up to five seconds, with a guaranteed bite at the end. On a bite, `spawnFish` draws `nextLoot` from the table, dips the bobber (`Motion[1] = -0.4`), and plays particles in the loot's rarity colour. `readyToCatch` stays true for 20 ticks; a right-click in that window summons the loot as a named item entity at the bobber with a `Motion` vector aimed at the player, kills the bobber, and after 10 ticks replaces the flying entity with a real `/give`. Clicking outside the window just reels in.

**Loot table** (`LootTable/`). A `LootTable` holds a `Loot[]` and a parallel `Float[]` of probabilities. `getLoot.msc` draws one uniform number and walks the cumulative sum until it exceeds it. `defaultLoot` in `lendfishing.nms` is: dried kelp 50 percent, cod 20, salmon 20, emerald 10.

**Loot instances** (`Loot/`). A `Loot` is defined by item id, display name, `[minWeight, maxWeight]`, base price and a rarity index. The constructor resolves the index into a rarity name, chat colour and particle colour from three parallel arrays in the namespace (`Common`, `Uncommon`, `Rare`, `Legendary`, `Extinct`). `getLootInstanceCommandData.msc` rolls a weight to 0.1 kg, scales price linearly from 1x at minimum weight to 2x at maximum, applies a 1 percent "shiny" roll that triples the price and adds an enchantment glint, and returns two strings: the NBT for the summoned item entity (custom name with weight, no pickup) and the component string for the final `/give` (name, rarity, weight and price in the lore).

## Layout

| File | Purpose |
|---|---|
| `lendfishing.nms` (repo root) | Class declarations, rarity tables, the two loot tables, per-player state |
| `lendfishing/summonInteraction.msc` | Creates and binds the per-player interaction entity |
| `lendfishing/interactionEntityScript.msc` | Right-click handler: throw meter, catch, reel-in |
| `lendfishing/startFishing.msc`, `spawnFish.msc` | Bite timing and bite effects |
| `lendfishing/Loot/Loot(String,String,Float[],Int,Int).msc` | `Loot` constructor (file name is the signature) |
| `lendfishing/Loot/getLootInstanceCommandData.msc` | Rolls an instance and builds the summon/give commands |
| `lendfishing/LootTable/LootTable(lendfishing__Loot[],Float[]).msc` | `LootTable` constructor (`__` stands in for `::` in the type name) |
| `lendfishing/LootTable/getLoot.msc`, `getLootCommandData.msc` | Weighted draw |
| `lendfishing/enableInteraction.msc`, `disableInteraction.msc`, `errorMessage.msc` | Helpers |

## Running it

`summonInteraction(player)` is invoked once when a player enters a fishing area; everything after that is driven by right-clicks on the attached entity. Holding a barrier and clicking removes the entity.

## Notes and limitations

- The throw strength is measured and reported but does not yet affect the cast: the flow comment in `interactionEntityScript.msc` plans to set the bobber's `Motion` from it, and `startFishing` is always called with the same parameters.
- `defaultLoot` lists five items but only four probabilities, so the diamond entry can never be drawn. `defaultLoot2` (nine metal/gem items) is defined but unused, and its probabilities sum to 0.955, so a draw from it would hit the error branch about 4.5 percent of the time.
- The statistics variables (`fishCaught`, `biggestFish`, `totalMoney`, ...) are declared in the namespace but nothing writes them yet.
- Bobber position is read back through `util::executeAndQueryResult` on `/data get`, scaled by 1000, because entity NBT is not directly readable from MSC.
- Weights, rarity tiers and the world name (`theta` in the `/execute in` calls) are hardcoded.
