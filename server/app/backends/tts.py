from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
import threading
import time
import wave
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from .. import audio as A
from ..config import DATA_DIR, Config

log = logging.getLogger("bilisimul.tts")

OUT_SR = 24000

EDGE_VOICES = {
    "zh": ("zh-CN-XiaoxiaoNeural", "zh-CN-YunxiNeural"),
    "en": ("en-US-AriaNeural", "en-US-GuyNeural"),
    "ja": ("ja-JP-NanamiNeural", "ja-JP-KeitaNeural"),
    "ko": ("ko-KR-SunHiNeural", "ko-KR-InJoonNeural"),
    "es": ("es-ES-ElviraNeural", "es-ES-AlvaroNeural"),
    "fr": ("fr-FR-DeniseNeural", "fr-FR-HenriNeural"),
    "de": ("de-DE-KatjaNeural", "de-DE-ConradNeural"),
    "ru": ("ru-RU-SvetlanaNeural", "ru-RU-DmitryNeural"),
    "pt": ("pt-BR-FranciscaNeural", "pt-BR-AntonioNeural"),
    "it": ("it-IT-ElsaNeural", "it-IT-DiegoNeural"),
    "ar": ("ar-SA-ZariyahNeural", "ar-SA-HamedNeural"),
    "hi": ("hi-IN-SwaraNeural", "hi-IN-MadhurNeural"),
    "th": ("th-TH-PremwadeeNeural", "th-TH-NiwatNeural"),
    "vi": ("vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"),
    "id": ("id-ID-GadisNeural", "id-ID-ArdiNeural"),
    "tr": ("tr-TR-EmelNeural", "tr-TR-AhmetNeural"),
    "nl": ("nl-NL-ColetteNeural", "nl-NL-MaartenNeural"),
    "pl": ("pl-PL-ZofiaNeural", "pl-PL-MarekNeural"),
}

XTTS_LANGS = {
    "en": "en", "es": "es", "fr": "fr", "de": "de", "it": "it", "pt": "pt",
    "pl": "pl", "tr": "tr", "ru": "ru", "nl": "nl", "cs": "cs", "ar": "ar",
    "zh": "zh-cn", "ja": "ja", "hu": "hu", "ko": "ko", "hi": "hi",
}


class NoReferenceAudio(RuntimeError):
    """Raised when a cloning engine has no speaker reference yet.

    Expected for the first sentence or two, so it must NOT trip the circuit
    breaker - otherwise cloning would stay disabled for 10 minutes.
    """


@dataclass
class RefVoice:
    path_24k: str
    path_16k: str
    seconds: float
    text: str = ""


def split_text(text: str, limit: int = 140) -> List[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    if len(text) <= limit:
        return [text]
    parts: List[str] = []
    buf = ""
    for piece in re.split(r"(?<=[。！？.!?;；,，、])", text):
        if not piece:
            continue
        if len(buf) + len(piece) <= limit:
            buf += piece
        else:
            if buf:
                parts.append(buf)
            buf = piece
    if buf:
        parts.append(buf)
    out: List[str] = []
    for part in parts:
        while len(part) > limit:
            out.append(part[:limit])
            part = part[limit:]
        if part.strip():
            out.append(part.strip())
    return out


def _join(chunks: List[np.ndarray], sr: int, gap: float = 0.08) -> np.ndarray:
    chunks = [c for c in chunks if c is not None and c.size > 0]
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    silence = np.zeros(int(sr * gap), dtype=np.float32)
    out: List[np.ndarray] = []
    for i, chunk in enumerate(chunks):
        if i:
            out.append(silence)
        out.append(chunk.astype(np.float32))
    return np.concatenate(out)


class EdgeTTS:
    """Free Microsoft Edge voices. No cloning, but fast and very reliable."""

    name = "edge"
    sr = OUT_SR
    supports_clone = False

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.detail = "edge-tts (no voice cloning)"
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None

    # edge-tts is asyncio/aiohttp based; keep one long lived loop instead of
    # creating and tearing one down for every single sentence.
    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is not None:
            return self._loop
        loop = asyncio.new_event_loop()
        thread = threading.Thread(target=loop.run_forever, name="edge-tts-loop", daemon=True)
        thread.start()
        self._loop = loop
        self._thread = thread
        return loop

    def _run(self, coro, timeout: float = 20.0):
        loop = self._ensure_loop()
        return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=timeout)

    def warmup(self) -> str:
        return "tts: " + self.detail

    def _voice_for(self, lang: str) -> str:
        if self.cfg.preset_voice:
            return self.cfg.preset_voice
        pair = EDGE_VOICES.get(lang) or EDGE_VOICES["en"]
        return pair[0]

    def _synth_one(self, text: str, voice: str) -> bytes:
        import edge_tts  # type: ignore

        speed = float(self.cfg.tts_speed or 1.0)
        rate = f"{int(round((speed - 1.0) * 100)):+d}%"

        async def run() -> bytes:
            communicate = edge_tts.Communicate(text, voice, rate=rate)
            buf = bytearray()
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio":
                    buf.extend(chunk["data"])
            return bytes(buf)

        return self._run(run(), timeout=12.0)

    def synth(self, text: str, lang: str, ref: Optional[RefVoice] = None) -> np.ndarray:
        voice = self._voice_for(lang)  # edge voices cannot be cloned
        chunks: List[np.ndarray] = []
        for piece in split_text(text):
            data = self._synth_one(piece, voice)
            if not data:
                continue
            pcm, sr = A.decode_audio(data, self.sr)
            chunks.append(pcm)
        out = _join(chunks, self.sr)
        return A.trim_silence(out, self.sr)


