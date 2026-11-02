from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np

from ..config import Config


@dataclass
class ASRResult:
    text: str = ""
    lang: str = ""
    ms: float = 0.0
    avg_logprob: float = 0.0
    no_speech: float = 0.0

    @property
    def usable(self) -> bool:
        return bool(self.text.strip()) and self.no_speech < 0.85 and self.avg_logprob > -1.2


class FasterWhisperASR:
    """Local streaming-friendly ASR on top of CTranslate2 / faster-whisper."""

    name = "faster_whisper"
    supports_partial = False

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.detail = ""
        self._model = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    def load(self) -> None:
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            if self.cfg.hf_endpoint:
                os.environ.setdefault("HF_ENDPOINT", self.cfg.hf_endpoint)
                if "huggingface.co" not in self.cfg.hf_endpoint:
                    # Xet storage is not proxied by the mirrors, it 401s
                    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
            os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

            from faster_whisper import WhisperModel  # type: ignore

            device = (self.cfg.asr_device or "auto").lower()
            compute = (self.cfg.asr_compute_type or "auto").lower()
            # Importing torch first puts its bundled CUDA runtime (cublas64_12.dll,
            # cudnn*) on the DLL search path; ctranslate2 cannot find them alone.
            try:
                import torch  # type: ignore  # noqa: F401
            except Exception:
                pass
            if device == "auto":
                device = "cpu"
                try:
                    import torch  # type: ignore

                    if torch.cuda.is_available():
                        device = "cuda"
                except Exception:
                    pass
            if compute == "auto":
                compute = "float16" if device == "cuda" else "int8"
            os.makedirs(self.cfg.model_dir or ".", exist_ok=True) if self.cfg.model_dir else None

            started = time.time()
            self._model = WhisperModel(
                self.cfg.asr_model,
                device=device,
                compute_type=compute,
                download_root=self.cfg.model_dir or None,
            )
            self.detail = f"{self.cfg.asr_model} on {device}/{compute} (load {time.time() - started:.1f}s)"

    def warmup(self) -> str:
        try:
            self.load()
            dummy = np.zeros(int(16000 * 1.0), dtype=np.float32)
            self.transcribe(dummy, None)
            return "asr: " + self.detail
        except Exception as exc:  # pragma: no cover
            self.detail = f"unavailable ({exc})"
            return "asr: " + self.detail

    # ------------------------------------------------------------------
    def transcribe(self, audio: np.ndarray, lang_hint: Optional[str] = None) -> ASRResult:
        self.load()
        assert self._model is not None
        started = time.time()
        language = (lang_hint or self.cfg.asr_language or "auto").strip()
        if language in ("auto", "", "detect"):
            language = None

        prompt = None
        if language and language.lower().startswith(("zh", "cmn", "yue")):
            prompt = "以下是普通话的句子，请使用简体中文和标点。"

        with self._lock:
            segments, info = self._model.transcribe(
                np.asarray(audio, dtype=np.float32),
                language=language,
                beam_size=max(1, int(self.cfg.asr_beam_size)),
                temperature=0.0,
                initial_prompt=prompt,
                condition_on_previous_text=False,
                without_timestamps=True,
                vad_filter=False,
            )
            texts = []
            worst_logprob = 0.0
            worst_nospeech = 0.0
            for seg in segments:
                piece = (seg.text or "").strip()
                if piece:
                    texts.append(piece)
                worst_logprob = min(worst_logprob, float(getattr(seg, "avg_logprob", 0.0)))
                worst_nospeech = max(worst_nospeech, float(getattr(seg, "no_speech_prob", 0.0)))

        text = " ".join(texts).strip()
        return ASRResult(
            text=text,
            lang=getattr(info, "language", language or "") or "",
            ms=(time.time() - started) * 1000.0,
            avg_logprob=worst_logprob,
            no_speech=worst_nospeech,
        )


class MockASR:
    """Deterministic fake ASR used for plumbing tests and demos without models."""

    name = "mock"
    supports_partial = True
    detail = "mock"

    SENTENCES = [
        "今天我们来聊一聊这个新版本到底值不值得升级。",
        "先说结论，我觉得大部分人现在还不必着急。",
        "它的性能提升很明显，但功耗也上去了。",
        "如果你只是日常办公，上一代其实完全够用。",
        "好了，这期视频就到这里，我们下期再见。",
    ]

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self._i = 0

    def warmup(self) -> str:
        return "asr: mock"

    def transcribe(self, audio: np.ndarray, lang_hint: Optional[str] = None) -> ASRResult:
        time.sleep(0.05)
        text = self.SENTENCES[self._i % len(self.SENTENCES)]
        self._i += 1
        return ASRResult(text=text, lang="zh", ms=50.0, avg_logprob=-0.1, no_speech=0.0)


def build_asr(cfg: Config):
    kind = (cfg.asr or "faster_whisper").lower()
    if kind in ("mock", "none", "fake"):
        return MockASR(cfg)
    return FasterWhisperASR(cfg)
