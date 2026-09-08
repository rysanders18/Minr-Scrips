"""Generate the three armour-dye gradient tables for irodoriAnimation::dyeArmourGradient.

The animation fades one mannequin's dyed armour through FRAMES steps, one step
per tick. Each frame needs three colours -- chestplate, leggings, boots -- that
read as a deliberate set rather than three unrelated ramps.

How it works:

  * Colours are authored in OKLCH (perceptual lightness, chroma, hue), not RGB.
    Interpolating in RGB/HSV drags a hue sweep through grey mud every time it
    passes between primaries; OKLCH keeps chroma up and lightness even.

  * KEYFRAMES is the journey for the *chestplate*. It starts near-black and
    then jumps around the wheel rather than marching round it: navy, gold,
    plum, green, azure, orange, red. Every consecutive pair is a recognised
    harmony -- blue and gold, gold and plum, plum and green, green and azure,
    azure and orange, orange and red -- which is what keeps a jumping order
    from reading as arbitrary. It also alternates cool and warm, so the fade
    has a pulse to it instead of a direction.

  * Getting between two distant hues is the whole problem with a jumping
    order, and TRANSITION is the answer: each keyframe colour is held, then the
    move to the next happens inside the middle TRANSITION of the segment.
    Compressing it means the intermediate hues a jump has to pass through go by
    in about a third of a second -- a swing, not a phase -- so the sequence
    reads as cut colours rather than a spectrum wipe. DIP_MAX takes a little
    chroma out mid-swing, in proportion to how far the hue has to travel, which
    keeps the pass-through from looking like a third colour in its own right.

    The obvious alternative -- cross-dissolving through OKLab, so opposite hues
    cancel to neutral and bloom out the other side -- was tried and dropped.
    The drain is geometric, not temporal: near-complementary jumps bottom out
    around 0.05 vibrance whatever window they are given, which put roughly a
    second of grey mud in the middle of the fade. The arc swing never drops
    below 0.32.

  * Chroma is authored as VIBRANCE, a 0..1 fraction of the most chroma sRGB can
    actually hold at that lightness and hue, rather than an absolute number.
    Peak chroma swings hugely across the wheel (blue reaches ~0.31, yellow only
    ~0.21, and each at a very different lightness), so a fixed number would
    read as vivid in one place and washed out in another. As a fraction, "more
    and more vibrant" means the same thing at every hue.

    Vibrance climbs steadily across the whole journey (0.06 to 1.00) rather
    than arriving at full saturation early and sitting there -- the fade should
    read as colour building the whole way, not as one dark stop followed by
    seven vivid ones. Lightness is deliberately kept below each hue's chroma
    peak early on for the same reason: a low-chroma colour at high lightness
    goes chalky, where the same chroma darker reads as deep and deliberate. So
    the navy and gold are rich and muted, and only the orange and red at the
    end sit at the top of the gamut.

  * The three pieces are one tonal set, not three colours: TIER puts leggings
    and boots progressively further from the chestplate, each lifted toward
    light by a fraction of the *remaining* headroom (so a bright yellow frame
    can't blow the boots out to white), softened in chroma, and rotated a step
    round the wheel. HSHIFT does most of the work -- 50 degrees at full tier is
    enough that the boots sit in a neighbouring hue rather than a shade of the
    chestplate's, which is what makes the set legible at a glance on a small
    figure. It stays an analogous triad because the three are still inside one
    quadrant of the wheel. The last frame lands on red, rose, orchid pink from
    chest to boots.

  * Easing: the move inside each segment is smootherstep
    (6t^5 - 15t^4 + 10t^3), which has zero first and second derivative at both
    ends, and it is clamped at the edges of the TRANSITION window -- so the
    fade eases out of a held colour and eases into the next with no corner at
    either the hold or the move. Swings are quick by design and peak around
    40/255 on a channel; that is the intended snap between two stops, not
    banding.

Run:  python irodori_gradient.py
Writes the tables straight into irodori/irodoriAnimation/dyeArmourGradient.msc.
"""

import math
import re
from pathlib import Path

FRAMES = 240

# The chestplate's journey: (position 0..1, lightness, vibrance, hue degrees).
# Vibrance must climb; hue jumps, and always takes the short way round.
KEYFRAMES = [
    (0.00, 0.05, 0.06, 300.0),  # near-black, the faintest violet cast
    (0.14, 0.36, 0.40, 255.0),  # navy blue
    (0.29, 0.68, 0.55, 90.0),   # gold
    (0.43, 0.50, 0.66, 325.0),  # plum
    (0.57, 0.66, 0.77, 150.0),  # green
    (0.71, 0.62, 0.87, 225.0),  # azure
    (0.86, 0.74, 0.95, 55.0),   # orange
    (1.00, 0.58, 1.00, 28.0),   # vivid red
]

# Fraction of each segment the move between two stops happens in; the rest is
# spent holding the colour at either end.
TRANSITION = 0.35
# Chroma given up at the midpoint of a 180-degree jump, scaled down for
# shorter ones, so the hues a swing passes through do not read as a stop.
DIP_MAX = 0.35