class XTTS:
    """Coqui XTTS-v2 zero-shot cloning, 17 languages, runs on 4 GB GPUs."""

    name = "xtts"
    sr = OUT_SR
    supports_clone = True

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.detail = cfg.xtts_model
        self._tts = None
        self._device = "cpu"
        self._cond = None
        self._cond_key = None

    def local_dir(self) -> str:
        return self.cfg.xtts_dir or os.path.join(str(DATA_DIR), "models", "xtts_v2")

    def load(self) -> None:
        if self._tts is not None:
            return
        # coqui asks for a TOS confirmation through input(); a server has no stdin
        os.environ.setdefault("COQUI_TOS_AGREED", "1")
        from TTS.api import TTS  # type: ignore

        device = "cuda" if self._cuda() else "cpu"
        self._device = device
        model_path = os.path.join(self.local_dir(), "model.pth")
        config_path = os.path.join(self.local_dir(), "config.json")
        if os.path.isfile(model_path) and os.path.isfile(config_path):
            speakers = os.path.join(self.local_dir(), "speakers_xtts.pth")
            self._tts = TTS(
                model_name="",
                model_path=model_path,
                config_path=config_path,
                speakers_file_path=speakers if os.path.isfile(speakers) else None,
                progress_bar=False,
            )
            # 0.28 deprecated the `gpu=` flag (it no longer moves the model)
            self._tts.to(device)
            self.detail = "XTTS-v2 local (%s, %s)" % (self.local_dir(), device)
        else:
            self._tts = TTS(self.cfg.xtts_model).to(device)
            self.detail = f"{self.cfg.xtts_model} ({device})"

    def _cuda(self) -> bool:
        want = (getattr(self.cfg, "tts_device", "auto") or "auto").lower()
        if want == "cpu":
            return False
        try:
            import torch  # type: ignore

            if not torch.cuda.is_available():
                return False
            return want in ("auto", "cuda")
        except Exception:
            return False

    def warmup(self) -> str:
        try:
            self.load()
            self._preload()
            return "tts: " + self.detail
        except Exception as exc:  # pragma: no cover
            self.detail = f"unavailable ({exc})"
            return "tts: " + self.detail

    def _preload(self) -> None:
        """Force the lazy model build + a dummy inference at startup.

        Without this the first real sentence pays 25-45 s of model init, which
        looks exactly like "the plugin does nothing".
        """
        try:
            tmp = os.path.join(tempfile.gettempdir(), "bilisimul-xtts-warmup.wav")
            if not os.path.isfile(tmp):
                sr = 24000
                t = np.arange(int(sr * 2.0), dtype=np.float32) / sr
                A.write_wav(tmp, (0.05 * np.sin(2 * np.pi * 160.0 * t)).astype(np.float32), sr)
            model = self._tts.synthesizer.tts_model  # type: ignore[union-attr]
            gpt, spk = model.get_conditioning_latents(audio_path=[tmp])
            model.inference(
                "Warm up.", "en", gpt, spk,
                temperature=0.65, length_penalty=1.0, repetition_penalty=2.0,
                top_k=50, top_p=0.8,
            )
        except Exception as exc:  # pragma: no cover
            log.warning("xtts preload skipped: %s", exc)

    def synth(self, text: str, lang: str, ref: Optional[RefVoice] = None) -> np.ndarray:
        self.load()
        assert self._tts is not None
        xtts_lang = XTTS_LANGS.get(lang, "en")
        speaker = ref.path_24k if ref and os.path.isfile(ref.path_24k) else None
        if speaker is None:
            speaker = self.cfg.preset_voice if self.cfg.preset_voice and os.path.isfile(self.cfg.preset_voice) else None
        if speaker is None:
            raise NoReferenceAudio("XTTS: no speaker reference captured yet")
        # Conditioning (speaker embedding + GPT latents) costs ~2 s and only
        # depends on the reference clip, so compute it once and reuse it.
        latents = None
        if speaker:
            try:
                latents = self._conditioning(speaker)
            except Exception:
                latents = None

        model = self._tts.synthesizer.tts_model
        src_sr = int(self._tts.synthesizer.output_sample_rate)
        chunks: List[np.ndarray] = []
        for piece in split_text(text):
            arr = None
            if latents is not None:
                try:
                    res = model.inference(
                        piece,
                        xtts_lang,
                        latents[0],
                        latents[1],
                        temperature=0.65,
                        length_penalty=1.0,
                        repetition_penalty=2.0,
                        top_k=50,
                        top_p=0.8,
                        enable_text_splitting=True,
                    )
                    arr = np.asarray(res["wav"], dtype=np.float32).reshape(-1)
                except Exception:
                    arr = None
            if arr is None:
                wav = self._tts.tts(text=piece, speaker_wav=speaker, language=xtts_lang, speed=float(self.cfg.tts_speed or 1.0))
                arr = np.asarray(wav, dtype=np.float32).reshape(-1)
            chunks.append(A.resample(arr, src_sr, self.sr))
        out = _join(chunks, self.sr)
        return A.trim_silence(out, self.sr)

    def _conditioning(self, speaker: str):
        key = (speaker, os.path.getmtime(speaker))
        if self._cond is not None and self._cond_key == key:
            return self._cond
        model = self._tts.synthesizer.tts_model  # type: ignore[union-attr]
        gpt_cond, spk_emb = model.get_conditioning_latents(audio_path=[speaker])
        self._cond = (gpt_cond, spk_emb)
        self._cond_key = key
        return self._cond


