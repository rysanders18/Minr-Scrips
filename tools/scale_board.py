"""Wrap every rotation/scale/translation entry of the block_display
`transformation:[...]` matrices in rychess/rychess/__init__.msc with
`{{value*m}}` so the whole board can be scaled by editing the single
`@define Float m` at the top of that file. Idempotent: already-wrapped
values are left alone. Run from the repo root:

    python tools/scale_board.py
"""
import os
import re

path = os.path.join(os.path.dirname(__file__), "..", "rychess", "rychess", "__init__.msc")

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# To "scale by m without changing rotation", every entry of the 3x3 rotation*scale
# submatrix must be multiplied by m. The 3x3 occupies indices 0,1,2,4,5,6,8,9,10
# of the row-major 4x4 transformation. Translations are 3,7,11. So all of indices
# 0..11 should be wrapped; the bottom row (12..15) stays [0,0,0,1].
WRAP_INDICES = set(range(12))

# Match `transformation:[...]` capturing the inner list.
TRANSFORMATION_RE = re.compile(r"transformation:\[([^\]]+)\]")
# Plain float literal still in unscaled form (e.g. -0.001992f, 0f).
PLAIN_VALUE_RE = re.compile(r"-?\d+(?:\.\d+)?f")
# Already-wrapped value (e.g. {{0.026*m}}f) -- leave as-is.
WRAPPED_VALUE_RE = re.compile(r"\{\{[^}]+\}\}f")

wrapped_count = 0


def replace_transformation(match: "re.Match[str]") -> str:
    global wrapped_count
    body = match.group(1)
    values = [v.strip() for v in body.split(",")]
    if len(values) != 16:
        raise ValueError(f"Expected 16 values, got {len(values)}: {body}")
    new_values = []
    for i, v in enumerate(values):
        if i in WRAP_INDICES and PLAIN_VALUE_RE.fullmatch(v):
            num = v[:-1]  # strip trailing 'f'
            new_values.append("{{" + num + "*m}}f")
            wrapped_count += 1
        else:
            # Already wrapped, or in the bottom row -- keep as-is.
            new_values.append(v)
    return "transformation:[" + ",".join(new_values) + "]"


new_content, count = TRANSFORMATION_RE.subn(replace_transformation, content)
print(f"Visited {count} transformation arrays, wrapped {wrapped_count} additional values")

with open(path, "w", encoding="utf-8") as f:
    f.write(new_content)
