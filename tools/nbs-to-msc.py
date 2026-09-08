import os
import pynbs

# ============================================================================
# nbsTest.py - convert .nbs (Note Block Studio) songs to .msc (Minr) scripts
#
# Old approach: emit one full @bypass /playsound line per note plus an @delay
# line between ticks. Each note line was ~120-150 characters, so long songs
# blew straight past hastebin's character limit.
#
# New approach: encode the song as a flat list of "entries" stored in parallel
# arrays, then iterate them with a single @for loop. The loop body is written
# ONCE per chunk, so per-note cost drops to roughly 25 characters of array
# data.
#
# Entry tuple = (instrument, volume, pitch, panning)
#
#   Note entry  (volume > 0):
#       instrument = index into INSTRUMENT_NAMES (0..15)
#       volume     = 0..1, used directly in /playsound
#       pitch      = playback pitch, used directly in /playsound
#       panning    = horizontal block offset; 0 means "no panning"
#
#   Rest entry  (volume == 0  -- branch goes to @delay, never to /playsound):
#       instrument = number of ticks to @delay
#                    (the field is REUSED so a multi-tick rest costs ONE entry
#                    instead of N -- big win for sparse songs)
#       volume     = 0
#       pitch      = unused (0)
#       panning    = unused (0)
#
# MSC list literals are capped at 1000 elements, so entries are split into
# chunks of CHUNK_SIZE; each chunk gets its own arrays (instrument1/volume1/
# pitch1/panning1, instrument2/..., etc.) and its own @for loop. Adjacent
# chunks run back-to-back with no extra delay between them.
# ============================================================================

song_file = r'C:\Users\ryanp\OneDrive\Desktop\code\Minr Scrips\Harha\NeverGonnaGiveYouUp.nbs'
output_file = r'C:\Users\ryanp\OneDrive\Desktop\code\Minr Scrips\Harha\RickAstley.msc'

CHUNK_SIZE = 1000

panningMode = True   # if False, all panning is forced to 0 (use the simple form)
particleMode = True  # if False, no flame particles spawn alongside panned notes

# Index -> Minecraft note block sound suffix.
# Stored once in the .msc as a single String[] lookup table so each per-note
# instrument value can be a compact int (~3 chars) instead of a string (~8 chars).
INSTRUMENT_NAMES = [
    "harp",
    "bass",
    "basedrum",
    "snare",
    "hat",
    "guitar",
    "flute",
    "bell",
    "chime",
    "xylophone",
    "iron_xylophone",
    "cow_bell",
    "didgeridoo",
    "bit",
    "banjo",
    "pling",
]


def build_entries(song_path):
    """Walk the .nbs file and produce a flat list of (instrument, volume, pitch, panning)."""
    entries = []
    previous_tick = 0
    first = True
    note_count = 0
    rest_count = 0

    for tick, chord in pynbs.read(song_path):
        if not first:
            gap = tick - previous_tick
            if gap > 0:
                # One rest entry encodes the entire multi-tick gap.
                # The instrument field carries the delay count.
                entries.append((gap, 0.0, 0.0, 0.0))
                rest_count += 1
        first = False

        for note in chord:
            if note.velocity == 0:
                continue  # silent notes contribute nothing
            note_value = note.key - 33
            if 0 <= note.instrument < len(INSTRUMENT_NAMES):
                instrument = note.instrument
            else:
                instrument = 0
            volume = note.velocity / 100.0
            pitch = 2 ** ((note_value - 12) / 12)
            panning = (note.panning / 100.0) * 2.0 if panningMode else 0.0
            entries.append((instrument, volume, pitch, panning))
            note_count += 1

        previous_tick = tick

    return entries, note_count, rest_count