class CosyVoice:
    """CosyVoice2-0.5B: strong zh/en/ja/ko zero-shot cloning, streaming capable."""

    name = "cosyvoice"
    sr = OUT_SR
    supports_clone = True

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.detail = cfg.cosyvoice_dir or "not configured"
        self._model = None

    def load(self) -> None:
        if self._model is not None:
            return
        repo = self.cfg.cosyvoice_dir
        if not repo or not os.path.isdir(repo):
            raise RuntimeError("cosyvoice_dir is not set to a CosyVoice checkout")
        import sys

        for extra in (os.path.join(repo, "third_party", "Matcha-TTS"), repo):
            if extra not in sys.path:
                sys.path.insert(0, extra)
        from cosyvoice.cli.cosyvoice import CosyVoice2  # type: ignore

        model_dir = os.path.join(repo, "pretrained_models", "CosyVoice2-0.5B")
        self._model = CosyVoice2(model_dir, load_jit=False, load_trt=False, fp16=False)
        self.detail = f"CosyVoice2-0.5B ({model_dir})"
        self.sr = int(getattr(self._model, "sample_rate", OUT_SR))

    def warmup(self) -> str:
        try:
            self.load()
            return "tts: " + self.detail
        except Exception as exc:  # pragma: no cover
            self.detail = f"unavailable ({exc})"
            return "tts: " + self.detail

    def synth(self, text: str, lang: str, ref: Optional[RefVoice] = None) -> np.ndarray:
        import torch  # type: ignore
        import torchaudio  # type: ignore

        self.load()
        assert self._model is not None
        if ref and os.path.isfile(ref.path_16k):
            speech, sr = torchaudio.load(ref.path_16k)
            speech = torchaudio.functional.resample(speech, sr, 16000)
            prompt = speech.mean(dim=0, keepdim=True)
        else:
            raise NoReferenceAudio("CosyVoice: no speaker reference captured yet")

        chunks: List[np.ndarray] = []
        for piece in split_text(text, 90):
            for out in self._model.inference_cross_lingual(piece, prompt, stream=False):
                arr = out["tts_speech"].squeeze(0).detach().cpu().numpy().astype(np.float32)
                chunks.append(A.resample(arr, self.sr, OUT_SR))
        out = _join(chunks, OUT_SR)
        self.sr = OUT_SR
        return A.trim_silence(out, OUT_SR)


