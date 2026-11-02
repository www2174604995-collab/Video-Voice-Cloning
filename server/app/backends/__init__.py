from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from ..config import Config


@dataclass
class Backends:
    asr: Any
    mt: Any
    tts: Any

    def describe(self) -> Dict[str, Any]:
        return {
            "asr": getattr(self.asr, "name", "unknown"),
            "asr_detail": getattr(self.asr, "detail", ""),
            "mt": getattr(self.mt, "name", "unknown"),
            "mt_detail": getattr(self.mt, "detail", ""),
            "tts": getattr(self.tts, "name", "unknown"),
            "tts_detail": getattr(self.tts, "detail", ""),
            "tts_sample_rate": getattr(self.tts, "sr", 24000),
            "supports_clone": bool(getattr(self.tts, "supports_clone", False)),
        }

    def warmup(self) -> List[str]:
        notes = []
        for part in (self.asr, self.mt, self.tts):
            fn = getattr(part, "warmup", None)
            if callable(fn):
                try:
                    note = fn()
                    if note:
                        notes.append(str(note))
                except Exception as exc:  # pragma: no cover
                    notes.append(f"warmup failed ({part}): {exc}")
        return notes


def build(cfg: Config) -> Backends:
    from .asr import build_asr
    from .mt import build_mt
    from .tts import build_tts

    return Backends(asr=build_asr(cfg), mt=build_mt(cfg), tts=build_tts(cfg))
