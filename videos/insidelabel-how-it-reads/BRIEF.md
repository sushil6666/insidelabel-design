---
workflow: faceless-explainer
flow: automation
storyboard: no
message: "One photo: an AI reads the pack, fixed rules decide, and your avoid list comes first."
destination: shorts
aspect: 1080x1920
language: en
audience: "Indian shoppers, especially allergy households and parents of young children"
length: 41s
angle: how-to
---

## Intent

A short product film of how InsideLabel checks a pack, made to be watched on a phone (the
9:16 cut is the main one; a 16:9 cut exists for YouTube and the website). The app plays on a
phone and shows each step; the words on screen name the step in 2 to 4 words and never
describe what the picture already shows (Sushil, 2026-10-01: "more we are describing to
user"). Calm, clear and trustworthy; it should feel like the app itself.

## Story (both cuts, same timings)

| Time | On the phone | Words |
|---|---|---|
| 0 to 5 s | (no phone) a full back-of-pack ingredient list | "Can you find the milk?" |
| 5 to 11 s | the label shrinks into the camera, where the photo holds the ingredients and the nutrition table; shutter; "Sending the photo…", "Reading the ingredient list…" | "Ingredients and table." |
| 11 to 17 s | three lines quoted from the label each get the rule's tag | "AI reads." / "Rules decide." |
| 17 to 25 s | the result (D-153): the deep panel with the person line first (zoom), then the headline, the not-permitted tile, "Worth knowing (2)" and "Holding another pack? Scan it to compare" | "Your avoid list first." |
| 25 to 31 s | a tile is tapped; its page quotes the label | "We quote the label." |
| 31 to 37 s | a blurry photo; the amber "couldn't read" card | "Blurry photo?" / "We won't guess." |
| 37 to 41 s | (no phone) logo | "Read the label for your family.", insidelabel.ai |

## Customizations

- Style comes from the app, not a preset: `MOTION.md`, read before every build.
- Real fonts from the InsideLabel repo's `web/fonts` (OFL), local files.
- An original soundtrack, synced to the picture (`src/music.py`, see README).

## Notes: the source of every word on screen

Nothing on screen is invented. The pack ("Sample biscuits", no brand) is an illustration; the
ingredient list is a sample in the format packs print.

| On screen | Source (InsideLabel repo) |
|---|---|
| "Can you find the milk?" | the hook, over the sample pack's own ingredient list |
| "Ingredients and table." | the app's photo ask: "Photograph the ingredients and the nutrition table" (`web/app.js`, `photo`; Sushil, 2026-10-03) |
| The nutrition table in the viewfinder (Energy 489 kcal ... Sodium 310 mg) | the sample pack's own table, made up like its ingredient list (no real product) |
| "Sending the photo…", "Reading the ingredient list…" | `web/app.js` waiting stages |
| "The first read of a pack takes about 8 to 15 seconds. Once a pack is in our catalogue, its barcode gives the result at once." | the app's waiting screen (`style-frames/2-reading.png`) |
| "AI reads." / "Rules decide." | D-004; `web/site/how.html` ("An AI reads the words printed on the pack. It never decides anything.") |
| "Rules checked against FSSAI's regulations." | `web/site/how.html` ("our tables, which are checked against FSSAI's regulations"); D-086 |
| Tags: "On your avoid list", "Worth knowing", "Not permitted in India" | the result's own words (`lenses/allergens.py`, `lenses/screen.py`, `web/site/how.html` glossary) |
| "Contains milk. It's on your avoid list." | `lenses/allergens.py` `parent_text`, state `contains`, own profile |
| "Has Potassium bromate, an additive with higher concern.", the not-permitted tile, "Worth knowing (2)", "Holding another pack? Scan it to compare" | the app's result screen after D-153 (`lenses/screen.py` headline; `web/app.js` `result`) |
| The tile page for Potassium bromate (flour treatment 924a) | the app's tile page (`style-frames/4-tile-page.png`) |
| "We quote the label." | CLAUDE.md: "Quote the label; don't characterise it." |
| "Blurry photo?" / "We won't guess." | `web/site/how.html`: "When the photo is hard to read, we say we can't confirm, rather than guess." |
| "We couldn't read the label clearly enough to check for milk. Please retake the ingredients photo." | `lenses/allergens.py`, state `cannot_confirm` |
| "We could read only part of the ingredient list.", "Part of the ingredient list was cut off…", "Retake the ingredients photo" | the app's partial-read screen (`style-frames/5-cannot-confirm.png`) |
| "Read the label for your family." | `web/site/index.html` h1 (Sushil, 2026-10-03) |

Rules: no em or en dashes; never say misleading, false, illegal, violation, toxic, dangerous,
poison, safe, free from, healthy (D-042/D-071); never judge a brand; no profile nickname; no
paid calls; render locally.