class SapiTTS:
    """Offline Windows voices (SAPI5). Robotic, but always available."""

    name = "sapi"
    sr = OUT_SR
    supports_clone = False

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.detail = "Windows SAPI5 (offline, no cloning)"

    def warmup(self) -> str:
        return "tts: " + self.detail

    @staticmethod
    def _lcid(lang: str) -> str:
        return {
            "zh": "804", "en": "409", "ja": "411", "ko": "412", "es": "c0a",
            "fr": "40c", "de": "407", "ru": "419", "pt": "416", "it": "410",
        }.get(lang, "409")

    def _speak(self, text: str, lang: str, path: str) -> None:
        """Write a wav through SAPI. COM objects must be released *before*
        CoUninitialize, otherwise comtypes/win32 leaks and the file can end up
        truncated."""
        import pythoncom  # type: ignore
        import win32com.client  # type: ignore

        pythoncom.CoInitialize()
        speaker = stream = voices = chosen = None
        try:
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            voices = speaker.GetVoices()
            want = self._lcid(lang)
            for i in range(voices.Count):
                v = voices.Item(i)
                try:
                    attr = str(v.GetAttribute("Language"))
                except Exception:
                    attr = ""
                if want in attr:
                    chosen = v
                    break
            if chosen is not None:
                speaker.Voice = chosen

            stream = win32com.client.Dispatch("SAPI.SpFileStream")
            stream.Format.Type = 22  # 22 kHz 16 bit mono
            stream.Open(path, 3, False)
            speaker.AudioOutputStream = stream
            speaker.Rate = 1
            speaker.Speak(text)
            stream.Close()
        finally:
            # drop every COM reference before tearing the apartment down
            chosen = None
            voices = None
            stream = None
            speaker = None
            pythoncom.CoUninitialize()

    def synth(self, text: str, lang: str, ref: Optional[RefVoice] = None) -> np.ndarray:
        tmp = os.path.join(tempfile.gettempdir(), "bilisimul-sapi-%d.wav" % os.getpid())
        try:
            self._speak(text, lang, tmp)
            with wave.open(tmp, "rb") as w:
                sr = w.getframerate()
                raw = w.readframes(w.getnframes())
            pcm = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
            return A.trim_silence(A.resample(pcm, sr, OUT_SR), OUT_SR)
        finally:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass


INDEX_LANGS = {
    "zh": "ZH", "en": "EN", "ja": "JA", "ko": "KO", "es": "ES", "fr": "FR",
    "de": "DE", "ru": "RU", "pt": "PT", "it": "IT", "ar": "AR", "hi": "HI",
    "th": "TH", "vi": "VI", "id": "ID", "tr": "TR", "nl": "NL", "pl": "PL",
}


