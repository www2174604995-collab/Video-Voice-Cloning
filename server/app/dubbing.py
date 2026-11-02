"""Offline dubbing core: replace a video's speech with a cloned voice.

Used by both the CLI (tools/dub_video.py) and the web endpoint (/api/dub).
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import time
from dataclasses import replace
from types import SimpleNamespace
from typing import Callable, List, Optional

import numpy as np

from . import audio as A
from .backends import Backends, build as build_backends
from .backends.tts import RefVoice
from .config import Config, load as load_config
from .vad import StreamSegmenter

SR = 16000
MIX_SR = 48000      # VoxCPM2 speaks at 48 kHz; mixing there avoids a resample

Progress = Optional[Callable[[str, int, int, str], None]]


def ffmpeg() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def decode_audio(path: str, sr: int = SR) -> np.ndarray:
    cmd = [ffmpeg(), "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg decode failed: " + proc.stderr.decode("utf-8", "replace")[:300])
    return np.frombuffer(proc.stdout, dtype="<i2").astype(np.float32) / 32768.0


def prepare_ref(path: str, seconds: float = 15.0) -> str:
    """Cut the reference down to the most speech-dense ~15 s window.

    A 40 s reference makes VoxCPM2 echo the prompt (Japanese leaking into the
    Chinese dub) and drags the timbre toward whatever else is in the clip. 15 s
    of continuous speech is the sweet spot for reference-mode cloning.
    """
    # work at 44.1 kHz: decoding to 16 kHz and back killed everything above
    # 8 kHz, which made every cloned line sound muffled compared to the
    # single-line tests (those used the original file untouched).
    hi = 44100
    x = decode_audio(path, hi)
    win = int(seconds * hi)
    if seconds > 0 and len(x) > win:
        frame = int(0.05 * hi)
        n = len(x) // frame
        rms = np.sqrt(np.mean(x[: n * frame].reshape(n, frame) ** 2, axis=1) + 1e-12)
        thr = max(0.01, float(np.percentile(rms, 70)) * 0.5)
        voiced = (rms > thr).astype(np.float32)
        k = max(1, win // frame)
        cum = np.concatenate([[0.0], np.cumsum(voiced)])
        scores = cum[k:] - cum[:-k]
        start = int(np.argmax(scores)) * frame if len(scores) else 0
        x = x[start:start + win]
    peak = float(np.max(np.abs(x))) or 1.0
    x = (x / peak * 0.9).astype(np.float32)
    out = os.path.join(tempfile.gettempdir(), "ref-%d.wav" % int(time.time() * 1000))
    A.write_wav(out, x, hi)
    return out


def fade(x: np.ndarray, sr: int, ms_in: float = 15.0, ms_out: float = 45.0) -> np.ndarray:
    """Tiny fade in/out so consecutive lines do not click or chop."""
    x = np.asarray(x, dtype=np.float32).copy()
    n_in, n_out = int(sr * ms_in / 1000), int(sr * ms_out / 1000)
    if x.size > n_in + n_out:
        x[:n_in] *= np.linspace(0.0, 1.0, n_in, dtype=np.float32)
        x[-n_out:] *= np.linspace(1.0, 0.0, n_out, dtype=np.float32)
    return x


def norm_clip(x: np.ndarray, target_db: float = -20.0, peak: float = 0.95) -> np.ndarray:
    """Pin every line to the same loudness (each one is synthesised separately)."""
    x = np.asarray(x, dtype=np.float32)
    if x.size == 0:
        return x
    rms = float(np.sqrt(np.mean(x ** 2))) + 1e-9
    gain = (10 ** (target_db / 20.0)) / rms
    y = x * gain
    # soft-knee limiting instead of a hard peak cap: hard caps made loud lines
    # quieter than quiet ones, which is what "volume keeps changing" sounded like
    top = float(np.max(np.abs(y))) + 1e-9
    if top > peak:
        y = np.tanh(y * (peak / top) * 1.25) / 1.25
    return y.astype(np.float32)


def stretch(x: np.ndarray, factor: float) -> np.ndarray:
    """Pitch-preserving time scale (factor > 1 = shorter)."""
    if abs(factor - 1.0) < 0.05 or x.size < 2:
        return x
    try:
        import librosa

        return librosa.effects.time_stretch(x.astype(np.float32), rate=float(factor))
    except Exception:
        return x


def _read_wav(path: str, expect_sr: int) -> np.ndarray:
    import wave

    with wave.open(path, "rb") as w:
        data = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
        if w.getnchannels() > 1:
            data = data.reshape(-1, w.getnchannels()).mean(axis=1)
    return data


def _fit_factor(pcm: np.ndarray, slot: float, cap: float = 1.25) -> float:
    factor = len(pcm) / MIX_SR / max(0.4, slot)
    if cap <= 1.0:
        return 1.0
    if factor > cap:
        return cap
    if factor < 0.85:
        return 1.0
    return factor


def _sim(a: str, b: str) -> float:
    import difflib

    a = "".join(ch for ch in a if ch.isalnum())
    b = "".join(ch for ch in b if ch.isalnum())
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _synth_checked(b: Backends, text: str, lang: str, ref, cfg: Config,
                   scorer=None, ref_emb=None, tries: int = 2):
    """Synthesise a line, listen back, and keep the best of several attempts.

    Three independent checks decide whether a take is good enough:
      * language  - VoxCPM2 sometimes drifts into the reference language
      * words     - ASR of the output vs the text we asked for
      * timbre    - speaker embedding vs the reference clip (catches the
                    "clear but wrong voice" takes)

    Returns the best (pcm, sr) or (None, 0).
    """
    best, best_score, best_sr = None, -1.0, 0
    check = bool(getattr(cfg, "dub_check", True))
    stats = getattr(cfg, "_dub_stats", None)
    for attempt in range(tries if check else 1):
        try:
            pcm = b.tts.synth(text, lang, ref)
        except Exception:
            continue
        sr = int(getattr(b.tts, "sr", MIX_SR))
        pcm = np.asarray(pcm, dtype=np.float32)
        if not check:
            return pcm, sr, True
        pcm16 = A.resample(pcm, sr, SR)
        try:
            # force the expected language: a global asr_language hint (e.g. "ja"
            # for the source video) would otherwise mis-transcribe our own output
            hint = None if lang in ("", "same", None) else lang
            heard = b.asr.transcribe(pcm16, hint)
            ok_lang = (not heard.lang) or heard.lang == lang or lang == "same"
            sim = _sim(heard.text or "", text)
        except Exception:
            return pcm, sr, True
        spk = 0.0
        if scorer is not None and getattr(scorer, "ready", False):
            spk = scorer.cos(scorer.embed(pcm16), ref_emb)
        score = sim * 1.0 + spk * 1.0 + (0.5 if ok_lang else 0.0)
        if score > best_score:
            best, best_score, best_sr = pcm, score, sr
        good = ok_lang and sim >= 0.45 and (spk >= 0.60 or not getattr(scorer, "ready", False))
        if good:
            if stats is not None and attempt > 0:
                stats["retried"] = stats.get("retried", 0) + 1
                print("[gate] retried x%d (words %.2f / voice %.2f): %s"
                      % (attempt + 1, sim, spk, text[:20]), flush=True)
            return best, best_sr, True
    if stats is not None:
        stats["rejected"] = stats.get("rejected", 0) + 1
        print("[gate] kept best of %d: %s" % (tries, text[:20]), flush=True)
    return best, best_sr, False


def _segment(audio: np.ndarray, seg: StreamSegmenter) -> List:
    out = []
    step = int(0.1 * SR)
    t = 0.0
    for i in range(0, len(audio), step):
        chunk = audio[i:i + step]
        if chunk.size < step // 2:
            break
        t1 = t + chunk.size / SR
        out.extend(seg.feed(chunk, t, t1, 1.0))
        t = t1
    silence = np.zeros(int(1.2 * SR), dtype=np.float32)
    out.extend(seg.feed(silence, t, t + 1.2, 1.0))
    return out


def dub_video(
    video: str,
    ref_audio: str,
    out_path: str,
    *,
    target: str = "same",
    bg: float = 0.0,
    tts: Optional[str] = None,
    asr_model: Optional[str] = None,
    vc: Optional[bool] = None,
    subtitles: Optional[str] = None,
    cfg: Optional[Config] = None,
    backends: Optional[Backends] = None,
    progress: Progress = None,
) -> str:
    def emit(stage: str, done: int = 0, total: int = 0, msg: str = "") -> None:
        if progress:
            progress(stage, done, total, msg)

    overrides = {}
    if tts:
        overrides["tts"] = tts
    if vc is not None:
        overrides["vc"] = bool(vc)
    cfg = replace(cfg or load_config(), **overrides)
    object.__setattr__(cfg, "_dub_stats", {"retried": 0, "rejected": 0})
    if asr_model:
        cfg = replace(cfg, asr_model=asr_model)

    emit("decode", 0, 0, "解码音轨")
    audio = decode_audio(video)
    duration = len(audio) / SR

    emit("models", 0, 0, "加载模型")
    b = backends or build_backends(cfg)
    if backends is None:
        b.warmup()

    trim = float(getattr(cfg, "ref_trim", 15.0) or 0.0)
    # ref_trim: 0 means "use the reference exactly as given" — never re-encode it
    ref_path = prepare_ref(ref_audio, trim) if trim > 0 else ref_audio
    ref = RefVoice(path_24k=ref_path, path_16k=ref_path, seconds=15.0, text="")

    emit("segment", 0, 0, "切句")
    if subtitles and os.path.isfile(subtitles):
        from .subs import prepare as _prepare_subs

        cues = _prepare_subs(subtitles, float(getattr(cfg, "sub_merge_sec", 14.0) or 14.0))
        segs = [SimpleNamespace(t0=c["t0"], t1=c["t1"], duration=max(0.4, c["t1"] - c["t0"]),
                                audio=audio[int(c["t0"] * SR): int(c["t1"] * SR)], text=c["text"])
                for c in cues]
        print("[subs] %d cues from %s" % (len(segs), os.path.basename(subtitles)), flush=True)
    else:
        seg = StreamSegmenter(sr=SR, frame_ms=cfg.vad_frame_ms, min_speech=cfg.vad_min_speech,
                              max_segment=cfg.vad_max_segment, end_silence=cfg.vad_end_silence,
                              energy_threshold=cfg.vad_energy)
        segs = _segment(audio, seg)
    total = len(segs)

    scorer = None
    ref_emb = None
    if bool(getattr(cfg, "dub_check", True)):
        try:
            from .spk import SpeakerScorer

            scorer = SpeakerScorer()
            if scorer.ready:
                ref_emb = scorer.embed(decode_audio(ref_path, SR))
                emit("gate", 0, 0, "声纹校验就绪")
            else:
                emit("gate", 0, 0, "声纹校验不可用（未装 resemblyzer）")
        except Exception as exc:
            print("[gate] scorer unavailable: %s" % exc, flush=True)

    work = tempfile.mkdtemp(prefix="dub-")
    lines: List = []
    ctx: List = []
    done = 0
    stats = getattr(cfg, "_dub_stats", None)
    for i, s in enumerate(segs):
        preset = getattr(s, "text", None)
        if preset:
            # subtitle text: already the target language, no ASR and no translation
            text_out = preset.strip()
            want = target if target and target != "same" else "zh"
            if not text_out:
                continue
        else:
            try:
                asr = b.asr.transcribe(s.audio, None)
            except Exception as exc:
                # a single bad line (or a CUDA hiccup) must not kill the whole video
                print("[asr] line %d failed: %s" % (i, exc), flush=True)
                if stats is not None:
                    stats["asr_failed"] = stats.get("asr_failed", 0) + 1
                continue
            text = (asr.text or "").strip()
            if not text or not asr.usable:
                continue
            if target and target != "same":
                mt = b.mt.translate(text, asr.lang or "auto", target, ctx)
                text_out = mt.text
                if mt.ok:
                    ctx.append((text, mt.text))
            else:
                text_out = text
            if not text_out.strip():
                continue
            want = target if target and target != "same" else (asr.lang or "zh")
        pcm, sr, ok = _synth_checked(b, text_out, want, ref, cfg, scorer=scorer, ref_emb=ref_emb,
                                     tries=int(getattr(cfg, "dub_candidates", 2) or 2))
        if pcm is None:
            continue
        pcm = A.resample(np.asarray(pcm, dtype=np.float32), sr, MIX_SR)
        pcm = fade(norm_clip(pcm), MIX_SR)
        pcm = stretch(pcm, _fit_factor(pcm, s.duration, float(getattr(cfg, "dub_max_speedup", 1.25) or 1.25)))

        line_path = os.path.join(work, "seg_%04d.wav" % i)
        A.write_wav(line_path, pcm, MIX_SR)
        lines.append({"t0": s.t0, "dur": s.duration, "path": line_path,
                      "text": text_out, "lang": want, "ok": bool(ok)})
        done += 1
        emit("dub", done, total, text_out[:40])

    # ---- optional second stage: swap the timbre onto the reference voice ----
    if lines and bool(getattr(cfg, "vc", False)):
        from .vc import VoiceConverter

        conv = VoiceConverter(cfg)
        if conv.available():
            emit("vc", 0, len(lines), "声音转换")
            pairs = [(ln["path"], ln["path"].replace(".wav", ".vc.wav")) for ln in lines]
            ratio = conv.convert(pairs, ref_path)
            if ratio > 0.5:
                for ln in lines:
                    alt = ln["path"].replace(".wav", ".vc.wav")
                    if os.path.isfile(alt):
                        ln["path"] = alt
                emit("vc", len(lines), len(lines), "声音转换完成")
            else:
                emit("vc", 0, len(lines), "声音转换失败，改用合成音色")
        else:
            emit("vc", 0, len(lines), "未找到 Seed-VC，跳过")

    # ---- repair pass: lines the gate could not rescue, redone with a second engine ----
    bad = [ln for ln in lines if not ln.get("ok", True)]
    repair_tts = (getattr(cfg, "repair_tts", "") or "").strip()
    if bad and repair_tts and repair_tts != cfg.tts:
        emit("repair", 0, len(bad), "修补 %d 句（%s）" % (len(bad), repair_tts))
        try:
            import torch  # type: ignore
            from .backends.tts import build_tts as _build_tts

            b.tts = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            b.tts = _build_tts(replace(cfg, tts=repair_tts))
            print("[repair] engine:", repair_tts, flush=True)
            fixed = 0
            for j, ln in enumerate(bad):
                try:
                    with torch.inference_mode():
                        pcm = b.tts.synth(ln["text"], ln["lang"], ref)
                except Exception as exc:
                    print("[repair] line %d failed: %s" % (j, exc), flush=True)
                    continue
                sr2 = int(getattr(b.tts, "sr", MIX_SR))
                pcm = A.resample(np.asarray(pcm, dtype=np.float32), sr2, MIX_SR)
                pcm = fade(norm_clip(pcm), MIX_SR)
                pcm = stretch(pcm, _fit_factor(pcm, ln["dur"], float(getattr(cfg, "dub_max_speedup", 1.25) or 1.25)))
                A.write_wav(ln["path"], pcm, MIX_SR)
                ln["ok"] = True
                fixed += 1
                emit("repair", fixed, len(bad), ln["text"][:40])
            print("[repair] fixed %d/%d with %s" % (fixed, len(bad), repair_tts), flush=True)
        except Exception as exc:
            print("[repair] unavailable: %s" % exc, flush=True)

    if stats:
        print("[gate] retried=%d rejected=%d asr_failed=%d of %d lines" % (
            stats.get("retried", 0), stats.get("rejected", 0), stats.get("asr_failed", 0), done), flush=True)

    emit("mix", done, total, "混音")
    mix = np.zeros(int(duration * MIX_SR) + MIX_SR, dtype=np.float32)
    prev_end = -1
    for ln in lines:
        pcm = _read_wav(ln["path"], MIX_SR)
        at = int(ln["t0"] * MIX_SR)
        # a line that overran its cue used to overlap the next one: two voices
        # at once (+6 dB, audible as "cut off" then "too loud"). Truncate the
        # tail with a short fade so the two never sound together.
        if 0 < prev_end > at:
            fade_n = min(int(0.06 * MIX_SR), prev_end - at)
            if fade_n > 0:
                mix[at:at + fade_n] *= np.linspace(1.0, 0.0, fade_n, dtype=np.float32)
                mix[at + fade_n:prev_end] = 0.0
            else:
                mix[at:prev_end] = 0.0
        end = min(len(mix), at + len(pcm))
        if end > at:
            mix[at:end] += pcm[: end - at]
        prev_end = end
    if bg > 0:
        bed_audio = A.resample(audio, SR, MIX_SR)
        bed = np.zeros_like(mix)
        n = min(len(bed), len(bed_audio))
        bed[:n] = bed_audio[:n] * max(0.0, min(1.0, bg))
        mix = mix + bed
    peak = float(np.max(np.abs(mix))) if mix.size else 0.0
    if peak > 0.95:
        mix = mix * (0.95 / peak)
    final = np.clip(mix, -1.0, 1.0)

    tmp = tempfile.mktemp(suffix=".wav")
    A.write_wav(tmp, final, MIX_SR)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    cmd = [ffmpeg(), "-y", "-v", "error", "-i", video, "-i", tmp,
           "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
           "-c:a", "aac", "-b:a", "192k", "-shortest", out_path]
    proc = subprocess.run(cmd, capture_output=True)
    try:
        os.remove(tmp)
    except OSError:
        pass
    if proc.returncode != 0:
        raise RuntimeError("mux failed: " + proc.stderr.decode("utf-8", "replace")[:300])
    emit("done", done, total, out_path)
    return out_path
