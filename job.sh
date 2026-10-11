#!/bin/bash
# Game Studio, every minute on the server:
# - keeps the character queue moving (design_queue.py);
# - syncs each game with its Project, so edits made in Projects reach the studio
#   and the other way round (game_project.py);
# - brings players' playtest notes from each game's app (playtest_notes.py).
cd "$(dirname "$0")" || exit 1
python3 design_queue.py
status=$?
python3 game_project.py sync "${APP_ID:-12}" >/dev/null || status=1
python3 playtest_notes.py "${APP_ID:-12}" || status=1
exit $status