class IndexTTS2:
    """IndexTTS-2 via the pure-torch windextts implementation.

    Better Chinese prosody than XTTS and it runs comfortably on small cards
    because it can shed the wav2vec encoder to CPU (low_vram).
    """

    name = "indextts"
    sr = OUT_SR
    supports_clone = True

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.detail = "IndexTTS-2 (not loaded)"
        self._eng = None
        self._quantized = False

    def local_dir(self) -> str:
        return self.cfg.indextts_dir or os.path.join(str(DATA_DIR), "models", "indextts2")

    def _cuda(self) -> bool:
        want = (getattr(self.cfg, "tts_device", "auto") or "auto").lower()
        if want == "cpu":
            return False
        try:
            import torch  # type: ignore

            return bool(torch.cuda.is_available())
        except Exception:
            return False

    def load(self, int4: bool = False) -> None:
        if self._eng is not None:
            return
        import torch  # type: ignore
        from windextts.inference import WIndexTTS  # type: ignore

        device = "cuda" if self._cuda() else "cpu"
        dtype = torch.float16 if device == "cuda" else torch.float32
        low_vram = False
        if device == "cuda":
            total_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
            low_vram = total_gb < 8.5      # IndexTTS-2 wants 6-8 GB
            log.info("indextts: %.1f GB VRAM -> low_vram=%s", total_gb, low_vram)
        self._quantized = bool(int4 and device == "cuda")
        self._eng = WIndexTTS(
            weights_dir=self.local_dir(),
            device=device,
            dtype=dtype,
            low_vram=low_vram,
            enable_w4a16=self._quantized,
        )
        try:
            self._eng.warmup()
        except Exception as exc:  # pragma: no cover - optional fast path
            log.warning("indextts warmup skipped: %s", exc)
        self.detail = "IndexTTS-2 (%s, %s)" % (device, str(dtype).replace("torch.", ""))

    def warmup(self) -> str:
        try:
            self.load()
            return "tts: " + self.detail
        except Exception as exc:  # pragma: no cover
            self.detail = f"unavailable ({exc})"
            return "tts: " + self.detail

    def synth(self, text: str, lang: str, ref: Optional[RefVoice] = None) -> np.ndarray:
        self.load()
        if not ref or not os.path.isfile(ref.path_24k):
            raise NoReferenceAudio("IndexTTS: no speaker reference captured yet")
        try:
            return self._run(text, lang, ref)
        except RuntimeError as exc:
            if "out of memory" not in str(exc).lower() or self._quantized:
                raise
            # 4 GB cards: fall back to int4 GPT and retry once
            log.warning("indextts out of memory, retrying with int4: %s", exc)
            import torch  # type: ignore

            self._eng = None
            torch.cuda.empty_cache()
            self.load(int4=True)
            return self._run(text, lang, ref)

    def _run(self, text: str, lang: str, ref: RefVoice) -> np.ndarray:
        assert self._eng is not None
        code = INDEX_LANGS.get(lang, "EN")
        sr, wav = self._eng.infer(
            spk_audio_prompt=ref.path_24k,
            text=text,
            lang=code,
            do_sample=True,
            top_p=0.8,
            top_k=30,
            temperature=0.8,
            cfm_steps=12,
        )
        if hasattr(wav, "detach"):
            arr = wav.detach().cpu().numpy().reshape(-1)
        else:
            arr = np.asarray(wav, dtype=np.float32).reshape(-1)
        arr = arr.astype(np.float32)
        self.sr = OUT_SR
        if int(sr) != OUT_SR:
            arr = A.resample(arr, int(sr), OUT_SR)
        return A.trim_silence(arr, OUT_SR)


