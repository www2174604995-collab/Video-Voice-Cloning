#!/usr/bin/env bash
#   TTS=indextts bash scripts/run_server.sh
#   TTS=xtts     bash scripts/run_server.sh
set -euo pipefail
cd "$(dirname "$0")/.."
. .venv/bin/activate

export PYTHONIOENCODING=utf-8
export COQUI_TOS_AGREED=1
export HF_ENDPOINT=https://hf-mirror.com
export HF_HUB_DISABLE_XET=1

cd server
exec python -m app --host 0.0.0.0 --port "${PORT:-8765}" --tts "${TTS:-indextts}" "$@"
