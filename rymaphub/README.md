# rymaphub

Chat-message map art importer for the RYmaphub hub on Minr. Pairs with the
web page at `rysanders18.github.io/rymaphub` (`script.js` there is the encoder).

Minr no longer lets a script import another script, so the old flow (web
page posts a build script to paste.minr.org, hub imports it) is dead. The
replacement: the web page encodes the 128x128 map as a series of chat
messages, and `importMapArt` reads them with `@prompt`, validates each one,
recomputes the staircase heights, and places the blocks itself.

## Files

| File | Role |
|---|---|
| `rymaphub.nms` | Namespace: hub coordinates, block list, alphabet, per-player decode state, function signatures |
| `rymaphub/importMapArt.msc` | Entry point (bind to the import sign). Prompt loop with validation and retry |
| `rymaphub/checkMessage.msc` | Index + alphabet + checksum check for one data message |
| `rymaphub/decodeMapArt.msc` | Symbol stream to pixels, 512 symbols per tick |
| `rymaphub/emitSymbol.msc` | Appends the pixels of one plain symbol |
| `rymaphub/repeatSymbol.msc` | Applies a run code (repeat the previous symbol) |
| `rymaphub/emitPixels.msc` | Buffers pixels into one column at a time |
| `rymaphub/buildColumn.msc` | Valley heights for a column, clear, noobline, fills |

## Setup

1. Edit `world`, `startX/startY/startZ`, `clearHeight`, `mapId`, `baseBlock`
   and `nooblineBlock` in `rymaphub.nms` to match the hub. Every fill/setblock
   runs through `/execute in {{world}} run ...`. Columns are cleared from
   `startY` to `startY+clearHeight`, so that range must fit under the world
   height and above the tallest column the web page reports (the page's
   "Max staircasing height" slider caps it at 128; default 32). The shipped values,
   `startY = 120` and `clearHeight = 128`, build up to Y 248 and put the
   glass floor at 119, which fits a 0-255 dimension with room to spare.
2. Create the namespace and define the seven functions with the signatures in
   `rymaphub.nms`, then import each `.msc`.
3. Bind an interact script to the import sign: `@var rymaphub::importMapArt(player)`.
4. The area must be loaded while building (the player is standing at the hub
   in that dimension). The area is 128 wide by 129 deep: the extra row at
   `startZ-1` is the noobline.

## Staircasing (why heights are recomputed, not sent)

The map renderer shades each block dark, normal or light by comparing its
height with the block to its north, and only the sign of the difference
matters. So a pixel's tone pins down only whether its column steps up, down
or stays level; the actual heights are free. Both sides run the same Valley
algorithm (from MapartCraft): running-sum heights, then every non-plateau
stretch of a column pulled down to the floor and every plateau pulled down
by the smaller of the two neighbouring pull-downs. Nothing about heights is
transmitted. The row north of the map (the "noobline") gets one block per
column at the height row 0 is compared against.

The pixel south of a transparent pixel is compared with the void: it always
renders light and is not a step in the staircase. The web page restricts it
to light tones, and both sides treat it as a level step.

## Encoding contract (protocol v6)

Shared with `script.js`. Change one side only together with the other.

- **Alphabet.** A symbol is one chat character whose value is its position
  in the alphabet string (`String.indexOf` is the only char-to-number
  primitive in MSC). The alphabet is 2,980 consecutive CJK ideographs,
  U+4E00..U+59A3, one UTF-16 unit each. See "The alphabet size" below
  before changing it.
- **Colours.** Master index 0 = transparent. For m >= 1, block =
  `blocks[(m-1)/3]`, tone = `(m-1)%3` (0 dark, 1 normal, 2 light). 157 values.
- **Stream.** Pixels in column-major order (x outer, z inner). A pixel is a
  master colour index and K is the full count of them (`colours` = 157), not
  a per-image palette: 157^2 already fits the alphabet, so two pixels still
  pack into one character and nothing about the palette is transmitted.
  P = pixels per plain symbol (2 if K^2+64 fits the alphabet, else 1; with
  a 2,980-character alphabet and 157 colours it is 1),
  base = K^P, N = alphabet size. Symbol `s < base` is P pixels (P=2:
  `s / K` then `s % K`). Symbol `s >= base` is a run code: repeat the
  previous PLAIN SYMBOL `s - base + 1` more times, at most 499 per code.
  Runs may span columns and messages.
- **Message 1**: `RYMH` + `A[P]` + `A[N-1-nMsgs]` + payload + skip(check),
  with `check = (P + nMsgs + sum(payload values)) % (N-1)`. The header rides
  in front of message 1's own payload instead of taking a message to
  itself, so it costs 6 characters rather than a whole line, and an image
  small enough to fit is a single message. `nMsgs` is the field next to the
  payload because its value sits near the top of the alphabet, far above
  any symbol value, so those two characters can never be equal.
