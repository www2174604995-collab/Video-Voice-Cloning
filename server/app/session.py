from __future__ import annotations

import asyncio
import collections
import json
import logging
import os
import tempfile
import threading
import time
import uuid
from typing import Any, Deque, Dict, List, Optional

import numpy as np

from . import audio as A
from .backends.tts import RefVoice
from .config import Config
from .protocol import pack_audio_frame, unpack_client_frame
from .vad import Segment, StreamSegmenter

log = logging.getLogger("bilisimul.session")

SR_IN = 16000
TTS_LOCK = threading.Lock()

SAME_GROUP = {"zh": "zh", "zh-cn": "zh", "zh-tw": "zh", "cmn": "zh", "yue": "zh"}


def base_lang(code: str) -> str:
    code = (code or "").lower().replace("_", "-")
    if code in SAME_GROUP:
        return SAME_GROUP[code]
    return code.split("-")[0]


class Session:
    """One WebSocket = one video tab = one translation stream."""

    def __init__(self, ws, cfg: Config, backends, hello: Dict[str, Any], runtime=None) -> None:
        self.sid = uuid.uuid4().hex[:8]
        self.ws = ws
        self.cfg = cfg
        self.b = backends
        self.rt = runtime
        self.target = str(hello.get("target_lang") or "en").strip()
        self.src_hint = str(hello.get("source_lang") or "auto").strip()
        self.voice_mode = str(hello.get("voice") or cfg.voice or "clone").strip()
        self.preset_voice = str(hello.get("preset_voice") or cfg.preset_voice or "").strip()
        self.rate = 1.0
        self.paused = False
        self.last_tick = 0.0

        self.segmenter = StreamSegmenter(
            sr=SR_IN,
            frame_ms=cfg.vad_frame_ms,
            min_speech=cfg.vad_min_speech,
            max_segment=cfg.vad_max_segment,
            end_silence=cfg.vad_end_silence,
            energy_threshold=cfg.vad_energy,
        )
        self.q: asyncio.Queue = asyncio.Queue(maxsize=32)
        self.ctx: Deque = collections.deque(maxlen=max(0, cfg.mt_context))
        self.seg_id = 0
        self.closed = False
        self._ref_parts: List[np.ndarray] = []
        self._ref_seconds = 0.0
        self._ref_text = ""
        self.ref: Optional[RefVoice] = None
        self._tmpdir = tempfile.mkdtemp(prefix="bilisimul-")
        self.lang_hist: Deque[str] = collections.deque(maxlen=4)
        self.passthrough = False
        self.stats: Dict[str, float] = {}
        self.dropped = 0
        self.skipped = 0
        self.ending = False
        if getattr(cfg, "ref_audio", "") and os.path.isfile(cfg.ref_audio):
            text = ""
            txt = cfg.ref_audio + ".txt"
            if os.path.isfile(txt):
                with open(txt, encoding="utf-8") as fh:
                    text = fh.read().strip()
            if not text:
                # VoxCPM needs the transcript of the reference; derive it once
                try:
                    audio, sr = A.decode_audio(open(cfg.ref_audio, "rb").read(), SR_IN)
                    text = (self.b.asr.transcribe(audio, None).text or "").strip()
                    log.info("[%s] reference transcript: %s", self.sid, text[:40])
                except Exception as exc:
                    log.warning("[%s] reference transcript failed: %s", self.sid, exc)
            self.ref = RefVoice(path_24k=cfg.ref_audio, path_16k=cfg.ref_audio,
                                seconds=20.0, text=text)
            log.info("[%s] fixed reference: %s (%.1fs)", self.sid, cfg.ref_audio, 20.0)

    # -- plumbing --------------------------------------------------------
    async def send_json(self, payload: Dict[str, Any]) -> None:
        if self.closed:
            return
        try:
            await self.ws.send_text(json.dumps(payload, ensure_ascii=False))
        except Exception:
            self.closed = True

    async def send_bytes(self, payload: bytes) -> None:
        if self.closed:
            return
        try:
            await self.ws.send_bytes(payload)
        except Exception:
            self.closed = True

    # -- main loop -------------------------------------------------------
    async def run(self) -> None:
        info = self.b.describe()
        await self.send_json(
            {
                "type": "ready",
                "session": self.sid,
                "target": self.target,
                "source": self.src_hint,
                "voice": self.voice_mode,
                "backends": info,
            }
        )
        reader = asyncio.create_task(self._read_loop(), name="reader-" + self.sid)
        worker = asyncio.create_task(self._work_loop(), name="worker-" + self.sid)
        try:
            await asyncio.wait({reader, worker}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            self.closed = True
            for task in (reader, worker):
                task.cancel()
            await asyncio.gather(reader, worker, return_exceptions=True)
            log.info("[%s] closed (skipped=%d dropped=%d)", self.sid, self.skipped, self.dropped)
            self._cleanup()

    async def _read_loop(self) -> None:
        while not self.closed:
            msg = await self.ws.receive()
            kind = msg.get("type")
            if kind == "websocket.disconnect":
                return
            data = msg.get("bytes")
            if data:
                try:
                    _, t0, t1, pcm = unpack_client_frame(data)
                except Exception:
                    continue
                if self.paused:
                    continue
                segments = self.segmenter.feed(pcm, t0, t1, self.rate)
                for seg in segments:
                    if self.q.qsize() >= 6:
                        try:
                            self.q.get_nowait()
                            self.dropped += 1
                        except asyncio.QueueEmpty:
                            pass
                    await self.q.put(seg)
                continue
            text = msg.get("text")
            if text:
                try:
                    await self._control(json.loads(text))
                except Exception as exc:  # pragma: no cover
                    log.warning("[%s] bad control message: %s", self.sid, exc)

    async def _control(self, data: Dict[str, Any]) -> None:
        kind = data.get("type")
        if kind == "tick":
            self.rate = float(data.get("rate") or 1.0) or 1.0
            was_paused = self.paused
            self.paused = bool(data.get("paused"))
            if self.paused and not was_paused:
                self.segmenter.reset()
        elif kind == "reset":
            self.segmenter.reset()
            self._drain()
            self.ctx.clear()
            self.paused = False
        elif kind == "config":
            if data.get("target_lang"):
                self.target = str(data["target_lang"])
            if data.get("voice"):
                self.voice_mode = str(data["voice"])
            if data.get("preset_voice") is not None:
                self.preset_voice = str(data["preset_voice"])
            await self.send_json({"type": "config-ack", "target": self.target, "voice": self.voice_mode})
        elif kind == "end":
            self.ending = True
            if self.q.empty():
                await self.q.put(None)

    def _drain(self) -> None:
        while True:
            try:
                self.q.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def _work_loop(self) -> None:
        while not self.closed:
            seg = await self.q.get()
            if seg is None:
                return
            try:
                await self._process(seg)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover
                log.exception("[%s] segment failed", self.sid)
                await self.send_json({"type": "error", "message": str(exc)[:200]})
            if self.ending and self.q.empty():
                return

    # -- pipeline --------------------------------------------------------
    async def _process(self, seg: Segment) -> None:
        if seg.audio.size < int(SR_IN * 0.2) or A.rms(seg.audio) < 5e-4:
            return
        started = time.time()
        seg_id = self.seg_id
        self.seg_id += 1

        asr = await asyncio.to_thread(self.b.asr.transcribe, seg.audio, self.src_hint or None)
        self.stats["asr"] = round(asr.ms, 1)
        src_text = (asr.text or "").strip()
        if not src_text or not asr.usable:
            self.skipped += 1
            return

        detected = base_lang(asr.lang or self.src_hint)
        self.lang_hist.append(detected)
        # after two consistent detections, lock the source language: it makes
        # whisper faster and stops it flip-flopping between zh / en per line
        if self.src_hint in ("", "auto") and len(self.lang_hist) >= 2 and len(set(list(self.lang_hist)[-2:])) == 1:
            self.src_hint = detected

        if detected and detected == base_lang(self.target) and detected not in ("", "auto"):
            self.skipped += 1
            await self._maybe_passthrough(True)
            await self.send_json(
                {
                    "type": "subtitle",
                    "id": seg_id,
                    "t0": seg.t0,
                    "t1": seg.t1,
                    "src": src_text,
                    "dst": "",
                    "lang": detected,
                    "dub": False,
                    "same_language": True,
                }
            )
            return

        await self._maybe_passthrough(False)

        # enrol the speaker early so the first *cloned* line is not far away
        if self.voice_mode == "clone" and self.ref is None and getattr(self.b.tts, "supports_clone", False):
            # every short utterance still contributes a few syllables: with 2 s
            # lines only, gating on "long enough" meant cloning never started
            if seg.duration >= min(self.cfg.clone_min_segment, 0.8):
                self._enrol(seg.audio, src_text)

        mt = await asyncio.to_thread(self.b.mt.translate, src_text, detected or "auto", self.target, list(self.ctx))
        self.stats["mt"] = round(mt.ms, 1)
        if mt.ok:
            self.ctx.append((src_text, mt.text))

        await self.send_json(
            {
                "type": "subtitle",
                "id": seg_id,
                "t0": seg.t0,
                "t1": seg.t1,
                "src": src_text,
                "dst": mt.text,
                "lang": detected,
                "dub": True,
                "engine": mt.engine,
                "ok": mt.ok,
            }
        )

        if not mt.text.strip() or not mt.ok:
            await self.send_json({"type": "stat", **self.stats, "total": round((time.time() - started) * 1000, 1), "dropped": self.dropped})
            return

        pcm, sr = await asyncio.to_thread(self._tts_sync, mt.text, seg_id)
        self.stats["engine"] = str(getattr(self.b.tts, "last_engine", ""))
        if pcm is None or pcm.size == 0:
            await self.send_json({"type": "stat", **self.stats, "total": round((time.time() - started) * 1000, 1), "dropped": self.dropped})
            return

        await self.send_bytes(pack_audio_frame(seg_id, seg.t0, seg.t1, sr, pcm))
        total = (time.time() - started) * 1000.0
        self.stats["total"] = round(total, 1)
        self.stats["dropped"] = self.dropped
        await self.send_json({"type": "stat", **self.stats, "queued": self.q.qsize()})
        log.info(
            "[%s] seg=%d %.1fs asr=%sms mt=%sms tts=%sms total=%.0fms  %s -> %s",
            self.sid, seg_id, seg.duration, self.stats.get("asr"), self.stats.get("mt"),
            self.stats.get("tts"), total, src_text[:24], mt.text[:24],
        )

    def _tts_sync(self, text: str, seg_id: int):
        t0 = time.time()
        engine = self.b.tts
        try:
            with TTS_LOCK:
                pcm = engine.synth(text, self.target, self.ref)
        except Exception as exc:
            log.warning("[%s] tts failed: %s", self.sid, exc)
            self.stats["tts_error"] = 1
            return None, getattr(engine, "sr", 24000)
        self.stats["tts"] = round((time.time() - t0) * 1000.0, 1)
        return np.asarray(pcm, dtype=np.float32), int(getattr(engine, "sr", 24000))

    # -- voice cloning ---------------------------------------------------
    def _enrol(self, audio: np.ndarray, text: str) -> None:
        piece = A.trim_silence(A.resample(audio, SR_IN, SR_IN), SR_IN)
        if piece.size < int(SR_IN * 0.4):
            return
        self._ref_parts.append(piece)
        self._ref_seconds += piece.size / SR_IN
        self._ref_text = (self._ref_text + " " + text).strip()[-200:]
        # freeze the profile as soon as it is usable (3.5 s); waiting for the
        # full 7 s means a video made of short lines never starts cloning
        upper = min(self.cfg.clone_ref_seconds, 9.0)
        if self._ref_seconds >= 3.5 or (self._ref_seconds >= 2.4 and self.q.empty()):
            joined = np.concatenate(self._ref_parts)[: int(SR_IN * upper)]
            path16 = os.path.join(self._tmpdir, "ref16.wav")
            path24 = os.path.join(self._tmpdir, "ref24.wav")
            A.write_wav(path16, joined, SR_IN)
            A.write_wav(path24, A.resample(joined, SR_IN, 24000), 24000)
            self.ref = RefVoice(path_24k=path24, path_16k=path16, seconds=len(joined) / SR_IN, text=self._ref_text)
            log.info("[%s] speaker enrolled (%.1fs)", self.sid, self.ref.seconds)

    async def _maybe_passthrough(self, on: bool) -> None:
        if on == self.passthrough:
            return
        if on:
            recent = list(self.lang_hist)[-2:]
            if len(recent) < 2 or len(set(recent)) != 1:
                return
        self.passthrough = on
        await self.send_json({"type": "passthrough", "on": on, "lang": base_lang(self.target)})

    def _cleanup(self) -> None:
        try:
            for name in os.listdir(self._tmpdir):
                try:
                    os.remove(os.path.join(self._tmpdir, name))
                except OSError:
                    pass
            os.rmdir(self._tmpdir)
        except Exception:
            pass