# How far down the set each piece sits. 0 is the authored colour.
TIER = {"chest": 0.0, "legs": 0.5, "boots": 1.0}

L_TOP = 0.97   # lightness a tier-1 piece leans toward, never reaches
LIFT = 0.40    # fraction of the remaining headroom a tier-1 piece takes
CSOFT = 0.22   # chroma a tier-1 piece gives up
HSHIFT = 50.0  # degrees a tier-1 piece rotates back round the wheel

# Tier strength ramps from this fraction up to 1.0 across the fade. It is held
# high because the separation between the pieces is meant to be legible from
# the first coloured frame, not just by the end.
TIER_FLOOR = 0.55

# Floors for the spiral particle colours. A mote hangs in the air with nothing
# behind it, so the near-black opening of the armour fade would just be an
# invisible speck; these keep every particle readable without changing its hue.
SPARK_L_MIN = 0.58
SPARK_V_MIN = 0.62

# Hue wheel for the finale's ground spiral. Each band is drawn at its own
# gamut cusp, floored here so the darker hues still carry in the air.
# Keep this divisible by finaleArms in the .nms, so rainbowArmOffset can be
# an exact bands/arms and the streams sit evenly round the wheel.
RAINBOW_STEPS = 120
RAINBOW_L_MIN = 0.55


# --- OKLab / sRGB conversion ------------------------------------------------


def _srgb_encode(c):
    if c <= 0.0031308:
        return 12.92 * c
    return 1.055 * (c ** (1 / 2.4)) - 0.055


def oklab_to_linear_srgb(L, a, b):
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_**3, m_**3, s_**3
    return (
        4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
        -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
    )


def _in_gamut(rgb, eps=1e-6):
    return all(-eps <= c <= 1 + eps for c in rgb)


def _linear_at(L, C, h_rad):
    return oklab_to_linear_srgb(L, C * math.cos(h_rad), C * math.sin(h_rad))


def max_chroma(L, hue_deg, ceiling=0.45):
    """Most chroma sRGB can hold at this lightness and hue."""
    h = math.radians(hue_deg % 360.0)
    if _in_gamut(_linear_at(L, ceiling, h)):
        return ceiling
    lo, hi = 0.0, ceiling
    for _ in range(40):
        mid = (lo + hi) / 2
        if _in_gamut(_linear_at(L, mid, h)):
            lo = mid
        else:
            hi = mid
    return lo


def oklch_to_rgb8(L, C, hue_deg):
    """OKLCH -> 8-bit sRGB. Chroma is reduced (never lightness or hue) if the
    colour sits outside sRGB; naive per-channel clipping would swing the hue."""
    h = math.radians(hue_deg % 360.0)
    L = min(max(L, 0.0), 1.0)
    rgb = _linear_at(L, C, h)
    if not _in_gamut(rgb):
        rgb = _linear_at(L, max_chroma(L, hue_deg, C), h)
    return tuple(
        min(255, max(0, round(_srgb_encode(min(max(c, 0.0), 1.0)) * 255))) for c in rgb
    )


# --- curve ------------------------------------------------------------------


