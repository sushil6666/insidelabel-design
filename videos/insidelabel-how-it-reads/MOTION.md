# MOTION.md: how an InsideLabel video looks and moves

**Read this file before every build or edit of a composition in this project.** It is the
style; the same prompt without it picks its own look. It covers both cuts (9:16 main, 16:9)
and the sound. Sources: `docs/APP_DESIGN.md` section 8
and the `:root` tokens in `web/app.css` (InsideLabel repo, 2026-10-01), plus the five frames
in `style-frames/`, which are real screens of the app.

## The five frames, and what each one teaches

| Frame | Take from it |
|---|---|
| `1-home.png` | The one big green action (`--brand`, radius 24, white text, a drawn icon at left). Cream page with soft mint and blue glows in the corners. |
| `2-reading.png` | Waiting looks calm: an icon in a pale disc, a thin two-part progress bar, a display-face title, muted body text that tells the truth about time ("about 8 to 15 seconds"). |
| `3-result.png` | The result's grammar: tinted cards with a 6 px left bar in the status colour, a tiny uppercase label (YOU), then one bold sentence. Below: a display-face headline, then tiles with a status disc, a title, a coloured chip line and a chevron. |
| `4-tile-page.png` | Detail page: small uppercase headings (WHAT IT IS, ON THE LABEL), a status pill, a red-barred notice; the label quoted in curly quotes, never characterised. |
| `5-cannot-confirm.png` | Uncertainty has its own colour (`--unsure`, amber) and its own words; it is never dressed up as green. |

## Colour (light theme only for the video)

| Token | Hex | Use in the video |
|---|---|---|
| bg | #fbf9ee | every frame's ground |
| surface | #ffffff | cards, the phone |
| ink | #244b6b | titles and body text |
| muted | #57768c | secondary text, captions |
| line | #c9e3ec | dividers, empty bars |
| brand | #048149 | the scan action, the brand mark, emphasis words |
| accent / mint | #6dc88f / #c4f6d4 | glows, progress fill |
| stop / stop-bg | #c92324 / #ffe5e0 | "Contains", "Not permitted in India" |
| unsure / unsure-bg / unsure-line | #6c380d / #ffefcd / #f59e3b | can't confirm, worth knowing |
| calm / calm-bg | #194860 / #d5f7f4 | not listed |
| ring | #008cba | the second reader's highlight |

Hero glow: `radial-gradient(60% 60% at 15% 10%, rgba(196,246,212,.7), transparent 70%)` plus a
pale blue one top right. Status colours appear only beside words that say the same thing.

## Type

- Display: **Bricolage Grotesque 800** for titles (line height 1.15, letter spacing -0.01em).
- Body: **DM Sans** 400 / 600 / 700 (line height 1.4 at video sizes).
- Uppercase labels: DM Sans 700, letter spacing 0.06em, muted.
- Words on screen: Bricolage 800, 100 px (9:16, centred above the phone) or 112 px (16:9, left
  of the phone), 2 to 4 words, the payoff word in `--brand` green.
- On the phone the app keeps its own sizes (17 px card sentence, 15 px tiles) scaled 1.795x
  (9:16) or 1.159x (16:9). Fonts load from `assets/fonts/` (local files; no network at render).

## Shape and depth

Radius 16 on cards and buttons (40 at video scale), 24 on the scan button (60 at video scale),
pills 999. Shadow: `0 2px 4px rgba(36,75,107,.06), 0 30px 80px -30px rgba(36,75,107,.18)`.
Icons: 2 px strokes scaled up (5 px at video scale), round caps, `currentColor`.

## Motion

The app's curves, slowed for a screen people watch rather than tap:

| App token | App value | Video value | Use |
|---|---|---|---|
| ease-enter | cubic-bezier(.1,.7,.1,1) | same (GSAP `CustomEase` not needed: use `power3.out` / `expo.out` as the stand-in) | anything arriving |
| ease-standard | cubic-bezier(.2,0,0,1) | `power2.inOut` | moves, morphs |
| ease-exit | cubic-bezier(.3,0,1,1) | `power2.in` | anything leaving |
| d-enter | 200 ms | 0.6 s | a block arriving |
| d-reveal | 250 ms | 0.7 s | each block of a result |
| stagger | 40 ms | 0.12 s, at most 6 items | lists, tiles |

Rules carried over from the app:
- Only transform and opacity move (plus clip-path for a wipe). Arrivals rise 24 to 40 px and fade
  in; nothing bounces, nothing overshoots, no elastic.
- **The allergen card never performs.** It fades in with a small rise and holds still; no
  pulse, shake or flash. It is the most important sentence on screen.
- A tick means only "this photo is readable", never anything about the food.
- Every frame holds still long enough to read every word twice (about 3 s per sentence).
- Show, don't tell (v2): the phone shows the flow; words on screen are 2 to 4 per beat, never
  a sentence that describes what the picture already shows.
- One idea moves at a time. The camera never drifts: it makes one decisive zoom (power3.inOut,
  about 1 s) to the one thing that matters, holds still, then zooms back. The ground never moves.
- The phone sits in the same place in every scene, so scene cuts are seamless.

## Layout per cut

| | 9:16 (main) | 16:9 |
|---|---|---|
| Phone | 730 x 1504 at (175, 420), bleeds off the bottom | 480 x 980 at (1060, 50) |
| Words | centred band, y 40 to 400 | left column, x 140, 720 wide |
| Zooms | 1.25x to 1.3x (the phone is already big); the label quote gets a mint marker sweep instead | 1.6x to 1.7x |
| "Rules decide." | the phone steps down out of the way, the rows stack in the middle, the phone returns | rows sit left of the phone |

Keep the phone in the same place in every scene of a cut. Zoom targets are measured
(`src/measure.mjs`), never guessed.

## Sound

- Original music only (`src/music.py`): calm, light, 90 BPM in C; no samples, no stock tracks.
- It follows the picture: the hook is pad only; the arpeggio starts as the phone arrives; a soft
  kick from "AI reads"; it resolves on the end card and fades.
- Small sounds mark real actions only: the shutter (6.6 s, 32.2 s), the tap on the tile
  (25.95 s), a two-note chime as the allergen card lands (17.55 s). No whooshes on cuts.
- -16 LUFS integrated, peaks under -1.5 dBTP. It must also work muted: the words carry the story.

## Words

Quote the app and the label; never characterise. Never: misleading, false, illegal, violation,
toxic, dangerous, poison, safe, free from, healthy. No em or en dashes. No brand judged, no
competitor imitated, no profile nickname (say "your avoid list").
