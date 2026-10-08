# D-185 redesign evidence

The screenshots and motion recordings behind the D-185 redesign (DECISIONS.md), saved here at Sushil's request
(2026-10-08) so they stay with the code. Nothing in this folder is served by the app or the website.

- **Before and after** files are one image: main before the phase on the left, the phase's branch on the right,
  the same walk and the same recorded reading. WebP, at 1x.
- **GIFs** are stepped from the real animations (each frame set exactly, then played at real speed), compressed to
  64 colours.
- **Score** is the design reviewer's final score for that screen (out of 100; the target was above 96). Rubric:
  hierarchy 15, type 10, colour 10, motion 15, brand 10, one hand 10, trust 10, consistency 10, performance 10.
- Width is the browser window in CSS pixels: 390 a typical phone, 1280 a computer.

## Phase 1: design system and app screens (PR #141, web-63)

Lighthouse mobile 100/100/100/100. The Phase 1 home drawing ran three passes, then stopped; Phase 2 replaced that
with a loop that plays while home is on screen.

| File | Screen | Theme | Width (px) | Score |
|---|---|---|---|---|
| [before-after-compare-390-dark.webp](phase1/before-after-compare-390-dark.webp) | Compare | dark | 390 | 97 |
| [before-after-compare-390-light.webp](phase1/before-after-compare-390-light.webp) | Compare | light | 390 | 97 |
| [before-after-data-390-dark.webp](phase1/before-after-data-390-dark.webp) | Your data | dark | 390 | 97 |
| [before-after-data-390-light.webp](phase1/before-after-data-390-light.webp) | Your data | light | 390 | 97 |
| [before-after-home-1280-light.webp](phase1/before-after-home-1280-light.webp) | Home on a computer | light | 1280 | 97 |
| [before-after-home-390-dark.webp](phase1/before-after-home-390-dark.webp) | Home | dark | 390 | 98 |
| [before-after-home-390-light.webp](phase1/before-after-home-390-light.webp) | Home | light | 390 | 98 |
| [before-after-household-390-dark.webp](phase1/before-after-household-390-dark.webp) | Household | dark | 390 | 98 |
| [before-after-household-390-light.webp](phase1/before-after-household-390-light.webp) | Household | light | 390 | 98 |
| [before-after-person-390-dark.webp](phase1/before-after-person-390-dark.webp) | Person editor | dark | 390 | 97 |
| [before-after-person-390-light.webp](phase1/before-after-person-390-light.webp) | Person editor | light | 390 | 97 |
| [before-after-scans-1280-light.webp](phase1/before-after-scans-1280-light.webp) | Your scans on a computer | light | 1280 | 98 |
| [before-after-scans-390-dark.webp](phase1/before-after-scans-390-dark.webp) | Your scans | dark | 390 | 98 |
| [before-after-scans-390-light.webp](phase1/before-after-scans-390-light.webp) | Your scans | light | 390 | 98 |
| [specimen-dark.webp](phase1/specimen-dark.webp) | Figtree at 13 px, as above | dark | 390 | not a screen |
| [specimen-light.webp](phase1/specimen-light.webp) | Figtree at 13 px: prices, pack names, ingredients, INS numbers, a nutrition table | light | 390 | not a screen |
| [home-enter-dark.gif](phase1/home-enter-dark.gif) | Home opening (motion) | dark | 390 | 98 |
| [home-enter-light.gif](phase1/home-enter-light.gif) | Home opening (motion) | light | 390 | 98 |
| [home-loop-dark.gif](phase1/home-loop-dark.gif) | Home's Scan here drawing, Phase 1 version (motion) | dark | 390 | 98 |
| [home-loop-light.gif](phase1/home-loop-light.gif) | Home's Scan here drawing, Phase 1 version: three passes, then still (motion) | light | 390 | 98 |

## Phase 2: the scan flow and the result (PR #142, web-64)

Lighthouse mobile 99/100/100/100 (main 100 in the same runs); layout shift 0 from "Check this pack" to the settled
result. The refusal, Send it to us and Thank you screens have no before: main's walk could not reach them.

