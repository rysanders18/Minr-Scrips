#!/usr/bin/env python3
"""Generate the j100 mass interact-script import chain.

Reads setup1.msc / setup2.msc, replays every /fill and /setblock in file order
(later commands overwrite earlier ones), drops every coordinate whose FINAL
block is air or light, then decomposes the remaining set into maximal cuboids
and emits chained `interactImportN(Player player)` functions.

Each emitted cuboid becomes a nested @for that issues, per block,

    @command /s r i <x> <y> <z> Epsilon
    @command /s c i <x> <y> <z> Epsilon @var j100::clickBlock(player)

-- every block individually, never a /fill. The remove-before-create pair makes
the import safely re-runnable. Same shape as j100/__init__.msc (which loops and
emits /s r g + /s c g per gold block), split into chained parts like the
slimemaze mass imports because of the hastebin cap. No @fast: the work is spread
across ticks rather than dumped into one.

Run from the j100/ directory:  python gen_interact_imports.py
"""

import re
import collections

WORLD = "Epsilon"
NAMESPACE = "j100"
CALLBACK = "@var j100::clickBlock(player)"
FUNC_PREFIX = "interactImport"
OUT_DIR = "j100"

# Hastebin import caps: ~4k lines AND a byte budget. Stay well under both.
MAX_LINES = 2100
MAX_BYTES = 200_000

# Blocks that never get an interact script. Plain glass is the level-cell shell
# and is deliberately excluded -- only white_stained_glass is clickable.
SKIP = {
    "minecraft:air",
    "minecraft:cave_air",
    "minecraft:void_air",
    "minecraft:light",
    "minecraft:glass",
}

FILL = re.compile(
    r"^@bypass /fill (-?\d+) (-?\d+) (-?\d+) (-?\d+) (-?\d+) (-?\d+) "
    r"(.+?)(?: strict| replace| destroy| keep| hollow| outline)?\s*$"
)
SETBLOCK = re.compile(
    r"^@bypass /setblock (-?\d+) (-?\d+) (-?\d+) "
    r"(.+?)(?: strict| replace| destroy| keep)?\s*$"
)


def replay(paths):
    """Replay the setup scripts into a coord -> block-state dict."""
    world = {}
    for path in paths:
        with open(path) as fh:
            for lineno, raw in enumerate(fh, 1):
                line = raw.strip()
                if not line or line.startswith("#") or line == "@fast":
                    continue
                m = FILL.match(line)
                if m:
                    x1, y1, z1, x2, y2, z2 = (int(v) for v in m.groups()[:6])
                    block = m.group(7)
                else:
                    m = SETBLOCK.match(line)
                    if not m:
                        raise ValueError(f"{path}:{lineno}: unparsed: {line}")
                    x1 = x2 = int(m.group(1))
                    y1 = y2 = int(m.group(2))
                    z1 = z2 = int(m.group(3))
                    block = m.group(4)
                for x in range(min(x1, x2), max(x1, x2) + 1):
                    for y in range(min(y1, y2), max(y1, y2) + 1):
                        for z in range(min(z1, z2), max(z1, z2) + 1):
                            world[(x, y, z)] = block
    return world


def decompose(coords):
    """Greedy maximal-cuboid cover of a coordinate set.

    Grows +x, then +z, then +y from each unclaimed cell in (y, z, x) order.
    Returns [(x0, y0, z0, x1, y1, z1), ...] with no overlaps and exact coverage.
    """
    remaining = set(coords)
    boxes = []
    for cell in sorted(coords, key=lambda p: (p[1], p[2], p[0])):
        if cell not in remaining:
            continue
        x0, y0, z0 = cell
        x1 = x0
        while (x1 + 1, y0, z0) in remaining:
            x1 += 1
        z1 = z0
        while all((x, y0, z1 + 1) in remaining for x in range(x0, x1 + 1)):
            z1 += 1
        y1 = y0
        while all(
            (x, y1 + 1, z) in remaining
            for x in range(x0, x1 + 1)
            for z in range(z0, z1 + 1)
        ):
            y1 += 1
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                for z in range(z0, z1 + 1):
                    remaining.discard((x, y, z))
        boxes.append((x0, y0, z0, x1, y1, z1))
    return boxes


