# Motion audit against Apple's HIG "Motion" page

Source: developer.apple.com/design/human-interface-guidelines/motion (the page's JSON, read
2026-10-01). Also checked against HyperFrames' own motion doctrine (smooth over bouncy,
sequential reveal, no drifting camera, velocity-matched cuts). Re-run this audit after any
motion change and add a section.

## Current film (v4, both cuts), 2026-10-01

| Rule | What the film does | Verdict |
|---|---|---|
| Add motion purposefully; not for its own sake | Every move is an action in the app (label into the camera, shutter, tap, screen change) or points at the one thing that matters (a zoom, a marker sweep) | Pass |
| Avoid motion at the edges of view | The ground and the glows never move; nothing enters from the edges except the phone, once | Pass |
| A stationary frame of reference | The phone sits in the same place in every scene of a cut; the ground is still | Pass |
| Don't make motion the only way to say something | Every step is named in words; the music and sounds repeat the picture, and the film works muted | Pass |
| Realistic motion | A tap compresses the tile, pages slide in like the app's navigation, the shutter flashes once | Pass |
| Brevity and precision | Entrances 0.55 to 0.6 s, power3 ease, no bounce or overshoot; zooms about 1 s, then a hold | Pass |
| Use fades to relocate | Screens cross-fade; the label morphs into the camera and fades | Pass |
| A steady 30 to 60 fps | 30 fps | Pass |
| Don't make people wait | Every word holds at least 2.5 s; the longest card (the amber one) holds 3.5 s zoomed | Pass |
| The allergen card never performs (MOTION.md) | It fades in with a 14 px rise and holds still | Pass |

Not applicable to a video: cancelling motion, animated SF Symbols, frequent UI interactions,
visionOS. A video can't follow the viewer's Reduce Motion setting.

## v1 (2026-10-01), for the record

| Rule | Before | Verdict | Change |
|---|---|---|---|
| Purposeful motion | The background glows drifted for the whole film | Failed | Removed |
| Motion at the edges | The drifting glows sat at the top corners | Failed | Same fix |
| Stationary frame of reference | Ground drifted, the picture side pushed 3 % | Partly | Ground still, push cut to 2 %; v2 removed the push entirely |
| Don't make people wait | The "can't confirm" scene had 6 s for about 35 words | Failed | 7 s; v2 cut the words to 4 |