| File | Screen | Theme | Width (px) | Score |
|---|---|---|---|---|
| [before-after-digit-check-390-light.webp](phase2/before-after-digit-check-390-light.webp) | Check the barcode | light | 390 | 98 |
| [before-after-front-review-390-light.webp](phase2/before-after-front-review-390-light.webp) | Front review | light | 390 | 98 |
| [before-after-front-review-ticked-390-light.webp](phase2/before-after-front-review-ticked-390-light.webp) | Front review, same pack ticked | light | 390 | 99 |
| [before-after-front-step-390-light.webp](phase2/before-after-front-step-390-light.webp) | Step 4, the front | light | 390 | 97 |
| [before-after-list-checking-390-light.webp](phase2/before-after-list-checking-390-light.webp) | A photo being checked | light | 390 | 98 |
| [before-after-list-review-390-light.webp](phase2/before-after-list-review-390-light.webp) | Ingredient list review | light | 390 | 98 |
| [before-after-list-step-390-light.webp](phase2/before-after-list-step-390-light.webp) | Step 2, the ingredient list | light | 390 | 97 |
| [before-after-lookup-wait-390-light.webp](phase2/before-after-lookup-wait-390-light.webp) | Looking the barcode up | light | 390 | 98 |
| [before-after-reading-1-390-light.webp](phase2/before-after-reading-1-390-light.webp) | Reading the label | light | 390 | 98 |
| [before-after-reading-2-390-light.webp](phase2/before-after-reading-2-390-light.webp) | Reading the label, later | light | 390 | 98 |
| [before-after-result-390-light.webp](phase2/before-after-result-390-light.webp) | The result arriving | light | 390 | 99 |
| [before-after-result-full-390-light.webp](phase2/before-after-result-full-390-light.webp) | The result, whole page | light | 390 | 98 |
| [before-after-result-settled-390-light.webp](phase2/before-after-result-settled-390-light.webp) | The result | light | 390 | 98 |
| [before-after-scan-drawn-390-light.webp](phase2/before-after-scan-drawn-390-light.webp) | Scan the barcode, no live reader | light | 390 | 98 |
| [before-after-scan-live-390-light.webp](phase2/before-after-scan-live-390-light.webp) | Scan the barcode, live camera | light | 390 | 97 |
| [before-after-tab-onthepack-390-light.webp](phase2/before-after-tab-onthepack-390-light.webp) | On the pack tab, whole page | light | 390 | 97 |
| [before-after-tab-whatsinside-390-light.webp](phase2/before-after-tab-whatsinside-390-light.webp) | What's inside tab, whole page | light | 390 | 98 |
| [before-after-table-review-390-light.webp](phase2/before-after-table-review-390-light.webp) | Table review | light | 390 | 97 |
| [before-after-table-step-390-light.webp](phase2/before-after-table-step-390-light.webp) | Step 3, the nutrition table | light | 390 | 97 |
| [before-after-tile-page-390-light.webp](phase2/before-after-tile-page-390-light.webp) | A finding's page | light | 390 | 98 |
| [after-reading-1-1280-light.webp](phase2/after-reading-1-1280-light.webp) | Reading on a computer, already the result's width (after only) | light | 1280 | 98 |
| [after-refusal-0-390-dark.webp](phase2/after-refusal-0-390-dark.webp) | First refusal (after only) | dark | 390 | 97 |
| [after-refusal-0-390-light.webp](phase2/after-refusal-0-390-light.webp) | First refusal (after only) | light | 390 | 97 |
| [after-refusal-1-390-dark.webp](phase2/after-refusal-1-390-dark.webp) | Second refusal, with Send it to us (after only) | dark | 390 | 97 |
| [after-refusal-1-390-light.webp](phase2/after-refusal-1-390-light.webp) | Second refusal, with Send it to us (after only) | light | 390 | 97 |
| [after-result-settled-1280-light.webp](phase2/after-result-settled-1280-light.webp) | The result on a computer (after only) | light | 1280 | 97 |
| [after-send-390-dark.webp](phase2/after-send-390-dark.webp) | Send it to us (after only) | dark | 390 | 97 |
| [after-send-390-light.webp](phase2/after-send-390-light.webp) | Send it to us (after only) | light | 390 | 97 |
| [after-sent-390-dark.webp](phase2/after-sent-390-dark.webp) | Thank you (after only) | dark | 390 | 99 |
| [after-sent-390-light.webp](phase2/after-sent-390-light.webp) | Thank you (after only) | light | 390 | 99 |
| [checking.gif](phase2/checking.gif) | A photo being checked: gold band, turning ring (motion) | light | 390 | 98 |
| [home.gif](phase2/home.gif) | Home's Scan here loop, Phase 2 version: plays while home is on screen (motion) | light | 390 | 98 (Phase 1 review) |
| [inside.gif](phase2/inside.gif) | What's inside: bars filling, cards rising (motion) | light | 390 | 98 |
| [photos-in.gif](phase2/photos-in.gif) | All photos in: the tick drawing (motion) | light | 390 | 98 |
| [reading.gif](phase2/reading.gif) | Reading: lines lighting up under the lens (motion) | light | 390 | 98 |
| [result.gif](phase2/result.gif) | The result arriving: cards rising after the people block (motion) | light | 390 | 99 |
| [review.gif](phase2/review.gif) | Review: photos arriving (motion) | light | 390 | 98 |
| [scanner.gif](phase2/scanner.gif) | Scanner corners and gold line (motion) | light | 390 | 97 |
| [step.gif](phase2/step.gif) | A photo step opening: step pill, example card, tick drawing (motion) | light | 390 | 97 |

## Phase 3: the website (web-65)

