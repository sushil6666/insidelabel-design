#!/usr/bin/env bash
# One-time tidy. Read it before running it.
set -e

# 1. Stale duplicate data tables at the repo root. engine.py loads data/ only.
#    The root copies predate the additive_class_words fix, so editing one has
#    no effect and reading one gives you the pre-fix table. Two sources of
#    truth for the moat data is worse than one imperfect source.
echo "== stale root data tables (engine reads data/ only)"
for f in additives.json normalization.json nova_markers.json; do
  if [ -f "$f" ] && [ -f "data/$f" ]; then
    if diff -q "$f" "data/$f" >/dev/null 2>&1; then echo "   $f  (identical to data/$f)"
    else echo "   $f  DIFFERS from data/$f — check before deleting"; fi
  fi
done
echo "   -> rm additives.json normalization.json nova_markers.json"

# 2. Predictions from earlier prompt/model versions, unstamped and unusable
#    as evidence for anything.
echo
echo "== stale predictions"
ls predictions/*.json 2>/dev/null | grep -Ev 'limca-pet-2250' || true
echo "   -> keep only ids that have a matching gold/ file"

# 3. Stray uploads and the superseded smoke test.
echo
echo "== stray files"
for f in limca.png limcaa.png test_gemini_vision.py; do [ -f "$f" ] && echo "   $f"; done

echo
echo "Nothing deleted. Run the commands above yourself once you agree."
