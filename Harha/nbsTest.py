import pynbs
import math

song_file = r'C:\Users\ryanp\OneDrive\Desktop\code\Minr Scrips\Harha\RainbowRoad.nbs'
output_file = r'C:\Users\ryanp\OneDrive\Desktop\code\Minr Scrips\Harha\RainbowRoadMusic.msc'

# for tick, chord in pynbs.read(song_file):
#     print(f"Tick = {tick}, Chord = {[(note.key - 33) for note in chord]}, velocity = {[note.velocity for note in chord]}, panning = {[note.panning for note in chord]}, instrument = {[note.instrument for note in chord]}")

panningMode = "true"  # Set to "true" to enable panning
particleMode = "true"  # Set to "true" to enable particle effects with panning

def note_to_playsound(note, velocity, panning, instrument):
    """
    Convert note data to a Minecraft /playsound command.
    
    Args:
        note: MIDI note number (0-24 for Minecraft)
        velocity: Volume (0-100, converted to 0.0-1.0)
        panning: Stereo panning (-100 to 100, affects left/right audio)
        instrument: Instrument ID (0-15 in NBS)
    
    Returns:
        str: Minecraft playsound command
    """
    # Map NBS instruments to Minecraft note block sounds
    instrument_sounds = {
        0: "block.note_block.harp",
        1: "block.note_block.bass",
        2: "block.note_block.basedrum",
        3: "block.note_block.snare",
        4: "block.note_block.hat",
        5: "block.note_block.guitar",
        6: "block.note_block.flute",
        7: "block.note_block.bell",
        8: "block.note_block.chime",
        9: "block.note_block.xylophone",
        10: "block.note_block.iron_xylophone",
        11: "block.note_block.cow_bell",
        12: "block.note_block.didgeridoo",
        13: "block.note_block.bit",
        14: "block.note_block.banjo",
        15: "block.note_block.pling"
    }
    
    sound = instrument_sounds.get(instrument, "block.note_block.harp")
    volume = velocity / 100.0  # Convert to 0.0-1.0 range
    pitch = 2 ** ((note - 12) / 12)  # Convert MIDI note to pitch
    
    # Check if panning is zero
    if panning == 0 or panningMode == "false":
        # No panning, use default position
        command = f"@bypass /playsound {sound} master @p ~ ~ ~ {volume:.2f} {pitch:.4f}"
    else:
        # Calculate panning distance (-2 to 2 blocks)
        pan_distance = (panning / 100.0) * 2.0
        
        # Command with position calculations embedded in the output
        # The calculations will be evaluated by the game/script system
        if particleMode == "true":
            command = f"@bypass /playsound {sound} master @p ~{{{{ {pan_distance:.2f} * math::cos(Double(player.getYaw() + 180)) }}}} ~ ~{{{{ {pan_distance:.2f} * math::sin(Double(player.getYaw() + 180)) }}}} {volume:.2f} {pitch:.4f} \n@bypass /particle minecraft:flame ~{{{{ {pan_distance:.2f} * math::cos(Double(player.getYaw() + 180)) }}}} ~ ~{{{{ {pan_distance:.2f} * math::sin(Double(player.getYaw() + 180)) }}}} 0 0 0 0 1"
        else:
            command = f"@bypass /playsound {sound} master @p ~{{{{ {pan_distance:.2f} * math::cos(Double(player.getYaw() + 90)) }}}} ~ ~{{{{ {pan_distance:.2f} * math::sin(Double(player.getYaw() + 90)) }}}} {volume:.2f} {pitch:.4f}"

    return command



chord_count = 0
note_count = 0

with open(output_file, 'w') as f:
    f.write("@fast\n")
    previous_tick = 0
    for tick, chord in pynbs.read(song_file):
        chord_count += 1
        # Calculate delay between this chord and the previous one
        delay = tick - previous_tick
        
        # Add delay command if there's a gap between chords
        if delay > 0 and previous_tick > 0:
            f.write(f"@delay {delay}\n")
        
        # f.write(f"# Tick = {tick}\n")
        for note in chord:
            note_count += 1
            note_value = note.key - 33
            command = note_to_playsound(note_value, note.velocity, note.panning, note.instrument)
            f.write(f"{command}\n")
        
        previous_tick = tick

print(f"Processed {chord_count} chords with {note_count} total notes")
print(f"Commands written to {output_file}")