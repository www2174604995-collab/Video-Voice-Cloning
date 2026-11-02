#!/usr/bin/env bash
# 一键部署 BiliSimul 服务端（Linux / 云 GPU）
#   bash scripts/setup_linux.sh [--no-xtts] [--no-indextts]
set -euo pipefail
cd "$(dirname "$0")/.."

PIP_INDEX="https://pypi.tuna.tsinghua.edu.cn/simple"
WANT_XTTS=1
WANT_INDEX=1
for arg in "$@"; do
  [ "$arg" = "--no-xtts" ] && WANT_XTTS=0
  [ "$arg" = "--no-indextts" ] && WANT_INDEX=0
done

echo "== 1/5 Python 环境"
if [ ! -d .venv ]; then python3 -m venv .venv; fi
. .venv/bin/activate
python -m pip install -U pip -i "$PIP_INDEX" >/dev/null

echo "== 2/5 PyTorch (cu121, 2.5.1)"
pip install torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu121

echo "== 3/5 应用依赖"
pip install -r server/requirements.txt -i "$PIP_INDEX"
pip install pypinyin -i "$PIP_INDEX"

if [ "$WANT_XTTS" = "1" ]; then
  echo "== 4/5 XTTS-v2"
  pip install coqui-tts==0.28.0 "transformers>=4.43,<5" -i "$PIP_INDEX"
  python tools/download_xtts.py || echo "  XTTS 权重下载失败，可稍后重跑"
fi

if [ "$WANT_INDEX" = "1" ]; then
  echo "== 5/5 IndexTTS-2"
  pip install --no-deps windextts -i "$PIP_INDEX"
  pip install jieba cn2an tiktoken safetensors wetext bitsandbytes -i "$PIP_INDEX"
  python -m windextts.download --out data/models/indextts2 --skip-qwen
fi

echo
echo "== 自检"
export PYTHONIOENCODING=utf-8 COQUI_TOS_AGREED=1 HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1
python - <<PYEOF
import sys
sys.path.insert(0, "server")
import torch
print("torch", torch.__version__, "cuda", torch.cuda.is_available())
if torch.cuda.is_available():
    print("gpu:", torch.cuda.get_device_name(0),
          round(torch.cuda.get_device_properties(0).total_memory / 1e9, 1), "GB")
from app.config import load
c = load()
print("config:", c.tts, c.asr_model, c.mt)
PYEOF
echo
echo "下一步:  TTS=indextts bash scripts/run_server.sh"
