"""Speaker-similarity scorer used by the offline dubbing quality gate."""
from __future__ import annotations

import os
from typing import Optional

import numpy as np


class SpeakerScorer:
    """Cosine similarity between two clips (0..1). Falls back to 'always ok'
    when resemblyzer is not installed, so the pipeline keeps working."""

    def __init__(self) -> None:
        self._enc = None
        self._failed = False
        try:
            from resemblyzer import VoiceEncoder  # type: ignore

            self._enc = VoiceEncoder("cpu")
        except Exception:
            self._failed = True

    @property
    def ready(self) -> bool:
        return self._enc is not None

    def embed(self, audio16k: np.ndarray) -> Optional[np.ndarray]:
        if self._enc is None:
            return None
        try:
            from resemblyzer import preprocess_wav  # type: ignore

            wav = preprocess_wav(audio16k, source_sr=16000)
            if wav.size < 1600:
                return None
            emb = self._enc.embed_utterance(wav)
            return emb / (np.linalg.norm(emb) + 1e-9)
        except Exception:
            return None

    @staticmethod
    def cos(a: Optional[np.ndarray], b: Optional[np.ndarray]) -> float:
        if a is None or b is None:
            return 0.0
        return float(np.dot(a, b))
