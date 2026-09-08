# Slimemaze v3 — server import checklist (Epsilon world)

THE IMPORT SET IS `server_export/` — regenerate it any time with
`python make_buildall.py` then `python make_server_export.py`.
It contains exactly what the server needs (368 .msc + slimemaze.nms);
the segmented build/walls/dome/floor/lanterns/decor chains and all
removes are DELIBERATELY EXCLUDED (buildALL replaces them; no
in-place wipe on the server). The maze is centered at
(4618.0, 3380.0), y -72..306; commands below y=-64 fail by design
(hand-built end room).

## 1. Namespace

Import `server_export/slimemaze.nms` first (365 declarations incl.
`relative Block lastBlock`).

## 2. Function imports (368 files, any order — nothing runs on import)

| family            | files | note                                   |
|-------------------|------:|----------------------------------------|
| buildALL          |   315 | every block of the whole maze, 64x64 regions: tp, wait 500 ticks, place, hop; @fast parts; largest 211KB |
| trigger wiring    |    45 | `grounds1..3`, `slimegrounds1..42`     |
| hand-tuned hooks  |     5 | `slimeblock`, `spliceFx`, `fallFx1`, `fallFx2`, `scaryTitle` — skip any the server already has |
| core logic        |     3 | `splice`, `fall`, `__init__`           |

## 3. Run (in-game, as the map maker — stay online, it teleports you)

    /function execute slimemaze::buildALL1(Player("You"))

One command: places all 815k blocks region by region (~22 min of
region waits + placement), then tail-calls grounds1 -> slimegrounds
to wire every splice + bounce trigger, ending with a completion toast.

## 4. Wiring

- Fall: bind the map's kill-floor / fall-catch region to
  `slimemaze::fall(player)` (slimeblock also self-triggers fall when a
  player drops 2+ below their last bounce block).
- After ANY future namespace re-import: run `grounds1` once by hand to
  re-wire every trigger (see `__init__.msc`).
- Registries for reference: `splices.txt`, `starts.txt`, `solution.txt`.
