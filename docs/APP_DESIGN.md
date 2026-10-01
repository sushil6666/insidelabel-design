# The app's design: review and design system (branch `app-polish`, 2026-10-01)

Sushil, 2026-10-01: make the app (web/, served at /app/ and wrapped as the Play app
`ai.insidelabel.app.f`) look and feel as good as the best-rated apps, or better. This file is
step 1: every screen reviewed, the fixes ranked, and the design system the build uses. Step 2
(the build) and step 3 (the checks) are recorded at the end.

No other app's design, layout, icons or assets are copied. The principles come from the public
guidance listed in "Sources", each read on 2026-10-01; a number used here cites its page.

**How the screens were seen.** Every screen and state in `web/` was listed by reading `app.js`,
`lib.js` and `camera.js`, then walked in headless Chromium at 390 x 844, light and dark, through the
real UI, against the real server code. `/scan` answers were real `/scan` bodies built by the server
from recorded readings (no model call, no paid scan); the live scanner ran on Chromium's fake
camera with a stand-in barcode detector. Contact sheets: `docs/app-design/before-light-*.jpg` and
`before-dark-*.jpg` (46 screens each). Packs are invented ("Sample cream biscuits"); profiles
are You (avoids peanut), Mini (a child, avoids milk) and Pip (a baby).

---

## 1. The rules the design works inside

- **Words.** Every sentence about a pack comes from `lenses/screen.py` (D-091) and passes
  `tests/test_wording.py` (D-042, D-071). This branch changes no word in JS.
- **Allergens first** (D-060): the people block leads every result and is never delayed or hidden by
  motion.
