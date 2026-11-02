"""End-to-end check: boot a server, stream a sample, verify subtitles + audio.

    python tests/e2e.py                 # mock backends (fast, no models)
    python tests/e2e.py --real          # real asr/mt/tts (downloads models)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable


def free_port() -> int:
    import socket

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


PORT = free_port()


def wait_health(timeout=240.0) -> dict:
    """Wait until the server is up *and* its models finished warming up."""
    deadline = time.time() + timeout
    last = None
    info = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=3) as r:
                info = json.loads(r.read().decode("utf-8"))
            if info.get("warmup") or info.get("warmup_error"):
                return info
        except Exception as exc:  # noqa: BLE001
            last = exc
        time.sleep(0.5)
    if info is not None:
        return info  # warmup disabled -> serve anyway
    raise SystemExit(f"server did not become healthy: {last}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--real", action="store_true")
    ap.add_argument("--asr-model", default="tiny")
    ap.add_argument("--mt", default="", help="empty = use server/config.yaml")
    ap.add_argument("--tts", default="edge")
    args = ap.parse_args()

    sample = os.path.join(ROOT, "data", "samples", "zh.wav")
    if not os.path.exists(sample):
        subprocess.check_call([PY, os.path.join(HERE, "make_sample.py"), sample, "--lang", "zh"])

    cmd = [PY, "-m", "app", "--port", str(PORT), "--log-level", "INFO"]
    if args.real:
        cmd += ["--asr", "faster_whisper", "--asr-model", args.asr_model, "--tts", args.tts]
        if args.mt:
            cmd += ["--mt", args.mt]
    else:
        cmd += ["--asr", "mock", "--mt", "mock", "--tts", "mock"]
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    print("starting:", " ".join(cmd))
    proc = subprocess.Popen(cmd, cwd=os.path.join(ROOT, "server"), env=env)
    try:
        info = wait_health()
        print("health:", json.dumps(info.get("backends"), ensure_ascii=False))
        out = os.path.join(ROOT, "data", "out", "e2e.wav")
        code = subprocess.call(
            [
                PY,
                os.path.join(HERE, "ws_client.py"),
                sample,
                "--url",
                f"ws://127.0.0.1:{PORT}",
                "--target",
                "en",
                "--out",
                out,
                "--fast",
                "--drain",
                "90",
            ],
            cwd=ROOT,
            env=env,
        )
        print("client exit:", code)
        print("output exists:", os.path.exists(out), os.path.getsize(out) if os.path.exists(out) else 0, "bytes")
        return 0 if code == 0 else code
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
