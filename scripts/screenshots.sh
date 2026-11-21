#!/usr/bin/env bash
# Roborazzi screenshot goldens of :app (M1-03). Exact match, no tolerance (the options live in the test helper).
# Usage: scripts/screenshots.sh verify   fail on any pixel difference from the goldens in app/src/test/screenshots
#        scripts/screenshots.sh record   rewrite the goldens (a PR that changes them needs the golden-update label)
set -euo pipefail
cd "$(dirname "$0")/.."

DIFFS=app/build/outputs/roborazzi

case "${1:-} ${2:-}" in
  "verify ")
    rm -rf "$DIFFS"
    if ! ./gradlew -q --console=plain :app:verifyRoborazziDebug; then
      echo "screenshots: verify failed; actual and compare images are in $DIFFS (CI uploads them as screenshot-diffs)"
      exit 1
    fi
    ;;
  "record ")
    ./gradlew -q --console=plain :app:recordRoborazziDebug
    ;;
  *)
    echo "Usage: scripts/screenshots.sh verify|record" >&2
    exit 2
    ;;
esac
