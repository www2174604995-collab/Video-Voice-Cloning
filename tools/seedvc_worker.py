"""Batch voice conversion with Seed-VC using a single model load.

Run with the Seed-VC venv from inside the seed-vc checkout:

    .venv-vc/bin/python /path/tools/seedvc_worker.py manifest.json

manifest.json = {"ref": "ano.wav", "files": [["in1.wav", "out1.wav"], ...],
                 "steps": 25, "cfg": 0.7}
"""
import json
import os
import shutil
import sys
import types

HERE = os.getcwd()
sys.path.insert(0, HERE)

import inference  # noqa: E402  (lives in the seed-vc checkout)


def make_args(source, target, output, steps, cfg):
    return types.SimpleNamespace(
        source=source, target=target, output=output,
        diffusion_steps=steps, length_adjust=1.0, inference_cfg_rate=cfg,
        f0_condition=False, auto_f0_adjust=False, semi_tone_shift=0,
        checkpoint=None, config=None, fp16=True,
    )


def main() -> int:
    manifest = json.load(open(sys.argv[1], encoding="utf-8"))
    ref = manifest["ref"]
    steps = int(manifest.get("steps", 25))
    cfg = float(manifest.get("cfg", 0.7))
    files = manifest["files"]

    cache = {}
    original = inference.load_models

    def cached(args):
        if "models" not in cache:
            print("loading seed-vc models ...", flush=True)
            cache["models"] = original(args)
            print("models ready", flush=True)
        return cache["models"]

    inference.load_models = cached

    out_dir = os.path.dirname(files[0][1]) if files else "."
    os.makedirs(out_dir, exist_ok=True)

    for i, (src, dst) in enumerate(files):
        args = make_args(src, ref, out_dir, steps, cfg)
        before = set(os.listdir(out_dir))
        try:
            inference.main(args)
        except Exception as exc:
            print("FAIL %s: %s" % (src, exc), flush=True)
            continue
        new = [f for f in os.listdir(out_dir) if f not in before and f.endswith(".wav")]
        if not new:
            print("FAIL %s: no output" % src, flush=True)
            continue
        shutil.move(os.path.join(out_dir, new[0]), dst)
        print("ok %d/%d %s" % (i + 1, len(files), os.path.basename(dst)), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
