# pip install nbtlib
import nbtlib
import os

print("This is running now FR")

# Path to the NBT file in Downloads folder
nbt_path = os.path.join(os.path.expanduser("~"), "Downloads", "Harha.nbt")
doc = nbtlib.load(nbt_path)

# Debug: print available keys
print("Available keys:", list(doc.keys()))
print("Doc type:", type(doc))

# Try to access the root - it might be the doc itself
root = doc

palette = root["palette"]  # or root["palettes"][0] if present
name_by_index = {i: entry["Name"].unpack() for i, entry in enumerate(palette)}

button_names = {
    "minecraft:flower_pot"
}

# Apply offsets to the air coordinates: -4723 84 5051
# Apply offsets to the air coordinates: -9246 36 9452
button_coords = []
for blk in root["blocks"]:
    state_idx = int(blk["state"])
    name = name_by_index[state_idx]
    # print(name)
    if name in button_names:
        x, y, z = [int(v) for v in blk["pos"]]
        # Apply offsets: -9246 36 9452
        adjusted_x = x - 9246
        adjusted_y = y + 36
        adjusted_z = z + 9452
        button_coords.append((adjusted_x, adjusted_y, adjusted_z))

# Print adjusted coordinates
for coord in button_coords:
    print(f"({coord[0]},{coord[1]},{coord[2]}),", end=" ")

print(f"\n\nTotal buttons found: {len(button_coords)}")