class VoxCPMBackend:
    """VoxCPM-0.5B (OpenBMB): tokenizer-free TTS, clones from a short clip.

    Measured on this 4 GB RTX 3050 laptop: 1.5 GB weights, peak 2.2 GB VRAM,
    RTF 2.4-2.6 -> 5-7 s for a 2.5 s line. Fits comfortably, unlike IndexTTS-2.
    """

    name = "voxcpm"
    sr = 16000
    supports_clone = True

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.detail = "VoxCPM-0.5B (not loaded)"
        self._m = None
        self._cache = None
        self._cache_key = None

    def local_dir(self) -> str:
        return self.cfg.voxcpm_dir or os.path.join(str(DATA_DIR), "models", "voxcpm")

    def _use_cuda(self) -> bool:
        want = (getattr(self.cfg, "tts_device", "auto") or "auto").lower()
        if want == "cpu":
            return False
        try:
            import torch  # type: ignore

            return bool(torch.cuda.is_available())
        except Exception:
            return False

    def load(self) -> None:
        if self._m is not None:
            return
        from voxcpm import VoxCPM  # type: ignore

        device = "cuda" if self._use_cuda() else "cpu"
        # torch.compile on CPU is a net loss (minutes of compile, no speedup)
        optimize = bool(getattr(self.cfg, "voxcpm_optimize", True)) and device == "cuda"
        # load_denoiser=False: the ZipEnhancer path imports modelscope, which is
        # not a dependency here and is only needed for the web demo's denoise.
        lora_path = (getattr(self.cfg, "voxcpm_lora", "") or "").strip()
        kwargs = {}
        if lora_path and os.path.isfile(lora_path):
            try:
                from voxcpm.model.voxcpm2 import LoRAConfig  # type: ignore

                kwargs["lora_config"] = LoRAConfig(
                    enable_lm=True,
                    enable_dit=True,
                    enable_proj=bool(getattr(self.cfg, "voxcpm_lora_proj", False)),
                    r=int(getattr(self.cfg, "voxcpm_lora_r", 32) or 32),
                    alpha=int(getattr(self.cfg, "voxcpm_lora_alpha", 32) or 32),
                    dropout=0.0,
                )
                kwargs["lora_weights_path"] = lora_path
                log.info("voxcpm: loading LoRA %s", lora_path)
            except Exception as exc:
                log.warning("voxcpm: LoRA setup failed (%s), using the base model", exc)
        self._m = VoxCPM.from_pretrained(self.local_dir(), device=device,
                                         optimize=optimize, load_denoiser=False, **kwargs)
        tag = "+lora" if kwargs else ""
        self.detail = "VoxCPM-0.5B%s (%s, compile=%s)" % (tag, device, optimize)

    def warmup(self) -> str:
        try:
            self.load()
            return "tts: " + self.detail
        except Exception as exc:  # pragma: no cover
            self.detail = f"unavailable ({exc})"
            return "tts: " + self.detail

    def _is_v2(self) -> bool:
        try:
            from voxcpm.model.voxcpm2 import VoxCPM2Model  # type: ignore

            return isinstance(self._m.tts_model, VoxCPM2Model)
        except Exception:
            return False

    def _prompt(self, ref):
        key = (ref.path_24k, os.path.getmtime(ref.path_24k))
        if self._cache is not None and self._cache_key == key:
            return self._cache
        assert self._m is not None
        text = (ref.text or "").strip()
        mode = (getattr(self.cfg, "voxcpm_mode", "both") or "both").lower()
        if self._is_v2():
            if mode == "prompt":
                if not text:
                    raise NoReferenceAudio("VoxCPM prompt mode needs the reference transcript")
                self._cache = self._m.tts_model.build_prompt_cache(
                    prompt_text=text, prompt_wav_path=ref.path_24k
                )
            elif mode == "both" and text:
                # what the official demo does: timbre embedding + the reference's
                # own transcript, which anchors both voice and prosody
                self._cache = self._m.tts_model.build_prompt_cache(
                    prompt_text=text,
                    prompt_wav_path=ref.path_24k,
                    reference_wav_path=ref.path_24k,
                )
            else:
                # reference mode: timbre only, safest across languages
                self._cache = self._m.tts_model.build_prompt_cache(
                    reference_wav_path=ref.path_24k
                )
        else:
            if not text:
                raise NoReferenceAudio("VoxCPM needs the reference transcript")
            self._cache = self._m.tts_model.build_prompt_cache(
                prompt_text=text, prompt_wav_path=ref.path_24k
            )
        self._cache_key = key
        return self._cache

    def _normalize_text(self, text: str) -> str:
        """Digits/symbols/units -> spoken form; skipping this made the model
        stumble on numbers and read some tokens literally."""
        try:
            if getattr(self._m, "text_normalizer", None) is None:
                from voxcpm.utils.text_normalize import TextNormalizer  # type: ignore

                self._m.text_normalizer = TextNormalizer()
            return self._m.text_normalizer.normalize(text)
        except Exception:
            return text

    def synth(self, text: str, lang: str, ref=None) -> np.ndarray:
        self.load()
        if not ref or not os.path.isfile(ref.path_24k):
            raise NoReferenceAudio("VoxCPM: no speaker reference captured yet")
        cache = self._prompt(ref)
        assert self._m is not None
        if bool(getattr(self.cfg, "voxcpm_normalize", True)):
            text = self._normalize_text(text)
        gen = self._m.tts_model._generate_with_prompt_cache(
            target_text=text,
            prompt_cache=cache,
            min_len=2,
            max_len=4096,
            inference_timesteps=int(getattr(self.cfg, "voxcpm_timesteps", 12) or 12),
            cfg_value=float(getattr(self.cfg, "voxcpm_cfg", 2.0) or 2.0),
            # the model occasionally emits nonsense; this makes it regenerate
            # when the audio/text length ratio looks wrong
            retry_badcase=bool(getattr(self.cfg, "voxcpm_retry", True)),
            retry_badcase_max_times=2,
            retry_badcase_ratio_threshold=6.0,
            streaming=False,
        )
        wav, _, _ = next(gen)
        arr = wav.squeeze(0).detach().cpu().numpy().reshape(-1).astype(np.float32)
        # the model carries its own output rate (VoxCPM2 is not 16 kHz);
        # hardcoding 16k made the result play 1.5x too slow ("alien voice")
        self.sr = int(getattr(self._m.tts_model, "sample_rate", 16000) or 16000)
        return A.trim_silence(arr, self.sr)