def emit_box(box, world):
    """Render one cuboid as a comment plus its nested @for / @command block."""
    x0, y0, z0, x1, y1, z1 = box
    volume = (x1 - x0 + 1) * (y1 - y0 + 1) * (z1 - z0 + 1)

    kinds = collections.Counter()
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            for z in range(z0, z1 + 1):
                kinds[world[(x, y, z)].split("[")[0].replace("minecraft:", "")] += 1
    label = "/".join(k for k, _ in kinds.most_common(2))

    if volume == 1:
        return [
            f"# {x0} {y0} {z0} ({label})",
            f"@command /s r i {x0} {y0} {z0} {WORLD}",
            f"@command /s c i {x0} {y0} {z0} {WORLD} {CALLBACK}",
        ]

    axes = [
        ("i", x0, x1, "{{i}}"),
        ("j", y0, y1, "{{j}}"),
        ("k", z0, z1, "{{k}}"),
    ]
    coord = []
    loops = []
    for var, lo, hi, tmpl in axes:
        if lo == hi:
            coord.append(str(lo))
        else:
            coord.append(tmpl)
            loops.append(f"@for Int {var} in list::range({lo}, {hi + 1})")

    out = [
        f"# {x0} {y0} {z0} -> {x1} {y1} {z1}  ({volume} blocks, {label})",
    ]
    for depth, loop in enumerate(loops):
        out.append("    " * depth + loop)
    indent = "    " * len(loops)
    pos = " ".join(coord)
    out.append(f"{indent}@command /s r i {pos} {WORLD}")
    out.append(f"{indent}@command /s c i {pos} {WORLD} {CALLBACK}")
    for depth in range(len(loops) - 1, -1, -1):
        out.append("    " * depth + "@done")
    return out


def chunk(blocks):
    """Pack rendered box blocks into parts under the line and byte caps."""
    parts = [[]]
    lines = bytes_ = 0
    for block in blocks:
        # +1 for the blank separator line emitted after every block.
        cost = len(block) + 1
        size = sum(len(l) + 1 for l in block) + 1
        if parts[-1] and (lines + cost > MAX_LINES or bytes_ + size > MAX_BYTES):
            parts.append([])
            lines = bytes_ = 0
        parts[-1].append(block)
        lines += cost
        bytes_ += size
    return parts


def main():
    world = replay(["setup1.msc", "setup2.msc"])
    coords = {c for c, b in world.items() if b.split("[")[0] not in SKIP}
    boxes = decompose(coords)

    covered = sum(
        (b[3] - b[0] + 1) * (b[4] - b[1] + 1) * (b[5] - b[2] + 1) for b in boxes
    )
    assert covered == len(coords), (covered, len(coords))

    rendered = [emit_box(b, world) for b in boxes]
    parts = chunk(rendered)
    total = len(parts)

    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    zs = [c[2] for c in coords]
    banner = [
        f"# Generated by gen_interact_imports.py from setup1.msc + setup2.msc.",
        f"# {len(coords)} blocks in {len(boxes)} cuboids -- /s r i + /s c i per block, never a /fill.",
        f"# Air, light and plain glass are excluded (checked against each block's FINAL state).",
        f"# Bounds: x {min(xs)}..{max(xs)}, y {min(ys)}..{max(ys)}, z {min(zs)}..{max(zs)}",
    ]

    for idx, part in enumerate(parts, 1):
        name = f"{FUNC_PREFIX}{idx}"
        out = [f"# {name}(Player player)"]
        if total > 1:
            out.append(f"# part {idx} of {total} - chains to the next part when done")
        out += banner
        out += ["", f"@using {NAMESPACE}", ""]
        for block in part:
            out += block
            out.append("")
        if idx < total:
            out.append(f"@var {FUNC_PREFIX}{idx + 1}(player)")
        text = "\n".join(out).rstrip() + "\n"
        with open(f"{OUT_DIR}/{name}.msc", "w") as fh:
            fh.write(text)
        print(
            f"{OUT_DIR}/{name}.msc  {text.count(chr(10))} lines  "
            f"{len(text) / 1000:.0f}KB  {len(part)} cuboids"
        )

    print(f"\n{len(coords)} interact scripts across {total} part(s)")


if __name__ == "__main__":
    main()
