
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "server"))

os.environ.setdefault("COQUI_TOS_AGREED", "1")
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


def main() -> int:
    from app.config import load
    from app.backends.tts import XTTS

    cfg = load()
    eng = XTTS(cfg)
    print("model dir:", eng.local_dir())
    print("loading ... (CPU 大约 20~60 秒)")
    eng.load()
    print("OK  ", eng.detail, " sample_rate =", eng.sr)
    tts = eng._tts
    print("multi_speaker:", getattr(tts, "is_multi_speaker", "?"), " cloning:", getattr(tts.synthesizer.tts_model.config, "supports_cloning", "?"))
    print("output_sample_rate:", tts.synthesizer.output_sample_rate)
    return 0


if __name__ == "__main__":
    sys.exit(main())