Lighthouse mobile on the website home, gzip as live, run in turn with main, 3 each: 100/100/100/100 in every run; LCP
1435 to 1448 ms (main 1517 to 1532, Accessibility 96), CLS 0. There is no GIF of the film: it plays only on a tap, and
this headless browser cannot play its H.264 file.
Before images are main at the same width and theme; the 360 px and 1280 dark images, and the reduced-motion still, are after only.

| File | Screen | Theme | Width (px) | Score |
|---|---|---|---|---|
| [after-about-top-1280-dark.webp](phase3/after-about-top-1280-dark.webp) | About, first view | dark | 1280 | 98 |
| [after-home-full-1280-dark.webp](phase3/after-home-full-1280-dark.webp) | Home, whole page | dark | 1280 | 98 |
| [after-home-top-1280-dark.webp](phase3/after-home-top-1280-dark.webp) | Home, first view | dark | 1280 | 98 |
| [after-home-top-360-dark.webp](phase3/after-home-top-360-dark.webp) | Home, first view | dark | 360 | 97 |
| [after-home-top-390-light-still.webp](phase3/after-home-top-390-light-still.webp) | Home, first view, reduced motion (still) | light | 390 | 97 |
| [after-how-top-1280-dark.webp](phase3/after-how-top-1280-dark.webp) | How we check, first view | dark | 1280 | 99 |
| [after-menu-360-dark.webp](phase3/after-menu-360-dark.webp) | The menu, open | dark | 360 | 97 |
| [after-privacy-top-1280-dark.webp](phase3/after-privacy-top-1280-dark.webp) | Privacy, first view | dark | 1280 | 97 |
| [before-after-about-top-1280-light.webp](phase3/before-after-about-top-1280-light.webp) | About, first view | light | 1280 | 98 |
| [before-after-about-top-390-dark.webp](phase3/before-after-about-top-390-dark.webp) | About, first view | dark | 390 | 98 |
| [before-after-about-top-390-light.webp](phase3/before-after-about-top-390-light.webp) | About, first view | light | 390 | 98 |
| [before-after-home-full-1280-light.webp](phase3/before-after-home-full-1280-light.webp) | Home, whole page | light | 1280 | 98 |
| [before-after-home-full-390-dark.webp](phase3/before-after-home-full-390-dark.webp) | Home, whole page | dark | 390 | 97 |
| [before-after-home-full-390-light.webp](phase3/before-after-home-full-390-light.webp) | Home, whole page | light | 390 | 97 |
| [before-after-home-top-1280-light.webp](phase3/before-after-home-top-1280-light.webp) | Home, first view | light | 1280 | 98 |
| [before-after-home-top-390-dark.webp](phase3/before-after-home-top-390-dark.webp) | Home, first view | dark | 390 | 97 |
| [before-after-home-top-390-light.webp](phase3/before-after-home-top-390-light.webp) | Home, first view | light | 390 | 97 |
| [before-after-how-full-1280-light.webp](phase3/before-after-how-full-1280-light.webp) | How we check, whole page | light | 1280 | 99 |
| [before-after-how-top-1280-light.webp](phase3/before-after-how-top-1280-light.webp) | How we check, first view | light | 1280 | 99 |
| [before-after-how-top-390-dark.webp](phase3/before-after-how-top-390-dark.webp) | How we check, first view | dark | 390 | 98 |
| [before-after-how-top-390-light.webp](phase3/before-after-how-top-390-light.webp) | How we check, first view | light | 390 | 98 |
| [before-after-menu-390-dark.webp](phase3/before-after-menu-390-dark.webp) | The menu, open | dark | 390 | 97 |
| [before-after-menu-390-light.webp](phase3/before-after-menu-390-light.webp) | The menu, open | light | 390 | 97 |
| [before-after-privacy-top-1280-light.webp](phase3/before-after-privacy-top-1280-light.webp) | Privacy, first view | light | 1280 | 97 |
| [before-after-privacy-top-390-dark.webp](phase3/before-after-privacy-top-390-dark.webp) | Privacy, first view | dark | 390 | 97 |
| [before-after-privacy-top-390-light.webp](phase3/before-after-privacy-top-390-light.webp) | Privacy, first view | light | 390 | 97 |
| [hero-1280-dark.gif](phase3/hero-1280-dark.gif) | The hero phone on a computer (motion) | dark | 1280 | 98 |
| [hero-390-light.gif](phase3/hero-390-light.gif) | The hero phone: scan, photograph, the result, sliding like pages, 9 s loop (motion) | light | 390 | 97 |
| [reveal-1280-light.gif](phase3/reveal-1280-light.gif) | Scrolling on a computer: the step cards and the film rise in (motion) | light | 1280 | 98 |
| [reveal-390-light.gif](phase3/reveal-390-light.gif) | Scrolling: How it works and the film rise in as they arrive (motion) | light | 390 | 97 |
