from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np


@dataclass
class Segment:
    audio: np.ndarray
    t0: float
    t1: float
    rate: float = 1.0

    @property
    def duration(self) -> float:
        return float(self.t1 - self.t0)


class StreamSegmenter:
    """Energy VAD that turns a live PCM stream into utterance-sized chunks.

    The stream arrives as batches; every batch carries the *video* timestamp it
    was captured at, so the produced segments stay aligned with the player even
    when the user scrubs or changes playback speed.
    """

    def __init__(
        self,
        sr: int = 16000,
        frame_ms: int = 30,
        min_speech: float = 0.55,
        max_segment: float = 6.0,
        end_silence: float = 0.32,
        energy_threshold: float = 0.0,
        pre_roll: float = 0.18,
    ) -> None:
        self.sr = int(sr)
        self.frame = max(64, int(self.sr * frame_ms / 1000))
        self.min_speech = float(min_speech)
        self.max_segment = float(max_segment)
        self.end_silence = float(end_silence)
        self.fixed_threshold = float(energy_threshold or 0.0)
        self.pre_roll = float(pre_roll)

        self._samples = np.zeros(0, dtype=np.float32)
        self._t0 = 0.0
        self._rate = 1.0
        self._pos = 0
        self._noise = 0.004
        self._speaking = False
        self._silence_run = 0.0
        self._speech_run = 0.0
        self._seg_start = 0
        self._frame_dur = frame_ms / 1000.0

    # -- helpers ---------------------------------------------------------
    def _time_at(self, index: int) -> float:
        return self._t0 + (index / self.sr) / max(self._rate, 0.05)

    def reset(self) -> None:
        self._samples = np.zeros(0, dtype=np.float32)
        self._pos = 0
        self._speaking = False
        self._silence_run = 0.0
        self._speech_run = 0.0

    def _threshold(self) -> float:
        if self.fixed_threshold > 0:
            return self.fixed_threshold
        return max(0.0035, min(0.06, self._noise * 3.2))

    def _emit(self, end_index: int) -> Segment:
        a = max(0, int(self._seg_start - self.pre_roll * self.sr))
        b = min(len(self._samples), int(end_index))
        audio = self._samples[a:b].copy()
        seg = Segment(audio=audio, t0=self._time_at(a), t1=self._time_at(b), rate=self._rate)
        # drop everything we just emitted
        self._samples = self._samples[b:].copy()
        self._t0 = self._time_at(b)
        self._pos = 0
        self._seg_start = 0
        self._speaking = False
        self._silence_run = 0.0
        self._speech_run = 0.0
        return seg

    # -- public ----------------------------------------------------------
    def feed(self, pcm: np.ndarray, t0: float, t1: float, rate: float = 1.0) -> List[Segment]:
        pcm = np.asarray(pcm, dtype=np.float32).reshape(-1)
        if pcm.size == 0:
            return []
        if self._samples.size == 0:
            self._t0 = float(t0)
            self._rate = float(rate) or 1.0
        else:
            # a timestamp jump means the user seeked
            expect = self._time_at(self._samples.size)
            if abs(float(t0) - expect) > 1.5:
                self.reset()
                self._t0 = float(t0)
                self._rate = float(rate) or 1.0

        self._samples = np.concatenate([self._samples, pcm]) if self._samples.size else pcm.copy()
        out: List[Segment] = []
        thr = self._threshold()

        while self._pos + self.frame <= self._samples.size:
            block = self._samples[self._pos : self._pos + self.frame]
            level = float(np.sqrt(np.mean(np.square(block, dtype=np.float64))))
            voiced = level > thr
            if not self._speaking:
                # adapt the noise floor only while idle
                self._noise = 0.98 * self._noise + 0.02 * level
                self._noise = min(max(self._noise, 5e-5), 0.05)
                thr = self._threshold()

            if voiced:
                if not self._speaking:
                    self._speaking = True
                    self._seg_start = self._pos
                    self._speech_run = 0.0
                self._speech_run += self._frame_dur
                self._silence_run = 0.0
            elif self._speaking:
                self._silence_run += self._frame_dur

            if self._speaking:
                seg_seconds = (self._pos + self.frame - self._seg_start) / self.sr
                end_now = (
                    self._silence_run >= self.end_silence
                    and self._speech_run >= self.min_speech
                )
                hard_cut = seg_seconds >= self.max_segment and self._speech_run >= 0.3
                if end_now or hard_cut:
                    out.append(self._emit(self._pos + self.frame))
                    # buffer was sliced; restart scanning from the front
                    self._pos = 0
                    continue
            self._pos += self.frame

        # keep memory bounded if nobody ever speaks
        if not self._speaking and self._samples.size > self.sr * 2:
            keep = int(self.pre_roll * self.sr)
            cut = self._samples.size - keep
            self._t0 = self._time_at(cut)
            self._samples = self._samples[cut:].copy()
            self._pos = max(0, self._pos - cut)

        return out