- **No judgement in colour, icon or motion.** Colour repeats what the words already say (the
  stylesheet's own rule since D-110). No tick meaning "fine to eat", no celebration on a result, no
  score read in JS (D-064). No brand is judged.
- **Low friction** (Sushil): no new tap, step, prompt or screen in the scan flow. D-146's digit
  check stays exactly as merged.
- **Cheap phones first:** most users are on low-end Android. Motion uses transform and opacity only,
  and nothing comes from outside the app.

## 2. What matters most, across all screens (highest impact first)

| # | Finding | Evidence | Fix |
|---|---|---|---|
| 1 | **The scan waits feel empty.** "Looking up this pack" and "Reading the ingredient list" are a pulsing dot over a blank screen, with a seconds counter. The wait is the most anxious moment of the app. | sheets 2 and 3: `10-looking-up`, `17-working-reading` | A calm, honest wait: the two stages the app really knows (the photo going up, then the reading), an indeterminate bar (no percentage), the existing words and timer. |
| 2 | **Layout shift (CLS 0.106 on home, 0.111 on a result, above Google's 0.1 "good").** The footer sits at the top of an empty `main`, then jumps when the screen renders (0.074 of it); the font swap in the header adds 0.002. | Layout-shift sources measured at 4x CPU (section 6) | `main` reserves the screen height, so the footer starts below the fold; the swap shift is left (0.002). |
| 3 | **Tap targets under 48 x 48 dp** (Android's recommendation; WCAG 2.2 2.5.8's floor is 24 x 24 CSS px). Measured: the header pills 34 px tall; the footer links 18 px; the feedback rating labels 36 px; "More" summaries, "Report a mistake", "Done", "Cancel" and "Upload a photo" 44 px; source links 20 to 42 px; the catalogue hit's "Scan again" has no minimum at all. | `targets.js` audit, 9 screens | 48 px minimum everywhere; the header pills keep their look and get a 48 px hit area. |
| 4 | **Text fields' borders are 1.27:1** (`--line` on white). WCAG 2.2 1.4.11 asks 3:1 for what identifies a component. | contrast script (section 7) | A `--field-line` token: 3.35:1 light, 3.74:1 dark. |
| 5 | **No sense of moving between screens.** Each view swaps in at once and jumps to the top; nothing says "forward" or "back". | every screen | A short enter motion on the new screen (200 ms, opacity and a 12 px rise), never blocking input. |
| 6 | **Press feedback is uneven.** Buttons and the scan button sink on press; tiles move 1 px; answer chips, summaries, list rows and links do nothing. Apple: "Without a press state, a button can feel unresponsive". | code review of `app.css` | One press state for everything tappable. |
| 7 | **Icons are font glyphs** (✕ ! › ✓ ✗ •), drawn differently by every phone's font, misaligned in their discs. | sheets 3 and 4: tiles, additive badges | One set of inline SVG icons drawn for this app (section 8.7). |
| 8 | **The photo step's main action looks secondary.** "Take the ingredients photo" is an outline button; the filled button is "Check this pack", disabled until there is a photo. | sheet 2: `12-photo-empty` | The take-photo button carries the primary style until a photo is in; then "Check this pack" does. No new tap. |
| 9 | **Links in running text are the browser's blue** (purple once visited, which fails contrast on the dark background): "How we check", "Privacy" and the email on "Your data". | sheets 1 and 6 | One link colour, the brand green, underlined. |
| 10 | **Forms group badly.** A label sits 14 px under the paragraph above and 14 px over its field, the same gap as between groups, so labels float. | `01-join`, `40-report`, `43-feedback` | Label and field 6 px apart, groups 20 px apart. |
| 11 | **The live scanner's frame** is a plain rectangle with a dimmed surround; it doesn't say "put the barcode here", and nothing marks the moment a code is caught except the vibration (60 ms). | `09-scan-camera` | Corner guides with a slow scan line while looking; on a catch the guides close and the phone gives a 15 ms tap. Reduced motion: still guides, no line, no vibration. |
| 12 | **Type sizes drift**: 24 distinct font sizes (22 in rem, from .66rem to 2.3rem, and two in px), and the body is set in px, so a phone's own text-size setting can't scale it. | `app.css` | A 7-step type scale in rem (section 8.2). |
| 13 | **Dark mode is solid but flat**: card shadows vanish on the navy, borders are 1.7:1, and visited links go purple. | dark sheets | A lighter raised surface for cards in dark mode, the field border token, the link colour. |
| 14 | **Empty states are a sentence.** Compare with nothing added says "Nothing added yet." under the heading. | `38-compare-empty` | A small drawn illustration and the same words, in a card. |

## 3. Every screen and state

Ratings 1 to 5 (5: nothing to fix). H hierarchy, Sp spacing, Ty type, Co colour, Cn contrast, Tt tap
targets, Pr press feedback, Lo loading, Mo motion, Dk dark mode, Em empty and error states. "-": not
applicable.

| Screen (file prefix in the sheets) | H | Sp | Ty | Co | Cn | Tt | Pr | Lo | Mo | Dk | Em |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Invite code (`01-join`) | 4 | 3 | 4 | 4 | 3 | 3 | 3 | - | 2 | 4 | 4 |
| Before you start (`02-agree`) | 4 | 4 | 4 | 4 | 4 | 4 | 3 | 2 | 2 | 4 | 3 |
| Welcome, Who avoids it (`03`, `04`) | 4 | 3 | 4 | 4 | 4 | 3 | 3 | - | 2 | 4 | - |
| Household, person editor (`05`, `07`, `08`) | 3 | 3 | 4 | 4 | 3 | 3 | 3 | 2 | 2 | 4 | 3 |
| Home, first run (`06-home-empty`) | 4 | 4 | 4 | 4 | 4 | 3 | 4 | - | 2 | 4 | 3 |
| Home with history (`36`, `47`) | 3 | 3 | 4 | 4 | 4 | 3 | 3 | - | 2 | 4 | - |
| Live scanner (`09-scan-camera`) | 3 | 4 | 4 | 4 | 4 | 3 | 3 | 3 | 2 | 4 | 4 |
| Scanner without live reading (`48`) | 3 | 4 | 4 | 4 | 4 | 3 | 3 | - | - | 4 | 4 |
| Looking up, reading (`10`, `17`) | 3 | 2 | 4 | 4 | 4 | - | - | 2 | 2 | 4 | 4 |
| Digit check, D-146 (`11-digit-check`) | 5 | 4 | 5 | 4 | 4 | 5 | 4 | - | 2 | 4 | - |
| Photo step (`12` to `16`) | 2 | 3 | 4 | 4 | 4 | 3 | 3 | 3 | 2 | 4 | 4 |
| Result, first screen (`18-result-main`) | 4 | 3 | 4 | 4 | 4 | 3 | 3 | - | 2 | 4 | - |
| Result, chip open and More (`20`, `21`) | 4 | 3 | 3 | 4 | 4 | 3 | 2 | - | 2 | 4 | - |
| A tile's page (`22-tile-page`) | 4 | 4 | 4 | 4 | 4 | 3 | 3 | - | 2 | 4 | 4 |
| Toddler question (`23`) | 4 | 4 | 4 | 4 | 4 | 4 | 3 | - | 2 | 4 | - |
| Partial read, retake (`25`, `26`, `27`) | 4 | 4 | 4 | 4 | 4 | 4 | 3 | - | 2 | 4 | 4 |
| Read from a screen (`28`) | 4 | 3 | 4 | 4 | 4 | 4 | 3 | - | 2 | 4 | - |
| Supplement (`29`) | 4 | 3 | 4 | 4 | 4 | 4 | 3 | - | 2 | 4 | - |
| Catalogue hit (`35`) | 4 | 3 | 4 | 4 | 4 | 1 | 2 | - | 2 | 4 | - |
| Table offer and photo (`30`, `31`) | 4 | 4 | 4 | 4 | 4 | 4 | 3 | 3 | 2 | 4 | - |
| Photo-scan limit, D-148 (`32-limit`) | 3 | 4 | 4 | 4 | 4 | 4 | 3 | - | 2 | 4 | 3 |
| Errors (`33`, `34`, `46`) | 3 | 4 | 4 | 4 | 4 | 4 | 3 | - | 2 | 4 | 3 |
| Compare (`38`, `39`) | 3 | 3 | 4 | 4 | 4 | 3 | 3 | 2 | 2 | 4 | 2 |
| Report a mistake, problem, feedback (`40` to `43`) | 4 | 2 | 4 | 4 | 3 | 2 | 3 | - | 2 | 4 | 4 |
| Your data (`44`, `45`) | 3 | 3 | 4 | 3 | 3 | 3 | 3 | - | 2 | 3 | - |

### 3.1 Invite code (D-102), Before you start (D-105)
**First-time feel:** clear and short; the code box and one green button. "Before you start" reads as
a contract: five numbered rules, then a tick box, then a pale disabled button. **Fixes:** label 6 px
over its field (finding 10); the field border at 3:1 (4); the rules list's tick row at 48 px; a
skeleton instead of "Loading…" while the rules load; the screen enters with the shared motion.

### 3.2 Welcome and Who avoids it (D-069, D-127)
**Feel:** friendly; the question card ("Does anyone you shop for avoid a food...") is the right
first question. On "Who avoids it?" the two answers have different widths ("Me" full width, "A
child I shop for" its own width), which reads as one preferred answer. **Fixes:** equal full-width
answers; "Done" as a 48 px text button.

### 3.3 Household and the person editor (D-074, D-140)
**Feel:** tidy list; the editor is long (13 allergens) but plain. **Fixes:** list rows get a chevron
and a press state (they are links that look like text); the "Nickname" label is glued to the
paragraph above; radio and tick rows at 48 px; "How we check" link colour (9); the editor shows
blank while the allergen list loads (a skeleton instead).

### 3.4 Home (first run, and with history)
**Feel:** the green "Scan a pack" button is unmistakable, the right hero. With history the page
stacks the shop list, "Your scans" and "Recent scans", each a card of a different shape.
**Fixes:** "Recent scans" rows with a chevron and a press state; the progress bars animate from 0 only
when motion is allowed; the scan button's icon becomes a drawn barcode-and-frame icon.
**D-150's "How it works" film card (2026-10-01) was removed by D-151 the same day:** home is the scan button
first with nothing added; the film is on the website home only.

### 3.5 The live scanner (D-024, D-124)
**Feel:** the camera is there at once, which is good; the frame doesn't invite placing the barcode,
and a catch is felt (60 ms buzz) but not seen. **Fixes:** finding 11. The vibration drops to 15 ms
(a tap, not a buzz) and stays off under reduced motion. Chrome on Android needs a user gesture for
`navigator.vibrate` since version 60 (MDN browser-compat-data, read 2026-10-01): the person has
always tapped "Scan a pack" first, so it works where it should.

### 3.6 Looking up, reading (D-068, D-124)
**Feel:** honest (time passing, what a first read usually takes) but empty: a small dot in the top
third and white space below. **Fixes:** finding 1. The photo's upload is a stage the app can know
(the upload's own completion event), so the first stage reads "Sending the photo…" until the photo
is up, then "Reading the ingredient list…" (both sentences the app already uses). No percentage,
no invented steps. The 20-second "Taking longer than usual" line stays.

### 3.7 Digit check (D-146)
**Feel:** clear: big first 3 and last 4 digits, two answers. Kept exactly as merged: no change to
its words, buttons or order; only the shared enter motion and press states reach it.

### 3.8 The photo step (D-068, D-100, D-104, D-119)
**Feel:** a lot on one screen: the first-time card, the sample drawing, two ways to add a photo, the
optional front, the button at the bottom. The thing to do first doesn't stand out (finding 8).
After a photo: the preview, a green check line, and the "Is the whole list in this photo?" card.
**Fixes:** finding 8; the photo preview gets rounded corners and a calm enter; the check line's
glyph becomes an icon; "Upload a photo" at 48 px.

### 3.9 The result, first screen (D-060 to D-066, D-134)
**Feel:** strong. The people cards say who is affected in words and colour; the headline follows;
tiles read as "look at these". It is dense: cards, tiles, chips, the glance ring and two buttons
fill the screen with little air between groups, and "More" in a person card is plain text.
**Fixes:** the people block appears first and at once (no motion on it, D-060); the rest follows in
a short staggered reveal (40 ms apart, all done within about 0.3 s, interactive at once); tiles get
drawn icons (7); "More" gets a chevron that turns; the answer chips get a press state.

### 3.10 The result, opened (answer chip, More about this pack)
**Feel:** the chip's sentence appears under the chips with no transition, so the eye loses where it
came from; "More about this pack" opens a long list of further summaries. **Fixes:** the answer
panel and every opened summary fade in (opacity only); summaries get a chevron; summary rows at 48 px.

### 3.11 A tile's page (D-134)
**Feel:** calm and readable; "‹ Back to the result" is a small text link at the top. **Fixes:** the
back link becomes an icon and the same words at 48 px; the page enters from the right and leaves to
the right (direction says "deeper", "back").

### 3.12 Result variants
- **Toddler question (D-140):** good; buttons equal. Only the shared fixes.
- **Partial read and retake (D-062, D-037):** the amber card and one green button are clear. On the
  second refusal "Send it to us" appears; fine.
- **Read from a screen (D-130):** the warning card is in the right place; fine.
- **Supplement and other kinds (D-139, D-140):** the kind card's blue edge is the only colour cue;
  fine.
- **Catalogue hit (D-146):** "Not this pack? Scan again" is a muted line with a zero-height button
  (padding 0, min-height 0): the hardest target in the app. **Fix:** a 48 px target, same words.
- **Table offer (D-133):** fine; the table photo screen gets the photo step's fixes.

### 3.13 Photo-scan limit (D-148)
**Feel:** calm and complete; four lines and a button. A little bare. **Fix:** a small drawn
illustration (a pack with a clock, no colour that judges), the shared enter motion.

### 3.14 Errors and offline
"That didn't work" (busy, offline), "Sorry" (not found). **Feel:** plain but honest, with a retry
and the report-a-problem link (D-092). **Fixes:** the same small illustration style; nothing else.
Offline: the shell opens from the service worker; a scan offline says "No connection". Unchanged.

### 3.15 Compare (D-057, D-139)
**Feel:** functional; the empty state is a heading, a paragraph and "Nothing added yet." with a pale
disabled button under it (2 on empty states). "Comparing…" is a text line. **Fixes:** empty state as
a card with a drawn illustration and the same words; a skeleton while comparing; list rows with
48 px "Remove" and "Add" targets.

### 3.16 Report a mistake, Report a problem, Feedback, Send it to us
**Feel:** forms that work; spacing is the weak point (finding 10), and the 1 to 5 rating is five
small radios. **Fixes:** finding 10; the rating labels as 48 px pills (same radio inputs and words,
styled); field borders at 3:1.

### 3.17 Your data (D-129)
**Feel:** honest and complete; links in browser blue, and "Delete my data" sits beside "Done"
inline, cramped. **Fixes:** link colour; the two actions on their own rows; the delete button keeps
its red text (it is the one destructive action, and says so in words).

### 3.18 Shared chrome
**Header:** the name, the mark and two pills; pills 34 px tall (fix: 48 px hit area, same look).
**Footer:** four links 18 px tall (fix: 48 px tall, wrapped). **Focus:** a 3 px ring, visible
everywhere; with a sticky header a focused element can scroll under it (WCAG 2.2 2.4.11): fix with
`scroll-padding-top`.

## 4. Things judged and not done

- **The View Transitions API.** Chrome supports `document.startViewTransition` from version 111
  (MDN browser-compat-data, Android Chrome and WebView mirror it). While a view transition runs,
  the page shows captured snapshots under an overlay, and by default taps during it don't reach the
  new screen.
  A scan must never wait on motion (Sushil), so the app animates the new screen itself (opacity and
  transform on the incoming view): it is interactive from its first frame, and the next navigation
  simply replaces it, which makes every transition interruptible on every browser.
- **A framing guide inside the label photo.** The label photo is taken by the phone's own camera
  app (`<input capture>`), where the app can draw nothing. An in-app photo camera would be a new
  flow and a new way to fail; the sample drawing stays the guide.
- **Skeletons on the result.** A result appears when its answer arrives, all at once; a skeleton
  before it would sit over the honest wait screen and imply a layout before anything is read.
- **Haptics on anything but the barcode catch.** A buzz on a result could read as "good" or "bad".
- **Changing the palette.** The tokens are kept and refined (section 8.1), not replaced.
- **A "caught" moment on the scanner.** The lookup replaces the camera at once; showing the catch
  would mean holding the screen for it, which slows the scan. The 15 ms tap is the catch.
- **A fade on "More about this pack".** Measured: it took the slowest tap from 40 ms to 56 to 64 ms
  (its body is long), so that one panel opens without it. Smaller panels fade.
- **A skeleton for the person editor.** Its allergen list is cached on the phone after the first
  load, so the wait it would cover is a few milliseconds.

## 5. Sources (each read on 2026-10-01)

- Material Design 3 motion tokens, from Google's own source: `material-components-android`,
  `lib/java/com/google/android/material/motion/res/values/tokens.xml` (GitHub, main branch):
  durations short1 50 ms, short2 100, short3 150, short4 200, medium1 250, medium2 300, medium3 350,
  medium4 400, long1 450 to long4 600; easings standard `cubic-bezier(0.2, 0, 0, 1)`, standard
  decelerate `cubic-bezier(0, 0, 0, 1)`, standard accelerate `cubic-bezier(0.3, 0, 1, 1)`,
  emphasized decelerate `cubic-bezier(0.1, 0.7, 0.1, 1)`, emphasized accelerate
  `cubic-bezier(0.3, 0, 0.8, 0.2)`. (m3.material.io itself was not reachable from this session.)
- Android, "Make apps more accessible" (developer.android.com, last updated 2026-09-22): "we
  recommend that each interactive UI element have a focusable area, or touch target size, of at
  least 48dpx48dp".
- WCAG 2.2, from the W3C's source (`w3c/wcag`, `guidelines/sc/`): 1.4.3 Contrast (Minimum) "at
  least 4.5:1", large text 3:1; 1.4.11 Non-text Contrast "at least 3:1 against adjacent color(s)" for
  "visual information required to identify user interface components and states"; 2.5.8 Target Size
  (Minimum) "at least 24 by 24 CSS pixels" with its spacing and inline exceptions; 2.4.7 Focus
  Visible; 2.4.11 Focus Not Obscured (Minimum) "not entirely hidden due to author-created content";
  1.4.4 Resize Text "up to 200 percent without loss of content or functionality"; 2.3.3 Animation
  from Interactions (AAA) "can be disabled".
- Apple Human Interface Guidelines (developer.apple.com): Buttons, "a button needs a hit region of
  at least 44x44 pt" and "Always include a press state for a custom button. Without a press state,
  a button can feel unresponsive"; Motion, "Don't add motion for the sake of adding motion",
  "Make motion optional", "Aim for brevity and precision in feedback animations".
- Core Web Vitals thresholds, from Google's `web-vitals` library source (`GoogleChrome/web-vitals`,
  `src/onLCP.ts`, `onINP.ts`, `onCLS.ts`): good up to LCP 2500 ms, INP 200 ms, CLS 0.1.
  (web.dev itself was not reachable from this session.)
- MDN, "CSS and JavaScript animation performance" (`mdn/content` on GitHub): properties that don't
  trigger reflow or repaint, chiefly transform, can be animated off the main thread.
- MDN browser-compat-data (`mdn/browser-compat-data`): `Document.startViewTransition` Chrome 111;
  `Navigator.vibrate` on Chrome for Android needs a user gesture since Chrome 60.

## 6. Performance before the build

Measured in headless Chromium 141.0.7390.37 at 390 x 844, 4x CPU throttling (Chrome DevTools Protocol
`Emulation.setCPUThrottlingRate`), local server, median of 5 runs, the same harness before and after.

| Measure | Before |
|---|---|
| Home, cold load: LCP | 212 ms |
| Home, cold load: CLS | 0.106 |
| A result, cold load: LCP | 272 ms |
| A result, cold load: CLS | 0.111 |
| INP (slowest of 7 taps: two answer chips, More, a tile, back, home, Scan a pack) | 40 ms |
| "Check this pack" to the result on screen (answer already back) | 190 ms |
| JS and CSS shipped (gzip): app.js 24.7 KB, lib.js 5.4 KB, camera.js 1.8 KB, app.css 6.9 KB | 38.8 KB |

## 7. Contrast, measured

Every text pair in `app.css` passes 4.5:1 in both modes (lowest: `--muted` on `--bg` in light,
4.55:1). Below 3:1 for non-text: `--line` on white 1.34:1 and on the page 1.27:1 (light), 1.68:1
and 2.11:1 (dark), which matters for text fields; the amber tile edge on its fill is 1.88:1 in light,
but that edge only repeats the chip's words (decorative).

## 8. The design system

One source of truth: custom properties on `:root` in `web/app.css`, redefined for dark mode.

### 8.1 Colour (the D-110 palette, kept; additions marked new)

| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` | #fbf9ee (the manifest's) | #193043 (the Play app's dark bars) | page |
| `--surface` | #ffffff | #234058 | cards, fields |
| `--surface-2` (new) | #f4f2e6 | #2b4b64 | pressed rows, skeletons, raised dark cards |
| `--ink` / `--muted` | #244b6b / #57768c | #e0f2f6 / #a3c4d1 | text |
| `--line` | #c9e3ec | #3e6378 | dividers (decorative) |
| `--field-line` (new) | #6f8ca0 (3.35:1 on bg) | #7a9db1 (3.74:1 on surface) | text fields, tick boxes |
| `--brand` / `--brand-ink` | #048149 / #fcfcf8 | #66c189 / #042234 | actions, links |
| `--ring` | #008cba | #7dccda | focus |
| status pairs | `--stop`, `--unsure`, `--calm` and their `-bg` | as now | only beside words that say the same |

### 8.2 Type (rem, so a phone's text-size setting scales it)

| Token | Size | Use |
|---|---|---|
| `--fs-xs` | 0.75rem (12 px) | uppercase labels, chips |
| `--fs-sm` | 0.875rem (14 px) | secondary text, captions |
| `--fs-md` | 1rem (16 px) | body |
| `--fs-lg` | 1.125rem (18 px) | lead, card titles |
| `--fs-xl` | 1.375rem (22 px) | result headline |
| `--fs-2xl` | 1.75rem (28 px) | page titles |
| `--fs-3xl` | 2.25rem (36 px) | the D-146 digits |
Display face Bricolage Grotesque 800 for titles; DM Sans 400, 600, 700 for the rest (both
self-hosted since D-110). Line height 1.5 body, 1.15 titles.

### 8.3 Spacing (4 px base)
`--sp-1` 4, `--sp-2` 8, `--sp-3` 12, `--sp-4` 16, `--sp-5` 20, `--sp-6` 24, `--sp-8` 32 px. Label to
field 6 px; within a group 8 to 12; between groups 20; page gutter 16.

### 8.4 Shape
`--r-sm` 8 px (chips' inner parts, thumbnails), `--r-md` 12 (fields, small cards), `--r-lg` 16
(cards, buttons; the existing `--radius`), `--r-xl` 24 (the scan button), `--r-pill` 999.

### 8.5 Elevation
`--e-1` resting cards (the existing soft shadow); `--e-2` raised (the scan button, the sticky
header when scrolled). In dark mode shadows barely show, so a raised card also steps up to
`--surface-2`.

### 8.6 Motion (Material 3 tokens, section 5)
| Token | Value | Use |
|---|---|---|
| `--d-press` | 100 ms (short2) | press in and out |
| `--d-fast` | 150 ms (short3) | opening a panel, a chevron turning |
| `--d-enter` | 200 ms (short4) | a screen entering |
| `--d-reveal` | 250 ms (medium1) | each block of the result's reveal |
| `--stagger` | 40 ms | between revealed blocks, at most 6 |
| `--ease-standard` | cubic-bezier(0.2, 0, 0, 1) | presses, toggles |
| `--ease-enter` | cubic-bezier(0.1, 0.7, 0.1, 1) (emphasized decelerate) | anything arriving |
| `--ease-exit` | cubic-bezier(0.3, 0, 1, 1) (standard accelerate) | anything leaving |
Only `transform` and `opacity` animate. Under `prefers-reduced-motion: reduce` every duration is 0
and transforms are dropped; a cross-fade at most. Nothing animates the allergen block.

### 8.7 Icons
Drawn for this app on a 24 px grid: 2 px strokes, round caps and joins, `currentColor`, no
fill except a status disc behind a mark. Set: chevron right, chevron down, back, barcode in a
frame, camera, alert (!), cross (not permitted), check (a photo is clear), clock, pack. Always
`aria-hidden`; the words beside them carry the meaning. A check means only "this photo is
readable", never anything about the food.

### 8.8 Targets and focus
Every target at least 48 x 48 CSS px (a small visual element gets a larger invisible hit area);
focus ring 3 px `--ring`, offset 2 px; `scroll-padding-top` the header's height.

---

## 9. What was built (step 2, branch `app-polish`)

| Commit | What changed |
|---|---|
| 1 | This file: the review, the sources, the design system, the baseline numbers. |
| 2 | **The foundation.** Tokens on `:root` (type, spacing, shape, elevation, motion, `--surface-2`, `--field-line`); body text in rem; every target 48 px (the header keeps its look with 48 px hit areas; inline links get padding that moves no text); one link colour; labels 6 px over their field and 20 px under the group before; the rating as 48 px pills on one row; standalone buttons on their own row; one press state for everything tappable; `scroll-padding-top`; reduced motion turns every animation and press off. **CLS:** the footer waits for the first screen. |
| 3 | **Motion and icons.** Screens after the first enter with a 200 ms rise; a tile's page slides in from the right, and its result doesn't move when returned to; on a new result the people block is there at once and the rest follows 40 ms apart; opened panels fade in. `web/icons.js`: the app's own icons in place of the font glyphs; chevrons on every summary; small drawings on the limit, error and empty Compare screens. |
| 4 | **The scan wait.** For one photo, "Sending the photo…" until the upload finishes (XMLHttpRequest's upload event, for `/scan` only), then "Reading the ingredient list…"; a two-part track, no percentage. Checked against a real `/scan` that takes 3 s. |
| 5 | **The live scanner.** Corner guides, a slow scan line, the surround dimmed; the catch is a 15 ms tap, none under reduced motion. |
| 6 | **The photo step leads with its next action** (the take-photo button is filled until a photo is in, on the ingredients, front and table screens); chevrons on list rows; skeleton lines under "Loading…" and "Comparing…"; the home progress bars grow in. |
| 7 | **200% text and zoom** (WCAG 1.4.4), found while checking: the header, the answer chips, the tiles and the glance legend ran off the edge at 200%, on main as well. Fixed; the header stops being sticky under 300 px wide. |
| 8 | **No fade on "More about this pack"** (INP, section 10). |
| 9 | **Inline links at 48 x 48** (padding offset by a negative margin, so no word moves). |
| 10 | `APP_VERSION` web-33 and the service worker's `il-shell-33`, together (`icons.js` joined the offline shell in commit 3); this section, STATE.md. |

No word in JS changed: a script compared every string literal in `web/*.js` before and after;
the only removals are the glyphs ✓ ✗ ✕ › • and the "‹ " of "Back to the result", each replaced by
an icon; every addition is a class name, an icon name or path data. The one sentence reused in a
new place is "Sending the photo…", which the front photo already says.

## 10. Checks (step 3)

**Walks.** The whole flow in headless Chromium at 390 x 844 and 360 x 800, light and dark, with
reduced motion off and on (8 runs, 48 screens each, no step failed): a one-photo scan, a
three-part scan, a barcode hit ("Not this pack? Scan again"), the digit check, the limit screen, a
baby profile's lines and the toddler question, a refused read, a partial read, a screen read, a
supplement, busy and offline errors, Compare, the forms, "Your data". After the build:
`docs/app-design/after-light-*.jpg` and `after-dark-*.jpg` (390 x 844).

**D-060, checked frame by frame on a new result:** the people block and every ancestor are at
opacity 1 with no animation from the first frame; only the blocks after it reveal.

**Performance**, the same harness as section 6 (4x CPU, median of 9 runs; the 5-run medians before
are in section 6):

| Measure | Before | After |
|---|---|---|
| Home LCP | 196 ms | 188 ms |
| Home CLS | 0.106 | 0.002 |
| A result's LCP | 264 ms | 236 ms |
| A result's CLS | 0.111 | 0.002 |
| INP (slowest of 7 taps) | 40 ms | 40 ms |
| "Check this pack" to the result (mean) | 195 ms | 201 ms (within the spread, 163 to 238) |
| JS and CSS shipped, gzip | 38.8 KB | 45.7 KB (+6.9 KB: app.css +3.7, app.js +1.4, icons.js +1.3, lib.js +0.4, camera.js +0.1) |

Google's "good" thresholds (section 5): LCP 2500 ms, INP 200 ms, CLS 0.1.

**Accessibility.**
- Contrast: every text pair as in section 7; field borders 3.35:1 (light) and 3.74:1 (dark); the
  scan wait's finished segment 4.69:1 (light) and 6.18:1 (dark) against the page, 2.93:1 against the
  empty segment beside it in dark mode, where the stage's words carry the meaning.
- Targets: the audit (9 screens) finds nothing under 48 x 48 px except tick boxes inside 48 px rows
  (the row is the target), labels of text fields (the field is the target) and the header's
  visuals, whose hit areas are 48 px.
- 200%: browser zoom 200% (a 195 px viewport) and a 32 px root font, 11 screens each: nothing
  scrolls sideways.
- Reduced motion: no animation, no press transform, no scan line sweep, no vibration.
- Focus: the 3 px ring everywhere; `scroll-padding-top` keeps it clear of the header.

**Offline:** the shell (with `icons.js`) loads from the service worker with the network off.
