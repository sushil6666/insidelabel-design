#!/usr/bin/env bash
# Build, check and render one cut. Read MOTION.md before changing anything.
#   ./make.sh landscape            build 16:9 and run the HyperFrames check
#   ./make.sh vertical render      build 9:16, check, render renders/insidelabel-9x16.mp4
#   MEASURE=1 ./make.sh vertical   re-measure the zoom points first (needs playwright-core)
# compositions/ and index.html are generated: edit src/, never them.
set -euo pipefail
cd "$(dirname "$0")"
fmt="${1:?landscape or vertical}"
case "$fmt" in
  landscape) out=renders/insidelabel-16x9.mp4; python3 src/build_landscape.py ;;
  vertical)
    out=renders/insidelabel-9x16.mp4
    python3 src/build_vertical.py
    if [ "${MEASURE:-0}" = 1 ]; then
      pts=$(node src/measure.mjs '{"c3":["c3-allergen"],"c5":["c5-ucard"]}' |
            python3 -c "import json,sys; d=json.load(sys.stdin); print(json.dumps({k: v for c in d.values() for k, v in c.items()}))")
      echo "zoom points: $pts"
      python3 src/build_vertical.py "$pts"
    fi ;;
  *) echo "landscape or vertical" >&2; exit 2 ;;
esac
[ -f assets/music.m4a ] || { echo "assets/music.m4a missing: run python3 src/music.py and the ffmpeg line in README.md" >&2; exit 1; }
npx hyperframes check
if [ "${2:-}" = render ]; then
  npx hyperframes render --skill=faceless-explainer --quality high --output "$out"
fi