- **Messages 2..nMsgs**: `A[N-1-i]` + payload + skip(check) for
  i = 1..nMsgs-1, `check = (i + sum(payload values)) % (N-1)`.
- **skip(v)** writes the checksum as `A[v]` when `v` is below the preceding
  character's value and `A[v+1]` otherwise, so it can never equal that
  character.
- Every message is at most 256 characters. That is Minecraft's chat limit,
  and the packet checks character count rather than UTF-8 byte count, so a
  full 256 CJK characters is accepted.
- **Message length is a setting on the web page, not part of the format.**
  The decoder never looks at it. Minr rejected 250-character messages while
  accepting a 36-character header, so the server's real limit is lower than
  Minecraft's own 256 and has to be found by trying one message: the script
  prints how many characters it received whenever a message fails.

### No two adjacent characters are ever equal

This is a hard property of protocol v5, not a nicety. Under v2, Minr chat
delivered a 250-character message as 249: one character was silently
dropped out of a run of eight identical ones, and the checksum caught it.
Three rules secure the property, and `test_roundtrip.js` asserts it on
every generated message including solid-colour images:

1. Every repeat becomes a run code, and consecutive run codes are forced to
   differ, so a payload never repeats a character.
2. `nMsgs` and the message index are written from the top of the alphabet,
   far above any symbol value, so they cannot equal a neighbour. `P` is the
   one small field, and it is kept away from the payload by putting `nMsgs`
   between them.
3. The checksum skips the preceding character's value.

## Sizes

From `test_roundtrip.js` on the site repo (synthetic images):

| Image | Messages | Colours | Tallest column |
|---|---|---|---|
| Photo-like gradient, Valley, Floyd-Steinberg, max height 32 | 56 | 139 | 32 |
| Same, unlimited height | 56 | 136 | 104 |
| Same, flat, Floyd-Steinberg | 50 | 50 | 0 |
| Flat logo, Valley, Atkinson | 20 | 9 | 32 |
| Solid colour, flat | 1 | 1 | 0 |

Message counts scale with the message-length setting. For the dithered
photo above: 56 messages at 256 characters, 57 at 250, 71 at 200, 95 at
150, 143 at 100, 180 at 80, 242 at 60.

## Verified in game (2026-09-01)

- Minr chat delivers CJK characters (U+4E00 range) to `@prompt` unchanged.
- A 2,980-character alphabet constant survived the namespace import.
- MSC lists (including `list::range`) are capped at 1000 elements.
- Minr chat dropped one character from a run of eight identical ones in a
  250-character message; the per-message checksum caught it. Protocol v3
  makes such runs impossible.

## The alphabet size

Protocol v1 used 2,980 characters from U+4E00 and worked: every message it
produced passed its checksum in game. v2 grew the alphabet to 27,584 by
prefixing CJK Extension A, and from then on data messages failed their
checksums while the header still passed.

Two red herrings were ruled out along the way. Chat is not truncating: a
250-character message arrives as 250, and 200 as 200, and 80 as 80. Chat is
not substituting characters outside the alphabet either, or the check would
report a foreign character rather than a checksum mismatch.

The header passed because it could not fail. Under v5 it was a message of
its own, and its checksum total was `P + nMsgs`, around 30, so
`total % (N-1)` was that same number for any plausible `N`, and the three
characters it used sat at the very start and very end of the alphabet. A
data message sums hundreds of symbols into the millions, so its checksum
depends on the alphabet being exactly right everywhere. Under v6 the header
shares a message with a payload, so it is covered by a real checksum too.

v5 therefore reverted to the v1 alphabet, and v6 keeps it. 2,980 symbols
cannot hold 157^2, so P is 1 pixel per character and message counts roughly
double: 56 for a dithered photo at 256 characters, against 33 if the wider
alphabet could be used.
`importMapArt` refuses to start unless `alphaU.length()` is 2980 and says so
plainly, so a truncated import is caught before it turns into confusing
checksum failures.

## Feedback while pasting

Every accepted message plays `block.note_block.pling` at a pitch that climbs
from 0.5 to 2.0 across the whole paste, so a finished run is audible without
reading the counter, and a progress bar is printed alongside it. Failures
play `block.note_block.didgeridoo` at 0.5. The build prints a line every 32
columns and ends on `entity.player.levelup`.

## Still to verify

- Build speed with `@fast` on a dithered staircased image.
- That the noobline row renders row 0 with the intended tones.
- Whether a larger alphabet can be reintroduced (check the [diag] line).