def smootherstep(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * t * (t * (t * 6 - 15) + 10)


def sample_base(t):
    """Chestplate lightness, vibrance and hue at progress t.

    The segment is held at both ends and moves through the middle TRANSITION of
    itself, so each colour reads as a stop rather than a waypoint. Hue takes the
    short way round and gives up some chroma mid-swing, in proportion to how far
    it has to go."""
    for i in range(len(KEYFRAMES) - 1):
        t0, L0, V0, H0 = KEYFRAMES[i]
        t1, L1, V1, H1 = KEYFRAMES[i + 1]
        if t <= t1 or i == len(KEYFRAMES) - 2:
            raw = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
            k = smootherstep(min(max((raw - 0.5) / TRANSITION + 0.5, 0.0), 1.0))
            dH = (H1 - H0 + 180.0) % 360.0 - 180.0
            hump = 1.0 - (2.0 * k - 1.0) ** 2
            dip = 1.0 - DIP_MAX * (abs(dH) / 180.0) * hump
            return (L0 + (L1 - L0) * k, (V0 + (V1 - V0) * k) * dip, H0 + dH * k)
    raise AssertionError


def build_tables():
    tables = {piece: [] for piece in TIER}
    for frame in range(FRAMES):
        t = frame / (FRAMES - 1)
        L, vibrance, H = sample_base(t)
        # Pieces fan apart on the same eased curve the colours travel on.
        strength = TIER_FLOOR + (1.0 - TIER_FLOOR) * smootherstep(t)
        for piece, tier in TIER.items():
            k = tier * strength
            Lp = L + (L_TOP - L) * LIFT * k
            Hp = H - HSHIFT * k
            Cp = max_chroma(Lp, Hp) * vibrance * (1.0 - CSOFT * k)
            r, g, b = oklch_to_rgb8(Lp, Cp, Hp)
            tables[piece].append(r * 65536 + g * 256 + b)
    return tables


def build_spiral():
    """Particle colours for spiralParticles, as "r,g,b" floats 0..1.

    Same journey the armour walks, but floored in lightness and vibrance --
    a particle hangs in the air with nothing behind it, so the near-black
    opening of the fade would simply be invisible. The floors keep every mote
    readable while the hue still tracks the cutscene exactly. Hue sits halfway
    between the chestplate and leggings so the motes read as part of the set."""
    out = []
    for frame in range(FRAMES):
        L, vibrance, H = sample_base(frame / (FRAMES - 1))
        Ls = max(L + (L_TOP - L) * LIFT * 0.75, SPARK_L_MIN)
        Hs = H - HSHIFT * 0.5
        Cs = max_chroma(Ls, Hs) * max(vibrance, SPARK_V_MIN)
        h = math.radians(Hs % 360.0)
        lin = _linear_at(Ls, Cs, h)
        out.append(
            ",".join("%.3f" % min(max(_srgb_encode(min(max(c, 0.0), 1.0)), 0.0), 1.0) for c in lin)
        )
    return out


def cusp_lightness(hue_deg, coarse=0.01):
    """Lightness at which this hue holds the most chroma in sRGB.

    The gamut's widest point moves enormously round the wheel -- blue peaks
    near L 0.45, yellow up at 0.87 -- so a rainbow drawn at one fixed
    lightness is vivid at a couple of hues and chalky everywhere else.
    Scanning for the cusp per hue gives every band its most saturated form,
    which is what makes the ring read as a spectrum rather than a gradient."""
    best_L, best_C = 0.5, -1.0
    steps = int(1.0 / coarse)
    for n in range(1, steps):
        L = n * coarse
        C = max_chroma(L, hue_deg)
        if C > best_C:
            best_L, best_C = L, C
    lo, hi = best_L - coarse, best_L + coarse
    for _ in range(24):
        a = lo + (hi - lo) / 3
        b = hi - (hi - lo) / 3
        if max_chroma(a, hue_deg) < max_chroma(b, hue_deg):
            lo = a
        else:
            hi = b
    return (lo + hi) / 2


def build_rainbow():
    """A full hue wheel for the finale spiral, as "r,g,b" floats 0..1.

    Evenly spaced in OKLCH hue, not RGB -- an RGB rainbow bunches up in the
    cyans and races through the oranges. Each band sits at its own cusp
    lightness (floored for visibility, since these hang in the air)."""
    out = []
    for n in range(RAINBOW_STEPS):
        H = n * 360.0 / RAINBOW_STEPS
        L = max(cusp_lightness(H), RAINBOW_L_MIN)
        lin = _linear_at(L, max_chroma(L, H), math.radians(H))
        out.append(
            ",".join("%.3f" % min(max(_srgb_encode(min(max(c, 0.0), 1.0)), 0.0), 1.0) for c in lin)
        )
    return out


# --- emit -------------------------------------------------------------------

HERE = Path(__file__).parent / "irodoriAnimation"
MSC = HERE / "dyeArmourGradient.msc"
SPIRAL_MSC = HERE / "spiralParticles.msc"
FINALE_MSC = HERE / "finale.msc"
VAR = {"chest": "colorListChestplate", "legs": "colorListPants", "boots": "colorListBoots"}


def write_table(path, name, values):
    line = "@define String[] {} = String[{}]".format(
        name, ", ".join('"{}"'.format(v) for v in values)
    )
    src = path.read_text(encoding="utf-8")
    src, n = re.subn(
        r"^@define String\[\] " + name + r" = String\[.*?\]$", lambda _m: line, src, flags=re.M
    )
    assert n == 1, "did not find {} in {}".format(name, path)
    path.write_text(src, encoding="utf-8")


def main():
    tables = build_tables()
    for piece, name in VAR.items():
        write_table(MSC, name, tables[piece])

    spiral = build_spiral()
    write_table(SPIRAL_MSC, "spiralColors", spiral)

    rainbow = build_rainbow()
    write_table(FINALE_MSC, "rainbowColors", rainbow)

    print("wrote {} frames to {} and {}".format(FRAMES, MSC.name, SPIRAL_MSC.name))
    print("wrote {} rainbow bands to {}".format(len(rainbow), FINALE_MSC.name))
    worst = 0
    for piece in TIER:
        seq = tables[piece]
        for i in range(1, FRAMES):
            a, b = seq[i - 1], seq[i]
            worst = max(
                worst,
                max(abs(((a >> s) & 255) - ((b >> s) & 255)) for s in (16, 8, 0)),
            )
    print("  max per-frame channel step: {}/255".format(worst))
    for t, _L, _V, _H in KEYFRAMES:
        frame = round(t * (FRAMES - 1))
        row = "  ".join(
            "{}=#{:06x}".format(p, tables[p][frame]) for p in ("chest", "legs", "boots")
        )
        print("  frame {:3d} ({:4.1f}s)  {}".format(frame, frame / 20, row))


if __name__ == "__main__":
    main()