class MockTTS:
    """Cheap placeholder audio so the whole pipeline can be tested without models."""

    name = "mock"
    sr = OUT_SR
    supports_clone = False
    detail = "mock tone"

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def warmup(self) -> str:
        return "tts: mock"

    def synth(self, text: str, lang: str, ref: Optional[RefVoice] = None) -> np.ndarray:
        dur = float(min(6.0, max(0.5, len(text) * 0.12)))
        n = int(self.sr * dur)
        t = np.arange(n, dtype=np.float32) / self.sr
        base = 180.0 + 20.0 * np.sin(2 * np.pi * 3.0 * t)
        phase = 2 * np.pi * np.cumsum(base) / self.sr
        wave = 0.22 * np.sin(phase) + 0.1 * np.sin(2 * phase) + 0.05 * np.sin(3 * phase)
        env = np.minimum(1.0, np.minimum(t * 12, (dur - t) * 12))
        env = np.clip(env, 0, 1)
        # syllable-ish amplitude modulation so it is obviously "speech"
        wave *= (0.6 + 0.4 * np.abs(np.sin(2 * np.pi * 4.2 * t)))
        return (wave * env).astype(np.float32)


class TTSChain:
    """Primary engine plus fallbacks, with the same circuit breaker as MT."""

    name = "chain"

    def __init__(self, engines, labels) -> None:
        self.engines = list(engines)
        self.labels = list(labels)
        self.name = self.labels[0]
        self.detail = " -> ".join(self.labels)
        self.sr = int(getattr(self.engines[0], "sr", OUT_SR))
        self.supports_clone = any(bool(getattr(e, "supports_clone", False)) for e in self.engines)
        self._fails = {}
        self.last_engine = self.name

    def warmup(self) -> str:
        return "tts: " + self.detail

    def synth(self, text: str, lang: str, ref: Optional[RefVoice] = None) -> np.ndarray:
        now = time.time()
        for engine, label in zip(self.engines, self.labels):
            state = self._fails.get(label)
            if state and state[1] > now:
                continue
            use_ref = ref if bool(getattr(engine, "supports_clone", False)) else None
            try:
                pcm = engine.synth(text, lang, use_ref)  # type: ignore[attr-defined]
                if pcm is not None and len(pcm) > 0:
                    self._fails.pop(label, None)
                    self.sr = int(getattr(engine, "sr", OUT_SR))
                    self.last_engine = label
                    return pcm
                raise RuntimeError("empty audio")
            except NoReferenceAudio:
                # normal at the very beginning of a video: try the next engine
                # but do not punish this one
                continue
            except Exception as exc:
                count = (state[0] if state else 0) + 1
                self._fails[label] = (count, now + (600.0 if count >= 2 else 0.0))
                log.warning("tts engine %s failed (%d): %s", label, count, exc)
        return np.zeros(0, dtype=np.float32)


def build_tts(cfg: Config):
    kind = (cfg.tts or "edge").lower()
    if kind in ("mock", "fake"):
        return MockTTS(cfg)
    if kind in ("sapi", "windows"):
        return SapiTTS(cfg)
    if kind in ("xtts", "xtts_v2", "coqui"):
        primary = XTTS(cfg)
    elif kind in ("cosyvoice", "cosyvoice2"):
        primary = CosyVoice(cfg)
    elif kind in ("indextts", "indextts2", "index", "index-tts"):
        primary = IndexTTS2(cfg)
    elif kind in ("voxcpm", "vox"):
        primary = VoxCPMBackend(cfg)
    else:
        primary = EdgeTTS(cfg)

    engines = [primary]
    labels = [primary.name]
    if os.name == "nt":
        engines.append(SapiTTS(cfg))
        labels.append("sapi")
    if len(engines) == 1:
        return primary
    return TTSChain(engines, labels)
