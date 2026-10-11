#!/usr/bin/env bash
# The "Play" build of a Game Studio game's Project: one self-contained,
# playable page. See play_build.py.
set -euo pipefail
exec python3 "$(cd "$(dirname "$0")/.." && pwd)/play_build.py"
