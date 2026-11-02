"""Seed-VC bridge: convert synthesised lines to the reference timbre."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from typing import List, Optional, Tuple

from .config import PROJECT_DIR


class VoiceConverter:
    """Wraps an external Seed-VC install (kept in its own venv so its heavy
    dependencies never touch the server environment)."""

    def __init__(self, cfg) -> None:
        self.cfg = cfg

    def python(self) -> str:
        p = getattr(self.cfg, "vc_python", "") or ""
        if not p:
            p = str(PROJECT_DIR / "seed-vc" / ".venv-vc" / "bin" / "python")
        return p

    def repo(self) -> str:
        r = getattr(self.cfg, "vc_dir", "") or ""
        return r or str(PROJECT_DIR / "seed-vc")

    def available(self) -> bool:
        return os.path.isfile(self.python()) and os.path.isfile(os.path.join(self.repo(), "inference.py"))

    def convert(self, pairs: List[Tuple[str, str]], ref: str) -> float:
        """Convert every (src, dst) pair with one model load. Returns 0..1 success."""
        if not self.available() or not pairs:
            return 0.0
        manifest = {
            "ref": os.path.abspath(ref),
            "files": [[os.path.abspath(a), os.path.abspath(b)] for a, b in pairs],
            "steps": int(getattr(self.cfg, "vc_steps", 25) or 25),
            "cfg": float(getattr(self.cfg, "vc_cfg", 0.7) or 0.7),
        }
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh)
        env = dict(os.environ)
        env.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        env.setdefault("HF_HUB_DISABLE_XET", "1")
        cmd = [self.python(), os.path.join(str(PROJECT_DIR), "tools", "seedvc_worker.py"), path]
        print("[vc] converting %d lines ..." % len(pairs), flush=True)
        proc = subprocess.run(cmd, cwd=self.repo(), env=env, capture_output=True, text=True)
        try:
            os.remove(path)
        except OSError:
            pass
        if proc.returncode != 0:
            print("[vc] failed: " + (proc.stderr or proc.stdout)[-400:], flush=True)
            return 0.0
        done = sum(1 for _, dst in pairs if os.path.isfile(dst) and os.path.getsize(dst) > 1000)
        return done / max(1, len(pairs))
