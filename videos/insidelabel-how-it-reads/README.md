# How InsideLabel checks a label (explainer video)

A 41 second product film, written as code with [HyperFrames](https://hyperframes.heygen.com)
and rendered to MP4. Two cuts of the same film:

| Cut | Size | For | Output |
|---|---|---|---|
| vertical | 1080 x 1920 (9:16) | Reels, Shorts, WhatsApp Status, Stories: **the main one**, it is mostly watched on phones | `renders/insidelabel-9x16.mp4` |
| landscape | 1920 x 1080 (16:9) | YouTube, the website, LinkedIn | `renders/insidelabel-16x9.mp4` |

Owner: Sushil. Built 2026-10-01 with Claude Code.

## The documents

| File | What it holds | Keep it current when |
|---|---|---|
| `README.md` | this page: what, how to build, versions | anything changes |
| `BRIEF.md` | the message, audience, story, and the **source of every word on screen** | a word on screen changes |
| `MOTION.md` | the look, motion and sound rules. **Read it before every build or edit** | the style changes |
| `AUDIT.md` | the check against Apple's HIG motion rules, and what was fixed | after a motion change |
| `CLAUDE.md` / `AGENTS.md` | instructions for an AI agent working here (same text) | the workflow changes |

## Build and render

Needs Node 22+, Python 3.11+, ffmpeg. HyperFrames runs through `npx` (pinned in `package.json`).

```bash
./make.sh vertical render      # build 9:16, check, render renders/insidelabel-9x16.mp4
./make.sh landscape render     # build 16:9, check, render renders/insidelabel-16x9.mp4
./make.sh vertical             # build and check only
npx hyperframes preview        # watch it in the browser (after a build)
```

`compositions/` and `index.html` are **generated** by `src/build_vertical.py` or
`src/build_landscape.py` (whichever ran last); edit `src/`, never them. Each render takes
about 70 to 90 s on a laptop-class CPU, all local, no account and no paid call.

The vertical cut zooms to two measured points. If the result or the blurry-photo screen
changes layout, re-measure: `MEASURE=1 ./make.sh vertical` (needs `playwright-core`; set
`PLAYWRIGHT_CORE` and `CHROMIUM_PATH` if they aren't found).

## Music

`assets/music.m4a` is an original track made by `src/music.py` (plain Python, no samples, so
it is free to use anywhere and needs no licence). 90 BPM in C, pad, plucked arpeggio, soft kick,
with sounds timed to the picture: the shutter clicks, a chime as the allergen card lands, a tap
on the tile. To remake it:

```bash
python3 src/music.py
ffmpeg -y -i assets/music.wav -af "pan=stereo|c0=c0|c1=c0,adelay=0|11,aecho=0.8:0.6:70|110:0.22|0.15,lowpass=f=9000,afade=t=in:d=0.6,afade=t=out:st=39.4:d=1.6,loudnorm=I=-16:TP=-1.5:LRA=11" -ar 44100 -c:a aac -b:a 192k assets/music.m4a
rm assets/music.wav
```

Loudness is -16 LUFS integrated, peaks under -1.5 dBTP (right for Instagram and YouTube).

## Layout

```
make.sh                 build, check, render one cut
src/build_vertical.py   the 9:16 film (scenes, app screens, timeline)
src/build_landscape.py  the 16:9 film (same story and timings)
src/music.py            the soundtrack
src/measure.mjs         measures zoom targets in a headless browser
assets/                 fonts (DM Sans, Bricolage Grotesque, OFL), app icon, GSAP, music
style-frames/           five real app screens the style is taken from
v1/                     the first version (a described explainer), kept for reference
compositions/, index.html   generated
renders/                MP4s (not committed; publish them)
```

## Versions

| Version | Date | What changed |
|---|---|---|
| v1 | 2026-10-01 | 54 s, 16:9, silent: five described steps, one sentence per scene. In `v1/`. |
| v2 | 2026-10-01 | Sushil: "more we are describing to user". Show, don't tell: the app plays on a phone, 2 to 4 words per beat, one decisive zoom per idea. 41 s. |
| v3 | 2026-10-01 | Sushil: "it will mostly be watched on phones". The 9:16 cut becomes the main one; the phone fills 80 % of the frame. |
| v4 | 2026-10-01 | An original soundtrack synced to the picture, in both cuts. Both cuts built from this one project. |

## Rules that come from the InsideLabel product

The film is user-facing, so the repo's wording rules apply to it (D-042/D-071): never
misleading, false, illegal, violation, toxic, dangerous, poison, safe, free from, healthy; no
brand judged; quote the label, don't characterise it; no em or en dashes. The pack shown is a
sample ("Sample biscuits") with no brand. Every sentence on screen has a source in `BRIEF.md`.
