
"""Fetch the XTTS-v2 weights into data/models/xtts_v2 (cross platform fallback).

Windows 用户直接用 install-xtts.bat（curl 更快）；这个脚本是给没有 curl 的环境用的。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "data", "models", "xtts_v2")
FILES = ["config.json", "vocab.json", "speakers_xtts.pth", "mel_stats.pth", "dvae.pth", "model.pth"]

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("COQUI_TOS_AGREED", "1")


def main() -> int:
    from huggingface_hub import hf_hub_download

    os.makedirs(DEST, exist_ok=True)
    print("endpoint:", os.environ["HF_ENDPOINT"])
    for name in FILES:
        print(" ->", name, flush=True)
        path = hf_hub_download("coqui/XTTS-v2", name, local_dir=DEST)
        print("    ok", os.path.basename(path), flush=True)
    print("done ->", DEST)
    return 0


if __name__ == "__main__":
    sys.exit(main())
