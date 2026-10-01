# Motion audit against Apple's HIG "Motion" page (read 2026-10-01)

Source: developer.apple.com/design/human-interface-guidelines/motion (page JSON). The rules
that apply to a rendered video, and what this film does about each.

| HIG rule | Before | Verdict | Change |
|---|---|---|---|
| Add motion purposefully; don't add motion for its own sake | The two background glows drifted for the whole film, meaning nothing | Failed | Removed: the ground is still |
| Avoid motion at the edges of the field of view | The drifting glows sat at the top corners | Failed | Same fix |
| Give people a stationary frame of reference | Ground drifted, picture side pushed 3 % | Partly | Ground still, brand mark still, push cut to 2 % on the picture side only |
| Make motion optional: never the only way to say something | Every step is said in words; the scan line and blue chips repeat "a second reader checks" | Pass | None |
| Realistic motion that matches expectations | Arrivals rise and fade, exits fade, one short shutter flash, the lens moves onto the label | Pass | None |
| Brevity and precision | Entrances 0.6 s, flash 0.12 s, no bounce or overshoot | Pass | None |
| Use fades to relocate things | Scene changes are fades, no slides or spins | Pass | None |
| A steady 30 to 60 fps | Rendered at 30 fps | Pass | None |
| Don't make people wait for motion | The "can't confirm" scene had 6 s for about 35 words | Failed | Extended to 7 s (film is now 54 s) |

Not applicable to a video: cancelling motion, animated SF Symbols, frequent UI interactions,
visionOS. A video can't follow the viewer's Reduce Motion setting; a cross-fade-only cut is
possible if wanted.
