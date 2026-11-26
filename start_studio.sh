#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then python3 -m venv .venv; fi
if [ ! -f .venv/.studio_v1 ]; then .venv/bin/python -m pip install -r requirements.txt; touch .venv/.studio_v1; fi
.venv/bin/python server.py --open