def fmt_num(v):
    """Compact float formatting -- drops trailing zeros but always keeps one decimal.
    MSC requires float/double literals to have at least one decimal place
    (e.g. `1.0F`, not `1F`)."""
    s = f"{v:.3f}".rstrip('0')
    if s.endswith('.'):
        s += '0'
    if s in ('', '-', '.0', '-.0'):
        s = '0.0'
    return s


def write_chunk(f, idx, chunk):
    """Emit one chunk: four @define array literals followed by an @for loop body."""
    n = len(chunk)
    instr_arr = ",".join(str(e[0]) for e in chunk)
    vol_arr   = ",".join(f"{fmt_num(e[1])}F" for e in chunk)
    pitch_arr = ",".join(f"{fmt_num(e[2])}D" for e in chunk)
    pan_arr   = ",".join(f"{fmt_num(e[3])}D" for e in chunk)

    f.write(f"# === Chunk {idx} ({n} entries) ===\n")
    f.write(f"@define Int[] instrument{idx} = Int[{instr_arr}]\n")
    f.write(f"@define Float[] volume{idx} = Float[{vol_arr}]\n")
    f.write(f"@define Double[] pitch{idx} = Double[{pitch_arr}]\n")
    f.write(f"@define Double[] panning{idx} = Double[{pan_arr}]\n")
    f.write("\n")
    f.write(f"@for Int i in list::range(0, {n})\n")
    f.write(f"    @if volume{idx}[i] == 0.0F\n")
    # Rest branch -- the instrument field holds the delay tick count.
    # Inline @delay does not accept array interpolation, so we go through
    # the Harha::delay(Int ticks) wrapper.
    f.write(f"        @var Harha::delay(instrument{idx}[i])\n")
    f.write(f"    @else\n")
    f.write(f"        @if panning{idx}[i] == 0.0D\n")
    f.write(
        f"            @bypass /playsound block.note_block.{{{{instrumentNames[instrument{idx}[i]]}}}}"
        f" master @p ~ ~ ~ {{{{volume{idx}[i]}}}} {{{{pitch{idx}[i]}}}}\n"
    )
    f.write(f"        @else\n")
    f.write(
        f"            @bypass /playsound block.note_block.{{{{instrumentNames[instrument{idx}[i]]}}}}"
        f" master @p"
        f" ~{{{{ panning{idx}[i] * math::cos(Double(player.getYaw() + 180)) }}}}"
        f" ~"
        f" ~{{{{ panning{idx}[i] * math::sin(Double(player.getYaw() + 180)) }}}}"
        f" {{{{volume{idx}[i]}}}} {{{{pitch{idx}[i]}}}}\n"
    )
    if particleMode:
        f.write(
            f"            @bypass /particle minecraft:flame"
            f" ~{{{{ panning{idx}[i] * math::cos(Double(player.getYaw() + 180)) }}}}"
            f" ~"
            f" ~{{{{ panning{idx}[i] * math::sin(Double(player.getYaw() + 180)) }}}}"
            f" 0 0 0 0 1\n"
        )
    f.write(f"        @fi\n")
    f.write(f"    @fi\n")
    f.write("@done\n\n")


entries, note_count, rest_count = build_entries(song_file)

with open(output_file, 'w') as f:
    f.write("@using Harha\n")
    f.write("@fast\n\n")

    # Single shared lookup table for note block instrument names. Referenced
    # by every chunk via instrumentNames[instrumentK[i]] inside /playsound.
    instr_lookup = ",".join(f'"{name}"' for name in INSTRUMENT_NAMES)
    f.write(f"@define String[] instrumentNames = String[{instr_lookup}]\n\n")

    chunk_count = 0
    for start in range(0, len(entries), CHUNK_SIZE):
        chunk_count += 1
        write_chunk(f, chunk_count, entries[start:start + CHUNK_SIZE])

size = os.path.getsize(output_file)
print(f"Processed {note_count} notes and {rest_count} rests across {chunk_count} chunk(s)")
print(f"Wrote {len(entries)} total entries ({size} bytes) to {output_file}")
